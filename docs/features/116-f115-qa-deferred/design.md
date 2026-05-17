# Design: F116 — F115 QA-Gate Deferred Hardening

**Source spec:** `docs/features/116-f115-qa-deferred/spec.md` rev 6
**Inherits from:** `docs/features/115-pd-data-model-followups/design.md` rev 2 (canonical evidence base)
**Status:** Draft rev 1
**Scope:** Coverage + observability. **Four** small code-surface additions (DiagnosticReport extension, `check_severity_vocab.py`, `check_cross_workspace_parent_uuid.py` file extraction, `_normalize_and_validate_fix_hint` helper) + ~25 new tests across 7 test files.

## 1. Prior Art Research

Per YOLO directive: research stage skipped. F115 design rev 2 is the canonical evidence base for cross-workspace gates, triage tool, severity vocabulary, M6/M7 migrations, and M15 audit counter. F116 inherits all F115 contracts (C7, C10, C13, C14, C15, C16, C17, C18) without re-derivation. Only the three F116 deltas below introduce new component surface.

Codebase patterns reused (verified at spec time, pinned in spec §5):
- `check_status_write_path.py` + `check_audit_counter_write_path.py` — AST visitor pattern for `check_severity_vocab.py` (FR-2)
- `_parse_triage_choice` + `_fix_triage_cross_workspace_link` — call-site for `_normalize_and_validate_fix_hint` (FR-9)
- `DiagnosticReport` dataclass at `models.py:37-46` — extension point for `severity_summary` (FR-1)
- `@pytest.mark.parametrize` + session-scoped fixtures — pattern for FR-3/FR-4/FR-6/FR-7 matrices

External research: not applicable — all coverage targets are internal pd plugin code.

## 2. Architecture Overview

F116 is a coverage + observability feature. The architectural footprint:

```
┌────────────────────────────────────────────────────────────────────┐
│ doctor/                                                             │
│  ├── models.py                                                      │
│  │    └── DiagnosticReport ── (FR-1) add severity_summary field    │
│  │         + default_factory                                        │
│  ├── __init__.py                                                    │
│  │    └── run_diagnostics() ── (FR-1) populate severity_summary    │
│  │         in DiagnosticReport(...) call site (line ~294)          │
│  │    └── CHECK_ORDER ── (FR-2) append check_severity_vocab        │
│  │         at position 20                                           │
│  │    └── import ── (FR-8) re-source check_cross_workspace_parent_uuid│
│  │         from its own module                                      │
│  ├── checks.py                                                      │
│  │    └── (FR-8) DELETE check_cross_workspace_parent_uuid           │
│  ├── check_severity_vocab.py ── (FR-2) NEW FILE                    │
│  │    AST visitor: rejects severity= kwarg Constant outside         │
│  │    {error, warning, info}                                        │
│  ├── check_cross_workspace_parent_uuid.py ── (FR-8) NEW FILE       │
│  │    Function moved verbatim from checks.py                        │
│  └── fix_actions/__init__.py                                        │
│       └── _normalize_and_validate_fix_hint() ── (FR-9) NEW         │
│            Defensive segment-aware parser; ValueError on rejection  │
│       └── _fix_triage_cross_workspace_link ── (FR-9) call         │
│            normalizer before _parse_triage_choice                   │
│                                                                     │
│ tests (new + extended):                                             │
│  ├── doctor/test_severity_summary.py            ── (FR-1)         │
│  ├── doctor/test_check_severity_vocab.py        ── (FR-2)         │
│  ├── doctor/test_doctor.py                       ── (FR-8)         │
│  │    test_check_order_preserved_post_f116                         │
│  ├── doctor/test_fix_actions.py                  ── (FR-7, FR-9)  │
│  ├── semantic_memory/test_database.py            ── (FR-3, FR-4)   │
│  └── entity_registry/test_database.py            ── (FR-5)         │
│  └── entity_registry/test_cross_workspace_matrix.py ── (FR-6)     │
└────────────────────────────────────────────────────────────────────┘
```

**Production code delta:** 3 new files + 4 modified files. Test delta: ~25 new test functions across 7 test files.

## 3. Components

### C16-116 — `severity_summary` rollup (FR-1)

**Location:** `doctor/models.py:37-46` (DiagnosticReport) + `doctor/__init__.py` `run_diagnostics()` (construction site near line 294).

**Dataclass extension:**
```python
@dataclass
class DiagnosticReport:
    healthy: bool
    checks: list[CheckResult]
    total_issues: int
    error_count: int
    warning_count: int
    severity_summary: dict[str, int] = field(
        default_factory=lambda: {"error": 0, "warning": 0, "info": 0}
    )
    elapsed_ms: int = 0
```

**Population (in `run_diagnostics`):**
```python
sev = {"error": 0, "warning": 0, "info": 0}
for cr in check_results:
    for issue in cr.issues:
        if issue.severity in sev:
            sev[issue.severity] += 1
report = DiagnosticReport(
    healthy=...,
    checks=check_results,
    total_issues=...,
    error_count=...,
    warning_count=...,
    severity_summary=sev,
    elapsed_ms=...,
)
```

**Design invariants:**
- `severity_summary["error"] == error_count` always (both count error-severity issues from same `check_results` source).
- `severity_summary["warning"] == warning_count` always.
- `severity_summary["info"]` is new — no legacy field to compare against.
- Skipped-check synthetic error issues (from `_make_failed_result`) ARE included because they pass through the same `check_results` aggregation path.

**Failure modes:** None at component level (additive field with defaults).

### C19-116 — `check_severity_vocab` AST audit (FR-2)

**Location:** New file `doctor/check_severity_vocab.py`. Pattern matches `check_audit_counter_write_path.py` (F115 C10-115.4) and `check_status_write_path.py` (F109).

**Interface (matches existing doctor check contract — verified against `check_status_write_path` and `check_audit_counter_write_path`):**
```python
def check_severity_vocab(
    project_root: str | None = None,
    **_kwargs: object,
) -> CheckResult:
    """AST audit: reject doctor-check files emitting severity literals
    outside {error, warning, info}.

    Scans doctor/checks.py + doctor/check_*.py (excluding test files).
    Returns CheckResult with Issue(severity='error') per violation.
    """
```

Doctor dispatch at `doctor/__init__.py:261` calls `check_fn(**ctx)` where `ctx` does NOT contain a `db` key — only `project_root`, `entities_conn`, etc. Signature uses `**_kwargs` to absorb the unused ones.

**Source-file resolution (plugin-portability per CLAUDE.md):** The check uses `__file__`-relative resolution to locate sibling doctor source files:
```python
doctor_dir = pathlib.Path(__file__).parent
candidates = [doctor_dir / "checks.py"] + sorted(doctor_dir.glob("check_*.py"))
```
This works portably whether pd is installed as a plugin (under `~/.claude/plugins/cache/*/pd*/*/hooks/lib/doctor/`) or in the dev workspace (`plugins/pd/hooks/lib/doctor/`) — `__file__` always points to the executing file's location.

**AST visitor (spec §3 FR-2 verbatim):**
- Walk `ast.Call` nodes.
- For each `keyword` where `kw.arg == 'severity'` AND `isinstance(kw.value, ast.Constant)` AND `isinstance(kw.value.value, str)`:
  - If `kw.value.value not in {"error", "warning", "info"}` → emit Issue.
- Line number folded into `message` (Issue dataclass has no `line` field).

**Scope limitation:** Keyword arguments only. Positional severity is not inspected (acceptable — all current call sites use kwargs; grep-verified).

**Registration:** Append to `CHECK_ORDER` in `doctor/__init__.py` at position 20 (after F115's 19 checks). NOT a member of `_ENTITY_DB_CHECKS` or `_MEMORY_DB_CHECKS` (needs neither DB).

**Failure modes:**
- Source file not found → return empty issues list (defensive — failure is opaque to caller).
- AST parse error → emit single Issue with severity='error', message='AST parse failed: {path}' (matches `check_status_write_path` pattern).

### C20-116 — `check_cross_workspace_parent_uuid` standalone module (FR-8)

**Location:** Function moved verbatim from `doctor/checks.py:2259` to new file `doctor/check_cross_workspace_parent_uuid.py`.

**Refactor mechanics:**
1. `git mv` is NOT applicable (the source has many other functions). Manual move:
   - Read `check_cross_workspace_parent_uuid` body from `checks.py:2259+` (function definition + all imports it uses).
   - Create `doctor/check_cross_workspace_parent_uuid.py` with module docstring + imports + function body verbatim.
   - Delete the function from `checks.py`.
2. Update `doctor/__init__.py:25` import: replace `from .checks import check_cross_workspace_parent_uuid` with `from .check_cross_workspace_parent_uuid import check_cross_workspace_parent_uuid`.

**Invariants:**
- `CHECK_ORDER` byte-identical sequence post-refactor (regression test in `test_doctor.py`).
- `_ENTITY_DB_CHECKS` membership preserved.
- No behavior change — function body bytes identical to current `checks.py:2259+`.

**Failure modes:** None (pure code-organization refactor).

### C21-116 — `_normalize_and_validate_fix_hint` defensive parser (FR-9)

**Location:** New helper in `doctor/fix_actions/__init__.py` (added near `_parse_triage_choice` at line ~395). Call site: `_fix_triage_cross_workspace_link` line 445.

**Interface:**
```python
def _normalize_and_validate_fix_hint(fix_hint: str | None) -> str:
    """Defensive normalizer + grammar validator for fix_hint inputs.

    Returns NFC-normalized, whitespace-stripped string.
    Raises ValueError (existing exception class) on:
      - utf-8 byte length > 1024
      - uuid-segment containing non-hex/non-dash characters
      - choice-segment containing chars outside [a-zA-Z- ]
      - reason-segment containing control chars or shell metas ($, \\, `)
      - unknown top-level segment
    """
```

**Segment-aware grammar:**
- Split on `|`.
- Head segment: matches `triage_cross_workspace_links:<uuid>:<uuid>`. UUID-like chars only (hex + dash).
- `choice:<value>` segment: value matches `^[a-zA-Z\- ]+$` (4 known choices all conform).
- `reason:<value>` segment: free text MINUS denylist `[\x00-\x1f;&()`$\\]` (covers control chars + all shell metas listed in PRD §3 FR-9: `;|&\`$()`). Note `|` is the segment separator so a literal `|` would split into a new segment, not embedded — no separate denial needed.
- Any other segment prefix → `ValueError("fix_hint contains unknown segment: ...")`.

**Integration with `_fix_triage_cross_workspace_link`:**
```python
# Line 445 (before normalization):
#   choice_info = _parse_triage_choice(issue.fix_hint)
# Line 445 (after FR-9):
normalized_hint = _normalize_and_validate_fix_hint(issue.fix_hint)
choice_info = _parse_triage_choice(normalized_hint)
```

Normalizer returns a NEW string; does NOT mutate `issue.fix_hint`. On rejection, raises before `_parse_triage_choice` is called.

**Failure modes:**
- Legitimate inputs with leading/trailing whitespace → normalized (stripped) silently. Existing harness happy-path tests must remain green.
- Operator types unicode confusable in UUID → rejected with `ValueError("invalid character in uuid field")`.
- Operator types shell-meta in reason → rejected. Reason field already free-text but tightening denylist is acceptable scope-creep (PRD §3 FR-9 explicitly scopes this as "defensive parser layer").
- Bypass risk: if a second call site of `_parse_triage_choice` is added later, that path bypasses normalization. Mitigated by Empirical Pin §5 (1 call site verified) + CHANGELOG entry requirement.

## 4. Interfaces

### IF-116-1: DiagnosticReport.severity_summary

```python
# Input: DiagnosticReport instance
# Output: dict[str, int] with keys exactly {"error", "warning", "info"}
report.severity_summary
# {"error": 2, "warning": 5, "info": 0}
```

**Contract:**
- Always present (default_factory ensures non-None).
- Keys are exactly `{"error", "warning", "info"}` (closed set).
- Values are non-negative integers.
- Invariant: `report.severity_summary["error"] == report.error_count` AND `report.severity_summary["warning"] == report.warning_count`.

### IF-116-2: check_severity_vocab

```python
# Signature (matches doctor check contract — see _make_failed_result for shape):
check_severity_vocab(
    db: EntityDatabase | None,
    *,
    project_root: pathlib.Path,
    artifacts_root: pathlib.Path | None,
    **_kwargs,
) -> CheckResult
```

**Contract:**
- `name`: "check_severity_vocab"
- `passed`: True iff no issues.
- `issues`: list of `Issue(severity='error', ...)` — one per violating source location.
- `elapsed_ms`: time to scan + parse.

### IF-116-3: _normalize_and_validate_fix_hint

```python
def _normalize_and_validate_fix_hint(fix_hint: str | None) -> str
```

**Contract:**
- Returns NFC-normalized, whitespace-stripped string.
- Raises `ValueError` (existing class) on rejection.
- Idempotent: `f(f(x)) == f(x)` for any accepted `x`.
- Empty/None input → returns `""` (no rejection).

## 5. Technical Decisions

| # | Decision | Alternatives considered | Rationale |
|---|---|---|---|
| TD-1 | Use `field(default_factory=...)` for `severity_summary` | (a) required field, breaking 5+ existing call sites; (b) `Optional[dict]` defaulting to None then populated post-construction | Non-breaking; downstream consumers who forget to populate get zero-counts which AC-1.4 invariant test catches |
| TD-2 | Fold AST line number into `Issue.message` instead of extending `Issue` dataclass | Add `line: int \| None = None` field to Issue | Avoids cross-cutting Issue change touching all checks; line in message is searchable via grep and human-readable |
| TD-3 | Move `check_cross_workspace_parent_uuid` via manual read+write rather than `git mv` | `git mv checks.py check_cross_workspace_parent_uuid.py` then strip other content | Source file has many other functions; `git mv` would require subsequent surgery |
| TD-4 | Reuse `ValueError` for FR-9 rejection instead of new `InvalidFixHintError` class | Introduce typed exception | Matches existing pattern (`_parse_triage_choice` already raises ValueError at lines 450, 455, 499); avoids cross-cutting exception class addition |
| TD-5 | Segment-aware grammar (FR-9) rather than blanket char allowlist | Strict allowlist for all chars | Blanket allowlist rejects legitimate grandfather reasons like "operator approved cross-org link" (contains spaces, lowercase, apostrophes); segment-aware preserves reason free-text while locking UUID + choice segments |
| TD-6 | Test fixture replays migrations 1..5 directly against raw sqlite3.Connection rather than instantiating `MemoryDatabase` | Use `MemoryDatabase` then rewind | M6/M7 are the tests' subjects — using the class runs them first; replaying individual migrations isolates them |
| TD-7 | `_build_memory_db_at_v6` stamps schema_version='6' WITHOUT running M6 body | Run M6 then test M7 | M6 has its own gates that could fail before M7 testing begins; manual stamp isolates M7 tests |

## 6. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-1 | Forgotten `severity_summary` population at construction site silently emits zero counts | AC-1.4 invariant test: `report.severity_summary["error"] == report.error_count` |
| R-2 | FR-8 refactor disturbs `CHECK_ORDER` ordering during file move | Regression test in `test_doctor.py` asserts full 20-name byte-identical sequence |
| R-3 | FR-9 normalizer rejects legitimate-but-large `fix_hint` (>1024 bytes) | §13 pre-implementation grep validates max-observed length in source; raise cap if needed |
| R-4 | FR-9 grammar tightens reason field behavior — control chars + shell metas now rejected (previously accepted) | AC-9.3 happy-path test for "operator approved cross-org link" verifies common-case regression-free |
| R-5 | Test fixture `_build_memory_db_at_v5` fails because individual migrations expect kwargs the test doesn't pass | Spec pins call signature `MIGRATIONS[v](conn, fts5_available=True)` — verified against production runner at `semantic_memory/database.py:1510` |
| R-6 | `_seed_tool_failure_rows` IntegrityError because of unstated NOT NULL columns | Spec rev 7 lists exact post-M3 NOT NULL columns: `id`, `name`, `description`, `category`, `source`, `source_hash`, `created_at`, `updated_at` (verified via Migration 3 entries_new at `:255-259`); seed helpers now compute `source_hash = sha256(description)[:16]` deterministically |
| R-9 | M15 own-transaction conflicts with caller's implicit tx in default `sqlite3.connect()` mode | Spec rev 7 opens connections with `isolation_level=None` (autocommit) for FR-5 test, eliminating the implicit-tx collision; M15's BEGIN IMMEDIATE runs without conflict |
| R-7 | AST check false positive on dynamic severity construction | AST visitor narrowly scoped: requires `Constant(value=str)` in `severity=` kwarg — dynamic constructions (variable assignments, function calls) pass through |
| R-8 | `_make_fix_ctx` test helper drifts as `FixContext` dataclass evolves | Spec pins all 8 fields; if `FixContext` schema changes, FR-7/FR-9 tests fail loudly (TypeError) rather than silently — acceptable |

## 7. Component Mapping to Spec FRs

| Spec FR | Component(s) | Test files |
|---|---|---|
| FR-1 severity rollup | C16-116 | `test_severity_summary.py` (new) |
| FR-2 vocab AST check | C19-116 | `test_check_severity_vocab.py` (new) |
| FR-3 M6 abort tests | (test only) | `semantic_memory/test_database.py` extended |
| FR-4 M7 abort test | (test only) | `semantic_memory/test_database.py` extended |
| FR-5 M15 rerun safety | (test only) | `entity_registry/test_database.py` extended |
| FR-6 9-case matrix | (test only) | `entity_registry/test_cross_workspace_matrix.py` (new) |
| FR-7 4-decision triage | (test only) | `doctor/test_fix_actions.py` (new) |
| FR-8 helper file extraction | C20-116 | `doctor/test_doctor.py::test_check_order_preserved_post_f116` |
| FR-9 adversarial parser | C21-116 | `doctor/test_fix_actions.py` (extended) |

## 8. Implementation Sequencing (TDD-oriented)

**Pre-implementation gate (C0):** Before Theme C, run spec §13 pre-implementation grep audit:
- FM-2: grep audit_log + source for max-observed `fix_hint` length. If observed > 800 bytes, raise `_MAX_LEN` cap above 1024 before implementing C21-116.
- FM-7: `grep -c "_parse_triage_choice(" plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` → expect 2 (definition + 1 call). If > 2, expand FR-9 integration to cover all call sites.

**Sequencing:**
- **Theme A** (FR-1, FR-2): DiagnosticReport extension + check_severity_vocab AST check.
- **Theme B** (FR-3, FR-4, FR-5): Migration abort-path tests (pure test additions — no production code).
- **C0 pre-implementation gate.**
- **Theme C** (FR-8 → FR-6 → FR-7 + FR-9):
  - FR-8 first (file extraction refactor — pin CHECK_ORDER post-refactor).
  - FR-6 (9-case matrix — pure test addition).
  - FR-7 + FR-9 together (triage tests + defensive parser; FR-9 helper integrates into the same fix function FR-7 exercises).

Within each theme, write tests first (per TDD) then implement the component.

## 9. Failure Mode Analysis

**FM-1: Forgotten DiagnosticReport population (R-1)**
- Detection: AC-1.4 invariant test.
- Impact: Silent zero-count; downstream consumers see misleading metric.
- Mitigation: Test must run before merge.

**FM-2: CHECK_ORDER drift after FR-8 (R-2)**
- Detection: AC-2.1 (full sequence assertion).
- Impact: Doctor check ordering shifts; affects log output but not behavior.
- Mitigation: Test must run before merge.

**FM-3: FR-9 over-rejection (R-3, R-4)**
- Detection: AC-9.3 happy-path regression test.
- Impact: Triage tool rejects legitimate operator input; user can't grandfather links.
- Mitigation: AC-9.3 + spec §13 pre-implementation grep audit.

**FM-4: Migration test fixtures fail to compile (R-5, R-6)**
- Detection: Initial test run fails before any test passes.
- Impact: Blocks Theme B implementation.
- Mitigation: Spec pins exact column lists + migration runner kwargs.

## 10. Out of Scope (Inherited from Spec)

- New MCP tools / new migrations / new exception classes (per F115 inheritance + behavioral constraints).
- M15 INSERT-OR-IGNORE conversion (FR-5 documents existing INSERT-OR-REPLACE reset semantics, does not modify).
- Dynamic `max(MIGRATIONS.keys())` test-fixture refactor (F115 retro KB candidate #6).
- Audit log table for fix_hint persistence (FM-2 grep uses source-code occurrences instead).

## 11. Reviewer Inheritance Note

F115 design rev 2 reviewers (3 rounds, 4 blockers + 5 warnings + 1 suggestion) already validated the upstream C7, C10, C13, C14, C15, C16, C17, C18 components. F116 design REUSES those components without modification — only the 3 new components (C16-116, C19-116, C20-116, C21-116) require fresh review. Reviewer effort should focus there.
