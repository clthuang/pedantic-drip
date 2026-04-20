"""Tests for semantic_memory.maintenance module (Feature 082).

All tests share the autouse ``reset_decay_state`` fixture per design I-10:
module-level globals are monkeypatched per-test to the clean state documented
in spec FR-8a's reset-semantics table, and INFLUENCE_DEBUG_LOG_PATH is
redirected to a per-test ``tmp_path`` so tests that enable
``memory_influence_debug`` do not pollute the real
``~/.claude/pd/memory/influence-debug.log``.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import MAXYEAR, datetime, timedelta, timezone

import pytest

from semantic_memory import maintenance, refresh
from semantic_memory.database import MemoryDatabase


@pytest.fixture(autouse=True)
def reset_decay_state(monkeypatch, tmp_path):
    """Reset all module-globals + redirect INFLUENCE_DEBUG_LOG_PATH.

    MUST use ``monkeypatch.setattr`` (not ``from maintenance import ...`` +
    reassign): bool is immutable, and ``from X import Y`` creates a local
    binding to the same object rather than a live reference — setattr is
    the only way to mutate the module namespace reliably.

    Feature 089 FR-3.6 / AC-16 (#00155): also invoke the public
    ``reset_warning_state()`` helpers on both ``maintenance`` and ``refresh``
    so any state those functions clear beyond the monkeypatched set is also
    reset per-test.  The monkeypatched attributes already auto-restore on
    teardown; the helper call is belt-and-suspenders for flags that might be
    added later without updating every test fixture.
    """
    monkeypatch.setattr(maintenance, "_decay_warned_fields", set())
    monkeypatch.setattr(maintenance, "_decay_config_warned", False)
    monkeypatch.setattr(maintenance, "_decay_log_warned", False)
    monkeypatch.setattr(maintenance, "_decay_error_warned", False)
    monkeypatch.setattr(
        maintenance,
        "INFLUENCE_DEBUG_LOG_PATH",
        tmp_path / "influence-debug.log",
    )
    # Feature 089 FR-3.6: call public reset helpers so any new module-level
    # dedup flag added later is cleared without needing a fixture change.
    maintenance.reset_warning_state()
    refresh.reset_warning_state()
    yield
    # monkeypatch auto-restores on teardown


# ---------------------------------------------------------------------------
# reset_warning_state — Feature 089 FR-3.6 / AC-16 (#00155)
# ---------------------------------------------------------------------------


class TestResetWarningState:
    """Feature 089 FR-3.6 / AC-16 (#00155)."""

    def test_reset_warning_state_clears_module_globals(self, monkeypatch):
        """Populate each dedup flag, call reset_warning_state, assert cleared.

        Covers the maintenance-side helper.  The autouse fixture calls this
        helper pre-yield; this test exercises it explicitly so a regression
        that removes the helper (or stops clearing a flag) fails fast.
        """
        # Set dirty state directly on the module (bypassing autouse fixture's
        # monkeypatch by setting the flags post-fixture).
        monkeypatch.setattr(maintenance, "_decay_config_warned", True)
        monkeypatch.setattr(maintenance, "_decay_log_warned", True)
        monkeypatch.setattr(maintenance, "_decay_error_warned", True)
        maintenance._decay_warned_fields.add("some_field")

        maintenance.reset_warning_state()

        assert maintenance._decay_config_warned is False
        assert maintenance._decay_log_warned is False
        assert maintenance._decay_error_warned is False
        assert maintenance._decay_warned_fields == set()

    def test_reset_warning_state_clears_refresh_module_globals(self, monkeypatch):
        """Populate each refresh dedup flag, call reset, assert cleared."""
        monkeypatch.setattr(refresh, "_slow_refresh_warned", True)
        monkeypatch.setattr(refresh, "_refresh_error_warned", True)
        refresh._refresh_warned_fields.add("some_field")

        refresh.reset_warning_state()

        assert refresh._slow_refresh_warned is False
        assert refresh._refresh_error_warned is False
        assert refresh._refresh_warned_fields == set()


# ---------------------------------------------------------------------------
# _warn_and_default
# ---------------------------------------------------------------------------


class TestWarnAndDefault:
    """Task 1.3 / 1.4 — refresh.py:127-140 mirror with `[memory-decay]` prefix."""

    def test_emits_warning_and_adds_key_on_first_call(self, capsys):
        warned: set[str] = set()
        result = maintenance._warn_and_default(
            "some_key", "bogus", 42, warned
        )
        assert result == 42
        assert "some_key" in warned
        captured = capsys.readouterr()
        # stderr prefix diverges from refresh: [memory-decay] per spec FR-8.
        assert "[memory-decay]" in captured.err
        assert "some_key" in captured.err
        assert "is not an int" in captured.err
        # Exactly one stderr line.
        assert captured.err.count("\n") == 1

    def test_deduped_on_second_call_same_key(self, capsys):
        warned: set[str] = set()
        maintenance._warn_and_default("k", "bogus", 10, warned)
        capsys.readouterr()  # drain first warning
        result = maintenance._warn_and_default("k", "bogus2", 10, warned)
        assert result == 10
        captured = capsys.readouterr()
        assert captured.err == ""


# ---------------------------------------------------------------------------
# _resolve_int_config
# ---------------------------------------------------------------------------


class TestResolveIntConfig:
    """Task 1.5 / 1.6 — mirrors refresh._resolve_int_config (refresh.py:143-183)."""

    def test_int_accepted_pass_through(self):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": 30}, "k", 42, warned=warned
        )
        assert result == 30
        assert warned == set()

    def test_bool_rejected(self, capsys):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": True}, "k", 42, warned=warned
        )
        assert result == 42
        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err
        assert "k" in warned

    def test_numeric_string_parsed_via_int(self):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": "30"}, "k", 42, warned=warned
        )
        assert result == 30
        assert warned == set()

    def test_non_numeric_string_rejected(self, capsys):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": "thirty"}, "k", 42, warned=warned
        )
        assert result == 42
        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err
        assert "k" in warned

    def test_none_rejected(self, capsys):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": None}, "k", 42, warned=warned
        )
        assert result == 42
        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err

    def test_float_rejected(self, capsys):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": 5.7}, "k", 42, warned=warned
        )
        assert result == 42
        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err

    def test_clamp_zero_to_one(self):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": 0}, "k", 30, clamp=(1, 365), warned=warned
        )
        assert result == 1

    def test_clamp_five_hundred_to_three_sixty_five(self):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": 500}, "k", 30, clamp=(1, 365), warned=warned
        )
        assert result == 365

    def test_clamp_none_branch_returns_raw_unclamped(self):
        warned: set[str] = set()
        result = maintenance._resolve_int_config(
            {"k": 9999}, "k", 30, clamp=None, warned=warned
        )
        assert result == 9999

    def test_dedup_across_three_consecutive_bad_values(self, capsys):
        warned: set[str] = set()
        maintenance._resolve_int_config(
            {"k": "first_bad"}, "k", 30, warned=warned
        )
        maintenance._resolve_int_config(
            {"k": "second_bad"}, "k", 30, warned=warned
        )
        maintenance._resolve_int_config(
            {"k": "third_bad"}, "k", 30, warned=warned
        )
        captured = capsys.readouterr()
        # Exactly one stderr line despite 3 failures.
        assert captured.err.count("\n") == 1


# ---------------------------------------------------------------------------
# _emit_decay_diagnostic
# ---------------------------------------------------------------------------


def _make_diag(**overrides):
    """Baseline FR-7 diag dict; tests override specific fields."""
    base = {
        "scanned": 10,
        "demoted_high_to_medium": 2,
        "demoted_medium_to_low": 1,
        "skipped_floor": 3,
        "skipped_import": 0,
        "skipped_grace": 1,
        "elapsed_ms": 42,
        "dry_run": False,
    }
    base.update(overrides)
    return base


class TestEmitDecayDiagnostic:
    """Task 1.7 / 1.8 — design I-4."""

    def test_normal_write_produces_one_json_line(self):
        diag = _make_diag()
        maintenance._emit_decay_diagnostic(diag)
        path = maintenance.INFLUENCE_DEBUG_LOG_PATH
        assert path.exists()
        lines = path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        # FR-7 required fields.
        assert record["event"] == "memory_decay"
        assert record["scanned"] == 10
        assert record["demoted_high_to_medium"] == 2
        assert record["demoted_medium_to_low"] == 1
        assert record["skipped_floor"] == 3
        assert record["skipped_import"] == 0
        assert record["skipped_grace"] == 1
        assert record["elapsed_ms"] == 42
        assert record["dry_run"] is False
        assert "ts" in record

    def test_mkdir_failure_on_directory_path_warns_once(
        self, capsys, tmp_path, monkeypatch
    ):
        # Point INFLUENCE_DEBUG_LOG_PATH to a DIRECTORY (not a file):
        # IsADirectoryError is raised by open('a').
        bad_path = tmp_path / "some_dir"
        bad_path.mkdir()
        monkeypatch.setattr(maintenance, "INFLUENCE_DEBUG_LOG_PATH", bad_path)

        maintenance._emit_decay_diagnostic(_make_diag())
        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err
        assert "log write failed" in captured.err
        assert maintenance._decay_log_warned is True

        # Second call: silent.
        maintenance._emit_decay_diagnostic(_make_diag())
        captured = capsys.readouterr()
        assert captured.err == ""


def _read_json_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# _build_summary_line
# ---------------------------------------------------------------------------


class TestBuildSummaryLine:
    """Task 1.9 / 1.10 — design I-5 (ASCII-only, 4 branches)."""

    def test_zero_change_normal_returns_empty(self):
        diag = _make_diag(
            demoted_high_to_medium=0,
            demoted_medium_to_low=0,
            dry_run=False,
        )
        assert maintenance._build_summary_line(diag) == ""

    def test_zero_change_dry_run_returns_empty(self):
        diag = _make_diag(
            demoted_high_to_medium=0,
            demoted_medium_to_low=0,
            dry_run=True,
        )
        assert maintenance._build_summary_line(diag) == ""

    def test_demotions_normal_format(self):
        diag = _make_diag(
            demoted_high_to_medium=1,
            demoted_medium_to_low=2,
            dry_run=False,
        )
        assert maintenance._build_summary_line(diag) == (
            "Decay: demoted high->medium: 1, medium->low: 2 (dry-run: false)"
        )

    def test_demotions_dry_run_format(self):
        diag = _make_diag(
            demoted_high_to_medium=1,
            demoted_medium_to_low=2,
            dry_run=True,
        )
        assert maintenance._build_summary_line(diag) == (
            "Decay (dry-run): would demote high->medium: 1, medium->low: 2"
        )

    def test_output_contains_no_unicode_arrow(self):
        for dry_run in (False, True):
            diag = _make_diag(
                demoted_high_to_medium=5,
                demoted_medium_to_low=7,
                dry_run=dry_run,
            )
            line = maintenance._build_summary_line(diag)
            assert "\u2192" not in line, "Unicode arrow leaked into summary"
            assert "->" in line


# ---------------------------------------------------------------------------
# _select_candidates
# ---------------------------------------------------------------------------


def _seed_entry(
    db: MemoryDatabase,
    *,
    entry_id: str,
    confidence: str = "medium",
    source: str = "session-capture",
    last_recalled_at=None,
    created_at: str,
):
    """Minimal entry seed that lets confidence/source/timestamps be set
    directly. Uses the public ``insert_test_entry_for_testing`` method so
    tests do not touch the private connection (feature 088 FR-10.3 / AC-36).

    Constraint note: `source` is CHECK-constrained to ('retro',
    'session-capture', 'manual', 'import'); default is 'session-capture'
    for the non-import path. `source_project` and `source_hash` are NOT
    NULL so both must be supplied.
    """
    db.insert_test_entry_for_testing(
        entry_id=entry_id,
        confidence=confidence,
        source=source,
        last_recalled_at=last_recalled_at,
        created_at=created_at,
    )


@pytest.fixture
def fresh_db():
    db = MemoryDatabase(":memory:")
    yield db
    db.close()


class TestSelectCandidates:
    """Task 1.11 / 1.12 — design I-2 (single SELECT + Python partition)."""

    def test_partitions_six_entries_across_all_buckets(self, fresh_db):
        # AC-9c: pin canonical Z-suffix format that production _iso_utc uses.
        # Feature 091 FR-6 (New-082-inv-1): swap from stdlib-isoformat (produces
        # `+00:00` suffix) to _iso() (Z suffix) so SQLite lexical comparisons
        # match production behavior. `NOW` resolves via module-level
        # `_TEST_EPOCH` alias at line 507.
        assert _iso(NOW) == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        now_iso = _iso(NOW)
        high_cutoff = _iso(NOW - timedelta(days=30))
        med_cutoff = _iso(NOW - timedelta(days=60))
        grace_cutoff = _iso(NOW - timedelta(days=14))

        stale_high_ts = _iso(NOW - timedelta(days=100))
        stale_med_ts = _iso(NOW - timedelta(days=100))
        fresh_in_grace_ts = _iso(NOW - timedelta(days=10))  # within grace
        past_grace_ts = _iso(NOW - timedelta(days=80))  # past 14d + past 60d

        # Row 1: source=import + stale (must appear in import_count).
        _seed_entry(
            fresh_db,
            entry_id="e1-import",
            confidence="high",
            source="import",
            last_recalled_at=stale_high_ts,
            created_at=stale_high_ts,
        )
        # Row 2: confidence=low + stale (floor).
        _seed_entry(
            fresh_db,
            entry_id="e2-low",
            confidence="low",
            source="session-capture",
            last_recalled_at=stale_med_ts,
            created_at=stale_med_ts,
        )
        # Row 3: never-recalled (last_recalled_at IS NULL) + created within grace.
        _seed_entry(
            fresh_db,
            entry_id="e3-grace",
            confidence="medium",
            source="session-capture",
            last_recalled_at=None,
            created_at=fresh_in_grace_ts,
        )
        # Row 4: never-recalled + past grace + medium → goes to medium_ids.
        _seed_entry(
            fresh_db,
            entry_id="e4-grace-past-medium",
            confidence="medium",
            source="session-capture",
            last_recalled_at=None,
            created_at=past_grace_ts,
        )
        # Row 5: high + stale → goes to high_ids.
        _seed_entry(
            fresh_db,
            entry_id="e5-high-stale",
            confidence="high",
            source="session-capture",
            last_recalled_at=stale_high_ts,
            created_at=stale_high_ts,
        )
        # Row 6: medium + stale → goes to medium_ids.
        _seed_entry(
            fresh_db,
            entry_id="e6-medium-stale",
            confidence="medium",
            source="session-capture",
            last_recalled_at=stale_med_ts,
            created_at=stale_med_ts,
        )

        # Feature 088 FR-3.3 / FR-9.6: _select_candidates is now a generator
        # (no now_iso); bucket partitioning moved to _partition_candidates.
        rows = list(
            maintenance._select_candidates(
                fresh_db,
                high_cutoff=high_cutoff,
                med_cutoff=med_cutoff,
                grace_cutoff=grace_cutoff,
            )
        )
        result = maintenance._partition_candidates(
            rows,
            high_cutoff=high_cutoff,
            med_cutoff=med_cutoff,
            grace_cutoff=grace_cutoff,
        )

        assert result["import_count"] == 1
        assert result["floor_count"] == 1
        assert result["grace_count"] == 1
        assert sorted(result["high_ids"]) == ["e5-high-stale"]
        assert sorted(result["medium_ids"]) == [
            "e4-grace-past-medium",
            "e6-medium-stale",
        ]


# ---------------------------------------------------------------------------
# decay_confidence — Phase 3a (AC-1..AC-9) + Phase 3b (AC-10..AC-32)
# ---------------------------------------------------------------------------


# Feature 088 FR-9.7 / AC-33: canonical test-epoch constant. The ``_TEST_EPOCH``
# name signals test-only scope (underscore prefix) and deterministic value
# (``datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)``) against which all
# ``_days_ago(...)`` offsets are computed. The ``NOW`` alias is preserved so
# existing tests reading ``now=NOW`` continue to work unchanged — the
# ``_days_ago`` default argument ``base=NOW`` still resolves to the same
# datetime after the rename.
_TEST_EPOCH = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
NOW = _TEST_EPOCH  # backward-compat alias


def _iso(dt: datetime) -> str:
    # Feature 088 FR-3.1: Z-suffix UTC format (matches production
    # ``maintenance._iso_utc`` so tests that assert ``updated_at == _iso(NOW)``
    # compare against the same format ``decay_confidence`` now writes).
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_ago(days: float, *, base: datetime = _TEST_EPOCH) -> str:
    return _iso(base - timedelta(days=days))


def _enabled_config(**overrides) -> dict:
    """Baseline config with decay enabled and default thresholds."""
    cfg = {
        "memory_decay_enabled": True,
        "memory_decay_high_threshold_days": 30,
        "memory_decay_medium_threshold_days": 60,
        "memory_decay_grace_period_days": 14,
        "memory_decay_dry_run": False,
    }
    cfg.update(overrides)
    return cfg


def _get_row(db: MemoryDatabase, entry_id: str) -> dict:
    """Read a handful of columns for assertions (feature 088 FR-10.3).

    Uses ``db.fetch_row_for_testing`` instead of reaching into the private
    connection.
    """
    row = db.fetch_row_for_testing(
        "SELECT id, confidence, updated_at, last_recalled_at, source "
        "FROM entries WHERE id = ?",
        (entry_id,),
    )
    assert row is not None, f"entry {entry_id} not found"
    return row


class TestDecayBasicTierTransitions:
    """AC-1 / AC-2 / AC-3 basic tier behaviour."""

    def test_ac1_high_to_medium(self, fresh_db):
        """AC-1: one high entry, last_recalled 31 days ago, default threshold 30."""
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["demoted_high_to_medium"] == 1
        assert result["demoted_medium_to_low"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "medium"
        assert row["updated_at"] == _iso(NOW)

    def test_ac2_medium_to_low(self, fresh_db):
        """AC-2: one medium entry, last_recalled 61 days ago, med threshold 60."""
        stale = _days_ago(61)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="medium",
            last_recalled_at=stale,
            created_at=stale,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["demoted_medium_to_low"] == 1
        assert result["demoted_high_to_medium"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "low"

    def test_ac3_low_is_floor(self, fresh_db):
        """AC-3: low stale 365 days → skipped_floor=1, updated_at unchanged."""
        stale = _days_ago(365)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="low",
            last_recalled_at=stale,
            created_at=stale,
        )
        row_before = _get_row(fresh_db, "e1")

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["skipped_floor"] == 1
        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0
        row_after = _get_row(fresh_db, "e1")
        assert row_after["confidence"] == "low"
        assert row_after["updated_at"] == row_before["updated_at"]


class TestDecayOneTierPerRun:
    """AC-4: high stale 90 days meets both thresholds, but demotes only one tier."""

    def test_ac4_high_stale_ninety_days_demotes_to_medium_only(self, fresh_db):
        stale = _days_ago(90)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["demoted_high_to_medium"] == 1
        assert result["demoted_medium_to_low"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "medium"


class TestDecayGracePeriod:
    """AC-5 / AC-6 never-recalled entries + grace-period interaction."""

    def test_ac5_never_recalled_inside_grace_window_skipped(self, fresh_db):
        """AC-5: medium + last_recalled_at NULL + created 10 days ago < grace 14."""
        created = _days_ago(10)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="medium",
            last_recalled_at=None,
            created_at=created,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["skipped_grace"] == 1
        assert result["demoted_medium_to_low"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "medium"

    def test_ac6_never_recalled_past_grace_and_threshold_demoted(
        self, fresh_db
    ):
        """AC-6: medium + NULL recall + created 80 days ago (> 14 grace, > 60 med)."""
        created = _days_ago(80)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="medium",
            last_recalled_at=None,
            created_at=created,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["demoted_medium_to_low"] == 1
        assert result["skipped_grace"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "low"


class TestDecaySourceImportExclusion:
    """AC-7: source=import entries are not demoted regardless of staleness."""

    def test_ac7_import_source_is_skipped(self, fresh_db):
        stale = _days_ago(365)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            source="import",
            last_recalled_at=stale,
            created_at=stale,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["skipped_import"] == 1
        assert result["demoted_high_to_medium"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "high"


class TestDecayDisabled:
    """AC-8: memory_decay_enabled=False → zero-overhead no-op."""

    def test_ac8_disabled_is_noop(self, fresh_db):
        stale = _days_ago(365)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        row_before = _get_row(fresh_db, "e1")

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(memory_decay_enabled=False), now=NOW
        )

        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0
        assert result["scanned"] == 0
        assert result["skipped_floor"] == 0
        assert result["skipped_import"] == 0
        assert result["skipped_grace"] == 0
        assert result["dry_run"] is False
        row_after = _get_row(fresh_db, "e1")
        assert row_after["confidence"] == "high"
        assert row_after["updated_at"] == row_before["updated_at"]


class TestDecayDryRun:
    """AC-9: dry-run populates counts, leaves DB unchanged."""

    def test_ac9_dry_run_reports_without_modifying(self, fresh_db):
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        row_before = _get_row(fresh_db, "e1")

        result = maintenance.decay_confidence(
            fresh_db,
            _enabled_config(memory_decay_dry_run=True),
            now=NOW,
        )

        assert result["demoted_high_to_medium"] == 1
        assert result["dry_run"] is True
        row_after = _get_row(fresh_db, "e1")
        assert row_after["confidence"] == "high"
        assert row_after["updated_at"] == row_before["updated_at"]


# ---------------------------------------------------------------------------
# Phase 3b — acceptance sweep (AC-10..AC-32 excluding those covered already)
# ---------------------------------------------------------------------------


class TestDecayIntraTickIdempotency:
    """AC-10: running twice with the same `now` is a no-op on the 2nd call."""

    def test_ac10_second_invocation_is_zero_demotions(self, fresh_db):
        # Seed: 1 high stale, 1 medium stale, 1 low stale.
        high_stale = _days_ago(31)
        med_stale = _days_ago(61)
        low_stale = _days_ago(365)
        _seed_entry(
            fresh_db,
            entry_id="e-high",
            confidence="high",
            last_recalled_at=high_stale,
            created_at=high_stale,
        )
        _seed_entry(
            fresh_db,
            entry_id="e-med",
            confidence="medium",
            last_recalled_at=med_stale,
            created_at=med_stale,
        )
        _seed_entry(
            fresh_db,
            entry_id="e-low",
            confidence="low",
            last_recalled_at=low_stale,
            created_at=low_stale,
        )

        # First call: high→medium, medium→low, low is floor.
        r1 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r1["demoted_high_to_medium"] == 1
        assert r1["demoted_medium_to_low"] == 1
        assert r1["skipped_floor"] == 1

        # Snapshot DB state after first call.
        snapshot = {
            eid: _get_row(fresh_db, eid)
            for eid in ("e-high", "e-med", "e-low")
        }

        # Second call: same NOW — updated_at guard blocks re-demotion.
        r2 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r2["demoted_high_to_medium"] == 0
        assert r2["demoted_medium_to_low"] == 0
        # After first call: e-med is now low (61 days stale > 60 med cutoff),
        # AND the original e-low is still stale.  Both match the staleness
        # superset SELECT, and both end up in floor_count.
        assert r2["skipped_floor"] == 2

        # DB state unchanged from snapshot.
        for eid, expected in snapshot.items():
            assert _get_row(fresh_db, eid) == expected


class TestDecayCrossTick:
    """AC-10b-1 + AC-10b-2: cross-tick progressions."""

    def test_ac10b1_freshly_seeded_medium_demotes_on_later_tick(
        self, fresh_db
    ):
        """AC-10b-1: at NOW_1 no entries, at NOW_2 seed a new stale medium."""
        now1 = NOW
        # First invocation: no candidates.
        r1 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=now1
        )
        assert r1["demoted_medium_to_low"] == 0

        # Advance 31 days.
        now2 = now1 + timedelta(days=31)
        # Seed a fresh medium with last_recalled_at 61 days before NOW_2.
        stale_v_now2 = _iso(now2 - timedelta(days=61))
        _seed_entry(
            fresh_db,
            entry_id="e-med",
            confidence="medium",
            last_recalled_at=stale_v_now2,
            created_at=stale_v_now2,
        )

        r2 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=now2
        )
        assert r2["demoted_medium_to_low"] == 1
        assert _get_row(fresh_db, "e-med")["confidence"] == "low"

    def test_ac10b2_demoted_high_now_medium_demotes_again(self, fresh_db):
        """AC-10b-2: high→medium at NOW_1, then medium→low at NOW_2=NOW_1+31."""
        now1 = NOW
        # Use 30d + 1s so the entry is strictly past the 30-day high threshold
        # (the SQL guard is `last_recalled_at < high_cutoff`, strict <).
        stale_v_now1 = _iso(now1 - timedelta(days=30, seconds=1))
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale_v_now1,
            created_at=stale_v_now1,
        )

        r1 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=now1
        )
        assert r1["demoted_high_to_medium"] == 1
        row_mid = _get_row(fresh_db, "e1")
        assert row_mid["confidence"] == "medium"
        # Critical invariant: last_recalled_at MUST NOT have been touched.
        assert row_mid["last_recalled_at"] == stale_v_now1

        # Advance to NOW_2 = NOW_1 + 31 days.  last_recalled_at is now ~61
        # days old, past the 60-day medium threshold.
        now2 = now1 + timedelta(days=31)
        r2 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=now2
        )
        assert r2["demoted_medium_to_low"] == 1
        row_final = _get_row(fresh_db, "e1")
        assert row_final["confidence"] == "low"
        # And still — last_recalled_at is untouched by decay.
        assert row_final["last_recalled_at"] == stale_v_now1


class TestDecayConfigCoercion:
    """AC-11 / AC-12 / AC-13: clamp + bool-reject + malformed-string handling."""

    def test_ac11a_high_threshold_zero_clamped_to_one(
        self, fresh_db, capsys
    ):
        # 0 → clamped to 1.  Feature 088 FR-9.2 / AC-28: clamp is NOT silent —
        # the shared ``_config_utils._resolve_int_config`` emits a stderr
        # warning when ``warn_on_clamp=True`` (maintenance.py binding). The
        # ``capsys`` assertion pins this so the correction from the original
        # "clamped silently" I-3 docstring never regresses.
        #
        # Seeding with last_recalled_at 2 days stale so the clamped
        # threshold of 1 triggers decay.
        stale = _days_ago(2)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config(memory_decay_high_threshold_days=0)
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert result["demoted_high_to_medium"] == 1
        # AC-28: stderr warning pins the warn-on-clamp behavior.
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_high_threshold_days",
            captured.err,
        ), f"expected clamp warning, got stderr: {captured.err!r}"

    def test_ac11b_high_threshold_overflow_clamped_to_365(
        self, fresh_db, capsys,
    ):
        # 500 → clamped to 365.  Entry stale 400 days should still demote.
        # Feature 088 AC-28: stderr warning pinned via capsys.
        stale = _days_ago(400)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config(memory_decay_high_threshold_days=500)
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert result["demoted_high_to_medium"] == 1
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_high_threshold_days",
            captured.err,
        ), f"expected clamp warning, got stderr: {captured.err!r}"

    def test_ac11c_grace_period_negative_clamped_to_zero(
        self, fresh_db, capsys,
    ):
        """AC-11c: grace=-5 clamped to 0 → never-recalled rows past any age decay.

        Feature 088 AC-28: augmented with capsys to pin the warn-on-clamp
        behavior for ``memory_decay_grace_period_days`` (parallel key to the
        high-threshold case exercised by AC-28a/b).
        """
        # Seed a never-recalled medium created 1 day ago.  With grace=0,
        # any created_at < NOW passes the grace filter.  But medium decay
        # still needs 60 days staleness vs created_at; here created_at=1
        # day ago, so it's NOT past 60-day threshold.  Choose a case where
        # grace-clamp actually matters: created 90 days ago, so past both
        # grace=0 and medium threshold=60.
        created = _days_ago(90)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="medium",
            last_recalled_at=None,
            created_at=created,
        )
        cfg = _enabled_config(memory_decay_grace_period_days=-5)
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert result["skipped_grace"] == 0
        assert result["demoted_medium_to_low"] == 1
        # AC-28: clamp warning for the grace-period key. The spec regex
        # targets ``memory_decay_high_threshold_days`` for AC-28a/b; here the
        # parallel key is ``memory_decay_grace_period_days`` (same FR-9.2
        # warn-on-clamp invariant).
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_grace_period_days",
            captured.err,
        ), f"expected clamp warning, got stderr: {captured.err!r}"

    def test_ac12_bool_threshold_rejected(self, fresh_db, capsys):
        # memory_decay_high_threshold_days: True → default 30 + warning.
        stale = _days_ago(31)  # stale per default 30-day threshold
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config(memory_decay_high_threshold_days=True)
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        # Falls back to default 30 → entry 31 days stale → demotes.
        assert result["demoted_high_to_medium"] == 1
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_high_threshold_days",
            captured.err,
        )

    def test_ac12_enabled_bool_is_correct_type(self, fresh_db):
        # memory_decay_enabled: True → decay runs (bool is the expected type).
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        # Explicitly pass True (default).
        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(memory_decay_enabled=True), now=NOW
        )
        assert result["demoted_high_to_medium"] == 1

    def test_ac13_malformed_string_threshold_rejected(self, fresh_db, capsys):
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config(memory_decay_high_threshold_days="thirty")
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert result["demoted_high_to_medium"] == 1
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*'memory_decay_high_threshold_days'"
            r".*'thirty'.*is not an int",
            captured.err,
        )


class TestDecaySemanticCoupling:
    """AC-14: medium < high → one warning per process (dedup via flag)."""

    def test_ac14_inverted_thresholds_warn_once(self, fresh_db, capsys):
        cfg = _enabled_config(
            memory_decay_high_threshold_days=60,
            memory_decay_medium_threshold_days=30,
        )
        maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        captured1 = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*medium_threshold_days.*<.*high_threshold_days",
            captured1.err,
        )

        # Second invocation: zero new warnings.
        maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        captured2 = capsys.readouterr()
        assert captured2.err == ""


class TestDecayWarningDedup:
    """AC-15: 3 consecutive invocations with same malformed field → 1 warning total."""

    def test_ac15_dedup_across_three_invocations(self, fresh_db, capsys):
        cfg = _enabled_config(memory_decay_high_threshold_days="thirty")
        # Invoke 3 times — module-level dedup via _decay_warned_fields.
        for _ in range(3):
            maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        captured = capsys.readouterr()
        # Exactly one warning line containing the malformed field.
        matches = re.findall(
            r"\[memory-decay\].*memory_decay_high_threshold_days.*"
            r"is not an int",
            captured.err,
        )
        assert len(matches) == 1


class TestDecayWarningPredicate:
    """Feature 091 FR-2 (#00076): med_days <= high_days emits stderr warning.

    Predicate flipped from strict `<` to inclusive `<=` so the equal-threshold
    case (where medium and high tiers decay at the same pace) also triggers
    the semantic-coupling warning. Both cases use the same warning template.
    """

    def test_equal_threshold_emits_warning(self, fresh_db, capsys):
        """AC-3: med_days == high_days emits stderr warning.

        The autouse ``reset_decay_state`` fixture resets
        ``maintenance._decay_config_warned`` per-test; no manual reset needed.
        """
        cfg = _enabled_config(
            memory_decay_high_threshold_days=30,
            memory_decay_medium_threshold_days=30,
        )
        maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_medium_threshold_days.*<=.*"
            r"memory_decay_high_threshold_days",
            captured.err,
        ), f"expected equal-threshold warning; got stderr: {captured.err!r}"

    def test_strictly_less_threshold_still_emits_warning(self, fresh_db, capsys):
        """AC-3b: med_days < high_days case continues to emit warning.

        Regression pin for the `<` → `<=` predicate swap: the strict-less
        case MUST still fire so the swap does not silently drop prior behavior.
        """
        cfg = _enabled_config(
            memory_decay_high_threshold_days=30,
            memory_decay_medium_threshold_days=10,
        )
        maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_medium_threshold_days.*<=.*"
            r"memory_decay_high_threshold_days",
            captured.err,
        ), f"expected strict-less warning; got stderr: {captured.err!r}"


class TestDecayImportIdempotency:
    """AC-16: source=import entries remain skipped idempotently."""

    def test_ac16_source_import_skip_is_idempotent(self, fresh_db):
        stale = _days_ago(400)
        _seed_entry(
            fresh_db,
            entry_id="e-import",
            confidence="high",
            source="import",
            last_recalled_at=stale,
            created_at=stale,
        )
        row_before = _get_row(fresh_db, "e-import")

        r1 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r1["skipped_import"] == 1

        r2 = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r2["skipped_import"] == 1

        row_after = _get_row(fresh_db, "e-import")
        assert row_after == row_before


class TestDecayDiagnosticEmission:
    """AC-17 / AC-18: diagnostic log emission on / off."""

    def test_ac17_debug_on_emits_one_json_line(self, fresh_db):
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config()
        cfg["memory_influence_debug"] = True

        maintenance.decay_confidence(fresh_db, cfg, now=NOW)

        lines = _read_json_lines(maintenance.INFLUENCE_DEBUG_LOG_PATH)
        assert len(lines) == 1
        record = lines[0]
        assert record["event"] == "memory_decay"
        # FR-7 required fields.
        for field in (
            "scanned",
            "demoted_high_to_medium",
            "demoted_medium_to_low",
            "skipped_floor",
            "skipped_import",
            "skipped_grace",
            "elapsed_ms",
            "dry_run",
            "ts",
        ):
            assert field in record

    def test_ac18_debug_off_skips_emission(self, fresh_db):
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config()  # memory_influence_debug not set → False
        maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        lines = _read_json_lines(maintenance.INFLUENCE_DEBUG_LOG_PATH)
        assert lines == []


class TestDecayLogWriteFailure:
    """AC-19: INFLUENCE_DEBUG_LOG_PATH → directory → warn once, keep demoting."""

    def test_ac19_log_write_failure_doesnt_block_decay(
        self, fresh_db, capsys, tmp_path, monkeypatch
    ):
        bad_path = tmp_path / "some_dir"
        bad_path.mkdir()
        monkeypatch.setattr(
            maintenance, "INFLUENCE_DEBUG_LOG_PATH", bad_path
        )
        # Two stale high entries so we can assert demotions fire on both calls.
        stale = _days_ago(31)
        for i in range(2):
            _seed_entry(
                fresh_db,
                entry_id=f"e{i}",
                confidence="high",
                last_recalled_at=stale,
                created_at=stale,
            )

        cfg = _enabled_config()
        cfg["memory_influence_debug"] = True

        # First call: emits 1 stderr warning, demotion 1st entry (both,
        # actually — both rows demote in one batch_demote call).
        r1 = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert r1["demoted_high_to_medium"] == 2

        # Second call: silent (dedup via _decay_log_warned).  No new demotions
        # because updated_at guard; but the call should succeed cleanly.
        r2 = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert r2["demoted_high_to_medium"] == 0

        captured = capsys.readouterr()
        # Exactly one log-write-failure warning, across both calls combined.
        matches = re.findall(
            r"\[memory-decay\].*log write failed", captured.err
        )
        assert len(matches) == 1


class TestDecayDbError:
    """AC-20: DB error path — no exception propagates, error key returned."""

    def test_ac20_sqlite_operational_error_captured(
        self, fresh_db, capsys, monkeypatch
    ):
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )

        def _raise(self, *args, **kwargs):
            # MUST be sqlite3.OperationalError (subclass of sqlite3.Error)
            # so the `except sqlite3.Error` in decay_confidence catches it.
            # A generic Exception would escape and crash the call.
            raise sqlite3.OperationalError("mock")

        monkeypatch.setattr(MemoryDatabase, "batch_demote", _raise)

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert "error" in result
        assert "mock" in result["error"]
        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0

        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err
        # Second call should be silent (dedup via _decay_error_warned).
        maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        captured2 = capsys.readouterr()
        assert captured2.err == ""


class TestDecayPromotionAfterDecay:
    """AC-23: source=retro entry demoted, then re-promoted via merge_duplicate."""

    def test_ac23_retro_promotion_after_decay(self, fresh_db):
        # Seed a retro-source high entry that is stale per the high
        # threshold.  Decay demotes it to medium.
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            source="retro",
            last_recalled_at=stale,
            created_at=stale,
        )
        # Pre-observation count: test seeded observation_count=1; merge_duplicate
        # increments by 1 per call.  The promotion threshold is configurable via
        # memory_promote_medium_threshold (default 5).  Ensure observation_count
        # reaches >=5 at the time of the promotion check.
        # merge_duplicate reads pre-increment count, then checks >= threshold.
        # We need post-increment count >= 5, so pre-increment >= 4 at start.
        fresh_db.execute_test_sql_for_testing(
            "UPDATE entries SET observation_count = ? WHERE id = ?",
            (4, "e1"),
        )

        # Decay to medium.
        r = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r["demoted_high_to_medium"] == 1
        assert _get_row(fresh_db, "e1")["confidence"] == "medium"

        # Invoke merge_duplicate with auto-promote on.  retro + medium +
        # observation_count >= memory_promote_medium_threshold → high.
        merge_cfg = {
            "memory_auto_promote": True,
            "memory_promote_low_threshold": 3,
            "memory_promote_medium_threshold": 5,
        }
        fresh_db.merge_duplicate("e1", ["k2"], config=merge_cfg)

        assert _get_row(fresh_db, "e1")["confidence"] == "high"


def _bulk_seed(db: MemoryDatabase, rows: list[tuple]) -> None:
    """Batched executemany seed helper — keeps large seeds (~10k rows) under 2s.

    ``rows`` is a list of 14-tuples matching the INSERT column order in
    ``_seed_entry``.  Caller is responsible for generating plausible values.
    Uses ``db.insert_test_entries_bulk_for_testing`` (feature 088 FR-10.3).
    """
    db.insert_test_entries_bulk_for_testing(rows)


class TestDecayPerformance:
    """AC-24: 10k entries → elapsed_ms < 5000."""

    def test_ac24_ten_thousand_entries_under_five_seconds(self, fresh_db):
        stale_high = _days_ago(31)
        stale_med = _days_ago(61)
        fresh_ts = _days_ago(5)
        rows: list[tuple] = []
        kw = json.dumps(["k"])
        for i in range(10_000):
            mode = i % 4
            if mode == 0:
                conf, last, src = "high", stale_high, "session-capture"
            elif mode == 1:
                conf, last, src = "medium", stale_med, "session-capture"
            elif mode == 2:
                conf, last, src = "low", stale_high, "session-capture"
            else:
                conf, last, src = "high", fresh_ts, "session-capture"
            rows.append(
                (
                    f"e-{i}",
                    f"n-{i}",
                    "d",
                    "patterns",
                    kw,
                    src,
                    "/tmp/p",
                    f"{i:016x}",
                    conf,
                    1 if last else 0,
                    last,
                    last,
                    last,
                    1,
                )
            )
        _bulk_seed(fresh_db, rows)

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        # Hard CI bound per spec AC-24.
        assert result["elapsed_ms"] < 5000
        # Canonical print line for `pytest -s` capture.
        print(
            f"[AC-24 local] elapsed_ms={result['elapsed_ms']} (target: 500ms)"
        )


class TestDecayThresholdEquality:
    """AC-31: high == medium threshold → one-tier demotion holds."""

    def test_ac31_threshold_equality_edge(self, fresh_db, capsys):
        # Use 30d + 1s so the entry is strictly past the cutoff (the SQL guard
        # is `staleness_ts < cutoff`).  Equality-of-thresholds is the edge
        # being tested — not equality-of-cutoff.
        stale = _iso(NOW - timedelta(days=30, seconds=1))
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config(
            memory_decay_high_threshold_days=30,
            memory_decay_medium_threshold_days=30,
        )
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)
        assert result["demoted_high_to_medium"] == 1
        assert result["demoted_medium_to_low"] == 0
        assert _get_row(fresh_db, "e1")["confidence"] == "medium"
        # Feature 091 FR-2: med == high now emits semantic-coupling warning.
        # Drain stderr to prevent pollution of downstream test output.
        capsys.readouterr()


class TestDecayChunkingHappyPath:
    """AC-32 (decay-level): 2000 stale high entries all demoted."""

    def test_ac32_chunking_happy_path_two_thousand_entries(self, fresh_db):
        stale = _days_ago(31)
        kw = json.dumps(["k"])
        rows: list[tuple] = []
        for i in range(2000):
            rows.append(
                (
                    f"e-{i}",
                    f"n-{i}",
                    "d",
                    "patterns",
                    kw,
                    "session-capture",
                    "/tmp/p",
                    f"{i:016x}",
                    "high",
                    1,
                    stale,
                    stale,
                    stale,
                    1,
                )
            )
        _bulk_seed(fresh_db, rows)

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert result["demoted_high_to_medium"] == 2000
        # Feature 088 FR-10.3: public-API read.
        row = fresh_db.fetch_row_for_testing(
            "SELECT COUNT(*) AS cnt FROM entries WHERE confidence = 'medium'"
        )
        assert row["cnt"] == 2000


# ---------------------------------------------------------------------------
# AC-30 end-to-end decay → refresh integration
# ---------------------------------------------------------------------------


class _FixedSimilarityProvider:
    """Inline copy of ``test_memory_server._FixedSimilarityProvider``.

    Defined inline per task 3.22's preference — importing from
    ``plugins/pd/mcp/test_memory_server.py`` requires a cross-directory
    sys.path insert; inline keeps the test self-contained.
    """

    def __init__(self, similarity: float = 0.8, dims: int = 768) -> None:
        self._similarity = similarity
        self._dims = dims

    @property
    def dimensions(self) -> int:
        return self._dims

    @property
    def provider_name(self) -> str:
        return "fixed-similarity"

    @property
    def model_name(self) -> str:
        return "fixed-similarity-model"

    def embed(self, text: str, task_type: str = "query"):
        import numpy as np

        s = self._similarity
        vec = np.zeros(self._dims, dtype=np.float32)
        vec[0] = s
        vec[1] = float(np.sqrt(max(0.0, 1.0 - s * s)))
        return vec

    def embed_batch(
        self, texts: list[str], task_type: str = "document"
    ):
        return [self.embed(t, task_type) for t in texts]


class TestDecayRefreshEndToEnd:
    """AC-30: decay then refresh — stale entry absent, fresh entries present."""

    def test_ac30_decay_then_refresh_filters_stale_from_digest(
        self, fresh_db
    ):
        import numpy as np

        from semantic_memory import refresh as refresh_mod

        stale = _days_ago(61)
        fresh_ts = _days_ago(1)

        # Seed 1 stale medium (will decay to low) + 5 fresh medium/high.
        # Use upsert_entry for proper schema handling; overwrite last_recalled_at
        # and updated_at via raw UPDATE to bypass upsert_entry's behaviour.
        kw = json.dumps(["alpha"])

        # Stale medium.
        stale_entry = {
            "id": "stale",
            "name": "Stale Alpha",
            "description": "stale description",
            "category": "patterns",
            "source": "manual",
            "source_project": "/tmp/p",
            "source_hash": "stale-hash",
            "confidence": "medium",
            "keywords": kw,
            "created_at": stale,
            "updated_at": stale,
        }
        fresh_db.upsert_entry(stale_entry)
        emb_stale = np.zeros(768, dtype=np.float32)
        emb_stale[0] = 1.0
        fresh_db.update_embedding("stale", emb_stale.tobytes())
        fresh_db.execute_test_sql_for_testing(
            "UPDATE entries SET last_recalled_at = ?, updated_at = ? "
            "WHERE id = ?",
            (stale, stale, "stale"),
        )

        # 5 fresh entries.
        for i in range(5):
            conf = "high" if i % 2 == 0 else "medium"
            entry = {
                "id": f"fresh-{i}",
                "name": f"Fresh Alpha {i}",
                "description": f"fresh description {i}",
                "category": "patterns",
                "source": "manual",
                "source_project": "/tmp/p",
                "source_hash": f"fresh-hash-{i}",
                "confidence": conf,
                "keywords": kw,
                "created_at": fresh_ts,
                "updated_at": fresh_ts,
            }
            fresh_db.upsert_entry(entry)
            emb = np.zeros(768, dtype=np.float32)
            emb[0] = 1.0
            fresh_db.update_embedding(f"fresh-{i}", emb.tobytes())
            fresh_db.execute_test_sql_for_testing(
                "UPDATE entries SET last_recalled_at = ?, updated_at = ? "
                "WHERE id = ?",
                (fresh_ts, fresh_ts, f"fresh-{i}"),
            )

        # Decay — stale medium → low.
        r = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert r["demoted_medium_to_low"] == 1
        assert _get_row(fresh_db, "stale")["confidence"] == "low"

        # Refresh per 081 signature at refresh.py:273-282.
        provider = _FixedSimilarityProvider(similarity=0.8)
        digest = refresh_mod.refresh_memory_digest(
            fresh_db,
            provider,
            "alpha",
            10,
            config={},
            feature_type_id="feature:082-test",
            completed_phase="design",
        )

        assert digest is not None
        names = [e["name"] for e in digest["entries"]]
        # (b) stale NOT in digest.
        assert "Stale Alpha" not in names
        # (c) all 5 fresh in digest.
        for i in range(5):
            assert f"Fresh Alpha {i}" in names


# ---------------------------------------------------------------------------
# Phase 3c — CLI tests (AC-29 + NFR-3 process-level)
# ---------------------------------------------------------------------------


class TestCliDryRunOverride:
    """AC-29: --dry-run CLI flag wins over memory_decay_dry_run=false in config."""

    def test_ac29_cli_dry_run_overrides_config_false(self, tmp_path):
        import subprocess

        # Create an isolated HOME so memory.db creation is scoped to tmp_path.
        home = tmp_path / "home"
        home.mkdir()
        project_root = tmp_path / "project"
        (project_root / ".claude").mkdir(parents=True)
        (project_root / ".claude" / "pd.local.md").write_text(
            "memory_decay_enabled: true\n"
            "memory_decay_high_threshold_days: 30\n"
            "memory_decay_medium_threshold_days: 60\n"
            "memory_decay_grace_period_days: 14\n"
            "memory_decay_dry_run: false\n"
        )

        # Seed memory.db inside the isolated HOME.
        db_path = home / ".claude" / "pd" / "memory" / "memory.db"
        db_path.parent.mkdir(parents=True)
        seed_db = MemoryDatabase(str(db_path))
        try:
            stale = _days_ago(31)
            _seed_entry(
                seed_db,
                entry_id="e1",
                confidence="high",
                last_recalled_at=stale,
                created_at=stale,
            )
        finally:
            seed_db.close()

        # Invoke CLI in isolated-HOME subprocess.
        result = subprocess.run(
            [
                "plugins/pd/.venv/bin/python",
                "-m",
                "semantic_memory.maintenance",
                "--decay",
                "--dry-run",
                "--project-root",
                str(project_root),
            ],
            env={
                "HOME": str(home),
                "PYTHONPATH": "plugins/pd/hooks/lib",
                "PATH": "/usr/bin:/bin",
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"stderr={result.stderr!r}"
        )
        # Dry-run summary line.
        assert "(dry-run)" in result.stdout

        # DB unchanged (entry still high, updated_at unchanged).
        verify_db = MemoryDatabase(str(db_path))
        try:
            row = verify_db.fetch_row_for_testing(
                "SELECT confidence, updated_at FROM entries WHERE id = ?",
                ("e1",),
            )
            assert row["confidence"] == "high"
            # updated_at equals the original stale timestamp seeded above.
            assert row["updated_at"] == _days_ago(31)
        finally:
            verify_db.close()


class TestCliProcessLevelZeroOverhead:
    """NFR-3: disabled → subprocess short-circuits BEFORE opening memory.db."""

    def test_nfr3_disabled_cli_does_not_create_memory_db(self, tmp_path):
        import subprocess

        home = tmp_path / "home"
        home.mkdir()
        project_root = tmp_path / "project"
        (project_root / ".claude").mkdir(parents=True)
        (project_root / ".claude" / "pd.local.md").write_text(
            "memory_decay_enabled: false\n"
        )

        result = subprocess.run(
            [
                "plugins/pd/.venv/bin/python",
                "-m",
                "semantic_memory.maintenance",
                "--decay",
                "--project-root",
                str(project_root),
            ],
            env={
                "HOME": str(home),
                "PYTHONPATH": "plugins/pd/hooks/lib",
                "PATH": "/usr/bin:/bin",
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"stderr={result.stderr!r}"
        )
        # memory.db must NOT have been created (NFR-3 process-level).
        assert not (
            home / ".claude" / "pd" / "memory" / "memory.db"
        ).exists()


# ---------------------------------------------------------------------------
# Feature 088 Bundle B — FR-3 (timestamp/overflow) + FR-9.6 (scan_limit)
# ---------------------------------------------------------------------------


class TestDecayOverflowGuard:
    """AC-11: OverflowError/ValueError in cutoff arithmetic → error dict."""

    def test_overflow_config_returns_error_dict(
        self, fresh_db, capsys, monkeypatch
    ):
        """FR-3.2: pathological ``now - timedelta(days=...)`` that overflows
        ``datetime`` range MUST NOT crash — return the zero-diag error dict.

        The production clamp ``(1, 365)`` for threshold days would prevent
        the pathological config from reaching ``timedelta()``, so this test
        widens the clamp via a pass-through monkeypatch so the raw
        ``10_000_000`` survives and actually hits the overflow branch.
        """
        # Pass-through: return int(config[key]) verbatim for threshold keys.
        def _no_clamp(config, key, default, *, clamp=None, warned):
            return int(config.get(key, default))

        monkeypatch.setattr(maintenance, "_resolve_int_config", _no_clamp)

        cfg = _enabled_config(
            memory_decay_high_threshold_days=10_000_000,
            memory_decay_medium_threshold_days=10_000_000,
            memory_decay_grace_period_days=10_000_000,
        )
        # datetime(MAXYEAR, 12, 31) - timedelta(days=10_000_000) → OverflowError.
        far_future = datetime(MAXYEAR, 12, 31, 0, 0, 0, tzinfo=timezone.utc)

        result = maintenance.decay_confidence(
            fresh_db, cfg, now=far_future
        )

        assert "error" in result
        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0
        assert result["scanned"] == 0

        captured = capsys.readouterr()
        assert "[memory-decay]" in captured.err
        assert (
            "overflow" in captured.err.lower()
            or "OverflowError" in captured.err
        )


class TestDecayExactThresholdBoundary:
    """AC-37: last_recalled_at == cutoff is NOT stale (strict ``<``)."""

    def test_exact_threshold_boundary_is_not_stale(self, fresh_db):
        """Seed an entry with ``last_recalled_at = _iso_utc(NOW - 30 days)``
        EXACTLY.  Decay's SQL guard is ``last_recalled_at < high_cutoff``
        (strict <) — boundary equality MUST NOT demote.  Mutation of ``<``
        to ``<=`` at maintenance.py:259/262 is caught by this test.
        """
        boundary_ts = maintenance._iso_utc(NOW - timedelta(days=30))
        _seed_entry(
            fresh_db,
            entry_id="e1",
            confidence="high",
            last_recalled_at=boundary_ts,
            created_at=boundary_ts,
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0
        row = _get_row(fresh_db, "e1")
        assert row["confidence"] == "high"


class TestDecayScanLimit:
    """AC-32: ``memory_decay_scan_limit`` caps the number of rows scanned."""

    def test_scan_limit_caps_result_set(self, fresh_db, monkeypatch):
        """Seed 10 stale-high entries, pass ``memory_decay_scan_limit=5``
        in config (bypassing the production clamp via monkeypatch so the raw
        value survives).  Assert ``scanned == 5`` — the ``LIMIT ?`` clause
        in ``_select_candidates`` caps the result set regardless of how many
        rows match the WHERE predicate.
        """
        stale = _days_ago(31)
        for i in range(10):
            _seed_entry(
                fresh_db,
                entry_id=f"e-{i}",
                confidence="high",
                last_recalled_at=stale,
                created_at=stale,
            )

        # The production ``_resolve_int_config`` clamp is (1000, 10_000_000)
        # so a raw config value of 5 would be clamped up to 1000.  Replace it
        # with a pass-through that returns ``config[key]`` verbatim for this
        # single key so the LIMIT=5 behavior can be exercised directly.
        original = maintenance._resolve_int_config

        def _pass_through_scan_limit(config, key, default, *, clamp=None, warned):
            if key == "memory_decay_scan_limit":
                return int(config.get(key, default))
            return original(config, key, default, clamp=clamp, warned=warned)

        monkeypatch.setattr(
            maintenance, "_resolve_int_config", _pass_through_scan_limit
        )

        cfg = _enabled_config(memory_decay_scan_limit=5)
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)

        assert result["scanned"] == 5
        # And the 5 rows LIMIT-selected all demote (all are stale high).
        assert result["demoted_high_to_medium"] == 5


# ---------------------------------------------------------------------------
# Feature 088 Bundle G — FR-10.1 (strict config coercion + unknown-key warn)
#                         FR-10.2 (CLI uid check)
# ---------------------------------------------------------------------------


class TestCoerceBoolStrict:
    """AC-34b: ``_coerce_bool('False', ...)`` MUST fall back to default + warn."""

    def test_coerce_false_capital_string_returns_default_with_warning(self, capsys):
        """Capital-F ``'False'`` is ambiguous (not in ``_FALSE_VALUES``) — the
        canonical bug from finding #00096 part B where ``'False'`` was silently
        treated as truthy.  Must fall back to ``default`` (True here) AND emit
        the ``ambiguous boolean`` stderr warning.
        """
        from semantic_memory.config import _coerce_bool

        result = _coerce_bool("memory_decay_enabled", "False", True)

        assert result is True  # default returned because 'False' is ambiguous
        captured = capsys.readouterr()
        assert "ambiguous boolean" in captured.err
        assert "memory_decay_enabled" in captured.err


class TestWarnUnknownKeys:
    """AC-34: typos like ``memory_decay_enabaled`` MUST emit a stderr warning."""

    def test_unknown_key_emits_warning(self, capsys):
        """Only the unknown ``memory_decay_enabaled`` typo warns; the correctly-
        spelled ``memory_decay_enabled`` (present in DEFAULTS) does not.
        """
        from semantic_memory.config import _warn_unknown_keys

        _warn_unknown_keys({
            "memory_decay_enabaled": True,    # typo — warns
            "memory_decay_enabled": False,    # correct — silent
        })

        captured = capsys.readouterr()
        assert "memory_decay_enabaled" in captured.err
        # The correct key (in DEFAULTS) MUST NOT warn.  Check via a marker
        # that only the unknown-key warning line would contain:
        # ``'memory_decay_enabled'`` (single-quoted by ``{key!r}``).
        assert "'memory_decay_enabled'" not in captured.err
        # Defense-in-depth: only one warning line (one unknown key).
        assert captured.err.count("unknown key") == 1


class TestForeignUidProjectRootRefuses:
    """AC-35: ``maintenance._main`` with foreign-uid project_root MUST exit 2."""

    def test_foreign_uid_project_root_refuses(
        self, tmp_path, monkeypatch, capsys
    ):
        """Monkeypatch ``os.getuid`` to return 1000 and ``Path.stat`` for the
        resolved ``project_root`` to return st_uid=2000.  Calling ``_main``
        (via ``sys.argv``) MUST ``SystemExit(2)`` and emit a stderr warning
        containing ``REFUSING``.
        """
        import os as os_module

        # Use a real directory so .resolve() + is_dir() succeeds.
        foreign_root = tmp_path / "foreign"
        foreign_root.mkdir()

        # Stub os.getuid() (called from maintenance._main).
        monkeypatch.setattr(os_module, "getuid", lambda: 1000)

        # Stub Path.stat() so the resolved project_root reports a foreign uid.
        real_stat = type(foreign_root).stat

        class _FakeStat:
            st_uid = 2000

        def _fake_stat(self, *a, **kw):
            try:
                resolved = self.resolve()
            except OSError:
                resolved = self
            if resolved == foreign_root.resolve():
                return _FakeStat()
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(type(foreign_root), "stat", _fake_stat)

        # Invoke CLI via sys.argv (parser.parse_args() reads sys.argv[1:]).
        monkeypatch.setattr(
            "sys.argv",
            [
                "semantic_memory.maintenance",
                "--decay",
                "--project-root",
                str(foreign_root),
            ],
        )

        with pytest.raises(SystemExit) as excinfo:
            maintenance._main()

        assert excinfo.value.code == 2
        captured = capsys.readouterr()
        assert "REFUSING" in captured.err
        assert "uid=2000" in captured.err
        assert "uid=1000" in captured.err


class TestInfluenceLogSymlinkRefusal:
    """AC-2 (FR-1.2, #00097): O_NOFOLLOW prevents symlink-clobber attack."""

    def test_influence_log_refuses_symlink_follow(
        self, fresh_db, tmp_path, monkeypatch, capsys
    ):
        """Symlink at the log path MUST cause write failure, not follow.

        Threat model: attacker pre-creates `influence-debug.log` as a symlink
        to a sensitive file (e.g. /tmp/target). Without O_NOFOLLOW, the
        maintenance process would append to the symlink target. With the
        FR-1.2 fix, `os.open(..., O_NOFOLLOW, ...)` raises OSError (ELOOP)
        and the try/except OSError swallows it into a one-shot warning.
        """
        # Target file that MUST remain untouched.
        target = tmp_path / "target_sentinel"
        target.write_text("untouched\n")
        target_mtime_before = target.stat().st_mtime

        # Symlink at the log path → target.
        log_link = tmp_path / "symlink-log.log"
        log_link.symlink_to(target)

        monkeypatch.setattr(maintenance, "INFLUENCE_DEBUG_LOG_PATH", log_link)

        # Seed one stale high entry + enable influence-debug so the diagnostic
        # emission codepath fires.
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="sym-1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg = _enabled_config()
        cfg["memory_influence_debug"] = True

        # Run decay. Should not raise — OSError must be swallowed by the
        # _emit_decay_diagnostic try/except (best-effort logging).
        result = maintenance.decay_confidence(fresh_db, cfg, now=NOW)

        # Decay itself completed successfully (log failure is non-blocking).
        assert result["demoted_high_to_medium"] == 1

        # Symlink target MUST be unchanged (O_NOFOLLOW prevented the write).
        assert target.read_text() == "untouched\n"
        assert target.stat().st_mtime == target_mtime_before

        # Symlink itself remains a symlink (was not replaced by a regular file).
        assert log_link.is_symlink()

        # Exactly one stderr warning about the log write failure.
        captured = capsys.readouterr()
        matches = re.findall(
            r"\[memory-decay\].*log write failed", captured.err
        )
        assert len(matches) == 1


# ---------------------------------------------------------------------------
# Feature 088 Bundle H.3a — Concurrency + integration tests
# ---------------------------------------------------------------------------


class TestConcurrentWriterViaDecayConfidence:
    """AC-31 (FR-9.5, #00108): end-to-end concurrent-writer test.

    Thread A holds a BEGIN IMMEDIATE write lock past the busy_timeout budget;
    thread B calls ``decay_confidence`` against the same file-backed DB. The
    decay-layer sqlite3.Error catch MUST surface as an error-dict return
    value (NOT a raised exception — FR-8 invariant).
    """

    def test_concurrent_writer_via_decay_confidence(self, tmp_path):
        import threading

        db_path = str(tmp_path / "concurrent-decay.db")

        # Seed: create a stale-high entry so decay would want to demote it.
        seed_db = MemoryDatabase(db_path)
        try:
            stale = _days_ago(31)
            seed_db.insert_test_entry_for_testing(
                entry_id="contention-1",
                confidence="high",
                last_recalled_at=stale,
                created_at=stale,
            )
        finally:
            seed_db.close()

        # Open thread B's DB BEFORE the lock-holder starts, so its __init__
        # migration completes without contention. Very short busy_timeout so
        # batch_demote's BEGIN IMMEDIATE raises rather than waiting.
        db_b = MemoryDatabase(db_path, busy_timeout_ms=200)

        hold_lock_started = threading.Event()
        release_lock = threading.Event()

        def writer_holds_lock():
            # Raw sqlite3 connection, long timeout so lock acquisition
            # succeeds immediately.
            conn_a = sqlite3.connect(db_path, timeout=10.0)
            try:
                conn_a.execute("BEGIN IMMEDIATE")
                # Apply a no-op write so the IMMEDIATE lock is unambiguous.
                conn_a.execute(
                    "UPDATE entries SET description = description "
                    "WHERE id = ?",
                    ("contention-1",),
                )
                hold_lock_started.set()
                # Hold the lock until told to release.
                release_lock.wait(timeout=10.0)
                conn_a.rollback()
            finally:
                conn_a.close()

        thread_a = threading.Thread(target=writer_holds_lock)
        thread_a.start()

        try:
            assert hold_lock_started.wait(timeout=5.0), (
                "Thread A failed to acquire write lock within 5s"
            )
            result = maintenance.decay_confidence(
                db_b, _enabled_config(), now=NOW
            )
        finally:
            db_b.close()
            release_lock.set()
            thread_a.join(timeout=10.0)

        # FR-8 invariant: decay MUST NOT raise on DB errors. It returns a
        # diagnostic dict with the ``error`` key populated.
        assert isinstance(result, dict), (
            f"decay_confidence must return dict, got {type(result).__name__}"
        )
        assert "error" in result, (
            f"expected 'error' key under lock contention; got: {result!r}"
        )
        # No demotion happened (write path never acquired the lock).
        assert result["demoted_high_to_medium"] == 0


class TestConcurrentDecayAndRecordInfluence:
    """AC-39 part 1 (FR-10.6, #00115): decay + record_influence together."""

    def test_concurrent_decay_and_record_influence_both_succeed_eventually(
        self, tmp_path,
    ):
        import threading

        db_path = str(tmp_path / "cross-feature.db")
        loop_count = 20

        # Seed: 5 stale-high entries (decay candidates) + 1 influence target.
        seed_db = MemoryDatabase(db_path)
        try:
            stale = _days_ago(31)
            for i in range(5):
                seed_db.insert_test_entry_for_testing(
                    entry_id=f"decay-{i}",
                    confidence="high",
                    last_recalled_at=stale,
                    created_at=stale,
                )
            # Influence target — a separate entry, not a decay candidate.
            seed_db.insert_test_entry_for_testing(
                entry_id="influence-target",
                confidence="medium",
                last_recalled_at=_days_ago(1),
                created_at=_days_ago(1),
            )
        finally:
            seed_db.close()

        errors: list[BaseException] = []

        def run_record_influence():
            try:
                db = MemoryDatabase(db_path, busy_timeout_ms=5000)
                try:
                    for _ in range(loop_count):
                        db.record_influence(
                            "influence-target", "reviewer", "feature:cross-001"
                        )
                finally:
                    db.close()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def run_decay_once():
            try:
                db = MemoryDatabase(db_path, busy_timeout_ms=5000)
                try:
                    maintenance.decay_confidence(
                        db, _enabled_config(), now=NOW
                    )
                finally:
                    db.close()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t_influence = threading.Thread(target=run_record_influence)
        t_decay = threading.Thread(target=run_decay_once)

        t_influence.start()
        t_decay.start()
        t_influence.join(timeout=30.0)
        t_decay.join(timeout=30.0)

        assert not t_influence.is_alive(), "record_influence thread hung"
        assert not t_decay.is_alive(), "decay thread hung"
        assert errors == [], f"unexpected errors: {errors}"

        # Post-run invariants (AC-39 strengthened assertions).
        verify_db = MemoryDatabase(db_path)
        try:
            # (1) At least one stale-high entry was demoted to medium.
            demoted = verify_db.fetch_row_for_testing(
                "SELECT COUNT(*) AS cnt FROM entries "
                "WHERE confidence = 'medium' AND id LIKE 'decay-%'"
            )
            assert demoted["cnt"] >= 1, (
                f"expected >=1 decay-demotion, got {demoted['cnt']}"
            )

            # (2) influence_log has >= loop_count rows from the record_influence loop.
            log_rows = verify_db.fetch_row_for_testing(
                "SELECT COUNT(*) AS cnt FROM influence_log "
                "WHERE entry_id = 'influence-target'"
            )
            assert log_rows["cnt"] >= loop_count, (
                f"expected >= {loop_count} influence_log rows, "
                f"got {log_rows['cnt']}"
            )
        finally:
            verify_db.close()


class TestFts5QueriesStillWorkAfterBulkDecay:
    """AC-39 part 2 (FR-10.6, #00115): FTS5 survives bulk decay."""

    def test_fts5_queries_still_work_after_bulk_decay(self, fresh_db):
        if not fresh_db.fts5_available:
            pytest.skip("FTS5 not available on this SQLite build")

        stale = _days_ago(31)
        distinctive_keyword = "glyphosaurus"  # unlikely to collide
        # Seed 50 stale-high entries with the distinctive keyword in `name`
        # so the FTS5 `name` column indexes it.
        rows = []
        for i in range(50):
            rows.append(
                (
                    f"fts-{i}",
                    f"{distinctive_keyword} entry {i}",
                    f"description {i}",
                    "patterns",
                    json.dumps(["keyword"]),
                    "session-capture",
                    "/tmp/p",
                    f"{i:016x}",
                    "high",
                    1,
                    stale,
                    stale,
                    stale,
                    1,
                )
            )
        _bulk_seed(fresh_db, rows)

        # Record last_recalled_at before decay — decay must NOT change it
        # (only updated_at is touched by batch_demote).
        before = fresh_db.fetch_row_for_testing(
            "SELECT last_recalled_at FROM entries WHERE id = 'fts-0'"
        )
        before_ts = before["last_recalled_at"]

        # Run decay — all 50 demote from high to medium.
        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert result["demoted_high_to_medium"] == 50

        # FTS5 MATCH query must still return all 50 rows.
        matches = fresh_db.fts5_search(distinctive_keyword, limit=100)
        assert len(matches) == 50, (
            f"FTS5 returned {len(matches)} rows, expected 50"
        )

        # Every returned row has post-decay confidence in (medium, low).
        returned_ids = [m[0] for m in matches]
        placeholders = ", ".join("?" * len(returned_ids))
        conf_row = fresh_db.fetch_row_for_testing(
            f"SELECT COUNT(*) AS cnt FROM entries "
            f"WHERE id IN ({placeholders}) "
            f"AND confidence IN ('medium', 'low')",
            returned_ids,
        )
        assert conf_row["cnt"] == 50

        # last_recalled_at on those rows is unchanged (decay only touches
        # confidence + updated_at, NOT the recall timestamp).
        after = fresh_db.fetch_row_for_testing(
            "SELECT last_recalled_at FROM entries WHERE id = 'fts-0'"
        )
        assert after["last_recalled_at"] == before_ts


class TestRejectsOrNormalizesNaiveDatetimeNow:
    """AC-38 (FR-10.5, #00114): tz-naive ``now`` handling is pinned."""

    def test_rejects_or_normalizes_naive_datetime_now(self, fresh_db):
        """Pass a tz-naive ``datetime(2026,4,16,12)`` to ``decay_confidence``.

        Current implementation (maintenance.py:316-324) normalizes by NOT
        calling ``astimezone`` when ``tzinfo is None`` — leaving the naive
        datetime in place. This test PINS that branch: decay runs without
        raising (no TypeError / ValueError) despite the lack of tzinfo.
        A future refactor that tightens this MUST update this test.
        """
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="naive-1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        naive_now = datetime(2026, 4, 16, 12, 0, 0)  # NO tzinfo
        assert naive_now.tzinfo is None

        # MUST NOT raise — naive datetime is accepted (left un-normalized).
        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=naive_now
        )
        assert isinstance(result, dict)
        # The decay still runs — no error key required, scanning happened.
        assert "error" not in result, (
            f"decay should not error on naive datetime: {result!r}"
        )


# ---------------------------------------------------------------------------
# Feature 088 Bundle H.3b — Boundary + error-path + augmentation tests
# ---------------------------------------------------------------------------


class TestEmptyDbReturnsAllZerosWithNoError:
    """AC-40 part 1 (FR-10.7, #00116): empty DB → all-zero diag, no error."""

    def test_empty_db_returns_all_zeros_with_no_error(self, fresh_db):
        # fresh_db has zero entries.
        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )
        assert result["scanned"] == 0
        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0
        assert result["skipped_floor"] == 0
        assert result["skipped_import"] == 0
        assert result["skipped_grace"] == 0
        # No error key on the happy (empty) path.
        assert "error" not in result, (
            f"expected no error key on empty DB, got: {result!r}"
        )


class TestNanInfinityAndNegativeZeroThresholdValues:
    """AC-40 part 2 (FR-10.7): NaN/Inf threshold values → default + warn."""

    def test_nan_threshold_falls_back_to_default_with_warning(
        self, fresh_db, capsys, monkeypatch,
    ):
        # Ensure the warned-set is empty at start of this test (autouse
        # fixture does this, but reset here for defense-in-depth).
        monkeypatch.setattr(maintenance, "_decay_warned_fields", set())

        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="nan-1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        # NaN: _resolve_int_config rejects float (bool/str/int only); NaN hits
        # the "unsupported type" branch and falls back to default=30.
        cfg_nan = _enabled_config(
            memory_decay_high_threshold_days=float("nan"),
        )
        result_nan = maintenance.decay_confidence(fresh_db, cfg_nan, now=NOW)
        # Default 30 applies → entry 31 days stale demotes.
        assert result_nan["demoted_high_to_medium"] == 1
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_high_threshold_days",
            captured.err,
        ), f"expected NaN warning, got stderr: {captured.err!r}"

    def test_infinity_threshold_falls_back_to_default_with_warning(
        self, fresh_db, capsys, monkeypatch,
    ):
        # Separate test (not shared warned-set) so the dedup guard does not
        # swallow the second warning. AC-40 covers both float('nan') and
        # float('inf') independently.
        monkeypatch.setattr(maintenance, "_decay_warned_fields", set())

        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="inf-1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )
        cfg_inf = _enabled_config(
            memory_decay_high_threshold_days=float("inf"),
        )
        result_inf = maintenance.decay_confidence(fresh_db, cfg_inf, now=NOW)
        assert result_inf["demoted_high_to_medium"] == 1
        captured = capsys.readouterr()
        assert re.search(
            r"\[memory-decay\].*memory_decay_high_threshold_days",
            captured.err,
        ), f"expected inf warning, got stderr: {captured.err!r}"


class TestSqliteErrorDuringSelectPhase:
    """AC-40 part 3 (FR-10.7): sqlite3.Error during SELECT → error dict."""

    def test_sqlite_error_during_select_phase_returns_error_dict(
        self, fresh_db, monkeypatch,
    ):
        """Monkeypatch ``maintenance._select_candidates`` (the module-level
        SELECT helper) to raise ``sqlite3.OperationalError('disk I/O error')``.
        The ``decay_confidence`` sqlite3.Error branch MUST surface an error
        dict with zero demotion counts (FR-8 invariant).

        Uses monkeypatch on the public module binding rather than reaching
        into the private connection (feature 088 FR-10.3 / AC-36).
        """
        stale = _days_ago(31)
        _seed_entry(
            fresh_db,
            entry_id="err-1",
            confidence="high",
            last_recalled_at=stale,
            created_at=stale,
        )

        def _raising_select_candidates(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(
            maintenance, "_select_candidates", _raising_select_candidates
        )

        result = maintenance.decay_confidence(
            fresh_db, _enabled_config(), now=NOW
        )

        assert "error" in result, (
            f"expected error dict on SELECT failure, got: {result!r}"
        )
        assert result["demoted_high_to_medium"] == 0
        assert result["demoted_medium_to_low"] == 0


# Note: AC-28 (FR-9.2) — the ``test_ac11a/b/c`` methods in
# ``TestDecayConfigCoercion`` were augmented in-place with ``capsys`` +
# stderr regex assertions (per the spec DoD wording). No separate augmented
# class is needed.


# ---------------------------------------------------------------------------
# Feature 089 Bundle A — Security hardening tests
# ---------------------------------------------------------------------------


class TestFeature089BundleA:
    """Feature 089 Bundle A (#00139, #00141, #00154): strict boolean
    coercion routed through ``read_config``, tz-naive rejection in
    ``_iso_utc``, and insecure-parent-dir refusal in the influence log.
    """

    def test_coerce_bool_routed_from_read_config(self, tmp_path, capsys):
        """AC-1 (FR-1.1 / #00139).

        ``read_config`` MUST route bool-default keys through ``_coerce_bool``
        so ambiguous variants like the capital-F ``'False'`` fall back to
        the DEFAULTS value (False) AND emit a one-line stderr warning.

        Pre-089 this string round-tripped as ``'False'`` (truthy) and later
        truthy-checks silently ran decay against the operator's intent.
        """
        from semantic_memory.config import read_config

        project_root = tmp_path
        (project_root / ".claude").mkdir()
        (project_root / ".claude" / "pd.local.md").write_text(
            "memory_decay_enabled: False\n"
        )

        config = read_config(str(project_root))

        assert config["memory_decay_enabled"] is False, (
            f"capital 'False' must coerce to False (default), got "
            f"{config['memory_decay_enabled']!r}"
        )
        captured = capsys.readouterr()
        assert re.search(r"ambiguous boolean", captured.err), (
            f"expected 'ambiguous boolean' stderr warning, got: "
            f"{captured.err!r}"
        )

    def test_iso_utc_raises_on_naive_datetime(self):
        """AC-3 (FR-1.3 / #00141).

        ``_iso_utc`` MUST raise ``ValueError`` for tz-naive inputs and
        return a Z-suffix string for tz-aware inputs.
        """
        # Naive datetime → ValueError.
        with pytest.raises(ValueError, match="timezone-aware"):
            maintenance._iso_utc(datetime(2026, 1, 1, 12, 0, 0))

        # Tz-aware datetime → expected Z-suffix string.
        result = maintenance._iso_utc(
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        )
        assert result == "2026-01-01T12:00:00Z"

    def test_influence_log_refuses_insecure_parent_dir_mode(
        self, tmp_path, monkeypatch
    ):
        """AC-7 (FR-1.7 / #00154).

        Parent directory with group/world-readable mode (0o755) MUST cause
        ``_emit_decay_diagnostic`` to decline the write (no log file
        created, no data leaked to a weakly-protected path).
        """
        # Build a parent dir with INSECURE mode 0o755.
        insecure_parent = tmp_path / "insecure"
        insecure_parent.mkdir(mode=0o755)
        # Explicitly chmod in case the umask masked bits we asked for.
        os.chmod(str(insecure_parent), 0o755)

        log_path = insecure_parent / "influence-debug.log"
        monkeypatch.setattr(maintenance, "INFLUENCE_DEBUG_LOG_PATH", log_path)

        diag = _make_diag()
        maintenance._emit_decay_diagnostic(diag)

        # File MUST NOT exist, or at minimum have zero bytes written.
        if log_path.exists():
            assert log_path.stat().st_size == 0, (
                f"insecure parent dir must not receive log writes, "
                f"but {log_path} has {log_path.stat().st_size} bytes"
            )

        # Tighten mode back down so pytest cleanup can remove the dir.
        os.chmod(str(insecure_parent), 0o700)


# ---------------------------------------------------------------------------
# Feature 089 Bundle E — Test-gap closure (AC-18, AC-19, AC-20, AC-26)
# ---------------------------------------------------------------------------


class TestFeature089BundleE:
    """Feature 089 Bundle E (#00160, #00161, #00162, #00168): direct coverage
    of the type-exact ``_coerce_bool`` ambiguity table, ``_iso_utc`` both
    branches, scan-limit zero-behavior contract, and ``_warn_unknown_keys``
    namespace-filter + dedup semantics.
    """

    # ---- AC-18 (#00160): _coerce_bool ambiguity parametrization ----

    @pytest.mark.parametrize("raw_value,expected", [
        # Ambiguous — fall back to default (=True used here to distinguish
        # the fallback from a legitimate False parse), plus warning.
        ("TRUE", "default"),       # capital accepted only by legacy frozenset
        (" true", "default"),      # leading space — type-exact rejects
        ("1.0", "default"),        # float-as-string — not bool
        ("yes", "default"),        # English truthy — not accepted
        ("01", "default"),         # leading zero int-as-string — ambiguous
        # Accepted values (empty string is treated as False by _coerce_bool).
        ("", False),
    ])
    def test_coerce_bool_ambiguous_variants_parameterized(
        self, raw_value, expected, capsys,
    ):
        """AC-18 (FR-1.1 / #00160). Type-exact ``_coerce_bool`` rejects every
        legacy-frozenset variant (``'TRUE'``, ``' true'``, ``'1.0'``, ``'yes'``,
        ``'01'``) and falls back to ``default`` with a one-line ``ambiguous
        boolean`` stderr warning.  Empty string is an accepted False literal
        (matching the production contract at ``config.py:78-79``).
        """
        from semantic_memory.config import _coerce_bool

        default_value = True  # distinct from False so fallback is observable
        result = _coerce_bool("memory_decay_enabled", raw_value, default_value)

        captured = capsys.readouterr()
        if expected == "default":
            assert result is default_value, (
                f"{raw_value!r} must fall back to default={default_value}, "
                f"got {result!r}"
            )
            assert "ambiguous boolean" in captured.err, (
                f"expected 'ambiguous boolean' warning for {raw_value!r}, "
                f"got stderr: {captured.err!r}"
            )
            assert "memory_decay_enabled" in captured.err
        else:
            # Expected is a concrete bool; no warning should be emitted.
            assert result is expected, (
                f"{raw_value!r} must coerce to {expected!r}, got {result!r}"
            )
            assert "ambiguous boolean" not in captured.err, (
                f"unexpected warning for accepted value {raw_value!r}: "
                f"{captured.err!r}"
            )

    # ---- AC-19 (#00161): _iso_utc both branches, direct ----

    def test_iso_utc_handles_both_branches_directly(self):
        """AC-19 (FR-3.2 / #00161). Directly exercise ``_iso_utc`` for:

        - tz-aware UTC input → straight format to ``Z``-suffix.
        - tz-aware non-UTC input → converts to UTC before formatting
          (so US/Eastern 12:00 stamps as 17:00 in winter; ZoneInfo returns
          standard-time offset for January 1).
        - tz-naive input → raises ``ValueError`` per FR-1.3.

        The helper now lives in ``semantic_memory._config_utils`` after
        Feature 089 FR-3.2 / AC-12 (#00148); we test it via the relocated
        module *and* through the ``maintenance._iso_utc`` re-export so both
        import paths remain guaranteed.
        """
        from zoneinfo import ZoneInfo
        from semantic_memory._config_utils import _iso_utc as _iso_utc_core

        # Path 1: tz-aware UTC → passes through unchanged (minus the astimezone).
        utc_input = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert _iso_utc_core(utc_input) == "2026-01-01T12:00:00Z"
        # Module-level re-export must agree with the canonical helper.
        assert maintenance._iso_utc(utc_input) == "2026-01-01T12:00:00Z"

        # Path 2: tz-aware non-UTC → astimezone(UTC) first.
        # US/Eastern on 2026-01-01 is EST (UTC-5), so 12:00 EST → 17:00 UTC.
        est_input = datetime(
            2026, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("US/Eastern")
        )
        assert _iso_utc_core(est_input) == "2026-01-01T17:00:00Z"

        # Path 3: tz-naive → ValueError (FR-1.3 security fix).
        with pytest.raises(ValueError, match="timezone-aware"):
            _iso_utc_core(datetime(2026, 1, 1, 12, 0, 0))
        # Re-export MUST propagate the same error (it is the same function).
        with pytest.raises(ValueError, match="timezone-aware"):
            maintenance._iso_utc(datetime(2026, 1, 1, 12, 0, 0))

    # ---- AC-20 (#00162): scan_limit=0 pinned behavior ----

    def test_scan_limit_zero_behavior_pinned(self, fresh_db, monkeypatch):
        """AC-20 (FR-1.2 / #00162). Pin the contract for
        ``memory_decay_scan_limit=0``:

        - Production path: the clamp ``(1000, 10_000_000)`` in
          ``decay_confidence`` (``maintenance.py:462``) raises the raw 0 to
          1000, so the SQL LIMIT never reaches 0 — ``_resolve_int_config``
          enforces the min.
        - Monkeypatched pass-through path: when the clamp is bypassed, 0
          reaches ``_select_candidates`` as ``LIMIT 0``, which returns zero
          rows → ``scanned == 0``.

        Whichever contract the production code pins is fine; this test
        exercises BOTH paths so a refactor cannot silently flip the
        behavior.
        """
        # Seed 3 stale-high rows so the candidate pool is non-empty.
        stale = _days_ago(31)
        for i in range(3):
            _seed_entry(
                fresh_db, entry_id=f"z-{i}", confidence="high",
                last_recalled_at=stale, created_at=stale,
            )

        # Path 1: production clamp kicks in — raw 0 clamped up to 1000.
        # With only 3 rows total, scanned is 3 (bounded by row count, not LIMIT).
        cfg_clamped = _enabled_config(memory_decay_scan_limit=0)
        result_clamped = maintenance.decay_confidence(
            fresh_db, cfg_clamped, now=NOW
        )
        assert "error" not in result_clamped, (
            f"production path unexpectedly errored: {result_clamped!r}"
        )
        # The clamp raised LIMIT to 1000 so all 3 rows scan through.
        assert result_clamped["scanned"] == 3, (
            f"expected 3 (clamped to 1000, bounded by row count), got "
            f"{result_clamped['scanned']}"
        )

        # Path 2: bypass the clamp via monkeypatch so raw 0 reaches SQL.
        def _pass_through(config, key, default, *, clamp=None, warned):
            if key == "memory_decay_scan_limit":
                return int(config.get(key, default))
            return default

        monkeypatch.setattr(
            maintenance, "_resolve_int_config", _pass_through,
        )
        cfg_raw = _enabled_config(memory_decay_scan_limit=0)
        result_raw = maintenance.decay_confidence(
            fresh_db, cfg_raw, now=NOW
        )
        assert "error" not in result_raw
        # LIMIT 0 returns no rows → scanned == 0.
        assert result_raw["scanned"] == 0, (
            f"expected 0 (LIMIT 0 returns nothing), got {result_raw['scanned']}"
        )

    # ---- AC-26 (#00168): _warn_unknown_keys namespace filter + dedup ----

    def test_warn_unknown_keys_namespace_filter_and_dedup(self, capsys):
        """AC-26 (FR-3.6 / #00168). Pin the ``_warn_unknown_keys`` contract:

        1. Off-namespace typos (no ``memory_`` / ``pd_`` prefix) are silently
           tolerated — forward-compat escape hatch.
        2. On-namespace typos emit a one-line stderr warning naming the key.
        3. Dedup behavior is currently NOT stateful — each invocation of
           ``_warn_unknown_keys`` re-emits the same warning for the same
           key.  This test pins that observable contract so a future switch
           to process-level dedup (e.g., via a module-level set) must update
           the pin deliberately.
        """
        from semantic_memory.config import _warn_unknown_keys

        # Case 1: off-namespace typo — no ``memory_``/``pd_`` prefix → silent.
        capsys.readouterr()
        _warn_unknown_keys({"memor_decay_enabled": True})
        captured_off = capsys.readouterr()
        assert captured_off.err == "", (
            f"off-namespace typo must not warn, got: {captured_off.err!r}"
        )

        # Case 2: on-namespace typo — warning names the typo exactly.
        capsys.readouterr()
        _warn_unknown_keys({"memory_decay_enabaled": True})
        captured_on = capsys.readouterr()
        assert "memory_decay_enabaled" in captured_on.err, (
            f"on-namespace typo must warn, got: {captured_on.err!r}"
        )
        assert captured_on.err.count("unknown key") == 1, (
            f"expected exactly 1 warning line, got: {captured_on.err!r}"
        )

        # Case 3: dedup pin — 3 calls with same typo.  Current production
        # implementation does NOT dedup across calls (each invocation
        # iterates the dict unconditionally).  Pin the observable count
        # so a future dedup refactor has to update this assertion.
        capsys.readouterr()
        cfg = {"memory_decay_enabaled": True}
        _warn_unknown_keys(cfg)
        _warn_unknown_keys(cfg)
        _warn_unknown_keys(cfg)
        captured_dedup = capsys.readouterr()
        warning_count = captured_dedup.err.count("unknown key")
        # Current contract: 3 warnings (no cross-call dedup).
        assert warning_count == 3, (
            f"Pinned: no cross-call dedup — expected 3 warnings for 3 calls, "
            f"got {warning_count}. Stderr: {captured_dedup.err!r}. "
            f"If you intentionally added dedup, update this pin."
        )
