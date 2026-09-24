"""C5b step 1: parse_backlog_md's defensive insert names the __unknown__ workspace
by uuid, no longer through the ``project_id="__unknown__"`` alias.

The ``entity_created`` label stays ``"__unknown__"``: it is that workspace's
``project_id_legacy``, and it is what the alias wrote before.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parents[1]
_HOOKS_LIB = Path(__file__).resolve().parents[2] / "hooks" / "lib"
for _path in (_SCRIPT_DIR, _HOOKS_LIB):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import parse_backlog_md  # noqa: E402
from entity_registry import database as database_module  # noqa: E402
from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase  # noqa: E402


def test_defensive_insert_registers_in_the_unknown_workspace_by_uuid(monkeypatch):
    db = EntityDatabase(":memory:")

    class _ThisRegistry:
        def __new__(cls, *_args, **_kwargs):
            return db

    monkeypatch.setattr(database_module, "EntityDatabase", _ThisRegistry)
    registrations: list[dict] = []
    original = db.register_entity
    signature = inspect.signature(original)

    def recording(*args, **kwargs):
        registrations.append(dict(signature.bind(*args, **kwargs).arguments))
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "register_entity", recording)
    records = [{"entity_id": "077-from-markdown", "format": "table_row", "section": None,
                "section_intro": None, "subsection": None, "name": "From markdown"}]

    result = parse_backlog_md.apply_records(records, db_path=":memory:")

    assert result["inserted"] == 1
    assert len(registrations) == 1
    assert registrations[0].get("project_id") is None, registrations[0]
    assert registrations[0].get("workspace_uuid") == _UNKNOWN_WORKSPACE_UUID
    entity = db.get_entity("backlog:077-from-markdown")
    assert entity["workspace_uuid"] == _UNKNOWN_WORKSPACE_UUID
    label = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = 'backlog:077-from-markdown' AND event_type = 'entity_created'"
    ).fetchall()
    assert [row[0] for row in label] == ["__unknown__"]
    db.close()
