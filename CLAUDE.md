# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Claude Code plugin providing a structured development workflow—skills, commands, agents, and hooks that guide methodical development from ideation to implementation.

## Key Principles

- **No backward compatibility** - This is private tooling with no external users. Delete old code, don't maintain compatibility shims.
- **Branches for all modes** - All workflow modes (standard, small, express) create a `workitem/<id>` branch. Branches are lightweight.
- **Retro before cleanup** - Retrospective runs BEFORE branch deletion so context is still available.
- **Plugin portability** - Never use hardcoded `plugins/pd/` paths in agent, skill, or command files. Use two-location Glob: primary `~/.claude/plugins/cache/*/pd*/*/...`, fallback `plugins/*/...` (dev workspace). Mark fallback lines with "Fallback" or "dev workspace" so `validate.sh` can distinguish them from violations.
- **Project-aware design** - pd is used across multiple projects. Paths resolution, configs, and state must be relative to the current project context — never assume a specific project root.
- **Use uv for Python dependencies** - `uv add` for package management, never `pip install` directly. Run tests with the correct venv: `plugins/pd/.venv/bin/python -m pytest`.

## Working Standards

**When things go sideways:** Stop pushing. Re-read relevant code, question your assumptions, and re-plan before continuing. After 3 failed attempts at a fix, the approach is wrong — don't iterate on a broken path.

**Verification (all work):** Never claim work is complete without demonstrating correctness — run tests, check for regressions, diff against the base branch when relevant. Ask: "Would a staff engineer approve this?"

**Bug fixing posture:** Be autonomous. When pointed at errors, failing tests, or broken CI — investigate root causes and fix without hand-holding. Use `systematic-debugging` skill for structured investigation; `/pd:root-cause-analysis` for thorough multi-cause analysis.

**When corrected:** After any user correction, capture the pattern (via Claude Code's native memory) so it persists across sessions. Don't repeat the same mistake twice.

**Before non-trivial changes:** Pause and ask whether there's a simpler approach. Skip this for obvious, mechanical fixes.

**Plans from any source:** When the user provides a plan (via CC plan mode, pasted in chat, or from a file), always dispatch plan-reviewer before implementing. No hook enforces this since thin pd deleted the ExitPlanMode hook (T2.1); do it by hand for every plan.

**Worktree directory:** `implement-tasks` runs each task in a Claude Code worktree under `.claude/worktrees/` (`isolation: 'worktree'`), branched from the work item's branch HEAD by the `worktree.baseRef: "head"` setting. It is gitignored; Claude Code removes clean ones itself. Never commit inside `.claude/worktrees/` or treat it as source of truth — the merger lands each `pd/<id>/task-<n>` branch on the work item's branch.

**Worktree includes (`.worktreeinclude`):** Projects whose tests need gitignored files (e.g., `.env`, build outputs, local config) list them in a `.worktreeinclude` at the project root (`.gitignore` syntax); Claude Code copies them into every worktree it creates, subagent worktrees included (code.claude.com/docs/en/worktrees). Omit it when tests need no gitignored files.

## Behavioral Guardrails

**Review gate protocol (thin pd):** One reviewer pass → up to three fix cycles against runnable checks → remaining blockers go to the user. Before code, a pass with no blocker ends the stage; a zero-finding confirmatory rerun is an anti-pattern. Review calls at Contracts, Plan and Verify, plus the security review at finish.
*Why:* 3-5 open-ended iteration cycles consumed large context/time portions (feature 134); thin pd bounds the loop by runnable checks instead (plan §A2).
*Enforced by:* `verify-change.js`'s three-cycle loop (`test-workflows.mjs`); `workflow-transitions` "Loops and caps".
*Stays because:* the conductor runs the Contracts and Plan review calls by hand, and no script counts those cycles.

**Reviewer-claim verification:** When a reviewer's finding asserts a specific, checkable fact about existing code ("X writes column Y", "helper Z is unused"), verify it against the source (file:line) BEFORE writing it into a spec/design/plan. Reviewer output is not self-verifying.
*Why:* Feature 131's spec absorbed a false reviewer claim about `backfill_project_ids` for a full round; only a second independent dispatch caught it.
*Enforced by:* Convention — cite the verifying file:line in the applied-fix note; `verify-change`'s fixer checks findings before acting.
*Stays because:* whether a claim is true takes reading the code; no check can decide it.

**Non-vacuity test guard:** When a change adds a new/rewritten code path beside an existing tolerate/fallback path, every test targeting the new path must assert a fact true ONLY on that path — "no exception / zero issues" is satisfied by the fallback too. Restatements: a contract lives once, in its `shape.md` code block, and `pd-lint` fails a duplicate contract block or a `status:`/`phase:` line outside frontmatter; prose and docstrings restating a changed contract are still swept by hand. Verification claims must TRAIL their verification, never lead it — not even by one commit message (126's matcher-fix commit claimed a probe not yet run; caught in self-review and run immediately after).
*Why:* Feature 131 re-flagged vacuous-green in 4 separate review rounds, and a half-swept doc contract cost a handoff blocker.
*Enforced by:* `pd-lint` (restatements); the planning and verifying checklists and the merger's red-first proof (non-vacuity).
*Stays because:* work in this repo doesn't always run through pd's workflow, and "claims trail verification" has no check.

**Cross-contract collision check:** When a spec pins a grep/scan-based success criterion and a design pins VERBATIM content (code block, mandated comment, no-edit range) whose scope the scan covers, RUN the scan against the pinned content — including its own comments/docstrings/names — before approving either artifact. Internal-soundness review of each contract separately does not catch the pair colliding.
*Why:* Feature 125 shipped two such collisions past every pre-implementation review layer, one surviving six passes after being pinned: D1's verbatim block carried the SC2-grepped token in its own prose; D7's no-edit range kept a test name the SC2 clause forbade. Both caught only at execution, both preventable by one mechanical grep.
*Enforced by:* Convention; the implementer flags any residual collision instead of silently resolving it.
*Stays because:* which scan covers which pinned content takes judgment; no checklist line carries it yet.

**Author-restated literals drift across artifacts:** When an artifact restates a literal from an upstream artifact (key names, casing, constants, signatures), verify it against BOTH the immediately-prior artifact AND the live consumer code before trusting it. A spec-correct literal can be silently flipped by design and copied forward through plan/tasks unchallenged. Source-class hierarchy for behavior/shape claims: the WRITER'S TESTS outrank on-disk artifacts (artifacts are downstream projections — possibly reconciler-written); feature 126's spec verified skippedPhases against two on-disk files through three skeptic iterations while the writer's own tests proved a second live shape, forcing the campaign's first backward transition.
*Why:* Feature 119's payload-key casing was correct in spec, forked to snake_case in design D2, and copied through two more artifacts — caught only by checking the live .meta.json writer.
*Enforced by:* Reviewer-claim verification practice; `pd-lint` catches a duplicated contract block, not a drifted literal.
*Stays because:* which artifact holds the canonical literal takes judgment.

**Dispatch-briefing figures are restated literals too:** Headline metrics in a prompt handed to a downstream agent (iteration counts, blocker trajectories, commit counts) must be re-derived from primary sources (the work item's `log.md` entries and git; pre-thin-pd items used `.meta.json` and `.review-history.md`) at composition time — and any agent SYNTHESIZING from a briefing should re-derive them again before enshrining them in an artifact.
*Why:* Feature 130's retro briefing carried three source-contradicting figures (an iteration count, a swapped campaign trajectory, a reviewer-breakdown miscount) — the 119 author-restated-literal class, one layer up at the briefing↔artifact boundary. The retro-facilitator caught all three only because it re-derived. Superlative self-labels ("campaign-first", "Nth consecutive") are the same class: before an artifact ships, grep it for EVERY first/only/Nth/consecutive/highest claim and chain-verify each against the prior-retro record — checking one streak is not checking them all (119's battery label, 120's design-gate label, and 126's "first spec-layer self-inflicted" all needed dated corrections; 126's slipped while the battery streak WAS being checked).
*Enforced by:* retro-facilitator re-derivation practice; orchestrator briefing hygiene.
*Stays because:* briefings are prose the conductor writes; no check reads them.

**Shared-config blast radius:** When a change bumps a repo-wide config value (`requires-python`, a version pin, a default path), grep the ENTIRE repo for the old value's consumers (CI workflows, shell scripts — `validate.sh`, `scripts/release-pr.sh` — and docs) before the phase gate. Same trigger applies when a REVIEWER FIX pulls a previously out-of-scope file/surface into an artifact: the pull-in is a second, independent finding needing its own adjacent-surface check (shared regexes, id formats, sibling consumers) — satisfying the original blocker's criterion is not that check.
*Also-why:* Feature 121's specify iter-1 fix pulled the project-creation command in; iter-2 found the pull-in would deterministically re-mint P001 via a format/regex interaction the fix never examined — 2 of its 10 blockers came from that one unchecked scope-widening.
*Why:* Feature 118's Python-floor bump left the bootstrap and health-check scripts and CI enforcing 3.12 — every reviewer was scoped to the work item's diff, so the stale consumers were invisible until a finish-phase grep; a 3.12 venv would have crashed at runtime with a false all-clear.
*Enforced by:* `planning`'s review checklist ("Shared config"), which the Plan review applies.
*Stays because:* the scope pull-in half has no checklist line, and work here doesn't always run through pd's workflow.

## Writing Guidelines

**Agents with Write/Edit access should use judgment.** Avoid modifying:
- `.git/`, `node_modules/`, `.env*`, `*.key`, `*.pem`, lockfiles

**Agent Generated Content**
- Use `agent_sandbox/` for temporary files, experiments, debugging scripts.
- Put all agent generated non-workflow related content in `agent_sandbox/[YYYY-MM-DD]/[Meaningful Directory Name]/`

## User Input Standards

**All interactive choices MUST use AskUserQuestion tool:**
- Required for yes/no prompts (not `(y/n)` text patterns)
- Required for numbered menus (not ASCII `1. Option` blocks)
- Required for any user selection

**AskUserQuestion format:**
```
AskUserQuestion:
  questions: [{
    "question": "Your question",
    "header": "Category",
    "options": [
      {"label": "Option", "description": "What this does"}
    ],
    "multiSelect": false
  }]
```

**Exceptions (plain text OK):**
- Informational messages with no choice ("Run /verify to check")
- Error messages with instructions
- Status output

## Commands

See [Commands Reference](docs/dev-guide/commands-reference.md) for the full list of test, validation, and release commands.

**Quick reference:**
```bash
./validate.sh                    # Validate components
bash plugins/pd/hooks/tests/test-hooks.sh  # Hook integration tests
scripts/release-pr.sh            # Release: opens the release PR into main
```

## Key References

| Document | Use When |
|----------|----------|
| [Component Authoring Guide](docs/dev-guide/component-authoring.md) | Creating skills, agents, plugins, commands, or hooks |
| [Developer Guide](README_FOR_DEV.md) | Architecture, release process, design principles |
| [Hook Development Guide](docs/dev-guide/hook-development.md) | Writing or modifying hooks — covers PROJECT_ROOT vs PLUGIN_ROOT, JSON output, shared libs |
| [Commands Reference](docs/dev-guide/commands-reference.md) | Test commands, validation, release process |

## Gotchas

- **Knowledge bank:** `docs/dev_artifacts/knowledge-bank/{patterns,anti-patterns,heuristics}.md` — inert reference markdown (no tooling reads/writes it)
- **Helper dispatch isolation:** When a function orchestrates N independent helpers, wrap each in its own `try/except`. List-literal dispatch (`[helper1(), helper2()]`) means one exception blocks all subsequent helpers.
- **Hook subprocess safety:** Always suppress stderr (`2>/dev/null`) for Python/external calls in hooks to prevent corrupting JSON output
- **Hook EPIPE safety (feature 107):** Hooks emitting structured output via printf/cat MUST keep `trap '' PIPE` AND wrap writes with `{ ...; } 2>/dev/null || true`. The trap is co-load-bearing — without it, the bash process is SIGPIPE-killed before `|| true` can run. Use `safe_emit_hook_json` from `lib/session-start-helpers.sh`. See `docs/dev-guide/hook-development.md` "Broken-pipe handling".
- **Bash 3.2 / macOS BSD portability:** Use POSIX `[[:space:]]` (not `\s`) in `grep -E`; use `${!varname:-default}` indirect expansion (not `eval`) for env-var indirection — both work on macOS bash 3.2 and avoid eval-injection. `$?` in `trap '...' EXIT` strings expands at fire time, not registration time (verified empirically).

## Quick Reference

**Naming conventions:** lowercase, hyphens, no spaces
- Skills: gerund form (`creating-tests`, `reviewing-code`)
- Agents: action/role (`code-reviewer`, `security-auditor`)
- Plugins: noun (`datascience-team`)

**Token budget:** SKILL.md <500 lines, <5,000 tokens

**Documentation sync:** When adding, removing, or renaming skills, commands, agents, or hooks in `plugins/pd/`, update:
- `README.md` — the command tables, the skill list and the skill and agent counts
- `README_FOR_DEV.md` — the skill tables and the agent groups
- `plugins/pd/README.md` — component counts table and command/agent tables
- `plugins/pd/commands/secretary.md` — Specialist Fast-Path table (if renaming agents listed there)
- `README_FOR_DEV.md` — hooks table (if adding/removing hooks)

A hookify rule (`.claude/hookify.docs-sync.local.md`) will remind you on plugin component edits.

**Agent model tiers:** Every `subagent_type:` dispatch must include `model:` (opus/sonnet/haiku) matching the agent's frontmatter. Verify with: `grep -rn 'subagent_type:' plugins/pd/ | wc -l` and confirm each has a nearby `model:` line.

**Reviewer prompt consistency:** Every review prompt carries the return schema pinned in `plugins/pd/references/workflow-results.md` ("The review call"), inline, per `plugins/pd/references/review-call.md` — never prose like "Return assessment with approval status".

**Project-aware config:** `.claude/pd.local.md` fields (injected at session start by `pd-session-start.sh` once the repo is adopted: `/pd:adopt` sets `sop: 1`, still pending here):
- `artifacts_root` (default: `docs/dev_artifacts`) — root directory for work items, plans, brainstorms, rca and backlog items
- `base_branch` (default: `auto` — detects from remote HEAD, falls back to `main`) — merge target branch
- `release_script` (default: empty) — path to release script, conditional execution

Skills/commands reference these as `{pd_artifacts_root}`, `{pd_base_branch}`, `{pd_release_script}`.

**Base branch for this repo is `main`** — `base_branch: auto` resolves to it from the remote HEAD. Branches merge to `main` through PRs; releases go through `scripts/release-pr.sh`.

**Backlog:** Capture ad-hoc ideas with `/pd:add-to-backlog <description>`. [docs/backlog-manual.md](docs/dev_artifacts/backlog-manual.md) is the historical detail annex for pre-134 items.
