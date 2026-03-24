"""CLI entry point for pd:doctor diagnostic tool.

Usage:
    python -m doctor --entities-db PATH --memory-db PATH --project-root PATH [--artifacts-root PATH]

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

    print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    main()
