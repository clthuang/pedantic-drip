"""Feature 129 Task 1/2 regression: MCP-level envelope shape for the three
lib-only cross-workspace round-trips.

``test_cross_workspace_matrix.py`` deliberately tests ONLY ``EntityDatabase``
instance methods (its own docstring: "isolates handler behavior from MCP
runtime availability"), so the MCP tool wrappers for ``add_dependency``,
``add_okr_alignment``, and ``set_parent`` -- each of which had its OWN
``CrossWorkspaceError`` catch/envelope block deleted by Task 1
(``entity_server.py`` x2 at the former ``add_dependency``/``add_okr_alignment``
sites, ``server_helpers.py`` x1 at ``_process_set_parent``) -- have NEVER
been exercised cross-workspace, before or after the gate deletion. This
module closes that gap: each tool's SUCCESS response for a cross-workspace
pair is asserted to carry no residual error-envelope fragment (the deleted
gate used to inject ``{"error": True, "error_type":
"cross_workspace_forbidden", ...}`` here, or -- for set_parent's plain-string
success shape -- an "Error setting parent: ..." string).

Mirrors the ``server``/``db``/``_reset_entity_server_globals`` fixture
pattern from ``test_issue_spawn.py`` (same ``entity_server`` module).

See spec:
  /Users/terry/projects/pedantic-drip/docs/features/129-workspace-scoped-queries/spec.md
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

# Make hooks/lib importable for the database + entity_registry imports the
# tests use directly (mirrors test_issue_spawn.py).
_hooks_lib = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "hooks", "lib")
)
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

# Make sibling mcp modules importable so ``import entity_server`` works.
_mcp_dir = os.path.dirname(__file__)
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server  # noqa: E402

from entity_registry.database import EntityDatabase  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers / fixtures (mirrors test_issue_spawn.py)
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously (mirrors test_export_entities)."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_entity_server_globals():
    """Save / restore ``entity_server`` module globals per test."""
    saved_db = entity_server._db
    saved_unavailable = entity_server._db_unavailable
    saved_project_id = entity_server._project_id
    saved_workspace_uuid = entity_server._workspace_uuid
    try:
        yield
    finally:
        entity_server._db = saved_db
        entity_server._db_unavailable = saved_unavailable
        entity_server._project_id = saved_project_id
        entity_server._workspace_uuid = saved_workspace_uuid


@pytest.fixture
def db():
    """In-memory ``EntityDatabase`` with all migrations applied."""
    return EntityDatabase(":memory:")


@pytest.fixture
def server(db):
    """Install ``db`` as ``entity_server._db`` so MCP tools resolve it."""
    entity_server._db = db
    entity_server._db_unavailable = False
    entity_server._project_id = "__unknown__"
    entity_server._workspace_uuid = ""
    return entity_server


@pytest.fixture
def cross_workspace_pair(db, tmp_path):
    """Two entities in two DIFFERENT workspaces.

    entity_a lives in the default `__unknown__` workspace (matching the
    `server` fixture's caller context); entity_b lives in a SECOND, real
    workspace. Returns their UUIDs -- MCP calls below use raw UUIDs (not
    type_id refs) to sidestep resolve_ref's/`_resolve_ref_param`'s
    project_id-scoped resolution, matching the existing precedent in
    test_issue_spawn.py (`parent_uuid=parent_uuid_ws_b`) and
    test_complete_phase_closes.py (`closes=[u_bug_ws2]`): a type_id ref
    would be resolved via `_effective_project_id()` == "__unknown__" and
    would NOT find an entity registered under a different workspace_uuid,
    which would fail the setup for the wrong reason (ValueError: ref not
    found) rather than exercising the cross-workspace success path.
    """
    import uuid as _uuid
    ws_b_uuid = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_b_uuid, "ws-b-mcp-regress", str(tmp_path / "ws_b"), now, now),
    )
    entity_a_uuid = db.register_entity(
        entity_type="feature", entity_id="301-entity-a", name="Entity A",
        status="active", project_id="__unknown__",
    )
    entity_b_uuid = db.register_entity(
        entity_type="backlog", entity_id="302-entity-b", name="Entity B",
        workspace_uuid=ws_b_uuid,
    )
    return entity_a_uuid, entity_b_uuid


# ---------------------------------------------------------------------------
# Regression: no residual error-envelope shape leaks post gate-deletion
# ---------------------------------------------------------------------------


class TestCrossWorkspaceMcpEnvelopeRegression:
    """Feature 129 Task 1: the deleted CrossWorkspaceError catch/envelope
    sites in the add_dependency / add_okr_alignment / set_parent MCP tool
    wrappers must not leave residual error-shaped output for a
    cross-workspace pair that now succeeds.
    """

    def test_add_dependency_cross_workspace_mcp_response_has_no_error_residue(
        self, server, db, cross_workspace_pair,
    ):
        """Anticipate: a leftover/mis-ordered except clause (or a partial
        deletion that keeps the CrossWorkspaceError branch but drops only
        the raise) could still route a cross-workspace pair through the
        deleted error envelope. Kills that residual-branch mutation.
        derived_from: design:D1 (pure removal, no replacement error),
                      dimension:adversarial (Never/Always)
        """
        entity_a_uuid, entity_b_uuid = cross_workspace_pair

        result_raw = _run(server.add_dependency(
            entity_ref=entity_a_uuid, blocked_by_ref=entity_b_uuid,
        ))
        data = json.loads(result_raw)
        assert "error" not in data, (
            f"add_dependency cross-workspace must succeed with no "
            f"residual error envelope, got {data!r}"
        )
        assert "cross_workspace_forbidden" not in result_raw
        assert "result" in data and "Dependency added" in data["result"], (
            f"expected the success envelope shape, got {data!r}"
        )

        rows = db.query_dependencies(
            entity_uuid=entity_a_uuid, blocked_by_uuid=entity_b_uuid,
        )
        assert len(rows) == 1

    def test_add_okr_alignment_cross_workspace_mcp_response_has_no_error_residue(
        self, server, db, cross_workspace_pair,
    ):
        """Anticipate: same residual-branch risk as add_dependency above,
        at the SEPARATE entity_server.py catch site that guarded
        add_okr_alignment specifically.
        derived_from: design:D1 (pure removal, no replacement error),
                      dimension:adversarial (Never/Always)
        """
        entity_a_uuid, entity_b_uuid = cross_workspace_pair

        result_raw = _run(server.add_okr_alignment(
            entity_ref=entity_a_uuid, kr_ref=entity_b_uuid,
        ))
        data = json.loads(result_raw)
        assert "error" not in data, (
            f"add_okr_alignment cross-workspace must succeed with no "
            f"residual error envelope, got {data!r}"
        )
        assert "cross_workspace_forbidden" not in result_raw
        assert "result" in data and "Aligned" in data["result"], (
            f"expected the success envelope shape, got {data!r}"
        )

        aligned = db.get_okr_alignments(entity_a_uuid)
        assert any(kr["uuid"] == entity_b_uuid for kr in aligned)

    def test_set_parent_cross_workspace_mcp_response_has_no_error_residue(
        self, server, db, cross_workspace_pair,
    ):
        """set_parent's success path returns a plain confirmation STRING
        (not JSON) -- distinct from add_dependency/add_okr_alignment's
        JSON envelope. Its deleted CrossWorkspaceError branch used to
        return a JSON error string instead; a partial deletion or a
        surviving generic-Exception fallback would produce something
        that does NOT start with "Parent set:". Kills that residual
        mutation at the server_helpers.py `_process_set_parent` site.
        derived_from: design:D1 (pure removal, no replacement error),
                      dimension:adversarial (Never/Always)
        """
        entity_a_uuid, entity_b_uuid = cross_workspace_pair

        result_raw = _run(server.set_parent(
            type_id=entity_a_uuid, parent_type_id=entity_b_uuid,
        ))
        assert result_raw.startswith("Parent set:"), (
            f"set_parent cross-workspace must succeed with the plain "
            f"confirmation string, got {result_raw!r}"
        )
        assert "cross_workspace_forbidden" not in result_raw
        assert "error" not in result_raw.lower()

        child = db.get_entity(entity_a_uuid)
        assert child is not None
        assert child["parent_uuid"] == entity_b_uuid
