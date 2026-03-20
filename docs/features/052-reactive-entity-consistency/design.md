# Design: pd as Fractal Organisational Management Hub

## Prior Art Research

Research completed during PRD phase (5 agents on org management, 3 on VSM/agent orchestration). Key findings incorporated into PRD:
- **VSM (Stafford Beer):** S1-S5 recursive structure validates fractal lifecycle. Algedonic signals = anomaly propagation.
- **OpenProject:** Closest software precedent — unified work package model with per-type workflows.
- **C2SIM (NATO):** Bidirectional intent/status data model validates entity lineage approach.
- **Magentic-One (Microsoft):** Dual-ledger task decomposition with stall detection validates the decompose→execute→feedback pattern.
- **AOP (ICLR 2025):** Decomposition principles — solvability, completeness, non-redundancy.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER / SECRETARY                         │
│  Natural language → mode detection → context enrichment         │
│  → dispatch to workflow engine or entity query                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌──────────────────────┐   ┌──────────────────────────┐
│   ENTITY ENGINE      │   │  WORKFLOW ENGINE          │
│   (data layer)       │   │  (lifecycle layer)        │
│                      │   │                           │
│  EntityDatabase      │   │  EntityWorkflowEngine     │
│  (pure data layer)   │   │  (lifecycle + cascade)    │
│  ├── entities        │   │  ├── get_template()       │
│  ├── workflow_phases │   │  ├── transition_phase()   │
│  ├── entity_tags     │   │  ├── complete_phase()     │
│  ├── entity_deps     │   │  │   └── cascade:         │
│  ├── entity_okr_aln  │   │  │       ├── unblock      │
│  └── _metadata       │   │  │       ├── rollup       │
│                      │   │  │       └── notify        │
│  No hooks — pure     │   │  └── backends:            │
│  data access only    │   │      ├── FeatureBackend   │
│                      │   │      │   (frozen existing │
│                      │   │      │    WorkflowState    │
│                      │   │      │    Engine)          │
│                      │   │      ├── FiveDBackend     │
│                      │   │      │   (L1/L2/L4)       │
│                      │   │      └── template_registry│
│                      │   │                           │
└──────────┬───────────┘   └──────────┬────────────────┘
           │                          │
           └────────┬─────────────────┘
                    ▼
         ┌─────────────────────┐
         │   MCP SERVER        │
         │   (API layer)       │
         │                     │
         │  Existing tools:    │
         │  ├── get_phase      │
         │  ├── transition_phase│
         │  ├── complete_phase │
         │  ├── register_entity│
         │  ├── export_entities│
         │  └── ...            │
         │                     │
         │  New tools:         │
         │  ├── promote_task   │
         │  ├── add_entity_tag │
         │  ├── query_ready_tasks│
         │  ├── add_dependency │
         │  ├── create_objective│
         │  ├── update_kr_score│
         │  └── get_notifications│
         └─────────────────────┘
```

### Key Architectural Decisions

**D1: Strategy Pattern for Workflow Engine** (AC-26)
The existing `WorkflowStateEngine` is frozen for L3 features — too coupled to refactor safely. A new `EntityWorkflowEngine` wraps it with a strategy pattern:

```python
class EntityWorkflowEngine:
    def __init__(self, db: EntityDatabase):
        self._db = db
        self._feature_engine = WorkflowStateEngine(db)  # frozen, delegated
        self._templates = WEIGHT_TEMPLATES

    def get_template(self, entity_type: str, weight: str) -> list[str]:
        return self._templates[(entity_type, weight)]

    def transition_phase(self, entity_uuid: str, target_phase: str) -> TransitionResult:
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity.entity_type == "feature":
            return self._feature_engine.transition_phase(entity.type_id, target_phase)
        return self._five_d_transition(entity, target_phase)

    def complete_phase(self, entity_uuid: str, phase: str) -> CompletionResult:
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity.entity_type == "feature":
            result = self._feature_engine.complete_phase(entity.type_id, phase)
        else:
            result = self._five_d_complete(entity, phase)
        # Post-completion triggers (all entity types)
        self._cascade_unblock(entity)
        self._rollup_parent(entity)
        return result
```

**Decision rationale:** Wrapping vs forking. Wrapping preserves L3 test compatibility. The feature backend delegates to the frozen engine; 5D backends implement minimal phase-sequence-only transitions (no artifact prerequisites initially).

**D2: Cascade Logic Owned by EntityWorkflowEngine, Not EntityDatabase** (AC-25, AC-29, AC-34)

EntityDatabase remains a **pure data layer** — no post-commit hooks, no cascade logic. All cascade operations (unblock, rollup, notification) are orchestrated by `EntityWorkflowEngine.complete_phase()` which wraps the data operations in a single `BEGIN IMMEDIATE` transaction:

```python
class EntityWorkflowEngine:
    def complete_phase(self, entity_uuid: str, phase: str, **kwargs) -> CompletionResult:
        with self._db.begin_immediate() as txn:
            # 1. Complete the phase (delegates to frozen engine for features)
            entity = self._db.get_entity_by_uuid(entity_uuid)
            if entity.entity_type == "feature":
                result = self._feature_engine.complete_phase(entity.type_id, phase)
            else:
                result = self._five_d_complete(entity, phase)

            # 2. Derive kanban (within same transaction)
            derive_and_set_kanban(self._db, entity.type_id)

            # 3. Cascade unblock (within same transaction)
            unblocked = self._dep_manager.cascade_unblock(entity.uuid)

            # 4. Rollup parent chain (within same transaction)
            rollup_parent(self._db, entity.uuid)

        # 5. Queue notifications AFTER commit (filesystem, not DB)
        self._notification_queue.push(completion_ripple(entity))
        for uuid in unblocked:
            self._notification_queue.push(unblock_notification(uuid))

        return CompletionResult(...)
```

**Decision rationale:** Single transaction for atomicity — if any cascade step fails, the entire completion rolls back. Notifications queue AFTER commit (filesystem writes can't be rolled back with SQLite). EntityDatabase stays pure — the frozen `WorkflowStateEngine`'s direct `update_entity(status='completed')` call still works but doesn't trigger cascades. Only `EntityWorkflowEngine.complete_phase()` triggers cascades — it is the **single entry point for phase completion** across all entity types.

**Implication for Phase 3:** `cascade_unblock` and `rollup_parent` are introduced in Phase 3 (not Phase 4) because task completion needs them (AC-25). Phase 4 extends them for project lifecycle.

**D3: UUID as Canonical FK, type_id as Display** (AC-7)
Migration approach for the ~320 existing `parent_type_id` references across ~21 files:

```
Phase 1: parent_uuid already exists but is underused
  → Make parent_uuid the canonical FK for new code paths
  → Retain parent_type_id as denormalised display field
  → New junction tables use uuid exclusively

Phase 2: Gradual migration of existing consumers
  → get_lineage() accepts both uuid and type_id, resolves internally
  → backfill/reconciliation reads parent_uuid first, falls back to parent_type_id
  → parent_type_id updated automatically when slug renames occur
```

**Decision rationale:** Big-bang migration of 266 references is risky. Gradual migration with dual-read (uuid primary, type_id fallback) is safer. The denormalised parent_type_id ensures backward compatibility during migration.

**D4: Central ID Generator** (AC-8)
```python
def generate_entity_id(db: EntityDatabase, entity_type: str, name: str) -> str:
    """Generate standardised {seq}-{slug} entity_id."""
    key = f"next_seq_{entity_type}"
    seq = db.get_metadata(key) or _scan_existing_max_seq(db, entity_type)
    seq = int(seq) + 1
    db.set_metadata(key, str(seq))
    slug = _slugify(name, max_length=30)
    return f"{seq:03d}-{slug}"
```

**Decision rationale:** Per-type counters stored in `_metadata` table (already exists). `_scan_existing_max_seq` bootstraps from existing entities on first use. Existing entities keep their current IDs — no forced migration.

---

## Components

### C1: Schema Migration Module

**Location:** `scripts/migrate_db.py` (existing migration infrastructure)

**New migration (migration 6):**
1. DROP entity_type CHECK constraint → table rebuild with no CHECK on entity_type
2. Expand workflow_phase CHECK to include 5D phases
3. Expand mode CHECK to include 'light'
4. Create `entity_tags` table
5. Create `entity_dependencies` table with UNIQUE(entity_uuid, blocked_by_uuid)
6. Create `entity_okr_alignment` table
7. Add `next_seq_{type}` entries to `_metadata` for existing entity types (bootstrapped from max existing ID)
8. Add `uuid` column to `workflow_phases` table; backfill from parent entity uuid; update FK references from `workflow_phases.type_id` to `workflow_phases.uuid` as canonical key

**Backup:** `entities.db.bak.{ISO_timestamp}` created before migration starts.
**Dry-run:** `--dry-run` flag simulates migration on in-memory copy, reports changes.

### C2: derive_kanban Module

**Location:** `plugins/pd/hooks/lib/workflow_engine/kanban.py` (new file)

```python
PHASE_TO_KANBAN = {
    "brainstorm": "backlog", "specify": "backlog",
    "design": "prioritised", "create-plan": "prioritised", "create-tasks": "prioritised",
    "implement": "wip", "finish": "documenting",
    "discover": "backlog", "define": "backlog",
    "deliver": "wip", "debrief": "documenting",
}

def derive_kanban(status: str, workflow_phase: str | None) -> str:
    if status in ("completed", "abandoned"):
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "planned":
        return "backlog"
    return PHASE_TO_KANBAN.get(workflow_phase, "backlog")
```

**Integration points:** Called from `update_workflow_phase()`, `update_entity(status=...)`, `complete_phase()`, `init_feature_state()`. Replaces both `STATUS_TO_KANBAN` and `FEATURE_PHASE_TO_KANBAN` mappings.

### C3: EntityWorkflowEngine

**Location:** `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` (new file)

**Responsibilities:**
- Template lookup: `WEIGHT_TEMPLATES[(entity_type, weight)]`
- Phase transition for non-feature entities (phase-sequence-only, no artifact prerequisites initially)
- Phase completion with post-commit triggers (cascade unblock, parent rollup, notification queue)
- L3 feature delegation to frozen `WorkflowStateEngine`

**Backends:**

| Backend | Entity Types | Phase Validation | Gate Model |
|---------|-------------|-----------------|------------|
| FeatureBackend | feature | Existing PHASE_SEQUENCE + HARD_PREREQUISITES + 43 guards | Frozen WorkflowStateEngine |
| FiveDBackend | initiative, objective, key_result, project, task | WEIGHT_TEMPLATES sequence-only | Phase-order validation, blocked_by check at Deliver |

### C4: Dependency Manager

**Location:** `plugins/pd/hooks/lib/entity_registry/dependencies.py` (new file)

```python
class DependencyManager:
    def __init__(self, db: EntityDatabase):
        self._db = db

    def add_dependency(self, entity_uuid: str, blocked_by_uuid: str) -> None:
        """Add dependency. Raises CycleError if cycle detected."""
        self._check_cycle(entity_uuid, blocked_by_uuid)
        self._db.execute(
            "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) VALUES (?, ?)",
            (entity_uuid, blocked_by_uuid)
        )

    def cascade_unblock(self, completed_uuid: str) -> list[str]:
        """Remove completed entity from all dependents' blocked_by. Returns unblocked entity uuids."""
        dependents = self._db.execute(
            "SELECT entity_uuid FROM entity_dependencies WHERE blocked_by_uuid = ?",
            (completed_uuid,)
        ).fetchall()
        self._db.execute(
            "DELETE FROM entity_dependencies WHERE blocked_by_uuid = ?",
            (completed_uuid,)
        )
        unblocked = []
        for (dep_uuid,) in dependents:
            remaining = self._db.execute(
                "SELECT COUNT(*) FROM entity_dependencies WHERE entity_uuid = ?",
                (dep_uuid,)
            ).fetchone()[0]
            if remaining == 0:
                entity = self._db.get_entity_by_uuid(dep_uuid)
                if entity.status == "blocked":
                    self._db.update_entity(entity.type_id, status="planned")
                    unblocked.append(dep_uuid)
        return unblocked

    def _check_cycle(self, entity_uuid: str, blocked_by_uuid: str) -> None:
        """Recursive CTE cycle detection. Depth limit 20."""
        result = self._db.execute("""
            WITH RECURSIVE dep_chain(uuid, depth) AS (
                SELECT blocked_by_uuid, 1 FROM entity_dependencies WHERE entity_uuid = ?
                UNION ALL
                SELECT d.blocked_by_uuid, dc.depth + 1
                FROM entity_dependencies d JOIN dep_chain dc ON d.entity_uuid = dc.uuid
                WHERE dc.depth < 20
            )
            SELECT 1 FROM dep_chain WHERE uuid = ?
        """, (blocked_by_uuid, entity_uuid)).fetchone()
        if result:
            raise CycleError(f"Dependency cycle detected")
```

### C5: Progress Rollup Engine

**Location:** `plugins/pd/hooks/lib/workflow_engine/rollup.py` (new file)

```python
PHASE_WEIGHTS_7 = {
    "brainstorm": 0.0, "specify": 0.1, "design": 0.3,
    "create-plan": 0.3, "create-tasks": 0.3, "implement": 0.7, "finish": 0.9,
}
PHASE_WEIGHTS_5D = {
    "discover": 0.0, "define": 0.1, "design": 0.3, "deliver": 0.7, "debrief": 0.9,
}

def compute_progress(entity: Entity, children: list[Entity]) -> float:
    """Compute parent progress from children phases/status."""
    if not children:
        return 0.0
    total = 0.0
    for child in children:
        if child.status == "completed":
            total += 1.0
        elif child.status == "abandoned":
            continue  # excluded from denominator
        else:
            weights = PHASE_WEIGHTS_7 if child.entity_type == "feature" else PHASE_WEIGHTS_5D
            total += weights.get(child.workflow_phase, 0.0)
    active_children = [c for c in children if c.status != "abandoned"]
    return total / len(active_children) if active_children else 0.0

def compute_okr_score(kr: Entity, children: list[Entity]) -> float:
    """Compute KR score based on metric_type."""
    metric_type = kr.metadata.get("metric_type", "milestone")
    if metric_type == "milestone":
        completed = sum(1 for c in children if c.status == "completed")
        return completed / len(children) if children else 0.0
    elif metric_type == "binary":
        if children:
            return 1.0 if all(c.status == "completed" for c in children) else 0.0
        return kr.metadata.get("score", 0.0)  # manual for childless binary
    elif metric_type in ("target", "baseline"):
        return kr.metadata.get("score", 0.0)  # manual only
    return 0.0

def rollup_parent(db: EntityDatabase, child_uuid: str) -> None:
    """Synchronously recompute parent's progress up the ancestor chain.

    Note: update_entity() with metadata kwarg performs a dict MERGE (not replace)
    — existing metadata keys are preserved, only provided keys are updated.
    Verified: database.py:908-914 shallow-merges metadata.
    """
    entity = db.get_entity_by_uuid(child_uuid)
    parent_uuid = entity.parent_uuid
    while parent_uuid:
        parent = db.get_entity_by_uuid(parent_uuid)
        children = db.get_children_by_uuid(parent_uuid)
        if parent.entity_type == "key_result":
            score = compute_okr_score(parent, children)
            db.update_entity(parent.type_id, metadata={"score": score})
        else:
            progress = compute_progress(parent, children)
            db.update_entity(parent.type_id, metadata={"progress": progress})
        parent_uuid = parent.parent_uuid
```

### C6: Notification Queue

**Location:** `plugins/pd/hooks/lib/workflow_engine/notifications.py` (new file)

```python
@dataclass
class Notification:
    type: str  # completion_ripple, threshold_crossed, anomaly_escalation, stale_work
    entity_type_id: str
    message: str
    timestamp: str
    project_root: str  # scoping: which project generated this notification

class NotificationQueue:
    """File-backed notification queue. Notifications surfaced at interaction boundaries."""

    def __init__(self, queue_path: str = "~/.claude/pd/notifications.jsonl"):
        self._path = Path(queue_path).expanduser()

    def push(self, notification: Notification) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(notification)) + "\n")

    def drain(self, project_root: str | None = None) -> list[Notification]:
        """Read pending notifications, optionally filtered by project. Clears drained entries."""
        if not self._path.exists():
            return []
        with open(self._path) as f:
            all_notifs = [Notification(**json.loads(line)) for line in f]
        if project_root:
            matched = [n for n in all_notifs if n.project_root == project_root]
            remaining = [n for n in all_notifs if n.project_root != project_root]
            if remaining:
                with open(self._path, "w") as f:
                    for n in remaining:
                        f.write(json.dumps(asdict(n)) + "\n")
            else:
                self._path.unlink()
            return matched
        self._path.unlink()
        return all_notifs
```

**Delivery channels:**
1. Session-start hook reads `drain()` and includes in reconciliation summary
2. Secretary appends relevant notifications when answering queries
3. `get_notifications` MCP tool for external dashboards

### C7: Secretary Extensions

**Location:** `plugins/pd/commands/secretary.md` (existing, extended)

Extensions to existing 7-step pipeline:

| Step | Extension | Description |
|------|-----------|-------------|
| TRIAGE | Entity registry query | Search for parent candidates, check duplicates |
| MATCH | Weight recommendation | Analyse scope/risk signals → suggest full/standard/light |
| RECOMMEND | Notification append | Include pending notifications in recommendations |

**Mode detection** added before DISCOVER step:
```
IF context = feature_branch → default CONTINUE
ELIF action_verbs in request → CREATE
ELIF question_words in request → QUERY
ELIF continuation_words in request → CONTINUE
ELSE → ask clarification
```

---

## Interface Design

### I1: EntityDatabase Extensions

```python
# Phase 1b (foundational — needed by EntityWorkflowEngine and ref resolution)
def get_entity_by_uuid(self, uuid: str) -> Entity | None
def resolve_ref(self, ref: str) -> str  # uuid or type_id → uuid
def search_by_type_id_prefix(self, prefix: str) -> list[Entity]
def begin_immediate(self) -> ContextManager  # wraps BEGIN IMMEDIATE / COMMIT / ROLLBACK

# Phase 3 (needed by rollup and task queries)
def get_children_by_uuid(self, parent_uuid: str) -> list[Entity]

# Phase 6 (needed by circle-aware queries)
def add_tag(self, entity_uuid: str, tag: str) -> None
def get_tags(self, entity_uuid: str) -> list[str]
def query_by_tag(self, tag: str) -> list[Entity]
```

### I2: New MCP Tools

```python
# Phase 1b
@mcp_tool
def add_dependency(entity_ref: str, blocked_by_ref: str) -> dict
@mcp_tool
def remove_dependency(entity_ref: str, blocked_by_ref: str) -> dict

# Phase 3
@mcp_tool
def promote_task(feature_ref: str, task_heading: str) -> dict
@mcp_tool
def query_ready_tasks(feature_ref: str | None = None) -> dict

# Phase 5
@mcp_tool
def create_objective(name: str, parent_ref: str | None = None, ...) -> dict
@mcp_tool
def create_key_result(name: str, objective_ref: str, metric_type: str, ...) -> dict
@mcp_tool
def update_kr_score(kr_ref: str, score: float) -> dict

# Phase 2
@mcp_tool
def get_notifications(project_root: str | None = None) -> dict

# Phase 6
@mcp_tool
def add_entity_tag(entity_ref: str, tag: str) -> dict
@mcp_tool
def get_entity_tags(entity_ref: str) -> dict
@mcp_tool
def add_okr_alignment(entity_ref: str, kr_ref: str) -> dict
@mcp_tool
def get_okr_alignments(entity_ref: str) -> dict
```

### I3: EntityWorkflowEngine Interface

```python
class TransitionResult:
    transitioned: bool
    results: list[GateResult]
    degraded: bool

class CompletionResult:
    completed: bool
    next_phase: str | None
    unblocked: list[str]  # entity uuids unblocked by this completion
    parent_progress: float | None  # updated parent progress

class EntityWorkflowEngine:
    def get_template(self, entity_type: str, weight: str) -> list[str]
    def transition_phase(self, entity_uuid: str, target_phase: str) -> TransitionResult
    def complete_phase(self, entity_uuid: str, phase: str, **kwargs) -> CompletionResult
    def get_state(self, entity_uuid: str) -> WorkflowState
```

### I4: Existing Tool Extension — ref Parameter

All existing MCP tools that accept `type_id` gain an alternative `ref` parameter:

```python
# Before (still works):
get_entity(type_id="feature:052-reactive-entity-consistency")

# After (also works):
get_entity(ref="feature:052")     # partial type_id, prefix match
get_entity(ref="01JNQX5K8R...")   # uuid direct
```

Resolution logic in shared helper:
```python
def resolve_ref(db: EntityDatabase, ref: str) -> str:
    """Resolve ref to uuid. Accepts uuid, full type_id, or partial type_id."""
    # Try as uuid first
    if db.get_entity_by_uuid(ref):
        return ref
    # Try as exact type_id
    entity = db.get_entity(type_id=ref)
    if entity:
        return entity.uuid
    # Try as prefix match
    matches = db.search_by_type_id_prefix(ref)
    if len(matches) == 1:
        return matches[0].uuid
    if len(matches) > 1:
        raise AmbiguousRefError(f"Multiple matches: {[m.type_id for m in matches]}")
    raise NotFoundError(f"No entity matching: {ref}")
```

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Engine generalisation | Strategy pattern (wrap, don't fork) | Preserves L3 test compat. 5D backends are minimal. |
| Post-commit triggers | Synchronous in EntityDatabase | CLI-scale, bounded fan-out (~5 ancestors max). |
| UUID adoption | Gradual dual-read migration | 266 parent_type_id references. Big-bang too risky. |
| CHECK constraints | Drop entity_type CHECK, keep phase/mode CHECK | Entity types change more often than phases. |
| Notification delivery | File-backed JSONL queue + poll-on-interaction | No daemon. Session-start + secretary queries. Scoped by project_root field. |
| Weight escalation storage | Mode column update + skipped_phases metadata | `workflow_phases.mode` updated; `metadata.skipped_phases` tracks phases absent from original template. |
| Cascade logic ownership | EntityWorkflowEngine, not EntityDatabase | DB stays pure data layer. Single transaction wraps completion + cascade + rollup. |
| OKR alignment table | Created Phase 1b, populated Phase 6 | `add_okr_alignment` / `get_okr_alignments` MCP tools deferred to Phase 6. Table exists but empty until then. |
| Cycle detection | Recursive CTE on junction table | Indexed, depth-limited (20). O(edges) per check. |
| OKR rollup | parent_uuid lineage, not entity_okr_alignment | Alignment table is for lateral cross-linkage only. |
| Task promotion | Heading-text fuzzy match, not index | Indices are fragile. Heading text is stable. |
| Progress storage | Eager (stored on child change) | Avoids recursive recompute on every query. |
| Kanban derivation | Single function, unified phase map | Replaces two competing maps. Covers 7-phase + 5D. |

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Schema migration corrupts production DB | Auto-backup + dry-run + test on copy first |
| EntityWorkflowEngine breaks L3 features | Strategy pattern delegates to frozen engine — L3 code path unchanged |
| Post-commit rollup creates unexpected slowdown | Bounded at 5 ancestor levels. Performance NFR: <500ms for 1000 entities |
| Notification queue file grows unbounded | drain() clears file. Stale detection limits queue to recent entries. |
| Dependency cycle detection too slow | CTE with depth limit 20. Indexed junction table. <100ms for 1000 entities. |
| UUID migration breaks existing MCP tool consumers | Dual-read (uuid primary, type_id fallback). All existing tools continue working. |

---

## Implementation Order

Each phase builds on the previous but is independently shippable:

```
Phase 1a: derive_kanban, field validation, frontmatter removal, maintenance mode,
          artifact warnings, reconciliation reporting
          → No schema changes. Ship immediately.

Phase 1b: Schema migration, junction tables, UUID canonical FK, central ID
          generator, WEIGHT_TEMPLATES, gate parameterisation
          → Foundation for everything else. Tested against DB copy.

Phase 2:  Secretary mode detection, entity registry queries in TRIAGE,
          notification queue, universal work creation flow
          → Secretary becomes organisational router.

Phase 3:  promote_task MCP tool, task entity registration, agent-executable
          task query, DependencyManager (C4), Progress Rollup Engine (C5),
          post-completion cascade in EntityWorkflowEngine, task completion
          → parent rollup
          → Tasks become first-class entities. Cascade infrastructure added.

Phase 4:  FiveDBackend for EntityWorkflowEngine, project 5D lifecycle,
          dependency enforcement at Deliver gate, orphan guard
          → Projects become living entities (cascade infra from Phase 3).

Phase 5:  Initiative/objective/key_result entities, OKR scoring logic,
          anti-pattern detection, OKR progress rollup
          → Strategic layer added.

Phase 6:  Anomaly propagation, catchball (parent intent on creation),
          entity tagging, circle-aware queries, cross-level progress view
          → Full topology intelligence.
```
