"""Markdown importer for the semantic memory system.

Scans project-local and global knowledge bank markdown files, parses
entries using the same logic as memory.py, and upserts them into the
semantic memory database with source='import'.  Embeddings and keywords
are left NULL for deferred processing on the next write-path.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from semantic_memory import content_hash, source_hash

if TYPE_CHECKING:
    from semantic_memory.database import MemoryDatabase


# Category filename -> category name mapping.
CATEGORIES = [
    ("anti-patterns.md", "anti-patterns"),
    ("patterns.md", "patterns"),
    ("heuristics.md", "heuristics"),
]


class MarkdownImporter:
    """Import knowledge bank markdown files into the semantic memory database.

    Parameters
    ----------
    db:
        The MemoryDatabase instance to upsert entries into.
    """

    def __init__(self, db: MemoryDatabase, artifacts_root: str = "docs") -> None:
        self._db = db
        self._artifacts_root = artifacts_root

    def import_all(self, project_root: str, global_store: str) -> dict:
        """Import entries from local and global knowledge bank files.

        Scans ``{project_root}/{artifacts_root}/knowledge-bank/*.md`` (local)
        and ``{global_store}/*.md`` (global) for each known category file.

        Returns ``{"imported": N, "skipped": N}`` where *imported* counts
        entries actually upserted and *skipped* counts hash-matched entries.
        """
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        imported = 0
        skipped = 0

        local_kb = os.path.join(project_root, self._artifacts_root, "knowledge-bank")
        for filename, category in CATEGORIES:
            filepath = os.path.join(local_kb, filename)
            entries = self._parse_markdown_entries(filepath, category)
            for entry in entries:
                result = self._upsert_entry(entry, project_root, now)
                if result == "skipped":
                    skipped += 1
                else:
                    imported += 1

        for filename, category in CATEGORIES:
            filepath = os.path.join(global_store, filename)
            entries = self._parse_markdown_entries(filepath, category)
            for entry in entries:
                result = self._upsert_entry(entry, project_root, now)
                if result == "skipped":
                    skipped += 1
                else:
                    imported += 1

        return {"imported": imported, "skipped": skipped}

    def _upsert_entry(self, parsed: dict, project_root: str, now: str) -> str:
        """Convert a parsed entry dict into the DB format and upsert.

        Returns ``"inserted"``, ``"updated"``, or ``"skipped"``.
        """
        entry_id = parsed["content_hash"]
        raw_chunk = parsed.get("raw_chunk", "")
        sh = source_hash(raw_chunk) if raw_chunk else None

        # Check if the source content is unchanged
        if sh is not None:
            existing_hash = self._db.get_source_hash(entry_id)
            if existing_hash == sh:
                return "skipped"

        is_new = self._db.get_entry(entry_id) is None

        entry = {
            "id": entry_id,
            "name": parsed["name"],
            "description": parsed["description"],
            "reasoning": None,
            "category": parsed["category"],
            "keywords": "[]",
            "source": "import",
            "source_project": project_root,
            "references": None,
            "observation_count": parsed["observation_count"],
            "confidence": parsed["confidence"],
            "embedding": None,
            "created_at": now,
            "updated_at": now,
            "source_hash": sh,
            "created_timestamp_utc": datetime.now(tz=timezone.utc).timestamp(),
        }
        self._db.upsert_entry(entry)
        return "inserted" if is_new else "updated"

    def _parse_markdown_entries(
        self, filepath: str, category: str
    ) -> list[dict]:
        """Parse a knowledge bank markdown file into entry dicts.

        Uses the same logic as ``memory.py:parse_entries()`` to ensure
        consistent parsing across the legacy and semantic memory paths.
        """
        if not os.path.isfile(filepath):
            return []

        with open(filepath, "r") as f:
            raw = f.read()

        # Strip HTML comments
        raw = re.sub(r"<!--[\s\S]*?-->", "", raw)

        # Split on ### headings
        chunks = re.split(r"(?m)^### ", raw)
        entries: list[dict] = []

        for chunk in chunks:
            if not chunk.strip():
                continue

            first_line = chunk.split("\n", 1)[0]
            if first_line.startswith("## ") or first_line.startswith("# "):
                continue

            lines = chunk.split("\n")
            header_line = lines[0].strip()

            # Strip type prefix
            name = header_line
            for prefix in ("Anti-Pattern: ", "Pattern: "):
                if name.startswith(prefix):
                    name = name[len(prefix):]
                    break

            # Partition into description and metadata
            desc_lines: list[str] = []
            meta_lines: list[str] = []
            in_metadata = False
            for line in lines[1:]:
                if line.startswith("- ") and not in_metadata:
                    in_metadata = True
                if in_metadata:
                    meta_lines.append(line)
                else:
                    desc_lines.append(line)

            description = "\n".join(desc_lines).strip()

            # Extract metadata with defaults
            obs_count = 1
            confidence = "medium"

            for ml in meta_lines:
                ml_lower = ml.lower().strip()
                if ml_lower.startswith("- observation count:"):
                    try:
                        obs_count = int(ml.split(":", 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif ml_lower.startswith("- confidence:"):
                    val = ml.split(":", 1)[1].strip().lower()
                    if val in {"high", "medium", "low"}:
                        confidence = val

            entries.append({
                "name": name,
                "category": category,
                "description": description,
                "observation_count": obs_count,
                "confidence": confidence,
                "content_hash": content_hash(description),
                "raw_chunk": chunk.strip(),
            })

        return entries
