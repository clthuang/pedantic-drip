"""Verify Feature 111 Group E cleanup of free-text status-suffix parsers.

Per spec FR-CL.1-4 / AC-CL.1-4:

* AC-CL.1 — grep for ``(closed:|(promoted →|(fixed:`` returns 0 matches
  across the THREE production paths (entity_registry/backfill.py,
  doctor/checks.py, reconciliation_orchestrator/entity_status.py).
* AC-CL.2 — backfill no longer derives status from prose markers; the
  ``derived_status`` block at backfill.py:418-444 is gone.
* AC-CL.3 — synthetic backlog row with ``status='dropped'`` plus an
  ``entity_relations`` row is identified by doctor as ``closed by
  feature_X`` via DB query, no prose parsing involved.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid as uuid_mod
from pathlib import Path

import pytest


# Resolve the project root via git so this test works regardless of CWD.
def _project_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback for environments without git: walk up to find pyproject/.git
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
                return parent
        raise RuntimeError("Could not resolve project root")


PROJECT_ROOT = _project_root()
TARGET_FILES = [
    PROJECT_ROOT / "plugins/pd/hooks/lib/entity_registry/backfill.py",
    PROJECT_ROOT / "plugins/pd/hooks/lib/doctor/checks.py",
    PROJECT_ROOT / "plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
]


# Pattern matches the markers the parsers used to consume.
# Three discriminators: "(closed:", "(promoted →" (unicode arrow), "(fixed:".
_FREE_TEXT_PARSER_RE = re.compile(r"\(closed:|\(promoted →|\(fixed:")


class TestACCL1NoParsersInProductionFiles:
    """AC-CL.1 — grep returns 0 matches across all 3 production paths."""

    def test_backfill_py_has_no_free_text_parsers(self):
        path = PROJECT_ROOT / "plugins/pd/hooks/lib/entity_registry/backfill.py"
        assert path.is_file(), f"Target file does not exist: {path}"
        content = path.read_text()
        hits = [
            (i + 1, line)
            for i, line in enumerate(content.splitlines())
            if _FREE_TEXT_PARSER_RE.search(line)
        ]
        assert hits == [], (
            f"Found free-text parser markers in {path}:\n"
            + "\n".join(f"  L{n}: {ln}" for n, ln in hits)
        )

    def test_doctor_checks_py_has_no_free_text_parsers(self):
        path = PROJECT_ROOT / "plugins/pd/hooks/lib/doctor/checks.py"
        assert path.is_file(), f"Target file does not exist: {path}"
        content = path.read_text()
        hits = [
            (i + 1, line)
            for i, line in enumerate(content.splitlines())
            if _FREE_TEXT_PARSER_RE.search(line)
        ]
        assert hits == [], (
            f"Found free-text parser markers in {path}:\n"
            + "\n".join(f"  L{n}: {ln}" for n, ln in hits)
        )

    def test_reconciliation_entity_status_py_has_no_free_text_parsers(self):
        path = (
            PROJECT_ROOT
            / "plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py"
        )
        assert path.is_file(), f"Target file does not exist: {path}"
        content = path.read_text()
        hits = [
            (i + 1, line)
            for i, line in enumerate(content.splitlines())
            if _FREE_TEXT_PARSER_RE.search(line)
        ]
        assert hits == [], (
            f"Found free-text parser markers in {path}:\n"
            + "\n".join(f"  L{n}: {ln}" for n, ln in hits)
        )

    def test_combined_grep_returns_zero(self):
        """Run the same grep invocation the doctor check executes
        (per FR-CL.4): grep -nE across all 3 target files; expect 0 hits."""
        # Mirror the FR-CL.4 grep verb used in the doctor check.
        cmd = ["grep", "-nE", r"\(closed:|\(promoted →|\(fixed:"]
        cmd.extend(str(p) for p in TARGET_FILES)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        # grep rc=0 → matches; rc=1 → no matches; rc=2 → error.
        assert proc.returncode == 1, (
            f"Expected grep rc=1 (no matches) across 3 files; "
            f"got rc={proc.returncode}.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        assert proc.stdout == "", (
            f"Expected empty stdout; got:\n{proc.stdout}"
        )


class TestACCL2BackfillNoMarkerDerivation:
    """AC-CL.2 — backfill no longer derives status from prose markers.

    Pre-feature-111 behavior:
        backfill.py:418-444 inspected the description for "(closed:",
        "(fixed:", "(already implemented" markers and called update_entity
        with status='dropped'/'promoted' on a match.

    Post-feature-111 behavior:
        That block is gone. Backfill is a name/metadata refresher only —
        it does NOT touch ``entities.status`` based on prose markers.
        Whatever was already in the DB stays.
    """

    def _make_artifacts(self, tmp_path, rows):
        """Build the minimum artifact tree required by run_backfill."""
        (tmp_path / "brainstorms").mkdir(exist_ok=True)
        (tmp_path / "projects").mkdir(exist_ok=True)
        (tmp_path / "features").mkdir(exist_ok=True)
        lines = [
            "# Backlog",
            "",
            "| ID | Timestamp | Description |",
            "|----|-----------|-------------|",
        ]
        for row_id, ts, desc in rows:
            lines.append(f"| {row_id} | {ts} | {desc} |")
        (tmp_path / "backlog.md").write_text("\n".join(lines) + "\n")

    def test_backfill_does_not_set_status_dropped_for_closed_marker(self, tmp_path):
        """Pre-feature-111 the parser would set status='dropped' on '(closed: ...)'.
        Post-feature-111 status remains as it was (None for a brand-new row)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.backfill import run_backfill

        self._make_artifacts(
            tmp_path,
            [("00101", "2026-01-01T00:00:00Z", "Cleanup something (closed: parser removed)")],
        )
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00101")
            assert entity is not None, "backlog entity should be registered"
            # Post-cleanup: backfill no longer mints status='dropped' from markers.
            # The status defaults to None (per the upsert call which omits status).
            assert entity["status"] in (None, "", "open"), (
                f"backfill should NOT derive status='dropped' from prose marker; "
                f"got status={entity['status']!r}"
            )
        finally:
            db.close()

    def test_backfill_does_not_set_status_promoted_for_promoted_marker(self, tmp_path):
        from entity_registry.database import EntityDatabase
        from entity_registry.backfill import run_backfill

        self._make_artifacts(
            tmp_path,
            [("00102", "2026-01-01T00:00:00Z", "Thing (promoted → feature:111)")],
        )
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00102")
            assert entity is not None
            assert entity["status"] in (None, "", "open"), (
                f"backfill should NOT derive status='promoted' from prose marker; "
                f"got status={entity['status']!r}"
            )
        finally:
            db.close()


class TestACCL3DoctorIdentifiesClosureViaDb:
    """AC-CL.3 — synthetic backlog row at status='dropped' + an
    ``entity_relations(from=<feature>, to=<backlog>, kind='fixes')`` row is
    correctly resolved as ``closed by feature_X`` via DB query, not via
    prose parsing.

    Verifies ``EntityDatabase.get_prior_closer`` -- the DB-only closure
    resolution helper introduced for feature 111's cleanup, which the
    equivalent doctor closure-linkage check (retired in feature 133) once
    mirrored via its own cross-ref query. Hand-crafted DB fixtures only;
    no ``complete_phase`` invocation (parallel-safe with Group D).
    """

    def test_synthetic_closed_by_relation_visible_to_doctor(self, tmp_path):
        from entity_registry.database import EntityDatabase
        from entity_registry.test_helpers import bootstrap_test_workspace

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            ws = bootstrap_test_workspace(db, "p-cl3")

            # Register a feature (the closer) and a backlog (the closed).
            feat_uuid = db.register_entity(
                entity_type="feature",
                entity_id="999-closer",
                name="Closer Feature",
                status="active",
                workspace_uuid=ws,
            )
            bl_uuid = db.register_entity(
                entity_type="backlog",
                entity_id="00777",
                name="Some backlog",
                artifact_path="docs/backlog.md",
                status="dropped",  # already terminal
                workspace_uuid=ws,
            )

            # Write an entity_relations row indicating feature closed backlog.
            # Migration 14 created the table; use the new helper from Group B.
            inserted = db.insert_entity_relation(
                from_uuid=feat_uuid,
                to_uuid=bl_uuid,
                kind="fixes",
            )
            assert inserted is True

            # Verify the helper finds the closer (the DB-only resolution
            # path that replaces prose parsing).
            prior = db.get_prior_closer(bl_uuid)
            assert prior == feat_uuid, (
                f"Expected prior closer to be feature uuid {feat_uuid!r}; "
                f"got {prior!r}"
            )

            # And the closed entity's status is intact (the DB is the
            # source of truth — no parsing step would mutate it).
            entity = db.get_entity("backlog:00777")
            assert entity["status"] == "dropped"
        finally:
            db.close()
