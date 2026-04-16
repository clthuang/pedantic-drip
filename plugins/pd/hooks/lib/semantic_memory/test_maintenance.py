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
from datetime import datetime, timedelta, timezone

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

        result = maintenance._select_candidates(
            fresh_db,
            high_cutoff=high_cutoff,
            med_cutoff=med_cutoff,
            grace_cutoff=grace_cutoff,
            now_iso=now_iso,
        )

        assert result["import_count"] == 1
        assert result["floor_count"] == 1
        assert result["grace_count"] == 1
        assert sorted(result["high_ids"]) == ["e5-high-stale"]
        assert sorted(result["medium_ids"]) == [
            "e4-grace-past-medium",
            "e6-medium-stale",
        ]
