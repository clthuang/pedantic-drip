# PRD: Entity UUID Primary Key Migration

## Source

Extracted from Project P001 (iflow Architectural Evolution) PRD and Roadmap.

*Source: Backlog #00024*

- Project PRD: `docs/projects/P001-iflow-arch-evolution/prd.md`
- Roadmap: `docs/projects/P001-iflow-arch-evolution/roadmap.md`

## Problem Statement

The entity registry uses `type_id` (format `"{entity_type}:{entity_id}"`) as its PRIMARY KEY. This text-based composite key couples identity to display semantics — if naming conventions change, the key changes. Five downstream features (002, 005, 012, 013, 018) need to reference entities by stable, immutable identifiers for foreign keys, file headers, search indexes, and UI URLs. Without a decoupled identity layer, every downstream feature must account for key instability.

### Evidence

- Entity DB schema: 4 types (backlog, brainstorm, project, feature), immutable type_id/entity_type triggers, recursive CTE for cycle detection, 1 migration — Location: `database.py:10-75`
- Entity DB has WAL-mode SQLite, migration framework, immutability triggers — all patterns to extend, not replace
- `type_id` is a composite of `entity_type:entity_id` — renaming either component changes the primary key
- 5 features blocked on stable identity: 002 (markdown headers), 005 (workflow phases table), 012 (full-text search), 013 (context export), 018 (UI server)
- Entity DB schema migration framework already exists with versioning (`_metadata.schema_version`) — adding migration 2 follows established pattern

## Goals

1. Make UUID v4 the canonical primary key for the `entities` table, decoupling identity from display
2. Retain `type_id` as a UNIQUE indexed column for human-readable lookups
3. Provide dual-read compatibility so all existing callers (MCP tools, backfill, CLI) continue working with either UUID or type_id
4. Migrate existing data with zero data loss via the existing schema migration framework
5. Maintain all existing immutability and safety invariants (type_id, entity_type, created_at triggers)

## User Stories

### Story 1: Agent References Entity by UUID

**As a** downstream feature implementer **I want** to reference entities by immutable UUID **So that** foreign keys, file headers, and indexes remain valid even if entity naming conventions change.

**Acceptance criteria:**
- `register_entity()` returns UUID v4 string
- `get_entity(uuid)` returns the entity
- `set_parent(uuid, parent_uuid)` works with UUID identifiers
- UUID is immutable after creation (trigger-enforced)

### Story 2: Backward-Compatible Lookup

**As an** existing MCP tool consumer **I want** to continue using `type_id` strings for entity lookups **So that** no existing workflows break during or after migration.

**Acceptance criteria:**
- `get_entity("feature:001-slug")` still works (type_id lookup)
- `set_parent("feature:child", "project:P001")` still works
- All 6 existing MCP tools accept either UUID or type_id transparently
- Backfill runs without code changes

### Story 3: Zero-Loss Data Migration

**As a** developer **I want** existing entities to receive stable UUIDs during migration **So that** post-migration references are immediately usable without re-registration.

**Acceptance criteria:**
- All existing entities get UUID v4 values during migration
- `parent_uuid` correctly references the parent entity's UUID
- Schema version updates from 1 to 2
- Migration is idempotent (running on migrated DB is no-op)
- Migration failure rolls back completely (no partial state)

## Functional Requirements

From Project PRD cross-cutting concerns and roadmap:

- **FR-UUID-1:** UUID v4 as canonical primary key; text-based `type_id` becomes display-only UNIQUE column
- **FR-UUID-2:** Dual-read compatibility — support both `type_id` and UUID lookups during and after migration
- **FR-UUID-3:** Schema versioning via lightweight `schema_version` metadata (not Alembic)
- **FR-UUID-4:** Entity DB owns the schema — no direct SQL from commands or skills
- **FR-UUID-5:** All existing MCP tool signatures preserved (register_entity, set_parent, get_entity, get_lineage, update_entity, export_lineage_markdown)
- **FR-UUID-6:** `parent_uuid` column as canonical parent foreign key alongside retained `parent_type_id`

## Non-Functional Requirements

- **NFR-UUID-1:** Zero data loss during migration
- **NFR-UUID-2:** Migration completes atomically — no partial state on failure
- **NFR-UUID-3:** State transitions (register, update, set_parent) complete in <100ms (current SQLite local performance maintained)
- **NFR-UUID-4:** All 184 existing tests pass after migration (with updates for changed return values)

## Constraints

From Project PRD:

- SQLite is the storage backend (existing infrastructure)
- Python is the implementation language (existing venv)
- Entity DB has immutable constraints on `type_id` and `entity_type` columns (trigger-enforced) — must not break
- `INSERT OR IGNORE` semantics use `type_id` UNIQUE constraint for duplicate detection
- SQLite does not support `ALTER TABLE ... ADD PRIMARY KEY` — must use table recreation
- UUID generation uses Python's `uuid.uuid4()` — no external dependencies

## Dependency Context

From Roadmap dependency graph:

```
F001 (this feature) → F002 (markdown entity file header schema)
F001 → F005 (workflow phases table with dual-dimension status)
F001 → F012 (full-text entity search MCP tool)
F001 → F013 (entity context export MCP tool)
F001 → F018 (unified iflow UI server with SSE)
```

Feature 001 is the **root node** in the P001 dependency graph. It has no prerequisites and is required by 5 downstream features. It is part of Milestone M0: Identity and Taxonomy Foundations.

## Scope Boundary

### In Scope

- Schema migration v1 → v2 (CREATE-COPY-DROP-RENAME pattern)
- UUID column as PRIMARY KEY, type_id as UNIQUE
- parent_uuid column as canonical parent FK
- Dual-read resolver (`_resolve_identifier`)
- API return value changes (UUID instead of type_id)
- Immutability triggers for UUID
- Self-parent prevention triggers
- MCP tool dual-read compatibility
- Server helper display adjustments
- Test updates for all changed behavior

### Out of Scope

- Removing `type_id` column (kept indefinitely for human-readable lookups)
- Removing `parent_type_id` column (kept alongside `parent_uuid`)
- Adding new MCP tools (search, export — handled by features 012, 013)
- Adding workflow phase tracking (handled by feature 005)
- Changing entity_type vocabulary (handled by feature 005)
- UI changes (handled by features 018-022)
- Performance optimization beyond maintaining current levels

## Risk Assessment

From Project PRD strategic analysis:

- **Risk 1:** Schema migration failure corrupts entity DB — **Mitigation:** Explicit transaction with rollback, idempotent migration, WAL mode
- **Risk 2:** Dual-read introduces ambiguity (UUID-like type_id strings) — **Mitigation:** UUID v4 regex with version nibble check (`4` in position 13, `[89ab]` in position 18)
- **Risk 3:** Downstream features assume specific return types — **Mitigation:** Spec documents exact before/after return types per method; all callers updated in this feature
- **Risk 4:** Backfill compatibility breaks silently — **Mitigation:** Backfill uses `register_entity()` signature (unchanged) and `set_parent()` with dual-read; explicit AC for backfill passing without code changes
