---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Getting Started

A guide for contributors who want to set up the development environment and run the test suite.

## Prerequisites

Everything in the user guide's [Prerequisites](../user-guide/installation.md#prerequisites), plus:

- macOS or Linux shell (zsh/bash)
- Python 3.14+ (`plugins/pd/pyproject.toml`); the scripts are stdlib-only, except `pd-html.py`
- [uv](https://github.com/astral-sh/uv) — all Python dependency management (`uv add`, never `pip install`); `pd-html.py` runs through `uv run`
- Node.js — the workflow scripts' test

## Repository Setup

```bash
git clone https://github.com/clthuang/pedantic-drip.git
cd pedantic-drip
cd plugins/pd && uv sync && cd ../..
```

## Installing the Plugin Locally

Install the released plugin as [Installation](../user-guide/installation.md#install) shows.

To try plugin changes, start a session with this checkout's plugin in place of the installed one, for that session only:

```bash
claude --plugin-dir plugins/pd
```

The installed copy changes only through a release, which reaches installs through `stable` ([Update](../user-guide/installation.md#update)).

## Project Configuration

Each project's settings live in `.claude/pd.local.md`, written by `/pd:init`. Key fields:

| Field | Default | Purpose |
|-------|---------|---------|
| `artifacts_root` | `docs/dev_artifacts` | Root for work items, plans, brainstorms, rca items and the backlog |
| `base_branch` | `auto` | Merge target: origin's HEAD, else `main` |
| `qa_battery` | none | The QA commands Verify requires; `phase-gate.sh verify` fails without it |
| `workflow_output_cap` | none (`/pd:init` writes `2000000`) | Output tokens per workflow run |
| `workitem_token_budget` | unset | Tokens per work item, checked by the Stop hook |

## Running Tests

The test commands are in [commands-reference.md](commands-reference.md). Run them in a throwaway shell, as that page shows (a fresh `HOME`, `ENTITY_DB_PATH` unset), so no test touches your real `~/.claude`.
