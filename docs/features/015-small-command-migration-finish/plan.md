# Plan: Small Command Migration — finish-feature, show-status, list-features

## Implementation Order

The three components have no inter-dependencies — each modifies a separate command file. However, C1 and C2 share identical algorithm text, so implementing C1 first establishes the canonical algorithm block that C2 copies.

```
Phase 1: C1 (show-status.md)     — establishes Phase Resolution algorithm
Phase 2: C2 (list-features.md)   — copies algorithm from C1, adapts anchors
Phase 3: C3 (finish-feature.md)  — independent dual-write addition
Phase 4: Verification             — manual verification across all three commands
```

**Parallelism:** Phases 1 and 3 are independent and could execute in parallel. Phase 2 depends on Phase 1 (copies algorithm text). Phase 4 depends on all three.

**Commit strategy:** All changes are on the `feature/015-small-command-migration-finish` branch. Commit once per phase after verification passes (3 commits total for Phases 1-3). Phase 4 is verification-only and produces no additional commits.

**Rollback strategy:** If any phase verification fails, revert the modified file via `git checkout -- {file}` and re-attempt from that phase's first step.

## Phase 1: show-status.md — Phase Resolution Migration (C1)

### 1.1: Read current show-status.md

**Why:** Must identify exact anchor text and replacement targets before editing. Line numbers in the design are approximate and may drift.
**Why this order:** Must read before editing — establishes the ground truth for all subsequent steps.

Read `plugins/iflow/commands/show-status.md` in full. Confirm anchor lines exist:
- After: `Display a workspace dashboard with current context, open features, and brainstorms.`
- Before: `## Section 1: Current Context`

Confirm the three phase detection lines to be replaced:
- Section 1 (~line 19): artifact-based phase detection text
- Section 1.5 (~line 32): phase annotation in feature bullet format
- Section 2 (~line 43): phase detection in Open Features

**Done when:** All anchor lines and replacement targets identified with exact text.

### 1.2: Insert Phase Resolution Algorithm block

**Why:** The algorithm block must exist before Sections 1, 1.5, and 2 can reference it.
**Why this order:** Subsequent steps (1.3-1.5) reference "the Phase Resolution algorithm above" — the block must be inserted first.

Insert the Phase Resolution algorithm block (design section "C1.1: Phase Resolution Algorithm Block") between the identified anchors. The block starts with a `## Phase Resolution Algorithm` heading, followed by:
- `<!-- SYNC: phase-resolution-algorithm -->` marker (single marker, following existing codebase convention — not paired start/end markers)
- `mcp_available` tri-state tracking
- `resolve_phase(feature_folder_name, meta_json)` function pseudocode
- Key behaviors list

**Design deviation:** Design C1.1 says markers "at start and end" but codebase convention (confirmed in finish-feature.md, wrap-up.md) is a single marker per block. Use single marker only.

Use the exact pseudocode from design.md section "C1.1: Phase Resolution Algorithm Block" (the `Algorithm (pseudocode)` code block plus the `Key behaviors` list).

**Done when:** Algorithm block inserted with `## Phase Resolution Algorithm` heading, single SYNC marker, between correct anchors. The heading creates clear structural separation from the command description above.

### 1.3: Update Section 1 phase detection reference

**Why:** Section 1 currently has inline artifact-based detection that must be replaced with a reference to the new algorithm.
**Why this order:** Algorithm block (1.2) must exist before sections can reference it.

Replace the artifact-based detection text in Section 1 (design C1.2). The replacement is within list item 2 of Section 1 — only the phrase starting from "determine current phase" through the closing parenthesis is replaced. The surrounding sentence structure ("read ... .meta.json to get feature name and ...") is preserved:
- Old: `determine current phase (first missing artifact from: spec.md, design.md, plan.md, tasks.md — or 'implement' if all exist)`
- New: `determine current phase using the Phase Resolution algorithm above`

**Done when:** Section 1 references the algorithm. No artifact-based inline detection remains. Surrounding sentence structure intact.

### 1.4: Update Section 1.5 phase annotation

**Why:** Section 1.5 lists all project features including non-active ones. The phase annotation format must change to use the algorithm for active features and display status directly for non-active.
**Why this order:** Algorithm block (1.2) must exist before this step can reference it.

Modify Section 1.5 feature listing step 2d (design C1.3). The current text to locate and replace is:

- Old (line 32): `d. List all features for that project as bullets: \`- {id}-{slug} ({status}[, phase: {phase}])\` — include ALL statuses (planned, active, completed, abandoned)`
- New: `d. List all features for that project as bullets — include ALL statuses (planned, active, completed, abandoned). For active features: \`- {id}-{slug} ({status}, phase: {resolved_phase})\` where \`{resolved_phase}\` comes from the Phase Resolution algorithm above. For non-active features (planned, completed, abandoned): \`- {id}-{slug} ({status})\` with status from \`.meta.json\` directly — omit the phase annotation.`

**Done when:** Section 1.5 step 2d distinguishes active vs non-active phase resolution with explicit old/new text replaced. Template syntax matches design C1.3.

### 1.5: Update Section 2 phase detection

**Why:** Section 2 has its own inline artifact-based detection that must be replaced.
**Why this order:** Algorithm block (1.2) must exist. Independent of 1.3/1.4 but logically follows the section ordering.

Replace Section 2 phase detection (design C1.4). Preserve the bold markdown formatting on "Phase":
- Old: `**Phase**: determined from first missing artifact (spec.md, design.md, plan.md, tasks.md) or "implement" if all exist`
- New: `**Phase**: determined using the Phase Resolution algorithm above`

**Done when:** Section 2 references the algorithm. Bold formatting on "Phase" preserved.

### 1.6: Verify show-status.md integrity

**Why:** Must confirm all edits are consistent and no regressions introduced before committing.
**Why this order:** Must run after all edits (1.2-1.5) are applied.

Read the modified file end-to-end. Confirm:
- Algorithm block is correctly placed and formatted
- All three sections reference the algorithm
- No orphaned artifact-based detection text remains
- Existing section structure, column alignment, and footer logic unchanged (FR-4)
- Feature discovery remains filesystem-based (FR-5)

If verification fails: `git checkout -- plugins/iflow/commands/show-status.md` and re-attempt from step 1.1.

**Done when:** File reads correctly with all changes applied and no regressions. Commit changes.

## Phase 2: list-features.md — Phase Resolution Migration (C2)

### 2.1: Read current list-features.md

**Why:** Must identify exact anchor text and replacement targets. list-features.md has different section structure than show-status.md.
**Why this order:** Must read before editing.

Read `plugins/iflow/commands/list-features.md` in full. Confirm anchor lines:
- After: `## Gather Features` section (after step 3)
- Before: `## For Each Feature`

Confirm the phase determination line to be replaced (~line 23).

**Done when:** Anchor lines and replacement target identified.

### 2.2: Insert Phase Resolution Algorithm block

**Why:** list-features.md needs its own copy of the algorithm for self-containment (design D1).
**Why this order:** Must be inserted before step 2.3 can reference it.

Insert the identical algorithm block from Phase 1 — same `## Phase Resolution Algorithm` heading, same single SYNC marker, same pseudocode and key behaviors — between the identified anchors (design C2.1). The `##` heading level is intentional and matches the peer headings (`## Gather Features`, `## For Each Feature`) — it logically sits between the gathering and iteration phases.

**Design deviation:** Same as step 1.2 — design C2.1 says markers "at start and end" but codebase convention is a single marker per block. Use single marker only.

**Done when:** Algorithm block inserted. Text from `## Phase Resolution Algorithm` heading through end of Key behaviors list is character-identical to C1's block.

### 2.3: Update phase determination reference

**Why:** Replace inline artifact-based detection with reference to the algorithm.
**Why this order:** Algorithm block (2.2) must exist first.

Replace the phase determination text (design C2.2):
- Old: `Current phase (from artifacts, or 'planned' if status is planned)`
- New: `Current phase (using the Phase Resolution algorithm above)`

**Done when:** Phase determination references the algorithm.

### 2.4: Verify list-features.md integrity and algorithm consistency

**Why:** Must confirm edits are correct and algorithm block matches the C1 copy.
**Why this order:** Must run after all edits (2.2-2.3). Algorithm consistency check requires both files to be modified.

Read the modified file. Confirm:
- Algorithm block correctly placed and formatted
- Phase determination references the algorithm
- Table format, column headers, "No active features" message preserved (FR-4)
- Feature discovery unchanged (FR-5)

**Algorithm consistency check:** Extract both algorithm blocks using `sed -n '/^## Phase Resolution Algorithm$/,/^## /p' {file} | sed '$d'` on both show-status.md and list-features.md. Diff the outputs — must be character-identical (no diff output).

If verification fails: `git checkout -- plugins/iflow/commands/list-features.md` and re-attempt from step 2.1.

**Done when:** File reads correctly, algorithm blocks match across both files. Commit changes.

## Phase 3: finish-feature.md — Dual-Write Addition (C3)

### 3.1: Read current finish-feature.md Step 6a

**Why:** Must locate exact insertion point and surrounding context. Line numbers are approximate.
**Why this order:** Must read before editing.

Read `plugins/iflow/commands/finish-feature.md` and locate Step 6a `.meta.json` update block (~lines 415-428). Confirm the JSON update structure exists.

**Done when:** Step 6a located with exact surrounding context.

### 3.2: Add complete_phase MCP call block

**Why:** This is the core FR-3 change — adding the dual-write MCP call.
**Why this order:** Insertion point must be identified (3.1) before editing.

After the existing `.meta.json` update JSON block in Step 6a, add the MCP call block (design section "C3.1: Add MCP Call Block") as a continuation within Step 6a (no new sub-heading), separated by a blank line from the JSON update block:

```
After updating .meta.json, sync workflow state to the database:
1. Construct feature_type_id as "feature:{folder_name}" where {folder_name} is the
   feature directory name (e.g., "015-small-command-migration-finish").
2. Call complete_phase(feature_type_id, "finish").
3. If the call succeeds: no additional output needed.
4. If the call fails (MCP unavailable, phase mismatch, feature not found, or
   no active phase in DB): output a warning line "Note: Workflow DB sync
   skipped — {error reason}. State will reconcile on next reconcile_apply
   run." but do NOT stop or block the completion flow. The .meta.json
   update already succeeded. All error types are handled identically.
```

Place before Step 6b (delete temporary files).

**Done when:** MCP call block added after `.meta.json` update within Step 6a (not a new sub-section), before Step 6b.

### 3.3: Verify finish-feature.md integrity

**Why:** Must confirm the MCP call is correctly placed and all other steps are untouched.
**Why this order:** Must run after the edit (3.2).

Read the modified Step 6 section. Confirm:
- `.meta.json` update unchanged
- MCP call block correctly placed after update, before Step 6b
- All failure modes enumerated (MCP unavailable, phase mismatch, feature not found, no active phase in DB)
- Warning format matches design D4
- All other steps (1-5, 6b-6d) unchanged (FR-4)

If verification fails: `git checkout -- plugins/iflow/commands/finish-feature.md` and re-attempt from step 3.1.

**Done when:** Step 6a has both `.meta.json` update and MCP call, rest of file untouched. Commit changes.

## Phase 4: Verification

### 4.1: Cross-file algorithm consistency check

**Why:** Design D1 requires identical algorithm text in both files. Must verify no drift.
**Why this order:** Runs after all implementation phases.

Extract the algorithm block from each file: from the `## Phase Resolution Algorithm` heading (inclusive) through to the next `##` heading (exclusive). Compare the extracted text — must be character-identical.

**Concrete method:** Use `sed -n '/^## Phase Resolution Algorithm$/,/^## /p' {file} | sed '$d'` on both files, then `diff` the outputs.

**Done when:** Diff produces no output, confirming identical algorithm text.

### 4.2: Acceptance criteria trace

**Why:** Must verify all 10 ACs are covered by the implementation.
**Why this order:** Runs after all implementation is complete.

Trace each AC against the implementation:

| AC | Verification |
|----|-------------|
| AC-1 | show-status Sections 1, 1.5, 2 reference Phase Resolution algorithm with `get_phase` |
| AC-2 | list-features phase determination uses Phase Resolution algorithm with `get_phase` |
| AC-3 | finish-feature Step 6a calls `complete_phase(feature_type_id, "finish")` after `.meta.json` update |
| AC-4 | Algorithm Step 3 provides artifact-based fallback when MCP fails |
| AC-5 | C3.1 block warns but does not block on `complete_phase` failure |
| AC-6 | Algorithm Step 1 returns `"planned"` for planned features without calling `get_phase` |
| AC-7 | Algorithm Step 1 returns status for completed/abandoned without calling `get_phase` |
| AC-8 | Algorithm `mcp_available = false` after first failure skips remaining features in show-status |
| AC-9 | Same circuit breaker applies in list-features |
| AC-10 | Algorithm Step 2 maps `null`/`"brainstorm"` to `"specify"` |

**Done when:** All 10 ACs traced to specific implementation locations.

### 4.3: Manual command verification

**Why:** Closes the loop with the spec Verification Strategy (spec lines 163-169).
**Why this order:** Runs after all implementation and static verification.

Per the spec Verification Strategy (also verify Claude correctly treats the algorithm block as a referenceable section rather than part of the command description — the `## Phase Resolution Algorithm` heading provides structural separation):
1. Run `/iflow:show-status` with the workflow-engine MCP server running — confirm phase output uses `get_phase` values
2. Stop the workflow-engine MCP server and re-run `/iflow:show-status` — confirm artifact-based fallback produces equivalent output
3. Run `/iflow:finish-feature` on a test feature — confirm `complete_phase` is called after `.meta.json` update
4. Run `/iflow:finish-feature` with the MCP server stopped — confirm completion succeeds with a non-blocking warning

**Done when:** All 4 manual verification steps pass.

## TDD Note

This feature modifies markdown instruction files, not executable code. There are no automated tests to write. Verification is manual per the spec Verification Strategy section.
