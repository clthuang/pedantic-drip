# Design: Small Command Migration — finish-feature, show-status, list-features

## Prior Art Research

### Codebase Patterns
- **Existing MCP call syntax:** Direct named-parameter invocation used throughout (e.g., `get_lineage(type_id=...)`, `register_entity(entity_type=...)`). No wrapper boilerplate — Claude invokes MCP tools natively.
- **Existing MCP fallback pattern:** `create-feature.md` wraps MCP calls with: "if any MCP call fails, warn but do NOT block." Same pattern needed for `complete_phase`.
- **Existing MCP error detection:** `show-lineage.md` checks for `error` field in response. `create-feature.md` uses non-blocking warn pattern.
- **workflow-transitions SKILL.md:** Uses pure `.meta.json` inspection for transition validation — no MCP calls. Explicitly out of scope (feature 016).

### External Patterns
- **Dual-write → Transactional Outbox:** Primary write (`.meta.json`) always succeeds; secondary write (`complete_phase` MCP) is best-effort with reconciliation backup. Matches FR-3 dual-write rationale.
- **Circuit breaker for batched calls:** First failure → skip remaining calls in batch. Matches AC-8/AC-9 batching short-circuit.
- **Hard-to-soft dependency transformation (AWS Well-Architected):** MCP tools are soft dependencies — failure degrades to artifact-based detection but does not block the command.

## Dependencies

**Runtime:** Workflow-engine MCP server (feature 009) must be registered in the Claude session for MCP paths to activate. No new servers, tools, or packages are required (NFR-1).

## Architecture Overview

This migration modifies three markdown command files. Since these are Claude instruction files (not executable code), the "architecture" is the structure of instruction changes within each file.

### Change Strategy

All three commands follow the same pattern: **wrap existing behavior as fallback, add MCP-primary path**.

```
Before: artifact-based detection (inline)
After:  MCP call → success? use result : artifact-based fallback
```

No shared code or abstractions are introduced — each command file is self-contained. The phase resolution algorithm is described inline in each command that needs it (show-status.md, list-features.md). This avoids cross-file dependencies between command files and keeps each command independently understandable.

### Component Map

| Component | File | Change Type | Spec Ref |
|-----------|------|-------------|----------|
| C1: show-status phase resolution | `plugins/iflow/commands/show-status.md` | Replace inline phase detection | FR-1, FR-4, FR-5 |
| C2: list-features phase resolution | `plugins/iflow/commands/list-features.md` | Replace inline phase detection | FR-2, FR-4, FR-5 |
| C3: finish-feature dual-write | `plugins/iflow/commands/finish-feature.md` | Add MCP call after `.meta.json` update | FR-3, FR-4 |

## Components

### C1: show-status.md — Phase Resolution Migration

**Current state:** Phase determined by artifact presence check (line 19, line 32, line 43).

**Target state:** Add a "Phase Resolution" subsection before Section 1, describing the shared algorithm used across Sections 1, 1.5, and 2. Then modify each section's phase reference to use the algorithm.

#### C1.1: Phase Resolution Algorithm Block

Insert a new subsection after the line `Display a workspace dashboard with current context, open features, and brainstorms.` and before the line `## Section 1: Current Context`. This block defines the algorithm once; sections reference it. Mark with `<!-- SYNC: phase-resolution-algorithm -->` at start and end.

**Algorithm (pseudocode):**
```
mcp_available = null  # tri-state: null (untested), true, false

function resolve_phase(feature_folder_name, meta_json):
    # Step 1: Skip non-active features
    if meta_json.status in ("completed", "abandoned", "planned"):
        return meta_json.status

    # Step 2: Try MCP (with fail-fast)
    if mcp_available != false:
        result = call get_phase(feature_type_id="feature:{feature_folder_name}")
        if result does not contain "error": true:
            mcp_available = true
            phase = result.current_phase
            if phase is null or phase == "brainstorm":
                return "specify"
            # MCP path returns "finish" accurately; fallback cannot (shows "implement" instead)
            return phase
        else:
            mcp_available = false  # skip MCP for all remaining features

    # Step 3: Artifact-based fallback
    ARTIFACT_TO_PHASE = {
        "spec.md": "specify",
        "design.md": "design",
        "plan.md": "create-plan",
        "tasks.md": "create-tasks"
    }
    for artifact, phase in ARTIFACT_TO_PHASE.items():
        if artifact missing in feature directory:
            return phase
    return "implement"
```

**Key behaviors:**
- `mcp_available` starts as `null` (unknown), becomes `true` on first success, `false` on first failure
- Once `false`, all subsequent features in the same invocation use artifact-based fallback (AC-8, AC-9)
- Non-active features bypass MCP entirely — their `.meta.json` status is the display value (AC-6, AC-7)
- The Step 1 filter and Step 2 MCP call use the same in-memory `.meta.json` data read at invocation start, so no race condition exists between status check and MCP call

#### C1.2: Section 1 (Current Context) Change

Replace: "determine current phase (first missing artifact from: spec.md, design.md, plan.md, tasks.md — or 'implement' if all exist)"

With: "determine current phase using the Phase Resolution algorithm above"

#### C1.3: Section 1.5 (Project Features) Change

Current line 32: `- {id}-{slug} ({status}[, phase: {phase}])` — where phase is implicitly artifact-based.

Change: Phase annotation uses the Phase Resolution algorithm. For non-active features (planned, completed, abandoned), the status is displayed directly without a phase annotation. For active features, phase is resolved via the algorithm.

#### C1.4: Section 2 (Open Features) Change

Current line 43: "Phase: determined from first missing artifact..."

Change: "Phase: determined using the Phase Resolution algorithm above"

### C2: list-features.md — Phase Resolution Migration

**Current state:** Phase determined from "artifacts and metadata" (line 17-22).

**Target state:** Add the same Phase Resolution algorithm (identical to C1.1) and modify the phase determination step.

#### C2.1: Phase Resolution Algorithm Block

Insert the same algorithm block as C1.1 after the line `## Gather Features` section (after step 3) and before the line `## For Each Feature`. The algorithm is identical — duplicated for self-containment (each command file must be independently interpretable). Both copies are marked with `<!-- SYNC: phase-resolution-algorithm -->` at start and end to enable drift detection via text comparison (follows existing `<!-- SYNC: ... -->` convention in finish-feature.md).

#### C2.2: Phase Determination Change

Replace line 23: "Current phase (from artifacts, or `planned` if status is planned)"

With: "Current phase (using the Phase Resolution algorithm above)"

### C3: finish-feature.md — Dual-Write Addition

**Current state:** Step 6a updates `.meta.json` only (lines 415-428).

**Target state:** Step 6a keeps the `.meta.json` update unchanged, adds a `complete_phase` MCP call after it.

#### C3.1: Add MCP Call Block

After the existing `.meta.json` update JSON block in Step 6a, add:

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

**Placement rationale:** After `.meta.json` update, before Step 6b (delete temporary files). The `.meta.json` is the source of truth; the MCP call is best-effort synchronization.

**Commit timing note:** Step 6 runs after Step 5 (either Merge & Release or Create PR). The `.meta.json` update and MCP call execute on whichever branch is current at that point — base branch after merge, feature branch after PR creation. The commit timing for Step 6 changes is inherited from the existing finish-feature.md structure and is not modified by this design.

## Technical Decisions

### D1: Inline algorithm vs. shared reference

**Decision:** Duplicate the Phase Resolution algorithm in both show-status.md and list-features.md.

**Rationale:** Command files are independent Claude instruction documents. Cross-referencing between commands (e.g., "see show-status.md for algorithm") creates fragile coupling — if one file is loaded without the other, the instructions are incomplete. Duplication is the lesser evil for ~15 lines of pseudocode.

**Trade-off:** Algorithm changes must be applied to both files. Mitigated by `<!-- SYNC: phase-resolution-algorithm -->` markers in both files for drift detection. Acceptable given the algorithm is stable (derived from spec) and feature 016 will eventually consolidate.

### D2: Tri-state MCP availability tracking

**Decision:** Use a tri-state (`null`/`true`/`false`) rather than binary for `mcp_available`.

**Rationale:** `null` (untested) triggers the first MCP call to probe availability. `true` (confirmed working) allows subsequent calls. `false` (confirmed broken) skips all subsequent calls. Binary would require either always probing (wasteful) or pre-probing before the command starts (adds latency).

### D3: No retry logic for get_phase

**Decision:** Single attempt per feature, fail-fast on first error for the batch.

**Rationale:** `get_phase` is a read operation where the fallback (artifact-based detection) is functionally equivalent in most cases. Retrying adds latency for a marginal benefit. The circuit breaker (fail-fast after first error) is more valuable than per-call retries.

### D4: Warning format for complete_phase failure

**Decision:** Use `"Note: Workflow DB sync skipped — {reason}"` format.

**Rationale:** Non-blocking, informational. The word "Note" signals it's not an error requiring action. The reconciliation hint ("reconcile on next reconcile_apply run") tells the user the state will converge.

## Risks

### R1: Algorithm duplication drift

**Risk:** Phase Resolution algorithm diverges between show-status.md and list-features.md during future edits.
**Mitigation:** Feature 016 migrates the remaining commands and may consolidate the algorithm into a shared skill. Until then, both files have identical algorithm text — easy to verify via diff.
**Severity:** Low — the algorithm is spec-derived and stable.

### R2: MCP tool name changes

**Risk:** If `get_phase` or `complete_phase` tool names change in the workflow-engine MCP server, command files silently break (Claude would see the tool as unavailable and fall back).
**Mitigation:** Fallback ensures graceful degradation. Tool names are part of the MCP server's public API (feature 009) and are stable.
**Severity:** Low.

### R3: Incorrect feature_type_id construction

**Risk:** If `feature_type_id` format drifts from entity registry convention, `get_phase` returns errors for valid features.
**Mitigation:** Format `"feature:{folder_name}"` is spec-defined and matches `create-feature.md`'s entity registration. The folder name is the canonical identifier.
**Severity:** Low.

## Interfaces

### I1: get_phase MCP Tool Call

**Caller:** show-status.md (Sections 1, 1.5, 2), list-features.md
**Tool:** `get_phase` (from workflow-engine MCP server)
**Input:** `feature_type_id: str` — format `"feature:{folder_name}"`
**Output (success):**
```json
{
  "feature_type_id": "feature:015-small-command-migration-finish",
  "current_phase": "specify",
  "last_completed_phase": null,
  "completed_phases": [],
  "mode": "standard",
  "source": "db",
  "degraded": false
}
```
**Output (error):**
```json
{
  "error": true,
  "error_type": "feature_not_found",
  "message": "Feature not found: feature:999-nonexistent",
  "recovery_hint": "Verify feature_type_id format: 'feature:{id}-{slug}'"
}
```
**Consumer behavior:**
- Success: Extract `current_phase`. Map `null`/`"brainstorm"` → `"specify"`. All others as-is.
- Error: Check for `"error": true` field. Set `mcp_available = false`. Fall back to artifact-based detection. The `error_type`, `message`, and `recovery_hint` fields are informational — consumer only needs the `error` field for branching.

### I2: complete_phase MCP Tool Call

**Caller:** finish-feature.md (Step 6a)
**Tool:** `complete_phase` (from workflow-engine MCP server)
**Input:** `feature_type_id: str`, `phase: str` — always `"finish"` for this command
**Output (success):** Updated `FeatureWorkflowState` JSON (same shape as I1 success)
**Output (error):** Same shape as I1 error (includes `error`, `error_type`, `message`, `recovery_hint`)
**Consumer behavior:**
- Success: Silent (no output change).
- Error: Warn with "Note: Workflow DB sync skipped — {message}" but do not block.

### I3: Artifact-Based Phase Detection (Fallback)

**Used by:** show-status.md, list-features.md (when MCP unavailable)
**Algorithm:** Check feature directory for existence of: `spec.md`, `design.md`, `plan.md`, `tasks.md`. First missing artifact name is the current phase. If all exist, phase is `"implement"`.
**Note:** This is the existing behavior, preserved unchanged as fallback. It cannot distinguish `"finish"` from `"implement"` — this is a known limitation accepted in the spec (NFR-4).

### I4: Non-Active Feature Status Display

**Used by:** show-status.md (Sections 1.5, 2), list-features.md
**Algorithm:** If `.meta.json` `status` is `"completed"`, `"abandoned"`, or `"planned"`, display that status string directly. Do not call `get_phase`.
**Rationale:** Non-active features may not have workflow state in the engine. Their `.meta.json` status is definitive.
**Note:** The spec NFR-3 table lists completed/abandoned only for show-status Section 1.5, but `list-features.md` also displays completed features (current behavior, line 38 in display example). The Phase Resolution algorithm handles this correctly for all commands — non-active statuses are displayed from `.meta.json` regardless of which command invokes the algorithm.
