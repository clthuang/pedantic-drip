#!/usr/bin/env python3
"""Feature 110 Task 8.2 — Backfill parser for ``docs/backlog.md``.

Reads the existing ``docs/backlog.md`` file and classifies each row into
the ``format``/``section``/``section_intro``/``subsection`` metadata
shape consumed by ``_project_backlog_md`` (per design TD-10).

Dry-run (default): prints a JSON-line classification summary to stdout
and a human-readable summary to stderr. NO DB writes.

Apply mode (``--apply``): deferred to feature 110 Task 12.4. Currently a
no-op with a warning printed to stderr.

Stdlib-only. Run via the project's plugin venv when possible (matches
the rest of the ``plugins/pd/scripts/`` convention).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Regexes for the two row formats per design TD-10:
#  - Top-level table row: ``| {seq} | {timestamp} | {description} |``
#    where seq is a 5-digit zero-padded integer.
#  - Per-section bullet row: ``- **#{seq}** ...`` (with optional ``~~``
#    strikethrough wrapper).
TABLE_ROW_RE = re.compile(
    r"^\|\s*(?P<id>\d{5})\s*\|\s*(?P<ts>[^|]+?)\s*\|\s*(?P<desc>.*?)\s*\|\s*$"
)
BULLET_ROW_RE = re.compile(
    r"^-\s+(?P<strike>~~)?\*\*#(?P<id>\d{5})\*\*~?~?\s*(?P<desc>.*?)\s*$"
)
H2_RE = re.compile(r"^##\s+(?P<heading>.+?)\s*$")
H3_RE = re.compile(r"^###\s+(?P<heading>.+?)\s*$")


def parse_backlog(text: str) -> list[dict]:
    """Parse ``backlog.md`` text into a list of classification records.

    Each record is a dict with the schema:
      {
        "entity_id": "00400",
        "format": "table_row" | "bullet_item",
        "section": str | None,
        "section_intro": str | None,
        "subsection": str | None,
        "name": str (the description),
      }

    The order of records matches the file order.
    """
    out: list[dict] = []
    lines = text.splitlines()
    current_section: str | None = None
    current_subsection: str | None = None
    pending_intro: str | None = None
    # Intro is "the prose paragraph(s) between a `## ` header and the
    # FIRST item in that section". We accumulate non-blank/non-H3
    # lines after a section header until the first item is reached;
    # the resulting text is attached only to the first item.

    intro_buffer: list[str] = []
    section_first_item_seen = False

    for line in lines:
        # H2 boundary: opens a new section. If it starts with "From "
        # we record it; otherwise (e.g., the top "# Backlog" heading
        # is H1, not H2) we keep the section empty.
        m_h2 = H2_RE.match(line)
        if m_h2:
            heading = m_h2.group("heading")
            current_section = heading
            current_subsection = None
            intro_buffer = []
            section_first_item_seen = False
            continue

        m_h3 = H3_RE.match(line)
        if m_h3:
            current_subsection = m_h3.group("heading")
            continue

        # Table row (top-level table only — bullet sections don't
        # have pipe-table rows in the existing file).
        m_table = TABLE_ROW_RE.match(line)
        if m_table and current_section is None:
            out.append({
                "entity_id": m_table.group("id"),
                "format": "table_row",
                "section": None,
                "section_intro": None,
                "subsection": None,
                "name": m_table.group("desc"),
            })
            continue

        m_bullet = BULLET_ROW_RE.match(line)
        if m_bullet and current_section is not None:
            # First item in this section: flush intro buffer.
            attached_intro: str | None = None
            if not section_first_item_seen:
                # Strip trailing blank lines from buffer; rejoin.
                while intro_buffer and not intro_buffer[-1].strip():
                    intro_buffer.pop()
                if intro_buffer:
                    attached_intro = "\n".join(intro_buffer).strip()
                section_first_item_seen = True

            out.append({
                "entity_id": m_bullet.group("id"),
                "format": "bullet_item",
                "section": current_section,
                "section_intro": attached_intro,
                "subsection": current_subsection,
                "name": m_bullet.group("desc"),
            })
            continue

        # Accumulate intro text inside a section before the first item.
        if current_section is not None and not section_first_item_seen:
            # Skip pure separator lines (the table header inside a
            # general section is unusual; we keep prose as-is).
            intro_buffer.append(line)

    return out


def _summarize(records: list[dict]) -> dict:
    """Group records by format/section for a printable summary."""
    summary = {
        "total_records": len(records),
        "table_row_count": sum(1 for r in records if r["format"] == "table_row"),
        "bullet_item_count": sum(1 for r in records if r["format"] == "bullet_item"),
        "section_count": len({
            r["section"] for r in records
            if r["format"] == "bullet_item" and r["section"]
        }),
        "subsection_count": len({
            (r["section"], r["subsection"]) for r in records
            if r["subsection"]
        }),
        "sections": sorted({
            r["section"] for r in records
            if r["format"] == "bullet_item" and r["section"]
        }),
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse docs/backlog.md and classify rows for "
                    "feature 110 backfill.",
    )
    parser.add_argument(
        "--backlog-path",
        default="docs/backlog.md",
        help="Path to backlog.md (default: docs/backlog.md).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="(Not yet implemented in this dispatch; deferred to Task 12.4) "
             "Apply parsed metadata to the entity registry.",
    )
    parser.add_argument(
        "--emit-records",
        action="store_true",
        help="Print full classification records as JSON to stdout "
             "(one record per line). Useful for diffing.",
    )
    args = parser.parse_args(argv)

    backlog_path = Path(args.backlog_path)
    if not backlog_path.exists():
        sys.stderr.write(f"error: backlog file not found: {backlog_path}\n")
        return 2

    text = backlog_path.read_text(encoding="utf-8")
    records = parse_backlog(text)

    if args.apply:
        sys.stderr.write(
            "WARNING: --apply is not implemented in this dispatch. "
            "Live-DB application is deferred to feature 110 Task 12.4.\n"
        )

    if args.emit_records:
        for r in records:
            sys.stdout.write(json.dumps(r) + "\n")
    else:
        summary = _summarize(records)
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
