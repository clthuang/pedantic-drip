# Backlog

- [ ] 2026-11-01-pd-codebase-explorer-uses-codegraph — pd:codebase-explorer uses CodeGraph when the repo has it: in a repo with a .codegraph/ directory, the agent queries codegraph (MCP codegraph_explore, else the codegraph explore CLI) before Glob/Grep/Read, and falls back to them without it Reviewers enumerate a rename's or store move's surfaces call graph first (folds #078).
- [ ] 2026-11-01-investigate-design-worktree-management-pd — Investigate and design worktree management in pd
- [x] 2026-11-02-commit-target-py-see-commits — promoted → workitems/2026-11-03-commit-guard-sees-wrapped-commits
- [ ] 2026-11-05-commit-guard-ksh-93-runs — commit guard: ksh 93 runs a bare string argument as a command (ksh 'git commit' is unseen) (from: workitems/2026-11-03-commit-guard-sees-wrapped-commits)
- [ ] 2026-11-05-commit-hooks-commit-prefilter-drops — commit hooks: the *commit* prefilter drops a quote-split commit word the parser sees (git com''mit, git co\mmit) (from: workitems/2026-11-03-commit-guard-sees-wrapped-commits)
- [ ] 2026-11-05-commit-target-normalize-printed-directory — commit_target: normalize the printed directory after cd .. (sub/.. today) (from: workitems/2026-11-03-commit-guard-sees-wrapped-commits)
- [ ] 2026-11-05-commit-target-pin-untested-wrappers — commit_target: pin the untested WRAPPERS options (xargs -I {}, -d; sudo -g/-h/-p/-T), ~ on directory options, one-digit \xH (from: workitems/2026-11-03-commit-guard-sees-wrapped-commits)
