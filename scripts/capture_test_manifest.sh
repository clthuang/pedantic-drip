#!/usr/bin/env bash
# Capture Wave 2's test manifests, the one definition every step compares.
# Usage: scripts/capture_test_manifest.sh <out-dir>
#
# Writes COMMIT, ENV, collected.txt and outcomes.txt. collected.txt ids are
# rootdir-relative (hooks/lib/...); outcomes.txt ids are cwd-relative
# (plugins/pd/hooks/lib/...). Compare like with like. Manifests up to Wave 2
# step 4 also hold strict-all.txt and strict-nonformat.txt, from a forced-strict
# run; step 5 deleted the switch, so that run would repeat this one.
set -uo pipefail
out="${1:?usage: capture_test_manifest.sh <out-dir>}"
cd "$(git rev-parse --show-toplevel)" || exit 1
mkdir -p "$out"
py=plugins/pd/.venv/bin/python
# One process for all four, as every manifest since step 0 was taken.
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

echo "collected $(wc -l < "$out/collected.txt" | tr -d ' ')" \
     "| passed $(grep -c '^PASSED ' "$out/outcomes.txt")" \
     "| skipped $(grep -c '^SKIPPED ' "$out/outcomes.txt")" \
     "| not passed $(grep -cvE '^(PASSED|SKIPPED) ' "$out/outcomes.txt")"
