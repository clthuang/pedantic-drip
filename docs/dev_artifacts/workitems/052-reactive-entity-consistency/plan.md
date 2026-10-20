# Plan: pd as Fractal Organisational Management Hub

## Implementation Order

7 phases. Dependencies flow forward — later phases build on earlier ones.

**Shippability:** Phase 1a delivers immediate bugfixes. Phase 1b is foundation work (schema, ref resolution, templates) — not independently valuable to users but required for Phases 2-6. Phases 2+ each deliver user-visible capability.

**TDD discipline:** Every step follows: (1) define interface/types, (2) write failing tests against the interface, (3) implement to make tests pass. Steps below describe the deliverable, not the execution order — TDD ordering is implicit.

**Complexity labels:** [S]imple (1-2 files, <1hr), [M]edium (3-5 files, 1-4hrs), [C]omplex (5+ files or architectural change, 4+hrs), [XC] Extra Complex (multi-day, highest-risk item in phase — focus of integration testing).

```
Phase 1a ──→ Phase 1b ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6
(bugfixes)   (schema)     (secretary)  (tasks)     (projects)   (OKRs)      (topology)
```

---

## Phase 1a: Depth Fixes (AC-1 through AC-6)

**No schema changes. Zero migration risk. Ship immediately.**

### Step 1a.1: derive_kanban() function [S]
- **File:** New `plugins/pd/hooks/lib/workflow_engine/kanban.py`
- **Work:** Create `PHASE_TO_KANBAN` mapping (unified 7-phase + 5D), `derive_kanban(status, workflow_phase)` function
- **Test:** Unit tests: every (status, phase) combination returns expected kanban column
- **ACs:** AC-4
- **Dependencies:** None

### Step 1a.2: Replace all kanban-setting code paths [M]
- **Files:** `feature_lifecycle.py` (STATUS_TO_KANBAN), `workflow_state_server.py` (FEATURE_PHASE_TO_KANBAN usages), `engine.py` (hydration kanban backfill), `entity_registry/backfill.py` (STATUS_TO_KANBAN at line 35, 20+ refs)
- **Work:** Replace all direct kanban_column sets with `derive_kanban()` calls. Remove `STATUS_TO_KANBAN` from both `feature_lifecycle.py` and `backfill.py`. Remove `FEATURE_PHASE_TO_KANBAN`. Audit all files referencing these constants (grep shows ~36 refs across production and test files). Update `VALID_MODES` in `backfill.py` to include `'light'`. Update test files: `test_backfill.py`, `test_engine.py`, `test_constants.py`, `test_reconciliation.py`, `test_workflow_state_server.py`.
- **Test:** ALL existing kanban-related tests pass (not just "existing tests" — verified by running full test suite). New integration test: complete_phase → verify kanban_column matches derive_kanban output. Backfill with status=active and no workflow_phase row → verify kanban derived from .meta.json-inferred phase, not just status.
- **ACs:** AC-4
- **Dependencies:** 1a.1

### Step 1a.3: Field validation in init_feature_state [S]
- **File:** `feature_lifecycle.py`
- **Work:** Add validation loop for `feature_id`, `slug`, `branch` — reject empty/null/whitespace with ValueError
- **Test:** Unit tests: empty string, None, whitespace-only for each field → ValueError
- **ACs:** AC-1
- **Dependencies:** None

### Step 1a.4: Remove frontmatter health check [S]
- **File:** `workflow_state_server.py` (`_process_reconcile_status`), `reconciliation.py` (frontmatter scan logic)
- **Work:** Exclude frontmatter drift from `reconcile_status` health boolean. Frontmatter scan still runs but doesn't affect `healthy` flag.
- **Test:** `reconcile_status(summary_only=True)` returns `healthy: true` with frontmatter drift present
- **ACs:** AC-2
- **Dependencies:** None

### Step 1a.5: Maintenance mode for meta-json-guard [S]
- **File:** `plugins/pd/hooks/meta-json-guard.sh`
- **Work:** Add early check: `if [[ "${PD_MAINTENANCE:-}" == "1" ]]; then output_json "allow" "Maintenance mode active"; exit 0; fi`
- **Test:** Hook integration test with PD_MAINTENANCE=1 → allows write. Without → blocks as before.
- **ACs:** AC-3
- **Dependencies:** None

### Step 1a.6: Artifact completeness warning [S]
- **File:** `workflow_state_server.py` (`_process_complete_phase`)
- **Work:** On `phase="finish"`, check expected artifacts per mode. Phase 1a only handles `standard` and `full` modes (the only modes that exist pre-1b). `light` mode artifact expectations are added in a post-1b follow-up step. Mode read from `workflow_phases.mode` column (already exists).
- **Test:** Complete standard feature missing retro.md → succeeds with warning. Complete with all artifacts → no warning.
- **ACs:** AC-5
- **Dependencies:** None

### Step 1a.7: Reconciliation reporting [M]
- **File:** `reconciliation.py`, session-start hook
- **Work:** `apply_workflow_reconciliation()` returns summary dict with counts. Session-start hook surfaces: "Reconciled: {n} features synced, {n} kanban fixed, {n} warnings". Silent when zero changes.
- **Test:** Force kanban drift → run reconciliation → summary output. No drift → no output.
- **ACs:** AC-6
- **Dependencies:** 1a.2 (kanban derivation)

---

## Phase 1b: Schema Foundation (AC-7 through AC-16)

**Destructive migrations. Test on DB copy first. Backup before applying.**

### Step 1b.1: Schema migration — combined table rebuilds [XC]
- **File:** `scripts/migrate_db.py`, `database.py`
- **Rollback strategy:** (1) Backup verified by opening + querying backup DB before any destructive operation, (2) all steps within single SQLite transaction with `PRAGMA foreign_keys=OFF`, (3) if any step fails, transaction rolls back and backup is the recovery path. Explicit `--verify-backup` check before proceeding.
- **DDL ordering (B3 fix — explicit FK-safe sequence):**
  1. `PRAGMA foreign_keys=OFF`
  2. `BEGIN IMMEDIATE`
  3. Rebuild `entities` table: CREATE `entities_new` (drop entity_type CHECK, keep all columns), INSERT from `entities`, DROP `entities`, ALTER TABLE RENAME `entities_new` TO `entities`, recreate indexes
  4. Rebuild `workflow_phases` table: CREATE `workflow_phases_new` (expand workflow_phase CHECK to include 5D phases, expand mode CHECK to include 'light', add `uuid TEXT` column), INSERT with uuid backfill via `SELECT e.uuid FROM entities e WHERE e.type_id = workflow_phases.type_id`, DROP `workflow_phases`, ALTER TABLE RENAME `workflow_phases_new` TO `workflow_phases`, recreate indexes. **Note:** `uuid` is an additional indexed column, NOT a PRIMARY KEY change — `type_id` remains PRIMARY KEY for backward compatibility with the frozen engine.
  5. Rebuild `entities_fts` (virtual table must be rebuilt after base table rename)
  6. CREATE `entity_tags` table (entity_uuid, tag) with indexes
  7. CREATE `entity_dependencies` table (entity_uuid, blocked_by_uuid) with unique constraint + indexes
  8. CREATE `entity_okr_alignment` table (entity_uuid, key_result_uuid) with indexes
  9. INSERT `next_seq_{type}` entries into `_metadata` (bootstrap from max existing IDs)
  10. `PRAGMA foreign_key_check` — verify zero FK violations
  11. Data integrity check A: `SELECT type_id FROM entities WHERE parent_type_id IS NOT NULL AND parent_uuid IS NULL` — backfill any orphaned parent_uuid
  12. Data integrity check B: `SELECT wp.type_id FROM workflow_phases wp LEFT JOIN entities e ON wp.type_id = e.type_id WHERE e.type_id IS NULL` — report orphaned workflow_phases rows. `SELECT type_id FROM workflow_phases WHERE uuid IS NULL` — report/fix NULL uuids after backfill.
  13. `COMMIT`
  14. `PRAGMA foreign_keys=ON`
- **Work:** Single migration (migration 6) following the DDL sequence above.
- **Test:** Migration on test DB copy. Row counts match. All type_ids preserved. Backup file exists. `PRAGMA foreign_key_check` returns zero violations. Zero orphaned workflow_phases rows. Zero rows with NULL uuid in workflow_phases. Zero rows with parent_type_id set but parent_uuid NULL. FTS5 search returns correct results for entities after migration. All 1100+ existing tests pass.
- **ACs:** AC-9, AC-10, AC-11, AC-12, AC-16
- **Dependencies:** None (but must be first step in 1b)

### Step 1b.2: Update VALID_ENTITY_TYPES [S]
- **File:** `database.py`
- **Work:** Expand tuple to include `initiative`, `objective`, `key_result`, `task`. Update `_validate_entity_type`.
- **Test:** register_entity with each new type → succeeds. Invalid type → ValueError.
- **ACs:** AC-9
- **Dependencies:** 1b.1

### Step 1b.3: EntityDatabase new methods [M]
- **File:** `database.py`
- **Work:** Add: `get_entity_by_uuid()`, `resolve_ref()`, `search_by_type_id_prefix()`, `begin_immediate()` context manager
- **Test:** Unit tests for each method. resolve_ref with uuid, full type_id, partial type_id, ambiguous, not found.
- **ACs:** AC-7 (partial)
- **Dependencies:** 1b.1

### Step 1b.4: Central ID generator [S]
- **File:** New utility in `database.py` or separate `id_generator.py`
- **Work:** `generate_entity_id(db, entity_type, name)` → `{seq}-{slug}`. Per-type counter from `_metadata` table. Bootstrap `_scan_existing_max_seq` for existing types.
- **Test:** Generate IDs for new types → sequential. Generate for existing type → continues from max. Slug rules (max 30, lowercase, hyphens).
- **ACs:** AC-8
- **Dependencies:** 1b.1

### Step 1b.5: MCP tool ref parameter [M]
- **File:** `workflow_state_server.py`, `mcp/entity_server.py`
- **Work:** Audit all `@mcp_tool` decorators in both files for `type_id` parameters (verify count via grep). Add `ref` parameter to each. Resolution: uuid → direct, full type_id → lookup, partial type_id → prefix search. Partial match on mutations → error with candidates.
- **Test:** get_entity(ref="feature:052") → resolves. get_entity(ref="feature:05") with 3 matches → error listing all. update_entity(ref="feature:05") → error (ambiguous, mutation).
- **ACs:** AC-7
- **Dependencies:** 1b.3

### Step 1b.6: Dependency cycle detection [M]
- **File:** New `plugins/pd/hooks/lib/entity_registry/dependencies.py`
- **Work:** `DependencyManager` class with `add_dependency()`, `_check_cycle()` (recursive CTE, depth 20), `cascade_unblock()`. MCP tools: `add_dependency`, `remove_dependency`.
- **Test:** A→B→C chain, attempt C→A → CycleError. D→A → succeeds. Performance: 1000 entities, <100ms.
- **ACs:** AC-13
- **Dependencies:** 1b.1, 1b.3

### Step 1b.7: WEIGHT_TEMPLATES registry [S]
- **File:** New in `constants.py` or `plugins/pd/hooks/lib/workflow_engine/templates.py`
- **Work:** `WEIGHT_TEMPLATES` dict mapping `(entity_type, weight)` → phase sequence. Lookup function `get_template(entity_type, weight)`.
- **Test:** Lookup each defined (type, weight) pair → correct sequence. Unknown pair → KeyError or default.
- **ACs:** AC-14
- **Dependencies:** None

### Step 1b.7a: Update backfill.py for uuid-primary parent resolution [M]
- **File:** `entity_registry/backfill.py`
- **Work:** Change parent linkage reads to prefer `parent_uuid`, fall back to `parent_type_id`. Dual-read logic per design D3.
- **Test:** Backfill on entity with `parent_uuid` set → uses uuid. Backfill on legacy entity with only `parent_type_id` → resolves via type_id fallback.
- **ACs:** AC-7 (partial), NFR-6
- **Dependencies:** 1b.1, 1b.3

### Step 1b.8: Gate parameterisation for light weight [M]
- **File:** `transition_gate/gate.py`, `transition_gate/constants.py`
- **B4 fix — frozen engine has no entity context:** The frozen engine's `_evaluate_gates` calls `check_hard_prerequisites(target_phase, existing_artifacts)` with no entity/mode context. Two-layer approach:
  1. Add optional `active_phases: list[str] | None` parameter to `check_hard_prerequisites()`. When provided, filter `HARD_PREREQUISITES` to only include entries whose phase key is in `active_phases`. When `None` (default), behave exactly as today — full prerequisite check. This is backward-compatible: all existing callers pass no `active_phases` argument.
  2. In `WorkflowStateEngine._evaluate_gates`, pass `active_phases=None` (unchanged behavior for L3 features via frozen engine).
  3. `EntityWorkflowEngine` resolves the entity's template via `get_template(entity_type, mode)` → phase list, then calls `check_hard_prerequisites(target_phase, existing_artifacts, active_phases=template_phases)` directly, BEFORE delegating to the frozen engine for features (or instead of it for 5D entities).
- **Work:** Modify `check_hard_prerequisites` signature. EntityWorkflowEngine's `transition_phase` checks template-filtered prerequisites as its first gate.
- **Test:** **Unit tests only** — EntityWorkflowEngine (the caller) does not exist until Step 3.3. Direct call with `active_phases=["specify","implement"]` + target "implement" → only spec.md required. Direct call with `active_phases=None` → spec.md + tasks.md (unchanged). Standard feature via frozen engine → unchanged (passes `None`).
- **B6 note:** Light-weight features are NOT end-to-end functional until Phase 3 when EntityWorkflowEngine wires the `active_phases` call. Step 3.3 must include an integration test: create light feature → transition to implement → verify only spec.md required.
- **ACs:** AC-15
- **Dependencies:** 1b.7

### Step 1b.9a: Entity tagging CRUD [M]
- **File:** `database.py` (add_tag, get_tags, query_by_tag), MCP tools (add_entity_tag, get_entity_tags)
- **Work:** Tag operations on `entity_tags` junction table (created in 1b.1). Tags: lowercase, hyphens, max 50 chars. Query by tag returns all matching entities across types.
- **Why here (not Phase 6):** Secretary (Phase 2) needs tagging for circle-aware routing. Phases 3-5 benefit from tagging entities at creation. Deferring to Phase 6 makes earlier phases less useful.
- **Test:** Tag 3 entities with "security" → query by "security" → all 3 returned.
- **ACs:** AC-35b, AC-36
- **Dependencies:** 1b.1

### Step 1b.10: Light-mode artifact completeness [S]
- **File:** `workflow_state_server.py` (`_process_complete_phase`)
- **Work:** Extend Step 1a.6's artifact check to handle `light` mode. Light features on finish check only `spec.md`. Light tasks have no artifact expectations.
- **Test:** Complete light feature with spec.md → no warning. Without spec.md → warning. Light task → no artifact check.
- **ACs:** AC-5 (light mode)
- **Dependencies:** 1b.1 (mode='light' exists), 1a.6

---

## Phase 2: Secretary + Universal Work Creation (AC-17 through AC-22a)

**Secretary testing strategy:** Deterministic logic (mode detection heuristic, entity search, weight recommendation) is extracted into testable Python functions that the secretary prompt invokes via MCP tools. Tests verify the functions, not the prompt. The prompt is a thin routing layer over tested code.

### Step 2.0: Secretary intelligence module [M]
- **File:** New `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py`
- **Work:** Extract testable Python functions for secretary logic:
  - `detect_mode(request_text: str, context: dict) -> str` — returns "CREATE", "CONTINUE", or "QUERY"
  - `find_parent_candidates(db: EntityDatabase, entity_type: str, name: str) -> list[dict]` — FTS5 search for parent matching
  - `check_duplicates(db: EntityDatabase, name: str) -> list[dict]` — detect potential duplicate entities
  - `recommend_weight(scope_signals: list[str]) -> str` — returns "light", "standard", or "full"
  - `detect_scope_expansion(current_mode: str, signals: list[str]) -> str | None` — returns recommended upgrade or None
- **Test:** Unit tests for each function with explicit input/output scenarios from AC-17, AC-18, AC-22a.
- **ACs:** AC-17, AC-18, AC-22a (foundations)
- **Dependencies:** 1b.3

### Step 2.1: Secretary mode detection [M]
- **File:** `commands/secretary.md` (prompt), `secretary_intelligence.py` (logic via MCP calls)
- **Work:** Add mode detection before DISCOVER step. Context check (feature branch → CONTINUE), keyword classification (action verbs → CREATE, questions → QUERY, continuation → CONTINUE), ambiguity → clarification.
- **Test:** Specific input/output scenarios from AC-17 verification.
- **ACs:** AC-17 (partial), AC-18 (partial), AC-19
- **Dependencies:** None

### Step 2.2: Secretary entity registry queries [M]
- **File:** `commands/secretary.md`
- **Work:** Extend TRIAGE step: search entity registry for parent candidates (FTS5 on name/entity_id), check duplicates, propose linkage. Extend MATCH step: weight recommendation from scope signals.
- **Test:** CREATE with existing parent → parent proposed. CREATE with empty registry → standalone. QUERY matching → results shown.
- **ACs:** AC-17, AC-18
- **Dependencies:** 1b.3, 1b.5

### Step 2.3: Notification queue [S]
- **File:** New `plugins/pd/hooks/lib/workflow_engine/notifications.py`
- **Work:** `Notification` dataclass (with project_root field), `NotificationQueue` class (file-backed JSONL, project-scoped drain). MCP tool: `get_notifications`. **Concurrency:** Use `fcntl.flock()` around push and drain operations to prevent TOCTOU races between concurrent Claude sessions. Acceptable fallback: document that concurrent sessions may lose notifications (CLI tool, rare scenario).
- **Test:** Push notification → drain with matching project_root → returned. Drain with different project_root → empty. Drain clears matched entries.
- **ACs:** AC-21
- **Dependencies:** None

### Step 2.4: Universal work creation flow [M]
- **File:** `commands/secretary.md`
- **Work:** 4-step flow (identify → link → register → activate) integrated into secretary CREATE mode. Backlog triage via secretary.
- **Test:** Create task via secretary → entity registered with parent, tags, template. Promote backlog item → feature created.
- **ACs:** AC-20, AC-22
- **Dependencies:** 2.1, 2.2

### Step 2.5: Weight escalation [M]
- **File:** `commands/secretary.md`
- **Work:** Secretary detects scope expansion signals, recommends weight upgrade. Upgrade = update `workflow_phases.mode`, write `skipped_phases` to metadata. Template expansion preserves completed phases.
- **Test:** Light feature in implement → user describes expansion → secretary suggests upgrade → mode updated, skipped phases recorded.
- **ACs:** AC-22a
- **Dependencies:** 1b.7, 1b.8

---

## Phase 3: L4 Tasks as Work Items (AC-23 through AC-25)

### Step 3.1: promote_task MCP tool [M]
- **File:** New MCP tool in `workflow_state_server.py`
- **Work:** `promote_task(feature_ref, task_heading)` — fuzzy-match heading in tasks.md, create task entity with parent=feature uuid, status=planned, template from weight. Parse dependencies from tasks.md ordering → `entity_dependencies`.
- **Test:** Promote by heading → entity created. Ambiguous heading → candidates returned. Already promoted → error.
- **ACs:** AC-23
- **Dependencies:** 1b.3, 1b.6

### Step 3.2: DependencyManager + Rollup integration [M]
- **File:** `dependencies.py` (from 1b.6), new `rollup.py`
- **Work:** `rollup_parent()` function — synchronous ancestor chain recomputation. Progress rollup (PHASE_WEIGHTS_7, PHASE_WEIGHTS_5D). `get_children_by_uuid()` method on EntityDatabase.
- **Test:** Complete child → parent progress updates. Complete all children → parent progress = 100%. Abandoned children excluded.
- **ACs:** AC-25 (partial)
- **Dependencies:** 1b.3, 1b.6

### Step 3.3: EntityWorkflowEngine (minimal, feature + task backends) [XC]
- **File:** New `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
- **B1 fix — frozen engine auto-commits internally:** The frozen `WorkflowStateEngine.complete_phase()` calls `db.update_workflow_phase()` and `db.update_entity()`, which both call `self._conn.commit()`. Wrapping in an outer `BEGIN IMMEDIATE` is impossible without modifying `EntityDatabase`'s commit behavior. **Chosen approach: two-phase commit with idempotent cascade.**
  1. **Phase A (completion):** Delegate to frozen engine (auto-commits). Feature completion is now durable.
  2. **Phase B (cascade):** In a separate `BEGIN IMMEDIATE` transaction, run: cascade_unblock → rollup_parent → notification push. If cascade fails, completion still stands — cascade is idempotent and retryable.
  3. **Failure mode:** If process crashes between Phase A and Phase B, next session's reconciliation detects the missing cascade (child completed but parent progress stale) and re-runs it. Add `_pending_cascades` check to `apply_workflow_reconciliation()`.
  4. **UUID resolution:** EntityWorkflowEngine resolves `entity_uuid` → `type_id` before delegating to the frozen engine (which uses `type_id`). Return type wraps `FeatureWorkflowState` in `CompletionResult` (adds cascade outcomes: unblocked entities, updated parent progress).
- **Work:** Strategy pattern wrapping frozen WorkflowStateEngine. FeatureBackend delegates to frozen engine then runs cascade. TaskBackend handles task mini-lifecycle with same two-phase pattern. Notification push is **optional** — if NotificationQueue is available (Phase 2 shipped), cascade includes notify; otherwise cascade works without it.
- **Test:**
  1. Feature complete_phase → delegates to frozen engine + triggers cascade (separate transaction)
  2. Task complete_phase → 5D transition + cascade
  3. Cascade failure after completion → completion persists, cascade retryable
  4. UUID-to-type_id resolution → correct delegation
  5. Degraded mode (DB unhealthy) → frozen engine falls back to .meta.json, cascade is skipped
  6. No children → rollup_parent is a no-op
  7. Mixed children (active + abandoned) → abandoned excluded from progress
  8. Without notification queue → cascade still works
- **ACs:** AC-25
- **Dependencies:** 3.1, 3.2 (2.3 optional — notifications are non-blocking enhancement)

### Step 3.3a: Reconciliation cascade recovery [S]
- **File:** `reconciliation.py`
- **B5 fix — two-phase commit needs a recovery mechanism:** If process crashes between Phase A (completion committed) and Phase B (cascade), the system is in an inconsistent state: child completed but parent progress stale, dependents not unblocked.
- **Work:** Add `_recover_pending_cascades(db)` to `apply_workflow_reconciliation()`:
  1. Detection query: For each entity with status=completed and a parent_uuid, compute expected parent progress from children. Compare with stored parent progress in metadata. Mismatch = missed cascade.
  2. For each mismatch: re-run `rollup_parent(db, parent_uuid)` and `cascade_unblock(db, completed_entity_uuid)`.
  3. Log: "Recovered {n} missed cascades" (silent when zero).
- **Test:**
  1. Simulate crash: complete child via frozen engine directly (Phase A only), skip cascade (Phase B). Run reconciliation → parent progress updated, dependents unblocked.
  2. No missed cascades → reconciliation is a no-op for this check.
  3. Already-correct state → detection query returns zero mismatches.
- **ACs:** AC-25 (reliability)
- **Dependencies:** 3.2, 3.3

### Step 3.4: Wire MCP server to EntityWorkflowEngine [M]
- **File:** `mcp/workflow_state_server.py`
- **B2 fix — MCP server currently calls frozen engine directly:** `_process_complete_phase` (line 448) takes a `WorkflowStateEngine` and calls `engine.complete_phase()`. Without rewiring, the cascade (unblock, rollup, notification) never fires for features completed via MCP tools — the primary code path.
- **Work:** Update the following functions in `workflow_state_server.py` to route through `EntityWorkflowEngine` instead of `WorkflowStateEngine`:
  1. `_process_complete_phase` → call `entity_engine.complete_phase(entity_uuid, phase)` instead of `engine.complete_phase(feature_type_id, phase)`. The entity engine handles frozen-engine delegation + cascade internally. **Responsibility split:** MCP handler retains phase_timing metadata, iterations, reviewer_notes, and .meta.json projection (lines 459-507) as post-cascade steps. The `finish → status='completed'` update moves INTO EntityWorkflowEngine (completion semantics, not MCP-layer concern).
  2. `_process_transition` → call `entity_engine.transition_phase(entity_uuid, target_phase)` for blocked_by gate checks before delegating to frozen engine.
  3. Server lifespan: instantiate `EntityWorkflowEngine(frozen_engine, db)` alongside the existing engine. Pass both to MCP tool handlers.
  4. **Backward compatibility:** Keep the frozen engine accessible for any code paths that don't need cascade (e.g., `get_phase`, `validate_prerequisites` — read-only operations stay on frozen engine).
- **Test:**
  1. MCP `complete_phase` for feature → cascade fires (unblock + rollup)
  2. MCP `complete_phase` for task → task mini-lifecycle + cascade
  3. MCP `transition_phase` with blocked_by → rejected
  4. Read-only MCP tools (`get_phase`, `validate_prerequisites`) → still use frozen engine, unaffected
  5. Existing 272 workflow state server tests pass (no regression)
- **ACs:** AC-25 (integration)
- **Dependencies:** 3.3

### Step 3.5: Agent-executable task query [S]
- **File:** New MCP tool `query_ready_tasks`
- **Work:** Query: type=task, status=planned, no blocked_by entries, parent in implement phase. Return task list with parent context.
- **Test:** 3 tasks (A ready, B blocked, C parent not in implement) → returns only A.
- **ACs:** AC-24
- **Dependencies:** 3.1, 3.2

---

## Phase 4: L2 Living Projects (AC-26 through AC-30)

### Step 4.1: FiveDBackend for EntityWorkflowEngine [C]
- **File:** `entity_engine.py`
- **Work:** 5D phase-sequence-only transitions (no artifact prerequisites initially). Gate contract: (a) no active blocked_by at Deliver, (b) entity in prior phase. Deliver phase mapping: features=implement, 5D=deliver.
- **Test:** Project transitions through 5D phases. Attempt out-of-sequence → rejected. Attempt deliver with active blocked_by → rejected.
- **ACs:** AC-26, AC-28
- **Dependencies:** 3.3

### Step 4.2: Project progress derivation [M]
- **File:** `rollup.py`
- **Work:** Extend `compute_progress()` to handle both 7-phase and 5D children. Traffic light: RED (<0.4), YELLOW (0.4 to <0.7), GREEN (>=0.7). Store progress + traffic_light in parent metadata.
- **Test:** Project with mixed children → correct weighted progress. Traffic light thresholds verified at boundaries (0.39 → RED, 0.4 → YELLOW, 0.7 → GREEN).
- **ACs:** AC-27
- **Dependencies:** 3.2

### Step 4.3: Deliver gate blocked_by enforcement [M]
- **File:** `entity_engine.py` (FiveDBackend transition validation)
- **Work:** When transitioning to Deliver phase (implement for features, deliver for 5D entities), check `entity_dependencies` table — if any blocked_by entries exist for this entity AND those blockers are not completed, reject the transition. Note: cascade_unblock (removing completed blockers from dependents) was already implemented in Step 3.2/3.3. This step adds the **gate check** that prevents entering Deliver while blocked.
- **Test:** Feature B blocked by A. Attempt implement on B → rejected with "blocked by feature:A". Complete A → cascade_unblock runs → B's blocked_by cleared → implement succeeds.
- **ACs:** AC-28, AC-29
- **Dependencies:** 3.3, 1b.6

### Step 4.4: Orphan guard on abandonment [M]
- **File:** `entity_engine.py` or `database.py`
- **Work:** Before abandoning entity, check for active children (status not completed/abandoned). Block with error unless `--cascade` flag. Cascade = abandon all descendants in single transaction.
- **Test:** Abandon project with active features → blocked. With --cascade → all abandoned. Abandon project with no active children → succeeds.
- **ACs:** AC-30
- **Dependencies:** 1b.3

---

## Phase 5: L1 Strategic — Initiatives & OKRs (AC-31 through AC-34)

### Step 5.1: Initiative and Objective entity lifecycle [M]
- **File:** `entity_engine.py`
- **Work:** Register initiative/objective entity types with FiveDBackend. Standard 5D lifecycle with human-gated transitions (L1 gate stringency — human approval required, no AI auto-approval).
- **Test:** Create initiative → create objective as child → both transition through 5D.
- **ACs:** AC-31
- **Dependencies:** 4.1

### Step 5.2: Key Result entity with scoring [M]
- **File:** New MCP tools: `create_key_result`, `update_kr_score`. Extend `rollup.py` with `compute_okr_score()`.
- **Work:** KR entity with `metric_type` and `score` in metadata. Automated rollup: milestone (completed/total), binary (all-complete or manual), baseline/target (manual only). Un-scored default 0.0 with secretary warning.
- **Test:** Milestone KR with 3 children (2 complete) → score 0.67. Binary KR with children → 0.0 until all complete. Target KR → manual update only.
- **ACs:** AC-32
- **Dependencies:** 5.1, 3.2

### Step 5.3: OKR progress rollup [M]
- **File:** `rollup.py`
- **Work:** Objective score = weighted average of KR scores. Colour coding: Red (<0.4), Yellow (0.4 to <0.7), Green (>=0.7). Rollup uses parent_uuid lineage (not entity_okr_alignment).
- **Test:** Objective with 3 KRs (0.8, 0.5, 1.0) → score 0.77 → Green.
- **ACs:** AC-34
- **Dependencies:** 5.2

### Step 5.4: OKR anti-pattern detection [S]
- **File:** `commands/secretary.md`
- **Work:** On KR creation, check text for activity words (launch, build, implement, etc.) → warn "output not outcome". Check objective KR count > 5 → warn.
- **Test:** "Launch mobile app" → warning. "Achieve 50K MAU" → no warning. 6th KR on objective → warning.
- **ACs:** AC-33
- **Dependencies:** 5.2

---

## Phase 6: Cross-Topology Intelligence (AC-35 through AC-37)

### Step 6.1: Anomaly propagation [M]
- **File:** `entity_engine.py`
- **Work:** On debrief completion with systemic findings, record anomaly in parent metadata: `{anomalies: [{description, source_type_id, timestamp}]}`. Secretary surfaces on parent query.
- **Test:** Feature retro flags systemic issue → parent project metadata includes anomaly.
- **ACs:** AC-35
- **Dependencies:** 3.3

### Step 6.2: Catchball — parent intent on creation [S]
- **File:** `commands/secretary.md`, work creation flow
- **Work:** When creating entity with parent, display parent's name, phase, progress/score as context before confirmation.
- **Test:** Create feature under project → user sees "Parent: project:003 (deliver, 67%)".
- **ACs:** AC-35a
- **Dependencies:** 2.4

### Step 6.3: (Moved to Step 1b.9a — entity tagging ships in Phase 1b)

### Step 6.4: Cross-level progress view [M]
- **File:** `rollup.py`, new MCP tool
- **Work:** Read pre-computed progress from entity metadata up the ancestor chain. No recursive recomputation on query — eager rollup from Phases 3-5 maintains stored progress.
- **Test:** Full hierarchy (initiative → objective → KR → project → features → tasks). Complete all → progress ripples up through stored values.
- **ACs:** AC-37
- **Dependencies:** 5.3, 4.2, 3.2

### Step 6.5: OKR alignment tools [S]
- **File:** New MCP tools: `add_okr_alignment`, `get_okr_alignments`
- **Work:** CRUD on `entity_okr_alignment` junction table. Lateral cross-linkage only — does not participate in automated rollup.
- **Test:** Link feature to KR it's not a child of → alignment recorded. Query alignments → returned.
- **ACs:** (supports AC-37 lateral linkage)
- **Dependencies:** 1b.1

---

## Cross-Cutting: Documentation Sync

Each phase must end with: update CHANGELOG.md, sync README.md / README_FOR_DEV.md / plugins/pd/README.md per CLAUDE.md documentation sync rules. Run `validate.sh` to verify no component table mismatches. This is not a separate step — it's part of the phase's final commit.

---

## Risk Mitigations per Phase

| Phase | Key Risk | Mitigation |
|-------|----------|------------|
| 1a | Kanban derivation breaks existing flows | Replace call sites one at a time, test after each |
| 1b | Schema migration corrupts DB | Auto-backup, dry-run, test on copy, all 1100+ tests pass |
| 2 | Secretary mode detection is unreliable | Context overrides keywords, fallback to clarification |
| 3 | EntityWorkflowEngine breaks L3 features | Feature backend delegates to frozen engine — same code path |
| 4 | 5D transitions untested with real projects | Phase-sequence-only initially (no artifact prerequisites) |
| 5 | OKR scoring produces misleading results | Child-completion rollup only; target-metric is manual |
| 6 | Cross-level rollup is slow at scale | Eager storage, pre-computed progress, no recursive queries |
