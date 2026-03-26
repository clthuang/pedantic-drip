# PRD: Reviewer Token Efficiency

## Status
- Created: 2026-03-27
- Status: Draft
- Problem Type: Optimization
- Backlog: #00033

## Problem Statement
The reviewer dispatch pattern in 5 command files (specify, design, create-plan, create-tasks, implement) embeds full artifact content in fresh dispatch prompts. For example, spec-reviewer's fresh dispatch includes `{content of spec.md}` — the entire spec inlined in the prompt. The reviewer then reads the same file via its Read tool, doubling token usage. This happens on every iteration 1 dispatch and every context-compaction fallback.

### Evidence
- `specify.md` line 76: `{content of spec.md}` embedded in spec-reviewer prompt
- `implement.md` line 332: `{list of files with code}` embedded in implementation-reviewer prompt
- `implement.md` line 509, 672: `{list of files}` embedded in quality and security reviewer prompts
- Resumed dispatches (I2 template) already avoid this — they send only the delta and tell reviewers "You already have the upstream artifacts in context from your prior review"
- The "Required Artifacts" section in every fresh dispatch already instructs reviewers to read files: "You MUST read the following files before beginning your review"

## Goals
1. Fresh reviewer dispatches provide file PATHS, not file CONTENT
2. Reviewers read files themselves via Read tool (they already do this — the pattern is established)
3. Reduce fresh dispatch prompt size by 50-80% (artifact content is typically the largest part)
4. No behavior change — reviewers still read and validate the same artifacts

## Requirements

### Functional
- FR-1: In all 5 command files (specify.md, design.md, create-plan.md, create-tasks.md, implement.md), replace `{content of X.md}` placeholders in fresh dispatch (I1-R4) prompts with file path references in the "Required Artifacts" section
- FR-2: The "Required Artifacts" section already lists files — just remove the duplicate `## Spec/Design/Plan/Tasks (what you're reviewing) {content}` section from the prompt template
- FR-3: For implement.md: replace `{list of files with code}` and `{list of files}` with `## Implementation Files\n{newline-separated file paths}` section. For quality-reviewer and security-reviewer, add this section below their existing Required Artifacts. Update the Required Artifacts instruction to include: "Also read files listed under Implementation Files below."
- FR-4: No code change needed — `iteration1_prompt_length` is measured dynamically at dispatch time and will naturally shrink when content is removed.
- FR-5: No changes to resumed dispatch (I2) or final validation (I2-FV) templates — they already use deltas

### Non-Functional
- NFR-1: Reviewer behavior must not change — same files read, same validation performed
- NFR-2: Fallback detection (I9 "Files read:" pattern) remains unchanged — it already checks the reviewer's response, not the prompt

## Files to Change
| File | Change |
|------|--------|
| `plugins/pd/commands/specify.md` | Remove `{content of spec.md}` from spec-reviewer fresh dispatch |
| `plugins/pd/commands/design.md` | Remove `{content of design.md}` from design-reviewer fresh dispatch |
| `plugins/pd/commands/create-plan.md` | Remove `{content of plan.md}` from plan-reviewer fresh dispatch |
| `plugins/pd/commands/create-tasks.md` | Remove `{content of tasks.md}` from task-reviewer fresh dispatch |
| `plugins/pd/commands/implement.md` | Remove file content/lists from implementation, quality, and security reviewer fresh dispatches |

## Decision
Pure deletion. Remove embedded content from fresh dispatch prompts. Reviewers already have Read tool access and the Required Artifacts section already instructs them to read files. The content embedding was a belt-and-suspenders pattern that's now just waste.
