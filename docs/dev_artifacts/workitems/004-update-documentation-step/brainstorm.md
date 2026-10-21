# Brainstorm: Update Documentation Step in /finish

**Date:** 2026-01-30
**Trigger:** Observation that /finish workflow lacks documentation update step

## The Gap

Current `/finish` workflow handles:
- Code quality (tests, reviews)
- Git workflow (merge, PR, cleanup)
- Internal knowledge (retrospectives → patterns.md, anti-patterns.md)

**Missing:** External documentation that users/developers need:
- README.md updates
- CHANGELOG entries
- API documentation
- User guides/tutorials

## Why This Matters

1. **Feature completion includes docs** - A feature isn't truly "done" until users know how to use it
2. **Docs rot** - If not updated at finish time, they fall out of sync
3. **Context loss** - The implementer has the most context; delay = lost knowledge
4. **PR quality** - PRs without doc updates are incomplete

## Questions to Explore

1. What documentation types need updating?
2. When in the flow should this happen?
3. Should it be mandatory or optional?
4. How to detect what docs need updating?
5. Should Claude assist or fully automate?

## Idea 1: Pre-Merge Documentation Check

Add a step before merge/PR options:

```
Documentation review:
- README.md: No changes needed / Needs update
- CHANGELOG.md: Entry needed for this feature
- API docs: {n} new endpoints undocumented

Update documentation now? (y/n)
```

**Pros:** Catches doc gaps before merge
**Cons:** Slows down finish flow; may feel tedious

## Idea 2: Documentation as Pre-Completion Check

Add to existing pre-completion checks:
1. Uncommitted changes
2. Incomplete tasks
3. Quality review
4. **Documentation review** ← NEW

**Pros:** Consistent with existing checks
**Cons:** Still another gate before completion

## Idea 3: Post-PR Documentation Reminder

After PR creation, suggest:
```
PR created. Consider:
- Update README if user-visible changes
- Add CHANGELOG entry
- Update API docs if applicable
```

**Pros:** Non-blocking; advisory
**Cons:** Easy to ignore; docs may be forgotten

## Idea 4: Dedicated /update-docs Command

Create separate command that:
1. Analyzes changes in feature branch
2. Identifies affected documentation
3. Suggests or generates updates

**Pros:** Explicit; can be used anytime
**Cons:** One more command to remember

## Idea 5: Documentation as Part of Retrospective

Extend `/retrospect` to include:
- "Does this feature need user documentation?"
- "Should the README be updated?"

**Pros:** Natural place for reflection
**Cons:** Retro is optional; docs might be skipped

## Idea 6: Smart Documentation Detection

Create a skill that:
1. Analyzes feature spec/design for user-visible changes
2. Scans for new exports, APIs, commands
3. Compares README sections to implementation
4. Suggests specific doc updates

**Pros:** Intelligent; reduces manual checking
**Cons:** Complex; might have false positives

## Potential Documentation Types

| Type | When to Update | Detection Method |
|------|----------------|------------------|
| README.md | User-visible features | Manual or spec analysis |
| CHANGELOG.md | Any release-worthy change | Always for non-hotfix |
| API docs | New/changed endpoints | Code analysis |
| CLI docs | New commands/flags | Command file analysis |
| Architecture docs | Structural changes | Design.md review |

## Recommended Approach

**Hybrid: Check + Skill**

1. Add documentation check to `/finish` pre-completion:
   - "Documentation review recommended. Run /update-docs? (y/n)"
   - Skippable for hotfixes

2. Create `/update-docs` skill/command that:
   - Reads feature spec for user-visible changes
   - Suggests CHANGELOG entry based on commits
   - Highlights README sections that might need updates
   - Doesn't auto-write (user controls docs)

## Decisions Made

**Approach:** Hybrid
- Add doc check to `/finish` pre-completion (skippable)
- Create `/update-docs` skill for explicit use

**Scope:** Project-dependent
- Detect available doc files (README, CHANGELOG, API docs, etc.)
- Suggest updates based on what exists in the project

## Next Steps

- [ ] Promote to feature?
- [ ] Define detection logic for doc files
- [ ] Design /update-docs skill behavior

## Related

- `/finish` command: `commands/finish.md`
- `/retrospect` skill: `skills/retrospecting/SKILL.md`
- Knowledge bank: `docs/dev_artifacts/knowledge-bank/`
