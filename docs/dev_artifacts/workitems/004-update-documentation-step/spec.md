# Specification: Update Documentation Step

## Problem Statement

The `/finish` workflow completes features without checking if project documentation (README, CHANGELOG, API docs) needs updating, leading to documentation drift.

## Success Criteria

- [ ] `/finish` command includes a documentation review check before merge/PR options
- [ ] New `/update-docs` skill guides documentation updates based on detected doc files
- [ ] Documentation check is skippable (not blocking)
- [ ] Detection is project-dependent (only suggests for docs that exist)

## Scope

### In Scope

- Add documentation review step to `/finish` pre-completion checks
- Create `/update-docs` skill that:
  - Detects common documentation files (README.md, CHANGELOG.md, docs/*.md)
  - Suggests updates based on feature spec/changes
  - Does NOT auto-write (user controls content)
- Modify `/finish` command to offer `/update-docs` before completion

### Out of Scope

- Auto-generating documentation content
- Enforcing documentation (remains advisory)
- Integration with external doc tools (Docusaurus, MkDocs)
- API doc generation from code

## Acceptance Criteria

### Documentation Check in /finish

- Given a feature is ready to complete
- When user runs `/finish`
- Then a documentation check is offered before merge/PR options
- And the check can be skipped by user choice

### Project-Dependent Detection

- Given a project has README.md
- When `/update-docs` runs
- Then README.md is listed as potentially needing update

- Given a project has no CHANGELOG.md
- When `/update-docs` runs
- Then CHANGELOG.md is NOT suggested

### Update Suggestions

- Given a feature with user-visible changes (from spec.md)
- When `/update-docs` runs
- Then it suggests which docs might need updating
- And provides context from the feature

## Dependencies

- Existing `/finish` command
- Feature spec/brainstorm for context

## Open Questions

- Should detection include docs/ subdirectories recursively?
- What heuristics determine "user-visible changes"?
