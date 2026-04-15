---
last-updated: 2026-04-02T00:00:00Z
source-feature: 075-phase-context-accumulation
status: Accepted
---
# ADR-003: Backward Transition Detection via Completed Timestamp

## Status
Accepted

## Context
Feature 075 injects phase context (prior summaries and backward travel context) on backward transitions — when a feature re-enters a phase it has already completed. A reliable, low-ambiguity detection mechanism was needed to distinguish first-time phase entry from re-entry.

Two potential signals existed: the presence of `backward_context` in `.meta.json` (set by `handleReviewerResponse` on reviewer-initiated rework) and the `phase_timing[target_phase].completed` timestamp (set by `_process_complete_phase` on any phase completion).

## Decision
Trigger context injection whenever `phases[target_phase].completed` exists in `.meta.json`, regardless of whether `backward_context` is present.

Detection logic:
```python
def is_backward_transition(phase_name, meta_json):
    phase_timing = meta_json.get("phases", {})
    target_phase_timing = phase_timing.get(phase_name, {})
    return "completed" in target_phase_timing
```

Note: `.meta.json` projects `phase_timing` as `phases` (see `_project_meta_json` line 377).

## Alternatives Considered
Detecting backward transitions solely by the presence of `backward_context` in `.meta.json` was considered. This would limit injection to reviewer-initiated rework only.

## Consequences
Using the `completed` timestamp as the signal covers both:
- Reviewer-initiated backward travel (which sets `backward_context`)
- User-initiated re-runs (e.g., manually running `/pd:specify` on a feature that already completed specify, without a reviewer referral)

Both cases benefit from prior phase summaries. A false positive (user intentionally re-running a completed phase) results in helpful context being displayed — the injection is informational and never blocking, so the downside is minimal.

Relying only on `backward_context` would miss user-initiated re-runs entirely, providing no rework context in those cases.

## References
- spec.md: AC-4 note — injection triggers on ANY re-entry into a completed phase
- design.md: TD-4, I4
- SKILL.md:71-95 — validateAndSetup Step 1b implementation
