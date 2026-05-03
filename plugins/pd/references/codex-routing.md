# Codex Reviewer Routing Protocol

When the `openai-codex/codex` plugin is installed, all pd reviewer dispatches **except `pd:security-reviewer`** route through Codex via the shared codex-companion runtime instead of dispatching the in-process pd reviewer agent. Security review stays on Anthropic Claude (codex is GPT-based; Anthropic-trained reviewer is preferred for safety-critical analysis).

This applies to: `pd:prd-reviewer`, `pd:brainstorm-reviewer`, `pd:spec-reviewer`, `pd:design-reviewer`, `pd:plan-reviewer`, `pd:task-reviewer`, `pd:phase-reviewer`, `pd:implementation-reviewer`, `pd:code-quality-reviewer`, `pd:secretary-reviewer`, `pd:relevance-verifier`, `pd:test-deepener`, `pd:ds-analysis-reviewer`, `pd:ds-code-reviewer`, `pd:project-decomposition-reviewer`. **Excludes:** `pd:security-reviewer`.

## Detection (with path-integrity check)

Before any reviewer dispatch, run:

```bash
codex_installed() {
  local cache_root="$HOME/.claude/plugins/cache/openai-codex/codex"
  [[ -d "$cache_root" ]] || return 1
  local script
  script=$(ls "$cache_root"/*/scripts/codex-companion.mjs 2>/dev/null | head -1)
  [[ -n "$script" ]] || return 1
  # Path-integrity check: resolved real path must be under the expected cache root.
  # Defends against symlink redirection (cache dir is user-writable).
  local resolved
  resolved=$(/usr/bin/realpath -- "$script" 2>/dev/null) || return 1
  local resolved_root
  resolved_root=$(/usr/bin/realpath -- "$cache_root" 2>/dev/null) || return 1
  [[ "$resolved" == "$resolved_root"/* ]] || return 1
  echo "$script"
}
```

Capture the script path: `CODEX_COMPANION=$(codex_installed)` succeeds (exit 0) and prints the validated path. On failure (cache missing, script missing, or symlink-redirection detected) the function exits non-zero and the caller falls back to `Task(subagent_type: pd:<reviewer>, ...)`.

## Codex Routing — Foreground (sync)

For sync reviewer dispatches (per-iteration review loops where the orchestrator needs the result before continuing), use the `task` subcommand with a **temp-file-delivered prompt** (NOT argv interpolation — see Security section below). The prompt body is the pd reviewer's full prompt verbatim (artifacts to read, JSON schema, iteration context, user filter):

```bash
CODEX_COMPANION=$(codex_installed) || { fallback_to_pd_reviewer; exit; }
PROMPT_FILE=$(mktemp -t pd-reviewer-prompt.XXXXXX)
trap 'rm -f "$PROMPT_FILE"' EXIT

# Write the pd reviewer's full prompt body to the temp file (heredoc preserves all
# special characters including backticks, $, \, and embedded code fences).
cat > "$PROMPT_FILE" <<'PD_REVIEWER_PROMPT_END'
<the pd reviewer's full prompt body — single-quoted heredoc prevents any
interpolation of artifact content; safe for adversarial reviewer-prompt
contents including PRD body, spec text, code diffs>
PD_REVIEWER_PROMPT_END

# Invoke codex with --prompt-file (no argv interpolation of prompt body).
node "$CODEX_COMPANION" task --prompt-file "$PROMPT_FILE"
```

Capture the JSON output from stdout. Parse it against the codex schema at `~/.claude/plugins/cache/openai-codex/codex/*/schemas/review-output.schema.json`. The schema has these top-level required fields: `verdict`, `summary`, `findings[]`, `next_steps[]`. Each finding requires: `severity`, `title`, `body`, `file`, `line_start`, `line_end`, `confidence`, `recommendation`.

**Verdict translation:**
| Codex `verdict` | pd `approved` |
|---|---|
| `"approve"` | `true` |
| `"needs-attention"` | `false` |

**Severity translation:**
| Codex `severity` | pd `severity` |
|---|---|
| `"critical"` or `"high"` | `"blocker"` |
| `"medium"` | `"warning"` |
| `"low"` | `"suggestion"` |

**Per-finding field translation:**
| Codex finding field | pd issue field |
|---|---|
| `severity` (translated above) | `severity` |
| `title` + `body` (concatenate as `"{title}: {body} (codex confidence: {confidence})"`) | `description` |
| `file` + `line_start` (format as `"{file}:{line_start}"`) | `location` |
| `recommendation` | `suggestion` |

The `confidence` value is preserved inside the translated `description` so the orchestrator can still weight low-confidence findings. `next_steps[]` is appended to the translated `summary` as a "Next steps:" trailer.

## Codex Routing — Background (async)

For the QA gate parallel dispatch in `/pd:finish-feature` Step 5b, where 4 reviewers run in parallel and the orchestrator collects all results before deciding:

```bash
CODEX_COMPANION=$(codex_installed) || { fallback_to_pd_reviewer; exit; }
PROMPT_FILE=$(mktemp -t pd-reviewer-prompt.XXXXXX)
cat > "$PROMPT_FILE" <<'PD_REVIEWER_PROMPT_END'
<reviewer prompt body verbatim>
PD_REVIEWER_PROMPT_END

# Background dispatch returns immediately with a job-id.
JOB_ID=$(node "$CODEX_COMPANION" task --background --prompt-file "$PROMPT_FILE" \
  | jq -r '.job_id // .id')
echo "$JOB_ID"
# Note: do NOT delete the prompt file here; codex-companion may still be reading it
# until the background job actually starts. Clean up after `result` returns.
```

1. For each non-security reviewer, dispatch as above; capture each `JOB_ID`.
2. Continue to dispatch `pd:security-reviewer` via the standard `Task(subagent_type: pd:security-reviewer, ...)` (Anthropic). **This is non-negotiable per the security exclusion below.**
3. Poll codex jobs to completion: `node "$CODEX_COMPANION" status "$JOB_ID"` (parse status: completed | failed | running).
4. Collect each result: `node "$CODEX_COMPANION" result "$JOB_ID"`.
5. Apply field translation per the tables above.
6. Clean up the prompt files: `rm -f "$PROMPT_FILE"` after each result is collected.

## Security: NO argv interpolation of prompt body

**Do not** pass the reviewer prompt body as an argv argument like:
```bash
# UNSAFE — bash performs $() and backtick substitution on the double-quoted string
node "$CODEX_COMPANION" task -- "<prompt body with adversarial content>"
```

Reviewer prompt bodies contain reviewer-injected artifact content (PRDs, specs, code diffs) which can include backticks and `$(...)` from user-authored sources. Bash double-quote expansion would execute these on the host. The temp-file delivery via `--prompt-file` (with single-quoted heredoc to populate the file) prevents this entirely — the file content is read by codex-companion at runtime, not interpreted by bash.

## Reviewer Prompt Reuse

The reviewer prompt body (artifacts to read, JSON schema, iteration context, user filter) is reused verbatim via the temp-file path — codex receives the same prompt the pd reviewer would have received. Only the dispatch mechanism changes.

## Failure Modes

- **Codex companion script missing, non-executable, or fails path-integrity check:** treat as `codex_installed == false`; fall back to pd reviewer Task dispatch.
- **`mktemp` fails:** fall back to pd reviewer Task dispatch.
- **Codex returns malformed JSON or schema mismatch:** treat as parse failure per existing pd reviewer JSON-parse fallback (ask reviewer to retry, or proceed with empty issues array).
- **Codex job times out (background mode):** kill the job via codex-companion's cancel command, log the timeout, fall back to pd reviewer Task dispatch.
- **Codex returns Codex-shape JSON that doesn't match the translation table:** log the unrecognized shape, fall back to pd reviewer.

## Why security-reviewer is excluded

- Anthropic models have specific safety training relevant to security-critical analysis (OWASP, secrets handling, injection vectors).
- Codex (GPT-5 family) is a general-purpose code reasoning model without the same safety calibration.
- Security review failures have outsized blast radius (vulnerabilities ship to production); diversity-of-thought from a different model family is valuable.
- All other reviewers operate on quality/correctness signals where Codex is at parity or stronger.

## Programmatic Guard Against Future Regression

The exclusion is currently enforced only by prose in the per-command preambles. Until this routing is promoted to a workflow-transitions skill function (see Future Considerations), `validate.sh` MUST assert that:

1. Every command/skill referencing `plugins/pd/references/codex-routing.md` also names `pd:security-reviewer` in an exclusion clause.
2. No prose in those files routes `pd:security-reviewer` through codex.

This guards against a future refactor accidentally regressing the exclusion.

## Future Considerations

- Once codex's `task` JSON schema stabilizes and the field-mapping is dogfooded across 3+ features, this routing could be promoted from per-command preambles to a `workflow-transitions::dispatchReviewer(name, prompt)` helper. The helper MUST hardcode `if reviewer == 'pd:security-reviewer': use_codex = False`.
- Cross-model reviewer disagreement is a useful signal — when codex approves and security-reviewer flags HIGH, the code is high-confidence safe-but-buggy; when codex flags HIGH and security-reviewer approves, likely a model-disagreement edge case worth surfacing to the user.
