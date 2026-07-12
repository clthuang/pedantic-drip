# Tasks: Two-Axis Phase/Status Schema (feature 122)

Execution: STRICTLY SERIAL 1→3 (task 2 appends to task 1's test file; task 3's baseline re-derivation measures the complete feature). `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Task 1: axes.py + shape/registration/view pins

**Why:** spec SC1 + SC4 / design D1, D2 (build + registration), D3, D4.

**Files:** `plugins/pd/hooks/lib/entity_registry/axes.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_axes.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` (membership line ONLY)

**Do:**
0. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"axes.py"` — THIS LINE ONLY, atomic with the file's creation: the ships-dark scan (test_schema_v2.py:551-568) runs on every suite invocation over all non-test *.py, and axes.py's own module-top `from entity_registry import views` trips needle :543 unless exempted — without this, any suite run between tasks 1 and 3 fails on an unexplained offender (120/121 precedent: membership landed with module creation). Needle widening + teeth stay in Task 3.
1. `axes.py`: dark preamble mirroring `plugins/pd/hooks/lib/entity_registry/views.py`; module-top `from entity_registry import views` + LOAD-BEARING comment (registry replays in registration order — the named view SELECTs FROM entity_state, so the chain is events → views → axes; D4). `PIPELINE_PHASES = ("brainstorm", "specify", "design", "create-plan", "implement", "finish")`; `EXECUTION_STATUSES = ("backlog", "prioritised", "ready", "wip", "blocked", "documenting", "completed")`; exported frozenset views of both. Module-load assertion: no vocabulary value contains `'` (fails LOUD at import — never emits malformed DDL). `_VOCAB_TRIGGER_DDL` interpolated per D2's pinned mechanism (`"(" + ", ".join(f"'{v}'" for v in ...) + ")"`) with BOTH triggers verbatim from design D2 (events_vocab_pipeline + events_vocab_execution; `BEFORE INSERT ON events`; `WHEN NEW.axis = '{axis}' AND NEW.to_value IS NOT NULL AND NEW.to_value NOT IN (...)`; `RAISE(ABORT, 'out-of-vocabulary to_value ' || quote(NEW.to_value) || ' on {axis} axis (feature 122 — see entity_registry/axes.py {CONSTANT})')`). `entity_phase_status` view DDL EXACTLY per D3 (five columns: entity_uuid, pipeline_phase, pipeline_at, execution_status, execution_at — thin rename over entity_state, zero new MAX); `register_ddl("axes", <view DDL>)` at import. `register_vocab_ddl()`: assert `sqlite3.sqlite_version_info >= (3, 47, 0)` FIRST (loud pre-3.47 failure), then `register_ddl("axes_vocab_triggers", _VOCAB_TRIGGER_DDL)`. `is_vocab_registered()` (canonical name — D4's export list governs) LATCH-FREE: returns whether owner `"axes_vocab_triggers"` is CURRENTLY in the DDL registry (scan, not a module flag) — the snapshot/restore idiom removes the owner between tests, so a sticky latch would silently skip re-registration (vacuous teeth) or trip duplicate-owner ValueError. Docstring: D3's #067 inheritance note (per-entity reads inherit entity_state's O(total-events) cost — consumers use entity_axis_state per-entity) + lifecycle-is-vocab-free (renames carry type_ids).
2. `test_axes.py`: define a LOCAL snapshot/restore registry fixture (pytest fixtures are not cross-importable without a conftest and the package deliberately has none — copy the test_views.py pattern, do not import test_schema_v2's) + bootstrapped-DB/connect_v2/seeded-workspace-entity idioms (test_views.py). D5 group 1 — `PIPELINE_PHASES == (...)` and `EXECUTION_STATUSES == (...)` tuple equality (order pinned; the 126 precedent — downstream features assert against these). Registration semantics — fresh registry: `is_vocab_registered()` False; after `register_vocab_ddl()`: True; second call → `pytest.raises(ValueError)` (register_ddl duplicate-owner). D5 group 5 — `PRAGMA table_info(entity_phase_status)` name list == `["entity_uuid", "pipeline_phase", "pipeline_at", "execution_status", "execution_at"]`; round-trip: seed ONE entity with DISTINCT in-vocab values AND DISTINCT timestamps on the two axes (e.g. pipeline `design`@t1, execution `wip`@t2), assert ALL FOUR axis columns equal their `entity_axis_state` counterparts (a swapped alias OR swapped `*_at` source is red — non-vacuity pin); INSERT/UPDATE/DELETE on the view → `sqlite3.OperationalError` (120's pin pattern).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_axes.py -q` green.

## Task 2: trigger-teeth battery

**Why:** spec SC2 + SC3 + SC6(structural) / design D2 semantics, D5 groups 2-4 + 7.

**Files:** `plugins/pd/hooks/lib/entity_registry/test_axes.py`

**Do:** Append: an OPT-IN (non-autouse) fixture registering `register_vocab_ddl()` ONCE per snapshot scope (guarded by `is_vocab_registered()` where re-entry is possible). NON-AUTOUSE is load-bearing: the leak-detection pin below bootstraps WITHOUT triggers — an autouse fixture would break it or render the teeth vacuous. D5 group 2 — acceptance: EVERY member of both tuples accepted on its axis via raw `conn.execute` INSERT (13 probes: 6 pipeline + 7 execution — parametrize over the constants so vocabulary drift auto-updates the matrix); rejections: out-of-vocab per axis (`'bogus-value'`), cross-axis vocabulary (`'wip'` on pipeline, `'design'` on execution), wrong case (`'WIP'` on execution) — each `pytest.raises(sqlite3.IntegrityError)` EXACTLY (RAISE(ABORT) in trigger = SQLITE_CONSTRAINT_TRIGGER; 119 precedent) with BOTH the axis name and the offending value asserted in `str(excinfo.value)` (expression-RAISE, D2); NULL to_value accepted on ALL THREE axes; lifecycle acceptance: free-text + type_id-shaped (`feature:122-two-axis-phase-status-schema`) + legacy `completed` (no lifecycle trigger exists). D5 group 3 — leak-detection pin: a bootstrap WITHOUT `register_vocab_ddl()` accepts an out-of-vocab pipeline INSERT (proves sibling suites structurally unaffected — SC6's guarantee). D5 group 4 — `from workflow_engine.kanban import derive_kanban, PHASE_TO_KANBAN` (the LIVE module at plugins/pd/hooks/lib/workflow_engine/kanban.py, importable via hooks/lib/conftest.py — precedent import from this same directory: test_backfill.py:1112; tests importing live code is unrestricted — the dark guard polices the reverse), enumerate reachable outputs = `set(PHASE_TO_KANBAN.values())` ∪ terminal-branch literals {completed, blocked, backlog} (literals inside derive_kanban's body, not module constants), assert every output ∈ EXECUTION_STATUSES AND the set is a STRICT subset (six ⊂ seven — `ready` unreachable from derive_kanban by design, FR-8's slot). D5 group 7 — comment on the rejection probes noting raw-INSERT = FR122-3's structural proof (triggers can't be bypassed by skipping append_event).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_axes.py -q` green (the rejection-message asserts themselves cover axis + quoted-value presence per Do above — the binary gate is the coded `str(excinfo.value)` assertions, no manual step).

## Task 3: dark-guard teeth + integration QA

**Why:** spec SC5 + SC6(suite) + SC7 / design D5 group 6, Testing Strategy 2-3, FR122-5.

**Files:** `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py`

**Do:**
1. `test_schema_v2.py` (the `_V2_DARK_MODULES` membership line landed in Task 1 — no membership work here): `_V2_LIVE_REFERENCE_NEEDLES` += `entity_registry.axes` / `from entity_registry import axes` / `from .axes import`; 3 seeded-offender teeth tests, one per spelling, written RED first against the un-extended needle set (121's exact pattern).
2. Integration QA — FR122-5 baseline RE-DERIVED, not the pinned literal (FR122-5, spec.md:28, mandates re-derivation on the feature-base commit — the spec carries NO pinned literal; 3631 is the 126-finish figure, context only): `git worktree add <scratch> $(git merge-base HEAD develop)`, run the IDENTICAL `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q` there, record that total as the true pre-122 baseline, remove the worktree; then the same command on the feature branch and diff the totals; `git diff develop...HEAD --stat` shows ZERO edits to test_events.py / test_views.py / test_meta_projection.py (SC6) and matches D7 inventory BY NAME: axes.py (NEW), test_axes.py (NEW), test_schema_v2.py, spec.md (landed in design commit 138a3d82) + feature docs; `./validate.sh` 0 errors; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged; repo-wide grep: zero live importers of axes (needle spellings) outside entity_registry tests. SC7's roadmap clause pre-satisfied at specify (903f3964 — docs/projects/P004-entity-db-redesign/roadmap.md entries 9/12/15), mirroring the D6 callout: no action here.

**Verify:** all green; teeth demonstrated red pre-needles; suite delta recorded; no unsanctioned files.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | — |
| 2 | 1 (same test file) | — |
| 3 | 1-2 (baseline measures complete feature; guard needles reference axes.py) | — |

Order: 1 → 2 → 3. Concurrency: NONE.
