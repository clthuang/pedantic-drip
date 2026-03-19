#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Guard: already renamed?
if [[ -d plugins/pd ]]; then
  echo "plugins/pd/ already exists — rename may have already run"
  exit 1
fi
if [[ ! -d plugins/pd ]]; then
  echo "plugins/pd/ not found — nothing to rename"
  exit 1
fi

echo "=== Phase 1: Directory rename ==="
git mv plugins/pd plugins/pd

echo "=== Phase 2: Config and directory renames ==="
if [[ -f .claude/pd.local.md ]]; then
  git mv .claude/pd.local.md .claude/pd.local.md
fi
if [[ -f docs/pd-audit-findings.md ]]; then
  git mv docs/pd-audit-findings.md docs/pd-audit-findings.md
fi
# Rename global data directory (~/.claude/pd/ → ~/.claude/pd/)
if [[ -d "$HOME/.claude/pd" ]]; then
  mv "$HOME/.claude/pd" "$HOME/.claude/pd"
  echo "Renamed ~/.claude/pd/ -> ~/.claude/pd/"
elif [[ -d "$HOME/.claude/pd" ]]; then
  echo "~/.claude/pd/ already exists — skipping"
else
  echo "~/.claude/pd/ not found — skipping"
fi

echo "=== Phase 3: Bulk text replacement ==="
# Ordered replacements (most specific first)
REPLACEMENTS=(
  # Rule 1-5: Template variables
  "pd_artifacts_root|pd_artifacts_root"
  "pd_base_branch|pd_base_branch"
  "pd_release_script|pd_release_script"
  "pd_doc_tiers|pd_doc_tiers"
  "pd_plugin_root|pd_plugin_root"
  # Rule 6: Bash variable names
  "PD_CONFIG|PD_CONFIG"
  "PD_|PD_"
  # Rule 7: Config filename in code references
  "pd.local.md|pd.local.md"
  # Rule 8: Global data directory paths
  "pd/memory|pd/memory"
  "pd/entities|pd/entities"
  "pd/ui-server|pd/ui-server"
  "pd/mcp-bootstrap|pd/mcp-bootstrap"
  ".claude/pd|.claude/pd"
  # Rule 9: Plugin paths
  "plugins/pd|plugins/pd"
  # Rule 10: Command/skill/agent prefixes
  "pd:|pd:"
)

# Files/dirs to process (from spec include list)
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

for pair in "${REPLACEMENTS[@]}"; do
  old="${pair%%|*}"
  new="${pair##*|}"
  for pattern in "${INCLUDE_PATTERNS[@]}"; do
    if [[ -f "$pattern" ]]; then
      sed -i '' "s|${old}|${new}|g" "$pattern"
    elif [[ -d "$pattern" ]]; then
      find "$pattern" -type f \( -name "*.md" -o -name "*.py" -o -name "*.sh" -o -name "*.json" \) \
        ! -path "*/__pycache__/*" ! -path "*/.venv/*" \
        -exec sed -i '' "s|${old}|${new}|g" {} +
    fi
  done
done

echo "=== Phase 3b: Fix glob patterns ==="
# Catch glob patterns like */pd*/ used for plugin cache discovery
find plugins/pd -type f \( -name "*.md" -o -name "*.py" -o -name "*.sh" \) \
  ! -path "*/__pycache__/*" ! -path "*/.venv/*" \
  -exec sed -i '' 's|[*]/pd[*]/|*/pd*/|g' {} +

echo "=== Phase 4: JSON targeted edits ==="
python3 -c "
import json
p = 'plugins/pd/.claude-plugin/plugin.json'
d = json.loads(open(p).read())
d['name'] = 'pd'
open(p, 'w').write(json.dumps(d, indent=2) + '\n')
print(f'Updated {p}: name=pd')
"

python3 -c "
import json
p = '.claude-plugin/marketplace.json'
d = json.loads(open(p).read())
for plugin in d.get('plugins', []):
    if plugin.get('name') in ('pd', 'pd'):
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

echo "=== Phase 3c: Verify no remaining pd references ==="
REMAINING=$(grep -ri 'pd' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ .claude-plugin/ \
  --include='*.md' --include='*.py' --include='*.sh' --include='*.json' \
  --exclude-dir=__pycache__ --exclude-dir=.venv 2>/dev/null | wc -l | tr -d ' ')
if [[ "$REMAINING" -gt 0 ]]; then
  echo "WARNING: $REMAINING remaining pd references found:"
  grep -rn 'pd' plugins/pd/ scripts/ validate.sh README.md README_FOR_DEV.md CLAUDE.md .claude/ .claude-plugin/ \
    --include='*.md' --include='*.py' --include='*.sh' --include='*.json' \
    --exclude-dir=__pycache__ --exclude-dir=.venv 2>/dev/null | head -30
  echo ""
  echo "Review and fix these before committing."
else
  echo "No remaining pd references — clean rename!"
fi

echo ""
echo "=== Done ==="
echo "Next steps:"
echo "  1. Review changes: git diff --stat"
echo "  2. Fix any remaining references from Phase 3c output"
echo "  3. Run tests: ./validate.sh + test suites"
echo "  4. Commit all changes"
echo "  5. Rename GitHub repo: gh repo rename pedantic-drip --yes"
echo "  6. Update remote: git remote set-url origin git@github.com:clthuang/pedantic-drip.git"
echo "  7. Sync cache: rm -rf ~/.claude/plugins/cache/*/pd* && bash plugins/pd/hooks/sync-cache.sh"
