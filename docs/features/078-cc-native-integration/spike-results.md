# Spike Results: CC Native Feature Integration

This document captures the results of validation spikes performed during the CC native integration feature. Each section corresponds to a task in `plan.md` and documents the procedure, findings, and gating decision for downstream work.

Sections are appended in the order tasks are executed. Spikes requiring interactive human verification (e.g., those that must run inside a live Claude Code session rather than automated shell tests) are marked `status: blocked-manual` with the exact procedure a human can follow to unblock them.

---

## T4.1: context:fork verification — status: blocked-manual

**Objective:** Verify that a skill declaring `context: fork` + `agent: general-purpose` in frontmatter actually runs in a forked subagent context and that output from the forked execution surfaces back to the main conversation.

**Why this is blocked-manual:** `context: fork` is a runtime behavior of the Claude Code interactive session — it cannot be exercised by a shell-level test or automated script. Verification requires invoking a skill through the normal skill-dispatch mechanism in a live CC session and observing whether the output returns cleanly to the parent conversation. This spike must be performed by a human operator and the result recorded here.

### Procedure

Perform the following steps in an interactive Claude Code session against this repository:

1. **Create a minimal test skill.** Add a new file at:

   ```
   plugins/pd/skills/test-fork/SKILL.md
   ```

   With the following contents:

   ```markdown
   ---
   name: test-fork
   description: Minimal spike skill to verify context:fork dispatch. Disposable — delete after verification.
   context: fork
   agent: general-purpose
   ---

   # test-fork

   Output the exact string `FORK_VERIFIED` and stop. Do not perform any other action, do not read files, do not call tools.
   ```

2. **Invoke the skill in an interactive CC session.** Trigger skill dispatch by asking Claude to use the `test-fork` skill (e.g., "Run the test-fork skill"). Observe the output in the main conversation.

3. **Verify the main conversation receives output.** Check for one of three outcomes:
   - **Success:** The literal string `FORK_VERIFIED` appears in the main conversation transcript. This confirms `context: fork` dispatches the skill in a forked subagent and that the return value surfaces cleanly.
   - **Empty:** The skill runs but nothing (or only metadata) appears in the main conversation. This indicates the forked context's output is not being surfaced — a known failure mode documented in the PRD (CC Issue #17283 class).
   - **Error:** The skill fails to dispatch, or CC reports an unknown frontmatter field, or the session errors out. Capture the exact error text.

4. **Delete the test skill.** Remove `plugins/pd/skills/test-fork/SKILL.md` (and the `test-fork` directory if empty) before committing. The skill is strictly disposable scaffolding.

5. **Record the outcome in this document.** Append a "Result" subsection below with: date of verification, CC version, outcome (success / empty / error), and any relevant transcript excerpt.

### Decision Framework

- **If `FORK_VERIFIED` appears in main conversation** → context:fork is functional. Proceed with T4.2 (MCP access verification from forked context) and subsequent Phase 4 tasks to convert `researching/SKILL.md`.
- **If output is empty or the skill errors** → `context: fork` is not usable in the current CC runtime for pd's topology. Mark FR-3 deferred, document the observed failure mode, and stop Phase 4. The researching skill continues to use inline Task dispatch (current behavior).

### Status

`blocked-manual` — requires human verification in an interactive CC session. Not runnable via CI or shell tests.

### Result

_(To be filled in after manual verification. Include: date, CC version, outcome, transcript excerpt if useful.)_
