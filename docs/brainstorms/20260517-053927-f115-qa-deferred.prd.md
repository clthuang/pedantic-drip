# PRD: F115 QA-Gate Deferred Hardening

## Status
- Created: 2026-05-17
- Last updated: 2026-05-17 (rev 2 — addresses prd-reviewer iteration 1 blockers)
- Status: Draft
- Problem Type: Technical/Architecture
- Archetype: exploring-an-idea
- Mode: YOLO (Stage 1 CLARIFY + Stage 2 RESEARCH skipped per user — all evidence already in F115 artifacts and `docs/brainstorms/116-f115-qa-deferred-source.md`)

## Problem Statement

F115's post-merge 4-reviewer adversarial QA gate (Step 5b) identified **2 implementation-reviewer blockers** and **6 test-deepener HIGH gaps** that were deferred to F116 via `qa-override.md`. F115's structural invariants hold (atomic emit, cross-workspace gates, triage tool, writer quality gates, hash recompute), but the test-completeness + observability surfaces have not yet been auditable or regression-proof. F116 closes those 8 HIGH gaps without introducing new functional surface — except for two explicitly-scoped additions: (1) a helper module file `check_cross_workspace_parent_uuid.py` per F115 T2b.6 that F115's implementation parked inside `checks.py` rather than its planned standalone module, and (2) an internal defensive parser helper `_normalize_and_validate_fix_hint` in `fix_actions/__init__.py` to give the adversarial `fix_hint` test cases a single rejection point (no new exception class, no new MCP surface).

### Evidence

- F115 qa-override.md: 8 HIGH findings enumerated — Evidence: `docs/features/115-pd-data-model-followups/qa-override.md`
- F115 final merge commit `515cfdda` (full implementation, all 5 clusters) — Evidence: `git log` history
- F115 QA gate cache `.qa-gate.json` records: implementation-reviewer NOT APPROVED (2 blockers); test-deepener 6 HIGH gaps — Evidence: `docs/features/115-pd-data-model-followups/.qa-gate.json`
- `_metadata.audit_emit_failed_count` initialized to `"0"` by M15 via `INSERT OR REPLACE` — Evidence: `plugins/pd/hooks/lib/entity_registry/database.py:5414-5417`
- Doctor `CHECK_ORDER` currently 19 entries post-F115 — Evidence: `plugins/pd/hooks/lib/doctor/__init__.py:41-70`
- 5 production entity kinds (`feature, backlog, brainstorm, project, workspace`) — Evidence: `plugins/pd/hooks/lib/entity_registry/database.py:46`
- 3 MCP handlers gated by `_assert_same_workspace_pairwise`: `set_parent, add_dependency, add_okr_alignment` — Evidence: F115 spec.md FR-E + design rev 2 C13-115
- `check_cross_workspace_parent_uuid` currently lives inside `doctor/checks.py:2259` rather than the standalone `check_cross_workspace_parent_uuid.py` planned by F115 T2b.6 — Evidence: `docs/features/115-pd-data-model-followups/tasks.md` T2b.6 line "Create plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py per design C13-115.3 verbatim"
- F115's actual T2b.5 definition is `3 handlers × 3 ACs = 9 test cases minimum` — Evidence: `docs/features/115-pd-data-model-followups/tasks.md` T2b.5 acceptance criteria
- 4 actual triage choices `{"re-attribute parent", "re-attribute child", "delete relation", "grandfather"}` with `grandfather` requiring a `reason` column — Evidence: `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:403-404, 431-502`
- M6/M7 use `raise RuntimeError(...)` (no typed `MigrationAbortError`) — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py`
- M6 "identity spot-check" is `pre_freeze/observed_count < 0.95` on `created_at < '2026-05-16'` (a pre-freeze temporal anchor ratio, NOT a hash drift gate) — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py` M6 body
- M6 does NOT catch `sqlite3.OperationalError`; the runner's outer transaction handles rollback — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py` (no try/except wrapping the migration body for OperationalError)

## Goals

1. **Auditable severity reporting** — every doctor invocation produces a `severity_summary` rollup block aggregated across all checks' issues + AST-pinned closed-set vocabulary check.
2. **Regression-proof migration gates** — bounded-count + pre-freeze temporal-anchor + IO-error-propagation paths for M6/M7 land as parametrized tests; M15 re-run safety pinned.
3. **Complete cross-workspace coverage** — 9-case handler × AC matrix per F115's actual T2b.5 spec, 4-decision triage branches per actual implementation, adversarial `fix_hint` parser tests reusing `ValueError`, and helper-file extraction per F115 T2b.6.

## Success Criteria

- [ ] Doctor JSON output includes `severity_summary: {error: N, warning: N, info: N}` aggregated across **all `CheckResult.issues` items across all checks** (not per-check). Block is present even when all counts are 0. Skipped-check synthetic issues (from `_make_failed_result`) ARE included to surface infrastructure errors. **AC-Sev.1 / AC-Sev.2 / AC-E-115.2 satisfied.**
- [ ] `check_severity_vocab.py` AST check (new file) rejects any doctor check file containing an `ast.Constant` value (string) in a keyword named `severity` outside `{error, warning, info}`. Emits an `Issue` with `severity='error'` per existing doctor convention; `validate.sh` is the CI enforcement layer.
- [ ] M6 abort-path parametrized tests cover:
  - **T3b.3a:** Populated entries.db with `observed_count > expected_max` (or `< expected_min`) → `RuntimeError` raised, message matches `r"bounded.count"` AND `schema_version` unchanged.
  - **T3b.3b:** Populated entries with < 95% pre-freeze `created_at` ratio (`pre_freeze / observed_count < 0.95`) → `RuntimeError` raised, message matches `r"identity spot.check|pre.freeze|temporal"` AND `schema_version` unchanged.
  - **T3b.3c:** Inject `sqlite3.OperationalError` via a `Connection` proxy wrapping `.execute` (NOT global monkeypatch) on the first `DELETE FROM entries` statement → assert `OperationalError` propagates AND the migration runner's outer transaction rolls back (`schema_version` unchanged + DB row count unchanged).
- [ ] M7 abort-path test T3b.4: Populate memory.db with observation_count outside M7's bounds → `RuntimeError` raised; `schema_version` unchanged.
- [ ] M15 re-run safety test T1.10: After M15 has run once, manually rewind `schema_version` to 14 and re-run M15. Assert: (a) no exception, (b) counter value is `"0"` (INSERT OR REPLACE semantics — re-running resets, which is acceptable because migration-runner contiguity (`range(current+1, target+1)`) prevents this in production). Documents the actual semantics rather than asserting a preservation invariant the code does not provide.
- [ ] T2b.5 matrix (per F115's actual definition): parametrized matrix of `3 handlers × 3 ACs = 9 cases`. Handlers: `set_parent`, `add_dependency`, `add_okr_alignment`. ACs: AC-E.1 cross-workspace call rejected with `CrossWorkspaceError`; AC-E.2 same-workspace call succeeds; AC-E.3 allowlisted pair (row in `cross_workspace_allowlist`) succeeds despite cross-workspace.
- [ ] T2a.7: 4-decision triage tests for `_fix_triage_cross_workspace_link`, parametrized over the 4 actual branches:
  - **re-attribute parent:** Verify `UPDATE entities SET workspace_uuid = <child_ws> WHERE uuid = <parent>`; parent now in child's workspace.
  - **re-attribute child:** Verify `UPDATE entities SET workspace_uuid = <parent_ws> WHERE uuid = <child>`; child now in parent's workspace.
  - **delete relation:** Verify `UPDATE entities SET parent_uuid = NULL WHERE uuid = <child>`; child's `parent_uuid` is NULL.
  - **grandfather:** Verify `INSERT OR IGNORE INTO cross_workspace_allowlist (parent_uuid, child_uuid, reason)`; allowlist row includes the `reason` from `fix_hint` (or fallback `"operator-grandfathered (no reason supplied)"`).
- [ ] `check_cross_workspace_parent_uuid` moved from `checks.py:2259` into standalone file `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py` per F115 T2b.6. Import path updated in `doctor/__init__.py`; `CHECK_ORDER` position preserved byte-identical (regression test asserts the full sequence).
- [ ] Adversarial `fix_hint` parser tests cover leading/trailing whitespace, unicode confusables (NFC normalization), shell metacharacters (`;|&\`$()`), and nul-byte injection. Reuse existing `ValueError` (not a new exception class) — assert error message regex.
- [ ] All 8 carry-forward items checked off in a new `qa-override.md` resolution table appended to F115's `qa-override.md`.
- [ ] `validate.sh` passes with 0 errors and ≤5 warnings.
- [ ] F115's existing invariants (atomicity post-merge gate, cross-workspace gates, audit emit) regress 0 tests.

## User Stories

### Story 1: Auditable Severity Reporting
**As a** pd plugin maintainer **I want** every doctor invocation to emit a `severity_summary` rollup aggregated across all checks **So that** I can `jq .severity_summary` for overall health without re-aggregating per-check fields.
**Acceptance criteria:**
- `severity_summary` is present in doctor's JSON output every run.
- Aggregation is across all `CheckResult.issues` items across all checks (including skipped-check synthetic error issues).
- AST check `check_severity_vocab.py` emits a severity=error `Issue` if any check file uses a `severity=` keyword constant outside the closed set.

### Story 2: Regression-Proof Migration Gates
**As a** future pd developer **I want** M6/M7 abort paths covered by parametrized regression tests **So that** a refactor breaking the bounded-count or pre-freeze temporal-anchor gate fails fast.
**Acceptance criteria:**
- T3b.3a/b/c + T3b.4 live in the existing semantic_memory test module.
- Tests assert `RuntimeError` (the actual migration abort mechanism), not `MigrationAbortError`.
- M15 re-run safety test T1.10 asserts no-exception + INSERT-OR-REPLACE reset semantics + documents the runner-contiguity protection.

### Story 3: Cross-Workspace Coverage Completeness
**As a** pd plugin maintainer **I want** all 9 handler × AC combinations + all 4 triage decision branches + adversarial `fix_hint` inputs exercised by tests **So that** a regression in cross-workspace logic surfaces at PR-time, not in production.
**Acceptance criteria:**
- 9-case matrix uses `@pytest.mark.parametrize` over `(handler ∈ {set_parent, add_dependency, add_okr_alignment}) × (AC ∈ {AC-E.1, AC-E.2, AC-E.3})`.
- 4-decision triage tests assert side-effects on `entities` and `cross_workspace_allowlist` tables matching the actual fix function's SQL.
- Adversarial `fix_hint` test cases reject malformed input with `ValueError` containing recognizable message fragments.

## Use Cases

### UC-1: Doctor Severity Rollup
**Actors:** pd plugin maintainer | **Preconditions:** Doctor invoked via `python -m doctor` or session-start hook.
**Flow:**
1. Doctor runs all 20 checks (19 from F115 + new `check_severity_vocab`).
2. Each check returns a `CheckResult` with `issues: list[Issue]` (potentially multi-severity per check).
3. Doctor aggregates: `severity_summary[k] = sum over all CheckResult.issues across all checks where issue.severity == k` for `k ∈ {error, warning, info}`.
4. JSON output includes `severity_summary` block at top level (sibling of per-check fields).
**Postconditions:** Caller can `jq .severity_summary` to get rollup without per-check re-aggregation.
**Edge cases:**
- Zero issues → `severity_summary: {error: 0, warning: 0, info: 0}` (present, all zeros).
- One check emits `[error, warning]`, another emits `[warning, warning, info]` → `severity_summary: {error: 1, warning: 3, info: 1}`.
- Skipped check (DB-locked path produces synthetic error via `_make_failed_result`) → counted toward `error`. Operational rationale: surfaces infrastructure failures alongside real findings rather than hiding them.

### UC-2: M6 Bounded-Count Abort
**Actors:** Migration runner | **Preconditions:** memory.db has population state outside M6's expected bounds.
**Flow:**
1. Migration runner enters M6 body (`_migration_6`).
2. Bounded-count assertion fails (count outside `[expected_min, expected_max]`).
3. Migration raises `RuntimeError("M6: bounded-count gate failed — observed N, expected [min, max]")`.
4. Migration runner's outer transaction context rolls back; `schema_version` remains unchanged.
**Postconditions:** DB state preserved; runner surfaces actionable error to operator.
**Edge cases:**
- Fresh DB (count=0) → no-op (falls through to non-aborting branch per existing M6 behavior; pinned by an existing fresh-DB regression test).
- Pre-freeze ratio violation (`< 0.95` pre-freeze) → separate `RuntimeError` message containing "identity spot-check" / "pre-freeze" terms.
- `sqlite3.OperationalError` mid-statement → NOT caught by M6; propagates to the runner; outer tx rolls back (verified by T3b.3c).

### UC-3: Cross-Workspace Triage — Re-attribute Parent
**Actors:** pd plugin maintainer running `pd doctor --fix` | **Preconditions:** `check_cross_workspace_parent_uuid` reports a violating link.
**Flow:**
1. AskUserQuestion harness (caller of `_fix_triage_cross_workspace_link`) presents 4 options to operator.
2. Operator selects "re-attribute parent".
3. Harness encodes `fix_hint = "triage_cross_workspace_links:<parent_uuid>:<child_uuid>|choice:re-attribute parent"`.
4. `_fix_triage_cross_workspace_link` parses fix_hint, looks up child/parent workspace_uuids, executes `UPDATE entities SET workspace_uuid = <child_ws> WHERE uuid = <parent>`.
5. Doctor re-runs cross-workspace check; violation cleared (parent now in same workspace as child).
**Postconditions:** Parent entity's `workspace_uuid` matches child's. The relationship persists; only the parent's workspace anchor moved.
**Edge cases:**
- `fix_hint` missing `choice:` → harness raises `ValueError` containing `"requires choice:<value>"`.
- `fix_hint` missing `parent_uuid:child_uuid` pair → harness raises `ValueError` containing `"requires parent_uuid:child_uuid"`.
- Adversarial `fix_hint` (shell metacharacters / nul bytes / unicode confusables) → adversarial parser rejects with `ValueError` containing recognizable fragment; harness re-prompts.
- "grandfather" choice with no `reason:` field → fix function falls back to `"operator-grandfathered (no reason supplied)"` and inserts allowlist row.

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Doctor check emits unknown severity literal in source | `check_severity_vocab.py` emits severity=error `Issue`; `validate.sh` fails CI | Closed-set vocabulary invariant must be statically enforced (AST-level) |
| Doctor check emits multiple severities per run | All counted in `severity_summary` (sum across `CheckResult.issues`) | Per-issue, not per-check, aggregation matches the data model |
| Skipped check's synthetic error issue | Counted in `severity_summary.error` | Infrastructure failures must surface, not hide |
| M6 over-bounds populated DB | `RuntimeError` with "bounded-count" in message; outer tx rolls back | DB state preservation > silent overcorrection |
| M6 pre-freeze ratio violation (< 0.95 `created_at < '2026-05-16'`) | `RuntimeError` with "identity spot-check" / "pre-freeze" / "temporal" in message; outer tx rolls back | Pre-freeze anchor is the actual integrity gate; documented operational definition |
| M6 sqlite3.OperationalError mid-tx | `OperationalError` propagates uncaught; outer tx rolls back | Matches existing M6 behavior; no defensive catch added |
| M7 bounds violation | `RuntimeError`; outer tx rolls back | Consistent with M6 abort semantics |
| M15 re-run on populated DB | INSERT OR REPLACE → counter reset to `"0"`; no crash; schema_version stays at 15 | Documents actual semantics; runner-contiguity prevents this in production |
| Cross-workspace 9-case matrix — cross-ws call (AC-E.1) | `CrossWorkspaceError` raised; envelope translated to MCP error | F115 spec.md FR-E |
| Cross-workspace 9-case matrix — same-ws call (AC-E.2) | Operation succeeds normally; row inserted | Negative case validation |
| Cross-workspace 9-case matrix — allowlisted pair (AC-E.3) | Operation succeeds despite cross-workspace pair (allowlist row present) | F115 spec.md FR-E.2 |
| Triage tool — adversarial `fix_hint` with shell metas | `ValueError` containing fragment like "invalid character" | Defensive parsing; no shell reaches; existing exception class reused |
| Triage tool — unicode normalization in `fix_hint` | NFC-normalize before parsing; reject if post-normalization fails UUID shape | Unicode confusables can disguise malicious input |
| Triage tool — empty `fix_hint` | `_parse_triage_choice` returns dict with all None values; `_fix_triage_cross_workspace_link` raises `ValueError("requires parent_uuid:child_uuid")` | Existing behavior; no change |

## Constraints

### Behavioral Constraints (Must NOT do)

- **Must NOT introduce new MCP tools** — Rationale: F116 is coverage + observability only.
- **Must NOT introduce new migrations** — Rationale: M15/M16/M17 sufficient. M18 would expand schema surface.
- **Must NOT change F115's existing migration bodies** — Rationale: M6/M7 behavior pinned; we only add tests around current behavior.
- **Must NOT introduce new exception classes** (no `MigrationAbortError`, no `InvalidFixHintError`) — Rationale: M6/M7 raise `RuntimeError`; triage tool raises `ValueError`. Reuse existing exception types; assert message-regex in tests.
- **Must NOT change `CHECK_ORDER` sequence beyond appending `check_severity_vocab` at the end** — Rationale: existing order is a stable contract used by deterministic tests.
- **Must NOT add backwards-compatibility shims** — Rationale: private tooling; consumers update simultaneously.

### Technical Constraints

- Python 3.11+ — Evidence: `plugins/pd/pyproject.toml`
- `python -c "import sqlite3; print(sqlite3.sqlite_version)"` ≥ `3.35.0` (for F115 features inherited; F116 tests use only Python-stdlib sqlite3 APIs) — Evidence: F115 design rev 2 + project CLAUDE.md gotcha
- pytest as test framework with `@pytest.mark.parametrize` for matrix coverage — Evidence: existing test patterns in `test_database.py`
- Closed-set severity vocab: `{error, warning, info}` — Evidence: existing usage in doctor checks (e.g., `Issue(severity='warning', ...)`)
- AST check pattern template: `plugins/pd/hooks/lib/doctor/check_status_write_path.py` — Evidence: cited by F109 pattern + existing in codebase
- Test fixtures use only SQLite operations supported by Python 3.11's bundled sqlite3 module; avoid DROP COLUMN in fixture builds — Evidence: project CLAUDE.md SQLite migration patterns gotcha

## Requirements

### Functional

- **FR-1 (Severity rollup):** Doctor's JSON output MUST include a top-level `severity_summary` block with integer counts for each value in the closed set `{error, warning, info}`. **Aggregation:** for `k ∈ {error, warning, info}`, `severity_summary[k] = len([i for cr in check_results for i in cr.issues if i.severity == k])`. Block is present even when all counts are 0. **Skipped checks:** synthetic error issues from `_make_failed_result` ARE counted. **No `total` field** — consumers compute via jq if needed.
- **FR-2 (Severity vocab AST check):** New file `plugins/pd/hooks/lib/doctor/check_severity_vocab.py` MUST: *(This FR closes both qa-override item 1 — severity_summary absence's vocab enforcement — and item 4 — missing `check_severity_vocab.py` file. FR-1 covers the rollup; FR-2 covers the vocab AST check and the missing file.)*
  - **AST visitor structure:** Walk module AST. For each `ast.Call`, inspect `node.keywords`. For each keyword where `keyword.arg == 'severity'` AND `isinstance(keyword.value, ast.Constant)` AND `isinstance(keyword.value.value, str)`: if value not in `{'error', 'warning', 'info'}`, emit Issue with severity='error'.
  - **Scope:** Scan `plugins/pd/hooks/lib/doctor/checks.py`, `plugins/pd/hooks/lib/doctor/check_*.py`, AND the standalone `check_cross_workspace_parent_uuid.py` (after FR-8 extraction). Exclude test files via path filter (`/test_*.py` and `_test.py` excluded).
  - **Registration:** Append `check_severity_vocab` to `CHECK_ORDER` after F115's existing 19 checks (becomes position 20).
  - **Failure mode:** Emits doctor `Issue(severity='error')`. Session-start does NOT abort; `validate.sh` is the CI enforcement layer (existing convention).
- **FR-3 (M6 abort-path tests):** New parametrized tests in `plugins/pd/hooks/lib/semantic_memory/test_database.py`:
  - **T3b.3a:** Use a Connection fixture, populate `entries` table to violate bounded-count (parametrized: `observed > expected_max` AND `observed < expected_min` cases). Run M6. Assert `RuntimeError` raised with message matching `r"bounded.count"`. Assert `_metadata.schema_version` unchanged.
  - **T3b.3b:** Populate entries such that the pre-freeze ratio (`pre_freeze / observed_count`) falls below 0.95. Operationally: of the rows targeted by M6's DELETE predicate, fewer than 95% have `created_at < '2026-05-16'`. Run M6. Assert `RuntimeError` raised with message matching `r"(identity spot.check|pre.freeze)"`. Assert `schema_version` unchanged.
  - **T3b.3c:** Inject `sqlite3.OperationalError` via a `Connection` proxy that wraps `.execute` and raises on the first SQL starting with `DELETE FROM entries`. Run M6 against the proxied connection. Assert `OperationalError` propagates (NOT caught by M6). Assert the outer test transaction is rollback-able (no commits before the raise). Assert `schema_version` unchanged.
- **FR-4 (M7 abort-path test T3b.4):** New test populates memory.db with observation_count outside M7's bound. Runs M7. Asserts `RuntimeError` raised (M7's actual abort mechanism) AND `schema_version` unchanged.
- **FR-5 (M15 re-run safety test T1.10):** New test in entity_registry test module. (a) Run M15 once on a populated entities.db; capture `_metadata.audit_emit_failed_count`. (b) Manually rewind `_metadata.schema_version` to `"14"` (via direct UPDATE). (c) Run M15 again. Assert: no exception raised; counter value is `"0"` (INSERT OR REPLACE semantics). Test docstring explicitly documents that this is "safe-to-re-run" semantics, NOT "value-preservation" — runner-contiguity prevents re-run in production.
- **FR-6 (T2b.5 9-case matrix — handler × AC):** New parametrized test in entity_registry test module:
  - Parametrize over `handler ∈ {set_parent, add_dependency, add_okr_alignment}` × `AC ∈ {AC-E.1 cross-ws-rejected, AC-E.2 same-ws-succeeds, AC-E.3 allowlisted-succeeds}` = 9 cases.
  - Use single session-scoped fixture (`entities_db`) with three pre-built workspaces and seeded entities.
  - AC-E.1: invoke handler with cross-workspace pair → assert `CrossWorkspaceError` raised (envelope: `error_type='cross_workspace_forbidden'`).
  - AC-E.2: invoke handler with same-workspace pair → assert success; relevant table row inserted.
  - AC-E.3: insert `cross_workspace_allowlist` row, invoke handler with that pair → assert success; relevant table row inserted.
- **FR-7 (T2a.7 4-decision triage tests):** New parametrized test for `_fix_triage_cross_workspace_link` in `plugins/pd/hooks/lib/doctor/test_fix_actions.py` (create if absent):
  - **re-attribute parent:** Pre-state: parent in workspace A, child in workspace B. Construct `Issue` with `fix_hint = "triage_cross_workspace_links:<parent>:<child>|choice:re-attribute parent"`. Call fix function. Assert post-state: parent's `workspace_uuid == workspace B`.
  - **re-attribute child:** Same pre-state. `choice:re-attribute child`. Assert post-state: child's `workspace_uuid == workspace A`.
  - **delete relation:** Same pre-state. `choice:delete relation`. Assert post-state: child's `parent_uuid IS NULL`.
  - **grandfather:** Same pre-state. `choice:grandfather|reason:operator approved cross-org link`. Assert post-state: row inserted into `cross_workspace_allowlist` with `(parent_uuid=<parent>, child_uuid=<child>, reason='operator approved cross-org link')`. Sub-case without `reason:` → assert fallback `"operator-grandfathered (no reason supplied)"`.
  - **Unknown choice:** Assert `ValueError` containing `"Unknown triage choice"`.
- **FR-8 (Helper file extraction — F115 T2b.6):** Move `check_cross_workspace_parent_uuid` from `doctor/checks.py:2259` into new file `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py`. Update import in `doctor/__init__.py`. **CHECK_ORDER position preservation:** existing position in `CHECK_ORDER` MUST be byte-identical post-refactor (verified by a new regression test that asserts the full `CHECK_ORDER` sequence as a fixed list). **`_ENTITY_DB_CHECKS` set membership preserved**.
- **FR-9 (Adversarial `fix_hint` parser tests):** New tests in `test_fix_actions.py` exercising the existing `_parse_triage_choice` + downstream validation. Each adversarial input asserts the existing `ValueError` (NOT a new exception class):
  - Leading/trailing whitespace in `fix_hint`: parser strips; if remainder is empty or malformed, raises `ValueError` containing `"requires parent_uuid:child_uuid"` OR `"requires choice"`.
  - Unicode confusables (e.g., Cyrillic 'а' in place of Latin 'a'): pre-validate by attempting to parse UUIDs with `uuid.UUID(s)`; on failure raise `ValueError` containing `"invalid uuid"`. (Defensive parser layer is added as a helper function `_normalize_and_validate_fix_hint(fix_hint: str) -> str` inside `fix_actions/__init__.py` — explicitly scoped as new internal helper, not a new exception type or MCP surface.)
  - Shell metacharacters (`;|&\`$()`): rejected by character allowlist (UUID hex digits, `-`, `:`, `|`, `,` only); raises `ValueError` containing `"invalid character"`.
  - Nul-byte injection: rejected by character allowlist; raises `ValueError`.
  - Empty `fix_hint`: `_parse_triage_choice` returns all-None dict; `_fix_triage_cross_workspace_link` raises `ValueError` (existing behavior).
  - Over-length `fix_hint` (> 1024 bytes): pre-validator rejects with `ValueError` containing `"too long"`.

### Non-Functional

- **NFR-1:** All new tests MUST run under the `plugins/pd/.venv/bin/python -m pytest` venv per CLAUDE.md.
- **NFR-2:** `validate.sh` MUST pass with 0 errors after F116 lands.
- **NFR-3:** Test additions MUST keep per-test wall-clock under 2s (use `@pytest.mark.parametrize` to share fixtures; use session-scoped entities.db fixture for FR-6 matrix). Total suite wall-clock budget: no hard cap, but document the delta in retro.md. (Original +15s cap was unverifiable; replaced with per-test budget.)
- **NFR-4:** No new top-level config keys in `.claude/pd.local.md`.
- **NFR-5:** Doctor check count after F116 = 20 (current 19 + `check_severity_vocab`). Regression test asserts `len(CHECK_ORDER) == 20`.

## Non-Goals

- **NOT introducing `MigrationAbortError` class** — Rationale: M6/M7 raise `RuntimeError`; tests assert on message regex.
- **NOT introducing `InvalidFixHintError` class** — Rationale: `_parse_triage_choice` and downstream code raise `ValueError`; tests assert on message regex.
- **NOT changing M15's INSERT OR REPLACE semantics to INSERT OR IGNORE** — Rationale: M15 already in production; runner-contiguity prevents re-run; test documents semantics rather than asserting a different invariant.
- **NOT building new MCP tools** — Rationale: F116 is coverage + observability only.
- **NOT retroactively backfilling audit log** — Rationale: Counter starts at 0 by design.
- **NOT changing cross-workspace allowlist schema** — Rationale: F115's M17 schema is correct.
- **NOT modifying F111 closure model** — Rationale: F111's `entity_relations(kind='fixes')` is stable.

## Out of Scope (This Release)

- **Test-fixture refactor to `max(MIGRATIONS.keys())` dynamically** — Future consideration: post-F116 hygiene pass.
- **Telemetry log format JSON schema pinning** — Future consideration: from F115 LOW sidecar #3.
- **`CHECK_ORDER` content (not just length) assertion across all sites** — Future consideration: F115 LOW sidecar #4.

## Research Summary

*(Skipped per YOLO mode + user directive — all evidence already in F115 artifacts.)*

### Codebase Analysis (verified post-iteration-1 review)
- F115 spec: `docs/features/115-pd-data-model-followups/spec.md` — full FR-C/FR-E/FR-E.2/FR-B-H3/FR-B-H4 chain
- F115 design rev 2: `docs/features/115-pd-data-model-followups/design.md` — C16/C17/C18 component contracts
- F115 tasks: `docs/features/115-pd-data-model-followups/tasks.md` — T2b.5 (handlers × ACs), T2b.6 (standalone helper file)
- F115 retro: `docs/features/115-pd-data-model-followups/retro.md`
- F115 qa-override: `docs/features/115-pd-data-model-followups/qa-override.md`
- F116 brainstorm source: `docs/brainstorms/116-f115-qa-deferred-source.md`

### Existing Capabilities
- Existing AST check pattern: `plugins/pd/hooks/lib/doctor/check_status_write_path.py` (F109) and `plugins/pd/hooks/lib/doctor/check_audit_counter_write_path.py` (F115) — How they relate: templates for `check_severity_vocab.py` AST visitor structure.
- Existing `@pytest.mark.parametrize` usage in `plugins/pd/hooks/lib/entity_registry/test_database.py` — How it relates: pattern for FR-3/FR-6 matrix tests.
- Existing `_fix_triage_cross_workspace_link` (F115 Cluster E.2) at `fix_actions/__init__.py:431-502` — How it relates: target of FR-7 4-decision tests.
- Existing `_parse_triage_choice` (F115 Cluster E.2) at `fix_actions/__init__.py:395-428` — How it relates: target of FR-9 adversarial parser tests + new `_normalize_and_validate_fix_hint` helper.

## Strategic Analysis

*(Advisory team analysis skipped per YOLO mode + user directive. Risk assessment inlined and recalibrated post-iteration-1 review.)*

### Inline Risk Assessment (rev 2)

- **MED — FR-8 helper extraction touches `CHECK_ORDER` import path.** Moving `check_cross_workspace_parent_uuid` to its own file changes `doctor/__init__.py` import statements. Mitigated by adding a regression test asserting the full `CHECK_ORDER` sequence (FR-8 acceptance criterion).
- **MED — FR-9 introduces a new internal helper `_normalize_and_validate_fix_hint`.** This is a defensive parser layer (not a new exception type or MCP surface), but it does add functional code — explicitly scoped. Mitigated by reusing existing `ValueError` and naming the helper as internal (leading underscore).
- **LOW — Test fixture sweep cost.** Aggressive `@pytest.mark.parametrize` keeps fixture count low.
- **LOW — Severity vocab AST check false positives.** Scoping to `keyword.arg == 'severity'` + `isinstance(keyword.value.value, str)` + path filter for test files prevents over-eager flagging.
- **LOW — Adversarial parser rejects legitimate edge cases.** Allowlist is UUID-hex + `-`, `:`, `|`, `,` characters only; matches the actual fix_hint grammar.
- **LOW — M15 INSERT-OR-REPLACE reset semantics may surprise.** Mitigated by explicit test docstring + edge case row in this PRD.

## Review History

### Review 1 (2026-05-17 — prd-reviewer iteration 1)

**Findings:**
- [blocker] FR-7 named wrong triage branches (allowlist add / reparent / detach / skip vs actual re-attribute parent / re-attribute child / delete relation / grandfather)
- [blocker] FR-6 9-case matrix redefined T2b.5 (kinds × kinds vs F115's actual handlers × ACs)
- [blocker] `audit_log.counter` references — actual key is `_metadata.audit_emit_failed_count`; M15 is INSERT-OR-REPLACE (not preservation-safe)
- [blocker] FR-8 unactionable — function already named; actual target is standalone module file per F115 T2b.6
- [blocker] T3b.3b mislabeled "hash drift" — actual gate is pre-freeze temporal anchor ratio
- [blocker] T3b.3c IO injection technique wrong — `sqlite3.connect` monkeypatch breaks pytest; M6 doesn't catch OperationalError
- [warning] Closed-set vocab multi-severity aggregation not specified
- [warning] AST visitor structure not pinned
- [warning] `InvalidFixHintError` introduced without scope rationale
- [warning] NFR-3 +15s budget unverified
- [warning] SQLite version pin missing
- [warning] Edge case contradiction (positive vs negative matrix)
- [warning] AST check fail mode (throw vs emit) unspecified

**Corrections Applied:**
- Rewrote FR-7 and UC-3 with actual 4 branches + `reason` field on grandfather — Reason: blocker on wrong triage semantics
- Rewrote FR-6 as 3-handlers × 3-ACs = 9-case matrix per F115 tasks.md T2b.5 — Reason: blocker on matrix definition
- Replaced all `audit_log.counter` references with `_metadata.audit_emit_failed_count`; rewrote FR-5 to assert INSERT-OR-REPLACE reset semantics (safe-to-re-run, not value-preservation) — Reason: blocker on factual evidence
- Reframed FR-8 as standalone file extraction per F115 T2b.6 with CHECK_ORDER position preservation regression test — Reason: blocker on actionability
- Rewrote T3b.3b with pre-freeze temporal anchor ratio terminology + RuntimeError message regex — Reason: blocker on operational definition
- Rewrote T3b.3c with Connection-proxy `.execute` injection (NOT global monkeypatch) + OperationalError propagation assertion (NOT MigrationAbortError) — Reason: blocker on testability + non-existent exception class
- Added explicit aggregation rule to FR-1 (sum over all CheckResult.issues across all checks; skipped-check synthetics included) — Reason: closed-set vocab edge case
- Pinned FR-2 AST visitor structure with ast.Call / ast.keyword / ast.Constant path — Reason: AST clarity
- Dropped `InvalidFixHintError`; FR-9 reuses `ValueError` with new internal helper `_normalize_and_validate_fix_hint` (explicitly scoped) — Reason: no new exception class per behavioral constraint
- Replaced NFR-3 +15s budget with per-test 2s budget + suite delta logged in retro — Reason: unverifiable global budget
- Added SQLite version pin to Technical Constraints — Reason: explicit version contract
- Resolved 9-case matrix ambiguity: matrix is 3 handlers × 3 ACs (one of which is positive same-ws case) — Reason: per F115 actual definition, AC-E.2 is the negative/positive case
- Specified AST check fail mode: emits doctor Issue, validate.sh CI enforces — Reason: consistent with existing pattern
- Resolved Open Questions inline: no total field; no new exception classes — Reason: pre-decided to remove downstream blockers
- Recalibrated Strategic Analysis risks (FR-8 + FR-9 → MED, rest LOW) — Reason: honesty about MED-level risks

## Open Questions

*(All Open Questions from rev 1 resolved inline in rev 2 — none remain. Spec phase will validate the FR set against design rev 2 contracts.)*

## Next Steps

Ready for `/pd:create-feature --prd=docs/brainstorms/20260517-053927-f115-qa-deferred.prd.md` to begin implementation. Mode: Standard (per YOLO override). Merge target: `develop` (per user memory).
