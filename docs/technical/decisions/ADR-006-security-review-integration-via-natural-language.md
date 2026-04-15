---
last-updated: 2026-04-15T00:00:00Z
source-feature: 078-cc-native-integration
status: Accepted
---
# ADR-006: Security Review Integration via Natural Language Instruction

## Status
Accepted

## Context
Feature 078 adds a pre-merge security scan step to `/pd:finish-feature` and `/pd:wrap-up`. The natural integration point would be invoking `/security-review` programmatically from skill/command markdown. However, CC slash commands cannot be called programmatically from skill or command markdown — they are only available through natural language instructions to the orchestrating agent. The `security-review` command is an open-source reference implementation (`anthropics/claude-code-security-review`) that users copy to their project's `.claude/commands/` directory.

## Decision
Add a Step 5a-bis block to `finish-feature.md` and `wrap-up.md` that instructs the orchestrating agent in natural language to run `/security-review` after all project checks pass:

- If `.claude/commands/security-review.md` is present: the agent invokes it; critical/high findings block the merge (same auto-fix loop as other Step 5a failures).
- If the command is not installed or fails: skip with a warning and proceed to merge.

Add a `check_security_review_command` doctor health check that warns when `.claude/commands/security-review.md` is absent. The doctor does not install the file — it informs the user where to copy it from. pd bundles the template at `plugins/pd/references/security-review.md`.

## Alternatives Considered
- **Programmatic invocation from skill markdown** — not supported; CC slash commands are not available to skill/command instructions.
- **Bundle and auto-install security-review.md** — pd managing files in `.claude/commands/` is outside its scope and risks overwriting user customizations.
- **Skip security review entirely** — leaves a capability gap; graceful degradation (skip when not installed) achieves the goal without hard dependency.

## Consequences
- Pre-merge security scanning is available to any project that copies the reference implementation into `.claude/commands/`.
- The integration is inherently graceful: workflows in projects without the command are unaffected.
- Natural language invocation means the behavior depends on the orchestrating agent correctly interpreting the instruction — it cannot be unit tested the same way a direct function call could be.
- Doctor check provides visibility into missing setup without imposing it.

## References
- Feature 078 design.md TD-4
- `anthropics/claude-code-security-review` — reference implementation
- `plugins/pd/references/security-review.md` — bundled template
