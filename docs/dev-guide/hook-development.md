# Hook Development Guide

Guidelines for developing hooks in the pedantic-drip plugin. The table of registered hooks lives in [README_FOR_DEV.md "Hooks"](../../README_FOR_DEV.md#hooks).

## Critical Concept: PLUGIN_ROOT vs PROJECT_ROOT

### The Problem

When Claude Code installs a plugin, it copies files to a cache directory:
```
~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
```

Hooks receive `CLAUDE_PLUGIN_ROOT` pointing to this cached location. However:
- **Static plugin assets** (scripts, templates): Use PLUGIN_ROOT
- **Dynamic project state** (work items, source code): Use PROJECT_ROOT

### The Solution

Start every hook the way the existing hooks do (`pd-session-start.sh`, `pd-commit-lint.sh`):

- **Ignore SIGPIPE:** `trap '' PIPE`; see "Broken-pipe handling" below.
- **Install the ERR trap:** `install_err_trap` right after sourcing `lib/common.sh`. `validate.sh` fails a hook that sources `common.sh` without it.
- **Take the project from stdin:** Claude Code passes `cwd` in the hook's JSON input; `git rev-parse --show-toplevel` from there gives PROJECT_ROOT.

```bash
#!/usr/bin/env bash
set -uo pipefail
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap

input=$(cat)
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd"
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
```

A hook that doesn't take its root from stdin's `cwd` uses `PROJECT_ROOT="$(detect_project_root)"` from `lib/common.sh` instead, which walks up from the working directory (`pre-commit-guard.sh` reads stdin only for `tool_input.command`).

### When to Use Each

| Variable | Use For | Example |
|----------|---------|---------|
| `PLUGIN_ROOT` | Static plugin files | Template files, reference docs |
| `PROJECT_ROOT` | Dynamic project state | Work item metadata, test files, source code |
| `PWD` | User's current directory | Relative path display |

## Hook Output Format

A hook answers Claude Code in one of five ways. Pick the narrowest one that does the job.

- **Pass-through:** exit 0 with no output, the usual exit when the event isn't the hook's business. `pre-commit-guard.sh` leaves this way on a Bash call that isn't a `git commit`.
- **Block:** exit 2 with the reason on stderr; Claude sees the reason. No JSON. `pd-commit-lint.sh` blocks a commit this way, `pd-agent-write-guard.sh` a write and `pd-stop-gate.sh` a stop:
  ```bash
  printf 'pd-agent-write-guard: %s\n' "$reason" >&2 || true
  exit 2
  ```
- **Reminder:** `hookSpecificOutput.additionalContext`, a note for Claude that changes no permission. `pre-commit-guard.sh` reminds this way:
  ```bash
  remind() {
      safe_emit_hook_json "{\"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", \"additionalContext\": \"$(escape_json "$1")\"}}"
  }
  ```
- **PreToolUse decision:** `hookSpecificOutput.permissionDecision`, `deny` or `ask`, with a `permissionDecisionReason`. No pd hook makes one today. Never return `allow` casually: it skips the user's permission prompt for that tool call.
  ```bash
  safe_emit_hook_json "$(jq -nc --arg why "$reason" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $why}}')"
  exit 0
  ```
- **SessionStart context:** `hookSpecificOutput.additionalContext` through `safe_emit_hook_json`, as `pd-session-start.sh` does:
  ```bash
  safe_emit_hook_json "$(jq -nc --arg ctx "$text" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}')"
  exit 0
  ```

Build JSON with `jq -nc --arg`, or escape each value with `escape_json()`. Write it with `safe_emit_hook_json` from `lib/session-start-helpers.sh`, with `trap '' PIPE` set first.

## Shared Library Functions

### `hooks/lib/common.sh`

- **`detect_project_root`:** walks up from PWD to the nearest `.git` (a directory in a main checkout, a file in a linked worktree); falls back to PWD. So a session in a linked worktree roots at the worktree, not the main checkout. A git submodule's `.git` is a file too, so a session inside a submodule roots at the submodule. An orphaned worktree (its `.git` file names a pruned `.git/worktrees/<name>`) also roots at itself.
- **`extract_command_workdir "$command"`:** the directory a Bash command string runs in (`cd dir && …`, `(cd dir && …)`, `git -C dir …`), or empty for PWD.
- **`run_git_in_command_context "$command" <git args>`:** runs git in that directory, with stderr suppressed.
- **`escape_json "$string"`:** escapes backslashes, double quotes, newlines, carriage returns and tabs for a JSON string value.
- **`read_local_md_field "$file" "$field" "$default" [preserve_spaces]`:** reads a frontmatter field from a `.local.md` file, such as `.claude/pd.local.md`; returns the default when the file or field is missing.
- **`read_hook_state` / `write_hook_state`:** read and write one key in a `key=value` state file.
- **`install_err_trap`:** an ERR trap that prints `{}` and exits 0, so an unexpected failure never breaks the session. Required in every hook that sources `common.sh`.

### `hooks/lib/session-start-helpers.sh`

- **`safe_emit_hook_json "$json"`:** writes the JSON exactly as given, EPIPE-safe. It doesn't add `hookEventName`. The caller must set `trap '' PIPE` first.
- **`pd_log_diagnostic`:** appends one tab-separated line to a log file named by an environment variable or a default path, rotating it past 1 MB. Every failure returns 0.
- **`pd_log_session_start_diagnostic`:** `pd_log_diagnostic` for `pd-session-start.sh`, writing to `$PD_SESSION_START_LOG`, default `~/.claude/pd/session-start.log`.
- **`install_session_start_traps`:** an ERR trap that logs a diagnostic, and an EXIT trap that prints `{}` when the hook exits non-zero and always exits 0. `validate.sh` accepts it in place of `install_err_trap`.

## Testing Hooks

Four hooks have their own suite (`plugins/pd/hooks/tests/test-pd-*.sh`); `pre-commit-guard`, `cleanup-stale-versions` and the shared library are tested in the integration suite, `test-hooks.sh`. [commands-reference.md](commands-reference.md) lists every suite CI runs:
```bash
bash plugins/pd/hooks/tests/test-hooks.sh
```

`./validate.sh` runs `test-hooks.sh` too. The full list of test commands is in [commands-reference.md](commands-reference.md).

## Anti-Patterns

| Don't | Why | Do Instead |
|-------|-----|------------|
| Use `find .` for project files | Wrong results from subdirectories | Use `find "${PROJECT_ROOT}"` |
| Read metadata from PLUGIN_ROOT | Stale cached data | Use PROJECT_ROOT for dynamic state |
| Duplicate utility functions | Maintenance burden, drift | Source `lib/common.sh` |
| Output unescaped strings in JSON | Invalid JSON breaks hook | Build it with `jq -nc --arg`, or use `escape_json()` |
| Return `permissionDecision: "allow"` | Skips the user's permission prompt | Pass through silently, or use `additionalContext` |

## Hook Types Reference

The events pd registers in `plugins/pd/hooks/hooks.json`:

| Event | pd hooks | Stdin fields pd reads | Can block | Responds with |
|-------|----------|------------------------|-----------|---------------|
| SessionStart | `pd-session-start.sh`, `cleanup-stale-versions.sh` | `source` (`startup`, `resume`, `clear`, `compact`), `cwd` | No | `hookSpecificOutput.additionalContext`, or nothing |
| PreToolUse | `pre-commit-guard.sh`, `pd-commit-lint.sh` (Bash); `pre-edit-unicode-guard.sh`, `pd-agent-write-guard.sh` (Write, Edit) | `tool_name`, `tool_input` (`command`, `file_path`, `old_string`, `new_string`, `content`), `cwd`, `session_id`, `agent_type` | Yes | pd emits exit 2 with stderr, `additionalContext`, `{"continue": true}` (the unicode guard), or nothing; the protocol also allows `permissionDecision`, which no pd hook sets |
| Stop | `pd-stop-gate.sh` (fires each time Claude finishes a response) | `session_id`, `cwd`, `stop_hook_active`, `transcript_path` (token charging), `background_tasks` (yielding to running work) | Yes | exit 2 with the reason on stderr keeps Claude working |

`validate.sh` accepts these event names in `hooks.json`: PreToolUse, PostToolUse, PostToolUseFailure, UserPromptSubmit, Stop, SubagentStop, SessionStart, SessionEnd, PreCompact, Notification.

## Hook JSON Output Schema

Claude Code enforces a schema on hook JSON output. **Every `hookSpecificOutput` block MUST include a `hookEventName` field** matching the event the hook is registered for:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Reminder: Test files exist in this project. Have you run the tests?"
  }
}
```

### Preferred: use the shared emitter

Build the complete payload yourself, including `hookEventName`, then emit it through the EPIPE-safe `safe_emit_hook_json` helper from `lib/session-start-helpers.sh`:

```bash
trap '' PIPE   # without it, bash dies of SIGPIPE before the helper's || true runs
source "$(dirname "${BASH_SOURCE[0]}")/lib/session-start-helpers.sh"
payload=$(jq -nc --arg ctx "$text" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}')
safe_emit_hook_json "$payload"
```

`safe_emit_hook_json` emits the payload exactly as given. It does NOT wrap it or add `hookEventName`; its job is EPIPE-safe delivery (see "Broken-pipe handling" below). Building the payload with `jq -nc` and passing it whole keeps `hookEventName` from going missing.

### Common pitfall: missing `hookEventName`

Omitting `hookEventName` produces this error in user transcripts:

```
PreToolUse:Bash hook error — Hook JSON output validation failed
hookSpecificOutput is missing required field "hookEventName"
```

### Cross-event error attribution: the label is misleading

**Claude Code attributes a hook's JSON-validation failure to the NEXT tool event in the transcript, not to the hook that produced the malformed JSON.** If you see `PreToolUse:Bash hook error` but your PreToolUse:Bash hooks look fine, grep ALL hooks for the emission pattern: the bug is most likely in a hook on an earlier event that fired right before the Bash call.

### Stale cached plugin versions

Claude Code does not garbage-collect old cached plugin versions when a new release lands. A long-running session keeps using the previous version's hook scripts until you start a new session. If a hook fix doesn't seem to take effect, start a new Claude Code session (don't resume).

The `cleanup-stale-versions.sh` SessionStart hook removes old versions on startup, resume and clear. It reads `installed_plugins.json` and deletes each cached version that doesn't match the active one, except a version whose `.in_use/<pid>` marker (written by Claude Code) names a live process: deleting it would pull the hooks and scripts out from under that session.

### Enforcement

`validate.sh` runs a static scanner on every PR: any `"hookSpecificOutput":` emission (the literal JSON-emission signature) without `hookEventName` in the same file fails CI. It skips `plugins/pd/hooks/tests/` (tests read hook output, they don't emit it) and `plugins/pd/hooks/lib/` (the helpers and their self-tests).

## Broken-pipe handling for hooks emitting structured output

Claude Code can close a hook's stdout before the hook finishes writing, for example during `/clear` or `/compact`. Every hook that writes JSON must survive that and still exit 0.

### Why `set -e` + `cat <<EOF` is unsafe

- **The write fails:** a `cat <<EOF` heredoc runs a child `cat` whose write returns EPIPE on the closed pipe, so the child exits 1.
- **The hook fails:** `set -e` and `pipefail` turn that exit 1 into the hook's exit code.
- **The user sees it:** Claude Code shows "Failed with non-blocking status code: No stderr output", and the hook's context is lost.

### Why `trap '' PIPE` is necessary but not sufficient

Both halves are required; removing either brings the failure back.

- **`trap '' PIPE`:** stops SIGPIPE from killing the bash process. Without it, the builtin `printf` is killed before any `|| true` can run.
- **`{ printf …; } 2>/dev/null || true`:** with SIGPIPE ignored, `printf` returns 1 on EPIPE, and `set -e` would abort; `|| true` swallows it. `safe_emit_hook_json` is this wrapper.

`plugins/pd/hooks/tests/probe-printf-sigpipe.sh` prints the outcome of all four combinations.

### The canonical pattern (`pd-session-start.sh`)

```bash
#!/usr/bin/env bash
set -uo pipefail
trap '' PIPE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/session-start-helpers.sh"
source "${SCRIPT_DIR}/lib/common.sh"
install_session_start_traps

# ... main work builds $text ...

safe_emit_hook_json "$(jq -nc --arg ctx "$text" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}')"
exit 0
```

- **`safe_emit_hook_json`** (`plugins/pd/hooks/lib/session-start-helpers.sh`) wraps `printf` in `{ …; } 2>/dev/null || true`.
- **`install_session_start_traps`** installs an EXIT trap that prints a fallback `{}` only when the hook exits non-zero, so the happy path's output is never doubled. Both trap handlers run `set +e` first.

### Test recipes

Each recipe closes the hook's output early; each must report `rc=0`. Run them with bash from the repository root:

```bash
# stdout closed before the first write
bash plugins/pd/hooks/pd-session-start.sh </dev/null | dd of=/dev/null bs=1 count=0; echo "rc=${PIPESTATUS[0]}"
# stdout closed after one byte
bash plugins/pd/hooks/pd-session-start.sh </dev/null | head -c 1 >/dev/null; echo "rc=${PIPESTATUS[0]}"
# stdout and stderr both closed
bash plugins/pd/hooks/pd-session-start.sh </dev/null \
    > >(dd of=/dev/null bs=1 count=0) \
    2> >(dd of=/dev/null bs=1 count=0); echo "rc=$?"
```

`test-hooks.sh` runs `plugins/pd/hooks/tests/probe-a1-exit0-under-broken-pipe.sh` with its stdout closed and fails unless it exits 0.

### Anti-pattern: do NOT remove `trap '' PIPE`

A contributor seeing the `printf … || true` pattern might assume the trap is left over. It isn't: without the trap, the bash process dies of SIGPIPE before `|| true` can recover. `probe-printf-sigpipe.sh` shows the exit codes.
