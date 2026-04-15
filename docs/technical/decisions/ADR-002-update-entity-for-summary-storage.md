---
last-updated: 2026-04-02T00:00:00Z
source-feature: 075-phase-context-accumulation
status: Accepted
---
# ADR-002: update_entity for Summary Storage

## Status
Accepted

## Context
Feature 075 requires storing a phase summary dict after each phase completion. The existing `complete_phase` MCP call already records phase completion (timing, iterations, reviewer notes) at Step 2 of `commitAndComplete`. A mechanism was needed to also persist the new `phase_summaries` entry without changing the `complete_phase` API contract.

The spec explicitly states that `_process_complete_phase` at `workflow_state_server.py:661` must remain unchanged (spec.md:19).

## Decision
Use `update_entity` MCP after `complete_phase` succeeds (in a new Step 3a), rather than adding a `phase_summary` parameter to `complete_phase`.

`commitAndComplete` calls `update_entity(type_id, metadata={"phase_summaries": existing + [new_entry]})` after Step 3 (plain-text Phase Summary output). Step 3a is best-effort — failure is logged as a warning and does not block the workflow.

## Alternatives Considered
Adding a new `phase_summary` parameter to `complete_phase` MCP would consolidate both operations into a single MCP call and ensure atomicity between phase completion and summary storage.

## Consequences
Decoupling summary storage from phase completion provides:
- (+) `_process_complete_phase` remains unchanged — no risk of regression in the phase completion path
- (+) Summary failure is isolated — a failed `update_entity` does not roll back or interfere with phase completion (which already succeeded in Step 2)
- (+) The `update_entity` path is already proven for metadata updates (e.g., `backward_context` storage in `handleReviewerResponse`)
- (-) Two MCP round-trips instead of one (latency impact is negligible in practice)
- (-) A successful `complete_phase` with a failed `update_entity` leaves the feature without a summary for that phase — acceptable given summaries are informational, not operational

## References
- spec.md:19 — _process_complete_phase unchanged requirement
- design.md: TD-2, C2
- SKILL.md:303-309 — existing update_entity usage for backward_context storage
