# Design: Prompt Intelligence System

## Prior Art Research

### Codebase Patterns

| Pattern | Source | Applicability |
|---------|--------|---------------|
| Reviewer agent canonical shape | spec-reviewer, design-reviewer, code-quality-reviewer | Reference for output format — but promptimize is a skill, not an agent |
| code-quality-reviewer adds `strengths` array | code-quality-reviewer.md | Adopt for promptimize report — affirm good patterns before listing issues |
| Command-to-agent delegation via Task tool | design.md, specify.md commands | Pattern for refresh-prompt-guidelines → internet-researcher |
| File/type selection with AskUserQuestion | review-ds-code.md, review-ds-analysis.md | Pattern for promptimize command when no path provided |
| Progressive disclosure via references/ | spotting-ds-analysis-pitfalls, writing-skills | Pattern for SKILL.md + references/prompt-guidelines.md |
| internet-researcher JSON interface | internet-researcher.md | Returns `{findings: [{finding, source, relevance}], no_findings_reason}` |

### External Research

| Finding | Source | Design Impact |
|---------|--------|---------------|
| VS Code Prompt Linter: 5 rule categories (Role Clarity, Logical Conflicts, I/O Examples, Instruction Complexity, Emphasis Overuse) | VS Code Marketplace | Validates multi-dimension approach; our 9 dimensions are more comprehensive |
| GPTLint: rules as declarative markdown files evaluated by LLM | github.com/gptlint | Validates our approach — guidelines file IS the rule set |
| Rubric best practice: 0-3 scales with behavioral anchors, 3-5 dimensions max for low variance | PulseGeek, PEARL framework | Our 9 dimensions may cause reviewer variance. Mitigate with concrete behavioral anchors per dimension per score level |
| Promptfoo LLM Rubric: returns `{reason, pass, score}` JSON | promptfoo.dev | Confirms our pass/partial/fail + reason pattern |
| Anthropic Claude 4.x: emphasis overuse anti-pattern, positive framing preferred | Anthropic docs | Must encode in guidelines — contradicts older "use MUST/CRITICAL" advice |
| No existing tool reviews markdown system prompts with rationale output | Gap analysis | Confirms this is novel — no off-the-shelf solution to adopt |
| Microsoft PromptWizard: mutate → critique → refine cycle | github.com/microsoft/PromptWizard | Our single-pass review + rewrite is simpler and sufficient for the use case |

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                 User Interface                    │
│                                                   │
│  /promptimize <path>    /refresh-prompt-guidelines │
│        │                         │                │
│   promptimize.md            refresh-prompt-        │
│   (command)                 guidelines.md          │
│        │                    (command)               │
│        ▼                         │                │
│  ┌───────────┐              ┌────▼──────┐         │
│  │promptimize│              │ internet- │         │
│  │  SKILL.md │              │ researcher│         │
│  │(main      │              │  (agent)  │         │
│  │ session)  │              └────┬──────┘         │
│  └─────┬─────┘                   │                │
│        │ reads                   │ returns        │
│        ▼                         ▼                │
│  ┌─────────────────────────────────────────┐      │
│  │   references/prompt-guidelines.md        │      │
│  │   (living guidelines document)           │      │
│  └─────────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

Note: The skill no longer reads `docs/dev_guides/component-authoring.md` at runtime. Relevant structural and quality criteria from component-authoring.md are distilled into `prompt-guidelines.md` during the initial seed (see "Plugin-Specific Patterns" section of the guidelines). This eliminates the cross-directory dependency.

### Components

| Component | Type | Responsibility |
|-----------|------|----------------|
| `commands/promptimize.md` | Command | Thin dispatcher: parse args or file selection UX, invoke promptimize skill |
| `skills/promptimize/SKILL.md` | Skill | Core logic: detect type, load guidelines, score 9 dimensions, generate improved version, present report, handle user approval |
| `skills/promptimize/references/prompt-guidelines.md` | Reference file | Living guidelines document, seeded at build time, updated by refresh command. Contains ALL evaluation criteria (including distilled component-authoring rules). |
| `skills/promptimize/references/scoring-rubric.md` | Reference file | Behavioral anchors per dimension per score level, with component-type applicability matrix. Loaded by skill at evaluation time. |
| `commands/refresh-prompt-guidelines.md` | Command | Research pipeline: delegate to internet-researcher, diff, synthesize, update guidelines |

### Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Skill vs. Agent for review | **Skill** (runs in main session) | Must use AskUserQuestion for Accept all/Accept some/Reject. Skills run in main session where AskUserQuestion works. Agents run as Task subprocesses where AskUserQuestion is invisible (same problem that motivated the secretary migration). |
| Scoring approach | **Behavioral anchors per dimension** | Research shows 0-3 scales with anchors reduce variance. Our pass(3)/partial(2)/fail(1) maps to this. Each dimension gets concrete criteria defining what pass/partial/fail looks like, adjusted by component type. |
| Guidelines location | **Skill's own references/ dir** | Follows progressive disclosure pattern. SKILL.md stays lean. Guidelines loaded on-demand when skill is invoked. |
| Component-authoring.md loading | **Distill into prompt-guidelines.md** | The relevant structural rules (token budget, description quality, macro-structure per type) are distilled into the Plugin-Specific Patterns section of prompt-guidelines.md during the initial seed. This avoids a cross-directory runtime dependency — no existing skill loads docs/dev_guides/ at runtime, and the cache-dir path traversal (`../../`) would be unworkable. The skill reads two reference files (guidelines + scoring rubric) plus the target. |
| Refresh pipeline delegation | **Command delegates to internet-researcher agent** | Reuses existing agent and its WebSearch/WebFetch tools. No new agent needed. The command provides specific search queries, not the agent's default brainstorm framing. |
| Improved version format | **Full rewrite with `<!-- CHANGE -->` comments** | Inline comments serve as the "diff" mechanism. Each comment marks the dimension and rationale. CHANGE comments are stripped before writing the final file — they are review artifacts, not permanent content. |
| Accept-some merge strategy | **Per-dimension change blocks** | Each `<!-- CHANGE: dim -->` starts a change block that extends to the next `<!-- CHANGE -->` or `<!-- END CHANGE -->` marker. Each block maps to exactly one dimension. If two dimensions modify the same region, they are merged into one block and presented as a single inseparable selection. User selects by dimension name. |
| Guidelines write target | **Resolve via Glob, write back to same path** | The refresh command uses two-location Glob to FIND the guidelines file (cache primary, dev workspace fallback), resolves to an absolute path, then writes back to that same path. This works in both installed and dev contexts. |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 9 dimensions cause reviewer variance (research says 3-5 max) | Medium | Medium | Concrete behavioral anchors per dimension per score level. If calibration test fails (spread < 20 points), collapse similar dimensions. |
| Claude 4.x emphasis anti-pattern contradicts existing plugin patterns | High | Low | Encode as guideline. Promptimize will flag existing emphasis overuse (MUST/CRITICAL) as "partial" on technique currency, with nuanced suggestion. |
| Accept-some UX is complex for many failing dimensions | Low | Low | In practice, most prompts will have 2-4 partial/fail dimensions. AskUserQuestion multiSelect handles this cleanly. |
| Improved version exceeds token budget | Low | Medium | CHANGE comments stripped before writing. Post-generation check: if improved version (sans comments) exceeds budget, flag as warning in report. |

## Interfaces

### promptimize.md (Command)

**Frontmatter:**
```yaml
---
description: Review a plugin prompt against best practices and return an improved version
argument-hint: "[file-path]"
---
```

**Input flow:**
1. If `$ARGUMENTS` contains a file path → use directly
2. If no arguments:
   a. AskUserQuestion: "What type of component?" → Skill / Agent / Command
   b. Glob the corresponding directory:
      - Skill: `~/.claude/plugins/cache/*/iflow*/*/skills/*/SKILL.md` (fallback: `plugins/*/skills/*/SKILL.md`)
      - Agent: `~/.claude/plugins/cache/*/iflow*/*/agents/*.md` (fallback: `plugins/*/agents/*.md`)
      - Command: `~/.claude/plugins/cache/*/iflow*/*/commands/*.md` (fallback: `plugins/*/commands/*.md`)
   c. If no files found → display: "No {type} files found. Expected location: {glob pattern}. Verify plugin installation or check working directory." → STOP
   d. AskUserQuestion: present matching files for selection
3. Validate path matches component detection pattern (skills/*/SKILL.md, agents/*.md, commands/*.md)
4. If invalid → error listing valid patterns → STOP
5. Invoke promptimize skill with the path

**Output:** Delegates entirely to skill. No post-processing.

### promptimize SKILL.md (Skill)

**Frontmatter:**
```yaml
---
name: promptimize
description: Reviews plugin prompts against best practices guidelines and returns scored assessment with improved version. Use when user says 'review this prompt', 'improve this skill', 'optimize this agent', 'promptimize', or 'check prompt quality'.
---
```

**Input:** File path to a plugin component (.md file)

**Process:**
1. **Detect component type** — Match path against patterns:
   - `skills/*/SKILL.md` → skill
   - `agents/*.md` → agent
   - `commands/*.md` → command
   - No match → error with valid patterns, STOP

2. **Load references** (3 reads via two-location Glob):
   - `references/prompt-guidelines.md` — primary: `~/.claude/plugins/cache/*/iflow*/*/skills/promptimize/references/prompt-guidelines.md`, fallback: `plugins/*/skills/promptimize/references/prompt-guidelines.md`
   - `references/scoring-rubric.md` — same pattern with `scoring-rubric.md`
   - Target file itself (absolute path from input)

3. **Check staleness** — Parse `## Last Updated: YYYY-MM-DD` from guidelines. If > 30 days old, set staleness flag.

4. **Evaluate 9 dimensions** — For each dimension, apply behavioral anchors from `references/scoring-rubric.md` to produce pass/partial/fail. Dimensions not applicable to a component type score as pass by default per the applicability matrix in the rubric.

   **Dimension applicability by component type:**
   | Dimension | Skill | Agent | Command |
   |-----------|-------|-------|---------|
   | Structure compliance | Evaluated | Evaluated | Evaluated |
   | Token economy | Evaluated | Evaluated | Evaluated |
   | Description quality | Evaluated | Evaluated | Evaluated |
   | Persuasion strength | Evaluated | Evaluated | Auto-pass |
   | Technique currency | Evaluated | Evaluated | Evaluated |
   | Prohibition clarity | Evaluated | Evaluated | Auto-pass |
   | Example quality | Evaluated | Evaluated | Auto-pass |
   | Progressive disclosure | Evaluated | Auto-pass | Auto-pass |
   | Context engineering | Evaluated | Evaluated | Evaluated |

5. **Calculate score** — Sum dimension scores from step 4 / 27 * 100, round to integer. Step 4 output (per-dimension scores) feeds both this step and step 6.

6. **Generate improved version** — Rewrite the full prompt applying all partial/fail improvements. Mark changes with paired HTML comment delimiters:
   ```
   <!-- CHANGE: {dimension} - {rationale} -->
   {modified content}
   <!-- END CHANGE -->
   ```

   **Concrete example** (two adjacent change blocks):
   ```markdown
   <!-- CHANGE: token_economy - Remove redundant preamble -->
   You are a code reviewer focused on quality.
   <!-- END CHANGE -->

   ## Process

   <!-- CHANGE: structure_compliance - Add numbered steps with bold semantic labels -->
   1. **Read** — Load the target file
   2. **Analyze** — Check against criteria
   <!-- END CHANGE -->
   ```

   A "changed section" is the contiguous block of text between a CHANGE and its matching END CHANGE. If a dimension's improvements touch multiple non-contiguous regions, each region gets its own CHANGE/END CHANGE pair but they are grouped as a single selectable unit in Accept-some (keyed by dimension name). If two dimensions modify the same text region (i.e., the improved text for one dimension overwrites or overlaps the line range of another dimension's improvement), they are merged into one block with both dimensions listed in the CHANGE comment — presented as a single inseparable selection. Preserve all pass-dimension content unchanged.

   **Malformed marker fallback:** If CHANGE/END CHANGE parsing fails (markers missing, mismatched, or overlapping), degrade gracefully to Accept all / Reject only, with a warning: "Selective acceptance unavailable — markers could not be parsed. Use Accept all or Reject."

   **Token budget check:** After generating the improved version, strip all `<!-- CHANGE: ... -->` and `<!-- END CHANGE -->` comments and count lines/tokens. If the result exceeds the budget (<500 lines or <5000 tokens), add a warning to the report: "Improved version exceeds token budget — consider moving content to references/."

7. **Generate report** — Output formatted report (see Output Format below). Dimensions scoring pass are listed in the Strengths section with a brief note on what was done well.

8. **User approval** — AskUserQuestion with 3 options:
   - "Accept all" → Strip CHANGE comments, write improved version to original file
   - "Accept some" → Present each dimension's changes as an AskUserQuestion option (multiSelect: true). Each option label = dimension name, description = one-line summary of the change. Apply selected dimensions' blocks to original; for unselected dimensions, retain original text. **Invariant:** the resulting file must be structurally valid markdown — no orphaned CHANGE/END CHANGE markers and no truncated content.
   - "Reject" → No file changes, STOP

**Output Format:**
```markdown
## Promptimize Report: {filename}

**Component type:** {Skill | Agent | Command}
**Overall score:** {score}/100
**Guidelines version:** {date from prompt-guidelines.md}
{if staleness flag: "Guidelines last updated {date} — consider running /refresh-prompt-guidelines"}

### Strengths
- {dimension}: {what's done well}

### Issues Found

| # | Severity | Dimension | Finding | Suggestion |
|---|----------|-----------|---------|------------|
| 1 | blocker  | {dim}     | {finding} | {suggestion} |
| 2 | warning  | {dim}     | {finding} | {suggestion} |

### Improved Version

{Full rewritten prompt with CHANGE/END CHANGE block delimiters}
```

### refresh-prompt-guidelines.md (Command)

**Frontmatter:**
```yaml
---
description: Scout latest prompt engineering best practices and update the guidelines document
argument-hint: ""
---
```

**Process:**
1. **Locate guidelines file** — Two-location Glob for `skills/promptimize/references/prompt-guidelines.md`. Resolve to absolute path for subsequent write. If Glob returns no matches → display error: "prompt-guidelines.md not found. Verify plugin installation or run implementation setup." → STOP.
2. **Read current guidelines** — Load existing file content
3. **Scout** — Delegate to internet-researcher agent via Task tool:
   ```
   Task:
     subagent_type: iflow-dev:internet-researcher
     prompt: |
       Research the latest prompt engineering best practices published in the last 3 months.

       Execute these specific searches:
       - "Anthropic prompt engineering guide 2026"
       - "OpenAI prompting best practices 2026"
       - "arxiv prompt engineering techniques 2025 2026"
       - "Simon Willison prompt engineering"
       - "Lilian Weng prompt engineering"
       - "context engineering AI agents"

       These cover three source tiers:
       - Tier 1 (official): Anthropic, OpenAI, Google AI prompting docs
       - Tier 2 (research): arxiv papers, DSPy updates
       - Tier 3 (practitioners): Willison, Mollick, Weng, Goodside

       Focus on: new techniques, updated best practices, anti-patterns discovered,
       model-specific changes (Claude 4.x, GPT-4.1+), and context engineering developments.
   ```
   The agent returns its standard output: `{findings: [{finding, source, relevance}], no_findings_reason}`. Parse the `findings` array — each entry has `finding` (string), `source` (URL), `relevance` (high/medium/low).
   - If Task fails or WebSearch unavailable → log warning ("WebSearch unavailable — guidelines not refreshed from external sources"), proceed with empty findings
   - If agent output is not parseable as structured findings → treat as zero findings and proceed (mirrors WebSearch-unavailable fallback)
4. **Diff** — Compare each finding against existing guidelines. A finding overlaps an existing guideline if it references the same technique by name or describes the same behavioral pattern. When in doubt, append as a new entry rather than merge — false negatives (duplicates) are less harmful than false positives (lost findings). Mark overlapping findings for merge, new findings for append.
5. **Synthesize** — For each new/merged finding, format as a guideline entry with evidence tier (Strong/Moderate/Emerging) and source citation.
6. **Update** — Write updated `prompt-guidelines.md` to the absolute path resolved in step 1. Preserve structure (Core Principles, Plugin-Specific Patterns, Persuasion Techniques, Techniques by Evidence Tier, Anti-Patterns, Update Log).
7. **Changelog** — Append row to Update Log table: `| {date} | {summary of changes} | {sources} |`
8. **Update date** — Set `## Last Updated: {today's date}`
9. **Output** — Display summary: "{n} guidelines added, {m} guidelines updated, {k} unchanged. Guidelines version: {date}"

### prompt-guidelines.md (Reference File — Initial Seed)

Seeded from PRD research evidence + existing reference files (anthropic-best-practices.md, persuasion-principles.md, component-authoring.md). The initial seed MUST contain at least 15 guidelines with citations to meet spec success criteria. The 7+ Core Principles plus Plugin-Specific Patterns (3 types x ~3 patterns = 9) plus Anti-Patterns (4+) = 20+ guidelines, exceeding the minimum.

Structure:

```markdown
# Prompt Engineering Guidelines

## Last Updated: {implementation date}

## Core Principles
1. **Be explicit, not implicit** — State requirements directly [Anthropic Claude 4.x guide]
2. **Provide context and rationale** — Explain WHY, not just WHAT [The Prompt Report]
3. **Use XML tags for structure** — Separates instructions from context [Anthropic docs]
4. **Decompose complex tasks** — Break into steps with semantic labels [The Prompt Report]
5. **Few-shot Chain-of-Thought** — Include reasoning examples [The Prompt Report]
6. **Positive framing** — "Do X" not "Don't do Y" [Anthropic Claude 4.x]
7. **Calibrated emphasis** — Normal-intensity language; avoid ALL-CAPS/excessive MUST [Anthropic Claude 4.x]
8. **Provide additional context** — "Massively underrated" technique [The Prompt Report]
9. **Quality examples** — Quantity, order, and format matter; small tweaks yield up to 90% accuracy improvement [The Prompt Report]
10. **Instruction placement** — Place key instructions at top AND bottom for agentic tasks [OpenAI GPT-4.1 Guide]

## Plugin-Specific Patterns

### Skills
- **Structure:** Frontmatter → YOLO overrides → Process (numbered steps with bold semantic labels) → Output format → Error handling → Self-check → PROHIBITED section [Codebase analysis]
- **Token budget:** <500 lines, <5000 tokens. Use reference files for overflow. [component-authoring.md]
- **Progressive disclosure:** SKILL.md = overview/routing, references/ = detailed content loaded on demand [anthropic-best-practices.md]
- **Description:** Gerund name, third person, includes trigger conditions and key terms [component-authoring.md]
- **Conditional logic:** Use response-action tables for conditionals, quality-gate loops for review stages [Codebase analysis]

### Agents
- **Structure:** Frontmatter (name/description/model/tools/color) → Two `<example>` blocks → Single-question focus → Input → Output format (JSON schema) → Process → MUST NOT section [Codebase analysis]
- **Tool scoping:** Explicitly list allowed tools; read-only agents get [Read, Glob, Grep] only [component-authoring.md]
- **Output severity:** Universal blocker/warning/suggestion with "Blocks Approval?" column [Codebase analysis]
- **Description:** Action/role noun form, includes delegation triggers [component-authoring.md]

### Commands
- **Structure:** Frontmatter (description + argument-hint) → Conditional routing → Delegation to skills/agents → Completion [Codebase analysis]
- **Argument handling:** Use $ARGUMENTS for direct input, AskUserQuestion for interactive selection when no args [Codebase analysis]
- **Delegation pattern:** Task tool for agent dispatch, Skill tool for skill invocation [Codebase analysis]

## Persuasion Techniques
- **Authority:** Use "the system" or established norms, not "I think" [persuasion-principles.md]
- **Commitment & Consistency:** Reference prior agreements ("As established in the spec...") [persuasion-principles.md]
- **Loss Aversion:** Frame omissions as risks ("Skipping this step risks...") [persuasion-principles.md]
- **Unity/Identity:** Invoke shared standards ("We follow TDD in this codebase") [persuasion-principles.md]

## Techniques by Evidence Tier

### Strong Evidence
- Few-shot Chain-of-Thought — Highest-performing across benchmarks [The Prompt Report]
- Task decomposition — Strong across all models [The Prompt Report]
- Self-criticism / reflection — Strong for iterative tasks [The Prompt Report]
- Additional context — "Massively underrated" [The Prompt Report]
- Example quality tuning — Up to 90% accuracy improvement from small tweaks [The Prompt Report]

### Moderate Evidence
- XML tags for structure (Claude-specific) — Recommended in official docs [Anthropic guide]
- Instruction placement top AND bottom — ~4% benchmark improvement for agentic tasks [OpenAI GPT-4.1 Guide]
- Positive framing over negation — Preferred in Claude 4.x [Anthropic Claude 4.x guide]

### Emerging / Experimental
- Context engineering framing — Endorsed by Karpathy, Willison, Gartner [Multiple practitioners 2025]
- Degrees-of-freedom matching — Prompt constraints should match task flexibility [anthropic-best-practices.md]

## Anti-Patterns
- **Role prompting for correctness** — Affects tone only, not accuracy [The Prompt Report]
- **Self-consistency** — Underperforms despite popularity [The Prompt Report]
- **Emphasis overuse** — ALL-CAPS, excessive MUST/CRITICAL causes overtriggering in Claude 4.x [Anthropic docs]
- **Anti-laziness language** — "Be thorough", "Don't be lazy" causes overthinking in newer models [Anthropic Claude 4.x guide]
- **All content in one file** — Violates progressive disclosure principle [anthropic-best-practices.md]
- **Weak constraint language** — "Should", "try to", "consider" instead of definitive "MUST", "NEVER" for hard constraints [Codebase analysis]

## Update Log
| Date | Changes | Sources |
|------|---------|---------|
| {implementation date} | Initial seed from PRD research + codebase analysis + component-authoring.md + anthropic-best-practices.md + persuasion-principles.md | The Prompt Report, Anthropic docs, OpenAI GPT-4.1 Guide, codebase patterns |
```

### scoring-rubric.md (Reference File)

Behavioral anchors per dimension per score level. Loaded by the promptimize skill alongside prompt-guidelines.md.

```markdown
# Scoring Rubric

## Behavioral Anchors

| Dimension | Pass (3) | Partial (2) | Fail (1) |
|-----------|----------|-------------|----------|
| Structure compliance | Matches macro-structure for component type exactly | Missing 1-2 optional sections | Missing required sections or wrong structure |
| Token economy | Under budget (<500 lines, <5000 tokens) with no redundant content | Under budget but contains redundant content | Over budget |
| Description quality | Has trigger phrases, activation conditions, third person, specific | Missing some trigger conditions | Vague, first person, or missing |
| Persuasion strength | Uses 3+ persuasion principles effectively | Uses 1-2 principles or uses them weakly | No persuasion techniques |
| Technique currency | Uses current best practices (XML tags, positive framing, appropriate emphasis) | Uses some current practices, has minor outdated patterns | Uses outdated patterns (emphasis overuse, anti-laziness language) |
| Prohibition clarity | All constraints are specific, unambiguous, use definitive language | Some constraints vague or use weak language ("should", "try to") | No explicit constraints or constraints are contradictory |
| Example quality | 2+ concrete, minimal, representative examples | 1 example or examples are too long/generic | No examples (when component type expects them) |
| Progressive disclosure | SKILL.md is overview, details in references/ | Some detail in SKILL.md that could move to references/ | All content crammed in one file, no progressive disclosure |
| Context engineering | Tool restrictions appropriate, minimal context passing, clean boundaries | Minor context bloat or loose tool restrictions | Unrestricted tools, excessive context, unclear boundaries |

## Component Type Applicability

| Dimension | Skill | Agent | Command |
|-----------|-------|-------|---------|
| Structure compliance | Evaluated | Evaluated | Evaluated |
| Token economy | Evaluated | Evaluated | Evaluated |
| Description quality | Evaluated | Evaluated | Evaluated |
| Persuasion strength | Evaluated | Evaluated | Auto-pass |
| Technique currency | Evaluated | Evaluated | Evaluated |
| Prohibition clarity | Evaluated | Evaluated | Auto-pass |
| Example quality | Evaluated | Evaluated | Auto-pass |
| Progressive disclosure | Evaluated | Auto-pass | Auto-pass |
| Context engineering | Evaluated | Evaluated | Evaluated |

Dimensions marked "Auto-pass" score 3 automatically for that component type.
```

## File Structure

```
plugins/iflow-dev/
├── commands/
│   ├── promptimize.md              # Command: arg parsing + file selection UX → skill
│   └── refresh-prompt-guidelines.md # Command: internet-researcher → diff → synthesize → write
├── skills/
│   └── promptimize/
│       ├── SKILL.md                 # Core: detect type, load refs, score 9 dims, rewrite, approve
│       └── references/
│           ├── prompt-guidelines.md # Living guidelines (seeded, updated by refresh command)
│           └── scoring-rubric.md   # Behavioral anchors per dimension per score level
```

5 new files total (2 commands, 1 skill, 2 reference files). No new agents. No hooks. No MCP tools.

## Dependencies

| Dependency | Type | How Used |
|------------|------|----------|
| `internet-researcher` agent | Existing agent | Refresh command delegates research via Task tool. Agent returns `{findings: [{finding, source, relevance}], no_findings_reason}`. Refresh command provides specific search queries to compensate for agent's brainstorm-oriented system prompt. |
| `writing-skills/references/anthropic-best-practices.md` | Existing file | Content distilled into initial prompt-guidelines.md seed (not read at runtime) |
| `writing-skills/references/persuasion-principles.md` | Existing file | Content distilled into initial prompt-guidelines.md seed (not read at runtime) |
| `docs/dev_guides/component-authoring.md` | Existing file | Relevant rules distilled into prompt-guidelines.md Plugin-Specific Patterns section (not read at runtime) |

**Implementation order constraint:** Reference files (prompt-guidelines.md, scoring-rubric.md) must be created before the skill is testable end-to-end. Commands can be authored in parallel with the skill but cannot be integration-tested until the skill and both reference files exist.

## YOLO Mode Behavior

- Promptimize command: file selection auto-selects first match by type
- Promptimize skill: user approval auto-selects "Accept all". Users should run `validate.sh` afterward to verify structural compliance.
- Refresh command: no interactive prompts (fully autonomous)
