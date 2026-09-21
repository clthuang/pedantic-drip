"""Tests for the clean-break selector (B5) and high-water sweep (B4)."""
from __future__ import annotations

import sqlite3

import pytest

from entity_registry.clean_break import (
    establish_high_water,
    group_by_workspace_kind_status,
    live_rows_outside,
    parse_legacy_seq,
    select_legacy_entities,
)


def make_conn(entities=(), display=(), sequences=(), tags=()):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE workspaces (uuid TEXT PRIMARY KEY, project_root TEXT);
        CREATE TABLE entities (uuid TEXT PRIMARY KEY, workspace_uuid TEXT,
                               kind TEXT, entity_id TEXT, status TEXT, name TEXT,
                               is_legacy INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE entity_display (uuid TEXT PRIMARY KEY, seq INTEGER, slug TEXT);
        CREATE TABLE sequences (workspace_uuid TEXT, entity_type TEXT, next_val INTEGER);
        CREATE TABLE entity_tags (entity_uuid TEXT, tag TEXT);
    """)
    seen = set()
    with_display = {d[0] for d in display}
    for (u, ws, kind, eid, status) in entities:
        if ws not in seen:
            c.execute("INSERT INTO workspaces VALUES (?,?)", (ws, f"/repo/{ws}"))
            seen.add(ws)
        # Mirrors v2 migration 4's one-time conversion: absence of a display
        # row becomes a STATED flag. After that point the two can diverge,
        # and is_legacy is the truth — see
        # test_display_less_but_not_legacy_is_a_bug_not_history.
        c.execute("INSERT INTO entities VALUES (?,?,?,?,?,?,?)",
                  (u, ws, kind, eid, status, eid, 0 if u in with_display else 1))
    c.executemany("INSERT INTO entity_display VALUES (?,?,?)", display)
    c.executemany("INSERT INTO sequences VALUES (?,?,?)", sequences)
    c.executemany("INSERT INTO entity_tags VALUES (?,?)", tags)
    return c


def counters(conn):
    return {(r["workspace_uuid"], r["entity_type"]): r["next_val"]
            for r in conn.execute("SELECT * FROM sequences")}


# ---------------------------------------------------------------------------
# The sanctioned legacy parse
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind,eid,expected", [
    ("project",    "P004-entity-db-redesign", 4),    # the original root cause
    ("project",    "P001",                    1),
    ("project",    "001-owg-v0-8",            1),    # prefix-free shape
    ("feature",    "134-workflow-rebuild",    134),
    ("backlog",    "00081",                   81),
    ("backlog",    "278-entity-rename",       278),
    ("brainstorm", "20260326-030832-slug",    None), # timestamp, not a sequence
    ("feature",    "20260326-030832-slug",    None), # date-shaped whatever the kind
    ("feature",    "unnamed-b43fd0f1",        None), # carries no sequence
    ("feature",    "",                        None),
])
def test_parse_legacy_seq(kind, eid, expected):
    assert parse_legacy_seq(kind, eid) == expected


def test_unparseable_id_is_none_not_zero():
    """0 and None must not collapse.

    _display_number returned 0 for an unparseable id, so an unparseable id
    contributed a floor of 1 and could lower a counter. None means 'carries
    no sequence' and contributes nothing.
    """
    assert parse_legacy_seq("feature", "unnamed-b43fd0f1") is None
    assert parse_legacy_seq("feature", "0-zero") == 0


# ---------------------------------------------------------------------------
# B5 — selector
# ---------------------------------------------------------------------------

class TestSelectLegacyEntities:
    def test_selects_exactly_the_rows_without_a_display_row(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "001-a", "active"),
                      ("u2", "ws-a", "feature", "002-b", "completed"),
                      ("u3", "ws-a", "backlog", "00059", "open")],
            display=[("u1", 1, "a")],
        )
        got = {r.entity_id for r in select_legacy_entities(conn)}
        assert got == {"002-b", "00059"}

    def test_display_less_but_not_legacy_is_a_bug_not_history(self):
        """The distinction the absence-based form could not express.

        A non-strict write creates an entity with no display row. Under the
        old LEFT-JOIN-IS-NULL rule that entity was indistinguishable from a
        genuine pre-structural row, so the clean break would have swept up
        a live bug as if it were history. is_legacy states which is which.
        """
        conn = make_conn(entities=[("u1", "ws-a", "feature", "007-fresh", "active")])
        conn.execute("UPDATE entities SET is_legacy = 0 WHERE uuid = 'u1'")
        assert conn.execute(
            "SELECT COUNT(*) FROM entities e LEFT JOIN entity_display d "
            "ON d.uuid = e.uuid WHERE d.uuid IS NULL"
        ).fetchone()[0] == 1, "fixture precondition: it has no display row"
        assert select_legacy_entities(conn) == []

    def test_marker_tag_makes_it_idempotent(self):
        """After the break every selected row carries the tag, so it returns 0."""
        conn = make_conn(
            entities=[("u1", "ws-a", "backlog", "00059", "open")],
            tags=[("u1", "legacy-archived-2026-09")],
        )
        assert len(select_legacy_entities(conn)) == 1          # no marker supplied
        assert select_legacy_entities(conn, marker_tag="legacy-archived-2026-09") == []

    def test_status_cannot_be_the_discriminator(self):
        """Already-terminal rows are still legacy; terminal status proves nothing."""
        conn = make_conn(entities=[("u1", "ws-a", "backlog", "00059", "dropped")])
        assert len(select_legacy_entities(conn)) == 1

    def test_live_rows_outside_the_invoking_workspace_are_surfaced(self):
        conn = make_conn(entities=[
            ("u1", "ws-a", "project", "P001", "active"),
            ("u2", "ws-b", "project", "P001", "active"),     # another repo, live
            ("u3", "ws-b", "backlog", "00010", "dropped"),   # another repo, finished
        ])
        rows = select_legacy_entities(conn)
        outside = live_rows_outside(rows, "ws-a")
        assert [r.uuid for r in outside] == ["u2"]

    def test_grouping_reports_workspace_kind_and_status(self):
        conn = make_conn(entities=[
            ("u1", "ws-a", "backlog", "00001", "dropped"),
            ("u2", "ws-a", "backlog", "00002", "dropped"),
            ("u3", "ws-a", "project", "P001", "active"),
        ])
        g = group_by_workspace_kind_status(select_legacy_entities(conn))
        assert g[("/repo/ws-a", "backlog", "dropped")] == 2
        assert g[("/repo/ws-a", "project", "active")] == 1

    def test_dropped_and_completed_are_not_live(self):
        """'live' is open/active/planned/NULL — not TERMINAL_STATUSES' complement."""
        conn = make_conn(entities=[
            ("u1", "ws-a", "backlog", "00001", "dropped"),
            ("u2", "ws-a", "backlog", "00002", "completed"),
            ("u3", "ws-a", "backlog", "00003", None),
        ])
        live = [r.entity_id for r in select_legacy_entities(conn) if r.is_live]
        assert live == ["00003"]


# ---------------------------------------------------------------------------
# B4 — high-water sweep
# ---------------------------------------------------------------------------

class TestEstablishHighWater:
    def test_raises_every_bucket_from_a_forced_floor_of_one(self):
        """Non-vacuity: a no-op passes on 17 of 19 live buckets.

        Forcing every counter to 1 makes all of them discriminate.
        """
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "134-x", "completed"),
                      ("u2", "ws-a", "project", "P004-y", "active"),
                      ("u3", "ws-b", "backlog", "00278", "open")],
            sequences=[("ws-a", "feature", 1), ("ws-a", "project", 1), ("ws-b", "backlog", 1)],
        )
        establish_high_water(conn)
        assert counters(conn) == {
            ("ws-a", "feature"): 135,
            ("ws-a", "project"): 5,      # P004 parses despite the slug suffix
            ("ws-b", "backlog"): 279,
        }

    def test_stored_counter_is_a_floor_not_an_override(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "003-x", "active")],
            sequences=[("ws-a", "feature", 99)],
        )
        establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 99

    def test_counter_only_bucket_survives(self):
        conn = make_conn(entities=[], sequences=[("ws-a", "feature", 42)])
        establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 42

    def test_an_allocation_between_two_runs_is_not_undone(self):
        """The case that separates max() from assignment.

        Back-to-back runs are identical under both. Only an intervening
        allocation reveals assignment lowering the counter below numbers
        already issued.
        """
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "003-x", "active")],
            sequences=[("ws-a", "feature", 4)],
        )
        first = establish_high_water(conn)
        conn.execute("UPDATE sequences SET next_val = 7 WHERE entity_type = 'feature'")
        second = establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 7
        assert second[("ws-a", "feature")] == 7
        assert first[("ws-a", "feature")] == 4

    def test_brainstorm_is_excluded_from_the_sequence_model(self):
        """Its identity is a timestamp; no path allocates from this counter."""
        conn = make_conn(
            entities=[("u1", "ws-a", "brainstorm", "20260711-120000-x", None)],
            sequences=[("ws-a", "brainstorm", 20260711)],
        )
        establish_high_water(conn)
        assert counters(conn)[("ws-a", "brainstorm")] == 20260711

    def test_unparseable_ids_never_lower_a_counter(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "unnamed-b43fd0f1", None)],
            sequences=[("ws-a", "feature", 57)],
        )
        establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 57

    def test_display_rows_contribute_a_floor(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "opaque", "active")],
            display=[("u1", 88, "slug")],
            sequences=[("ws-a", "feature", 2)],
        )
        establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 89

    def test_returns_every_bucket_in_entities_union_sequences(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "001-x", "active")],
            sequences=[("ws-b", "backlog", 5)],
        )
        result = establish_high_water(conn)
        assert set(result) == {("ws-a", "feature"), ("ws-b", "backlog")}

    def test_rerun_without_an_allocation_changes_nothing(self):
        conn = make_conn(
            entities=[("u1", "ws-a", "feature", "010-x", "active")],
            sequences=[("ws-a", "feature", 3)],
        )
        assert establish_high_water(conn) == establish_high_water(conn)
        assert counters(conn)[("ws-a", "feature")] == 11
