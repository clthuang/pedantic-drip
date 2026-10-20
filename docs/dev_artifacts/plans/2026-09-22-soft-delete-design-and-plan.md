# Soft Delete — Design and Plan

**Closes:** backlog `#081` — *v2 hard-delete vs append-only history: entity_deleted events are structurally impossible*
**Depends on:** `entities.is_legacy` (`d42689b1`), `entities.is_archived` (`bb0fb55e`)
**Status:** design agreed 2026-09-22; not yet implemented.

---

## 1. The problem, stated precisely

`delete_entity` cannot succeed for any entity in the registry, and never could.

`events.entity_uuid` is `NOT NULL REFERENCES entities(uuid)` with no `ON DELETE`
clause, and the `events_no_delete` trigger (BEFORE DELETE, immutable) fires even
on an FK-CASCADE-induced delete. Every one of the 579 live entities has at least
one `events` row, so the final `DELETE FROM entities` raises
`sqlite3.IntegrityError` unconditionally — verified in every statement order,
with and without `PRAGMA defer_foreign_keys`.

**Measured:** 0 of 579 entities lack an events row.

Two consequences, both live today:

- The **MCP `delete_entity` tool** (`entity_server.py:1141`) is user-callable and
  always fails.
- Deletion has nowhere to go, so it gets expressed as `status='archived'` — the
  same conflation just removed from archiving, one step further along.

**Not a problem:** partial-cascade corruption. `delete_entity` performs five
cascade deletes before the failing one, but the method is transactional and the
whole thing rolls back. Verified on a snapshot: `entity_tags`,
`workflow_phases`, `entities_fts` and the entity row are all intact afterwards.
So the method is inert dead code, not a corruption path, and **nothing is lost
by changing its semantics.**

## 2. Why hard delete is not the answer

The obvious repair — add `ON DELETE CASCADE` to `events.entity_uuid` — is wrong.
`events` is an append-only audit ledger, protected by three triggers
(`events_no_update`, `events_no_delete`, `events_no_replace`) under PRD NFR-4.
Cascading deletes into it would let deleting an entity silently destroy the
audit record of everything that ever happened to it. The immutability is the
feature; the inability to hard-delete is a consequence of it, not a bug in it.

**Decision: deletion is soft. The ledger wins.**

## 3. Design

### D1 — `entities.is_deleted`, the third stated flag

```sql
ALTER TABLE entities ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_entities_is_deleted ON entities(is_deleted);
```

Completes the set. Each flag states one orthogonal fact, none of them inferred:

| flag | states | independent of |
|---|---|---|
| `is_legacy` | identity predates the structural model | status, archived, deleted |
| `is_archived` | put away, still real | status, legacy, deleted |
| `is_deleted` | gone as far as the user is concerned | status, legacy, archived |

`status` returns to meaning workflow state and nothing else.

### D2 — `delete_entity` keeps its signature and starts working

Same name, same arguments, same MCP tool. It sets `is_deleted = 1` instead of
issuing a `DELETE`. Callers that expect "this entity is gone" get that; the row
and its history survive underneath.

No `hard_delete` escape hatch. There is no correct use for one — it cannot work
while the ledger exists, and offering it would only produce the same
`IntegrityError` behind a name that promises otherwise.

### D3 — the cascade becomes a no-op, deliberately

Today's five cascade deletes (`entity_tags`, `entity_okr_alignment`,
`workflow_phases`, `entities_fts`, and `entity_relations` via FK) are **not**
performed on a soft delete. Deleting a row's tags and workflow state would make
restore lossy, which defeats the point. The FTS row is the one judgement call:
leaving it means a deleted entity stays searchable, so **D3a: `search_entities`
filters `is_deleted`** rather than the FTS row being removed.

### D4 — children keep their parent

`parent_uuid` still points at a present row, so lineage survives a delete
intact. This is strictly better than hard delete, which would have orphaned or
cascaded them.

The existing guard stays: an entity with children **cannot** be deleted
(`ValueError`). Soft-deleting a parent out from under live children hides a
subtree without saying so.

### D5 — dependents are still re-evaluated

`delete_entity`'s feature-124 behaviour — a dependent whose last blocker has
just gone flips `blocked` → `ready`, fail-open with a stderr warning — is
preserved. A soft-deleted blocker is no longer blocking.

### D6 — reads filter by default, with one opt-out

`get_entity`, `get_entity_by_uuid`, `list_entities` and `search_entities` exclude
deleted rows. A new keyword `include_deleted: bool = False` is the only way to
see them, so restoring is possible without a raw SQL escape.

### D7 — restore is a first-class operation

`set_deleted(type_id, False)` — the mirror of `set_archived`, writing only the
flag. Delete → restore is lossless because D3 removed the cascade.

### D8 — the event is emitted, and now it can be

`entity_deleted` on the lifecycle axis. This is the actual content of #081: the
event was "structurally impossible" only because the entity row had to vanish
before it could be written. Soft delete removes that ordering problem.

## 4. Plan

Each task states its contract and a check that fails before it is done.

### T1 — migration

**Contract.** `is_deleted` exists on both generations, defaults 0, and no
existing row is marked deleted. **Interface.** `_v2_migration_6_soft_delete`,
registered as `V2_MIGRATIONS[6]` and `MIGRATIONS[24]`, replay-safe via
`PRAGMA table_info`. **Verify.** Fresh database has the column; live snapshot
migrates with `SELECT COUNT(*) FROM entities WHERE is_deleted = 1` → 0.
**Depends.** Nothing.

### T2 — `delete_entity` becomes soft

**Contract.** Succeeds for an entity that has events. Sets only `is_deleted`;
`status`, tags, workflow row and FTS row are unchanged. Still raises `ValueError`
for an unknown type_id and for an entity with children. Emits `entity_deleted`.
**Verify.** Red first: delete `feature:134-workflow-rebuild` on a snapshot — today
raises `IntegrityError`, after T2 succeeds with tags/workflow/status intact.
**Depends.** T1.

### T3 — `set_deleted` and the restore round trip

**Contract.** `set_deleted(type_id, bool)` writes only the flag.
`delete → restore` returns the entity to its exact prior state.
**Verify.** Snapshot a row's full column tuple, delete, restore, assert equality
excluding `updated_at`. **Depends.** T2.

### T4 — reads exclude deleted rows

**Contract.** The four read paths exclude deleted rows unless
`include_deleted=True`. **Verify.** For each: seed two entities, delete one,
assert it is absent by default and present with the flag. A single shared
assertion over all four, so none is missed. **Depends.** T2.

### T5 — sweep the conflation

**Contract.** Nothing uses `status='archived'` or absence-of-a-row to mean
deleted. **Verify.** `grep` for archival-as-deletion in commands and skills;
`/pd:doctor` clean; full battery green. **Depends.** T4.

## 5. Risks

- **D6 is the wide one.** Filtering four read paths changes every consumer's
  results. Mitigated by zero rows being deleted at migration time, so the
  behaviour change is inert until something is actually deleted.
- **A deleted parent with live children** is refused, not cascaded. If that
  proves annoying in practice the answer is an explicit recursive delete, not a
  silent one.
- **No hard delete means the file only grows.** Accepted: the ledger is the
  point, and 579 entities is not a size problem.
