# Design: Command Cleanup and Pseudocode Removal

## Prior Art Research

### Codebase Patterns

1. **Feature 015 MCP read pattern** — `show-status.md` and `list-features.md` call `get_phase(feature_type_id)` for phase detection, fall back to artifact-based detection on failure. Established the `get_phase` response shape and fallback convention.

2. **Feature 016 dual-write pattern** — `workflow-transitions/SKILL.md` Step 4 calls `transition_phase` after `.meta.json` write; Step 2 of `commitAndComplete` calls `complete_phase` after `.meta.json` write. Both use warn-and-continue on failure. Feature 017 uses the same `get_phase` call pattern for the secretary.md and create-specialist-team.md replacements.

3. **SC-5 test constraint** — `test_gate.py` lines 1861-1924 reads `workflow-state/SKILL.md`, locates heading containing "Phase Sequence" (line 1891), then finds first line with arrow character `→` after that heading (line 1896). Both the heading and the one-line arrow sequence must be preserved.

4. **Inline hard prerequisites** — Commands `implement.md`, `create-tasks.md`, `create-plan.md` already have the full Level 1-4 error messages inline. They reference `validateArtifact(path, "type")` by name but don't depend on the central pseudocode definition — it's a documentation shorthand.

### External Patterns

1. **StateFlow (Microsoft Research)** — Formalizes replacing text-based LLM workflow control with explicit state machine definitions. Result: 6x cost reduction. Aligns with our migration: pseudocode is the "text-based control" being replaced by Python state engine calls.

2. **Strangler Fig pattern** — New deterministic engine calls coexist with old text-based pseudocode during transition, then prose is surgically removed once engine handles the state. This is exactly features 014-016 (coexistence) → feature 017 (removal).

3. **Camunda agentic orchestration** — Keep core business logic deterministic (programmatic state engine), delegate only creative/adaptive tasks to LLM. Remove prose descriptions of "what should happen" from instructions.

## Architecture Overview

### Change Nature: Text-Only Cleanup

This feature modifies **only markdown files** — no Python code, no MCP servers, no database changes. All changes are deletions or text replacements within 9 markdown files (plus 1 verify-only).

### Component Map

```
workflow-state/SKILL.md          ← HEAVY: Remove ~188 lines (6 sections of pseudocode/tables)
secretary.md                     ← MEDIUM: Remove Phase Progression Table, update 2 reference sites
create-specialist-team.md        ← MEDIUM: Remove 3 targets (sequence, mapping table, comparison logic)
workflow-transitions/SKILL.md    ← LIGHT: Update 3 lines in Step 1
implement.md                     ← LIGHT: Replace 2 function name references
create-tasks.md                  ← LIGHT: Replace 1 function name reference
create-plan.md                   ← LIGHT: Replace 1 function name reference
CLAUDE.md                        ← LIGHT: Update 1 line in Documentation Sync table
.claude/hookify.docs-sync.local.md ← LIGHT: Update 'Workflow Map' reference to 'Phase Sequence one-liner'
docs/dev_guides/templates/command-template.md ← LIGHT: Update 'validateTransition' reference
docs/knowledge-bank/patterns.md  ← VERIFY-ONLY: Historical context reference, no change needed
```

### Execution Order

Changes must be applied in dependency order to avoid intermediate broken states:

```
Phase 1: Core removal (workflow-state/SKILL.md)
  - Remove pseudocode, tables, validation sections
  - Preserve: Phase Sequence heading + one-liner, Planned→Active, State Schema
  - Update FR-11 cross-reference (line 119)

Phase 2: Table replacements (secretary.md, create-specialist-team.md)
  - Remove phase progression/mapping tables
  - Insert get_phase MCP-based resolution with .meta.json fallback
  - File-independent from Phase 1 (different files); ordering is for implementer clarity

Phase 3: Reference updates (workflow-transitions/SKILL.md, implement.md, create-tasks.md, create-plan.md)
  - Update references to removed constructs
  - These are independent of Phase 2

Phase 4: Documentation and verification
  - Update CLAUDE.md reference (prerequisites note removed — Python test suite covers prerequisite correctness)
  - Update .claude/hookify.docs-sync.local.md: 'Workflow Map' → 'Phase Sequence one-liner'
  - Update docs/dev_guides/templates/command-template.md: 'Apply validateTransition logic' → describe check directly or reference workflow-transitions Step 1
  - Verify docs/knowledge-bank/patterns.md: 'validateTransition' reference is historical context (no change needed)
  - Measure line counts
  - Run grep validation and test suite
  - Run broad codebase grep across entire repo (excluding feature/project docs):
    grep -rn 'validateTransition\|validateArtifact\|Phase Progression Table\|Workflow Map' . --include='*.md' | grep -v docs/features/ | grep -v docs/projects/ | grep -v docs/brainstorms/
  - Verify yolo-stop.sh (FR-12, verify-only)
```

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SC-5 test breaks | Low | High | Preserve exact heading + arrow line; verify with pytest after changes |
| validate.sh fails | Low | Medium | Run after each phase; revert if needed |
| Phase Progression Table removal breaks secretary routing | Low | High | Replace with get_phase before removing; test with /iflow:show-status |
| Incomplete removal leaves stale references | Medium | Low | Final grep sweep (AC-1 through AC-15) catches any missed references |

### Technical Decisions

1. **Within-file atomic replace-then-remove:** Within secretary.md and create-specialist-team.md, perform the table removal and `get_phase` insertion in the same edit operation to avoid any intermediate state where routing logic is absent. The cross-file phasing (Phase 1 vs Phase 2) is for implementer clarity, not a technical dependency.

2. **`get_phase` response parsing:** The replacement text in secretary.md and create-specialist-team.md specifies the full JSON response shape and field names, matching `workflow_state_server.py:_serialize_state()`. This is a read-only `get_phase` call (not a write), so no dual-write complexity.

3. **Fallback pattern:** When `get_phase` MCP is unavailable, fall back to `.meta.json` `lastCompletedPhase` + canonical sequence logic. This matches the graceful degradation pattern from feature 010 and is consistent with how show-status.md and list-features.md already handle fallback.

4. **Line number approach:** Match by content (quoted text), not line numbers. Spec notes line numbers are approximate. Use grep to locate target content before editing. If content grep returns zero matches, manually inspect the target file to locate the functionally equivalent section before proceeding.

5. **`get_phase` source field:** The replacement text only reads `current_phase`, `last_completed_phase`, and `degraded` fields for routing decisions. The `source` field is documented for reference but not used in routing logic, so any future source values (e.g., test-internal `entity_db`) would not affect behavior.

6. **Edge case: "no active feature" routing:** The spec's FR-7 edge case says "route to iflow:brainstorm or iflow:create-feature" — this ambiguity is intentional. The maturity-based routing decision (brainstorm vs create-feature) is handled by the secretary's Triage step (Step 3), not by phase resolution. The edge case in the replacement text should simply state "no phase routing applicable" and fall through to the triage logic.

7. **Cross-reference precision for canonical sequence:** After cleanup, references to "the canonical sequence in workflow-state SKILL.md" point to the preserved one-liner (`brainstorm → specify → design → create-plan → create-tasks → implement → finish`), not the removed Phase Sequence table. The implementer should use the explicit one-liner text when clarity is needed.

## Interfaces

### No New Interfaces

This feature creates no new interfaces. It modifies text content in existing files while preserving existing interfaces:

- **MCP tool interfaces** (`get_phase`, `transition_phase`, `complete_phase`) — unchanged
- **`.meta.json` schema** — unchanged
- **File structure** (`workflow-state/SKILL.md`, `secretary.md`, etc.) — files continue to exist with reduced content
- **Test interface** (`test_gate.py` SC-5) — reads same file, same heading, same arrow line

### Contracts Between Changes

Each FR is independent at the implementation level (separate files or sections), but they share these contracts:

1. **Phase sequence one-liner** (NFR-3): All FRs that reference phase sequence (FR-5, FR-7, FR-8) point to the same preserved one-liner in workflow-state/SKILL.md rather than duplicating it.

2. **`get_phase` replacement text** (FR-7, FR-8): Both secretary.md and create-specialist-team.md use identical `get_phase` call structure with identical fallback logic. The replacement text is defined once in the spec (FR-7) and referenced by FR-8. Note: while the replacement text is identical, the two sites in secretary.md (Orchestrate subcommand line 336 vs Workflow Guardian line 520) differ in how feature identity is already established in preceding context — verify during implementation that the id/slug extraction assumptions hold for both sites.

3. **`validateArtifact` removal** (FR-2, FR-6, FR-10): The central definition (FR-2, FR-6) is removed, and references in commands (FR-10) are updated to describe the checks directly. These are independent edits but semantically linked.

### Verification Contracts

- **Pre-edit:** `wc -l` on all 9 editable target files to capture before counts (FR-13)
- **Post-edit:** Same `wc -l` to compute reductions
- **Grep validation:** All AC-1 through AC-15 grep patterns must pass
- **Test suite:** `./validate.sh` and SC-5 specific test must pass
- **Smoke test:** `/iflow:specify` on a test feature to verify end-to-end flow
