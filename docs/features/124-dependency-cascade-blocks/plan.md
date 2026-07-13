# Plan: 124-dependency-cascade-blocks

Implements design.md (8096dd3). Three SERIAL tasks — the store swap is atomic (a split would leave the suite red mid-stream), semantics ride on the swapped store, materialization/doctor ride on the semantics.

## Task slicing rationale

- **Task 1 = the atomic store swap.** M18 drops `entity_dependencies`; every DB method and every non-migration test fixture must re-target `entity_relations` IN THE SAME TASK or the suite goes red (old cascade BEHAVIOR — tombstone, `planned` — is retained in task 1: it runs unchanged on the rewired methods, so green is meaningful, not vacuous).
- **Task 2 = the semantics flip.** All FOUR predicate sites + cascade body + delete hook + readiness gates change together — they share `_all_blockers_resolved`, and SC3's red-first tests pin the before/after pairs (planned→ready, tombstone→survive, any-edge→unresolved-only).
- **Task 3 = new writers + doctor + sweeps.** Auto-materialization (SC7), the missed-cascade check replacement, retirements, and every comment/docstring sweep — the SC6 grep gate runs here, LAST, when all dispositions have landed.

## Task 1 — Migration 18 + store rewire (D1, D2, D9-fixtures)

- M18 per D1: ONE BEGIN IMMEDIATE, 4 steps, pragma bracketing per the m14 finally idiom, self-edge + orphan LEFT-JOIN filters, created_at = migration ts, fingerprint = `entity_dependencies` ABSENT from sqlite_master. Registered in MIGRATIONS after 17.
- D2 rewire: 5 methods re-target `entity_relations WHERE kind='blocks'`; SELECT aliases + WHERE remap + workspace JOIN on to_uuid; return shapes FROZEN; :9098 comment reworded. cascade_unblock body UNTOUCHED (old behavior on new store).
- Test fixtures: the 8 D9 files port their seeding to add_dependency/relations EXCEPT migration tests (old-shape seeding per SC6 carve-out); NEW migration tests = SC1 (CHECK both directions, replay no-op, index/FK survival via PRAGMA probes) + SC2 (per-edge existence, overlap dedup, created_at, orphan + self-edge skip notes, table ABSENT) + SC4 (cycle CTE + self-dep rejection on new store) + both-kwarg guard (ports test_database.py:5547).
- Gate: full standard-scope suite green; `git diff` confined to D10 ∩ (D1/D2/D9) files.

## Task 2 — Cascade semantics + gates (D3, D4, D5, D8)

- RED-FIRST (write failing tests before the code flips): SC3-a (completing A flips B planned→**ready** + `cascade_ready` event + edge SURVIVES — 3 assertions each red today), SC3-b (partial multi-blocker: no flip, no event), SC3-c (wip untouched), SC3-d (delete blocker → edge gone via FK + dependent flips iff remaining resolved; `all([]) is True` empty-set case), SC3-e (cross-workspace flip), deliver-gate red pair (entity with COMPLETED-blocker surviving edge reaches deliver phase; UNRESOLVED-blocker still raises), task_promotion red pair (ready task WITH surviving resolved edge IS returned; task with unresolved blocker is NOT).
- D4: `_blocker_completed` + `_all_blockers_resolved` + the 5-row pinned table (test parametrizes over EVERY row incl. defensive wont_fix); FOUR sites collapse: :7574 widen (idempotency test: repeat terminal write re-flips nothing), dependency_freshness.py:25, checks.py:1872 (deferred to task 3 with D6), entity_engine.py:248-262 filter.
- D3: `_evaluate_and_flip` shared unit; per-flip re-entrant `db.transaction()`; survive (no remove_dependencies_by_blocker call); `cascade_ready` phase_events row in-transaction; `_run_cascade` unwrap + rollup_parent own-transaction; :7577 stderr warn (type-name only).
- D5: manual DELETE removal + :7817 docstring reword (token dropped); pre-capture `get_dependents` + post-commit `_evaluate_and_flip`; dependency_freshness narrowed to blocked-downstream scan.
- D8: task_promotion :64 gate + :70 unresolved-predicate.
- Gate: suite green; every SC3 red-first test now green; diff confined.

## Task 3 — Materialization, doctor, sweeps (D6, D7, schema_v2, SC5/SC6)

- D7: register_entity + upsert_entity auto-materialization (kwargs form, self-edge filter, unresolvable warn-skip); SC7 red-first on BOTH paths asserting edge DIRECTION.
- D6: :1146 rewire (+ :1137 comment); missed-cascade check replaces :1856 (CASE over kind per D4's table; SQL-vs-Python equivalence test with ONE blocker per arm: abandoned brainstorm, dropped backlog, closes=-closed task, resolved bug, completed feature); orphan check (:1788-1816) + `_fix_remove_orphan_dependency` (:250-266) + fixer.py:45 entry DELETED; `_fix_stale_dependency` (:347-359) renamed to the missed-cascade action, registry updated.
- Sweeps: dependencies.py:19, dependency_freshness.py:1-4 docstrings; schema_v2.py:64 comment → names 132.
- SC5 test (fires ONLY when all blockers resolved and downstream blocked; multi-blocker partial case does NOT fire); SC6 grep gate (exemptions: m6 CREATE :872-887 + :637 docstring line, the M18 function, migration-test seeding).
- Gate: suite green; hooks 67/67; validate.sh 0 errors; SC6 grep exact; diff-vs-develop file list ⊆ D10 inventory.

## Risks

- **M18 on a populated live DB** — unification volume is small (dozens of edges); INSERT OR IGNORE + UNIQUE dedups; the migration runs at next session-start everywhere. Mitigation: migration tests seed the overlap + orphan + self-edge corpus.
- **Suite-wide fixture churn (task 1)** — 8 files; mechanical but wide. Mitigation: the frozen return shapes mean ASSERTIONS mostly stand; only seeding changes.
- **Behavior-change blast (task 2)** — planned→ready reaches UI (ready column shipped at 125) and yolo gates (read .meta.json, unaffected). query_ready_tasks consumers see ready tasks appear — that IS FR-8's intent.

## Verification (end of task 3)

Standard-scope suite green; hooks; validate; SC1-SC7 each named green; SC6 grep output pasted into the QA record; diff-gate file list matches D10.
