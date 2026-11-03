<!-- Append-only history of 2026-11-03-codebase-explorer-uses-codegraph. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-03 11:02+08:00 note
Request (verbatim):
> pd:codebase-explorer uses CodeGraph when the repo has it: in a repo with a .codegraph/ directory, the agent queries codegraph (MCP codegraph_explore, else the codegraph explore CLI) before Glob/Grep/Read, and falls back to them without it Reviewers enumerate a rename's or store move's surfaces call graph first (folds #078).
Round request (user, 2026-11-03, verbatim):
> proceed to investigate, design and plan for three open backlog items in this round

## 2026-11-03 11:02+08:00 phase triage -> specify
Reason: small: two or three tasks, agent and reviewer markdown plus a validate check; existing agents to extend, no new module.

## 2026-11-03 11:08+08:00 decision
Q: when a repo has `.codegraph/` but the CodeGraph MCP tool is not connected, what should the explorer do (fall back to Grep, or add Bash to try the `codegraph explore` CLI)?
A (user, verbatim): "Fall back to Grep (Recommended)"
