---
last-updated: 2026-04-02T00:00:00Z
source-feature: 075-phase-context-accumulation
status: Accepted
---
# ADR-001: Phase Summaries Append-List Storage

## Status
Accepted

## Context
Feature 075 introduces structured phase summary accumulation to preserve context across backward transitions in the workflow. When a reviewer sends a feature back to a prior phase for rework, the re-entered phase previously had no knowledge of what prior phases decided or produced. The core problem statement: reviewers re-raise already-resolved issues, drafters contradict prior conclusions, and iteration counts inflate because context is lost on each backward hop.

A storage model was needed that preserves the full rework history across multiple completions of the same phase.

## Decision
Store `phase_summaries` as `list[dict]` in entity metadata, not as `dict[phase_name, dict]`.

Each entry in the list conforms to the 7-field schema: `{phase, timestamp, outcome, artifacts_produced, key_decisions, reviewer_feedback_summary, rework_trigger}`.

New entries are appended via `update_entity` MCP after each phase completion. The list is never overwritten in place — append-only.

## Alternatives Considered
A keyed dict (`{"specify": {...}, "design": {...}}`) was considered. It would map each phase name to a single summary entry, providing O(1) lookup by phase name.

## Consequences
A keyed dict would overwrite prior entries when a phase is re-completed during rework. The append-list preserves the full rework history — the second time specify completes, the list has two specify entries. This history is the primary value of the feature (spec.md FR-2).

Trade-offs of the append-list:
- (+) Full rework history preserved — multiple entries per phase are possible
- (+) Append is trivially correct — no merge logic needed
- (-) Lookup by phase name requires filtering the list
- (-) List grows unbounded across rework cycles (mitigated by 2000-char cap per entry and display trimming to last 2 per phase)

The injection layer (validateAndSetup Step 1b) trims display to the last 2 entries per phase to contain token cost. Storage remains unbounded but each entry is small (max 2000 chars serialized).

## References
- spec.md: FR-2, AC-1, AC-9
- design.md: TD-1, I1
- Context-Folding pattern (arxiv 2510.11967): fold intermediate reasoning into compressed summaries, retain summary, discard steps
