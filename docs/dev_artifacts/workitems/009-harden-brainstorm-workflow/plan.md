# Plan: Harden Brainstorm Workflow

## Implementation Order

### Phase 1: Foundation

No new files needed—modifying existing skill file.

1. **Verify brainstorm-reviewer agent exists** — Confirm agent is in place
   - Complexity: Simple
   - Files: `plugins/iflow/agents/brainstorm-reviewer.md` (verify only)

### Phase 2: Core Implementation

Modify the brainstorming skill file.

1. **Add Verification section** — Insert new ### 7. Verification section
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `plugins/iflow/skills/brainstorming/SKILL.md`
   - Insert after line 134 (after "### 6. Capture Ideas" section)

2. **Replace Promotion Flow** — Replace ### 3. Promotion Flow with hardened version
   - Depends on: Step 1 (numbering coordination)
   - Complexity: Medium
   - Files: `plugins/iflow/skills/brainstorming/SKILL.md`
   - Replace lines 49-85 with ### 8. Promotion Flow

3. **Update Completion section** — Unify standalone and with-feature paths
   - Depends on: Steps 1-2 (section references)
   - Complexity: Simple
   - Files: `plugins/iflow/skills/brainstorming/SKILL.md`
   - Replace lines 172-179

4. **Add PROHIBITED section** — Append forbidden actions list
   - Depends on: None (can be done independently)
   - Complexity: Simple
   - Files: `plugins/iflow/skills/brainstorming/SKILL.md`
   - Append at end of file

### Phase 3: Validation

1. **Manual test: standalone brainstorm** — Run /iflow:brainstorm on new topic
   - Depends on: Phase 2 complete
   - Complexity: Simple
   - Verify: Reviewer runs, AskUserQuestion appears, both Yes/No paths work

2. **Manual test: with-feature brainstorm** — Run /iflow:brainstorm on existing feature
   - Depends on: Phase 2 complete
   - Complexity: Simple
   - Verify: Same hardened flow applies

## Dependency Graph

```
[Verify agent] ──→ [Add Verification] ──→ [Replace Promotion] ──→ [Update Completion]
                                                                          ↓
                   [Add PROHIBITED] ─────────────────────────────────────→ [Test]
```

## Risk Areas

- **Section renumbering**: Inserting new sections changes numbering of existing sections. Must coordinate carefully to avoid broken references.
- **Agent invocation**: If brainstorm-reviewer agent doesn't exist or has wrong format, verification will fail silently.

## Testing Strategy

- Manual test: Run standalone brainstorm, verify reviewer invokes
- Manual test: Answer "No" to promotion, verify session ends
- Manual test: Answer "Yes" to promotion, verify /create-feature is invoked

## Definition of Done

- [ ] Verification section added to skill
- [ ] Promotion flow replaced with hardened version
- [ ] Completion section unified
- [ ] PROHIBITED section added
- [ ] Manual tests pass for both paths
