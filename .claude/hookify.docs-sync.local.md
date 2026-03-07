---
name: warn-docs-sync
enabled: true
event: file
tool_matcher: Edit|Write|MultiEdit
conditions:
  - field: file_path
    operator: regex_match
    pattern: plugins/iflow/(commands|skills|agents)/
action: warn
---

**Plugin component modified.** If you added, removed, or renamed a skill, command, or agent, update:
- `README.md` — user-facing tables
- `README_FOR_DEV.md` — developer lists and counts
- `plugins/iflow/skills/workflow-state/SKILL.md` — Phase Sequence one-liner (if phase names change)
