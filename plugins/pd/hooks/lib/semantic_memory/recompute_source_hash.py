"""Feature 115 FR-B-H4-115.4 / IF-115-2: hash recomputation helper.

Provides:
- ``recompute_all(db, dry_run)``: iterate entries, recompute source_hash from
  description, update those that differ. Identity-safe — same row IDs,
  corrected hash values only.
- ``recompute_all_with_conn(conn, dry_run)``: connection-accepting variant
  (used by M6 Op 2 which receives a raw sqlite3.Connection from the migration
  runner).
- ``report(db)``: SELECT-only diagnostic for spec AC-B-H4-115.5.

CLI entry: ``python -m plugins.pd.hooks.lib.semantic_memory.recompute_source_hash --report``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from semantic_memory.database import MemoryDatabase


def _hash_description(description: str) -> str:
    """Canonical hash per spec FR-B-H4.1: SHA-256(description)[:16].

    Mirrors the pattern used in Migration 3 backfill (database.py:234).
    """
    return hashlib.sha256(description.encode()).hexdigest()[:16]


def _recompute_core(conn: sqlite3.Connection, dry_run: bool) -> dict:
    """Shared implementation for both recompute_all and recompute_all_with_conn.

    Returns: {"shifted_ids": list[str], "unchanged_count": int, "total": int,
              "null_or_empty_skipped": int}
    """
    cur = conn.execute("SELECT id, description, source_hash FROM entries")
    shifted: list[str] = []
    unchanged = 0
    total = 0
    skipped = 0
    for row in cur.fetchall():
        total += 1
        entry_id = row[0] if not hasattr(row, "keys") else row["id"]
        desc = row[1] if not hasattr(row, "keys") else row["description"]
        stored_hash = row[2] if not hasattr(row, "keys") else row["source_hash"]
        if desc is None or desc == "":
            skipped += 1
            continue
        new_hash = _hash_description(desc)
        if new_hash != stored_hash:
            shifted.append(entry_id)
            if not dry_run:
                conn.execute(
                    "UPDATE entries SET source_hash = ? WHERE id = ?",
                    (new_hash, entry_id),
                )
        else:
            unchanged += 1
    if not dry_run:
        # The caller (migration or CLI) is responsible for COMMIT — migrations
        # run inside an outer BEGIN IMMEDIATE (semantic_memory/database.py
        # _migrate() wraps all migrations in one); CLI commits via the
        # MemoryDatabase wrapper.
        pass
    return {
        "shifted_ids": shifted,
        "unchanged_count": unchanged,
        "total": total,
        "null_or_empty_skipped": skipped,
    }


def recompute_all(db: MemoryDatabase, dry_run: bool = True) -> dict:
    """Recompute source_hash for all entries using description as input.

    114 IF-5 contract carried forward.
    """
    result = _recompute_core(db._conn, dry_run=dry_run)
    if not dry_run:
        db._conn.commit()
    return result


def recompute_all_with_conn(
    conn: sqlite3.Connection, dry_run: bool = False
) -> dict:
    """Connection-accepting variant for use inside migrations.

    Does NOT call commit() — the caller (migration runner) owns the
    transaction.
    """
    return _recompute_core(conn, dry_run=dry_run)


def report(db: MemoryDatabase) -> dict:
    """SELECT-only diagnostic for spec AC-B-H4-115.5.

    Returns:
        {
          "n_shifted": int,
          "n_tool_failure": int,
          "n_inflated": int,
          "observed_at": str (ISO 8601),
        }
    """
    dry = recompute_all(db, dry_run=True)
    n_shifted = len(dry["shifted_ids"])
    n_tool_failure = db._conn.execute(
        "SELECT COUNT(*) FROM entries "
        "WHERE source='session-capture' AND name LIKE 'Tool failure:%'"
    ).fetchone()[0]
    n_inflated = db._conn.execute(
        "SELECT COUNT(*) FROM entries "
        "WHERE source='import' AND observation_count > 100"
    ).fetchone()[0]
    return {
        "n_shifted": int(n_shifted),
        "n_tool_failure": int(n_tool_failure),
        "n_inflated": int(n_inflated),
        "observed_at": datetime.now(tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recompute source_hash for memory.db entries (feature 115 FR-B-H4)"
    )
    parser.add_argument(
        "--db",
        default=os.path.expanduser("~/.claude/pd/memory/memory.db"),
        help="Path to memory.db (default: ~/.claude/pd/memory/memory.db)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--report",
        action="store_true",
        help="Diagnostic report mode (SELECT-only; AC-B-H4-115.5).",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Recompute without writing; print shifted_ids JSON.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Recompute AND write back unified hashes.",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"Error: memory.db not found at {args.db}", file=sys.stderr)
        return 2

    db = MemoryDatabase(args.db)
    try:
        if args.report:
            print(json.dumps(report(db), indent=2))
        elif args.dry_run:
            result = recompute_all(db, dry_run=True)
            print(json.dumps({
                "n_shifted": len(result["shifted_ids"]),
                "shifted_ids_first_10": result["shifted_ids"][:10],
                "unchanged_count": result["unchanged_count"],
                "total": result["total"],
                "null_or_empty_skipped": result["null_or_empty_skipped"],
            }, indent=2))
        elif args.apply:
            result = recompute_all(db, dry_run=False)
            print(json.dumps({
                "applied": True,
                "n_shifted": len(result["shifted_ids"]),
                "total": result["total"],
            }, indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
