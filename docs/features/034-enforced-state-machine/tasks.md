# Tasks: Enforced State Machine (Phase 1)

## Dependency Graph

```
Phase A (parallel):  T0.1  T1.1─T1.2  T3.1─T3.2─T3.3  T5.1
                                  │                           │
                                  ▼                           ▼
Phase A→B bridge:               T1.2─────────────────────→T5.2─T5.3
                       │      │
                       ▼      ▼
Phase B:             T2.1─T2.2─T2.3─T2.4
                       │
                       ▼
Phase C (parallel):  T4.1─T4.2─T4.3  T6.1─T6.2  T7.1─T7.2─T7.3  T8.1─T8.2─T8.3
                       │                  │            │                  │
                       ▼                  ▼            ▼                  ▼
Phase D:             T9.1─T9.2─T9.3─T9.4─T9.5─T9.6─T9.7─T9.8─T9.9
                       │
                       ▼
Phase E:             T10.1─T10.2
```

---

## Phase A: Foundation (parallel — no dependencies)

### T0.1: Add `_iso_now()` utility + tests
**File:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Run `grep -n "from datetime import" plugins/iflow/mcp/workflow_state_server.py` — add import only if absent
2. Add `def _iso_now() -> str: return datetime.now(timezone.utc).isoformat()`
3. Write tests: returns ISO 8601 string, contains `+00:00` or `Z` suffix
**Done when:** Tests pass, `_iso_now()` callable

---

### T1.1: Write `_atomic_json_write()` tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Add test class `TestAtomicJsonWrite`
2. Test: writes valid JSON with trailing newline to a temp path
3. Test: existing file not corrupted if write raises mid-way (mock `json.dump` to raise)
4. Test: temp file cleaned up on `BaseException`
5. Test: file created in correct directory (not `/tmp`)
**Done when:** All 4 tests written, all FAIL (function doesn't exist yet)

---

### T1.2: Implement `_atomic_json_write()` (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `import tempfile` if not present
2. Add `_atomic_json_write(path: str, data: dict) -> None` per design C8
3. `NamedTemporaryFile(mode="w", dir=dirname, suffix=".tmp", delete=False)` → `json.dump` → `os.replace`
4. `except BaseException:` → cleanup temp → re-raise
**Done when:** T1.1 tests pass

---

### T3.1: Write `meta-json-guard.sh` deny/allow tests (RED)
**File:** `plugins/iflow/hooks/tests/test-hooks.sh`
**Do:**
0. Read existing `test-hooks.sh` to understand stdin piping and assertion patterns before writing tests
1. Add test function: pipe Write + `.meta.json` stdin → assert stdout contains `permissionDecision.*deny`
2. Add test: pipe Edit + `.meta.json` stdin → assert deny
3. Add test: pipe Write + `projects/XXX/.meta.json` → assert deny
4. Add test: pipe Write + `spec.md` stdin → assert stdout is `{}`
5. Add test: pipe stdin with `.meta.json` in content but different file_path → assert `{}`
6. Add test: pipe stdin with no `.meta.json` reference → assert `{}`
7. Add test: after deny, check `~/.claude/iflow/meta-json-guard.log` last line is valid JSON with keys `timestamp`, `tool`, `path`, `feature_id` (redirect HOME to temp dir in test)
8. Add test: feature_id extracted correctly from path (`features/034-foo/.meta.json` → `034-foo`)
**Done when:** 8 tests written, all FAIL (script doesn't exist)

---

### T3.2: Implement `meta-json-guard.sh` (GREEN)
**File:** `plugins/iflow/hooks/meta-json-guard.sh`
**Do:**
1. Create file with shebang `#!/usr/bin/env bash`, `set -euo pipefail`
2. Source `lib/common.sh` for `escape_json()`, `install_err_trap()`
3. Read stdin: `INPUT=$(cat)`
4. Fast-path: `if [[ "$INPUT" != *".meta.json"* ]]; then echo '{}'; exit 0; fi`
5. Single python3 call per design C1: `IFS=$'\t' read -r FILE_PATH TOOL_NAME < <(echo "$INPUT" | python3 -c ...)` — do NOT use separate python3 calls or jq (design D2 requires single subprocess)
6. Check `[[ "$FILE_PATH" != *".meta.json" ]]` → allow
7. `log_blocked_attempt()` function: mkdir -p, extract feature_id via regex, append JSONL
8. Inline deny JSON via `cat <<EOF`
9. `chmod +x meta-json-guard.sh`
**Done when:** T3.1 tests pass, script is executable

---

### T3.3: Verify hook latency benchmark
**File:** `plugins/iflow/hooks/tests/test-hooks.sh`
**Do:**
1. Add timing test in `test-hooks.sh`: run hook with non-.meta.json input, assert < 200ms (CI threshold)
2. Run locally once: `time echo '{"tool_name":"Write","tool_input":{"file_path":"foo.md"}}' | plugins/iflow/hooks/meta-json-guard.sh` → verify real < 0.050s
**Done when:** CI latency test (< 200ms) passes; NFR-3 (< 50ms) verified once locally

---

### T5.1: Write `init_project_state` tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Add test class `TestInitProjectState`
2. Test: creates project entity + `.meta.json` with features and milestones arrays
3. Test: brainstorm_source included when provided, omitted when None
4. Test: JSON string params parsed correctly
5. Test: `@_catch_value_error` catches malformed JSON string for `features`/`milestones`
6. Test: project `.meta.json` contains `id`, `slug`, `status`, `created`, `features` (list), `milestones` (list) — and does NOT contain `phases`, `lastCompletedPhase`, `branch`, `mode` (these are feature-only per design C4)
**Done when:** All tests written, all FAIL

---

### T5.2: Implement `_process_init_project_state()` (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `_process_init_project_state(db, project_dir, project_id, slug, features, milestones, brainstorm_source)` per design C4
2. `@_with_error_handling` + `@_catch_value_error` decorators
3. `json.loads(features)`, `json.loads(milestones)` for param parsing
4. `db.register_entity(entity_type="project", ...)` with INSERT OR IGNORE
5. Build project `.meta.json` dict, call `_atomic_json_write()`
**Done when:** T5.1 tests pass

---

### T5.3: Add `init_project_state` MCP wrapper
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `@mcp.tool() async def init_project_state(...)` wrapper
2. Guard: `if _db is None: return _NOT_INITIALIZED`
3. Call `_process_init_project_state(_db, ...)`
**Done when:** MCP tool callable, existing tests still pass

---

## Phase B: Projection function (depends on Phase A: T0.1, T1.2)

### T2.1: Write `_project_meta_json()` tests — happy path (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Mock entity shape:** `{"artifact_path": "...", "metadata": json.dumps({"id":"034","slug":"foo","mode":"standard","branch":"feature/034-foo","phase_timing":{...}}), "status": "active", "created_at": "2026-..."}` — metadata is a JSON string (TEXT column), not a dict.
**Do:**
1. Add test class `TestProjectMetaJson`
2. Test: projects correct JSON structure from mock entity dict + mock engine state
3. Test: `engine=None` → falls back to metadata-only (no `engine.get_state` call); `last_completed` from `metadata.get("last_completed_phase")`
4. Test: resolves `feature_dir` from `entity["artifact_path"]` when not provided
5. Test: phase timing with `iterations` and `reviewerNotes` projected correctly
**Done when:** 4 tests written, all FAIL

---

### T2.2: Write `_project_meta_json()` tests — edge cases (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Test: missing entity → returns warning string
2. Test: write failure → `@patch("<module_path>._atomic_json_write", side_effect=OSError("disk full"))` → returns warning string, no exception raised
3. Test: optional fields (`brainstorm_source`, `skippedPhases`) only present when set
4. Test: NULL metadata → uses empty dict, no TypeError
5. Test: entity with no `artifact_path` and no `feature_dir` param → returns warning
**Done when:** 5 tests written, all FAIL

---

### T2.3: Implement `_project_meta_json()` (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add function per design C2 with dict-style entity access
2. `json.loads(entity["metadata"]) if entity["metadata"] else {}` for safe metadata parsing
3. Guard: `if engine is not None: engine_state = engine.get_state(...); last_completed = engine_state.last_completed_phase if engine_state else None` else: `last_completed = metadata.get("last_completed_phase")`
4. Build `.meta.json` dict: id, slug, mode, status, created, branch, optional fields
5. Phase timing loop from metadata
6. `try: _atomic_json_write(...); return None except Exception as exc: return f"projection failed: {exc}"`
**Done when:** T2.1 + T2.2 tests pass

---

### T2.4: Run existing test suite — verify no regressions
**Command:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
**Done when:** All existing + new tests pass

---

## Phase C: MCP tools (depends on Phase B: T2.3)

### T4.1: Write `init_feature_state` tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Add test class `TestInitFeatureState`
2. Test: creates new entity + `.meta.json` with all fields (id, slug, mode, branch, status)
3. Test: idempotent retry preserves existing `phase_timing`, `last_completed_phase`, `skipped_phases`
4. Test: brainstorm_source and backlog_source included when provided
5. Test: status defaults to "active", respects "planned"
6. Test: returns `projection_warning` if `_project_meta_json` returns warning
7. Test: `@_catch_value_error` catches ValueError on bad input
**Done when:** 6 tests written, all FAIL

---

### T4.2: Implement `_process_init_feature_state()` (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add function per design C3 with dict-style entity access
2. Build metadata dict with id, slug, mode, branch, phase_timing
3. `existing = db.get_entity(feature_type_id)` — register if None, update if exists
4. Retry path: `json.loads(existing["metadata"]) if existing["metadata"] else {}` → preserve timing
5. Call `_project_meta_json(db, engine, feature_type_id, feature_dir)`
**Done when:** T4.1 tests pass

---

### T4.3: Add `init_feature_state` MCP wrapper
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `@mcp.tool() async def init_feature_state(...)` wrapper
2. Guard: `if _db is None: return _NOT_INITIALIZED`
3. Call `_process_init_feature_state(_db, _engine, ...)`
**Done when:** MCP tool callable, all tests pass

---

### T6.1: Write `activate_feature` tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Add test class `TestActivateFeature`
2. Test: planned entity → activated, status becomes "active"
3. Test: non-planned entity → raises ValueError
4. Test: non-existent entity → raises ValueError
5. Test: `.meta.json` projected after activation
6. Test: returns `projection_warning` if projection fails
**Done when:** 5 tests written, all FAIL

---

### T6.2: Implement `_process_activate_feature()` + MCP wrapper (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add function per design C5 with dict-style entity access
2. `entity = db.get_entity(feature_type_id)` → check None → check status == "planned"
3. `db.update_entity(feature_type_id, status="active")`
4. Call `_project_meta_json(db, engine, feature_type_id)`
5. Add `@mcp.tool() async def activate_feature(...)` wrapper
**Done when:** T6.1 tests pass

---

### T7.1: Update existing `_process_transition_phase` test call sites
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Grep for `_process_transition_phase` in test file — count affected call sites
2. Add `db` param (mock EntityDatabase) to every existing call
3. Add `skipped_phases=None` default to every existing call
**Done when:** Existing transition tests still pass with updated signatures

---

### T7.2: Write new transition_phase tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Test: `.meta.json` projected after successful transition
2. Test: `phase_timing[target_phase].started` stored in entity metadata
3. Test: `skipped_phases` stored when provided as JSON string
4. Test: `skipped_phases` not stored when None
5. Test: `started_at` included in response JSON
6. Test: `projection_warning` included when `_project_meta_json` returns warning
**Done when:** 6 tests written, all FAIL

---

### T7.3: Extend `_process_transition_phase()` implementation (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `db: EntityDatabase` and `skipped_phases: str | None = None` params to signature
2. After `engine.transition_phase()` success: `entity = db.get_entity(...)`, parse metadata
3. Store `phase_timing[target_phase]["started"] = _iso_now()`
4. If `skipped_phases`: `metadata["skipped_phases"] = json.loads(skipped_phases)`
5. `db.update_entity(feature_type_id, metadata=metadata)`
6. Call `_project_meta_json(db, engine, feature_type_id)`
7. Update MCP wrapper: pass `_db`, add `skipped_phases` param
**Done when:** T7.1 existing + T7.2 new tests pass

---

### T8.1: Update existing `_process_complete_phase` test call sites
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Grep for `_process_complete_phase` in test file — count affected call sites
2. Add `db` param (mock EntityDatabase) to every existing call
3. Add `iterations=None, reviewer_notes=None` defaults to every existing call
**Done when:** Existing completion tests still pass with updated signatures

---

### T8.2: Write new complete_phase tests (RED)
**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**Do:**
1. Test: `.meta.json` projected after successful completion
2. Test: `phase_timing[phase].completed`, `iterations`, `reviewerNotes` stored correctly
3. Test: `last_completed_phase` updated in entity metadata
4. Test: terminal phase `"finish"` → entity status set to "completed"
5. Test: `completed_at` included in response JSON
6. Test: `projection_warning` included when `_project_meta_json` returns warning
7. Test: `reviewer_notes` parsed from JSON string
**Done when:** 7 tests written, all FAIL

---

### T8.3: Extend `_process_complete_phase()` implementation (GREEN)
**File:** `plugins/iflow/mcp/workflow_state_server.py`
**Do:**
1. Add `db: EntityDatabase`, `iterations: int | None = None`, `reviewer_notes: str | None = None` params
2. After `engine.complete_phase()`: `entity = db.get_entity(...)`, parse metadata
3. Store `phase_timing[phase]["completed"] = _iso_now()`, iterations, reviewerNotes
4. `metadata["last_completed_phase"] = phase`
5. If `phase == "finish"`: `db.update_entity(..., status="completed", metadata=metadata)`
6. Else: `db.update_entity(..., metadata=metadata)`
7. Call `_project_meta_json(db, engine, feature_type_id)`
8. Update MCP wrapper: pass `_db`, add `iterations`/`reviewer_notes` params
**Done when:** T8.1 existing + T8.2 new tests pass

---

## Phase D: Write site updates (depends on Phase C)

### T9.1: Update `commands/create-feature.md` (Site 1)
**File:** `plugins/iflow/commands/create-feature.md`
**Do:**
1. Find Write tool instruction for `.meta.json` (~lines 97-110)
2. Replace with `init_feature_state(feature_dir, feature_id, slug, mode, branch, brainstorm_source, backlog_source, status)` call
3. Remove inline JSON template — MCP tool handles format
**Verify:** `grep -n 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/commands/create-feature.md` returns empty
**Done when:** No direct `.meta.json` write instructions remain in file

---

### T9.2: Update `skills/decomposing/SKILL.md` — planned features (Site 2)
**File:** `plugins/iflow/skills/decomposing/SKILL.md`
**Do:**
1. Find Write instruction for planned feature `.meta.json` (~lines 224-239)
2. Replace with `init_feature_state(feature_dir, feature_id, slug, mode, branch, status="planned")` call
**Verify:** Check file for remaining `.meta.json` write instructions
**Done when:** Planned feature creation uses MCP tool

---

### T9.3: Update `skills/decomposing/SKILL.md` — project .meta.json (Site 3)
**File:** `plugins/iflow/skills/decomposing/SKILL.md`
**Do:**
1. Find Write instruction for project `.meta.json` (~lines 282-292)
2. Replace with `init_project_state(project_dir, project_id, slug, features, milestones, brainstorm_source)` call
**Verify:** `grep -n 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/decomposing/SKILL.md` returns empty
**Done when:** No direct `.meta.json` write instructions remain in file

---

### T9.4: Update `skills/workflow-state/SKILL.md` — planned→active (Site 4)
**File:** `plugins/iflow/skills/workflow-state/SKILL.md`
**Do:**
1. Find Edit instruction for status planned→active (~lines 41-46)
2. Replace with `activate_feature(feature_type_id)` call
**Done when:** Status transition uses MCP tool

---

### T9.5: Update `skills/workflow-state/SKILL.md` — skippedPhases (Site 5)
**File:** `plugins/iflow/skills/workflow-state/SKILL.md`
**Do:**
1. Find Edit instruction for `skippedPhases` array (~lines 117-120)
2. Replace with `transition_phase(feature_type_id, target_phase, yolo_active, skipped_phases=json_string)` call
**Verify:** `grep -n 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/workflow-state/SKILL.md` returns empty
**Done when:** No direct `.meta.json` write instructions remain in file

---

### T9.6: Update `skills/workflow-transitions/SKILL.md` — phase started (Site 6)
**File:** `plugins/iflow/skills/workflow-transitions/SKILL.md`
**Do:**
1. Find Edit instruction for `phases.{name}.started` (~lines 109-118)
2. Remove — `transition_phase()` now stores started timestamp automatically via `_project_meta_json()`
3. Update surrounding text to note the timestamp comes from MCP response `started_at` field
**Done when:** No direct phase-started Edit instruction remains

---

### T9.7: Update `skills/workflow-transitions/SKILL.md` — phase completed (Site 7)
**File:** `plugins/iflow/skills/workflow-transitions/SKILL.md`
**Do:**
1. Find Edit instruction for `phases.{name}.completed`, `iterations`, `reviewerNotes`, `lastCompletedPhase` (~lines 206-217)
2. Remove — `complete_phase()` now stores timing data + projects `.meta.json` automatically
3. Update surrounding text to note `complete_phase(feature_type_id, phase, iterations, reviewer_notes)` handles this
**Verify:** `grep -n 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/workflow-transitions/SKILL.md` returns empty
**Done when:** No direct `.meta.json` write instructions remain in file

---

### T9.8: Update `commands/finish-feature.md` — terminal status (Site 8)
**File:** `plugins/iflow/commands/finish-feature.md`
**Do:**
1. Find Edit instruction for `status: "completed"` (~lines 415-429)
2. Replace with `complete_phase(feature_type_id, "finish")` — this sets entity status to "completed" and projects `.meta.json`
**Verify:** `grep -n 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/commands/finish-feature.md` returns empty
**Done when:** No direct `.meta.json` write instructions remain in file

---

### T9.9: Update `commands/create-project.md` — project .meta.json (Site 9)
**File:** `plugins/iflow/commands/create-project.md`
**Do:**
1. Find Write instruction for project `.meta.json` (~lines 60-75)
2. Replace with `init_project_state(project_dir, project_id, slug, features, milestones, brainstorm_source)` call
**Verify:** `grep -rn 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/ plugins/iflow/commands/` returns zero matches across ALL files
**Done when:** Zero residual `.meta.json` write instructions in entire plugin

---

## Phase E: Enforcement (depends on Phase D + T3.3)

### T10.1: Register hook in `hooks.json`
**File:** `plugins/iflow/hooks/hooks.json`
**Do:**
1. Insert at index 2 in `PreToolUse` array (after `Bash`/pre-commit-guard, before `.*`/yolo-guard):
   ```json
   {
     "matcher": "Write|Edit",
     "hooks": [{ "type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/meta-json-guard.sh" }]
   }
   ```
2. If `Write|Edit` regex matcher fails empirically, fall back to two separate entries
**Done when:** Hook registered, JSON valid

---

### T10.2: Final verification
**Commands:**
1. `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v` — all pass
2. `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v` — all pass
3. `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_reconciliation.py -v` — all pass
4. `bash plugins/iflow/hooks/tests/test-hooks.sh` — all pass including new hook tests
5. `grep -rn 'Write.*meta.json\|Edit.*meta.json' plugins/iflow/skills/ plugins/iflow/commands/` — zero matches
**Done when:** All 5 checks pass, feature ready for implement-phase review

---

## Summary

| Phase | Tasks | Parallel | Depends On |
|-------|-------|----------|------------|
| A | T0.1, T1.1-T1.2, T3.1-T3.3, T5.1 | Yes | None |
| A→B | T5.2-T5.3 | No | T1.2 |
| B | T2.1-T2.4 | No | A (T0.1, T1.2) |
| C | T4.1-T4.3, T6.1-T6.2, T7.1-T7.3, T8.1-T8.3 | Yes | B (T2.3) |
| D | T9.1-T9.9 | Sequential | C (all) |
| E | T10.1-T10.2 | No | D + T3.2 |

**Total:** 36 tasks across 5 phases
