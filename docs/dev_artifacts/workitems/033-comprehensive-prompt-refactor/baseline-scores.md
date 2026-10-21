# Baseline Promptimize Scores

> **Note:** Pre-refactor baselines are unavailable — feature 033 refactoring was already merged
> before scoring was performed. Scores below are post-refactor baselines collected via interactive
> promptimize in a fresh CC session (2026-03-01).

## Post-Refactor Baseline (2026-03-01)

| File | Type | Lines | Score | Key Issues |
|------|------|-------|-------|------------|
| plugins/iflow/agents/design-reviewer.md | agent | 256 | 97/100 | token_economy (2): redundant Note on Tools blockquote duplicates Tool Fallback section |
| plugins/iflow/agents/ds-analysis-reviewer.md | agent | 153 | 97/100 | token_economy (2): redundant Note on Tools blockquote duplicates Tool Fallback section |
| plugins/iflow/commands/secretary.md | command | 700 | 93/100 | token_economy (1): 700 lines exceeds 500-line budget |
| plugins/iflow/agents/ds-code-reviewer.md | agent | 141 | 90/100 | structure (2), token_economy (2), prohibition (2) |
| plugins/iflow/skills/brainstorming/SKILL.md | skill | 532 | 83/100 | token_economy (1), structure (2), examples (2), cache (2) |

**Mean score:** 92/100
**All files >= 80:** Yes

## Recurring Patterns

1. **Note on Tools duplication** — All 3 agent files contain a "Note on Tools" blockquote that duplicates the "Tool Fallback" section. Removing would improve token_economy across agents.
2. **Token budget overruns** — secretary.md (700 lines) and brainstorming/SKILL.md (532 lines) exceed the 500-line budget. Both need content extraction to reference files.
3. **Missing MUST NOT section** — ds-code-reviewer.md has an informal "Principle" section instead of a formal "What You MUST NOT Do" section per agent structure guidelines.
