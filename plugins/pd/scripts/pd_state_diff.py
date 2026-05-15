#!/usr/bin/env python3
"""Feature 110 FR-4.6 — pd-state.diff.md generator (local-only artifact).

Emits a markdown diff of entity registry state between the current DB and
the base-commit timestamp horizon. The DB is the source of truth; `.meta.json`
is gitignored, so file-level diff is impossible. The algorithm replays
`phase_events` rows whose ``timestamp <= base_commit_ts`` to reconstruct each
entity's base-time state and compares it against the current row.

Per design §4.1:
  1. Resolve ``base_commit_ts`` via ``git log -1 --format=%aI <base>``.
  2. SELECT current state from ``entities`` LEFT JOIN ``workflow_phases``.
  3. Backfilled-entity defense: skip replay for entities whose
     ``created_at <= base_commit_ts`` AND have no ``entity_created``
     event — treat as no-change.
  4. Otherwise replay phase_events: ``entity_created`` → base-existed=True;
     ``entity_status_changed`` → update status; ``started``/``completed`` →
     update workflow_phase; ``entity_promoted`` → update type_id.
  5. Compare current vs base-time; emit row per entity with marker
     ``(added)`` / ``(removed)`` / ``(changed: <fields>)``.

Failure modes (TD-5):
  - Missing base ref → write ``pd-state diff unavailable: base ref '{base}' not found`` and exit 0 (AC-6.6).
  - Rebase/cherry-pick in progress → write short note and exit 0.
  - DB connection failure → write ``pd-state diff unavailable: DB connection failed`` and exit 0.
  - All other unexpected errors → write error note to stderr and exit 0.

Output:
  - Markdown to stdout (caller redirects to ``pd-state.diff.md``).
  - Atomic-rename via ``os.replace`` when ``--output PATH`` is supplied
    (concurrent-commit safety, TD-5).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
from pathlib import Path

DEFAULT_DB_PATH = os.path.expanduser("~/.claude/pd/entities/entities.db")

# Terminal statuses that move an entity out of the "active view". When an
# entity transitioned from existed-at-base into one of these, we mark the
# row as (removed).
_REMOVED_STATUSES = {"archived", "deleted"}


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_base_commit_ts(base: str) -> str | None:
    """Resolve ISO timestamp of ``base`` ref HEAD. Returns None if absent."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", base],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    ts = result.stdout.strip()
    return ts or None


def _is_rebase_or_cherry_pick_in_progress() -> bool:
    """Detect interrupted git state via .git markers."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return False
    if result.returncode != 0:
        return False
    git_dir = Path(result.stdout.strip())
    markers = ("rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")
    return any((git_dir / marker).exists() for marker in markers)


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------


def _open_db_readonly(db_path: str) -> sqlite3.Connection | None:
    """Open the entities DB read-only. Returns None on any failure."""
    try:
        # URI mode allows ``mode=ro`` flag for true read-only access.
        # Falls back to a regular connect when the URI form fails (e.g.,
        # in-memory or unusual paths in tests).
        if db_path == ":memory:":
            conn = sqlite3.connect(db_path, timeout=5.0)
        else:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


# ---------------------------------------------------------------------------
# State replay
# ---------------------------------------------------------------------------


def _fetch_current_state(conn: sqlite3.Connection) -> list[dict]:
    """Return list of current-state dicts keyed on entity uuid.

    Joins entities ⨝ workflow_phases via ``type_id`` (NOT entity_uuid;
    phase_events / workflow_phases is keyed on type_id).
    """
    rows = conn.execute(
        """
        SELECT e.uuid          AS uuid,
               e.type_id       AS type_id,
               e.status        AS status,
               e.parent_uuid   AS parent_uuid,
               e.created_at    AS created_at,
               e.updated_at    AS updated_at,
               wp.workflow_phase AS workflow_phase
        FROM entities e
        LEFT JOIN workflow_phases wp ON wp.type_id = e.type_id
        ORDER BY e.uuid
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _phase_events_for(
    conn: sqlite3.Connection,
    type_id: str,
    horizon_ts: str,
) -> list[sqlite3.Row]:
    """Return events for ``type_id`` with ``timestamp <= horizon_ts``.

    Note: phase_events table is keyed on ``type_id`` (NOT uuid). Design §4.1
    step 3 mentions ``entity_uuid``; that is a doc typo — the schema uses
    type_id (confirmed via PRAGMA table_info(phase_events)).
    """
    return conn.execute(
        """
        SELECT event_type, metadata, phase, timestamp
        FROM phase_events
        WHERE type_id = ? AND timestamp <= ?
        ORDER BY timestamp ASC, id ASC
        """,
        (type_id, horizon_ts),
    ).fetchall()


def _replay_to_base_state(
    events: list[sqlite3.Row],
    current_type_id: str,
) -> dict | None:
    """Replay events to reconstruct base-time state.

    Returns
    -------
    dict | None
        State dict with keys ``existed``, ``status``, ``workflow_phase``,
        ``type_id``. None when the entity did NOT exist at base time
        (no ``entity_created`` event observed in the horizon window).

    Algorithm:
      - entity_created → existed=True, status='active'
      - entity_status_changed → status = metadata.new_status (fallback: prior)
      - started/completed → workflow_phase = event.phase
      - entity_promoted → type_id = metadata.new_type_id (fallback: prior)
    """
    state: dict | None = None
    for ev in events:
        et = ev["event_type"]
        md_raw = ev["metadata"]
        try:
            md = json.loads(md_raw) if md_raw else {}
        except (ValueError, TypeError):
            md = {}

        if et == "entity_created":
            state = {
                "existed": True,
                "status": "active",
                "workflow_phase": None,
                "type_id": current_type_id,
            }
        elif state is None:
            # Event before entity_created (or no entity_created yet). Skip;
            # caller treats as "did not exist at base time" via None.
            continue
        elif et == "entity_status_changed":
            new_status = md.get("new_status")
            if new_status is not None:
                state["status"] = new_status
        elif et in ("started", "completed"):
            phase = ev["phase"]
            if phase is not None:
                state["workflow_phase"] = phase
        elif et == "entity_promoted":
            new_tid = md.get("new_type_id")
            if new_tid is not None:
                state["type_id"] = new_tid
        # Unknown event types ignored; replay tolerates schema evolution.
    return state


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def _short_uuid(u: str | None) -> str:
    if not u:
        return ""
    return u[:8]


def _compare_rows(
    current: dict,
    base_state: dict | None,
) -> tuple[str, list[str]]:
    """Return (marker, changed_fields).

    marker is one of:
      - "(added)"   — entity created after base
      - "(removed)" — existed at base, now archived/deleted
      - "(changed: <fields>)" — field-level diff
      - ""          — no change
    """
    if base_state is None:
        return "(added)", []

    # Treat current status in terminal-removed set as a "(removed)" row.
    if (
        current.get("status") in _REMOVED_STATUSES
        and base_state.get("status") not in _REMOVED_STATUSES
    ):
        return "(removed)", []

    changed: list[str] = []
    for field in ("type_id", "status", "workflow_phase"):
        cur_v = current.get(field)
        base_v = base_state.get(field)
        if cur_v != base_v:
            changed.append(field)

    if not changed:
        return "", []
    return f"(changed: {', '.join(changed)})", changed


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_markdown(base: str, rows: list[dict]) -> str:
    """Render TD-9 markdown table format. Caller passes already-classified rows.

    Each ``rows`` entry has keys: uuid, type_id, status, workflow_phase,
    parent_uuid, marker.
    """
    changed_count = sum(1 for r in rows if r["marker"].startswith("(changed"))
    added_count = sum(1 for r in rows if r["marker"] == "(added)")
    removed_count = sum(1 for r in rows if r["marker"] == "(removed)")

    if not rows:
        return f"No entity state changes vs {base}\n"

    lines = [
        f"# pd-state diff vs {base}",
        "",
        "| uuid (short) | type_id | status | workflow_phase | parent_uuid | change |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {uuid} | {tid} | {status} | {wp} | {parent} | {marker} |".format(
                uuid=_short_uuid(r["uuid"]),
                tid=r["type_id"] or "",
                status=r["status"] or "",
                wp=r["workflow_phase"] or "—",
                parent=_short_uuid(r["parent_uuid"]),
                marker=r["marker"],
            )
        )
    lines.append("")
    lines.append(
        f"Total: {changed_count} changed, {added_count} added, {removed_count} removed."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def generate_diff(base: str, db_path: str) -> str:
    """Compute the diff. Returns markdown string. Never raises.

    The function is the testable core; CLI wraps it for argv handling and
    optional atomic file-write.
    """
    # Edge case: rebase / cherry-pick in progress → skip generation entirely.
    if _is_rebase_or_cherry_pick_in_progress():
        return "pd-state diff skipped: rebase or cherry-pick in progress\n"

    # Edge case: base ref missing.
    base_ts = _git_base_commit_ts(base)
    if base_ts is None:
        return f"pd-state diff unavailable: base ref '{base}' not found\n"

    # Edge case: DB connection failure.
    conn = _open_db_readonly(db_path)
    if conn is None:
        return "pd-state diff unavailable: DB connection failed\n"

    try:
        try:
            current_rows = _fetch_current_state(conn)
        except sqlite3.Error:
            return "pd-state diff unavailable: DB connection failed\n"

        # Empty-tree branch / empty DB → no changes.
        if not current_rows:
            return f"No entity state changes vs {base}\n"

        diff_rows: list[dict] = []
        for cur in current_rows:
            created_at = cur.get("created_at") or ""
            type_id = cur.get("type_id") or ""

            # Backfilled-entity defense (design §4.1 step 3):
            # created_at <= base_ts AND no entity_created event → no change.
            try:
                events = _phase_events_for(conn, type_id, base_ts)
            except sqlite3.Error:
                events = []

            has_created_event = any(
                ev["event_type"] == "entity_created" for ev in events
            )

            if created_at <= base_ts and not has_created_event:
                # Backfilled: treat as base-time == current-time → no-change.
                continue

            if created_at > base_ts:
                # Entity didn't exist at base time.
                base_state = None
            else:
                base_state = _replay_to_base_state(events, current_type_id=type_id)

            marker, _changed = _compare_rows(cur, base_state)
            if not marker:
                continue
            diff_rows.append({
                "uuid": cur["uuid"],
                "type_id": cur["type_id"],
                "status": cur["status"],
                "workflow_phase": cur["workflow_phase"],
                "parent_uuid": cur["parent_uuid"],
                "marker": marker,
            })

        return _render_markdown(base, diff_rows)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _atomic_write(path: str, content: str) -> None:
    """Write ``content`` to ``path`` via tmp + os.replace (TD-5)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(target))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit pd-state.diff.md (entity registry diff vs base ref).",
    )
    parser.add_argument(
        "--base",
        required=True,
        help="Base branch name (e.g. develop). Resolved via git log -1 --format=%%aI.",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("ENTITY_DB_PATH", DEFAULT_DB_PATH),
        help="Path to entities.db. Defaults to $ENTITY_DB_PATH or ~/.claude/pd/entities/entities.db.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path. If provided, write atomically; "
             "otherwise emit to stdout.",
    )
    args = parser.parse_args(argv)

    try:
        content = generate_diff(args.base, args.db)
    except Exception as exc:  # pragma: no cover — defensive
        # Per AC-6.6: never block on unexpected error.
        print(
            f"[pd-state-diff] unexpected error: {exc}",
            file=sys.stderr,
        )
        content = "pd-state diff unavailable: internal error\n"

    if args.output:
        try:
            _atomic_write(args.output, content)
        except OSError as exc:
            print(
                f"[pd-state-diff] failed to write {args.output}: {exc}",
                file=sys.stderr,
            )
            return 0
    else:
        sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
