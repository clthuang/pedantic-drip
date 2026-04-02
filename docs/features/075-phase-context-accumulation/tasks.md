# Tasks: Phase Context Accumulation

**Feature:** 075-phase-context-accumulation
**Plan:** plan.md
**Created:** 2026-04-02

## Stage 1: Storage Infrastructure

### Task 1.1: Write test for validate_metadata accepting phase_summaries (AC-11) [TDD: test first]
**File:** `plugins/pd/hooks/lib/entity_registry/test_metadata.py` (or appropriate test file)
**Change:** Add test asserting `validate_metadata("feature", {"phase_summaries": [{"phase": "specify", "timestamp": "2026-04-02T08:00:00Z", "outcome": "Done", "artifacts_produced": ["spec.md"], "key_decisions": "Chose X", "reviewer_feedback_summary": "LGTM", "rework_trigger": None}]})` returns no warnings for the `phase_summaries` key. Run test — expect failure (key not in schema yet).
**Time:** 5 min
**Done:** Test written and fails (red phase)
**Depends on:** none

### Task 1.2: Add phase_summaries to METADATA_SCHEMAS (C6) [TDD: make green]
**File:** `plugins/pd/hooks/lib/entity_registry/metadata.py`
**Change:** Add `"phase_summaries": list,` to `METADATA_SCHEMAS['feature']` dict (after `"weight": str,` at line 44). Also add `"backward_context": dict,`, `"backward_return_target": str,`, `"backward_history": list,` to eliminate pre-existing schema warnings (opportunistic fix). Run test from Task 1.1 — expect pass.
**Time:** 5 min
**Done:** METADATA_SCHEMAS['feature'] contains `"phase_summaries": list` and backward_* keys; Task 1.1 test passes
**Depends on:** Task 1.1

### Task 2.1: Write test for _project_meta_json phase_summaries projection (AC-3, AC-10) [TDD: test first]
**File:** `plugins/pd/mcp/test_workflow_state_server.py`
**Change:** Add two tests:
1. When entity metadata contains `phase_summaries` with 2 entries, `_project_meta_json` output includes `"phase_summaries": [{...}, {...}]`
2. When entity metadata has no `phase_summaries`, the key is absent from .meta.json output (AC-10 zero behavior change)
Run tests — expect test 1 fails (projection not implemented), test 2 passes (key already absent).
**Time:** 10 min
**Done:** Tests written; test 1 fails (red phase), test 2 passes
**Depends on:** none

### Task 2.2: Add phase_summaries projection to _project_meta_json (C3) [TDD: make green]
**File:** `plugins/pd/mcp/workflow_state_server.py`
**Change:** After the backward travel fields block (line 388), before the atomic write (line 390), add:
```python
# Phase summaries (feature 075)
if metadata.get("phase_summaries"):
    meta["phase_summaries"] = metadata["phase_summaries"]
```
Run tests from Task 2.1 — expect both pass.
**Time:** 5 min
**Done:** `_project_meta_json` includes `phase_summaries` in .meta.json output when present in entity metadata; Task 2.1 tests pass
**Depends on:** Task 2.1

## Stage 2: Summary Generation

### Task 3.1: Add Step 3a heading and position to commitAndComplete (C1)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** After existing Step 3 (Phase Summary output) and before existing Step 3b (Forward Re-Run Check), insert a new `### Step 3a: Store Phase Summary (best-effort)` section. Start with the purpose statement: construct a structured summary dict from Step 3 output and persist it via update_entity.
**Time:** 5 min
**Done:** Step 3a heading exists between Step 3 and Step 3b
**Depends on:** none

### Task 3.2: Define summary dict schema in Step 3a
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** Within Step 3a, add the summary dict construction instructions with all 7 fields:
- `phase`: from phaseName parameter
- `timestamp`: current UTC ISO 8601 (matching _iso_now() format)
- `outcome`: from Step 3 outcome decision table
- `artifacts_produced`: `[basename(f) for f in artifacts[]]`
- `key_decisions`: free-text paragraph of key choices
- `reviewer_feedback_summary`: brief summary of reviewer feedback across iterations
- `rework_trigger`: if backward_context existed at phase start, summarize it; else null
**Time:** 10 min
**Done:** All 7 fields documented with source mapping
**Depends on:** Task 3.1

### Task 3.3: Add truncation instructions to Step 3a (AC-8)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** Add truncation instructions within Step 3a:
- Keep each text field under 300 chars
- If total serialized JSON exceeds 2000 chars, truncate `reviewer_feedback_summary` first (min 100 chars), then `key_decisions`, appending "..."
- If still over: truncate `artifacts_produced` (remove tail entries), then `outcome`
**Time:** 5 min
**Done:** Truncation order and limits documented in Step 3a
**Depends on:** Task 3.2

### Task 3.4: Add update_entity call and error handling to Step 3a (AC-2)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** Add the append + update_entity instructions:
1. Read `phase_summaries` from .meta.json loaded at phase start — no re-read needed due to single-writer guarantee per feature (design.md:358)
2. Append new summary dict
3. Call `update_entity(type_id=feature_type_id, metadata={"phase_summaries": updated_list})` — pass ONLY phase_summaries key (shallow merge preserves other keys)
4. Error handling: if update_entity fails, log warning "Phase summary storage failed: {error}" and proceed to Step 3b. Phase completion already succeeded in Step 2.
**Time:** 10 min
**Done:** Complete Step 3a with construction, truncation, storage, and error handling
**Depends on:** Task 3.3

### Task 4.1: Confirm update_entity shallow-merge test coverage (C2)
**File:** `plugins/pd/mcp/test_workflow_state_server.py`
**Change:** Run `grep -n 'update_entity.*metadata' plugins/pd/mcp/test_workflow_state_server.py` to check if a shallow-merge test already exists. If found, record the test name in this task's notes. If not found, write a test: register entity with `metadata={'a': 1}`, call `update_entity` with `metadata={'b': 2}`, assert entity metadata has both keys `a` and `b`. Done when shallow-merge test confirmed or written.
**Time:** 5 min
**Done:** Shallow-merge test confirmed (test name noted) or new test written and passing
**Depends on:** Tasks 1.2, 2.2

## Stage 3: Summary Injection

### Task 5.1: Add backward transition detection to validateAndSetup Step 1b (C4, I4)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** In Step 1b, add backward transition detection logic:
- Check if `phases[target_phase].completed` exists in .meta.json (loaded in Step 1)
- If it exists, this is a backward transition (re-entry into a completed phase)
- This detection is independent of `backward_context` presence (covers both reviewer-initiated and user-initiated re-entry per TD-4)
**Time:** 10 min
**Done:** Detection logic documented in Step 1b
**Depends on:** Tasks 3.1-3.4

### Task 5.2: Add phase_summaries reading and trimming to Step 1b (AC-9)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** When backward transition detected, add instructions to:
1. Read `phase_summaries` from .meta.json
2. Group entries by phase name
3. Keep only last 2 entries per phase (by list position — append order)
4. All entries remain in metadata storage; trimming is display-only
**Time:** 5 min
**Done:** Trimming logic documented in Step 1b
**Depends on:** Task 5.1

### Task 5.3a: Enumerate all Backward Travel Context references (TD-7)
**File:** N/A — enumeration task
**Change:** Run `grep -rn "Backward Travel Context" plugins/pd/` and record every file and line number that references the old heading. This list drives Task 5.3b.
**Time:** 5 min
**Done:** Full list of references captured (file paths + line numbers noted)
**Depends on:** Task 5.2

### Task 5.3b: Replace Backward Travel Context with unified ## Phase Context format in SKILL.md (TD-7, I5)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** Using the reference list from Task 5.3a, replace the standalone `## Backward Travel Context` block in Step 1b with the unified `## Phase Context` format:
- `### Reviewer Referral` sub-section: existing backward_context content (only if backward_context exists)
- `### Prior Phase Summaries` sub-section: formatted summaries (only if phase_summaries has entries)
- If both absent: no `## Phase Context` block at all
- Per-entry format: `**{phase}** ({timestamp}): {outcome}` with key_decisions, artifacts, and rework_trigger (if non-null)
- `reviewer_feedback_summary` omitted from injection to save tokens
- Existing backward_context clearing behavior (Step 1b item 4) is unchanged
- Update any remaining references found in 5.3a
**Time:** 10 min
**Done:** `grep -rn "Backward Travel Context" plugins/pd/` returns no matches; new `## Phase Context` format is present in SKILL.md Step 1b
**Depends on:** Task 5.3a

### Task 6.1: Update specify.md — add Phase Context to reviewer dispatches (C5)
**File:** `plugins/pd/commands/specify.md`
**Change:** Use the injection template from design I6. Add conditional Phase Context injection template to spec-reviewer and phase-reviewer dispatch prompts:
- Check if `phases[current_phase]` has `completed` timestamp in .meta.json
- If yes: read backward_context and phase_summaries, construct `## Phase Context` block per I5 format
- Insert after `## Relevant Engineering Memory`, before review instructions / Return JSON block
- If no completed timestamp: skip injection entirely
**Time:** 10 min
**Done:** Both reviewer dispatches in specify.md include conditional Phase Context
**Depends on:** Tasks 5.1-5.3b

### Task 6.2: Update design.md — add Phase Context to reviewer dispatches (C5)
**File:** `plugins/pd/commands/design.md`
**Change:** Same injection template as Task 6.1, applied to design-reviewer and phase-reviewer dispatch prompts.
**Time:** 10 min
**Done:** Both reviewer dispatches in design.md include conditional Phase Context
**Depends on:** Tasks 5.1-5.3b

### Task 6.3: Update create-plan.md — add Phase Context to reviewer dispatches (C5)
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Same injection template as Task 6.1, applied to plan-reviewer, task-reviewer, and combined-reviewer dispatch prompts.
**Time:** 10 min
**Done:** All 3 reviewer dispatches in create-plan.md include conditional Phase Context
**Depends on:** Tasks 5.1-5.3b

### Task 6.4: Update implement.md — add Phase Context to reviewer dispatches (C5)
**File:** `plugins/pd/commands/implement.md`
**Change:** Same injection template as Task 6.1, applied to relevance-verifier, code-reviewer, and integration-reviewer dispatch prompts.
**Time:** 10 min
**Done:** All 3 reviewer dispatches in implement.md include conditional Phase Context
**Depends on:** Tasks 5.1-5.3b

### Task 6.5: Verify Phase Context injection blocks present in all command files
**File:** N/A — verification task
**Change:** Run `grep -c '## Phase Context' plugins/pd/commands/specify.md plugins/pd/commands/design.md plugins/pd/commands/create-plan.md plugins/pd/commands/implement.md`. Verify output shows non-zero counts for all four files (specify: 2, design: 2, create-plan: 3, implement: 3 — matching the dispatch counts in design.md I6 table).
**Time:** 5 min
**Done:** All four command files report expected match counts; no file shows 0
**Depends on:** Tasks 6.1, 6.2, 6.3, 6.4

## Stage 4: Testing & Verification

### Task 7.1: Write integration test for update_entity phase_summaries append (AC-1)
**File:** `plugins/pd/mcp/test_workflow_state_server.py` or `plugins/pd/hooks/lib/entity_registry/test_database.py`
**Change:** Test that calling `update_entity` with `metadata={"phase_summaries": [entry1]}` then again with `metadata={"phase_summaries": [entry1, entry2]}` results in entity metadata containing both entries. Verify prior entries are preserved (not overwritten).
**Time:** 10 min
**Done:** Test passes, append behavior confirmed
**Depends on:** Tasks 1.2, 2.2

### Task 7.2: Verify Step 3a error-handling prose in SKILL.md (AC-2)
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** After Task 3.4 is complete, run `grep -n 'Phase summary storage failed' plugins/pd/skills/workflow-transitions/SKILL.md`. This verifies that the try/except equivalent prose and warning message text are present in the Step 3a instructions (the LLM-readable instructions, not Python code).
**Time:** 5 min
**Done:** `grep` returns at least one match — the warning text "Phase summary storage failed:" is present in SKILL.md Step 3a
**Depends on:** Task 3.4

### Task 7.3: Write test for zero behavior change without summaries (AC-10)
**File:** `plugins/pd/mcp/test_workflow_state_server.py`
**Change:** Test that a feature with no `phase_summaries` in metadata produces no `phase_summaries` key in .meta.json and no errors/warnings from `_project_meta_json`.
**Time:** 5 min
**Done:** Test passes
**Depends on:** Task 2.2

### Task 8.1: Run full regression test suite
**Change:** Run all affected test suites:
```bash
# Workflow state server (272 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v

# Entity registry (940+ tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v

# Workflow engine (309 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v

# Transition gate (257 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v
```
**Time:** 15 min
**Done:** All test suites pass with zero regressions
**Depends on:** Tasks 7.1-7.3

## Task Dependencies

```
1.1 → 1.2  (TDD: test first, then schema change)
2.1 → 2.2  (TDD: test first, then projection)
Tasks 1.x, 2.x, and 3.x can run in parallel (different files, no code dependencies)
3.1 → 3.2 → 3.3 → 3.4
1.2 + 2.2 → 4.1
3.4 → 7.2  (7.2 verifies Step 3a warning text is present)
Real constraint: 2.2 before 5.1 (injection reads projected phase_summaries)
3.4 → 5.1 → 5.2 → 5.3a → 5.3b
5.3b → 6.1, 6.2, 6.3, 6.4  (parallel)
6.1 + 6.2 + 6.3 + 6.4 → 6.5
1.2 + 2.2 → 7.1
All implementation → 7.1, 7.2, 7.3 → 8.1
```

## Summary

| Stage | Tasks | Est. Time | Type |
|-------|-------|-----------|------|
| Stage 1: Infrastructure | 1.1, 1.2, 2.1, 2.2 | 25 min | TDD: tests first, then Python code |
| Stage 2: Generation | 3.1-3.4, 4.1 | 35 min | SKILL.md instructions + verification |
| Stage 3: Injection | 5.1-5.2, 5.3a, 5.3b, 6.1-6.5 | 80 min | SKILL.md + command file instructions + verification |
| Stage 4: Testing | 7.1-7.3, 8.1 | 30 min | Integration tests + regression |
| **Total** | **21 tasks** | **~2.8 hours** | |
