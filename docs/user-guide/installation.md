---
last-updated: 2026-04-02T00:00:00Z
source-feature: 075-phase-context-accumulation
---

<!-- AUTO-GENERATED: START - source: 075-phase-context-accumulation -->
# Installation

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Claude Code | latest | The CLI tool from Anthropic |
| Python | 3.10+ | Required for semantic memory. Linux: also install `python3-venv` |
| git | any | Required for branch management |

Optional: `rsync` and `gtimeout` (macOS: `brew install coreutils`).

## Install

```bash
/plugin marketplace add clthuang/pedantic-drip
/plugin install pd@my-local-plugins
```

Core dependencies install automatically on first session launch.

## Set Up Semantic Memory (Recommended)

Semantic memory lets pd find relevant past learnings by topic. After installing, run the interactive setup:

```bash
bash "$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts/setup.sh 2>/dev/null | head -1)"
```

The setup walks through provider selection and API key configuration.

| Provider | API Key | Notes |
|----------|---------|-------|
| gemini | `GEMINI_API_KEY` | Free tier available (default) |
| none | — | Disables semantic search |

## Per-Project Configuration

Each project can have a `.claude/pd.local.md` file with local settings:

```markdown
artifacts_root: docs          # where features/, brainstorms/ live (default: docs)
base_branch: develop          # merge target branch (default: auto-detected)
ui_server_enabled: true       # Kanban board auto-start (default: true)
ui_server_port: 8718          # Kanban board port (default: 8718)
```

## Verify Installation

Run the doctor to check workspace health:

```bash
bash "$(ls -d ~/.claude/plugins/cache/*/pd/*/scripts/doctor.sh 2>/dev/null | head -1)"
```

The doctor checks five categories: system prerequisites, plugin environment, embedding provider, memory system, and project context. It prints OS-specific fix commands for any issues found.

If you see all categories pass, pd is ready to use.
<!-- AUTO-GENERATED: END -->
