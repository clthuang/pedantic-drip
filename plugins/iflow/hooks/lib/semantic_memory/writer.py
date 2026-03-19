"""Writer CLI for the semantic memory system.

Upserts knowledge bank entries into the semantic memory database,
generates embeddings when a provider is available, and processes
pending embedding batches.
"""
import os
import sys

_lib_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _lib_dir not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _lib_dir)

import argparse
import json
from datetime import datetime, timezone

from semantic_memory import content_hash, source_hash
from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import create_provider

from semantic_memory import VALID_CATEGORIES


def _validate_entry(entry: dict) -> str | None:
    """Validate entry fields.  Returns an error message or None if valid."""
    name = entry.get("name")
    if not name or not str(name).strip():
        return "Validation error: 'name' is required and must be non-empty."

    description = entry.get("description")
    if not description or not str(description).strip():
        return "Validation error: 'description' is required and must be non-empty."

    category = entry.get("category")
    if category not in VALID_CATEGORIES:
        return (
            f"Validation error: 'category' must be one of "
            f"{sorted(VALID_CATEGORIES)}, got {category!r}."
        )

    return None


def _build_db_entry(entry: dict, entry_id: str, now: str, *, project_root: str = "") -> dict:
    """Convert a user-supplied entry dict to the DB row format."""
    keywords = entry.get("keywords")
    if isinstance(keywords, list):
        keywords = json.dumps(keywords)
    elif keywords is None:
        keywords = "[]"

    references = entry.get("references")
    if isinstance(references, list):
        references = json.dumps(references)

    return {
        "id": entry_id,
        "name": entry["name"],
        "description": entry["description"],
        "reasoning": entry.get("reasoning"),
        "category": entry["category"],
        "keywords": keywords,
        "source": entry.get("source", "manual"),
        "source_project": entry.get("source_project") or project_root,
        "references": references,
        "confidence": entry.get("confidence", "medium"),
        "created_at": now,
        "updated_at": now,
        "source_hash": source_hash(entry["description"]),
        "created_timestamp_utc": datetime.now(tz=timezone.utc).timestamp(),
    }


def _merge_keywords(db: MemoryDatabase, entry_id: str, new_keywords: list | None) -> None:
    """Merge new keywords into an existing entry's keyword list."""
    if not new_keywords:
        return

    existing = db.get_entry(entry_id)
    if existing is None:
        return

    existing_kw_raw = existing.get("keywords")
    existing_kw: list[str] = []
    if existing_kw_raw:
        try:
            existing_kw = json.loads(existing_kw_raw)
        except (json.JSONDecodeError, TypeError):
            existing_kw = []

    # Merge: add new keywords that aren't already present
    merged = list(existing_kw)
    seen = set(existing_kw)
    for kw in new_keywords:
        if kw not in seen:
            merged.append(kw)
            seen.add(kw)

    if merged != existing_kw:
        db.update_keywords(entry_id, json.dumps(merged))


def _check_provider_migration(
    db: MemoryDatabase,
    config: dict,
    provider: object | None,
) -> None:
    """Check if embedding provider/model changed and clear embeddings if so (TD9)."""
    stored_provider = db.get_metadata("embedding_provider")
    stored_model = db.get_metadata("embedding_model")
    current_provider = config.get("memory_embedding_provider", "")
    current_model = config.get("memory_embedding_model", "")

    if stored_provider and (
        stored_provider != current_provider or stored_model != current_model
    ):
        db.clear_all_embeddings()
        print(
            f"Embedding provider changed from {stored_provider}/{stored_model} "
            f"to {current_provider}/{current_model}. Cleared all embeddings.",
            file=sys.stderr,
        )

    if provider:
        db.set_metadata("embedding_provider", current_provider)
        db.set_metadata("embedding_model", current_model)
        db.set_metadata("embedding_dimensions", str(provider.dimensions))


def _embed_text_for_entry(entry: dict) -> str:
    """Build the text string used to generate an embedding for an entry."""
    parts = [entry.get("name", ""), entry.get("description", "")]
    keywords_raw = entry.get("keywords")
    if keywords_raw:
        try:
            kw_list = json.loads(keywords_raw) if isinstance(keywords_raw, str) else keywords_raw
            parts.append(" ".join(kw_list))
        except (json.JSONDecodeError, TypeError):
            pass
    reasoning = entry.get("reasoning")
    if reasoning:
        parts.append(reasoning)
    return " ".join(parts)


def _process_pending_embeddings(db: MemoryDatabase, provider: object) -> int:
    """Generate embeddings for entries that don't have one yet.

    Returns the number of entries processed.  Also updates the
    ``pending_embeddings`` metadata key so the injector diagnostic
    line reflects the true count.
    """
    pending = db.get_entries_without_embedding(limit=50)
    count = 0
    for entry in pending:
        text = _embed_text_for_entry(entry)
        try:
            embedding = provider.embed(text, task_type="document")
            db.update_embedding(entry["id"], embedding.tobytes())
            count += 1
        except Exception as exc:
            print(
                f"Warning: embedding failed for {entry['id']}: {exc}",
                file=sys.stderr,
            )

    # Update pending count so the injector diagnostic is accurate.
    remaining = db.count_entries_without_embedding()
    db.set_metadata("pending_embeddings", str(remaining))

    return count


def main() -> None:
    """CLI entry point for the writer."""
    parser = argparse.ArgumentParser(description="Semantic memory writer CLI")
    parser.add_argument(
        "--action",
        required=True,
        choices=["upsert", "delete"],
        help="Action to perform",
    )
    parser.add_argument(
        "--global-store",
        required=True,
        help="Path to the global store directory",
    )
    parser.add_argument(
        "--entry-json",
        help="Entry data as a JSON string",
    )
    parser.add_argument(
        "--entry-file",
        help="Path to a file containing entry JSON",
    )
    parser.add_argument(
        "--entry-id",
        help="Entry ID (required for --action delete)",
    )
    parser.add_argument(
        "--project-root",
        default=os.getcwd(),
        help="Project root for config reading (default: cwd)",
    )

    args = parser.parse_args()

    # Post-parse validation: --entry-id required for delete
    if args.action == "delete" and not args.entry_id:
        parser.error("--entry-id required for delete")

    # Handle delete action
    if args.action == "delete":
        db_path = os.path.join(args.global_store, "memory.db")
        try:
            db = MemoryDatabase(db_path)
        except Exception as exc:
            print(f"Error opening database: {exc}", file=sys.stderr)
            sys.exit(2)
        try:
            db.delete_entry(args.entry_id)
            print(f"Deleted memory entry: {args.entry_id}")
            sys.exit(0)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)
        finally:
            db.close()

    # Read entry from JSON string or file
    if args.entry_json:
        raw_json = args.entry_json
    elif args.entry_file:
        try:
            with open(args.entry_file, "r") as f:
                raw_json = f.read()
        except OSError as exc:
            print(f"Error reading entry file: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print(
            "Error: one of --entry-json or --entry-file is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        entry_data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate
    error = _validate_entry(entry_data)
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)

    # Compute content hash as ID
    entry_id = content_hash(entry_data["description"])
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Open database
    db_path = os.path.join(args.global_store, "memory.db")
    try:
        db = MemoryDatabase(db_path)
    except Exception as exc:
        print(f"Error opening database: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        # Read config and create embedding provider
        config = read_config(args.project_root)
        provider = create_provider(config)

        # Check provider migration (TD9)
        _check_provider_migration(db, config, provider)

        # Check if entry already exists (for keyword merging)
        existing = db.get_entry(entry_id)

        # Build and upsert entry
        db_entry = _build_db_entry(entry_data, entry_id, now,
                                   project_root=args.project_root)
        db.upsert_entry(db_entry)

        # Merge keywords if this was an update
        if existing is not None:
            new_keywords = entry_data.get("keywords")
            if isinstance(new_keywords, list):
                _merge_keywords(db, entry_id, new_keywords)

        # Generate embedding for this entry if provider is available
        if provider:
            stored = db.get_entry(entry_id)
            text = _embed_text_for_entry(stored)
            try:
                embedding = provider.embed(text, task_type="document")
                db.update_embedding(entry_id, embedding.tobytes())
            except Exception as exc:
                print(
                    f"Warning: embedding failed for {entry_id}: {exc}",
                    file=sys.stderr,
                )

        # Process pending embeddings batch
        if provider:
            _process_pending_embeddings(db, provider)

        print(f"Stored: {entry_data['name']} (id: {entry_id})")
        sys.exit(0)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
