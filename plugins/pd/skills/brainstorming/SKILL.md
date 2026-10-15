---
name: brainstorming
description: Clarify playbook for an idea — the brainstorm item, the Clarify questions, the optional research-fanout, the PRD, and promotion at Criteria. Use when the user says 'brainstorm this', 'explore options for', 'start ideation', or 'create a PRD'.
---

# Brainstorming

The conductor's playbook for Clarify on an idea (plan §A2, row 1). Where state lives, workflow runs and the dispatch rules: the workflow-transitions skill.

**Clarify has no phase and no `phase-gate.sh` exit check.** The work lives in its brainstorm item; `pd-lint` checks the item at every commit.

**Entries this stage writes,** under the item's `## Log` (shapes: `${CLAUDE_PLUGIN_ROOT}/references/log-entries.md`): `decision` (each ruling that settles scope or success, quoted verbatim), `run` (a research-fanout run), `note` (promotion, parking).

## 1. Create the item
`${CLAUDE_PLUGIN_ROOT}/scripts/pd-new brainstorm "<title>"` writes `{pd_artifacts_root}/brainstorms/<YYYY-MM-DD>-<slug>.md`: frontmatter, body, `## Now` and `## Log`. Commit it.

## 2. Clarify: the user owns the answers
Settle five things through AskUserQuestion, one question at a time: the problem, who it affects, what success looks like in measurable terms ("works better" is not a criterion), known constraints, and approaches already tried. Apply YAGNI to every "nice to have". Keep `## Now` on the next open question.

## 3. Research
- **One narrow question:** dispatch one `pd:codebase-explorer` (what exists here, and where) or `pd:internet-researcher` (prior art), or read it yourself. Findings with sources, never file dumps.
- **A question that spans many independent sources:** start the `research-fanout` workflow, only when you judge it does; the `run` entry records why (§A8.3 S5). Its args, from committed files:
  - `question`: the clarified question;
  - `source`: the brainstorm item's path;
  - `lenses`: one `{name, brief}` per advisor, the brief being the verbatim text of `references/advisors/<name>.advisor.md` plus the Clarify answers. Default pair: `pre-mortem` and `opportunity-cost`. Swap in `feasibility` for build risk, `working-backwards` for a fuzzy deliverable, `first-principles` for open exploration. A missing template is skipped with a warning;
  - `workflow_output_cap`: from `.claude/pd.local.md`.
- **Around the run:** the workflow-transitions protocol: the `run in flight:` line in the item's `## Now` before launch; after it, a `run` entry with `agents_used`, `tokens` and the reason, the line cleared, a commit. Its result is `findings[{claim, evidence, source}]` (`${CLAUDE_PLUGIN_ROOT}/references/workflow-results.md`).
- **A failed agent** is a warning, not a stop.

## 4. Write the PRD into the item's body
- **Converge:** every claim carries `— Evidence: {URL | file:line | User input}` or `— Assumption: needs verification`. Contradictions between sources are stated, not averaged away.
- **Sections, in order:** Problem Statement · Goals · Success Criteria · User Stories · Use Cases · Edge Cases & Error Handling · Constraints (behavioral, then technical) · Requirements (FR and NFR) · Non-Goals · Research Summary · Strategic Analysis (one subsection per advisor, closing with its evidence quality) · Open Questions · Next Steps.
- **No review here.** A PRD gets none; calvin covers it at Criteria (§A2, row 1).

## 5. Decide
Ask through AskUserQuestion:
- **Promote to a feature (Criteria):** apply `/pd:secretary`'s depth rules now to pick `mode` (`standard` or `small`) and any `risk:` tag, then `${CLAUDE_PLUGIN_ROOT}/scripts/pd-new feature --from brainstorms/<id>.md "<title>" --mode <mode>`, set `risk:` in its README, and continue with the specifying skill. On the brainstorm: `status: done`, a `note` entry `Promoted → features/<feature id>.`, one commit.
- **Several features:** `pd-new plan "<title>" --from brainstorms/<id>.md`, its features listed as `planned:` roadmap items (Part B §7.1); then `pd-new feature --plan <plan> <slug> "<title>"` for the first one.
- **Park it:** `## Now` names what would reopen it; a `note` entry; commit.
- **Drop it:** `status: abandoned` with a `decision` entry giving the reason; commit.

**Constraints:** this playbook writes the brainstorm item, and at promotion runs `pd-new`. No code, no phase moves.
