# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Claude Code plugin providing a structured feature development workflow—skills, commands, agents, and hooks that guide methodical development from ideation to implementation.

## Key Principles

- **No backward compatibility** - This is private tooling with no external users. Delete old code, don't maintain compatibility shims.
- **Branches for all modes** - All workflow modes (Standard, Full) create feature branches. Branches are lightweight.
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

**Plans from any source:** When the user provides a plan (via CC plan mode, pasted in chat, or from a file), always dispatch plan-reviewer before implementing. The PreToolUse ExitPlanMode hook enforces this in CC plan mode; compensate manually for plans pasted in chat or from files.

**Worktree directory:** The `.pd-worktrees/` directory at the project root is used by the implementing skill for parallel task dispatch (worktree isolation workaround for CC Issue #33045). It is gitignored and auto-cleaned after successful merges. Never commit files inside `.pd-worktrees/` or treat them as source of truth — the orchestrating skill merges worktree branches back to the feature branch.

**Worktree includes (`.worktreeinclude`):** Projects that adopt the worktree-parallel implementation pattern and depend on gitignored files (e.g., `.env`, build outputs, local config) at agent-runtime should add a `.worktreeinclude` file at the project root listing those paths. The worktree creation step copies/symlinks listed files into each `.pd-worktrees/task-{N}/` so agents can run tests and builds. If the project's tests don't need any gitignored files, omit `.worktreeinclude` entirely.

## Behavioral Guardrails

**Review gate protocol (feature 134):** One reviewer pass → at most one fix round → remaining blockers escalate to the user. Never iterate to a cap; a zero-finding confirmatory rerun is an anti-pattern. Two standing review moments per deep feature (design, code) plus the conditional security review at finish.
*Why:* 3-5 iteration cycles consumed large context/time portions; the rebuilt workflow encodes the one-pass rule in workflow-transitions.
*Enforced by:* Iteration cap in `implement.md`.

**Reviewer-claim verification:** When a reviewer's finding asserts a specific, checkable fact about existing code ("X writes column Y", "helper Z is unused"), verify it against the source (file:line) BEFORE writing it into a spec/design/plan. Reviewer output is not self-verifying.
*Why:* Feature 131's spec absorbed a false reviewer claim about `backfill_project_ids` for a full round; only a second independent dispatch caught it.
*Enforced by:* Convention — cite the verifying file:line in the applied-fix note.

**Non-vacuity test guard:** When a change adds a new/rewritten code path beside an existing tolerate/fallback path, every test targeting the new path must assert a fact true ONLY on that path — "no exception / zero issues" is satisfied by the fallback too. Interface-contract edits inside one doc must sweep ALL restatements (signature, snippets, prose) in the same revision — MECHANICALLY: after any contract-changing fix, grep the whole current-phase artifact set for the fact's other restatements (headline/table/prose/risk-note quadruple) before declaring the fix done; a reviewer naming one location is not evidence the others were checked (feature 130+121: four half-sweep occurrences across two features, all gate-caught, all iteration-budget burns). The sweep is a MANDATORY step of EVERY absorption edit — direction-agnostic (downstream fixes sweep back into upstream artifacts too; 126's create-plan absorptions left design.md stale, the 7th occurrence, 100% gate-caught / 0% prevented — the gap is executing the sweep, not rule coverage). Verification claims must TRAIL their verification, never lead it — not even by one commit message (126's matcher-fix commit claimed a probe not yet run; caught in self-review and run immediately after). The sweep INCLUDES code docstrings/comments adjacent to a changed code contract — feature 120's #061 guard (a SQL read newly preceding json.dumps) staled the neighboring docstring's "before any SQL" ordering claim, caught only at the final 360° gate.
*Why:* Feature 131 re-flagged vacuous-green in 4 separate review rounds, and a half-swept doc contract cost a handoff blocker.
*Enforced by:* Design/plan reviewer checklists; design docs pin contracts in ONE code block where possible.

**Cross-contract collision check:** When a spec pins a grep/scan-based success criterion and a design pins VERBATIM content (code block, mandated comment, no-edit range) whose scope the scan covers, RUN the scan against the pinned content — including its own comments/docstrings/names — before approving either artifact. Internal-soundness review of each contract separately does not catch the pair colliding.
*Why:* Feature 125 shipped two such collisions past every pre-implementation review layer, one surviving six passes after being pinned: D1's verbatim block carried the SC2-grepped token in its own prose; D7's no-edit range kept a test name the SC2 clause forbade. Both caught only at execution, both preventable by one mechanical grep.
*Enforced by:* Convention — design/spec reviewer prompts; the implementer flags any residual collision instead of silently resolving it.

**Author-restated literals drift across artifacts:** When an artifact restates a literal from an upstream artifact (key names, casing, constants, signatures), verify it against BOTH the immediately-prior artifact AND the live consumer code before trusting it. A spec-correct literal can be silently flipped by design and copied forward through plan/tasks unchallenged. Source-class hierarchy for behavior/shape claims: the WRITER'S TESTS outrank on-disk artifacts (artifacts are downstream projections — possibly reconciler-written); feature 126's spec verified skippedPhases against two on-disk files through three skeptic iterations while the writer's own tests proved a second live shape, forcing the campaign's first backward transition.
*Why:* Feature 119's payload-key casing was correct in spec, forked to snake_case in design D2, and copied through two more artifacts — caught only by checking the live .meta.json writer.
*Enforced by:* Reviewer-claim verification practice; task-reviewer checks.

**Dispatch-briefing figures are restated literals too:** Headline metrics in a prompt handed to a downstream agent (iteration counts, blocker trajectories, commit counts) must be re-derived from primary sources (phase-event reviewer notes via the engine, `.meta.json`, git; pre-134 features used `.review-history.md`) at composition time — and any agent SYNTHESIZING from a briefing should re-derive them again before enshrining them in an artifact.
*Why:* Feature 130's retro briefing carried three source-contradicting figures (an iteration count, a swapped campaign trajectory, a reviewer-breakdown miscount) — the 119 author-restated-literal class, one layer up at the briefing↔artifact boundary. The retro-facilitator caught all three only because it re-derived. Superlative self-labels ("campaign-first", "Nth consecutive") are the same class: before an artifact ships, grep it for EVERY first/only/Nth/consecutive/highest claim and chain-verify each against the prior-retro record — checking one streak is not checking them all (119's battery label, 120's design-gate label, and 126's "first spec-layer self-inflicted" all needed dated corrections; 126's slipped while the battery streak WAS being checked).
*Enforced by:* retro-facilitator re-derivation practice; orchestrator briefing hygiene.

**Shared-config blast radius:** When a change bumps a repo-wide config value (`requires-python`, a version pin, a default path), grep the ENTIRE repo for the old value's consumers (CI workflows, shell scripts — `validate.sh`, `release.sh` — and docs) before the phase gate. Same trigger applies when a REVIEWER FIX pulls a previously out-of-scope file/surface into an artifact: the pull-in is a second, independent finding needing its own adjacent-surface check (shared regexes, id formats, sibling consumers) — satisfying the original blocker's criterion is not that check.
*Also-why:* Feature 121's specify iter-1 fix pulled the project-creation command in; iter-2 found the pull-in would deterministically re-mint P001 via a format/regex interaction the fix never examined — 2 of the feature's 10 blockers came from that one unchecked scope-widening.
*Why:* Feature 118's Python-floor bump left the bootstrap and health-check scripts and CI enforcing 3.12 — every reviewer was scoped to the feature diff, so the stale consumers were invisible until a finish-phase grep; a 3.12 venv would have crashed at runtime with a false all-clear.
*Enforced by:* plan-reviewer checklist line ("shared-config value change … repo-wide consumer sweep").

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

See [Commands Reference](docs/dev_guides/commands-reference.md) for the full list of test, validation, and release commands.

**Quick reference:**
```bash
./validate.sh                    # Validate components
bash plugins/pd/hooks/tests/test-hooks.sh  # Hook integration tests
bash scripts/release.sh --ci     # Release (develop→main)
```

## Key References

| Document | Use When |
|----------|----------|
| [Component Authoring Guide](docs/dev_guides/component-authoring.md) | Creating skills, agents, plugins, commands, or hooks |
| [Developer Guide](README_FOR_DEV.md) | Architecture, release process, design principles |
| [Hook Development Guide](docs/dev_guides/hook-development.md) | Writing or modifying hooks — covers PROJECT_ROOT vs PLUGIN_ROOT, JSON output, shared libs |
| [Commands Reference](docs/dev_guides/commands-reference.md) | Test commands, validation, release process |
| [ECC Comparison Improvements](docs/ecc-comparison-improvements.md) | Prioritizing plugin improvements based on competitive analysis |

## Gotchas

- **Knowledge bank:** `docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md` — inert reference markdown (no tooling reads/writes it)
- **Helper dispatch isolation:** When a function orchestrates N independent helpers, wrap each in its own `try/except`. List-literal dispatch (`[helper1(), helper2()]`) means one exception blocks all subsequent helpers.
- **Hook subprocess safety:** Always suppress stderr (`2>/dev/null`) for Python/external calls in hooks to prevent corrupting JSON output
- **Hook EPIPE safety (feature 107):** Hooks emitting structured output via printf/cat MUST keep `trap '' PIPE` AND wrap writes with `{ ...; } 2>/dev/null || true`. The trap is co-load-bearing — without it, the bash process is SIGPIPE-killed before `|| true` can run. Use `safe_emit_hook_json` from `lib/session-start-helpers.sh`. See `docs/dev_guides/hook-development.md` "Broken-pipe handling".
- **Bash 3.2 / macOS BSD portability:** Use POSIX `[[:space:]]` (not `\s`) in `grep -E`; use `${!varname:-default}` indirect expansion (not `eval`) for env-var indirection — both work on macOS bash 3.2 and avoid eval-injection. `$?` in `trap '...' EXIT` strings expands at fire time, not registration time (verified empirically).

## Quick Reference

**Naming conventions:** lowercase, hyphens, no spaces
- Skills: gerund form (`creating-tests`, `reviewing-code`)
- Agents: action/role (`code-reviewer`, `security-auditor`)
- Plugins: noun (`datascience-team`)

**Token budget:** SKILL.md <500 lines, <5,000 tokens

**Documentation sync:** When adding, removing, or renaming skills, commands, agents, or hooks in `plugins/pd/`, update:
- `README.md` and `README_FOR_DEV.md` — skill/agent/command tables and counts
- `plugins/pd/README.md` — component counts table and command/agent tables
- `plugins/pd/commands/secretary.md` — Specialist Fast-Path table (if renaming agents listed there)
- `README_FOR_DEV.md` — hooks table (if adding/removing hooks)

A hookify rule (`.claude/hookify.docs-sync.local.md`) will remind you on plugin component edits.

**Agent model tiers:** Every `subagent_type:` dispatch must include `model:` (opus/sonnet/haiku) matching the agent's frontmatter. Verify with: `grep -rn 'subagent_type:' plugins/pd/ | wc -l` and confirm each has a nearby `model:` line.

**Reviewer prompt consistency:** All reviewer dispatch prompts in command files must include explicit JSON return schema blocks (`{approved, issues[], summary}`). Plain prose like "Return assessment with approval status" gets caught late in implement review. Verify with: `grep -n 'Return.*assessment\|Return.*JSON\|Return.*approval' plugins/pd/commands/*.md`

**Project-aware config:** `.claude/pd.local.md` fields (injected at session start once build task T4.7's `pd-session-start.sh` lands):
- `artifacts_root` (default: `docs`) — root directory for features, brainstorms, projects
- `base_branch` (default: `auto` — detects from remote HEAD, falls back to `main`) — merge target branch
- `release_script` (default: empty) — path to release script, conditional execution

Skills/commands reference these as `{pd_artifacts_root}`, `{pd_base_branch}`, `{pd_release_script}`.

**Base branch for this repo is `develop`** — `base_branch: auto` detects `main` from remote HEAD, but all feature branches merge to `develop` (confirmed by git merge history). The release script handles `develop→main`.

**Agent concurrency:** `max_concurrent_agents` in `.claude/pd.local.md` controls max parallel Task dispatches (default: 5). Skills and commands batch accordingly.

**Backlog:** Capture ad-hoc ideas with `/pd:add-to-backlog <description>` (rewritten for thin pd in build task T4.5i). [docs/backlog-manual.md](docs/backlog-manual.md) is the historical detail annex for pre-134 items.
