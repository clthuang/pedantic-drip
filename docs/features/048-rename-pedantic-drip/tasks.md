# Tasks: Rename to pedantic-drip

## Phase 1: Script Creation

### Task 1.1: Create rename script
- **File:** `scripts/rename-to-pd.sh`
- **Implementation:** Write the full rename script from design.md C1 — Phases 1-5 plus 3b/3c verification. Include all 10 replacement rules, directory renames, JSON edits via Python, venv recreate, glob pattern fix, and verification grep.
- **Done when:** Script exists, is executable, passes `shellcheck scripts/rename-to-pd.sh` (or `bash -n` if shellcheck unavailable)
- **Depends on:** nothing

## Phase 2: Execute Rename

### Task 2.1: Run rename script
- **Preconditions:** Clean working tree (`git status` shows clean or stash first). No other Claude Code sessions active.
- **Implementation:** Run `bash scripts/rename-to-pd.sh`. Review Phase 3c output for remaining references.
- **Done when:** Script exits 0, `plugins/pd/` exists, `plugins/iflow/` does not. `~/.claude/pd/` exists OR `~/.claude/iflow/` did not exist pre-rename (skip is valid)
- **Depends on:** Task 1.1

### Task 2.2: Fix remaining iflow references
- **Implementation:** Run `grep -ri 'iflow' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ .claude-plugin/ docs/dev_guides/ docs/backlog.md docs/ecc-comparison-improvements.md docs/pd-audit-findings.md --include='*.md' --include='*.py' --include='*.sh' --include='*.json' --exclude-dir=__pycache__ --exclude-dir=.venv`. For each match, apply targeted fix. Repeat until zero results.
- **Done when:** Grep returns zero results (AC-4, AC-9, AC-12)
- **Depends on:** Task 2.1

## Phase 3: Validation

### Task 3.1: Run validate.sh
- **Implementation:** `./validate.sh` — must report 0 errors
- **Done when:** 0 errors (AC-1)
- **Depends on:** Task 2.2

### Task 3.2: Run all test suites
- **Implementation:** Run all test suites from CLAUDE.md Commands section:
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v`
  - `bash plugins/pd/mcp/test_run_memory_server.sh`
  - `bash plugins/pd/mcp/test_run_workflow_server.sh`
  - `bash plugins/pd/mcp/test_entity_server.sh`
  - `PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v`
  - `python3 -m pytest scripts/test_migrate_db.py scripts/test_migrate_e2e.py scripts/test_migrate_deepened.py -v`
  - `bash scripts/test_migrate_bash.sh`
  - `bash plugins/pd/hooks/tests/test-hooks.sh`
- **Done when:** All suites pass (AC-2)
- **Depends on:** Task 3.1

### Task 3.3: Verify JSON files
- **Implementation:** `python3 -m json.tool plugins/pd/.claude-plugin/plugin.json && python3 -m json.tool .claude-plugin/marketplace.json && python3 -m json.tool plugins/pd/hooks/hooks.json`
- **Done when:** All parse without errors, plugin.json and marketplace.json show name "pd" (AC-3, AC-11)
- **Depends on:** Task 2.2

## Phase 4: Commit & Ship

### Task 4.1: Commit and push
- **Implementation:**
  1. `git add -A`
  2. `git commit -m "feat: rename plugin iflow → pd, repo my-ai-setup → pedantic-drip"`
  3. `git push origin feature/048-rename-pedantic-drip`
  4. Verify push: `git log origin/feature/048-rename-pedantic-drip --oneline -1`
- **Done when:** Commit and push succeed
- **Depends on:** Tasks 3.1, 3.2, 3.3

### Task 4.2: Rename GitHub repository
- **Preconditions:** Task 4.1 push verified.
- **Implementation:**
  1. `gh repo rename pedantic-drip --yes`
  2. `git remote set-url origin git@github.com:clthuang/pedantic-drip.git`
  3. Verify: `gh repo view --json name`
- **Done when:** Repo shows name "pedantic-drip", remote updated (AC-8, AC-10)
- **Depends on:** Task 4.1

### Task 4.3: Sync cache and verify
- **Implementation:**
  1. `rm -rf ~/.claude/plugins/cache/*/iflow*`
  2. `bash plugins/pd/hooks/sync-cache.sh`
  3. Start new Claude Code session, run `/pd:show-status`
- **Done when:** Cache synced, `/pd:show-status` outputs dashboard without 'command not found' errors (AC-5)
- **Depends on:** Task 4.2
