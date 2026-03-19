#!/usr/bin/env python3
"""Memory injection module for pd session-start hook.

Reads knowledge bank entries from project-local and global stores,
deduplicates, selects top entries by priority, and outputs formatted
markdown for injection into session context.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone


CATEGORIES = [
    ("anti-patterns.md", "anti-patterns"),
    ("patterns.md", "patterns"),
    ("heuristics.md", "heuristics"),
]

CATEGORY_PRIORITY = ["anti-patterns", "heuristics", "patterns"]

CONFIDENCE_MAP = {"high": 3, "medium": 2, "low": 1}

CATEGORY_HEADERS = {
    "anti-patterns": "### Anti-Patterns to Avoid",
    "heuristics": "### Heuristics",
    "patterns": "### Patterns to Follow",
}


def content_hash(text):
    """SHA-256 of normalized description text, first 16 hex chars."""
    normalized = " ".join(text.lower().strip().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def parse_entries(filepath, category):
    """Parse knowledge bank file into entry dicts using split-and-partition."""
    if not os.path.isfile(filepath):
        return []

    with open(filepath, "r") as f:
        raw = f.read()

    # Strip HTML comments (removes trailing example template blocks)
    raw = re.sub(r"<!--[\s\S]*?-->", "", raw)

    # Split on lines starting with ###
    chunks = re.split(r"(?m)^### ", raw)
    entries = []

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        # Skip section headers (## lines) and non-entry chunks
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
        desc_lines = []
        meta_lines = []
        in_metadata = False
        for line in lines[1:]:
            if line.startswith("- ") and not in_metadata:
                in_metadata = True
            if in_metadata:
                meta_lines.append(line)
            else:
                desc_lines.append(line)

        description = "\n".join(desc_lines).strip()
        metadata_text = "\n".join(meta_lines).strip()

        # Extract sort-relevant metadata with defaults
        obs_count = 1
        confidence = "medium"
        last_observed = None

        for ml in meta_lines:
            ml_lower = ml.lower().strip()
            if ml_lower.startswith("- observation count:"):
                try:
                    obs_count = int(ml.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
            elif ml_lower.startswith("- confidence:"):
                val = ml.split(":", 1)[1].strip().lower()
                if val in CONFIDENCE_MAP:
                    confidence = val
            elif ml_lower.startswith("- last observed:"):
                last_observed = ml.split(":", 1)[1].strip()

        entries.append({
            "name": name,
            "category": category,
            "description": description,
            "metadata_text": metadata_text,
            "header_line": "### " + header_line,
            "observation_count": obs_count,
            "confidence": confidence,
            "last_observed": last_observed,
            "file_position": i,
            "content_hash": content_hash(description),
        })

    return entries


def deduplicate(entries):
    """Deduplicate by content hash, keep version with higher observation count."""
    by_hash = {}

    for entry in entries:
        h = entry["content_hash"]
        if h not in by_hash or entry["observation_count"] > by_hash[h]["observation_count"]:
            by_hash[h] = entry

    return list(by_hash.values())


def _sort_key(entry):
    """Sort key: observation count desc, confidence desc, recency desc."""
    conf_val = CONFIDENCE_MAP.get(entry["confidence"], 2)
    # For recency: try ISO date first (global), fall back to file position (local)
    recency = 0
    lo = entry.get("last_observed")
    if lo:
        try:
            recency = datetime.fromisoformat(lo.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            recency = entry.get("file_position", 0)
    else:
        recency = entry.get("file_position", 0)

    return (-entry["observation_count"], -conf_val, -recency)


def select_entries(entries, limit):
    """Select top entries respecting category balance and priority."""
    if limit <= 0:
        return []

    # Group by category
    buckets = {}
    for cat in CATEGORY_PRIORITY:
        buckets[cat] = sorted(
            [e for e in entries if e["category"] == cat],
            key=_sort_key,
        )

    non_empty = [cat for cat in CATEGORY_PRIORITY if buckets[cat]]

    if not non_empty:
        return []

    selected = []
    remaining = limit

    # Min-guarantee phase: allocate min(3, size) per category for breadth.
    # Skipped when limit < 3*non_empty (pure priority allocation instead).
    if remaining >= 3 * len(non_empty):
        for cat in non_empty:
            take = min(3, len(buckets[cat]))
            selected.extend(buckets[cat][:take])
            buckets[cat] = buckets[cat][take:]
            remaining -= take

    # Fill remaining by category priority
    for cat in CATEGORY_PRIORITY:
        if remaining <= 0:
            break
        take = min(remaining, len(buckets[cat]))
        selected.extend(buckets[cat][:take])
        remaining -= take

    return selected


def format_output(selected):
    """Format selected entries as markdown block."""
    if not selected:
        return ""

    # Group by category
    by_cat = {}
    for entry in selected:
        by_cat.setdefault(entry["category"], []).append(entry)

    parts = ["## Engineering Memory (from knowledge bank)\n"]

    for cat in CATEGORY_PRIORITY:
        cat_entries = by_cat.get(cat, [])
        if not cat_entries:
            continue
        parts.append(CATEGORY_HEADERS[cat])
        for entry in cat_entries:
            parts.append(entry["header_line"])
            if entry["description"]:
                parts.append(entry["description"])
            if entry["metadata_text"]:
                parts.append(entry["metadata_text"])
            parts.append("")  # blank line between entries

    parts.append("---")
    return "\n".join(parts)


def write_tracking(entries, project_root, global_store):
    """Write .last-injection.json tracking file."""
    os.makedirs(global_store, exist_ok=True)
    tracking_path = os.path.join(global_store, ".last-injection.json")

    local_count = sum(1 for e in entries if e.get("_source") == "local")
    global_count = sum(1 for e in entries if e.get("_source") == "global")

    tracking = {
        "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": os.path.basename(os.path.abspath(project_root)),
        "entries_injected": len(entries),
        "sources": {
            "local": local_count,
            "global": global_count,
        },
        "entry_names": [e["name"] for e in entries],
    }

    with open(tracking_path, "w") as f:
        json.dump(tracking, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Memory injection for pd sessions")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--limit", type=int, required=True, help="Max entries to inject")
    parser.add_argument(
        "--global-store",
        default=os.path.expanduser("~/.claude/pd/memory"),
        help="Global memory store path",
    )
    args = parser.parse_args()

    # Parse local entries
    local_entries = []
    kb_dir = os.path.join(args.project_root, "docs", "knowledge-bank")
    for filename, category in CATEGORIES:
        filepath = os.path.join(kb_dir, filename)
        for entry in parse_entries(filepath, category):
            entry["_source"] = "local"
            local_entries.append(entry)

    # Parse global entries
    global_entries = []
    for filename, category in CATEGORIES:
        filepath = os.path.join(args.global_store, filename)
        for entry in parse_entries(filepath, category):
            entry["_source"] = "global"
            global_entries.append(entry)

    # Deduplicate
    all_entries = deduplicate(local_entries + global_entries)

    # Select
    selected = select_entries(all_entries, args.limit)

    # Format and output
    output = format_output(selected)
    if output:
        print(output)

    # Write tracking (only if entries were selected)
    if selected:
        write_tracking(selected, args.project_root, args.global_store)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"memory.py error: {e}", file=sys.stderr)
        sys.exit(1)
