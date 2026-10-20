# Plan: Manual Learning Command (`/remember`)

## Implementation Steps

### Step 1: Write tests for confidence parameter and differentiated return (RED)

**Component:** C6 (Test Updates)
**File:** `plugins/iflow-dev/mcp/test_memory_server.py`
**Dependencies:** None (TDD: tests first)

**Changes:** Add new test class `TestConfidence` with 5 test methods:
1. `test_confidence_defaults_to_medium` — call `_process_store_memory` without `confidence` param, verify entry has `confidence='medium'`
2. `test_confidence_low_stored_correctly` — call with `confidence="low"`, verify entry has `confidence='low'`
3. `test_invalid_confidence_returns_error` — call with `confidence="invalid"`, verify error string returned containing "Error", no entry created
4. `test_new_entry_with_confidence_returns_stored` — call with `confidence="low"` on new content, verify result starts with `"Stored:"`. This exercises the NEW confidence parameter (unlike existing `TestValidStoreMemory.test_creates_entry_with_correct_fields` which tests the old signature).
5. `test_duplicate_entry_returns_reinforced` — call twice with same description, verify second call returns string starting with `"Reinforced:"` and contains the actual observation count

**Expected state:** Tests 1-4 will ERROR in RED phase with `TypeError` (unexpected keyword argument `confidence`). Test 5 will FAIL with `AssertionError` (return string starts with `"Stored:"` not `"Reinforced:"`). All 5 are non-passing. Step 2 makes all 5 pass (GREEN).

**Verification:** Tests are syntactically valid and importable. Expected failures confirmed.

### Step 2: Add confidence parameter and differentiated return to `_process_store_memory()` (GREEN)

**Component:** C2 (MCP `store_memory` Enhancement — core function)
**File:** `plugins/iflow-dev/mcp/memory_server.py`
**Dependencies:** Step 1 (tests exist and fail)

**Changes:**
1. Add `confidence: str = "medium"` parameter to `_process_store_memory()` signature (after `references`)
2. Add confidence validation after the category validation block:
   ```python
   if confidence not in ("high", "medium", "low"):
       return (
           f"Error: invalid confidence '{confidence}'. "
           f"Must be one of: high, medium, low"
       )
   ```
3. Add `"confidence": confidence` to the entry dict (after the `"source": source` entry)
4. Insert existence check BEFORE `db.upsert_entry(entry)` and move the return after all embedding logic:
   ```python
   # Check existence BEFORE upsert to distinguish new vs. reinforced
   existing = db.get_entry(entry_id)

   db.upsert_entry(entry)

   # ... embedding logic (unchanged) ...

   # Differentiated return based on pre-upsert existence
   if existing:
       # Read post-upsert state for accurate observation_count
       updated = db.get_entry(entry_id)
       return f"Reinforced: {name} (id: {entry_id}, observations: {updated['observation_count']})"
   return f"Stored: {name} (id: {entry_id})"
   ```

**Key detail:** The existence check uses `db.get_entry(entry_id)` BEFORE `db.upsert_entry(entry)` to determine if the entry is new or existing. The observation count is read AFTER upsert from the post-upsert state to get the accurate incremented value.

**Safety assumption (single-connection serialization):** The pre-upsert `get_entry` and post-upsert `get_entry` calls occur outside `upsert_entry`'s internal `BEGIN IMMEDIATE` transaction. This is safe because `MemoryDatabase` uses a single `sqlite3.Connection` and Python's sqlite3 module serializes all operations on a single connection — no TOCTOU race is possible. Implementation MUST include a code comment documenting this assumption so future refactors to multi-connection access don't silently introduce a race condition.

**Note on confidence immutability:** `_update_existing()` in database.py does NOT update `confidence` on conflict — this is intentional per design R3. First confidence wins on dedup.

**Verification:** `cd plugins/iflow-dev && python -m pytest mcp/test_memory_server.py -v` — all tests pass (GREEN), including new TestConfidence tests and all existing tests (return format for new entries unchanged).

### Step 3: Add confidence parameter to `store_memory()` MCP tool

**Component:** C2 (MCP `store_memory` Enhancement — MCP wrapper)
**File:** `plugins/iflow-dev/mcp/memory_server.py`
**Dependencies:** Step 2

**Changes:**
1. Add `confidence: str = "medium"` parameter to `store_memory()` async function signature (after `references`)
2. Pass `confidence=confidence` to `_process_store_memory()` call
3. Add `confidence` to the tool's docstring Parameters section:
   ```
   confidence:
       Confidence level for this learning. One of: high, medium, low.
       Default: medium.
   ```

**Verification:** All tests still pass. MCP tool schema auto-generates from type annotation.

### Step 4: Add config defaults for capture mode and budget

**Component:** C5 (Config Extension)
**Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/config.py`, `plugins/iflow-dev/templates/config.local.md`
**Dependencies:** None (independent of Steps 1-3, can run in parallel)

**Changes to `config.py`:**
Add two entries to the `DEFAULTS` dict (after existing `memory_keyword_provider` entry):
```python
"memory_model_capture_mode": "ask-first",
"memory_silent_capture_budget": 5,
```

**Changes to `templates/config.local.md`:**
Add under the `# Memory` section (before the closing `---`):
```yaml
memory_model_capture_mode: ask-first
memory_silent_capture_budget: 5
```

**Note:** `_coerce("ask-first")` returns `"ask-first"` as string (no bool/int/float match). `_coerce("5")` returns `int(5)`. Types are consistent with DEFAULTS.

**Verification:** `cd plugins/iflow-dev && python -m pytest hooks/tests/test_config.py -v` — config tests pass. Additionally verify: `read_config` with missing file returns `result["memory_model_capture_mode"] == "ask-first"` and `result["memory_silent_capture_budget"] == 5`.

### Step 5: Create `/remember` command

**Component:** C1 (`/remember` Command)
**File:** `plugins/iflow-dev/commands/remember.md` (new file)
**Dependencies:** Steps 2-3 (store_memory accepts confidence)

**Content:** Markdown command file following `add-to-backlog.md` pattern. Flow steps match design C1 exactly; see design.md C1 for authoritative details.
- Frontmatter: `description`, `argument-hint: <learning>`
- Body: Numbered instructions implementing the 8-step flow from design C1:
  1. Validate input: strip whitespace, if fewer than 20 characters output error message and stop (model-enforced validation via explicit instruction text)
  2. Infer category using signal words (anti-patterns/patterns/heuristics, default heuristics)
  3. Generate name (≤60 chars, truncate to 57+"...")
  4. Generate reasoning (1-2 sentences)
  5. Set description = raw text after stripping
  6. Call `store_memory` MCP with `confidence="low"`
  7. Fallback to writer CLI with explicit `source="session-capture"` and PYTHONPATH
  8. Parse return string prefix for "Stored" vs "Reinforced" confirmation

**Verification:** File exists, frontmatter parses correctly, all 8 flow steps present, category inference rules include concrete signal words, CLI fallback command includes PYTHONPATH and explicit source.

### Step 6: Create model guidance skill

**Component:** C3 (Model Guidance Skill)
**File:** `plugins/iflow-dev/skills/capturing-learnings/SKILL.md` (new file)
**Dependencies:** Steps 2-3 (store_memory), Step 4 (config keys exist) — these are documentation-accuracy dependencies (skill references features that must exist), not build/test dependencies. The skill is a standalone markdown file with no imports.

**Content:** Markdown skill file following `detecting-kanban/SKILL.md` pattern:
- Frontmatter: `name: "capturing-learnings"`, multi-line `description`
- Body sections:
  1. Config reading: look for "Memory capture mode:" and "Memory silent capture budget:" lines in session context. If config lines are absent from session context (e.g., session-start hook not yet updated), default to ask-first mode with budget 5.
  2. Five trigger patterns with one concrete example each (per AC-11)
  3. Capture procedure: infer category/name/reasoning, call `store_memory` with `confidence="low"`
  4. Budget tracking: maintain explicit counter in reasoning, switch to ask-first at limit
  5. Mode behavior: ask-first (propose + wait), silent (capture + notify), off (do nothing)
  6. Fallback: CLI invocation with explicit `source="session-capture"`
  7. Invalid config value: default to `ask-first` if mode value unrecognized

**Verification:** File exists, frontmatter valid, all 5 trigger patterns present with examples, <500 lines, <5000 tokens.

### Step 7: Add session-start hint and config injection

**Component:** C4 (Session-Start Hint and Config Injection)
**File:** `plugins/iflow-dev/hooks/session-start.sh`
**Dependencies:** Step 4 (config keys exist)

**Changes:** In `build_context()`, after the "Available commands:" line (grep for `context+="\\nAvailable commands:"`) and before the `check_claude_md_plugin` block (grep for `check_claude_md_plugin`), append these 3 lines that extend the `context` string variable:
```bash
context+="\nTip: Use /remember <learning> to capture insights, or use the store_memory MCP tool directly."
context+="\nMemory capture mode: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_model_capture_mode" "ask-first")"
context+="\nMemory silent capture budget: $(read_local_md_field "$PROJECT_ROOT/.claude/iflow-dev.local.md" "memory_silent_capture_budget" "5")"
```

`read_local_md_field` is an existing function from `common.sh` (sourced at the top of session-start.sh) with signature `read_local_md_field "$file" "field_name" "default_value"`.

**Verification:** `cd plugins/iflow-dev && bash hooks/tests/test-hooks.sh` — hook tests pass. Manually verify build_context output includes tip and config lines.

### Step 8: Update documentation

**Files:** `README.md`, `README_FOR_DEV.md`, `plugins/iflow-dev/skills/workflow-state/SKILL.md`
**Dependencies:** Steps 5-6 (command and skill created)

**Changes:**
- `README.md`: Add `/remember` row to commands table, add `capturing-learnings` row to skills table, increment command and skill counts
- `README_FOR_DEV.md`: Add `/remember` and `capturing-learnings` to relevant tables, increment counts
- `plugins/iflow-dev/skills/workflow-state/SKILL.md`: Add `/remember` to available commands in the Workflow Map section if it lists commands

**Verification:** Documentation command/skill counts match actual counts in `plugins/iflow-dev/commands/` and `plugins/iflow-dev/skills/`.

## Dependency Graph

```
Step 1 (tests — RED)
  → Step 2 (core implementation — GREEN)
    → Step 3 (MCP wrapper)
      → Step 5 (/remember command)

Step 4 (config defaults) — independent, parallelizable with Steps 1-3
  → Step 6 (model guidance skill) — also depends on Steps 2-3
  → Step 7 (session-start hint)

Step 5 + Step 6 + Step 7
  → Step 8 (documentation)
```

## Parallelization Opportunities

- Steps 1-3 (C2+C6) and Step 4 (C5) can run in parallel — no shared files
- Steps 5, 6, 7 can run in parallel once their dependencies complete — different files
- Step 8 runs last (needs final component list)

## Risk Mitigations

- **TDD compliance:** Tests written first (Step 1, RED), then implementation (Step 2, GREEN). Existing tests remain unchanged and pass.
- **Existing test preservation:** Return format `"Stored: {name} (id: {id})"` unchanged for new entries. `TestDuplicateEntry.test_duplicate_increments_observation_count` only checks `observation_count`, not return string — passes unchanged.
- **get_entry ordering:** Existence check happens BEFORE upsert. Post-upsert `get_entry` used only for accurate observation_count in return message.
- **Confidence immutability on dedup:** `_update_existing()` does not update `confidence` — intentional per R3. First confidence wins.
- **CLI fallback differentiation:** Writer CLI always returns `"Stored: ..."` even for duplicates. Acceptable for v1 — fallback is rare.
- **Config type consistency:** DEFAULTS budget is integer `5`; `_coerce("5")` returns `int(5)`. Types match.

## Acceptance Criteria Coverage

| AC | Covered By | Key Verification |
|----|-----------|-----------------|
| AC-1 (user captures) | Step 5 | Command flow steps 1-8 |
| AC-2 (reject short) | Step 5 | Model-enforced ≥20 chars (standard command pattern, manual verification) |
| AC-3 (dedup) | Steps 2, 5 | Differentiated "Reinforced" return |
| AC-4 (ask-first mode) | Step 6 | Skill mode behavior section |
| AC-5 (silent mode) | Step 6 | Skill mode behavior section |
| AC-6 (budget) | Step 6 | Skill budget tracking section |
| AC-7 (off mode) | Step 6 | Skill mode behavior section |
| AC-8 (CLI fallback) | Step 5 | Command step 7 with writer CLI |
| AC-9 (confidence param) | Steps 1-3 | Tests verify default + explicit + invalid |
| AC-10 (session hint) | Step 7 | Exact tip text in build_context |
| AC-11 (trigger patterns) | Step 6 | 5 patterns with examples in skill |
| AC-12 (category inference) | Step 5 | Signal word rules in command |
| AC-13 (model fallback) | Step 6 | Skill fallback section |
