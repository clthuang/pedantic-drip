# Commands Reference

```bash
# Validate components
./validate.sh

# Run memory server tests (requires plugin venv for MCP deps)
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v

# Run MCP bootstrap wrapper tests
bash plugins/pd/mcp/test_run_memory_server.sh

# Run MCP bootstrap shared library tests (unit + integration, ~2-5 min)
bash plugins/pd/mcp/test_bootstrap_venv.sh

# Run entity registry tests (database, backfill, server helpers, frontmatter, frontmatter_sync, search, metadata — 940+ tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v

# Run sqlite retry unit tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry.py -v

# Run sqlite retry concurrent-write integration tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry_integration.py -v

# Run entity search MCP tool tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_search_mcp.py -v

# Run entity server bootstrap wrapper tests
bash plugins/pd/mcp/test_entity_server.sh

# Run transition gate tests (gate functions, constants, models — 257 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v

# Run workflow engine tests (state engine, hydration, transitions, degradation — 309 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v

# Run reconciliation orchestrator tests (entity sync, backlog parsing, brainstorm archive — 62 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/reconciliation_orchestrator/ -v

# Run reconciliation module tests (drift detection, apply, frontmatter sync — 118 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v

# Run workflow state MCP server tests (processing + reconciliation integration — 272 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v

# Run workflow server bootstrap wrapper tests
bash plugins/pd/mcp/test_run_workflow_server.sh

# Run UI server tests (app + CLI + deepened — 190+ tests, requires PYTHONPATH for entity_registry + ui)
PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v
# Known pre-existing test issues (not regressions):
# - test_deepened_app.py: intermittent segfault (SQLite threading)
# - test_cli.py::test_cli_startup_url_output: fails when port 8718 in use

# Run doctor diagnostic + auto-fix tests (150 tests)
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v
# Doctor CLI supports --fix (apply safe fixes) and --fix --dry-run (preview fixes)

# Run migration tool tests (system python3, not plugin venv — 128 tests)
python3 -m pytest scripts/test_migrate_db.py scripts/test_migrate_e2e.py scripts/test_migrate_deepened.py -v
bash scripts/test_migrate_bash.sh

# Rebuild FTS index on entities DB (kills MCP servers temporarily, they auto-restart)
python3 scripts/migrate_db.py rebuild-fts [--skip-kill] [db_path]

# Run hook integration tests
bash plugins/pd/hooks/tests/test-hooks.sh

# Run capture-tool-failure hook tests (PostToolUseFailure — 11 tests)
bash plugins/pd/hooks/tests/test-capture-tool-failure.sh

# Run memory deprecation warning tests (legacy injection path escape hatch)
bash plugins/pd/hooks/tests/test-deprecation-warning.sh

# Run memory pattern embedding tests
bash plugins/pd/hooks/tests/test-memory-pattern.sh

# Release (bumps version, merges develop→main, tags)
# Uses --ci for non-interactive; BUMP_OVERRIDE=patch|minor|major to force bump type
bash scripts/release.sh --ci
# Preconditions: (1) clean working tree — git stash first, (2) CHANGELOG.md needs entries under [Unreleased]
```
