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

from doctor.identity_inference import InferenceSite, iter_inference_sites


def sites(src: str) -> list[InferenceSite]:
    return list(iter_inference_sites(ast.parse(src), "<fixture>"))


def idioms(src: str) -> set[str]:
    return {s.idiom for s in sites(src)}


# ---------------------------------------------------------------------------
# Receiver forms — the axis the old pattern got wrong
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("receiver", [
    "entity_id",            # the only spelling the old grep knew
    "eid",                  # database.py:10281
    "tid",
    "type_id",
    "feature_type_id",      # engine.py:376, feature_lifecycle.py:97
    "old_type_id",          # database.py:7815
    "parent_type_id",       # backfill.py:752
    "proj_entity_id",
])
def test_bare_name_receivers_are_recognised(receiver):
    assert idioms(f'{receiver}.split(":")[1]') == {"split"}


@pytest.mark.parametrize("expr", [
    'entity["type_id"]',        # frontmatter_sync.py:109
    "row['entity_id']",         # reconciliation.py:787
    'anomaly["type_id"]',       # rebuild_tool.py:1138
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
