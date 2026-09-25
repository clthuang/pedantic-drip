"""Integration tests for reconciliation_orchestrator CLI (__main__.py).

T2.1 — TDD: tests written before implementation.

Test strategy:
- Most tests use subprocess.run to invoke `python -m reconciliation_orchestrator`
  with temp directories, matching the real invocation pattern from session-start.sh.
- test_per_task_error_isolation uses direct import + unittest.mock to patch one
  task function, since subprocess cannot easily inject per-function mocks.
- test_db_connections_closed uses direct import + unittest.mock for the same reason.
"""
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYTHON = sys.executable
MODULE = "reconciliation_orchestrator"


def _run_cli(project_root, artifacts_root, entity_db, extra_args=None):
    """Run the orchestrator CLI as a subprocess and return CompletedProcess."""
    cmd = [
        PYTHON, "-m", MODULE,
        "--project-root", project_root,
        "--artifacts-root", artifacts_root,
        "--entity-db", entity_db,
    ]
    if extra_args:
        cmd.extend(extra_args)
    env = os.environ.copy()
    # Test file is at lib/reconciliation_orchestrator/test_orchestrator.py
    # One level up is lib/
    lib_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    env["PYTHONPATH"] = lib_dir
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _make_entity_db(path):
    """Create (and close) an EntityDatabase at path so the file exists."""
    db = EntityDatabase(path)
    db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullRunOutputsValidJson:
    """test_full_run_outputs_valid_json: subprocess run produces valid JSON with expected keys."""

    def test_full_run_outputs_valid_json(self, tmp_path):
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        # Minimal project layout — no features/projects/brainstorms dirs needed
        # (orchestrator handles missing dirs gracefully)
        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        )

        output = result.stdout.strip()
        assert output, f"Expected JSON on stdout, got empty output. stderr: {result.stderr}"

        data = json.loads(output)

        expected_keys = {"entity_sync", "cascade_recovery",
                         "dependency_cleanup", "elapsed_ms", "errors"}
        assert set(data.keys()) == expected_keys, (
            f"Expected keys {expected_keys}, got {set(data.keys())}"
        )

        assert isinstance(data["elapsed_ms"], (int, float))
        assert isinstance(data["errors"], list)

    def test_full_run_with_fixtures(self, tmp_path):
        """Full run with actual feature and brainstorm fixtures produces correct counts.

        Task 1 registers the new brainstorm file and skips the registered
        one; the feature's projection is not read (W1.1). Tasks 2 and 3 run
        in the resolved workspace and find nothing to do.
        """
        entity_db_path = str(tmp_path / "entities.db")

        # Seed entity DB with one feature and one registered brainstorm
        db = EntityDatabase(entity_db_path)
        db.register_entity(
            entity_type="feature",
            seq=1, slug="test-feature",
            name="001-test-feature",
            status="active",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.register_entity(
            entity_type="brainstorm",
            display_id="20260101-000001-known",
            name="known",
            status="active",
            artifact_path="docs/brainstorms/20260101-000001-known.prd.md",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.close()

        # A stale .meta.json that session start must not read back
        feature_dir = tmp_path / "docs" / "features" / "001-test-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(json.dumps({"status": "completed"}))

        brainstorms_dir = tmp_path / "docs" / "brainstorms"
        brainstorms_dir.mkdir(parents=True)
        (brainstorms_dir / "20260101-000001-known.prd.md").touch()
        (brainstorms_dir / "20260101-000002-new.prd.md").touch()

        # Workspace identity foundation: resolve_workspace_uuid requires
        # .claude/ to exist for the precedence chain to bootstrap a workspace.
        (tmp_path / ".claude").mkdir()

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["entity_sync"] == {"registered": 1, "skipped": 1, "warnings": []}
        assert data["cascade_recovery"] == 0
        assert data["dependency_cleanup"] == 0
        assert data["errors"] == []
        db = EntityDatabase(entity_db_path)
        try:
            assert db.get_entity("feature:001-test-feature")["status"] == "active"
        finally:
            db.close()


class TestPerTaskErrorIsolation:
    """test_per_task_error_isolation: one task raises → others still run, error captured."""

    def test_entity_status_error_isolated(self, tmp_path):
        """If entity_status.sync_entity_statuses raises, other tasks still run."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        with patch(
            "reconciliation_orchestrator.entity_status.sync_entity_statuses",
            side_effect=RuntimeError("forced entity_status failure"),
        ):
            import reconciliation_orchestrator.__main__ as orch_main

            captured_output = {}

            def fake_exit(code):
                raise SystemExit(code)

            with patch("sys.stdout") as mock_stdout, patch("sys.exit", side_effect=fake_exit):
                import argparse
                args = argparse.Namespace(
                    project_root=str(tmp_path),
                    artifacts_root="docs",
                    entity_db=entity_db_path,
                    workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                )
                written_chunks = []
                mock_stdout.write = lambda s: written_chunks.append(s)

                try:
                    orch_main.run(args)
                except SystemExit:
                    pass

                output_str = "".join(written_chunks)
                data = json.loads(output_str)

            assert data["entity_sync"] is None or "error" in str(data.get("errors", [])), (
                f"Expected entity_sync error captured; got: {data}"
            )
            # Other tasks should still have run (their results are set)
            assert data["cascade_recovery"] == 0
            assert data["dependency_cleanup"] == 0
            assert data["errors"] == ["entity_status: forced entity_status failure"]


class TestDbConnectionsClosed:
    """test_db_connections_closed: EntityDatabase.close() called once."""

    def test_db_connections_closed_on_success(self, tmp_path):
        """close() is called in the finally block on normal exit."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        real_entity_db = EntityDatabase(entity_db_path)

        entity_close_calls = []
        original_entity_close = real_entity_db.close

        real_entity_db.close = lambda: entity_close_calls.append(1) or original_entity_close()

        # Patch where __main__ looks up the names (not in the source module)
        with patch("reconciliation_orchestrator.__main__.EntityDatabase", return_value=real_entity_db):

            def fake_exit(code):
                raise SystemExit(code)

            written_chunks = []
            with patch("sys.stdout") as mock_stdout, patch("sys.exit", side_effect=fake_exit):
                mock_stdout.write = lambda s: written_chunks.append(s)
                try:
                    orch_main.run(args)
                except SystemExit:
                    pass

        assert len(entity_close_calls) == 1, (
            f"EntityDatabase.close() should be called exactly once, got {len(entity_close_calls)}"
        )

    def test_db_connections_closed_on_task_error(self, tmp_path):
        """close() is called even when a task raises."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        real_entity_db = EntityDatabase(entity_db_path)

        entity_close_calls = []
        original_entity_close = real_entity_db.close
        real_entity_db.close = lambda: entity_close_calls.append(1) or original_entity_close()

        with patch("reconciliation_orchestrator.__main__.EntityDatabase", return_value=real_entity_db), \
             patch(
                 "reconciliation_orchestrator.entity_status.sync_entity_statuses",
                 side_effect=RuntimeError("forced failure"),
             ):

            def fake_exit(code):
                raise SystemExit(code)

            written_chunks = []
            with patch("sys.stdout") as mock_stdout, patch("sys.exit", side_effect=fake_exit):
                mock_stdout.write = lambda s: written_chunks.append(s)
                try:
                    orch_main.run(args)
                except SystemExit:
                    pass

        assert len(entity_close_calls) == 1


class TestCliArgsParsed:
    """test_cli_args_parsed: --project-root, --artifacts-root, --entity-db parsed."""

    def test_required_args_accepted(self, tmp_path):
        """CLI accepts all required args without error."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        # If args were not parsed correctly, argparse exits 2
        assert result.returncode == 0, (
            f"CLI failed with returncode {result.returncode}. stderr: {result.stderr}"
        )

    def test_missing_required_arg_exits_nonzero(self, tmp_path):
        """Omitting a required arg causes argparse to exit with code 2."""
        # Missing --entity-db
        cmd = [
            PYTHON, "-m", MODULE,
            "--project-root", str(tmp_path),
            "--artifacts-root", "docs",
            # --entity-db omitted
        ]
        env = os.environ.copy()
        lib_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        env["PYTHONPATH"] = lib_dir
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        assert result.returncode != 0, (
            "Expected non-zero exit when required arg --entity-db is missing"
        )

    def test_args_passed_through_to_run(self, tmp_path):
        """Parsed args are passed correctly to the run() function."""
        import reconciliation_orchestrator.__main__ as orch_main

        args = orch_main.parse_args([
            "--project-root", "/some/root",
            "--artifacts-root", "my_docs",
            "--entity-db", "/some/entities.db",
        ])

        assert args.project_root == "/some/root"
        assert args.artifacts_root == "my_docs"
        assert args.entity_db == "/some/entities.db"


class TestExitCodeAlwaysZero:
    """test_exit_code_always_zero: orchestrator always exits 0, even on errors."""

    def test_exit_zero_on_success(self, tmp_path):
        """Normal run exits 0."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        assert result.returncode == 0

    def test_exit_zero_on_nonexistent_entity_db(self, tmp_path):
        """Even with a non-existent entity DB path, exit code is 0 (fail-open).

        Note: EntityDatabase auto-creates the DB file at the given path,
        so this tests that the orchestrator handles the DB init gracefully.
        """
        entity_db_path = str(tmp_path / "nonexistent" / "entities.db")

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        # Fail-open: exit 0 regardless, error captured in JSON or graceful failure
        assert result.returncode == 0, (
            f"Expected exit 0 (fail-open), got {result.returncode}. stderr: {result.stderr}"
        )

    def test_exit_zero_on_missing_project_root(self, tmp_path):
        """Missing project-root directory → exit 0 (all tasks handle missing dirs gracefully)."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        result = _run_cli(
            project_root="/nonexistent/path/that/does/not/exist",
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for missing project root, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )

    def test_output_is_valid_json_on_error(self, tmp_path):
        """Even when tasks encounter errors, stdout is valid JSON."""
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        result = _run_cli(
            project_root="/nonexistent/path/that/does/not/exist",
            artifacts_root="docs",
            entity_db=entity_db_path,
        )

        assert result.returncode == 0
        output = result.stdout.strip()
        # Must be parseable JSON
        data = json.loads(output)
        assert "errors" in data


# ---------------------------------------------------------------------------
# Task 4: workflow reconciliation tests
# ---------------------------------------------------------------------------


class TestCascadeRecoveryErrorIsolation:
    """Patch _recover_pending_cascades (Task 2) to raise, verify other tasks still run."""

    def test_cascade_recovery_error_does_not_block_other_tasks(self, tmp_path):
        entity_db_path = str(tmp_path / "entities.db")
        _make_entity_db(entity_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )

        with patch(
            "workflow_engine.reconciliation._recover_pending_cascades",
            side_effect=RuntimeError("forced cascade recovery failure"),
        ):
            written_chunks = []

            def fake_exit(code):
                raise SystemExit(code)

            with patch("sys.stdout") as mock_stdout, patch("sys.exit", side_effect=fake_exit):
                mock_stdout.write = lambda s: written_chunks.append(s)
                try:
                    orch_main.run(args)
                except SystemExit:
                    pass

            data = json.loads("".join(written_chunks))

        # Tasks 1 and 3 still ran
        assert data["entity_sync"] == {"registered": 0, "skipped": 0, "warnings": []}
        assert data["dependency_cleanup"] == 0
        # cascade_recovery stays None (error before assignment)
        assert data["cascade_recovery"] is None
        # Error captured
        assert data["errors"] == ["cascade_recovery: forced cascade recovery failure"]
