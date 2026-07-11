"""Tests for scripts/seed-census-db.py (feature 126, design D8 5b) and the
session-start.sh sentinel markers bench-populated-read.sh depends on
(design D8's suite-visible drift signal, second guard layer).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from entity_registry import events
from entity_registry import meta_projection

# entity_registry/test_census_seeder.py -> entity_registry -> lib -> hooks
# -> pd -> plugins -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SEED_SCRIPT_PATH = _REPO_ROOT / "scripts" / "seed-census-db.py"
_SESSION_START_SH = _REPO_ROOT / "plugins" / "pd" / "hooks" / "session-start.sh"


def _load_seed_census_db_module():
    """scripts/seed-census-db.py has a hyphenated filename (not a normal
    importable module name) — load it via importlib, the same way a shell
    caller would invoke it as a script, but in-process so this test can
    call seed_census_db() directly and inspect its return value."""
    spec = importlib.util.spec_from_file_location("seed_census_db", _SEED_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Seeder smoke (tasks.md Task 3 item 4(i)): reduced scale (20 entities / 2
# workspaces), seed=0x126. Row counts are EXACT (not >0) — pinned by
# actually running the deterministic seeder once at this scale/seed; a
# silent drop (swallowed exception mid-loop, off-by-one) would move the
# real count away from these values without an ">0" assertion noticing.
# ---------------------------------------------------------------------------
class TestSeederSmoke:
    def test_reduced_scale_seed_produces_exact_row_counts(self, tmp_path):
        module = _load_seed_census_db_module()
        summary = module.seed_census_db(
            str(tmp_path), entity_count=20, workspace_count=2, seed=0x126,
        )
        assert summary["entities"] == 20
        assert summary["events"] == 211
        assert summary["workspaces"] == 2

    def test_seeded_feature_entity_round_trips_through_project_meta(self, tmp_path):
        module = _load_seed_census_db_module()
        summary = module.seed_census_db(
            str(tmp_path), entity_count=20, workspace_count=2, seed=0x126,
        )
        conn = events.connect_v2(summary["db_path"])
        try:
            meta = meta_projection.project_meta(conn, summary["first_entity_uuid"])
        finally:
            conn.close()

        assert meta["id"] == "0000"
        assert meta["slug"]
        assert meta["status"] is not None
        assert meta["mode"] in ("standard", "full")


# ---------------------------------------------------------------------------
# Seeder determinism (test-deepening dimension 5): two independent runs at
# the SAME seed must produce identical row content, not merely identical
# row COUNTS (the existing smoke test above already pins exact counts, but
# never compares two runs against each other). entity_uuid/workspace_uuid
# VALUES legitimately differ run-to-run (generate_uuid7() is never seeded,
# per the script's own docstring) -- determinism lives in the SEEDED
# content (type_id, status, mode, phase depth, iterations, reviewerNotes),
# which is why this test compares type_id + project_meta shape, not uuids.
# ---------------------------------------------------------------------------
class TestSeederDeterminism:
    def test_two_runs_with_same_seed_produce_identical_type_ids_and_meta_shape(
        self, tmp_path
    ):
        module = _load_seed_census_db_module()
        # Given two independent seed_census_db() runs at the same seed,
        # into two separate target directories
        summary_1 = module.seed_census_db(
            str(tmp_path / "run1"), entity_count=20, workspace_count=2, seed=0x126,
        )
        summary_2 = module.seed_census_db(
            str(tmp_path / "run2"), entity_count=20, workspace_count=2, seed=0x126,
        )

        # Then row counts match (row-count equality)
        assert summary_1["entities"] == summary_2["entities"]
        assert summary_1["events"] == summary_2["events"]
        assert summary_1["workspaces"] == summary_2["workspaces"]

        conn_1 = events.connect_v2(summary_1["db_path"])
        conn_2 = events.connect_v2(summary_2["db_path"])
        try:
            # And every entity's type_id (seed-derived, NOT uuid-derived)
            # is identical across both runs, in the same order (sample-row
            # equality across the FULL row set, not just a spot check)
            type_ids_1 = conn_1.execute(
                "SELECT type_id FROM entities ORDER BY type_id"
            ).fetchall()
            type_ids_2 = conn_2.execute(
                "SELECT type_id FROM entities ORDER BY type_id"
            ).fetchall()
            assert type_ids_1 == type_ids_2

            # And the first entity's projected shape (status/mode/phase
            # set) matches too -- proving determinism survives the full
            # event-append + project_meta round trip, not just the raw
            # entities-row INSERT.
            meta_1 = meta_projection.project_meta(conn_1, summary_1["first_entity_uuid"])
            meta_2 = meta_projection.project_meta(conn_2, summary_2["first_entity_uuid"])
            assert meta_1["id"] == meta_2["id"] == "0000"
            assert meta_1["slug"] == meta_2["slug"]
            assert meta_1["status"] == meta_2["status"]
            assert meta_1["mode"] == meta_2["mode"]
            assert meta_1["phases"].keys() == meta_2["phases"].keys()
        finally:
            conn_1.close()
            conn_2.close()


# ---------------------------------------------------------------------------
# Sentinel-existence test (tasks.md Task 3 item 4(ii); design D8 second
# guard layer): a cheap, suite-visible drift signal that runs on every
# `pytest` invocation, independent of whether anyone runs the bench script.
# ---------------------------------------------------------------------------
class TestSentinelMarkersExist:
    def test_all_four_bench_sentinel_markers_present_in_session_start_sh(self):
        content = _SESSION_START_SH.read_text()
        for marker in (
            "# BENCH-WALK-START",
            "# BENCH-WALK-END",
            "# BENCH-GLOB-START",
            "# BENCH-GLOB-END",
        ):
            assert marker in content, f"missing sentinel marker: {marker}"
