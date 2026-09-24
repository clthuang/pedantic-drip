"""Fixtures for the identity-text inference detector.

The detector's predecessor keyed on the literal variable name
``entity_id`` and so found none of the real sites. These fixtures are
therefore organised by RECEIVER FORM, not by idiom: a detector that
handles every idiom but only recognises one spelling of the receiver
reproduces the original bug and passes an idiom-only fixture set.
"""
from __future__ import annotations

import ast

import pytest

from pathlib import Path

from doctor.identity_inference import (
    InferenceSite,
    iter_inference_sites,
    scan_template,
)


def sites(src: str) -> list[InferenceSite]:
    return list(iter_inference_sites(ast.parse(src), "<fixture>"))


def idioms(src: str) -> set[str]:
    return {s.idiom for s in sites(src)}


# ---------------------------------------------------------------------------
# Receiver forms — the axis the old pattern got wrong
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("receiver", [
    "entity_id",            # the only spelling the old grep knew
    "eid",                  # database.py:929
    "tid",
    "type_id",
    "feature_type_id",      # engine.py:376, feature_lifecycle.py:98
    "old_type_id",
    "parent_type_id",
    "proj_entity_id",
])
def test_bare_name_receivers_are_recognised(receiver):
    assert idioms(f'{receiver}.split(":")[1]') == {"split"}


@pytest.mark.parametrize("expr", [
    'entity["type_id"]',        # frontmatter_sync.py:109
    "row['entity_id']",         # reconciliation.py:787
    'anomaly["type_id"]',
    'entity.get("type_id")',
    "self.entity_id",
])
def test_subscript_get_and_attribute_receivers_are_recognised(expr):
    assert idioms(f'{expr}.split(":")[1]') == {"split"}


# ---------------------------------------------------------------------------
# Idioms
# ---------------------------------------------------------------------------

def test_compiled_pattern_applied_to_an_id():
    assert idioms('_ENTITY_ID_FORMAT_RE.match(entity_id)') == {"regex"}


def test_module_level_re_match_puts_the_id_in_the_second_argument():
    """database.py:10281 — checking only arg 0 misses every call of this shape."""
    assert idioms(r're.match(r"^(\d+)", eid)') == {"regex"}


def test_separator_split_and_partition():
    assert idioms('type_id.partition(":")') == {"split"}
    assert idioms('type_id.rsplit("-", 1)') == {"split"}


def test_dash_index_then_slice():
    src = 'dash = entity_id.index("-")\nseq = entity_id[:dash]\nslug = entity_id[dash + 1:]'
    assert idioms(src) == {"slice"}
    assert len(sites(src)) == 3


def test_kind_sniffing_via_prefix():
    assert idioms('row["type_id"].startswith("feature:")') == {"startswith"}


def test_sql_inference_in_a_module_level_constant():
    """Module-level SQL constants are invisible to an in-function-only walk."""
    src = '_SQL = "SELECT * FROM entities WHERE type_id LIKE \'feature:%\'"'
    assert idioms(src) == {"sql"}
    assert idioms('q = "SELECT substr(entity_id, 1, 3) FROM entities"') == {"sql"}


# ---------------------------------------------------------------------------
# Negative controls — these must NOT fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("src", [
    '_UUID_RE.match(value)',
    '_TAG_RE.match(tag)',
    '_TASK_HEADING_RE.match(line)',
    '_WORKSPACE_UUID_RE.match(workspace_uuid)',
    'uuid.split("-")',
    'workspace_uuid.split("-")',
    'path.split("/")',
    'name.split()',
    'entity_id.split()',              # no separator argument
    'entity_id.upper()',
    'type_id.strip()',
    'line.startswith("#")',
    'type_id.startswith("f")',        # no colon — not kind sniffing
    'entities[0]',                    # subscript, but not an id key
    'row["name"].split(":")',
])
def test_negative_controls_do_not_fire(src):
    assert sites(src) == []


def test_prose_naming_an_idiom_cannot_produce_a_site():
    """Comments and docstrings are invisible: detection is over an AST."""
    src = (
        '"""Do not call entity_id.split(":") here — use entities.kind."""\n'
        '# entity_id.split(":")[0] would be wrong\n'
        'kind = entity["kind"]\n'
    )
    assert sites(src) == []


def test_a_site_reports_its_line_and_idiom():
    src = 'a = 1\nb = 2\nkind = type_id.split(":")[0]\n'
    found = sites(src)
    assert len(found) == 1
    assert found[0].lineno == 3
    assert found[0].idiom == "split"
    assert found[0].receiver == "type_id"


class TestTemplateScanning:
    """B2: Jinja templates are scanned exactly as .py files are."""

    def test_reports_type_id_split_in_an_output_expression(self, tmp_path):
        tpl = tmp_path / "t.html"
        tpl.write_text(
            "<div>\n"
            "  {{ item.entity_name or item.type_id.split(':')[1] }}\n"
            "</div>\n"
        )
        sites = scan_template(tpl)
        assert [(s.lineno, s.idiom) for s in sites] == [(2, "split")]

    def test_reports_type_id_split_in_a_set_tag(self, tmp_path):
        tpl = tmp_path / "t.html"
        tpl.write_text("{% set kind = item.type_id.split(':')[0] %}\n")
        sites = scan_template(tpl)
        assert [(s.lineno, s.idiom) for s in sites] == [(1, "split")]

    @pytest.mark.parametrize("label,src", [
        ("if", "{% if item.type_id.split(':')[0] == 'feature' %}x{% endif %}\n"),
        ("elif", "{% if x %}a{% elif item.type_id.split(':')[0] %}b{% endif %}\n"),
        ("for", "{% for p in item.type_id.split(':') %}x{% endfor %}\n"),
        ("tuple_set", "{% set a, b = item.type_id.split(':') %}\n"),
    ])
    def test_statement_tags_are_scanned(self, tmp_path, label, src):
        """All four were MISSED before the tag scan was generalised.

        The first version had a `set`-only regex requiring a single
        identifier target, so an if/for/elif tag or a tuple target carried an
        undetected parser straight past the cutover.
        """
        tpl = tmp_path / f"{label}.html"
        tpl.write_text(src)
        assert [s.idiom for s in scan_template(tpl)] == ["split"]

    def test_tags_without_identity_are_not_sites(self, tmp_path):
        tpl = tmp_path / "t.html"
        tpl.write_text(
            "{% block title %}hello{% endblock %}\n"
            "{% for x in items %}{{ x.name }}{% endfor %}\n"
        )
        assert scan_template(tpl) == []

    def test_multiline_expression_reports_the_offending_line(self, tmp_path):
        """`.strip()` eats the leading newline, so anchoring the rebase on the
        match start reported this one line early."""
        tpl = tmp_path / "t.html"
        tpl.write_text("<div>\n  {{\n    item.type_id.split(':')[0]\n  }}\n</div>\n")
        assert [s.lineno for s in scan_template(tpl)] == [3]

    def test_line_numbers_are_rebased_onto_the_template(self, tmp_path):
        """The offending line, not the first line of the file.

        ast parses each expression standalone, so its linenos start at 1. A
        detector that forgot to rebase would report every template site at
        line 1 and still look like it worked.
        """
        tpl = tmp_path / "t.html"
        tpl.write_text("\n" * 40 + "{{ e.type_id.split(':')[0] }}\n")
        assert [s.lineno for s in scan_template(tpl)] == [41]

    def test_plain_markup_is_not_a_site(self, tmp_path):
        """A comment body that IS valid Python, so this tests exclusion.

        The original used ``{# item.type_id.split(':') in a comment #}``,
        whose body fails to parse ("unexpected indent") — so it passed via
        the parse guard and would have kept passing even if ``{# #}`` were
        scanned. This body parses cleanly, so the only thing keeping it out
        of the results is that comments are not matched at all.
        """
        tpl = tmp_path / "t.html"
        tpl.write_text(
            "<a href='/entities/{{ item.type_id }}'>{{ item.name }}</a>\n"
            "{#item.type_id.split(':')[0]#}\n"
        )
        assert scan_template(tpl) == []

    def test_a_comment_does_not_shift_a_real_site(self, tmp_path):
        tpl = tmp_path / "t.html"
        tpl.write_text("{#item.type_id.split(':')[0]#}\n{{ e.type_id.split(':')[0] }}\n")
        assert [s.lineno for s in scan_template(tpl)] == [2]

    def test_jinja_filters_and_tests_still_parse(self, tmp_path):
        """Filters are Python BinOp, so they do NOT defeat detection.

        Worth pinning because it is counterintuitive: ``|`` and ``is`` read as
        Jinja-only syntax but are valid Python operators, so these sites are
        analysed normally rather than silently skipped.
        """
        tpl = tmp_path / "t.html"
        tpl.write_text(
            "{{ item.type_id.split(':')[0] | upper }}\n"
            "{{ item.type_id.split(':')[1] | default('x') }}\n"
        )
        assert [s.lineno for s in scan_template(tpl)] == [1, 2]

    def test_jinja_only_syntax_is_skipped_not_crashed(self, tmp_path):
        """The two real blind spots, pinned so they stay deliberate.

        Jinja's ``~`` concatenation and its ``if`` without ``else`` are not
        valid Python, so those expressions do not parse and any site inside
        them goes unreported. Accepted cost of reusing the Python AST walker;
        this test exists so the gap is on record rather than a surprise.
        """
        tpl = tmp_path / "t.html"
        tpl.write_text(
            "{{ item.type_id.split(':')[0] ~ '-suffix' }}\n"
            "{{ item.type_id.split(':')[1] if item }}\n"
        )
        assert scan_template(tpl) == []

    def test_real_card_template_reports_both_known_sites(self):
        card = (
            Path(__file__).resolve().parents[3] / "ui" / "templates" / "_card.html"
        )
        assert card.exists(), "the B2 fixture template moved"
        assert sorted(s.lineno for s in scan_template(card)) == [4, 10]
