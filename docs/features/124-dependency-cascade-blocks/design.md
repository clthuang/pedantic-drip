# Design: 124-dependency-cascade-blocks

Implements spec.md (61a383d). All spec D-items resolved here; contracts pinned in ONE place each.

## D1 — Migration 18: entity_relations widening + unification + drop

Highest live migration = 17 (15 = audit counter :5403; 16 = no-op stub :5448; 17 per PRD retention note). **Migration 18**, one function, replay-safe early-return (fingerprint: `blocks` present in the rebuilt CHECK — mirror `_v14_schema_already_applied` shape):

1. Copy-rename rebuild of `entity_relations` per the m14 CHECK-widening helper pattern (database.py:4484): `PRAGMA foreign_keys=OFF` + verify, `BEGIN IMMEDIATE`, CREATE `entity_relations_new` with `kind CHECK(kind IN ('fixes','blocks'))`, columns/FKs byte-identical otherwise, `INSERT INTO ... SELECT` via `PRAGMA table_info` column discovery, DROP old, RENAME, recreate ALL three indices incl. `idx_entity_relations_unique(from_uuid,to_uuid,kind)` (SC1 asserts via `PRAGMA index_list` + `foreign_key_list`), `PRAGMA foreign_key_check` pre-commit, `foreign_keys=ON`.
2. Unification copy: `INSERT OR IGNORE INTO entity_relations (from_uuid, to_uuid, kind, created_at) SELECT blocked_by_uuid, entity_uuid, 'blocks', :migration_ts FROM entity_dependencies` — **mapping: from_uuid = blocked_by_uuid (the blocker), to_uuid = entity_uuid (the blocked)**; rows whose either uuid misses `entities` are skipped with one stderr line each (the old table has no FK — pre-filter via LEFT JOIN, don't let `foreign_key_check` abort the batch).
3. `depends_on_features` materialization: scan `entities.metadata` for the key, resolve each `feature:{id}-{slug}` ref within the SAME workspace (`resolve_ref`), `INSERT OR IGNORE` blocks rows (same created_at policy); unresolvable → stderr note, metadata untouched.
4. `DROP TABLE entity_dependencies` + drop its 2 indices. Migration 6's CREATE (:872-887) is NOT touched (SC6 exemption (a)).

## D2 — dep_mgr + DB-method rewire (return shapes frozen)

The 5 DB methods (database.py:9101/9113/9122/9130/9198) re-target `entity_relations ... WHERE kind='blocks'`; **query_dependencies SELECTs `to_uuid AS entity_uuid, from_uuid AS blocked_by_uuid`** so every consumer (dependencies.py:89-123, dependency_freshness.py:24, task_promotion.py:70) sees the frozen dict shape; get_blockers/get_dependents keep uuid-list returns. check_dependency_cycle's recursive CTE (:9198) ports with column renames only; self-dependency rejection preserved. add_dependency inserts `(from_uuid=blocker, to_uuid=blocked, kind='blocks', created_at=now)`; the UNIQUE index makes repeats idempotent (INSERT OR IGNORE, matching current UNIQUE-pair semantics). The section-header comment database.py:9098 rewords to name entity_relations.

## D3 — cascade_unblock modification (spec FR124-4 a-d)

Name and all 5 call sites unchanged. New body contract:
1. `affected = get_dependents(completed_uuid)` (via blocks rows — NO edge removal; FR124-4(c) survive).
2. For each affected uuid: if entity.status == 'blocked' AND `_all_blockers_resolved(uuid)` (D4): one per-flip `BEGIN IMMEDIATE` transaction containing `update_entity(type_id, status='ready')` (the sanctioned status write path — already emits the migration-15 audit) + one `phase_events` row (event_type `cascade_ready`, from_value `blocked`, to_value `ready`, actor `system:cascade` — OQ-1 RESOLVED; migration-10 schema :1503).
3. Returns the flipped uuid list (shape preserved).

**Nesting unwrap (spec D-item):** `_run_cascade` (entity_engine.py:536-540) drops its outer `with self._db.transaction():` — cascade_unblock now owns per-flip transactions; `rollup_parent` runs AFTER in its OWN `db.transaction()` (its atomicity is unchanged — it was never coupled to the cascade's writes; order preserved: flips then rollup). database.py:7577's call keeps post-commit fail-open but the bare `except Exception: pass` becomes `except Exception as exc: print(f"cascade_unblock failed (recovered by doctor): {type(exc).__name__}", file=sys.stderr)` — type-name only (the #072 sanitization rule).

## D4 — `_all_blockers_resolved(uuid)` + per-kind completion predicate

One helper in dependencies.py: every blocker (via get_blockers) satisfies `_blocker_completed(entity)`, itself the SINGLE per-kind predicate (spec FR124-5): dispatch on entity kind via 123's `MACHINE_REGISTRY` — **5D kinds + task + feature + project: `status == 'completed'`; brainstorm/backlog (lifecycle kinds): `status IN ('promoted','archived','completed')`** (terminals from ENTITY_MACHINES graphs; `bug`: status-only, 'completed'). The three inline sites collapse onto it: database.py:7574 (trigger guard), dependency_freshness.py:25, checks.py:1872 (the REPLACED check re-expresses it in SQL — D6 pins the equivalent WHERE). Table above is the design's pinned contract; skeptic verifies against router.py:197-238 graphs.

## D5 — delete_entity + runtime foreign_keys (spec SC3-d)

1. The manual `DELETE FROM entity_dependencies` (:7868-7872) is REMOVED; TD-6 docstring (:7817) rewords to "dependency edges via entity_relations FK ON DELETE CASCADE" (token dropped — SC6).
2. **Runtime pragma ENSURE:** `EntityDatabase.__init__`/connect path gains `self._conn.execute("PRAGMA foreign_keys = ON")` immediately after connection setup (today only migrations toggle it :365/:458/:617/:991). One new connect-path line; migrations continue their own OFF/ON dance unaffected (per-connection scope).
3. **OQ-2 RESOLVED — unblock-on-delete hook = delete_entity:** capture `dependents = get_dependents(uuid)` BEFORE the delete (FK wipes edges at commit), then post-commit run the D3 flip-evaluation over `dependents` (same per-flip transactions, same fail-open-with-stderr posture as the :7577 site). SC3-d's edge-gone assertion exercises the FK; the flip assertion exercises this hook.

## D6 — Doctor surface

- blocked-entity lookup (checks.py:1146): SQL re-targets entity_relations; comment :1137 reworded (token dropped).
- stale-edge check (:1856-1885) REPLACED by **missed-cascade check**: SELECT blocked entities WHERE every blocker satisfies D4's predicate (SQL: NOT EXISTS an unresolved blocker) — fires ONLY then (spec SC5); fix_hint "Run cascade evaluation"; NEW fix action calling the D3 evaluation for that entity; registered in fixer.py replacing the retired pair.
- orphan-edge check (:1790-1816) + `_fix_remove_orphan_dependency` (fix_actions/__init__.py:250-266) + fixer.py:45 registry entry: DELETED together (FKs preclude orphans).
- Docstring/comment sweep (spec list): dependencies.py:19, dependency_freshness.py:1-4, database.py:9098, checks.py:1137, database.py:7817.

## D7 — SC7 auto-materialization (register/upsert)

`register_entity` (database.py:6531) and `upsert_entity` (:6851): after the entity row persists and metadata is parsed, for each `depends_on_features` ref that `resolve_ref` resolves in-workspace → `add_dependency(blocker_uuid, this_uuid)` (INSERT OR IGNORE semantics); unresolvable → one stderr warn, registration NOT blocked (matches the decomposing skill's existing fail-open registration posture; SKILL.md:231/:248 byte-unchanged). Inside the existing registration transaction where one exists; otherwise its own.

## D8 — Readiness consumers (spec H5 — collision CONFIRMED and closed)

`query_ready_tasks`'s lib (task_promotion.py:63) gates `status != "planned"` — post-124 a cascade-flipped task is `ready`, so it would be SKIPPED. Fix: gate becomes `status not in ("planned", "ready")` (never-blocked tasks stay 'planned' until promotion; cascade-flipped arrive as 'ready' — both are promotable). Its dependency read (:70) rides D2's frozen shape. `promote_task`'s own transition validation is untouched (123's router owns it).

## D9 — Test-file rewrite surface (spec/gate handoff)

8 files seed or assert `entity_dependencies` (gate-r2 grep): test_dependencies.py, test_fixer.py, test_search.py, test_checks.py, test_database.py, test_cross_workspace_matrix.py, test_register_upsert_split.py, test_atomic_promotion.py. All port fixtures to `entity_relations(kind='blocks')` via add_dependency EXCEPT migration tests, which keep old-shape seeding to exercise Migration 18 (SC6 carve-out). New tests: SC1 rebuild assertions, SC2 per-edge parity + created_at, SC3 a-e (incl. deletion + cross-workspace), SC5 predicate matrix, SC7 both paths, D8 both-status promotion.

## D10 — Change inventory (complete file list)

database.py (M18, 5 methods, :9098 comment, delete_entity, :7577 warn, connect pragma, :7817 docstring), dependencies.py (cascade body, D4 helpers, :19 docstring), entity_engine.py (:536-540 unwrap), dependency_freshness.py (:25 predicate, docstring), checks.py (:1146 rewire, :1856 replace, :1790 delete, :1137 comment), fix_actions/__init__.py (:250-266 delete, new missed-cascade action), fixer.py (:45 registry swap), task_promotion.py (:63 gate), + D9 test files. NO changes to: router.py, MCP server surfaces (both dependency tools keep their contracts), UI, skills.

## Open (design-resolved) items ledger

OQ-1 → `system:cascade`. OQ-2 → delete_entity hook (D5.3). Nesting → D3 unwrap. Pragma → D5.2. Per-kind table → D4. Test surface → D9. H5 → D8.
