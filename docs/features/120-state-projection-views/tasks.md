# Tasks: State Projection Views (feature 120)

Execution: STRICTLY SERIAL 1→4 (task 2 appends to task 1's test file; task 4's bench needs tasks 1-3 committed). `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Task 1: views.py + deterministic pins + guard teeth

**Why:** spec SC1 + SC2 + SC6(guard) / design D1, D2, D5, D6.

**Files:** `plugins/pd/hooks/lib/entity_registry/views.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_views.py` (NEW), `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py`

**Do:**
1. `views.py`: dark preamble mirroring events.py (`plugins/pd/hooks/lib/entity_registry/events.py`); module-top `import entity_registry.events` + load-bearing comment (registry replays in registration order — views reference the events table); `_VIEWS_DDL` EXACTLY per design D1 (per-axis `entity_axis_state` GROUP BY + MAX(uuid); pivoted `entity_state` FROM entities with six correlated scalar subqueries; axis-generic column names `pipeline_value`/`execution_value`/`lifecycle_value` + `*_at`); D1's two-precondition CONTRACT text in the module docstring; `register_ddl("views", _VIEWS_DDL)`.
2. `test_views.py`: reuse `_reset_ddl_registry` (test_schema_v2.py:90) + bootstrapped-DB/connect_v2/seeded-workspace-entity idioms (test_display.py); SIX fixtures per design D5: (a) three-axis latest; (b) out-of-order timestamp — later uuid + earlier timestamp wins; (c) rowid-confound — pre-mint two uuids via `generate_uuid7()`, raw-INSERT the LARGER first with DISTINCT to_values, assert the larger-uuid value returned (kills no-aggregate bare-column and rowid-latest rewrites); (d) single-axis entity — pivoted row's other four state columns NULL, per-axis has exactly one row; (e) zero-event entity — absent from `entity_axis_state`, present in `entity_state` with all-NULL state; (f) NULL-to_value latest → view reports NULL ("latest non-null" is the rejected semantic). SC2: parametrized INSERT/UPDATE/DELETE × {entity_axis_state, entity_state} → `sqlite3.OperationalError` (6 pins); `PRAGMA table_info(entities)` column set == 118's DDL list.
3. `test_schema_v2.py`: `_V2_DARK_MODULES` += `"views.py"`; `_V2_LIVE_REFERENCE_NEEDLES` += `entity_registry.views` / `from entity_registry import views` / `from .views import`; 3 seeded-offender teeth tests (one per spelling — write them RED first against the un-extended needle set).

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_views.py plugins/pd/hooks/lib/entity_registry/test_schema_v2.py -q` green; teeth demonstrated red pre-needles.

## Task 2: replay property test

**Why:** spec SC3 / design D4.

**Files:** `plugins/pd/hooks/lib/entity_registry/test_views.py`

**Do:** Append the property test per design D4 EXACTLY: `MASTER_SEED = 0x120` module constant; `random.Random(MASTER_SEED)` mints per-case seeds; each case uses its OWN `random.Random(case_seed)` for EVERY draw (counts, axes, values incl. None, actors, out-of-order timestamps, the shuffled-insert coin flip, the uuid shuffle — global `random` never touched); 1-8 entities × 0-12 events; ~half the cases pre-mint + shuffle uuids and raw-INSERT on the connect_v2 conn (insertion order ≠ uuid order), other half write through `append_event`; ONE bootstrapped DB for all 200 cases, per-case fresh entity uuids, NO event cleanup (immutability triggers forbid DELETE — isolation is `WHERE entity_uuid IN (case uuids)`); replay = pure-Python max-uuid fold per (entity, axis); assert field-by-field (`to_value`, `event_uuid`, `timestamp`) against `entity_axis_state` AND the pivoted triple against `entity_state`; failure message carries `seed=` + the full sequence; wall-clock assert < 5s around the case loop, assert message carrying the measured elapsed.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/test_views.py -q` green; run TWICE — identical pass/fail outcome and case STRUCTURE (counts/axes/values/coin-flips all derive from MASTER_SEED); raw uuid7 values legitimately DIFFER run-to-run (generate_uuid7 encodes wall-clock, not the seed — expected; do NOT seed uuid minting to force identity); duration well under 5s with the elapsed printed in the assert message.

## Task 3: #061 guard

**Why:** spec SC4 / design D3 + D5's #061 test bullet.

**Files:** `plugins/pd/hooks/lib/entity_registry/events.py`, `plugins/pd/hooks/lib/entity_registry/test_events.py`

**Do:**
1. `events.py`: design D3's EXACT probe as the FIRST statement of `append_event` (before the `in_transaction` branch): `PRAGMA foreign_keys` fetchone; `row is None or row[0] != 1` → `ValueError` with D3's message (names connect_v2, per-connection pragma, #061). One docstring line added to the factory-requirement block.
2. `test_events.py`: NEW tests (TDD — red against unguarded append_event): (a) bare `sqlite3.connect` standalone → `pytest.raises(ValueError, match="connect_v2")` + `SELECT COUNT(*) FROM events` == 0; (b) bare conn with an already-open transaction (compose path) → same raise, zero rows; (c) connect_v2 conn passes unchanged (one smoke — the existing suite is the broader net). `test_bare_connection_inserts_the_same_orphan_successfully` (:506) NOT modified — it exercises raw INSERT, structurally orthogonal to the guard.

**Verify:** guard tests (a)/(b) demonstrated RED before events.py's probe lands (bare-conn append currently succeeds pre-guard), green after; `pytest plugins/pd/hooks/lib/entity_registry/test_events.py -q` green; `git diff plugins/pd/hooks/lib/entity_registry/test_events.py` shows additions only around the preserved :506 test.

## Task 4: latency baseline + integration QA

**Why:** spec SC5 / design D7; spec SC6's suite/validate/doctor portion / design Testing Strategy #5 (SC6's teeth portion lives in task 1 via D6).

**Files:** `docs/features/120-state-projection-views/latency-baseline.md` (NEW)

**Do:**
1. Confirm tasks 1-3 COMMITTED and tree clean (`git status --porcelain` empty — the bench exits 2 otherwise); run `bash plugins/pd/hooks/tests/bench-session-start.sh` capturing stdout REGARDLESS of exit code (its internal NFR2 gate is not ours; medians echo before that check), then `git restore plugins/pd/hooks/tests/bench-results.txt` (the script overwrites this tracked do-not-re-commit file — tree must end clean); write `latency-baseline.md`: both medians (merge-base + HEAD — note they estimate the same quantity on this branch), raw script output verbatim, machine context (`sw_vers`, `uname -m`, `sysctl -n machdep.cpu.brand_string`), reproduction command, and the SCOPE STATEMENT (empty-HOME fixed session-start overhead, median-only — NOT PRD NFR-3's populated p50/p95 read-latency baseline; that CAPTURE is feature 126's, verification 127's, per roadmap.md:42).
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` (0 errors); `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor count unchanged (EXPECTED_CHECK_COUNT pin in suite); `git diff develop...HEAD --stat` vs inventory BY NAME: views.py (NEW), events.py, test_views.py (NEW), test_events.py, test_schema_v2.py, latency-baseline.md (NEW) + feature docs (backlog-manual.md's #061 closure happens at finish, not here).

**Verify:** all green; artifact carries every required section; no unsanctioned files.

## Summary

| Task | Depends on | Collides with |
|------|-----------|---------------|
| 1 | — | — |
| 2 | 1 (same test file) | — |
| 3 | — (file-disjoint; serialized after 2 for reviewer clarity only — the property test's raw-INSERT half is unguarded regardless of order) | — |
| 4 | 1-3 committed | — |

Order: 1 → 2 → 3 → 4. Concurrency: NONE.
