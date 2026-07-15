"""Tests for entity_registry.rebuild_tool (feature 132, Tasks 1+2).

Task 1 slice: design D1's three-step Scope-model build (chain replay ->
selective v2 seed -> generation stamp) and spec FR132-1's ``_migrate()``
generation guard.

Task 2 slice: D2's backfill (dedup, parent-topological order, uuid7
re-mint), D3's v2 event emission, the pre-import vocab diff (SC5 #077
clause), D6.9's ``sequences`` seed, D7's reports, D8's FTS population,
and D4's WAL-safe cutover swap.

H6/#059 (spec Hazards): the fork-race flake (``TestMigration11ConcurrentRunners``,
backlog #059) lives in the OLD migration chain's tests — nothing in this
file uses multiprocessing/threading/forking; every test here is a plain
sequential sqlite3 sequence on its own tmp_path.
"""
from __future__ import annotations

import inspect
import json
import re
import sqlite3
import uuid as uuid_mod
from pathlib import Path

import pytest

from entity_registry import axes
from entity_registry import database
from entity_registry import rebuild_tool
from entity_registry import schema_v2

_NOW = "2026-01-01T00:00:00Z"
_LATER = "2026-01-02T00:00:00Z"


@pytest.fixture(autouse=True)
def _isolate_rebuild_report_and_marker_dirs(monkeypatch, tmp_path):
    """Defense-in-depth: EVERY test in this file gets
    ``PD_REBUILD_REPORT_DIR``/``PD_REBUILD_MARKER_DIR`` pointed at its own
    tmp_path, regardless of whether the test itself remembers to pass
    ``--report-dir``/``--marker-dir`` explicitly. Without this, a
    ``main()`` call that omits either flag falls through to the REAL
    ``~/.claude/pd`` (production default, correct for actual CLI usage) —
    exactly the class of leak a prior run of this suite hit before this
    fixture existed (a stray ``~/.claude/pd/migrations/v2-cutover.json``
    from a --swap test that forgot --marker-dir)."""
    monkeypatch.setenv("PD_REBUILD_REPORT_DIR", str(tmp_path / "_autouse-reports"))
    monkeypatch.setenv("PD_REBUILD_MARKER_DIR", str(tmp_path / "_autouse-marker-home"))


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
# Task 2 fixture helpers: build OLD (v1-shaped) census files via the real
# migration chain (so every constraint the live file itself enforces is
# genuinely in force), then raw-SQL seed pathological data.
# ---------------------------------------------------------------------------


def _build_empty_old_v1_file(path) -> str:
    """A valid, chain-replayed, ZERO-entity v1 file — the minimal
    always-valid old-file fixture for tests that only need SOME --db
    target (CLI wiring tests, vocab-diff positive-path, etc.)."""
    db = database.EntityDatabase(str(path))
    db.close()
    return str(path)


def _relax_entities_unique_constraint(conn: sqlite3.Connection) -> None:
    """TEST-ONLY: rebuild ``entities`` WITHOUT its composite
    ``UNIQUE(workspace_uuid, type_id)`` constraint.

    A schema_version=19 file can never reach a within-workspace duplicate
    type_id state via any normal write path — the constraint is baked
    into the table's own CREATE (not a separately droppable index) and
    has been enforced since the row the census's own historical
    migration first built it. SC2's corpus still needs to model this
    pathology (design D2/#054(a)) to prove the backfill's dedup logic,
    so this helper constructs the ONE state a live file cannot reach —
    mirrors ``_copy_rename_entities_for_v14``'s capture/rebuild/restore
    idiom (database.py) sans the UNIQUE clause. Call BEFORE seeding any
    entities row, with ``PRAGMA foreign_keys = OFF`` (the caller's
    responsibility — this helper does not toggle it, since pathological
    parent references need the same OFF window, see
    :func:`_seed_pathological_corpus`).
    """
    saved_indexes = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name='entities' AND sql IS NOT NULL"
    ).fetchall()
    saved_triggers = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='trigger' AND tbl_name='entities' AND sql IS NOT NULL"
    ).fetchall()
    cross_triggers = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type='trigger' AND tbl_name != 'entities' "
        "AND sql LIKE '%entities%' AND sql IS NOT NULL"
    ).fetchall()
    for name, _sql in cross_triggers:
        conn.execute(f"DROP TRIGGER IF EXISTS {name}")

    conn.execute("""
        CREATE TABLE entities_relaxed (
            uuid           TEXT NOT NULL PRIMARY KEY,
            workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid),
            type_id        TEXT NOT NULL,
            entity_id      TEXT NOT NULL,
            name           TEXT NOT NULL,
            status         TEXT,
            parent_uuid    TEXT REFERENCES entities_relaxed(uuid),
            artifact_path  TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            metadata       TEXT,
            type           TEXT NOT NULL DEFAULT 'work',
            kind           TEXT NOT NULL DEFAULT 'feature',
            lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow',
            CHECK (
                (type='workspace' AND kind='workspace') OR
                (type='brainstorm' AND kind='brainstorm') OR
                (type='container' AND kind='project') OR
                (type='work' AND kind IN (
                    'feature','backlog','bug','initiative','objective','key_result','task'
                ))
            )
        )
    """)
    conn.execute("INSERT INTO entities_relaxed SELECT * FROM entities")
    conn.execute("DROP TABLE entities")
    conn.execute("ALTER TABLE entities_relaxed RENAME TO entities")
    for _name, sql in saved_indexes:
        conn.execute(sql)
    for _name, sql in saved_triggers:
        conn.execute(sql)
    for _name, sql in cross_triggers:
        conn.execute(sql)


def _seed_workspace(conn, uuid_, project_id_legacy, now=_NOW) -> None:
    conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (uuid_, project_id_legacy, f"/tmp/{project_id_legacy}", now, now),
    )


def _seed_entity(
    conn, *, uuid_, workspace_uuid, kind, entity_id, name, status=None,
    parent_uuid=None, created_at=_NOW, updated_at=_NOW, entity_type="work",
    lifecycle_class="feature_flow", metadata=None,
) -> None:
    type_id = f"{kind}:{entity_id}"
    metadata_json = json.dumps(metadata) if metadata is not None else None
    conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, "
        "status, parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, kind, lifecycle_class) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)",
        (uuid_, workspace_uuid, type_id, entity_id, name, status, parent_uuid,
         created_at, updated_at, metadata_json, entity_type, kind, lifecycle_class),
    )


def _seed_workflow_phase(
    conn, *, type_id, workspace_uuid, workflow_phase=None, kanban_column="backlog",
    last_completed_phase=None, mode=None, updated_at=_NOW,
) -> None:
    conn.execute(
        "INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase, "
        "last_completed_phase, mode, backward_transition_reason, updated_at, "
        "uuid, workspace_uuid) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?)",
        (type_id, kanban_column, workflow_phase, last_completed_phase, mode,
         updated_at, workspace_uuid),
    )


def _seed_phase_event(
    conn, *, type_id, project_id, event_type, phase=None, timestamp=_NOW,
    iterations=None, reviewer_notes=None, backward_reason=None,
    backward_target=None, metadata=None, created_at=_NOW,
) -> None:
    metadata_json = json.dumps(metadata) if metadata is not None else None
    conn.execute(
        "INSERT INTO phase_events (type_id, project_id, phase, event_type, "
        "timestamp, iterations, reviewer_notes, backward_reason, "
        "backward_target, source, created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', ?, ?)",
        (type_id, project_id, phase, event_type, timestamp, iterations,
         reviewer_notes, backward_reason, backward_target, created_at, metadata_json),
    )


def _seed_entity_relation(conn, *, from_uuid, to_uuid, kind, created_at=_NOW) -> None:
    conn.execute(
        "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
        "VALUES (?, ?, ?, ?)",
        (from_uuid, to_uuid, kind, created_at),
    )


def _build_pathological_corpus(path) -> str:
    """SC2's corpus: empty ids, WITHIN-workspace duplicate (keep-newest,
    loser relations/phase_events re-point to survivor), cross-workspace
    P001s preserved un-deduped, a uuid4-shaped row, blocks edges (+ a
    dedup-collision edge), a parent cycle, an orphan parent, 5D +
    lifecycle phase histories, and a bug-kind entity.

    Two workspaces: ws-alpha (legacy id 'alpha'), ws-beta (legacy id
    'beta'). Built with ``PRAGMA foreign_keys = OFF`` (re-enabled before
    close, WITHOUT a retroactive ``foreign_key_check`` — the orphan
    parent and parent cycle are deliberately left FK-invalid on the OLD
    file; that is exactly the pathology under test) and the entities
    UNIQUE relaxed (the within-workspace duplicate pathology).
    """
    db = database.EntityDatabase(str(path))
    db.close()

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = OFF")
    _seed_workspace(conn, "ws-alpha", "alpha")
    _seed_workspace(conn, "ws-beta", "beta")
    _relax_entities_unique_constraint(conn)

    # Cross-workspace P001s — preserved un-deduped (different workspace_uuid).
    uuid4_project_alpha = f"uuid4-{uuid_mod.uuid4()}"
    _seed_entity(
        conn, uuid_=uuid4_project_alpha, workspace_uuid="ws-alpha", kind="project",
        entity_id="P001", name="Alpha Project", status="active",
        entity_type="container", lifecycle_class="container_flow",
    )
    _seed_entity(
        conn, uuid_="proj-beta", workspace_uuid="ws-beta", kind="project",
        entity_id="P001", name="Beta Project", status="active",
        entity_type="container", lifecycle_class="container_flow",
    )

    # WITHIN-workspace duplicate type_id: dup-winner (newest updated_at) survives.
    _seed_entity(
        conn, uuid_="dup-loser", workspace_uuid="ws-alpha", kind="feature",
        entity_id="003-dup-feature", name="Loser", status="active",
        created_at=_NOW, updated_at=_NOW,
    )
    _seed_entity(
        conn, uuid_="dup-winner", workspace_uuid="ws-alpha", kind="feature",
        entity_id="003-dup-feature", name="Winner", status="active",
        created_at=_NOW, updated_at=_LATER,
    )

    # Empty entity_id AND name.
    _seed_entity(
        conn, uuid_="blank-id-entity", workspace_uuid="ws-alpha", kind="task",
        entity_id="", name="", status="active", lifecycle_class="task_flow",
    )

    # Parent cycle: cycle-a's parent is cycle-b, cycle-b's parent is cycle-a.
    _seed_entity(
        conn, uuid_="cycle-a", workspace_uuid="ws-alpha", kind="backlog",
        entity_id="005-cycle-a", name="Cycle A", parent_uuid="cycle-b",
        lifecycle_class="work_flow",
    )
    _seed_entity(
        conn, uuid_="cycle-b", workspace_uuid="ws-alpha", kind="backlog",
        entity_id="006-cycle-b", name="Cycle B", parent_uuid="cycle-a",
        lifecycle_class="work_flow",
    )

    # Orphan parent reference (missing old uuid).
    _seed_entity(
        conn, uuid_="orphan-child", workspace_uuid="ws-alpha", kind="task",
        entity_id="007-orphan", name="Orphan Child", parent_uuid="does-not-exist",
        lifecycle_class="task_flow",
    )

    # bug-kind entity (status-only model — no workflow_phases row).
    _seed_entity(
        conn, uuid_="bug-1", workspace_uuid="ws-alpha", kind="bug",
        entity_id="008-a-bug", name="A Bug", status="active",
        lifecycle_class="bug_flow",
    )

    # A full-history feature: brainstorm -> specify, parented under the
    # alpha project, with a workflow_phases row whose stored kanban_column
    # is DELIBERATELY stale (the import must overwrite it).
    _seed_entity(
        conn, uuid_="full-history-feature", workspace_uuid="ws-alpha", kind="feature",
        entity_id="009-full-history", name="Full History", status="active",
        parent_uuid=uuid4_project_alpha, created_at=_NOW, updated_at=_LATER,
    )
    _seed_workflow_phase(
        conn, type_id="feature:009-full-history", workspace_uuid="ws-alpha",
        workflow_phase="specify", kanban_column="blocked",  # stale on purpose
        last_completed_phase="brainstorm", mode="standard", updated_at=_LATER,
    )
    _seed_phase_event(
        conn, type_id="feature:009-full-history", project_id="alpha",
        event_type="started", phase="brainstorm", timestamp=_NOW, created_at=_NOW,
    )
    _seed_phase_event(
        conn, type_id="feature:009-full-history", project_id="alpha",
        event_type="completed", phase="brainstorm", iterations=1,
        timestamp=_NOW, created_at=_NOW,
    )
    _seed_phase_event(
        conn, type_id="feature:009-full-history", project_id="alpha",
        event_type="started", phase="specify", timestamp=_LATER, created_at=_LATER,
    )

    # 5D lifecycle phase history on the duplicate's SHARED type_id (belongs
    # to whichever entity survives dedup — the survivor, dup-winner).
    _seed_phase_event(
        conn, type_id="feature:003-dup-feature", project_id="alpha",
        event_type="started", phase="brainstorm", timestamp=_NOW, created_at=_NOW,
    )

    # backlog-kind 5D phase history (routes to lifecycle — non-feature kind).
    _seed_phase_event(
        conn, type_id="backlog:005-cycle-a", project_id="alpha",
        event_type="started", phase="discover", timestamp=_NOW, created_at=_NOW,
    )

    # entity_status_changed (non-phase, lifecycle axis, carried new_status).
    _seed_phase_event(
        conn, type_id="bug:008-a-bug", project_id="alpha",
        event_type="entity_status_changed", timestamp=_LATER, created_at=_LATER,
        metadata={"new_status": "blocked"},
    )

    # entity_relations: fixes + blocks, PLUS a loser-side edge that collides
    # with an existing survivor-side edge post-remap (dedup-collision path).
    _seed_entity_relation(conn, from_uuid="dup-winner", to_uuid="bug-1", kind="fixes")
    _seed_entity_relation(conn, from_uuid="bug-1", to_uuid="dup-winner", kind="blocks")
    _seed_entity_relation(conn, from_uuid="dup-loser", to_uuid="bug-1", kind="blocks")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    return str(path)


def _build_scale_corpus(
    path, *, entity_count: int = 533, workspace_count: int = 7, seed: int = 0x132,
) -> str:
    """D4b's ~533-entity corpus for :class:`TestResolverExplainAndLatency`
    — deterministic (seeded), mostly feature-kind with realistic
    phase_events depth so statement-2's measurement runs against a
    non-trivial events table (127 GO's scale)."""
    import random
    from datetime import datetime, timedelta, timezone

    rng = random.Random(seed)
    db = database.EntityDatabase(str(path))
    db.close()
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = OFF")

    workspace_uuids = [f"ws-scale-{i}" for i in range(workspace_count)]
    for i, ws in enumerate(workspace_uuids):
        _seed_workspace(conn, ws, f"scale-{i}")

    kinds = ["feature"] * 6 + ["task", "backlog", "bug"]
    statuses = ["active", "completed", "blocked", "planned"]
    lifecycle_by_kind = {
        "feature": "feature_flow", "task": "task_flow",
        "backlog": "work_flow", "bug": "bug_flow",
    }
    phases = list(axes.PIPELINE_PHASES)
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Monotonically-incrementing per-event clock: phase_events carries a
    # partial UNIQUE(type_id, phase, event_type, timestamp) WHERE
    # source='backfill' (migration 10, pre-dates this feature) — a
    # constant timestamp across many synthetic events risks colliding
    # once every copied row is re-stamped 'backfill' (database.py; see
    # rebuild_tool._emit_all_events' own defensive catch for the
    # production-side handling of a genuine collision).
    event_clock = [0]

    def _next_timestamp() -> str:
        event_clock[0] += 1
        return (epoch + timedelta(seconds=event_clock[0])).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i in range(entity_count):
        ws_index = i % workspace_count
        ws = workspace_uuids[ws_index]
        kind = rng.choice(kinds)
        entity_id = f"{i:04d}-entity"
        entity_uuid = f"scale-entity-{i}"
        _seed_entity(
            conn, uuid_=entity_uuid, workspace_uuid=ws, kind=kind,
            entity_id=entity_id, name=f"Entity {i}", status=rng.choice(statuses),
            lifecycle_class=lifecycle_by_kind[kind],
        )
        if kind == "feature":
            phase = None
            for _ in range(rng.randint(1, 4)):
                phase = rng.choice(phases)
                _seed_phase_event(
                    conn, type_id=f"feature:{entity_id}", project_id=f"scale-{ws_index}",
                    event_type=rng.choice(["started", "completed"]),
                    phase=phase, timestamp=_next_timestamp(),
                )
            _seed_workflow_phase(
                conn, type_id=f"feature:{entity_id}", workspace_uuid=ws,
                workflow_phase=phase, kanban_column="wip",
            )

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    return str(path)


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

    def test_without_staging_only_runs_the_full_backfill(self, tmp_path):
        """Task 2 supersedes task 1's placeholder: the default (no
        --staging-only) CLI path now runs build + backfill + report to
        completion. --db points at a tmp-path old file (never the real
        live path) and --report-dir at a tmp dir (never the real
        ~/.claude/pd/migrations) — the CLI-level contract every other
        full-run test in this file also honors."""
        old_db_path = _build_empty_old_v1_file(tmp_path / "old.db")
        staging_path = tmp_path / "cli-staging-2.db"
        exit_code = rebuild_tool.main([
            "--db", old_db_path,
            "--staging-path", str(staging_path),
            "--report-dir", str(tmp_path / "reports"),
        ])
        assert exit_code == 0
        assert staging_path.exists()

    def test_staging_only_and_swap_are_mutually_exclusive(self, tmp_path):
        staging_path = tmp_path / "cli-staging-mutex.db"
        exit_code = rebuild_tool.main(
            ["--staging-only", "--swap", "--staging-path", str(staging_path)]
        )
        assert exit_code != 0
        assert not staging_path.exists()

    def test_refuses_to_overwrite_an_existing_staging_path(self, tmp_path):
        staging_path = tmp_path / "cli-staging-3.db"
        staging_path.write_bytes(b"")
        exit_code = rebuild_tool.main(
            ["--staging-only", "--staging-path", str(staging_path)]
        )
        assert exit_code != 0


def _new_conn(staging_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(staging_path))
    conn.row_factory = sqlite3.Row
    return conn


def _build_and_backfill(tmp_path, corpus_builder, name="run") -> tuple[str, str, dict]:
    """Build an old file via *corpus_builder*, build+backfill a fresh
    staging file, return ``(old_db_path, staging_path, report)``."""
    old_db_path = corpus_builder(tmp_path / f"{name}-old.db")
    staging_path = str(tmp_path / f"{name}-staging.db")
    rebuild_tool.build_staging_database(staging_path)
    report = rebuild_tool.run_backfill(old_db_path, staging_path)
    return old_db_path, staging_path, report


# ---------------------------------------------------------------------------
# SC5 #077 clause: the pre-import vocab diff — abort path (zero writes) and
# a positive-path smoke (a clean corpus never trips it).
# ---------------------------------------------------------------------------
class TestPreimportVocabDiffAborts:
    def test_feature_kind_out_of_pipeline_vocab_phase_aborts_with_zero_writes(
        self, tmp_path
    ):
        """A feature-kind entity's phase-named event with phase='discover'
        is LEGAL under workflow_phases' own CHECK (the 5D vocab is part of
        that union) but outside PIPELINE_PHASES_SET — the one genuinely
        reachable mismatch a schema_version=19 file can still carry
        (open-vocabulary v1 columns feeding a NARROWER v2 axis trigger)."""
        old_db_path = str(tmp_path / "old.db")
        db = database.EntityDatabase(old_db_path)
        db.close()
        conn = sqlite3.connect(old_db_path)
        _seed_workspace(conn, "ws-1", "p1")
        _seed_entity(
            conn, uuid_="e-1", workspace_uuid="ws-1", kind="feature",
            entity_id="001-feat", name="Feat",
        )
        _seed_phase_event(
            conn, type_id="feature:001-feat", project_id="p1",
            event_type="started", phase="discover",
        )
        conn.commit()
        conn.close()

        staging_path = str(tmp_path / "staging.db")
        rebuild_tool.build_staging_database(staging_path)

        with pytest.raises(rebuild_tool.BackfillVocabMismatchError, match="discover"):
            rebuild_tool.run_backfill(old_db_path, staging_path)

        conn = _new_conn(staging_path)
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM phase_events").fetchone()[0] == 0
        conn.close()

    def test_clean_corpus_never_trips_the_diff(self, tmp_path):
        """Positive control: the pathological corpus (which DOES include a
        legal-but-unusual 5D phase on a non-feature kind) backfills clean —
        proves the diff isn't a blanket false-positive over any unusual
        phase value, only feature-kind-plus-out-of-pipeline-vocab ones."""
        _, _, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        assert report["counts"]  # backfill actually ran (non-empty report)


# ---------------------------------------------------------------------------
# SC2: backfill parity over the pathological corpus.
# ---------------------------------------------------------------------------
class TestBackfillParityPathologicalCorpus:
    def test_per_kind_workspace_counts_equal_or_explained(self, tmp_path):
        _, _, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        counts = report["counts"]
        # feature: 2 old (dup-loser + dup-winner) -> 1 new (dedup).
        assert counts["feature"]["ws-alpha"] == {"old": 3, "new": 2}
        # project: cross-workspace P001s preserved un-deduped.
        assert counts["project"]["ws-alpha"] == {"old": 1, "new": 1}
        assert counts["project"]["ws-beta"] == {"old": 1, "new": 1}
        # No unexplained deltas anywhere (run_backfill would have raised
        # BackfillIntegrityError otherwise — this assertion is redundant
        # insurance that the run actually reached report-building).
        for kind, by_ws in counts.items():
            for ws, bucket in by_ws.items():
                assert bucket["new"] <= bucket["old"], (kind, ws, bucket)

    def test_every_anomaly_category_populated(self, tmp_path):
        _, _, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        anomalies = report["anomalies"]
        assert len(anomalies["duplicate_type_id"]) == 1
        assert anomalies["duplicate_type_id"][0]["old_uuid"] == "dup-loser"
        assert anomalies["duplicate_type_id"][0]["survivor_old_uuid"] == "dup-winner"

        normalized_fields = {a["field"] for a in anomalies["empty_id_normalized"]}
        assert normalized_fields == {"entity_id", "name"}
        assert all(
            a["old_uuid"] == "blank-id-entity" for a in anomalies["empty_id_normalized"]
        )

        assert anomalies["orphan_parent"] == [
            {"old_uuid": "orphan-child", "missing_parent_old_uuid": "does-not-exist"}
        ]
        assert anomalies["parent_cycle"] == [
            {"old_uuid": "cycle-b", "broken_parent_old_uuid": "cycle-a"}
        ]

    def test_bug_kind_entity_imported_with_execution_status(self, tmp_path):
        _, staging_path, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        row = conn.execute(
            "SELECT uuid, kind, status FROM entities WHERE type_id = 'bug:008-a-bug'"
        ).fetchone()
        assert row["kind"] == "bug"
        events = conn.execute(
            "SELECT event_type, axis, to_value FROM events WHERE entity_uuid = ? "
            "ORDER BY uuid",
            (row["uuid"],),
        ).fetchall()
        event_types = [e["event_type"] for e in events]
        assert "entity_created" in event_types
        assert "status_backfilled" in event_types
        assert "entity_status_changed" in event_types
        # entity_status_changed carries its metadata['new_status'] onto
        # lifecycle — NEVER onto execution (design D3's collision guard).
        status_changed = next(e for e in events if e["event_type"] == "entity_status_changed")
        assert status_changed["axis"] == "lifecycle"
        assert status_changed["to_value"] == "blocked"
        conn.close()

    def test_uuid4_shaped_old_uuid_remaps_cleanly(self, tmp_path):
        """The alpha project's OLD uuid is a uuid4-style string (mixed
        uuid4/uuid7 census, #054(b)) — the import must not assume
        old uuids are themselves uuid7-shaped."""
        old_db_path, staging_path, report = _build_and_backfill(
            tmp_path, _build_pathological_corpus
        )
        conn = _new_conn(staging_path)
        row = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'project:P001' "
            "AND workspace_uuid = 'ws-alpha'"
        ).fetchone()
        assert row is not None
        # New uuid is a real uuid7 (version nibble '7'), regardless of the
        # old uuid's own shape.
        assert row["uuid"][14] == "7"
        conn.close()

    def test_cross_workspace_p001_preserved_undeduped(self, tmp_path):
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        rows = conn.execute(
            "SELECT workspace_uuid, uuid FROM entities WHERE type_id = 'project:P001'"
        ).fetchall()
        assert {r["workspace_uuid"] for r in rows} == {"ws-alpha", "ws-beta"}
        assert len({r["uuid"] for r in rows}) == 2  # two DISTINCT new uuids
        conn.close()

    def test_loser_phase_event_resolves_to_survivor(self, tmp_path):
        """The duplicate's shared type_id carries one phase_events row —
        it must land on the SURVIVOR's (dup-winner's) new uuid, not be
        dropped, not create a phantom third entity."""
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        survivor_uuid = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'feature:003-dup-feature'"
        ).fetchone()["uuid"]
        pipeline_events = conn.execute(
            "SELECT to_value FROM events WHERE entity_uuid = ? AND axis = 'pipeline'",
            (survivor_uuid,),
        ).fetchall()
        assert [r["to_value"] for r in pipeline_events] == ["brainstorm"]
        conn.close()

    def test_loser_relation_repoints_to_survivor_without_pk_collision(self, tmp_path):
        """dup-loser's ``blocks`` edge to bug-1 (``loser -> bug-1``),
        remapped through the survivor, becomes ``winner -> bug-1 blocks``
        — a DIFFERENT (from, to, kind) tuple from BOTH winner's own
        ``winner -> bug-1 fixes`` edge AND the pre-existing
        ``bug-1 -> winner blocks`` edge (direction/kind both differ), so
        all three rows survive distinctly with no UNIQUE-index collision
        (the identical-tuple collision case is covered separately by
        test_entity_relations_dedup_collision_is_silently_collapsed)."""
        _, staging_path, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        assert report["entity_relations"]["old"] == 3
        assert report["entity_relations"]["new"] == 3
        conn = _new_conn(staging_path)
        winner_uuid = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'feature:003-dup-feature'"
        ).fetchone()["uuid"]
        bug_uuid = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'bug:008-a-bug'"
        ).fetchone()["uuid"]
        rows = {
            (r["from_uuid"], r["to_uuid"], r["kind"])
            for r in conn.execute("SELECT from_uuid, to_uuid, kind FROM entity_relations")
        }
        assert rows == {
            (winner_uuid, bug_uuid, "fixes"),
            (bug_uuid, winner_uuid, "blocks"),
            (winner_uuid, bug_uuid, "blocks"),  # dup-loser's edge, remapped
        }
        conn.close()

    def test_5d_and_lifecycle_phase_histories_route_to_lifecycle_axis(self, tmp_path):
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        cycle_a_uuid = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'backlog:005-cycle-a'"
        ).fetchone()["uuid"]
        events = conn.execute(
            "SELECT event_type, axis, to_value FROM events WHERE entity_uuid = ? "
            "AND event_type = 'started'",
            (cycle_a_uuid,),
        ).fetchall()
        assert len(events) == 1
        assert events[0]["axis"] == "lifecycle"
        assert events[0]["to_value"] == "discover"
        conn.close()

    def test_full_history_feature_pipeline_events_and_kanban_overwrite(self, tmp_path):
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        row = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'feature:009-full-history'"
        ).fetchone()
        events = conn.execute(
            "SELECT event_type, axis, to_value FROM events WHERE entity_uuid = ? "
            "ORDER BY uuid",
            (row["uuid"],),
        ).fetchall()
        pipeline = [e for e in events if e["axis"] == "pipeline"]
        assert [e["to_value"] for e in pipeline] == ["brainstorm", "brainstorm", "specify"]

        # kanban_column was seeded stale ('blocked') — the import must
        # overwrite it with the freshly derived value, not preserve the
        # stale copy verbatim.
        wf = conn.execute(
            "SELECT kanban_column FROM workflow_phases WHERE type_id = 'feature:009-full-history'"
        ).fetchone()
        execution_event = next(e for e in events if e["axis"] == "execution")
        assert wf["kanban_column"] == execution_event["to_value"]
        assert wf["kanban_column"] != "blocked"
        conn.close()

    def test_status_backfilled_is_the_latest_execution_event(self, tmp_path):
        """SC3's parity note: status_backfilled must be the LAST-inserted
        (hence MAX(uuid)-latest) event on the execution axis — checked
        both via a direct events-table query AND via entity_axis_state's
        own MAX(uuid) selection (the view a live consumer would read)."""
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        for row in conn.execute("SELECT DISTINCT entity_uuid FROM events"):
            actual_latest = conn.execute(
                "SELECT event_type, uuid FROM events WHERE entity_uuid = ? "
                "AND axis = 'execution' ORDER BY uuid DESC LIMIT 1",
                (row["entity_uuid"],),
            ).fetchone()
            assert actual_latest["event_type"] == "status_backfilled"

            axis_state = conn.execute(
                "SELECT event_uuid FROM entity_axis_state "
                "WHERE entity_uuid = ? AND axis = 'execution'",
                (row["entity_uuid"],),
            ).fetchone()
            assert axis_state["event_uuid"] == actual_latest["uuid"]
        conn.close()

    def test_entity_relations_dedup_collision_is_silently_collapsed(self, tmp_path):
        """A SEPARATE, targeted corpus: the loser's remapped relation is
        byte-IDENTICAL to an edge the survivor already owns — proves the
        (from,to,kind) pre-filter avoids the UNIQUE index crash without
        double-counting the edge."""
        def _build(path):
            db = database.EntityDatabase(str(path))
            db.close()
            conn = sqlite3.connect(str(path))
            conn.execute("PRAGMA foreign_keys = OFF")
            _seed_workspace(conn, "ws-1", "p1")
            _relax_entities_unique_constraint(conn)
            _seed_entity(
                conn, uuid_="loser", workspace_uuid="ws-1", kind="feature",
                entity_id="001-dup", name="Loser", created_at=_NOW, updated_at=_NOW,
            )
            _seed_entity(
                conn, uuid_="winner", workspace_uuid="ws-1", kind="feature",
                entity_id="001-dup", name="Winner", created_at=_NOW, updated_at=_LATER,
            )
            _seed_entity(
                conn, uuid_="target", workspace_uuid="ws-1", kind="feature",
                entity_id="002-target", name="Target",
            )
            _seed_entity_relation(conn, from_uuid="winner", to_uuid="target", kind="fixes")
            _seed_entity_relation(conn, from_uuid="loser", to_uuid="target", kind="fixes")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            conn.close()
            return str(path)

        _, staging_path, report = _build_and_backfill(tmp_path, _build, name="collision")
        assert report["entity_relations"] == {"old": 2, "new": 1, "orphans": []}
        conn = _new_conn(staging_path)
        assert conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0] == 1
        conn.close()


# ---------------------------------------------------------------------------
# Discovered edge case: migration 10's phase_events_backfill_dedup partial
# UNIQUE(type_id, phase, event_type, timestamp) WHERE source='backfill'
# (database.py) — pre-dates this feature, but applies to ANY row carrying
# source='backfill', which D2 mandates for every copied row. Two OLD rows
# sharing an identical tuple (both originally source='live', legitimately
# unconstrained) collide only once BOTH are re-stamped.
# ---------------------------------------------------------------------------
class TestPhaseEventsBackfillDedupCollision:
    def test_colliding_tuple_is_caught_not_aborted(self, tmp_path):
        def _build(path):
            db = database.EntityDatabase(str(path))
            db.close()
            conn = sqlite3.connect(str(path))
            _seed_workspace(conn, "ws-1", "p1")
            _seed_entity(
                conn, uuid_="e-1", workspace_uuid="ws-1", kind="feature",
                entity_id="001-collide", name="Collide",
            )
            # Two DISTINCT rows, identical (type_id, phase, event_type,
            # timestamp) — legal in the OLD file (both source='live', the
            # partial index does not constrain them there).
            _seed_phase_event(
                conn, type_id="feature:001-collide", project_id="p1",
                event_type="started", phase="brainstorm", timestamp=_NOW,
                iterations=None,
            )
            _seed_phase_event(
                conn, type_id="feature:001-collide", project_id="p1",
                event_type="started", phase="brainstorm", timestamp=_NOW,
                iterations=None,
            )
            conn.commit()
            conn.close()
            return str(path)

        _, staging_path, report = _build_and_backfill(tmp_path, _build, name="pe-collide")

        # The import completed (no BackfillIntegrityError raised) —
        # exactly ONE row lost its v1 phase_events copy to the collision.
        assert report["phase_events"]["old"] == 2
        assert report["phase_events"]["new"] == 1
        assert len(report["anomalies"]["phase_events_dedup_collision"]) == 1
        collision = report["anomalies"]["phase_events_dedup_collision"][0]
        assert collision["type_id"] == "feature:001-collide"
        assert collision["timestamp"] == _NOW

        conn = _new_conn(staging_path)
        assert conn.execute("SELECT COUNT(*) FROM phase_events").fetchone()[0] == 1
        # BOTH rows still contribute a v2 event -- no data silently lost,
        # only the redundant v1-side copy of the second row.
        entity_uuid = conn.execute("SELECT uuid FROM entities").fetchone()["uuid"]
        pipeline_events = conn.execute(
            "SELECT to_value FROM events WHERE entity_uuid = ? AND axis = 'pipeline'",
            (entity_uuid,),
        ).fetchall()
        assert len(pipeline_events) == 2
        conn.close()


# ---------------------------------------------------------------------------
# SC2: idempotence — two independent runs against the SAME old file
# produce a byte-identical (pure, comparable) report.
# ---------------------------------------------------------------------------
class TestIdempotentRerun:
    def test_two_runs_produce_identical_reports(self, tmp_path):
        old_db_path = _build_pathological_corpus(tmp_path / "old.db")
        staging_1 = str(tmp_path / "staging-1.db")
        staging_2 = str(tmp_path / "staging-2.db")
        rebuild_tool.build_staging_database(staging_1)
        rebuild_tool.build_staging_database(staging_2)

        report_1 = rebuild_tool.run_backfill(old_db_path, staging_1)
        report_2 = rebuild_tool.run_backfill(old_db_path, staging_2)

        assert report_1 == report_2
        assert report_1["checksum"] == report_2["checksum"]


# ---------------------------------------------------------------------------
# D6.9 seed-half: sequences seeded at census max per kind x workspace.
# ---------------------------------------------------------------------------
class TestSequencesSeeded:
    def test_seeded_rows_match_census_max_per_kind_workspace(self, tmp_path):
        _, staging_path, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        rows = {
            (r["workspace_uuid"], r["entity_type"]): r["next_val"]
            for r in conn.execute("SELECT workspace_uuid, entity_type, next_val FROM sequences")
        }
        conn.close()

        # feature: max numbered id is 009-full-history -> next_val 10.
        assert rows[("ws-alpha", "feature")] == 10
        # task: 007-orphan is the only numbered id (blank-id contributes 0).
        assert rows[("ws-alpha", "task")] == 8
        # backlog: 006-cycle-b is the max.
        assert rows[("ws-alpha", "backlog")] == 7
        # bug: 008-a-bug.
        assert rows[("ws-alpha", "bug")] == 9
        # project: P{NNN} pattern, regex-blind to the leading "P" for the
        # GENERIC pattern — the kind='project' special-case must still
        # resolve P001 -> 1 -> next_val 2, independently per workspace.
        assert rows[("ws-alpha", "project")] == 2
        assert rows[("ws-beta", "project")] == 2

        assert report["sequences_seeded"]["project"]["ws-alpha"] == 2
        assert report["sequences_seeded"]["project"]["ws-beta"] == 2


# ---------------------------------------------------------------------------
# D7: the two on-disk report forms — the full machine JSON (entity-named,
# outside the repo) and the counts-only committed summary (zero names).
# ---------------------------------------------------------------------------
class TestReportArtifacts:
    def test_write_machine_report_round_trips_the_full_report(self, tmp_path):
        _, _, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        report_dir = str(tmp_path / "machine-reports")
        report_path = rebuild_tool.write_machine_report(report, report_dir)
        assert Path(report_path).exists()
        on_disk = json.loads(Path(report_path).read_text())
        assert on_disk == report

    def test_write_summary_report_contains_zero_entity_names(self, tmp_path):
        """D7: the committed summary is COUNTS ONLY — no entity_id/name
        strings from the corpus (e.g. 'Winner', 'Alpha Project') may leak
        into it, only kinds/workspace uuids/counts/checksums."""
        _, _, report = _build_and_backfill(tmp_path, _build_pathological_corpus)
        summary_path = str(tmp_path / "summary.md")
        rebuild_tool.write_summary_report(report, summary_path)
        content = Path(summary_path).read_text()

        for leaked_name in ("Winner", "Loser", "Alpha Project", "Beta Project", "A Bug"):
            assert leaked_name not in content
        assert "checksum" in content.lower()
        assert "ws-alpha" in content  # workspace UUIDs are fine — not entity names
        assert str(report["uuid_remap_count"]) in content

    def test_default_report_dir_and_marker_dir_honor_env_overrides(self, monkeypatch, tmp_path):
        """D7/D4: CONFIGURABLE via env var for test hermeticity — the
        contract main() relies on (and this file's own autouse fixture
        exercises implicitly on every other test)."""
        monkeypatch.setenv("PD_REBUILD_REPORT_DIR", str(tmp_path / "custom-reports"))
        monkeypatch.setenv("PD_REBUILD_MARKER_DIR", str(tmp_path / "custom-marker"))
        assert rebuild_tool._default_report_dir() == str(tmp_path / "custom-reports")
        assert rebuild_tool._default_marker_dir() == str(tmp_path / "custom-marker")


# ---------------------------------------------------------------------------
# SC3(a): replaying an entity's events stream reproduces entity_axis_state's
# latest-per-axis rows and the entity_state pivot EXACTLY.
# ---------------------------------------------------------------------------
class TestReplayReproducesAxisViews:
    def test_entity_axis_state_and_entity_state_match_python_replay(self, tmp_path):
        _, staging_path, _ = _build_and_backfill(tmp_path, _build_pathological_corpus)
        conn = _new_conn(staging_path)
        entity_uuids = [r["uuid"] for r in conn.execute("SELECT uuid FROM entities")]
        assert entity_uuids  # non-vacuity: the corpus actually produced rows

        for entity_uuid in entity_uuids:
            all_events = conn.execute(
                "SELECT uuid, axis, to_value, timestamp FROM events "
                "WHERE entity_uuid = ? ORDER BY uuid",
                (entity_uuid,),
            ).fetchall()
            assert all_events  # every entity gets at least entity_created + status_backfilled

            # Python replay: per axis, the row whose uuid is lexically MAX
            # (events.uuid is the PRIMARY KEY — no ties possible).
            expected_by_axis: dict[str, sqlite3.Row] = {}
            for row in all_events:
                axis = row["axis"]
                if axis not in expected_by_axis or row["uuid"] > expected_by_axis[axis]["uuid"]:
                    expected_by_axis[axis] = row

            actual_by_axis = {
                r["axis"]: r
                for r in conn.execute(
                    "SELECT axis, to_value, timestamp FROM entity_axis_state "
                    "WHERE entity_uuid = ?",
                    (entity_uuid,),
                ).fetchall()
            }
            assert set(actual_by_axis) == set(expected_by_axis), entity_uuid
            for axis, expected_row in expected_by_axis.items():
                actual_row = actual_by_axis[axis]
                assert actual_row["to_value"] == expected_row["to_value"], (
                    entity_uuid, axis, "to_value",
                )
                assert actual_row["timestamp"] == expected_row["timestamp"], (
                    entity_uuid, axis, "timestamp",
                )

            pivot = conn.execute(
                "SELECT pipeline_value, pipeline_at, execution_value, execution_at, "
                "lifecycle_value, lifecycle_at FROM entity_state WHERE entity_uuid = ?",
                (entity_uuid,),
            ).fetchone()
            for axis in ("pipeline", "execution", "lifecycle"):
                expected_row = expected_by_axis.get(axis)
                if expected_row is None:
                    assert pivot[f"{axis}_value"] is None, (entity_uuid, axis)
                    assert pivot[f"{axis}_at"] is None, (entity_uuid, axis)
                else:
                    assert pivot[f"{axis}_value"] == expected_row["to_value"], (entity_uuid, axis)
                    assert pivot[f"{axis}_at"] == expected_row["timestamp"], (entity_uuid, axis)
        conn.close()


# ---------------------------------------------------------------------------
# SC3(b): old-file vs new-file phase_events agree on row count and rich
# fields; ``source`` is EXCLUDED (deliberately re-stamped 'backfill').
# ---------------------------------------------------------------------------
class TestPhaseEventsRichFieldParity:
    def test_row_count_and_rich_fields_match_excluding_source(self, tmp_path):
        old_db_path, staging_path, report = _build_and_backfill(
            tmp_path, _build_pathological_corpus
        )
        assert report["phase_events"]["old"] == report["phase_events"]["new"]
        assert report["phase_events"]["old"] > 0  # non-vacuity

        old_conn = sqlite3.connect(old_db_path)
        old_conn.row_factory = sqlite3.Row
        new_conn = _new_conn(staging_path)

        rich_cols = (
            "phase", "event_type", "iterations", "reviewer_notes",
            "backward_reason", "backward_target",
        )
        old_rows = old_conn.execute(
            f"SELECT {', '.join(rich_cols)} FROM phase_events ORDER BY id"
        ).fetchall()
        new_rows = new_conn.execute(
            f"SELECT {', '.join(rich_cols)} FROM phase_events ORDER BY id"
        ).fetchall()
        assert len(old_rows) == len(new_rows)
        for old_row, new_row in zip(old_rows, new_rows):
            for col in rich_cols:
                assert old_row[col] == new_row[col], col

        new_sources = {
            r[0] for r in new_conn.execute("SELECT DISTINCT source FROM phase_events")
        }
        assert new_sources == {"backfill"}  # every row re-stamped, none left 'live'
        old_conn.close()
        new_conn.close()


# ---------------------------------------------------------------------------
# SC4 (D4b): the per-entity entity_axis_state statement shows predicate
# pushdown (no full SCAN of events) and p95 <= 5ms per entity at the
# ~533-entity corpus.
# ---------------------------------------------------------------------------
class TestResolverExplainAndLatency:
    _STATEMENT = "SELECT to_value, timestamp FROM entity_axis_state WHERE entity_uuid = ?"

    def test_explain_shows_pushdown_and_p95_latency_under_5ms(self, tmp_path):
        import time

        old_db_path = _build_scale_corpus(tmp_path / "scale-old.db")
        staging_path = str(tmp_path / "scale-staging.db")
        rebuild_tool.build_staging_database(staging_path)
        rebuild_tool.run_backfill(old_db_path, staging_path)

        conn = _new_conn(staging_path)
        entity_uuids = [r["uuid"] for r in conn.execute("SELECT uuid FROM entities")]
        assert len(entity_uuids) >= 500  # non-vacuity: genuinely at 127 GO's scale

        plan_rows = conn.execute(
            f"EXPLAIN QUERY PLAN {self._STATEMENT}", (entity_uuids[0],)
        ).fetchall()
        plan_text = " ".join(str(cell) for row in plan_rows for cell in row)
        assert "SCAN events" not in plan_text, plan_text
        assert "idx_events_entity_axis" in plan_text, plan_text

        durations = []
        for entity_uuid in entity_uuids:
            start = time.perf_counter()
            conn.execute(self._STATEMENT, (entity_uuid,)).fetchall()
            durations.append(time.perf_counter() - start)
        durations.sort()
        p95_index = max(0, int(len(durations) * 0.95) - 1)
        p95_ms = durations[p95_index] * 1000
        assert p95_ms <= 5.0, f"p95 latency {p95_ms:.3f}ms exceeds the 5ms flake-proof ceiling"
        conn.close()


# ---------------------------------------------------------------------------
# SC6: old-DB safety — post-swap, a write against the archived old path
# fails loud; the marker carries the dated 30-day expiry.
# ---------------------------------------------------------------------------
class TestOldFileReadonlyAndMarker:
    def _swap(self, tmp_path):
        old_db_path = str(tmp_path / "entities.db")
        db = database.EntityDatabase(old_db_path)
        db.close()
        conn = sqlite3.connect(old_db_path)
        _seed_workspace(conn, "ws-1", "p1")
        conn.commit()
        conn.close()

        staging_path = str(tmp_path / "entities.db.rebuild-test")
        rebuild_tool.build_staging_database(staging_path)
        rebuild_tool.run_backfill(old_db_path, staging_path)

        marker_dir = str(tmp_path / "marker-home")
        marker = rebuild_tool.perform_cutover_swap(
            old_db_path, staging_path, report_path="dummy.json", marker_dir=marker_dir
        )
        return old_db_path, marker_dir, marker

    def test_write_against_archived_old_file_fails_loud(self, tmp_path):
        old_db_path, _marker_dir, _marker = self._swap(tmp_path)
        archived_path = old_db_path + ".v1-readonly"
        assert Path(archived_path).exists()
        # old_db_path itself still exists post-swap — it's now the
        # PROMOTED staging file (the live path is untouched, D4); the
        # ARCHIVED copy at archived_path is the one under test here.
        assert Path(old_db_path).exists()

        conn = sqlite3.connect(archived_path)
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute(
                    "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
                    "created_at, updated_at) VALUES ('ws-x', 'x', '/tmp', ?, ?)",
                    (_NOW, _NOW),
                )
        finally:
            conn.close()

    def test_archived_old_file_still_readable_via_immutable_uri(self, tmp_path):
        old_db_path, _marker_dir, _marker = self._swap(tmp_path)
        archived_path = old_db_path + ".v1-readonly"
        ro_conn = rebuild_tool.open_archived_old_file(archived_path)
        try:
            rows = ro_conn.execute("SELECT uuid FROM workspaces").fetchall()
            assert rows == [("ws-1",)]
        finally:
            ro_conn.close()

    def test_marker_carries_dated_30_day_expiry(self, tmp_path):
        from datetime import datetime, timedelta, timezone

        old_db_path, marker_dir, marker = self._swap(tmp_path)
        marker_path = Path(marker_dir) / "migrations" / "v2-cutover.json"
        assert marker_path.exists()
        on_disk = json.loads(marker_path.read_text())
        assert on_disk == marker

        cutover_at = datetime.strptime(marker["cutover_at"], "%Y-%m-%dT%H:%M:%SZ")
        expiry = datetime.strptime(marker["expiry"], "%Y-%m-%dT%H:%M:%SZ")
        assert (expiry - cutover_at) == timedelta(days=30)
        assert marker["old_file"] == old_db_path + ".v1-readonly"
        assert marker["old_sha256"]


class TestSwapNeverImpliedByOrdinaryRun:
    def test_default_backfill_run_does_not_swap_the_old_file(self, tmp_path):
        """D4: --swap is a SEPARATE explicit flag — an ordinary (no
        --swap) full run must leave --db exactly where it was."""
        old_db_path = _build_empty_old_v1_file(tmp_path / "old.db")
        staging_path = tmp_path / "staging.db"
        exit_code = rebuild_tool.main([
            "--db", old_db_path,
            "--staging-path", str(staging_path),
            "--report-dir", str(tmp_path / "reports"),
        ])
        assert exit_code == 0
        assert Path(old_db_path).exists()
        assert not Path(old_db_path + ".v1-readonly").exists()
        assert staging_path.exists()  # the backfilled file, NOT swapped into place

    def test_swap_flag_performs_the_cutover(self, tmp_path):
        old_db_path = _build_empty_old_v1_file(tmp_path / "old.db")
        staging_path = tmp_path / "staging.db"
        exit_code = rebuild_tool.main([
            "--db", old_db_path,
            "--staging-path", str(staging_path),
            "--report-dir", str(tmp_path / "reports"),
            "--marker-dir", str(tmp_path / "marker-home"),
            "--swap",
        ])
        assert exit_code == 0
        assert Path(old_db_path).exists()  # now the PROMOTED staging file
        assert Path(old_db_path + ".v1-readonly").exists()
        assert not staging_path.exists()  # renamed away
