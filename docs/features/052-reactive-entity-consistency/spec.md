# Specification: pd as Fractal Organisational Management Hub

## Overview

Transform pd from a tactical feature development engine into a fractal organisational management hub that applies the same lifecycle engine at every organisational level (strategic, program, tactical, operational) with level-appropriate gate stringency, ceremony weight, and topology-aware coordination.

**Theoretical foundation:** Stafford Beer's Viable System Model (VSM) — recursive fractal structure where every viable system contains the same five subsystems at every level.

**Scope boundary:** This spec covers all 7 implementation phases (1a through 6). Each phase is independently shippable. Later phases are unlocked, not mandated.

---

## Phase 1a: Depth Fixes

### AC-1: Field Validation on Feature Creation

**Given** `init_feature_state()` is called
**When** `id`, `slug`, or `branch` is empty, null, or whitespace-only
**Then** `ValueError` is raised with message `"Feature {field} cannot be empty"`.

**Verification:** `init_feature_state(feature_id="", slug="test", branch="test")` raises `ValueError`.

### AC-2: Remove Frontmatter Health Check

**Given** `reconcile_status` is called
**When** computing the health report
**Then** frontmatter drift is excluded from the `healthy` boolean and drift entries.

**Verification:** `reconcile_status(summary_only=True)` returns `healthy: true` on a clean workspace with no workflow drift, regardless of frontmatter state.

### AC-3: Maintenance Mode for meta-json-guard

**Given** `PD_MAINTENANCE=1` environment variable is set
**When** a `.meta.json` write is attempted
**Then** meta-json-guard allows the write with "Maintenance mode active" log entry.

**Verification:** Set `PD_MAINTENANCE=1`, write to `.meta.json` via Edit tool — hook allows it. Any other value or unset means maintenance mode is inactive.

### AC-4: Kanban Derivation

**Given** any call to `update_workflow_phase()`, `update_entity(status=...)`, `complete_phase()`, or `transition_phase()`
**When** the mutation completes
**Then** `kanban_column` equals `derive_kanban(status, workflow_phase)` — never set independently.

```python
def derive_kanban(status: str, workflow_phase: str | None) -> str:
    if status in ("completed", "abandoned"):
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "planned":
        return "backlog"
    return FEATURE_PHASE_TO_KANBAN.get(workflow_phase, "backlog")
```

**Verification:** All existing kanban-setting code paths replaced with `derive_kanban()` calls. After any state mutation, `kanban_column == derive_kanban(status, workflow_phase)`.

### AC-5: Artifact Completeness Warning

**Given** `complete_phase(phase="finish")` is called
**When** status is set to completed
**Then** expected artifacts are checked per mode. Warnings logged for missing artifacts. Completion is NOT blocked.

| Mode | Expected (warn if missing) |
|------|---------------------------|
| standard | spec.md, tasks.md, retro.md |
| full | spec.md, design.md, plan.md, tasks.md, retro.md |

**Verification:** Complete a standard-mode feature missing `retro.md`. Assert completion succeeds with warning in return value.

### AC-6: Reconciliation Reporting

**Given** session-start reconciliation runs
**When** changes are made (features synced, kanban fixed)
**Then** a summary is surfaced: `"Reconciled: {n} features synced, {n} kanban fixed, {n} warnings"`.

**When** zero changes are made
**Then** silent — no output.

**Verification:** Force a kanban drift, run reconciliation. Assert summary output. Run again with no drift — assert no output.

---

## Phase 1b: Schema Foundation

### AC-7: Two-ID System — UUID as Source of Truth

**Given** any entity in the registry
**Then** `uuid` (UUIDv4) is the system identity used for ALL internal references: `parent_uuid`, junction tables, `workflow_phases` foreign key.

**`type_id`** remains as human-readable display identity: `{type}:{seq}-{slug}`. Mutable slug — renaming an entity's slug does not break any internal references.

**Verification:**
1. Create entity A. Create entity B with parent=A. Rename A's slug. Assert B's parent relationship is intact (via uuid, not type_id).
2. All MCP tools accept both uuid and type_id as input, resolve to uuid internally.

### AC-8: Standardised Human ID Format

**Given** a new entity is created (any type)
**Then** `entity_id` follows the format `{seq}-{slug}` where:
- `seq`: per-type sequential counter (from `_metadata` table key `next_seq_{entity_type}`)
- `slug`: max 30 chars, lowercase, hyphens, derived from name/description

**Existing entities** retain their current type_ids. No forced rename.

**Verification:** Create initiative → `initiative:001-enterprise-reliability`. Create feature → `feature:053-structured-logging` (continues from existing sequence).

### AC-9: Entity Type Expansion

**Given** the entity registry
**When** after schema migration
**Then** `VALID_ENTITY_TYPES` includes: `backlog`, `brainstorm`, `project`, `feature`, `initiative`, `objective`, `key_result`, `task`.

SQL CHECK constraint on `entity_type` is dropped in favour of Python-only validation (`_validate_entity_type`). Future type additions require only a Python change, no table rebuild.

**Verification:** `register_entity(entity_type="initiative", entity_id="001-test", name="test")` succeeds. `register_entity(entity_type="invalid_type", ...)` raises ValueError.

### AC-10: Workflow Phase Expansion

**Given** the `workflow_phases` table
**When** after migration
**Then** CHECK constraint allows the 5D phase names (`discover`, `define`, `design`, `deliver`, `debrief`) in addition to existing 7 feature phases.

**Verification:** `create_workflow_phase(type_id, workflow_phase="discover")` succeeds.

### AC-11: Mode Constraint Expansion

**Given** the `workflow_phases` table
**When** after migration
**Then** `mode` CHECK constraint includes `'standard'`, `'full'`, `'light'`.

**Verification:** `create_workflow_phase(type_id, mode="light")` succeeds. Existing `standard` and `full` rows unaffected.

### AC-12: Junction Tables

**Given** the entity registry database
**When** after migration
**Then** three junction tables exist with uuid-based foreign keys:

- `entity_tags` (entity_uuid TEXT, tag TEXT) — indexed on both columns
- `entity_dependencies` (entity_uuid TEXT, blocked_by_uuid TEXT) — indexed, unique pair constraint
- `entity_okr_alignment` (entity_uuid TEXT, key_result_uuid TEXT) — indexed

**Verification:** Insert into each table. Query by entity_uuid and by tag/blocked_by_uuid/key_result_uuid — both use index.

### AC-13: Dependency Cycle Detection

**Given** entity A with `blocked_by=[B]` and entity B with `blocked_by=[C]`
**When** attempting to add `blocked_by=[A]` to entity C
**Then** the operation is rejected with error "Dependency cycle detected: C → A → B → C".

**Implementation:** Recursive CTE walking the `entity_dependencies` graph from `blocked_by_uuid`. If the source `entity_uuid` is reachable, reject. Depth limit: 20.

**Verification:** Create A→B→C dependency chain. Assert adding C→A fails. Assert adding D→A succeeds (no cycle).

### AC-14: Workflow Templates Registry

**Given** the workflow engine
**Then** a `WEIGHT_TEMPLATES` registry maps `(entity_type, weight)` to phase sequences:

```python
WEIGHT_TEMPLATES = {
    ("initiative", "full"):     ["discover", "define", "design", "deliver", "debrief"],
    ("initiative", "standard"): ["discover", "define", "design", "deliver", "debrief"],
    ("objective", "standard"):  ["define", "design", "deliver", "debrief"],
    ("key_result", "standard"): ["define", "deliver", "debrief"],
    ("project", "full"):        ["discover", "define", "design", "deliver", "debrief"],
    ("project", "standard"):    ["discover", "define", "design", "deliver", "debrief"],
    ("project", "light"):       ["define", "design", "deliver", "debrief"],
    ("feature", "full"):        EXISTING_7_PHASE_SEQUENCE,
    ("feature", "standard"):    EXISTING_7_PHASE_SEQUENCE,
    ("feature", "light"):       ["specify", "implement", "finish"],
    ("task", "standard"):       ["define", "deliver", "debrief"],
    ("task", "light"):          ["deliver"],
}
```

**Verification:** Look up `("feature", "light")` → `["specify", "implement", "finish"]`. Look up `("task", "light")` → `["deliver"]`.

### AC-15: Gate Parameterisation for Light Weight

**Given** a light-weight feature with template `["specify", "implement", "finish"]`
**When** evaluating HARD_PREREQUISITES for `implement`
**Then** only artifacts from phases IN the active template are required. Since `design`, `create-plan`, `create-tasks` are not in the template, `design.md`, `plan.md`, `tasks.md` are NOT required. Only `spec.md` (from `specify`) is required.

**Verification:** Create light feature. Transition to `implement` with only `spec.md` present — succeeds. Without `spec.md` — fails.

### AC-16: Schema Migration Safety

**Given** the migration script
**Then:**
1. Automatically backs up DB file (`entities.db.bak.{timestamp}`) before any destructive operation
2. Can run against a copy first (`--dry-run` mode)
3. All 1100+ existing tests pass after migration
4. Existing entity data is preserved — no rows lost, no type_ids changed

**Verification:** Run migration on test DB copy. Assert row counts match. Assert all type_ids unchanged. Assert backup file exists.

---

## Phase 2: Secretary + Universal Work Creation

### AC-17: Secretary CREATE Mode

**Given** a user request with work creation intent (action verbs: need, want, build, add, create)
**When** secretary processes the request
**Then** secretary:
1. Detects entity type from scope (company-wide → L1, multi-feature → L2, single deliverable → L3, bounded fix → L4/light L3)
2. Searches entity registry for parent candidates (partial type_id match)
3. Checks for duplicates/overlaps
4. Proposes: type, weight, parent linkage, circle tags
5. On user confirmation, dispatches the appropriate create command with parent linkage

**Verification:** "We need better observability" → secretary proposes L2 project, finds parent KR if exists, suggests tags.

### AC-18: Secretary QUERY Mode

**Given** a user request with query intent (question words: how, what, status, progress)
**When** secretary processes the request
**Then** secretary queries entity engine and presents topology-aware view including: entity status, lifecycle phase, children progress, OKR scores (if applicable), blockers.

**Verification:** "How are we doing on reliability?" → secretary finds matching objective, computes score from children, surfaces blockers.

### AC-19: Secretary CONTINUE Mode

**Given** a user request with continuation intent (next, resume, continue, what's ready)
**When** secretary processes the request
**Then** secretary checks current context (branch, active feature, phase) and:
- If on feature branch: proposes continuing at current phase
- If not: lists ready work (unblocked features, ready tasks, untriaged backlog)

**Verification:** On feature branch → "Feature 052 is in specify phase. Continue?" Not on feature branch → lists available work.

### AC-20: Universal 4-Step Work Creation

**Given** any work creation request (from decomposition, ad-hoc, emergent, or lateral trigger)
**Then** the creation flow follows:
1. **Identify** — type, weight, circle(s)
2. **Link** — search for parent candidates, propose linkage
3. **Register** — entity created with type, tags, parent_uuid, status=planned, workflow template
4. **Activate** — status → active, enters first phase of template

**Verification:** Create a task via secretary → entity registered with parent_uuid, tags, template assigned, status=planned. Activate → enters first template phase.

### AC-21: Proactive Notifications

**Given** entity state changes that cross thresholds
**Then** notifications are queued and surfaced via:
1. Session-start summary (reconciliation)
2. Secretary query responses (appended when relevant)
3. MCP tool polling (for external dashboards)

Notification types: threshold crossed, completion ripple, anomaly escalation, stale work (no phase transition for >N days).

**Verification:** Complete a feature → notification queued: "Feature X completed. Project Y: 67%." Next secretary query includes the notification.

### AC-22: Backlog as Organisational Inbox

**Given** `/pd:add-to-backlog "description"`
**Then** backlog entity created with status=open.

**Given** secretary triage request
**Then** secretary can promote backlog item: identify type/weight/circle/parent → register as work item → remove from backlog (status=promoted).

**Verification:** Add to backlog → entity created. Triage via secretary → promoted to feature with parent linkage.

---

## Phase 3: L4 Operational — Tasks as Work Items

### AC-23: Task Entity Registration

**Given** `create-tasks` phase completes producing `tasks.md`
**Then** each task in tasks.md is optionally registered as an entity with:
- `entity_type="task"`, `parent_uuid` = feature's uuid
- `status="planned"`, template from weight
- Dependencies between tasks stored in `entity_dependencies`

Opt-in: simple tasks stay as markdown. Tasks are promoted to entities when the implementing agent or user explicitly promotes them.

**Verification:** Feature with 5 tasks in tasks.md. Promote 3 → 3 task entities created with parent=feature uuid. 2 remain markdown-only.

### AC-24: Agent-Executable Task Query

**Given** AI agent queries for ready tasks
**When** querying `entity_type="task" AND status="planned" AND blocked_by=[] AND parent.phase="implement"`
**Then** returns list of tasks ready for autonomous execution.

**Verification:** Create 3 tasks: A (no deps, ready), B (blocked by A), C (parent not in implement). Query → returns only A.

### AC-25: Task Completion Updates Parent

**Given** a task entity completes
**When** status set to "completed"
**Then:**
1. Siblings' `blocked_by` lists updated (cascade unblock via `entity_dependencies`)
2. Parent feature's progress recomputed synchronously
3. If all task entities complete, parent feature's implement phase can advance

**Verification:** Complete task A → task B unblocks (was blocked by A). Complete all tasks → parent feature progress = 100%.

---

## Phase 4: L2 Program — Living Projects

### AC-26: Project 5D Lifecycle

**Given** a project entity
**Then** it follows the 5D lifecycle: discover → define → design → deliver → debrief, managed by `EntityWorkflowEngine` (new class, strategy pattern) with project-specific gate configuration.

The existing `WorkflowStateEngine` remains frozen for L3 features.

**Verification:** Create project. Transition through discover → define → design → deliver → debrief. Each transition validated by EntityWorkflowEngine.

### AC-27: Project Progress Derivation

**Given** a project with child features
**Then** project progress is derived synchronously from children:
- Weighted: completed=1.0, implement=0.7, design=0.3, specify=0.1, planned=0.0
- Traffic light: GREEN (≥0.7), YELLOW (0.4-0.6), RED (<0.4)

**Verification:** Project with 3 features (1 completed, 1 in implement, 1 in design). Progress = (1.0+0.7+0.3)/3 = 0.67 → YELLOW.

### AC-28: Dependency Enforcement at Deliver

**Given** a feature with `blocked_by` entries in `entity_dependencies`
**When** attempting to transition to `implement` (Deliver)
**Then** transition is blocked if any `blocked_by` sibling is not completed.

**Verification:** Feature B blocked by Feature A. Attempt implement on B → rejected. Complete A → B's blocked_by cleared → implement succeeds.

### AC-29: Cascade Unblock on Completion

**Given** entity X completes (any type)
**When** entity X's uuid appears in `entity_dependencies.blocked_by_uuid` for entity Y
**Then:**
1. X's entry removed from Y's dependencies
2. If Y has no remaining dependencies AND Y's status="blocked", Y's status changes to "planned"

**Verification:** B blocked by A and C. A completes → B still blocked (by C). C completes → B unblocked, status → planned.

### AC-30: Orphan Guard on Abandonment

**Given** entity with active children
**When** attempting to abandon it
**Then** blocked with error "Cannot abandon entity with N active children. Use --cascade to abandon all descendants."

**When** `--cascade` flag provided
**Then** entity and all descendants abandoned in single transaction.

**Verification:** Project with 2 active features. Abandon without cascade → rejected. Abandon with cascade → project + 2 features all abandoned.

---

## Phase 5: L1 Strategic — Initiatives & OKRs

### AC-31: Initiative and Objective Entities

**Given** new entity types `initiative` and `objective`
**Then** they follow 5D lifecycle via `EntityWorkflowEngine`. Initiatives are optional strategic containers. Objectives represent what to achieve.

**Verification:** Create initiative. Create objective with parent=initiative. Both transition through 5D phases.

### AC-32: Key Result Entity with Scoring

**Given** a `key_result` entity
**Then** it has:
- `metric_type` in metadata: `target` | `baseline` | `milestone` | `binary`
- `score` in metadata: 0.0-1.0

**Automated scoring (child-completion rollup):**
- milestone: completed_children / total_children
- binary: 1.0 if all children complete, else 0.0
- baseline: 1.0 if measured (manual), else 0.0
- target: manual score update only (no external metrics integration)

**Un-scored KRs** default to 0.0. Secretary warns "Objective includes N un-scored KRs."

**Verification:** KR with 3 child features (2 complete, 1 active). milestone score = 2/3 = 0.67. Objective score = weighted avg of KR scores.

### AC-33: OKR Anti-Pattern Detection

**Given** KR text is provided at creation
**When** text contains activity words (launch, build, implement, complete, deploy, ship, release, create)
**Then** secretary warns: "This looks like an output, not an outcome. Consider reframing as a measurable result."

**Given** objective with >5 KRs
**Then** secretary warns: "Consider reducing KR count. Recommended max: 5."

**Verification:** Create KR "Launch mobile app" → warning. Create KR "Achieve 50K MAU on mobile" → no warning.

### AC-34: OKR Progress Rollup

**Given** a KR score changes (child completes or manual update)
**Then** parent objective score recomputed synchronously as weighted average of all KR scores.
**Then** colour coding applied: Green (0.7-1.0), Yellow (0.4-0.6), Red (0.0-0.3).

**Verification:** Objective with 3 KRs scoring 0.8, 0.5, 1.0. Objective score = 0.77 → Green.

---

## Phase 6: Cross-Topology Intelligence

### AC-35: Anomaly Propagation

**Given** a Debrief phase identifies a systemic issue (flagged in retro findings)
**When** the entity has a parent
**Then** the anomaly is recorded in parent entity's metadata: `{anomalies: [{description, source_type_id, timestamp}]}`.

**Verification:** Feature retro flags "auth middleware fundamentally broken." Parent project metadata includes the anomaly. Secretary surfaces it on next parent query.

### AC-36: Circle-Aware Queries

**Given** entities tagged with circles via `entity_tags`
**When** querying with tag filter (e.g., `tag="security"`)
**Then** results include all entities tagged with that circle, across all types and levels.

**Verification:** Tag 3 entities (initiative, project, feature) with "security". Query by tag → all 3 returned.

### AC-37: Cross-Level Progress View

**Given** an initiative with children spanning L1→L2→L3→L4
**When** querying the initiative's progress
**Then** recursive rollup computes: initiative progress from objectives, objective scores from KRs, KR scores from projects/features, project progress from features, feature progress from tasks.

**Verification:** Create full hierarchy: initiative → objective → KR → project → 2 features → 4 tasks. Complete all tasks → features complete → project complete → KR score = 1.0 → objective score updates → initiative progress reflects all completions.

---

## Non-Functional Requirements

### NFR-1: Backward Compatibility
- All existing 1100+ tests pass after every migration phase
- L3 tactical workflow behaviour unchanged: same phase names, same gates, same artifacts
- A user who ignores L1/L2/L4 sees zero change in their L3 workflow

### NFR-2: Cold-Start / Bootstrapping
- With zero entities, `/pd:create-feature` works identically to current behaviour
- No setup wizard or configuration required
- Intelligence improves as entities accumulate — circles emerge from tags, not setup

### NFR-3: Performance
- Rollup recomputes within 500ms for graphs up to 1000 entities
- Cycle detection completes within 100ms for dependency graphs up to 1000 entities

### NFR-4: Migration Safety
- DB backed up automatically before destructive operations (`entities.db.bak.{timestamp}`)
- Migration supports `--dry-run` mode
- Rollback = restore backup file

### NFR-5: Existing Entity Preservation
- Existing entities retain their current type_ids (no forced rename)
- New entities use standardised format
- `parent_type_id` retained as denormalised display field alongside canonical `parent_uuid`

---

## Out of Scope

- External metrics integration for target-metric KR scoring (manual only)
- Real-time notifications (no daemon — poll-on-interaction only)
- Kanban UI (view, retrofitted later as dashboard)
- Web-based L1/L2 planning interface (existing UI server extended separately)
- Workspace scoping (`workspace_id` column deferred to separate feature)
- Wardley Mapping integration
- Multi-user collaboration / access control

---

## Dependencies

### Phase 1a
- `engine.py` — `derive_kanban()` function
- `feature_lifecycle.py` — field validation
- `reconciliation.py` — remove frontmatter check, add reporting
- `meta-json-guard.sh` — maintenance mode check

### Phase 1b
- `database.py` — schema migration (DROP CHECK constraints, add junction tables, uuid-based FKs)
- `constants.py` — `WEIGHT_TEMPLATES` registry
- `transition_gate/` — gate parameterisation by active template

### Phase 2
- `commands/secretary.md` — extend TRIAGE/MATCH/RECOMMEND steps
- `workflow_state_server.py` — notification queue MCP tools

### Phase 3
- `commands/create-tasks.md` or `skills/breaking-down-tasks/` — task entity promotion
- New MCP tools: `query_ready_tasks`, `promote_task`

### Phase 4
- New `EntityWorkflowEngine` class (strategy pattern with L2/L3/L4 backends)
- `workflow_state_server.py` — project lifecycle MCP tools

### Phase 5
- New MCP tools: `create_objective`, `create_key_result`, `update_kr_score`
- OKR scoring logic in entity engine
- Anti-pattern detection in secretary

### Phase 6
- Anomaly metadata schema
- Recursive rollup queries (CTE across entity hierarchy)
- Tag-based query APIs
