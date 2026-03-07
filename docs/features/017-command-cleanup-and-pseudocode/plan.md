# Plan: Command Cleanup and Pseudocode Removal

## Implementation Order

All changes are text-only edits to markdown files. No Python code, no MCP servers, no database changes. Files within each phase are independent; phasing is for implementer clarity.

### Phase 1: Core Removal (workflow-state/SKILL.md)

Single file, multiple section removals. Match by content, not line numbers.

**Step 1.1: Capture pre-edit line count**
- Run `wc -l` on `plugins/iflow/skills/workflow-state/SKILL.md` (FR-13)
- Record: expected ~363 lines

**Step 1.2: Remove Phase Sequence table and Workflow Map (FR-5)**
- Locate `## Phase Sequence` heading
- Remove the table (lines ~22-30) mapping phases to artifacts
- Remove the `## Workflow Map` section (lines ~32-49) — visual overview and prerequisites
- **Preserve all four elements:** `## Phase Sequence` heading, `The canonical workflow order:` intro, code fence delimiters, and the arrow one-liner
- Preserve blank lines between preserved elements and surrounding sections to maintain valid markdown structure
- Verify SC-5 anchor intact: heading + arrow line both present

**Step 1.3: Remove Transition Validation section (FR-3)**
- Locate `## Transition Validation` heading
- Remove entire section (~lines 51-93): Hard Prerequisites table, Soft Prerequisites AskUserQuestion, Normal Transitions
- Stop before `## Planned→Active Transition` (retained)

**Step 1.4: Remove validateTransition pseudocode (FR-1)**
- Locate `### Validation Logic` heading
- Remove heading + code fence + entire `validateTransition` function body (~34 lines, ~lines 123-156)

**Step 1.5: Remove Backward Transition Warning (FR-4)**
- Locate `### Backward Transition Warning` heading
- Remove entire section (~lines 158-175) including AskUserQuestion example

**Step 1.6: Remove Artifact Validation section (FR-6)**
- Locate `## Artifact Validation` heading
- Remove header, intro text, `### validateArtifact(path, type)` sub-header, Level 1-4 descriptions, type-specific sections table (~lines 177-200)

**Step 1.7: Remove validateArtifact pseudocode (FR-2)**
- Locate `function validateArtifact(path, type)` code block
- Remove the "Implementation" label, code fence, function body, and "Usage in Commands" section (~lines 201-237, ~36 lines)

**Step 1.8: Normalize section spacing**
- After all removals (Steps 1.2-1.7), ensure each remaining section is separated by exactly one blank line for consistent markdown formatting
- Do NOT apply formatting fixups between individual removal steps — wait until all removals complete

**Step 1.9: Update Planned→Active cross-reference (FR-11)**
- Locate line containing `proceed to \`validateTransition\` below`
- Replace with `proceed to workflow-transitions Step 1`

**Step 1.10: Verify preservation**
- Confirm `## Phase Sequence` heading present
- Confirm one-liner `brainstorm → specify → design → create-plan → create-tasks → implement → finish` present
- Confirm `## Planned→Active Transition` section intact
- Confirm `## State Schema` section intact

**Step 1.11: Early SC-5 test**
- Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5"` to verify Phase Sequence preservation before proceeding to Phase 2
- If fails: fix immediately — do not proceed with stale content in other files

**Dependencies:** None (first phase)
**Files:** `plugins/iflow/skills/workflow-state/SKILL.md`
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-11

### Phase 2: Table Replacements (secretary.md, create-specialist-team.md)

Two files with atomic replace-then-remove per Technical Decision 1.

**Step 2.1: Capture pre-edit line counts**
- Run `wc -l` on `plugins/iflow/commands/secretary.md` and `plugins/iflow/commands/create-specialist-team.md` (FR-13)

**Step 2.2: Remove Phase Progression Table from secretary.md (FR-7)**
- Locate `### Phase Progression Table` section (~lines 28-41)
- Remove the entire section (heading + table)

**Step 2.3: Update secretary.md site 1 — Orchestrate (FR-7)**
- Locate "Determine Next Command" (~line 336) containing `Use the Phase Progression Table above`
- Context: feature id/slug extracted via glob+parse before this line (lines ~320-321). **Verify** id and slug are available as discrete extracted values (not just embedded in a formatted report string) before the `get_phase` call. If only in report string, add explicit extraction from `.meta.json` fields
- Use the exact replacement text from spec FR-7 item 1 (lines 95-106) verbatim, maintaining current indentation level

**Step 2.4: Update secretary.md site 2 — Workflow Guardian (FR-7)**
- Locate "Workflow Guardian" (~line 520) containing `Determine next phase using the Phase Progression Table above`
- **Pre-requisite:** lines ~512-513 glob for `.meta.json` and filter by status, but do NOT explicitly extract id/slug as discrete values — only `lastCompletedPhase` is extracted at line ~519. **Add id/slug extraction** from the `.meta.json` read before the `get_phase` call (needed to construct `feature_type_id`)
- Use the exact replacement text from spec FR-7 item 1 verbatim (identical to Step 2.3)

**Step 2.5: Remove inline phase sequence from create-specialist-team.md Step 3 (FR-8 item 1)**
- Locate Step 3 (~lines 111-112): line 111 ends with colon introducing the sequence on line 112
- Replace lines 111-112 with the text from spec FR-8 item 1 (lines 141-147) verbatim, maintaining the current indentation level (6 spaces)
- The `get_phase` call happens AFTER glob-based feature discovery (id/slug already known)

**Step 2.6: Remove phase-to-command mapping table from create-specialist-team.md (FR-8 item 2)**
- Locate mapping table (~lines 180-191) with phase-to-command mappings
- Replace with inline mapping: `Phase names map 1:1 to commands: iflow:{phase-name}, except: finish → iflow:finish-feature`

**Step 2.7: Replace phase comparison logic in create-specialist-team.md (FR-8 item 3)**
- Locate phase comparison instructions (~lines 212-214) about preferring next phase
- Replace with MCP-based comparison using `get_phase` response `current_phase` field (per spec FR-8 item 3)

**Dependencies:** Independent from Phase 1 (different files)
**Files:** `plugins/iflow/commands/secretary.md`, `plugins/iflow/commands/create-specialist-team.md`
**FRs covered:** FR-7, FR-8

### Phase 3: Reference Updates (4 files)

Light edits — update references to removed constructs.

**Step 3.1: Capture pre-edit line counts**
- Run `wc -l` on `plugins/iflow/skills/workflow-transitions/SKILL.md`, `plugins/iflow/commands/implement.md`, `plugins/iflow/commands/create-tasks.md`, `plugins/iflow/commands/create-plan.md` (FR-13)

**Step 3.2: Update workflow-transitions Step 1 (FR-9)**
- Locate Step 1 (~lines 34-36) containing `Apply validateTransition logic`
- Replace 3-line block with updated text per spec FR-9:
  - "Check transition validity" heading
  - Read `.meta.json` state
  - Hard prerequisites validated by calling command before Step 1
  - Determine transition type: normal forward, backward, or skip
  - Command already stopped if blocked

**Step 3.3: Update implement.md hard prerequisite references (FR-10)**
- Locate `validateArtifact(path, "spec.md")` (~line 29)
- Replace with: `validate spec.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`
- Locate `validateArtifact(path, "tasks.md")` (~line 40)
- Replace with: `validate tasks.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`

**Step 3.4: Update create-tasks.md hard prerequisite reference (FR-10)**
- Locate `validateArtifact(path, "plan.md")` (~line 16)
- Replace with: `validate plan.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`

**Step 3.5: Update create-plan.md hard prerequisite reference (FR-10)**
- Locate `validateArtifact(path, "design.md")` (~line 16)
- Replace with: `validate design.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`

**Dependencies:** Independent from Phase 2 (different files)
**Files:** `plugins/iflow/skills/workflow-transitions/SKILL.md`, `plugins/iflow/commands/implement.md`, `plugins/iflow/commands/create-tasks.md`, `plugins/iflow/commands/create-plan.md`
**FRs covered:** FR-9, FR-10

### Phase 4: Documentation and Verification

**Step 4.1: Update CLAUDE.md (FR-14)**
- Locate Documentation Sync table row referencing `Workflow Map section (if phase sequence or prerequisites change)`
- Replace with `Phase Sequence one-liner (if phase names change)`

**Step 4.2: Update .claude/hookify.docs-sync.local.md**
- Locate reference to `Workflow Map`
- Replace with `Phase Sequence one-liner`

**Step 4.3: Update docs/dev_guides/templates/command-template.md**
- Locate line 16: `- Apply validateTransition logic for target phase`
- Replace with: `- Check transition validity by following workflow-transitions Step 1 for target phase`

**Step 4.4: Verify docs/knowledge-bank/patterns.md (verify-only)**
- Confirm `validateTransition` reference is historical context ("Avoided modifying core validateTransition logic")
- No change needed — this is a retrospective entry, not active instruction

**Step 4.5: Verify yolo-stop.sh (FR-12)**
- Confirm primary path uses `PHASE_SEQUENCE` from `transition_gate.constants`
- Confirm `phase_map` exists only in `except` block (graceful degradation fallback)
- No changes needed

**Step 4.6: Measure line counts (FR-13)**
- Run `wc -l` on all 9 editable target files
- Compute per-file and aggregate reduction
- Estimate token savings (1 line ≈ 10-15 tokens)

**Step 4.7: Run grep validation (AC-1 through AC-15)**
- AC-1: `grep "validateTransition\|function validateTransition" workflow-state/SKILL.md` → zero matches
- AC-2: `grep "validateArtifact\|function validateArtifact" workflow-state/SKILL.md` → zero matches
- AC-3: `grep "## Transition Validation" workflow-state/SKILL.md` → zero matches
- AC-4: `grep "## Workflow Map" workflow-state/SKILL.md` → zero matches
- AC-5: `grep "brainstorm → specify → design" workflow-state/SKILL.md` → exactly 1 match
- AC-6: `grep "Phase Progression Table" secretary.md` → zero matches
- AC-7: `grep "Phase-to-command mapping\|Phase name (.meta.json)" create-specialist-team.md` → zero matches; `grep "brainstorm → specify → design" create-specialist-team.md` → zero matches in Step 3
- AC-8: `./validate.sh` → passes
- AC-9: SC-5 test → passes
- AC-10: `grep "validateArtifact(" implement.md create-tasks.md create-plan.md` → zero matches
- AC-11: workflow-transitions Step 1 references no removed functions
- AC-12: `grep "get_phase" secretary.md` → matches in both sites; `grep "lastCompletedPhase" secretary.md` → match (fallback)
- AC-13: Line counts documented
- AC-14: `grep "PHASE_SEQUENCE" plugins/iflow/hooks/yolo-stop.sh` → match (primary path)
- AC-15: `grep "validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map" CLAUDE.md README.md README_FOR_DEV.md` → zero matches

**Step 4.8: Run broad codebase grep**
- `grep -rn 'validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map' . --include='*.md' | grep -v docs/features/ | grep -v docs/projects/ | grep -v docs/brainstorms/`
- Expected hit: `docs/knowledge-bank/patterns.md` (historical context, acceptable)
- Note: other feature docs (e.g., 025, 028) may reference `Workflow Map` but are historical planning snapshots — no update needed
- Any other hits in active files: investigate and update

**Step 4.9: Run test suite**
- `./validate.sh`
- `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5 or sc_5 or skill_md"`
- Both must pass

**Step 4.10: Smoke test (per design Verification Contracts)**
- Run `/iflow:specify` on a scratch/test feature
- Verify: no reference to `validateTransition` in workflow output, phase starts successfully, no errors about missing functions
- If fails: investigate and fix before proceeding

**Step 4.11: Update CHANGELOG.md (FR-14)**
- Add entry under `[Unreleased]` documenting pseudocode/table removal
- Include aggregate line reduction and token savings estimate

**Dependencies:** After Phases 1-3 (verifies their work)
**Files:** `CLAUDE.md`, `.claude/hookify.docs-sync.local.md`, `docs/dev_guides/templates/command-template.md`, `docs/knowledge-bank/patterns.md` (verify), `CHANGELOG.md`
**FRs covered:** FR-12, FR-13, FR-14

## Task Sizing Estimate

| Phase | Steps | Est. Complexity |
|-------|-------|-----------------|
| Phase 1 | 11 steps | Medium — many sections but single file, content-match removal + early test |
| Phase 2 | 7 steps | Medium — atomic replace-then-remove, two files |
| Phase 3 | 5 steps | Light — small text replacements, four files |
| Phase 4 | 11 steps | Light-Medium — documentation updates + validation sweep + smoke test |

Total: ~34 steps across 4 phases. All text-only edits.

## Risks and Mitigations

1. **SC-5 test failure** — Mitigated by Step 1.10 preservation check, Step 1.11 early SC-5 test, and Step 4.9 test run
2. **Secretary routing broken** — Mitigated by atomic replace-then-remove (Steps 2.2-2.4)
3. **Stale references missed** — Mitigated by broad grep (Step 4.8) and AC-1 through AC-15
4. **Line number drift** — Mitigated by Technical Decision 4 (match by content, not line numbers)
