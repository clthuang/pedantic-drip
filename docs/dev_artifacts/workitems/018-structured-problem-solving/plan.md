# Plan: Structured Problem-Solving Framework

## Implementation Order

```
Step 0: Validate Assumptions (risk reduction)
    ↓
Step 1: Create reference files ─────────────────┐
    ↓                                            │ (parallel)
Step 2: Create SKILL.md        Step 3: Modify    │
    ↓                          brainstorm-reviewer│
    ↓                              ↓              │
Step 4: Modify brainstorming SKILL.md ◄──────────┘
    ↓
Step 5: Verify line budgets and integration
    ↓
Step 6: End-to-end validation
```

## Design Divergences Noted

| Source | Says | Plan Follows | Rationale |
|---|---|---|---|
| PRD FR-9 | Use `mcp__mermaid__generate_mermaid_diagram` tool | Spec BS-5 / Design TD-1: inline Mermaid text | Spec-reviewer resolved this: no external tool dependency. MCP tool is optional enhancement only. |
| PRD UC-3 | "User can load framework at any point" | Spec/Design: Stage 1 Step 7 only | Handoff reviewer flagged. Spec is authoritative. Loop back via Stage 7 is the path. |
| Spec FR-4 | 7 options (5 types + Other + Skip) | Design TD-5: 6 explicit options if "Other" is built-in | Step 0a resolves: if "Other" is NOT built-in, add explicit 7th option to match FR-4. Either way, user sees 7 options. |
| Design Component 3 | Use `${CLAUDE_PLUGIN_ROOT}` for cross-skill Read | Base directory from system prompt injection | `${CLAUDE_PLUGIN_ROOT}` only works in hooks.json shell commands. Plan uses Base directory path which is injected into the skill invocation prompt. |

## Reviewer Warnings Addressed

| Warning | Where Addressed |
|---|---|
| Line budget tight (~474/500) | Step 5a: explicit line count with concrete trim plan |
| AskUserQuestion "Other" built-in behavior unverified | Step 0a: verify before implementation; explicit fallback |
| Loop-back should replace, not duplicate Structured Analysis | Step 4 Change 1: explicit delete-before-regenerate instruction |
| Stage 6 dispatch search target | Step 4 Change 2: uses exact line text `- prompt: PRD file path + request for JSON response` |
| Criteria table duplicated in two files | Step 1d + Step 3 Change 2: accepted trade-off, noted as maintenance risk |

---

## Step 0: Validate Assumptions

**Why this step:** Two design assumptions have never been tested in this codebase. Verifying them first avoids rework if either fails.

**Why first:** All subsequent steps depend on these assumptions. If cross-skill Read fails, Step 4's framework loading mechanism changes. If "Other" isn't built-in, Step 4's AskUserQuestion changes.

### 0a: AskUserQuestion "Other" Behavior — RESOLVED

**Result:** "Other" IS built-in. The AskUserQuestion tool description explicitly states: "Users will always be able to select 'Other' to provide custom text input." All 15+ AskUserQuestion invocations across the codebase omit an explicit "Other" option, relying on the built-in behavior. Feature 014 (secretary-agent) also documents this as a known platform feature.

**Decision:** Use 6 explicit options as designed (5 types + Skip). User sees 7 choices (6 + built-in Other). This satisfies both Design TD-5 and Spec FR-4.

### 0b: Cross-Skill Read Mechanism — RESEARCH COMPLETE, VERIFY AT RUNTIME

**Research findings:**
- `${CLAUDE_PLUGIN_ROOT}` is ONLY expanded in hooks.json shell commands (5 uses in hooks.json, 0 uses in any SKILL.md). It does NOT work in Read tool invocations.
- The system DOES inject `Base directory for this skill: {absolute path}` into the skill invocation prompt (confirmed from this session's system prompt).
- No existing skill has ever Read another skill's files. This is a novel pattern.
- All existing skills read their OWN references/ via relative markdown links (e.g., `[Name](references/file.md)`) — this pattern has 100% success rate.
- One cross-skill markdown link exists: root-cause-analysis links to `../systematic-debugging/SKILL.md` — but this is a documentation reference, not a proven Read tool invocation.

**Mechanism to test at runtime (Step 0b during implementation):**
1. When brainstorming skill executes, the Base directory is available (e.g., `~/.claude/plugins/cache/.../skills/brainstorming/`)
2. Derive sibling path: replace `skills/brainstorming` with `skills/structured-problem-solving`
3. Test Read tool with derived path
4. **If works:** Document as proven pattern for cross-skill reads
5. **If fails:** Use fallback below

**Fallback (likely path):** The structured-problem-solving skill is a standalone package. For brainstorming to use it, Step 7 instructions in brainstorming/SKILL.md simply tell the LLM to read the sibling skill using the Base directory path derivation. Since the LLM (not the SKILL.md file system) performs the Read, and the LLM has the Base directory in its context, it can construct the absolute path. This is how the LLM already resolves relative reference links — the mechanism is the LLM's own path resolution, not a file system mechanism.

**Key insight:** Skills don't "execute" in a directory — they provide instructions to the LLM. The LLM reads reference files because the SKILL.md text tells it to. Cross-skill Read works the same way: tell the LLM to derive the sibling path from its Base directory and Read it. The Read tool accepts absolute paths.

**Exit criteria:** Test during implementation Step 0b. Both outcomes are covered.

---

## Step 1: Create Reference Files

**Why this step:** Reference files contain all domain knowledge. SKILL.md (Step 2) links to them, and brainstorm-reviewer (Step 3) duplicates review criteria from them. Creating references first establishes the source of truth.

**Why before Steps 2-4:** SKILL.md cannot be written without reference files to link to. Brainstorming SKILL.md cannot describe the framework without knowing what the reference files contain.

**Order:** These 4 files have no interdependencies; create in any order (or parallel).

### 1a: `references/problem-types.md` (~180 lines)

**Create:** `plugins/iflow-dev/skills/structured-problem-solving/references/problem-types.md`

**Content:** Problem Type Taxonomy with 5 types, each having exactly 4 sub-sections:
1. Framing Approach (SCQA focus for this type)
2. Decomposition Method (MECE, issue tree, hypothesis tree, design space, or generic)
3. PRD Sections (domain-specific sections to add)
4. Review Criteria (3 boolean existence checks matching design taxonomy table)

Types: product/feature, technical/architecture, financial/business, research/scientific, creative/design.

**Source:** Design § Problem Type Taxonomy table + Component 2 § problem-types.md.

**Acceptance test:** File has 5 `## {type}` sections, each with 4 `### {subsection}` headings.

### 1b: `references/scqa-framing.md` (~90 lines)

**Create:** `plugins/iflow-dev/skills/structured-problem-solving/references/scqa-framing.md`

**Content:**
- Universal SCQA template (S/C/Q/A with field descriptions)
- Guidance per type (5 sections showing type-specific S/C/Q/A focus)
- The SCQA template is the hardcoded fallback when other reference files are missing (BS-3)

**Source:** Design § Component 2 § scqa-framing.md.

**Acceptance test:** File has `## Template` section + 5 type-specific guidance sections.

### 1c: `references/decomposition-methods.md` (~120 lines)

**Create:** `plugins/iflow-dev/skills/structured-problem-solving/references/decomposition-methods.md`

**Content:**
- MECE Decomposition (for product/feature, financial/business)
- Issue Tree (for technical/architecture)
- Hypothesis Tree (for research/scientific)
- Design Space Exploration (for creative/design)
- Generic Issue Tree (for "Other" types)
- Each method includes: description, tree format example, depth/breadth constraints (2-3 levels, 2-5 items/layer)

**Source:** Design § Component 2 § decomposition-methods.md + External Research (craftingcases.com constraints).

**Acceptance test:** File has 5 `## Method` sections, each with tree format example.

### 1d: `references/review-criteria-by-type.md` (~90 lines)

**Create:** `plugins/iflow-dev/skills/structured-problem-solving/references/review-criteria-by-type.md`

**Content:**
- Universal Criteria (5 items — matches brainstorm-reviewer's existing checklist)
- Type-Specific Criteria table (4 columns: Problem Type, Check 1, Check 2, Check 3)
- Criteria Descriptions (one paragraph per criterion explaining what "existence" means)

**Duplication note:** The criteria table is duplicated in brainstorm-reviewer.md (Step 3 Change 2). This is an accepted trade-off — the agent needs inline criteria for runtime use, and the reference file is the canonical source. If criteria change in the future, both files must be updated. Step 5b verifies they match.

**Source:** Design § Component 2 § review-criteria-by-type.md + Problem Type Taxonomy table.

**Acceptance test:** File has universal criteria list (5 items) + type-specific table (5 rows) + descriptions section.

**Step 1 exit criteria:** All 4 files created in `plugins/iflow-dev/skills/structured-problem-solving/references/`.

---

## Step 2: Create SKILL.md

**Why this step:** The structured-problem-solving skill is the core new component — it orchestrates SCQA framing and type-specific decomposition.

**Why after Step 1:** SKILL.md links to all 4 reference files via inline markdown links (e.g., `[scqa-framing.md](references/scqa-framing.md)`). The files must exist to verify the links.

**Why before Step 4:** Step 4 adds instructions to brainstorming SKILL.md to Read this file. The file must exist first.

**Can run parallel with Step 3:** Step 2 and Step 3 are independent — SKILL.md does not reference brainstorm-reviewer, and the reviewer does not reference SKILL.md.

**Create:** `plugins/iflow-dev/skills/structured-problem-solving/SKILL.md` (~80-120 lines)

**Content structure:**
```
---
name: structured-problem-solving
description: "Applies SCQA framing and type-specific decomposition to problems. Use when brainstorming skill loads the structured problem-solving framework in Stage 1 Step 7."
---

# Structured Problem-Solving

## Input
- problem_type, problem_statement, context (target_user, success_criteria, constraints, approaches)

## Process

### 1. SCQA Framing
- Reference: [scqa-framing.md](references/scqa-framing.md)
- Apply universal template; use type-specific guidance
- Output: Situation, Complication, Question, Answer

### 2. Type-Specific Decomposition
- Reference: [problem-types.md](references/problem-types.md)
- Reference: [decomposition-methods.md](references/decomposition-methods.md)
- Lookup type → select method → apply
- For "Other": use generic issue tree

### 3. Mind Map Generation
- Convert decomposition to Mermaid mindmap syntax
- Shapes: ((root)) for SCQA Question, [square] for categories, (rounded) for leaves
- Depth: 2-3 levels max
- Output: fenced ```mermaid code block (inline text, no MCP tool dependency)

## Output
Return ## Structured Analysis section with 4 subsections:
### Problem Type, ### SCQA Framing, ### Decomposition, ### Mind Map

## Graceful Degradation
- If reference files missing: apply SCQA framing only (hardcoded template below)
- Hardcoded SCQA fallback: {minimal S/C/Q/A template embedded here}
```

**Key constraints:**
- Must stay under 500 lines (target: ~100)
- Must NOT be invocable standalone — only via brainstorming Stage 1 Step 7
- Domain knowledge lives in references, not SKILL.md
- Inline markdown links to reference files (matches root-cause-analysis pattern)
- Description must contain "Use when" and be 50+ chars (validate.sh checks)

**Acceptance test:** File < 500 lines, has frontmatter with valid description, references all 4 files, includes hardcoded SCQA fallback.

---

## Step 3: Modify Brainstorm-Reviewer Agent

**Why this step:** The reviewer must understand problem types to apply domain-specific criteria (FR-6).

**Why independent of Steps 1-2:** The reviewer receives problem type via Task prompt text (Interface 2), not by reading skill files. Its criteria table is self-contained in its own markdown.

**Why before Step 4:** Step 4 changes the brainstorming dispatch prompt to send inline content + Problem Type. The reviewer must be ready to receive this format. Implementing the reviewer first means the dispatch format has a known target.

**Can run parallel with Step 2:** No dependency between them.

**File:** `plugins/iflow-dev/agents/brainstorm-reviewer.md`

**3 changes (matching design § Component 4):**

### Change 1: Add Input section (after existing line ~36)

Add `## Input` section describing the two inputs:
1. Brainstorm content (PRD markdown, passed inline in prompt)
2. Problem Type (optional, from `## Context` section of prompt). When present and not "none", apply type-specific criteria.

### Change 2: Replace Brainstorm Checklist (lines ~66-74)

Split existing 5-item checklist into:
- **Universal Criteria** (same 5 items, reformatted with checkbox markers)
- **Type-Specific Criteria** table (4 columns: Problem Type, Check 1, Check 2, Check 3 — 5 rows)
- Note for absent/none/custom types: universal only
- Existence check emphasis: check presence, not correctness (BS-4)

### Change 3: Update Review Process (lines ~91-100)

Add steps for:
1. Read the brainstorm file thoroughly
2. Parse Problem Type from `## Context` section (if provided)
3. Check universal criteria (5 items)
4. If known type: check 3 type-specific criteria
5. Assess overall readiness
6. Return structured feedback including which criteria set was applied

**Acceptance test:** Agent has Input section, split checklist with type table (5 rows), updated review process mentioning Problem Type parsing.

---

## Step 4: Modify Brainstorming SKILL.md

**Why this step:** This is the integration point — connecting the new skill (Step 2) and modified reviewer (Step 3) into the existing brainstorming workflow.

**Why last among implementation steps:** Depends on all three prior steps:
- Step 1: Reference file content informs what Step 7 reads
- Step 2: The skill file must exist for Step 7 to Read it
- Step 3: The reviewer's expected input format must be known for the dispatch change

**File:** `plugins/iflow-dev/skills/brainstorming/SKILL.md` (currently 399 lines)

**3 changes (matching design § Component 3):**

### Change 1: Insert Steps 6-8 in Stage 1 CLARIFY (~60 lines added)

**Insertion point:** After exit condition (line 62), before the `---` separator (line 64).

**Content to insert (abbreviated — full content in design § Component 3 Change 1):**

```
**After exit condition is satisfied, always run Steps 6-8 before proceeding to Stage 2:**

#### Step 6: Problem Type Classification

Present problem type options:
{AskUserQuestion with 6 or 7 options per Step 0a result}

**Handling "Other":** {per Step 0a: either built-in free text or explicit option}

#### Step 7: Optional Framework Loading

**If user selected a named type (not "Skip"):**
1. Derive sibling skill path from Base directory: replace `skills/brainstorming` with `skills/structured-problem-solving`
2. Read `{derived path}/SKILL.md` via Read tool
3. If file not found: warn "Structured problem-solving skill not found, skipping framework" → skip to Step 8
4. Read reference files: `{derived path}/references/scqa-framing.md`, `references/problem-types.md`, `references/decomposition-methods.md`
5. If reference files missing: warn, apply SCQA framing only
6. Apply SCQA framing to the problem
7. Apply type-specific decomposition (or generic issue tree for "Other")
8. Generate inline Mermaid mind map from decomposition

**If user selected "Other" (free text):**
- Apply SCQA framing (universal) + generic issue tree decomposition
- Store custom type string as-is

**If "Skip":**
- Set type to "none"
- Skip Step 7 body entirely

**Loop-back behavior:** If `## Structured Analysis` section already exists in the PRD (from a previous Stage 7 → Stage 1 loop), delete it entirely before re-running Steps 6-8. Do NOT duplicate.

#### Step 8: Store Problem Type
- Add `- Problem Type: {type}` to PRD Status section
```

### Change 2: Modify Stage 6 dispatch (~5 lines modified)

**Search target:** The exact line text `- prompt: PRD file path + request for JSON response` (including the leading `- `) near line 169.

**Replace with:** Inline prompt that passes full PRD content + Problem Type context:
```
- prompt: |
    Review this brainstorm for promotion readiness.

    ## PRD Content
    {full PRD markdown content — read from file before dispatch}

    ## Context
    Problem Type: {type from Step 8, or "none" if skipped/absent}

    Return your assessment as JSON:
    { "approved": true/false, "issues": [...], "summary": "..." }
```

### Change 3: Modify PRD Output Format (~15 lines added)

**In the Status section template (~line 258):** Add `- Problem Type: {type}` line.

**Between `## Research Summary` and `## Review History`:** Add conditional `## Structured Analysis` section template with 4 subsections (Problem Type, SCQA Framing, Decomposition, Mind Map).

**Conditional:** Section is ONLY included when Problem Type is not "none".

**Acceptance test:** File has Steps 6-8 in Stage 1, modified Stage 6 dispatch with inline content, PRD template with Problem Type and Structured Analysis.

---

## Step 5: Verify Line Budgets and Integration

**Why this step:** The design flagged line budget as tight (~474/500). This step catches overages before they cause validate.sh failures.

**Why after all implementation:** Line counts can only be verified after all edits are complete.

### 5a: Line Count Verification

| File | Budget | Action if Over |
|---|---|---|
| `structured-problem-solving/SKILL.md` | <500 lines | Move content to references |
| `brainstorming/SKILL.md` | <500 lines | See trim plan below |

**Critical:** Count actual lines of brainstorming SKILL.md. Design estimated ~474 with ~26 lines headroom.

**Trim plan if brainstorming SKILL.md exceeds 490 lines:**
1. First target: compress the AskUserQuestion example in Step 6 — replace full JSON with a summary + "See AskUserQuestion format in CLAUDE.md" (~10 lines saved)
2. Second target: compress Step 7's numbered list — replace detailed sub-steps with a concise paragraph referencing the structured-problem-solving SKILL.md for details (~15 lines saved)
3. Last resort: extract the entire Structured Analysis PRD template into a reference file `brainstorming/references/structured-analysis-template.md` (new file, not currently in plan)

### 5b: Cross-Reference Verification

1. Verify the cross-skill Read path resolves (per Step 0b mechanism)
2. Verify all 4 reference file paths resolve from structured-problem-solving SKILL.md
3. Verify brainstorm-reviewer criteria table matches review-criteria-by-type.md content exactly (same 5 rows, same 3 criteria per row)

### 5c: Backward Compatibility Check

1. Brainstorm-reviewer with no Problem Type in prompt → universal criteria only
2. PRD without Problem Type in Status → no Structured Analysis section expected
3. Skip selection → type "none", no framework content in PRD

**Exit criteria:** All files within budget, cross-references resolve, backward compat confirmed.

---

## Step 6: End-to-End Validation

**Why this step:** validate.sh is the project's quality gate. New skill must pass all checks.

**Why last:** Validation can only run after all files are in their final state.

### 6a: Run validate.sh

```bash
./validate.sh
```

Expect 0 errors, 0 warnings. Specific checks that apply to new/modified files:
- structured-problem-solving/SKILL.md: description >= 50 chars, contains "Use when", < 500 lines
- brainstorming/SKILL.md: < 500 lines
- brainstorm-reviewer.md: has model, color, example blocks in frontmatter

### 6b: Verify File Structure

```
plugins/iflow-dev/skills/structured-problem-solving/
├── SKILL.md                           (new, <500 lines)
└── references/
    ├── problem-types.md               (new, ~180 lines)
    ├── scqa-framing.md                (new, ~90 lines)
    ├── decomposition-methods.md       (new, ~120 lines)
    └── review-criteria-by-type.md     (new, ~90 lines)

plugins/iflow-dev/skills/brainstorming/
└── SKILL.md                           (modified, <500 lines)

plugins/iflow-dev/agents/
└── brainstorm-reviewer.md             (modified)
```

### 6c: Spot-Check Key Behaviors

1. **Steps 6-8 placement:** Verify they appear after exit condition, before Stage 2 separator
2. **Loop-back regeneration:** Verify explicit "delete existing Structured Analysis" instruction present
3. **"Other" handling:** Verify SCQA + generic issue tree path, universal review criteria only
4. **"Skip" handling:** Verify type "none", no framework content, no Structured Analysis
5. **Dispatch change:** Verify Stage 6 sends inline PRD content + `Problem Type:` line, not file path

---

## Dependencies

```
Step 0 ──→ Step 4 (AskUserQuestion option count and Read path mechanism)
Step 1 ──→ Step 2 (SKILL.md links to reference files)
Step 1 ──→ Step 4 (brainstorming references skill content from Step 1)
            Step 2 ──→ Step 4 (skill file must exist for Step 7 to Read it)
            Step 3 ──→ Step 4 (dispatch format must match reviewer's expected input)
Step 2,3,4 ──→ Step 5 (verification requires all files in final state)
Step 5 ──→ Step 6 (validation after verification)

Parallelizable:
- Step 2 and Step 3 can run in parallel (no mutual dependency)
- Step 1a, 1b, 1c, 1d can run in parallel (no interdependency)
```

## Files Changed

| File | Action | Step |
|---|---|---|
| `plugins/iflow-dev/skills/structured-problem-solving/references/problem-types.md` | Create | 1a |
| `plugins/iflow-dev/skills/structured-problem-solving/references/scqa-framing.md` | Create | 1b |
| `plugins/iflow-dev/skills/structured-problem-solving/references/decomposition-methods.md` | Create | 1c |
| `plugins/iflow-dev/skills/structured-problem-solving/references/review-criteria-by-type.md` | Create | 1d |
| `plugins/iflow-dev/skills/structured-problem-solving/SKILL.md` | Create | 2 |
| `plugins/iflow-dev/agents/brainstorm-reviewer.md` | Modify | 3 |
| `plugins/iflow-dev/skills/brainstorming/SKILL.md` | Modify | 4 |

**Total:** 5 new files, 2 modified files.

**Contingency file** (only if Step 5a trim plan exhausted): `plugins/iflow-dev/skills/brainstorming/references/structured-analysis-template.md` — extract PRD template to stay under 500 lines.
