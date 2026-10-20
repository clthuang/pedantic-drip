# Tasks: Update Documentation Step

## Task List

### Phase 1: Foundation

#### Task 1.1: Create skill directory structure
- **Files:** `skills/updating-docs/`
- **Do:** Create the `skills/updating-docs/` directory
- **Test:** Directory exists
- **Done when:** Empty directory created at `skills/updating-docs/`

#### Task 1.2: Write documentation detector reference
- **Files:** `skills/updating-docs/references/detect-docs.md`
- **Do:** Write reference specification defining:
  - Detection targets (README.md, CHANGELOG.md, HISTORY.md, API.md, docs/*.md)
  - Return structure with exists boolean and path for each
  - Top-level docs/ only (no recursion)
- **Test:** Reference spec is complete and matches design.md interface
- **Done when:** detect-docs.md in references/ contains full detection spec per design

### Phase 2: Core Implementation

#### Task 2.1: Create /update-docs skill frontmatter
- **Depends on:** Task 1.1
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Create skill file with YAML frontmatter:
  - name: updating-docs
  - description: "Guide user through documentation updates based on feature context"
- **Test:** Frontmatter parses correctly
- **Done when:** SKILL.md exists with valid frontmatter

#### Task 2.2: Write skill prerequisites section
- **Depends on:** Task 2.1
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Add prerequisites section:
  - Check for feature context (spec.md)
  - Can work without feature context (just detect docs)
- **Test:** Section clearly states when skill can be used
- **Done when:** Prerequisites documented

#### Task 2.3: Write documentation detection section
- **Depends on:** Task 1.2, Task 2.2
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Add detection logic section:
  - Reference detect-docs.md reference spec
  - Present detected files to user
  - Handle "no docs found" case
- **Test:** Section covers all detection targets from design
- **Done when:** Detection flow documented

#### Task 2.4: Write user-visible change heuristics section
- **Depends on:** Task 2.3
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Add heuristics section:
  - Read spec.md "In Scope" section
  - Match against indicator table (from design.md)
  - Report user-visible vs internal changes
- **Test:** Heuristics match design.md table exactly
- **Done when:** Heuristics logic documented with examples

#### Task 2.5: Write suggestion and interaction flow
- **Depends on:** Task 2.4
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Add interaction section:
  - Present which docs might need updates (with reasoning)
  - Let user select which to update
  - Provide context for each selected doc
- **Test:** Flow matches design.md interface spec
- **Done when:** Interactive flow documented

#### Task 2.6: Review complete /update-docs skill
- **Depends on:** Task 2.5
- **Files:** `skills/updating-docs/SKILL.md`
- **Do:** Review full skill for:
  - Consistency with other skills in codebase
  - No auto-generation (advisory only)
  - Complete coverage of design requirements
- **Test:** Skill reads naturally and matches design
- **Done when:** Skill reviewed and any issues fixed

### Phase 3: Integration

#### Task 3.1: Add doc check step to /finish command
- **Depends on:** Task 2.6
- **Files:** `commands/finish.md`
- **Do:** Insert new pre-completion check after step 3 (quality review):
  - New step 4: Offer documentation review
  - Check if any doc files exist (README.md, CHANGELOG.md, etc.)
  - If yes: prompt "Documentation review? (y/n)"
  - If no: skip silently
- **Test:** New step 4 appears after quality review (step 3), before "Completion Options"
- **Done when:** Step added in Pre-Completion Checks section, numbered as step 4

#### Task 3.2: Document skip behavior
- **Depends on:** Task 3.1
- **Files:** `commands/finish.md`
- **Do:** Add behavior for both responses:
  - y: Invoke /update-docs skill
  - n: Continue to completion options
- **Test:** Both paths are clearly documented
- **Done when:** y/n behavior specified

#### Task 3.3: Final integration review
- **Depends on:** Task 3.2
- **Files:** `commands/finish.md`, `skills/updating-docs/SKILL.md`
- **Do:** Review complete integration:
  - /finish correctly references /update-docs
  - Flow is consistent between command and skill
  - No gaps in handoff
- **Test:** Manual walkthrough of /finish flow makes sense
- **Done when:** Integration reviewed and verified

## Summary

- Total tasks: 11
- Phase 1: 2 tasks (foundation)
- Phase 2: 6 tasks (core skill)
- Phase 3: 3 tasks (integration)
