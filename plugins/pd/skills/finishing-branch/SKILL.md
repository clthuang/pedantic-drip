---
name: finishing-branch
description: The Finish stage's playbook — security review, docs, the metrics entry, the retro trigger check, the replan, then merge and cleanup. Use when a feature's phase is finish.
---

# Finishing a Branch

The conductor's playbook for `phase: finish`. Entry, exit and commits follow the `workflow-transitions` skill. Verify's exit check already passed when `phase:` moved here, and `pd-lint` re-runs it at every commit.

Order matters: the retro runs before cleanup, because branch and worktree cleanup destroy the evidence it reads.

## Steps

1. **Security review.** Mandatory when the frontmatter's `risk:` lists `security`. Otherwise run it when the branch diff (`git diff {pd_base_branch}...HEAD`) touches a security surface: auth, secrets, input parsing at a trust boundary, permissions, data deletion, dependency bumps.
   - **Dispatch `pd:security-reviewer` directly,** with the `Agent` tool on its Anthropic model. It is never the review call and never Codex. The prompt carries `shape.md`, the full branch diff, and "return only `{approved, issues[], summary}` JSON", and it ends with the dispatch-hygiene line.
   - **Record it** as a `review` entry naming `security-reviewer`, one issue line per finding.
   - **A blocker sends the feature back to Verify:** append `phase finish -> verify (back)` with `Reason:` and `Invalidates: nothing`, commit, and run the `verifying` skill. Verify's fixer works with a fresh budget of three fix cycles. When the feature returns, the security reviewer re-checks only its own findings.
2. **Docs:** run the `updating-docs` skill: the component sync, and publishing any artifact that became reference material.
3. **The `metrics` entry**, written once: `Mode: <mode>. Tokens: <n> (source: <gate state file>)`. `<n>` is the `tokens` value in the `Stop` gate's per-feature file, `~/.claude/pd/gate/<repo key>/<feature id>.json`. The repo key is the first 16 hex digits of the SHA-256 of `git remote get-url origin`, or of the repository root's path when there is no origin. If there is no file, write `Tokens: unknown (no gate state)`; never estimate.
4. **The retro trigger check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh finish <feature dir>`.
   - **A `retro.md missing` failure names the triggers:** run the `retrospecting` skill, then re-run the check until it passes.
   - **A pass with no retro owed:** append finish's `note` entry, `No retro trigger.`
5. **Replan, for a feature listed in a roadmap** (a `plans/*.md` whose `roadmap:` names `workitems/<id>`). Show the plan's computed state from `pd-status`, then append a `replan` entry: `Plan: plans/<plan id>.md — still holds.`, or what changed, with the roadmap edit in the same commit.
6. **Close:** set `status: done`, delete the `branch:` line, overwrite `## Now` with `Done.`, and commit `finish: <summary>`. The commit hook checks the done feature's entries.
7. **Merge** into `{pd_base_branch}`:
   ```bash
   git checkout {pd_base_branch} && git pull && git merge --no-ff workitem/<id> && git push
   ```
   - **A conflict is a hard stop** (AskUserQuestion): report the conflicted paths and leave both branches intact. Never force-push, and never resolve a conflict by discarding one side.
   - **PR path, when `{pd_base_branch}` requires pull requests:** `gh api repos/{owner}/{repo}/rules/branches/{pd_base_branch} --jq 'any(.[]; .type == "pull_request")'` prints `true` (gh fills in `{owner}/{repo}`). Instead of the merge above, run `git push -u origin workitem/<id>`, `gh pr create --base {pd_base_branch} --fill`, `gh pr checks --watch`, then `gh pr merge --merge --delete-branch`. A failing check is a hard stop, like a conflict. `--delete-branch` removes the branch locally and on the remote, so step 9 skips it.
8. **Release:** run `{pd_release_script}` if it is set and the file exists. Otherwise say none is configured.
9. **Cleanup, only after the merge:**
   - **Delete the branches** with `git branch -d workitem/<id>`, then each `pd/<id>/task-*` branch. Never `-D`: the safe delete refusing unmerged work is the guard.
   - **Run `${CLAUDE_PLUGIN_ROOT}/scripts/pd-lint --sweep`.** Delete the `agent_sandbox/` directories it lists for done items, and show the user the rest of its list.

## Entries this stage writes
`review` (the security review), `phase` (a move back to Verify), `metrics`, `note` (no retro trigger), `replan`, and `decision` (a user's ruling, such as waiving a security finding, quoted verbatim). `retro.md` comes from the `retrospecting` skill.

## Exit check
`phase-gate.sh finish`: `retro.md` exists when `log.md` records a retro trigger. `pd-lint` adds the done-feature checks: a `metrics` entry, and `retro.md` or finish's `note`.
