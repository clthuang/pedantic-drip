# Design: Status Taxonomy Design and Schema ADR

## Prior Art Research

### Research Conducted
| Question | Source | Finding |
|----------|--------|---------|
| Entity registry migration pattern? | database.py:10-75 | Yes — integer-versioned MIGRATIONS dict, `executescript()` for DDL, `_metadata` table tracks schema_version |
| CHECK constraint patterns? | database.py:15, semantic_memory/database.py:34-40 | Yes — `CHECK(col IN (...))` pattern used for entity_type, category, source, confidence |
| FK pattern? | database.py:19 | Yes — `TEXT REFERENCES entities(type_id)`, `PRAGMA foreign_keys = ON` at connection init |
| Immutability triggers? | database.py:32-63 | Yes — `BEFORE UPDATE ... RAISE(ABORT)` pattern for type_id, entity_type, created_at |
| Dual-dimension status models? | WebSearch (Jira, Linear, UML) | Yes — Jira uses separate issue_status + workflow_step; Linear uses triage + workflow status; UML orthogonal regions formalize independent state dimensions |
| SQLite state machine enforcement? | WebSearch | BEFORE UPDATE triggers with RAISE(ABORT) for cross-table validation; CHECK constraints for row-local enum enforcement |
| ADR template standards? | WebSearch (MADR, Joel Parker Henderson) | MADR is the most adopted format: context, decision drivers, options, outcome, consequences |

### Existing Solutions Evaluated
| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| Entity registry migration framework | database.py:72-75, 541-561 | Adopted — next migration is version 2; follows existing `MIGRATIONS` dict pattern |
| CHECK constraint pattern | database.py:15 | Adopted — `CHECK(col IN (...))` for enum enforcement on workflow_phase and kanban_column |
| Immutability trigger pattern | database.py:32-63 | Adopted — `BEFORE UPDATE OF type_id` trigger for workflow_phases.type_id |
| Jira dual-column pattern | Atlassian docs | Adopted conceptually — independent status + workflow step; but Jira's app-level sync is a known desync hazard. We mitigate by making workflow_phase the source of truth and kanban_column the derived/overridable view |
| Transitions allowlist table | exceptionnotfound.net | Rejected — overkill for current scope. Transition validation is feature 008's responsibility. ADR defines the valid values; enforcement is application-level |
| Normalized status reference table | dev.to | Rejected — adds join overhead for no benefit. Our value sets are small (7 phases, 8 columns) and stable. CHECK constraints are simpler and faster |
| Event-sourcing state machine | Felix Geisendörfer | Rejected — full audit trail is feature 008's concern. This feature defines the snapshot table only |

### Novel Work Justified
The dual-dimension model (workflow_phase + kanban_column) is a well-established pattern (UML orthogonal regions, Jira's implementation). The novel aspect is fitting it into the existing entity registry's SQLite schema with minimal disruption — a new `workflow_phases` table joined via FK rather than altering the `entities` table. This preserves backward compatibility while enabling the kanban board.

## Architecture Overview

This feature produces an **ADR document** containing schema DDL — it is a design artifact, not a runtime component. No Python code is delivered; implementation is feature 005's responsibility. The architecture describes what the ADR defines and how it integrates with the existing entity registry.

```
┌─────────────────────────────────────────────────────────────┐
│                     entities.db                              │
│                                                              │
│  ┌──────────────┐         ┌─────────────────────────────┐   │
│  │   entities    │ 1──────1 │     workflow_phases          │   │
│  │              │  type_id │                              │   │
│  │ type_id (PK) │◄────────│ type_id (PK, FK)             │   │
│  │ entity_type  │         │ workflow_phase (nullable)     │   │
│  │ status       │         │ kanban_column (NOT NULL)      │   │
│  │ ...          │         │ last_completed_phase          │   │
│  └──────────────┘         │ mode                          │   │
│                           │ backward_transition_reason    │   │
│                           │ updated_at                    │   │
│                           └─────────────────────────────┘   │
│                                                              │
│  ┌──────────────┐                                           │
│  │  _metadata   │  schema_version: 2                        │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

**Key design principles:**
- **Separate table, not ALTER TABLE** — avoids modifying the `entities` table; preserves existing API surface
- **1:1 relationship** — one `workflow_phases` row per participating entity (features, brainstorms, backlog items); no row for projects
- **Current state snapshot** — no history; phase transition audit is feature 008's concern
- **ADR-only deliverable** — this feature produces the ADR document containing the DDL content; Python implementation is feature 005's responsibility
- **workflow_phase is source of truth** — kanban_column is the derived/overridable view; workflow_phase determines actual progress. This primacy is an application-level invariant enforced by the state engine (feature 008), not expressible in DDL

## Components

### Component 1: ADR Document
- Purpose: Formal record of the dual-dimension status model design decisions
- Inputs: Spec.md acceptance criteria, research findings
- Outputs: `adr-004-status-taxonomy.md` following MADR structure (context, decision drivers, options, outcome, consequences)
- Location: `docs/dev_artifacts/workitems/004-status-taxonomy-design-and-sch/adr-004-status-taxonomy.md`

### Component 2: Migration DDL
- Purpose: SQL schema for the `workflow_phases` table, to be added as migration version 2 in `database.py`
- Inputs: AC-6 schema definition from spec
- Outputs: DDL content embedded in ADR document (the Python migration function wrapping this DDL is implemented by feature 005)
- Location: Content defined in design; implemented by feature 005
- **Deliverable boundary:** Feature 004 produces the DDL content as part of the ADR document. The Python migration function code is implemented by feature 005. Feature 004 delivers documentation only — no Python code.

### Component 3: Workflow Phase Enumeration
- Purpose: Authoritative list of valid workflow phase values with definitions
- Inputs: AC-2 from spec
- Outputs: Enumerated values in ADR with one-sentence definitions

| Phase | Definition |
|-------|-----------|
| `brainstorm` | Exploring problem space and generating a PRD |
| `specify` | Writing precise requirements and acceptance criteria |
| `design` | Creating technical architecture and interface contracts |
| `create-plan` | Breaking design into ordered implementation steps |
| `create-tasks` | Decomposing plan into individual actionable tasks |
| `implement` | Writing code, tests, and executing tasks |
| `finish` | Final review, documentation, merge, and retrospective |

### Component 4: Kanban Column Enumeration
- Purpose: Authoritative list of valid kanban column values with definitions and ownership
- Inputs: AC-3 from spec
- Outputs: Enumerated values in ADR

| Column | Definition | Who moves cards here |
|--------|-----------|---------------------|
| `backlog` | Work item identified but not yet prioritised for action | System (default) or Human |
| `prioritised` | Selected for upcoming work, awaiting start | Human |
| `wip` | Active work in progress by agent or human | Agent (on phase_start) |
| `agent_review` | Agent has dispatched a reviewer subagent | Agent (on reviewer_dispatch) |
| `human_review` | Awaiting human input or decision | Agent (on human_input_requested) |
| `blocked` | Cannot proceed due to missing prerequisite or error | Agent (on phase_blocked) |
| `documenting` | In documentation/wrap-up phase | Agent (on documentation_started) |
| `completed` | Work finished (completed normally or cancelled) | Agent (on feature_completed or feature_cancelled) |

### Component 5: Event-to-Column Transition Map
- Purpose: Defines which workflow events trigger kanban_column changes
- Inputs: AC-4 from spec
- Outputs: Complete mapping table in ADR (10 events as defined in spec)

### Component 6: Backward Compatibility Map
- Purpose: Documents disposition of every .meta.json field
- Inputs: AC-7 from spec (25+ fields with explicit disposition)
- Outputs: Complete mapping table in ADR with status-to-kanban conversion rules

## Interfaces

### Interface 1: Migration Function
```
Input:  conn: sqlite3.Connection (with PRAGMA foreign_keys = ON)
Output: None (side effect: workflow_phases table created)
Errors: sqlite3.OperationalError if table already exists (mitigated by IF NOT EXISTS)
```

**DDL content:**
```sql
CREATE TABLE IF NOT EXISTS workflow_phases (
    -- FK uses implicit ON DELETE NO ACTION (SQLite default). Deleting an entity
    -- while its workflow_phases row exists will fail at statement end, which is
    -- the desired behavior — workflow state must be cleaned up before entity deletion.
    type_id                    TEXT PRIMARY KEY REFERENCES entities(type_id),
    workflow_phase             TEXT CHECK(workflow_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','create-tasks',
                                   'implement','finish'
                               ) OR workflow_phase IS NULL),
    kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                               CHECK(kanban_column IN (
                                   'backlog','prioritised','wip',
                                   'agent_review','human_review',
                                   'blocked','documenting','completed'
                               )),
    last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','create-tasks',
                                   'implement','finish'
                               ) OR last_completed_phase IS NULL),
    mode                       TEXT CHECK(mode IN ('standard', 'full')
                                   OR mode IS NULL),
    backward_transition_reason TEXT,
    updated_at                 TEXT NOT NULL
);

-- Immutability trigger for type_id (FK, should not change)
CREATE TRIGGER IF NOT EXISTS enforce_immutable_wp_type_id
BEFORE UPDATE OF type_id ON workflow_phases
BEGIN
    SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
END;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_wp_kanban_column ON workflow_phases(kanban_column);
CREATE INDEX IF NOT EXISTS idx_wp_workflow_phase ON workflow_phases(workflow_phase);
```

### Interface 2: ADR Document Structure
```
Input:  Design decisions from spec and research
Output: Markdown document following MADR format
Errors: N/A (static document)
```

**ADR sections:**
1. Title and status (accepted)
2. Context and problem statement
3. Decision drivers (spec requirements, backward compat, simplicity)
4. Considered options (single-dimension vs dual-dimension vs hierarchical)
5. Decision outcome (dual-dimension with snapshot table)
6. Consequences (positive: clean separation; negative: app-level enforcement needed for cross-table rules)
7. Appendices: Phase definitions, Column definitions, Event map, Conflict scenarios, Backward compat map

## Technical Decisions

### TD-1: Separate table vs. ALTER TABLE entities
- **Choice:** New `workflow_phases` table with FK to `entities(type_id)`
- **Alternatives Considered:**
  1. Add `workflow_phase` and `kanban_column` columns to `entities` — Rejected: couples workflow state to entity identity; violates Single Responsibility; would affect all entity operations
  2. JSON blob in `entities.metadata` — Rejected: no CHECK constraints possible; no indexing; no type safety
- **Trade-offs:** Pros: Clean separation, independent schema evolution, preserves existing API | Cons: Requires JOIN for combined queries
- **Rationale:** The workflow state is a concern independent of entity identity. Separate table allows feature 008 to extend the schema without touching entities.
- **Engineering Principle:** Single Responsibility, KISS
- **Evidence:** Codebase: database.py entities table has 10 columns already; adding more increases coupling. Jira uses separate tables for status and workflow step.

### TD-2: CHECK constraints for enum enforcement
- **Choice:** `CHECK(col IN (...))` for both workflow_phase and kanban_column
- **Alternatives Considered:**
  1. Foreign key to reference table — Rejected: adds complexity for small, stable enum sets (7 phases, 8 columns)
  2. Application-only validation — Rejected: allows invalid data from direct SQL access
- **Trade-offs:** Pros: Database-level guarantee, no extra tables | Cons: Requires migration to add new enum values
- **Rationale:** Value sets are small, well-defined, and unlikely to change frequently. CHECK constraints are the simplest valid approach.
- **Engineering Principle:** KISS, Fail Fast
- **Evidence:** Codebase: database.py:15 uses same pattern for entity_type; semantic_memory uses it for category, source, confidence

### TD-3: One row per entity (current state snapshot)
- **Choice:** Single row stores current workflow_phase and kanban_column
- **Alternatives Considered:**
  1. One row per phase per entity (historical) — Rejected: couples schema to phase history; complex queries for current state; feature 008's concern
  2. Event-sourced log — Rejected: overkill for current needs; SQLite not optimized for aggregate-on-read patterns
- **Trade-offs:** Pros: Simple queries, fast reads, clear PK | Cons: No built-in history (deferred to feature 008)
- **Rationale:** Current state is the primary query pattern (kanban board, status dashboard). History is a secondary concern handled by the transition log.
- **Engineering Principle:** YAGNI (for history in this table), KISS
- **Evidence:** Spec Decision D-2; Linear stores current status as a single field, not a log

### TD-4: Immutability trigger for type_id
- **Choice:** `BEFORE UPDATE OF type_id` trigger with `RAISE(ABORT)`
- **Alternatives Considered:**
  1. No trigger (rely on application code) — Rejected: inconsistent with existing pattern; allows accidental PK mutation
- **Trade-offs:** Pros: Consistent with entity table pattern | Cons: One more trigger in the schema
- **Rationale:** Follows established codebase convention. type_id is the PK and FK — mutation would orphan the relationship.
- **Engineering Principle:** Consistency, Fail Fast
- **Evidence:** Codebase: database.py:32-36 uses identical pattern for entities.type_id

### TD-5: Application-level enforcement for cross-table constraints
- **Choice:** Per-entity-type kanban restrictions and conflict scenario validation enforced by feature 008's state engine, not DDL
- **Alternatives Considered:**
  1. BEFORE INSERT/UPDATE triggers that query entities table — Considered but rejected: adds coupling between tables; triggers with subqueries in SQLite have performance implications; the state engine (feature 008) already needs this logic for transition validation
- **Trade-offs:** Pros: Simpler DDL, no cross-table triggers | Cons: Invalid data possible via direct SQL INSERT (mitigated: only the state engine writes to this table)
- **Rationale:** SQLite CHECK constraints are row-local — they cannot reference other tables. Triggers could work but add complexity better placed in the application layer where transition rules live.
- **Engineering Principle:** Single Responsibility (DDL defines structure; application defines behavior)
- **Evidence:** Spec AC-5 and AC-8 explicitly delegate enforcement to feature 008

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Migration version conflict with concurrent features | Schema version 2 claimed by multiple features | ADR defines content only; version number assigned at implementation time (feature 005). Sequential migration numbering is documented in spec. |
| UUID migration (feature 001) changes PK before this DDL runs | FK type mismatch | ADR documents intent with text `type_id`; implementing feature adapts to PK type at execution time. Explicit note in spec. |
| Direct SQL access bypasses app-level constraints | Invalid state combinations (e.g., brainstorm with kanban_column='wip') | Only the state engine (feature 008) writes to workflow_phases. Direct DB access is a developer tool, not a production path. |
| Abandoned inference rule depends on convention | Future phases added could break `workflow_phase != 'finish'` rule | Rule is documented in ADR and spec AC-8 scenario #6. Any phase addition requires updating the inference rule. |
| Feature 008 scope changes | Application-level constraints become unenforceable | Dependency explicitly documented in spec. If 008 changes, constraints require re-evaluation. |

## Dependencies

- **Entity registry database** (`database.py`) — migration framework, existing schema
- **Feature 005** — implements the migration defined here
- **Feature 008** — enforces application-level constraints defined here
- **Spec.md** — acceptance criteria that this design must satisfy
