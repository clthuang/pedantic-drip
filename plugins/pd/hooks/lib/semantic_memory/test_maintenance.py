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
import re
import sqlite3
from datetime import MAXYEAR, datetime, timedelta, timezone

import pytest

from semantic_memory import maintenance
from semantic_memory.database import MemoryDatabase


@pytest.fixture(autouse=True)
def reset_decay_state(monkeypatch, tmp_path):
    """Reset all module-globals + redirect INFLUENCE_DEBUG_LOG_PATH.

    MUST use ``monkeypatch.setattr`` (not ``from maintenance import ...`` +
    reassign): bool is immutable, and ``from X import Y`` creates a local
    binding to the same object rather than a live reference — setattr is
    the only way to mutate the module namespace reliably.
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
    yield
    # monkeypatch auto-restores on teardown


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
    directly. Uses raw INSERT so tests can set confidence/source/timestamps
    outside upsert_entry's normalization path (and to bypass the
    observation_count++ on-conflict behaviour).

    Constraint note: `source` is CHECK-constrained to ('retro',
    'session-capture', 'manual', 'import'); default is 'session-capture'
    for the non-import path. `source_project` and `source_hash` are NOT
    NULL so both must be supplied.
    """
    db._conn.execute(
        "INSERT INTO entries (id, name, description, category, keywords, "
        "source, source_project, source_hash, confidence, recall_count, "
        "last_recalled_at, created_at, updated_at, observation_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            f"name-{entry_id}",
            "desc",
            "patterns",
            json.dumps(["k"]),
            source,
            "/tmp/test-project",
            "0" * 16,
            confidence,
            1 if last_recalled_at else 0,
            last_recalled_at,
            created_at,
            created_at,
            1,
        ),
    )
    db._conn.commit()


@pytest.fixture
def fresh_db():
    db = MemoryDatabase(":memory:")
    yield db
    db.close()


class TestSelectCandidates:
    """Task 1.11 / 1.12 — design I-2 (single SELECT + Python partition)."""

    def test_partitions_six_entries_across_all_buckets(self, fresh_db):
        NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
        now_iso = NOW.isoformat()
        high_cutoff = (NOW - timedelta(days=30)).isoformat()
        med_cutoff = (NOW - timedelta(days=60)).isoformat()
        grace_cutoff = (NOW - timedelta(days=14)).isoformat()

        stale_high_ts = (NOW - timedelta(days=100)).isoformat()
        stale_med_ts = (NOW - timedelta(days=100)).isoformat()
        fresh_in_grace_ts = (NOW - timedelta(days=10)).isoformat()  # within grace
        past_grace_ts = (NOW - timedelta(days=80)).isoformat()  # past 14d + past 60d

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


NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    # Feature 088 FR-3.1: Z-suffix UTC format (matches production
    # ``maintenance._iso_utc`` so tests that assert ``updated_at == _iso(NOW)``
    # compare against the same format ``decay_confidence`` now writes).
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_ago(days: float, *, base: datetime = NOW) -> str:
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
    row = db._conn.execute(
        "SELECT id, confidence, updated_at, last_recalled_at, source "
        "FROM entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    assert row is not None, f"entry {entry_id} not found"
    return dict(row)


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
        # 0 → clamped to 1.  But 0 is a VALID int, so NO warning is emitted
        # (clamp is silent by design per spec FR-3).  See design I-3 docstring.
        #
        # However, seeding with last_recalled_at < NOW - 1 day makes the entry
        # stale after clamp.  Use 2 days stale so the clamped threshold of 1
        # triggers decay.
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
        # Clamp 0 → 1 is silent; decay still fires.
        assert result["demoted_high_to_medium"] == 1

    def test_ac11b_high_threshold_overflow_clamped_to_365(self, fresh_db):
        # 500 → clamped to 365.  Entry stale 400 days should still demote.
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

    def test_ac11c_grace_period_negative_clamped_to_zero(self, fresh_db):
        """AC-11c: grace=-5 clamped to 0 → never-recalled rows past any age decay."""
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
        fresh_db._conn.execute(
            "UPDATE entries SET observation_count = ? WHERE id = ?",
            (4, "e1"),
        )
        fresh_db._conn.commit()

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
    """
    db._conn.executemany(
        "INSERT INTO entries (id, name, description, category, keywords, "
        "source, source_project, source_hash, confidence, recall_count, "
        "last_recalled_at, created_at, updated_at, observation_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    db._conn.commit()


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

    def test_ac31_threshold_equality_edge(self, fresh_db):
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
        count_medium = fresh_db._conn.execute(
            "SELECT COUNT(*) FROM entries WHERE confidence = 'medium'"
        ).fetchone()[0]
        assert count_medium == 2000


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
        fresh_db._conn.execute(
            "UPDATE entries SET last_recalled_at = ?, updated_at = ? "
            "WHERE id = ?",
            (stale, stale, "stale"),
        )
        fresh_db._conn.commit()

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
            fresh_db._conn.execute(
                "UPDATE entries SET last_recalled_at = ?, updated_at = ? "
                "WHERE id = ?",
                (fresh_ts, fresh_ts, f"fresh-{i}"),
            )
            fresh_db._conn.commit()

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
            row = verify_db._conn.execute(
                "SELECT confidence, updated_at FROM entries WHERE id = ?",
                ("e1",),
            ).fetchone()
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
