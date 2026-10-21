# Specification: Prompt Intelligence System

## Problem Statement

Plugin prompt files (28+ skills, 28+ agents, 24+ commands) go stale relative to evolving prompt engineering best practices, with no systematic way to track changes in the field, evaluate existing prompts, or improve them.

## Definitions

**Source Tiers:**
- **Tier 1 (official):** Anthropic prompt engineering docs, OpenAI Cookbook/prompting guides, Google AI prompting guides
- **Tier 2 (research):** arxiv papers on prompting, The Prompt Report, DSPy research
- **Tier 3 (practitioners):** Riley Goodside experiments, Simon Willison blog, Ethan Mollick threads, Lilian Weng posts

**Component detection patterns:**
- Skill: path matches `skills/*/SKILL.md`
- Agent: path matches `agents/*.md`
- Command: path matches `commands/*.md`

**Dimension-to-severity mapping:** fail = blocker, partial = warning. Dimensions scoring pass do not appear in the issues table.

## Success Criteria

- [ ] A living `prompt-guidelines.md` reference file exists with at least 15 evidence-backed guidelines, each citing a source
- [ ] `/iflow-dev:promptimize <file-path>` produces a scored report (pass/partial/fail across 9 dimensions) and an improved version for any skill, agent, or command file
- [ ] Promptimize report generation completes within 2 minutes for a single plugin prompt file (wall-clock time, measured from command invocation to report display)
- [ ] `/iflow-dev:refresh-prompt-guidelines` updates the guidelines document from Tier 1-3 sources via `internet-researcher` agent, with WebSearch fallback (skip with warning if unavailable)
- [ ] Running `/iflow-dev:refresh-prompt-guidelines` completes within 5 minutes (wall-clock time, assuming WebSearch is available)
- [ ] Improved prompts maintain structural compliance — users are advised to run `validate.sh` after accepting changes
- [ ] At least 3 of 9 evaluation dimensions produce actionable findings on a typical plugin prompt
- [ ] Scoring rubric verified: running promptimize on 3 real prompts of varying quality produces overall scores spanning at least 20 percentage points, and at least 2 different dimensions receive different scores across the 3 prompts

## Scope

### In Scope

- `promptimize` skill (SKILL.md + references/prompt-guidelines.md) — reviews a single plugin prompt against guidelines, scores 9 dimensions, generates improved version
- `promptimize` command — thin dispatcher accepting file path argument, delegating to skill
- `refresh-prompt-guidelines` command — delegates to `internet-researcher` for web scouting, then synthesizes findings into guidelines document
- Initial `prompt-guidelines.md` seeded from PRD research evidence + existing reference files (`anthropic-best-practices.md`, `component-authoring.md`, `persuasion-principles.md`). Structure follows PRD: Core Principles, Plugin-Specific Patterns (Skills/Agents/Commands), Techniques by Evidence Tier (Strong/Moderate/Emerging), Anti-Patterns, Update Log.
- Support for all three component types: skill, agent, command

### Out of Scope

- Automated scheduled execution (GitHub Actions cron)
- Batch mode (reviewing all prompts at once)
- CI/CD integration (promptfoo-style testing)
- Cross-model optimization (Claude-only)
- Replacing `writing-skills` skill (promptimize evaluates existing prompts; writing-skills teaches creation)

## Acceptance Criteria

### Promptimize Skill — Review and Score

- Given a path to any plugin skill SKILL.md file
- When `/iflow-dev:promptimize <path>` is invoked
- Then the skill detects component type as "skill", loads prompt-guidelines.md (which includes distilled component-authoring rules) and scoring-rubric.md, scores 9 dimensions (structure compliance, token economy, description quality, persuasion strength, technique currency, prohibition clarity, example quality, progressive disclosure, context engineering) as pass/partial/fail, and outputs a report with overall score (sum/27 * 100). The overall score is informational — the per-dimension pass/partial/fail is the actionable signal.

### Promptimize Skill — Improved Version

- Given a promptimize report with at least one dimension scoring partial or fail
- When the report is generated
- Then an improved version of the full prompt is presented with `<!-- CHANGE: {dimension} - {rationale} -->` inline comments before each modified section, and the user is presented with AskUserQuestion: Accept all / Accept some / Reject

### Promptimize Skill — Write on Accept

- Given the user selects "Accept all"
- When the approval is confirmed
- Then the improved version is written directly to the original file

- Given the user selects "Accept some"
- When the approval is confirmed
- Then the skill presents each changed section as a separate AskUserQuestion choice (multiSelect: true), where each option shows the dimension name and a one-line summary of the change. Each changed section corresponds to one dimension's modification — the prompt region touched by that dimension's improvement is one selectable unit. Selected changes are applied to the original file; unselected sections retain the original text.

### Promptimize Skill — Agent and Command Support

- Given a path to an agent .md file or command .md file
- When `/iflow-dev:promptimize <path>` is invoked
- Then the skill detects the correct component type from file location (see Definitions) and applies type-specific evaluation (agent patterns: frontmatter, examples, MUST NOT; command patterns: frontmatter, routing, delegation)

### Promptimize Skill — Invalid Path

- Given a file path that does not match any known component location pattern (skills/*/SKILL.md, agents/*.md, commands/*.md)
- When `/iflow-dev:promptimize <path>` is invoked
- Then the skill displays an error message listing valid path patterns and exits without scoring

### Promptimize Skill — Staleness Warning

- Given `prompt-guidelines.md` has a "Last Updated" date older than 30 days
- When a promptimize report is generated
- Then the report header includes a warning: "Guidelines last updated {date} — consider running /refresh-prompt-guidelines"

### Promptimize Command — Dispatcher

- Given no file path argument is provided
- When `/iflow-dev:promptimize` is invoked
- Then the command first asks the user to select a component type (Skill / Agent / Command) via AskUserQuestion, then globs the corresponding directory and presents matching files as a second AskUserQuestion. If no files are found for the selected type, display an informational message. After selection, delegate to the promptimize skill with the chosen path.

### Refresh Guidelines — Happy Path

- Given WebSearch is available
- When `/iflow-dev:refresh-prompt-guidelines` is invoked
- Then the command delegates to `internet-researcher` with a detailed prompt specifying Tier 1-3 sources and prompt-engineering-specific search terms, deduplicates results against existing guidelines by content similarity (overlapping findings are merged, new findings are appended), synthesizes new entries with citations, writes updated guidelines, and appends a dated changelog entry

### Refresh Guidelines — WebSearch Unavailable

- Given WebSearch is unavailable or denied by the user
- When `/iflow-dev:refresh-prompt-guidelines` is invoked
- Then the command logs a warning ("WebSearch unavailable — guidelines not refreshed from external sources"), skips the Scout step, and proceeds with existing guidelines (no crash, no empty file)

### Scoring Methodology

- Given any plugin prompt is evaluated
- When scores are calculated
- Then each of the 9 dimensions is scored pass (3) / partial (2) / fail (1), overall score = (sum / 27) * 100 rounded to nearest integer, and only dimensions scoring partial or fail generate suggestions in the report (fail = blocker severity, partial = warning severity)

## Feasibility Assessment

### Assessment Approach
1. **First Principles** — Both components are standard skill/command patterns. The skill reads files, loads references, evaluates, and outputs. The command delegates to an existing agent (`internet-researcher`) and writes a file.
2. **Codebase Evidence** — Existing reviewer agents (spec-reviewer, design-reviewer, code-quality-reviewer) follow the same LLM-as-reviewer pattern. Reference file loading is proven in skills like `brainstorming/references/`. Component authoring guide documents the exact patterns at `docs/dev_guides/component-authoring.md`.
3. **External Evidence** — WebSearch tool already used successfully by `internet-researcher` agent in brainstorming Stage 2.

### Assessment
**Overall:** Confirmed
**Reasoning:** Both components use well-established patterns in the codebase (skill with references, command delegating to agent, LLM-as-reviewer). No new infrastructure, APIs, or tools required. The initial guidelines can be seeded from research already gathered in the PRD.
**Key Assumptions:**
- `internet-researcher` agent can effectively scout prompt engineering content from Tier 1-3 sources — Status: Verified (used successfully in brainstorm Stage 2 research)
- 9-dimension scoring rubric produces meaningful differentiation — Status: Needs verification during implementation (verified if 3 real prompts produce scores spanning 20+ percentage points with at least 2 dimensions differing; if not, collapse similar dimensions before shipping)
- Guidelines file stays under token budget as a reference file — Status: Likely (reference files are loaded on-demand, not embedded in SKILL.md)
**Open Risks:** Scoring rubric may need calibration after testing on real prompts.

## Dependencies

- `internet-researcher` agent — used by refresh-prompt-guidelines command for web scouting. Note: this agent is currently scoped for brainstorm research. The refresh command must provide a detailed query prompt specifying Tier 1-3 sources and prompt-engineering-specific search terms. No changes to the agent needed (its tools are sufficient).
- `component-authoring.md` at `docs/dev_guides/component-authoring.md` — relevant rules distilled into prompt-guidelines.md at seed time (not loaded at runtime)
- Existing reference files: `anthropic-best-practices.md`, `component-authoring.md`, `persuasion-principles.md` — used to seed initial guidelines

## Open Questions

- None — all open questions resolved in PRD
