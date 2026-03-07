# Tasks: Small Command Migration — finish-feature, show-status, list-features

## Phase 1: show-status.md — Phase Resolution Migration (C1)

### Task 1.1: Read show-status.md and confirm anchors

- [ ] Read `plugins/iflow/commands/show-status.md` in full
- [ ] Confirm anchor lines exist: after `Display a workspace dashboard with current context, open features, and brainstorms.` (line 12) and before `## Section 1: Current Context` (line 14)
- [ ] Confirm the three phase detection lines to be replaced: Section 1 (~line 19), Section 1.5 (~line 32), Section 2 (~line 43)
- [ ] Record exact text of each replacement target for subsequent tasks

**Plan ref:** Step 1.1
**Done when:** All anchor lines and replacement targets identified with exact text.

### Task 1.2: Insert Phase Resolution Algorithm block in show-status.md

- [ ] Insert `## Phase Resolution Algorithm` heading between the confirmed anchors (after line 12, before `## Section 1`)
- [ ] Add single `<!-- SYNC: phase-resolution-algorithm -->` marker on the line immediately following the `## Phase Resolution Algorithm` heading, before the `mcp_available = null` line (codebase convention — not paired start/end)
- [ ] Insert exact pseudocode from design.md section C1.1 — the `resolve_phase(feature_folder_name, meta_json)` function with tri-state `mcp_available`, Step 1 (skip non-active), Step 2 (try MCP with fail-fast), Step 3 (artifact-based fallback with `ARTIFACT_TO_PHASE` map)
- [ ] Insert Key behaviors list from design.md section C1.1 — `mcp_available` tri-state semantics, circuit breaker (AC-8/AC-9), non-active bypass (AC-6/AC-7), race condition note

**Depends on:** Task 1.1
**Plan ref:** Step 1.2
**Done when:** Algorithm block inserted between correct anchors with heading, single SYNC marker, complete pseudocode, and key behaviors list. The heading creates structural separation from the command description above.

### Task 1.3: Update Section 1, 1.5, and 2 phase detection references

- [ ] Section 1 (line 19): Replace `determine current phase (first missing artifact from: spec.md, design.md, plan.md, tasks.md — or "implement" if all exist)` with `determine current phase using the Phase Resolution algorithm above` — preserve surrounding sentence structure
- [ ] Section 1.5 step 2d (line 32): Replace `d. List all features for that project as bullets: \`- {id}-{slug} ({status}[, phase: {phase}])\` — include ALL statuses (planned, active, completed, abandoned)` with `d. List all features for that project as bullets — include ALL statuses (planned, active, completed, abandoned). For active features: \`- {id}-{slug} ({status}, phase: {resolved_phase})\` where \`{resolved_phase}\` comes from the Phase Resolution algorithm above. For non-active features (planned, completed, abandoned): \`- {id}-{slug} ({status})\` with status from \`.meta.json\` directly — omit the phase annotation.`
- [ ] Section 2 (line 43): Replace `**Phase**: determined from first missing artifact (spec.md, design.md, plan.md, tasks.md) or "implement" if all exist` with `**Phase**: determined using the Phase Resolution algorithm above` — preserve bold markdown on "Phase"

**Depends on:** Task 1.2
**Plan ref:** Steps 1.3 + 1.4 + 1.5
**Done when:** All three sections reference the Phase Resolution algorithm. No artifact-based inline detection remains. Section 1.5 distinguishes active vs non-active features. Bold formatting preserved on Section 2 "Phase".

### Task 1.4: Verify show-status.md integrity and commit

- [ ] Read modified file end-to-end
- [ ] Confirm algorithm block is correctly placed and formatted
- [ ] Confirm all three sections reference the algorithm
- [ ] Confirm no orphaned artifact-based detection text remains
- [ ] Confirm existing section structure, column alignment, and footer logic unchanged (FR-4)
- [ ] Confirm feature discovery remains filesystem-based (FR-5)
- [ ] Commit: `git add plugins/iflow/commands/show-status.md && git commit -m "feat(015): migrate show-status phase detection to MCP"`

**Depends on:** Task 1.3
**Plan ref:** Step 1.6
**Rollback:** `git checkout -- plugins/iflow/commands/show-status.md`
**Done when:** File passes all integrity checks. Changes committed.

## Phase 2: list-features.md — Phase Resolution Migration (C2)

> **Depends on Phase 1:** Copies canonical algorithm text established in show-status.md.

### Task 2.1: Insert Phase Resolution Algorithm block in list-features.md

- [ ] Read `plugins/iflow/commands/list-features.md` in full
- [ ] Confirm anchor lines: after `## Gather Features` section (after step 3, ~line 17), before `## For Each Feature` (line 19)
- [ ] Insert identical algorithm block from show-status.md (as written by Task 1.2) — same `## Phase Resolution Algorithm` heading, same single SYNC marker, same pseudocode, same key behaviors
- [ ] The `##` heading level matches peer headings (`## Gather Features`, `## For Each Feature`)
- [ ] Verify inserted text is character-identical to show-status.md's algorithm block — run: `diff <(sed -n '/^## Phase Resolution Algorithm$/,/^## /p' plugins/iflow/commands/show-status.md | sed '$d') <(sed -n '/^## Phase Resolution Algorithm$/,/^## /p' plugins/iflow/commands/list-features.md | sed '$d')` — must produce no output

**Depends on:** Task 1.4
**Plan ref:** Steps 2.1 + 2.2
**Done when:** Algorithm block inserted between correct anchors. Text from heading through key behaviors is character-identical to show-status.md's block.

### Task 2.2: Update phase determination reference, verify, and commit

- [ ] In `## For Each Feature` section, replace `Current phase (from artifacts, or \`planned\` if status is planned)` with `Current phase (using the Phase Resolution algorithm above)`
- [ ] Read modified file end-to-end
- [ ] Confirm algorithm block correctly placed and formatted
- [ ] Confirm phase determination references the algorithm
- [ ] Confirm table format, column headers, "No active features" message preserved (FR-4)
- [ ] Confirm feature discovery unchanged (FR-5)
- [ ] Run algorithm consistency check: `diff <(sed -n '/^## Phase Resolution Algorithm$/,/^## /p' plugins/iflow/commands/show-status.md | sed '$d') <(sed -n '/^## Phase Resolution Algorithm$/,/^## /p' plugins/iflow/commands/list-features.md | sed '$d')` — diff must produce no output
- [ ] Commit: `git add plugins/iflow/commands/list-features.md && git commit -m "feat(015): migrate list-features phase detection to MCP"`

**Depends on:** Task 2.1
**Plan ref:** Steps 2.3 + 2.4
**Rollback:** `git checkout -- plugins/iflow/commands/list-features.md`
**Done when:** File passes all checks, algorithm blocks match across both files. Changes committed.

## Phase 3: finish-feature.md — Dual-Write Addition (C3)

> **Parallelism:** Phase 3 is independent of Phases 1 and 2. Can execute in parallel with Phase 1.

### Task 3.1: Add complete_phase MCP call block to finish-feature.md

- [ ] Read `plugins/iflow/commands/finish-feature.md` and locate Step 6a `.meta.json` update block (~lines 415-428)
- [ ] Confirm the JSON update structure ends at the closing `}` + code fence (line 429)
- [ ] After the `.meta.json` update JSON block, add a blank line then insert the MCP call block as a continuation within Step 6a (no new sub-heading):

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

- [ ] Ensure block is placed before Step 6b (`### Step 6b: Delete temporary files`)

**Plan ref:** Steps 3.1 + 3.2
**Done when:** MCP call block added after `.meta.json` update within Step 6a, before Step 6b. All four failure modes enumerated.

### Task 3.2: Verify finish-feature.md integrity and commit

- [ ] Read Step 6 section of modified file
- [ ] Confirm `.meta.json` update JSON block unchanged
- [ ] Confirm MCP call block correctly placed after update, before Step 6b
- [ ] Confirm all failure modes enumerated: MCP unavailable, phase mismatch, feature not found, no active phase in DB
- [ ] Confirm warning format matches design D4: `"Note: Workflow DB sync skipped — {error reason}"`
- [ ] Confirm all other steps (1-5, 6b-6d) unchanged (FR-4)
- [ ] Commit: `git add plugins/iflow/commands/finish-feature.md && git commit -m "feat(015): add complete_phase dual-write to finish-feature"`

**Why:** Ensures the MCP call block is correctly placed and no existing steps were disturbed before committing.
**Depends on:** Task 3.1
**Plan ref:** Step 3.3
**Rollback:** `git checkout -- plugins/iflow/commands/finish-feature.md`
**Done when:** Step 6a has both `.meta.json` update and MCP call block, rest of file untouched. Changes committed.

## Phase 4: Verification

> **Depends on:** Tasks 1.4, 2.2, 3.2 (all implementation phases complete)

### Task 4.1: Cross-file algorithm consistency check and acceptance criteria trace

- [ ] Extract algorithm blocks from both files: `sed -n '/^## Phase Resolution Algorithm$/,/^## /p' plugins/iflow/commands/show-status.md | sed '$d'` and same for list-features.md
- [ ] Diff outputs — must produce no output (character-identical)
- [ ] Verify structural ACs via grep: `grep -c "Phase Resolution algorithm above" plugins/iflow/commands/show-status.md` must return 3 (AC-1); same on list-features.md must return 1 (AC-2); `grep -c "complete_phase" plugins/iflow/commands/finish-feature.md` must return >= 1 (AC-3)
- [ ] Trace all 10 ACs to specific implementation locations (ACs 4-10 verified by reading algorithm block internals already confirmed in Tasks 1.2/2.1):

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

**Depends on:** Tasks 1.4, 2.2, 3.2
**Plan ref:** Steps 4.1 + 4.2
**Done when:** Algorithm blocks match across files. All 10 ACs traced to specific implementation locations.

### Task 4.2: Manual command verification

- [ ] Run `/iflow:show-status` with the workflow-engine MCP server running — confirm phase output uses `get_phase` values
- [ ] Stop the workflow-engine MCP server (remove from active MCP session via `/mcp` or kill process: `pkill -f workflow_state_server`; confirm unavailable by checking tool list) and re-run `/iflow:show-status` — confirm artifact-based fallback produces equivalent output
- [ ] Run `/iflow:finish-feature` on a test feature (use any feature in active status via `/iflow:list-features`, or a scratch feature) — confirm `complete_phase` appears in the tool call history in the Claude session sidebar after `.meta.json` update
- [ ] Run `/iflow:finish-feature` with the MCP server stopped — confirm completion succeeds with a non-blocking warning ("Note: Workflow DB sync skipped")
- [ ] Confirm algorithm block is referenced by name in show-status.md: `grep -c "Phase Resolution algorithm above" plugins/iflow/commands/show-status.md` must return 3 (Sections 1, 1.5, 2). Same grep on list-features.md must return 1

**Depends on:** Task 4.1
**Plan ref:** Step 4.3
**Done when:** All 4 manual verification steps pass.

## Summary

| Phase | Tasks | Files Modified |
|-------|-------|---------------|
| Phase 1 (C1) | 1.1, 1.2, 1.3, 1.4 | `plugins/iflow/commands/show-status.md` |
| Phase 2 (C2) | 2.1, 2.2 | `plugins/iflow/commands/list-features.md` |
| Phase 3 (C3) | 3.1, 3.2 | `plugins/iflow/commands/finish-feature.md` |
| Phase 4 | 4.1, 4.2 | None (verification only) |

**Total:** 10 tasks across 4 phases, 2 parallel groups (Phases 1+3 parallel).

**TDD Note:** This feature modifies markdown instruction files, not executable code. No automated tests. Verification is manual per spec Verification Strategy.
