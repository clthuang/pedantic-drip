# Plan: Large Command Migration — workflow-transitions dual-write

## Overview

Single-file migration: insert two MCP dual-write blocks into `plugins/iflow/skills/workflow-transitions/SKILL.md`. No other files modified.

## Implementation Order

### Phase 1: Insert transition_phase block into validateAndSetup Step 4

**Target:** `plugins/iflow/skills/workflow-transitions/SKILL.md`, immediately after the Step 4 `.meta.json` update code block (the `}` closing the JSON example), before Step 5: Inject Project Context.

**Action:** Insert the transition_phase prose template from design.md (Interface Prose Template 1) as a new sub-section under Step 4, immediately after the `.meta.json` update block.

**Insertion content:** The "Sync to workflow DB (best-effort)" block for `transition_phase`, which:
1. Constructs `feature_type_id` as `"feature:{id}-{slug}"` from `id` and `slug` fields in the `.meta.json` state read during validateAndSetup Step 1 (Validate Transition). Note: unlike commitAndComplete Step 1, validateAndSetup does not pre-construct `entity_type_id` — extract `id` and `slug` directly from the `.meta.json` state
2. Calls `transition_phase(feature_type_id, "{phaseName}")`
3. Passes `yolo_active=true` when `[YOLO_MODE]` is active
4. On success (`transitioned: true` AND `degraded: false`): silent, proceed
5. On any failure (MCP unavailable, `error: true`, `transitioned: false`, `degraded: true`, non-JSON response): warn with standard format, do NOT block
6. Includes partial-phase resume note (Step 3 re-entry handling)

**Dependencies:** None. This is the first edit.

**Verification:** Read the modified file and confirm the block appears between Step 4's `.meta.json` update and Step 5: Inject Project Context.

### Phase 2: Insert complete_phase block into commitAndComplete Step 2

**Target:** `plugins/iflow/skills/workflow-transitions/SKILL.md`, immediately after the commitAndComplete Step 2 `.meta.json` update code block (the `}` closing the JSON example).

**Action:** Insert the complete_phase prose template from design.md (Interface Prose Template 2) as a new sub-section under Step 2, immediately after the `.meta.json` update block.

**Insertion content:** The "Sync to workflow DB (best-effort)" block for `complete_phase`, which:
1. Constructs `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` fields (same value as validateAndSetup Step 4 and `entity_type_id` in Step 1 frontmatter injection)
2. Calls `complete_phase(feature_type_id, "{phaseName}")`
3. On success: silent, proceed
4. On any failure (MCP unavailable, `error: true`, non-JSON response): warn with standard format, do NOT block

**Dependencies:** Phase 1 must complete first so Phase 2 can be verified against the already-modified file structure, ensuring no insertion conflicts.

**Verification:** Read the modified file and confirm the block appears after Step 2's `.meta.json` update block and before the end of the file.

### Phase 3: End-to-end verification

**Action:** Verify the complete modified SKILL.md for correctness:

1. **Structural check:** Confirm the file has no broken markdown structure — both new blocks are properly nested under their parent steps, headings are consistent, and no existing content was modified or displaced.

2. **Content cross-check against spec:**
   - AC-1: `transition_phase` call present in validateAndSetup Step 4, after `.meta.json` started write ✓
   - AC-2: `complete_phase` call present in commitAndComplete Step 2, after `.meta.json` completed write ✓
   - AC-3/AC-4: Both blocks use warn-and-continue pattern, never block ✓
   - AC-5: `yolo_active` parameter set when `[YOLO_MODE]` active ✓
   - AC-8: `feature_type_id` format is `"feature:{id}-{slug}"` ✓
   - NFR-3: Warning format matches `"Note: Workflow DB sync skipped — {reason}..."` ✓
   - NFR-5: Dual-write ordering is `.meta.json` FIRST, MCP SECOND ✓
   - AC-10: Verify transition_phase block contains no stop/block/halt language on rejection — only warn-and-continue ✓

3. **No-modification check:** Run `git diff plugins/iflow/skills/workflow-transitions/SKILL.md` and confirm the diff shows only additions (lines prefixed with `+`) — zero existing lines changed (no `-` prefixed lines except the `---` header).

**Dependencies:** Phases 1 and 2.

## Risk Mitigations

- **Insertion ordering:** Both phases use context-based targeting (not absolute line numbers), so they are resilient to content shifts. Phase 2 depends on Phase 1 for structural verification, not mechanical line counting.
- **Prose interpretation variance (R5):** Both blocks use explicit ordering language ("After the `.meta.json` update above") and numbered steps to minimize Claude misinterpretation.
- **Existing behavior preservation:** Zero existing lines modified. Both insertions are additive sub-sections under existing steps.
- **Rollback:** `git checkout -- plugins/iflow/skills/workflow-transitions/SKILL.md` reverts the single-file change if needed.
