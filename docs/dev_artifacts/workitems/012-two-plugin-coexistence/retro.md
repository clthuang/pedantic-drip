# Retrospective: Two-Plugin Coexistence

## What Went Well
- Two-plugin model cleanly separates development from production
- Release script worked correctly on first real test (v1.2.0)
- Quality reviewer caught real issues (outdated iflow/ hooks before release)
- Validation framework caught missing `completed` field in abandoned feature

## What Could Improve
- Verify actual implementation state before running /iflow:finish
- Run documentation update step earlier in finish workflow
- sync-cache.sh needed `|| true` for grep with pipefail - consider this pattern for new hooks

## Learnings Captured
- Added to patterns.md: Two-Plugin Coexistence
- Added to patterns.md: Environment Variable Bypass for Automation

## Key Insight
Claude Code uses `plugin.json` name field for display, not marketplace.json name. This discovery led to the two-plugin model as the clean solution.

## Action Items
- None - feature complete and released as v1.2.0
