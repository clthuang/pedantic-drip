# pd Plugin

Structured feature development workflow with skills, agents, and commands for methodical development from ideation to implementation.

See the [workflow diagram](../../README.md#workflow) in the repository README.

## Components

| Type | Count |
|------|-------|
| Skills | 24 |
| Agents | 21 |
| Commands | 24 |

## Commands

**Start:**
| Command | Description |
|---------|-------------|
| `/pd:brainstorm [topic]` | Explore an idea into an evidence-backed PRD |
| `/pd:create-feature <desc>` | Start building: `pd-new feature` creates the folder and branch; `--mode express` writes a mini-spec and goes to implement |

**Build phases** (run in order):
| Command | Output |
|---------|--------|
| `/pd:specify [--feature=ID]` | `shape.md` — `## Requirements`, calvin, your sign-off |
| `/pd:design` | `shape.md` — `## Design` (+ the review call) |
| `/pd:create-plan` | `plan.md` — `## Plan` (task blocks with test cases, + the test-case review) |
| `/pd:implement` | Code changes: the `implement-tasks` workflow, one task per worktree |
| `/pd:verify` | The code review beside QA, then fix cycles (`verify-change`) |
| `/pd:abandon-feature` | Transition a feature to abandoned status |
| `/pd:finish-feature` | Security review, docs sync, metrics, retro, merge |
| `/pd:wrap-up` | End the session — commit WIP, write `## Now` and a handoff entry |

**Anytime:**
| Command | Purpose |
|---------|---------|
| `/pd:retrospect` | Capture learnings |
| `/pd:add-to-backlog <idea>` | Capture ideas for later |
| `/pd:secretary` | Intelligent task routing to commands, agents, and skills |
| `/pd:root-cause-analysis` | Investigate bugs and failures to find all root causes |
| `/pd:create-specialist-team` | Create ephemeral specialist teams for complex tasks |
| `/pd:init-ds-project <name>` | Scaffold a new data science project |
| `/pd:promptimize [file-path or inline text]` | Review a prompt against best practices and return an improved version |
| `/pd:refresh-prompt-guidelines` | Scout latest prompt engineering best practices and update the guidelines document |
| `/pd:review-ds-analysis <file>` | Review data analysis for statistical pitfalls |
| `/pd:review-ds-code <file>` | Review DS Python code for anti-patterns |
| `/pd:generate-docs` | Generate three-tier documentation scaffold or update existing docs |
| `/pd:subagent-ras` | Research, analyze, and summarize any topic using parallel agents |

## Quality Gates

- **Exit checks:** `scripts/phase-gate.sh <phase> <feature dir>` checks what each phase must hand down; one line per failure.
- **Commit checks:** the `pd-commit-lint` hook runs `pd-lint --staged` before every `git commit` Claude runs; an error blocks it. Commits typed in a terminal aren't checked.
- **The review call** at Contracts, Plan and Verify (`references/review-call.md`): Codex first with one retry unless CLAUDE.md disables it, else the stage's Claude reviewer. One pass, then up to three fix cycles against runnable checks, then you.
- **The merger** lands each task only if its tests load at the test commit (one already green there is named for Verify) and pass at HEAD, untouched since (`scripts/pd-proof`); a task marked `proof: green-only` only has to pass.
- **QA** (`pd:qa-executor`) runs `qa_battery` beside the code review at Verify; it reports and fixes nothing.
- **Security review** (`pd:security-reviewer`) runs at finish, on Anthropic models, mandatory for `risk: security`.
- **Express** (`/pd:create-feature --mode express`) writes a mini-spec and goes straight to implement, with a lighter Verify.

## Agents

| Agent | Purpose |
|-------|---------|
| advisor | Applies strategic/domain advisory lens to brainstorm problems |
| calvin-runner | Runs the calvin skill on a feature's criteria and writes the ledger to one named path |
| ds-analysis-reviewer | Reviews data analysis for statistical pitfalls and methodology |
| code-quality-reviewer | Reviews implementation quality by severity |
| codebase-explorer | Analyzes codebase for patterns and constraints |
| design-reviewer | Challenges design assumptions and finds gaps (skeptic) |
| documentation-researcher | Researches documentation state and identifies update needs |
| documentation-writer | Writes and updates documentation |
| ds-code-reviewer | Reviews DS Python code for anti-patterns and best practices |
| generic-worker | General-purpose implementation agent |
| implementer | Task implementation with TDD and self-review |
| internet-researcher | Searches web for best practices and standards |
| investigation-agent | Read-only research before implementation |
| merger | Checks a task's proof with pd-proof and lands its branch on the feature branch |
| plan-reviewer | Skeptical plan reviewer for failure modes and TDD compliance |
| qa-executor | Execution-grounded QA — runs suites and drives affected flows, returning evidence |
| ras-synthesizer | Synthesizes multi-source research findings into thematic analysis with confidence calibration |
| rca-investigator | Finds all root causes through 6-phase systematic investigation |
| retro-facilitator | Runs data-driven AORTA retrospective with full intermediate context |
| security-reviewer | Reviews implementation for security vulnerabilities |
| skill-searcher | Finds relevant existing skills |

## Installation

In a Claude Code session (`#stable` follows releases):

```bash
/plugin marketplace add clthuang/pedantic-drip#stable
/plugin install pd@pedantic-drip-marketplace
```

Then, once per project, run `/pd:init`. It writes `.claude/pd.local.md` (paths, `qa_battery`, the budgets) and proposes, as a diff you approve, these `.claude/settings.json` entries:

- **`worktree.baseRef: "head"`:** without it, each task's worktree starts from the default branch instead of the feature branch.
- **The env cap** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`: agents can't spawn agents.
- **Allow rules** for `git merge`, `git worktree` and the `qa_battery` commands, so an unattended `/goal` run isn't stopped by a permission prompt.

An old-layout pd project (`docs/features/` without `sop: 1` in `.claude/pd.local.md`) runs `/pd:adopt` instead. The budgets in `.claude/pd.local.md`: `workflow_output_cap` (output tokens per workflow run, default 2,000,000), `feature_token_budget` (tokens per feature, unset by default) and `budget_increment`.
