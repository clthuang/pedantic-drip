# Plan: Rotted Doctor-Check Fix

## Implementation Order

### Stage 1: Foundation

1. **`_run_live_schema_query` helper + unit tests** — the surface/tolerate discriminator, TDD-first
   - **Why this item:** Design Component [A]; every rewrite routes through it, so it must exist and be proven before any call site changes.
   - **Why this order:** No dependencies; all Stage 2 rewrites consume its `(rows, tolerated)` contract.
   - **Deliverable:** Helper in `doctor/checks.py` returning `tuple[list[tuple], bool]` with PRAGMA-probe discrimination and EMIT-ONCE dedupe; unit tests for surface branch, tolerate branch, dedupe, and happy path.
   - **Complexity:** Medium
   - **Files:** `plugins/pd/hooks/lib/doctor/checks.py`, `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** New helper tests pass; no existing test touched yet.

2. **Live-schema test fixtures** — `_make_live_db()`, `_insert_workspace()`, live `_register_feature(..., workspace_uuid=)`
   - **Why this item:** Design Component [D] fixture-migration plan; Stage 2 behavioral tests and Stage 4 scoping tests all build on these.
   - **Why this order:** No dependencies; parallel with item 1.
   - **Deliverable:** Fixture helpers in `test_checks.py` built on the real `EntityDatabase(tmp_path)` bootstrap; legacy `_make_db`/`_register_feature` untouched.
   - **Complexity:** Simple
   - **Files:** `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** A smoke test registers one feature via the live fixture and reads it back with `kind='feature'`, AND asserts `_insert_workspace` round-trips through the resolution query (`SELECT uuid FROM workspaces WHERE project_root IS NOT NULL AND project_root = ?` returns the inserted uuid) — proving `scoped=True` is reachable before Stage 4 relies on it (guards the repo's silent-INSERT gotcha from defeating every scoping test).

### Stage 2: Core Implementation

1. **Rewrite `check_feature_status` (:709) and `check_brainstorm_status` (:988, :1083)** — candidate-set consumers
   - **Why this item:** Design Component [B] rows 1-3; the simple `entity_type → kind` renames routed through the helper.
   - **Why this order:** Needs the helper (Stage 1.1) and live fixtures for repointed tests (Stage 1.2).
   - **Deliverable:** Three sites rewritten (`kind = 'feature'` / `kind = 'brainstorm'`), `:1083` adapted to list return (`rows[0] if rows else None`), enclosing wrappers at `:985-993` and `:1066-1099` retained; their behavioral suites repointed to live fixtures WITH design [D].1's non-vacuity guard: each repointed suite asserts its check's candidate set is NON-EMPTY where the fixture registers rows (spec SC#3 smoke) — a suite that silently routes to the tolerate branch cannot pass.
   - **Complexity:** Medium
   - **Files:** `plugins/pd/hooks/lib/doctor/checks.py`, `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** Repointed `check_feature_status`/`check_brainstorm_status` suites pass against live schema, including the non-vacuity assertions.

2. **Rewrite `check_entity_orphans` control flow (:1383-1454, :1488)** — two row-sets, scoping, tolerate gates
   - **Why this item:** Design Component [B] rows 4-6 + the reconciliation section: `db_features_all` (always) + `db_features_step1` (two-arm when scoped), workspace resolution mirroring `checks.py:582-592`, merged step-1 loop (scoped bypasses `local_entity_ids`), steps 2/4 gated on `features_tolerated`/`brainstorms_tolerated`.
   - **Why this order:** Needs the helper; most intricate change, isolated from item 1's simple renames.
   - **Deliverable:** Rewritten `check_entity_orphans` per the design's pinned code blocks; `project_id` kwarg no longer read. TDD front-load for the novel behavior: [D].5 cases (a) foreign-workspace exclusion and (b) unknown-bucket inclusion are written FAILING FIRST in this item, then the control flow is implemented against them (remaining scoping matrix lands in Stage 4).
   - **Complexity:** Complex
   - **Files:** `plugins/pd/hooks/lib/doctor/checks.py`, `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** Repointed `test_check7_*` suite passes (with [D].1 non-vacuity assertions); front-loaded scoping cases (a)/(b) pass; remaining scoping tests (Stage 4) pin the rest.

### Stage 3: Deletion

1. **Delete `check_project_attribution` full deregistration surface**
   - **Why this item:** Design Component [C]; spec In-Scope DELETE decision (surface duplicated by live `check_unknown_workspace_orphans`).
   - **Why this order:** Independent of Stage 2 code paths but sequenced after so test-suite churn happens once; before Stage 4 so the scan test never sees the dead `project_id` query.
   - **Deliverable:** Removed: check function; `doctor/__init__.py` import/:55 `CHECK_ORDER`/:97 `_ENTITY_DB_CHECKS` entries; `_fix_project_attribution` (`fix_actions/__init__.py:348-359`); `fixer.py` import (:21) + `_SAFE_PATTERNS` entry (:52); `test_doctor.py` `expected_names` entry (:24); its cases in `test_checks.py`/`test_fix_actions.py`/`test_fixer.py`. KEPT: `EntityDatabase.backfill_project_ids`, `check_unknown_workspace_orphans`.
   - **Complexity:** Simple
   - **Files:** `plugins/pd/hooks/lib/doctor/checks.py`, `doctor/__init__.py`, `doctor/fixer.py`, `doctor/fix_actions/__init__.py`, `doctor/test_doctor.py`, `doctor/test_checks.py`, `doctor/test_fix_actions.py`, `doctor/test_fixer.py`
   - **Verification:** `grep -rn check_project_attribution plugins/` → zero non-history hits; `test_doctor.py` CHECK_ORDER assertion passes; spec SC#6 fixer-net check: `grep -n "entity_type\|project_id" doctor/fix_actions/__init__.py doctor/fixer.py` shows only allowed matches (live `workspaces.project_id_legacy` usage and message text — no dropped-column SQL).

### Stage 4: Behavioral Test Coverage

1. **Scoping, tolerate, surface, and empty-DB tests** — design [D].3-[D].7
   - **Why this item:** Pins the new behavior non-vacuously (each scoping test fails if the two-arm predicate is removed; tolerate test proves the steps-2/4 skip).
   - **Why this order:** Needs Stages 1-3 complete (final behavior in place).
   - **Deliverable:** Tests: (a) foreign-workspace entity, missing dir, EMPTY features dir → info not warning; (b) unknown-bucket entity, missing dir, scoped → warning; (c) foreign-real-workspace on-disk dir → not step-2-flagged; (d) 0/>1 workspace matches → legacy branching; tolerate whole-check zero Issues (legacy fixture + registered feature + on-disk dir); surface branch → one `error` Issue; empty live DB → all three checks clean.
   - **Complexity:** Medium
   - **Files:** `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** All new tests pass; mutating the two-arm predicate to single-arm makes (a)/(b) fail (spot-check).

2. **Committed EXPLAIN scan test** — design [D].2, durable form of spec SC#1
   - **Why this item:** Spec SC#5's committed scan; prevents the next column drop from rotting silently.
   - **Why this order:** After Stage 3 so the deleted `:1558` site is gone; the scan must pass on the final code.
   - **Deliverable:** AST-walk of `checks.py` constant SQL in `execute()` calls; `EXPLAIN` each against a live-schema connection; assert zero failures.
   - **Complexity:** Simple
   - **Files:** `plugins/pd/hooks/lib/doctor/test_checks.py`
   - **Verification:** Scan test passes; temporarily re-adding an `entity_type` query makes it fail (spot-check).

### Stage 5: Integration Verification

1. **Full-suite + live doctor run**
   - **Why this item:** Spec success criteria demand all existing doctor tests pass and the live false-positive class disappears.
   - **Why this order:** Final gate over the completed change.
   - **Deliverable:** Green `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/`; a live doctor run on this repo showing zero entity_orphans false positives for the 533-entity DB and zero `project_attribution` issues.
   - **Complexity:** Simple
   - **Files:** none (verification only)
   - **Verification:** Pytest exit 0; doctor output inspected with an explicit false-positive discrimination step — cross-reference every remaining "in DB but feature directory not found" / "has .meta.json but no entity in DB" flag against actual on-disk directory existence and DB membership, so only genuinely-both-present entities count against SC#2 (a truly-deleted directory is a TRUE positive, not a failure).

## Dependency Graph

```
S1.1 helper ───┬──→ S2.1 renames ──┬──→ S3.1 deletion ──┬──→ S4.1 behavior tests ──┬──→ S5.1 verify
               └──→ S2.2 orphans ──┘                    └──→ S4.2 scan test ───────┘
S1.2 fixtures ─┬──→ S2.1 renames
               └──→ S2.2 orphans
```

(S2.1 and S2.2 each require BOTH S1.1 and S1.2. Parallelism is stage-level only: items within a stage that touch the same files — S1.1/S1.2 both edit `test_checks.py`; S2.1/S2.2 both edit `checks.py` and `test_checks.py` — MUST serialize; do not dispatch them to concurrent worktrees.)

## Rollback & Refactor Notes

- **Rollback boundary:** each stage exits with a green test suite and its own commit — any stage's commit is a safe rollback point (git-backed, no external side effects).
- **Refactor pass:** none needed as a separate step — the rewrites are mechanical (column renames, one control-flow consolidation already pinned in design code blocks); cleanup happens within each task's TDD cycle.

## Risk Areas

- **S2.2 (check_entity_orphans rewrite):** most intricate — two row-sets, scoped/unscoped partition, tolerate gates. Mitigated by the design's pinned code blocks and [D].5's non-vacuous tests.
- **Suite repointing (S2.1):** legacy suites assert message strings and Issue counts; repointing must preserve assertions, changing only fixtures. Any assertion change is a red flag to re-check behavior.
- **AST scan false-positives (S4.2):** f-string/parameterized SQL must be skipped exactly as the authoring harness did (constant-only extraction).

## Testing Strategy

- Unit tests for: `_run_live_schema_query` (4 branches), fixture helpers (smoke).
- Behavioral tests for: three rewritten checks on live fixtures; scoping matrix (a)-(d); tolerate/surface/empty-DB boundaries.
- Static test for: EXPLAIN scan over all `checks.py` SQL.
- Integration: full doctor pytest suite + live doctor run on this repo.

## Definition of Done

- [ ] All plan items implemented
- [ ] All doctor tests pass (existing + new)
- [ ] Live doctor run: zero entity_orphans false positives, zero project_attribution issues
- [ ] EXPLAIN scan test committed and green
- [ ] grep zero for `check_project_attribution` outside git history
