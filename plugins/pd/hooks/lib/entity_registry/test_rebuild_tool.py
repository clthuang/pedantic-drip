"""Tests for entity_registry.rebuild_tool (feature 132, Task 1 slice).

Covers design D1's three-step Scope-model build (chain replay -> selective
v2 seed -> generation stamp) and spec FR132-1's ``_migrate()`` generation
guard, both scoped to Task 1's "build steps only" slice (tasks.md: the
tool exposes ``--staging-only`` because task 2's backfill/report/cutover
machinery doesn't exist yet).

H6/#059 (spec Hazards): the fork-race flake (``TestMigration11ConcurrentRunners``,
backlog #059) lives in the OLD migration chain's tests — nothing in this
file uses multiprocessing/threading/forking; every test here is a plain
sequential sqlite3 sequence on its own tmp_path.
"""
from __future__ import annotations

import inspect
import re
import sqlite3

import pytest

from entity_registry import database
from entity_registry import rebuild_tool
from entity_registry import schema_v2

_NOW = "2026-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test (mirrors
    test_axes.py/test_schema_v2.py's established idiom).

    ``build_staging_database`` calls ``axes.register_vocab_ddl()`` as
    PRODUCTION behavior (D1 step 2), so without this, "axes_vocab_triggers"
    would leak into whatever test runs next in this process.
    """
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


def _insert_probe_workspace_and_entity(conn: sqlite3.Connection) -> None:
    """Minimal workspace + entity row so an events insert has a valid FK
    target — shared by the tests below that need one."""
    conn.execute(
        "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
        "VALUES ('ws-probe', '/tmp/probe', ?, ?)",
        (_NOW, _NOW),
    )
    conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, "
        "status, parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, kind, lifecycle_class) VALUES "
        "('e-probe', 'ws-probe', 'feature:probe', 'probe', 'Probe', NULL, NULL, "
        "NULL, ?, ?, NULL, 'work', 'feature', 'feature_flow')",
        (_NOW, _NOW),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# SC1: fresh-bootstrap — the tool creates the new file from empty.
# ---------------------------------------------------------------------------
class TestBuildStagingDatabase:
    def test_fresh_bootstrap_stamps_generation_and_version(self, tmp_path):
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        try:
            rows = dict(
                conn.execute(
                    "SELECT key, value FROM _metadata "
                    "WHERE key IN ('schema_generation', 'schema_version')"
                ).fetchall()
            )
        finally:
            conn.close()
        assert rows["schema_generation"] == "v2"
        assert rows["schema_version"] == str(schema_v2.V2_SCHEMA_VERSION)

    def test_metadata_carries_a_single_schema_version_cell(self, tmp_path):
        """#062 non-vacuity: exactly ONE row for the schema_version key —
        a duplicate-INSERT bug would leave more than one."""
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM _metadata WHERE key = 'schema_version'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1

    def test_upsert_re_stamp_updates_existing_cell_not_ignored(self, tmp_path):
        """#062 upsert re-bootstrap test: re-stamping with a DIFFERENT
        version value updates the existing cell in place — a plain
        INSERT OR IGNORE would silently keep the original value."""
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        try:
            database._upsert_metadata(conn, "schema_version", "999")
            conn.commit()
            rows = conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
        finally:
            conn.close()
        assert rows == [("999",)]

    def test_chain_shaped_tables_present_from_step_one(self, tmp_path):
        """Step 1: the v1 chain replay's operational shapes survive
        step 2's selective seed untouched."""
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        try:
            table_names = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            conn.close()
        for expected in (
            "entities", "workflow_phases", "phase_events", "entity_relations",
            "workspaces", "sequences", "entities_fts",
        ):
            assert expected in table_names

    def test_v2_event_core_seeded_from_step_two(self, tmp_path):
        """Step 2: events + the two views + entity_phase_status land on
        the SAME file as step 1's chain-shaped tables (not a separate
        v2 database)."""
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        try:
            names = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                ).fetchall()
            }
        finally:
            conn.close()
        for expected in (
            "events", "entity_axis_state", "entity_state", "entity_phase_status",
        ):
            assert expected in names

    def test_122_vocab_triggers_fire_on_the_new_file_from_birth(self, tmp_path):
        """SC1 non-vacuity: an out-of-vocabulary to_value write on the
        pipeline axis is rejected on the tool's own output, AND a
        genuinely valid value is still accepted (positive control — a
        blanket-rejecting trigger would pass the negative half alone)."""
        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)

        conn = sqlite3.connect(staging_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            _insert_probe_workspace_and_entity(conn)

            with pytest.raises(sqlite3.IntegrityError, match="out-of-vocabulary"):
                conn.execute(
                    "INSERT INTO events (uuid, entity_uuid, event_type, axis, "
                    "to_value, actor, timestamp) VALUES "
                    "('ev-bad', 'e-probe', 'phase_completed', 'pipeline', "
                    "'not-a-real-phase', 'test-actor', ?)",
                    (_NOW,),
                )
            zero_rows = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert zero_rows == 0

            conn.execute(
                "INSERT INTO events (uuid, entity_uuid, event_type, axis, "
                "to_value, actor, timestamp) VALUES "
                "('ev-good', 'e-probe', 'phase_completed', 'pipeline', "
                "'design', 'test-actor', ?)",
                (_NOW,),
            )
            conn.commit()
            one_row = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert one_row == 1
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# FR132-1: the _migrate() generation guard, tested non-vacuously (SC1).
# ---------------------------------------------------------------------------
class TestMigrateGenerationGuardNonVacuity:
    """At HEAD, MIGRATIONS tops out at 19, so range(20, 20) is empty
    regardless of any guard — a bare "zero migrations ran" assertion
    would pass vacuously. A phantom migration 20 (test-scoped MIGRATIONS
    entry) makes the range non-empty, so the guard's short-circuit is
    the ONLY thing that can still block it."""

    def test_v2_generation_file_skips_the_phantom_migration(
        self, tmp_path, monkeypatch
    ):
        # Given a genuinely v2-stamped file (built before the phantom
        # migration is registered, so it only replays the real 1-19 chain).
        staging_path = str(tmp_path / "v2-guard-probe.db")
        rebuild_tool.build_staging_database(staging_path)

        # When a phantom migration 20 is registered AFTER the stamp
        # lands, and the file is opened again
        calls = []
        monkeypatch.setitem(database.MIGRATIONS, 20, lambda conn: calls.append(20))
        db = database.EntityDatabase(staging_path)
        db.close()

        # Then the guard short-circuits before the loop — it never runs
        assert calls == []

    def test_v1_file_positive_control_runs_the_phantom_migration(
        self, tmp_path, monkeypatch
    ):
        """Proves the harness itself is capable of detecting a missing
        guard: an ordinary v1 file (no schema_generation stamp) DOES run
        migration 20 once it's registered — a guard that always
        short-circuited (broken in the OTHER direction) would fail this
        half instead."""
        # Given an ordinary v1 file at the real ceiling (19), unstamped
        v1_path = str(tmp_path / "v1-positive-control.db")
        db = database.EntityDatabase(v1_path)
        db.close()

        # When a phantom migration 20 is registered and the file reopened
        calls = []
        monkeypatch.setitem(database.MIGRATIONS, 20, lambda conn: calls.append(20))
        db = database.EntityDatabase(v1_path)
        db.close()

        # Then it DOES run
        assert calls == [20]


# ---------------------------------------------------------------------------
# D6.5 call-half / plan.md "chain-replay DDL-identity": removing the
# _atomic_write_workspace_mapping call from migration 11 must not change
# what migration 11 BUILDS — only that it no longer writes a JSON audit
# file (#066's root cause).
# ---------------------------------------------------------------------------
class TestMigrationElevenCallSiteRemoved:
    def test_workspace_identity_ddl_survives_the_removed_call(
        self, tmp_path, monkeypatch
    ):
        # Given a fresh CWD and no PD_WORKSPACE_ROOT override: if the
        # removed call site regressed, the stray JSON would land here.
        fresh_cwd = tmp_path / "cwd"
        fresh_cwd.mkdir()
        monkeypatch.delenv("PD_WORKSPACE_ROOT", raising=False)
        monkeypatch.chdir(fresh_cwd)

        staging_path = str(tmp_path / "chain-replay.db")

        # When the chain replay runs (step 1 alone — the only step that
        # executes migration bodies)
        rebuild_tool._replay_v1_chain(staging_path)

        # Then migration 11's DDL/DML artifacts are all present
        conn = sqlite3.connect(staging_path)
        try:
            entities_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(entities)").fetchall()
            }
            workspaces_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(workspaces)").fetchall()
            }
            trigger_names = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
            }
            version = conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchone()[0]
        finally:
            conn.close()

        assert "workspace_uuid" in entities_cols
        assert workspaces_cols == {
            "uuid", "project_id_legacy", "project_root", "created_at", "updated_at",
        }
        assert {"wp_reject_orphaned_insert", "wp_autofill_workspace_uuid"} <= trigger_names
        assert version == str(max(database.MIGRATIONS))

        # And no stray audit JSON anywhere under the fresh CWD.
        assert not (fresh_cwd / ".claude").exists()


# ---------------------------------------------------------------------------
# D1: "Implement verifies no OTHER migration has an unguarded filesystem
# side effect on an empty file (grep os.\b/open( in migration bodies)" —
# codified so a FUTURE migration reintroducing one fails this suite
# instead of silently repeating the #066 class.
# ---------------------------------------------------------------------------
_FS_SIDE_EFFECT_RE = re.compile(r"\bos\.|open\(")

# Migration 13's env-var feature-flag READ is the one documented
# exception (os.environ.get, not a filesystem WRITE) — D1's grep pattern
# is textual and can't itself distinguish read from write.
_ALLOWLISTED_LINE = 'os.environ.get("PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS")'


class TestMigrationBodySideEffectSweep:
    def test_no_unguarded_filesystem_side_effects_in_migration_bodies(self):
        offending = []
        for version, migration_fn in database.MIGRATIONS.items():
            source_lines = inspect.getsource(migration_fn).splitlines()
            for line in source_lines:
                stripped = line.strip()
                if not _FS_SIDE_EFFECT_RE.search(stripped):
                    continue
                if _ALLOWLISTED_LINE in stripped:
                    continue
                offending.append((version, stripped))
        assert offending == []


# ---------------------------------------------------------------------------
# default_staging_path / --staging-only CLI wiring.
# ---------------------------------------------------------------------------
class TestDefaultStagingPath:
    def test_uses_yyyymmdd_convention_beside_the_live_path(self):
        result = rebuild_tool.default_staging_path(
            "/home/user/.claude/pd/entities/entities.db"
        )
        prefix = "/home/user/.claude/pd/entities/entities.db.rebuild-"
        assert result.startswith(prefix)
        suffix = result[len(prefix):]
        assert len(suffix) == 8 and suffix.isdigit()


class TestStagingOnlyCli:
    def test_staging_only_builds_and_exits_zero(self, tmp_path):
        staging_path = tmp_path / "cli-staging.db"
        exit_code = rebuild_tool.main(
            ["--staging-only", "--staging-path", str(staging_path)]
        )
        assert exit_code == 0
        assert staging_path.exists()

    def test_without_staging_only_reports_not_yet_implemented(self, tmp_path):
        staging_path = tmp_path / "cli-staging-2.db"
        exit_code = rebuild_tool.main(["--staging-path", str(staging_path)])
        assert exit_code != 0
        assert not staging_path.exists()

    def test_refuses_to_overwrite_an_existing_staging_path(self, tmp_path):
        staging_path = tmp_path / "cli-staging-3.db"
        staging_path.write_bytes(b"")
        exit_code = rebuild_tool.main(
            ["--staging-only", "--staging-path", str(staging_path)]
        )
        assert exit_code != 0
