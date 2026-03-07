# Tasks: Large Command Migration — workflow-transitions dual-write

## Phase 1: Insert transition_phase block into validateAndSetup Step 4

### Task 1.1: Read design.md prose template and SKILL.md target location
- [ ] Read `docs/features/016-large-command-migration-specif/design.md` lines 195-211 (Prose Template 1: transition_phase block)
- [ ] Read `plugins/iflow/skills/workflow-transitions/SKILL.md` and identify the exact insertion point: immediately after the Step 4 `.meta.json` update code block (the `}` closing the JSON example on line 117), before Step 5: Inject Project Context (line 119)
- **Done when:** Both files read, insertion point confirmed between lines 117 and 119

### Task 1.2: Insert transition_phase prose block into SKILL.md
- [ ] Insert the "Sync to workflow DB (best-effort)" block from design.md Prose Template 1 into SKILL.md, immediately after the closing `}` of the Step 4 `.meta.json` update JSON code block (identified in Task 1.1), before the blank line preceding Step 5: Inject Project Context
- [ ] The inserted block must:
  - Construct `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` `id` and `slug` fields (available from the `.meta.json` read in validateAndSetup Step 1 — extract directly; unlike commitAndComplete Step 1, no `entity_type_id` variable is pre-constructed)
  - Call `transition_phase(feature_type_id, "{phaseName}")`
  - Include `yolo_active=true` when `[YOLO_MODE]` is active
  - On success (`transitioned: true` AND `degraded: false`): silent, proceed
  - On any failure: warn with `Note: Workflow DB sync skipped — {reason}. State will reconcile on next reconcile_apply run.` — do NOT block
  - Include partial-phase resume note
- **Done when:** Block inserted, no existing lines modified

### Task 1.3: Verify Phase 1 insertion
- [ ] Read the modified SKILL.md and confirm the transition_phase block appears between Step 4's `.meta.json` update and Step 5: Inject Project Context
- [ ] Confirm no existing content was modified or displaced
- **Done when:** Insertion verified in correct location, file structure intact

## Phase 2: Insert complete_phase block into commitAndComplete Step 2

> Depends on: Phase 1 (all tasks)

### Task 2.1: Identify commitAndComplete Step 2 insertion point
- [ ] Read the modified SKILL.md and locate the commitAndComplete Step 2 `.meta.json` update code block (the `}` closing the JSON example, originally at line 201 but shifted by Phase 1 insertion)
- **Note:** The commitAndComplete Step 2 closing `}` is the last substantive line of the file (after Phase 1 shift). The complete_phase block will be appended as new content at end of file — no existing content follows the `}`
- **Done when:** Insertion point identified after Step 2's JSON closing brace, confirmed no content follows it

### Task 2.2: Insert complete_phase prose block into SKILL.md
- [ ] Insert the "Sync to workflow DB (best-effort)" block from design.md Prose Template 2 into SKILL.md, immediately after the commitAndComplete Step 2 `.meta.json` update code block
- [ ] The inserted block must:
  - Construct `feature_type_id` as `"feature:{id}-{slug}"` from `.meta.json` fields
  - Call `complete_phase(feature_type_id, "{phaseName}")`
  - On success: silent, proceed
  - On any failure: warn with standard format — do NOT block
- **Done when:** Block inserted, no existing lines modified (except those added in Phase 1)

### Task 2.3: Verify Phase 2 insertion
- [ ] Read the modified SKILL.md and confirm the complete_phase block appears after commitAndComplete Step 2's `.meta.json` update block
- [ ] Confirm Phase 1's transition_phase block is still intact and correctly positioned
- **Done when:** Both insertions verified, file structure intact

## Phase 3: End-to-end verification

> Depends on: Phase 2 (all tasks)

### Task 3.1: Structural and content cross-check
- [ ] Read the complete modified SKILL.md
- [ ] Verify structural integrity: both new blocks properly nested under parent steps, headings consistent, no displaced content
- [ ] Cross-check against spec acceptance criteria:
  - AC-1: `transition_phase` call in validateAndSetup Step 4, after `.meta.json` started write
  - AC-2: `complete_phase` call in commitAndComplete Step 2, after `.meta.json` completed write
  - AC-3/AC-4: Both blocks use warn-and-continue, never block
  - AC-5: `yolo_active` parameter set when `[YOLO_MODE]` active
  - AC-8: `feature_type_id` format is `"feature:{id}-{slug}"`
  - NFR-3: Warning format matches `"Note: Workflow DB sync skipped — {reason}..."`
  - NFR-5: Dual-write ordering is `.meta.json` FIRST, MCP SECOND
  - AC-10: transition_phase block has no stop/block/halt language on rejection
- **Note:** AC-6, AC-7, AC-9, AC-11 require live execution and are out of scope for this static verification — they are covered by the spec Verification Strategy (manual end-to-end runs)
- **Done when:** All listed checks pass

### Task 3.2: No-modification check via git diff
- [ ] Run `git diff plugins/iflow/skills/workflow-transitions/SKILL.md`
- [ ] Confirm the diff shows only additions (lines prefixed with `+`) — zero existing lines changed (no `-` prefixed lines except the `---` header)
- **Done when:** Diff confirms pure additions only
