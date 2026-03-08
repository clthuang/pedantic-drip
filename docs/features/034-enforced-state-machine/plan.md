# Plan: Enforced State Machine (Phase 1)

## Build Order

Implementation follows the dependency chain from design.md (C8→C2→C1→C3→C4→C5→C6→C7→sites→hook), with tests written TDD-style before each component.

**Deployment constraint:** All 10 steps must land in a single merge to develop. Do NOT merge partial skill updates without the corresponding MCP tools — the feature branch provides natural isolation.

### Entity access convention

`db.get_entity()` returns `dict | None`. Access fields via dict keys: `entity["status"]`, `entity["metadata"]`, `entity["artifact_path"]`, `entity["created_at"]`. The `metadata` field is a nullable JSON TEXT column — use `json.loads(entity["metadata"]) if entity["metadata"] else {}` for safe parsing. All `_process_*` functions and `_project_meta_json()` must use dict-style access throughout.

**Note:** Design.md pseudocode (C3, C5, C6, C7) uses attribute-style access (`entity.metadata`) for readability. This plan overrides: use dict-style access (`entity["metadata"]`) in actual implementation.

### Step 0: `_iso_now()` utility

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**Why this item:** Referenced by Steps 2, 4, 7, 8 for timestamp generation. Must exist before any caller.

**What:**
- Add `def _iso_now() -> str: return datetime.now(timezone.utc).isoformat()` utility function
- Add `from datetime import datetime, timezone` import if not present

**Tests (write first):**
- Returns ISO 8601 format string
- Returns UTC timezone

**Depends on:** Nothing

---

### Step 1: `_atomic_json_write()` utility (C8)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Add `_atomic_json_write(path, data)` function using `NamedTemporaryFile` + `os.replace()` pattern
- Handle `BaseException` with cleanup + re-raise

**Tests (write first):**
- Writes valid JSON with trailing newline
- Atomic: partial write doesn't corrupt existing file
- Cleans up temp file on failure
- Creates file in correct directory

**Depends on:** Nothing

---

### Step 2: `_project_meta_json()` projection (C2)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Add `_project_meta_json(db, engine, feature_type_id, feature_dir=None)` function
- Read entity from DB, get authoritative state from `engine.get_state()`
- Build `.meta.json` structure from entity metadata + engine state
- Call `_atomic_json_write()` for crash-safe write
- Return `None` on success, warning string on failure (fail-open)
- Accept `engine: WorkflowStateEngine | None` — if `None`, skip `engine.get_state()` and fall back to metadata-only projection (needed for `init_feature_state` where no prior engine state exists)
- Parse `entity["metadata"]` via `json.loads()` — it's a JSON TEXT column, not a dict

**Tests (write first):**
- Projects correct JSON structure from mock DB entity + engine state
- Falls back to metadata when engine state unavailable
- Projects correctly with `engine=None` (new feature, no prior state)
- Returns warning string (not raises) on write failure
- Resolves `feature_dir` from `entity["artifact_path"]` when not provided
- Handles missing entity gracefully
- Includes optional fields (`brainstorm_source`, `skippedPhases`) only when present
- Phase timing with `iterations` and `reviewerNotes` projected correctly

**Depends on:** Steps 0, 1

---

### Step 3: `meta-json-guard.sh` hook (C1)

**Files:** `plugins/iflow/hooks/meta-json-guard.sh`, `plugins/iflow/hooks/tests/test-hooks.sh`

**What:**
- Create hook script with fast-path string check
- Single python3 call for `file_path` + `tool_name` extraction (tab-delimited)
- `log_blocked_attempt()` function appending JSONL
- Source `lib/common.sh` for `escape_json()`, `detect_project_root()`, `install_err_trap()`
- Inline deny JSON (no shared `output_block`)

**Tests (write first):**
- Denies Write targeting `features/XXX/.meta.json`
- Denies Edit targeting `features/XXX/.meta.json`
- Denies Write targeting `projects/XXX/.meta.json`
- Allows Write targeting `spec.md` (non-.meta.json)
- Allows Write with content mentioning `.meta.json` but different file_path
- Fast-path: returns `{}` immediately when input has no `.meta.json` reference
- Log entry created with correct JSONL format
- Feature ID extracted from path regex
- Latency benchmark: verify < 200ms for CI stability (target 50ms per NFR-3, documented as local verification)

**Test approach:** Pipe mock JSON stdin to `meta-json-guard.sh` and assert stdout. Check existing `test-hooks.sh` for precedent patterns — extend with deny/allow test cases.

**Depends on:** Nothing (independent of C2, but ordered here for build clarity)

**NOTE:** Do NOT register in `hooks.json` yet — registration is Step 10.

---

### Step 4: `init_feature_state` MCP tool (C3)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Add `_process_init_feature_state(db, engine, feature_dir, feature_id, slug, mode, branch, brainstorm_source, backlog_source, status)` with `@_with_error_handling` + `@_catch_value_error`
- Register entity via `db.register_entity()`, or update metadata on retry (preserve existing `phase_timing`, `last_completed_phase`, `skipped_phases`)
- Call `_project_meta_json()` for projection
- Add `@mcp.tool()` async wrapper: `init_feature_state(...)` passing `_db`, `_engine`

**Tests (write first):**
- Creates new entity + `.meta.json` with all fields
- Idempotent retry preserves existing phase_timing
- Brainstorm source and backlog source included when provided
- Status defaults to "active", respects "planned"
- Returns `projection_warning` if projection fails
- `@_catch_value_error` catches malformed input

**Depends on:** Step 2

---

### Step 5: `init_project_state` MCP tool (C4)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Add `_process_init_project_state(db, project_dir, project_id, slug, features, milestones, brainstorm_source)` with `@_with_error_handling` + `@_catch_value_error`
- Register entity via `db.register_entity(entity_type="project", ...)`
- Build project-specific `.meta.json` (different schema: `features[]`, `milestones[]`, no `phases`, `lastCompletedPhase`, `branch`, `mode`)
- Write via `_atomic_json_write()` directly (not `_project_meta_json`)
- Add `@mcp.tool()` async wrapper

**Tests (write first):**
- Creates project entity + `.meta.json` with features and milestones arrays
- Includes brainstorm_source when provided
- Parses JSON string params (`features`, `milestones`)
- Atomic write (no partial files)
- `@_catch_value_error` catches malformed JSON input

**Depends on:** Step 1

---

### Step 6: `activate_feature` MCP tool (C5)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Add `_process_activate_feature(db, engine, feature_type_id)` with `@_with_error_handling` + `@_catch_value_error`
- Pre-condition: entity status must be "planned" (raise `ValueError` otherwise)
- Update entity status to "active" via `db.update_entity()`
- Call `_project_meta_json()` for projection
- Add `@mcp.tool()` async wrapper

**Tests (write first):**
- Activates planned feature → status becomes "active"
- Rejects non-planned status with ValueError
- Rejects non-existent entity with ValueError
- Projects `.meta.json` after activation
- Returns `projection_warning` if projection fails

**Depends on:** Step 2

---

### Step 7: Extend `transition_phase` (C6)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Modify `_process_transition_phase` signature: add `db: EntityDatabase` and `skipped_phases: str | None` params
- After successful transition: store `phase_timing[target_phase].started` in entity metadata (use `json.loads(entity["metadata"])` for dict access)
- Store `skipped_phases` in metadata when provided
- Call `_project_meta_json()` after DB update
- Update `@mcp.tool()` wrapper: pass `_db`, add `skipped_phases` param

**Signature change impact:** All existing test calls to `_process_transition_phase()` must add the `db` param. Grep `_process_transition_phase` in test files to identify affected call sites and update them first.

**Tests (extend existing):**
- `.meta.json` projected after successful transition
- Phase timing `started` timestamp stored in entity metadata
- Skipped phases stored when provided
- Skipped phases not stored when None
- `started_at` included in response
- `projection_warning` included when projection fails
- Existing transition tests still pass (with updated call signatures)

**Depends on:** Step 2

---

### Step 8: Extend `complete_phase` (C7)

**Files:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`

**What:**
- Modify `_process_complete_phase` signature: add `db: EntityDatabase`, `iterations: int | None`, `reviewer_notes: str | None` params
- After engine completes phase: store timing metadata (use `json.loads(entity["metadata"])` for dict access)
- Store `last_completed_phase` in entity metadata
- For `phase == "finish"`: set entity status to "completed"
- Call `_project_meta_json()` after DB update
- Update `@mcp.tool()` wrapper: pass `_db`, add `iterations`/`reviewer_notes` params

**Signature change impact:** All existing test calls to `_process_complete_phase()` must add the `db` param. Grep `_process_complete_phase` in test files to identify affected call sites and update them first.

**Tests (extend existing):**
- `.meta.json` projected after successful completion
- Phase timing `completed`, `iterations`, `reviewerNotes` stored correctly
- `last_completed_phase` updated in entity metadata
- Terminal phase ("finish") sets entity status to "completed"
- `completed_at` included in response
- `projection_warning` included when projection fails
- Existing completion tests still pass (with updated call signatures)
- `reviewer_notes` parsed from JSON string

**Depends on:** Step 2

---

### Step 9: Skill/command write site updates (9 sites)

**Files:** 6 skill/command files

**What:** Replace all 9 direct `.meta.json` Write/Edit instructions with MCP tool calls.

| Site | File | Current | New MCP Call |
|------|------|---------|-------------|
| 1 | `commands/create-feature.md` | Write `.meta.json` | `init_feature_state(...)` |
| 2 | `skills/decomposing/SKILL.md` | Write planned `.meta.json` | `init_feature_state(status="planned")` |
| 3 | `skills/decomposing/SKILL.md` | Write project `.meta.json` | `init_project_state(...)` |
| 4 | `skills/workflow-state/SKILL.md` | Edit status planned→active | `activate_feature(...)` |
| 5 | `skills/workflow-state/SKILL.md` | Edit skippedPhases | `transition_phase(..., skipped_phases=...)` |
| 6 | `skills/workflow-transitions/SKILL.md` | Edit phase started | Remove — `transition_phase()` now handles |
| 7 | `skills/workflow-transitions/SKILL.md` | Edit phase completed | Remove — `complete_phase()` now handles |
| 8 | `commands/finish-feature.md` | Edit status completed | `complete_phase("finish")` |
| 9 | `commands/create-project.md` | Write project `.meta.json` | `init_project_state(...)` |

**Verification after each site:**
- `grep -rn 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/ plugins/iflow/commands/` confirms removal
- Run full test suite to catch regressions

**Depends on:** Steps 4-8 (all MCP tools must exist before sites reference them)

---

### Step 10: Hook registration in `hooks.json`

**Files:** `plugins/iflow/hooks/hooks.json`

**What:**
- Insert `meta-json-guard.sh` entry in `PreToolUse` array at index 2 (after `Bash`/pre-commit-guard, before `.*`/yolo-guard)
- Matcher: `"Write|Edit"`

**Critical:** This must be the LAST step. If the hook is enabled before all 9 write sites are updated, legitimate `.meta.json` writes will be blocked.

**Verification:**
- Run full test suite
- Manual test: attempt Write to `.meta.json` → confirm deny
- Manual test: call `transition_phase` → confirm `.meta.json` updated (not blocked)

**Depends on:** Steps 3, 9

---

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|-------------------|
| Test suite disruption (392 references) | Incremental: run suite after each step, fix test failures before next step |
| Hook blocks legitimate writes | Hook registration is LAST step — all sites converted first |
| Stale `.meta.json` | `_project_meta_json` is synchronous, called inline |
| Latency regression | Hook fast-path tested in Step 3 (NFR-3 < 50ms) |

## Parallelizable Steps

Steps that share no dependencies can be implemented in parallel:
- **Step 0 + Step 1 + Step 3 + Step 5**: All independent (Step 5 needs only Step 1, not Step 2)
- **Step 4 + Step 6 + Step 7 + Step 8**: All depend on Step 2, independent of each other

Sequential constraints:
- Step 0 has no dependencies (can run in parallel with Step 1 + Step 3)
- Step 2 must follow Steps 0 and 1
- Steps 4-8 must follow Step 2
- Step 9 must follow Steps 4-8
- Step 10 must follow Steps 3 and 9

## Completion Criteria

- [ ] All 10 steps implemented and tested
- [ ] `grep -rn 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/ plugins/iflow/commands/` returns zero matches
- [ ] Full test suite passes: engine (289), workflow_state_server (146+), reconciliation (103), hooks
- [ ] Hook latency < 50ms verified
- [ ] JSONL instrumentation log format verified
