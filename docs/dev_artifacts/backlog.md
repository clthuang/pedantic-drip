# Backlog

- [ ] 2026-11-01-pd-codebase-explorer-uses-codegraph — pd:codebase-explorer uses CodeGraph when the repo has it: in a repo with a .codegraph/ directory, the agent queries codegraph (MCP codegraph_explore, else the codegraph explore CLI) before Glob/Grep/Read, and falls back to them without it Reviewers enumerate a rename's or store move's surfaces call graph first (folds #078).
- [x] 2026-11-01-investigate-design-worktree-management-pd — promoted → workitems/2026-11-03-worktree-management-pd
- [ ] 2026-11-02-commit-target-py-see-commits — commit_target.py: see commits behind timeout, sudo -u, env -u and bash -c, and a bare trailing -- after checkout (PR #29 review notes)
- [ ] 2026-11-04-conftest-hostile-refs-repository-fixture — conftest: a hostile-refs repository fixture (same-named tag, symbolic ref and chain, slash in a stray name, last-sorting branch) that every git-parsing script test runs against (from: workitems/2026-11-03-worktree-management-pd)
- [ ] 2026-11-04-phase-gate-implement-fail-first — phase-gate implement: fail a first-commit green that plan.md does not declare as expected (from: workitems/2026-11-03-worktree-management-pd)
- [ ] 2026-11-04-pd-common-git-keep-last — pd_common.git(): keep the last line's trailing whitespace and decode refnames losslessly (security S3, QA Q5 of the worktree item) (from: workitems/2026-11-03-worktree-management-pd)
- [ ] 2026-11-04-pd-lint-risk-stop-re — pd-lint --risk: stop re-raising a security signal the owner cleared by decision (from: workitems/2026-11-03-worktree-management-pd)
- [ ] 2026-11-04-pd-local-md-set-source — pd.local.md: set source_paths and test_paths so the verify gate ignores untracked files and pd-lint --isolation checks the diff (from: workitems/2026-11-03-worktree-management-pd)
- [ ] 2026-11-04-planning-run-calvin-plan-md — planning: run calvin on plan.md before the review call, so its Design edits get reviewed (from: workitems/2026-11-03-worktree-management-pd)
