"""Feature 114 Cluster A — M12 stub-trap remediation CLI.

Diagnoses and (with --apply) recovers entities.db instances stuck in the
M12 stub-trap state: ``_metadata.schema_version == 12`` while the entities
table still has the pre-M12 layout (``entity_type`` column present;
``type``/``kind``/``lifecycle_class`` columns absent).

Root cause: commit 6722191a shipped Migration 12 as a stub that stamped
schema_version=12 without doing any schema work. Subsequent commits added
the real schema body, but the pre-114 idempotency guard at database.py:2683
read the stamp and returned immediately, bypassing the body.

This CLI offers two paths:

  --diagnose (default): inspect the DB and report which state it's in
  --apply: roll the stamp back to 11; the next session restart will re-run
           M12 (with the FR-A.1 tightened guard) and pick up M13/M14

The rollback approach is the simplest robust recovery: M12 already runs
correctly when invoked at the right stamp; we just need to put the stamp
where M12 expects it. This avoids the complexity of forcibly executing the
M12 body while the stamp is already 12.

Usage:
    python -m plugins.pd.hooks.lib.entity_registry.remediate_m12
    python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 --apply
    python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 --db /path/to/entities.db
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _detect_state(conn: sqlite3.Connection) -> dict:
    """Return the current schema state classification.

    Possible states:
      - "no_metadata": _metadata table missing entirely (pristine DB)
      - "stamp_missing": _metadata present but no schema_version key
      - "pre_m11": stamp < 11
      - "stub_trap_m12": stamp == 12 AND entities pre-M12 layout (THE TARGET)
      - "fully_recovered_m12_or_later": stamp >= 12 AND entities post-M12 layout
      - "partial_m12": stamp == 12 AND entities in mixed state (some new columns
        added, some not) — needs manual inspection
      - "unknown": unrecognized combination
    """
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return {"state": "no_metadata", "stamp": None, "cols": []}
        raise
    if v_row is None:
        return {"state": "stamp_missing", "stamp": None, "cols": []}
    try:
        stamp = int(v_row[0])
    except (TypeError, ValueError):
        stamp = 0
    try:
        cols = sorted(
            r[1] for r in conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        )
    except sqlite3.OperationalError:
        cols = []
    has_entity_type = "entity_type" in cols
    has_type = "type" in cols
    has_kind = "kind" in cols
    has_lifecycle_class = "lifecycle_class" in cols
    post_m12 = (
        has_type and has_kind and has_lifecycle_class and not has_entity_type
    )
    pre_m12 = has_entity_type and not (has_type or has_kind or has_lifecycle_class)
    if stamp < 11:
        state = "pre_m11"
    elif stamp == 12 and pre_m12:
        state = "stub_trap_m12"
    elif stamp >= 12 and post_m12:
        state = "fully_recovered_m12_or_later"
    elif stamp == 12:
        state = "partial_m12"
    else:
        state = "unknown"
    return {
        "state": state,
        "stamp": stamp,
        "cols": cols,
        "has_entity_type": has_entity_type,
        "has_type": has_type,
        "has_kind": has_kind,
        "has_lifecycle_class": has_lifecycle_class,
    }


def _apply_recovery(db_path: Path, dry_run: bool = False) -> int:
    """Roll the M12 stamp back to 11 so next session re-runs the body.

    Pre-conditions verified: state == "stub_trap_m12".
    Backs up the DB before mutating.

    Returns 0 on success, non-zero on failure.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        state = _detect_state(conn)
    finally:
        conn.close()
    if state["state"] != "stub_trap_m12":
        print(
            f"Refusing to apply: state is {state['state']!r}, not stub_trap_m12. "
            f"Run --diagnose for details.",
            file=sys.stderr,
        )
        return 2
    if dry_run:
        print(
            f"Would: backup {db_path} → {db_path}.pre-m12-recovery-<timestamp>.bak"
        )
        print(
            f"Would: UPDATE _metadata SET value='11' WHERE key='schema_version'"
        )
        print("Would: PRAGMA wal_checkpoint(TRUNCATE)")
        return 0
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(
        db_path.name + f".pre-m12-recovery-{timestamp}.bak"
    )
    shutil.copy2(db_path, backup_path)
    print(f"Backup written: {backup_path}", file=sys.stderr)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE _metadata SET value='11' WHERE key='schema_version'"
        )
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        # Verify
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if not v_row or v_row[0] != "11":
            print(
                f"Verification failed: schema_version is {v_row}, expected 11",
                file=sys.stderr,
            )
            return 3
    finally:
        conn.close()
    print(
        "Recovery applied. Next session restart will re-run M12 (with the "
        "FR-A.1 tightened guard) and pick up M13/M14.",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose and recover M12 stub-trap state in entities.db"
    )
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".claude/pd/entities/entities.db"),
        help="Path to entities.db (default: ~/.claude/pd/entities/entities.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the recovery (rolls schema_version back to 11). "
        "Default mode is diagnose-only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --apply, report what would happen without mutating.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit state as JSON instead of human-readable output.",
    )
    args = parser.parse_args(argv)
    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 4
    conn = sqlite3.connect(str(db_path))
    try:
        state = _detect_state(conn)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(
            f"Database: {db_path}\n"
            f"  schema_version: {state['stamp']}\n"
            f"  entities columns: {', '.join(state['cols']) if state['cols'] else '(table missing)'}\n"
            f"  state: {state['state']}",
            file=sys.stderr,
        )
    if args.apply:
        if state["state"] == "fully_recovered_m12_or_later":
            print(
                "Already recovered. No action needed.", file=sys.stderr
            )
            return 0
        if state["state"] == "pre_m11":
            print(
                "Pre-M11 state. Nothing to remediate at M12 level — "
                "restart the session and let normal migrations run.",
                file=sys.stderr,
            )
            return 0
        if state["state"] == "partial_m12":
            print(
                "Partial-M12 state detected (stamp=12, some new columns added "
                "but not all). This is unsafe to recover via stamp rollback. "
                "Manual inspection required — restore from a backup or open "
                "an issue.",
                file=sys.stderr,
            )
            return 5
        if state["state"] == "stub_trap_m12":
            return _apply_recovery(db_path, dry_run=args.dry_run)
        print(
            f"Cannot apply: state {state['state']!r} not recoverable.",
            file=sys.stderr,
        )
        return 6
    # Diagnose-only mode
    if state["state"] == "stub_trap_m12":
        print(
            "\nStub-trap detected. To recover, run with --apply:\n"
            f"  python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 "
            f"--apply --db {db_path}",
            file=sys.stderr,
        )
        return 1  # non-zero so scripts can detect "needs remediation"
    return 0


if __name__ == "__main__":
    sys.exit(main())
