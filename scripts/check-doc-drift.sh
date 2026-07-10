#!/usr/bin/env bash
# check-doc-drift.sh — assert living docs match the implementation.
#
# Three checks (docs accuracy audit, 2026-07):
#   1. counts     — component/MCP-tool counts computed from the filesystem vs README claims
#   2. hooks      — hooks.json ↔ disk ↔ README_FOR_DEV.md cross-check
#   3. blocklist  — strings that only ever appear in stale docs must have 0 hits
#
# Invoked by validate.sh; exits non-zero on any drift. POSIX grep -E only.
set -euo pipefail
cd "$(dirname "$0")/.."

DRIFT_ERRORS=0
fail() {
    echo "FAIL(doc-drift): $1"
    DRIFT_ERRORS=$((DRIFT_ERRORS + 1))
}

# Canonical living-doc set (explicit include-list; historical trees are never scanned).
LIVING_DOCS="README.md README_FOR_DEV.md CLAUDE.md plugins/pd/README.md \
docs/dev_guides docs/user-guide docs/dev-guide plugins/pd/references \
docs/technical/architecture.md docs/technical/api-reference.md docs/technical/workflow-artifacts.md"

# --- Check 1: counts -------------------------------------------------------
commands=$(ls plugins/pd/commands/*.md | wc -l | tr -d ' ')
agents=$(ls plugins/pd/agents/*.md | wc -l | tr -d ' ')
skills=$(find plugins/pd/skills -mindepth 1 -maxdepth 1 -type d ! -name lib ! -name tests | wc -l | tr -d ' ')
entity_tools=$(grep -cF '@mcp.tool()' plugins/pd/mcp/entity_server.py)
workflow_tools=$(grep -cF '@mcp.tool()' plugins/pd/mcp/workflow_state_server.py)

# Components table in plugins/pd/README.md — label-anchored (Skills and Agents share a numeral).
table_val() {
    grep -E "^\| $1 \| [0-9]+ \|" plugins/pd/README.md | head -1 | grep -oE '[0-9]+' | head -1
}
[ "$(table_val Skills)" = "$skills" ] || fail "plugins/pd/README.md Components table: Skills=$(table_val Skills), filesystem=$skills"
[ "$(table_val Agents)" = "$agents" ] || fail "plugins/pd/README.md Components table: Agents=$(table_val Agents), filesystem=$agents"
[ "$(table_val Commands)" = "$commands" ] || fail "plugins/pd/README.md Components table: Commands=$(table_val Commands), filesystem=$commands"

# MCP tool tables — bound each table by its ### subheader; count only backtick-led rows.
entity_rows=$(awk '/^### Entity Registry Server/,/^### Workflow Engine Server/' plugins/pd/README.md | grep -cE '^\| \`' || true)
workflow_rows=$(awk '/^### Workflow Engine Server/,/^## /' plugins/pd/README.md | grep -cE '^\| \`' || true)
[ "$entity_rows" = "$entity_tools" ] || fail "plugins/pd/README.md entity tool table: $entity_rows rows, server has $entity_tools @mcp.tool()"
[ "$workflow_rows" = "$workflow_tools" ] || fail "plugins/pd/README.md workflow tool table: $workflow_rows rows, server has $workflow_tools @mcp.tool()"

# Digit-prose claims.
grep -q "exposes $entity_tools tools" plugins/pd/README.md || fail "plugins/pd/README.md prose: expected 'exposes $entity_tools tools' for entity server"
grep -q "exposes $workflow_tools tools" plugins/pd/README.md || fail "plugins/pd/README.md prose: expected 'exposes $workflow_tools tools' for workflow server"
grep -q "$skills skills and $agents agents" README.md || fail "README.md prose: expected '$skills skills and $agents agents'"

# --- Check 2: hooks --------------------------------------------------------
registered=$(python3 - <<'PYEOF'
import json
h = json.load(open('plugins/pd/hooks/hooks.json'))['hooks']
names = []
for entries in h.values():
    for e in entries:
        for hk in e.get('hooks', []):
            names.append(hk['command'].split('/')[-1].split('"')[0].strip())
print('\n'.join(names))
PYEOF
)
for name in $registered; do
    [ -f "plugins/pd/hooks/$name" ] || fail "hooks.json registers $name but plugins/pd/hooks/$name does not exist"
    base="${name%.sh}"
    grep -qE "(^|[^A-Za-z0-9-])${base}([^A-Za-z0-9-]|$)" README_FOR_DEV.md || fail "registered hook $base missing from README_FOR_DEV.md hooks table"
done
# Every hook script on disk must be registered or whitelisted (utility/worker).
for f in plugins/pd/hooks/*.sh; do
    b=$(basename "$f")
    case "$b" in cleanup-sandbox.sh) continue ;; esac
    echo "$registered" | grep -qF "$b" || fail "hook script $b on disk but not registered in hooks.json (whitelist it here if intentional)"
done

# --- Check 3: stale-string blocklist ---------------------------------------
# Strings that only ever appear in rotted docs. emit_hook_json needs a boundary
# guard so the legitimate safe_emit_hook_json never matches.
for pattern in 'meta-json-guard' 'code-simplifier' 'my-local-plugins' '(^|[^_[:alnum:]])emit_hook_json'; do
    hits=$(grep -rnE "$pattern" $LIVING_DOCS 2>/dev/null || true)
    if [ -n "$hits" ]; then
        fail "stale string '$pattern' found in living docs:"
        echo "$hits" | head -5
    fi
done

if [ "$DRIFT_ERRORS" -gt 0 ]; then
    echo "doc-drift: $DRIFT_ERRORS issue(s) — docs no longer match the implementation"
    exit 1
fi
echo "doc-drift: OK (commands=$commands agents=$agents skills=$skills entity_tools=$entity_tools workflow_tools=$workflow_tools)"
exit 0
