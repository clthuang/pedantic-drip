# Tasks: pd as Fractal Organisational Management Hub

## Phase 1a: Depth Fixes

### Group 1a-A (parallel — no inter-task dependencies)

#### Task 1a.1: Create derive_kanban() function
- **File:** New `plugins/pd/hooks/lib/workflow_engine/kanban.py`
- **Do:** Create `PHASE_TO_KANBAN` mapping covering 7-phase + 5D phase names. Implement `derive_kanban(status: str, workflow_phase: str | None) -> str`.
- **Done when:** Unit tests pass for every (status, phase) combination: active+specify→wip, completed+finish→completed, abandoned+any→abandoned, active+None→backlog, active+discover→wip (5D)
- **Implements:** Plan Step 1a.1, AC-4

#### Task 1a.3: Field validation in init_feature_state
- **File:** `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py`
- **Do:** Add validation for `feature_id`, `slug`, `branch` — reject empty string, None, whitespace-only with ValueError.
- **Done when:** 9 unit tests pass (3 fields × 3 invalid inputs each). Existing `init_feature_state` tests still pass.
- **Implements:** Plan Step 1a.3, AC-1

#### Task 1a.4: Remove frontmatter health check
- **Files:** `mcp/workflow_state_server.py` (`_process_reconcile_status`), `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- **Do:** Exclude frontmatter drift from `reconcile_status` health boolean. Scan still runs, just doesn't affect `healthy` flag.
- **Done when:** `reconcile_status(summary_only=True)` returns `healthy: true` even with frontmatter drift present. Existing reconciliation tests pass.
- **Implements:** Plan Step 1a.4, AC-2

#### Task 1a.5: Maintenance mode for meta-json-guard
- **File:** `plugins/pd/hooks/meta-json-guard.sh`
- **Do:** Add early check: `if [[ "${PD_MAINTENANCE:-}" == "1" ]]; then output_json "allow" "Maintenance mode active"; exit 0; fi`
- **Done when:** Hook test with PD_MAINTENANCE=1 → allows write. Without → blocks as before.
- **Implements:** Plan Step 1a.5, AC-3

#### Task 1a.6: Artifact completeness warning
- **File:** `mcp/workflow_state_server.py` (`_process_complete_phase`)
- **Do:** On `phase="finish"`, check expected artifacts per mode (standard/full only — light deferred to 1b.10). Read mode from `workflow_phases.mode` column.
- **Done when:** Complete standard feature missing retro.md → succeeds with warning in response JSON. Complete with all artifacts → no warning. Existing tests pass.
- **Implements:** Plan Step 1a.6, AC-5

### Group 1a-B (depends on 1a.1)

#### Task 1a.2a: Audit kanban constant references
- **Files:** All files referencing `STATUS_TO_KANBAN` or `FEATURE_PHASE_TO_KANBAN`
- **Do:** Run `grep -rn 'STATUS_TO_KANBAN\|FEATURE_PHASE_TO_KANBAN' plugins/pd/`. List every file and line. Categorize as production vs test. Update `VALID_MODES` in `backfill.py` to include `'light'`.
- **Done when:** Audit list produced. VALID_MODES updated. No code changes to kanban paths yet (that's 1a.2b).
- **Implements:** Plan Step 1a.2 (audit sub-task)

#### Task 1a.2b: Replace kanban-setting code paths with derive_kanban()
- **Files:** `feature_lifecycle.py`, `workflow_state_server.py`, `engine.py`, `backfill.py`
- **Do:** Replace all direct kanban_column sets with `derive_kanban()` calls. Remove `STATUS_TO_KANBAN` and `FEATURE_PHASE_TO_KANBAN` dicts.
- **Done when:** `grep -rn 'STATUS_TO_KANBAN\|FEATURE_PHASE_TO_KANBAN' plugins/pd/` returns zero production code hits. New integration test: complete_phase → kanban_column matches derive_kanban output. Backfill with status=active, no workflow_phase → kanban derived correctly.
- **Depends on:** Task 1a.2a
- **Implements:** Plan Step 1a.2, AC-4

#### Task 1a.2c: Update test files for kanban constant removal
- **Files:** `test_backfill.py`, `test_engine.py`, `test_constants.py`, `test_reconciliation.py`, `test_workflow_state_server.py`
- **Do:** Update all test files that import or reference removed constants. Replace with `derive_kanban()` calls or updated assertions.
- **Done when:** Full test suite passes: `plugins/pd/.venv/bin/python -m pytest plugins/pd/ -v` (all 1100+ tests green).
- **Depends on:** Task 1a.2b
- **Implements:** Plan Step 1a.2

### Group 1a-C (depends on 1a.2)

#### Task 1a.7: Reconciliation reporting
- **Files:** `reconciliation.py`, session-start hook
- **Do:** `apply_workflow_reconciliation()` returns summary dict with counts. Session-start hook surfaces: "Reconciled: {n} features synced, {n} kanban fixed, {n} warnings". Silent when zero changes.
- **Done when:** Force kanban drift → run reconciliation → summary includes counts. No drift → no output. Existing reconciliation tests pass.
- **Depends on:** Task 1a.2b (kanban derivation must exist)
- **Implements:** Plan Step 1a.7, AC-6

### Group 1a-D: Documentation sync
#### Task 1a.docs: Phase 1a documentation sync
- **Do:** Update CHANGELOG.md, README.md, README_FOR_DEV.md, plugins/pd/README.md. Run `validate.sh`.
- **Done when:** validate.sh passes with 0 errors.
- **Depends on:** All Phase 1a tasks

---

## Phase 1b: Schema Foundation

### Group 1b-A (sequential — migration must complete first)

#### Task 1b.1: Schema migration (migration 6)
- **Files:** `scripts/migrate_db.py`, `plugins/pd/hooks/lib/entity_registry/database.py`
- **Do:** Implement migration 6 following the 14-step DDL sequence in the plan: PRAGMA foreign_keys=OFF → BEGIN IMMEDIATE → rebuild entities (drop entity_type CHECK) → rebuild workflow_phases (expand CHECK constraints, add uuid column with backfill) → rebuild entities_fts → CREATE entity_tags/entity_dependencies/entity_okr_alignment tables → INSERT seq counters → integrity checks → COMMIT → PRAGMA foreign_keys=ON.
- **Done when:** Migration on test DB copy passes: row counts match, all type_ids preserved, backup exists, `PRAGMA foreign_key_check` returns zero violations, zero orphaned workflow_phases, zero NULL uuids, zero orphaned parent_uuid, FTS5 search works, all 1100+ existing tests pass.
- **Implements:** Plan Step 1b.1 [XC], AC-9/10/11/12/16

### Group 1b-B (parallel — all depend only on 1b.1)

#### Task 1b.2: Update VALID_ENTITY_TYPES
- **File:** `database.py`
- **Do:** Expand tuple to include `initiative`, `objective`, `key_result`, `task`. Update `_validate_entity_type`.
- **Done when:** register_entity with each new type → succeeds. Invalid type → ValueError.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 1b.2, AC-9

#### Task 1b.3a: get_entity_by_uuid() and resolve_ref()
- **File:** `database.py`
- **Do:** Add `get_entity_by_uuid(uuid)` → returns entity dict or None. Add `resolve_ref(ref)` → uuid lookup, full type_id lookup, partial type_id prefix search. Ambiguous → raises ValueError with candidates.
- **Done when:** Unit tests: uuid resolve, full type_id, partial match (unique → resolves), partial match (ambiguous → ValueError with candidate list), not found → None.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 1b.3, AC-7

#### Task 1b.3b: search_by_type_id_prefix() and begin_immediate()
- **File:** `database.py`
- **Do:** Add `search_by_type_id_prefix(prefix)` → list of matching entities. Add `begin_immediate()` context manager for explicit transaction control.
- **Done when:** Prefix search returns correct matches. begin_immediate context commits on success, rolls back on exception.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 1b.3, AC-7

#### Task 1b.4: Central ID generator
- **File:** `database.py` or new `id_generator.py`
- **Do:** `generate_entity_id(db, entity_type, name)` → `{seq}-{slug}`. Per-type counter from `_metadata.next_seq_{type}`. Bootstrap `_scan_existing_max_seq`.
- **Done when:** New types → sequential IDs. Existing type → continues from max. Slug: max 30 chars, lowercase, hyphens.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 1b.4, AC-8

#### Task 1b.7: WEIGHT_TEMPLATES registry
- **File:** New `plugins/pd/hooks/lib/workflow_engine/templates.py`
- **Do:** `WEIGHT_TEMPLATES` dict mapping `(entity_type, weight)` → phase sequence. `get_template(entity_type, weight)` lookup function.
- **Done when:** Lookup each defined (type, weight) pair → correct phase sequence. Unknown pair → KeyError or default.
- **Depends on:** None (pure data structure, but phase names only usable after 1b.1)
- **Implements:** Plan Step 1b.7, AC-14

#### Task 1b.9a: Entity tagging CRUD
- **Files:** `database.py` (add_tag, get_tags, query_by_tag), MCP tools in `entity_server.py`
- **Do:** Tag operations on `entity_tags` junction table. Tags: lowercase, hyphens, max 50 chars. MCP tools: `add_entity_tag`, `get_entity_tags`.
- **Done when:** Tag 3 entities with "security" → query_by_tag("security") → all 3 returned. Invalid tag (uppercase, >50 chars) → ValueError. MCP tools work.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 1b.9a, AC-35b/36

### Group 1b-C (depends on 1b.3)

#### Task 1b.5: MCP tool ref parameter
- **Files:** `workflow_state_server.py`, `mcp/entity_server.py`
- **Do:** Audit all `@mcp_tool` decorators for `type_id` params. Add `ref` parameter to each. Resolution: uuid → direct, full type_id → lookup, partial → prefix search. Partial match on mutations → error.
- **Done when:** get_entity(ref="feature:052") → resolves. get_entity(ref="feature:05") with 3 matches → error. update_entity(ref="feature:05") → ambiguous error.
- **Depends on:** Task 1b.3a
- **Implements:** Plan Step 1b.5, AC-7

#### Task 1b.6: Dependency cycle detection
- **File:** New `plugins/pd/hooks/lib/entity_registry/dependencies.py`
- **Do:** `DependencyManager` with `add_dependency()`, `_check_cycle()` (recursive CTE, depth 20), `cascade_unblock()`. MCP tools: `add_dependency`, `remove_dependency`.
- **Done when:** A→B→C, attempt C→A → CycleError. D→A → succeeds. 1000 entities <100ms.
- **Depends on:** Tasks 1b.1, 1b.3a
- **Implements:** Plan Step 1b.6, AC-13

#### Task 1b.7a: Update backfill.py for uuid-primary parent resolution
- **File:** `entity_registry/backfill.py`
- **Do:** Parent linkage reads prefer `parent_uuid`, fall back to `parent_type_id`.
- **Done when:** Backfill entity with parent_uuid set → uses uuid. Legacy entity with only parent_type_id → resolves via fallback.
- **Depends on:** Tasks 1b.1, 1b.3a
- **Implements:** Plan Step 1b.7a, AC-7/NFR-6

### Group 1b-D (depends on 1b.7)

#### Task 1b.8: Gate parameterisation for light weight
- **Files:** `transition_gate/gate.py`, `transition_gate/constants.py`
- **Do:** Add optional `active_phases: list[str] | None = None` to `check_hard_prerequisites()`. When provided, filter HARD_PREREQUISITES to phases in active_phases. When None → unchanged behavior.
- **Done when:** Unit tests: `active_phases=["specify","implement"]` + target "implement" → only spec.md required. `active_phases=None` → spec.md + tasks.md (unchanged). **Note:** Integration test deferred to Phase 3 Step 3.3 (EntityWorkflowEngine).
- **Depends on:** Task 1b.7
- **Implements:** Plan Step 1b.8, AC-15

### Group 1b-E (depends on 1b.1 + 1a.6)

#### Task 1b.10: Light-mode artifact completeness
- **File:** `workflow_state_server.py` (`_process_complete_phase`)
- **Do:** Extend 1a.6's artifact check for `light` mode. Light features on finish check only `spec.md`. Light tasks → no artifact check.
- **Done when:** Complete light feature with spec.md → no warning. Without → warning. Light task → no check.
- **Depends on:** Tasks 1b.1, 1a.6
- **Implements:** Plan Step 1b.10, AC-5 (light)

### Group 1b-F: Documentation sync
#### Task 1b.docs: Phase 1b documentation sync
- **Do:** Update CHANGELOG.md, READMEs. Run `validate.sh`.
- **Depends on:** All Phase 1b tasks

---

## Phase 2: Secretary + Universal Work Creation

### Group 2-A (parallel)

#### Task 2.0: Secretary intelligence module
- **File:** New `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py`
- **Do:** Implement: `detect_mode()`, `find_parent_candidates()`, `check_duplicates()`, `recommend_weight()`, `detect_scope_expansion()` with signatures per plan.
- **Done when:** Unit tests for each function with input/output scenarios from AC-17/18/22a.
- **Depends on:** Task 1b.3a
- **Implements:** Plan Step 2.0

#### Task 2.3: Notification queue
- **File:** New `plugins/pd/hooks/lib/workflow_engine/notifications.py`
- **Do:** `Notification` dataclass, `NotificationQueue` (file-backed JSONL, `fcntl.flock()` for concurrency, project-scoped drain). MCP tool: `get_notifications`.
- **Done when:** Push → drain with matching project_root → returned. Different project_root → empty. Concurrent drain test (two processes) → no data loss.
- **Implements:** Plan Step 2.3, AC-21

### Group 2-B (depends on 2.0)

#### Task 2.1: Secretary mode detection (prompt)
- **File:** `commands/secretary.md`
- **Do:** Wire mode detection into secretary prompt via MCP calls to `secretary_intelligence.py` functions. Context check, keyword classification, ambiguity handling.
- **Done when:** Secretary prompt routes CREATE/CONTINUE/QUERY correctly per AC-17 scenarios.
- **Depends on:** Task 2.0
- **Implements:** Plan Step 2.1, AC-17/18/19

#### Task 2.2: Secretary entity registry queries (prompt)
- **File:** `commands/secretary.md`
- **Do:** Extend TRIAGE step: search for parents, check duplicates, propose linkage. MATCH step: weight recommendation.
- **Done when:** CREATE with existing parent → proposed. Empty registry → standalone.
- **Depends on:** Tasks 1b.3a, 1b.5, 2.0
- **Implements:** Plan Step 2.2, AC-17/18

### Group 2-C (depends on 2.1 + 2.2)

#### Task 2.4: Universal work creation flow
- **File:** `commands/secretary.md`
- **Do:** 4-step flow (identify → link → register → activate) in CREATE mode. Backlog triage.
- **Done when:** Create task → entity registered with parent, tags, template. Promote backlog item → feature created.
- **Depends on:** Tasks 2.1, 2.2
- **Implements:** Plan Step 2.4, AC-20/22

#### Task 2.5: Weight escalation
- **File:** `commands/secretary.md`
- **Do:** Detect scope expansion → recommend weight upgrade. Update mode, write skipped_phases.
- **Done when:** Light feature in implement → expansion detected → mode updated.
- **Depends on:** Tasks 1b.7, 1b.8, 2.0
- **Implements:** Plan Step 2.5, AC-22a

### Group 2-D: Documentation sync
#### Task 2.docs: Phase 2 documentation sync
- **Depends on:** All Phase 2 tasks

---

## Phase 3: L4 Tasks as Work Items

### Group 3-A (parallel, depend on 1b.3 + 1b.6)

#### Task 3.1: promote_task MCP tool
- **File:** `workflow_state_server.py`
- **Do:** `promote_task(feature_ref, task_heading)` — fuzzy-match heading in tasks.md, create task entity with parent=feature uuid, status=planned, template from weight. Parse dependencies → entity_dependencies.
- **Done when:** Promote by heading → entity created. Ambiguous → candidates. Already promoted → error.
- **Depends on:** Tasks 1b.3a, 1b.6
- **Implements:** Plan Step 3.1, AC-23

#### Task 3.2a: rollup_parent() function
- **File:** New `plugins/pd/hooks/lib/workflow_engine/rollup.py`
- **Do:** Synchronous ancestor chain recomputation. Progress rollup with PHASE_WEIGHTS_7 and PHASE_WEIGHTS_5D.
- **Done when:** Complete child → parent progress updated. All children complete → 100%. Abandoned excluded.
- **Depends on:** Tasks 1b.3a, 1b.6
- **Implements:** Plan Step 3.2, AC-25

#### Task 3.2b: get_children_by_uuid()
- **File:** `database.py`
- **Do:** Add `get_children_by_uuid(parent_uuid)` method returning list of child entity dicts.
- **Done when:** Parent with 3 children → returns all 3. No children → empty list.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 3.2

### Group 3-B (depends on 3.1 + 3.2)

#### Task 3.3: EntityWorkflowEngine core
- **File:** New `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
- **Do:** Strategy pattern with FeatureBackend (delegates to frozen engine + cascade) and TaskBackend (task mini-lifecycle + cascade). Two-phase commit: Phase A (frozen engine auto-commits) → Phase B (cascade in separate BEGIN IMMEDIATE). Accept `artifacts_root` parameter and pass through to frozen engine.
- **Done when:** Tests 1-8 from plan Step 3.3 pass. Integration test: light feature → transition to implement → only spec.md required (B6 integration).
- **Depends on:** Tasks 3.1, 3.2a, 3.2b
- **Implements:** Plan Step 3.3 [XC], AC-25

#### Task 3.3a: Reconciliation cascade recovery
- **File:** `reconciliation.py`
- **Do:** Add `_recover_pending_cascades(db)` — detect child completed but parent progress stale, re-run rollup + cascade_unblock.
- **Done when:** Simulated crash (Phase A only, no Phase B) → reconciliation recovers. No mismatches → no-op.
- **Depends on:** Tasks 3.2a, 3.3
- **Implements:** Plan Step 3.3a, AC-25 (reliability)

### Group 3-C (depends on 3.3)

#### Task 3.4: Wire MCP server to EntityWorkflowEngine
- **File:** `mcp/workflow_state_server.py`
- **Do:** Rewire `_process_complete_phase` and `_process_transition` to route through EntityWorkflowEngine. MCP handler retains phase_timing/iterations/reviewer_notes/.meta.json projection. Remove redundant `status='completed'` write from MCP handler (frozen engine handles it).
- **Done when:** MCP complete_phase for feature → cascade fires. For task → mini-lifecycle + cascade. Read-only tools unaffected. All 272 workflow state server tests pass.
- **Depends on:** Task 3.3
- **Implements:** Plan Step 3.4, AC-25 (integration)

#### Task 3.5: Agent-executable task query
- **File:** New MCP tool `query_ready_tasks`
- **Do:** Query: type=task, status=planned, no blocked_by, parent in implement phase.
- **Done when:** 3 tasks (A ready, B blocked, C parent not in implement) → returns only A.
- **Depends on:** Tasks 3.1, 3.2a
- **Implements:** Plan Step 3.5, AC-24

### Group 3-D: Documentation sync
#### Task 3.docs: Phase 3 documentation sync
- **Depends on:** All Phase 3 tasks

---

## Phase 4: L2 Living Projects

### Group 4-A (depends on 3.3)

#### Task 4.1: FiveDBackend for EntityWorkflowEngine
- **File:** `entity_engine.py`
- **Do:** 5D phase-sequence-only transitions. Gate: no active blocked_by at Deliver, entity in prior phase.
- **Done when:** Project transitions through 5D. Out-of-sequence → rejected. Deliver with blocked_by → rejected.
- **Depends on:** Task 3.3
- **Implements:** Plan Step 4.1 [C], AC-26/28

#### Task 4.2: Project progress derivation
- **File:** `rollup.py`
- **Do:** Extend `compute_progress()` for mixed 7-phase + 5D children. Traffic light: RED (<0.4), YELLOW (0.4-0.7), GREEN (>=0.7).
- **Done when:** Mixed children → correct progress. Boundary tests: 0.39→RED, 0.4→YELLOW, 0.7→GREEN.
- **Depends on:** Task 3.2a
- **Implements:** Plan Step 4.2, AC-27

### Group 4-B (depends on 4.1)

#### Task 4.3: Deliver gate blocked_by enforcement
- **File:** `entity_engine.py`
- **Do:** Transition to Deliver checks entity_dependencies. Blocked → rejected with blocker list.
- **Done when:** B blocked by A → implement rejected. Complete A → cascade_unblock → B's implement succeeds.
- **Depends on:** Tasks 3.3, 1b.6
- **Implements:** Plan Step 4.3, AC-28/29

#### Task 4.4: Orphan guard on abandonment
- **File:** `entity_engine.py` or `database.py`
- **Do:** Abandon with active children → blocked unless --cascade. Cascade = abandon all descendants.
- **Done when:** Abandon project with active features → blocked. With --cascade → all abandoned.
- **Depends on:** Task 1b.3a
- **Implements:** Plan Step 4.4, AC-30

### Group 4-C: Documentation sync
#### Task 4.docs: Phase 4 documentation sync
- **Depends on:** All Phase 4 tasks

---

## Phase 5: L1 Strategic — Initiatives & OKRs

### Group 5-A (depends on 4.1)

#### Task 5.1: Initiative and Objective entity lifecycle
- **File:** `entity_engine.py`
- **Do:** Register initiative/objective with FiveDBackend. Human-gated transitions.
- **Done when:** Create initiative → objective as child → both transition through 5D.
- **Depends on:** Task 4.1
- **Implements:** Plan Step 5.1, AC-31

### Group 5-B (depends on 5.1)

#### Task 5.2: Key Result entity with scoring
- **Files:** New MCP tools, `rollup.py`
- **Do:** KR entity with metric_type + score. Automated rollup: milestone, binary, baseline/target.
- **Done when:** Milestone KR 2/3 complete → 0.67. Binary → 0.0 until all complete. Target → manual only.
- **Depends on:** Tasks 5.1, 3.2a
- **Implements:** Plan Step 5.2, AC-32

### Group 5-C (depends on 5.2)

#### Task 5.3: OKR progress rollup
- **File:** `rollup.py`
- **Do:** Objective score = weighted average of KR scores. Colour coding.
- **Done when:** Objective with KRs (0.8, 0.5, 1.0) → 0.77 → Green.
- **Depends on:** Task 5.2
- **Implements:** Plan Step 5.3, AC-34

#### Task 5.4: OKR anti-pattern detection
- **File:** `commands/secretary.md`
- **Do:** KR creation checks for activity words → warn. KR count >5 → warn.
- **Done when:** "Launch mobile app" → warning. "Achieve 50K MAU" → no warning. 6th KR → warning.
- **Depends on:** Task 5.2
- **Implements:** Plan Step 5.4, AC-33

### Group 5-D: Documentation sync
#### Task 5.docs: Phase 5 documentation sync
- **Depends on:** All Phase 5 tasks

---

## Phase 6: Cross-Topology Intelligence

### Group 6-A (parallel)

#### Task 6.1: Anomaly propagation
- **File:** `entity_engine.py`
- **Do:** On debrief completion with systemic findings → record anomaly in parent metadata.
- **Done when:** Feature retro flags issue → parent project metadata includes anomaly entry.
- **Depends on:** Task 3.3
- **Implements:** Plan Step 6.1, AC-35

#### Task 6.2: Catchball — parent intent on creation
- **File:** `commands/secretary.md`
- **Do:** Creating entity with parent → display parent name, phase, progress as context.
- **Done when:** Create feature under project → "Parent: project:003 (deliver, 67%)" visible.
- **Depends on:** Task 2.4
- **Implements:** Plan Step 6.2, AC-35a

#### Task 6.5: OKR alignment tools
- **Files:** New MCP tools
- **Do:** CRUD on `entity_okr_alignment`. Lateral cross-linkage only (not in rollup).
- **Done when:** Link feature to non-parent KR → alignment recorded. Query → returned.
- **Depends on:** Task 1b.1
- **Implements:** Plan Step 6.5

### Group 6-B (depends on 5.3 + 4.2 + 3.2)

#### Task 6.4: Cross-level progress view
- **Files:** `rollup.py`, new MCP tool
- **Do:** Read pre-computed progress up ancestor chain. Eager rollup, no recursive recomputation.
- **Done when:** Full hierarchy test: initiative → objective → KR → project → features → tasks. Complete all → progress ripples up.
- **Depends on:** Tasks 5.3, 4.2, 3.2a
- **Implements:** Plan Step 6.4, AC-37

### Group 6-C: Documentation sync
#### Task 6.docs: Phase 6 documentation sync
- **Depends on:** All Phase 6 tasks
