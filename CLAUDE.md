# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Claude Code plugin providing a structured feature development workflow—skills, commands, agents, and hooks that guide methodical development from ideation to implementation.

## Key Principles

- **No backward compatibility** - This is private tooling with no external users. Delete old code, don't maintain compatibility shims.
- **Branches for all modes** - All workflow modes (Standard, Full) create feature branches. Branches are lightweight.
- **Retro before cleanup** - Retrospective runs BEFORE branch deletion so context is still available.
- **Plugin portability** - Never use hardcoded `plugins/pd/` paths in agent, skill, or command files. Use two-location Glob: primary `~/.claude/plugins/cache/*/pd*/*/...`, fallback `plugins/*/...` (dev workspace). Mark fallback lines with "Fallback" or "dev workspace" so `validate.sh` can distinguish them from violations.
- **Project-aware design** - pd is used across multiple projects. Paths resolution, configs, and state must be relative to the current project context — never assume a specific project root. The only global feature is the knowledge bank DB (`~/.claude/pd/memory/`), which accumulates learnings across all projects.
- **Use uv for Python dependencies** - `uv add` for package management, never `pip install` directly. Run tests with the correct venv: `plugins/pd/.venv/bin/python -m pytest`.

## Working Standards

**When things go sideways:** Stop pushing. Re-read relevant code, question your assumptions, and re-plan before continuing. After 3 failed attempts at a fix, the approach is wrong — don't iterate on a broken path.

**Verification (all work):** Never claim work is complete without demonstrating correctness — run tests, check for regressions, diff against the base branch when relevant. Ask: "Would a staff engineer approve this?"

**Bug fixing posture:** Be autonomous. When pointed at errors, failing tests, or broken CI — investigate root causes and fix without hand-holding. Use `systematic-debugging` skill for structured investigation; `/pd:root-cause-analysis` for thorough multi-cause analysis.

**When corrected:** After any user correction, capture the pattern via `/pd:remember` so it persists across sessions. Don't repeat the same mistake twice.

**Before non-trivial changes:** Pause and ask whether there's a simpler approach. Skip this for obvious, mechanical fixes.

**Plans from any source:** When the user provides a plan (via CC plan mode, pasted in chat, or from a file), always dispatch plan-reviewer before implementing. The PreToolUse ExitPlanMode hook enforces this in CC plan mode; compensate manually for plans pasted in chat or from files.

**Worktree directory:** The `.pd-worktrees/` directory at the project root is used by the implementing skill for parallel task dispatch (worktree isolation workaround for CC Issue #33045). It is gitignored and auto-cleaned after successful merges. Orphaned worktrees are detected by the doctor health check. Never commit files inside `.pd-worktrees/` or treat them as source of truth — the orchestrating skill merges worktree branches back to the feature branch.

**Worktree includes (`.worktreeinclude`):** Projects that adopt the worktree-parallel implementation pattern and depend on gitignored files (e.g., `.env`, build outputs, local config) at agent-runtime should add a `.worktreeinclude` file at the project root listing those paths. The worktree creation step copies/symlinks listed files into each `.pd-worktrees/task-{N}/` so agents can run tests and builds. If the project's tests don't need any gitignored files, omit `.worktreeinclude` entirely.

## Behavioral Guardrails

**YOLO mode persistence:** In YOLO mode, do not disable or exit YOLO mode. Continue executing autonomously through errors. Fix errors and keep going.
*Why:* YOLO mode disabling forces user intervention, defeating autonomous execution.
*Enforced by:* `yolo-guard.sh` hook intercepts AskUserQuestion in YOLO mode.

**Reviewer iteration targets:** Target 1-2 reviewer iterations per phase. Hard cap: 3 iterations. After 3 rounds, summarize remaining issues and ask user for guidance.
*Why:* 3-5 iteration cycles consumed large context/time portions.
*Enforced by:* Iteration cap in `implement.md`.

**SQLite lock recovery:** When encountering "database is locked" errors: (1) check for orphaned processes with `lsof +D ~/.claude/pd | grep .db`, (2) kill stale Python/MCP processes, (3) verify WAL mode with `PRAGMA journal_mode`. Do not silently swallow database exceptions.
*Why:* SQLite locking from stale MCP processes was the most persistent friction source.
*Addressed by:* Doctor auto-fix at session start, WAL mode on connect, `cleanup-locks.sh` hook.

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

## Knowledge & Memory

- **Knowledge bank:** `docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md` — updated by retrospectives
- **Global memory store:** `~/.claude/pd/memory/` — cross-project entries injected at session start
- **Entity registry DB:** `~/.claude/pd/entities/entities.db` — cross-project entity lineage (overridable via `ENTITY_DB_PATH` env var)
- **Entity type_id format gotcha:** `type_id` uses colon separator: `"{entity_type}:{entity_id}"` (e.g., `"feature:043-my-feature"`), NOT slash. See `database.py:627`.
- **Entity registry MCP metadata gotcha:** `register_entity` and `update_entity` accept `metadata` as either a dict or JSON string (dict preferred). Dicts are auto-coerced to JSON string via `json.dumps()` before `parse_metadata`. When updating entity state, prefer updating `.meta.json` directly (source of truth) and skip MCP metadata updates.
- **Entity metadata parsing:** Always use `from entity_registry.metadata import parse_metadata` — returns `{}` for None/invalid (never returns None). Do NOT use raw `json.loads` on metadata fields. `validate_metadata(entity_type, meta_dict)` returns warning strings for type mismatches.
- **Entity table schema gotcha:** The `entities` table has a `uuid TEXT NOT NULL PRIMARY KEY` column. Raw SQL `INSERT` in test helpers must include a uuid value or the insert silently fails with `INSERT OR IGNORE`. Use `import uuid; str(uuid.uuid4())`.
- **Entity DB encapsulation:** Never access `db._conn` directly. Use `db.add_dependency()`, `db.query_dependencies()`, `db.scan_entity_ids()`, `db.is_healthy()`, `db.register_entities_batch()` etc.
- **Entity delete_entity gotcha:** `delete_entity(type_id)` raises `ValueError` if the same `type_id` exists in multiple projects. Use UUID from `list_entities()` result instead. Also: **children** (entities whose `parent_uuid` points to this entity) block deletion; **dependencies** cascade automatically and do not block.
- **Helper dispatch isolation:** When a function orchestrates N independent helpers (e.g., `sync_entity_statuses` calling 4 sync helpers), wrap each in its own `try/except`. List-literal dispatch (`[helper1(), helper2()]`) means one exception blocks all subsequent helpers.
- **Entity state machine gotcha:** `ENTITY_MACHINES` in `entity_lifecycle.py` has assertions in TWO test files: `test_entity_lifecycle.py` and `test_workflow_state_server.py` (deepened tests). Update both when changing transitions.
- **Hook subprocess safety:** Always suppress stderr (`2>/dev/null`) for Python/external calls in hooks to prevent corrupting JSON output
- **Semantic memory CLI:** Find plugin root first: `PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/pd*/*/hooks 2>/dev/null | head -1 | xargs dirname)`, then `PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m semantic_memory.writer`. Fallback (dev workspace): `PYTHONPATH=plugins/pd/hooks/lib python3 -m semantic_memory.writer`

## Quick Reference

**Naming conventions:** lowercase, hyphens, no spaces
- Skills: gerund form (`creating-tests`, `reviewing-code`)
- Agents: action/role (`code-reviewer`, `security-auditor`)
- Plugins: noun (`datascience-team`)

**Token budget:** SKILL.md <500 lines, <5,000 tokens

**Documentation sync:** When adding, removing, or renaming skills, commands, agents, or hooks in `plugins/pd/`, update:
- `README.md` and `README_FOR_DEV.md` — skill/agent/command tables and counts
- `plugins/pd/README.md` — component counts table and command/agent tables
- `plugins/pd/skills/workflow-state/SKILL.md` — Phase Sequence one-liner (if phase names change)
- `plugins/pd/commands/secretary.md` — Specialist Fast-Path table (if renaming agents listed there)
- `README_FOR_DEV.md` — hooks table (if adding/removing hooks)

A hookify rule (`.claude/hookify.docs-sync.local.md`) will remind you on plugin component edits.

**Agent model tiers:** Every `subagent_type:` dispatch must include `model:` (opus/sonnet/haiku) matching the agent's frontmatter. Verify with: `grep -rn 'subagent_type:' plugins/pd/ | wc -l` and confirm each has a nearby `model:` line.

**Reviewer prompt consistency:** All reviewer dispatch prompts in command files must include explicit JSON return schema blocks (`{approved, issues[], summary}`). Plain prose like "Return assessment with approval status" gets caught late in implement review. Verify with: `grep -n 'Return.*assessment\|Return.*JSON\|Return.*approval' plugins/pd/commands/*.md`

**Project-aware config:** `.claude/pd.local.md` fields injected at session start:
- `artifacts_root` (default: `docs`) — root directory for features, brainstorms, projects, knowledge-bank
- `base_branch` (default: `auto` — detects from remote HEAD, falls back to `main`) — merge target branch
- `release_script` (default: empty) — path to release script, conditional execution
- `backfill_scan_dirs` (default: empty) — comma-separated dirs to scan for knowledge banks

Skills/commands reference these as `{pd_artifacts_root}`, `{pd_base_branch}`, `{pd_release_script}`.

**Base branch for this repo is `develop`** — `base_branch: auto` detects `main` from remote HEAD, but all feature branches merge to `develop` (confirmed by git merge history). The release script handles `develop→main`.

**Agent concurrency:** `max_concurrent_agents` in `.claude/pd.local.md` controls max parallel Task dispatches (default: 5). Skills and commands batch accordingly.

**Backlog:** Capture ad-hoc ideas with `/pd:add-to-backlog <description>`. Review at [docs/backlog.md](docs/backlog.md).
