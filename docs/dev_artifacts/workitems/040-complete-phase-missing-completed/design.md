# Design: complete_phase Missing Top-Level completed Timestamp

## Prior Art Research

Existing `_project_meta_json` function already handles all `.meta.json` field projection. The fix is a 3-line addition to the existing projection logic.

## Architecture Overview

No new components. Single function modification in `workflow_state_server.py`.

## Components

### Modified: `_project_meta_json` (workflow_state_server.py)

After the meta dict construction block (line 325), add conditional logic to populate `meta["completed"]` when status is terminal.

## Technical Decisions

- **D1: Use finish phase timing as primary source** — The finish phase `completed` timestamp is the most accurate reflection of when the feature was actually completed.
- **D2: Fall back to `_iso_now()` for missing timing** — Abandoned features never reach finish phase, and legacy data may lack timing. Using current time is acceptable for these edge cases.

## Interfaces

No new interfaces. The `.meta.json` output schema gains a `completed` field for terminal statuses, which `validate.sh` already expects.

## Risks

- **Low:** None identified. The change is additive and only affects terminal status projection.
