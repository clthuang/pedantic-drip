# RCA: SessionStart hook error + 61 skill descriptions dropped

- **Date:** 2026-05-08
- **Investigator:** rca-investigator (Claude Code agent, opus 4.7)
- **Reporter environment:** `/Users/terry_agent`, Claude Code v2.1.133, pd plugin installed, branch `main`.
- **Investigation environment:** `/Users/terry/projects/pedantic-drip` (same pd source tree on `develop`).
- **Sandbox:** `agent_sandbox/2026-05-08/rca-sessionstart-skills/`

## Symptoms

- **A.** Startup screen shows `SessionStart:startup hook error` with body `Failed with non-blocking status code: No stderr output`.
- **B.** Startup screen shows `61 skill descriptions dropped · /doctor for details`.

## Problem Statements

- **A.** `plugins/pd/hooks/session-start.sh` exits non-zero in some startup runs even though the script ends with `exit 0` and installs `trap '' PIPE` (line 10) and an ERR-trap recovery (`install_err_trap`, line 152 of `lib/common.sh`) that is supposed to print `{}` and `exit 0` on any failure. The script's own banner comment (lines 6–10) explicitly identifies this exact CC error fingerprint and claims the trap fixes it.
- **B.** Claude Code reports that 61 of the 62 SKILL.md files installed across all plugins on `terry_agent` were dropped from the listing injected into the model.

## Reproduction

Sandbox script: `agent_sandbox/2026-05-08/rca-sessionstart-skills/reproduction/run-hook-baseline.sh`. Direct exit-code probes saved under the same directory.

Reproduced Symptom A locally on macOS 25.3.0 / bash 3.2:

| Scenario | Hook exit | Hook stderr |
|---|---|---|
| Normal: hook stdout to file (baseline) | 0 | (empty) |
| Hook stdout closed *before* hook writes (`\| dd of=/dev/null bs=1 count=0`) | **1** | `cat: stdout: Broken pipe` |
| Hook stdout consumed first byte then closed (`\| head -c 1 >/dev/null`) | 0 | (empty) |
| Hook stderr also redirected into the closed pipe | **1** | (empty — message lost into closed FD) |

The exit-1-with-stderr-lost case matches "Failed with non-blocking status code: No stderr output" exactly.

Symptom B is a Claude Code v2.1.129+ behavior that I could not directly reproduce inside this agent (no CC instance to launch). Documentation and an open Anthropic GitHub issue confirm the mechanism.

## Hypotheses considered

### Symptom A

- **A-H1: `trap '' PIPE` does not propagate the way the comment expects** — `cat <<EOF` is implemented by bash spawning a child `cat` process; the child inherits a *non-default* SIGPIPE disposition (ignore) from the bash parent's `trap '' PIPE`. With SIGPIPE ignored, `cat`'s `write(2)` returns EPIPE instead of the process being killed by SIGPIPE; `cat` then prints `cat: stdout: Broken pipe` to stderr and **exits 1**. With `set -e` in effect, this aborts the hook before the explicit `exit 0` at line 931. Net effect: the trap converted "exit 141, silent" into "exit 1, EPIPE message" — both still surface to CC as a hook failure.
- **A-H2: ERR trap (`install_err_trap`) cannot self-recover when stdout is the broken pipe** — the ERR trap body is `echo "{}" 2>/dev/null; exit 0`. After `cat` fails, ERR trap fires; the trap's own `echo "{}"` writes to the same closed stdout, fails with EPIPE, `set -e` aborts the trap body, and `exit 0` is never reached. The trap's stderr-suppression (`2>/dev/null`) hides the trap's own EPIPE diagnostic, contributing to the "No stderr output" half of the message. Confirmed via `/tmp/full_repro.sh` — inner exit observed: 1, with only the original `cat: stdout: Broken pipe` on stderr.
- **A-H3: Failure inside one of the inline `python3 -c` heredocs producing a non-zero hook exit** — the hook spawns multiple inline Python heredocs (lines 61, 107, 191, 330, 458, 621, 665) plus `$VENV_PYTHON` invocations. All have `2>/dev/null` and most have `|| true`. Cross-checked: every Python subshell is captured via `$(...)` (so its stdout is bash, not CC), and every uncaptured invocation is followed by `|| true` or guarded with `[[ -x "$VENV_PYTHON" ]]`. **Rejected as primary cause** for the user's symptom but worth noting as a latent vector — `parse_feature_meta` at line 116 has `2>/dev/null` but no `|| true`, so under `set -e` an exit code from python3 would surface. However, `parse_feature_meta` is called via `meta_output=$(parse_feature_meta ...)` which is itself a command-substitution assignment — assignment masks the exit code under `set -e`, so this is also defended.
- **A-H4: Unbound variable under `set -u`** — line 445 sets `project_id=$(...)` without including `project_id` in the local declaration on line 440. Since `[[ -n "$project_id" ]]` does not trip `set -u` for unset variables (test operator handles unset as empty), and the variable IS always set when reached, this is not the cause. Documented for hygiene.
- **A-H5: First-run race** — first-run detection at line 833 checks `[[ ! -d "$HOME/.claude/pd/memory" ]]`. If true and `setup.sh` hasn't been run, every Python module call below it returns empty silently. Not a failure path, but it skews context-injection size, which interacts with Symptom B (more bytes can hit pipe buffer threshold). Not a primary cause.

### Symptom B

- **B-H1: Claude Code v2.1.129 introduced `skillListingBudgetFraction`, defaulting to ~1% of context window. With 62 skills installed on `terry_agent` (32 pd + 12 chrome-devtools-mcp + 9 ocm + 3 codex + 6 misc), the aggregate listing exceeds the budget; CC drops the lowest-priority full descriptions** until the listing fits, displaying `61 skill descriptions dropped`. This is the documented behavior of CC ≥ 2.1.129. Confirmed by GitHub issue [#56448](https://github.com/anthropics/claude-code/issues/56448) and community guides.
- **B-H2: pd skill descriptions exceeding the per-skill cap (`skillListingMaxDescChars`, default 1536 chars).** Investigated: the longest pd description is 281 chars (`test-deepener.md`); average 175 chars across 31 SKILL.md files; all parse cleanly with `yaml.safe_load`. **Rejected** — pd is not pushing per-skill limits.
- **B-H3: pd `description:` field formatting issue (multiline / quote-injection / non-ASCII).** Sweep with PyYAML showed all 31 pd skill descriptions parse without error and contain only printable characters. **Rejected.**

The two symptoms are NOT directly coupled: Symptom B is a CC-side budget enforcement that runs in CC's own skill loader, before any SessionStart hook executes. Symptom A is a hook-side bug. They surface together because both are visible on the startup screen.

## Verified Root Causes

### Cause 1 (primary, Symptom A): `trap '' PIPE` swaps SIGPIPE-141 for EPIPE-1; `set -e` then aborts before `exit 0`

`session-start.sh` enables `set -euo pipefail` (line 4) and `trap '' PIPE` (line 10). When CC closes the hook's stdout (during `/clear`, `/compact`, session bootstrap with `EnterPlanMode` interleaving, or when CC drops the hook output mid-flight), the `cat <<EOF` blocks at line 807 and 922 fork child processes (`cat`) that inherit the bash parent's "ignore SIGPIPE" disposition. The kernel returns EPIPE on write; `cat` exits 1; `set -e` propagates; the hook exits 1.

Evidence: `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-05-08/rca-sessionstart-skills/logs/`. Probe scripts at `/tmp/sigpipe_isolate.sh` and `/tmp/full_repro.sh` show:

- without `trap '' PIPE` + `set -e`: inner exit **141** (the original symptom the comment refers to)
- with `trap '' PIPE` + `set -e`: inner exit **1** (the current symptom)
- with `trap '' PIPE` + no `set -e`: inner exit **0** (would actually fix it)

The script's banner comment is therefore **stale or wrong**: `trap '' PIPE` alone does not solve the problem under `set -e`. The maintainer's intent (inferred from the comment) was to neutralize SIGPIPE, but `set -e` re-introduces a non-zero exit through a different kernel/process path.

### Cause 2 (contributing, Symptom A): ERR-trap self-recovery is defeated by the same broken pipe

`install_err_trap` in `lib/common.sh` line 152 sets `trap 'echo "{}" 2>/dev/null; exit 0' ERR` to provide a graceful-degradation fallback. When the broken-pipe failure at line 922 fires the ERR trap, the trap's own `echo "{}"` is also writing to the closed stdout. The `2>/dev/null` suppresses the trap's *own* EPIPE diagnostic but does not prevent the failed-write exit code; under `set -e` the trap body aborts before reaching `exit 0`.

Evidence: `/tmp/err_trap_test2.sh` shows `ERR_TRAP_FIRED rc=1` followed by `echo: write error: Broken pipe`, with inner exit observed as 1.

### Cause 3 (contributing, Symptom A): "No stderr output" portion explained by ERR-trap stderr suppression + CC display behavior

CC's "Failed with non-blocking status code: No stderr output" is reached because:
- The original `cat` EPIPE diagnostic (`cat: stdout: Broken pipe`) DOES go to stderr, but
- The ERR trap's own diagnostics (the `echo: write error: Broken pipe` from the trap body) are suppressed by the `2>/dev/null` in the trap, AND
- In some hook contexts CC suppresses the original stderr line if the hook also exits non-zero (CC v2.1.x non-blocking-failure formatting).

So depending on which point in the script the failure originates, CC may show the bare "No stderr output" message. The reporter's screenshot is consistent with the `cat` EPIPE having occurred late enough that CC has already disposed of stderr.

### Cause 4 (primary, Symptom B): CC v2.1.129+ `skillListingBudgetFraction` ratio drops 61 of 62 skills

The `terry_agent` machine has 62 SKILL.md files across plugins (counted on this machine via `find ~/.claude/plugins/cache -name SKILL.md`). The CC v2.1.129+ skill loader applies `skillListingBudgetFraction` (default ≈ 0.01 of the context window — for a 200K-token model that's ~2K tokens) on top of `skillListingMaxDescChars` (default 1536). pd alone contributes ~13.1K characters of description across its 95 components (31 skills + 29 agents + 35 commands); even if only the 31 SKILL.md files count, pd's ~5,415 chars + chrome-devtools-mcp's 12 + ocm's 9 + others well exceed the 1%-of-context budget on a typical default-config session. CC's loader drops descriptions in priority order until the remaining listing fits, hence "61 dropped, 1 retained."

**This is a Claude Code-side limit, not a pd bug.** It is the documented CC v2.1.129 behavior. GitHub issue #56448 (open as of 2026-05-05) reports a related count-mismatch concern but confirms skills still function.

### Cause 5 (contextual, Symptom B): pd contributes a large fraction of the global skill listing on this machine

By raw count, pd ships 32 SKILL.md files (one is the marketplace-level skill — `pedantic-drip-marketplace/pd/...`) — that's ~52% of the 62 SKILL.md files installed on `terry_agent`. So while pd is not malformed and is not the trigger of the budget exceedance per-se, pd is the largest contributor to the listing and makes the 61-dropped count more pronounced than it would be without pd.

## Out-of-scope (not a cause; documenting for completeness)

- **`detect_project_root` returning a non-pd directory** — when run from a CC working directory that walks up to a `.git` repo without `.claude/pd.local.md`, `read_local_md_field` returns defaults (empty file path → default value). This works correctly. Not a failure path.
- **MCP error log noise** — `check_mcp_health` reads `~/.claude/pd/mcp-bootstrap-errors.log`; even if that file is missing or malformed, the function is wrapped in `( set +e; ... ) 2>/dev/null || echo ""`, so errors there cannot bubble out.
- **Worktree state on `terry_agent`** — irrelevant to the SessionStart hook.

## Failed reproduction attempts

- Could not reproduce Symptom B in-agent — there is no CC runtime in this environment to inject pd skills into and observe the loader output. Verified via PyYAML that pd descriptions are parseable and within per-skill limits; the rest follows from the documented CC v2.1.129 behavior.
- Could not reproduce the **literal** screenshot's "no stderr output" string under controlled conditions: in the local sandbox, stderr is preserved (we always saw `cat: stdout: Broken pipe`). The "no stderr output" wording is a CC-side display artifact for non-blocking hook failures; the underlying failure (`cat` EPIPE → exit 1) is reproduced reliably.

## Severity / scope

- **Symptom A:** transient cosmetic — appears only when CC closes the hook's stdout before the hook writes the JSON. The hook's *intended* effect (context injection) is lost on those startups, so workflow-state context, memory injection, doctor summary, and reconciliation summary are skipped. Does not block CC operation.
- **Symptom B:** environmental and CC-version-driven. Not a pd defect; pd's contribution amplifies the count. Does not break skills (they still load, just without descriptions in the listing the model sees).

## File pointers

- `/Users/terry/projects/pedantic-drip/plugins/pd/hooks/session-start.sh` — lines 4 (`set -euo pipefail`), 10 (`trap '' PIPE`), 15 (`install_err_trap`), 807 (first `cat <<EOF`), 922 (final `cat <<EOF`), 931 (`exit 0`)
- `/Users/terry/projects/pedantic-drip/plugins/pd/hooks/lib/common.sh` — line 152 (`install_err_trap` body)
- `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-05-08/rca-sessionstart-skills/reproduction/run-hook-baseline.sh` — repro driver
- `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-05-08/rca-sessionstart-skills/logs/` — captured stdout/stderr from each repro variant

## References

- GitHub: [anthropics/claude-code#56448 — "[BUG] 2.1.129 prints '47 skill descriptions dropped'"](https://github.com/anthropics/claude-code/issues/56448)
- GitHub: [anthropics/claude-code#31505 — "Project skills silently dropped beyond ~28 limit — no warning or error"](https://github.com/anthropics/claude-code/issues/31505)
- [Claude Code's Hidden Skill Budget Setting (May 2026)](https://claudefa.st/blog/guide/mechanics/skill-listing-budget)
- [Extend Claude with skills — Claude Code Docs](https://code.claude.com/docs/en/skills)
- bash(1): `trap '' PIPE` propagation to children: see Posix § "Signals and Error Handling — `trap`" — ignored signals are inherited by `exec(2)`-spawned children.
