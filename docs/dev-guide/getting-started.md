---
last-updated: 2026-10-18T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Getting Started

A guide for contributors who want to set up the development environment and run the test suite.

## Prerequisites

- macOS or Linux shell (zsh/bash)
- Git
- Python 3.14+ (`plugins/pd/pyproject.toml`); the scripts are stdlib-only
- [uv](https://github.com/astral-sh/uv) — all Python dependency management (`uv add`, never `pip install`); `pd-html.py` runs through `uv run`
- Node.js — the workflow scripts' test
- [Claude Code](https://claude.ai/code) — the plugin is installed and used inside Claude Code

## Repository Setup

```bash
git clone https://github.com/clthuang/pedantic-drip.git
cd pedantic-drip
cd plugins/pd && uv sync && cd ../..
```

## Installing the Plugin Locally

Inside Claude Code, install the released plugin (`#stable` follows releases):

```
/plugin marketplace add clthuang/pedantic-drip#stable
/plugin install pd@pedantic-drip-marketplace
```

To try plugin changes, start a session with this checkout's plugin in place of the installed one, for that session only:

```bash
claude --plugin-dir plugins/pd
```

The installed copy changes only through a release, which reaches installs through `stable`.

## Project Configuration

Each project's settings live in `.claude/pd.local.md`, written by `/pd:init`. Key fields:

| Field | Default | Purpose |
|-------|---------|---------|
| `artifacts_root` | `docs/dev_artifacts` | Root for features, plans, brainstorms, rca items and the backlog |
| `base_branch` | `auto` | Merge target: origin's HEAD, else `main` |
| `qa_battery` | none | The QA commands Verify requires; `phase-gate.sh verify` fails without it |
| `workflow_output_cap` | `2000000` | Output tokens per workflow run |
| `feature_token_budget` | unset | Tokens per feature, checked by the Stop hook |

## Running Tests

Run every command with a throwaway `HOME`, so no test touches your real `~/.claude`. The full list is in [commands-reference.md](commands-reference.md).

```bash
H=$(mktemp -d)
env HOME=$H ./validate.sh                                       # component validation
env HOME=$H bash scripts/check-doc-drift.sh                     # docs match the components
env HOME=$H python3 plugins/pd/scripts/pd-lint --self-test      # each script has --self-test
env HOME=$H bash plugins/pd/scripts/test-phase-gate.sh          # the phase exit checks
env HOME=$H bash plugins/pd/hooks/tests/test-hooks.sh           # hook integration
node plugins/pd/workflows/tests/test-workflows.mjs              # workflow scripts, stubbed
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks -q       # Python hook tests
```
