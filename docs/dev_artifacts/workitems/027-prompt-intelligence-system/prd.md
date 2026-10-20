# PRD: Prompt Intelligence System

## Problem Statement

**Situation:** This plugin system contains 28+ agents, 28+ skills, and 24+ commands — all written as markdown prompt files. Prompt engineering best practices evolve rapidly across research papers, AI company blogs, and practitioner communities.

**Complication:** Plugin prompt files go stale relative to current best practices. There's no systematic way to (a) track what's changed in the field, (b) evaluate existing prompts against current guidelines, or (c) improve them. The existing `writing-skills` skill teaches authoring methodology but doesn't encode evolving external best practices or provide automated review.

**Question:** How do we keep plugin prompts aligned with the latest prompt engineering research and apply those insights systematically?

**Answer:** Two-component system: (1) a research pipeline that condenses the latest findings into a living guidelines document, and (2) a `promptimize` skill that reviews any plugin prompt against those guidelines and returns an improved version.

## Goals

1. **Living guidelines document** — A structured reference file that distills the latest prompt engineering best practices, updated weekly or on-demand
2. **Automated prompt review** — A skill that evaluates any plugin prompt (skill, agent, command) against the guidelines and produces a scored assessment with specific improvements
3. **Improved prompt returned** — The skill outputs an improved version of the prompt for user approval, not just critique
4. **Evidence-based** — Every guideline traces to a source (paper, official docs, empirical finding)

## Non-Goals

- General-purpose LLM prompt optimization (only plugin prompts: skills, agents, commands)
- Real-time monitoring of social media (batch research, not streaming)
- Automatic rewriting without approval (always returns for user review)
- Replacing the `writing-skills` skill (complements it — writing-skills teaches authoring methodology; promptimize evaluates against evolving best practices)

## User Stories

1. **As a plugin author**, I want to run `/iflow-dev:promptimize plugins/iflow-dev/skills/brainstorming/SKILL.md` and get a scored report showing which aspects of my skill prompt are stale or suboptimal, so I can improve it with evidence-backed suggestions.

2. **As a plugin maintainer**, I want to run `/iflow-dev:refresh-prompt-guidelines` to pull the latest prompt engineering research into a structured guidelines document, so that future promptimize reviews reflect current best practices.

3. **As a new contributor**, I want to run promptimize on a skill I just wrote to check if it follows established patterns (structure, token budget, description quality), so I get immediate feedback without needing to read all the reference docs.

4. **As a quality-conscious developer**, I want promptimize to show me a diff between my original prompt and the improved version with rationale per change, so I can selectively accept improvements rather than blindly replacing my work.

## Research Evidence

### What Works in Prompt Engineering (Current Consensus)

Evidence from The Prompt Report (1,500+ papers surveyed) [arxiv:2406.06608], Anthropic's official guide, OpenAI's GPT-4.1 Prompting Guide, and the "context engineering" framing endorsed by Karpathy, Willison, and Gartner:

| Technique | Evidence Strength | Source |
|-----------|------------------|--------|
| Few-shot Chain-of-Thought | Highest-performing across benchmarks | The Prompt Report |
| XML tags for structure (Claude) | Recommended in official docs; separates instructions from context | Anthropic prompt engineering guide (docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags) |
| Decomposition (break complex tasks) | Strong across all models | The Prompt Report |
| Self-criticism / reflection | Strong for iterative tasks | The Prompt Report |
| Providing additional context | "Massively underrated" | The Prompt Report |
| Example quality (quantity, order, format) | Up to 90% accuracy improvement from small tweaks | The Prompt Report |
| Instruction placement (top AND bottom) | ~4% benchmark improvement for agentic tasks | OpenAI GPT-4.1 Guide |
| Role prompting for correctness | Weak — affects tone only, not accuracy | The Prompt Report |
| Self-consistency | Underperforms despite popularity | The Prompt Report |

### Existing Plugin Prompt Patterns (From Codebase Analysis)

The codebase explorer identified consistent structural patterns:

**Skills:** Frontmatter → YOLO overrides → Process (numbered steps with bold semantic labels) → Output format → Error handling → Self-check → PROHIBITED section. Use response-action tables for conditionals, quality-gate loops for review stages.

**Agents:** Frontmatter (with tools/model/color) → Two `<example>` blocks → Single-question focus → Input → Output format (JSON schema) → Process → MUST NOT section. Universal blocker/warning/suggestion severity.

**Commands:** Frontmatter (description + argument-hint) → Conditional routing → Delegation to skills/agents → Completion.

**Existing quality standards:**
- `component-authoring.md`: token budget (<500 lines, <5000 tokens), description quality, activation rates
- `anthropic-best-practices.md`: token economy, progressive disclosure, degrees-of-freedom matching
- `persuasion-principles.md`: Authority, Commitment, Social Proof, Loss Aversion, Unity

### Prompt Optimization Approaches

| Approach | How It Works | Applicability |
|----------|-------------|---------------|
| DSPy (Stanford) | Programmatic — Python signatures + metrics + optimizers | Not applicable (our prompts are markdown files, not code) |
| OPRO (DeepMind) | LLM-as-optimizer — give prior attempts + scores, generate new | Partially applicable — could score prompts against guidelines |
| promptfoo | Evaluation framework — test prompts against configs | Not applicable (CI/CD testing tool, not prompt improvement) |
| LLM-as-reviewer | Feed prompt + guidelines → get critique + rewrite | Best fit — matches our existing reviewer agent pattern |

**Selected approach:** LLM-as-reviewer with structured guidelines. This aligns with the existing reviewer agent pattern in the codebase and doesn't require external tools or APIs beyond what Claude Code already provides.

### Research Aggregation Patterns

**Best-in-class model:** Sebastian Raschka's "Ahead of AI" — thematic organization + author commentary + code examples + regular cadence. Outperforms raw paper dumps or news aggregation. Key differentiator: curation with synthesis, not just collection.

**Applicable sources for prompt engineering:**
- **Tier 1 (official):** Anthropic prompt engineering docs, OpenAI Cookbook, Google AI prompting guides
- **Tier 2 (research):** arxiv papers on prompting, The Prompt Report updates, DSPy research
- **Tier 3 (practitioners):** Riley Goodside experiments, Simon Willison blog, Ethan Mollick threads, Lilian Weng posts

## Proposed Solution

### Component 1: Research Pipeline (`/iflow-dev:refresh-prompt-guidelines`)

A command that scouts, summarizes, and condenses prompt engineering best practices into a structured guidelines document.

**Execution model:** Manual command invocation. The command delegates to the `internet-researcher` agent for web scouting, then performs synthesis and file updates in the main session.

**Bootstrapping strategy:** The initial `prompt-guidelines.md` is seeded during implementation from the research evidence already gathered in this PRD plus the existing reference files (`anthropic-best-practices.md`, `component-authoring.md`, `persuasion-principles.md`). This means the system works immediately without requiring WebSearch — the first `/refresh-prompt-guidelines` run enriches an already-useful baseline rather than starting from nothing.

**WebSearch fallback:** If WebSearch is unavailable (network restrictions, tool not permitted), the command skips the Scout step and proceeds with existing guidelines. It logs a warning ("WebSearch unavailable — guidelines not refreshed from external sources") and still runs the Diff/Synthesize steps against any user-provided URLs or manually pasted content.

**Process:**
1. **Scout** — Delegate to `internet-researcher` agent: WebSearch for recent prompt engineering developments from Tier 1-3 sources. If WebSearch unavailable, skip with warning.
2. **Read current guidelines** — Load existing `references/prompt-guidelines.md`
3. **Diff** — Identify what's new vs. what's already captured
4. **Synthesize** — Condense new findings into guideline entries with source citations
5. **Update** — Write updated guidelines file
6. **Changelog** — Append dated summary of what changed to a changelog section within the guidelines

**Guidelines document structure:**
```markdown
# Prompt Engineering Guidelines

## Last Updated: YYYY-MM-DD

## Core Principles
[Ranked by evidence strength, each with source citation]

## Plugin-Specific Patterns
### Skills
[Best practices specific to SKILL.md files]
### Agents
[Best practices specific to agent .md files]
### Commands
[Best practices specific to command .md files]

## Techniques by Evidence Tier
### Strong Evidence
[Techniques with multiple confirming sources]
### Moderate Evidence
[Techniques with single-source or limited evidence]
### Emerging / Experimental
[Recent findings not yet widely validated]

## Anti-Patterns
[Things to avoid, with evidence for why]

## Update Log
| Date | Changes | Sources |
|------|---------|---------|
```

**Location:** `plugins/iflow-dev/skills/promptimize/references/prompt-guidelines.md`

### Component 2: Promptimize Skill

A skill that reviews any plugin prompt against the guidelines and returns an improved version.

**Invocation:** `/iflow-dev:promptimize <file-path>` or `/iflow-dev:promptimize` (prompts for file selection). The `promptimize.md` command acts as a thin dispatcher, accepting the file path argument and delegating immediately to the promptimize skill.

**Process:**
1. **Detect component type** — Read the target file, identify skill/agent/command from structure and location
2. **Load guidelines** — Read `references/prompt-guidelines.md` + type-specific section
3. **Load existing standards** — Read `component-authoring.md` quality criteria (token budget, description quality, structural requirements)
4. **Evaluate** — Score the prompt on each guideline dimension
5. **Generate improvements** — Produce specific, actionable changes
6. **Present diff** — Show original vs. improved with rationale per change
7. **User approval** — AskUserQuestion: Accept all / Accept some / Reject / View details

**Evaluation dimensions (from research + existing standards):**

| Dimension | What It Measures | Source |
|-----------|-----------------|--------|
| Structure compliance | Follows component-type macro-structure | Codebase patterns |
| Token economy | Within budget, no redundant content | anthropic-best-practices.md |
| Description quality | Trigger phrases, activation rate potential | component-authoring.md |
| Persuasion strength | Uses Authority, Commitment, Loss Aversion effectively | persuasion-principles.md |
| Technique currency | Uses current best practices (XML tags, few-shot, CoT) | prompt-guidelines.md |
| Prohibition clarity | Hard constraints are unambiguous and specific | Codebase patterns |
| Example quality | Examples are concrete, minimal, representative | The Prompt Report |
| Progressive disclosure | Reference files for detail, SKILL.md for overview | anthropic-best-practices.md |
| Context engineering | Appropriate tool restrictions, minimal context passing | Anthropic context engineering blog |

**Scoring methodology:** Each of the 9 dimensions is scored pass/partial/fail (3/2/1). The overall score is `(sum / 27) * 100`, rounded to nearest integer. The 70% threshold (score 19/27 = ~70) means at least 2 dimensions scored "fail" or 4+ scored "partial." Only dimensions scoring "fail" or "partial" generate suggestions in the report. This keeps the rubric simple and deterministic — the LLM evaluates each dimension against concrete criteria rather than assigning arbitrary percentages.

**Decision rule — promptimize vs. writing-skills:** Use `writing-skills` when *creating* a new component from scratch (it teaches structure, progressive disclosure, TDD for docs). Use `promptimize` when *evaluating* an existing component against current best practices (it scores, critiques, and rewrites). If a component doesn't exist yet, `writing-skills` is the right tool. If it exists and you want to improve it, `promptimize` is the right tool.

**Output format:**
```markdown
## Promptimize Report: {filename}

**Component type:** Skill | Agent | Command
**Overall score:** {score}/100
**Guidelines version:** {date}

### Issues Found

| # | Severity | Dimension | Finding | Suggestion |
|---|----------|-----------|---------|------------|
| 1 | blocker  | Token economy | SKILL.md is 6,200 tokens (budget: 5,000) | Move technique details to references/ |
| 2 | warning  | Persuasion | Uses "should" instead of "MUST" in constraints | Replace weak language with definitive |
| 3 | suggestion | Technique currency | Missing XML structure tags | Add <context>, <instructions> sections |

### Improved Version

[Full rewritten prompt with changes highlighted via inline comments]
```

### File Structure

```
plugins/iflow-dev/
├── commands/
│   ├── promptimize.md              # Command: routes to skill
│   └── refresh-prompt-guidelines.md # Command: runs research pipeline
├── skills/
│   └── promptimize/
│       ├── SKILL.md                 # Core review + improvement logic
│       └── references/
│           └── prompt-guidelines.md # Living guidelines (updated by pipeline)
```

## Strategic Analysis

### Pre-Mortem: What Could Kill This

1. **Guidelines go stale and nobody runs refresh** — The system works only if someone periodically runs the research pipeline. Mitigation: the promptimize skill shows the guidelines' last-updated date in every report and warns if >30 days old, creating natural pressure to refresh.

2. **Over-optimization makes prompts worse** — Blindly applying "best practices" to a prompt that works well could degrade it. Mitigation: the skill always returns for user approval, never auto-writes. The pass/partial/fail rubric focuses on clear deficiencies, not aesthetic preferences.

3. **Prompt engineering consensus shifts faster than guidelines** — A major model update could invalidate guidelines. Mitigation: guidelines are versioned with dates and sources. The tiered evidence system means only well-established practices get "strong evidence" status.

### Adoption Friction

| Friction Point | Severity | Mitigation |
|----------------|----------|------------|
| Must remember to run `/refresh-prompt-guidelines` | Medium | Staleness warning in every promptimize report creates pull |
| Must provide file path to promptimize | Low | Supports both explicit path and interactive file selection via AskUserQuestion |
| Guidelines file could grow unwieldy | Low | Structured sections with evidence tiers; old/superseded entries move to changelog |

### Flywheel Effect

`refresh-prompt-guidelines` improves guidelines → `promptimize` produces better reviews → improved prompts raise the quality bar → higher bar motivates more frequent guideline refresh. Each component amplifies the other.

### Feasibility Assessment

| Factor | Assessment |
|--------|-----------|
| Technical complexity | Low — Both components are standard skill/command patterns already proven in this codebase |
| External dependencies | Low — WebSearch is optional (bootstrapped from existing research). No APIs, databases, or services required |
| Effort estimate | Small — 4 files to create (2 commands, 1 skill, 1 seeded reference file) |
| Risk of scope creep | Medium — Temptation to add batch mode, CI integration, model-specific sections. PRD explicitly defers these |

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Guidelines drift from reality (stale sources) | Medium | High | Changelog section tracks freshness; staleness warning if >30 days old |
| Over-optimization (rewriting working prompts unnecessarily) | Medium | Medium | Score threshold — only suggest changes for dimensions scoring partial or fail (matching the scoring methodology's 70% threshold) |
| Research pipeline returns low-quality results | Low | Medium | Tier system prioritizes official docs over social media; human reviews guidelines |
| Token budget exceeded by guidelines file | Low | Low | Guidelines loaded on-demand as reference file, not in SKILL.md |
| Conflicting advice between sources | Medium | Medium | Evidence tier system — strong evidence overrides emerging findings |

## Success Criteria

1. `prompt-guidelines.md` contains at least 15 evidence-backed guidelines with source citations
2. Running `/iflow-dev:promptimize` on any skill/agent/command produces a scored report within 2 minutes
3. Improved versions maintain structural compliance (validate.sh still passes)
4. At least 3 of 9 evaluation dimensions produce actionable findings on a typical prompt
5. Guidelines can be refreshed in <5 minutes via the research command

## Scope

**In scope:**
- Guidelines research command
- Promptimize skill with review + improvement
- Promptimize command (thin dispatcher)
- Initial guidelines document seeded from research findings
- Support for all three component types (skill, agent, command)

**Out of scope:**
- Automated scheduled execution (GitHub Actions cron — future enhancement)
- Batch mode (review all prompts at once — future enhancement)
- Integration with CI/CD (promptfoo-style — future enhancement)
- Cross-model optimization (Claude-only for now)

## Open Questions (Resolved)

1. **Write directly vs. sidecar?** → Present improved version inline in the report. User uses AskUserQuestion to accept/reject. If accepted, write directly to original file. No sidecar — it would create file bloat and cleanup burden.
2. **Dry-run flag?** → No. The report always shows the assessment. The improved version is always generated (it's the main value). User approval gate prevents unwanted writes.
3. **Model-specific sections?** → Assume latest model only. This is private tooling running on a single model. Model-specific sections add complexity for a scenario that doesn't exist.
