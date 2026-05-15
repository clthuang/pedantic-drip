#!/usr/bin/env python3
"""FR-6a /pd:cleanup-backlog — backlog section archival utility.

Per spec FR-6a + design I-4. Stdlib-only (no PyYAML).

Feature 110 FR-4.3 — Archival semantics changed (design §2.3):
  Pre-feature-110 behavior was to MOVE archivable sections from
  ``docs/backlog.md`` into ``docs/backlog-archive.md`` via direct file
  writes. Post-feature-110, ``docs/backlog.md`` is a deterministic
  projection of DB state (``_project_backlog_md``) and is GUARDED by
  ``data-file-guard.sh``. The archival path now routes through
  ``update_entity(type_id, status='archived')`` (per design §2.3
  ``cleanup_backlog.py`` row) — flipping the DB status flag is sufficient
  because ``_project_backlog_md`` excludes archived rows from the main
  table (per design TD-10). After flipping all status flags, the script
  invokes the projection helper to regenerate ``docs/backlog.md``.

  # F4-AUDIT: annotation-only — see feature 110 design §2.3 row.

CLI:
  --dry-run        Default mode. Print archivable-section table.
  --apply          Perform writes via update_entity + re-project.
  --count-active   Print active-item count to stdout (used by FR-6b doctor + AC-X1).
  --backlog-path   Override default backlog path.
  --archive-path   DEPRECATED (feature 110 FR-4.3). Retained for CLI
                   backward compatibility; ignored when ``--apply`` routes
                   through ``update_entity``. The standalone archive
                   file is no longer maintained — archived rows are
                   identified via DB ``status='archived'`` flag.

The script NEVER commits. Commit responsibility belongs to the slash-command (cleanup-backlog.md).
"""
import argparse
import os
import re
import sys
from pathlib import Path

ITEM_RE = re.compile(r'^- (~~)?\*\*#\d+\*\*')
SECTION_HEADER_RE = re.compile(r'^## From ')
ANY_H2_RE = re.compile(r'^## ')
CLOSED_MARKERS = ('(closed:', '(promoted →', '(fixed in feature:', '**CLOSED')


def is_item_closed(line: str) -> bool:
    """Canonical predicate. Used by both FR-6a archival and FR-6b doctor count."""
    if line.startswith('- ~~'):
        return True
    return any(marker in line for marker in CLOSED_MARKERS)


def count_active(backlog_path: Path) -> int:
    """Per FR-6b: count active backlog items.

    Algorithm:
      1. Read file. Split into lines.
      2. For each line matching ITEM_RE: if not is_item_closed → increment.
      3. Return counter.
    """
    if not backlog_path.exists():
        return 0
    count = 0
    for line in backlog_path.read_text().splitlines():
        if ITEM_RE.match(line) and not is_item_closed(line):
            count += 1
    return count


def parse_sections(content: str) -> list:
    """Per FR-6a: parse `## From ` sections from backlog.md content.

    Returns list of {"header", "lines", "items", "is_archivable"} dicts.
    Top-level table (anything before first `## From`) is OUT OF SCOPE.
    """
    lines = content.splitlines(keepends=False)
    sections = []
    current = None
    for i, line in enumerate(lines):
        if SECTION_HEADER_RE.match(line):
            # Start a new "From" section.
            if current is not None:
                # Close prior section before its trailing blanks (handled below).
                sections.append(current)
            current = {"header": line, "lines": [line], "start_idx": i, "items": []}
        elif current is not None and ANY_H2_RE.match(line):
            # Different H2 boundary — close current section.
            sections.append(current)
            current = None
        elif current is not None:
            current["lines"].append(line)
            if ITEM_RE.match(line):
                current["items"].append(line)
    if current is not None:
        sections.append(current)

    # Trim trailing blank lines from each section's "lines" (keep one trailing blank for separation).
    for sec in sections:
        # Strip trailing fully-empty lines.
        while len(sec["lines"]) > 1 and sec["lines"][-1].strip() == "":
            sec["lines"].pop()
        # Re-append a single trailing blank for archive separation.
        sec["lines"].append("")
        sec["is_archivable"] = (
            len(sec["items"]) > 0
            and all(is_item_closed(it) for it in sec["items"])
        )
    return sections


def render_dry_run_table(sections: list) -> str:
    """Markdown table preview per spec FR-6a step 3."""
    out = ["| Section | Items | Closed | ARCHIVABLE |",
           "|---------|-------|--------|------------|"]
    archivable_count = 0
    total_items = 0
    for sec in sections:
        n_items = len(sec["items"])
        n_closed = sum(1 for it in sec["items"] if is_item_closed(it))
        archivable = "YES" if sec["is_archivable"] else "no"
        if sec["is_archivable"]:
            archivable_count += 1
            total_items += n_items
        # Trim section header to short form for the table.
        header_short = sec["header"].replace("## From ", "")[:50]
        out.append(f"| {header_short} | {n_items} | {n_closed} | {archivable} |")
    out.append("")
    out.append(f"Total: {archivable_count} archivable section(s) with {total_items} items.")
    return "\n".join(out)


ITEM_ID_RE = re.compile(r'^- (?:~~)?\*\*#(?P<id>\d{5})\*\*')


def _extract_item_ids(section_lines: list) -> list:
    """Extract 5-digit backlog IDs from a section's bullet lines."""
    ids = []
    for line in section_lines:
        m = ITEM_ID_RE.match(line)
        if m:
            ids.append(m.group("id"))
    return ids


def _setup_db_imports() -> None:
    """Augment sys.path so ``entity_registry.database`` +
    ``workflow_state_server`` can be imported from a vanilla python
    invocation (matches compare_backlog_projection.py pattern).
    """
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    mcp_dir = repo_root / "plugins" / "pd" / "mcp"
    hooks_lib = repo_root / "plugins" / "pd" / "hooks" / "lib"
    for p in (mcp_dir, hooks_lib):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)


def apply_archival(backlog_path: Path, archive_path: Path) -> int:
    """Archive archivable sections via ``update_entity(status='archived')``.

    Per feature 110 FR-4.3 / design §2.3:
      * Parse the current backlog file to identify archivable sections
        (closed-items-only sections — same predicate as pre-110).
      * For each item ID in those sections, call
        ``db.update_entity(type_id="backlog:{ID}", status="archived")``.
      * After flipping all status flags, invoke ``_project_backlog_md(db)``
        and write the result to ``backlog_path``. The projection excludes
        ``status='archived'`` rows (design TD-10), so the file shrinks
        deterministically.

    The ``archive_path`` argument is retained for CLI signature
    compatibility but is NO LONGER WRITTEN — archived rows are
    identified via the DB status flag. The standalone archive file is
    deprecated. ``cleanup_backlog.py`` no longer touches it.

    Returns the count of archived SECTIONS (not items).
    """
    content = backlog_path.read_text()
    sections = parse_sections(content)
    archivable = [s for s in sections if s["is_archivable"]]
    if not archivable:
        return 0

    # Collect all backlog item IDs across archivable sections.
    item_ids: list = []
    for sec in archivable:
        item_ids.extend(_extract_item_ids(sec["items"]))

    if not item_ids:
        # No items to flip — sections are archivable but contain no
        # bullet rows matching the ID pattern (defensive).
        return 0

    # Lazy DB import to avoid penalising the dry-run / count-active
    # paths (which never touch the DB).
    _setup_db_imports()
    try:
        from entity_registry.database import EntityDatabase
        from workflow_state_server import _project_backlog_md
    except Exception as exc:
        sys.stderr.write(
            f"error: failed to import DB/projection modules for --apply: {exc}\n"
        )
        return 0

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        str(Path.home() / ".claude" / "pd" / "entities" / "entities.db"),
    )
    try:
        db = EntityDatabase(db_path)
    except Exception as exc:
        sys.stderr.write(f"error: failed to open entity DB at {db_path}: {exc}\n")
        return 0

    # Route each archival through update_entity. Continue on individual
    # failures (e.g., type_id not registered in DB) — surface aggregate
    # failures to stderr at the end.
    failures: list = []
    for item_id in item_ids:
        type_id = f"backlog:{item_id}"
        try:
            db.update_entity(type_id=type_id, status="archived")
        except Exception as exc:
            failures.append((type_id, str(exc)))

    # Re-project backlog.md from DB state (archived rows excluded).
    try:
        projected = _project_backlog_md(db)
        backlog_path.write_text(projected)
    except Exception as exc:
        sys.stderr.write(f"error: re-projection failed after archival: {exc}\n")
        # Even if projection fails, the DB writes already happened — do
        # NOT touch the file in that case (preserves audit trail).

    if failures:
        sys.stderr.write(
            f"warning: {len(failures)} update_entity call(s) failed:\n"
        )
        for type_id, msg in failures:
            sys.stderr.write(f"  - {type_id}: {msg}\n")

    return len(archivable)


def main():
    parser = argparse.ArgumentParser(description="Backlog section archival utility (FR-6a).")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--dry-run', action='store_true', help='Preview archivable sections (default).')
    mode_group.add_argument('--apply', action='store_true', help='Perform writes.')
    mode_group.add_argument('--count-active', action='store_true', help='Print active-item count.')
    parser.add_argument('--backlog-path', default='docs/backlog.md', help='Backlog file path.')
    parser.add_argument(
        '--archive-path',
        default='docs/backlog-archive.md',
        help='DEPRECATED (feature 110 FR-4.3). Archive file path. Ignored '
             'in --apply mode; retained for CLI backward compatibility.',
    )
    args = parser.parse_args()

    backlog_path = Path(args.backlog_path)
    archive_path = Path(args.archive_path)

    # Mode resolution: count-active is exclusive; otherwise default = dry-run.
    if args.count_active:
        print(count_active(backlog_path))
        return 0

    if not backlog_path.exists():
        print(f"Error: backlog not found at {backlog_path}", file=sys.stderr)
        return 1

    if args.apply:
        moved = apply_archival(backlog_path, archive_path)
        # Post-feature-110, the archive file is no longer written; the
        # DB ``status='archived'`` flag IS the archive surface and
        # ``_project_backlog_md`` excludes archived rows.
        print(
            f"Archived {moved} section(s) via update_entity(status='archived'); "
            f"re-projected {backlog_path}."
        )
        return 0

    # Default: dry-run.
    sections = parse_sections(backlog_path.read_text())
    print(render_dry_run_table(sections))
    return 0


if __name__ == '__main__':
    sys.exit(main())
