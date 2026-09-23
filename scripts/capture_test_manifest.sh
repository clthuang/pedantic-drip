#!/usr/bin/env bash
# Capture Wave 2's test manifests, the one definition every step compares.
# Usage: scripts/capture_test_manifest.sh <out-dir>
#
# Writes COMMIT, ENV, collected.txt, outcomes.txt, strict-all.txt and
# strict-nonformat.txt. collected.txt ids are rootdir-relative (hooks/lib/...);
# the others are cwd-relative (plugins/pd/hooks/lib/...). Compare like with like.
set -uo pipefail
out="${1:?usage: capture_test_manifest.sh <out-dir>}"
cd "$(git rev-parse --show-toplevel)" || exit 1
mkdir -p "$out"
py=plugins/pd/.venv/bin/python
# One process for all four: the conftests' strict-off default is session-scoped
# and process-wide, so a scope run on its own is strict and not comparable.
scopes=(plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests plugins/pd/scripts/tests)

git rev-parse HEAD > "$out/COMMIT"
{
  echo "cwd=$PWD"
  "$py" -m pytest "${scopes[@]}" --collect-only -p no:randomly 2>/dev/null | grep -m1 '^rootdir'
  "$py" -c 'import sys, sqlite3, pytest; print(f"python={sys.version.split()[0]} pytest={pytest.__version__} sqlite={sqlite3.sqlite_version}")'
} > "$out/ENV"

"$py" -m pytest "${scopes[@]}" --collect-only -q -p no:randomly | grep '::' | sort > "$out/collected.txt"
"$py" -m pytest "${scopes[@]}" -q -p no:randomly --tb=no -rA \
  | grep -E '^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) ' | sort > "$out/outcomes.txt"
# pytest cuts summary lines to the terminal width (80 when piped); every node
# id here is longer, so without COLUMNS the failure reasons are dropped.
COLUMNS=1000 PD_REGISTER_ENTITY_STRICT_ID_FORMAT=1 "$py" -m pytest "${scopes[@]}" -q -p no:randomly --tb=line -rfE \
  | grep -E '^(FAILED|ERROR) ' | sort > "$out/strict-all.txt"
grep -v 'EntityIdFormatError' "$out/strict-all.txt" > "$out/strict-nonformat.txt"

echo "collected $(wc -l < "$out/collected.txt" | tr -d ' ')" \
     "| passed $(grep -c '^PASSED ' "$out/outcomes.txt")" \
     "| skipped $(grep -c '^SKIPPED ' "$out/outcomes.txt")" \
     "| not passed $(grep -cvE '^(PASSED|SKIPPED) ' "$out/outcomes.txt")" \
     "| strict failures $(wc -l < "$out/strict-all.txt" | tr -d ' ')" \
     "| of those not an id-format error $(wc -l < "$out/strict-nonformat.txt" | tr -d ' ')"
