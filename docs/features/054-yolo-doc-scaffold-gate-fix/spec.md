# Specification: YOLO Doc Scaffold Gate Fix

## Problem Statement

In `finish-feature.md`, when YOLO mode is active and tier directories are missing (`mode = scaffold`), the scaffold gate auto-selects "Skip" which jumps to Step 3 — bypassing the entire documentation pipeline including README/CHANGELOG updates. This causes documentation drift on every YOLO-mode feature completion in projects without pre-existing doc tier directories.

**RCA reference:** `docs/rca/20260323-yolo-doc-skip.md`

## Root Causes Addressed

- **RC-1:** Scaffold gate YOLO override unconditionally skips all documentation
- **RC-2:** No separation between tier scaffolding and README/CHANGELOG updates
- **RC-3 (partial):** Missing explicit "docs updates found → proceed" YOLO override for parity with `wrap-up`

**Intentionally unchanged:** The researcher `no_updates_needed + empty affected_tiers` YOLO override (line 21) is unchanged — RCA confirmed it is safe due to researcher structural safeguards (`documentation-researcher.md` lines 326-331).

## Requirements

### FR-1: Scaffold gate Skip path runs README/CHANGELOG writer directly

**Current behavior:** `finish-feature.md` line 109: `If "Skip" or "Defer": Continue to Step 3 (no documentation updates).` YOLO auto-selects "Skip" → entire doc pipeline skipped.

**New behavior:** When "Skip" or "Defer" is selected at scaffold gate (by user or YOLO):
1. Skip tier scaffolding (do NOT create `docs/{tier}/` directories)
2. Skip Pre-Computed Git Timestamps, Researcher Dispatch, Researcher Evaluation Gate, and Tier Writer Dispatches
3. Jump directly to the README/CHANGELOG Writer Dispatch
4. The README/CHANGELOG Writer Dispatch runs without researcher findings — receives git diff context directly instead

This follows `wrap-up.md` precedent (line 163): "If zero tier directories exist after filtering, skip tier writing entirely and dispatch only the README/CHANGELOG writer."

**Concrete change to lines 109-112:**

Replace:
```
If "Skip" or "Defer": Continue to Step 3 (no documentation updates).
If "Scaffold": Continue with enriched documentation flow below.

**YOLO override:** Auto-select "Skip" (never auto-scaffold during finish-feature).
```

With:
```
If "Skip" or "Defer": Skip to README/CHANGELOG Writer Dispatch below (bypasses tier scaffolding, researcher, and tier writers — but README/CHANGELOG still updated).
If "Scaffold": Continue with enriched documentation flow below.

**YOLO override:** Auto-select "Skip" (skip tier scaffolding, still run README/CHANGELOG writer).
```

**README/CHANGELOG Writer Dispatch context adjustment:** When reached via Skip path (no researcher findings available), the writer prompt replaces `{researcher findings}` with:
```
No researcher findings (scaffold skipped). Use git diff for context:
{git diff output against base branch}
```

**Acceptance criteria:**
- AC-1: Given YOLO mode active + no `docs/{tier}/` directories, when `finish-feature` reaches scaffold gate, then scaffold gate auto-selects Skip AND README/CHANGELOG writer dispatch executes
- AC-2: Given YOLO mode active + no `docs/{tier}/` directories, when `finish-feature` reaches scaffold gate, then tier writer dispatches do NOT execute
- AC-3: Given non-YOLO mode, when `finish-feature` reaches scaffold gate, then behavior is unchanged (user is prompted with Skip/Scaffold/Defer)
- AC-4: Given Skip path selected, when README/CHANGELOG writer runs, then it receives git diff context instead of researcher findings

### FR-2: Add explicit "docs updates found → proceed" YOLO override

**Current behavior:** `finish-feature.md` YOLO overrides section does not mention what happens when docs updates ARE found. `wrap-up.md` line 20 has: `Step 2b (docs updates found) → proceed with writer dispatches (no prompt needed)`.

**New behavior:** Add to `finish-feature.md` YOLO overrides section:
```
- Step 2b (docs updates found) → proceed with writer dispatches (no prompt needed)
```

This is a documentation-only change for parity with `wrap-up.md`. Current behavior already proceeds without prompting; this makes the implicit override explicit in the YOLO overrides section.

**Acceptance criteria:**
- AC-5: `finish-feature.md` YOLO overrides section includes the "docs updates found" override line
- AC-6: YOLO doc-related overrides in `finish-feature.md` are symmetric with `wrap-up.md`

### FR-3: Documentation Commit block reachable from both paths

The Documentation Commit block (`git add docs/ README.md CHANGELOG.md && git commit && git push`) must remain reachable from both the scaffold and skip paths. Currently it sits after the README/CHANGELOG Writer Dispatch — this position is correct for both paths. No structural change needed, but the spec confirms it.

**Acceptance criteria:**
- AC-7: Read `finish-feature.md` end-to-end, trace both YOLO+scaffold Skip path and Scaffold path — both reach the Documentation Commit block

## Out of Scope

- Post-merge doc drift detection hook (RC-3 full fix — separate feature)
- `promptimize` CHANGELOG updates (Finding 6 — low severity, by-design)
- Changes to `wrap-up.md` (already correctly designed)
- Changes to `generate-docs.md` (already correctly designed)
- Researcher Dispatch on Skip path (unnecessary — README/CHANGELOG writer uses git diff directly)

## Files Changed

1. `plugins/pd/commands/finish-feature.md`:
   - YOLO overrides section (add "docs updates found" line)
   - Scaffold UX Gate section (change Skip/Defer flow target from "Step 3" to "README/CHANGELOG Writer Dispatch")
   - YOLO override comment (update to clarify README/CHANGELOG still runs)
   - README/CHANGELOG Writer Dispatch prompt (add fallback context for when researcher was skipped)

## Verification

1. Grep `finish-feature.md` for "Continue to Step 3" after scaffold Skip — should find zero hits (replaced with README/CHANGELOG writer reference)
2. Compare YOLO override sections of `finish-feature.md` and `wrap-up.md` — doc-related overrides should be symmetric
3. Trace YOLO+scaffold Skip path through the file: scaffold gate → README/CHANGELOG Writer Dispatch → Documentation Commit → Step 3
4. Trace Scaffold path: scaffold gate → full pipeline → README/CHANGELOG Writer Dispatch → Documentation Commit → Step 3
