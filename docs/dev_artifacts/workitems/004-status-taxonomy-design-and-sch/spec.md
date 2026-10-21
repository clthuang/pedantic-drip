# Specification: Status Taxonomy Design and Schema ADR

## Problem Statement

iflow currently uses a single `status` field on features (`planned`, `active`, `completed`, `abandoned`) and a separate `lastCompletedPhase` field to track workflow progress. There is no concept of kanban process state — where a work item sits in the human-agent collaboration process. The new architecture requires two orthogonal status dimensions (workflow phase and kanban column) coexisting on each entity, but the exact taxonomy, column values, valid transitions, and schema design need formal definition before any implementation.

## Success Criteria

- [ ] ADR document produced with clear decision rationale for dual-dimension status model
- [ ] Complete enumeration of all valid values for each status dimension (workflow_phase, kanban_column)
- [ ] Mapping table defining automatic kanban_column transitions triggered by workflow events
- [ ] SQL schema for `workflow_phases` table defined with all columns, types, constraints, and indexes
- [ ] Entity type participation rules documented (which entity types use which dimensions)
- [ ] Backward compatibility analysis: how existing `status` field and `.meta.json` state maps to the new model — all fields accounted for with explicit disposition
- [ ] Edge case rules for conflicting states with at least 5 concrete scenarios

## Scope

### In Scope

- Dual-dimension status model design: workflow_phase dimension and kanban_column dimension
- Complete value enumerations for both dimensions with definitions
- Automatic transition mapping: complete workflow event vocabulary mapped to kanban columns
- Manual override rules: when and how humans can override kanban columns
- `workflow_phases` table SQL schema (columns, types, constraints, indexes, foreign keys)
- Entity type participation matrix with explicit defaults for each entity type
- Complete backward compatibility mapping from ALL `.meta.json` fields to new schema (with disposition per field)
- State conflict resolution rules with 5+ concrete scenarios
- Schema migration content (DDL for the new table; version number assigned at implementation time)

### Out of Scope

- Python implementation of the state engine (feature 008)
- MCP tool API design (feature 009)
- Kanban UI rendering (feature 019)
- Entity UUID migration (feature 001) — this feature assumes text-based `type_id` as the FK; UUID migration is a separate concern
- Actual data migration scripts — this feature produces the schema DDL only
- Transition guard implementation (feature 007) — this feature defines the taxonomy that guards enforce

## Decisions (resolved from open questions)

### D-1: kanban_column defaults and nullability
**Decision:** `kanban_column` defaults to `backlog` for feature entities. For non-feature entity types (brainstorm, backlog), `kanban_column` is set explicitly (limited to `backlog` or `prioritised`). Project entities do not have rows in `workflow_phases`.
**Rationale:** Features always participate in kanban. Brainstorms and backlog items appear on the board but only in early columns. Projects are containers, not work items.

### D-2: Table cardinality — one row per feature
**Decision:** `workflow_phases` stores one row per entity (current state snapshot). Per-phase timestamps are NOT stored in this table. Phase history (per-phase started/completed/iterations/reviewerNotes) is deferred to feature 008 (WorkflowStateEngine) which will implement an audit/transition log.
**Rationale:** Simpler schema, faster queries for current state. The current `.meta.json` `phases` sub-object is complex (nested per-phase data with varying structures like `design.stages.*`). Reproducing that complexity in SQL would couple this schema to implementation details. The state engine (feature 008) owns phase history.

### D-3: backward_transition_reason as TEXT column
**Decision:** `backward_transition_reason` is a nullable TEXT column on the `workflow_phases` row. It records the most recent backward transition reason only. Full transition audit log is feature 008's responsibility.
**Rationale:** Simple, sufficient for the "why was this phase re-run?" question. Full history is a different concern.

## Acceptance Criteria

### AC-1: ADR Structure
- Given a completed ADR document
- When reviewed by an engineer
- Then it contains: context, decision drivers, considered options, decision outcome, and consequences sections

### AC-2: Workflow Phase Values
- Given the workflow phase dimension
- When all valid values are listed
- Then they include: `brainstorm`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish`
- And `workflow_phase` is a **nullable** TEXT column — NULL means "not started" (no sentinel value)
- And each value has a one-sentence definition
- Note: SQLite CHECK constraints with IN(...) pass when the value is NULL, so `CHECK(workflow_phase IN (...) OR workflow_phase IS NULL)` is the explicit constraint form

### AC-3: Kanban Column Values
- Given the kanban column dimension
- When all valid values are listed
- Then they include exactly: `backlog`, `prioritised`, `wip`, `agent_review`, `human_review`, `blocked`, `documenting`, `completed`
- And each value has a one-sentence definition and a "who moves cards here" designation
- These are the DB-stored values (lowercase, underscore-separated). Display labels may differ (e.g., "WIP", "Agent Review") — display formatting is a UI concern (feature 019)

### AC-4: Automatic Transition Mapping — Complete Event Vocabulary
- Given a mapping table of workflow events to kanban column changes
- Then the following events are defined with their target kanban columns:

| Event | Target kanban_column | Triggered by |
|-------|---------------------|--------------|
| phase_start | wip | Agent begins phase execution |
| reviewer_dispatch | agent_review | Agent spawns reviewer subagent |
| human_input_requested | human_review | AskUserQuestion invoked |
| phase_complete | wip (if next phase auto-starts) | Phase marked completed; does not apply to the `finish` phase (finish completion triggers `feature_completed` instead). All phase transitions auto-start the next phase in sequence (brainstorm→specify→design→create-plan→create-tasks→implement→finish) — kanban_column moves to `wip` on each auto-start. No manual pause points exist in the current workflow |
| phase_blocked | blocked | Prerequisite missing or error |
| phase_unblocked | wip | Blocker resolved |
| feature_cancelled | completed | Feature abandoned |
| feature_completed | completed | finish-feature completed |
| documentation_started | documenting | finish-feature doc phase begins |
| manual_override | (any valid column) | Human drags card in UI |

### AC-5: Entity Type Participation
- Given the entity type participation matrix:

| Entity Type | Has workflow_phases row? | workflow_phase values | kanban_column values |
|------------|------------------------|----------------------|---------------------|
| feature | Yes | All 7 phases + NULL | All 8 columns |
| brainstorm | Yes | NULL only (brainstorms don't have workflow phases) | backlog, prioritised only |
| backlog | Yes | NULL only | backlog, prioritised only |
| project | No | N/A | N/A |

- Non-participating types (project) have no row in `workflow_phases`
- Brainstorm and backlog entities have constrained kanban columns (only early-stage columns)
- Per-entity-type kanban column restrictions are enforced by the state engine (feature 008) at the application level, NOT by DDL constraints — SQLite CHECK constraints cannot reference other tables to determine entity_type. The DDL in AC-6 intentionally allows all 8 kanban_column values for all entity types; column-restriction enforcement is entirely delegated to feature 008

### AC-6: Schema DDL
- Given the `workflow_phases` table DDL
- When executed against the existing `entities.db`
- Then the table is created with these columns:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| type_id | TEXT | PRIMARY KEY, FK → entities(type_id) | Entity reference |
| workflow_phase | TEXT | NULLABLE, CHECK(IN valid phases OR NULL) | Current active phase |
| kanban_column | TEXT | NOT NULL, DEFAULT 'backlog', CHECK(IN valid columns) | Current process state |
| last_completed_phase | TEXT | NULLABLE, CHECK(IN valid phases OR NULL) | Most recently completed phase |
| mode | TEXT | NULLABLE | standard or full |
| backward_transition_reason | TEXT | NULLABLE | Reason for most recent backward transition |
| updated_at | TEXT | NOT NULL | ISO-8601 timestamp of last state change |

- Indexes: `idx_wp_kanban_column` on `kanban_column`, `idx_wp_workflow_phase` on `workflow_phase`
- Note: Per-phase timestamps (started, completed, iterations, reviewerNotes, skippedPhases) are NOT in this table — they are deferred to the transition log in feature 008 (Decision D-2)
- The FK references `entities(type_id)` per current schema v1. If feature 001 (UUID migration) changes the PK before this DDL is executed, the FK column and type must be updated accordingly. This ADR records the design intent; the implementing feature (005) will use the PK that exists at implementation time
- `updated_at` uses UTC in ISO-8601 format (e.g., `2026-03-01T12:00:00Z`) — avoids mixed-timezone inconsistency from .meta.json
- `skipped_phases` is intentionally absent from this table — it will be managed by feature 008 (WorkflowStateEngine) in its own schema migration as part of the transition log

### AC-7: Backward Compatibility Mapping — Complete Field Disposition

| .meta.json field | Disposition | Target |
|-----------------|-------------|--------|
| `id` | Stays in .meta.json | Not migrated — display identifier |
| `slug` | Stays in .meta.json | Not migrated — display identifier |
| `status` | Maps to kanban_column | See status mapping table below |
| `created` | Already in entities table | `entities.created_at` |
| `completed` | Maps to workflow_phases | Captured via kanban_column = `completed` + updated_at |
| `mode` | Maps to workflow_phases | `workflow_phases.mode` |
| `branch` | Stays in .meta.json | Not migrated — git concern, not workflow state |
| `project_id` | Already in entities table | Via `parent_type_id` (project:P001) |
| `module` | Already in entities metadata | `entities.metadata` JSON |
| `depends_on_features` | Already in entities metadata | `entities.metadata` JSON |
| `lastCompletedPhase` | Maps to workflow_phases | `workflow_phases.last_completed_phase` |
| `skippedPhases` | Deferred to feature 008 | Transition log responsibility |
| `phases.{name}.started` | Deferred to feature 008 | Per-phase timestamps in transition log |
| `phases.{name}.completed` | Deferred to feature 008 | Per-phase timestamps in transition log |
| `phases.{name}.iterations` | Deferred to feature 008 | Per-phase iteration count in transition log |
| `phases.{name}.reviewerNotes` | Deferred to feature 008 | Reviewer notes in transition log |
| `phases.{name}.taskReview.*` | Deferred to feature 008 | Task review sub-object (iterations, approved, concerns) in transition log |
| `phases.{name}.chainReview.*` | Deferred to feature 008 | Chain review sub-object (iterations, approved, concerns) in transition log |
| `phases.{name}.reviewIterations` | Deferred to feature 008 | Per-phase review iteration count in transition log |
| `phases.{name}.approved` | Deferred to feature 008 | Per-phase approval status in transition log |
| `phases.{name}.status` | Deferred to feature 008 | Phase-level status (e.g., finish phase) in transition log |
| `phases.design.stages.*` | Deferred to feature 008 | Design-specific sub-structure in transition log |
| `backlog_source` | Stays in .meta.json | Not migrated — provenance metadata linking feature to backlog item |
| `brainstorm_source` | Stays in .meta.json | Not workflow state — provenance metadata |
| `lastCompletedMilestone` | Stays in .meta.json | Project-level, not feature workflow |
| `milestones` | Stays in .meta.json | Project-level, not feature workflow |
| `features` | Stays in .meta.json | Project-level, not feature workflow |

**Status → kanban_column mapping:**

| Current status | kanban_column | Rationale |
|---------------|---------------|-----------|
| planned | backlog | Not yet started = backlog |
| active | wip | Active work (actual kanban column refined by workflow events) |
| completed | completed | Terminal state |
| abandoned | completed | Terminal state — inferred as abandoned when kanban_column=`completed` AND (workflow_phase IS NULL OR workflow_phase != `finish`) (see AC-8 scenario #6) |

Note: `active` → `wip` is the initial mapping. Once the state engine is running, the kanban column for active features is dynamically updated by workflow events (reviewer dispatch → `agent_review`, AskUserQuestion → `human_review`, etc.).

### AC-8: Conflict Resolution — Concrete Scenarios

The ADR must address these conflict scenarios:

| # | Scenario | workflow_phase | kanban_column | Valid? | Resolution | Enforcement |
|---|----------|---------------|---------------|--------|------------|-------------|
| 1 | Active work demoted to backlog | design | backlog | Valid | Human override — feature deprioritised mid-work | N/A (valid state) |
| 2 | Working on nothing | NULL | wip | Invalid | Constraint: if kanban_column is wip/agent_review/human_review, workflow_phase must not be NULL for feature entities | Application-level (feature 008 state engine) — requires entity_type lookup |
| 3 | Premature completion | implement | completed | Invalid | Constraint: kanban_column=completed requires workflow_phase=finish OR feature_cancelled event was triggered (see scenario #6 for the valid abandoned case) | Application-level (feature 008 state engine) — requires event context |
| 4 | Orphaned row — both NULL | NULL | (missing) | Invalid | kanban_column has NOT NULL + DEFAULT 'backlog', so this cannot occur | DDL-level (NOT NULL + DEFAULT constraint) |
| 5 | Agent review without reviewer | design | agent_review | Valid | Transitional — the column is set before reviewer dispatch as a signal | N/A (valid state) |
| 6 | Distinguishing abandoned from completed | implement | completed | Valid | Abandoned inference rule: kanban_column=`completed` AND (workflow_phase IS NULL OR workflow_phase != `finish`) means the feature was cancelled/abandoned rather than completed normally. The `feature_cancelled` event triggers this state. | Application-level (feature 008 state engine reads workflow_phase to determine disposition) |

Note: Scenarios #2, #3, and #6 require application-level enforcement because SQLite CHECK constraints cannot reference other tables (for entity_type) or event context. The state engine (feature 008) validates these rules during transitions.

## Feasibility Assessment

### Assessment Approach
1. **First Principles** — Status taxonomy is a design decision, not a technical constraint. Two-column approach is standard in project management tools.
2. **Codebase Evidence** — Entity registry already has a generic `status` TEXT column with no CHECK constraint. Adding a new table with typed columns is a straightforward SQLite migration. Existing CHECK constraint pattern at `database.py:15`.
3. **External Evidence** — Kanban methodology (Anderson, 2010) defines columns as process states independent of work type — directly supports the orthogonal model.

### Assessment
**Overall:** Confirmed
**Reasoning:** This is a design/documentation feature producing an ADR. The schema DDL is constrained to SQLite (already used by entity registry). The dual-dimension model is well-established in project management theory. No technical unknowns.
**Key Assumptions:**
- SQLite CHECK constraints support the required value enumerations — Status: Verified at `database.py:15` (existing CHECK on entity_type)
- Entity DB migration framework can handle additional migrations — Status: Verified at `database.py` migration system (version-gated, integer-based)
- `workflow_phases` table uses `type_id` as FK referencing `entities(type_id)` — Status: Verified compatible with current schema
**Open Risks:**
- Migration version numbering is sequential (integer-based, not branching). If multiple features produce migrations concurrently, they must be serialized at implementation time. The ADR documents migration content; the version number is assigned at implementation.
- If UUID migration (feature 001) changes the PK before this DDL is executed, the FK definition needs adjustment. Mitigated: DDL only; implementing feature adapts to current PK.

## Dependencies

- None (this is a foundational feature with no prerequisites)
- Note: Features 005, 006, 008, and 019 depend ON this feature's output
- Feature 008 (WorkflowStateEngine) is the enforcement mechanism for: (a) per-entity-type kanban column restrictions (AC-5), (b) conflict resolution scenarios #2, #3, and #6 (AC-8), (c) all deferred phase history fields from AC-7. If feature 008 scope changes, these rules require re-evaluation.

## Open Questions

None — all questions resolved in Decisions section above.
