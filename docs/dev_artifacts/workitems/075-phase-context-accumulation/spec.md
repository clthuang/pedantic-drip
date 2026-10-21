# Specification: Phase Context Accumulation

**Origin:** Backlog #00044 — backward transitions (rework) have zero context about prior phase decisions, causing blind rework and unnecessary re-iterations.

## Problem Statement
When backward travel occurs (reviewer sends `backward_to`), the re-entered phase has no knowledge of what prior phases decided, produced, or were told by reviewers. `backward_context` exists but is cleared after phase completion — a second backward hop loses all prior context. `phase_timing` tracks iterations and reviewer notes but not decisions or artifacts. The result: reviewers re-raise resolved issues, drafters contradict prior conclusions, and iteration counts inflate.

## Success Criteria
- [ ] `complete_phase` MCP accepts a `phase_summary` parameter and stores it in entity metadata under `phase_summaries` (append-list)
- [ ] Summary schema: `{phase, timestamp, outcome, artifacts_produced, key_decisions, reviewer_feedback_summary, rework_trigger}`
- [ ] `_project_meta_json` projects `phase_summaries` to `.meta.json`
- [ ] On backward transition, `validateAndSetup` Step 1b injects prior phase summaries as merged `## Phase Context` block
- [ ] Reviewer dispatch prompts in 4 phase command files include the same block on backward transitions
- [ ] Multiple rework cycles through the same phase accumulate entries (append, not overwrite)
- [ ] Features without summaries experience zero behavior change

## Write Ownership
- `commitAndComplete` in workflow-transitions SKILL.md is the **summary author** — the LLM executing it constructs the summary dict from its Step 3 Phase Summary output. Data flow: Step 2 (complete_phase) → Step 3 (generate Phase Summary text) → **Step 3a (NEW)**: construct summary dict from Step 3 output, read existing `phase_summaries` from `.meta.json`, append new entry, call `update_entity` with the full list → Step 3b (existing Forward Re-Run Check, unchanged). Step 3a is inserted between Step 3 and the existing Step 3b.
- `_process_complete_phase` at workflow_state_server.py:661 is unchanged. Summary storage uses `update_entity` MCP, not `complete_phase`.
- `validateAndSetup` Step 1b is the **reader/injector** — reads `.meta.json`, formats summaries into prompt context

## API Changes

### Summary storage — via update_entity after completion
No change to `complete_phase` MCP signature. Instead, `commitAndComplete` Step 3b calls `update_entity` to append the summary to `phase_summaries` in entity metadata after the phase completion call succeeds. This keeps the existing `complete_phase` contract unchanged.

```python
# commitAndComplete Step 3b (new):
# After Step 3 Phase Summary output, construct dict and append:
update_entity(
    type_id=feature_type_id,
    metadata={"phase_summaries": existing_summaries + [new_summary]}
)
```

### Entity metadata — new key
```python
# METADATA_SCHEMAS['feature'] addition (metadata.py:31-45):
"phase_summaries": list  # append-list of summary entries

# Each entry:
{
    "phase": "specify",
    "timestamp": "2026-04-02T08:00:00Z",  // ISO 8601 with UTC, matching _iso_now()
    "outcome": "Specification complete (3 iterations).",
    "artifacts_produced": ["spec.md"],
    "key_decisions": "Free-text paragraph of key choices made.",
    "reviewer_feedback_summary": "Brief summary of reviewer feedback.",
    "rework_trigger": null  # or "design reviewer flagged AC-3 gap"
}
```

### .meta.json — new field
```json
{
  "phase_summaries": [
    {"phase": "specify", "timestamp": "...", "outcome": "...", ...},
    {"phase": "design", "timestamp": "...", "outcome": "...", ...}
  ]
}
```
Projected by `_project_meta_json` (workflow_state_server.py:295-385) alongside existing `phases`, `backward_context`.

## Scope

### In Scope
- Store summaries in entity metadata as append-list under `phase_summaries` key (via `update_entity` MCP, NOT a new `complete_phase` parameter)
- Project `phase_summaries` to `.meta.json` via `_project_meta_json`
- Add `phase_summaries: list` to `METADATA_SCHEMAS['feature']` in metadata.py
- Update `validateAndSetup` Step 1b to inject summaries on backward transitions
- Update `commitAndComplete` to construct and pass summary dict
- Update 4 phase command files (specify.md, design.md, create-plan.md, implement.md) to include phase summaries in reviewer dispatch prompts on backward transitions. Brainstorm command excluded — brainstorm has no reviewer dispatch prompts.
- Cap summaries at 2000 chars per entry; trim injection to last 2 per phase

### Out of Scope
- Structured DB tables for phase summaries (backlog #00051)
- Cross-feature context sharing
- Summary quality scoring or validation
- Forward-transition injection (summaries only injected on backward travel)

## Acceptance Criteria

### AC-1: commitAndComplete appends phase summary via update_entity
- Given `commitAndComplete` Step 3a constructs a summary dict after Step 3 Phase Summary output
- When it calls `update_entity` with the existing `phase_summaries` list plus the new entry
- Then entity metadata `phase_summaries` list contains the new entry appended
- And prior entries are preserved (not overwritten)
- Note: `commitAndComplete` reads existing `phase_summaries` from `.meta.json` (loaded by `validateAndSetup` Step 1 at phase start — available in the LLM's conversation context at Step 3a time), appends the new summary, then calls `update_entity` with the full list.

### AC-2: Summary storage failure does not block completion
- Given `update_entity` fails when storing the phase summary (e.g., MCP error)
- When the failure is caught
- Then phase completion is not affected (complete_phase already succeeded in Step 2)
- And a warning is logged

### AC-3: _project_meta_json projects phase_summaries
- Given entity metadata contains `phase_summaries` with 2 entries
- When `_project_meta_json` generates .meta.json
- Then .meta.json contains `"phase_summaries": [{...}, {...}]`

### AC-4: validateAndSetup injects on backward transition
- Given .meta.json contains `phase_summaries` with entries for specify and design
- When `validateAndSetup("specify")` detects backward travel (the target phase is already completed, i.e., `phase_timing[target_phase]` has a `completed` timestamp in .meta.json)
- Then a `## Phase Context` markdown block is prepended to the phase prompt, containing:
  - Backward context (existing `backward_context` field, if present) labeled "Reviewer Referral"
  - Phase summaries (last 2 per phase) labeled "Prior Phase Summaries"
- Note: injection triggers on ANY re-entry into a completed phase, regardless of whether `backward_context` exists. This covers both reviewer-initiated rework and user-initiated re-runs.
- Example rendered output:
  ```markdown
  ## Phase Context
  ### Reviewer Referral
  **Source phase:** design
  - [spec.md > AC-3] Gap in acceptance criteria — Suggestion: add edge case for empty input
  ### Prior Phase Summaries
  **specify** (2026-04-02T08:00:00Z): Specification complete (3 iterations).
    Key decisions: Chose append-list storage over keyed dict for rework history preservation.
    Artifacts: spec.md
  **design** (2026-04-02T09:00:00Z): Design complete (2 iterations).
    Key decisions: Used update_entity for summary storage, not new complete_phase parameter.
    Artifacts: design.md
  ```

### AC-5: validateAndSetup does NOT inject on forward transition
- Given .meta.json contains `phase_summaries`
- When `validateAndSetup("design")` processes a normal forward transition (specify completed, now entering design for the first time — no `completed` timestamp for design in phase_timing — the converse of AC-4's detection)
- Then no `## Phase Context` block is prepended

### AC-6: Reviewer prompts include phase context on backward transition
- Given backward travel to specify phase
- When spec-reviewer is dispatched
- Then the dispatch prompt includes `## Phase Context` section with prior summaries
- And this section appears after `## Relevant Engineering Memory` and before the review instructions

### AC-7: commitAndComplete constructs and stores summary
- Given a phase completes with 3 iterations and reviewer notes
- When `commitAndComplete` finishes (including Step 3a)
- Then entity metadata contains a new `phase_summaries` entry with all 7 schema fields present and non-empty (except `rework_trigger` which may be null)
- And the entry was stored via `update_entity` MCP call in Step 3a

### AC-8: Summary entries cap at 2000 chars
- Given `commitAndComplete` produces a summary exceeding 2000 chars when serialized
- When the summary is stored
- Then `reviewer_feedback_summary` is truncated first (to min 100 chars), then `key_decisions`, appending "..." to indicate truncation
- And the total serialized JSON entry is <=2000 chars
- If still over 2000 after truncating both text fields: truncate `artifacts_produced` by removing tail entries, then `outcome` if needed

### AC-9: Injection trims to last 2 per phase
- Given `phase_summaries` contains 4 entries for specify (4 rework cycles)
- When injection formats the `## Phase Context` block
- Then only the 2 most recent specify entries are included (by list position — append order, not timestamp)
- And all 4 entries remain in metadata (storage is not trimmed)

### AC-12: Malformed summary handled gracefully
- Given `commitAndComplete` constructs a summary that is not valid JSON or fails to serialize
- When the `update_entity` call attempts to store it
- Then the phase completion is not affected (summary storage is best-effort)
- And a warning is logged: "Phase summary storage failed: {error}"

### AC-10: Zero behavior change without summaries
- Given a feature with no `phase_summaries` in metadata (pre-existing or new)
- When `validateAndSetup` runs (forward or backward)
- Then no `## Phase Context` block is generated
- And no errors or warnings are produced

### AC-11: METADATA_SCHEMAS updated
- Given `validate_metadata` is called on a feature entity with `phase_summaries: [...]`
- When validation runs
- Then no schema-mismatch warnings are produced for the `phase_summaries` key

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** All integration points exist and are well-isolated. `_process_complete_phase` already writes structured data to metadata — adding a new field is mechanical. `_project_meta_json` already projects `backward_context` — projecting `phase_summaries` is identical pattern. `validateAndSetup` Step 1b already reads `.meta.json` and injects backward_context — adding phase_summaries to the same injection block is additive. `commitAndComplete` already produces Phase Summary text output — converting to structured dict is field mapping.

**Key Assumptions:**
- `_process_complete_phase` can accept a new parameter without breaking existing callers — Status: Verified (MCP parameters are optional with defaults)
- `commitAndComplete` has access to all summary fields at completion time — Status: Verified (SKILL.md:246-273 shows it has phase name, iterations, artifact list, reviewer notes)
- `.meta.json` projection handles arbitrary metadata keys — Status: Verified (`_project_meta_json` reads metadata dict and projects specific keys)

## Dependencies
- `workflow_state_server.py` — `_process_complete_phase` (storage), `_project_meta_json` (projection)
- `workflow-transitions/SKILL.md` — `commitAndComplete` (generation), `validateAndSetup` Step 1b (injection)
- `metadata.py` — `METADATA_SCHEMAS` (schema registration)
- 4 phase command files — `specify.md`, `design.md`, `create-plan.md`, `implement.md` (reviewer prompt injection)
