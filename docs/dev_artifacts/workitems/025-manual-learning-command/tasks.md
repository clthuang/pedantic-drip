# Tasks: Manual Learning Command (`/remember`)

## Phase 1: Core Infrastructure (Steps 1-3 + Step 4 parallel)

### Group A: MCP Enhancement + Tests (sequential)

#### Task 1.1: Add TestConfidence test class (RED)
**File:** `plugins/iflow-dev/mcp/test_memory_server.py`
**Action:** Add new test class `TestConfidence` after existing test classes with 5 test methods:
1. `test_confidence_defaults_to_medium` — call `_process_store_memory(db, provider, keyword_gen, name="test", description="test description for confidence default", reasoning="testing", category="heuristics", references=[])` (no `confidence` kwarg), verify `db.get_entry(content_hash("test description for confidence default"))["confidence"] == "medium"`
2. `test_confidence_low_stored_correctly` — call with same args + `confidence="low"`, verify entry has `confidence="low"`
3. `test_invalid_confidence_returns_error` — call with `confidence="invalid"`, verify result string contains `"Error"`, verify `db.get_entry(...)` returns `None`
4. `test_new_entry_with_confidence_returns_stored` — call with `confidence="low"` on new content, verify `result.startswith("Stored:")`
5. `test_duplicate_entry_returns_reinforced` — call twice with same description (using `confidence="low"`), verify second result starts with `"Reinforced:"` and contains observation count

Use existing test fixtures: `FakeEmbeddingProvider`, `SkipKeywordGenerator`, in-memory `MemoryDatabase`. Import `content_hash` from `semantic_memory`.
**Why:** RED phase for AC-9 (confidence parameter) and AC-3 (differentiated return).

**Done when:** All 5 tests exist, are syntactically valid, and import correctly. Test 1 PASSES immediately (entry dict has no `confidence` key, so `_insert_new()` omits the column and SQLite applies the `DEFAULT 'medium'` constraint from the schema). Tests 2-4 ERROR with `TypeError` (confidence kwarg not accepted by current `_process_store_memory` signature). Test 5 FAILS with `AssertionError` (returns "Stored:" not "Reinforced:"). 4 of 5 are non-passing = valid RED.
**Verification:** `cd plugins/iflow-dev && python -m pytest mcp/test_memory_server.py::TestConfidence --collect-only` succeeds (tests collected).

#### Task 1.2: Add confidence parameter to `_process_store_memory()` (GREEN)
**File:** `plugins/iflow-dev/mcp/memory_server.py`
**Action:**
1. Add `confidence: str = "medium"` parameter to `_process_store_memory()` signature, on a new line after the `references: list[str],` parameter
2. Add confidence validation immediately after the category validation block (after the `return ... Must be one of: ...` block):
   ```python
   if confidence not in ("high", "medium", "low"):
       return (
           f"Error: invalid confidence '{confidence}'. "
           f"Must be one of: high, medium, low"
       )
   ```
3. Add `"confidence": confidence` to the entry dict, after the `"source": source` line

Note: confidence is only set on initial insert. On duplicate upsert, the original confidence is preserved (by design — `_update_existing()` does not include `confidence` in its update columns).

**Why:** AC-9 (confidence parameter on store_memory), GREEN phase.
**Done when:** Tests `test_confidence_defaults_to_medium`, `test_confidence_low_stored_correctly`, `test_invalid_confidence_returns_error`, and `test_new_entry_with_confidence_returns_stored` pass.
**Verification:** `cd plugins/iflow-dev && python -m pytest mcp/test_memory_server.py::TestConfidence::test_confidence_defaults_to_medium mcp/test_memory_server.py::TestConfidence::test_confidence_low_stored_correctly mcp/test_memory_server.py::TestConfidence::test_invalid_confidence_returns_error mcp/test_memory_server.py::TestConfidence::test_new_entry_with_confidence_returns_stored -v` — all 4 pass.

#### Task 1.3: Add differentiated return to `_process_store_memory()`
**File:** `plugins/iflow-dev/mcp/memory_server.py`
**Action:**
1. Before the `db.upsert_entry(entry)` call, insert:
   ```python
   # Pre-check before upsert to distinguish new vs. reinforced return message
   # Safe: MCP server is single-threaded with one DB connection; no concurrent writes possible
   existing = db.get_entry(entry_id)
   ```
2. Replace the final return statement (`return f"Stored: {name} (id: {entry_id})"`) with:
   ```python
   # Differentiated return based on pre-upsert existence
   if existing:
       # Read post-upsert state for accurate observation_count
       updated = db.get_entry(entry_id)
       return f"Reinforced: {name} (id: {entry_id}, observations: {updated['observation_count']})"
   return f"Stored: {name} (id: {entry_id})"
   ```

**Why:** AC-3 (dedup with differentiated return).
**Done when:** `test_duplicate_entry_returns_reinforced` passes AND all existing tests pass (run full test file). The existing `TestDuplicateEntry` validates `observation_count`; the new test validates the "Reinforced:" return string. The existing `TestValidStoreMemory.test_creates_entry_with_correct_fields` validates "Stored:" format is unchanged for new entries.
**Verification:** `cd plugins/iflow-dev && python -m pytest mcp/test_memory_server.py -v` — all tests pass (GREEN).

#### Task 1.4: Wire confidence through `store_memory()` MCP tool
**File:** `plugins/iflow-dev/mcp/memory_server.py`
**Action:**
1. Add `confidence: str = "medium"` parameter to `store_memory()` async function signature, after the `references` parameter
2. Pass `confidence=confidence` to the `_process_store_memory()` call
3. Add to docstring Parameters section:
   ```
   confidence:
       Confidence level for this learning. One of: high, medium, low.
       Default: medium.
   ```

**Why:** AC-9 (MCP tool accepts confidence parameter).
**Done when:** `store_memory()` signature includes `confidence` param. All tests still pass.
**Verification:** `cd plugins/iflow-dev && python -m pytest mcp/test_memory_server.py -v` — all pass.

### Group B: Config Extension (parallel with Group A)

#### Task 1.5: Add config defaults for capture mode and budget
**File:** `plugins/iflow-dev/hooks/lib/semantic_memory/config.py`
**Action:**
1. Add two entries to `DEFAULTS` dict (after existing `memory_keyword_provider` entry):
   ```python
   "memory_model_capture_mode": "ask-first",
   "memory_silent_capture_budget": 5,
   ```
2. Add assertions to `TestReadConfigDefaults.test_missing_file_returns_defaults` in `hooks/tests/test_config.py`, after the existing `assert result["memory_injection_limit"] == 20` line:
   ```python
   assert result["memory_model_capture_mode"] == "ask-first"
   assert result["memory_silent_capture_budget"] == 5
   ```

**Why:** FR-3 config defaults (AC-4, AC-5, AC-6, AC-7 depend on these).
**Done when:** `DEFAULTS["memory_model_capture_mode"] == "ask-first"` and `DEFAULTS["memory_silent_capture_budget"] == 5` (integer, not string).
**Verification:** `cd plugins/iflow-dev && python -m pytest hooks/tests/test_config.py -v` — all pass.

#### Task 1.6: Add config keys to template
**File:** `plugins/iflow-dev/templates/config.local.md`
**Action:** Add under the `# Memory` section, after existing memory_* entries and before the closing `---`:
```yaml
memory_model_capture_mode: ask-first
memory_silent_capture_budget: 5
```

**Why:** FR-3 config discoverability (template shows users available config keys).
**Done when:** Template file contains both new keys in the Memory section.
**Verification:** `grep -c "memory_model_capture_mode\|memory_silent_capture_budget" plugins/iflow-dev/templates/config.local.md` returns `2`.

## Phase 2: User-Facing Components (Steps 5-7, parallel)

### Group C: /remember Command

#### Task 2.1: Create `/remember` command file
**File:** `plugins/iflow-dev/commands/remember.md` (new)
**Action:** Create markdown command file following `add-to-backlog.md` pattern. Frontmatter:
```yaml
---
description: Capture a learning to long-term memory for future session recall.
argument-hint: <learning>
---
```
Body: Numbered instruction steps implementing design C1's 8-step flow (see design.md C1 for authoritative details):
1. Validate input: strip whitespace, if `len(stripped) < 20` output "Learning too short (need at least 20 characters). Please provide more detail." and STOP
2. Infer category using signal words:
   - "never", "don't", "avoid", "wrong", "broken", "bug caused by" → `anti-patterns`
   - "always", "prefer", "use", "should", "best practice" → `patterns`
   - Rules of thumb, system quirks, domain knowledge → `heuristics`
   - Uncertain → default `heuristics`
3. Generate name: concise title ≤60 chars. If >60, truncate to 57 + "..."
4. Generate reasoning: 1-2 sentences explaining why this matters
5. Set description = user's raw free-text (after stripping)
6. Call `store_memory` MCP tool with: `name`, `description`, `reasoning`, `category`, `references=[]`, `confidence="low"`
7. If MCP unavailable, fallback to Bash (escape special characters in user input before embedding in JSON string):
   ```
   PYTHONPATH=plugins/iflow-dev/hooks/lib .venv/bin/python -m semantic_memory.writer \
     --action upsert --global-store ~/.claude/iflow/memory \
     --entry-json '{"name":"...","description":"...","reasoning":"...","category":"...","source":"session-capture","confidence":"low","references":"[]"}'
   ```
8. Parse return: if starts with "Stored" → display `Stored: {name} ({category})`. If "Reinforced" → display `Reinforced: {name} ({category}) — observation count incremented`

**Why:** FR-1 /remember command (AC-1, AC-2, AC-8, AC-12).
**Done when:** File exists at `plugins/iflow-dev/commands/remember.md` with valid YAML frontmatter and all 8 steps present.
**Verification:** File contains `argument-hint: <learning>` and all 8 numbered steps including signal words for category inference and the CLI fallback command with explicit `source` field.

### Group D: Model Guidance Skill

#### Task 2.2: Create capturing-learnings skill
**File:** `plugins/iflow-dev/skills/capturing-learnings/SKILL.md` (new directory + file)
**Action:** Create skill file following `detecting-kanban/SKILL.md` pattern. Frontmatter:
```yaml
---
name: capturing-learnings
description: >-
  Guides model-initiated learning capture. Use when detecting user corrections,
  unexpected system behavior, repeated errors, user preferences, or workarounds.
  Reads memory_model_capture_mode from config to determine behavior.
---
```
Body sections:
1. **Config Reading:** Look for "Memory capture mode:" and "Memory silent capture budget:" lines in session context. If absent, default to ask-first with budget 5.
2. **Trigger Patterns** (5 patterns, each with concrete example per AC-11):
   - User corrects model behavior (e.g., "No, always use absolute paths in hooks")
   - Model discovers unexpected system behavior (e.g., "FTS5 query fails on special characters")
   - Same error twice in one session (e.g., "Import error from missing PYTHONPATH again")
   - User shares preference/convention (e.g., "I prefer kebab-case for file names")
   - Workaround found (e.g., "Suppress stderr to avoid JSON corruption")
3. **Capture Procedure:** Infer category/name/reasoning, call `store_memory` with `confidence="low"`
4. **Budget Tracking:** Maintain explicit counter (e.g., "Silent captures this session: 3/5"). Switch to ask-first at limit. Display: "Silent capture budget reached. Proposing remaining learnings for approval."
5. **Mode Behavior:**
   - `ask-first`: Propose learning + wait for approval. If rejected, discard (no retry for same insight)
   - `silent`: Capture directly + display brief notification `Captured: {name} ({category})`
   - `off`: Do nothing
6. **Fallback:** CLI invocation with explicit `source="session-capture"` (same as /remember step 7)
7. **Invalid config:** Default to `ask-first` if mode value unrecognized

**Why:** FR-5 model guidance (AC-4, AC-5, AC-6, AC-7, AC-11, AC-13).
**Done when:** File exists with valid frontmatter, all 5 trigger patterns with examples, mode behavior for all 3 modes, budget tracking instructions, fallback procedure, and config-absent handling.
**Verification:** File is <500 lines and contains all 5 trigger pattern examples.

### Group E: Session-Start Hook

#### Task 2.3: Add session-start hint and config injection
**File:** `plugins/iflow-dev/hooks/session-start.sh`
**Action:** In `build_context()`, after the line starting with `context+="\nAvailable commands:` and before the `if ! check_claude_md_plugin; then` block, insert these 3 lines:
```bash
    context+="\nTip: Use /remember <learning> to capture insights, or use the store_memory MCP tool directly."
    context+="\nMemory capture mode: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_model_capture_mode" "ask-first")"
    context+="\nMemory silent capture budget: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_silent_capture_budget" "5")"
```
Note: `read_local_md_field` signature is `read_local_md_field "$file" "field_name" "default_value"` (file first).

**Why:** FR-6 session-start hint (AC-10) + config injection for AC-4/AC-5 mode detection.
**Done when:** `build_context` output includes the tip line and both config injection lines.
**Verification:** `cd plugins/iflow-dev && bash hooks/tests/test-hooks.sh` — hook tests pass. Secondary: verify content via `bash hooks/session-start.sh 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); ctx=d['hookSpecificOutput']['additionalContext']; assert '/remember' in ctx; assert 'Memory capture mode:' in ctx; print('OK')"`.

## Phase 3: Documentation (Step 8)

#### Task 3.1: Update README.md
**File:** `README.md`
**Action:**
1. Add `/iflow:remember` row to the Utilities commands table (after `/iflow:add-to-backlog`) with purpose "Capture a learning to long-term memory"
2. Add `capturing-learnings` row to the skills table with description matching SKILL.md frontmatter

**Why:** Documentation sync requirement (CLAUDE.md).
**Done when:** Commands table has `/iflow:remember` row, skills table has `capturing-learnings` row.
**Verification:** `grep "remember" README.md` returns a match in the commands table.

#### Task 3.2: Update README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Action:**
1. Add `/remember` to the commands table with same description as Task 3.1
2. Add `capturing-learnings` to the skills table

**Why:** Documentation sync requirement (CLAUDE.md).
**Done when:** Both new components appear in their respective tables.
**Verification:** `grep "remember" README_FOR_DEV.md` returns a match.

#### Task 3.3: Verify workflow-state skill (no change needed)
**File:** `plugins/iflow-dev/skills/workflow-state/SKILL.md`
**Action:** Verify that no update is needed. The workflow-state skill documents the phase sequence (`brainstorm → specify → ... → finish`) and hard/soft prerequisites. The `/remember` command is a utility command, not a workflow phase, and does not change the phase sequence or prerequisites. No modification required.

**Why:** CLAUDE.md says to update workflow-state "if phase sequence or prerequisites change" — this feature changes neither.
**Done when:** Verified that workflow-state/SKILL.md does not need updating.
**Verification:** No-op — this task is a verification checkpoint only.

## Dependency Summary

```
Phase 1 Group A (sequential): Task 1.1 → 1.2 → 1.3 → 1.4
Phase 1 Group B (parallel with A): Task 1.5, 1.6

Phase 2 (after Phase 1): Tasks 2.1, 2.2, 2.3 (all parallel)
  - 2.1 depends on: 1.4 (store_memory accepts confidence)
  - 2.2 depends on: 1.4 + 1.5 (store_memory + config keys)
  - 2.3 depends on: 1.5 (config keys exist)

Phase 3 (after Phase 2): Tasks 3.1, 3.2, 3.3 (all parallel)
  - All depend on: 2.1, 2.2 (command and skill created)
```

## Task Summary

| Task | Component | File(s) | Complexity |
|------|-----------|---------|------------|
| 1.1 | C6 | test_memory_server.py | Medium |
| 1.2 | C2 | memory_server.py | Simple |
| 1.3 | C2 | memory_server.py | Medium |
| 1.4 | C2 | memory_server.py | Simple |
| 1.5 | C5 | config.py | Simple |
| 1.6 | C5 | config.local.md | Simple |
| 2.1 | C1 | remember.md | Medium |
| 2.2 | C3 | SKILL.md | Medium |
| 2.3 | C4 | session-start.sh | Simple |
| 3.1 | docs | README.md | Simple |
| 3.2 | docs | README_FOR_DEV.md | Simple |
| 3.3 | docs | workflow-state/SKILL.md | Simple |
