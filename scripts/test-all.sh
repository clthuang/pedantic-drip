#!/usr/bin/env bash
# The one test battery: CI (.github/workflows/ci.yml) and Verify's QA (.claude/pd.local.md qa_battery) both run it,
# so the two can't drift. New tests join by location: pytest collects plugins/pd, and every pd-* script with
# a --self-test runs it. Needs python3, uv, node and jq.
# Usage: bash scripts/test-all.sh   (from anywhere in the repository)
set -euo pipefail
cd "$(dirname "$0")/.."

./validate.sh
bash plugins/pd/hooks/tests/test-hooks.sh
bash scripts/test-release.sh
for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done
for s in plugins/pd/scripts/pd-*; do
    if [[ "$s" != *.py ]] && grep -q -- '--self-test' "$s"; then "$s" --self-test; fi
done
python3 plugins/pd/scripts/pd_common.py --self-test
uv run --script plugins/pd/scripts/pd-html.py --self-test
node plugins/pd/workflows/tests/test-workflows.mjs
uv run --project plugins/pd pytest -q plugins/pd
echo "test-all: every suite passed"
