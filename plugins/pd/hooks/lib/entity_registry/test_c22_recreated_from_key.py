"""C22: the record of which new entity replaced which legacy original.

``scripts/c22_recreate_live_remainder.py`` recreates live legacy rows as new
entities. Each replacement stores the uuids of the originals it replaces
under one registered metadata key, written with the replacement itself. A
re-run reads that key to know an original is already done. The key is
registered for the two kinds C22 recreates, backlog and project, so writing
it raises no "unknown key" warning and a value of the wrong type is named.
"""
from __future__ import annotations

from entity_registry.metadata import RECREATED_FROM_KEY, validate_metadata

ORIGINAL_UUIDS = ["019f972c-80c7-7055-b724-d88782058418", "019f972c-80c7-7055-b724-d8d289bc6fd7"]


def test_the_stored_key_name_is_recreated_from():
    # Stored in registry rows, so renaming the constant would strand them.
    assert RECREATED_FROM_KEY == "recreated_from"


def test_recreated_from_is_registered_for_backlog_and_project():
    for kind in ("backlog", "project"):
        assert validate_metadata(kind, {RECREATED_FROM_KEY: ORIGINAL_UUIDS}) == []


def test_recreated_from_beside_each_kinds_ordinary_keys_is_valid():
    backlog = {"description": "full text", RECREATED_FROM_KEY: ORIGINAL_UUIDS[:1]}
    project = {
        "id": "005", "slug": "iflow-arch-evolution", "features": [], "milestones": [],
        RECREATED_FROM_KEY: ORIGINAL_UUIDS,
    }
    assert validate_metadata("backlog", backlog) == []
    assert validate_metadata("project", project) == []


def test_a_recreated_from_that_is_not_a_list_is_named():
    assert validate_metadata("backlog", {RECREATED_FROM_KEY: ORIGINAL_UUIDS[0]}) == [
        "Metadata key 'recreated_from' for backlog: expected list, got str"
    ]
