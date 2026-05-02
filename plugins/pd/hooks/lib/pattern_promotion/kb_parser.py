"""Knowledge-bank markdown parser tailored to /pd:promote-pattern.

Standalone per design C-3: the existing `semantic_memory/importer.py`
parser is private, returns DB-upsert dicts, has no line ranges, and no
Promoted-marker awareness. Duplication is acknowledged (TD-2) and preferred
to a refactor of the private API.

FR-1 rules:
- `effective_observation_count`:
    1. `Observation count: N` field if present
    2. Else count distinct `Feature #NNN` identifiers across all `- Used in:`
       / `- Observed in:` / `- Last observed:` lines
    3. Else 0
- Filter qualifying entries against min_observations.
- Files with explicit `Confidence:` field require `Confidence: high`.
- Files without the field (patterns.md) are eligible on observation count alone.
- Entries containing `- Promoted: ` are skipped (idempotent re-runs).
- constitution.md is excluded wholesale.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_FILES = {"constitution.md"}
CONFIDENCE_REQUIRED = {"anti-patterns", "heuristics"}


@dataclass
class KBEntry:
    """A single knowledge-bank entry eligible for promotion.

    `line_range` is 1-indexed (start, end) inclusive, matching the lines of the
    entry's markdown block (heading through the last content line before the
    next sibling heading).

    Feature 102 FR-5: `enforceability_score` is computed from deontic-modal
    regex matches in `name + description`. `descriptive` is `score == 0`
    (entry contains no rule-like markers).
    """

    name: str
    description: str
    confidence: str
    effective_observation_count: int
    category: str
    file_path: Path
    line_range: tuple[int, int]
    enforceability_score: int = 0
    descriptive: bool = True


_FEATURE_RE = re.compile(r"Feature\s+#(\d+)", re.IGNORECASE)
_OBS_COUNT_RE = re.compile(
    r"^\s*-\s*Observation\s+count\s*:\s*(\d+)\s*$", re.IGNORECASE
)
_CONFIDENCE_RE = re.compile(
    r"^\s*-\s*Confidence\s*:\s*(high|medium|low)\s*$", re.IGNORECASE
)
_PROMOTED_RE = re.compile(r"^\s*-\s*Promoted\s*:", re.IGNORECASE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")


def _category_from_filename(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem


def _strip_heading_prefix(heading: str) -> str:
    for prefix in ("Pattern: ", "Anti-Pattern: ", "Heuristic: "):
        if heading.startswith(prefix):
            return heading[len(prefix):]
    return heading


def _parse_file(path: Path) -> tuple[list[KBEntry], set[str]]:
    """Parse a single KB markdown file into KBEntry objects.

    Category is taken from the filename stem (heuristics, patterns, anti-patterns).
    Returns `(entries, promoted_names)` — `promoted_names` holds the raw
    heading of each entry already carrying a `- Promoted:` marker. Callers
    use this set to filter idempotent re-runs without mutating KBEntry.
    """
    category = _category_from_filename(path.name)
    text = path.read_text(encoding="utf-8")
    # Strip HTML comments to avoid parsing example content inside <!-- ... -->
    text_stripped = re.sub(r"<!--[\s\S]*?-->", "", text)
    lines = text_stripped.splitlines()

    entries: list[KBEntry] = []
    promoted_names: set[str] = set()
    # Find all h3 lines and their spans
    h3_positions: list[tuple[int, str]] = []
    for idx, ln in enumerate(lines):
        m = _H3_RE.match(ln)
        if m:
            h3_positions.append((idx, m.group(1)))

    for pos_idx, (line_idx, heading) in enumerate(h3_positions):
        # Determine end line (exclusive)
        end_idx = (
            h3_positions[pos_idx + 1][0]
            if pos_idx + 1 < len(h3_positions)
            else len(lines)
        )
        block = lines[line_idx:end_idx]

        # Skip if a higher-level heading follows directly (unlikely but safe)
        # Partition description vs metadata bullets
        desc_lines: list[str] = []
        meta_lines: list[str] = []
        in_meta = False
        for ln in block[1:]:
            if ln.startswith("- ") and not in_meta:
                in_meta = True
            if in_meta:
                meta_lines.append(ln)
            else:
                desc_lines.append(ln)

        description = "\n".join(desc_lines).strip()

        # Parse metadata
        obs_field: int | None = None
        confidence: str = "n/a"
        marker_seen = False
        for ml in meta_lines:
            if _PROMOTED_RE.match(ml):
                marker_seen = True
                continue
            m = _OBS_COUNT_RE.match(ml)
            if m:
                try:
                    obs_field = int(m.group(1))
                except ValueError:
                    obs_field = None
                continue
            m = _CONFIDENCE_RE.match(ml)
            if m:
                confidence = m.group(1).lower()

        if obs_field is not None:
            effective = obs_field
        else:
            # Count distinct Feature #NNN across metadata bullets only
            feature_ids = set()
            for ml in meta_lines:
                for match in _FEATURE_RE.finditer(ml):
                    feature_ids.add(match.group(1))
            effective = len(feature_ids)

        # KBEntry.name stores the raw heading (including any
        # `Pattern: ` / `Anti-Pattern: ` / `Heuristic: ` prefix) so
        # `mark_entry` can match it against the on-disk heading line.
        # Feature 102 FR-5: compute enforceability score from name + description.
        from pattern_promotion.enforceability import score_enforceability
        ef_score, _ = score_enforceability(f"{heading} {description}")
        entries.append(
            KBEntry(
                name=heading,
                description=description,
                confidence=confidence,
                effective_observation_count=effective,
                category=category,
                file_path=path,
                line_range=(line_idx + 1, end_idx),
                enforceability_score=ef_score,
                descriptive=(ef_score == 0),
            )
        )
        if marker_seen:
            promoted_names.add(heading)

    return entries, promoted_names


def enumerate_qualifying_entries(
    kb_dir: Path, min_observations: int = 3
) -> list[KBEntry]:
    """Return KB entries meeting promotion criteria per FR-1."""
    if not kb_dir.is_dir():
        return []

    qualifying: list[KBEntry] = []
    for path in sorted(kb_dir.iterdir()):
        if not path.is_file() or path.suffix != ".md":
            continue
        if path.name in EXCLUDED_FILES:
            continue
        file_entries, promoted_names = _parse_file(path)
        for e in file_entries:
            if e.name in promoted_names:
                continue
            if e.effective_observation_count < min_observations:
                continue
            if e.category in CONFIDENCE_REQUIRED and e.confidence != "high":
                continue
            qualifying.append(e)
    return qualifying


def mark_entry(
    path: Path,
    entry_name: str,
    target_type: str,
    target_path: str,
) -> None:
    """Append `- Promoted: {target_type}:{target_path}` to the entry block.

    Per FR-5 Stage 5:
    - immediately after the entry's `- Confidence:` line if present
    - else on a new line immediately before the next sibling heading
    - else at EOF for the last entry
    - never break adjacent entries.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=False)
    # keepends=False: we'll re-join with '\n' and preserve trailing newline.
    had_trailing_newline = text.endswith("\n")

    # Locate the h3 heading for entry_name (case-sensitive match on the
    # stripped form and the raw form).
    target_idx: int | None = None
    next_sibling_idx: int | None = None
    h3_positions: list[int] = [
        i for i, ln in enumerate(lines) if _H3_RE.match(ln)
    ]
    for pos, idx in enumerate(h3_positions):
        m = _H3_RE.match(lines[idx])
        assert m is not None
        heading = m.group(1)
        if heading == entry_name or _strip_heading_prefix(heading) == entry_name:
            target_idx = idx
            next_sibling_idx = (
                h3_positions[pos + 1]
                if pos + 1 < len(h3_positions)
                else None
            )
            break

    if target_idx is None:
        raise ValueError(f"Entry not found: {entry_name!r} in {path}")

    block_end = next_sibling_idx if next_sibling_idx is not None else len(lines)
    marker = f"- Promoted: {target_type}:{target_path}"

    # Idempotency: if already marked, no-op
    for i in range(target_idx, block_end):
        if _PROMOTED_RE.match(lines[i]):
            return

    # Prefer insertion immediately after a `- Confidence:` line
    insert_at: int | None = None
    for i in range(target_idx + 1, block_end):
        if _CONFIDENCE_RE.match(lines[i]):
            insert_at = i + 1
            break

    if insert_at is None:
        # Insert before the next sibling heading OR at EOF, after trimming
        # trailing blank lines within the block so the marker stays adjacent.
        j = block_end - 1
        while j > target_idx and lines[j].strip() == "":
            j -= 1
        insert_at = j + 1

    new_lines = lines[:insert_at] + [marker] + lines[insert_at:]
    out = "\n".join(new_lines)
    if had_trailing_newline and not out.endswith("\n"):
        out += "\n"
    path.write_text(out, encoding="utf-8")
