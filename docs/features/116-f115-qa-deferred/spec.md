# Spec: F115 QA-Gate Deferred Hardening (Feature 116)

**Source PRD:** `docs/features/116-f115-qa-deferred/prd.md` (rev 2)
**Inherits from:** `docs/features/115-pd-data-model-followups/{spec,design,tasks,retro}.md`
**Status:** Draft rev 2 (addresses spec-reviewer iteration 1 blockers)
**Coverage themes:** A (severity rollup + vocab AST) → B (migration regression) → C (cross-workspace coverage completeness)

## 1. Problem Restated

F115's post-merge 4-reviewer adversarial QA gate identified **8 HIGH-severity coverage and observability gaps** that were deferred via `qa-override.md` (rather than blocking the F115 merge). F115's structural invariants hold; F116 closes the 8 gaps without introducing new functional surface — except for two explicitly-scoped additions: (1) standalone module file `check_cross_workspace_parent_uuid.py` (per F115 T2b.6 plan that F115 implementation parked inline), and (2) internal defensive parser helper `_normalize_and_validate_fix_hint` in `fix_actions/__init__.py`. **No new MCP tools, no new migrations, no new exception classes.**

## 2. Inheritance Map

F115's spec rev 1 + design rev 2 + tasks are the canonical evidence base. F116 inherits and extends only where the QA gate findings dictate.

| F115 section | F116 status | Reason |
|---|---|---|
| F115 §3 FR-C-115.1 (atomic same-commit emit) | **INHERITED, no changes** | F116 only adds tests around current behavior |
| F115 §3 FR-E.1-.4 (cross-workspace gates + envelope) | **INHERITED + 9-case matrix (FR-6)** | Matrix exercises existing behavior |
| F115 §3 FR-E.5 (warning-only doctor check) | **INHERITED + standalone file (FR-8)** | T2b.6 planned standalone file but parked inline |
| F115 §3 FR-E.2.1-.3 (triage tool) | **INHERITED + 4-decision tests (FR-7) + adversarial parser tests (FR-9)** | Coverage of existing branches |
| F115 §3 FR-Sev (severity_summary contract) | **EXTENDED (FR-1, FR-2)** | Rollup field absent; AST check missing |
| F115 §3 FR-B-H4-115.1/.3 (M6/M7 bounded-count + identity spot-check) | **INHERITED + abort-path tests (FR-3, FR-4)** | Existing behavior pinned by new tests |
| F115 §3 FR-C-115.3 (M15 counter init) | **EXTENDED — re-run safety test (FR-5)** | Documents actual INSERT-OR-REPLACE semantics |

## 3. Functional Requirements (F116 deltas)

### FR-1 — Severity Rollup (closes qa-override item 1)

**Implementation location:** Extend `DiagnosticReport` dataclass in `plugins/pd/hooks/lib/doctor/models.py:38-46` with a new field `severity_summary: dict[str, int]`. This is an additive change — `error_count` and `warning_count` are preserved for backwards compatibility of downstream JSON consumers.

```python
@dataclass
class DiagnosticReport:
    healthy: bool
    checks: list[CheckResult]
    total_issues: int
    error_count: int
    warning_count: int
    severity_summary: dict[str, int]   # NEW — {"error": N, "warning": N, "info": N}
    elapsed_ms: int
```

**Population location:** In whatever code path constructs `DiagnosticReport` (search `DiagnosticReport(` to locate, expected in `doctor/__init__.py`).

**Aggregation rule:**

```python
severity_summary = {
    k: sum(1 for cr in checks for i in cr.issues if i.severity == k)
    for k in ("error", "warning", "info")
}
```

- Block present even when all counts are 0 (no conditional omission).
- Skipped-check synthetic error issues (produced by `_make_failed_result` at `doctor/__init__.py:93-111`; Issue construction at lines 102-108) ARE counted in `severity_summary.error`. Operational rationale: infrastructure failures must surface.
- **No `total` field** — consumers compute via jq.
- Invariant: `severity_summary["error"] == error_count` AND `severity_summary["warning"] == warning_count`. (Verified by AC-1.4.)

JSON output shape (top-level wraps in `{"diagnostic": ...}` per `doctor/__main__.py:85`):
```json
{"diagnostic": {
  "healthy": true,
  "checks": [...],
  "total_issues": 5,
  "error_count": 2,
  "warning_count": 3,
  "severity_summary": {"error": 2, "warning": 3, "info": 0},
  "elapsed_ms": 142
}}
```

### FR-2 — Severity Vocab AST Check (closes qa-override items 1 + 4)

New file `plugins/pd/hooks/lib/doctor/check_severity_vocab.py`. AST visitor:

```python
import ast, pathlib, re

CLOSED_SET = {"error", "warning", "info"}
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")

def _scan_targets(plugin_root: pathlib.Path) -> list[pathlib.Path]:
    """Return doctor check files to scan (excludes test files)."""
    doctor_dir = plugin_root / "hooks" / "lib" / "doctor"
    candidates = [doctor_dir / "checks.py"]
    candidates += list(doctor_dir.glob("check_*.py"))
    return [p for p in candidates if not _TEST_FILE_RE.search(str(p))]
```

For each scanned file:
1. Parse to `ast.Module`.
2. Walk; for each `ast.Call`, iterate `node.keywords`.
3. If `kw.arg == "severity"` AND `isinstance(kw.value, ast.Constant)` AND `isinstance(kw.value.value, str)` AND `kw.value.value not in CLOSED_SET`:
4. Emit `Issue(check="check_severity_vocab", severity="error", entity=str(path), message=f"line {kw.value.lineno}: severity={kw.value.value!r} outside closed set {CLOSED_SET}", fix_hint=f"change to one of {sorted(CLOSED_SET)}")`. **Line number is folded into `message`** because `Issue` dataclass has no `line` field (verified at `models.py:7-15`).

**Registration:** Append `check_severity_vocab` to `CHECK_ORDER` in `doctor/__init__.py:41-70` as position 20 (after the F115 `check_audit_emit_failed_count` at line 69). Also append `"check_severity_vocab"` to no membership sets (it requires neither entity nor memory DB; runs against source files only).

**Failure mode:** Emits `Issue(severity="error")`. Session-start does NOT abort. `validate.sh` is the CI enforcement layer (existing convention; matches `check_status_write_path` and `check_audit_counter_write_path`).

### FR-3 — M6 Abort-Path Regression Tests (closes qa-override item 2)

**Symbol pin:** M6 entry point is `_migration_6_unify_source_hash_and_cleanup` (verified at `plugins/pd/hooks/lib/semantic_memory/database.py:330`).

**Fixture contract (new helper to add to test module):**

```python
def _build_memory_db_at_v5(tmp_path) -> pathlib.Path:
    """Build a memory.db stamped at schema_version=5 with the schema in place.

    Returns path to the DB file. Caller adds rows as needed for each test.
    Uses the same migration runner used by production code: invoke migrations
    1..5 explicitly via _migrate(conn, target_version=5) and stop.
    """
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    # Apply migrations 1..5 (final pre-M6 state)
    from semantic_memory.database import MIGRATIONS, _migrate
    _migrate(conn, target_version=5)
    conn.commit()
    conn.close()
    return db_path

def _seed_tool_failure_rows(db_path: pathlib.Path, count: int, created_at: str) -> None:
    """Insert N rows matching M6's DELETE predicate at the given created_at.

    Schema columns: name, description, source, created_at (plus others).
    Predicate: source='session-capture' AND name LIKE 'Tool failure:%'.
    """
    with sqlite3.connect(db_path) as conn:
        for i in range(count):
            conn.execute(
                "INSERT INTO entries (name, description, source, source_hash, "
                "category, confidence, created_at, observation_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"Tool failure: seed-{i}", "seed body", "session-capture",
                 "0"*16, "anti-patterns", 0.5, created_at, 1),
            )
        conn.commit()

def _read_schema_version(db_path: pathlib.Path) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    return row[0] if row else None
```

**T3b.3a — bounded-count abort:**

```python
@pytest.mark.parametrize("seed_count,direction", [
    (600, "above"),   # 600 > expected_max 518
    (300, "below"),   # 300 < expected_min 418
])
def test_m6_aborts_on_bounded_count_violation(tmp_path, seed_count, direction):
    db_path = _build_memory_db_at_v5(tmp_path)
    _seed_tool_failure_rows(db_path, seed_count, created_at='2026-05-01T00:00:00')
    pre_version = _read_schema_version(db_path)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(RuntimeError, match=r"bounded.count"):
            _migration_6_unify_source_hash_and_cleanup(conn)
    assert _read_schema_version(db_path) == pre_version
```

**T3b.3b — pre-freeze temporal-anchor ratio abort:**

```python
def test_m6_aborts_on_pre_freeze_ratio_violation(tmp_path):
    """Seed exactly 425 pre-freeze rows + 25 post-freeze rows = 450 total.
    Total 450 falls within bounded-count [418, 518], so bounded gate passes.
    Pre-freeze ratio = 425/450 = 0.9444 < 0.95, triggering identity spot-check."""
    db_path = _build_memory_db_at_v5(tmp_path)
    _seed_tool_failure_rows(db_path, 425, created_at='2026-05-01T00:00:00')   # pre-freeze
    _seed_tool_failure_rows(db_path, 25,  created_at='2026-05-17T00:00:00')   # post-freeze
    pre_version = _read_schema_version(db_path)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(RuntimeError, match=r"(identity spot.check|pre.freeze)"):
            _migration_6_unify_source_hash_and_cleanup(conn)
    assert _read_schema_version(db_path) == pre_version
```

**T3b.3c — sqlite3.OperationalError propagation (NOT outer-runner rollback verification):**

The test verifies that `OperationalError` injected on the first `DELETE FROM entries` propagates uncaught from M6. It does NOT directly verify the production runner's outer-transaction rollback (which happens at `_migrate()`-level via the runner's outer `BEGIN IMMEDIATE`). Per F115 pin: M6 runs INSIDE the runner's outer transaction (see `semantic_memory/database.py` M6 docstring). Outer-runner rollback is an inherited F115 invariant.

```python
class _MidTxFailingConnection:
    """Proxy a Connection so the first DELETE FROM ENTRIES raises OperationalError.

    Full delegation surface: execute, executemany, executescript, cursor,
    commit, rollback, close, __enter__, __exit__, in_transaction.
    """
    def __init__(self, real_conn):
        self._real = real_conn
        self._injected = False

    def execute(self, sql, *args, **kwargs):
        if (not self._injected) and sql.strip().upper().startswith("DELETE FROM ENTRIES"):
            self._injected = True
            raise sqlite3.OperationalError("injected mid-tx failure")
        return self._real.execute(sql, *args, **kwargs)

    def executemany(self, *a, **kw): return self._real.executemany(*a, **kw)
    def executescript(self, *a, **kw): return self._real.executescript(*a, **kw)
    def cursor(self): return self._real.cursor()
    def commit(self): return self._real.commit()
    def rollback(self): return self._real.rollback()
    def close(self): return self._real.close()
    def __enter__(self): return self
    def __exit__(self, *a): return self._real.__exit__(*a)
    @property
    def in_transaction(self): return self._real.in_transaction

def test_m6_operational_error_propagates_uncaught(tmp_path):
    """Per Empirical Pin §5: M6 Op 1 (DELETE) executes BEFORE Op 2 (recompute).
    Injection on first DELETE thus fires before recompute_all_with_conn.
    M6 has NO try/except for OperationalError — verified at M6 body."""
    db_path = _build_memory_db_at_v5(tmp_path)
    _seed_tool_failure_rows(db_path, 450, created_at='2026-05-01T00:00:00')
    pre_version = _read_schema_version(db_path)
    pre_rowcount = _count_entries(db_path)
    raw_conn = sqlite3.connect(db_path)
    try:
        proxied = _MidTxFailingConnection(raw_conn)
        with pytest.raises(sqlite3.OperationalError, match="injected mid-tx failure"):
            _migration_6_unify_source_hash_and_cleanup(proxied)
        # Rollback uncommitted state to simulate runner's outer rollback
        raw_conn.rollback()
    finally:
        raw_conn.close()
    assert _read_schema_version(db_path) == pre_version
    assert _count_entries(db_path) == pre_rowcount
```

### FR-4 — M7 Abort-Path Regression Test (T3b.4)

**Symbol pin:** M7 entry point is `_migration_7_reset_inflated_observation_count` (verified at `plugins/pd/hooks/lib/semantic_memory/database.py:435`).

```python
def test_m7_aborts_on_bounds_violation(tmp_path):
    """Seed memory.db at v6 with observation_count outside M7's bound."""
    db_path = _build_memory_db_at_v6(tmp_path)  # similar helper to _build_memory_db_at_v5
    # Seed pattern that violates M7's bound — concrete count + observation_count
    # value pinned in the test docstring; matches M7's actual gate predicate.
    pre_version = _read_schema_version(db_path)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(RuntimeError):
            _migration_7_reset_inflated_observation_count(conn)
    assert _read_schema_version(db_path) == pre_version
```

**Implementation note:** Spec phase pins the M7 gate predicate by reading `semantic_memory/database.py:435+` body during implementation; the concrete seed shape (N inflated rows) is determined by the bound at implement-time and documented in the test docstring.

### FR-5 — M15 Re-Run Safety Test (T1.10)

**Symbol pin:** M15 entry point is `_migration_15_audit_emit_counter` (verified at `plugins/pd/hooks/lib/entity_registry/database.py:5404`). M15 owns its **own** `BEGIN IMMEDIATE` (line 5412) — unlike M6/M7 which inherit the runner transaction.

```python
def test_m15_safe_to_rerun_with_documented_reset_semantics(tmp_path):
    """Documents M15's INSERT-OR-REPLACE re-run semantics.

    Per database.py:5412, M15 owns its OWN BEGIN IMMEDIATE (unlike M6/M7).
    Migration runner contiguity (range(current+1, target+1)) prevents M15
    re-invocation in production. This test exercises the recovery path:
    rewind schema_version to '14' then re-run M15.

    Expected: no exception; counter resets to '0' (INSERT OR REPLACE).
    This is safe-to-re-run semantics, NOT value-preservation.
    """
    db_path = _build_entities_db_at_v14(tmp_path)  # helper: stamp v14 + create _metadata
    with sqlite3.connect(db_path) as conn:
        _migration_15_audit_emit_counter(conn)
        # Bump counter to verify reset is observable
        conn.execute(
            "UPDATE _metadata SET value='7' WHERE key='audit_emit_failed_count'"
        )
        conn.execute("UPDATE _metadata SET value='14' WHERE key='schema_version'")
        conn.commit()
    # Re-run M15
    with sqlite3.connect(db_path) as conn:
        _migration_15_audit_emit_counter(conn)
    # Assert reset (NOT preservation)
    with sqlite3.connect(db_path) as conn:
        counter = conn.execute(
            "SELECT value FROM _metadata WHERE key='audit_emit_failed_count'"
        ).fetchone()[0]
        version = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
    assert counter == "0", "INSERT OR REPLACE reset; not value-preserving"
    assert version == "15"
```

### FR-6 — T2b.5 9-Case Cross-Workspace Matrix (3 handlers × 3 ACs)

Tests invoke the **database.py-layer functions** (`db.set_parent_uuid`, `db.add_dependency`, `db.add_okr_alignment`) NOT the MCP server entry points — isolates gate behavior from MCP runtime availability, matches F115 design rev 2 contract.

```python
HANDLERS = [
    ("set_parent",      lambda db, p, c: db.set_parent_uuid(c, p)),
    ("add_dependency",  lambda db, p, c: db.add_dependency(p, c, kind="depends_on")),
    ("add_okr_alignment", lambda db, p, c: db.add_okr_alignment(p, c)),
]

@pytest.mark.parametrize("handler_name,handler_fn", HANDLERS)
@pytest.mark.parametrize("ac,pair_fixture,expected", [
    ("AC-E.1_cross_ws_rejected",  _cross_ws_pair_fixture,  pytest.raises(CrossWorkspaceError)),
    ("AC-E.2_same_ws_succeeds",   _same_ws_pair_fixture,   contextlib.nullcontext()),
    ("AC-E.3_allowlisted_succeeds", _allowlisted_pair_fixture, contextlib.nullcontext()),
])
def test_t2b_5_cross_workspace_gate_matrix(
    entities_db_session, handler_name, handler_fn, ac, pair_fixture, expected
):
    parent_uuid, child_uuid = pair_fixture(entities_db_session)
    with expected:
        handler_fn(entities_db_session, parent_uuid, child_uuid)
```

**Fixture contracts (new helpers in `plugins/pd/hooks/lib/entity_registry/test_cross_workspace_matrix.py` — new file):**
- `entities_db_session` (session-scoped): builds an entities.db with 3 pre-seeded workspaces (workspace_A, workspace_B, workspace_C) and seeded entities (1 feature + 1 backlog per workspace). Resets between cases via SAVEPOINT.
- `_cross_ws_pair_fixture(db)`: returns `(feature_in_A, backlog_in_B)`.
- `_same_ws_pair_fixture(db)`: returns `(feature_in_A, backlog_in_A)`.
- `_allowlisted_pair_fixture(db)`: returns `(feature_in_A, backlog_in_B)` AFTER inserting a row into `cross_workspace_allowlist`.

### FR-7 — T2a.7 4-Decision Triage Tests

New file `plugins/pd/hooks/lib/doctor/test_fix_actions.py`. Parametrized 4-branch coverage of `_fix_triage_cross_workspace_link` (verified branches at `fix_actions/__init__.py:472-499`):

```python
TRIAGE_CASES = [
    ("re-attribute parent", _assert_parent_moved_to_child_ws),
    ("re-attribute child",  _assert_child_moved_to_parent_ws),
    ("delete relation",     _assert_parent_uuid_set_null),
    ("grandfather",         _assert_allowlist_row_inserted_with_reason),
]

@pytest.mark.parametrize("choice,assertion", TRIAGE_CASES)
def test_t2a_7_triage_branch(entities_db_session, choice, assertion):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    reason = "operator approved cross-org link"
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:{choice}"
        f"|reason:{reason}"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="cross-workspace link",
        fix_hint=fix_hint,
    )
    ctx = FixContext(entities_conn=entities_db_session)
    _fix_triage_cross_workspace_link(ctx, issue)
    assertion(entities_db_session, parent_uuid, child_uuid, reason)
```

**Assertion helpers** (verify exact SQL from `fix_actions/__init__.py:472-499`):
- `_assert_parent_moved_to_child_ws`: `SELECT workspace_uuid FROM entities WHERE uuid=?` returns child's workspace_uuid for parent_uuid.
- `_assert_child_moved_to_parent_ws`: same query returns parent's workspace_uuid for child_uuid.
- `_assert_parent_uuid_set_null`: `SELECT parent_uuid FROM entities WHERE uuid=?` returns NULL for child_uuid.
- `_assert_allowlist_row_inserted_with_reason`: `SELECT reason FROM cross_workspace_allowlist WHERE parent_uuid=? AND child_uuid=?` returns the supplied `reason`.

**Sub-case for grandfather without reason:**

```python
def test_t2a_7_grandfather_without_reason_uses_fallback(entities_db_session):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}|choice:grandfather"
    )  # no reason: field
    issue = Issue(check="check_cross_workspace_parent_uuid", severity="warning",
                  entity=child_uuid, message="x", fix_hint=fix_hint)
    _fix_triage_cross_workspace_link(FixContext(entities_conn=entities_db_session), issue)
    with entities_db_session as conn:
        row = conn.execute(
            "SELECT reason FROM cross_workspace_allowlist WHERE parent_uuid=? AND child_uuid=?",
            (parent_uuid, child_uuid),
        ).fetchone()
    assert row[0] == "operator-grandfathered (no reason supplied)"
```

**Negative case — unknown choice:**

```python
def test_t2a_7_unknown_choice_raises_value_error(entities_db_session):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}|choice:bogus"
    )
    issue = Issue(check="check_cross_workspace_parent_uuid", severity="warning",
                  entity=child_uuid, message="x", fix_hint=fix_hint)
    with pytest.raises(ValueError, match="Unknown triage choice"):
        _fix_triage_cross_workspace_link(FixContext(entities_conn=entities_db_session), issue)
```

### FR-8 — Standalone Helper File Extraction (per F115 T2b.6)

**Refactor:** Move `check_cross_workspace_parent_uuid` from `plugins/pd/hooks/lib/doctor/checks.py:2259` into new file `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py`.

**Touch points:**
1. Create new file with module docstring + function body + imports.
2. Delete the function definition from `checks.py` (around line 2259).
3. Update `doctor/__init__.py:25` import path: replace `from .checks import check_cross_workspace_parent_uuid` with `from .check_cross_workspace_parent_uuid import check_cross_workspace_parent_uuid`.
4. `CHECK_ORDER` ordering (line 64) preserved byte-identical.
5. `_ENTITY_DB_CHECKS` set membership (line 83) preserved.

**Regression test (new):**

```python
def test_check_order_preserved_post_f116():
    """F116 FR-8: ensure FR-8 extraction + FR-2 new check don't disturb existing
    CHECK_ORDER ordering (only append at end)."""
    from doctor import CHECK_ORDER, _ENTITY_DB_CHECKS
    expected_names = [
        "check_db_readiness",
        "check_feature_status",
        "check_workflow_phase",
        "check_brainstorm_status",
        "check_backlog_status",
        "check_memory_health",
        "check_branch_consistency",
        "check_entity_orphans",
        "check_referential_integrity",
        "check_stale_dependencies",
        "check_project_attribution",
        "check_config_validity",
        "check_security_review_command",
        "check_stale_worktrees",
        "check_status_write_path",
        "check_no_free_text_status_parsers",
        "check_cross_workspace_parent_uuid",   # position 17 (1-indexed); F115
        "check_audit_counter_write_path",       # position 18
        "check_audit_emit_failed_count",        # position 19
        "check_severity_vocab",                 # position 20 — NEW (FR-2)
    ]
    assert [c.__name__ for c in CHECK_ORDER] == expected_names
    assert "check_cross_workspace_parent_uuid" in _ENTITY_DB_CHECKS
    assert "check_audit_emit_failed_count" in _ENTITY_DB_CHECKS
```

### FR-9 — Adversarial fix_hint Parser Tests + Defensive Helper

**New internal helper** `_normalize_and_validate_fix_hint(fix_hint: str) -> str` in `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py`. The helper is segment-aware: it splits on `|` and validates each segment per its grammar, so the `reason:` segment can contain free-text operator input while other segments stay locked to UUID-format characters.

```python
import unicodedata, re

_UUID_LIKE = re.compile(r"^[0-9a-fA-F\-]+$")        # for parent_uuid, child_uuid
_CHOICE_LIKE = re.compile(r"^[a-zA-Z\- ]+$")        # for choice value
_REASON_DENY = re.compile(r"[\x00-\x1f`$\\]")       # control chars + shell metas in reason
_MAX_LEN = 1024

def _normalize_and_validate_fix_hint(fix_hint: str) -> str:
    """Defensive parser layer.

    Steps:
    1. NFC-normalize unicode confusables.
    2. Reject if utf-8 byte length > 1024.
    3. Split on '|' into segments; validate each by grammar:
       - First segment: 'triage_cross_workspace_links:<uuid>:<uuid>'
         → UUID-like chars only.
       - 'choice:<value>' → choice value matches _CHOICE_LIKE.
       - 'reason:<value>' → free text, but reject control chars + shell
         metas ($, \\, `).
    4. Reject other unknown top-level segments.

    Raises ValueError on rejection. Reuses existing exception type.
    Returns the NFC-normalized, whitespace-stripped string.
    """
    if not fix_hint:
        return ""
    nfc = unicodedata.normalize("NFC", fix_hint)
    if len(nfc.encode("utf-8")) > _MAX_LEN:
        raise ValueError(f"fix_hint too long ({len(nfc)} chars, max {_MAX_LEN})")
    stripped = nfc.strip()
    segments = stripped.split("|")
    head = segments[0]
    if head.startswith("triage_cross_workspace_links:"):
        try:
            _, parent, child = head.split(":", 2)
        except ValueError:
            raise ValueError("fix_hint malformed: requires parent_uuid:child_uuid after prefix")
        if not _UUID_LIKE.match(parent) or not _UUID_LIKE.match(child):
            raise ValueError(f"fix_hint contains invalid character in uuid field: {head!r}")
    for seg in segments[1:]:
        if seg.startswith("choice:"):
            val = seg[len("choice:"):]
            if not _CHOICE_LIKE.match(val):
                raise ValueError(f"fix_hint contains invalid character in choice: {val!r}")
        elif seg.startswith("reason:"):
            val = seg[len("reason:"):]
            if _REASON_DENY.search(val):
                raise ValueError(f"fix_hint contains invalid character in reason: {val!r}")
        else:
            raise ValueError(f"fix_hint contains unknown segment: {seg!r}")
    return stripped
```

**Integration point:** Modify `_fix_triage_cross_workspace_link` at line 445 of `fix_actions/__init__.py`:

```python
# BEFORE:
choice_info = _parse_triage_choice(issue.fix_hint)

# AFTER (FR-9):
normalized_hint = _normalize_and_validate_fix_hint(issue.fix_hint)
choice_info = _parse_triage_choice(normalized_hint)
```

The normalizer returns the cleaned string (does NOT mutate `issue.fix_hint`). On rejection it raises `ValueError` before `_parse_triage_choice` is called.

**Call-site pin:** `_parse_triage_choice` has exactly ONE call site (`_fix_triage_cross_workspace_link` at line 445) — verified by grep at spec time. If a future caller is added, FR-9 normalization is bypassed (acknowledged in FM-7).

**New tests in `test_fix_actions.py`:**

```python
@pytest.mark.parametrize("bad_hint,error_fragment", [
    # case 1: nul byte injection
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}\x00", "invalid character"),
    # case 2: cyrillic confusable in uuid field (а = U+0430)
    (f"triage_cross_workspace_links:аaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:{_VALID_UUID_2}|choice:grandfather", "invalid character"),
    # case 3: shell metacharacter in uuid field
    (f"triage_cross_workspace_links:{_VALID_UUID_1};rm -rf /:{_VALID_UUID_2}|choice:grandfather", "invalid character"),
    # case 4: shell metacharacter in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:legit$(rm -rf /)", "invalid character in reason"),
    # case 5: backtick in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:abc`whoami`", "invalid character in reason"),
    # case 6: over-length
    ("triage_cross_workspace_links:" + ("a"*2000), "too long"),
    # case 7: unknown segment
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|bogus:val", "unknown segment"),
])
def test_fr9_adversarial_fix_hint_rejected(entities_db_session, bad_hint, error_fragment):
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity="any-child",
        message="x",
        fix_hint=bad_hint,
    )
    with pytest.raises(ValueError, match=error_fragment):
        _fix_triage_cross_workspace_link(FixContext(entities_conn=entities_db_session), issue)
```

**Happy-path regression (must pass post-FR-9):**

```python
def test_fr9_legitimate_grandfather_with_reason_preserves_behavior(entities_db_session):
    """Verify FR-9 normalization does NOT regress FR-7's grandfather happy path."""
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:grandfather|reason:operator approved cross-org link"
    )
    issue = Issue(check="check_cross_workspace_parent_uuid", severity="warning",
                  entity=child_uuid, message="x", fix_hint=fix_hint)
    _fix_triage_cross_workspace_link(FixContext(entities_conn=entities_db_session), issue)
    # Assertion: allowlist row inserted with expected reason
    with entities_db_session as conn:
        row = conn.execute(
            "SELECT reason FROM cross_workspace_allowlist WHERE parent_uuid=? AND child_uuid=?",
            (parent_uuid, child_uuid),
        ).fetchone()
    assert row[0] == "operator approved cross-org link"
```

## 4. Acceptance Criteria

| AC | Description | Verification command |
|----|-------------|----------------------|
| AC-1.1 | Doctor JSON output contains `.diagnostic.severity_summary` always | `python -m doctor --entities-db <db> --memory-db <db> --project-root . \| jq -e '.diagnostic.severity_summary'` |
| AC-1.2 | Aggregation matches sum over all check issues by severity | `pytest plugins/pd/hooks/lib/doctor/test_severity_summary.py -v` |
| AC-1.3 | Skipped-check synthetic error issues counted in `severity_summary.error` | Same test module |
| AC-1.4 | Invariant: `severity_summary.error == error_count` AND `severity_summary.warning == warning_count` | Same test module |
| AC-2.1 | `check_severity_vocab` is the 20th entry in `CHECK_ORDER` | `pytest plugins/pd/hooks/lib/doctor/test_doctor.py::test_check_order_preserved_post_f116 -v` |
| AC-2.2 | AST check emits `Issue(severity='error')` when severity literal outside `{error, warning, info}` | `pytest plugins/pd/hooks/lib/doctor/test_check_severity_vocab.py -v` |
| AC-2.3 | Test files excluded by `_TEST_FILE_RE` filter | Same test module |
| AC-3.1 | T3b.3a passes — bounded-count abort (both above and below) + schema preservation | `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::test_m6_aborts_on_bounded_count_violation -v` |
| AC-3.2 | T3b.3b passes — pre-freeze ratio abort + schema preservation (seed: 425 pre + 25 post = 450) | `pytest .../test_database.py::test_m6_aborts_on_pre_freeze_ratio_violation -v` |
| AC-3.3 | T3b.3c passes — `OperationalError` propagates uncaught from M6 (does NOT directly verify outer-runner rollback; that is inherited F115 invariant) | `pytest .../test_database.py::test_m6_operational_error_propagates_uncaught -v` |
| AC-4.1 | T3b.4 passes — M7 bounds violation abort + schema preservation | `pytest .../test_database.py::test_m7_aborts_on_bounds_violation -v` |
| AC-5.1 | T1.10 passes — M15 safe-to-rerun with INSERT-OR-REPLACE reset documented | `pytest plugins/pd/hooks/lib/entity_registry/test_database.py::test_m15_safe_to_rerun_with_documented_reset_semantics -v` |
| AC-6.1 | 9-case matrix passes — 3 handlers × 3 ACs via database.py-layer calls | `pytest plugins/pd/hooks/lib/entity_registry/test_cross_workspace_matrix.py -v` |
| AC-7.1 | 4-decision triage tests pass — all branches + grandfather-no-reason + unknown-choice | `pytest plugins/pd/hooks/lib/doctor/test_fix_actions.py -v -k triage` |
| AC-8.1 | `check_cross_workspace_parent_uuid.py` exists as standalone file | `test -f plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py` |
| AC-8.2 | `CHECK_ORDER` 20-name sequence preserved byte-identical | Covered by AC-2.1 (same test) |
| AC-8.3 | `_ENTITY_DB_CHECKS` membership preserved | Same test |
| AC-9.1 | 7 adversarial fix_hint cases reject with `ValueError` (nul byte, cyrillic, shell-meta-uuid, shell-meta-reason, backtick-reason, over-length, unknown-segment) | `pytest .../doctor/test_fix_actions.py -v -k adversarial_fix_hint` |
| AC-9.2 | `_normalize_and_validate_fix_hint` helper exists with segment-aware grammar | `grep -n "def _normalize_and_validate_fix_hint" plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` |
| AC-9.3 | Legitimate grandfather reason "operator approved cross-org link" still passes (no FR-7/FR-9 regression) | `pytest .../doctor/test_fix_actions.py::test_fr9_legitimate_grandfather_with_reason_preserves_behavior -v` |
| AC-Sev.1 | `severity_summary` aggregation reflects ALL issues across ALL checks | Covered by AC-1.2 |
| AC-Sev.2 | `severity_summary` block present even when all counts are 0 | Covered by AC-1.1 |
| AC-E-115.2 | Vocabulary AST check + severity_summary ship in same feature | AC-1.x + AC-2.x in same merge |
| AC-Validate | `validate.sh` passes with 0 errors | `./validate.sh` |
| AC-Regress | F115 invariants regress 0 tests | `plugins/pd/.venv/bin/python -m pytest plugins/pd/ -q` shows no NEW F115-test failures |

## 5. Empirical Pins

| Pin | Source-of-truth | Value at spec time |
|-----|-----------------|--------------------|
| F115 final merge commit | `git log --merges` | `515cfdda` |
| F115 QA gate override commit | `git log` | `f9e53fb1` |
| Doctor `CHECK_ORDER` count post-F115 | `doctor/__init__.py:41-70` | 19 |
| Doctor `CHECK_ORDER` count post-F116 (target) | Same | 20 (+ `check_severity_vocab`) |
| Full 19-name CHECK_ORDER sequence | `doctor/__init__.py:41-70` verbatim | See FR-8 expected_names list (drop final `check_severity_vocab` for pre-F116) |
| Issue dataclass fields | `doctor/models.py:7-15` | `check, severity, entity, message, fix_hint` (NO `line` field) |
| DiagnosticReport fields | `doctor/models.py:38-46` | `healthy, checks, total_issues, error_count, warning_count, elapsed_ms` (F116 adds `severity_summary`) |
| Doctor JSON output top-level wrapper | `doctor/__main__.py:85` | `{"diagnostic": report.to_dict()}` |
| Doctor CLI args | `doctor/__main__.py:21-46` | `--entities-db, --memory-db, --project-root, --workspace-uuid, --artifacts-root, --fix, --dry-run` (output is JSON by default; no `--json` flag) |
| 5 production entity kinds | `entity_registry/database.py:46` | feature, backlog, brainstorm, project, workspace |
| 3 MCP handlers gated by `_assert_same_workspace_pairwise` | F115 design rev 2 | set_parent, add_dependency, add_okr_alignment |
| 4 triage choices in `_fix_triage_cross_workspace_link` | `fix_actions/__init__.py:472-499` | re-attribute parent, re-attribute child, delete relation, grandfather |
| Grandfather fallback reason string | `fix_actions/__init__.py:491` verbatim | `"operator-grandfathered (no reason supplied)"` |
| M6 entry point function name | `semantic_memory/database.py:330` | `_migration_6_unify_source_hash_and_cleanup` |
| M7 entry point function name | `semantic_memory/database.py:435` | `_migration_7_reset_inflated_observation_count` |
| M15 entry point function name | `entity_registry/database.py:5404` | `_migration_15_audit_emit_counter` |
| M15 idempotency mechanism | `database.py:5414-5417` | INSERT OR REPLACE (reset semantics, not preservation) |
| M15 transaction ownership | `database.py:5412` | M15 owns its OWN BEGIN IMMEDIATE (unlike M6/M7 which inherit runner's outer tx) |
| M6 identity spot-check predicate | M6 body | `pre_freeze / observed_count < 0.95` on `created_at < '2026-05-16'` (predicate scoped to `source='session-capture' AND name LIKE 'Tool failure:%'`) |
| M6 bounded-count gate | M6 body | `[expected_min=418, expected_max=518]` |
| M6 Op ordering | M6 body | Op 1 (DELETE) executes BEFORE Op 2 (recompute_all_with_conn) |
| M6 / M7 abort exception class | Grep `raise RuntimeError` in M6/M7 bodies | `RuntimeError` (NOT `MigrationAbortError`) |
| M6 OperationalError handling | Grep `except OperationalError` in M6 body | None (uncaught; propagates to runner) |
| Triage tool abort exception class | `fix_actions/__init__.py:450,455,499` | `ValueError` (NOT `InvalidFixHintError`) |
| `_parse_triage_choice` call sites | grep | Exactly 1: `_fix_triage_cross_workspace_link` line 445 |
| Python/sqlite version | `plugins/pd/pyproject.toml`, `python -c "import sqlite3; print(sqlite3.sqlite_version)"` | Python ≥ 3.11; sqlite3 ≥ 3.35 |

## 6. Behavioral Constraints

- **Must NOT introduce new MCP tools** — F116 is coverage + observability only.
- **Must NOT introduce new migrations** — M15/M16/M17 sufficient.
- **Must NOT change F115's existing migration bodies** — only add tests around current behavior.
- **Must NOT introduce new exception classes** — reuse `RuntimeError` (migrations) and `ValueError` (triage tool).
- **Must NOT change `CHECK_ORDER` sequence beyond appending `check_severity_vocab`** — preserves stable contract.
- **Must NOT add backwards-compatibility shims** — private tooling.
- **Must NOT modify F111 closure model or F115 cross-workspace allowlist schema** — both pinned upstream.
- **DiagnosticReport extension is additive** — `error_count` and `warning_count` MUST remain present alongside the new `severity_summary` field (downstream consumers may still read the legacy fields).

## 7. Failure Modes + Mitigations

| FM | Description | Mitigation |
|----|-------------|------------|
| FM-1 | FR-8 refactor changes `CHECK_ORDER` position | AC-2.1 regression test pins full 20-name sequence as byte-identical list |
| FM-2 | FR-9 over-length cap (1024 bytes) rejects legitimate-but-large inputs | Pre-implement: grep `fix_actions` audit_log for max-observed `fix_hint` length; raise cap if observed ≥ 80% of 1024 |
| FM-3 | FR-9 segment-aware grammar may miss new segment types added in future | Pin call-site count = 1 (Empirical Pin §5); add CHANGELOG entry when extending grammar |
| FM-4 | T3b.3c proxy delegation incomplete vs M6 internal usage | Full delegation surface enumerated in `_MidTxFailingConnection` (execute, executemany, executescript, cursor, commit, rollback, close, __enter__, __exit__, in_transaction) |
| FM-5 | T3b.3b pre-freeze fixture seeding non-deterministic | Concrete seed pinned: 425 pre + 25 post = 450 total (within [418, 518]); ratio 0.9444 < 0.95 |
| FM-6 | T2b.5 9-case matrix fixture cost dominates suite wall-clock | Session-scoped fixture; entities.db built once, reset between parametrize cases via SAVEPOINT |
| FM-7 | `_parse_triage_choice` second call site appears later, bypassing normalization | Pinned at spec time; CHANGELOG entry required if new call site added |
| FM-8 | M15 own-transaction behavior differs from M6/M7 (inherited) | Documented in FR-5 docstring + Empirical Pin §5 |

## 8. Non-Goals

- **NOT introducing `MigrationAbortError` class** — M6/M7 raise `RuntimeError`.
- **NOT introducing `InvalidFixHintError` class** — `_parse_triage_choice` and downstream raise `ValueError`.
- **NOT changing M15 INSERT-OR-REPLACE semantics to INSERT-OR-IGNORE** — runner-contiguity protects production; FR-5 documents actual behavior.
- **NOT retroactively backfilling audit log** — counter starts at 0 by design.
- **NOT exhaustive shell metacharacter enumeration** — character allowlist + segment-aware grammar is the enforcement mechanism.
- **NOT dynamic `max(MIGRATIONS.keys())` test-fixture refactor** — F115 retro KB candidate #6, out of scope.

## 9. Out of Scope (This Release)

- Telemetry log format JSON schema pinning (F115 LOW sidecar #3).
- `CHECK_ORDER` content assertion across ALL test sites (F115 LOW sidecar #4 — addressed only at the refactor regression test site).

## 10. Carry-Forward Resolution Table (for F115 qa-override.md)

After implementation completes, append the following table to F115's `qa-override.md` documenting closure:

| qa-override item (verbatim title) | F116 FR | Resolution commit |
|---|---|---|
| 1. `severity_summary` field absent from doctor JSON output | FR-1, FR-2 | (filled at finish) |
| 2. M6/M7 abort-path tests (T3b.3a/b/c, T3b.4) not landed | FR-3, FR-4 | (filled at finish) |
| 3. T2b.5 9-case cross-workspace gate matrix missing | FR-6 | (filled at finish) |
| 4. T2b.8 `check_severity_vocab.py` AST check missing | FR-2 | (filled at finish) |
| 5. T2a.7 4-decision triage tests missing | FR-7 | (filled at finish) |
| 6. T1.10 M15 preservation test missing | FR-5 | (filled at finish) |
| 7. `check_cross_workspace_parent_uuid` inlined vs design spec | FR-8 | (filled at finish) |
| 8. Adversarial parsing for `fix_hint` in the triage tool | FR-9 | (filled at finish) |

## 11. Risks (rev 2 recalibrated)

- **MED — FR-8 refactor disturbs `CHECK_ORDER`.** Mitigated by AC-2.1 (full 20-name regression).
- **MED — FR-9 helper adds normalization layer.** Behavior-tightening for adversarial inputs; legitimate ASCII paths unchanged. AC-9.3 verifies happy-path regression.
- **MED — FR-9 over-length cap (1024) is unverified.** FM-2 requires pre-implement grep of audit_log.
- **LOW — Test fixture sweep cost.** Aggressive parametrize + session-scoped fixtures.
- **LOW — Severity vocab AST false positives.** Tight visitor scoping (Constant string in `severity=` kwarg only).

## 12. Implementation Strategy

Theme A first (low blast radius — additive JSON field + new file). Theme B second (test addition only). Theme C third (refactor + matrix + parser helper).

Within Theme C: refactor (FR-8) BEFORE matrix coverage (FR-6) so the regression test pins the new `CHECK_ORDER` structure post-extraction.

## 13. Pre-Implementation Verification Step (FM-2 + FM-7)

Before beginning FR-9 implementation, run:

```bash
# FM-2: max-observed fix_hint length in audit_log
sqlite3 ~/.claude/pd/entities/entities.db \
  "SELECT MAX(LENGTH(fix_hint)) FROM ... ;" # actual table name TBD at implement time

# FM-7: confirm _parse_triage_choice still has exactly 1 call site
grep -c "_parse_triage_choice(" plugins/pd/hooks/lib/doctor/fix_actions/__init__.py
# expected: 2 (definition + 1 call)
```

If max observed length > 800 bytes → raise `_MAX_LEN` cap (currently 1024).
If grep returns > 2 → update FM-7 and expand FR-9 integration points.
