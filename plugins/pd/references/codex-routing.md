# Codex Reviewer Routing Protocol

When the `openai-codex/codex` plugin is installed, all pd reviewer dispatches **except `pd:security-reviewer`** route through Codex via the shared codex-companion runtime instead of dispatching the in-process pd reviewer agent. Security review stays on Anthropic Claude (codex is GPT-based; Anthropic-trained reviewer is preferred for safety-critical analysis).

This applies to: `pd:prd-reviewer`, `pd:brainstorm-reviewer`, `pd:spec-reviewer`, `pd:design-reviewer`, `pd:plan-reviewer`, `pd:task-reviewer`, `pd:phase-reviewer`, `pd:implementation-reviewer`, `pd:code-quality-reviewer`, `pd:secretary-reviewer`, `pd:relevance-verifier`, `pd:test-deepener`, `pd:ds-analysis-reviewer`, `pd:ds-code-reviewer`, `pd:project-decomposition-reviewer`. **Excludes:** `pd:security-reviewer`.

## Detection

Before any reviewer dispatch, run:

```bash
codex_installed() {
  [[ -d "$HOME/.claude/plugins/cache/openai-codex/codex" ]] || return 1
  ls "$HOME/.claude/plugins/cache/openai-codex/codex"/*/scripts/codex-companion.mjs >/dev/null 2>&1
}
```

If `codex_installed` returns 0 (true), use **Codex routing** below. Otherwise dispatch the pd reviewer via `Task(subagent_type: pd:<reviewer>, ...)` per the existing pattern.

## Codex Routing — Foreground (sync)

For sync reviewer dispatches (e.g., per-iteration review loops where the orchestrator needs the result before continuing), run codex-companion in foreground via `Bash`:

```bash
CODEX_COMPANION=$(ls "$HOME/.claude/plugins/cache/openai-codex/codex"/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
node "$CODEX_COMPANION" adversarial-review --wait --base "${pd_base_branch}" -- "<the pd reviewer's full prompt body, including required-artifact reads, JSON schema, iteration context>"
```

Capture the JSON output from stdout. Parse it as the reviewer response. The `adversarial-review` command produces a structured verdict that maps to pd's reviewer JSON schema. If the schema differs (codex uses `verdict/findings/details` vs pd uses `approved/issues/summary`), translate fields:

| Codex field | pd field |
|---|---|
| `verdict == "approved"` | `approved: true` |
| `verdict == "needs-revision"` | `approved: false` |
| `findings[].severity` | `issues[].severity` |
| `findings[].location` | `issues[].location` |
| `findings[].description` | `issues[].description` |
| `findings[].suggestion` | `issues[].suggestion` |
| `summary` | `summary` |

## Codex Routing — Background (async)

For QA gate parallel dispatches in `/pd:finish-feature` Step 5b, where 4 reviewers run in parallel and the orchestrator collects all results before deciding:

1. Launch each non-security reviewer as a background codex task:
   ```bash
   node "$CODEX_COMPANION" adversarial-review --background --base "${pd_base_branch}" -- "<reviewer prompt>"
   ```
   Capture each returned `job-id`.
2. Continue to dispatch security-reviewer via the standard `Task(subagent_type: pd:security-reviewer, ...)` (Anthropic).
3. Poll codex jobs to completion via:
   ```bash
   node "$CODEX_COMPANION" status <job-id>
   ```
4. Collect each result via:
   ```bash
   node "$CODEX_COMPANION" result <job-id>
   ```
5. Apply field translation per the table above.

## Reviewer Prompt Reuse

The reviewer prompt body (artifacts to read, JSON schema, iteration context, user filter) is reused verbatim — codex receives the same prompt the pd reviewer would have received. Only the dispatch mechanism changes.

## Failure Modes

- **Codex companion script missing or non-executable:** treat as `codex_installed == false`; fall back to pd reviewer Task dispatch.
- **Codex returns malformed JSON:** treat as parse failure per existing pd reviewer JSON-parse fallback (ask reviewer to retry, or proceed with empty issues array).
- **Codex job times out (background mode):** kill the job, log the timeout, fall back to pd reviewer Task dispatch.
- **Codex returns Codex-shape JSON that doesn't match the translation table:** log the unrecognized shape, fall back to pd reviewer.

## Why security-reviewer is excluded

- Anthropic models have specific safety training relevant to security-critical analysis (OWASP, secrets handling, injection vectors).
- Codex (GPT-5 family) is a general-purpose code reasoning model without the same safety calibration.
- Security review failures have outsized blast radius (vulnerabilities ship to production); diversity-of-thought from a different model family is valuable.
- All other reviewers operate on quality/correctness signals where Codex is at parity or stronger (especially for adversarial code review, which is a documented Codex strength via its `adversarial-review` slash command).

## Future Considerations

- Once `codex-rescue` agent matures and codex's `adversarial-review` JSON schema stabilizes, this routing could be promoted from a per-command preamble to a workflow-transitions skill function.
- Cross-model reviewer disagreement is a useful signal — when codex approves and security-reviewer flags HIGH, the code is high-confidence safe-but-buggy; when codex flags HIGH and security-reviewer approves, likely a model-disagreement edge case worth surfacing to the user.
