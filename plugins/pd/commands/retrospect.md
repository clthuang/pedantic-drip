---
description: Run retrospective for current or completed feature
argument-hint: [feature-id]
---

Invoke the retrospecting skill for the specified or current feature.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read {pd_artifacts_root}/features/ to find feature, then follow retrospecting skill instructions.

Note: Best results when run after implementation phase completes
(when .review-history.md and full .meta.json are available).
Can also run on partially completed features with reduced data.
