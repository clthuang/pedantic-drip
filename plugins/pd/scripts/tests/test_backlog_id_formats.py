"""Every consumer of backlog.md's id column accepts both id generations.

B7 changed ``docs/backlog.md`` to render each row's real ``entity_id``
instead of a zero-padded sequence. Two shapes now coexist in that column
and both are live:

    00059                                       6 surviving legacy rows
    063-watch-code-quality-reviewer-fix-rate   19 current rows

Seven patterns across four files read that column. Before B7 they all
required exactly five digits, so a modern row was invisible to them —
and every one of these parsers reports success on zero matches. A
``cleanup_backlog --apply`` whose ``_extract_item_ids`` returns ``[]``
archives nothing and exits 0.

The first version of this change shipped with NO test for any of the
seven: reverting all of them to ``\\d{5}`` left the suite byte-identical
at 3948 passed. Every fixture id in this directory is 5-digit, so the
widened patterns were accepting a format nothing ever fed them.

This file is the missing coverage. It asserts the EXTRACTED id, not
merely that a match occurred — a pattern that matches but captures the
wrong span would otherwise pass.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
_LIB = _SCRIPTS.parent / "hooks" / "lib"
for _p in (str(_SCRIPTS), str(_LIB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LEGACY_ID = "00059"
MODERN_ID = "063-watch-code-quality-reviewer-fix-rate"


def _patterns():
    """(label, compiled, group, legacy_line, modern_line) for all 7 consumers."""
    import cleanup_backlog
    import parse_backlog_md
    import test_debt_report
    from entity_registry import backfill

    def tbl(i):
        return f"| {i} | 2026-07-25T11:23:36+00:00 | Some description |"

    def bullet(i):
        return f"- **#{i}** Some description"

    def testability(i):
        return f"- **#{i}** [LOW/testability] Some description"

    return [
        ("cleanup_backlog.ITEM_RE",
         cleanup_backlog.ITEM_RE, None, bullet, bullet),
        ("cleanup_backlog.ITEM_ID_RE",
         cleanup_backlog.ITEM_ID_RE, "id", bullet, bullet),
        ("parse_backlog_md.TABLE_ROW_RE",
         parse_backlog_md.TABLE_ROW_RE, "id", tbl, tbl),
        ("parse_backlog_md.BULLET_ROW_RE",
         parse_backlog_md.BULLET_ROW_RE, "id", bullet, bullet),
        ("test_debt_report.TESTABILITY",
         test_debt_report._BACKLOG_TESTABILITY_RE, 1, testability, testability),
        ("backfill.BACKLOG_MARKER_1",
         re.compile(backfill.BACKLOG_MARKER_PATTERN_1), 1,
         lambda i: f"*Source: Backlog #{i}*", lambda i: f"*Source: Backlog #{i}*"),
        ("backfill.BACKLOG_MARKER_2",
         re.compile(backfill.BACKLOG_MARKER_PATTERN_2), 1,
         lambda i: f"**Backlog Item:** {i}", lambda i: f"**Backlog Item:** {i}"),
    ]


def _ids():
    return [p[0] for p in _patterns()]


@pytest.mark.parametrize("idx", range(7), ids=_ids())
@pytest.mark.parametrize("entity_id", [LEGACY_ID, MODERN_ID], ids=["legacy", "modern"])
def test_consumer_matches_and_extracts_both_id_shapes(idx, entity_id):
    label, pattern, group, legacy_line, modern_line = _patterns()[idx]
    line = (legacy_line if entity_id == LEGACY_ID else modern_line)(entity_id)

    m = pattern.search(line)
    assert m is not None, (
        f"{label} does not match {entity_id!r}. Post-B7 backlog.md contains "
        f"both id shapes; a pattern that misses one silently drops those rows "
        f"and still reports success."
    )
    if group is not None:
        assert m.group(group) == entity_id, (
            f"{label} matched but captured {m.group(group)!r}, not {entity_id!r}"
        )


def test_modern_ids_are_actually_present_in_the_live_projection():
    """Guards the premise: if backlog.md ever stops carrying slug-form ids,
    the parametrised cases above become decorative rather than failing."""
    assert re.fullmatch(r"\d{3}-[a-z0-9][a-z0-9-]*", MODERN_ID), (
        "MODERN_ID no longer looks like a post-B7 entity_id"
    )
    assert re.fullmatch(r"\d{5}", LEGACY_ID)
    assert not re.fullmatch(r"\d{5}", MODERN_ID), (
        "the two shapes must differ, or these tests cannot distinguish the "
        "widened pattern from the old one"
    )
