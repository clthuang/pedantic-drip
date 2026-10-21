# Retrospective: Make Specs Executable

## What Went Well

- **Combined related gaps** - Executor-reviewer loop and worktree auto-creation were both "spec but not executable" issues. Combining them into one feature made sense.
- **Reused existing structure** - Commands already had pseudocode for the loop; we just made it executable with explicit Task tool calls.
- **Investigation-driven discovery** - Deep dive into "why doesn't this work?" revealed the gap was documentation clarity, not missing code.
- **Bug fix during feature** - Found and fixed PreToolUse hook JSON validation error while testing.

## What Could Improve

- **Test reviewer loop earlier** - Should have tested the loop execution before marking feature 003's design complete. The verification phase didn't catch that pseudocode != executable code.
- **Validate hook schemas** - Hook tests should validate against Claude Code's expected schema (via Context7). The wrong field names (`decision` vs `permissionDecision`) caused runtime errors.

## Learnings Captured

- Added to patterns.md: **Hook Schema Compliance** - Hook JSON output must use correct field names per hook type, validated against Context7 documentation

## Action Items

- [ ] Consider adding schema validation to hook tests (validate structure matches expected format)
- [ ] Feature 003 retrospective should note the "pseudocode != executable" gap

## Metrics

- **Files modified:** 9 (5 commands, 2 worktree flows, 1 hook, 1 test)
- **Lines changed:** ~1,500 additions
- **Bugs found and fixed:** 1 (PreToolUse hook schema)
