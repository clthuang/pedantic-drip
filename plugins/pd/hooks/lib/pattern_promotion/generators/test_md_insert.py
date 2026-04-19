"""Tests for _md_insert description sanitization (structural-injection defense).

The skill/agent/command generators embed `entry.description` verbatim into
target SKILL.md / agent / command markdown files. A malicious or careless
description can:
  - start a line with `#` → becomes a spurious heading
  - start a line with `---` → becomes a frontmatter / thematic break
  - contain ``` fences → swallow surrounding content
  - be arbitrarily long → balloon the target file and inject prompts into
    future Claude sessions

`_sanitize_description` neutralizes these structural patterns and caps
length at 500 chars. This file covers that helper directly and via the
public `insert_block` path to guarantee callers benefit.
"""
from __future__ import annotations

import textwrap

from pattern_promotion.generators._md_insert import (
    _MAX_DESCRIPTION_CHARS,
    _sanitize_description,
    insert_block,
)


SAMPLE_DOC = textwrap.dedent("""\
    # Target Doc

    ## Section A

    Paragraph text.

    ### Target Heading

    Some guidance:

    - existing bullet one
    - existing bullet two

    ### Next Sibling

    Tail.
    """)


# ---------------------------------------------------------------------------
# _sanitize_description direct coverage
# ---------------------------------------------------------------------------


class TestSanitizeDescription:
    def test_empty_returns_empty(self):
        assert _sanitize_description("") == ""
        assert _sanitize_description(None) == ""  # type: ignore[arg-type]

    def test_leading_hash_is_escaped(self):
        """`# heading` at line start would render as a heading."""
        out = _sanitize_description("# fake heading inside description")
        # Hash is backslash-escaped at line start.
        assert out.startswith("\\#")
        # Literal content preserved after the escape.
        assert "fake heading inside description" in out

    def test_leading_hash_multiline(self):
        text = "safe line\n## injected h2\nmore"
        out = _sanitize_description(text)
        lines = out.splitlines()
        # First line is untouched.
        assert lines[0] == "safe line"
        # Second line's leading hash-run is escaped.
        assert lines[1].startswith("\\##")
        # Third line untouched.
        assert lines[2] == "more"

    def test_triple_backtick_fence_escaped(self):
        text = "before\n```bash\nrm -rf /\n```\nafter"
        out = _sanitize_description(text)
        # No surviving triple-backtick anywhere.
        assert "```" not in out
        # Replacement marker uses single quotes, so content is still
        # human-readable.
        assert "'''" in out

    def test_frontmatter_delimiter_escaped(self):
        text = "ok line\n---\nbody"
        out = _sanitize_description(text)
        lines = out.splitlines()
        assert lines[0] == "ok line"
        # --- at line start is escaped so it won't act as a thematic break
        # or open YAML frontmatter.
        assert lines[1].startswith("\\---")

    def test_setext_heading_delimiter_escaped(self):
        text = "Heading text\n==="
        out = _sanitize_description(text)
        lines = out.splitlines()
        # Second line's === would otherwise turn the preceding line into an H1.
        assert lines[1].startswith("\\===")

    def test_truncates_above_cap(self):
        long = "a" * (_MAX_DESCRIPTION_CHARS + 100)
        out = _sanitize_description(long)
        assert len(out) == _MAX_DESCRIPTION_CHARS
        assert out.endswith("...")

    def test_under_cap_unchanged_length(self):
        short = "a" * (_MAX_DESCRIPTION_CHARS - 10)
        out = _sanitize_description(short)
        assert out == short

    def test_at_cap_exactly_unchanged(self):
        exact = "a" * _MAX_DESCRIPTION_CHARS
        out = _sanitize_description(exact)
        assert out == exact  # no truncation when exactly at cap

    def test_indented_structural_chars_also_escaped(self):
        # Leading whitespace + # should still be neutralized for safety —
        # markdown tolerates some indent before lazy block constructs.
        text = "   # pretending to be heading"
        out = _sanitize_description(text)
        # Starts with the preserved indent, then a backslash-escaped hash.
        assert out.startswith("   \\#")

    def test_plain_text_passes_through_unchanged(self):
        text = "Just a normal description with punctuation, okay? Cool."
        out = _sanitize_description(text)
        assert out == text


# ---------------------------------------------------------------------------
# insert_block integration — sanitization is applied at the block-render stage
# ---------------------------------------------------------------------------


class TestInsertBlockSanitization:
    def test_description_with_leading_hash_does_not_inject_heading(self):
        result = insert_block(
            SAMPLE_DOC,
            heading="### Target Heading",
            mode="append-to-list",
            entry_name="Safe Entry",
            description="# injected heading",
        )
        # Despite `#` in the description, no new actual heading should appear
        # between Target Heading and Next Sibling.
        lines = result.splitlines()
        tgt_idx = next(i for i, ln in enumerate(lines) if ln == "### Target Heading")
        sib_idx = next(i for i, ln in enumerate(lines) if ln == "### Next Sibling")
        between = lines[tgt_idx + 1 : sib_idx]
        # Any line in between that starts with a lone `#` is a bug. Escaped
        # forms start with `\#`, which is fine.
        for ln in between:
            stripped = ln.lstrip()
            if stripped.startswith("#"):
                # Must NOT be a markdown heading (`# text`).
                raise AssertionError(
                    f"description injected heading into target file: {ln!r}"
                )

    def test_description_with_code_fence_neutralized(self):
        result = insert_block(
            SAMPLE_DOC,
            heading="### Target Heading",
            mode="append-to-list",
            entry_name="X",
            description="text ```bash\nrm -rf /\n``` end",
        )
        # The original SAMPLE_DOC has no code fences, so any ``` in the
        # output would have been injected.
        assert "```" not in result

    def test_description_with_frontmatter_delim_neutralized(self):
        result = insert_block(
            SAMPLE_DOC,
            heading="### Target Heading",
            mode="append-to-list",
            entry_name="X",
            description="first\n---\nsecond",
        )
        # A bare --- line between sections can be parsed as a thematic
        # break. After newline-flattening in _render_block, the sanitized
        # escape (\---) must be what's present (if present at all).
        # The block ends up on a single bullet line, so check that no
        # bare `---` line exists in the output where only the original
        # `---` on the frontmatter-free doc would be acceptable.
        for ln in result.splitlines():
            assert ln.strip() != "---", (
                "description injected a bare --- line into the target"
            )

    def test_description_length_capped(self):
        long = "X" * 5000
        result = insert_block(
            SAMPLE_DOC,
            heading="### Target Heading",
            mode="append-to-list",
            entry_name="Entry",
            description=long,
        )
        # The inserted bullet should not carry all 5000 chars.
        inserted = [ln for ln in result.splitlines() if "Entry" in ln and "X" in ln]
        assert inserted, "bullet with entry+description not found"
        for ln in inserted:
            assert len(ln) <= _MAX_DESCRIPTION_CHARS + 200, (
                "description was not truncated to the cap"
            )

    def test_td8_marker_still_emitted_with_sanitization(self):
        result = insert_block(
            SAMPLE_DOC,
            heading="### Target Heading",
            mode="append-to-list",
            entry_name="Entry Name",
            description="# fake heading",
        )
        assert "<!-- Promoted: Entry Name -->" in result


# ---------------------------------------------------------------------------
# Feature 085 FR-1: entry_name sanitization (SC-2 / AC-H1 / AC-E2)
# ---------------------------------------------------------------------------

import pytest

from pattern_promotion.generators._md_insert import _render_block


class TestEntryNameSanitizationFR1:
    """_render_block MUST refuse entry_names containing HTML-comment or
    triple-backtick markers that would corrupt the `<!-- Promoted: X -->`
    wrapper if interpolated verbatim.
    """

    def test_render_block_rejects_html_comment_closer(self):
        """AC-H1: entry_name with `-->` closes the marker prematurely."""
        with pytest.raises(ValueError, match=r"-->"):
            _render_block(
                entry_name="weird -->",
                description="some description",
                mode="append-to-list",
            )

    def test_render_block_rejects_html_comment_opener(self):
        """entry_name with `<!--` opens an inner comment."""
        with pytest.raises(ValueError, match=r"<!--"):
            _render_block(
                entry_name="<!-- sneaky entry",
                description="some description",
                mode="append-to-list",
            )

    def test_render_block_rejects_triple_backtick(self):
        """AC-E2: entry_name with triple-backtick escapes the block."""
        with pytest.raises(ValueError, match=r"```"):
            _render_block(
                entry_name="code ```fence",
                description="some description",
                mode="append-to-list",
            )
