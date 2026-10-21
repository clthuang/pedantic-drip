# Specification: Command Cleanup and Pseudocode Removal

## Overview

Remove text-LLM state control pseudocode from `workflow-state/SKILL.md`, remove phase progression tables from `secretary.md` and `create-specialist-team.md`, and clean up references to removed constructs in command files. This is the final feature in the R1-P2 (Command and Hook Migration) milestone of project P001.

**What this feature achieves:** Features 008-009 extracted state control logic into Python (`transition_gate`, `WorkflowStateEngine`, MCP tools). Features 014-016 migrated all commands and hooks to call these MCP tools. Feature 017 removes the now-redundant text-based state control artifacts — pseudocode functions, phase progression tables, and stale references — achieving the PRD success criterion: "Zero text-LLM state control."

**No PRD:** This feature was created as part of the P001 project decomposition. The project PRD provides the overarching context.

**PRD traceability:** PRD Phase 4 (Cutover + Cleanup) items 2, 3, 5, 6, 7. Item 1 (`.meta.json` write removal) and item 4 (`phase_map` removal) are addressed separately — see Out of Scope.

## Functional Requirements

### FR-1: Remove `validateTransition()` pseudocode from workflow-state/SKILL.md

Remove the `validateTransition` function definition (lines 123-156) including the "### Validation Logic" header. This pseudocode is now implemented in Python at `transition_gate/gate.py` and exposed via `transition_phase` MCP tool.

**Current content (to remove):**
```
### Validation Logic

```
function validateTransition(currentPhase, targetPhase, artifacts):
  ...
```
```

**Includes:** The header, code fence, and entire function body (34 lines).

### FR-2: Remove `validateArtifact()` pseudocode from workflow-state/SKILL.md

Remove the `validateArtifact` function definition (lines 201-230) and the "Usage in Commands" section (lines 232-237). This pseudocode describes artifact content validation (4-level: existence, non-empty, structure, type-specific sections). The actual validation logic is already described inline in each command's hard prerequisite section.

**Current content (to remove):**
```
**Implementation:**
```
function validateArtifact(path, type):
  ...
```

**Usage in Commands:**
Commands with hard prerequisites should call validateArtifact instead of just checking existence:
- `/iflow:create-plan` validates design.md
- ...
```

**Includes:** The "Implementation" label, code fence, function body, and "Usage in Commands" section (36 lines).

### FR-3: Remove Transition Validation section from workflow-state/SKILL.md

Remove the entire "## Transition Validation" section (lines 51-93) including:
- "### Hard Prerequisites (Block)" table (lines 55-66)
- "### Soft Prerequisites (Warn)" AskUserQuestion example (lines 68-83)
- "### Normal Transitions (Proceed)" (lines 90-93)

These rules are now encoded in:
- Python: `transition_gate/gate.py` functions (`validate_hard_prerequisites`, `validate_soft_prerequisites`)
- Prose: `workflow-transitions/SKILL.md` Step 1 (backward/skip/proceed handling)
- Commands: inline hard prerequisite checks (implement.md, create-tasks.md, create-plan.md)

### FR-4: Remove Backward Transition Warning section from workflow-state/SKILL.md

Remove the "### Backward Transition Warning" section (lines 158-175) including the AskUserQuestion example. This is already defined identically in `workflow-transitions/SKILL.md` Step 1.

### FR-5: Remove Phase Sequence table and Workflow Map from workflow-state/SKILL.md

Remove:
- The Phase Sequence **table** (lines 22-30) — the table mapping phases to artifacts and "Required Before" relationships
- The "## Workflow Map" section (lines 32-49) — visual overview and prerequisite documentation

**Keep (all four elements are required):**
1. The `## Phase Sequence` heading (line 14) — the SC-5 test searches for a heading containing "Phase Sequence"
2. The introductory text `The canonical workflow order:` (line 16)
3. The code fence delimiters (lines 18, 20)
4. The one-line phase sequence (line 19): `brainstorm → specify → design → create-plan → create-tasks → implement → finish`

**Why all four:** The `test_gate.py` SC-5 test (lines 1861-1924) first locates the heading containing "Phase Sequence" (line 1891), then searches for the arrow-delimited line after that heading (line 1896). Removing the heading would break the test even if the arrow line is preserved.

### FR-6: Remove Artifact Validation section header and level descriptions from workflow-state/SKILL.md

Remove the "## Artifact Validation" header (line 177), the introductory text (lines 179-180), the "### validateArtifact(path, type)" sub-header (line 181), and the Level 1-4 descriptions with type-specific sections table (lines 183-200).

The Level 1-4 validation logic is already described inline in each command's hard prerequisite error messages. Removing the central definition eliminates redundancy.

### FR-7: Remove Phase Progression Table from secretary.md

Remove the "### Phase Progression Table" section (lines 28-41) from `secretary.md`. This table maps `lastCompletedPhase` values to the next workflow command.

**Replace with MCP-based phase resolution** at the two reference sites:

1. **"Determine Next Command" (line 336):** Replace `"Use the Phase Progression Table above..."` with:
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

2. **"Workflow Guardian" (line 520):** Replace `"Determine next phase using the Phase Progression Table above."` with identical replacement text as item 1 above (both sites use the same MCP-based resolution logic — no site-specific framing differences).

**`get_phase` response shape** (from `workflow_state_server.py`):
```json
{
  "feature_type_id": "feature:{id}-{slug}",
  "current_phase": "<phase-name> | null",
  "last_completed_phase": "<phase-name> | null",
  "completed_phases": ["<phase-name>", ...],
  "mode": "standard | full",
  "source": "db | meta_json | meta_json_fallback",
  "degraded": true/false
}
```
Note: MCP uses snake_case (`last_completed_phase`), while `.meta.json` uses camelCase (`lastCompletedPhase`). The replacement text uses the correct casing for each context.

**Edge cases for phase resolution (applies to both MCP and fallback paths):**
- `current_phase` is null AND `last_completed_phase` is null → next phase is `specify`
- `last_completed_phase` is `"finish"` → feature already complete, no next command
- No active feature found → route to `iflow:brainstorm` or `iflow:create-feature`
- `get_phase` MCP unavailable or `degraded: true` → fall back to `.meta.json` `lastCompletedPhase`

**Phase-name-to-command-name mapping** (inline, replaces the removed table). This is purely a naming convention — progression logic comes from `get_phase` or the canonical sequence:
```
Phase names map 1:1 to commands: iflow:{phase-name}, except:
- finish → iflow:finish-feature
```

### FR-8: Remove phase sequence and mapping tables from create-specialist-team.md

Remove from `create-specialist-team.md`:

1. **Inline phase sequence in Step 3** (line 112 only): Remove the arrow-delimited sequence line `brainstorm → specify → design → create-plan → create-tasks → implement → finish`. Update line 111's instruction from `using the canonical phase sequence (matches .meta.json values):` to use MCP-based resolution. Note: Step 3 already discovers the active feature via glob + `.meta.json` parsing (extracting `id`, `slug`, `lastCompletedPhase`). The replacement adds a `get_phase` call AFTER feature identity is known:
   ```
   by calling `get_phase("feature:{id}-{slug}")` (using `id` and `slug` extracted above).
   Parse the JSON response: if `current_phase` is non-null, use it; if null, determine next
   phase from `last_completed_phase` using the canonical sequence in workflow-state SKILL.md.
   If MCP unavailable, fall back to `lastCompletedPhase` from `.meta.json` (already extracted).
   Apply the same edge cases as FR-7 (null+null → specify, last=finish → complete, no active feature → brainstorm).
   ```

2. **Phase-to-command mapping table** (lines 180-191): Remove the table mapping `.meta.json` phase names to skill dispatch commands. Replace with inline mapping:
   ```
   Phase names map 1:1 to commands: `iflow:{phase-name}`, except:
   - finish → `iflow:finish-feature`
   ```

3. **Phase comparison logic** (lines 212-214): Remove the instructions about preferring next phase in sequence and minimizing phase-skipping. Replace with:
   ```
   If the suggested phase differs from the MCP-reported current phase (from the
   `get_phase` response `current_phase` field), recommend the current phase instead
   (prerequisites must be satisfied first).
   ```

**Keep (not removed):**
- The "If no active feature" output signals table (lines 192-198) — maps output types to recommended actions, not a phase sequence
- The "If active feature exists" output signals table (lines 203-210) — maps output types to suggested phases for routing, not state control
- The "Check which artifacts exist" instruction (line 113) — used for workflow context display

### FR-9: Update workflow-transitions Step 1 reference

`workflow-transitions/SKILL.md` Step 1 (line 34-36) currently says:
```
Check prerequisites using workflow-state skill:
- Read current `.meta.json` state
- Apply validateTransition logic for target phase `{phaseName}`
- If blocked: Show error, stop
```

Update to remove the reference to `validateTransition`:
```
Check transition validity:
- Read current `.meta.json` state (get `lastCompletedPhase`)
- Hard prerequisites are validated by the calling command before Step 1
- Determine transition type: normal forward, backward, or skip
- If blocked by command prerequisite: command already stopped before reaching Step 1
```

The backward and skip handling prose (lines 39-68) remains unchanged — those are the concrete AskUserQuestion blocks that implement the behavior.

**Verified:** All three commands with hard prerequisites (implement.md line 27, create-tasks.md line 14, create-plan.md line 14) perform their hard prerequisite checks BEFORE calling `validateAndSetup`. The replacement text accurately describes the current architecture. Note: only these 3 commands have hard prerequisites — the remaining phase commands (specify, design, finish) have no `validateArtifact` checks.

### FR-10: Update command hard prerequisite references

The following commands reference `validateArtifact` by name in their hard prerequisite sections:

| Command | Current text | Line |
|---------|-------------|------|
| implement.md | `validate spec.md using \`validateArtifact(path, "spec.md")\`` | 29 |
| implement.md | `validate tasks.md using \`validateArtifact(path, "tasks.md")\`` | 40 |
| create-tasks.md | `validate plan.md using \`validateArtifact(path, "plan.md")\`` | 16 |
| create-plan.md | `validate design.md using \`validateArtifact(path, "design.md")\`` | 16 |

**Update each** to remove the function name reference. Replace `validateArtifact(path, "type")` with a direct description:

```
Before: validate spec.md using `validateArtifact(path, "spec.md")`
After:  validate spec.md exists and has substantive content (>100 bytes, has ## headers, has required sections)
```

The Level 1-4 error messages below each check remain unchanged — they already describe the validation behavior inline.

### FR-11: Update Planned→Active Transition reference

`workflow-state/SKILL.md` line 119 says:
```
7. Continue with normal phase execution (proceed to `validateTransition` below)
```

Update to:
```
7. Continue with normal phase execution (proceed to workflow-transitions Step 1)
```

### FR-12: Verify yolo-stop.sh phase_map removal

Feature 014 migrated `yolo-stop.sh` from hardcoded `phase_map` dict to `PHASE_SEQUENCE` constant from `transition_gate.constants`. Verify:

1. `yolo-stop.sh` uses `PHASE_SEQUENCE` (not `phase_map` as primary path) — the `phase_map` dict remains only as a fallback in the `except` block
2. The fallback `phase_map` in the `except` block is acceptable — it's graceful degradation for when the Python import fails, not text-LLM state control
3. Test file `test_yolo_stop_phase_logic.py` validates both paths

**No changes needed** — verify only. The `phase_map` fallback in `yolo-stop.sh` is embedded Python inside a bash hook, not a text-LLM interpreted table. This satisfies PRD Phase 4 item 4 — the `phase_map` fallback is graceful degradation, not text-LLM state control, so no removal is required.

### FR-13: Measure token savings

After all removals, measure line count reduction for each modified file:

| File | Before (lines) | After (lines) | Reduction |
|------|----------------|---------------|-----------|
| workflow-state/SKILL.md | 363 | (measured) | (computed) |
| secretary.md | 699 | (measured) | (computed) |
| create-specialist-team.md | 239 | (measured) | (computed) |
| workflow-transitions/SKILL.md | 229 | (measured) | (computed) |
| implement.md | 999 | (measured) | (computed) |
| create-tasks.md | 396 | (measured) | (computed) |
| create-plan.md | 353 | (measured) | (computed) |

Report aggregate line reduction and estimated token savings (1 line ≈ 10-15 tokens). Document in the CHANGELOG entry (FR-14) and in the implementation commit message.

### FR-14: Update documentation

1. **CHANGELOG.md:** Add entry under `[Unreleased]` documenting the pseudocode and table removal
2. **README.md / README_FOR_DEV.md:** If any removed sections are referenced, update references
3. **CLAUDE.md:** Update line referencing "Workflow Map section" in the Documentation Sync table. Replace `Workflow Map section (if phase sequence or prerequisites change)` with `Phase Sequence one-liner (if phase names change)` since prerequisites are now in Python code, not SKILL.md

## Non-Functional Requirements

### NFR-1: No behavioral changes to phase transitions

All phase transition behavior (blocking, backward warnings, skip warnings, hard prerequisites) must remain identical after the removal. The pseudocode is being removed because the behavior is implemented elsewhere (Python engine, workflow-transitions prose, command inline checks), not because the behavior is changing.

### NFR-2: Test suite must pass

- `./validate.sh` must pass
- `test_gate.py` SC-5 test must pass (reads SKILL.md for phase sequence)
- All existing Python test suites must pass unmodified

### NFR-3: Preserve one-line phase sequence

The one-line `brainstorm → specify → design → create-plan → create-tasks → implement → finish` in workflow-state/SKILL.md must be preserved. It serves as:
1. Reference documentation for the canonical phase ordering
2. Test anchor for `test_gate.py` SC-5 (verifies Python constant matches SKILL.md)

### NFR-4: MCP fallback for phase resolution

When replacing phase progression tables with `get_phase` MCP calls (FR-7, FR-8), include a fallback path for MCP unavailability. The fallback should use `lastCompletedPhase` from `.meta.json` + the one-line canonical sequence to determine the next phase. This matches the graceful degradation pattern established by features 010/015.

### NFR-5: No new dependencies

All changes are removals or text edits to existing markdown files. No new tools, packages, or MCP servers required.

## Acceptance Criteria

- AC-1: GIVEN workflow-state/SKILL.md after cleanup, WHEN searching for `validateTransition` or `function validateTransition`, THEN zero matches found
- AC-2: GIVEN workflow-state/SKILL.md after cleanup, WHEN searching for `validateArtifact` or `function validateArtifact`, THEN zero matches found
- AC-3: GIVEN workflow-state/SKILL.md after cleanup, WHEN searching for `## Transition Validation`, THEN zero matches found
- AC-4: GIVEN workflow-state/SKILL.md after cleanup, WHEN searching for `## Workflow Map`, THEN zero matches found
- AC-5: GIVEN workflow-state/SKILL.md after cleanup, WHEN searching for `brainstorm → specify → design → create-plan → create-tasks → implement → finish`, THEN exactly one match found (the preserved one-line sequence)
- AC-6: GIVEN secretary.md after cleanup, WHEN searching for `Phase Progression Table`, THEN zero matches found
- AC-7: GIVEN create-specialist-team.md after cleanup, WHEN searching for `Phase-to-command mapping`, THEN zero matches found. WHEN searching for `Phase name (.meta.json)`, THEN zero matches found (table column header). WHEN searching for the inline arrow sequence `brainstorm → specify → design`, THEN zero matches found in Step 3 (the arrow sequence in workflow-state SKILL.md remains)
- AC-8: GIVEN `./validate.sh` is run, THEN it passes with zero errors
- AC-9: GIVEN `test_gate.py` SC-5 test is run, THEN it passes (SKILL.md still contains the one-line phase sequence)
- AC-10: GIVEN any command file (implement.md, create-tasks.md, create-plan.md), WHEN searching for `validateArtifact(`, THEN zero matches found
- AC-11: GIVEN workflow-transitions/SKILL.md Step 1, WHEN examining the text, THEN it references no removed pseudocode functions
- AC-12: GIVEN secretary.md after cleanup, WHEN searching for `get_phase`, THEN at least one match found in both the "Determine Next Command" and "Workflow Guardian" sections. WHEN searching for `Phase Progression Table`, THEN zero matches found. WHEN searching for `lastCompletedPhase`, THEN at least one match found (fallback path preserved)
- AC-13: GIVEN line counts before and after, WHEN comparing totals, THEN aggregate reduction is documented with estimated token savings
- AC-14: GIVEN `yolo-stop.sh`, WHEN examining the primary path, THEN it uses `PHASE_SEQUENCE` from `transition_gate.constants` (not a hardcoded `phase_map` dict as primary logic)
- AC-15: GIVEN project documentation files (CLAUDE.md, README.md, README_FOR_DEV.md), WHEN searching for `validateTransition`, `validateArtifact`, `Phase Progression Table`, or `Workflow Map`, THEN zero matches found (documentation cleaned up per FR-14)

## Out of Scope

- **`.meta.json` phase state write removal (PRD Phase 4 item 1):** The dual-write pattern (`.meta.json` primary + MCP secondary) established by feature 016 remains. Cutting over to MCP-only writes requires graceful degradation (feature 010) to handle MCP unavailability. Deferred to a future feature.
- **`.meta.json` read migration:** Commands and skills that read `.meta.json` for feature metadata (id, slug, status, branch, brainstorm_source) continue doing so. Phase state reads are progressively migrating to `get_phase` MCP (features 015, this feature) but full migration is out of scope.
- **State Schema documentation removal:** The "## State Schema" section (lines 240-364) in workflow-state/SKILL.md documents the `.meta.json` structure. This remains useful as reference documentation and is not "text-LLM state control."
- **Planned→Active Transition section removal:** This section (lines 94-121) describes the unique flow for activating planned features. It is not pseudocode — it's behavioral instructions consumed by workflow-transitions. Retained. Note: FR-11 modifies a single cross-reference within this retained section (line 119: `validateTransition` → `workflow-transitions Step 1`) but does not remove the section itself.
- **Python engine or MCP tool modifications:** No changes to `transition_gate`, `WorkflowStateEngine`, or MCP server code.
- **Domain-specific `.meta.json` metadata:** Reviewer notes, design stage tracking, task concerns — these remain as inline `.meta.json` operations in commands.
- **`yolo-stop.sh` fallback `phase_map`:** The hardcoded `phase_map` dict in the `except` block of `yolo-stop.sh` is an embedded Python fallback, not text-LLM state control. It stays for graceful degradation.
- **PRD Phase 4 item 7 validation (`.meta.json` write pattern grep):** Item 7 says "grep confirms zero remaining .meta.json write patterns in commands." This validation applies to item 1 (`.meta.json` write removal), which is deferred. This feature validates item 7 only for the cleanup portions: `./validate.sh` passes and grep confirms zero pseudocode/table references.

## Verification Strategy

Verification is manual — skill and command files are markdown instructions:

1. **Grep validation:** Run the following greps and confirm zero matches:
   ```bash
   grep -rn "validateTransition\|validateArtifact" plugins/iflow/skills/workflow-state/SKILL.md
   grep -n "Phase Progression Table" plugins/iflow/commands/secretary.md
   grep -n "canonical phase sequence\|Phase-to-command mapping" plugins/iflow/commands/create-specialist-team.md
   grep -n "validateArtifact(" plugins/iflow/commands/implement.md plugins/iflow/commands/create-tasks.md plugins/iflow/commands/create-plan.md
   grep -rn "validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map" CLAUDE.md README.md README_FOR_DEV.md
   ```

2. **Positive validation:** Confirm the one-line phase sequence is preserved:
   ```bash
   grep -c "brainstorm → specify → design → create-plan → create-tasks → implement → finish" plugins/iflow/skills/workflow-state/SKILL.md
   # Expected: 1
   ```

3. **Test suite:** Run `./validate.sh` and `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -k "SC_5 or sc_5 or skill_md"` to verify no test regressions.

4. **Line count comparison:** Run `wc -l` on all modified files before and after, compute aggregate reduction, estimate token savings.

5. **End-to-end smoke test:** Run `/iflow:specify` on a test feature to confirm the full workflow-transitions flow works after Step 1 reference updates. Verify: (1) validateAndSetup Step 1 does not reference `validateTransition` in its output, (2) phase starts successfully (.meta.json updated), (3) no error about missing functions or broken references.

## Technical Notes

- **Line number caveat:** Line numbers throughout this spec are approximate, based on files at the time of spec writing. Implementers should match by content (quoted text), not line number. If line numbers have drifted, use grep to locate the target content.
- workflow-state/SKILL.md currently has 363 lines. After removing ~188 lines (Phase Sequence table, Workflow Map, Transition Validation, validateTransition, Backward Transition Warning, Artifact Validation, validateArtifact), approximately 175 lines remain: frontmatter (4), config (5), intro (2), one-line sequence (1), Planned→Active Transition (28), State Schema (125), spacing (10).
- The `test_gate.py` SC-5 test at lines 1862-1918 reads `plugins/iflow/skills/workflow-state/SKILL.md`, extracts the arrow-delimited phase sequence, and compares against the Python `PHASE_SEQUENCE` constant. The test looks for the pattern `brainstorm → specify → ...` using character matching. Removing surrounding content does not affect this test as long as the one-line sequence remains.
- secretary.md's "Workflow Guardian" (lines 508-524) and "Determine Next Command" (line 336) both reference the Phase Progression Table. Both need updates to use `get_phase` MCP with `.meta.json` fallback.
- create-specialist-team.md Step 3 (lines 101-123) and Step 5 (lines 176-214) contain the phase-related content. Step 3 gathers workflow context; Step 5 assesses workflow routing. Both need MCP-based replacement.
- The `validateArtifact` references in commands use the function name as a shorthand. The actual validation behavior (Level 1-4 checks) is already described inline via the error messages. Removing the function name reference and describing the checks directly is a text-only change.
