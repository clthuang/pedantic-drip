"""C23: a build must not write a file stamped newer than it understands.

Both migration loops are ``range(current + 1, target + 1)``, so a file
above this build's max iterates zero times and then proceeds to write
normally. Nothing else on the write path reads the version — the only
``V2_SCHEMA_VERSION`` reference is an import-time assert comparing the
build to itself.

The scenario is not hypothetical: the plugin is installed once, globally,
and shared by every workspace. Updating it does not restart running MCP
servers, so an old process keeps serving requests against a file a newer
process has already migrated.

**What these tests cannot observe.** No test here runs a different
process on different code. They stand in for that with a file stamped
above the build's max, which is the same condition the old process would
see. That is a proxy, stated rather than implied.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from entity_registry.database import (
    MIGRATIONS,
    V2_MIGRATIONS,
    EntityDatabase,
)


def _future_file(tmp_path, bump: int = 1, generation: str = "v1"):
    """A database stamped *bump* versions above this build's max."""
    seed = tmp_path / "seed.db"
    EntityDatabase(str(seed)).close()
    path = tmp_path / "future.db"
    shutil.copy(seed, path)
    conn = sqlite3.connect(str(path))
    build_max = max(V2_MIGRATIONS) if generation == "v2" else max(MIGRATIONS)
    conn.execute(
        "UPDATE _metadata SET value = ? WHERE key = 'schema_version'",
        (str(build_max + bump),),
    )
    if generation == "v2":
        conn.execute(
            "INSERT OR REPLACE INTO _metadata(key, value) "
            "VALUES('schema_generation', 'v2')"
        )
    conn.commit()
    conn.close()
    return path


class TestFutureFileIsReadOnly:
    def test_reads_still_work(self, tmp_path):
        """Refusing to OPEN would break doctor, the UI and every census for
        everyone on the old build, not just the writers. Schema growth is
        additive, so a newer file is almost always readable."""
        db = EntityDatabase(str(_future_file(tmp_path)))
        assert db._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0

    @pytest.mark.parametrize("stmt", [
        "INSERT INTO workspaces(uuid,project_id_legacy,project_root,"
        "created_at,updated_at) VALUES('z','z','/z','t','t')",
        "UPDATE _metadata SET value='x' WHERE key='schema_version'",
        "DELETE FROM entities",
        "CREATE TABLE evil(x)",
        "DROP TABLE entities",
        "ALTER TABLE entities ADD COLUMN evil TEXT",
    ])
    def test_every_raw_write_form_is_denied(self, tmp_path, stmt):
        """Raw ``db._conn`` writes included, deliberately.

        A guard in ``_commit`` would miss these: nine call sites already
        commit via ``self._conn`` directly, and any caller holding ``_conn``
        bypasses a Python-level check entirely. The authorizer sits below
        all of them.
        """
        db = EntityDatabase(str(_future_file(tmp_path)))
        with pytest.raises(sqlite3.DatabaseError):
            db._conn.execute(stmt)

    def test_public_api_write_is_denied(self, tmp_path):
        db = EntityDatabase(str(_future_file(tmp_path)))
        with pytest.raises(Exception):
            db.register_entity(
                "feature", entity_id="001-x", name="x",
                workspace_uuid="w", _strict_id_format=False,
            )

    def test_the_version_is_not_advanced(self, tmp_path):
        """The migration loop must not run. If it did, this build would stamp
        its own lower max over a higher one and lose the signal."""
        expected = max(MIGRATIONS) + 1
        db = EntityDatabase(str(_future_file(tmp_path)))
        assert db.get_schema_version() == expected

    def test_v2_generation_is_compared_against_the_v2_max(self, tmp_path):
        """The two chains have different maxima — v1 is at 25, v2 at 7.

        Comparing a v2 file against the v1 max would never fire, since every
        v2 version is far below it. This is the case a single hardcoded
        maximum gets wrong.
        """
        db = EntityDatabase(str(_future_file(tmp_path, generation="v2")))
        assert db._is_v2_generation
        assert db.future_file_build_max == max(V2_MIGRATIONS)
        with pytest.raises(sqlite3.DatabaseError):
            db._conn.execute("DELETE FROM entities")


class TestCurrentFilesAreUnaffected:
    def test_a_fresh_database_writes_normally(self, tmp_path):
        """The guard must be invisible at the current version — otherwise it
        would have bricked every workspace the moment it shipped."""
        db = EntityDatabase(str(tmp_path / "fresh.db"))
        now = db._now_iso()
        db._conn.execute(
            "INSERT INTO workspaces(uuid,project_id_legacy,project_root,"
            "created_at,updated_at) VALUES(?,?,?,?,?)",
            ("w", "legacy", str(tmp_path), now, now),
        )
        db._conn.commit()
        assert db.get_schema_version() == max(MIGRATIONS)
        assert not hasattr(db, "future_file_version")

    def test_a_file_at_exactly_the_build_max_is_writable(self, tmp_path):
        """Off-by-one guard: the condition is `>`, not `>=`. A `>=` would
        refuse every up-to-date file, which is every file."""
        db = EntityDatabase(str(_future_file(tmp_path, bump=0)))
        db._conn.execute("DELETE FROM entities")
        db._conn.commit()
