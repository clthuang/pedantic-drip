# Design: Rename to pedantic-drip

## Prior Art Research

Research skipped — this is a mechanical rename operation, not an architectural decision. The "design" is the execution script and ordering.

## Architecture Overview

This feature is a **scripted bulk rename** — no new components, no new interfaces, no architectural changes. The design specifies the exact execution sequence and the rename script.

```
Phase 1: Directory rename (git mv)
Phase 2: Config file rename (git mv)
Phase 3: Bulk text replacement (sed, scoped)
Phase 4: JSON targeted edits (python/jq)
Phase 5: Venv recreate
Phase 6: Validation & tests
Phase 7: GitHub repo rename
Phase 8: Cache sync
```

## Components

### C1: Rename Script (`scripts/rename-to-pd.sh`)

A single idempotent bash script that executes Phases 1-5. Run once, verify, commit.

**Why a script:**
- Reproducible — can be re-run if interrupted
- Auditable — the exact transformations are visible in one file
- Idempotent — checks if already renamed before acting

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Guard: already renamed?
if [[ -d plugins/pd ]]; then
  echo "plugins/pd/ already exists — rename may have already run"
  exit 1
fi
if [[ ! -d plugins/iflow ]]; then
  echo "plugins/iflow/ not found — nothing to rename"
  exit 1
fi

echo "=== Phase 1: Directory rename ==="
git mv plugins/iflow plugins/pd

echo "=== Phase 2: Config and directory renames ==="
if [[ -f .claude/iflow.local.md ]]; then
  git mv .claude/iflow.local.md .claude/pd.local.md
fi
if [[ -f docs/iflow-audit-findings.md ]]; then
  git mv docs/iflow-audit-findings.md docs/pd-audit-findings.md
fi
# Rename global data directory (~/.claude/iflow/ → ~/.claude/pd/)
if [[ -d "$HOME/.claude/iflow" ]]; then
  mv "$HOME/.claude/iflow" "$HOME/.claude/pd"
  echo "Renamed ~/.claude/iflow/ -> ~/.claude/pd/"
elif [[ -d "$HOME/.claude/pd" ]]; then
  echo "~/.claude/pd/ already exists — skipping"
else
  echo "~/.claude/iflow/ not found — skipping"
fi

echo "=== Phase 3: Bulk text replacement ==="
# Ordered replacements (most specific first per spec rules 1-7)
REPLACEMENTS=(
  # Rule 1-5: Template variables (most specific first)
  "iflow_artifacts_root:pd_artifacts_root"
  "iflow_base_branch:pd_base_branch"
  "iflow_release_script:pd_release_script"
  "iflow_doc_tiers:pd_doc_tiers"
  "iflow_plugin_root:pd_plugin_root"
  # Rule 6: Bash variable names
  "IFLOW_CONFIG:PD_CONFIG"
  # Rule 7: Config filename in code references
  "iflow.local.md:pd.local.md"
  # Rule 8: Global data directory
  "iflow/memory:pd/memory"
  "iflow/entities:pd/entities"
  "iflow/ui-server:pd/ui-server"
  "iflow/mcp-bootstrap:pd/mcp-bootstrap"
  ".claude/iflow:.claude/pd"
  # Rule 9: Plugin paths
  "plugins/iflow:plugins/pd"
  # Rule 10: Command/skill/agent prefixes
  "iflow::pd:"
)

# Files to process (from spec include list)
INCLUDE_PATTERNS=(
  "plugins/pd"
  "scripts"
  "validate.sh"
  "README.md"
  "README_FOR_DEV.md"
  "CLAUDE.md"
  ".claude"
  "docs/dev_guides"
  "docs/backlog.md"
  "docs/ecc-comparison-improvements.md"
  "docs/pd-audit-findings.md"
)

# File extensions to process
EXTENSIONS="md|py|sh|json|yaml|yml"

for pair in "${REPLACEMENTS[@]}"; do
  old="${pair%%:*}"
  new="${pair##*:}"
  for pattern in "${INCLUDE_PATTERNS[@]}"; do
    if [[ -f "$pattern" ]]; then
      # Single file
      sed -i '' "s|${old}|${new}|g" "$pattern"
    elif [[ -d "$pattern" ]]; then
      # Directory — find matching files, exclude __pycache__ and .venv
      find "$pattern" -type f \( -name "*.md" -o -name "*.py" -o -name "*.sh" -o -name "*.json" \) \
        ! -path "*/__pycache__/*" ! -path "*/.venv/*" \
        -exec sed -i '' "s|${old}|${new}|g" {} +
    fi
  done
done

echo "=== Phase 4: JSON targeted edits ==="
# plugin.json — change name field
python3 -c "
import json, sys
p = 'plugins/pd/.claude-plugin/plugin.json'
d = json.loads(open(p).read())
d['name'] = 'pd'
open(p, 'w').write(json.dumps(d, indent=2) + '\n')
print(f'Updated {p}: name=pd')
"

# marketplace.json — change plugin entry name
python3 -c "
import json
p = '.claude-plugin/marketplace.json'
d = json.loads(open(p).read())
for plugin in d.get('plugins', []):
    if plugin.get('name') == 'iflow':
        plugin['name'] = 'pd'
        plugin['source'] = './plugins/pd'
open(p, 'w').write(json.dumps(d, indent=2) + '\n')
print(f'Updated {p}: plugin name=pd, source=./plugins/pd')
"

echo "=== Phase 5: Venv recreate ==="
if [[ -d plugins/pd/.venv ]]; then
  rm -rf plugins/pd/.venv
  echo "Deleted old .venv"
fi
cd plugins/pd
if [[ -f pyproject.toml ]]; then
  uv venv .venv
  uv sync || { echo "ERROR: uv sync failed — tests will fail without dependencies"; exit 1; }
  echo "Recreated .venv"
else
  echo "No pyproject.toml — skipping venv creation"
fi
cd "$REPO_ROOT"

echo "=== Phase 3b: Fix glob patterns (*/iflow*/) ==="
# Catch glob patterns like */iflow*/ used for plugin cache discovery
find plugins/pd -type f \( -name "*.md" -o -name "*.py" -o -name "*.sh" \) \
  ! -path "*/__pycache__/*" ! -path "*/.venv/*" \
  -exec sed -i '' 's|\*/iflow\*/|*/pd*/|g' {} +

echo "=== Phase 3c: Verify no remaining iflow references ==="
REMAINING=$(grep -ri 'iflow' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ \
  --include='*.md' --include='*.py' --include='*.sh' --include='*.json' \
  --exclude-dir=__pycache__ --exclude-dir=.venv 2>/dev/null | wc -l)
if [[ "$REMAINING" -gt 0 ]]; then
  echo "WARNING: $REMAINING remaining iflow references found:"
  grep -rn 'iflow' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ \
    --include='*.md' --include='*.py' --include='*.sh' --include='*.json' \
    --exclude-dir=__pycache__ --exclude-dir=.venv 2>/dev/null | head -20
  echo "Review and fix manually before committing."
else
  echo "No remaining iflow references — clean rename."
fi

echo "=== Done ==="
echo "Next steps:"
echo "  1. Review changes: git diff --stat"
echo "  2. Run tests: validate.sh + test suites"
echo "  3. Commit all changes"
echo "  4. Rename GitHub repo: gh repo rename pedantic-drip"
echo "  5. Update remote: git remote set-url origin git@github.com:clthuang/pedantic-drip.git"
echo "  6. Sync cache: bash plugins/pd/hooks/sync-cache.sh"
```

### C2: Post-rename manual steps

These cannot be scripted into the rename script because they affect external systems:

1. **GitHub rename:** `gh repo rename pedantic-drip --yes`
2. **Remote update:** `git remote set-url origin git@github.com:clthuang/pedantic-drip.git`
3. **Cache sync:** `bash plugins/pd/hooks/sync-cache.sh`
4. **Verify MCP servers:** Restart Claude Code session to pick up new paths

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single script vs manual | Script | Reproducible, auditable, idempotent |
| sed vs Python for bulk replace | sed | Simpler for text replacement; Python only for JSON |
| Replacement order | Most specific first | Prevents `iflow_artifacts_root` being partially matched by a later `iflow` → `pd` rule |
| Venv handling | Delete + recreate | Venvs have hardcoded absolute paths; patching is unreliable |
| GitHub rename timing | After code changes committed | Rename URL before code is pushed would break push |
| Glob pattern `*/iflow*/` | Separate pass (Phase 3b) | These have different sed patterns than the prefix replacements |
| `~/.claude/iflow/` directory | Rename to `~/.claude/pd/` | Code references and directory must match; data stays intact |
| `IFLOW_CONFIG` variable | Rename to `PD_CONFIG` | Variable name must match new config filename |

## Risks

| Risk | Mitigation |
|------|------------|
| sed corrupts binary files | File extension filter (md, py, sh, json only) |
| Over-replacement in archival docs | Strict include list — archival dirs not included |
| Rename script interrupted mid-way | git mv is atomic; sed changes can be reverted via git checkout |
| Tests fail after rename | Run full suite before committing; fix before proceeding |

## Interfaces

No new interfaces. This is a rename — all existing interfaces keep their contracts, only the prefix/path changes.

**Before → After mapping:**
- `/iflow:show-status` → `/pd:show-status`
- `subagent_type: iflow:implementer` → `subagent_type: pd:implementer`
- `{iflow_artifacts_root}` → `{pd_artifacts_root}`
- `plugins/iflow/hooks/session-start.sh` → `plugins/pd/hooks/session-start.sh`

## Dependencies

- `sed` (macOS BSD version — uses `-i ''` not `-i`)
- `python3` (for JSON manipulation)
- `uv` (for venv recreation)
- `gh` CLI (for GitHub repo rename)
- No new package dependencies
