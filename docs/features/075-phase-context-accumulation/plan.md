# Implementation Plan: Phase Context Accumulation

**Feature:** 075-phase-context-accumulation
**Spec:** spec.md | **Design:** design.md
**Created:** 2026-04-02

## Implementation Order

### Stage 1: Storage Infrastructure (no behavioral changes)

**Item 1: C6 — Schema Registration (metadata.py)**
Add `"phase_summaries": list` to `METADATA_SCHEMAS['feature']` in metadata.py (after line 44, within the feature dict). This prevents `validate_metadata` from producing schema-mismatch warnings when phase_summaries is present (AC-11).

Also add `backward_context: dict`, `backward_return_target: str`, `backward_history: list` to `METADATA_SCHEMAS['feature']` to eliminate pre-existing schema warnings (opportunistic fix).

- File: `plugins/pd/hooks/lib/entity_registry/metadata.py`
- TDD steps:
  1. Write test asserting `validate_metadata("feature", {"phase_summaries": [...]})` produces no warnings (test fails — key not in schema yet)
  2. Add `"phase_summaries": list` (and backward_* keys) to METADATA_SCHEMAS['feature'] dict
  3. Verify test passes

**Item 2: C3 — Summary Projection (_project_meta_json)**
Add `phase_summaries` projection to `_project_meta_json()` in workflow_state_server.py, following the backward_context pattern at lines 383-388. Insert after line 388, before the atomic write at line 390.

- File: `plugins/pd/mcp/workflow_state_server.py`
- TDD steps:
  1. Write test asserting `_project_meta_json` includes `phase_summaries` in output when present in entity metadata, and omits it when absent (AC-3, AC-10) (test fails — projection not implemented yet)
  2. Add 3 lines (comment + conditional projection) to `_project_meta_json`
  3. Verify test passes

### Stage 2: Summary Generation (SKILL.md instructions)

**Item 3: C1 — commitAndComplete Step 3a (summary construction + storage)**
Add Step 3a to commitAndComplete in `SKILL.md`, inserted between existing Step 3 (Phase Summary output) and existing Step 3b (Forward Re-Run Check). Step 3a instructs the LLM to:
1. Construct a summary dict from Step 3 output (7 schema fields per I1)
2. Apply 2000-char cap with truncation order per AC-8
3. Read existing `phase_summaries` from .meta.json
4. Append new entry and call `update_entity` (best-effort, per I2 pseudocode)

- File: `plugins/pd/skills/workflow-transitions/SKILL.md`
- Change: ~30-40 lines of instruction text
- No Python code changes — this is LLM prompt instructions

**Item 4: C2 — Summary Storage (verification only)**
No new code. C2 is handled by existing `update_entity` MCP which already supports arbitrary metadata dict merging. This item verifies that `update_entity` correctly performs shallow merge on `phase_summaries` key. Covered by existing update_entity tests plus new AC-1 integration test.

### Stage 3: Summary Injection (SKILL.md + command files)

**Item 5: C4 — validateAndSetup Step 1b Enhancement**
Enhance validateAndSetup Step 1b in `SKILL.md` to:
1. Detect backward transition via `phases[target_phase].completed` existence (I4)
2. Read `phase_summaries` from .meta.json
3. Format unified `## Phase Context` block with `### Reviewer Referral` and `### Prior Phase Summaries` sub-sections (I5)
4. Replace existing standalone `## Backward Travel Context` block with the unified format (TD-7)
5. Trim to last 2 entries per phase for display (AC-9)

- File: `plugins/pd/skills/workflow-transitions/SKILL.md`
- Change: Replace/enhance Step 1b backward context handling (~40-50 lines)
- Pre-implementation: `grep -rn 'Backward Travel Context' plugins/pd/` to find all references. Update all found references as part of this item.
- No Python code changes — LLM prompt instructions

**Item 6: C5 — Reviewer Prompt Injection (4 command files)**
Update 4 command files to include `## Phase Context` section in reviewer dispatch prompts on backward transitions. Same format as I5, inserted after `## Relevant Engineering Memory` and before review instructions (I6).

- Files: `plugins/pd/commands/specify.md`, `design.md`, `create-plan.md`, `implement.md`
- Change: Add conditional injection template to each reviewer dispatch (10 total dispatches across 4 files per design I6 table)
- Use the injection template from design I6. For each dispatch listed in design.md I6 table, insert after `## Relevant Engineering Memory`. Verify with grep that all dispatches are updated.
- No Python code changes — LLM prompt instructions

### Stage 4: Testing & Verification

**Item 7: Integration Tests for MCP-Mediated Storage Flow**
Unit tests for C6 (schema) and C3 (projection) are written in Items 1 and 2 (TDD). This item covers integration tests only:
- Integration test: `update_entity` appends to `phase_summaries` list (AC-1)
- Integration test: `update_entity` failure does not block phase completion (AC-2)
- Integration test: features without summaries have zero behavior change (AC-10)

**Item 8: Full Regression Suite**
Run complete test suites to verify no regressions:
- `workflow_state_server` tests (272 tests)
- `entity_registry` tests (940+ tests)
- `workflow_engine` tests (309 tests)
- `transition_gate` tests (257 tests)

## Dependency Graph

```
Item 1 (schema) ────┐
Item 2 (projection) ├──> Item 4 (storage verification)
                    │
Item 3 (generation) ┼──> Item 5 (injection) ──> Item 6 (reviewer prompts)
                    │
Items 1-6 ──────────┴──> Item 7 (integration tests) ──> Item 8 (regression)
```

Items 1, 2, and 3 are independent of each other (different files, no code dependencies) and can be done in parallel.
The real ordering constraint is: Item 2 must complete before Item 5 (injection reads projected phase_summaries from .meta.json).
Item 4 depends on Items 1+2 (infrastructure must exist before verification).
Item 5 depends on Items 3+4 (generation and storage before injection).
Item 6 depends on Item 5 (injection logic defined before reviewer prompts reference it).
Item 7 depends on all implementation items.
Item 8 depends on Item 7.

## Risk Areas

1. **Step 3a instruction clarity** — The LLM executing commitAndComplete must correctly construct the summary dict and handle the append + update_entity call. Mitigation: Provide explicit pseudocode in SKILL.md with field-by-field mapping.

2. **Backward transition detection accuracy** — Using `phases[target].completed` existence as the detection signal. Mitigation: Design I4 analysis confirms this covers both reviewer-initiated and user-initiated re-entry.

3. **Unified ## Phase Context replacing ## Backward Travel Context** — Must not break existing backward_context injection behavior. Mitigation: TD-7 specifies the existing content is preserved under `### Reviewer Referral` sub-section; only the heading changes.

4. **Reviewer dispatch template count** — 10 dispatches across 4 files is a broad surface area. Mitigation: Use identical injection template text across all dispatches; mechanical insertion.

5. **Stale .meta.json read in Step 3a** — Single-writer guarantee: only one phase runs per feature at a time (design.md:358). The stale-read risk is theoretical only. Step 3a instructions should explicitly note: "Read phase_summaries from .meta.json loaded at phase start — no re-read needed due to single-writer guarantee per feature."

## Testing Strategy

- **Unit tests** for Python code: metadata schema validation (AC-11), _project_meta_json projection (AC-3, AC-10)
- **Integration tests** via MCP: update_entity append behavior (AC-1), zero behavior change without summaries (AC-10)
- **Manual verification**: Run a feature through specify -> design -> backward to specify, confirm ## Phase Context block appears with prior summaries
- **Regression**: Full test suites for all affected modules

## Definition of Done

- [ ] `METADATA_SCHEMAS['feature']` includes `"phase_summaries": list`
- [ ] `_project_meta_json` projects `phase_summaries` to .meta.json (present when data exists, absent when not)
- [ ] `commitAndComplete` Step 3a instructions in SKILL.md construct and store summary dict via update_entity
- [ ] `validateAndSetup` Step 1b injects `## Phase Context` block on backward transitions
- [ ] 4 command files include phase context in reviewer dispatch prompts on backward transitions
- [ ] All tests pass (new + regression)
- [ ] Features without phase_summaries experience zero behavior change
