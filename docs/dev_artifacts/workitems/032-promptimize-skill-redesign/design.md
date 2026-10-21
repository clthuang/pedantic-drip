# Design: Promptimize Skill Redesign

## Prior Art Research

### Codebase Patterns

1. **Two-pass agent dispatch** (`commands/implement.md:112-184`): Test-deepener uses Phase A (generate outlines from spec) → Phase B (write executable tests from outlines). Closest precedent for structured two-pass LLM execution. Key difference: our two phases execute within a single skill invocation (structural decomposition), not two separate Task dispatches.

2. **JSON-parse-with-retry** (`skills/decomposing/SKILL.md:21-113`): Decomposing skill outputs structured JSON and the command parses it. Established pattern for LLM→JSON→command-level processing. Directly applicable to Phase 1 JSON extraction.

3. **Command-level data calculation** (`skills/retrospecting/SKILL.md:89-282`): Retrospecting skill computes metrics from agent-produced JSON. Precedent for moving deterministic computation out of LLM and into the orchestrating command.

4. **No existing XML tag parsing**: The codebase has no precedent for parsing `<change>` XML tags from LLM output. HTML comment markers (`<!-- CHANGE -->`) exist only in the current promptimize skill. This is new territory.

### External Patterns

1. **Grader→Rewriter decomposition**: Industry standard for LLM-as-judge pipelines. Databricks "grading notes" pattern: reasoning trace before score assignment. Patronus AI: force integer categorical scale, extract with regex, score comes LAST after chain-of-thought.

2. **Regex-based XML extraction**: Libraries like llm-xml-parser and LangChain XMLOutputParser extract structured XML from mixed LLM output using regex, not full XML parsers. Aligns with R4.3's regex-based validation approach.

3. **Partial acceptance**: ProseMirror suggestion-mode provides per-hunk accept/reject as prior art. Our approach (dimension-level granularity) is coarser but more appropriate for the promptimize use case.

---

## Architecture Overview

The redesign transforms the promptimize system from a **monolithic skill with thin command wrapper** into a **smart command orchestrating a focused skill**.

### Current Architecture

```
Command (promptimize.md)         Skill (SKILL.md)
┌─────────────────────┐         ┌──────────────────────────────┐
│ File selection       │         │ Step 1: Detect type          │
│ Delegate to skill ───┼────────>│ Step 2: Load references      │
│                      │         │ Step 3: Staleness check      │
│                      │         │ Step 4: Evaluate 9 dims      │
│                      │         │ Step 5: Calculate score       │
│                      │         │ Step 6: Generate improved     │
│                      │         │ Step 7: Generate report       │
│                      │         │ Step 8: User approval + merge │
└─────────────────────┘         └──────────────────────────────┘
```

Problems: God Prompt (Steps 4-7 in one pass), HTML markers, LLM math, brittle merge.

### New Architecture

```
Command (promptimize.md)                    Skill (SKILL.md)
┌────────────────────────────────┐         ┌─────────────────────────────┐
│ Step 1-2: File selection       │         │ Step 1: Detect type         │
│ Step 3: Invoke skill ──────────┼────────>│ Step 2: Load references     │
│                                │         │ Step 3: Staleness check     │
│ Step 4: Parse skill output  <──┼─────────│ Phase 1: Grade (→JSON)      │
│   ├ Extract Phase 1 JSON       │         │ Phase 2: Rewrite (→XML)     │
│   └ Extract Phase 2 content    │         └─────────────────────────────┘
│                                │
│ Step 5: Compute score          │
│ Step 6: Drift detection        │
│ Step 7: Assemble report        │
│ Step 8: User approval          │
│   ├ Accept all → strip tags    │
│   ├ Accept some → XML merge    │
│   └ Reject → no changes        │
└────────────────────────────────┘
```

Key shift: The command becomes the orchestrator. It handles all focused, single-concern operations (score calculation, tag validation, drift detection, report assembly, merge logic) as isolated steps — each with explicit instructions and no competing concerns. The skill focuses on what LLMs do well: evaluation and rewriting.

**Execution model:** Both skill and command are LLM-interpreted Markdown. The command does not execute deterministic code — it instructs the LLM to perform each operation as an isolated, focused step. This is a structural improvement (decomposing a God Prompt into single-concern steps) rather than true programmatic computation. The key reliability gain is that each step (e.g., "sum these 9 numbers and divide by 27") is the LLM's sole focus, not buried in a multi-concern generation. See TD6 for the honest framing.

**Skill-to-command data flow:** When the command invokes `Skill()`, the skill executes within the same LLM conversation context. The skill's output (text containing `<phase1_output>` and `<phase2_output>` sections) appears in the conversation and is directly available to subsequent command steps. No explicit variable capture is needed — the command's instructions reference the skill's output by its XML delimiters.

---

## Components

> **Implementation note:** C3-C10 are logical components implemented as sequential sections within `promptimize.md`. The component labels are design-time identifiers for clarity; they do not imply separate files or modules.

### C1: Skill — Phase 1 (Grader)

**Responsibility:** Evaluate 9 dimensions against the scoring rubric. Output structured JSON.

**Input:** Target file content, component type, scoring rubric, prompt guidelines.

**Output:** JSON matching R1.2 schema, wrapped in `<phase1_output>` tags.

**Behavior:**
- Steps 1-3 remain unchanged (detect type, load references, staleness check)
- Phase 1 replaces current Steps 4-5
- Produces finding + suggestion for partial/fail dimensions; suggestion=null for pass
- Records `guidelines_date` and `staleness_warning` from Step 3
- Does NOT compute overall score

### C2: Skill — Phase 2 (Rewriter)

**Responsibility:** Rewrite the target file, applying improvements for partial/fail dimensions.

**Input:** Original file content (from Step 2), Phase 1 JSON (wrapped in `<grading_result>` block).

**Output:** Complete rewritten file with `<change>` XML tags, wrapped in `<phase2_output>` tags.

**Behavior:**
- Consumes Phase 1 JSON as explicit context via `<grading_result>` block
- Wraps each modified region in `<change dimension="..." rationale="...">` tags
- Preserves text outside `<change>` tags as closely as possible to original (the command verifies content-equivalence after normalizing trailing whitespace per line and ignoring blank-line differences at file boundaries)
- Pass dimensions (score=3) have no `<change>` tags
- If all dimensions pass, Phase 2 output is identical to original (no `<change>` tags). Note: Phase 2 still runs in this case but is effectively a no-op. A future optimization could skip Phase 2 parsing when all Phase 1 scores are 3.

### C3: Command — Output Parser

**Responsibility:** Extract Phase 1 JSON and Phase 2 content from skill output.

**Behavior:**
- Parse `<phase1_output>...</phase1_output>` to extract Phase 1 JSON
- Parse `<phase2_output>...</phase2_output>` to extract Phase 2 content
- Validate Phase 1 JSON against R1.2 schema (9 dimensions, valid scores 1-3, required fields)
- If parsing fails: display error with raw output snippet, STOP

### C4: Command — Score Calculator

**Responsibility:** Compute overall score from Phase 1 dimension scores.

**Behavior:**
- Sum all 9 dimension scores (each 1-3)
- Compute `round((sum / 27) * 100)` to nearest integer
- Auto-passed dimensions already contribute 3 from the skill

### C5: Command — Tag Validator

**Responsibility:** Validate `<change>` tag structure in Phase 2 output.

**Behavior (R4.3):**
- Operate only within the `<phase2_output>` section
- Use regex to find all `<change ...>` and `</change>` tags, skipping any that appear inside fenced code blocks (between ``` delimiters)
- Check: every open has a close, no nesting, no overlapping pairs, non-empty dimension attribute
- Return: `{ valid: boolean, error?: string, blocks: ChangeBlock[] }`
- If invalid: set `tag_validation_failed = true` — used to disable "Accept some"
- **Known limitation:** If the target file itself contains literal `<change` text outside code fences, false positives may occur. This is expected to be rare for plugin prompt files.

### C6: Command — Drift Detector

**Responsibility:** Verify text outside `<change>` blocks matches original file.

**Behavior (R2.5):**
- For each `<change>` block, extract up to 3-line before-context and up to 3-line after-context anchors from Phase 2 output
- Locate the matching anchor region in original file
- Substitute each `<change>` block with the matched original text between the anchors
- Normalize both the reconstructed file and the original: strip trailing whitespace per line, ignore blank-line differences at file boundaries (blank-line runs at the start and end of the file)
- Compare normalized versions
- Return: `{ drift_detected: boolean, drift_details?: string }`
- If drift detected: set `drift_detected = true` — used to disable "Accept some"

**Edge cases:**
- **`<change>` at file start:** If fewer than 3 lines exist before the first `<change>` tag, use however many lines are available (0-2). A `<change>` tag on line 1 has 0 before-context lines — anchor match uses only the after-context.
- **`<change>` at file end:** If fewer than 3 lines exist after the last `</change>` tag, use however many are available (0-2).
- **Adjacent `<change>` blocks** (separated by fewer than 3 lines of unchanged content): The after-context of block N and before-context of block N+1 share or overlap lines. For drift detection, merge adjacent blocks into a single logical region — the before-context of the first block and the after-context of the last block form the anchor pair. The entire span (including non-change lines between the blocks) is compared: replace all `<change>` content with the corresponding original text between the outer anchors, then verify the reconstructed span matches the original. This avoids ambiguous overlapping anchors.
- **Zero context lines between blocks:** If the original file has changes in adjacent regions with no intervening unchanged content (e.g., two consecutive sections both need changes), context anchors between them are empty. This is a structural limitation — when it occurs, the merge degrades to Accept all / Reject per TD5. The Phase 2 prompt does not attempt to artificially separate adjacent changes.

### C7: Command — Report Assembler

**Responsibility:** Build the markdown report from structured data.

**Input:** Phase 1 JSON, computed score, Phase 2 content, warning flags.

**Output:** Markdown report matching R5.1 template.

**Behavior:**
- Strengths section: evaluated dimensions scoring pass (3), excluding auto-passed
- Issues table: partial (warning) and fail (blocker) dimensions, blockers first
- Improved Version section: Phase 2 output verbatim
- Conditional warnings: staleness (from Phase 1 JSON), over-budget (computed by command from Phase 2)
- **Token budget check:** Strip all `<change>` and `</change>` tags from Phase 2 output, count lines and approximate tokens (word count as proxy — the 5,000 token threshold is a budget guardrail, not a precise limit). If the stripped result exceeds 500 lines or 5,000 words, set `over_budget_warning = true`.

### C8: Command — Approval Handler

**Responsibility:** Present approval menu and execute the selected action.

**Behavior:**
- If all dimensions pass (score=100): skip menu, display "All dimensions passed — no improvements needed."
- If `[YOLO_MODE]` is active in the execution context: auto-select "Accept all" and skip AskUserQuestion. The command inherits YOLO detection from its existing Step 2d pattern — the same `[YOLO_MODE]` flag is checked again in Step 8.
- Otherwise present AskUserQuestion with options based on validation state:
  - Always: "Accept all", "Reject"
  - Only if `tag_validation_failed == false` AND `drift_detected == false`: "Accept some"
  - If either flag is true: show warning explaining why "Accept some" is unavailable. Use distinct messages per cause:
    - Tag validation failure: "Partial acceptance unavailable: `<change>` tag structure is malformed."
    - Drift detected: "Partial acceptance unavailable: text outside change blocks differs from original."
    - Anchor match failure (from C9 degradation): "Partial acceptance unavailable: could not uniquely match change regions to original file."

### C9: Command — Merge Engine (Accept Some)

**Responsibility:** Apply selected dimension changes using anchor-based merge.

**Behavior (R4.2):**
1. Parse `<change>` blocks from Phase 2 output with their context anchors
2. Present dimension multiSelect (overlapping dimensions as single option)
3. Start from original file content (`original_content` from Step 2.5)
4. For selected dimensions: find unique before+after context anchors in original, replace matched region with `<change>` block content
5. For unselected dimensions: keep the original text in place (no replacement)
6. All replacements computed simultaneously against original (not sequentially)
7. Applied in original-file order by line number
8. If any anchor match fails (zero, multiple, or overlapping): degrade to Accept all / Reject
9. Strip all residual `<change>` tags from result — this is the final operation, applied after all anchor-based replacements are written to the output buffer (defensive — should be none after the selected/unselected replacement pass above, but ensures no stray tags from parsing edge cases)
10. Write to original file path

**Concrete walkthrough:**

Original file:
```
Line 1: # My Skill
Line 2: Description here.
Line 3:
Line 4: ## Process
Line 5: Do step one.
Line 6: Do step two.
Line 7:
Line 8: ## Rules
Line 9: Rule content.
```

Phase 2 output (2 dimensions scoring partial):
```
Line 1: # My Skill
Line 2: <change dimension="token_economy" rationale="Trim description">
Line 3: Concise description.
Line 4: </change>
Line 5:
Line 6: ## Process
Line 7: <change dimension="structure_compliance" rationale="Add numbered steps">
Line 8: ### Step 1: Execute
Line 9: Do step one.
Line 10: ### Step 2: Verify
Line 11: Do step two.
Line 12: </change>
Line 13:
Line 14: ## Rules
Line 15: Rule content.
```

Parsing produces two ChangeBlocks:
- Block A: dimension=token_economy, before_context=["# My Skill"] (only 1 line — near file start, see C6 edge cases), after_context=["", "## Process"], content="Concise description."
- Block B: dimension=structure_compliance, before_context=["", "## Process"], after_context=["", "## Rules", "Rule content."], content="### Step 1: Execute\nDo step one.\n### Step 2: Verify\nDo step two."

User selects only token_economy (Block A):
1. Find "# My Skill" + ["", "## Process"] anchors in original → matches lines 1 and 3-4. Original text between anchors = "Description here." (line 2).
2. Replace line 2 with Block A content: "Concise description."
3. Block B (structure_compliance) is unselected → keep original lines 5-6 ("Do step one.\nDo step two.")
4. Result: lines 1, "Concise description.", 3-4, original 5-6, 7-9.

### C10: Command — Accept All Handler

**Responsibility:** Strip all `<change>` tags and write clean output.

**Behavior (R4.4):**
- Take Phase 2 output
- Remove all `<change ...>` opening tags and `</change>` closing tags via regex
- Write result to original file path

---

## Technical Decisions

### TD1: Single Skill Invocation with Structural Decomposition

**Decision:** Phase 1 and Phase 2 execute within a single skill invocation (one LLM generation). The skill's instructions enforce ordering: produce Phase 1 JSON first, then use it as context for Phase 2.

**Rationale:** Per R1.3, this provides grading-first ordering discipline and structured output without the complexity of managing two separate skill invocations. Full context isolation (two API calls) is out of scope for this iteration.

**Tradeoff:** No context isolation between phases — the LLM could theoretically let Phase 2 reasoning bleed into Phase 1 scoring. Mitigated by placing Phase 1 output first and wrapping it in explicit `<phase1_output>` delimiters.

### TD2: Regex-Based Tag Parsing, Not XML Parser

**Decision:** Use regex to parse `<change>` tags from Phase 2 output.

**Rationale:** Per R4.3, `<change>` tags are embedded in Markdown content. A full XML parser would choke on the surrounding non-XML content. Regex patterns for matched open/close tags with attributes are straightforward and reliable for this constrained grammar.

**Patterns:**
- Open tag: `<change\s+dimension="([^"]+)"\s+rationale="([^"]*)">`
- Close tag: `</change>`

**Known constraint:** The regex requires `dimension` before `rationale`. The skill's Phase 2 instructions specify this exact attribute order. If the LLM produces attributes in a different order, the regex will not match, triggering tag validation failure in C5 and graceful degradation to Accept all / Reject per TD5. This is acceptable — the strict pattern keeps the regex simple and the degradation path handles deviations. **Testing note:** The plan should include a test scenario verifying that reversed attribute order correctly triggers C5 validation failure and the degradation path fires.

### TD3: Anchor-Based Merge (Not Diff/Patch)

**Decision:** Use 3-line context anchors for partial acceptance, not standard diff/patch.

**Rationale:** Per spec design note, XML tag parsing preserves dimension attribution inline. Standard diff/patch would require generating per-dimension patches and applying them with offset tracking — more complex in a Markdown-heavy context. Context anchors provide a natural, self-describing mechanism tied to the `<change>` tag structure.

**Tradeoff:** More fragile than diff/patch if the LLM drifts in unchanged regions. Mitigated by R2.5 drift detection — if drift is detected, partial acceptance is disabled entirely.

### TD4: Simultaneous Replacement Computation

**Decision:** All anchor replacements are computed against the original file simultaneously, not sequentially.

**Rationale:** Per R4.2, sequential application would cause line-offset drift — earlier replacements shift the line positions of later anchors. By computing all match positions against the original and applying them in order, we avoid this class of bugs.

**Implementation approach:** Collect all (start_line, end_line, replacement_content) tuples from anchor matching. Sort by start_line ascending. Verify no overlaps. Build output by interleaving original regions with replacements.

### TD6: LLM-Interpreted "Computation" — Honest Framing

**Decision:** Acknowledge that command-level operations (score calculation, tag parsing, drift detection) are LLM-interpreted instructions, not executable code. The improvement is structural decomposition, not deterministic guarantees.

**Rationale:** Both the skill and command are Markdown files interpreted by the same LLM. When the spec says "the command computes the score," the LLM still performs the arithmetic. The reliability gain comes from decomposition: asking the LLM to compute `round((22/27)*100)` as its sole focus (one line of arithmetic) is substantially more reliable than asking it to compute the score while also generating a 200-line rewritten file and a multi-section report.

**What this means for R3:** The spec requirement "the LLM MUST NOT compute the overall score" is satisfied in spirit — the score computation is structurally separated from the evaluation and rewriting phases. It is a focused, single-operation step in the command, not buried in a multi-concern God Prompt. The LLM performs the arithmetic, but in an isolated context where error is minimized.

**Tradeoff:** True deterministic computation would require an executable script (Python/bash) invoked via Bash tool. This was considered but rejected for this iteration because: (1) it introduces a dependency on the Bash tool being permitted, (2) it breaks the Markdown-only convention for commands, and (3) the reliability gain from structural decomposition is sufficient for the current use case (simple integer arithmetic on 9 values).

### TD5: Progressive Degradation

**Decision:** When validation fails at any point, degrade gracefully rather than aborting.

**Degradation chain:**
1. Phase 1/Phase 2 parse failure → STOP with error
2. Tag validation failure → disable "Accept some", allow "Accept all" / "Reject"
3. Drift detection → disable "Accept some", allow "Accept all" / "Reject"
4. Anchor match failure during "Accept some" → warn and degrade to "Accept all" / "Reject"

This ensures the user always gets the report and can always accept the full output even if partial acceptance isn't available.

---

## Interfaces

### I1: Skill Output Format

The skill produces a single output containing both phases, delimited by XML tags:

```
<phase1_output>
{
  "file": "path/to/target.md",
  "component_type": "skill",
  "guidelines_date": "2026-02-24",
  "staleness_warning": false,
  "dimensions": [
    {
      "name": "structure_compliance",
      "score": 3,
      "finding": "Matches macro-structure exactly",
      "suggestion": null,
      "auto_passed": false
    },
    ...8 more dimensions...
  ]
}
</phase1_output>

<phase2_output>
---
name: example-skill
description: ...
---

# Example Skill

<change dimension="token_economy" rationale="Remove redundant preamble">
Concise description here.
</change>

## Process

Unchanged content here (content-equivalent to original).

<change dimension="structure_compliance" rationale="Add numbered steps">
### Step 1: Read
...
</change>
</phase2_output>
```

### I2: Phase 1 JSON Schema

```json
{
  "file": "string (path to target file)",
  "component_type": "string (skill|agent|command)",
  "guidelines_date": "string (YYYY-MM-DD or 'unknown')",
  "staleness_warning": "boolean",
  "dimensions": [
    {
      "name": "string (dimension_name)",
      "score": "integer (1|2|3)",
      "finding": "string (one-line observation)",
      "suggestion": "string|null (null when score=3)",
      "auto_passed": "boolean"
    }
  ]
}
```

**Validation rules:**
- `dimensions` array must have exactly 9 entries
- `score` must be 1, 2, or 3
- `suggestion` must be non-null when `score` < 3
- `suggestion` must be null when `score` == 3
- `name` must be one of the 9 known dimension names

**Canonical dimension name mapping** (rubric name → JSON name):

| Rubric Name | JSON `name` Value |
|---|---|
| Structure compliance | `structure_compliance` |
| Token economy | `token_economy` |
| Description quality | `description_quality` |
| Persuasion strength | `persuasion_strength` |
| Technique currency | `technique_currency` |
| Prohibition clarity | `prohibition_clarity` |
| Example quality | `example_quality` |
| Progressive disclosure | `progressive_disclosure` |
| Context engineering | `context_engineering` |

### I3: Change Tag Format

```xml
<change dimension="{dim_name}" rationale="{reason}">
{modified content}
</change>
```

**Attributes:**
- `dimension`: required, non-empty. Single dimension name or comma-separated for overlapping. MUST appear before `rationale` — attribute order is significant for regex parsing (see TD2).
- `rationale`: required, can be empty string. MUST appear after `dimension`.

**Enforcement in SKILL.md (critical implementation detail):** Phase 2 instructions must include an explicit example of the tag format with `dimension` first (e.g., `<change dimension="token_economy" rationale="Remove redundant preamble">`) and a rule stating: "Attribute order is fixed: dimension, then rationale. Do not reorder." This is a named implementation item — not implied by the general rewrite task — because the regex pattern in TD2 silently fails if attributes are reordered.

**Constraints:**
- No nesting of `<change>` tags
- No overlapping tag pairs
- Tags only appear in `<phase2_output>` section
- Content between tags replaces the corresponding region of the original file

### I4: ChangeBlock Data Structure

Internal data structure used by the command after parsing Phase 2 output:

```
ChangeBlock {
  dimensions: string[]        # e.g. ["token_economy"] or ["token_economy", "structure_compliance"]
  rationale: string
  content: string             # text between <change> and </change>
  before_context: string[]    # up to 3 lines before <change> tag in Phase 2 output
  after_context: string[]     # up to 3 lines after </change> tag in Phase 2 output
  original_start_line: int?   # line in original file where before_context matches (set during anchor matching)
  original_end_line: int?     # line in original file where after_context matches (set during anchor matching)
}
```

### I5: Command Step Sequence

The command's new orchestration flow:

```
Step 1: Check for direct path argument
Step 2: Interactive component selection (unchanged)
Step 2.5: Read the target file and store as `original_content`. This is a fresh read using the resolved file path from Steps 1-2 — it cannot reuse any content from file selection because selection only identifies the path, not the full content. Needed for drift detection (Step 6b), merge (Step 8c/C9), and accept-all (Step 8c/C10). If file read fails, display error and STOP. Note: All subsequent steps MUST reference this data by the exact label `original_content` for consistency.
Step 3: Invoke skill (pass file path). Skill output appears in conversation context.
Step 4: Parse skill output
  4a: Extract <phase1_output> → Phase 1 JSON
  4b: Extract <phase2_output> → Phase 2 content
  4c: Validate Phase 1 JSON (9 dimensions, valid scores)
Step 5: Compute score = round((sum_of_scores / 27) * 100)
Step 6: Validate and detect issues
  6a: Validate <change> tag structure (R4.3)
  6b: Run drift detection (R2.5)
  6c: Check token budget (R5.3)
Step 7: Assemble report
Step 8: User approval
  8a: Determine available options based on validation state
  8b: Present AskUserQuestion (or auto-select in YOLO)
  8c: Execute selected action (Accept all / Accept some / Reject)
```

### I6: Skill Internal Structure

The skill's new step sequence:

```
Step 1: Detect component type (unchanged)
Step 2: Load references (unchanged)
Step 3: Check staleness (unchanged)
Phase 1: Grade
  - Evaluate 9 dimensions using scoring rubric behavioral anchors
  - Output JSON wrapped in <phase1_output> tags
  - Include guidelines_date and staleness_warning
Phase 2: Rewrite
  - Reference Phase 1 JSON via <grading_result> block
  - Generate complete rewritten file with <change> XML tags
  - Output wrapped in <phase2_output> tags
  - Preserve all text outside <change> tags content-equivalent to original (verified by command after normalizing trailing whitespace and file-boundary blank lines)
```

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Phase 2 ignores Phase 1 findings | Medium | High | `<grading_result>` XML block makes Phase 1 JSON explicit input to Phase 2 |
| `<change>` tags mangled by LLM | Low | Medium | Regex validation (C5) before merge; fallback to Accept all / Reject |
| Drift in unchanged regions | Medium | High | Drift detector (C6) disables partial acceptance; Phase 2 prompt explicitly instructs preservation |
| Context anchor non-unique match | Low | Medium | Degrade to Accept all / Reject with warning |
| Command becomes complex | Medium | Medium | Clear step numbering; each component (C3-C10) has single responsibility |
| Phase 1 JSON malformed | Low | High | Schema validation in C3; STOP with error if invalid |

---

## File Change Summary

| File | Change Description |
|------|-------------------|
| `plugins/iflow/skills/promptimize/SKILL.md` | Replace Steps 4-7 with Phase 1 (Grade) + Phase 2 (Rewrite) — see I6 for the authoritative step/phase structure. Remove score calculation. Replace HTML markers with XML `<change>` tags. Add `<phase1_output>` / `<phase2_output>` / `<grading_result>` delimiters. Remove YOLO Mode Overrides section (approval handling moved to command). Update PROHIBITED section — **remove:** (1) "NEVER write the improved version to disk without explicit user approval" (moved to command C8), (2) "NEVER skip Step 8 (approval)" (moved to command C8), (3) "NEVER apply changes that would push…over budget" (moved to command C7); **retain:** (4) "NEVER score a dimension without referencing the behavioral anchors from scoring-rubric.md" (still skill responsibility in Phase 1). |
| `plugins/iflow/commands/promptimize.md` | Replace Step 3 delegation with full orchestration: read original file (Step 2.5), parse output (C3), compute score (C4), validate tags (C5), detect drift (C6), assemble report (C7), handle approval with YOLO check (C8), merge engine (C9), accept-all handler (C10). Add PROHIBITED rules for approval-related and budget-related responsibilities absorbed from skill. |
| `plugins/iflow/skills/promptimize/references/scoring-rubric.md` | No changes. |
| `plugins/iflow/skills/promptimize/references/prompt-guidelines.md` | No changes. |
