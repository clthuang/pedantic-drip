"""Tests for ``semantic_memory.refresh`` shared helper module (Feature 081).

Covers Phase 1 TDD tests:
- TestBuildRefreshQuery — AC-4a/b/c/d
- TestResolveIntConfig — AC-5 + bool/float rejection + dedup
- TestEmitRefreshDiagnostic — AC-8 diagnostic format + error flow
- TestSerializeEntries — AC-6 entry shape + AC-11 byte cap
- TestHybridRetrieve — AC-13 parity (deterministic ordering)

Test state conventions
----------------------
An autouse fixture (``reset_refresh_state``) resets module-level dedup
flags/sets in ``semantic_memory.refresh`` via ``monkeypatch.setattr`` so
teardown restores them automatically.  Tests that need to set config
values should pass a fresh ``dict`` explicitly rather than mutate any
module global — ``refresh.py`` takes config as a parameter.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# Ensure the mcp/ directory is importable so we can reuse
# ``_FixedSimilarityProvider`` from ``test_memory_server.py`` without
# duplicating the class.  From ``test_refresh.py`` the ancestry is:
#   parents[0]=semantic_memory, [1]=lib, [2]=hooks, [3]=pd, [4]=plugins,
#   [5]=repo root.  ``mcp`` lives as a sibling of ``hooks`` under ``pd``.
_MCP_DIR = Path(__file__).resolve().parents[3] / "mcp"
if str(_MCP_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_DIR))

from semantic_memory import refresh  # noqa: E402
from semantic_memory.database import MemoryDatabase  # noqa: E402


# ---------------------------------------------------------------------------
# Autouse fixture: reset module-level dedup state per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_refresh_state(monkeypatch):
    """Reset ``refresh``'s module-level dedup flags/sets before each test."""
    monkeypatch.setattr(refresh, "_slow_refresh_warned", False)
    monkeypatch.setattr(refresh, "_refresh_error_warned", False)
    monkeypatch.setattr(refresh, "_refresh_warned_fields", set())
    yield


# ---------------------------------------------------------------------------
# Scaffold sanity
# ---------------------------------------------------------------------------


def test_scaffold_imports():
    """Verify the module imports cleanly."""
    assert refresh is not None


# ---------------------------------------------------------------------------
# TestBuildRefreshQuery — AC-4a/b/c/d
# ---------------------------------------------------------------------------


class TestBuildRefreshQuery:
    def test_normal_slug_and_next_phase(self):
        # AC-4a: slug extract + next-phase lookup
        result = refresh.build_refresh_query(
            "feature:081-mid-session-memory-refresh-hoo", "specify"
        )
        assert result == "mid-session-memory-refresh-hoo design"

    def test_finish_terminal(self):
        # AC-4b: finish → "" → strip() removes trailing space
        result = refresh.build_refresh_query(
            "feature:081-mid-session-memory-refresh-hoo", "finish"
        )
        assert result == "mid-session-memory-refresh-hoo"

    def test_three_digit_id(self):
        # AC-4c
        result = refresh.build_refresh_query("feature:100-foo-bar", "design")
        assert result == "foo-bar create-plan"

    def test_regex_mismatch_returns_none(self):
        # AC-4d
        result = refresh.build_refresh_query("feature:weird-id", "specify")
        assert result is None


# ---------------------------------------------------------------------------
# TestResolveIntConfig — AC-5 + bool/float rejection + dedup
# ---------------------------------------------------------------------------


class TestResolveIntConfig:
    def test_int_passthrough(self):
        warned: set[str] = set()
        result = refresh._resolve_int_config(
            {"k": 7}, "k", 5, warned=warned
        )
        assert result == 7

    def test_string_parse_int(self):
        warned: set[str] = set()
        result = refresh._resolve_int_config(
            {"k": "12"}, "k", 5, warned=warned
        )
        assert result == 12

    def test_bool_rejected(self, capsys):
        warned: set[str] = set()
        # Python bool is int subclass; must reject BEFORE int branch.
        result = refresh._resolve_int_config(
            {"k": True}, "k", 5, warned=warned
        )
        assert result == 5
        captured = capsys.readouterr()
        assert "k" in captured.err or "True" in captured.err
        assert "k" in warned

    def test_float_rejected(self, capsys):
        warned: set[str] = set()
        # Int helper rejects floats like 5.7 (NOT an int).
        result = refresh._resolve_int_config(
            {"k": 5.7}, "k", 5, warned=warned
        )
        assert result == 5
        captured = capsys.readouterr()
        assert captured.err != ""
        assert "k" in warned

    def test_invalid_string_rejected(self, capsys):
        warned: set[str] = set()
        result = refresh._resolve_int_config(
            {"k": "bad"}, "k", 5, warned=warned
        )
        assert result == 5
        captured = capsys.readouterr()
        assert "k" in captured.err or "bad" in captured.err
        assert "k" in warned

    def test_clamp_above_max(self, capsys):
        warned: set[str] = set()
        result = refresh._resolve_int_config(
            {"k": 100}, "k", 5, clamp=(1, 20), warned=warned
        )
        assert result == 20
        # Clamping is silent (no warning).
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_clamp_below_min(self, capsys):
        warned: set[str] = set()
        result = refresh._resolve_int_config(
            {"k": 0}, "k", 5, clamp=(1, 20), warned=warned
        )
        assert result == 1
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warning_deduped_across_calls(self, capsys):
        warned: set[str] = set()
        # Two successive malformed calls with the same key → only one warning.
        refresh._resolve_int_config({"k": True}, "k", 5, warned=warned)
        refresh._resolve_int_config({"k": True}, "k", 5, warned=warned)
        captured = capsys.readouterr()
        # Exactly one warning line in stderr (per-key dedup).
        lines = [ln for ln in captured.err.splitlines() if ln.strip()]
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# TestEmitRefreshDiagnostic — AC-8 log line format + error flow
# ---------------------------------------------------------------------------


class TestEmitRefreshDiagnostic:
    def test_emits_one_line_when_called(self, tmp_path, monkeypatch):
        log = tmp_path / "log.jsonl"
        monkeypatch.setattr(refresh, "INFLUENCE_DEBUG_LOG_PATH", log)

        refresh._emit_refresh_diagnostic(
            feature_type_id="feature:081-mid-session-memory-refresh-hoo",
            completed_phase="specify",
            query="mid-session-memory-refresh-hoo design",
            entry_count=3,
            elapsed_ms=42,
        )

        assert log.exists()
        content = log.read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) == 1
        # Event name present
        assert re.search(r'"event":\s*"memory_refresh"', lines[0])
        # elapsed_ms field is present
        assert '"elapsed_ms"' in lines[0]
        # Parseable JSON
        rec = json.loads(lines[0])
        assert rec["event"] == "memory_refresh"
        assert rec["elapsed_ms"] == 42
        assert rec["entry_count"] == 3
        assert rec["feature_type_id"] == "feature:081-mid-session-memory-refresh-hoo"
        assert rec["completed_phase"] == "specify"
        assert rec["query"] == "mid-session-memory-refresh-hoo design"

    def test_missing_parent_dir_created(self, tmp_path, monkeypatch):
        log = tmp_path / "nested" / "deep" / "log.jsonl"
        monkeypatch.setattr(refresh, "INFLUENCE_DEBUG_LOG_PATH", log)

        refresh._emit_refresh_diagnostic(
            feature_type_id="feature:081-x",
            completed_phase="specify",
            query="x design",
            entry_count=1,
            elapsed_ms=10,
        )

        assert log.exists()

    def test_write_failure_warns_once_then_silent(self, tmp_path, monkeypatch, capsys):
        # Force a write failure by making the target path a directory.
        bad_path = tmp_path / "logdir"
        bad_path.mkdir()
        monkeypatch.setattr(refresh, "INFLUENCE_DEBUG_LOG_PATH", bad_path)

        # First call → one warning
        refresh._emit_refresh_diagnostic(
            feature_type_id="feature:081-x",
            completed_phase="specify",
            query="x design",
            entry_count=1,
            elapsed_ms=10,
        )
        # Second call → silent
        refresh._emit_refresh_diagnostic(
            feature_type_id="feature:081-x",
            completed_phase="specify",
            query="x design",
            entry_count=1,
            elapsed_ms=10,
        )

        captured = capsys.readouterr()
        # Exactly one warning line in stderr (flag-deduped)
        warning_lines = [
            ln for ln in captured.err.splitlines() if ln.strip()
        ]
        assert len(warning_lines) == 1


# ---------------------------------------------------------------------------
# TestSerializeEntries — AC-6 entry shape + AC-11 byte cap
# ---------------------------------------------------------------------------


class TestSerializeEntries:
    def test_exact_three_keys(self):
        # AC-6: entry shape has exactly {name, category, description}
        entries = [
            {
                "name": "Pattern A",
                "category": "patterns",
                "description": "Short desc",
                "confidence": "high",
                "influence_count": 5,
                "observation_count": 10,
                "references": ["foo.md"],
                "final_score": 0.9,
            }
        ]
        out = refresh._serialize_entries(entries)
        assert len(out) == 1
        assert set(out[0].keys()) == {"name", "category", "description"}
        assert out[0]["name"] == "Pattern A"
        assert out[0]["category"] == "patterns"
        assert out[0]["description"] == "Short desc"

    def test_description_truncated_240_chars(self):
        entry = {
            "name": "Long",
            "category": "patterns",
            "description": "x" * 500,
        }
        out = refresh._serialize_entries([entry])
        assert len(out) == 1
        assert len(out[0]["description"]) == 240

    def test_byte_cap_drops_from_end(self):
        # AC-11: 10 entries each with 500-char descriptions; total exceeds
        # 2000 bytes → final list is truncated from the end.
        entries = [
            {
                "name": f"Entry {i:02d}",
                "category": "patterns",
                "description": "x" * 500,
            }
            for i in range(10)
        ]
        out = refresh._serialize_entries(entries)
        # Each description truncated to 240 chars
        for e in out:
            assert len(e["description"]) <= 240
        # Final JSON byte size within budget
        serialized = json.dumps(out, separators=(",", ":"))
        assert len(serialized.encode("utf-8")) <= 2000
        # Entries may be <10 after drop-from-end.
        assert len(out) <= 10

    def test_empty_input_returns_empty_list(self):
        assert refresh._serialize_entries([]) == []


# ---------------------------------------------------------------------------
# TestHybridRetrieve — AC-13 parity (deterministic ordering)
# ---------------------------------------------------------------------------


class TestHybridRetrieve:
    def test_ranking_order_deterministic_with_seeded_provider(self):
        """AC-13: hybrid_retrieve returns a stable ordering given identical inputs.

        Use ``_FixedSimilarityProvider`` from ``test_memory_server.py`` (import
        via sys.path insert; do NOT duplicate the class).  Seed a MemoryDatabase
        with two entries, then call hybrid_retrieve twice — assert identical
        output ordering (parity).
        """
        # Import here (after sys.path insert at module top) to avoid side
        # effects at collection time.
        import numpy as np
        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)

            # Seed two entries with known embeddings (unit vector on axis 0).
            for i, (name, cat) in enumerate(
                [("Alpha", "patterns"), ("Beta", "heuristics")]
            ):
                emb = np.zeros(768, dtype=np.float32)
                emb[0] = 1.0
                entry = {
                    "id": f"entry-{i}",
                    "name": name,
                    "description": f"Description for {name}",
                    "category": cat,
                    "source": "manual",
                    "confidence": "medium",
                    "keywords": "[]",
                    "source_project": "/tmp",
                    "source_hash": f"000{i}",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
                db.upsert_entry(entry)
                db.update_embedding(f"entry-{i}", emb.tobytes())

            config: dict = {}
            a = refresh.hybrid_retrieve(db, provider, config, "alpha beta", 5)
            b = refresh.hybrid_retrieve(db, provider, config, "alpha beta", 5)

            # Parity: two calls with identical inputs yield identical results.
            assert [e["id"] for e in a] == [e["id"] for e in b]
            # All seeded entries returned (both match vector strongly).
            assert len(a) == 2
        finally:
            db.close()

    def test_ac13_parity_hybrid_retrieve_is_deterministic(self):
        """AC-13 characterization: hybrid_retrieve is structurally deterministic.

        Calls ``hybrid_retrieve`` twice with identical inputs and asserts the
        two returned lists are equal.  Guards against future regressions in
        the shared retrieval callable — if the Phase 2 refactor of
        ``_process_search_memory`` ever diverges from this function's
        behavior, this test pins the contract.

        Implementation detail: ``RankingEngine.rank`` internally calls
        ``datetime.now(timezone.utc)`` for recency-decay computations, so
        back-to-back calls can produce slightly different ``final_score``
        values in the last few decimal places.  We freeze the clock via
        ``monkeypatch`` on ``ranking.datetime`` so both calls see the same
        "now" — giving us the strongest-possible bitwise list equality.
        """
        import numpy as np
        from datetime import datetime, timezone

        from semantic_memory import ranking as ranking_module
        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        # Freeze RankingEngine's notion of "now" so both calls use the same
        # time for recency decay — making final_score bitwise-identical.
        frozen_now = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

        class _FrozenDateTime:
            @classmethod
            def now(cls, tz=None):
                return frozen_now

            @staticmethod
            def fromisoformat(s):
                return datetime.fromisoformat(s)

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)

            # Seed 3 entries so the list has enough shape for a meaningful
            # equality check across calls.
            for i, (name, cat) in enumerate([
                ("Gamma", "patterns"),
                ("Delta", "heuristics"),
                ("Epsilon", "anti-patterns"),
            ]):
                emb = np.zeros(768, dtype=np.float32)
                emb[0] = 1.0
                entry = {
                    "id": f"parity-{i}",
                    "name": name,
                    "description": f"Description for {name}",
                    "category": cat,
                    "source": "manual",
                    "confidence": "medium",
                    "keywords": "[]",
                    "source_project": "/tmp",
                    "source_hash": f"parity-hash-{i}",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
                db.upsert_entry(entry)
                db.update_embedding(f"parity-{i}", emb.tobytes())

            config: dict = {}

            # Monkeypatch ranking.datetime for both calls so recency-decay uses
            # the same "now" — makes score comparison bitwise-stable.
            import pytest
            mp = pytest.MonkeyPatch()
            try:
                mp.setattr(ranking_module, "datetime", _FrozenDateTime)
                first = refresh.hybrid_retrieve(
                    db, provider, config, "gamma delta", 10
                )
                second = refresh.hybrid_retrieve(
                    db, provider, config, "gamma delta", 10
                )
            finally:
                mp.undo()

            # Structural parity: ids + order identical (primary guarantee).
            assert [e["id"] for e in first] == [e["id"] for e in second]
            # Full field-level equality with frozen clock (strongest guard).
            assert first == second
            # Sanity: we actually got results back (not an empty parity check).
            assert len(first) == 3
        finally:
            db.close()


# ---------------------------------------------------------------------------
# TestRefreshMemoryDigest — AC-1/3/7/10/11 public entry tests
# ---------------------------------------------------------------------------


def _seed_refresh_entry(
    db: MemoryDatabase,
    entry_id: str,
    name: str,
    category: str,
    confidence: str,
    description: str = "A workflow helper entry",
) -> None:
    """Seed a single entry with a unit-vector embedding on axis 0."""
    import numpy as np
    emb = np.zeros(768, dtype=np.float32)
    emb[0] = 1.0
    entry = {
        "id": entry_id,
        "name": name,
        "description": description,
        "category": category,
        "source": "manual",
        "confidence": confidence,
        "keywords": "[]",
        "source_project": "/tmp",
        "source_hash": f"hash-{entry_id}",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    db.upsert_entry(entry)
    db.update_embedding(entry_id, emb.tobytes())


class TestRefreshMemoryDigest:
    def test_ac1_field_shape(self):
        """AC-1: provider + 3 medium/high entries → dict with 3 keys per entry."""
        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)

            for i, (name, cat, conf) in enumerate([
                ("Alpha", "patterns", "high"),
                ("Beta", "heuristics", "medium"),
                ("Gamma", "anti-patterns", "high"),
            ]):
                _seed_refresh_entry(db, f"ac1-{i}", name, cat, conf)

            result = refresh.refresh_memory_digest(
                db, provider, "workflow", 5, config={}
            )

            assert isinstance(result, dict)
            assert set(result.keys()) == {"query", "count", "entries"}
            assert result["query"] == "workflow"
            assert result["count"] == len(result["entries"])
            assert result["count"] == 3
            for entry in result["entries"]:
                assert set(entry.keys()) == {"name", "category", "description"}
        finally:
            db.close()

    def test_ac3_provider_none_returns_none(self):
        """AC-3: provider=None → returns None (deterministic, no BM25 fallback)."""
        db = MemoryDatabase(":memory:")
        try:
            # Seed an entry so DB is not empty — still expect None because
            # no provider means vector retrieval is unavailable and the
            # deterministic contract omits the field.
            _seed_refresh_entry(db, "none-0", "X", "patterns", "high")

            result = refresh.refresh_memory_digest(
                db, None, "workflow", 5, config={}
            )

            assert result is None
        finally:
            db.close()

    def test_ac7_confidence_filter(self):
        """AC-7: low-confidence entries are filtered out post-rank."""
        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)

            # One of each confidence; all match the query equally.
            _seed_refresh_entry(db, "conf-low", "LowOne", "patterns", "low")
            _seed_refresh_entry(db, "conf-med", "MedOne", "patterns", "medium")
            _seed_refresh_entry(db, "conf-high", "HighOne", "patterns", "high")

            result = refresh.refresh_memory_digest(
                db, provider, "workflow", 10, config={}
            )

            assert result is not None
            # low was filtered; only medium + high remain.
            assert result["count"] == 2
            names = {e["name"] for e in result["entries"]}
            assert names == {"MedOne", "HighOne"}
        finally:
            db.close()

    def test_ac11_byte_cap_end_to_end(self):
        """AC-11: 10 entries × 500-char descriptions → ≤10 entries, ≤240-char desc, ≤2000 JSON bytes."""
        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)

            # 10 medium-confidence entries, each with a 500-char description
            # so the byte-cap path actually activates.
            for i in range(10):
                _seed_refresh_entry(
                    db,
                    f"bc-{i:02d}",
                    f"Entry{i:02d}",
                    "patterns",
                    "medium",
                    description="x" * 500,
                )

            result = refresh.refresh_memory_digest(
                db, provider, "workflow", 10, config={}
            )

            assert result is not None
            # count reflects post-trim list
            assert result["count"] == len(result["entries"])
            assert result["count"] <= 10
            # Per-entry description cap enforced
            for e in result["entries"]:
                assert len(e["description"]) <= 240
            # Total serialized JSON of entries ≤ 2000 bytes
            serialized = json.dumps(
                result["entries"], separators=(",", ":")
            )
            assert len(serialized.encode("utf-8")) <= 2000
        finally:
            db.close()

    def test_ac10_slow_retrieval_warns_once_field_still_present(
        self, monkeypatch, capsys
    ):
        """AC-10: >500ms retrieval → one stderr warning, field still present,
        second slow call silent."""
        import time

        from test_memory_server import _FixedSimilarityProvider  # type: ignore

        db = MemoryDatabase(":memory:")
        try:
            provider = _FixedSimilarityProvider(similarity=0.8)
            _seed_refresh_entry(db, "slow-0", "SlowOne", "patterns", "high")

            # Monkeypatch the hybrid_retrieve call inside refresh_memory_digest
            # with a fake that sleeps 600ms and then delegates to the real
            # function (so we still get a non-empty result to serialize).
            real_hybrid = refresh.hybrid_retrieve

            def slow_hybrid(*args, **kwargs):
                time.sleep(0.6)
                return real_hybrid(*args, **kwargs)

            monkeypatch.setattr(refresh, "hybrid_retrieve", slow_hybrid)

            # Call twice — each takes ≥600ms.
            first = refresh.refresh_memory_digest(
                db, provider, "workflow", 5, config={}
            )
            second = refresh.refresh_memory_digest(
                db, provider, "workflow", 5, config={}
            )

            # (a) Both calls return a dict — latency is observability-only,
            # not pre-emption.  Field is still delivered.
            assert first is not None
            assert "memory_refresh" not in first  # it's the digest itself
            assert set(first.keys()) == {"query", "count", "entries"}
            assert second is not None
            assert set(second.keys()) == {"query", "count", "entries"}

            # (b) + (c) Exactly one matching stderr line (dedup via
            # module-level _slow_refresh_warned).
            captured = capsys.readouterr()
            pattern = re.compile(
                r"\[workflow-state\] memory_refresh took \d+ms \(>500ms budget\)"
            )
            matches = [
                ln
                for ln in captured.err.splitlines()
                if pattern.search(ln)
            ]
            assert len(matches) == 1
        finally:
            db.close()
