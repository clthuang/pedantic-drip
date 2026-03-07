# Tasks: Command Cleanup and Pseudocode Removal

All tasks are text-only markdown edits. No Python code, no MCP servers, no database changes.
Phases 1, 2, and 3 are fully independent (different files) and can execute in parallel.
Phase 4 depends on Phases 1-3 completion.

## Phase 1: Core Removal (workflow-state/SKILL.md)

### Task 1.1: Capture pre-edit baselines for all target files
- [ ] Run `wc -l` on all 10 editable target files and record results in task execution output (stdout):
  1. `plugins/iflow/skills/workflow-state/SKILL.md` (~363 lines)
  2. `plugins/iflow/commands/secretary.md`
  3. `plugins/iflow/commands/create-specialist-team.md`
  4. `plugins/iflow/skills/workflow-transitions/SKILL.md`
  5. `plugins/iflow/commands/implement.md`
  6. `plugins/iflow/commands/create-tasks.md`
  7. `plugins/iflow/commands/create-plan.md`
  8. `CLAUDE.md`
  9. `.claude/hookify.docs-sync.local.md`
  10. `docs/dev_guides/templates/command-template.md`

**Done when:** `wc -l` on all 10 files returns numeric output with no errors. Results are recorded in task execution output.

### Task 1.2: Remove Phase Sequence table and Workflow Map from SKILL.md
- [ ] Locate `## Phase Sequence` heading
- [ ] Remove the table (~lines 22-30) mapping phases to artifacts
- [ ] Remove the `## Workflow Map` section (~lines 32-49) — visual overview and prerequisites
- [ ] Preserve all four elements: `## Phase Sequence` heading, `The canonical workflow order:` intro, code fence delimiters, and the arrow one-liner
- [ ] Verify SC-5 anchor intact: heading + arrow line both present after removal

**Done when:** `grep "## Workflow Map" SKILL.md` returns zero matches. `## Phase Sequence` heading and arrow one-liner both present.

### Task 1.3: Remove Transition Validation section
- [ ] Locate `## Transition Validation` heading
- [ ] Remove entire section (~lines 51-93): Hard Prerequisites table, Soft Prerequisites AskUserQuestion, Normal Transitions
- [ ] Stop before `## Planned→Active Transition` (retained)

**Done when:** `grep "## Transition Validation" SKILL.md` returns zero matches. `grep "## Planned→Active Transition" SKILL.md` returns one match.

### Task 1.4: Remove validateTransition pseudocode
- [ ] Locate `### Validation Logic` heading
- [ ] Remove heading + code fence + entire `validateTransition` function body (~34 lines, ~lines 123-156)

**Done when:** `grep "validateTransition\|function validateTransition" SKILL.md` returns zero matches.

### Task 1.5: Remove Backward Transition Warning
- [ ] Locate `### Backward Transition Warning` heading
- [ ] Remove entire section (~lines 158-175) including AskUserQuestion example

**Done when:** `grep "Backward Transition Warning" SKILL.md` returns zero matches.

### Task 1.6: Remove Artifact Validation section and validateArtifact pseudocode
- [ ] Locate `## Artifact Validation` heading
- [ ] Remove header, intro text, `### validateArtifact(path, type)` sub-header, Level 1-4 descriptions, type-specific sections table (~lines 177-200)
- [ ] Locate `function validateArtifact(path, type)` code block
- [ ] Remove the "Implementation" label, code fence, function body, and "Usage in Commands" section (~lines 201-237, ~36 lines)

**Done when:** `grep "validateArtifact\|function validateArtifact" SKILL.md` returns zero matches. `grep "## Artifact Validation" SKILL.md` returns zero matches.

### Task 1.7: Normalize spacing and update cross-reference in SKILL.md
- [ ] Ensure each remaining section is separated by exactly one blank line — run `grep -n '^$' SKILL.md | awk -F: 'prev+1==$1{print NR": consecutive blank at line "$1} {prev=$1}'` to find consecutive blank lines; fix any found
- [ ] Locate line containing `proceed to \`validateTransition\` below`
- [ ] Replace with `proceed to workflow-transitions Step 1`

**Done when:** `grep "proceed to workflow-transitions Step 1" SKILL.md` returns one match. Consecutive blank line check returns zero hits.

### Task 1.8: Verify SKILL.md preservation after Phase 1 edits
- [ ] `grep "## Phase Sequence" SKILL.md` → one match
- [ ] `grep "brainstorm → specify → design → create-plan → create-tasks → implement → finish" SKILL.md` → one match
- [ ] `grep "## Planned→Active Transition" SKILL.md` → one match
- [ ] `grep "## State Schema" SKILL.md` → one match

**Done when:** All four grep checks return exactly one match each.

### Task 1.9: Run early SC-5 test
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5"`
- [ ] If fails: fix immediately before proceeding

**Done when:** SC-5 test passes.

**Parallel group:** Tasks 1.2-1.6 are sequential (same file, content-match removal order matters). Task 1.7 depends on 1.2-1.6. Task 1.8 depends on 1.7. Task 1.9 depends on 1.8. Task 1.1 is independent (baseline capture).

## Phase 2: Table Replacements (secretary.md, create-specialist-team.md)

### Task 2.1: Remove Phase Progression Table and update secretary.md site 1 — Orchestrate
- [ ] Locate `### Phase Progression Table` section (~lines 28-41) in secretary.md
- [ ] Remove the entire section (heading + table)
- [ ] Locate "Determine Next Command" (~line 336) containing `Use the Phase Progression Table above`
- [ ] Verify id and slug are available as discrete extracted values before the `get_phase` call (not just embedded in a formatted report string); if only in report string, add explicit extraction from `.meta.json` fields
- [ ] Replace the Phase Progression Table reference with the following verbatim text (maintain current indentation level):
  ```
  Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `id` and `slug` fields
  already extracted from `.meta.json`.
  Call `get_phase(feature_type_id)`. Parse the JSON response object.
  - If `current_phase` is non-null: the feature is mid-phase. Route to `iflow:{current_phase}`
    (or `iflow:finish-feature` when `current_phase` is `finish`).
  - If `current_phase` is null: the feature is between phases. Use `last_completed_phase`
    to determine the next phase from the canonical sequence:
    brainstorm → specify → design → create-plan → create-tasks → implement → finish.
    Route to the command for that next phase.
  If MCP unavailable, fall back to `.meta.json` `lastCompletedPhase` (camelCase)
  and apply the same canonical-sequence logic.
  ```

**Done when:** `grep "Phase Progression Table" secretary.md` returns zero matches. `grep -A5 "Determine Next Command" secretary.md | grep "get_phase"` returns a match (confirms replacement inserted at Orchestrate site).

**Note:** Table removal and site 1 replacement are done atomically per Technical Decision 1 (within-file atomic replace-then-remove). Complete both operations before any smoke test.

### Task 2.2: Update secretary.md site 2 — Workflow Guardian
- [ ] Locate "Workflow Guardian" (~line 520) containing `Determine next phase using the Phase Progression Table above`
- [ ] Lines ~512-513 glob for `.meta.json` but do NOT extract id/slug — add id/slug extraction from the `.meta.json` read before the `get_phase` call. Use the same extraction pattern as site 1 (Task 2.1): extract `id` and `slug` fields from the `.meta.json` that was already read for `lastCompletedPhase` at line ~519
- [ ] Replace the Phase Progression Table reference with the following verbatim text (identical to Task 2.1):
  ```
  Construct `feature_type_id` as `"feature:{id}-{slug}"` from the `id` and `slug` fields
  already extracted from `.meta.json`.
  Call `get_phase(feature_type_id)`. Parse the JSON response object.
  - If `current_phase` is non-null: the feature is mid-phase. Route to `iflow:{current_phase}`
    (or `iflow:finish-feature` when `current_phase` is `finish`).
  - If `current_phase` is null: the feature is between phases. Use `last_completed_phase`
    to determine the next phase from the canonical sequence:
    brainstorm → specify → design → create-plan → create-tasks → implement → finish.
    Route to the command for that next phase.
  If MCP unavailable, fall back to `.meta.json` `lastCompletedPhase` (camelCase)
  and apply the same canonical-sequence logic.
  ```

**Done when:** `grep "get_phase" secretary.md` returns at least 2 matches (both sites). `grep -B5 "get_phase" secretary.md | grep -i "guardian"` returns a match (confirms insertion at Workflow Guardian site). `grep "lastCompletedPhase" secretary.md` returns match (fallback).

### Task 2.3: Update create-specialist-team.md — three targets
- [ ] **Target 1 — Step 3 inline sequence** (~lines 111-112): Replace the instruction ending with colon + arrow-delimited sequence line with the following verbatim text (maintain 6-space indentation):
  ```
        by calling `get_phase("feature:{id}-{slug}")` (using `id` and `slug` extracted above).
        Parse the JSON response: if `current_phase` is non-null, use it; if null, determine next
        phase from `last_completed_phase` using the canonical sequence in workflow-state SKILL.md.
        If MCP unavailable, fall back to `lastCompletedPhase` from `.meta.json` (already extracted).
        Apply the same edge cases as FR-7 (null+null → specify, last=finish → complete, no active feature → brainstorm).
  ```
- [ ] **Target 2 — Mapping table** (~lines 180-191): Replace the phase-to-command mapping table with:
  ```
  Phase names map 1:1 to commands: `iflow:{phase-name}`, except:
  - finish → `iflow:finish-feature`
  ```
- [ ] **Target 3 — Phase comparison logic** (~lines 212-214): Replace the instructions about preferring next phase with:
  ```
  If the suggested phase differs from the MCP-reported current phase (from the
  `get_phase` response `current_phase` field), recommend the current phase instead
  (prerequisites must be satisfied first).
  ```

**Done when:** `grep "Phase-to-command mapping\|Phase name (.meta.json)" create-specialist-team.md` returns zero matches. `grep "brainstorm → specify → design" create-specialist-team.md` returns zero matches in Step 3 area.

**Parallel group:** Tasks 2.1-2.2 are sequential (same file). Task 2.3 is independent (different file, can run parallel with 2.1-2.2).

## Phase 3: Reference Updates (4 files)

### Task 3.1: Update workflow-transitions Step 1
- [ ] Locate Step 1 (~lines 34-36) in `plugins/iflow/skills/workflow-transitions/SKILL.md` containing `Apply validateTransition logic`
- [ ] Replace the 3-line block with the following verbatim text:
  ```
  Check transition validity:
  - Read current `.meta.json` state (get `lastCompletedPhase`)
  - Hard prerequisites are validated by the calling command before Step 1
  - Determine transition type: normal forward, backward, or skip
  - If blocked by command prerequisite: command already stopped before reaching Step 1
  ```

**Done when:** `grep "validateTransition" workflow-transitions/SKILL.md` returns zero matches. `grep "Check transition validity" workflow-transitions/SKILL.md` returns one match.

### Task 3.2: Update implement.md hard prerequisite references
- [ ] Locate `validateArtifact(path, "spec.md")` (~line 29)
- [ ] Replace with: `validate spec.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`
- [ ] Locate `validateArtifact(path, "tasks.md")` (~line 40)
- [ ] Replace with: `validate tasks.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`

**Done when:** `grep "validateArtifact(" implement.md` returns zero matches.

### Task 3.3: Update create-tasks.md and create-plan.md hard prerequisite references
- [ ] Locate `validateArtifact(path, "plan.md")` (~line 16) in create-tasks.md
- [ ] Replace with: `validate plan.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`
- [ ] Locate `validateArtifact(path, "design.md")` (~line 16) in create-plan.md
- [ ] Replace with: `validate design.md exists and has substantive content (>100 bytes, has ## headers, has required sections)`

**Done when:** `grep "validateArtifact(" create-tasks.md create-plan.md` returns zero matches.

**Parallel group:** Tasks 3.1, 3.2, 3.3 are all independent (different files).

## Phase 4: Documentation and Verification

### Task 4.1: Update documentation references
- [ ] Locate Documentation Sync table row in CLAUDE.md referencing `Workflow Map section (if phase sequence or prerequisites change)`; replace with `Phase Sequence one-liner (if phase names change)` (literal string replacement)
- [ ] Locate reference to `Workflow Map` in `.claude/hookify.docs-sync.local.md`; replace with the literal text `Phase Sequence one-liner`
- [ ] Locate line 16 in `docs/dev_guides/templates/command-template.md`: `- Apply validateTransition logic for target phase`; replace with `- Check transition validity by following workflow-transitions Step 1 for target phase`

- [ ] Run `grep -n "Workflow Map\|validateTransition\|validateArtifact\|Phase Progression Table" README.md README_FOR_DEV.md` — if any matches found, update the affected lines

**Done when:** `grep "Workflow Map" CLAUDE.md .claude/hookify.docs-sync.local.md` returns zero matches. `grep "validateTransition" docs/dev_guides/templates/command-template.md` returns zero matches. `grep "Phase Sequence one-liner" CLAUDE.md` returns one match. `grep "Phase Sequence one-liner" .claude/hookify.docs-sync.local.md` returns one match.

### Task 4.2: Verify read-only targets
- [ ] Run `grep -n "PHASE_SEQUENCE\|phase_map" plugins/iflow/hooks/yolo-stop.sh` — confirm `PHASE_SEQUENCE` appears in primary path, `phase_map` appears only inside an `except:` block
- [ ] Run `grep -n "validateTransition" docs/knowledge-bank/patterns.md` — confirm match is historical context ("Avoided modifying core validateTransition logic"), not active instruction

**Done when:** yolo-stop.sh has `PHASE_SEQUENCE` in primary path and `phase_map` only in `except` block. patterns.md reference is historical. No changes made to either file.

### Task 4.3: Measure line counts and compute savings
- [ ] Run `wc -l` on all 9 editable target files (post-edit)
- [ ] Compute per-file reduction vs pre-edit baselines from Task 1.1
- [ ] Estimate token savings (1 line ~ 10-15 tokens)

**Done when:** Line count table produced with before/after/reduction per file and aggregate totals.

### Task 4.4: Run grep validation (AC-1 through AC-15)
- [ ] AC-1: `grep "validateTransition\|function validateTransition" plugins/iflow/skills/workflow-state/SKILL.md` → zero matches
- [ ] AC-2: `grep "validateArtifact\|function validateArtifact" plugins/iflow/skills/workflow-state/SKILL.md` → zero matches
- [ ] AC-3: `grep "## Transition Validation" plugins/iflow/skills/workflow-state/SKILL.md` → zero matches
- [ ] AC-4: `grep "## Workflow Map" plugins/iflow/skills/workflow-state/SKILL.md` → zero matches
- [ ] AC-5: `grep "brainstorm → specify → design" plugins/iflow/skills/workflow-state/SKILL.md` → exactly 1 match
- [ ] AC-6: `grep "Phase Progression Table" plugins/iflow/commands/secretary.md` → zero matches
- [ ] AC-7: `grep "Phase-to-command mapping\|Phase name (.meta.json)" plugins/iflow/commands/create-specialist-team.md` → zero matches
- [ ] AC-8: `./validate.sh` → passes
- [ ] AC-9: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5"` → passes
- [ ] AC-10: `grep "validateArtifact(" plugins/iflow/commands/implement.md plugins/iflow/commands/create-tasks.md plugins/iflow/commands/create-plan.md` → zero matches
- [ ] AC-11: Manual check — `grep "validateTransition\|validateArtifact" plugins/iflow/skills/workflow-transitions/SKILL.md` → zero matches (Step 1 references no removed functions)
- [ ] AC-12: `grep "get_phase" plugins/iflow/commands/secretary.md` → at least 2 matches (both sites); `grep "lastCompletedPhase" plugins/iflow/commands/secretary.md` → at least 1 match (fallback)
- [ ] AC-13: Line counts documented (Task 4.3 output)
- [ ] AC-14: `grep "PHASE_SEQUENCE" plugins/iflow/hooks/yolo-stop.sh` → at least 1 match (primary path)
- [ ] AC-15: `grep "validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map" CLAUDE.md README.md README_FOR_DEV.md` → zero matches

**Done when:** All 15 ACs pass with expected match counts.

### Task 4.5: Run broad codebase grep, test suite, and smoke test
- [ ] Run `grep -rn 'validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map' . --include='*.md' | grep -v docs/features/ | grep -v docs/projects/ | grep -v docs/brainstorms/` — expected hit only in `docs/knowledge-bank/patterns.md` (historical, acceptable)
- [ ] Run `./validate.sh` — must pass
- [ ] Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5 or sc_5 or skill_md"` — must pass
- [ ] Smoke test setup: Create a throwaway test feature via `mkdir -p docs/features/999-smoke-test && echo '{"id":"999","slug":"smoke-test","status":"active","created":"2026-03-08T00:00:00+08:00","branch":"feature/017-command-cleanup-and-pseudocode","lastCompletedPhase":null,"phases":{}}' > docs/features/999-smoke-test/.meta.json`
- [ ] Run `/iflow:specify --feature=999-smoke-test` (can cancel after phase begins). Pass conditions:
  1. No `validateTransition` string appears in workflow output
  2. Phase begins without errors about missing functions or broken references
  3. No crash or unhandled reference errors
- [ ] Clean up: `rm -rf docs/features/999-smoke-test`

**Done when:** Broad grep shows only acceptable historical hits. Both test suites pass. All 3 smoke test conditions met. Test feature cleaned up.

### Task 4.6: Update CHANGELOG.md
- [ ] Add entry under `[Unreleased]` documenting pseudocode/table removal
- [ ] Include aggregate line reduction and token savings estimate from Task 4.3

**Done when:** CHANGELOG.md has entry under `[Unreleased]` with removal summary and metrics.

**Parallel group:** Task 4.1 independent. Task 4.2 independent. Task 4.3 depends on Phases 1-3. Tasks 4.4-4.5 depend on Phases 1-3 (sequential: 4.4 then 4.5). Task 4.6 depends on Task 4.3.

## Dependency Graph

```
Phases 1, 2, and 3 are fully independent and can execute in parallel.
A multi-agent execution could complete Phases 1-3 concurrently.
Phase 4 is the blocking gate (depends on Phases 1-3).

Phase 1 (sequential):
  1.1 (baseline, independent)
  1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 1.7 → 1.8 → 1.9

Phase 2 (mixed):
  2.1 → 2.2 (secretary.md, sequential)
  2.3 (create-specialist-team.md, parallel with 2.1-2.2)

Phase 3 (parallel):
  3.1, 3.2, 3.3 (all independent, different files)

Phase 4 (mixed, after Phases 1-3):
  4.1, 4.2 (independent, can run parallel)
  4.3 (after Phases 1-3, uses Task 1.1 baselines)
  4.4 → 4.5 (sequential validation)
  4.6 (after 4.3)
```

## Summary

| Phase | Tasks | Steps | Complexity |
|-------|-------|-------|------------|
| Phase 1 | 9 | 12 | Medium — many sections but single file, content-match removal + early test |
| Phase 2 | 3 | 7 | Medium — atomic replace-then-remove, two files |
| Phase 3 | 3 | 5 | Simple — small text replacements, four files |
| Phase 4 | 6 | 11 | Medium — documentation updates + validation sweep + smoke test |
| **Total** | **21** | **35** | |
