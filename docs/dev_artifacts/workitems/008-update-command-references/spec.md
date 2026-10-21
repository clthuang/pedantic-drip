# Specification: Update Command References

## Problem Statement

Command references use old `/command` format instead of namespaced `/iflow:command` format.

## Success Criteria

- [ ] All command references in README.md use `/iflow:` prefix
- [ ] All command references in CLAUDE.md use `/iflow:` prefix
- [ ] All command references in plugins/iflow/**/*.md use `/iflow:` prefix

## Scope

### In Scope

- README.md
- CLAUDE.md
- plugins/iflow/README.md
- plugins/iflow/commands/*.md
- plugins/iflow/skills/*/SKILL.md

### Out of Scope

- docs/features/ (historical records)
- docs/plans/ (historical records)
- docs/knowledge-bank/ (if any references exist)

## Commands to Update

| Old | New |
|-----|-----|
| `/add-to-backlog` | `/iflow:add-to-backlog` |
| `/brainstorm` | `/iflow:brainstorm` |
| `/create-feature` | `/iflow:create-feature` |
| `/specify` | `/iflow:specify` |
| `/design` | `/iflow:design` |
| `/create-plan` | `/iflow:create-plan` |
| `/create-tasks` | `/iflow:create-tasks` |
| `/implement` | `/iflow:implement` |
| `/verify` | `/iflow:verify` |
| `/finish` | `/iflow:finish` |
| `/show-status` | `/iflow:show-status` |
| `/list-features` | `/iflow:list-features` |
| `/retrospect` | `/iflow:retrospect` |
| `/cleanup-brainstorms` | `/iflow:cleanup-brainstorms` |
| `/update-docs` | `/iflow:update-docs` |
