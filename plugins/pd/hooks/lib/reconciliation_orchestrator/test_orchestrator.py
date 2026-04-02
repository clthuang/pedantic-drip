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

from entity_registry.database import EntityDatabase
from semantic_memory.database import MemoryDatabase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYTHON = sys.executable
MODULE = "reconciliation_orchestrator"


def _run_cli(project_root, artifacts_root, entity_db, memory_db, extra_args=None):
    """Run the orchestrator CLI as a subprocess and return CompletedProcess."""
    cmd = [
        PYTHON, "-m", MODULE,
        "--project-root", project_root,
        "--artifacts-root", artifacts_root,
        "--entity-db", entity_db,
        "--memory-db", memory_db,
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


def _make_memory_db(path):
    """Create (and close) a MemoryDatabase at path so the file exists."""
    db = MemoryDatabase(path)
    db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullRunOutputsValidJson:
    """test_full_run_outputs_valid_json: subprocess run produces valid JSON with expected keys."""

    def test_full_run_outputs_valid_json(self, tmp_path):
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        # Minimal project layout — no features/projects/brainstorms dirs needed
        # (orchestrator handles missing dirs gracefully)
        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0, (
            f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        )

        output = result.stdout.strip()
        assert output, f"Expected JSON on stdout, got empty output. stderr: {result.stderr}"

        data = json.loads(output)

        expected_keys = {"entity_sync", "kb_import", "workflow_reconcile",
                         "dependency_cleanup", "elapsed_ms", "errors"}
        assert set(data.keys()) == expected_keys, (
            f"Expected keys {expected_keys}, got {set(data.keys())}"
        )

        assert isinstance(data["elapsed_ms"], (int, float))
        assert isinstance(data["errors"], list)

    def test_full_run_with_fixtures(self, tmp_path):
        """Full run with actual feature and brainstorm fixtures produces correct counts."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")

        # Seed entity DB with one feature
        db = EntityDatabase(entity_db_path)
        db.register_entity(
            entity_type="feature",
            entity_id="001-test-feature",
            name="001-test-feature",
            status="active",
            project_id="__unknown__",
        )
        db.close()
        _make_memory_db(memory_db_path)

        # Write .meta.json matching the DB status (no drift)
        feature_dir = tmp_path / "docs" / "features" / "001-test-feature"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(json.dumps({"status": "active"}))

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["entity_sync"]["skipped"] >= 1  # matching status → skipped
        assert "registered" in data["entity_sync"]
        assert "deleted" in data["entity_sync"]
        assert data["errors"] == []


class TestPerTaskErrorIsolation:
    """test_per_task_error_isolation: one task raises → others still run, error captured."""

    def test_entity_status_error_isolated(self, tmp_path):
        """If entity_status.sync_entity_statuses raises, kb and other tasks still run."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

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
                    memory_db=memory_db_path,
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
            # kb and other tasks should still have run (keys present with results)
            assert "kb_import" in data
            assert len(data["errors"]) >= 1
            assert "entity_status" in data["errors"][0].lower() or "forced" in data["errors"][0].lower()

    def test_kb_import_error_isolated(self, tmp_path):
        """If kb_import raises, entity and brainstorm tasks still run and are reflected in output."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        with patch(
            "reconciliation_orchestrator.kb_import.sync_knowledge_bank",
            side_effect=RuntimeError("forced kb_import failure"),
        ):
            import reconciliation_orchestrator.__main__ as orch_main

            import argparse
            args = argparse.Namespace(
                project_root=str(tmp_path),
                artifacts_root="docs",
                entity_db=entity_db_path,
                memory_db=memory_db_path,
                )
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

        assert data["kb_import"] is None or len(data["errors"]) >= 1
        assert "entity_sync" in data
        # At least one error captured
        assert len(data["errors"]) >= 1


class TestDbConnectionsClosed:
    """test_db_connections_closed: EntityDatabase.close() and MemoryDatabase.close() called once."""

    def test_db_connections_closed_on_success(self, tmp_path):
        """Both close() methods are called in the finally block on normal exit."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        real_entity_db = EntityDatabase(entity_db_path)
        real_memory_db = MemoryDatabase(memory_db_path)

        entity_close_calls = []
        memory_close_calls = []
        original_entity_close = real_entity_db.close
        original_memory_close = real_memory_db.close

        real_entity_db.close = lambda: entity_close_calls.append(1) or original_entity_close()
        real_memory_db.close = lambda: memory_close_calls.append(1) or original_memory_close()

        # Patch where __main__ looks up the names (not in the source module)
        with patch("reconciliation_orchestrator.__main__.EntityDatabase", return_value=real_entity_db), \
             patch("reconciliation_orchestrator.__main__.MemoryDatabase", return_value=real_memory_db):

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
        assert len(memory_close_calls) == 1, (
            f"MemoryDatabase.close() should be called exactly once, got {len(memory_close_calls)}"
        )

    def test_db_connections_closed_on_task_error(self, tmp_path):
        """Both close() methods are called even when a task raises."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        real_entity_db = EntityDatabase(entity_db_path)
        real_memory_db = MemoryDatabase(memory_db_path)

        entity_close_calls = []
        memory_close_calls = []
        original_entity_close = real_entity_db.close
        original_memory_close = real_memory_db.close
        real_entity_db.close = lambda: entity_close_calls.append(1) or original_entity_close()
        real_memory_db.close = lambda: memory_close_calls.append(1) or original_memory_close()

        with patch("reconciliation_orchestrator.__main__.EntityDatabase", return_value=real_entity_db), \
             patch("reconciliation_orchestrator.__main__.MemoryDatabase", return_value=real_memory_db), \
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
        assert len(memory_close_calls) == 1


class TestCliArgsParsed:
    """test_cli_args_parsed: --project-root, --artifacts-root, --entity-db, --memory-db parsed."""

    def test_required_args_accepted(self, tmp_path):
        """CLI accepts all required args without error."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        # If args were not parsed correctly, argparse exits 2
        assert result.returncode == 0, (
            f"CLI failed with returncode {result.returncode}. stderr: {result.stderr}"
        )

    def test_missing_required_arg_exits_nonzero(self, tmp_path):
        """Omitting a required arg causes argparse to exit with code 2."""
        # Missing --memory-db
        cmd = [
            PYTHON, "-m", MODULE,
            "--project-root", str(tmp_path),
            "--artifacts-root", "docs",
            "--entity-db", str(tmp_path / "entities.db"),
            # --memory-db omitted
        ]
        env = os.environ.copy()
        lib_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        env["PYTHONPATH"] = lib_dir
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        assert result.returncode != 0, (
            "Expected non-zero exit when required arg --memory-db is missing"
        )

    def test_args_passed_through_to_run(self, tmp_path):
        """Parsed args are passed correctly to the run() function."""
        import reconciliation_orchestrator.__main__ as orch_main

        args = orch_main.parse_args([
            "--project-root", "/some/root",
            "--artifacts-root", "my_docs",
            "--entity-db", "/some/entities.db",
            "--memory-db", "/some/memory.db",
        ])

        assert args.project_root == "/some/root"
        assert args.artifacts_root == "my_docs"
        assert args.entity_db == "/some/entities.db"
        assert args.memory_db == "/some/memory.db"


class TestExitCodeAlwaysZero:
    """test_exit_code_always_zero: orchestrator always exits 0, even on errors."""

    def test_exit_zero_on_success(self, tmp_path):
        """Normal run exits 0."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0

    def test_exit_zero_on_nonexistent_entity_db(self, tmp_path):
        """Even with a non-existent entity DB path, exit code is 0 (fail-open).

        Note: EntityDatabase auto-creates the DB file at the given path,
        so this tests that the orchestrator handles the DB init gracefully.
        """
        entity_db_path = str(tmp_path / "nonexistent" / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        # Fail-open: exit 0 regardless, error captured in JSON or graceful failure
        assert result.returncode == 0, (
            f"Expected exit 0 (fail-open), got {result.returncode}. stderr: {result.stderr}"
        )

    def test_exit_zero_on_missing_project_root(self, tmp_path):
        """Missing project-root directory → exit 0 (all tasks handle missing dirs gracefully)."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root="/nonexistent/path/that/does/not/exist",
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0, (
            f"Expected exit 0 for missing project root, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )

    def test_output_is_valid_json_on_error(self, tmp_path):
        """Even when tasks encounter errors, stdout is valid JSON."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root="/nonexistent/path/that/does/not/exist",
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0
        output = result.stdout.strip()
        # Must be parseable JSON
        data = json.loads(output)
        assert "errors" in data


# ---------------------------------------------------------------------------
# Task 4: workflow reconciliation tests
# ---------------------------------------------------------------------------


class TestWorkflowReconcileKeyPresent:
    """Output JSON includes `workflow_reconcile` key with summary dict."""

    def test_workflow_reconcile_key_in_output(self, tmp_path):
        """Subprocess run includes workflow_reconcile key (empty DB = all zeros)."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert "workflow_reconcile" in data, f"Missing workflow_reconcile key: {data}"
        # With empty DB, summary should have all-zero counts
        summary = data["workflow_reconcile"]
        assert isinstance(summary, dict), f"Expected dict, got {type(summary)}"
        assert summary.get("reconciled", -1) == 0
        assert summary.get("skipped", -1) == 0


class TestWorkflowReconcileAppliesDrift:
    """Create feature with .meta.json ahead of DB, verify reconciliation."""

    def test_reconciles_drifted_feature(self, tmp_path):
        """Feature with .meta.json phase ahead of DB gets reconciled."""
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")

        # Seed entity DB with a feature at "specifying" phase
        db = EntityDatabase(entity_db_path)
        db.register_entity(
            entity_type="feature",
            entity_id="099-drift-test",
            name="099-drift-test",
            status="active",
            project_id="__unknown__",
        )
        # Set workflow phase to "specify" in DB (behind .meta.json)
        db.create_workflow_phase(
            "feature:099-drift-test",
            workflow_phase="specify",
            kanban_column="wip",
        )
        db.close()

        _make_memory_db(memory_db_path)

        # Write .meta.json with lastCompletedPhase="create-plan" → derived phase "implement"
        # This is ahead of DB's "specify", creating drift
        feature_dir = tmp_path / "docs" / "features" / "099-drift-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "create-plan",
        }))

        result = _run_cli(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        summary = data.get("workflow_reconcile")
        assert summary is not None, f"workflow_reconcile is None: {data}"
        assert summary["reconciled"] >= 1, f"Expected >=1 reconciled, got: {summary}"


class TestWorkflowReconcileErrorIsolation:
    """Patch apply_workflow_reconciliation to raise, verify other tasks still run."""

    def test_workflow_error_does_not_block_other_tasks(self, tmp_path):
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        with patch(
            "workflow_engine.reconciliation.apply_workflow_reconciliation",
            side_effect=RuntimeError("forced workflow reconcile failure"),
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

        # Other tasks should still have results
        assert "entity_sync" in data
        assert "kb_import" in data
        # workflow_reconcile should be None (error before assignment)
        assert data["workflow_reconcile"] is None
        # Error captured
        assert any("workflow_reconcile" in e for e in data["errors"])


class TestWorkflowReconcileImportDiagnostic:
    """Patch import to raise ImportError, verify diagnostic in errors."""

    def test_import_error_captured_in_errors(self, tmp_path):
        entity_db_path = str(tmp_path / "entities.db")
        memory_db_path = str(tmp_path / "memory.db")
        _make_entity_db(entity_db_path)
        _make_memory_db(memory_db_path)

        import reconciliation_orchestrator.__main__ as orch_main
        import argparse
        import builtins

        args = argparse.Namespace(
            project_root=str(tmp_path),
            artifacts_root="docs",
            entity_db=entity_db_path,
            memory_db=memory_db_path,
        )

        original_import = builtins.__import__

        def mock_import(name, *a, **kw):
            if name == "workflow_engine.engine" or name == "workflow_engine.reconciliation":
                raise ImportError(f"mocked missing: {name}")
            return original_import(name, *a, **kw)

        with patch("builtins.__import__", side_effect=mock_import):
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

        # workflow_reconcile stays None
        assert data["workflow_reconcile"] is None
        # Diagnostic error captured
        assert any("import skipped" in e for e in data["errors"])
