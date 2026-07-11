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
