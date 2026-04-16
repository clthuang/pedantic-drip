"""Shared markdown insertion helpers for skill/agent/command generators.

All three targets share the same two insertion modes defined in FR-3:
- `append-to-list`: append a bullet to the first bullet-list under the heading
- `new-paragraph-after-heading`: insert a blank-line-separated paragraph
  immediately after the heading

Plus a common TD-8 marker format for markdown contexts: an HTML comment
(`<!-- Promoted: <entry-name> -->`) that survives markdown parsing without
rendering inline.
"""
from __future__ import annotations

import re
from typing import Literal

InsertionMode = Literal["append-to-list", "new-paragraph-after-heading"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# Cap on description length when embedding into a target markdown file.
# Keeps promoted blocks compact and prevents unbounded prompt-injection
# payloads from corrupting future Claude sessions that read the target.
_MAX_DESCRIPTION_CHARS = 500


def _sanitize_description(text: str) -> str:
    """Neutralize markdown structural characters and cap length.

    KB `description` fields are author-controlled free text that gets
    embedded into target SKILL/agent/command markdown files. A malicious
    or careless description can contain:
      - leading `#` on a line — becomes a spurious heading
      - `---` alone on a line — becomes a frontmatter / thematic break
      - triple-backtick code fences — swallow surrounding content
    Any of these can corrupt target file structure and inject unintended
    instructions into Claude sessions that later read the file.

    This helper:
      - replaces triple-backtick fences with a safe inline marker
      - escapes leading `#` on each line with a zero-width-safe backslash
      - escapes leading `---` / `===` on each line
      - caps length at _MAX_DESCRIPTION_CHARS (truncate + "...")
    It runs BEFORE the newline-flattening step, so per-line structural
    patterns are detectable.
    """
    if not text:
        return ""

    # Neutralize triple-backtick code fences anywhere in the text. We
    # replace with a distinct marker rather than escaping because code
    # fences affect markdown parsing regardless of leading whitespace.
    safe = text.replace("```", "'''")

    # Escape structural patterns at line starts.
    out_lines: list[str] = []
    for line in safe.splitlines():
        stripped_leading = line.lstrip()
        indent = line[: len(line) - len(stripped_leading)]
        if stripped_leading.startswith("#"):
            # Escape the hash so it renders literally instead of becoming
            # a heading when the description happens to land at a line start.
            out_lines.append(f"{indent}\\{stripped_leading}")
        elif stripped_leading.startswith("---") or stripped_leading.startswith("==="):
            # Escape frontmatter / setext-heading delimiters.
            out_lines.append(f"{indent}\\{stripped_leading}")
        else:
            out_lines.append(line)
    safe = "\n".join(out_lines)

    if len(safe) > _MAX_DESCRIPTION_CHARS:
        # Leave room for the trailing ellipsis within the cap.
        safe = safe[: _MAX_DESCRIPTION_CHARS - 3] + "..."
    return safe


def find_heading_line(text: str, heading: str) -> int | None:
    """Return 0-indexed line of the first exact-match heading, else None.

    Match is exact on the full heading line (e.g. `### Step 2: ...`). Leading
    and trailing whitespace on the stored heading argument is tolerated.
    """
    target = heading.strip()
    for idx, line in enumerate(text.splitlines()):
        if line.strip() == target:
            return idx
    return None


def _heading_level(line: str) -> int | None:
    m = _HEADING_RE.match(line)
    if not m:
        return None
    return len(m.group(1))


def section_span(text: str, heading_line_idx: int) -> tuple[int, int]:
    """Return (start_inclusive, end_exclusive) 0-indexed line span of the section.

    End is the next heading at the same-or-higher level, or len(lines).
    """
    lines = text.splitlines()
    start = heading_line_idx
    level = _heading_level(lines[start])
    if level is None:
        return start, start + 1
    for i in range(start + 1, len(lines)):
        lvl = _heading_level(lines[i])
        if lvl is not None and lvl <= level:
            return start, i
    return start, len(lines)


def _render_block(entry_name: str, description: str, mode: InsertionMode) -> list[str]:
    """Return the list of lines (no trailing newline) to insert."""
    # Sanitize BEFORE newline-flattening so per-line structural patterns
    # (leading `#`, `---`, ```) can still be detected and escaped.
    sanitized = _sanitize_description(description or "")
    desc = sanitized.strip().replace("\n", " ")
    marker = f"<!-- Promoted: {entry_name} -->"
    if mode == "append-to-list":
        # Single bullet that combines the entry name and description so the
        # promoted guidance reads naturally alongside existing bullets.
        text = f"- {entry_name}: {desc}" if desc else f"- {entry_name}"
        return [marker, text]
    # new-paragraph-after-heading
    paragraph = f"**Promoted guidance:** {entry_name}"
    if desc:
        paragraph += f" — {desc}"
    return ["", marker, paragraph, ""]


def insert_block(
    text: str,
    heading: str,
    mode: InsertionMode,
    entry_name: str,
    description: str,
) -> str:
    """Insert a TD-8-marked block into `text` under `heading` per `mode`.

    Returns the modified text. Preserves the trailing newline convention of
    the input.
    """
    had_trailing_newline = text.endswith("\n")
    heading_idx = find_heading_line(text, heading)
    if heading_idx is None:
        raise ValueError(f"heading not found: {heading!r}")

    lines = text.splitlines()
    section_start, section_end = section_span(text, heading_idx)
    block = _render_block(entry_name, description, mode)

    if mode == "append-to-list":
        # Find the end of the FIRST bullet list under the heading.
        # "End" = first line after a run of bullets that is blank or a new
        # heading or non-bullet prose.
        list_start = None
        list_end = None
        in_list = False
        for i in range(section_start + 1, section_end):
            ln = lines[i]
            stripped = ln.lstrip()
            is_bullet = stripped.startswith("- ") or stripped.startswith("* ")
            if is_bullet:
                if not in_list:
                    list_start = i
                    in_list = True
                list_end = i + 1  # one past the last bullet seen
            else:
                if in_list:
                    # End of the first list.
                    break
        if list_end is None:
            # No list in the section — append at the end of the section as a
            # new paragraph instead, but still preserve append-to-list intent
            # by emitting a bullet.
            insert_at = section_end
            # Trim trailing blank lines within section for clean adjacency
            while insert_at > section_start + 1 and lines[insert_at - 1].strip() == "":
                insert_at -= 1
            new_lines = (
                lines[:insert_at]
                + block
                + [""]
                + lines[insert_at:]
            )
        else:
            insert_at = list_end
            new_lines = lines[:insert_at] + block + lines[insert_at:]
    else:  # new-paragraph-after-heading
        # Insert immediately after the heading. If the next line is blank,
        # skip it so we don't create double blanks.
        insert_at = heading_idx + 1
        new_lines = lines[:insert_at] + block + lines[insert_at:]

    out = "\n".join(new_lines)
    if had_trailing_newline and not out.endswith("\n"):
        out += "\n"
    return out
