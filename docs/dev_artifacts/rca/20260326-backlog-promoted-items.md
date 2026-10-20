---
id: 20260326-backlog-promoted-items
type: rca
title: Promoted Backlog Items Still Visible in docs/backlog.md
status: done
---
# RCA: Promoted Backlog Items Still Visible in docs/backlog.md

**Date:** 2026-03-26
**Severity:** Low (cosmetic -- filtering works at display layer)
**Status:** Known gap, partially addressed

## Problem Statement

Several backlog items that have been promoted to features (#00020, #00031, #00038, #00040, #00045) remain visible in `docs/backlog.md`. The user asked three questions: (1) where do backlog entries come from, (2) why do promoted items still show, and (3) is this a known gap or a bug.

## Root Causes

### Cause 1: Deliberate Design Change from Remove to Annotate

**Evidence:** The original implementation (commit `b0da57d`, 2026-01-31) in feature 010-backlog-to-feature-link specified *removing* the backlog row when a feature was created from it. This was later changed (commit `d385045`, 2026-02-27) to *annotating* the row instead, with an explicit comment: "Annotate the row (do NOT remove it)".

The annotation appends `(promoted -> feature:{id}-{slug})` to the description column. This preserves traceability -- you can see which backlog items became which features without needing the entity registry.

**File:** `plugins/pd/commands/create-feature.md`, line 139

### Cause 2: No Archival or Cleanup Mechanism Exists

**Evidence:** There is no command, hook, or automated process to archive, prune, or move promoted/completed backlog items out of `backlog.md`. The file grows monotonically. Items are only added (via `/pd:add-to-backlog`) and annotated (via `/pd:create-feature` promotion path), never removed.

The backlog itself acknowledges this gap:
- **#00039** proposes filtering promoted brainstorms from show-status display
- **#00041** proposes making show-status code-based (querying entity registry), which would solve filtering programmatically

Neither has been promoted to a feature yet.

### Cause 3: Display Layer Filtering Compensates (Partially)

**Evidence:** The `show-status` command already filters promoted items at display time via two paths:

- **MCP path** (line 159): `Filter: exclude entities where status != "open"` -- queries entity DB where backlog status is set to "promoted" by create-feature
- **Filesystem fallback** (line 171): `Exclude rows containing "(promoted" in description` -- text pattern match on backlog.md

So promoted items do NOT appear in `/pd:show-status` output. The "problem" is only visible when reading `docs/backlog.md` directly.

### Additional Finding: Inconsistent Annotation Pattern for Item #00031

**Evidence:** Backlog item #00031 uses `(completed -> feature:056-..., feature:058-...)` instead of the standard `(promoted -> ...)` pattern. This was likely annotated manually or by a different code path.

The show-status filesystem fallback only checks for `(promoted` substring (line 171), so #00031 would NOT be filtered in the fallback path. If the MCP path is used, filtering depends on the entity DB status for backlog:00031. This is an inconsistency that could cause #00031 to appear as an "open" backlog item in the filesystem fallback display.

## How Backlog Entries Are Created

Entries are added via `/pd:add-to-backlog <description>` (defined in `plugins/pd/commands/add-to-backlog.md`):

1. Parses the next sequential 5-digit ID from `docs/backlog.md`
2. Appends a new table row with ID, ISO 8601 timestamp, and description
3. Registers an entity in the entity registry with `status="open"`
4. Initializes workflow with `workflow_phase="open"`, `kanban_column="backlog"`

Some entries appear to have been added manually (varying timestamp formats, non-standard annotations like "completed" on #00031).

## Hypotheses Considered

| # | Hypothesis | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | show-status already filters promoted items | Confirmed | Both MCP and fallback paths exclude promoted items |
| 2 | Design deliberately changed from remove to annotate | Confirmed | Git history shows commit d385045 changed the behavior |
| 3 | No cleanup mechanism exists | Confirmed | No archive/prune command found; backlog items #00039 and #00041 self-reference this gap |
| 4 | This is a bug in create-feature | Rejected | The annotation behavior is explicitly marked "do NOT remove it" |

## Assessment: Known Gap, Not a Bug

This is a **known architectural gap**, not a bug. The system works as designed:

1. **Creation:** `/pd:add-to-backlog` adds entries correctly
2. **Promotion:** `/pd:create-feature` annotates (not removes) promoted items correctly, and updates entity DB status to "promoted"
3. **Display filtering:** `/pd:show-status` correctly hides promoted items from the dashboard
4. **Raw file:** `docs/backlog.md` accumulates all entries (promoted and open) indefinitely -- this is the gap

The two backlog items that reference this gap (#00039 and #00041) propose the right direction: making show-status code-based via entity registry queries would eliminate the dependency on text-pattern matching in backlog.md entirely.

## Actionable Items (Not Fixes -- For Consideration)

1. **Inconsistent annotation on #00031:** Uses `(completed ->` instead of `(promoted ->`. This will cause it to appear as "open" in the filesystem fallback path of show-status.
2. **No archival for backlog.md:** As the file grows, it becomes harder to scan manually. A periodic archival mechanism (move promoted/completed items to a separate section or file) could help readability.
3. **Backlog #00041 addresses the root architectural issue:** Making show-status code-based would remove the fragile text-pattern-matching approach entirely.

## Files Examined

- `docs/backlog.md` -- the backlog file (31 entries, 4 promoted, 1 completed)
- `plugins/pd/commands/add-to-backlog.md` -- entry creation command
- `plugins/pd/commands/create-feature.md` -- promotion annotation logic (lines 129-145)
- `plugins/pd/commands/show-status.md` -- display filtering (lines 155-177)
- `plugins/pd/commands/list-features.md` -- does not display backlogs
- `plugins/pd/hooks/lib/doctor/checks.py` -- backlog status consistency check (lines 770-878)
- `docs/dev_artifacts/workitems/010-backlog-to-feature-link/` -- original feature that added backlog linking
- `docs/dev_artifacts/workitems/035-brainstorm-backlog-state-track/` -- feature that added entity lifecycle states
- Git commits: `b0da57d` (original remove behavior), `d385045` (changed to annotate)

## Reproduction

Sandbox: `agent_sandbox/20260326/rca-backlog-promoted-items/`
- `reproduction/verify_filtering.sh` -- confirms 4 promoted + 1 completed items in backlog.md
- `experiments/verify_all_hypotheses.sh` -- tests all hypotheses with evidence
