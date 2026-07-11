#!/usr/bin/env python3
"""Seed a v2 entity-registry DB with realistic-scale synthetic census data
(feature 126, design D8 5b).

Bootstraps schema_v2 + events (+ any other registered DDL) into a target
directory and seeds ~533 entities across 7 workspaces with a full
`initialized` (+ phase) event stream per entity, so a future consumer
(127) has a realistic-scale v2 database to run project_meta against for
DB-direct-read benchmarking (compared against 5a's file-based reads).

ALL data is synthetic — no live repo content is read or copied. Entity
type_ids are SEQUENTIAL and deterministic (`feature:{i:04d}-{slug}`), so
they are collision-free by construction even though v2's `entities.type_id`
column carries no UNIQUE constraint (FR-4, schema_v2.py:49). Write API is
raw INSERTs on a connect_v2 connection for workspaces/entities (v2 has no
registration API until 122/123) and `events.append_event` for events.

Usage:
    python3 scripts/seed-census-db.py --target-dir /path/to/dir \
        [--entities 533] [--workspaces 7] [--seed 0x126]

Writes `v2.db` (+ WAL sidecars) into --target-dir. Deterministic:
`random.Random(seed)`, ONE instance for the whole run. design D8's "Seed
note": D6 (task 2's property test), 5a (bench-populated-read.sh), and 5b
(this script) each construct an INDEPENDENT random.Random(0x126) for their
own disjoint artifact — the shared literal is a convention, not a coupling.
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "plugins", "pd", "hooks", "lib"
))

from entity_registry import events  # noqa: E402 -- registers "events" DDL; must precede bootstrap_v2
from entity_registry import schema_v2  # noqa: E402
from entity_registry.uuid7 import generate_uuid7  # noqa: E402

DEFAULT_SEED = 0x126
DEFAULT_ENTITY_COUNT = 533
DEFAULT_WORKSPACE_COUNT = 7
_NOW = "2026-01-01T00:00:00Z"

# Census-proportioned lifecycle mix (design D8 5b: "kinds/phases/payload
# sizes at census proportions") — weights sum to 1.0, a defensible rough
# approximation of this project's own feature-status population (mostly
# completed, a working tail of active/planned, a small terminal-early
# residual). Order is significant only for readability.
_STATUS_WEIGHTS: list[tuple[str, float]] = [
    ("completed", 0.60),
    ("active", 0.15),
    ("planned", 0.15),
    ("abandoned", 0.05),
    ("archived", 0.05),
]

_PHASES = ["brainstorm", "spec", "design", "plan", "implement", "finish"]

_SLUG_WORDS = (
    "census", "synthetic", "seeded", "sample", "harness", "load",
    "bench", "fixture", "generated", "placeholder", "proxy", "data",
)


def _weighted_status(rng: random.Random) -> str:
    total = sum(weight for _, weight in _STATUS_WEIGHTS)
    pick = rng.uniform(0, total)
    running = 0.0
    for status, weight in _STATUS_WEIGHTS:
        running += weight
        if pick <= running:
            return status
    return _STATUS_WEIGHTS[-1][0]


def _slug(rng: random.Random, word_count: int = 3) -> str:
    return "-".join(rng.choice(_SLUG_WORDS) for _ in range(word_count))


def _seed_workspaces(conn, rng: random.Random, workspace_count: int) -> list[str]:
    workspace_uuids = []
    for i in range(workspace_count):
        workspace_uuid = generate_uuid7()
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, f"/synthetic/census-workspace-{i:02d}", _NOW, _NOW),
        )
        workspace_uuids.append(workspace_uuid)
    return workspace_uuids


def _seed_entity_row(conn, *, entity_uuid: str, workspace_uuid: str, type_id: str, slug: str) -> None:
    # kind="feature" (meta_projection's only supported kind, design D3
    # kind guard); type/lifecycle_class mirror the convention established
    # by test_meta_projection.py's own _seed_entity helper.
    conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
        "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entity_uuid, workspace_uuid, "feature", "feature", "artifact",
            type_id, f"Synthetic Census Feature {slug}", None, None,
            _NOW, _NOW, None,
        ),
    )


def _append_event_stream(conn, rng: random.Random, *, entity_uuid: str, status: str) -> None:
    """Append a synthetic initialized (+ phase) event stream for one
    entity, shaped by *status* (design D1 grammar; census-proportioned
    depth — not a literal reproduction of any real feature's history)."""
    events.append_event(
        conn, entity_uuid=entity_uuid, event_type="initialized", axis="lifecycle",
        to_value="planned", actor="seed-census-db", timestamp=_NOW,
        payload={"mode": rng.choice(["standard", "full"]), "branch": f"feature/{entity_uuid[:8]}"},
    )

    if status == "planned":
        return

    # Completed entities run the full pipeline; every other non-planned
    # status stops partway through a randomly-chosen phase depth.
    phase_count = len(_PHASES) if status == "completed" else rng.randint(1, len(_PHASES) - 1)

    for phase_index, phase in enumerate(_PHASES[:phase_count]):
        events.append_event(
            conn, entity_uuid=entity_uuid, event_type="phase_started", axis="pipeline",
            to_value=phase, actor="seed-census-db", timestamp=_NOW,
        )
        is_last_phase = phase_index == phase_count - 1
        leave_started_only = is_last_phase and status == "active"
        if not leave_started_only:
            events.append_event(
                conn, entity_uuid=entity_uuid, event_type="phase_completed", axis="pipeline",
                to_value=phase, actor="seed-census-db", timestamp=_NOW,
                payload={
                    "iterations": rng.randint(1, 3),
                    "reviewerNotes": _slug(rng, rng.randint(15, 60)),
                },
            )

    if status in ("completed", "abandoned", "archived"):
        events.append_event(
            conn, entity_uuid=entity_uuid, event_type=status, axis="lifecycle",
            to_value=status, actor="seed-census-db", timestamp=_NOW,
        )


def seed_census_db(target_dir: str, *, entity_count: int, workspace_count: int, seed: int) -> dict:
    """Bootstrap + seed a v2 DB under *target_dir*.

    Returns a summary dict: db_path, entities/events/workspaces row
    counts, and first_entity_uuid (any seeded entity always has an
    `initialized` event, so it always round-trips through project_meta).
    """
    os.makedirs(target_dir, exist_ok=True)
    db_path = os.path.join(target_dir, "v2.db")

    bootstrap_conn = schema_v2.bootstrap_v2(db_path)
    bootstrap_conn.close()

    conn = events.connect_v2(db_path)
    try:
        rng = random.Random(seed)
        first_entity_uuid = None

        # One explicit transaction for the whole seed run: append_event
        # "composes on conn.in_transaction" (events.py docstring) — inside
        # an already-open transaction it's a bare INSERT, so wrapping here
        # turns ~thousands of autocommitting writes into one commit.
        conn.execute("BEGIN IMMEDIATE")
        try:
            workspace_uuids = _seed_workspaces(conn, rng, workspace_count)

            for i in range(entity_count):
                workspace_uuid = rng.choice(workspace_uuids)
                entity_uuid = generate_uuid7()
                if first_entity_uuid is None:
                    first_entity_uuid = entity_uuid
                slug = _slug(rng)
                type_id = f"feature:{i:04d}-{slug}"
                status = _weighted_status(rng)

                _seed_entity_row(
                    conn, entity_uuid=entity_uuid, workspace_uuid=workspace_uuid,
                    type_id=type_id, slug=slug,
                )
                _append_event_stream(conn, rng, entity_uuid=entity_uuid, status=status)

            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

        entity_row_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        event_row_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        workspace_row_count = conn.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
    finally:
        conn.close()

    return {
        "db_path": db_path,
        "entities": entity_row_count,
        "events": event_row_count,
        "workspaces": workspace_row_count,
        "first_entity_uuid": first_entity_uuid,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-dir", required=True, help="directory to write v2.db into")
    parser.add_argument("--entities", type=int, default=DEFAULT_ENTITY_COUNT)
    parser.add_argument("--workspaces", type=int, default=DEFAULT_WORKSPACE_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    summary = seed_census_db(
        args.target_dir, entity_count=args.entities,
        workspace_count=args.workspaces, seed=args.seed,
    )
    print(
        f"seeded {summary['entities']} entities, {summary['events']} events, "
        f"{summary['workspaces']} workspaces -> {summary['db_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
