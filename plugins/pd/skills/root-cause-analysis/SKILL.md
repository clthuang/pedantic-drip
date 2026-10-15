---
name: root-cause-analysis
description: "Clarify playbook for a bug — the rca item, reproduction, 3+ hypotheses, the rca-fanout workflow with its refuters, the causal DAG and the RCA report, then the fix's entry depth. Use when user says 'run RCA', 'exhaustive multi-cause investigation', 'find ALL root causes', or runs /root-cause-analysis."
---

# Root Cause Analysis

The conductor's playbook for Clarify on a bug (plan §A2, row 1): find ALL contributing causes, not just the first one. Where state lives, workflow runs and the dispatch rules: the workflow-transitions skill.

**Clarify has no phase and no `phase-gate.sh` exit check.** The work lives in its rca item; `pd-lint` checks the item at every commit.

**Entries this stage writes,** under the item's `## Log` (shapes: `${CLAUDE_PLUGIN_ROOT}/references/log-entries.md`): `decision` (the user's rulings, quoted verbatim), `run` (the rca-fanout run), `note` (an intermittent reproduction, the hand-off).

```mermaid
graph LR
    A[1. Create] --> B[2. Clarify] --> C[3. Reproduce] --> D[4. Hypotheses] --> E[5. rca-fanout] --> F[6. Analyze] --> G[7. Report] --> H[8. Decide]
```

## 1. Create the item
`${CLAUDE_PLUGIN_ROOT}/scripts/pd-new rca "<title>"` writes `{pd_artifacts_root}/rca/<YYYY-MM-DD>-<slug>.md`: frontmatter, body, `## Now` and `## Log`. Commit it.

## 2. Clarify: the user owns the answers
Ask through AskUserQuestion, one at a time:
1. What is the exact error or unexpected behavior?
2. When did it start?
3. What changed recently (code, config, dependencies)?
4. Is it reproducible or intermittent?
5. What has already been tried?

The output is a clear problem statement: the symptom, in the item's body.

## 3. Reproduce
In `agent_sandbox/<YYYY-MM-DD>/rca-<slug>/` (`reproduction/`, `experiments/`, `logs/`), build a minimal reproduction. After three failed attempts, record "intermittent" in a `note` entry with what was tried. Never touch production code.

## 4. Hypotheses: at least three
Apply the 5 Whys ([five-whys-template](references/five-whys-template.md)): trace the error backward through the call stack, search for similar patterns, check recent commits on the related code, compare configuration and environments. With fewer than three genuine causes, list the alternatives considered and why each was set aside.

## 5. The `rca-fanout` workflow: every bug that reaches Clarify
One `rca-investigator` per hypothesis, then a refuter (`rca-investigator` with a refute brief) per supported cause. Its args, from committed files:
- `symptom`: the problem statement;
- `source`: the rca item's path;
- `hypotheses`: the list from step 4;
- `workflow_output_cap`: from `.claude/pd.local.md`.

Around the run, the workflow-transitions protocol: the `run in flight:` line in the item's `## Now` before launch; after it, a `run` entry with `agents_used` and `tokens`, the line cleared, a commit. Its result is `findings[{claim, evidence, source, verdict}]`, `verdict` being `survived` or `refuted` (`${CLAUDE_PLUGIN_ROOT}/references/workflow-results.md`). An investigator's claim is a claim: re-check the evidence of each surviving cause at file:line, or by re-running its command, before it enters the report.

## 6. Analyze
Identify every surviving cause and the interactions between them; draw the causal DAG ([causal-dag](references/causal-dag.md) has the cause categories and templates). A refuted cause stays in the report, with its refutation.

## 7. Report, in the item's body
Per [rca-report-template](references/rca-report-template.md):
- summary, with dates and status;
- timeline of events;
- reproduction steps and result;
- hypotheses explored, each with its evidence and verdict;
- experiments conducted;
- root causes: the primary one and the contributing factors, with the DAG;
- recommendations: directions, not fixes.

## 8. Decide the fix's entry depth
Ask through AskUserQuestion:
- **Express:** only for one known pattern. The codebase already holds the same change shape, and the mini-spec will cite that example's path (§A2). `${CLAUDE_PLUGIN_ROOT}/scripts/pd-new feature --from rca/<id>.md "<title>" --mode express`, then the specifying skill's express mini-spec.
- **Criteria:** apply `/pd:secretary`'s depth rules to pick `mode` and any `risk:` tag, then `pd-new feature --from rca/<id>.md "<title>" --mode <mode>`, set `risk:` in its README, and continue with the specifying skill.
- **No fix now:** `## Now` says why, and the recommendations go to the backlog with `pd-new backlog "<title>"`.

Then the rca item takes `status: done` and a `note` entry naming where the fix went; commit.

## Behavioral rules
- **MUST** reproduce before analyzing, or record the failed attempts.
- **MUST** explore at least three hypothesis paths.
- **MUST NOT** modify production code: `agent_sandbox/` and the rca item only.
- **MUST NOT** propose fixes in the report: causes only; the fix is a feature.

## Related
- [systematic-debugging](../systematic-debugging/SKILL.md): the Iron Law ("NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST") and the 3-fix rule.
