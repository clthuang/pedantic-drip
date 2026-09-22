"""C4: exactly one function composes a display id, and it drops the P prefix.

An AST count of `{seq:03d}` f-strings reaching 1 is necessary and NOT
sufficient — that count is satisfied by folding two identical kind-blind
bodies into one kind-blind function, which changes nothing. The P prefix
never came from either call site; it came from the caller
(``create-project.md``), which built ``P{NNN}`` from the returned ``seq``
and discarded the returned ``entity_id``.

So these assert rendered OUTPUT per kind, not a count.
"""
from __future__ import annotations

import pytest

from entity_registry.id_generator import NON_SEQUENCE_KINDS, render_display_id


class TestRenderedOutputPerKind:
    @pytest.mark.parametrize("kind,seq,slug,expected", [
        ("feature", 1, "first-thing", "001-first-thing"),
        ("feature", 135, "entity-uuid-migration", "135-entity-uuid-migration"),
        ("project", 4, "entity-db-redesign", "004-entity-db-redesign"),
        ("project", 1, "agent-orchestrator", "001-agent-orchestrator"),
        ("backlog", 63, "watch-fix-rate", "063-watch-fix-rate"),
        ("task", 7, "do-the-thing", "007-do-the-thing"),
        ("bug", 12, "it-broke", "012-it-broke"),
        ("initiative", 2, "q3-push", "002-q3-push"),
    ])
    def test_every_sequence_kind_renders_identically(self, kind, seq, slug, expected):
        assert render_display_id(kind, seq, slug) == expected

    def test_project_has_no_P_prefix(self):
        """The decision, pinned as its own case.

        A kind-blind refactor passes every other test in this class whether
        or not the prefix was ever applied, because the prefix lived in the
        caller. This names it.
        """
        rendered = render_display_id("project", 4, "entity-db-redesign")
        assert not rendered.startswith("P"), (
            f"project rendered {rendered!r}; C4 dropped the P prefix so "
            "projects render exactly like every other sequence-numbered kind"
        )
        assert rendered == render_display_id("feature", 4, "entity-db-redesign"), (
            "project and feature must render identically — any divergence "
            "reintroduces the special case _PROJECT_DISPLAY_RE existed to undo"
        )

    def test_four_digit_sequence_is_not_truncated(self):
        """Zero-padding is a MINIMUM width, not a field size. Features are at
        135 in this repo; a three-digit format that truncated at 1000 would
        be invisible until it happened."""
        assert render_display_id("feature", 1000, "x") == "1000-x"


class TestRefusals:
    def test_brainstorm_is_refused(self):
        """Brainstorm identity is a timestamp, not a sequence — 96 of 100
        live brainstorms are ``{YYYYMMDD-HHMMSS}-{slug}`` and no brainstorm
        path calls the allocator. Composing ``001-slug`` for one would mint a
        plausible-looking wrong id."""
        with pytest.raises(ValueError, match="not a sequence"):
            render_display_id("brainstorm", 1, "some-idea")

    def test_every_non_sequence_kind_is_refused(self):
        for kind in NON_SEQUENCE_KINDS:
            with pytest.raises(ValueError):
                render_display_id(kind, 1, "x")

    @pytest.mark.parametrize("seq", [0, -1, "3", 3.0, True, None])
    def test_non_positive_int_seq_is_refused(self, seq):
        """``True`` is in this list deliberately: bool is a subclass of int,
        so a naive isinstance check renders it as ``001``."""
        with pytest.raises(ValueError):
            render_display_id("feature", seq, "x")

    def test_empty_slug_is_refused(self):
        with pytest.raises(ValueError):
            render_display_id("feature", 1, "")


class TestSingleRenderer:
    def test_exactly_one_executable_03d_fstring_in_production(self):
        """Necessary, not sufficient — see this module's docstring."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        found = []
        for f in root.rglob("*.py"):
            if "/test" in str(f) or ".venv" in str(f):
                continue
            try:
                tree = ast.parse(f.read_text())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.JoinedStr):
                    continue
                for v in node.values:
                    if isinstance(v, ast.FormattedValue) and v.format_spec:
                        if "03d" in ast.unparse(v.format_spec):
                            found.append(f"{f.relative_to(root)}:{node.lineno}")
        assert len(found) == 1, f"expected 1 renderer, found {len(found)}: {found}"
        assert "id_generator.py" in found[0]
