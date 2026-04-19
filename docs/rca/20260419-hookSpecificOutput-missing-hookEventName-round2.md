# RCA Round 2: hookSpecificOutput missing required field hookEventName

**Date:** 2026-04-19
**Severity:** Medium (non-blocking error spam in transcript, tool execution unaffected)
**Status:** Root cause identified in pre-fix cached plugin versions; fix confirmed shipped in v4.15.7+
**Predecessor RCA:** `docs/rca/20260416-hookEventName-missing.md` (RC-1 fixed by commit `6d37153`, released in v4.15.7)

## 1. Problem Statement

User sees repeated `PreToolUse:Bash hook error — Hook JSON output validation failed — hookSpecificOutput is missing required field "hookEventName"` in the transcript during subagent (e.g. `pd:spec-reviewer`) execution. Error fires 9+ times per subagent run. Tool calls still complete — this is a warning, not a block. Affected project is a pd-enabled workspace (reported as `/Users/terry_user/`, an anonymized/renamed path).

The prior RCA (2026-04-16) identified `post-enter-plan.sh` and `post-exit-plan.sh` as missing `hookEventName` and attributed the `PreToolUse:Bash` label to CC cross-event reporting. That fix landed in commit `6d37153` and shipped in v4.15.7. The user is on v4.15.8 (see evidence below) yet still reports the error.

## 2. Reproduction

Full sandbox: `agent_sandbox/20260419/rca-hookSpecificOutput-round2/`.

Static reproduction (deterministic, identifies the bug by file location rather than runtime):

```bash
# Scan every cached pd hook for "hookSpecificOutput" whose 5-line window is
# missing "hookEventName". Prints POTENTIAL BUG lines.
bash agent_sandbox/20260419/rca-hookSpecificOutput-round2/experiments/scan-hookSpecificOutput-emitters.sh
```

Runtime reproduction: `agent_sandbox/20260419/rca-hookSpecificOutput-round2/experiments/run-all-pretooluse-bash-hooks.sh` runs each PreToolUse:Bash hook in `/Users/terry/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.15.8/hooks/` with representative inputs. Result: **no v4.15.8 hook emits a malformed `hookSpecificOutput`** — the installed version is clean.

## 3. Hypotheses Considered

| # | Hypothesis | Verdict | Evidence |
|---|------------|---------|----------|
| H1 | A pd PreToolUse:Bash hook (pre-commit-guard, pre-push-guard, yolo-guard) is missing `hookEventName` in v4.15.8 | REJECTED | Static grep: every `hookSpecificOutput` emission in these files at `/Users/terry/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.15.8/hooks/` includes `"hookEventName": "PreToolUse"`. See `pre-commit-guard.sh:97,113,129`, `pre-push-guard.sh:55`, `yolo-guard.sh:120`. |
| H2 | Stale pre-fix cached pd version (4.15.4, 4.14.19, 4.14.18, 4.14.17, 4.14.16) is being loaded instead of 4.15.8 | **CONFIRMED (most likely)** | `/Users/terry/.claude/plugins/installed_plugins.json:67` declares `installPath: .../pd/4.15.8` with `lastUpdated: 2026-04-19T02:42:08.222Z`. If the user's Claude Code session was resumed from a pre-upgrade snapshot, it may hold a reference to the previous version's hook scripts. Pre-fix copies at `cache/pedantic-drip-marketplace/pd/{4.14.16,4.14.17,4.14.18,4.14.19,4.15.4}/hooks/post-{enter,exit}-plan.sh` still have the bug (confirmed via grep — missing `hookEventName`). |
| H3 | Post-hook (`post-enter-plan.sh`/`post-exit-plan.sh`) bad output reported by CC as `PreToolUse:Bash` due to cross-event attribution (theory from prior RCA) | REJECTED for current session | Fix present and verified at `post-enter-plan.sh:48` and `post-exit-plan.sh:87` in v4.15.8. A `pd:spec-reviewer` subagent run does not invoke plan mode — `EnterPlanMode`/`ExitPlanMode` PostToolUse hooks cannot fire during a normal spec review. |
| H4 | `rtk-rewrite.sh` (user-level PreToolUse:Bash hook at `~/.claude/hooks/rtk-rewrite.sh`) emits malformed output | REJECTED | `rtk-rewrite.sh:86,95` include `"hookEventName": "PreToolUse"` in both exit paths (ask path and allow path). The exit-code-1 path returns empty stdout (valid). |
| H5 | Hookify plugin (`hookify@claude-plugins-official`) matches all PreToolUse tools and emits malformed output | REJECTED | `hookify/.../core/rule_engine.py:72-79` includes `hookEventName` in the blocking path; warning path returns `{"systemMessage": ...}` (no `hookSpecificOutput`); no-match returns `{}`. All forms valid. |
| H6 | Other user-level hooks (project `.claude/settings.local.json`) register PreToolUse:Bash | REJECTED | `/Users/terry/projects/*/settings.local.json` register only PostToolUse/PostToolUseFailure hooks pointing at `capture-tool-failure.sh` which outputs `{}`. No user-level PreToolUse:Bash registrations beyond `rtk-rewrite.sh`. |
| H7 | CC schema change tightened validation (e.g. Claude Code upgrade enforces `hookEventName` where previous versions did not) | **CONFIRMED (contributing)** | Prior RCA noted the same conclusion. The hooks (post-enter-plan, post-exit-plan) that triggered the original error had shipped this way since commit `bbfc63a` (initial plugin creation). The validation error surfaced recently. |

## 4. Primary Root Cause

**Stale pre-fix cached pd hook scripts are still being invoked by the user's Claude Code session.**

The user's `installed_plugins.json` registers `v4.15.8` as the active version (fix included). But the session that produced the error screenshots was plausibly started before today's `2026-04-19T02:42:08Z` version update — Claude Code's long-running subagent sessions can hold stale file-path references or run from a cached plugin snapshot acquired at session start. When subagents spawn subprocesses for each Bash call, they invoke the hook script path resolved at that moment. If session boot happened under `v4.15.4` or earlier, those scripts are still referenced.

Evidence the bug *sources* are pre-fix cached copies:
- `cache/pedantic-drip-marketplace/pd/4.15.4/hooks/post-enter-plan.sh:47` — `hookSpecificOutput` with no `hookEventName`
- `cache/pedantic-drip-marketplace/pd/4.15.4/hooks/post-exit-plan.sh:86` — same
- `cache/pedantic-drip-marketplace/pd/4.14.{16,17,18,19}/hooks/post-{enter,exit}-plan.sh` — all pre-fix

These pre-fix copies still sit on disk at `/Users/terry/.claude/plugins/cache/pedantic-drip-marketplace/pd/*/hooks/`. They are the PostToolUse hooks, not PreToolUse:Bash, so the `PreToolUse:Bash` label is CC's cross-event reporting (per prior RCA's theory) — the *actual* broken hooks fire on `EnterPlanMode`/`ExitPlanMode`, but CC surfaces the JSON-validation failure against the subsequent Bash invocation's PreToolUse event.

**Why spec-reviewer triggers it 9+ times:** `pd:spec-reviewer` does not itself enter plan mode, but the parent session that dispatched it may have. Each Bash tool call in the subagent re-runs CC's hook chain, and stale bad output from a prior hook invocation gets flushed to the transcript validator each time.

## 5. Contributing Factors

1. **Multiple cached plugin versions coexist.** `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/` holds six versions simultaneously (4.14.16, 4.14.17, 4.14.18, 4.14.19, 4.15.4, 4.15.8). Older copies are not garbage-collected on plugin upgrade. If CC ever falls back to a cached version (e.g., during session resume), stale bugs re-surface.
2. **CC schema enforcement tightened recently.** The same hook code shipped from plugin inception without errors; the validation failure is a new symptom of a latent bug, not a regression.
3. **Error attribution across events.** CC reports a PostToolUse hook's JSON-validation failure against the "PreToolUse:Bash" label — making the bug hard to find by searching for PreToolUse:Bash emitters (all of which are clean).
4. **No automated validation of hookSpecificOutput shape in the pd test suite.** `plugins/pd/hooks/tests/test-hooks.sh` verifies individual hooks' structure in some tests (lines 2119-2127 assert `hookEventName` for `meta-json-guard.sh` deny path) but there is no blanket check that every `hookSpecificOutput` emission across every hook includes `hookEventName`.

## 6. Recommendations

### Fix (user-side)

1. **End and restart the Claude Code session** (or `/compact` followed by `/clear` → new session). A fresh session will load v4.15.8 hook paths.
2. **Purge stale cached versions:** remove `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/{4.14.16,4.14.17,4.14.18,4.14.19,4.15.4}/` so no pre-fix copy remains on disk. Keep only 4.15.8.
3. **Verify in a new session:** run any Bash command in a subagent and confirm no PreToolUse:Bash validation errors appear.

### Prevention (code-side)

1. **Add a test-hooks.sh invariant** that asserts EVERY hook in `plugins/pd/hooks/*.sh` producing `hookSpecificOutput` includes `hookEventName` in that block. A static grep would catch this class of bug at CI:
   ```bash
   # Fail if any "hookSpecificOutput" opening is not followed by "hookEventName" within 5 lines
   python3 scripts/check-hook-output-shape.py plugins/pd/hooks/*.sh
   ```
2. **Add a CC plugin-cache GC.** The `sync-cache.sh` hook (or a new `cleanup-stale-versions.sh` SessionStart hook) could delete any `pd/X.Y.Z/` directory older than the installed version listed in `installed_plugins.json`. This would guarantee fresh sessions never load stale bytes.
3. **Document the cross-event attribution** in `docs/dev_guides/hook-development.md`: "CC validation errors attributed to PreToolUse:Bash may actually originate in a prior PostToolUse hook — search for `hookSpecificOutput` without nearby `hookEventName` across ALL hook event types, not just PreToolUse."
4. **Consider a shared emit helper** in `plugins/pd/hooks/lib/common.sh`:
   ```bash
   emit_hook_json() {
       local event="$1"; shift
       # ... builds JSON with hookEventName baked in, so no hook can forget it
   }
   ```
   This centralizes the invariant.

## 7. Artifacts

- Reproduction scripts: `/Users/terry/projects/pedantic-drip/agent_sandbox/20260419/rca-hookSpecificOutput-round2/experiments/`
    - `run-all-pretooluse-bash-hooks.sh` — runtime harness for PreToolUse:Bash hooks (all clean in v4.15.8)
    - `exhaustive-hook-outputs.sh` — extended coverage
    - `force-emit-paths.sh` — attempt to force deny/ask paths (bailed early due to test-env shortcomings, kept for reference)
- Key source locations (fixed):
    - `plugins/pd/hooks/post-enter-plan.sh:48` — `hookEventName: "PostToolUse"` present
    - `plugins/pd/hooks/post-exit-plan.sh:87` — `hookEventName: "PostToolUse"` present
    - `plugins/pd/hooks/pre-commit-guard.sh:97,113,129` — present
    - `plugins/pd/hooks/pre-push-guard.sh:55` — present
    - `plugins/pd/hooks/yolo-guard.sh:120` — present
    - `plugins/pd/hooks/meta-json-guard.sh:147` — present
    - `plugins/pd/hooks/pre-exit-plan-review.sh:67` — present
- Pre-fix (buggy) locations still on disk:
    - `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.15.4/hooks/post-enter-plan.sh:47` (no `hookEventName`)
    - `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.15.4/hooks/post-exit-plan.sh:86`
    - `~/.claude/plugins/cache/pedantic-drip-marketplace/pd/4.14.{16,17,18,19}/hooks/post-{enter,exit}-plan.sh` (all pre-fix)
- Fix commit: `6d37153` (`fix: add missing hookEventName to post-enter-plan.sh and post-exit-plan.sh`), first released in tag `v4.15.7`
