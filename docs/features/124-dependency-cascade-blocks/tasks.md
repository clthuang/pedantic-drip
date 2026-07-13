# Tasks: 124-dependency-cascade-blocks

Serial. Each task ends with the full standard-scope suite green + a confined-diff check against D10's inventory. Full artifact set (spec/design/plan) attached at dispatch — tasks are thin pointers.

## Task 1 — Migration 18 + store rewire

**Implements:** D1, D2, D9 fixture ports. **Files:** database.py (M18 + registry entry, 5 methods, :9098 comment), the 8 D9 test files (fixture seeding; migration tests keep old shape).
**Acceptance:** SC1 (CHECK both directions, replay no-op via absent-table fingerprint, UNIQUE + FKs + indices survive per PRAGMA probes), SC2 (per-edge parity, overlap dedup, created_at populated, orphan + self-edge stderr notes, `entity_dependencies` ABSENT), SC4 (cycle CTE + self-dep rejection on new store), both-kwarg guard ported. Old cascade behavior UNCHANGED on the new store (green = swap correct, not vacuous). Full suite green.

## Task 2 — Cascade semantics + gates

**Implements:** D3, D4, D5, D8. **Files:** dependencies.py (body + `_evaluate_and_flip` + `_all_blockers_resolved` + `_blocker_completed` + :19 docstring), database.py (:7574 widen, :7577 warn, delete_entity manual-DELETE removal + :7817 docstring, pre-capture hook), entity_engine.py (:536-540 unwrap, :248-262 gate filter), dependency_freshness.py (:25 predicate, blocked-downstream narrowing, module docstring), task_promotion.py (:64 gate, :70 predicate).
**Acceptance:** ALL red-first pairs from plan Task-2 written FIRST and red (SC3 a-e incl. `cascade_ready` event row, edge survival, `all([]) is True` deletion case, cross-workspace; deliver-gate pair; task_promotion pair); D4 table test parametrized over every row; :7574 idempotency (repeat terminal write no-ops). Then green. Full suite green.

## Task 3 — Materialization, doctor, sweeps

**Implements:** D6, D7, schema_v2 comment, SC5/SC6 gates. **Files:** database.py (register/upsert materialization), checks.py (:1146 rewire + :1137 comment, :1856 replace, :1788-1816 delete), fix_actions/__init__.py (:250-266 delete, :347-359 rename), fixer.py (:45 registry), schema_v2.py (:64 comment → 132).
**Acceptance:** SC7 red-first both paths asserting edge DIRECTION; SC5 fires-only-when test (multi-blocker partial does NOT fire); SQL-vs-Python equivalence with one blocker per CASE arm (5 arms); SC6 grep exact against the exemption model (m6 :872-887 + :637, the M18 function, migration-test seeding). Full suite green; hooks 67/67; validate 0 errors.
