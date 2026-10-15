# pd Plugin

Structured feature development workflow with skills, agents, and commands for methodical development from ideation to implementation.

See the [workflow diagram](../../README.md#workflow) in the repository README.

## Components

| Type | Count |
|------|-------|
| Skills | 23 |
| Agents | 19 |
| Commands | 22 |

## Commands

**Start:**
| Command | Description |
|---------|-------------|
| `/pd:brainstorm [topic]` | Explore an idea into an evidence-backed PRD |
| `/pd:create-feature <desc>` | Start building (creates folder + branch); `--express` records an inline mini-spec and jumps to implement |

**Build phases** (run in order):
| Command | Output |
|---------|--------|
| `/pd:specify [--feature=ID]` | `shape.md` — `## Requirements` |
| `/pd:design` | `shape.md` — `## Design` (+ design review moment) |
| `/pd:create-plan` | `plan.md` — `## Plan` (ordered tasks; no separate tasks.md) |
| `/pd:implement` | Code changes (QA execution + code-quality review) |
| `/pd:abandon-feature` | Transition a feature to abandoned status |
| `/pd:finish-feature` | QA battery, docs sync, retro, merge |
| `/pd:wrap-up` | End the session — commit WIP, report engine state and open items |

**Anytime:**
| Command | Purpose |
|---------|---------|
| `/pd:retrospect` | Capture learnings |
| `/pd:add-to-backlog <idea>` | Capture ideas for later |
| `/pd:sync-cache` | Reload plugin after changes (from the main checkout; a linked worktree publishes nothing) |
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

Quality is enforced in two tiers: **mechanical gates** on every phase boundary, and exactly **two LLM review moments** per deep feature.

### Tier 1 — Mechanical gates (zero dispatch)

`scripts/phase-gate.sh <phase> <feature-dir>` runs at each phase boundary and checks artifact existence, required sections, duplicate contract blocks (the restated-contract class), and uncommitted artifacts at implement entry. Failures print one line per problem; fix and re-run.

### Tier 2 — LLM review moments

| Moment | Phase | Agent | Question |
|--------|-------|-------|----------|
| 1 of 2 | design | `pd:design-reviewer` | Is the design sound and grounded? |
| 2 of 2 | implement | `pd:code-quality-reviewer` | Is the branch diff correct and maintainable? |

Per moment: one reviewer pass → at most one fix round → still-open blockers escalate to the user. There is no iterate-to-a-cap loop. Reviewers run in fresh context, cite `file:line`, and own their return schema (defined only in the agent file).

Two dispatches sit outside the review tier:

- `pd:qa-executor` — execution-grounded QA during implement. Runs the test battery and drives affected flows end-to-end, returning commands plus output evidence. It fixes nothing; it reports.
- `pd:security-reviewer` — dispatched from `/pd:finish-feature` when the branch touches a security surface (auth, secrets, input parsing, permissions, data deletion, dependency bumps). Always an Anthropic-model Task.

**Express mode** (`/pd:create-feature --express`) records an inline mini-spec as a `mini_spec` phase event, skips specify/design/create-plan, and collapses QA and review into a single combined pass during implement.

## Agents

| Agent | Purpose |
|-------|---------|
| advisor | Applies strategic/domain advisory lens to brainstorm problems |
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
| plan-reviewer | Skeptical plan reviewer for failure modes and TDD compliance |
| qa-executor | Execution-grounded QA — runs suites and drives affected flows, returning evidence |
| ras-synthesizer | Synthesizes multi-source research findings into thematic analysis with confidence calibration |
| rca-investigator | Finds all root causes through 6-phase systematic investigation |
| retro-facilitator | Runs data-driven AORTA retrospective with full intermediate context |
| security-reviewer | Reviews implementation for security vulnerabilities |
| skill-searcher | Finds relevant existing skills |

## Installation

```bash
/plugin marketplace add .
/plugin install pd@pedantic-drip-marketplace
```
