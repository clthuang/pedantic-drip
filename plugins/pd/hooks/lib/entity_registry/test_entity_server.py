"""Tests for entity_server MCP handler dual-identity messages."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

import pytest

# Make entity_server importable.
_mcp_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server
from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace

_UUID_V4_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Provide EntityDatabase and inject into entity_server._db."""
    database = EntityDatabase(str(tmp_path / "test.db"))
    monkeypatch.setattr(entity_server, "_db", database)
    yield database
    database.close()


@pytest.mark.asyncio
async def test_set_parent_handler_concise_message(db):
    """set_parent handler returns concise message with only type_ids, no UUIDs.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    parent_uuid = db.register_entity("project", "parent", "Parent Project", status="active", project_id="__unknown__")
    child_uuid = db.register_entity("feature", "child", "Child Feature", project_id="__unknown__")

    result = await entity_server.set_parent("feature:child", "project:parent")

    assert isinstance(result, str)
    assert result == "Parent set: feature:child \u2192 project:parent"
    # UUIDs must NOT appear in confirmation messages
    assert child_uuid not in result
    assert parent_uuid not in result


@pytest.mark.asyncio
async def test_update_entity_handler_concise_message(db):
    """update_entity handler returns concise message with only type_id, no UUID.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    entity_uuid = db.register_entity("feature", "f1", "Feature One", status="active", project_id="__unknown__")

    result = await entity_server.update_entity("feature:f1", status="completed")

    assert isinstance(result, str)
    assert result == "Updated: feature:f1"
    # UUID must NOT appear in confirmation message
    assert entity_uuid not in result


# ---------------------------------------------------------------------------
# Deepened tests: Phase B — spec-driven test deepening
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_handler_concise_message(db):
    """register_entity handler returns concise message with only type_id, no UUID.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    result = await entity_server.register_entity(
        entity_type="feature",
        entity_id="reg-test",
        name="Registration Test",
    )
    assert isinstance(result, str)
    assert result == "Registered: feature:reg-test"
    # UUID must NOT appear in confirmation message
    assert not _UUID_V4_RE.search(result), f"UUID found in message: {result}"


@pytest.mark.asyncio
async def test_set_parent_handler_uses_uuid_identifiers(db):
    """set_parent handler can accept UUID identifiers (not just type_id).
    Anticipate: If handler passes raw input to set_parent without
    dual-read resolution, UUID input would fail.
    derived_from: spec:R27, dimension:adversarial
    """
    parent_uuid = db.register_entity("project", "parent2", "Parent", project_id="__unknown__")
    child_uuid = db.register_entity("feature", "child2", "Child", project_id="__unknown__")
    # Use UUID for child and type_id for parent
    result = await entity_server.set_parent(child_uuid, "project:parent2")
    assert isinstance(result, str)
    # Should not contain "Error"
    assert "Error" not in result
    # Concise message uses type_ids only
    assert "Parent set:" in result


@pytest.mark.asyncio
async def test_get_entity_handler_compact_output(db):
    """get_entity handler returns compact JSON without uuid, entity_id, parent_uuid.
    These internal fields are stripped for token efficiency — callers already
    know the type_id they queried with, and uuid/parent_uuid are internal.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C2
    """
    db.register_entity("feature", "get-test", "Get Test", status="active", project_id="__unknown__")
    result = await entity_server.get_entity("feature:get-test")
    assert isinstance(result, str)
    parsed = json.loads(result)
    # Excluded fields
    assert "uuid" not in parsed
    assert "entity_id" not in parsed
    assert "parent_uuid" not in parsed
    # Retained fields
    assert parsed["type_id"] == "feature:get-test"
    assert parsed["name"] == "Get Test"
    assert parsed["status"] == "active"
    # Compact JSON: no indentation, minimal separators
    assert "\n" not in result
    assert ": " not in result  # compact separators use ':' not ': '


# ---------------------------------------------------------------------------
# Deepened tests Phase B: MCP Audit Token Efficiency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_not_found_returns_message(db):
    """get_entity for a non-existent type_id returns a not-found message, not crash.
    derived_from: spec:AC-2 (error handling), dimension:error_propagation

    Anticipate: If get_entity doesn't handle None from db.get_entity(),
    it would crash with AttributeError when trying to pop keys from None.
    This test verifies graceful handling of the not-found path.
    """
    # Given a database with no matching entity
    # When requesting a non-existent entity
    result = await entity_server.get_entity("feature:does-not-exist")
    # Then a human-readable not-found message is returned
    assert isinstance(result, str)
    assert "not found" in result.lower() or "Entity not found" in result
    assert "does-not-exist" in result


@pytest.mark.asyncio
async def test_set_parent_delegates_to_server_helpers(db):
    """set_parent MCP handler delegates to _process_set_parent helper.
    derived_from: spec:AC-15 (delegation to helpers), dimension:bdd_scenarios

    Anticipate: If set_parent inlines the logic instead of delegating to
    _process_set_parent, future changes to the helper would not be picked up
    by the MCP tool. This test verifies the delegation chain works end-to-end.
    """
    # Given parent and child entities
    db.register_entity("project", "p1", "Parent Project", status="active", project_id="__unknown__")
    db.register_entity("feature", "c1", "Child Feature", status="active", project_id="__unknown__")
    # When setting parent via MCP handler
    result = await entity_server.set_parent("feature:c1", "project:p1")
    # Then success message is returned
    assert "Parent set:" in result
    assert "feature:c1" in result
    assert "project:p1" in result


@pytest.mark.asyncio
async def test_entity_lifecycle_valueerror_caught_by_mcp_decorator(db):
    """Entity lifecycle ValueError is caught and returned as structured error.
    derived_from: spec:AC-5 (error handling), dimension:error_propagation

    Anticipate: If the init_entity_workflow or transition_entity_phase MCP
    handlers don't have the _catch_entity_value_error decorator, ValueErrors
    would propagate as unhandled exceptions instead of structured error JSON.
    This test verifies the end-to-end error handling chain via the workflow
    state server processing function.
    """
    import workflow_state_server as ws_mod

    # Given a brainstorm entity but NO workflow_phases row
    db.register_entity("brainstorm", "err-test", "Error Test", status="draft", project_id="__unknown__")

    # When attempting to transition without initializing workflow first
    result = ws_mod._process_transition_entity_phase(
        db, "brainstorm:err-test", "reviewing"
    )
    parsed = json.loads(result)
    # Then a structured error is returned (not an unhandled exception)
    assert parsed["error"] is True
    assert parsed["error_type"] == "entity_not_found"
    assert "recovery_hint" in parsed


# ---------------------------------------------------------------------------
# Metadata dict coercion tests (feature 046)
# ---------------------------------------------------------------------------


class TestMetadataDictCoercion:
    """Tests for dict-to-JSON-string coercion in register_entity and update_entity."""

    def test_register_entity_metadata_dict(self, db: EntityDatabase):
        """AC-1: Dict metadata is accepted and stored as JSON string."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-dict-001",
                name="Dict Test", metadata={"description": "test value"},
            )
        )
        assert "Registered:" in result
        entity = db.get_entity("feature:meta-dict-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["description"] == "test value"

    def test_register_entity_metadata_string(self, db: EntityDatabase):
        """AC-3: String metadata passthrough unchanged."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-str-001",
                name="String Test", metadata='{"key": "val"}',
            )
        )
        assert "Registered:" in result
        entity = db.get_entity("feature:meta-str-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["key"] == "val"

    def test_register_entity_metadata_none(self, db: EntityDatabase):
        """AC-4: None metadata stores no metadata."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-none-001",
                name="None Test", metadata=None,
            )
        )
        assert "Registered:" in result

    def test_update_entity_metadata_dict(self, db: EntityDatabase):
        """AC-2: Dict metadata accepted by update_entity, stored as JSON string."""
        db.register_entity("feature", "meta-upd-001", "Update Test", status="active", project_id="__unknown__")
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.update_entity(
                type_id="feature:meta-upd-001",
                metadata={"updated": True},
            )
        )
        assert "Updated:" in result
        entity = db.get_entity("feature:meta-upd-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["updated"] is True

    def test_register_entity_metadata_invalid_json_string(self, db: EntityDatabase):
        """AC-7: Invalid JSON string handled gracefully by parse_metadata.
        derived_from: server_helpers:parse_metadata, dimension:delegation
        """
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-bad-001",
                name="Bad JSON Test", metadata="{bad json}",
            )
        )
        # Should succeed (parse_metadata returns {"error": "..."} for invalid JSON)
        assert "Registered:" in result


# ---------------------------------------------------------------------------
# Phase 4: Cross-project entity scoping — startup and project tools
# ---------------------------------------------------------------------------


class TestProjectStartup:
    """T4.1: entity_server startup with project_id detection."""

    def test_project_id_set_after_detection(self, db, monkeypatch):
        """Monkeypatch _compute_legacy_project_id and verify _project_id is set."""
        monkeypatch.setattr(entity_server, "_project_id", "")
        monkeypatch.setattr(
            "entity_server._compute_legacy_project_id", lambda _root: "abc123def456"
        )
        monkeypatch.setattr(
            "entity_server.collect_git_info",
            lambda _root: entity_server.GitProjectInfo(
                project_id="abc123def456",
                root_commit_sha="a" * 40,
                name="test-project",
                remote_url="",
                normalized_url="",
                remote_host="",
                remote_owner="",
                remote_repo="",
                default_branch="main",
                project_root="/tmp/test",
                is_git_repo=True,
            ),
        )
        # Simulate the startup sequence
        entity_server._project_id = entity_server._compute_legacy_project_id("/tmp/test")
        info = entity_server.collect_git_info("/tmp/test")
        entity_server._upsert_project(db, info)

        assert entity_server._project_id == "abc123def456"
        # Verify project was inserted
        row = db._conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", ("abc123def456",)
        ).fetchone()
        assert row is not None
        assert row["name"] == "test-project"

    def test_backfill_claims_unknown_entities(self, db, monkeypatch):
        """Pre-populate __unknown__ entity with matching artifact_path, verify claimed."""
        project_root = "/tmp/my-project"
        project_id = "testproj1234"

        # Register an entity with __unknown__ project_id and matching artifact_path
        db.register_entity(
            "feature", "bf-test", "Backfill Test",
            artifact_path="/tmp/my-project/docs/features/test/design.md",
            project_id="__unknown__",
        )
        # Verify starts as __unknown__
        entity = db.get_entity("feature:bf-test")
        assert entity["project_id"] == "__unknown__"

        # Run backfill
        count = entity_server._backfill_project_ids(db, project_root, project_id)
        assert count == 1

        # Verify entity was claimed
        entity = db.get_entity("feature:bf-test")
        assert entity["project_id"] == project_id


class TestListProjects:
    """T4.5: list_projects MCP tool."""

    def test_list_projects_returns_inserted_project(self, db, monkeypatch):
        """Insert a project via _upsert_project, then list_projects returns it."""
        from entity_registry.project_identity import GitProjectInfo

        monkeypatch.setattr(entity_server, "_db", db)
        info = GitProjectInfo(
            project_id="proj12345678",
            root_commit_sha="b" * 40,
            name="list-test-project",
            remote_url="https://github.com/test/repo.git",
            normalized_url="github.com/test/repo",
            remote_host="github.com",
            remote_owner="test",
            remote_repo="repo",
            default_branch="main",
            project_root="/tmp/list-test",
            is_git_repo=True,
        )
        entity_server._upsert_project(db, info)

        import asyncio
        result = asyncio.run(entity_server.list_projects())
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        project_ids = [p["project_id"] for p in parsed]
        assert "proj12345678" in project_ids
        matched = [p for p in parsed if p["project_id"] == "proj12345678"][0]
        assert matched["name"] == "list-test-project"


class TestSearchProjectFiltering:
    """T4.3: search_entities project_id filtering."""

    @pytest.mark.asyncio
    async def test_search_filters_by_project(self, db, monkeypatch):
        """Search with project_id filters results to that project."""
        # Feature 108 Migration 11: project_id alias requires a matching
        # workspaces row. Pre-register both legacy ids.
        from entity_registry.test_helpers import bootstrap_test_workspace
        bootstrap_test_workspace(db, "project_aaa")
        bootstrap_test_workspace(db, "project_bbb")
        # Register entities under different projects
        db.register_entity(
            "feature", "proj-a-feat", "Project A Feature",
            status="active", project_id="project_aaa",
        )
        db.register_entity(
            "feature", "proj-b-feat", "Project B Feature",
            status="active", project_id="project_bbb",
        )

        monkeypatch.setattr(entity_server, "_project_id", "project_aaa")

        # Default search (scoped to project_aaa)
        result = await entity_server.search_entities(query="Feature")
        assert "proj-a-feat" in result
        assert "proj-b-feat" not in result

        # Wildcard search (all projects)
        result = await entity_server.search_entities(query="Feature", project_id="*")
        assert "proj-a-feat" in result
        assert "proj-b-feat" in result


class TestCreateKeyResultMissingParent:
    """FR-9: ``_process_create_key_result`` raises ValueError on missing parent.

    Pre-fix: ``parent_uuid = parent_entity["uuid"] if parent_entity else None``
    silently registered the KR as an orphan when the parent objective did not
    exist — violating AC-3c (canonical parent_uuid contract).

    Post-fix: explicit ``if parent_entity is None: raise ValueError(...)``.
    """

    def test_create_key_result_missing_parent_raises(self, db):
        """Missing parent objective → ValueError with explicit message."""
        from entity_server import _process_create_key_result

        # No parent objective registered. Calling _process_create_key_result
        # with a non-existent parent_type_id must raise ValueError.
        with pytest.raises(ValueError, match="Parent entity not found"):
            _process_create_key_result(
                db,
                parent_type_id="objective:nonexistent",
                eid="missing-parent-kr",
                name="KR Without Parent",
                status="active",
                metadata_json=json.dumps({"score": 0.0}),
                weight=1.0,
            )


def _upsert(db, project_id, project_root, workspace_uuid=None, name="p"):
    db.upsert_project(
        project_id=project_id, name=name, root_commit_sha=None,
        remote_url=None, normalized_url=None, remote_host=None,
        remote_owner=None, remote_repo=None, default_branch=None,
        project_root=project_root, is_git_repo=False,
        workspace_uuid=workspace_uuid,
    )


def _seed_ws(db, ws_uuid, legacy, root):
    db._conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, '2026-06-13T00:00:00Z', '2026-06-13T00:00:00Z')",
        (ws_uuid, legacy, root),
    )
    db._conn.commit()


def _projects_ws_uuid(db, project_id):
    return db._conn.execute(
        "SELECT workspace_uuid FROM projects WHERE project_id = ?",
        (project_id,),
    ).fetchone()["workspace_uuid"]


def _ws_present(db, ws_uuid):
    return db._conn.execute(
        "SELECT 1 FROM workspaces WHERE uuid = ?", (ws_uuid,)
    ).fetchone() is not None


_WSA = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
_WSB = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"


class TestUpsertProjectWorkspaceRow:
    """Task #3: upsert_project ensures/adopts a workspaces row (no FK fail)."""

    def test_provided_uuid_empty_workspaces_creates_row(self, db):
        """Incident step-2 regression: provided uuid + no row → row created,
        projects INSERT succeeds instead of FK-failing."""
        _upsert(db, "proj-aaa", "/root/aaa", workspace_uuid=_WSA)
        assert _ws_present(db, _WSA)
        assert _projects_ws_uuid(db, "proj-aaa") == _WSA

    def test_provided_uuid_conflict_root_adopts(self, db):
        """Provided uuid A while row B owns project_root → adopt B, no A row."""
        _seed_ws(db, _WSB, "legacy-b", "/root/shared")
        _upsert(db, "proj-x", "/root/shared", workspace_uuid=_WSA)
        assert _projects_ws_uuid(db, "proj-x") == _WSB  # adopted
        assert not _ws_present(db, _WSA)  # no competing row

    def test_provided_uuid_legacy_collision_inserts_null_legacy(self, db):
        """Row B holds the legacy pid at a DIFFERENT root → A inserted with
        NULL legacy, projects row points at A."""
        _seed_ws(db, _WSB, "proj-y", "/root/old")
        _upsert(db, "proj-y", "/root/new", workspace_uuid=_WSA)
        assert _projects_ws_uuid(db, "proj-y") == _WSA
        legacy = db._conn.execute(
            "SELECT project_id_legacy FROM workspaces WHERE uuid = ?", (_WSA,)
        ).fetchone()["project_id_legacy"]
        assert legacy is None

    def test_none_uuid_empty_resolution_no_crash(self, db):
        """workspace_uuid=None (the '' startup fallback) → mint, no crash."""
        _upsert(db, "proj-none", "/root/none", workspace_uuid=None)
        ws = _projects_ws_uuid(db, "proj-none")
        assert ws is not None  # minted
        assert _ws_present(db, ws)

    def test_none_uuid_adopts_root_match(self, db):
        """None path adopts a single project_root match instead of minting."""
        _seed_ws(db, _WSB, None, "/root/adopt")
        _upsert(db, "proj-adopt", "/root/adopt", workspace_uuid=None)
        assert _projects_ws_uuid(db, "proj-adopt") == _WSB


def _entity_ws(db, type_id):
    return db._conn.execute(
        "SELECT workspace_uuid FROM entities WHERE type_id = ?", (type_id,)
    ).fetchone()["workspace_uuid"]


class TestBackfillWorkspaceTarget:
    """Task #4: backfill_project_ids honours a supplied workspace_uuid and
    never cross-attributes into a stale legacy-keyed row."""

    def _register_unknown(self, db, eid, root):
        db.register_entity(
            "feature", eid, eid.title(),
            artifact_path=f"{root}/docs/features/{eid}/design.md",
            project_id="__unknown__",
        )

    def test_kwarg_orphan_claims_into_root_row(self, db):
        """Provided uuid orphaned while a root row exists → entities claimed
        into the canonical root row, not a freshly-minted competitor."""
        _seed_ws(db, _WSB, "legacy-b", "/root/shared")
        self._register_unknown(db, "bf-a", "/root/shared")
        n = db.backfill_project_ids(
            "/root/shared", "proj-shared", workspace_uuid=_WSA
        )
        assert n == 1
        assert _entity_ws(db, "feature:bf-a") == _WSB  # adopted root row
        assert not _ws_present(db, _WSA)

    def test_kwarg_wins_over_stale_legacy_row(self, db):
        """Provided uuid is the claim target even when a legacy-keyed row
        for project_id exists at a different root (legacy lookup skipped)."""
        _seed_ws(db, _WSB, "proj-y", "/root/other")
        self._register_unknown(db, "bf-y", "/root/y")
        n = db.backfill_project_ids(
            "/root/y", "proj-y", workspace_uuid=_WSA
        )
        assert n == 1
        # Claimed into A (the provided identity), NOT B (the legacy match).
        assert _entity_ws(db, "feature:bf-y") == _WSA

    def test_none_path_adopts_root_match(self, db):
        """None path: legacy miss + single root match → adopt that row."""
        _seed_ws(db, _WSB, None, "/root/z")
        self._register_unknown(db, "bf-z", "/root/z")
        n = db.backfill_project_ids("/root/z", "proj-z", workspace_uuid=None)
        assert n == 1
        assert _entity_ws(db, "feature:bf-z") == _WSB

    def test_none_path_mints_when_nothing_matches(self, db):
        """None path: no legacy row, no root row → mint a fresh workspace."""
        self._register_unknown(db, "bf-w", "/root/w")
        n = db.backfill_project_ids("/root/w", "proj-w", workspace_uuid=None)
        assert n == 1
        ws = _entity_ws(db, "feature:bf-w")
        assert ws not in (None, "00000000-0000-0000-0000-000000000000")
        assert _ws_present(db, ws)

    def test_multi_row_conflict_root_raises(self, db):
        """Codex blocker 3: >1 rows claim project_root → refuse to attribute
        ambiguously (raise), don't silently first-pick."""
        _seed_ws(db, _WSB, "l1", "/root/dup")
        _seed_ws(db, "cccccccc-3333-4333-8333-cccccccccccc", "l2", "/root/dup")
        self._register_unknown(db, "bf-dup", "/root/dup")
        with pytest.raises(ValueError, match="claimed by 2 workspace rows"):
            db.backfill_project_ids("/root/dup", "proj-dup", workspace_uuid=_WSA)

    def test_none_path_multi_row_raises(self, db):
        """Re-review: the None path must also raise on multi-row (not mint)."""
        _seed_ws(db, _WSB, "l1", "/root/dup2")
        _seed_ws(db, "cccccccc-3333-4333-8333-cccccccccccc", "l2", "/root/dup2")
        self._register_unknown(db, "bf-dup2", "/root/dup2")
        with pytest.raises(ValueError, match="claimed by 2 workspace rows"):
            db.backfill_project_ids("/root/dup2", "proj-dup2", workspace_uuid=None)


class TestUpsertProjectMultiRowConflict:
    """Codex blocker 2: upsert_project must not bind arbitrarily under
    multi-row project_root corruption."""

    def test_multi_row_conflict_root_raises(self, db):
        _seed_ws(db, _WSB, "l1", "/root/dup")
        _seed_ws(db, "cccccccc-3333-4333-8333-cccccccccccc", "l2", "/root/dup")
        with pytest.raises(ValueError, match="claimed by 2 workspace rows"):
            _upsert(db, "proj-dup", "/root/dup", workspace_uuid=_WSA)

    def test_none_path_multi_row_raises(self, db):
        """Re-review: the None path must also raise on multi-row (not mint)."""
        _seed_ws(db, _WSB, "l1", "/root/dup2")
        _seed_ws(db, "cccccccc-3333-4333-8333-cccccccccccc", "l2", "/root/dup2")
        with pytest.raises(ValueError, match="claimed by 2 workspace rows"):
            _upsert(db, "proj-dup2", "/root/dup2", workspace_uuid=None)


# ---------------------------------------------------------------------------
# Feature 121 D1/D2: allocate_entity_id MCP tool + register_entity
# blank-name pre-check
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_db(tmp_path, monkeypatch):
    """DB + seeded workspace for allocate_entity_id tests.

    The module-level ``db`` fixture (:24-30) injects ``_db`` but leaves
    ``_workspace_uuid`` at its "" default — every ``allocate_entity_id``
    call would then hit the ``workspace_unresolved`` early-return
    (vacuous green). This fixture seeds a REAL ``workspaces`` row (the
    ``sequences`` table FK requires it — database.py:2144) and
    monkeypatches both ``entity_server._db`` and
    ``entity_server._workspace_uuid`` so allocation tests exercise the
    real guarded path.
    """
    database = EntityDatabase(str(tmp_path / "alloc.db"))
    ws_uuid = bootstrap_test_workspace(database, "alloc-ws")
    monkeypatch.setattr(entity_server, "_db", database)
    monkeypatch.setattr(entity_server, "_workspace_uuid", ws_uuid)
    yield database, ws_uuid
    database.close()


def _sequences_row(database, ws_uuid, entity_type):
    """Return the ``sequences`` row for (ws_uuid, entity_type), or None."""
    return database._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (ws_uuid, entity_type),
    ).fetchone()


class TestAllocateEntityId:
    """Feature 121 D1: allocate_entity_id atomic MCP tool.

    derived_from: docs/features/121-atomic-display-id-allocation/design.md D1
    """

    @pytest.mark.asyncio
    async def test_format(self, ws_db):
        """First allocation in a fresh workspace returns seq=1 and the
        {seq:03d}-{slug} entity_id format (matches generate_entity_id
        byte-for-byte per D1)."""
        result = await entity_server.allocate_entity_id(
            entity_type="feature", name="Atomic Display Id Allocation"
        )
        parsed = json.loads(result)
        assert parsed == {"seq": 1, "entity_id": "001-atomic-display-id-allocation"}

    @pytest.mark.asyncio
    async def test_same_workspace_two_connections_distinct(self, tmp_path, monkeypatch):
        """Two independent EntityDatabase connections on the SAME db file
        (NOT two threads through the shared _db global — BEGIN IMMEDIATE
        can't nest on one connection) both allocate against one workspace.
        Sequential calls must land 1, 2 — proving next_sequence_value's
        state lives on disk, not cached per-connection. Simulates the
        'Concurrent MCP servers' risk noted in design.md."""
        db_path = str(tmp_path / "race.db")
        db_a = EntityDatabase(db_path)
        ws_uuid = bootstrap_test_workspace(db_a, "race-ws")
        db_b = EntityDatabase(db_path)
        monkeypatch.setattr(entity_server, "_workspace_uuid", ws_uuid)
        try:
            monkeypatch.setattr(entity_server, "_db", db_a)
            result_a = await entity_server.allocate_entity_id(
                entity_type="feature", name="Connection A"
            )
            monkeypatch.setattr(entity_server, "_db", db_b)
            result_b = await entity_server.allocate_entity_id(
                entity_type="feature", name="Connection B"
            )
        finally:
            db_a.close()
            db_b.close()

        parsed_a = json.loads(result_a)
        parsed_b = json.loads(result_b)
        assert parsed_a == {"seq": 1, "entity_id": "001-connection-a"}
        assert parsed_b == {"seq": 2, "entity_id": "002-connection-b"}

    @pytest.mark.asyncio
    async def test_cross_workspace_independent_sequences(self, ws_db, monkeypatch):
        """Two workspaces, same entity_type: each sequence progresses from
        its own value — workspace B's allocation does not perturb
        workspace A's counter."""
        database, ws_a = ws_db
        ws_b = bootstrap_test_workspace(database, "alloc-ws-2")

        monkeypatch.setattr(entity_server, "_workspace_uuid", ws_a)
        result_a1 = await entity_server.allocate_entity_id(
            entity_type="feature", name="Workspace A First"
        )
        monkeypatch.setattr(entity_server, "_workspace_uuid", ws_b)
        result_b1 = await entity_server.allocate_entity_id(
            entity_type="feature", name="Workspace B First"
        )
        monkeypatch.setattr(entity_server, "_workspace_uuid", ws_a)
        result_a2 = await entity_server.allocate_entity_id(
            entity_type="feature", name="Workspace A Second"
        )

        assert json.loads(result_a1)["seq"] == 1
        assert json.loads(result_b1)["seq"] == 1
        assert json.loads(result_a2)["seq"] == 2

    @pytest.mark.asyncio
    async def test_blank_name_envelope_no_consumption(self, ws_db):
        """Blank name -> invalid_input envelope (D1 exact text); the
        sequences row for (ws, 'feature') is untouched (pre-check precedes
        next_sequence_value)."""
        database, ws_uuid = ws_db
        before = _sequences_row(database, ws_uuid, "feature")
        result = await entity_server.allocate_entity_id(entity_type="feature", name="")
        parsed = json.loads(result)
        assert parsed == {
            "error": True,
            "error_type": "invalid_input",
            "message": "name must be non-empty and slugify to a non-empty slug",
            "recovery_hint": "supply a descriptive name containing letters/digits",
        }
        after = _sequences_row(database, ws_uuid, "feature")
        assert after == before

    @pytest.mark.asyncio
    async def test_unslugifiable_name_envelope_no_consumption(self, ws_db):
        """Symbols-only name ('!!!') slugifies to '' — same invalid_input
        envelope as blank, distinct input class, same no-consumption pin."""
        database, ws_uuid = ws_db
        before = _sequences_row(database, ws_uuid, "feature")
        result = await entity_server.allocate_entity_id(entity_type="feature", name="!!!")
        parsed = json.loads(result)
        assert parsed == {
            "error": True,
            "error_type": "invalid_input",
            "message": "name must be non-empty and slugify to a non-empty slug",
            "recovery_hint": "supply a descriptive name containing letters/digits",
        }
        after = _sequences_row(database, ws_uuid, "feature")
        assert after == before

    @pytest.mark.asyncio
    async def test_allocator_cutover_project_kind(self, ws_db):
        """Feature 132 D6.9: the entity_type == 'project' kind_deferred
        rejection guard is retired post-cutover -- allocate_entity_id now
        succeeds for 'project' exactly like any other kind, CONTINUING
        from wherever the `sequences` row was left. The rebuild tool's own
        D6.9 seed-half plants that row at the live census max per
        kind x workspace (task 2's SC2/D6.9 concern, not this MCP-tool
        unit's); simulated here via direct pre-seed, mirroring
        test_four_digit_sequence_value_not_clipped_to_three_digits' pattern
        above. Asserts a fact true ONLY on the post-cutover path: the
        returned seq CAME FROM the sequences table (the pre-seeded
        continuation value, not 1, and not a kind_deferred envelope) --
        and a second allocation advances it sequentially, proving the
        counter genuinely advances rather than being a static readback."""
        database, ws_uuid = ws_db
        database._conn.execute(
            "INSERT INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?, ?, ?)",
            (ws_uuid, "project", 5),
        )
        database._conn.commit()

        result = await entity_server.allocate_entity_id(
            entity_type="project", name="Post Cutover Project"
        )
        parsed = json.loads(result)
        assert parsed == {"seq": 5, "entity_id": "005-post-cutover-project"}

        # A second, distinct allocation in the same workspace continues
        # sequentially -- two concurrent-ish allocations land distinct,
        # ascending seq values, not a repeat of the first.
        result2 = await entity_server.allocate_entity_id(
            entity_type="project", name="Second Post Cutover Project"
        )
        parsed2 = json.loads(result2)
        assert parsed2["seq"] == 6

        # The sequences row itself advanced on disk (not just in the
        # response) -- the fact the counter is genuinely stateful, not a
        # readback.
        after = _sequences_row(database, ws_uuid, "project")
        assert after["next_val"] == 7

    @pytest.mark.asyncio
    async def test_missing_entity_type_invalid_input(self, ws_db):
        """Missing entity_type -> invalid_input envelope, checked BEFORE
        the slug check."""
        result = await entity_server.allocate_entity_id(entity_type="", name="Some Name")
        parsed = json.loads(result)
        assert parsed == {
            "error": True,
            "error_type": "invalid_input",
            "message": "entity_type is required",
            "recovery_hint": "pass entity_type, e.g. 'feature'",
        }

    @pytest.mark.asyncio
    async def test_workspace_unresolved(self, ws_db, monkeypatch):
        """_workspace_uuid == "" (degraded startup) -> workspace_unresolved
        envelope, refused before any kind/name checks."""
        monkeypatch.setattr(entity_server, "_workspace_uuid", "")
        result = await entity_server.allocate_entity_id(
            entity_type="feature", name="Something"
        )
        parsed = json.loads(result)
        assert parsed == {
            "error": True,
            "error_type": "workspace_unresolved",
            "message": (
                "workspace identity not resolved (degraded startup) — "
                "allocation refused"
            ),
            "recovery_hint": "restart the MCP server from the project root / run doctor",
        }

    # -----------------------------------------------------------------
    # Test-deepening additions (dimensions: boundary_values, adversarial,
    # error_propagation) — the tool tests above cover the format/race/
    # cross-workspace/rejection contract; these pin edges the outline
    # above left thin.
    # -----------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_symbols_and_single_letter_name_slugifies_to_valid_one_char_slug(
        self, ws_db
    ):
        """A name that is almost entirely hyphens/spaces around one letter
        ("- a -") slugifies to "a" (non-empty) via _slugify's collapse+
        strip rules (verified: _slugify("- a -") == "a") — this must NOT
        trip the empty-slug rejection. Kills a mutation that tightens the
        tool's `if not slug:` gate to also reject short-but-valid slugs
        (e.g. accidentally requiring `len(slug) >= 2`)."""
        result = await entity_server.allocate_entity_id(
            entity_type="feature", name="- a -"
        )
        parsed = json.loads(result)
        assert parsed == {"seq": 1, "entity_id": "001-a"}

    @pytest.mark.asyncio
    async def test_long_name_truncates_on_hyphen_boundary_through_tool_wiring(
        self, ws_db
    ):
        """_slugify's 30-char hyphen-boundary truncation (id_generator.py
        :33-37) is unit-pinned directly in test_id_generator.py's
        TestSlugify, but never exercised through allocate_entity_id's own
        wiring. Reuses that suite's exact truncation-boundary input
        (slugifies to 'enterprise-reliability', 22 chars, no trailing
        hyphen — verified empirically) to pin that the TOOL composes
        `{seq:03d}-{slug}` from the already-truncated, trailing-hyphen-
        free slug byte-for-byte — not a naive slice of the raw name that
        would land mid-word or leave a dangling hyphen."""
        result = await entity_server.allocate_entity_id(
            entity_type="feature", name="enterprise reliability platform"
        )
        parsed = json.loads(result)
        assert parsed == {"seq": 1, "entity_id": "001-enterprise-reliability"}
        assert not parsed["entity_id"].endswith("-")

    @pytest.mark.asyncio
    async def test_four_digit_sequence_value_not_clipped_to_three_digits(
        self, ws_db
    ):
        """`{seq:03d}` is a MINIMUM-width spec, not a fixed width — once a
        workspace's counter crosses 999, the next allocation must render
        as '1000-...', not a clipped/reformatted 3-digit value. No
        existing test (here or in test_id_generator.py) exercises a
        sequence value >999 through either generate_entity_id or
        allocate_entity_id. Pre-seeds the v1 `sequences` row directly
        (mirrors test_id_generator.py's
        test_continues_from_existing_via_sequences pattern) so the next
        call returns exactly 1000 without 999 prior allocations."""
        database, ws_uuid = ws_db
        database._conn.execute(
            "INSERT INTO sequences(workspace_uuid, entity_type, next_val) "
            "VALUES(?, ?, ?)",
            (ws_uuid, "feature", 1000),
        )
        database._conn.commit()

        result = await entity_server.allocate_entity_id(
            entity_type="feature", name="Boundary Seq"
        )
        parsed = json.loads(result)
        assert parsed == {"seq": 1000, "entity_id": "1000-boundary-seq"}

    @pytest.mark.asyncio
    async def test_next_sequence_value_operational_error_propagates_unhandled(
        self, ws_db, monkeypatch
    ):
        """allocate_entity_id has no try/except around
        next_sequence_value (unlike, e.g., create_key_result's `except
        Exception as exc: return json.dumps({"error": str(exc)})`
        wrapper) — a DB-layer failure here propagates as a raw, uncaught
        exception rather than a structured §3.5 envelope. Pins
        design.md's Error Handling line ('next_sequence_value sqlite
        errors propagate to the server's existing exception translation')
        at the unit level: calling the tool function directly (bypassing
        the FastMCP transport, which is what would apply any outer
        translation) surfaces the raw exception. Would catch a mutation
        that silently swallowed the error into a truthy-ish envelope
        (e.g. a bare `except Exception: return "{}"`)."""
        database, ws_uuid = ws_db

        def _boom(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(database, "next_sequence_value", _boom)

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            await entity_server.allocate_entity_id(entity_type="feature", name="Boom")


class TestRegisterEntityBlankNameGuard:
    """Feature 121 D2: register_entity blank/whitespace-name pre-check.

    Replaces the old auto_id-only truthy guard (:580-581) with an
    invalid_input envelope that fires for BOTH auto_id and explicit-id
    calls, before any sequence consumption.
    """

    @pytest.mark.asyncio
    async def test_blank_name_auto_id_envelope(self, db):
        """auto_id=True + name="" -> invalid_input envelope (not the old
        bare 'Error: name is required when auto_id=True' string)."""
        result = await entity_server.register_entity(
            entity_type="feature", name="", auto_id=True,
        )
        parsed = json.loads(result)
        assert parsed["error"] is True
        assert parsed["error_type"] == "invalid_input"

    @pytest.mark.asyncio
    async def test_whitespace_name_explicit_id_envelope(self, db):
        """Explicit entity_id + whitespace-only name -> invalid_input
        envelope. Pre-fix, only the auto_id path was guarded — an
        explicit-id call with a blank name reached the DB-layer raise
        unguarded."""
        result = await entity_server.register_entity(
            entity_type="feature", entity_id="explicit-blank", name="   ",
        )
        parsed = json.loads(result)
        assert parsed["error"] is True
        assert parsed["error_type"] == "invalid_input"

    @pytest.mark.asyncio
    async def test_auto_id_blank_name_no_sequence_consumption(self, db):
        """auto_id=True + blank name must NOT burn a sequence value — the
        pre-check precedes generate_entity_id (which calls
        next_sequence_value)."""
        before = db._conn.execute("SELECT COUNT(*) AS n FROM sequences").fetchone()["n"]
        result = await entity_server.register_entity(
            entity_type="feature", name="", auto_id=True,
        )
        parsed = json.loads(result)
        assert parsed["error"] is True
        after = db._conn.execute("SELECT COUNT(*) AS n FROM sequences").fetchone()["n"]
        assert after == before

    def test_truthy_guard_removed(self):
        """Grep pin: the deleted auto_id-only truthy guard's message string
        no longer appears anywhere in entity_server.py."""
        server_path = os.path.join(_mcp_dir, "entity_server.py")
        with open(server_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "name is required when auto_id=True" not in content
