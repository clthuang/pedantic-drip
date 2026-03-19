"""Backfill CLI: import markdown entries from all registered projects and generate embeddings."""
from __future__ import annotations

import argparse
import os
import sys

_lib_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _lib_dir not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _lib_dir)

from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import create_provider
from semantic_memory.importer import MarkdownImporter
from semantic_memory.writer import _check_provider_migration, _process_pending_embeddings


def _read_registry(registry_path: str) -> list[str]:
    """Read project paths from registry file. Skips comments and missing dirs."""
    if not os.path.isfile(registry_path):
        return []
    paths: list[str] = []
    with open(registry_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and os.path.isdir(line):
                paths.append(line)
    return paths


def _discover_knowledge_bank_projects(
    base_dirs: list[str] | None = None,
) -> list[str]:
    """Scan for directories with a knowledge-bank/ under *base_dirs*.

    Defaults to ``[~/projects]`` when *base_dirs* is ``None``.
    Checks both ``docs/knowledge-bank/`` and any other ``*/knowledge-bank/``
    patterns one level deep.
    """
    if base_dirs is None:
        base_dirs = [os.path.expanduser("~/projects")]
    found: list[str] = []
    for base_dir in base_dirs:
        base_dir = os.path.expanduser(base_dir.strip())
        if not os.path.isdir(base_dir):
            continue
        for name in sorted(os.listdir(base_dir)):
            candidate = os.path.join(base_dir, name)
            if os.path.isdir(candidate):
                kb = os.path.join(candidate, "docs", "knowledge-bank")
                if os.path.isdir(kb):
                    if candidate not in found:
                        found.append(candidate)
    return found


def backfill(
    project_root: str,
    global_store: str,
    registry_path: str | None = None,
    *,
    discover: bool = True,
    reset_observation_counts: bool = False,
) -> dict:
    """Run the full backfill pipeline. Returns stats dict."""
    db_path = os.path.join(global_store, "memory.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = MemoryDatabase(db_path)

    # Read config for project-aware settings
    config = read_config(project_root)
    artifacts_root = str(config.get("artifacts_root", "docs"))

    try:
        # 0. Optionally reset inflated observation counts
        if reset_observation_counts:
            db._conn.execute(
                "UPDATE entries SET observation_count = 1 WHERE source = 'import'"
            )
            db._conn.commit()
            print("  Reset observation_count to 1 for all imported entries")

        # 1. Determine which projects to scan
        project_roots: list[str] = []
        if registry_path:
            project_roots = _read_registry(registry_path)
        if discover:
            # Use configured scan dirs or default to ~/projects
            scan_dirs_raw = str(config.get("backfill_scan_dirs", ""))
            base_dirs: list[str] | None = None
            if scan_dirs_raw:
                base_dirs = [d.strip() for d in scan_dirs_raw.split(",") if d.strip()]
            for p in _discover_knowledge_bank_projects(base_dirs):
                if p not in project_roots:
                    project_roots.append(p)
        if project_root not in project_roots:
            project_roots.append(project_root)

        # 2. Count before
        before = db.count_entries()

        # 3. Import from all registered projects
        importer = MarkdownImporter(db, artifacts_root=artifacts_root)
        total_imported = 0
        total_skipped = 0
        for proj in project_roots:
            result = importer.import_all(proj, global_store)
            proj_imported = result["imported"]
            proj_skipped = result["skipped"]
            if proj_imported > 0 or proj_skipped > 0:
                print(f"  {proj}: {proj_imported} imported, {proj_skipped} skipped")
            total_imported += proj_imported
            total_skipped += proj_skipped

        after = db.count_entries()
        new_entries = after - before

        # 4. Create provider and generate embeddings
        provider = create_provider(config)

        embedded = 0
        if provider:
            _check_provider_migration(db, config, provider)

            # Process ALL pending in batches of 50
            while True:
                pending = db.count_entries_without_embedding()
                if pending == 0:
                    break
                count = _process_pending_embeddings(db, provider)
                embedded += count
                print(f"  Embedded {count} entries ({pending - count} remaining)")
                if count == 0:
                    break  # All failed, stop
        else:
            print("  No embedding provider available — skipping embedding generation")

        # 5. Final stats
        total = db.count_entries()
        with_embedding = total - db.count_entries_without_embedding()

        return {
            "projects_scanned": len(project_roots),
            "imported": total_imported,
            "skipped": total_skipped,
            "new_entries": new_entries,
            "embedded": embedded,
            "total": total,
            "with_embedding": with_embedding,
            "provider": provider.provider_name if provider else None,
            "model": provider.model_name if provider else None,
        }
    finally:
        db.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Backfill semantic memory from knowledge bank markdown files")
    parser.add_argument(
        "--project-root",
        default=os.getcwd(),
        help="Current project root (for config reading)",
    )
    parser.add_argument(
        "--global-store",
        required=True,
        help="Path to ~/.claude/pd/memory",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Path to projects.txt (optional; if omitted, only imports current project)",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Skip auto-discovery of projects under ~/projects",
    )
    parser.add_argument(
        "--reset-observation-counts",
        action="store_true",
        help="Reset observation_count to 1 for all imported entries (one-time fix)",
    )
    args = parser.parse_args()

    stats = backfill(
        project_root=args.project_root,
        global_store=args.global_store,
        registry_path=args.registry,
        discover=not args.no_discover,
        reset_observation_counts=args.reset_observation_counts,
    )

    print()
    print(f"  Projects scanned: {stats['projects_scanned']}")
    print(f"  Entries imported:  {stats['imported']} ({stats['new_entries']} new, {stats['skipped']} skipped)")
    print(f"  Embeddings added:  {stats['embedded']}")
    print(f"  Total entries:     {stats['total']} ({stats['with_embedding']} with embeddings)")
    if stats["provider"]:
        print(f"  Provider:          {stats['provider']} ({stats['model']})")


if __name__ == "__main__":
    main()
