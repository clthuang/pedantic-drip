---
# Project — paths and integration
# Root directory for work items, brainstorms, and projects
artifacts_root: docs/dev_artifacts
# Merge target branch. "auto" detects from remote HEAD, falls back to "main"
base_branch: auto
# Path to release script, run after merge in /finish-workitem. Empty to skip
release_script:
# Comma-separated documentation tiers: user-guide, dev-guide, technical
doc_tiers: user-guide,dev-guide,technical

# Commands Verify's QA runs; each must pass at the QA commit (mirrors CI's test steps)
qa_battery:
  - ./validate.sh
  - bash plugins/pd/hooks/tests/test-hooks.sh
  - bash scripts/test-release.sh
  - bash -ec 'for t in plugins/pd/hooks/tests/test-pd-*.sh plugins/pd/scripts/test-phase-gate.sh; do bash "$t"; done'
  - bash -ec 'for s in pd-adopt pd-init pd-lint pd-new pd-proof pd-review-filter pd-status; do "plugins/pd/scripts/$s" --self-test; done'
  - python3 plugins/pd/scripts/pd_common.py --self-test
  - uv run --script plugins/pd/scripts/pd-html.py --self-test
  - node plugins/pd/workflows/tests/test-workflows.mjs
  - uv run --project plugins/pd pytest -q plugins/pd
# Output cap for every pd workflow run (the /pd:init default)
workflow_output_cap: 2000000

sop: 1
---
