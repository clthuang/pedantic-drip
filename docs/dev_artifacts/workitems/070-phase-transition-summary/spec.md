# Spec: Phase Transition Summary

## Problem

When a phase completes and the user is asked whether to continue to the next phase, only a generic "Phase complete. Continue?" prompt is shown. The user has no visibility into:
- How many review iterations occurred
- Whether any reviewer concerns remain unresolved

This forces users to manually inspect `.review-history.md` or `.meta.json` to understand phase outcomes before making a transition decision.

## Requirements

### R1: Extended commitAndComplete Signature

The `commitAndComplete()` function in workflow-transitions SKILL.md currently accepts `(phaseName, artifacts[])`. Extend the signature to:

```
commitAndComplete(phaseName, artifacts[], iterations, reviewerNotes[])
```

- `iterations` (integer): The review loop counter at phase completion. For phases with two review stages (specify, design), this is the combined total across both stages (e.g., 2 spec-reviewer iterations + 1 phase-reviewer iteration = 3). For phases where the user triggers a counter reset (e.g., specify's "Fix and rerun reviews"), each retry resets the local iteration counter to 1; the value passed to `commitAndComplete()` is whatever the counter holds when the final retry loop exits.
- `reviewerNotes[]` (array of objects): Unresolved issues from the final reviewer iteration. Each object has shape: `{"severity": "warning|suggestion", "description": "..."}`. Command files construct this from the final reviewer JSON response's `issues[]` array, filtering to non-blocker items that were not addressed.

The current `commitAndComplete` Step 2 already passes placeholder iteration/reviewer_notes values to `complete_phase` MCP. This change replaces those with caller-provided values, ensuring the MCP receives accurate data from the review loop.

All five command files (specify, design, create-plan, create-tasks, implement) must update their `commitAndComplete()` call sites to pass these two additional parameters.

### R2: Phase Summary Block

Add a new **Step 3: Phase Summary** to `commitAndComplete()`, executed after Step 2 (Update State) and before returning control to the calling command's AskUserQuestion prompt. This step outputs a plain-text summary block.

The summary contains:

1. **Header line**: `"{PhaseName} complete ({iterations} iteration(s)). {outcome}"`
   - `outcome` is derived from this decision table (evaluated top to bottom, first match wins):
     - `iterations == max` (5 for all current phases) → "Review cap reached."
     - `iterations == 1` AND `reviewerNotes` is empty → "Approved on first pass."
     - `iterations > 1` AND `reviewerNotes` is empty → "Approved after {iterations} iterations."
     - `reviewerNotes` is non-empty → "Approved with notes."

2. **Artifacts line**: `"Artifacts: {comma-separated artifact filenames}"` — derived from `artifacts[]` parameter. If `artifacts[]` is empty (as in implement phase), omit this line.

3. **Remaining feedback** (only if `reviewerNotes[]` is non-empty):
   ```
   Remaining feedback ({W} warnings, {S} suggestions):
     [W] {description, truncated at 100 chars}
     [S] {description, truncated at 100 chars}
   ```
   - Use ASCII-safe prefixes `[W]` and `[S]` (not emoji) for terminal compatibility
   - Show at most 5 items, sorted by severity (warnings first)
   - If more than 5: append "...and {n} more"
   - **Cap-reached case**: When the header already says "Review cap reached.", the feedback section header becomes "Unresolved issues carried forward:" instead of "Remaining feedback (...):"

4. **Clean pass** (if `reviewerNotes[]` is empty): `"All reviewer issues resolved."`

### R3: Format Constraints

- Summary is plain text output, NOT inside AskUserQuestion
- Maximum 12 lines total for the summary block
- Each feedback description line truncated at 100 characters

### R4: reviewerNotes Construction in Command Files

Each command file constructs `reviewerNotes[]` from the final reviewer response before calling `commitAndComplete()`:

1. Take the last reviewer's JSON response `issues[]` array
2. Filter to items with `severity` of "warning" or "suggestion". For cap-reached cases (iterations == max), also include "blocker" severity items since the phase is completing despite unresolved blockers.
3. Map to `{"severity": item.severity, "description": item.description}`
4. Pass as the `reviewerNotes` parameter

For phases with two review stages (specify, design): use only the phase-reviewer's final `issues[]` array. The phase-reviewer is the final gate and covers the full scope — if domain-reviewer issues matter, the phase-reviewer will re-raise them.

For phases with one review stage (create-plan, create-tasks, implement): use that reviewer's final issues directly.

## Acceptance Criteria

- **AC-1**: All five command files pass `iterations` and `reviewerNotes[]` to `commitAndComplete()`
- **AC-2**: Phase completion shows iteration count and reviewer outcome in the summary block before the AskUserQuestion prompt
- **AC-3**: When `iterations == 1` and `reviewerNotes` is empty, summary shows "Approved on first pass." and "All reviewer issues resolved."
- **AC-4**: When review cap is reached (`iterations == max`), header shows "Review cap reached.", feedback section header is "Unresolved issues carried forward:", and blocker-severity items from the final reviewer response are included in the listed items
- **AC-5**: When unresolved warnings/suggestions exist, they are listed with `[W]`/`[S]` prefixes
- **AC-6**: Summary is generated in `commitAndComplete()` Step 3 — individual command files do NOT duplicate summary logic
- **AC-7**: Existing AskUserQuestion options remain unchanged — summary is additive
- **AC-8**: When `artifacts[]` is empty (implement phase), the artifacts line is omitted

Verification is manual (visual inspection of CLI output). No automated test is required — the feature is ephemeral display text in a SKILL.md procedural template. Run each phase command to completion and confirm the summary block appears before the AskUserQuestion prompt.

## Out of Scope

- Changing the AskUserQuestion options themselves
- Adding duration/timing information (separate concern)
- Persisting the summary to a file (ephemeral, shown once at transition)
- Modifying reviewer dispatch logic or feedback format
- Adding summary to YOLO mode auto-transitions (no user prompt to prepend to)
- Changing the `complete_phase` MCP tool signature (it already accepts iterations and reviewer_notes)
