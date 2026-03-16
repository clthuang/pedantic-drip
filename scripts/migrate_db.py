#!/usr/bin/env python3
"""migrate_db.py — CLI tool for iflow database migration operations.

All subcommands output JSON to stdout. Errors go to stderr.
Exit 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import traceback
import uuid as uuid_mod

SUPPORTED_SCHEMA_VERSION = 1


def _json_stub() -> None:
    """Print empty JSON object stub and exit successfully."""
    json.dump({}, sys.stdout)
    print()  # trailing newline


def _json_out(data: dict) -> None:
    """Print JSON to stdout with trailing newline."""
    json.dump(data, sys.stdout)
    print()


def _json_error(msg: str) -> None:
    """Print error JSON to stdout and exit 1."""
    _json_out({"ok": False, "error": msg})
    sys.exit(1)


def cmd_backup(args: argparse.Namespace) -> None:
    """Backup a database table using sqlite3.Connection.backup() API."""
    src_conn = sqlite3.connect(args.src_db)
    dst_conn = sqlite3.connect(args.dst_db)
    try:
        src_conn.backup(dst_conn, pages=-1)
    finally:
        src_conn.close()
        dst_conn.close()

    # Compute SHA-256 of the backup file
    sha = hashlib.sha256()
    with open(args.dst_db, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)

    # Count rows in the specified table
    conn = sqlite3.connect(args.dst_db)
    try:
        entry_count = conn.execute(
            f"SELECT count(*) FROM [{args.table}]"
        ).fetchone()[0]
    finally:
        conn.close()

    size_bytes = os.path.getsize(args.dst_db)

    _json_out({
        "sha256": sha.hexdigest(),
        "size_bytes": size_bytes,
        "entry_count": entry_count,
    })


def cmd_manifest(_args: argparse.Namespace) -> None:
    """Generate a migration manifest for a staging directory."""
    _json_stub()


def cmd_validate(_args: argparse.Namespace) -> None:
    """Validate a migration bundle directory."""
    _json_stub()


def cmd_merge_memory(args: argparse.Namespace) -> None:
    """Merge memory entries from source to destination database."""
    dst = sqlite3.connect(args.dst_db)
    add_count = 0
    skip_count = 0
    try:
        dst.execute("ATTACH DATABASE ? AS src", (args.src_db,))

        # Count new vs existing entries by source_hash
        add_count = dst.execute("""
            SELECT count(*) FROM src.entries
            WHERE source_hash NOT IN (SELECT source_hash FROM main.entries)
        """).fetchone()[0]
        skip_count = dst.execute(
            "SELECT count(*) FROM src.entries"
        ).fetchone()[0] - add_count

        if args.dry_run:
            _json_out({"added": add_count, "skipped": skip_count})
            return

        dst.execute("BEGIN")
        dst.execute("""
            INSERT OR IGNORE INTO main.entries (id, name, description, reasoning,
                category, keywords, source, source_project, "references",
                observation_count, confidence, recall_count, last_recalled_at,
                embedding, created_at, updated_at, source_hash, created_timestamp_utc)
            SELECT id, name, description, reasoning,
                category, keywords, source, source_project, "references",
                observation_count, confidence, recall_count, last_recalled_at,
                embedding, created_at, updated_at, source_hash, created_timestamp_utc
            FROM src.entries
            WHERE source_hash NOT IN (SELECT source_hash FROM main.entries)
        """)

        # Rebuild FTS5
        if add_count > 0:
            try:
                dst.execute(
                    "INSERT INTO entries_fts(entries_fts) VALUES('rebuild')"
                )
            except sqlite3.OperationalError:
                pass

        dst.execute("COMMIT")
    except Exception:
        try:
            dst.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        try:
            dst.execute("DETACH DATABASE src")
        except Exception:
            pass
        dst.close()

    _json_out({"added": add_count, "skipped": skip_count})


def cmd_merge_entities(args: argparse.Namespace) -> None:
    """Merge entity records from source to destination database."""
    dst = sqlite3.connect(args.dst_db)
    new_type_ids: list[tuple[str]] = []
    skip_count = 0
    try:
        dst.execute("ATTACH DATABASE ? AS src", (args.src_db,))
        dst.execute("PRAGMA foreign_keys = OFF")

        # Phase 1: Identify new type_ids
        new_type_ids = dst.execute("""
            SELECT type_id FROM src.entities
            WHERE type_id NOT IN (SELECT type_id FROM main.entities)
        """).fetchall()
        total_src = dst.execute(
            "SELECT count(*) FROM src.entities"
        ).fetchone()[0]
        skip_count = total_src - len(new_type_ids)

        if args.dry_run:
            _json_out({"added": len(new_type_ids), "skipped": skip_count})
            return

        dst.execute("BEGIN")

        # Phase 2: Insert entities with Python-generated UUIDs
        cols = [
            desc[0]
            for desc in dst.execute(
                "SELECT * FROM src.entities LIMIT 0"
            ).description
        ]
        uuid_idx = cols.index("uuid")
        parent_uuid_idx = cols.index("parent_uuid")
        placeholders = ",".join("?" * len(cols))
        col_names = ",".join(f'"{c}"' for c in cols)

        for (type_id,) in new_type_ids:
            row = dst.execute(
                "SELECT * FROM src.entities WHERE type_id = ?", (type_id,)
            ).fetchone()
            row = list(row)
            row[uuid_idx] = str(uuid_mod.uuid4())
            row[parent_uuid_idx] = None  # Cleared, reconstructed in Phase 4
            dst.execute(
                f"INSERT INTO main.entities ({col_names}) VALUES ({placeholders})",
                row,
            )

        # Phase 3: Merge workflow_phases for new type_ids only
        dst.execute("""
            INSERT OR IGNORE INTO main.workflow_phases (type_id, workflow_phase,
                kanban_column, last_completed_phase, mode,
                backward_transition_reason, updated_at)
            SELECT wp.type_id, wp.workflow_phase, wp.kanban_column,
                wp.last_completed_phase, wp.mode, wp.backward_transition_reason,
                wp.updated_at
            FROM src.workflow_phases wp
            WHERE wp.type_id NOT IN (SELECT type_id FROM main.workflow_phases)
        """)

        # Phase 4: Reconstruct parent_uuid for imported entities
        if new_type_ids:
            imported_list = ",".join(
                f"'{tid}'" for (tid,) in new_type_ids
            )
            dst.execute(f"""
                UPDATE main.entities
                SET parent_uuid = (
                    SELECT uuid FROM main.entities AS parent
                    WHERE parent.type_id = main.entities.parent_type_id
                )
                WHERE type_id IN ({imported_list})
                  AND parent_uuid IS NULL
                  AND parent_type_id IS NOT NULL
            """)

        # Phase 5: FTS5 rebuild
        try:
            dst.execute(
                "INSERT INTO entities_fts(entities_fts) VALUES('rebuild')"
            )
        except sqlite3.OperationalError:
            pass

        dst.execute("COMMIT")
    except Exception:
        try:
            dst.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        try:
            dst.execute("DETACH DATABASE src")
        except Exception:
            pass
        dst.close()

    _json_out({"added": len(new_type_ids), "skipped": skip_count})


def cmd_verify(args: argparse.Namespace) -> None:
    """Verify row counts in a database table after migration."""
    try:
        conn = sqlite3.connect(args.db_path)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        if integrity != "ok":
            _json_out({
                "ok": False,
                "actual_count": 0,
                "integrity": integrity,
            })
            conn.close()
            sys.exit(1)

        actual_count = conn.execute(
            f"SELECT count(*) FROM [{args.table}]"
        ).fetchone()[0]
        conn.close()

        expected = args.expected_count
        # If expected_count is 0, skip the comparison (count-only mode)
        if expected == 0:
            ok = True
        else:
            ok = actual_count == expected

        _json_out({
            "ok": ok,
            "actual_count": actual_count,
            "integrity": integrity,
        })
    except Exception as e:
        _json_out({
            "ok": False,
            "actual_count": 0,
            "integrity": str(e),
        })
        sys.exit(1)


def cmd_info(_args: argparse.Namespace) -> None:
    """Display information from a migration manifest."""
    _json_stub()


def cmd_check_embeddings(_args: argparse.Namespace) -> None:
    """Check embedding consistency between manifest and destination DB."""
    _json_stub()


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="migrate_db",
        description="iflow database migration tool",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # backup
    p_backup = subparsers.add_parser("backup", help="Backup a database table")
    p_backup.add_argument("src_db", help="Source database path")
    p_backup.add_argument("dst_db", help="Destination database path")
    p_backup.add_argument("--table", required=True, help="Main table name")
    p_backup.set_defaults(func=cmd_backup)

    # manifest
    p_manifest = subparsers.add_parser(
        "manifest", help="Generate migration manifest"
    )
    p_manifest.add_argument("staging_dir", help="Staging directory path")
    p_manifest.add_argument(
        "--plugin-version", required=True, help="Plugin version string"
    )
    p_manifest.set_defaults(func=cmd_manifest)

    # validate
    p_validate = subparsers.add_parser(
        "validate", help="Validate a migration bundle"
    )
    p_validate.add_argument("bundle_dir", help="Bundle directory path")
    p_validate.set_defaults(func=cmd_validate)

    # merge-memory
    p_merge_memory = subparsers.add_parser(
        "merge-memory", help="Merge memory databases"
    )
    p_merge_memory.add_argument("src_db", help="Source database path")
    p_merge_memory.add_argument("dst_db", help="Destination database path")
    p_merge_memory.add_argument(
        "--dry-run", action="store_true", help="Preview without modifying"
    )
    p_merge_memory.set_defaults(func=cmd_merge_memory)

    # merge-entities
    p_merge_entities = subparsers.add_parser(
        "merge-entities", help="Merge entity databases"
    )
    p_merge_entities.add_argument("src_db", help="Source database path")
    p_merge_entities.add_argument("dst_db", help="Destination database path")
    p_merge_entities.add_argument(
        "--dry-run", action="store_true", help="Preview without modifying"
    )
    p_merge_entities.set_defaults(func=cmd_merge_entities)

    # verify
    p_verify = subparsers.add_parser(
        "verify", help="Verify migration row counts"
    )
    p_verify.add_argument("db_path", help="Database path to verify")
    p_verify.add_argument(
        "--expected-count", required=True, type=int, help="Expected row count"
    )
    p_verify.add_argument("--table", required=True, help="Table name to check")
    p_verify.set_defaults(func=cmd_verify)

    # info
    p_info = subparsers.add_parser("info", help="Show manifest information")
    p_info.add_argument("manifest_path", help="Path to manifest file")
    p_info.set_defaults(func=cmd_info)

    # check-embeddings
    p_check = subparsers.add_parser(
        "check-embeddings", help="Check embedding consistency"
    )
    p_check.add_argument("manifest_path", help="Path to manifest file")
    p_check.add_argument("dst_memory_db", help="Destination memory database")
    p_check.set_defaults(func=cmd_check_embeddings)

    return parser


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
