# Plan: pd as Fractal Organisational Management Hub

## Implementation Order

7 phases, each independently shippable. Dependencies flow forward — later phases build on earlier ones but each delivers standalone value.

**TDD discipline:** Every step follows: (1) define interface/types, (2) write failing tests against the interface, (3) implement to make tests pass. Steps below describe the deliverable, not the execution order — TDD ordering is implicit.

**Complexity labels:** [S]imple (1-2 files, <1hr), [M]edium (3-5 files, 1-4hrs), [C]omplex (5+ files or architectural change, 4+hrs).

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
- **Work:** Replace all direct kanban_column sets with `derive_kanban()` calls. Remove `STATUS_TO_KANBAN` from both `feature_lifecycle.py` and `backfill.py`. Remove `FEATURE_PHASE_TO_KANBAN`. Update `test_backfill.py` tests that reference STATUS_TO_KANBAN.
- **Test:** Existing kanban tests pass. New integration test: complete_phase → verify kanban_column matches derive_kanban output.
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

### Step 1b.1: Schema migration — combined table rebuilds [C]
- **File:** `scripts/migrate_db.py`, `database.py`
- **Rollback strategy:** (1) Backup verified by opening + querying backup DB before any destructive operation, (2) all 8 steps within single SQLite transaction (CREATE TABLE and INSERT are transactional; table rebuilds use CREATE new → INSERT → DROP old → RENAME within transaction), (3) if any step fails, transaction rolls back and backup is the recovery path. Explicit `--verify-backup` check before proceeding.
- **Work:** Single migration (migration 6) combining:
  1. Drop entity_type CHECK constraint (Python-only validation via `_validate_entity_type`)
  2. Expand workflow_phase CHECK to include 5D phases
  3. Expand mode CHECK to include 'light'
  4. Create `entity_tags` table (entity_uuid, tag) with indexes
  5. Create `entity_dependencies` table (entity_uuid, blocked_by_uuid) with unique constraint + indexes
  6. Create `entity_okr_alignment` table (entity_uuid, key_result_uuid) with indexes
  7. Add `next_seq_{type}` entries to `_metadata` (bootstrap from max existing IDs)
  8. Add `uuid` column to `workflow_phases`, backfill from entity uuid
- **Test:** Migration on test DB copy. Row counts match. All type_ids preserved. Backup file exists. All 1100+ existing tests pass.
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
- **Work:** `HARD_PREREQUISITES` lookup filters to only phases in active template. If phase not in template → not a prerequisite. Read active template from entity's `(entity_type, mode)` via WEIGHT_TEMPLATES.
- **Test:** Light feature: implement requires only spec.md (design.md not required). Standard feature: implement requires spec.md + tasks.md (unchanged).
- **ACs:** AC-15
- **Dependencies:** 1b.7

### Step 1b.9: Light-mode artifact completeness [S]
- **File:** `workflow_state_server.py` (`_process_complete_phase`)
- **Work:** Extend Step 1a.6's artifact check to handle `light` mode. Light features on finish check only `spec.md`. Light tasks have no artifact expectations.
- **Test:** Complete light feature with spec.md → no warning. Without spec.md → warning. Light task → no artifact check.
- **ACs:** AC-5 (light mode)
- **Dependencies:** 1b.1 (mode='light' exists), 1a.6

---

## Phase 2: Secretary + Universal Work Creation (AC-17 through AC-22a)

**Secretary testing strategy:** Deterministic logic (mode detection heuristic, entity search, weight recommendation) is extracted into testable Python functions that the secretary prompt invokes via MCP tools. Tests verify the functions, not the prompt. The prompt is a thin routing layer over tested code.

### Step 2.1: Secretary mode detection [M]
- **File:** `commands/secretary.md`
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
- **Work:** `Notification` dataclass (with project_root field), `NotificationQueue` class (file-backed JSONL, project-scoped drain). MCP tool: `get_notifications`.
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

### Step 3.3: EntityWorkflowEngine (minimal, feature + task backends) [C]
- **File:** New `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
- **Work:** Strategy pattern wrapping frozen WorkflowStateEngine. FeatureBackend delegates to frozen engine. TaskBackend handles task mini-lifecycle. `complete_phase()` runs cascade: unblock → rollup (single BEGIN IMMEDIATE transaction). Notification push is **optional** — if NotificationQueue is available (Phase 2 shipped), cascade includes notify; otherwise cascade works without it.
- **Test:** Feature complete_phase → delegates to frozen engine + triggers cascade. Task complete_phase → 5D transition + cascade. Cascade unblock + rollup in single transaction. Without notification queue → cascade still works.
- **ACs:** AC-25
- **Dependencies:** 3.1, 3.2 (2.3 optional — notifications are non-blocking enhancement)

### Step 3.4: Agent-executable task query [S]
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

### Step 6.3: Entity tagging + circle-aware queries [M]
- **File:** `database.py` (add_tag, get_tags, query_by_tag), MCP tools (add_entity_tag, get_entity_tags)
- **Work:** Tag operations on `entity_tags` junction table. Tags: lowercase, hyphens, max 50 chars. Query by tag returns all matching entities across types.
- **Test:** Tag 3 entities with "security" → query by "security" → all 3 returned.
- **ACs:** AC-35b, AC-36
- **Dependencies:** 1b.1

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
