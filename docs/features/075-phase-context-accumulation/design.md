# Design: Phase Context Accumulation

**Feature:** 075-phase-context-accumulation
**Spec:** spec.md (source of truth)
**Created:** 2026-04-02

## Prior Art Research

| Question | Source | Finding |
|----------|--------|---------|
| Does commitAndComplete already produce summaries? | SKILL.md:246-273 | Yes. Step 3 outputs a plain-text Phase Summary (outcome, artifacts, feedback) to stdout but never persists it. The content is ephemeral. |
| Does validateAndSetup inject backward context? | SKILL.md:71-95 | Yes. Step 1b reads `backward_context` from .meta.json and prepends a `## Backward Travel Context` markdown block. Cleared after phase completes (line 95). |
| Does _process_complete_phase store timing metadata? | workflow_state_server.py:716-724 | Yes. Writes `phase_timing[phase].completed`, `iterations`, `reviewerNotes` to entity metadata, then calls `db.update_entity()`. |
| Does _project_meta_json project backward_context? | workflow_state_server.py:383-388 | Yes. Projects `backward_context` and `backward_return_target` from entity metadata to .meta.json. Same pattern is reusable for `phase_summaries`. |
| How does entity metadata handle new keys? | metadata.py:31-45 | `METADATA_SCHEMAS['feature']` lists expected keys. New keys produce validation warnings unless registered. Adding `phase_summaries: list` is sufficient. |
| Context folding in LLM workflows? | arxiv 2510.11967 (Context-Folding) | Fold intermediate reasoning steps into compressed summaries. Retain the summary, discard the steps. Directly applicable: each phase's full output is folded into a 7-field summary dict. |
| LLM positional bias for injected context? | LLM primacy/recency research | Critical context should appear early or late in prompts, not buried in the middle. Supports placing `## Phase Context` block before review instructions (high-salience position). |
| Saga pattern for LLM workflows? | SagaLLM (VLDB 2025) | Per-step audit trail with compensating actions. Each step stores its outcome for downstream recovery. Analogous to our append-list: each phase completion stores a summary entry for downstream rework phases. |

## Architecture Overview

```
                         commitAndComplete flow
                         ======================

  Step 2                  Step 3                    Step 3a (NEW)             Step 3b
  complete_phase -------> Phase Summary text -----> Construct summary ------> Forward Re-Run
  MCP call                (plain-text output,       dict from Step 3          Check (existing,
  (updates DB,            max 12 lines)             output; read existing     unchanged)
   projects .meta.json)                             phase_summaries from
                                                    .meta.json; append;
                                                    call update_entity
                                                    (best-effort)

                         Storage & Projection
                         ====================

  update_entity --------> Entity metadata ---------> _project_meta_json -----> .meta.json
  MCP call                (phase_summaries:          (reads phase_summaries    (phase_summaries
  (appends to             [{...}, {...}])            from metadata, writes     field visible to
   phase_summaries                                   to .meta.json)            validateAndSetup)
   list)

                         Injection flow
                         ==============

  .meta.json -----------> validateAndSetup ---------> ## Phase Context -------> Phase skill
  (phase_summaries,       Step 1b (enhanced)          markdown block            prompt context
   backward_context,      (detects backward           (backward_context +
   phase_timing)          transition via               last 2 summaries
                          phase_timing[target]         per phase)
                          .completed exists)

  .meta.json -----------> Reviewer dispatch --------> ## Phase Context -------> Reviewer agent
  (same data)             prompts in 4 command         (same format)            prompt context
                          files (specify.md,
                          design.md, create-plan.md,
                          implement.md)
```

## Components

### C1: Summary Generation (commitAndComplete Step 3a -- NEW)

**Location:** `plugins/pd/skills/workflow-transitions/SKILL.md`, inserted between existing Step 3 and Step 3b.

**Responsibility:** After Step 3 outputs the plain-text Phase Summary, Step 3a constructs a structured summary dict from that output and persists it via `update_entity`.

**Inputs available at Step 3a time:**
- `phaseName` parameter (from commitAndComplete call)
- Step 3 output text (outcome, artifacts list, reviewer feedback)
- `artifacts[]` parameter (file paths)
- `iterations` parameter
- `reviewerNotes[]` parameter
- `.meta.json` content (loaded by validateAndSetup Step 1 at phase start, available in conversation context)

### C2: Summary Storage (update_entity MCP)

**Location:** Called from Step 3a in SKILL.md. No changes to `_process_complete_phase` in workflow_state_server.py.

**Responsibility:** Append the new summary entry to the existing `phase_summaries` list in entity metadata. Uses `update_entity` MCP (not `complete_phase`) to avoid API signature changes.

**Why update_entity, not complete_phase:** The spec explicitly states `_process_complete_phase` is unchanged (spec.md:19). Summary storage is a separate concern from phase completion. `complete_phase` already succeeded in Step 2 before Step 3a runs. Using `update_entity` keeps the operations decoupled -- summary failure cannot affect completion.

### C3: Summary Projection (_project_meta_json)

**Location:** `plugins/pd/mcp/workflow_state_server.py`, within `_project_meta_json()` (lines 295-395).

**Responsibility:** Project `phase_summaries` from entity metadata to `.meta.json`, following the same pattern as `backward_context` projection (lines 383-388).

### C4: Summary Injection (validateAndSetup Step 1b enhancement)

**Location:** `plugins/pd/skills/workflow-transitions/SKILL.md`, Step 1b.

**Responsibility:** On backward transitions (re-entry into a completed phase), read `phase_summaries` and `backward_context` from `.meta.json` and format a unified `## Phase Context` markdown block prepended to the phase prompt.

**Backward transition detection:** Check if `phase_timing[target_phase].completed` exists in `.meta.json` (loaded in Step 1). If it does, the target phase was previously completed, and this is a backward (re-entry) transition.

### C5: Reviewer Prompt Injection (4 command files)

**Location:** `plugins/pd/commands/specify.md`, `design.md`, `create-plan.md`, `implement.md`.

**Responsibility:** On backward transitions, add a `## Phase Context` section to reviewer dispatch prompts. The section appears after `## Relevant Engineering Memory` and before the review instructions or `Return JSON` block.

### C6: Schema Registration (metadata.py)

**Location:** `plugins/pd/hooks/lib/entity_registry/metadata.py`, line 31-45 within `METADATA_SCHEMAS`.

**Responsibility:** Add `"phase_summaries": list` to `METADATA_SCHEMAS['feature']` to prevent schema-mismatch warnings from `validate_metadata`.

## Interfaces

### I1: Summary Dict Schema

Each entry in the `phase_summaries` list conforms to this schema:

```python
{
    "phase": str,                        # Phase name (e.g., "specify", "design")
    "timestamp": str,                    # ISO 8601 UTC (e.g., "2026-04-02T08:00:00Z"), matching _iso_now() format
    "outcome": str,                      # From Step 3 outcome decision table (e.g., "Approved after 3 iterations.")
    "artifacts_produced": list[str],     # Filenames only (e.g., ["spec.md"]), from artifacts[] parameter
    "key_decisions": str,                # Free-text paragraph of key choices made during the phase
    "reviewer_feedback_summary": str,    # Brief summary of reviewer feedback across all iterations
    "rework_trigger": str | None         # Why rework was triggered, or null if first completion
}
```

**Constraints:**
- Total serialized JSON per entry: max 2000 chars (AC-8)
- Truncation order when over 2000 chars: `reviewer_feedback_summary` first (min 100 chars), then `key_decisions` (min 100 chars), appending "..." to truncated fields. If still over: truncate `artifacts_produced` (remove tail entries), then `outcome`.

### I2: Step 3a Procedure (Pseudocode)

```
STEP 3a: Store Phase Summary (best-effort)

1. Construct summary_dict from Step 3 output:
   summary_dict = {
     "phase": phaseName,
     "timestamp": current UTC ISO 8601 timestamp,
     "outcome": outcome string from Step 3 decision table,
     "artifacts_produced": [basename(f) for f in artifacts[]],
     "key_decisions": <free-text paragraph summarizing key choices made during this phase>,
     "reviewer_feedback_summary": <brief summary of reviewer feedback across iterations>,
     "rework_trigger": <if backward_context existed at phase start, summarize it; else null>
   }

2. Apply 2000-char cap:
   Keep each text field under 300 chars. If the total serialized JSON exceeds 2000 chars,
   truncate reviewer_feedback_summary and key_decisions further, appending "...".
   The precise 4-level cascade is simplified for reliable LLM execution.

3. Read existing phase_summaries from .meta.json:
   existing = .meta.json.phase_summaries or []

4. Append new entry:
   updated = existing + [summary_dict]

5. Call update_entity:
   update_entity(
     type_id = feature_type_id,
     metadata = {"phase_summaries": updated}
   )
   Pass ONLY {"phase_summaries": updated_list} as the metadata parameter. Do NOT
   include other metadata fields — update_entity performs a shallow merge and
   preserves all other keys automatically.

6. Error handling:
   If update_entity fails (MCP error, timeout, invalid response):
     Log warning: "Phase summary storage failed: {error}"
     Do NOT block -- proceed to Step 3b regardless.
     Phase completion already succeeded in Step 2.
```

**Note on reading existing summaries:** At Step 3a time, the LLM has `.meta.json` content in its conversation context (loaded by validateAndSetup Step 1 at phase start). After Step 2 (`complete_phase`), `.meta.json` is re-projected by `_project_meta_json` and will include any existing `phase_summaries`. The LLM reads the `phase_summaries` array from its knowledge of the .meta.json contents.

### I3: _project_meta_json phase_summaries Projection

Add to `_project_meta_json()` in `workflow_state_server.py`, following the pattern at lines 383-388:

```python
# Phase summaries (feature 075)
if metadata.get("phase_summaries"):
    meta["phase_summaries"] = metadata["phase_summaries"]
```

**Placement:** After the backward travel fields block (line 388) and before the atomic write (line 391).

**Behavior:** If `phase_summaries` is absent or empty in entity metadata, the key is omitted from `.meta.json` (same pattern as `backward_context`).

### I4: Backward Transition Detection

Detection logic for both C4 (validateAndSetup) and C5 (reviewer prompts):

```
is_backward_transition(phaseName, meta_json):
  phase_timing = meta_json.get("phases", {})
  target_phase_timing = phase_timing.get(phaseName, {})
  return "completed" in target_phase_timing
```

**Rationale:** If `phase_timing[target_phase]` has a `completed` timestamp, that phase was previously completed. Re-entering it is a backward transition (or a re-run of an already-completed phase). This covers both reviewer-initiated backward travel (`backward_to`) and user-initiated re-runs.

**Note:** .meta.json projects phase_timing as 'phases' (see `_project_meta_json` line 377). Detection reads from .meta.json, hence uses the 'phases' key.

**Note:** This detection is independent of `backward_context` presence. A phase can be re-entered without `backward_context` (e.g., user manually runs `/pd:specify` on a feature that already completed specify). The injection still triggers because the phase was previously completed (AC-4 note).

### I5: Phase Context Injection Format (validateAndSetup Step 1b)

When `is_backward_transition` returns true AND `phase_summaries` exists with entries:

```markdown
## Phase Context
### Reviewer Referral
**Source:** {backward_context.source_phase} reviewer
**Findings:**
{for each finding in backward_context.findings:
  - [{finding.artifact}] {finding.section}: {finding.issue}
    Suggestion: {finding.suggestion}}
**Downstream Impact:** {backward_context.downstream_impact}

### Prior Phase Summaries
**{phase}** ({timestamp}): {outcome}
  Key decisions: {key_decisions}
  Artifacts: {comma-separated artifacts_produced}

**{phase}** ({timestamp}): {outcome}
  Key decisions: {key_decisions}
  Artifacts: {comma-separated artifacts_produced}
```

**Conditional sections:**
- `### Reviewer Referral` section: only present when `backward_context` exists in .meta.json. This replaces the current standalone `## Backward Travel Context` block in Step 1b.
- `### Prior Phase Summaries` section: only present when `phase_summaries` has entries.
- If both are absent: no `## Phase Context` block at all.
- If only one is present: `## Phase Context` heading still used, with only the relevant sub-section.

**Trimming (AC-9):** For each phase name in `phase_summaries`, include only the last 2 entries (by list position -- append order). All entries remain in metadata storage; trimming is display-only.

**Trimming implementation:**
```
trimmed_summaries = {}
for entry in phase_summaries:
  phase = entry["phase"]
  trimmed_summaries.setdefault(phase, [])
  trimmed_summaries[phase].append(entry)

for phase in trimmed_summaries:
  trimmed_summaries[phase] = trimmed_summaries[phase][-2:]  # last 2 per phase

# Flatten back to list for rendering, preserving phase grouping
```

**Summary line format per entry:**
```
**{phase}** ({timestamp}): {outcome}
  Key decisions: {key_decisions}
  Artifacts: {comma-separated artifacts_produced}
  Rework trigger: {rework_trigger}  ← only if non-null
```

The `reviewer_feedback_summary` field is omitted from injection to save tokens (it is preserved in storage for audit). The `rework_trigger` field is included when non-null as it is typically one sentence and provides critical rework provenance.

### I6: Reviewer Prompt Injection Format (4 command files)

Same `## Phase Context` block as I5, inserted into reviewer dispatch prompts.

**Placement in each dispatch prompt:**
- After `## Relevant Engineering Memory` section
- Before the `Return JSON` / review instructions block

**Conditional:** Only injected when `is_backward_transition(phaseName, meta_json)` is true. On forward transitions, the section is omitted entirely.

**Construction:** The command file reads `.meta.json` (already loaded by validateAndSetup Step 1) and formats the block using the same logic as I5.

**Concrete template text for command file injection (example for specify.md spec-reviewer dispatch):**

```
**Phase Context injection (backward transitions only):**
If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
1. Read `backward_context` and `phase_summaries` from .meta.json
2. Construct `## Phase Context` block per I5 format
3. Include this block in the reviewer dispatch prompt after `## Relevant Engineering Memory`

If no `completed` timestamp for current phase: skip injection entirely.
```

All reviewer dispatch templates in the 4 command files use this same instruction pattern, substituting the relevant phase name.

**Note:** The dispatch count per file is based on reviewer-specific dispatches only. Non-reviewer dispatches (e.g., implementer, test-deepener) do not receive phase context injection.

**Affected dispatch templates:**

| Command File | Reviewer(s) | Lines (approx) |
|---|---|---|
| specify.md | spec-reviewer (line 80), phase-reviewer (line 235) | After `## Relevant Engineering Memory` |
| design.md | design-reviewer (line 276), phase-reviewer (line 472) | After `## Relevant Engineering Memory` |
| create-plan.md | plan-reviewer (line 81), task-reviewer (line 226), combined-reviewer (line 377) | After `## Relevant Engineering Memory` |
| implement.md | relevance-verifier (line 515), code-reviewer (line 681), integration-reviewer (line 845) | After `## Relevant Engineering Memory` |

## Technical Decisions

### TD-1: Append-list storage, not keyed dict

**Decision:** Store `phase_summaries` as `list[dict]`, not `dict[phase_name, dict]`.

**Rationale:** A keyed dict (`{"specify": {...}, "design": {...}}`) would overwrite prior entries when a phase is re-completed during rework. The append-list preserves the full rework history -- the second time specify completes, the list has two specify entries. This history is the primary value of the feature (spec.md:14, FR-2).

### TD-2: update_entity for storage, not new complete_phase parameter

**Decision:** Use `update_entity` MCP after `complete_phase` succeeds, not a new `phase_summary` parameter on `complete_phase`.

**Rationale:** Keeps `_process_complete_phase` unchanged (spec.md:19). Decouples summary storage from phase completion -- summary failure cannot affect completion. The `update_entity` path is already proven for metadata updates (e.g., `backward_context` storage in handleReviewerResponse, SKILL.md:303-309).

### TD-3: Step 3a between Step 3 and existing Step 3b

**Decision:** Insert the new step between the existing Step 3 (Phase Summary output) and Step 3b (Forward Re-Run Check).

**Rationale:** Step 3 produces the content that Step 3a structures and stores. Step 3b may trigger forward re-runs which need the summary already stored. No reordering of existing steps required (spec.md:18).

### TD-4: Injection on ANY re-entry into completed phase

**Decision:** Trigger injection whenever `phase_timing[target_phase].completed` exists, regardless of `backward_context` presence.

**Rationale:** Covers both reviewer-initiated rework (which sets `backward_context`) and user-initiated re-runs (which don't). Both cases benefit from prior phase summaries (AC-4 note, spec.md:107).

### TD-5: Last 2 entries per phase for injection trimming

**Decision:** Trim injection display to the last 2 entries per phase. All entries remain in storage.

**Rationale:** Balances context richness with token cost. With 4+ rework cycles through one phase, injecting all summaries would consume excessive context window. The 2 most recent entries show the latest evolution without repeating stale context (AC-9, spec.md:73).

### TD-6: Truncation order for 2000-char cap

**Decision:** When a summary entry exceeds 2000 chars serialized, truncate fields in order: `reviewer_feedback_summary` -> `key_decisions` -> `artifacts_produced` -> `outcome`.

**Rationale:** `reviewer_feedback_summary` is the most verbose and lowest-priority field (reviewer feedback is already captured in `phase_timing.reviewerNotes`). `outcome` is the most critical single-line field. Truncation appends "..." to indicate loss (AC-8, spec.md:143-146).

### TD-7: Unified ## Phase Context block replaces standalone ## Backward Travel Context

**Decision:** Replace the current standalone `## Backward Travel Context` block (SKILL.md:78-91) with a unified `## Phase Context` block that has two sub-sections: `### Reviewer Referral` (the existing backward_context content) and `### Prior Phase Summaries`.

**Rationale:** Avoids two overlapping context blocks at the same injection point. A single `## Phase Context` heading with clear sub-sections provides provenance without confusion (PRD strategic analysis recommendation, prd.md:209).

**Note:** The existing backward_context clearing behavior (Step 1b item 4: clear backward_context via update_entity after phase completion) is unchanged. Only the injection format (items 1-2) is modified.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| update_entity fails after complete_phase succeeds | Low | Low | Best-effort: warn and proceed (AC-2). Phase completion unaffected. |
| Summary content is boilerplate/low quality | Medium | Medium | Schema enforces 7 specific fields. LLM constructs from concrete phase output (artifacts, iterations, reviewer notes). Quality matches commitAndComplete Step 3 output quality. |
| Metadata bloat from many rework cycles | Low | Low | 2000-char cap per entry. Injection trims to last 2 per phase. Storage is unbounded but each entry is small. |
| Backward transition detection false positive (user re-runs completed phase intentionally) | Low | Low | Injection is informational, not blocking. Having prior context available is helpful even for intentional re-runs. |
| ## Phase Context block consumes too many prompt tokens | Medium | Medium | Injection trims to last 2 per phase. `reviewer_feedback_summary` and `rework_trigger` omitted from injection format. Total injection typically under 500 tokens. |
| Race condition: .meta.json read in Step 3a sees stale data | Low | Low | After Step 2, `_project_meta_json` writes updated .meta.json (workflow_state_server.py:751). Step 3a reads from LLM conversation context (loaded at phase start). Worst case: existing_summaries is one projection behind, but the append still succeeds. |
| Concurrent phase_summaries modification | N/A | N/A | Not possible in normal workflow — only one phase runs per feature at a time. Reconciliation does not touch phase_summaries. The stale-read risk is theoretical only. |
| Reviewer prompt template changes break resumed dispatch delta sizing | Low | Medium | The `## Phase Context` section is added to fresh dispatch templates only. Resumed dispatches use deltas of artifact changes, not template changes. Template additions only affect `iteration1_prompt_length` baseline. |

## Dependencies

### Files to Modify

| File | Component | Change |
|------|-----------|--------|
| `plugins/pd/skills/workflow-transitions/SKILL.md` | C1, C4 | Add Step 3a (summary construction + storage). Enhance Step 1b (unified `## Phase Context` injection, backward transition detection). |
| `plugins/pd/mcp/workflow_state_server.py` | C3 | Add `phase_summaries` projection in `_project_meta_json()` (~3 lines, after line 388). |
| `plugins/pd/hooks/lib/entity_registry/metadata.py` | C6 | Add `"phase_summaries": list` to `METADATA_SCHEMAS['feature']` (line 44). |
| `plugins/pd/commands/specify.md` | C5 | Add `## Phase Context` section to spec-reviewer and phase-reviewer dispatch prompts. |
| `plugins/pd/commands/design.md` | C5 | Add `## Phase Context` section to design-reviewer and phase-reviewer dispatch prompts. |
| `plugins/pd/commands/create-plan.md` | C5 | Add `## Phase Context` section to plan-reviewer, task-reviewer, and combined-reviewer dispatch prompts. |
| `plugins/pd/commands/implement.md` | C5 | Add `## Phase Context` section to relevance-verifier, code-reviewer, and integration-reviewer dispatch prompts. |

### Files Read-Only (no changes)

| File | Reason |
|------|--------|
| `plugins/pd/mcp/workflow_state_server.py` (_process_complete_phase) | Unchanged per spec.md:19. Summary storage uses `update_entity` path, not `complete_phase`. |
| `plugins/pd/hooks/lib/entity_registry/database.py` | `update_entity` already supports arbitrary metadata dict merging. No schema changes needed. |

### Existing MCP Tools Used (no changes)

| Tool | Usage |
|------|-------|
| `update_entity` | Called from Step 3a to append summary to `phase_summaries` in entity metadata. |
| `complete_phase` | Called from Step 2 (unchanged). |
| `transition_phase` | Called from Step 4 (unchanged). |
