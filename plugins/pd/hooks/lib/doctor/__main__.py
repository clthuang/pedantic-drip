"""CLI entry point for pd:doctor diagnostic tool.

Usage:
    python -m doctor --entities-db PATH --memory-db PATH --project-root PATH [--artifacts-root PATH]
    python -m doctor ... --fix          # Apply safe fixes and re-run diagnostics
    python -m doctor ... --fix --dry-run  # Show what would be fixed without applying

Outputs a single JSON object to stdout. Exit code is always 0.
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pd:doctor diagnostic tool",
    )
    parser.add_argument(
        "--entities-db",
        required=True,
        help="Path to entities.db",
    )
    parser.add_argument(
        "--memory-db",
        required=True,
        help="Path to memory.db",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Path to project root directory",
    )
    parser.add_argument(
        "--artifacts-root",
        default=None,
        help="Path to artifacts root (default: resolved from config or 'docs')",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply safe fixes after diagnostics",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without applying (use with --fix)",
    )

    args = parser.parse_args()

    # Resolve artifacts_root: CLI arg > config > "docs"
    artifacts_root = args.artifacts_root
    if artifacts_root is None:
        try:
            from semantic_memory.config import read_config
            config = read_config(args.project_root)
            artifacts_root = str(config.get("artifacts_root", "docs"))
        except Exception:
            artifacts_root = "docs"

    from doctor import run_diagnostics

    report = run_diagnostics(
        entities_db_path=args.entities_db,
        memory_db_path=args.memory_db,
        artifacts_root=artifacts_root,
        project_root=args.project_root,
    )

    if not args.fix:
        # Default: diagnostic only (backward compatible)
        output = {"diagnostic": report.to_dict()}
    else:
        from doctor.fixer import apply_fixes

        fix_report = apply_fixes(
            report=report,
            entities_db_path=args.entities_db,
            memory_db_path=args.memory_db,
            artifacts_root=artifacts_root,
            project_root=args.project_root,
            dry_run=args.dry_run,
        )

        output = {
            "diagnostic": report.to_dict(),
            "fixes": fix_report.to_dict(),
        }

        if not args.dry_run:
            # Re-run diagnostics to verify fixes
            post_report = run_diagnostics(
                entities_db_path=args.entities_db,
                memory_db_path=args.memory_db,
                artifacts_root=artifacts_root,
                project_root=args.project_root,
            )
            output["post_fix"] = post_report.to_dict()

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
