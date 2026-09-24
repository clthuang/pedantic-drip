"""Shared test constants and helpers for entity_registry tests."""
from __future__ import annotations

import sqlite3
import uuid as _uuid
from pathlib import Path

from entity_registry.id_generator import registration_identity

TEST_PROJECT_ID = "__test__"


def identity_kwargs(kind: str, display_text: str) -> dict:
    """``register_entity``'s identity keywords for a test id written as display text.

    Fixtures write ids the way they display (``"001-f1"``); registration takes
    them as data. Literal ids are written out as ``seq=``/``slug=`` instead;
    this is for ids a test builds or forwards. Unlike production's
    ``registration_identity``, an id with no structured form is a fixture
    bug here, so it raises.
    """
    identity = registration_identity(kind, display_text)
    if identity is None:
        raise ValueError(f"{display_text!r} does not round-trip as a {kind} id")
    return identity


def seed_legacy_entity(db, kind: str, legacy_id: str, name: str, *,
                       workspace_uuid: str | None = None, status: str | None = None) -> str:
    """Insert a pre-cutover row as history left it: ``is_legacy = 1``, no display row.

    Registration takes only structured identity, so a legacy id (``00019``,
    ``P001``) can no longer be registered; and ``is_legacy`` cannot change
    after insert, so the row is written whole here. Returns its uuid.
    """
    from entity_registry.database import _derive_type_and_lifecycle

    if workspace_uuid is None:
        db._ensure_unknown_workspace_row()
        workspace_uuid = get_test_workspace_uuid()
    entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
    entity_uuid = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, status, "
        "created_at, updated_at, type, kind, lifecycle_class, is_legacy) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (entity_uuid, workspace_uuid, f"{kind}:{legacy_id}", legacy_id, name, status,
         now, now, entity_type, kind, lifecycle_class),
    )
    db._conn.commit()
    return entity_uuid


def bootstrap_test_workspace(db, legacy_id: str = TEST_PROJECT_ID) -> str:
    """Insert a workspaces row for ``legacy_id`` (post-Migration-11 prereq).

    Helper for ad-hoc test files that build their own EntityDatabase
    instances and register entities in the workspace of ``legacy_id``.
    Returns the workspace UUID for callers that want it; callers that did
    not keep it read it back with :func:`workspace_uuid_for`.
    """
    ws_uuid = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, legacy_id, None, now, now),
    )
    db._conn.commit()
    row = db._conn.execute(
        "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
        (legacy_id,),
    ).fetchone()
    return row["uuid"]


def workspace_uuid_for(db, legacy_id: str) -> str:
    """The uuid of the workspace a fixture seeded under ``legacy_id``.

    Fixtures seed workspaces by legacy project id (``TEST_PROJECT_ID``,
    ``"__other__"``, ``bootstrap_test_workspace(db, "P001")``) under random
    uuids, and registration takes the uuid, so this reads it back by
    ``workspaces.project_id_legacy``. The canonical unknown workspace needs no
    lookup: it is ``entity_registry.database._UNKNOWN_WORKSPACE_UUID``.

    Raises
    ------
    LookupError
        If no workspace carries ``legacy_id`` (the fixture never seeded it).
    """
    row = db._conn.execute(
        "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
        (legacy_id,),
    ).fetchone()
    if row is None:
        raise LookupError(
            f"no workspace seeded with project_id_legacy={legacy_id!r}"
        )
    return row["uuid"]


def get_test_workspace_uuid() -> str:
    """Return the canonical unknown-workspace UUID for test fixtures.

    Replaces the legacy ``project_id='__unknown__'`` literal across test
    fixtures. Pinned to ``"6250c8a6-5306-443f-b225-477a040016ea"``
    (FR-4 / design Decision 3 / Decision 12).

    The helper imports ``_UNKNOWN_WORKSPACE_UUID`` from
    ``entity_registry.database`` rather than recomputing — recomputing
    would defeat the purpose of pinning.

    Returns
    -------
    str
        The pinned canonical __unknown__ workspace UUID
        ("6250c8a6-5306-443f-b225-477a040016ea").
    """
    from entity_registry.database import _UNKNOWN_WORKSPACE_UUID
    return _UNKNOWN_WORKSPACE_UUID


def make_v10_db(path: Path | str | None = None) -> sqlite3.Connection:
    """Build a SQLite connection at exactly schema_version=10.

    Used by Migration 11 RED tests so they can exercise migration 11 against
    a known pre-11 baseline. **Do NOT use for live-DB testing** — the helper
    materialises the full pre-11 DDL in-process by running migrations 1-10.

    Parameters
    ----------
    path:
        File path or ``":memory:"``. ``None`` defaults to ``":memory:"``.

    Returns
    -------
    sqlite3.Connection
        Connection with row_factory set, busy_timeout pragma set, and the
        full pre-11 schema applied. ``_metadata.schema_version`` is the
        string ``'10'``.
    """
    from entity_registry.database import MIGRATIONS

    db_path = ":memory:" if path is None else str(path)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")

    # Bootstrap the _metadata table that the outer _migrate() loop creates.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()

    # Apply migrations 1-10 in order. Each migration manages its own
    # transaction; the outer loop also stamps schema_version.
    for version in sorted(MIGRATIONS.keys()):
        if version > 10:
            break
        MIGRATIONS[version](conn)
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(version)),
        )
        conn.commit()

    # Sanity check.
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "10", (
        f"make_v10_db: expected schema_version=10, got {v}"
    )
    return conn


def make_v11_db(path: Path | str | None = None) -> sqlite3.Connection:
    """Build a SQLite connection at exactly schema_version=11.

    Used by Migration 12 RED tests so they can exercise migration 12 against
    a known pre-12 baseline. Mirrors :func:`make_v10_db` but iterates
    ``MIGRATIONS[1..11]``.

    Parameters
    ----------
    path:
        File path or ``":memory:"``. ``None`` defaults to ``":memory:"``.

    Returns
    -------
    sqlite3.Connection
        Connection with row_factory set, busy_timeout pragma set, and the
        full pre-12 schema applied. ``_metadata.schema_version`` is the
        string ``'11'``.
    """
    from entity_registry.database import MIGRATIONS

    db_path = ":memory:" if path is None else str(path)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")

    # Bootstrap the _metadata table that the outer _migrate() loop creates.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()

    # Apply migrations 1-11 in order.
    for version in sorted(MIGRATIONS.keys()):
        if version > 11:
            break
        MIGRATIONS[version](conn)
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(version)),
        )
        conn.commit()

    # Sanity check.
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "11", (
        f"make_v11_db: expected schema_version=11, got {v}"
    )
    return conn


def make_v12_db(path: Path | str | None = None) -> sqlite3.Connection:
    """Build a SQLite connection at exactly schema_version=12.

    Used by feature 109 (polymorphic taxonomy + event-sourced state) tests.
    Mirrors :func:`make_v10_db` but iterates ``MIGRATIONS[1..12]``. Migration
    12 is currently a stub that only stamps ``schema_version=12``; subsequent
    feature-109 tasks populate its body.

    Parameters
    ----------
    path:
        File path or ``":memory:"``. ``None`` defaults to ``":memory:"``.

    Returns
    -------
    sqlite3.Connection
        Connection with row_factory set, busy_timeout pragma set, and the
        full v12 schema applied. ``_metadata.schema_version`` is the string
        ``'12'``.
    """
    from entity_registry.database import MIGRATIONS

    db_path = ":memory:" if path is None else str(path)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA foreign_keys = ON")

    # Bootstrap the _metadata table that the outer _migrate() loop creates.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()

    # Apply migrations 1-12 in order.
    for version in sorted(MIGRATIONS.keys()):
        if version > 12:
            break
        MIGRATIONS[version](conn)
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(version)),
        )
        conn.commit()

    # Sanity check.
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "12", (
        f"make_v12_db: expected schema_version=12, got {v}"
    )
    return conn
