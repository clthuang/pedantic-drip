# Thin pd: component inventory (T1.1, 2026-10-15)

Every skill, command, agent and hook script under `plugins/pd/`, with its verdict (plan §A6, §16 step 3; D17). Counted on `feature/thin-pd-build` at T0.2: 27 skills, 31 commands, 24 agents, 16 hook scripts.

**The verdicts:**
- **`keep`:** its body stays as it is. Every agent still gets T4.1's frontmatter (`tools`, `model`, `effort`, `skills`), which doesn't count as a rewrite.
- **`keep-rewrite`:** stays, with its body rewritten onto files and native features (T4.5, or the task named).
- **`delete`:** goes in the T2.1 commit (D17: "delete straight away if there is no use for them in the new implementation").

**Two reasons recur, cited by tag:**
- **[A9-scope]:** §A9's last paragraph: the domain skills (data science, crypto analysis, game design, promptimize, specialist teams) "don't depend on the registry, so they port as they are, or are pruned by the user at S6's prune". General-purpose utilities that don't touch the registry (debugging, skill authoring, research-and-summarize) are treated the same way.
- **[no-use]:** no use in the new design (D17).

**The name column** is the path under `plugins/pd/`, so a skill and a command with the same name (`root-cause-analysis`, `promptimize`) stay distinct.

## Skills (27)

| Name | Verdict | Reason |
|---|---|---|
| skills/brainstorming | keep-rewrite | §A6: a phase skill, the conductor's Clarify playbook (T4.5a). Its `prd-reviewer` dispatch goes (S2) |
| skills/choosing-ds-modeling-approach | keep | [A9-scope] |
| skills/creating-specialist-teams | keep | [A9-scope] |
| skills/crypto-analysis | keep | [A9-scope] |
| skills/data-science-analysis | keep | [A9-scope] |
| skills/decomposing | keep-rewrite | §7.1: decomposing a PRD now writes a plan's `roadmap:` instead of `projects/<id>/`; it is `project-decomposer`'s caller, which §A6 keeps (judgment call 1) |
| skills/designing | keep-rewrite | §A6: a phase skill (T4.5c); its D12 diagram rule landed at T0.2 |
| skills/detecting-kanban | delete | [no-use]: the Kanban UI retires (§A6, the user's ruling); no caller |
| skills/finishing-branch | keep-rewrite | §A6: a phase skill (T4.5g); dispatches `security-reviewer` (§A4) |
| skills/game-design | keep | [A9-scope] |
| skills/implementing-with-tdd | delete | [no-use]: no caller; tests-first is now the executor brief plus the merger's `pd-proof` check (§A4), not a skill (judgment call 2) |
| skills/implementing | keep-rewrite | §A6: a phase skill (T4.5e); loses its hand-run worktree steps |
| skills/planning | keep-rewrite | §A6: a phase skill (T4.5d) |
| skills/promptimize | keep | [A9-scope] |
| skills/researching | keep | [A9-scope]: the research-dispatch contract `/pd:subagent-ras` loads; no registry use |
| skills/retrospecting | keep-rewrite | §A6: a phase skill (T4.5g); reads `log.md` instead of phase events |
| skills/root-cause-analysis | keep-rewrite | §A6: a phase skill (T4.5a); starts `rca-fanout` |
| skills/specifying | keep-rewrite | §A6: a phase skill (T4.5b) |
| skills/spotting-ds-analysis-pitfalls | keep | [A9-scope] |
| skills/structured-problem-solving | keep | [A9-scope]: an SCQA lens, no registry use |
| skills/structuring-ds-projects | keep | [A9-scope] |
| skills/systematic-debugging | keep | [A9-scope]: called by `root-cause-analysis` and `/pd:secretary`; no registry use |
| skills/updating-docs | keep | §A6: publishes artifacts to the human docs. Its `doctor.sh` reference is replaced by a T2.1 marker |
| skills/workflow-state | delete | [no-use]: the workflow engine's tool catalog; the engine retires (§A6) |
| skills/workflow-transitions | keep-rewrite | §A6: a phase skill (T4.5h); its engine calls become file writes |
| skills/writing-ds-python | keep | [A9-scope] |
| skills/writing-skills | keep | [A9-scope]: skill authoring for pd itself |

## Commands (31)

| Name | Verdict | Reason |
|---|---|---|
| commands/abandon-feature.md | keep-rewrite | §5: `abandoned` status with its reason in `log.md`; the command writes both instead of calling the registry |
| commands/add-to-backlog.md | keep-rewrite | §7: becomes a thin entry point to `pd-new backlog` |
| commands/brainstorm.md | keep-rewrite | §A2 row 1: Clarify's entry point |
| commands/cleanup-backlog.md | delete | [no-use]: archives backlog sections in the entity DB; replaced by `pd-lint --archive` (§7) |
| commands/cleanup-brainstorms.md | delete | [no-use]: deletes brainstorm files, which §10 now keeps forever |
| commands/create-feature.md | keep-rewrite | §A2 row 0: Triage's `pd-new feature`, including `--from` promotion |
| commands/create-plan.md | keep-rewrite | §A2 row 4: the Plan stage |
| commands/create-project.md | keep-rewrite | §7.1, §13: a project becomes a plan with a `roadmap:`; the entry point to `decomposing` (judgment call 1) |
| commands/create-specialist-team.md | keep-rewrite | [A9-scope], but it reads `.meta.json` for the active feature; that becomes the README frontmatter (§5) |
| commands/design.md | keep-rewrite | §A2 row 3: the Contracts stage |
| commands/doctor.md | delete | [no-use]: `pd-lint` takes over the doctor's role (§A6) |
| commands/finish-feature.md | keep-rewrite | §A2 row 7: the Finish stage |
| commands/generate-docs.md | keep | [A9-scope]: scaffolds the human doc tiers (`doc_tiers`, §12); no registry use |
| commands/implement.md | keep-rewrite | §A2 row 5: starts `implement-tasks`; its review gate and circuit breaker go to `verify-change` (§A6) |
| commands/init-ds-project.md | keep | [A9-scope] |
| commands/list-features.md | delete | [no-use]: replaced by `pd-status` (§A6) |
| commands/promptimize.md | keep | [A9-scope] |
| commands/refresh-prompt-guidelines.md | keep | [A9-scope]: maintains `promptimize`'s guidelines |
| commands/retrospect.md | keep-rewrite | §A2 row 7, §A8.3 S4: the retro on a trigger |
| commands/review-ds-analysis.md | keep | [A9-scope] |
| commands/review-ds-code.md | keep | [A9-scope] |
| commands/root-cause-analysis.md | keep-rewrite | §A2 row 1: a bug's Clarify entry point |
| commands/secretary.md | keep-rewrite | §A6: Triage (§A2 row 0) |
| commands/show-lineage.md | delete | [no-use]: replaced by `pd-status` (§A6) |
| commands/show-status.md | delete | [no-use]: replaced by `pd-status` (§A6) |
| commands/specify.md | keep-rewrite | §A2 row 2: the Criteria stage |
| commands/subagent-ras.md | keep | [A9-scope]: research-and-summarize; no registry use |
| commands/sync-cache.md | keep | pd's own dev loop: publishes plugin source to the cache; no registry use |
| commands/test-debt-report.md | delete | [no-use]: reads `.qa-gate.json`, which §9 forbids after adopt; follow-ups now go to `backlog.md` through `capped` entries (§A2) |
| commands/wrap-up.md | keep-rewrite | §6, §13: a session bookend that writes `## Now` and a `handoff` entry instead of reading engine state (judgment call 3) |
| commands/yolo.md | delete | [no-use]: replaced by `/goal` and the `Stop` gate (§A6) |

`/pd:init`, `/pd:adopt` and the `verifying` skill are new (T4.5f, T4.8, T4.9), so they have no row here.

## Agents (24)

§A6 keeps 21 of the 24, retires three (S2), and adds `merger` and `calvin-runner` (T4.1).

| Name | Verdict | Reason |
|---|---|---|
| agents/advisor.md | keep | §A4: `research-fanout`'s advisor lenses |
| agents/code-quality-reviewer.md | keep | §A3: the code review's Claude fallback; T4.1 sets reviewer tools and the strongest model |
| agents/codebase-explorer.md | keep | §A2 row 3, §A4: grounds Contracts; a `research-fanout` researcher |
| agents/design-reviewer.md | keep | §A3: the design review's Claude fallback; T4.1 sets reviewer tools and preloads `designing` |
| agents/documentation-researcher.md | keep | §A6: `updating-docs`' dispatch |
| agents/documentation-writer.md | keep | §A6: `updating-docs`' dispatch |
| agents/ds-analysis-reviewer.md | keep | [A9-scope] |
| agents/ds-code-reviewer.md | keep | [A9-scope] |
| agents/generic-worker.md | keep | [A9-scope]: `creating-specialist-teams`' worker |
| agents/implementer.md | keep-rewrite | §A3: the executor (`sonnet`, `effort: medium`, the verification paragraph), plus the fixer brief |
| agents/internet-researcher.md | keep | §A4, §A8.3 S5: Clarify's researcher |
| agents/investigation-agent.md | keep | §A6 counts it among the 21; no caller names it today (judgment call 4) |
| agents/plan-reviewer.md | keep | §A6, D14: the test-case review's Claude fallback; T4.1 sets reviewer tools |
| agents/prd-reviewer.md | delete | §A8.3 S2: calvin covers it |
| agents/project-decomposer.md | keep | §A6 counts it; `decomposing`'s dispatch (judgment call 1) |
| agents/project-decomposition-reviewer.md | keep | §A6 counts it; `decomposing`'s dispatch (judgment call 1) |
| agents/qa-executor.md | keep | §A3: QA; T4.1 sets the strongest model, T4.2 limits its writes to `agent_sandbox/` |
| agents/ras-synthesizer.md | keep-rewrite | §A4: `research-fanout`'s synthesizer; its "entity registry" work-context source goes |
| agents/rca-investigator.md | keep | §A4: `rca-fanout`'s investigator; the refuter brief travels in the workflow's prompt |
| agents/relevance-verifier.md | delete | §A8.3 S2: `from_shape:` and the test-case review cover it |
| agents/retro-facilitator.md | keep-rewrite | §A2 row 7: re-derives figures from `log.md` and git; strongest model |
| agents/security-reviewer.md | keep | §A4: dispatched by `finishing-branch` on Anthropic models; T4.1 sets reviewer tools |
| agents/skill-searcher.md | keep | §A4: a `research-fanout` researcher |
| agents/test-deepener.md | delete | §A8.3 S2: QA's job |

## Hook scripts (16)

| Name | Verdict | Reason |
|---|---|---|
| hooks/cleanup-locks.sh | delete | [no-use]: SQLite lock recovery retires with the registry (§A9) |
| hooks/cleanup-sandbox.sh | delete | [no-use]: registered nowhere, called by nothing; `pd-lint --sweep` covers it (§10) |
| hooks/cleanup-stale-versions.sh | keep | Plugin-cache hygiene (feature 087), not registry machinery |
| hooks/data-file-guard.sh | delete | [no-use]: the data-file guards retire (§A9); `pd-lint` guards the files |
| hooks/inject-secretary-context.sh | delete | A YOLO hook: it runs only in YOLO mode, which retires (§A5) |
| hooks/post-enter-plan.sh | delete | [no-use]: plan-mode review instructions, part of the plan-mode review gate that retires with `pre-exit-plan-review.sh` and `plan_mode_review` (§A6, §12) |
| hooks/post-exit-plan.sh | delete | [no-use]: steers plan approval into the registry workflow (`.meta.json`, `/pd:show-status`); same retirement |
| hooks/pre-commit-guard.sh | keep-rewrite | §A6 ("the commit … guards" may stay): keeps the protected-branch block; drops its `pd_state_diff.py` call |
| hooks/pre-edit-unicode-guard.sh | keep | §A6 names the unicode guard; uses only `pre-edit-unicode-guard.py` |
| hooks/pre-exit-plan-review.sh | delete | §A6, §A8.3 S2 |
| hooks/pre-push-guard.sh | delete | [no-use]: its only check is `.meta.json` consistency, and `.meta.json` retires (§13) |
| hooks/session-start.sh | delete | §A6: replaced by the new `pd-session-start.sh` (T4.7) |
| hooks/start-ui-server.sh | delete | §A6: the Kanban UI retires |
| hooks/sync-cache.sh | keep | pd's own dev loop: publishes plugin source to the cache; no registry use |
| hooks/yolo-guard.sh | delete | A YOLO hook (§A5) |
| hooks/yolo-stop.sh | delete | A YOLO hook (§A6); T4.6 ports it from `git show <pre-T2.1>` |

## Totals

| | keep | keep-rewrite | delete | all |
|---|---|---|---|---|
| Skills | 14 | 10 | 3 | 27 |
| Commands | 8 | 15 | 8 | 31 |
| Agents | 18 | 3 | 3 | 24 |
| Hook scripts | 3 | 1 | 12 | 16 |

## What else goes in T2.1

Not inventory rows, but files that serve only deleted components or the registry (T2.1's file list):
- **The registry's code:** `plugins/pd/hooks/lib/{workflow_engine,entity_registry,transition_gate,reconciliation_orchestrator,doctor,data_file_guards,qa_gate,pattern_promotion,semantic_memory,pd_config}`, `sqlite_retry.py`, `yolo_deps.py` and their tests; `plugins/pd/mcp/`; `plugins/pd/ui/`. `transition_gate` goes only after T1.2's guard map is committed.
- **Scripts serving deleted rows:** `plugins/pd/scripts/{doctor.sh,pd_state_diff.py,test_debt_report.py,cleanup_backlog.py,parse_backlog_md.py,compare_backlog_projection.py}`.
- **Config:** `plugins/pd/hooks/data_file_guards.json`, the `hooks.json` entries of deleted hooks, `plugin.json`'s `mcpServers`.
- **References:** `plugins/pd/references/codex-routing.md` (§A6: the review call replaces it, T4.3).
- **Stays, because a kept hook uses it:** `hooks/lib/common.sh` and `hooks/lib/session-start-helpers.sh` (`pre-commit-guard.sh`, `sync-cache.sh`), `hooks/pre-edit-unicode-guard.py`.

T2.1 re-checks each of these with `grep` before deleting it; a caller found in a kept file gets the T2.1 marker.

## Judgment calls for the user's review

The verdicts above that the plan doesn't settle by name. T2.1's AskUserQuestion puts these to the user with the diff.
1. **`decomposing`, `/pd:create-project` and the two decomposer agents: keep.** §A6 keeps the agents, and their only caller is `decomposing`. Rewritten, they write a plan's `roadmap:` (§7.1). The alternative is to delete all four and write roadmaps by hand, since §14 defers `pd-plan` commands.
2. **`implementing-with-tdd`: delete.** Nothing calls it; the merger enforces tests-first mechanically. It is also a skill the user can invoke by saying "use TDD".
3. **`/pd:wrap-up`: keep, rewritten** to write `## Now` and a `handoff` entry (§13 names `handoff` entries as the HANDOFF.md replacement). The alternative: delete it, and the conductor writes the entry unprompted.
4. **`investigation-agent`: keep,** because §A6 counts 21 kept agents. Nothing calls it today; under D17 it would go. Deleting it makes §A6's count 20.

## Proof

Run from the repository root:

```bash
# The names match (prints nothing).
comm -3 <(cd plugins/pd && ls -d skills/*/ commands/*.md agents/*.md hooks/*.sh | sed 's:/$::' | sort) \
        <(grep -oE '^\| (skills|commands|agents|hooks)/[^ |]+' docs/plans/2026-10-14-thin-pd/inventory.md | cut -c3- | sort)
# Every row has a verdict (prints nothing).
grep -E '^\| (skills|commands|agents|hooks)/' docs/plans/2026-10-14-thin-pd/inventory.md | awk -F' \\| ' '$2 !~ /^(keep|keep-rewrite|delete)$/'
# §A6's named components (prints the expected verdicts).
grep -E '^\| (agents/(prd-reviewer|relevance-verifier|test-deepener|plan-reviewer)\.md|hooks/(pre-exit-plan-review|yolo-guard|yolo-stop|inject-secretary-context)\.sh|skills/updating-docs) ' docs/plans/2026-10-14-thin-pd/inventory.md | cut -d'|' -f2,3
```
