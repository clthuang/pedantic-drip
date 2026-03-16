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
import platform
import sqlite3
import sys
import uuid as uuid_mod
from datetime import datetime, timezone

SUPPORTED_SCHEMA_VERSION = 1


def _file_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _json_out(data: dict) -> None:
    """Print JSON to stdout with trailing newline."""
    json.dump(data, sys.stdout)
    print()


def cmd_backup(args: argparse.Namespace) -> None:
    """Backup a database table using sqlite3.Connection.backup() API."""
    src_conn = sqlite3.connect(args.src_db)
    dst_conn = sqlite3.connect(args.dst_db)
    try:
        src_conn.backup(dst_conn, pages=-1)
    finally:
        src_conn.close()
        dst_conn.close()

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
        "sha256": _file_sha256(args.dst_db),
        "size_bytes": size_bytes,
        "entry_count": entry_count,
    })


def cmd_manifest(args: argparse.Namespace) -> None:
    """Generate a migration manifest for a staging directory."""
    staging_dir = args.staging_dir

    # Build per-file entries with sha256 and size_bytes
    file_entries: dict[str, dict] = {}
    for root, _dirs, files in os.walk(staging_dir):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, staging_dir)
            if rel == "manifest.json":
                continue
            file_entries[rel] = {
                "sha256": _file_sha256(fpath),
                "size_bytes": os.path.getsize(fpath),
            }

    # Enrich DB file entries with counts; read embedding metadata
    embedding_provider = None
    embedding_model = None

    memory_db = os.path.join(staging_dir, "memory", "memory.db")
    if os.path.exists(memory_db):
        conn = sqlite3.connect(memory_db)
        try:
            entry_count = conn.execute(
                "SELECT count(*) FROM entries"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            entry_count = 0
        if "memory/memory.db" in file_entries:
            file_entries["memory/memory.db"]["entry_count"] = entry_count
        try:
            row = conn.execute(
                "SELECT value FROM _metadata WHERE key='embedding_provider'"
            ).fetchone()
            if row:
                embedding_provider = row[0]
            row = conn.execute(
                "SELECT value FROM _metadata WHERE key='embedding_model'"
            ).fetchone()
            if row:
                embedding_model = row[0]
        except sqlite3.OperationalError:
            pass  # _metadata table doesn't exist
        conn.close()

    entities_db = os.path.join(staging_dir, "entities", "entities.db")
    if os.path.exists(entities_db):
        conn = sqlite3.connect(entities_db)
        try:
            entity_count = conn.execute(
                "SELECT count(*) FROM entities"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            entity_count = 0
        try:
            wp_count = conn.execute(
                "SELECT count(*) FROM workflow_phases"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            wp_count = 0
        if "entities/entities.db" in file_entries:
            file_entries["entities/entities.db"]["entity_count"] = entity_count
            file_entries["entities/entities.db"]["workflow_phases_count"] = wp_count
        conn.close()

    manifest = {
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "plugin_version": args.plugin_version,
        "export_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_platform": f"{sys.platform}-{platform.machine()}",
        "python_version": platform.python_version(),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "files": file_entries,
    }

    # Write manifest.json to staging dir
    manifest_path = os.path.join(staging_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Output to stdout
    _json_out(manifest)


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a migration bundle directory."""
    bundle_dir = args.bundle_dir
    manifest_path = os.path.join(bundle_dir, "manifest.json")

    # Read manifest
    with open(manifest_path) as f:
        manifest = json.load(f)

    errors: list[str] = []

    # Check schema version
    schema_version = manifest.get("schema_version", 0)
    if schema_version > SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"Unsupported schema version {schema_version} "
            f"(max supported: {SUPPORTED_SCHEMA_VERSION})"
        )
        _json_out({"valid": False, "errors": errors})
        sys.exit(1)

    # Verify checksums for each listed file
    file_entries = manifest.get("files", {})
    checksum_mismatch = False
    for rel_path, file_info in file_entries.items():
        expected_sha = file_info.get("sha256", "")
        fpath = os.path.join(bundle_dir, rel_path)
        if not os.path.exists(fpath):
            errors.append(f"Missing file: {rel_path}")
            checksum_mismatch = True
            continue
        if _file_sha256(fpath) != expected_sha:
            errors.append(f"Checksum mismatch: {rel_path}")
            checksum_mismatch = True

    if checksum_mismatch:
        _json_out({"valid": False, "errors": errors})
        sys.exit(3)

    # Check for unexpected files (not in manifest and not manifest.json)
    for root, _dirs, files in os.walk(bundle_dir):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, bundle_dir)
            if rel == "manifest.json":
                continue
            if rel not in file_entries:
                errors.append(f"Unexpected file: {rel}")

    valid = len(errors) == 0
    _json_out({"valid": valid, "errors": errors})


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
        # Uses parameterized query to avoid SQL injection from type_id values
        if new_type_ids:
            for (tid,) in new_type_ids:
                dst.execute("""
                    UPDATE main.entities
                    SET parent_uuid = (
                        SELECT uuid FROM main.entities AS parent
                        WHERE parent.type_id = main.entities.parent_type_id
                    )
                    WHERE type_id = ?
                      AND parent_uuid IS NULL
                      AND parent_type_id IS NOT NULL
                """, (tid,))

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
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

            if integrity != "ok":
                _json_out({"ok": False, "actual_count": 0, "integrity": integrity})
                sys.exit(1)

            actual_count = conn.execute(
                f"SELECT count(*) FROM [{args.table}]"
            ).fetchone()[0]
        finally:
            conn.close()
    except SystemExit:
        raise
    except Exception as e:
        _json_out({"ok": False, "actual_count": 0, "integrity": str(e)})
        sys.exit(1)

    # If expected_count is 0, skip the comparison (count-only mode)
    ok = args.expected_count == 0 or actual_count == args.expected_count

    _json_out({
        "ok": ok,
        "actual_count": actual_count,
        "integrity": integrity,
    })


def cmd_info(args: argparse.Namespace) -> None:
    """Display information from a migration manifest."""
    with open(args.manifest_path) as f:
        manifest = json.load(f)
    _json_out(manifest)


def cmd_check_embeddings(args: argparse.Namespace) -> None:
    """Check embedding consistency between manifest and destination DB."""
    with open(args.manifest_path) as f:
        manifest = json.load(f)

    src_provider = manifest.get("embedding_provider")

    # Null provider in bundle — skip check
    if src_provider is None:
        _json_out({"mismatch": False})
        return

    # Read dst _metadata table
    conn = sqlite3.connect(args.dst_memory_db)
    try:
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key='embedding_provider'"
        ).fetchone()
        dst_provider = row[0] if row else None
    except sqlite3.OperationalError:
        # _metadata table doesn't exist (fresh machine)
        _json_out({"mismatch": False})
        return
    finally:
        conn.close()

    if dst_provider is None or src_provider == dst_provider:
        _json_out({"mismatch": False})
    else:
        _json_out({
            "mismatch": True,
            "warning": (
                f"Embedding provider mismatch: bundle uses '{src_provider}' "
                f"but destination uses '{dst_provider}'. "
                "Cosine similarity may be degraded."
            ),
        })


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
