---
last-updated: 2026-04-15T00:00:00Z
source-feature: 078-cc-native-integration
---

<!-- AUTO-GENERATED: START - source: 078-cc-native-integration -->

# Getting Started

A guide for contributors who want to set up the development environment and run the test suite.

## Prerequisites

- macOS or Linux shell (zsh/bash)
- Git
- Python 3.11+ (for plugin venv and test suites)
- [uv](https://github.com/astral-sh/uv) — used for all Python dependency management (`uv add`, never `pip install` directly)
- [Claude Code](https://claude.ai/code) — the plugin is installed and used inside Claude Code

## Repository Setup

Clone and enter the repository:

```bash
git clone https://github.com/clthuang/pedantic-drip.git
cd pedantic-drip
```

Install Python dependencies for the plugin:

```bash
cd plugins/pd
uv sync --extra gemini
cd ../..
```

The `--extra gemini` flag pulls in the Gemini SDK used for semantic memory embeddings. Without it, memory still works via keyword search but vector search is disabled.

## Installing the Plugin Locally

Open Claude Code from the repository root:

```bash
claude
```

Inside Claude Code, register and install the local plugin:

```
/plugin marketplace add .claude-plugin/marketplace.json
/plugin install pd@my-local-plugins
```

After making changes to any plugin file (`plugins/pd/`), sync the cache so Claude Code picks up the update:

```
/pd:sync-cache
```

## Environment Configuration

Create a `.env` file at the project root to enable semantic memory:

```bash
GEMINI_API_KEY=your-key-here
```

Without this key, semantic memory degrades gracefully to FTS5 keyword search.

Session-local configuration lives in `.claude/pd.local.md`. Key fields:

| Field | Default | Purpose |
|-------|---------|---------|
| `artifacts_root` | `docs` | Root directory for features, brainstorms, projects |
| `base_branch` | `auto` | Merge target branch detection |
| `max_concurrent_agents` | `5` | Max parallel subagent Task dispatches |
| `memory_semantic_enabled` | `true` | Toggle vector search for memory |

> **Note:** In this repository `base_branch` auto-detects `main` from the remote HEAD, but all feature branches merge to `develop`. The release script handles `develop → main`. Always merge to `develop`, never directly to `main`.

## Running Tests

Use the plugin venv for all test commands — the system Python does not have MCP dependencies.

### Core test suites

```bash
# Entity registry (database, backfill, server helpers, frontmatter, search — 940+ tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v

# Transition gate (gate functions, constants, models — 257 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v

# Workflow engine (state engine, hydration, transitions, degradation — 309 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v

# Workflow state MCP server (processing + reconciliation integration — 272 tests)
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v

# Memory MCP server
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
```

### UI and doctor

```bash
# UI server (app + CLI + deepened — 190+ tests)
PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v

# Doctor diagnostic (150 tests)
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v
```

### Hook integration and bootstrap tests

```bash
bash plugins/pd/hooks/tests/test-hooks.sh
bash plugins/pd/mcp/test_run_memory_server.sh
bash plugins/pd/mcp/test_bootstrap_venv.sh      # ~2-5 min
bash plugins/pd/mcp/test_entity_server.sh
bash plugins/pd/mcp/test_run_workflow_server.sh
```

### Feature 078 integration tests

```bash
bash plugins/pd/hooks/tests/test-sqlite-concurrency.sh    # parallel entity-write spike
bash plugins/pd/hooks/tests/test-workflow-regression.sh   # workflow behavioral baseline
bash plugins/pd/hooks/tests/test-worktree-dispatch.sh     # git worktree mechanics
bash plugins/pd/hooks/tests/test-cc-native-integration.sh # SKILL.md prose contracts + config parsing
```

### Migration tests (system Python, not venv)

```bash
python3 -m pytest scripts/test_migrate_db.py scripts/test_migrate_e2e.py scripts/test_migrate_deepened.py -v
bash scripts/test_migrate_bash.sh
```

### Validate all plugin components

```bash
./validate.sh
```

## Known Pre-Existing Test Issues

These are not regressions — do not investigate unless you changed the related code:

- `test_deepened_app.py` — intermittent segfault due to SQLite threading
- `test_cli.py::test_cli_startup_url_output` — fails when port 8718 is already in use

<!-- AUTO-GENERATED: END -->
