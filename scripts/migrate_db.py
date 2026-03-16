#!/usr/bin/env python3
"""migrate_db.py — CLI tool for iflow database migration operations.

All subcommands output JSON to stdout. Errors go to stderr.
Exit 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import json
import sys

SUPPORTED_SCHEMA_VERSION = 1


def _json_stub() -> None:
    """Print empty JSON object stub and exit successfully."""
    json.dump({}, sys.stdout)
    print()  # trailing newline


def cmd_backup(_args: argparse.Namespace) -> None:
    """Backup a database table."""
    _json_stub()


def cmd_manifest(_args: argparse.Namespace) -> None:
    """Generate a migration manifest for a staging directory."""
    _json_stub()


def cmd_validate(_args: argparse.Namespace) -> None:
    """Validate a migration bundle directory."""
    _json_stub()


def cmd_merge_memory(_args: argparse.Namespace) -> None:
    """Merge memory entries from source to destination database."""
    _json_stub()


def cmd_merge_entities(_args: argparse.Namespace) -> None:
    """Merge entity records from source to destination database."""
    _json_stub()


def cmd_verify(_args: argparse.Namespace) -> None:
    """Verify row counts in a database table after migration."""
    _json_stub()


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
    args.func(args)


if __name__ == "__main__":
    main()
