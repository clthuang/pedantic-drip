"""CLI entry point for frontmatter sync operations.

Provides subcommands for drift detection, DB-to-file stamping, file-to-DB
ingestion, bulk header backfill, and bulk drift scanning.

All output is JSON to stdout (machine-readable).  Human-readable summaries
go to stderr.  Exit code 0 for success (even if drift detected), non-zero
for fatal errors only (spec R30).

Usage::

    python -m entity_registry.frontmatter_sync_cli drift <filepath> <type_id>
    python -m entity_registry.frontmatter_sync_cli stamp <filepath> <type_id> <artifact_type>
    python -m entity_registry.frontmatter_sync_cli ingest <filepath>
    python -m entity_registry.frontmatter_sync_cli backfill <artifacts_root>
    python -m entity_registry.frontmatter_sync_cli scan <artifacts_root>
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from entity_registry.database import EntityDatabase
from entity_registry.frontmatter_sync import (
    backfill_headers,
    detect_drift,
    ingest_header,
    scan_all,
    stamp_header,
)


# ---------------------------------------------------------------------------
# DB lifecycle
# ---------------------------------------------------------------------------


def _open_db() -> EntityDatabase:
    """Open the entity database using ENTITY_DB_PATH env var or default.

    Returns
    -------
    EntityDatabase
        An open database instance.

    Raises
    ------
    Exception
        If the database cannot be opened (file not found, permission error,
        corrupt DB, etc.).
    """
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/iflow/entities/entities.db"),
    )
    return EntityDatabase(db_path)


def _run_handler(func: Callable[[EntityDatabase], Any]) -> None:
    """Shared DB lifecycle wrapper for all subcommand handlers.

    Opens the DB, calls *func(db)*, serializes the result as JSON to
    stdout, and closes the DB.  Handles DB construction failures (TD-5)
    by printing a JSON error and exiting with code 1.

    Parameters
    ----------
    func:
        A closure that accepts a single ``db`` parameter and returns a
        dataclass instance or a list of dataclass instances.
    """
    try:
        db = _open_db()
    except Exception as exc:
        # TD-5: DB construction failure -> JSON error, exit(1)
        json.dump({"error": f"Cannot open database: {exc}"}, sys.stdout)
        print(file=sys.stdout)  # trailing newline
        sys.exit(1)

    try:
        result = func(db)

        # Serialize: single dataclass or list of dataclasses
        if isinstance(result, list):
            output = [dataclasses.asdict(r) for r in result]
        else:
            output = dataclasses.asdict(result)

        json.dump(output, sys.stdout, default=str)
        print(file=sys.stdout)  # trailing newline
    except Exception as exc:
        json.dump({"error": f"Handler failed: {exc}"}, sys.stdout)
        print(file=sys.stdout)  # trailing newline
        sys.exit(1)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _handle_drift(args: argparse.Namespace) -> None:
    """Handler for the ``drift`` subcommand."""
    def handler(db: EntityDatabase):
        return detect_drift(db, args.filepath, args.type_id)
    _run_handler(handler)


def _handle_stamp(args: argparse.Namespace) -> None:
    """Handler for the ``stamp`` subcommand."""
    def handler(db: EntityDatabase):
        return stamp_header(db, args.filepath, args.type_id, args.artifact_type)
    _run_handler(handler)


def _handle_ingest(args: argparse.Namespace) -> None:
    """Handler for the ``ingest`` subcommand."""
    def handler(db: EntityDatabase):
        return ingest_header(db, args.filepath)
    _run_handler(handler)


def _handle_backfill(args: argparse.Namespace) -> None:
    """Handler for the ``backfill`` subcommand."""
    def handler(db: EntityDatabase):
        return backfill_headers(db, args.artifacts_root)
    _run_handler(handler)


def _handle_scan(args: argparse.Namespace) -> None:
    """Handler for the ``scan`` subcommand."""
    def handler(db: EntityDatabase):
        return scan_all(db, args.artifacts_root)
    _run_handler(handler)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="frontmatter_sync_cli",
        description="Frontmatter sync operations between files and entity DB.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # drift
    p_drift = sub.add_parser("drift", help="Detect drift between file and DB")
    p_drift.add_argument("filepath", help="Path to the markdown file")
    p_drift.add_argument("type_id", help="Entity type_id for DB lookup")
    p_drift.set_defaults(func=_handle_drift)

    # stamp
    p_stamp = sub.add_parser("stamp", help="Stamp DB record onto file header")
    p_stamp.add_argument("filepath", help="Path to the markdown file")
    p_stamp.add_argument("type_id", help="Entity type_id for DB lookup")
    p_stamp.add_argument("artifact_type", help="Artifact type (spec, design, ...)")
    p_stamp.set_defaults(func=_handle_stamp)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest file header into DB")
    p_ingest.add_argument("filepath", help="Path to the markdown file")
    p_ingest.set_defaults(func=_handle_ingest)

    # backfill
    p_backfill = sub.add_parser("backfill", help="Bulk stamp headers on artifact files")
    p_backfill.add_argument("artifacts_root", help="Root directory for artifacts")
    p_backfill.set_defaults(func=_handle_backfill)

    # scan
    p_scan = sub.add_parser("scan", help="Drift-scan all artifact files")
    p_scan.add_argument("artifacts_root", help="Root directory for artifacts")
    p_scan.set_defaults(func=_handle_scan)

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate handler."""
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
