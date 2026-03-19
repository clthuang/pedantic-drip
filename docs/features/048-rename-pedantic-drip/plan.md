# Plan: Rename to pedantic-drip

## Build Order

This is a scripted rename — the plan is the execution sequence. Most work is done by `scripts/rename-to-pd.sh` (design C1), followed by manual post-rename steps (design C2).

```
Step 1: Create rename script          ← no deps
Step 2: Run rename script             ← depends on Step 1
Step 3: Fix remaining references      ← depends on Step 2
Step 4: Validate & test               ← depends on Step 3
Step 5: Commit & push                 ← depends on Step 4
Step 6: GitHub repo rename            ← depends on Step 5
Step 7: Cache sync & verify           ← depends on Step 6
```

## Step 1: Create rename script

**Why this item:** The rename script (design C1) is the core deliverable — it executes Phases 1-5 from the design.
**Why this order:** Must exist before anything else can happen.

**File:** `scripts/rename-to-pd.sh`

**Implementation:**
1. Create the script following design.md C1 pseudocode exactly
2. Make it executable (`chmod +x`)
3. Include all replacement rules from design (rules 1-10)
4. Include Phase 3c verification step that reports remaining references

**Done when:** Script exists, is executable, and passes shellcheck

## Step 2: Run rename script

**Why this item:** Executes the bulk rename — directory moves, text replacements, JSON edits, venv recreate.
**Why this order:** Depends on Step 1.

**Implementation:**
1. Run `bash scripts/rename-to-pd.sh`
2. Review output — check Phase 3c verification for remaining references
3. If remaining references found, note them for Step 3

**Done when:** Script completes without error, `plugins/pd/` exists, `plugins/iflow/` does not

## Step 3: Fix remaining references

**Why this item:** The script's bulk replace may miss edge cases — unusual patterns, multi-line references, or patterns not covered by the 10 rules.
**Why this order:** Depends on Step 2 (script must run first to see what's left).

**Implementation:**
1. Run `grep -ri 'iflow' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ docs/dev_guides/ docs/backlog.md --include='*.md' --include='*.py' --include='*.sh' --include='*.json' --exclude-dir=__pycache__ --exclude-dir=.venv`
2. For each remaining reference, manually fix with targeted sed or edit
3. Repeat grep until zero results

**Done when:** Grep returns zero results across all included paths

## Step 4: Validate & test

**Why this item:** Verify the rename didn't break anything.
**Why this order:** Depends on Step 3 (all references fixed first).

**Implementation:**
1. `./validate.sh` — must report 0 errors
2. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v` — entity registry tests
3. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v` — semantic memory tests
4. `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v` — MCP memory tests
5. `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py -v` — MCP entity tests
6. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v` — workflow engine tests
7. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v` — transition gate tests
8. `bash plugins/pd/hooks/tests/test-hooks.sh` — hook integration tests
9. Verify JSON files parse: `python3 -m json.tool plugins/pd/.claude-plugin/plugin.json && python3 -m json.tool .claude-plugin/marketplace.json`

**Done when:** All suites pass, validate.sh reports 0 errors, JSON files parse

## Step 5: Commit & push

**Why this item:** Persist all changes.
**Why this order:** Only after validation passes.

**Implementation:**
1. `git add -A`
2. `git commit -m "feat: rename plugin iflow → pd, repo my-ai-setup → pedantic-drip"`
3. `git push origin feature/048-rename-pedantic-drip`

**Done when:** Commit and push succeed

## Step 6: GitHub repo rename

**Why this item:** Rename the GitHub repository itself (design C2 step 1-2).
**Why this order:** After code is committed and pushed — renaming before push would break the remote URL.

**Implementation:**
1. `gh repo rename pedantic-drip --yes`
2. `git remote set-url origin git@github.com:clthuang/pedantic-drip.git`
3. Verify: `gh repo view --json name` shows `"pedantic-drip"`

**Done when:** Repo renamed, remote updated, verification passes

## Step 7: Cache sync & verify

**Why this item:** The plugin cache at `~/.claude/plugins/cache/` has stale `iflow` references (design C2 step 3-4).
**Why this order:** After repo rename so sync-cache uses final paths.

**Implementation:**
1. Clean stale cache: `rm -rf ~/.claude/plugins/cache/*/iflow*`
2. Sync: `bash plugins/pd/hooks/sync-cache.sh`
3. Verify: `/pd:show-status` works in a new Claude Code session

**Done when:** Cache synced, commands work with `pd:` prefix

## Verification (AC Coverage)

| AC | Verified in Step |
|----|-----------------|
| AC-1 (validate.sh) | Step 4.1 |
| AC-2 (test suites) | Step 4.2-4.8 |
| AC-3 (plugin.json name) | Step 4.9 |
| AC-4 (no iflow in plugins/pd/) | Step 3 |
| AC-5 (/pd:show-status) | Step 7.3 |
| AC-6 (MCP servers) | Step 4.4-4.5 |
| AC-7 (pd.local.md) | Step 4.8 (hook tests) |
| AC-8 (repo name) | Step 6.3 |
| AC-9 (CLAUDE.md clean) | Step 3 |
| AC-10 (remote URL) | Step 6.2 |
| AC-11 (JSON valid) | Step 4.9 |
| AC-12 (scripts clean) | Step 3 |
