# Plan: Update Documentation Step

## Implementation Order

### Phase 1: Foundation

Items with no dependencies.

1. **Documentation Detector Reference** — Specification for detecting doc files in project
   - Complexity: Simple
   - Files: `skills/updating-docs/references/detect-docs.md`
   - Notes: Pure detection logic, returns structured result

### Phase 2: Core Implementation

Items depending on Phase 1.

1. **Create /update-docs Skill** — Skill that guides doc updates based on feature context
   - Depends on: Documentation Detector
   - Complexity: Medium
   - Files: `skills/updating-docs/SKILL.md`
   - Notes: Reads spec.md for context, presents suggestions, user decides

2. **User-Visible Change Heuristics** — Logic to determine if feature has user-visible changes
   - Depends on: Documentation Detector (needs to know which docs to suggest)
   - Complexity: Simple
   - Files: Inline in `/update-docs` skill
   - Notes: Parse spec.md "In Scope" section, match against indicator table from design

### Phase 3: Integration

Items depending on Phase 2.

1. **Modify /finish Command** — Add documentation check step to pre-completion flow
   - Depends on: /update-docs skill (needs to invoke it)
   - Complexity: Simple
   - Files: `commands/finish.md`
   - Notes: Insert after quality review step, single y/n prompt, skippable

## Dependency Graph

```
Documentation Detector ──→ /update-docs Skill ──→ /finish Integration
                          (includes heuristics)
```

Note: User-Visible Heuristics is embedded in the /update-docs skill, not a separate component.

## Risk Areas

- **/update-docs skill scope creep**: Keep it advisory-only. Don't add auto-generation features.
- **Detection false positives**: Start with explicit file patterns (README.md, CHANGELOG.md, etc.), not fuzzy matching.

## Testing Strategy

- **Manual testing**:
  - Run `/update-docs` in project with various doc files present/absent
  - Run `/finish` and verify doc check appears at correct point in flow
  - Verify skip works (n response)
  - Verify invoke works (y response → /update-docs runs)

- **Edge cases to verify**:
  - Project with no doc files → silent skip
  - Project with only README.md → only README suggested
  - Feature with no user-visible changes → reports "No user-visible changes"

## Definition of Done

- [ ] Documentation Detector identifies README.md, CHANGELOG.md, HISTORY.md, API.md, docs/*.md
- [ ] /update-docs skill detects docs, reads feature context, presents suggestions
- [ ] /update-docs correctly identifies user-visible changes from spec.md
- [ ] /finish includes doc check after quality review step
- [ ] Doc check is skippable (y/n prompt)
- [ ] All components follow existing skill/command patterns in codebase
