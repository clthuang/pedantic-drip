# Plan: 124-dependency-cascade-blocks

Implements design.md (8096dd3). Three SERIAL tasks — the store swap is atomic (a split would leave the suite red mid-stream), semantics ride on the swapped store, materialization/doctor ride on the semantics.

## Task slicing rationale

- **Task 1 = the atomic store swap.** M18 drops `entity_dependencies`; every DB method and every non-migration test fixture must re-target `entity_relations` IN THE SAME TASK or the suite goes red (old cascade BEHAVIOR — tombstone, `planned` — is retained in task 1: it runs unchanged on the rewired methods, so green is meaningful, not vacuous).
- **Task 2 = the semantics flip.** All FOUR predicate sites + cascade body + delete hook + readiness gates change together — they share `_all_blockers_resolved`, and SC3's red-first tests pin the before/after pairs (planned→ready, tombstone→survive, any-edge→unresolved-only).
- **Task 3 = new writers + doctor + sweeps.** Auto-materialization (SC7), the missed-cascade check replacement, retirements, and every comment/docstring sweep — the SC6 grep gate runs here, LAST, when all dispositions have landed.

## Task 1 — Migration 18 + store rewire (D1, D2, D9-fixtures)

- M18 per D1: ONE BEGIN IMMEDIATE, 4 steps, pragma bracketing per the m14 finally idiom, self-edge + orphan LEFT-JOIN filters, created_at = migration ts, fingerprint = `entity_dependencies` ABSENT from sqlite_master. Registered in MIGRATIONS after 17.
- D2 rewire: 5 methods re-target `entity_relations WHERE kind='blocks'`; SELECT aliases + WHERE remap + workspace JOIN on to_uuid; return shapes FROZEN; :9098 comment reworded. cascade_unblock body UNTOUCHED (old behavior on new store).
- **Pulled into task 1 (create-plan i1 — Task-1 gate is unsatisfiable without them, both sites still point at the dropped table):** (a) D5.1 ONLY — delete_entity's manual `DELETE FROM entity_dependencies` (:7868-7872) removed + :7817 docstring reworded (its except re-raises, so EVERY delete_entity call would crash post-M18; the D5.3 unblock-on-delete hook stays in task 2 — old behavior, edges removed no flip, preserved); (b) the narrow D6 slice — checks.py:1146's fallback SELECT rewired to relations + the :1137 comment (test_check3_entity_deps_fallback asserts >=1 warning; the swallowed OperationalError would silently red it).
- Test fixtures: the 8 D9 files port their seeding, ALL raw `db._conn`/table-name assertion SQL (e.g., test_dependencies.py :52/:65/:85/:184/:213/:229, test_register_upsert_split.py:527, test_atomic_promotion.py:313/:322/:332 — illustrative, not exhaustive; the task-1 suite gate catches executable stragglers hard), AND the literal's docstrings/comments/f-string messages in those files (e.g., test_checks.py:1263/:2538, test_database.py:6635, test_register_upsert_split.py:20/:513/:532, test_atomic_promotion.py:18/:303, test_cross_workspace_matrix.py:157 — NOT execution-breaking, so only task 3's SC6 grep would catch them; swept here per i2 W1) to add_dependency/relations, EXCEPT two old-shape carve-outs: migration tests (SC6 carve-out) AND the `_make_db` hand-rolled-schema doctor/fixer tests in test_checks.py/test_fixer.py (decoupled from the migration chain — untouched until task 3, EXCEPT the live-db TestCheck3EntityDepsFallback which task 1's :1146 rewire keeps green, and TestFixStaleDependency which is a TASK-1-ONLY anchor — unchanged in task 1, its :992/:996 assertions FLIP in task 2 (i2 corrected the earlier 'needs no change' mislabel); NEW migration tests = SC1 (CHECK both directions, replay no-op, index/FK survival via PRAGMA probes) + SC2 (per-edge existence, overlap dedup, created_at, orphan + self-edge skip notes, table ABSENT) + SC4 (cycle CTE + self-dep rejection on new store) + both-kwarg guard (ports test_database.py:5547).
- Non-vacuity anchors (named): test_dependencies.py::TestCascadeUnblock and test_fixer.py::TestFixStaleDependency exercise seed->cascade->assert end-to-end on the NEW store with OLD behavior — their green proves the swap.
- M18 is FORWARD-ONLY (create-plan i1 W2): NO MIGRATIONS_DOWN[18] (un-dropping a table is not implementable); the database.py:5557 'versions 11+ are reversible' invariant comment gains an 18-carve-out pointing at 132's cutover; test_database.py's MIGRATIONS_DOWN keys pin stays [11..17].
- Gate: full standard-scope suite green; `git diff` confined to D10 ∩ (D1/D2/D5.1/D6-narrow/D9) files.

## Task 2 — Cascade semantics + gates (D3, D4, D5.3, D8)

- RED-FIRST (write failing tests before the code flips): SC3-a (completing A flips B planned→**ready** + `cascade_ready` event + edge SURVIVES — 3 assertions each red today), SC3-d (delete blocker → edge gone via FK + dependent flips iff remaining resolved; `all([]) is True` empty-set case), SC3-e (cross-workspace flip), deliver-gate red pair (entity with COMPLETED-blocker surviving edge reaches deliver phase; UNRESOLVED-blocker still raises), task_promotion red pair (ready task WITH surviving resolved edge IS returned; task with unresolved blocker is NOT). REGRESSION GUARDS (green before AND after — NOT red-first; create-plan i1 W3): SC3-b's partial-completion no-flip half, SC3-c (wip untouched) — both already hold today via the status=='blocked' guard.
- D4: `_blocker_completed` + `_all_blockers_resolved` + the 5-row pinned table (test parametrizes over EVERY row incl. defensive wont_fix); FOUR sites collapse: :7574 widen (idempotency test: repeat terminal write re-flips nothing), dependency_freshness.py:25, checks.py:1872 (deferred to task 3 with D6), entity_engine.py:248-262 filter.
- D3: `_evaluate_and_flip` shared unit; per-flip re-entrant `db.transaction()`; survive (no remove_dependencies_by_blocker call); `cascade_ready` phase_events row in-transaction; `_run_cascade` unwrap + rollup_parent own-transaction; :7577 stderr warn (type-name only).
- D5.3 (D5.1 landed in task 1): pre-capture `get_dependents` + post-commit `_evaluate_and_flip`; dependency_freshness narrowed to blocked-downstream scan.
- D8: task_promotion :64 gate + :70 unresolved-predicate.
- **Existing-test FLIP INVENTORY (task 2 owns the tombstone->survive / planned->ready assertion inversion — create-plan i1 B1, completed at i2 where BOTH reviewers independently found 3 missed files). The table is AUTHORITATIVE and complete (plan-i3 verified via three independent nets); the grep below is a SUPPLEMENTARY safety net only — for test_entity_engine and test_database its hits land on incidental comments/docstrings, so never skip a table row because its grep hit looks non-flip: `grep -rnE "cascade_unblock|_fix_stale_dependency|cleanup_stale_dependencies" plugins/pd/ --include="test_*.py"`**

| file | asserting lines | old -> new |
|---|---|---|
| test_dependencies.py TestCascadeUnblock | :202-232 (return-set + edge-gone) | edge SURVIVES; flipped set = blocked-only |
| test_database.py | :6851/:6855/:6908/:6910 | len(deps)==0 -> ==1 survived; 'planned' -> 'ready' |
| reconciliation_orchestrator/test_dependency_freshness.py test_stale_edge_cleaned | :43/:47 (+ :39 count==1 on the return — confirm the reworked scan still returns flip-count, else add :39 to the flip) | len==0 -> ==1; 'planned' -> 'ready' |
| doctor/test_fixer.py TestFixStaleDependency | :992/:996 | len==0 -> ==1; 'planned' -> 'ready' |
| workflow_engine/test_entity_engine.py TestCascadeUnblock (NAME COLLISION with test_dependencies' class — different file) | :714/:718 | len==0 -> ==1; 'planned' -> 'ready' |

These stay green through task 1 (old behavior retained) and are INVERTED here, not 'fixed back'.
- Docstring ownership: dependencies.py:19 + dependency_freshness.py:1-4 sweeps land in THIS task (its edits already open both files); task 3's sweep list shrinks accordingly.
- Gate: suite green; every SC3 red-first test now green; diff confined.

## Task 3 — Materialization, doctor, sweeps (D6, D7, schema_v2, SC5/SC6)

- D7: register_entity + upsert_entity auto-materialization (kwargs form, self-edge filter, unresolvable warn-skip); SC7 red-first on BOTH paths asserting edge DIRECTION.
- D6: :1146 rewire (+ :1137 comment); missed-cascade check replaces :1856-1885 (CASE over kind per D4's table; SQL-vs-Python equivalence test with ONE blocker per arm: abandoned brainstorm, dropped backlog, closes=-closed task, resolved bug, completed feature); orphan check (:1788-1818 — through its closing `except sqlite3.Error: pass`, else a dangling except; create-plan i1) + `_fix_remove_orphan_dependency` (:250-266) + fixer.py:45 entry DELETED; `_fix_stale_dependency` (:347-359) renamed to the missed-cascade action, registry updated — **incl. TestFixStaleDependency's THIRD role (plan-i3 W1): test_fixer.py imports the old name at :957 and calls it at :986 (LIVE-db test, outside the _make_db carve-out) — rename the import+call, update the Issue check= id at :978, align assertions to missed-cascade semantics, else module-wide collection ImportError.**
- Sweeps: schema_v2.py:64 comment → names 132 (dependencies.py/dependency_freshness docstrings moved to task 2; checks.py:1137 moved to task 1).
- SC5 test (fires ONLY when all blockers resolved and downstream blocked; multi-blocker partial case does NOT fire); SC6 grep gate (exemptions: m6 CREATE :872-887 + :637 docstring line, the M18 function, migration-test seeding). **The 9 hand-rolled `_make_db` sites are NOT exempt and must be stripped here (plan-i3 W2): test_checks.py :96 CREATE + :1263/:2538/:2550/:3265/:3307; test_fixer.py :91 CREATE + :488/:507.**
- Gate: suite green; hooks 67/67; validate.sh 0 errors; SC6 grep exact; diff-vs-develop file list ⊆ D10 inventory.

## Risks

- **M18 on a populated live DB** — unification volume is small (dozens of edges); INSERT OR IGNORE + UNIQUE dedups; the migration runs at next session-start everywhere. Mitigation: migration tests seed the overlap + orphan + self-edge corpus.
- **Suite-wide fixture churn (task 1)** — 8 files; mechanical but wide. Mitigation: the frozen return shapes keep DICT-based assertions standing; seeding AND the enumerated raw-SQL assertion queries port (the 'only seeding changes' framing was disproved at create-plan i1).
- **Behavior-change blast (task 2)** — planned→ready reaches UI (ready column shipped at 125) and yolo gates (read .meta.json, unaffected). query_ready_tasks consumers see ready tasks appear — that IS FR-8's intent.

## Verification (end of task 3)

Standard-scope suite green; hooks; validate; SC1-SC7 each named green; SC6 grep output pasted into the QA record; diff-gate file list matches D10.
