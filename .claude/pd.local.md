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

# Commands Verify's QA runs; each must pass at the QA commit (scripts/test-all.sh is CI's battery too)
qa_battery:
  - bash scripts/test-all.sh
# Output cap for every pd workflow run (the /pd:init default)
workflow_output_cap: 2000000

sop: 1
---
