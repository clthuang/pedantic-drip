#!/usr/bin/env python3
"""Feature 110 Task 8.2 + 12.4 — Backfill parser for ``docs/backlog.md``.

Reads the existing ``docs/backlog.md`` file and classifies each row into
the ``format``/``section``/``section_intro``/``subsection`` metadata
shape consumed by ``_project_backlog_md`` (per design TD-10).

Dry-run (default): prints a JSON-line classification summary to stdout
and a human-readable summary to stderr. NO DB writes.

Apply mode (``--apply``, Task 12.4): for each parsed record, MERGE the
``format``/``section``/``section_intro``/``subsection`` keys into the
existing entity metadata via
``db.update_entity(type_id, metadata={...})`` (the registry merges
shallowly — existing keys are preserved). Entities not yet present in
the registry are inserted via ``db.register_entity(...)`` as a
defensive fallback. Re-running ``--apply`` is a no-op (idempotent)
because the metadata merge is a deep-equal write.

Stdlib-only. Run via the project's plugin venv when possible (matches
the rest of the ``plugins/pd/scripts/`` convention).
"""
from __future__ import annotations

import argparse
import json
import os
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


def _setup_db_imports() -> None:
    """Augment sys.path so ``entity_registry.database`` is importable.

    Matches the convention used by ``compare_backlog_projection.py`` and
    ``cleanup_backlog.py``.
    """
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    hooks_lib = repo_root / "plugins" / "pd" / "hooks" / "lib"
    sp = str(hooks_lib)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def _metadata_subset(record: dict) -> dict:
    """Project the classification record to the metadata keys we want
    to backfill.

    Per design TD-10, the backfill writes ``format``, ``section``,
    ``section_intro``, ``subsection``. We intentionally OMIT keys whose
    value is ``None`` (so the merge does not nullify other keys that the
    entity may already carry — ``update_entity``'s shallow merge would
    overwrite e.g. an existing ``section`` with ``None`` otherwise).
    """
    keys = ("format", "section", "section_intro", "subsection")
    return {k: record[k] for k in keys if record.get(k) is not None}


def _has_drift(existing_md: dict, target_subset: dict) -> bool:
    """Return True if ``existing_md`` is missing or differs from any key
    in ``target_subset``.

    Idempotency contract: when this returns False, the backfill is a
    no-op for this row (no DB write issued).
    """
    for k, v in target_subset.items():
        if existing_md.get(k) != v:
            return True
    return False


def apply_records(records: list[dict], db_path: str | None = None) -> dict:
    """Apply parsed records to the entity registry (Task 12.4).

    For each record:
      1. Look up the entity at ``type_id = backlog:{entity_id}``.
      2. If absent, register it (defensive — most rows should already
         exist as entities) via ``register_entity`` carrying the
         metadata subset.
      3. If present, compute the metadata-subset drift; if any key
         differs from the parsed value, call ``update_entity(metadata=...)``
         (registry merges shallowly — other keys preserved).
      4. If no drift, skip (idempotent re-run).

    Returns a dict summary: ``{updated, inserted, skipped, failed}``.
    """
    _setup_db_imports()
    try:
        from entity_registry.database import EntityDatabase
    except Exception as exc:
        sys.stderr.write(
            f"error: failed to import entity_registry.database: {exc}\n"
        )
        return {"updated": 0, "inserted": 0, "skipped": 0, "failed": len(records)}

    db_path_resolved = db_path or os.environ.get(
        "ENTITY_DB_PATH",
        str(Path.home() / ".claude" / "pd" / "entities" / "entities.db"),
    )
    try:
        db = EntityDatabase(db_path_resolved)
    except Exception as exc:
        sys.stderr.write(
            f"error: failed to open entity DB at {db_path_resolved}: {exc}\n"
        )
        return {"updated": 0, "inserted": 0, "skipped": 0, "failed": len(records)}

    updated = 0
    inserted = 0
    skipped = 0
    failed = 0

    for rec in records:
        type_id = f"backlog:{rec['entity_id']}"
        target_md = _metadata_subset(rec)
        if not target_md:
            # No metadata to backfill (defensive — should not happen
            # because at minimum ``format`` is always set).
            skipped += 1
            continue

        # Look up existing entity (any workspace). Use list_entities
        # filtered by entity_type so we can match on entity_id.
        try:
            rows = db.list_entities(entity_type="backlog")
        except Exception as exc:
            sys.stderr.write(
                f"warning: list_entities(backlog) failed: {exc}\n"
            )
            failed += 1
            continue

        # Find a row matching the entity_id. There may be multiple rows
        # across workspaces — in that case we update each (the backlog
        # is conventionally workspace-uniform, but defensiveness is free).
        matching = [r for r in rows if r.get("entity_id") == rec["entity_id"]]

        if not matching:
            # Defensive insert. The backlog entity SHOULD already exist
            # (created via /pd:add-to-backlog) but this path covers
            # backfill from a stale DB. Insert under the canonical
            # ``__unknown__`` workspace — the backlog is conventionally
            # workspace-uniform, and the backfill target was derived
            # from the project-root ``docs/backlog.md`` so any workspace
            # is acceptable for the defensive surface.
            try:
                db.register_entity(
                    entity_type="backlog",
                    entity_id=rec["entity_id"],
                    name=rec.get("name") or "",
                    project_id="__unknown__",
                    status="open",
                    metadata=target_md,
                )
                inserted += 1
            except Exception as exc:
                sys.stderr.write(
                    f"warning: register_entity({type_id}) failed: {exc}\n"
                )
                failed += 1
            continue

        # One or more matching rows. For each, parse existing metadata,
        # check drift, update if needed.
        for row in matching:
            raw_md = row.get("metadata")
            try:
                existing_md = (
                    json.loads(raw_md) if isinstance(raw_md, str) and raw_md
                    else (raw_md or {})
                )
            except (json.JSONDecodeError, ValueError):
                existing_md = {}

            if not _has_drift(existing_md, target_md):
                skipped += 1
                continue

            try:
                # update_entity shallow-merges metadata — other keys
                # preserved per database.py:6053.
                db.update_entity(
                    type_id=row.get("uuid") or type_id,
                    metadata=target_md,
                )
                updated += 1
            except Exception as exc:
                sys.stderr.write(
                    f"warning: update_entity({type_id}) failed: {exc}\n"
                )
                failed += 1

    return {
        "updated": updated,
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
    }


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
        help="Apply parsed metadata to the entity registry "
             "(idempotent — re-running is a no-op).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to entity registry SQLite DB. If omitted, uses "
             "ENTITY_DB_PATH or ~/.claude/pd/entities/entities.db.",
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
        result = apply_records(records, db_path=args.db_path)
        sys.stderr.write(
            f"--apply summary: "
            f"updated={result['updated']}, "
            f"inserted={result['inserted']}, "
            f"skipped={result['skipped']}, "
            f"failed={result['failed']}\n"
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
