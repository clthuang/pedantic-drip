"""Injector CLI for the semantic memory system.

Reads the memory database, performs hybrid retrieval and ranking,
then outputs formatted markdown for injection into the Claude context.
All errors go to stderr; stdout is never corrupted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Ensure semantic_memory package is on the path when run as a script.
_lib_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _lib_dir not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _lib_dir)

from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import create_provider
from semantic_memory.importer import MarkdownImporter
from semantic_memory.ranking import RankingEngine
from semantic_memory.retrieval import RetrievalPipeline
from semantic_memory.retrieval_types import RetrievalResult

# ---------------------------------------------------------------------------
# Output formatting constants
# ---------------------------------------------------------------------------

# Canonical category ordering for output sections.
CATEGORY_ORDER = ["anti-patterns", "heuristics", "patterns"]

CATEGORY_HEADERS = {
    "anti-patterns": "### Anti-Patterns to Avoid",
    "heuristics": "### Heuristics",
    "patterns": "### Patterns to Follow",
}

CATEGORY_PREFIXES = {
    "anti-patterns": "### Anti-Pattern: ",
    "patterns": "### Pattern: ",
    "heuristics": "### ",
}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_output(
    *,
    selected: list[dict],
    result: RetrievalResult,
    total_count: int,
    pending: int,
    model: str,
) -> str:
    """Format selected entries into the I10 injection output.

    Returns an empty string when *selected* is empty.
    """
    if not selected:
        return ""

    context_query = result.context_query
    query_display = (
        (context_query[:30] + "...")
        if context_query and len(context_query) > 30
        else (context_query or "none")
    )

    # Build diagnostic line
    if pending > 0:
        diag = (
            f"*Memory: {len(selected)} entries from {total_count} "
            f"| semantic: active "
            f"(vector={result.vector_candidate_count}, "
            f"fts5={result.fts5_candidate_count}, "
            f"pending_embedding={pending}) "
            f"| context: \"{query_display}\" "
            f"| model: {model}*"
        )
    else:
        diag = (
            f"*Memory: {len(selected)} entries from {total_count} "
            f"| semantic: active "
            f"(vector={result.vector_candidate_count}, "
            f"fts5={result.fts5_candidate_count}) "
            f"| context: \"{query_display}\" "
            f"| model: {model}*"
        )

    # Group entries by category
    by_category: dict[str, list[dict]] = {}
    for entry in selected:
        cat = entry.get("category", "unknown")
        by_category.setdefault(cat, [])
        by_category[cat].append(entry)

    # Build body sections in canonical order
    sections: list[str] = []
    for cat in CATEGORY_ORDER:
        cat_entries = by_category.get(cat)
        if not cat_entries:
            continue

        section_lines: list[str] = []
        section_lines.append(CATEGORY_HEADERS[cat])

        prefix = CATEGORY_PREFIXES[cat]
        for entry in cat_entries:
            section_lines.append(f"{prefix}{entry['name']}")
            section_lines.append(entry["description"])
            section_lines.append(f"- Observation count: {entry['observation_count']}")
            section_lines.append(f"- Confidence: {entry['confidence']}")
            section_lines.append("")

        sections.append("\n".join(section_lines))

    body = "\n".join(sections)

    return f"## Engineering Memory (from knowledge bank)\n\n{diag}\n\n{body}\n---\n"


# ---------------------------------------------------------------------------
# Injection tracking
# ---------------------------------------------------------------------------


def write_tracking(
    *,
    global_store: str,
    selected: list[dict],
    result: RetrievalResult,
    total_count: int,
    model: str,
) -> None:
    """Write .last-injection.json with semantic-specific diagnostics."""
    now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tracking = {
        "timestamp": now_iso,
        "mode": "semantic",
        "entries_injected": len(selected),
        "total_entries": total_count,
        "model": model,
        "retrieval": {
            "vector_candidates": result.vector_candidate_count,
            "fts5_candidates": result.fts5_candidate_count,
            "context_query": result.context_query,
        },
    }
    tracking_path = os.path.join(global_store, ".last-injection.json")
    try:
        with open(tracking_path, "w") as fh:
            json.dump(tracking, fh, indent=2)
            fh.write("\n")
    except OSError as exc:
        print(f"semantic_memory: tracking write failed: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Run the injector pipeline.

    Parameters
    ----------
    argv:
        Command-line arguments (defaults to ``sys.argv[1:]``).
        Accepts ``--project-root``, ``--limit``, and ``--global-store``.
    """
    parser = argparse.ArgumentParser(description="Semantic memory injector")
    parser.add_argument("--project-root", required=True, help="Path to the project root")
    parser.add_argument("--limit", type=int, default=None, help="Max entries to inject")
    parser.add_argument("--global-store", required=True, help="Path to global knowledge store")
    args = parser.parse_args(argv)

    project_root: str = args.project_root
    global_store: str = args.global_store

    db = None
    try:
        config = read_config(project_root)
        limit = args.limit if args.limit is not None else int(config.get("memory_injection_limit", 20))
        model = str(config.get("memory_embedding_model", "none"))

        # Open database (create dirs if needed)
        db_path = os.path.join(global_store, "memory.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = MemoryDatabase(db_path)

        # If DB is empty, run initial import
        if db.count_entries() == 0:
            importer = MarkdownImporter(db)
            importer.import_all(project_root, global_store)

        # Create embedding provider (may return None)
        provider = create_provider(config)

        # Retrieve
        pipeline = RetrievalPipeline(db, provider, config)
        context_query = pipeline.collect_context(project_root)
        result = pipeline.retrieve(context_query)

        # Rank
        all_entries = db.get_all_entries()
        entries_by_id = {e["id"]: e for e in all_entries}
        engine = RankingEngine(config)
        selected = engine.rank(result, entries_by_id, limit)

        # Recall tracking
        if selected:
            selected_ids = [e["id"] for e in selected]
            now_iso = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            db.update_recall(selected_ids, now_iso)

        # Format and output
        total_count = db.count_entries()
        pending = int(db.get_metadata("pending_embeddings") or "0")
        output = format_output(
            selected=selected,
            result=result,
            total_count=total_count,
            pending=pending,
            model=model,
        )
        if output:
            sys.stdout.write(output)

        # Write tracking file
        write_tracking(
            global_store=global_store,
            selected=selected,
            result=result,
            total_count=total_count,
            model=model,
        )

    except Exception as exc:
        print(f"semantic_memory: error: {exc}", file=sys.stderr)
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    main()
