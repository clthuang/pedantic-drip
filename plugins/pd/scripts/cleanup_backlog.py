#!/usr/bin/env python3
"""FR-6a /pd:cleanup-backlog — backlog section archival utility.

Per spec FR-6a + design I-4. Stdlib-only (no PyYAML).

CLI:
  --dry-run        Default mode. Print archivable-section table.
  --apply          Perform writes.
  --count-active   Print active-item count to stdout (used by FR-6b doctor + AC-X1).
  --backlog-path   Override default backlog path.
  --archive-path   Override default archive path.

The script NEVER commits. Commit responsibility belongs to the slash-command (cleanup-backlog.md).
"""
import argparse
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


def apply_archival(backlog_path: Path, archive_path: Path) -> int:
    """Move archivable sections from backlog to archive. Returns count moved."""
    content = backlog_path.read_text()
    sections = parse_sections(content)
    archivable = [s for s in sections if s["is_archivable"]]
    if not archivable:
        return 0

    # Build archive content.
    if not archive_path.exists():
        archive_header = "# Backlog Archive\n\nClosed sections moved from backlog.md by /pd:cleanup-backlog.\n\n"
        archive_path.write_text(archive_header)

    archive_text = archive_path.read_text()
    if not archive_text.endswith("\n"):
        archive_text += "\n"
    for sec in archivable:
        section_text = "\n".join(sec["lines"])
        if not section_text.endswith("\n"):
            section_text += "\n"
        archive_text += section_text
    archive_path.write_text(archive_text)

    # Remove archived sections from backlog by line range.
    archived_starts = {s["start_idx"] for s in archivable}
    lines = content.splitlines(keepends=False)
    new_lines = []
    skip_until_h2 = False
    for i, line in enumerate(lines):
        if i in archived_starts:
            skip_until_h2 = True
            continue
        if skip_until_h2:
            if ANY_H2_RE.match(line):
                skip_until_h2 = False
                new_lines.append(line)
            # else: drop this line.
            continue
        new_lines.append(line)

    # Collapse consecutive blank-line runs (AC-9(f)).
    collapsed = []
    prev_blank = False
    for line in new_lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    new_content = "\n".join(collapsed)
    if not new_content.endswith("\n"):
        new_content += "\n"
    backlog_path.write_text(new_content)
    return len(archivable)


def main():
    parser = argparse.ArgumentParser(description="Backlog section archival utility (FR-6a).")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--dry-run', action='store_true', help='Preview archivable sections (default).')
    mode_group.add_argument('--apply', action='store_true', help='Perform writes.')
    mode_group.add_argument('--count-active', action='store_true', help='Print active-item count.')
    parser.add_argument('--backlog-path', default='docs/backlog.md', help='Backlog file path.')
    parser.add_argument('--archive-path', default='docs/backlog-archive.md', help='Archive file path.')
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
        print(f"Archived {moved} section(s) from {backlog_path} to {archive_path}.")
        return 0

    # Default: dry-run.
    sections = parse_sections(backlog_path.read_text())
    print(render_dry_run_table(sections))
    return 0


if __name__ == '__main__':
    sys.exit(main())
