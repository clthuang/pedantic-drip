"""Lossless .meta.json projection: fold a feature entity's event stream
into the FR126 .meta.json dict shape (design 126, D1/D2/D3).

Owns everything v2 .meta.json-projection-shaped: ``project_meta(conn,
entity_uuid) -> dict``, the sole entry point. Ships dark: no live v17
code path imports this module, only its own tests do (mirrors
schema_v2.py/events.py/display.py/views.py, design 118 D1) — feature 127
owns wiring this into the live writer.

Grammar scope — live writer only (design D1): the fold below reproduces
the CURRENT writer's output (workflow_state_server.py:437-499) exactly.
Legacy pre-current-writer files on disk (114/116: ``completed_clusters``,
``deferral_reasoning``, ``files_changed``, ``notes``, phase-level
``status``, ``stages{...}``) have NO grammar slot BY DESIGN — the
current writer does not emit them; they are 132's historical-backfill
concern, and this projection correctly FLAGS them non-round-trippable
(by omission) rather than silently reproducing them. Invents nothing: no
wall-clock fallback anywhere (v1's ``_iso_now()`` fallback for
``created``/``completed`` is deliberately dropped) — every projected
value traces to either the ``entities`` row or a specific event/payload
key; a field with no carrier is simply absent.

Read path (design D3): ONE ``read_events(conn, entity_uuid)`` call (full
ordered stream, index-covered) + one ``entities`` row SELECT. No views,
no writes, no per-entity ``entity_state`` reads (#067's O(total-events)
trap) — 120's views are not used at all; per-phase history needs the
full ordered stream regardless of what any latest-per-axis view could
offer.
"""
from __future__ import annotations

import sqlite3

# Dual role (design D7): (1) side effect — importing entity_registry.events
# registers the "events" DDL entry into schema_v2.DDL_REGISTRY, the same
# mechanism views.py/display.py rely on for the "events before X" registry
# order — so any bootstrap_v2 call made after importing this module gets a
# schema with the events table present; (2) direct consumer — project_meta
# below calls events.read_events(...), so unlike views.py's `# noqa: F401`
# side-effect-only import, this one is also literally used and would not
# survive an "unused import" strip.
from entity_registry import events

# Sentinel distinguishing "this payload key was never carried by any event"
# from "carried, but its value happens to be falsy" — needed for the
# fields whose absence rule is "absent if never carried" (mode/branch
# excluded: an `initialized` event is required and always carries them,
# design FR126-2, so no sentinel is needed there).
_UNSET = object()

# DENYLIST framing (design D2, forward-compatible with 127's status
# vocabulary): every event_type NOT in this set participates in the
# status fold — both `lifecycle` and `execution` axes fold into ONE
# latest-wins-by-uuid answer (the spec's "axis precedence" question
# dissolves). A future status-bearing event_type 127 mints therefore
# participates BY DEFAULT — an allowlist would silently exclude it. The
# forward rule is the inverse: any future NON-status event_type MUST be
# added here; 127's integration asserts its event vocabulary against
# this set (events.event_type has no CHECK enumeration to assert against
# structurally, so this frozenset carries the obligation).
_NON_STATUS_EVENT_TYPES = frozenset({
    "renamed", "phase_started", "phase_completed", "phase_backward",
})

# design D1/D3: these four lifecycle event_types are the FALLBACK-only
# source for the top-level `completed` field, used when no "finish"
# phase_completed event exists (e.g. abandoned-pre-finish). Grouped
# verbatim per D1's grammar table row — the fold does not judge whether
# a given event_type is "really" terminal (e.g. `activated` reads oddly
# here); the finish-then-backward-without-terminal seam vs the live
# writer's tighter condition is consciously deferred to 127's
# writer-equivalence integration (design D3).
_COMPLETED_FALLBACK_EVENT_TYPES = frozenset({
    "completed", "abandoned", "archived", "activated",
})


def project_meta(conn: sqlite3.Connection, entity_uuid: str) -> dict:
    """Fold *entity_uuid*'s full event stream into a .meta.json-shaped dict.

    Kind guard FIRST, before any event read (design D3): *entity_uuid*
    absent from ``entities`` raises ``ValueError(entity_uuid)``; a
    non-"feature" ``kind`` raises ``ValueError(kind)`` — the project
    shape belongs to 123, not this module.

    Init required (design D1): zero ``initialized`` events raises
    ``ValueError`` naming the missing event class.

    ``read_events`` returns *entity_uuid*'s full stream ordered ascending
    by uuid, and uuid7 mint order IS chronological order (RFC 9562) — so
    a single forward pass that OVERWRITES plain variables in place
    already implements "the MAX(uuid) event wins" (design D2) for every
    last-write-wins field, with no separate max-tracking or re-sort
    needed. ``phase_summaries`` is the one ACCUMULATING field (appends,
    never overwrites); the two backward fields are filtered to ABSENT at
    the end if falsy, not mid-fold (design D3).

    ``phases`` dict key order = first-entry order (whichever
    phase-shaped event first mentions a given phase name) as a side
    effect of the single forward pass; per design D3 this is
    informational only — the contract is dict-level ``==``, never a
    key-order or serialized-byte comparison.
    """
    row = conn.execute(
        "SELECT type_id, kind, created_at FROM entities WHERE uuid = ?",
        (entity_uuid,),
    ).fetchone()
    if row is None:
        raise ValueError(entity_uuid)
    type_id, kind, created_at = row
    if kind != "feature":
        raise ValueError(kind)

    event_rows = events.read_events(conn, entity_uuid)
    if not any(event["event_type"] == "initialized" for event in event_rows):
        raise ValueError(
            f"entity {entity_uuid!r} has no 'initialized' event "
            "(init required, design 126 D1)"
        )

    status = None
    mode = None
    branch = None
    brainstorm_source = _UNSET
    backlog_source = _UNSET
    skipped_phases = _UNSET
    backward_context = None
    backward_return_target = None
    phase_summaries: list = []
    phases: dict[str, dict] = {}
    last_completed_phase = None
    finish_completed_ts = None
    terminal_lifecycle_ts = None

    for event in event_rows:
        event_type = event["event_type"]
        to_value = event["to_value"]
        timestamp = event["timestamp"]
        payload = event["payload"] or {}

        if event_type not in _NON_STATUS_EVENT_TYPES:
            status = to_value
        if event_type in _COMPLETED_FALLBACK_EVENT_TYPES:
            terminal_lifecycle_ts = timestamp

        if "mode" in payload:
            mode = payload["mode"]
        if "branch" in payload:
            branch = payload["branch"]
        if "brainstorm_source" in payload:
            brainstorm_source = payload["brainstorm_source"]
        if "backlog_source" in payload:
            backlog_source = payload["backlog_source"]
        if "skippedPhases" in payload:
            skipped_phases = payload["skippedPhases"]
        if "backwardContext" in payload:
            backward_context = payload["backwardContext"]
        if "backwardReturnTarget" in payload:
            backward_return_target = payload["backwardReturnTarget"]

        if event_type in ("phase_started", "phase_backward"):
            # Re-entry rule (design D3, workflow_state_server.py:941-945
            # setdefault + unconditional ["started"] = ts): setdefault
            # creates the phase's container on first mention only,
            # started itself is unconditionally overwritten every time —
            # backward-then-forward re-entry OVERWRITES, never preserves
            # the earliest started ts.
            phases.setdefault(to_value, {})["started"] = timestamp
        elif event_type == "phase_completed":
            phase_entry = phases.setdefault(to_value, {})
            phase_entry["completed"] = timestamp
            if "iterations" in payload:
                phase_entry["iterations"] = payload["iterations"]
            if "reviewerNotes" in payload:
                phase_entry["reviewerNotes"] = payload["reviewerNotes"]
            if "phaseSummaryEntry" in payload:
                phase_summaries.append(payload["phaseSummaryEntry"])
            last_completed_phase = to_value
            if to_value == "finish":
                finish_completed_ts = timestamp

    tail = type_id.split(":", 1)[1]
    id_part, _, slug_part = tail.partition("-")

    # Field order below mirrors the live writer's own insertion order
    # (workflow_state_server.py:437-499) — not load-bearing for dict
    # equality, but keeps this fold easy to diff against that writer at
    # 127's cutover.
    meta: dict = {
        "id": id_part,
        "slug": slug_part,
        "mode": mode,
        "status": status,
        "created": created_at,
        "branch": branch,
    }

    # Top-level `completed`: PRIMARY is the finish-phase completion ts
    # (fires independent of terminal status, per FR126-2); FALLBACK is
    # the latest terminal-ish lifecycle event's ts; ABSENT if neither
    # exists. Never a wall-clock invention (v1's `_iso_now()` fallback
    # is deliberately dropped).
    completed_value = (
        finish_completed_ts if finish_completed_ts is not None else terminal_lifecycle_ts
    )
    if completed_value is not None:
        meta["completed"] = completed_value

    if brainstorm_source is not _UNSET:
        meta["brainstorm_source"] = brainstorm_source
    if backlog_source is not _UNSET:
        meta["backlog_source"] = backlog_source

    meta["lastCompletedPhase"] = last_completed_phase
    meta["phases"] = phases

    if skipped_phases is not _UNSET:
        meta["skippedPhases"] = skipped_phases

    # backward_context/backward_return_target: "last-carrying wins; a
    # FALSY carried value projects ABSENT" (design D3) — never-carried
    # (still None here) and carried-but-falsy collapse to the same
    # absent output, so one truthy check covers both.
    if backward_context:
        meta["backward_context"] = backward_context
    if backward_return_target:
        meta["backward_return_target"] = backward_return_target

    if phase_summaries:
        meta["phase_summaries"] = phase_summaries

    return meta
