---
name: warn-docs-sync
enabled: true
event: file
tool_matcher: Edit|Write|MultiEdit
conditions:
  - field: file_path
    operator: regex_match
    pattern: plugins/pd/(commands|skills|agents)/
action: warn
---

**Plugin component modified.** If you added, removed, or renamed a skill, command, or agent, update:
- `README.md` — the command tables, the skill list and the counts
- `README_FOR_DEV.md` — the skill tables and the agent groups
- `plugins/pd/README.md` — component counts and the command and agent tables
