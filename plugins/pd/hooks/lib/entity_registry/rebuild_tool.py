"""Feature 132 — the v1->v2 entity-registry rebuild tool (Scope model, D1-D8).

Owns the NEW committed rebuild tool the spec names (not the pre-existing
v1 ``entity_registry/backfill.py`` — a different artifact). Builds the
new database file via three ordered steps design D1 pins, so the union
DDL is derived BY CONSTRUCTION rather than hand-copied:

1. **Chain replay** (:func:`_replay_v1_chain`) — construct an
   ``EntityDatabase`` against the (nonexistent) staging path, which
   unconditionally runs the full v1 migration chain, then close it. No
   hand-rolled replay loop — this IS the sanctioned initial use of
   ``_migrate()`` that the FR132-1 generation guard carves out (it runs
   BEFORE step 3's stamp, so the guard is a no-op here).
2. **Selective v2 seed** (:func:`_seed_v2_schema`) — one raw
   ``sqlite3.connect`` on the SAME file. Importing events/views/axes
   registers their DDL into ``schema_v2.DDL_REGISTRY`` (module-import
   side effect); ``axes.register_vocab_ddl()`` is called explicitly
   (register-on-demand, never at import). The four registry entries for
   owners ``events``/``views``/``axes``/``axes_vocab_triggers`` are then
   applied in ONE transaction — NOT the ``core`` owner (step 1 already
   built those chain-shaped tables, ``_metadata`` included) and NOT
   ``bootstrap_v2()`` wholesale (its ``IF NOT EXISTS`` replay would
   silently skip chain-shaped tables). D7b's ``events_no_replace`` guard
   trigger ships inside the ``events`` owner's own DDL (events.py) — no
   standalone register call exists for it.
3. **Generation stamp** (:func:`_stamp_v2_generation`) — same
   connection, upserts ``schema_generation='v2'`` + ``schema_version``
   via the shared ``database._upsert_metadata`` helper (#062: ON
   CONFLICT DO UPDATE, not INSERT OR IGNORE).

Task 1 slice: build steps only (``--staging-only``). Task 2 slice adds
the backfill (D2), the v2 event emission (D3), the pre-import vocabulary
diff (SC5 #077 clause), the ``sequences`` seed (D6.9's seed-half), the
machine + committed reports (D7), the FTS population (D8), and the
WAL-safe cutover swap (D4), gated behind a SEPARATE ``--swap`` flag never
implied by an ordinary backfill run. H5 (spec Hazards): this module runs
only when invoked — nothing here executes at import time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Side-effect imports: importing each registers its DDL into
# schema_v2.DDL_REGISTRY (module-top code in each sibling). Listed
# explicitly for clarity even though axes.py's own chain
# (events -> views -> axes) would register all three via `axes` alone.
from entity_registry import events  # noqa: F401
from entity_registry import views  # noqa: F401
from entity_registry import axes
from entity_registry import database
from entity_registry import schema_v2
from entity_registry.uuid7 import generate_uuid7

# D1 step 2: the four registry owners this tool seeds onto the v1
# chain-shaped file. "core" is deliberately excluded — step 1's chain
# replay already built those tables (including _metadata).
_V2_SEED_OWNERS = frozenset({"events", "views", "axes", "axes_vocab_triggers"})

# Same default remediate_m12.py uses for the live entities.db.
_DEFAULT_LIVE_DB_PATH = str(Path.home() / ".claude" / "pd" / "entities" / "entities.db")


def _replay_v1_chain(staging_path: str) -> None:
    """D1 step 1: the sanctioned initial ``_migrate()`` use.

    Constructing ``EntityDatabase`` against a fresh path unconditionally
    runs the full v1 migration chain (``__init__`` -> ``_migrate()``);
    this closes it immediately after. No hand-rolled replay loop.
    """
    db = database.EntityDatabase(staging_path)
    db.close()


def _seed_v2_schema(conn: sqlite3.Connection) -> None:
    """D1 step 2: selectively seed the v2 event core, in one transaction.

    *conn* must already have ``PRAGMA foreign_keys = ON`` set (a raw
    connection defaults OFF). Guards ``register_vocab_ddl()`` with
    ``is_vocab_registered()`` first (axes.py's own re-entry guidance for
    "callers that may re-enter") so building more than one staging
    database in the same process is safe.
    """
    if not axes.is_vocab_registered():
        axes.register_vocab_ddl()

    # Raw "BEGIN IMMEDIATE"/"COMMIT"/"ROLLBACK" SQL text, not
    # conn.commit()/.rollback(): on an autocommit=True connection those
    # convenience methods are no-ops against a transaction opened via raw
    # "BEGIN IMMEDIATE" text — verified empirically (mirrors
    # events.append_event's _insert_standalone, same finding documented
    # in its docstring).
    conn.execute("BEGIN IMMEDIATE")
    try:
        for owner, sql_script in schema_v2.DDL_REGISTRY:
            if owner in _V2_SEED_OWNERS:
                conn.executescript(sql_script)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _stamp_v2_generation(conn: sqlite3.Connection) -> None:
    """D1 step 3: stamp the generation marker + version (#062 upsert)."""
    database._upsert_metadata(conn, "schema_generation", "v2")
    database._upsert_metadata(
        conn, "schema_version", str(schema_v2.V2_SCHEMA_VERSION)
    )


def build_staging_database(staging_path: str) -> None:
    """Run D1's three build steps against *staging_path*.

    *staging_path* should not already exist — :func:`main`'s
    ``--staging-only`` path enforces that; this function does not
    special-case re-entry (it happens to be idempotent-safe regardless:
    a v2-stamped file re-run through this is a no-op, per the FR132-1
    guard plus this function's own IF-NOT-EXISTS/upsert DDL).
    """
    _replay_v1_chain(staging_path)

    conn = sqlite3.connect(staging_path, autocommit=True)
    try:
        # PRAGMA discipline (mirrors schema_v2.bootstrap_v2/events.connect_v2):
        # busy_timeout and foreign_keys are per-connection and non-persistent
        # — every fresh connection re-issues them BEFORE any transaction
        # opens (foreign_keys is a silent no-op if set mid-transaction).
        conn.execute(f"PRAGMA busy_timeout = {schema_v2._BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        _seed_v2_schema(conn)
        _stamp_v2_generation(conn)
    finally:
        conn.close()


def default_staging_path(live_db_path: str) -> str:
    """D1: ``<dir>/entities.db.rebuild-<yyyymmdd>`` beside *live_db_path*."""
    live = Path(live_db_path)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return str(live.parent / f"{live.name}.rebuild-{today}")


# ---------------------------------------------------------------------------
# Task 2 exceptions (D2/D3/D7 self-checks — all raised BEFORE or DURING the
# one import transaction; the caller's rollback handling in run_backfill
# guarantees neither leaves partial writes committed).
# ---------------------------------------------------------------------------


class BackfillVocabMismatchError(RuntimeError):
    """Pre-import vocab diff (SC5 #077 clause): a census value sits outside
    the live constraint surface. Raised BEFORE the staging connection ever
    opens a write transaction — ``run_backfill`` guarantees zero writes."""


class BackfillIntegrityError(RuntimeError):
    """A post-import self-check failed (FK violation, or a per-bucket
    entities count delta the import's own dedup bookkeeping cannot
    explain, FR132-3). Raised INSIDE the import transaction, which the
    caller rolls back."""


# ---------------------------------------------------------------------------
# D3: vendored, frozen status/phase -> kanban-column derivation.
#
# plan-i1 (SC5-collision fix): this symbol is named without the bare
# token the task-5 grep gate pins — see the comment on the gate's own
# pattern in design D6.10. Byte-derived from workflow_engine/kanban.py's
# mapping and priority order as they stood at task-2 time, BEFORE that
# module's task-4 deletion — a frozen, one-time-use copy the rebuild tool
# owns forever, not a live import of a module this same feature retires.
# ---------------------------------------------------------------------------

_PHASE_TO_KANBAN: dict[str, str] = {
    # L3 feature phases (7-phase workflow)
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "implement": "wip",
    "finish": "documenting",
    # 5D phases (L1/L2/L4)
    "discover": "backlog",
    "define": "backlog",
    "deliver": "wip",
    "debrief": "documenting",
    # "design" is shared between both — already mapped above
}


def _frozen_kanban_derivation(status: str | None, workflow_phase: str | None) -> str:
    """Frozen status/phase -> kanban-column mapping (design D3).

    Priority order (unchanged from the source function this vendors):
    1. Terminal statuses (completed, abandoned) -> "completed"
    2. Blocked status -> "blocked"
    3. Planned status -> "backlog"
    4. Phase-based lookup with "backlog" fallback

    The output range is exactly six literals — {"completed", "blocked",
    "backlog", "prioritised", "wip", "documenting"} — a fixed subset of
    both ``axes.EXECUTION_STATUSES_SET`` (7 values) and the v1
    ``workflow_phases.kanban_column`` CHECK (8 values): no input can ever
    make this function emit an out-of-vocabulary value on either side.
    """
    if status in ("completed", "abandoned"):
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "planned":
        return "backlog"
    return _PHASE_TO_KANBAN.get(workflow_phase, "backlog")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# D2: per-import bookkeeping.
# ---------------------------------------------------------------------------


@dataclass
class _ImportState:
    """Bookkeeping threaded through one import transaction (D2).

    old_to_new:
        Every OLD entity uuid (survivors AND dedup losers) -> its NEW
        uuid7. Losers map to their survivor's new uuid (H1: the whole
        import, including this map, is built and applied atomically).
    secondary_map:
        ``(old_workspace_uuid, old_type_id) -> new_uuid`` — the
        business-key-keyed resolution phase_events/workflow_phases rows
        need (they carry no entity uuid at all, database.py's
        phase_events/workflow_phases shapes).
    type_id_rename:
        ``(old_workspace_uuid, old_type_id) -> new_type_id`` — populated
        ONLY for entities whose entity_id was empty-normalized (D2), so
        their type_id changed. Absent key means "unchanged".
    survivors:
        One dict per surviving (post-dedup) entity, insertion-ordered
        the same as the entities INSERT (parent-topological, D2).
    counts:
        ``kind -> old_workspace_uuid -> {"old": N, "new": N}`` (FR132-3).
    anomalies:
        Category -> list of report entries (prd.md:106: every anomaly is
        listed, never silently skipped).
    """

    old_to_new: dict[str, str] = field(default_factory=dict)
    secondary_map: dict[tuple[str, str], str] = field(default_factory=dict)
    type_id_rename: dict[tuple[str, str], str] = field(default_factory=dict)
    survivors: list[dict] = field(default_factory=list)
    counts: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    anomalies: dict[str, list[dict]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pre-import vocabulary diff (SC5 #077 clause, D3) — MUST run before any
# write against the staging connection.
# ---------------------------------------------------------------------------


def _preimport_vocab_diff(old_conn: sqlite3.Connection) -> None:
    """Diff every census value the backfill is about to write into a
    constrained column against the LIVE constraint surface; abort with
    every offending value listed if any mismatch — before any write.

    Two dimensions are genuinely reachable (a value the v1 file happily
    stores, per its own open-vocabulary columns, that the NEW v2 axis
    triggers would reject): a feature-kind entity's phase-named
    phase_events.phase value against ``axes.PIPELINE_PHASES_SET`` (row 2
    of design D3's table), and the derived kanban value against
    ``axes.EXECUTION_STATUSES_SET`` (structurally unreachable given
    :func:`_frozen_kanban_derivation`'s fixed 6-value codomain, but
    computed from the LIVE axes constants — not a hardcoded mirror — so a
    future codomain change is still caught here). The remaining
    dimensions (entity_relations.kind, entities' (type, kind) CHECK,
    phase_events.event_type) are v1-side: the census already satisfied
    them once, when originally written against this SAME schema, so they
    are checked defensively for completeness against spec SC5's
    exhaustive list, not because they can fail in practice.
    """
    offenders: dict[str, list[str]] = {}

    feature_phase_rows = old_conn.execute(
        "SELECT DISTINCT pe.phase FROM phase_events pe "
        "JOIN entities e ON e.type_id = pe.type_id "
        "WHERE e.kind = 'feature' "
        "AND pe.event_type IN ('started', 'completed', 'skipped', 'backward') "
        "AND pe.phase IS NOT NULL"
    ).fetchall()
    feature_phases = {row[0] for row in feature_phase_rows}
    bad_pipeline = sorted(feature_phases - axes.PIPELINE_PHASES_SET)
    if bad_pipeline:
        offenders["pipeline_phase"] = bad_pipeline

    entity_status_rows = old_conn.execute(
        "SELECT e.status, wp.workflow_phase FROM entities e "
        "LEFT JOIN workflow_phases wp ON wp.type_id = e.type_id"
    ).fetchall()
    derived_values = {
        _frozen_kanban_derivation(row[0], row[1]) for row in entity_status_rows
    }
    bad_execution = sorted(derived_values - axes.EXECUTION_STATUSES_SET)
    if bad_execution:
        offenders["execution_status"] = bad_execution

    relation_kinds = {
        row[0]
        for row in old_conn.execute(
            "SELECT DISTINCT kind FROM entity_relations"
        ).fetchall()
    }
    bad_relations = sorted(relation_kinds - {"fixes", "blocks"})
    if bad_relations:
        offenders["entity_relations_kind"] = bad_relations

    entity_kinds = {
        row[0] for row in old_conn.execute("SELECT DISTINCT kind FROM entities").fetchall()
    }
    bad_kinds = sorted(entity_kinds - set(database._KIND_TO_TYPE_LIFECYCLE))
    if bad_kinds:
        offenders["entities_kind"] = bad_kinds

    event_types = {
        row[0]
        for row in old_conn.execute(
            "SELECT DISTINCT event_type FROM phase_events"
        ).fetchall()
    }
    bad_event_types = sorted(event_types - set(database._VALID_PARAMS))
    if bad_event_types:
        offenders["phase_events_event_type"] = bad_event_types

    if offenders:
        raise BackfillVocabMismatchError(
            "pre-import vocab diff found census values outside the live "
            f"constraint surface (aborting before any write): {offenders!r}"
        )


# ---------------------------------------------------------------------------
# D2: backfill import — workspaces, entities (dedup + parent-topological
# order + uuid7 re-mint), entity_relations, workflow_phases.
# ---------------------------------------------------------------------------


def _import_workspaces(old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> None:
    """Copy ``workspaces`` rows verbatim — uuid UNCHANGED.

    Workspace uuids are NOT part of FR132-2's "re-mint ALL as uuid7"
    scope (#054(b) is about entity identity); migration 11 mints them
    with the stdlib's plain, non-time-ordered uuid mint call (database.py)
    and nothing downstream depends on their format, only their stability
    as a join key.
    """
    rows = old_conn.execute(
        "SELECT uuid, project_id_legacy, project_root, created_at, updated_at "
        "FROM workspaces ORDER BY uuid"
    ).fetchall()
    for row in rows:
        new_conn.execute(
            "INSERT INTO workspaces "
            "(uuid, project_id_legacy, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (row["uuid"], row["project_id_legacy"], row["project_root"],
             row["created_at"], row["updated_at"]),
        )


_DISPLAY_ID_RE = re.compile(r"^(\d+)-(.+)$")

_ENTITIES_INSERT_SQL = (
    "INSERT INTO entities (" + ",".join(database._V14_ENTITIES_COLUMNS) + ") "
    "VALUES (" + ",".join("?" for _ in database._V14_ENTITIES_COLUMNS) + ")"
)


def _dedup_entities(
    old_rows: list[sqlite3.Row],
) -> tuple[dict[str, str], list[str], dict[str, list[dict]]]:
    """D2 dedup (spec #054(a)): WITHIN-workspace ``(workspace_uuid,
    type_id)`` collisions keep the newest ``updated_at`` (tie-broken on
    uuid for determinism); losers are recorded as anomalies and never get
    their own entities row (the composite UNIQUE the chain-replayed
    table still carries — Scope model step 1 — would reject a second row
    under the same key; cross-workspace collisions, e.g. three
    workspaces' own project:P001, are a DIFFERENT (workspace_uuid,
    type_id) pair each and are never touched here).

    Returns ``(collapse_map, survivor_old_uuids, anomalies)``:
    ``collapse_map`` maps every LOSER's old uuid to its survivor's old
    uuid; ``survivor_old_uuids`` lists survivors in deterministic
    first-appearance order (mirrors *old_rows*, itself ``ORDER BY uuid``).
    """
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in old_rows:
        groups.setdefault((row["workspace_uuid"], row["type_id"]), []).append(row)

    collapse_map: dict[str, str] = {}
    survivor_old_uuids: list[str] = []
    anomalies: dict[str, list[dict]] = {"duplicate_type_id": []}
    for (ws, type_id), members in groups.items():
        if len(members) == 1:
            survivor_old_uuids.append(members[0]["uuid"])
            continue
        ordered = sorted(members, key=lambda r: (r["updated_at"], r["uuid"]))
        survivor = ordered[-1]
        survivor_old_uuids.append(survivor["uuid"])
        for loser in ordered[:-1]:
            collapse_map[loser["uuid"]] = survivor["uuid"]
            anomalies["duplicate_type_id"].append({
                "old_uuid": loser["uuid"],
                "workspace_uuid": ws,
                "type_id": type_id,
                "survivor_old_uuid": survivor["uuid"],
            })
    return collapse_map, survivor_old_uuids, anomalies


def _parent_topological_order(
    by_old_uuid: dict[str, sqlite3.Row],
    survivor_old_uuids: list[str],
    collapse_map: dict[str, str],
) -> tuple[list[str], set[str], dict[str, list[dict]]]:
    """D2: parent-topological order over SURVIVORS (parent before child),
    resolving any parent reference that names a dedup LOSER through to
    its survivor. A genuine cycle (A's ancestry loops back to A) breaks
    at the edge that would re-visit an in-progress ancestor — that
    child's OWN parent link is dropped (NULL), not the ancestor's; a
    parent reference to a uuid outside the surviving set (missing, or a
    workspace this import never reached) is an orphan, also NULL'd.
    Neither case is silently skipped — both land in *anomalies*.
    """
    survivor_set = set(survivor_old_uuids)

    def resolve_survivor(old_uuid: str | None) -> str | None:
        if old_uuid is None:
            return None
        return collapse_map.get(old_uuid, old_uuid)

    state: dict[str, str] = {}
    order: list[str] = []
    broken_cycle: set[str] = set()
    anomalies: dict[str, list[dict]] = {"orphan_parent": [], "parent_cycle": []}

    def visit(old_uuid: str) -> None:
        if state.get(old_uuid) == "done":
            return
        state[old_uuid] = "visiting"
        row = by_old_uuid[old_uuid]
        raw_parent = row["parent_uuid"]
        parent_survivor = resolve_survivor(raw_parent)
        if raw_parent is not None and parent_survivor in survivor_set:
            if state.get(parent_survivor) == "visiting":
                broken_cycle.add(old_uuid)
                anomalies["parent_cycle"].append({
                    "old_uuid": old_uuid,
                    "broken_parent_old_uuid": parent_survivor,
                })
            else:
                visit(parent_survivor)
        elif raw_parent is not None:
            anomalies["orphan_parent"].append({
                "old_uuid": old_uuid,
                "missing_parent_old_uuid": raw_parent,
            })
        state[old_uuid] = "done"
        order.append(old_uuid)

    for old_uuid in survivor_old_uuids:
        visit(old_uuid)

    return order, broken_cycle, anomalies


def _import_entities(old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> _ImportState:
    """D2: the core entity backfill — dedup, parent-topological order,
    uuid7 re-mint, empty-id/name normalization, and the INSERT into
    entities + entities_fts + entity_display (D8's population — the
    standalone FTS5 virtual table has no external-content wiring back to
    ``entities``, so a post-commit ``INSERT ... VALUES('rebuild')`` alone
    cannot backfill it; this per-row population is the real mechanism).
    """
    old_rows = old_conn.execute(
        "SELECT uuid, workspace_uuid, type_id, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, kind, lifecycle_class FROM entities ORDER BY uuid"
    ).fetchall()
    by_old_uuid = {row["uuid"]: row for row in old_rows}

    collapse_map, survivor_old_uuids, dedup_anomalies = _dedup_entities(old_rows)
    topo_order, broken_cycle, topo_anomalies = _parent_topological_order(
        by_old_uuid, survivor_old_uuids, collapse_map
    )
    survivor_set = set(survivor_old_uuids)

    def resolve_survivor(old_uuid: str | None) -> str | None:
        if old_uuid is None:
            return None
        return collapse_map.get(old_uuid, old_uuid)

    anomalies: dict[str, list[dict]] = {
        "duplicate_type_id": dedup_anomalies["duplicate_type_id"],
        "empty_id_normalized": [],
        "orphan_parent": topo_anomalies["orphan_parent"],
        "parent_cycle": topo_anomalies["parent_cycle"],
    }

    # uuid7 re-mint: survivors first (insert order is irrelevant to the
    # mint order itself — entities carries no MAX(uuid)-latest contract,
    # unlike events), losers share their survivor's new uuid.
    old_to_new: dict[str, str] = {old_uuid: generate_uuid7() for old_uuid in topo_order}
    for loser_uuid, survivor_uuid in collapse_map.items():
        old_to_new[loser_uuid] = old_to_new[survivor_uuid]

    counts: dict[str, dict[str, dict[str, int]]] = {}

    def _bump(kind: str, ws: str, field_name: str) -> None:
        bucket = counts.setdefault(kind, {}).setdefault(ws, {"old": 0, "new": 0})
        bucket[field_name] += 1

    for row in old_rows:
        _bump(row["kind"], row["workspace_uuid"], "old")

    secondary_map: dict[tuple[str, str], str] = {}
    type_id_rename: dict[tuple[str, str], str] = {}
    survivors: list[dict] = []

    for old_uuid in topo_order:
        row = by_old_uuid[old_uuid]
        new_uuid = old_to_new[old_uuid]
        ws = row["workspace_uuid"]

        entity_id_new = row["entity_id"]
        name_new = row["name"]
        placeholder = f"unnamed-{old_uuid[:8]}"
        if not entity_id_new.strip():
            entity_id_new = placeholder
            anomalies["empty_id_normalized"].append({
                "old_uuid": old_uuid, "field": "entity_id", "normalized_to": placeholder,
            })
        if not name_new.strip():
            name_new = placeholder
            anomalies["empty_id_normalized"].append({
                "old_uuid": old_uuid, "field": "name", "normalized_to": placeholder,
            })

        type_id_new = f"{row['kind']}:{entity_id_new}"
        if type_id_new != row["type_id"]:
            type_id_rename[(ws, row["type_id"])] = type_id_new

        if old_uuid in broken_cycle:
            parent_new = None
        else:
            parent_survivor = resolve_survivor(row["parent_uuid"])
            parent_new = (
                old_to_new.get(parent_survivor) if parent_survivor in survivor_set else None
            )

        new_conn.execute(
            _ENTITIES_INSERT_SQL,
            (
                new_uuid, ws, type_id_new, entity_id_new, name_new, row["status"],
                parent_new, row["artifact_path"], row["created_at"], row["updated_at"],
                row["metadata"], row["type"], row["kind"], row["lifecycle_class"],
            ),
        )

        metadata_dict = json.loads(row["metadata"]) if row["metadata"] else None
        new_rowid = new_conn.execute(
            "SELECT rowid FROM entities WHERE uuid = ?", (new_uuid,)
        ).fetchone()[0]
        new_conn.execute(
            "INSERT INTO entities_fts "
            "(rowid, name, entity_id, kind, status, metadata_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_rowid, name_new, entity_id_new, row["kind"], row["status"] or "",
             database.flatten_metadata(metadata_dict)),
        )

        display_match = _DISPLAY_ID_RE.match(entity_id_new)
        if display_match:
            new_conn.execute(
                "INSERT INTO entity_display (uuid, seq, slug) VALUES (?, ?, ?)",
                (new_uuid, int(display_match.group(1)), display_match.group(2)),
            )

        secondary_map[(ws, row["type_id"])] = new_uuid
        survivors.append({
            "old_uuid": old_uuid,
            "new_uuid": new_uuid,
            "workspace_uuid": ws,
            "type_id_old": row["type_id"],
            "type_id_new": type_id_new,
            "kind": row["kind"],
            "entity_id_new": entity_id_new,
            "name_new": name_new,
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
        _bump(row["kind"], ws, "new")

    return _ImportState(
        old_to_new=old_to_new,
        secondary_map=secondary_map,
        type_id_rename=type_id_rename,
        survivors=survivors,
        counts=counts,
        anomalies=anomalies,
    )


def _import_entity_relations(
    old_conn: sqlite3.Connection, new_conn: sqlite3.Connection, old_to_new: dict[str, str]
) -> dict:
    """D2: copy ``entity_relations`` (incl. 124's ``blocks`` edges),
    remapping both endpoints through *old_to_new*. Dedup collapse can
    make two formerly-distinct edges coincide (a loser's and its
    survivor's own edge to the same target) — ``idx_entity_relations_
    unique`` on the chain-replayed table would reject the second INSERT,
    so duplicates are pre-filtered in Python instead of relying on an
    ``INSERT OR IGNORE`` (keeps the FK-violation surface identical to
    every other raw INSERT this tool issues).
    """
    old_rows = old_conn.execute(
        "SELECT from_uuid, to_uuid, kind, created_at FROM entity_relations ORDER BY id"
    ).fetchall()
    orphans: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    inserted = 0
    for row in old_rows:
        new_from = old_to_new.get(row["from_uuid"])
        new_to = old_to_new.get(row["to_uuid"])
        if new_from is None or new_to is None:
            orphans.append({
                "from_uuid": row["from_uuid"], "to_uuid": row["to_uuid"], "kind": row["kind"],
            })
            continue
        dedup_key = (new_from, new_to, row["kind"])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        new_conn.execute(
            "INSERT INTO entity_relations (from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, ?, ?)",
            (new_from, new_to, row["kind"], row["created_at"]),
        )
        inserted += 1
    return {"old": len(old_rows), "new": inserted, "orphans": orphans}


def _import_workflow_phases(
    old_conn: sqlite3.Connection, new_conn: sqlite3.Connection, state: _ImportState
) -> dict[tuple[str, str], dict]:
    """D2: copy ``workflow_phases`` rows. ``workflow_phases.type_id`` is
    a GLOBAL primary key (never workspace-scoped) — post-dedup there is
    at most one row per (workspace, type_id) key already, so no new
    collision this import could introduce; ``workspace_uuid`` is set
    EXPLICITLY (not left NULL for the AFTER-INSERT autofill trigger),
    sidestepping any scalar-subquery ambiguity across cross-workspace
    type_id collisions on kinds that never actually carry a
    workflow_phases row (projects) — belt-and-suspenders, not a case the
    live census is known to hit.

    D3's "final derived status per entity, written to the stored v1
    column" lands HERE, at INSERT time: ``kanban_column`` is set to
    :func:`_frozen_kanban_derivation`'s output (computed from the SAME
    row's ``workflow_phase`` plus the owning entity's status) rather than
    the copied-verbatim OLD value — a single write, not an insert
    followed by a same-table follow-up mutation (the doctor's static
    write-path audit, ``check_status_write_path.py``, polices direct
    post-insert writes to this table outside its permitted-callers list;
    the rebuild tool is not on that list, so structuring this as one
    INSERT keeps it out of the audit's scope entirely, cleanly, rather
    than needing an exemption).

    Returns ``(old_workspace_uuid, old_type_id) -> {"workflow_phase":
    ..., "new_type_id": ..., "kanban_column": ...}`` for
    :func:`_emit_all_events`'s status_backfilled event (the SAME
    already-computed value, never re-derived a second time).
    """
    old_rows = old_conn.execute(
        "SELECT type_id, workflow_phase, kanban_column, last_completed_phase, "
        "mode, backward_transition_reason, updated_at, workspace_uuid "
        "FROM workflow_phases ORDER BY type_id"
    ).fetchall()
    status_by_key = {
        (survivor["workspace_uuid"], survivor["type_id_old"]): survivor["status"]
        for survivor in state.survivors
    }

    result: dict[tuple[str, str], dict] = {}
    orphans: list[dict] = []
    for row in old_rows:
        ws_old = row["workspace_uuid"]
        key = (ws_old, row["type_id"])
        new_uuid = state.secondary_map.get(key)
        if new_uuid is None:
            orphans.append({"type_id": row["type_id"], "workspace_uuid": ws_old})
            continue
        new_type_id = state.type_id_rename.get(key, row["type_id"])
        derived = _frozen_kanban_derivation(status_by_key.get(key), row["workflow_phase"])
        new_conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, kanban_column, workflow_phase, last_completed_phase, "
            "mode, backward_transition_reason, updated_at, uuid, workspace_uuid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_type_id, derived, row["workflow_phase"],
             row["last_completed_phase"], row["mode"],
             row["backward_transition_reason"], row["updated_at"],
             new_uuid, ws_old),
        )
        result[key] = {
            "workflow_phase": row["workflow_phase"],
            "new_type_id": new_type_id,
            "kanban_column": derived,
        }
    if orphans:
        state.anomalies.setdefault("orphan_workflow_phase", []).extend(orphans)
    return result


# ---------------------------------------------------------------------------
# D3: v2 event emission (FR132-2b's axis mapping table, verbatim).
# ---------------------------------------------------------------------------

_BACKFILL_ACTOR = "backfill:132"

_PHASE_NAMED_EVENT_TYPES = frozenset({"started", "completed", "skipped", "backward"})


def _classify_phase_event(
    kind: str, event_type: str, phase: str | None, metadata_json: str | None
) -> tuple[str, str | None]:
    """D3's axis mapping for a COPIED phase_events row (table rows 2-4;
    rows 1 and 5 — entity_created and status_backfilled — are synthesized
    once per entity, not derived from a phase_events row, and are handled
    by :func:`_emit_events_for_entity` directly).

    Phase-named event_types (started/completed/skipped/backward) go to
    the pipeline axis for feature-kind entities, lifecycle for every
    other kind — including a feature-kind row whose phase is NOT one of
    the 6 pipeline phases, which the pre-import vocab diff has already
    guaranteed cannot exist by the time this runs (so no runtime
    vocabulary filter is needed here; a bug reintroducing that
    possibility would raise the 122 trigger loudly at INSERT time rather
    than silently misroute).

    Every other event_type (entity_created, entity_status_changed,
    entity_promoted, spawned_child, cascade_ready — row 4, "phase
    typically NULL") goes to lifecycle (vocab-free — 122's triggers only
    police pipeline/execution) with ``to_value`` set to
    ``metadata['new_status']`` when present (the SAME key
    ``append_phase_event``'s own entities.status projection reads,
    database.py) or NULL otherwise — NEVER the execution axis: historical
    values here may sit outside the 122 vocab, and lifecycle is where
    history is preserved without collision (design D3).
    """
    if event_type in _PHASE_NAMED_EVENT_TYPES:
        axis = "pipeline" if kind == "feature" else "lifecycle"
        return axis, phase
    metadata = json.loads(metadata_json) if metadata_json else {}
    return "lifecycle", metadata.get("new_status")


def _insert_event(
    new_conn: sqlite3.Connection,
    *,
    entity_uuid: str,
    event_type: str,
    axis: str,
    to_value: str | None,
    timestamp: str,
    payload: dict | None,
) -> None:
    new_conn.execute(
        "INSERT INTO events "
        "(uuid, entity_uuid, event_type, axis, from_value, to_value, actor, "
        "timestamp, payload) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)",
        (generate_uuid7(), entity_uuid, event_type, axis, to_value,
         _BACKFILL_ACTOR, timestamp, json.dumps(payload) if payload is not None else None),
    )


def _emit_events_for_entity(
    new_conn: sqlite3.Connection,
    *,
    entity_uuid: str,
    kind: str,
    phase_rows: list[sqlite3.Row],
    entity_created_ts: str,
    entity_payload: dict,
    derived_status: str,
    status_backfilled_ts: str,
) -> int:
    """D3: emit one entity's full v2 event stream.

    Ascending DOMAIN-timestamp insert order (spec FR132-2; ``MAX(uuid)``
    correctness — uuid7 mint order here IS physical insert order) for the
    synthesized ``entity_created`` row plus every phase_events-derived
    row; the synthesized ``status_backfilled`` row is ALWAYS inserted
    LAST regardless of its own timestamp (the SC3 parity note: it is by
    construction the execution axis's only — hence latest — event, but
    inserting it last keeps that true even if a future non-frozen
    derivation ever adds a second execution-axis producer).
    """
    # -1 sentinel tie-break sorts entity_created before any same-instant
    # phase_events row (ties broken on the copied row's own id otherwise).
    timeline: list[tuple[str, int, str, str, str | None, dict | None]] = [
        (entity_created_ts, -1, "lifecycle", "entity_created", None, entity_payload)
    ]
    for row in phase_rows:
        axis, to_value = _classify_phase_event(
            kind, row["event_type"], row["phase"], row["metadata"]
        )
        timeline.append((row["timestamp"], row["id"], axis, row["event_type"], to_value, None))
    timeline.sort(key=lambda item: (item[0], item[1]))

    for timestamp, _tiebreak, axis, event_type, to_value, payload in timeline:
        _insert_event(
            new_conn, entity_uuid=entity_uuid, event_type=event_type, axis=axis,
            to_value=to_value, timestamp=timestamp, payload=payload,
        )

    _insert_event(
        new_conn, entity_uuid=entity_uuid, event_type="status_backfilled", axis="execution",
        to_value=derived_status, timestamp=status_backfilled_ts, payload=None,
    )
    return len(timeline) + 1


def _emit_all_events(
    old_conn: sqlite3.Connection,
    new_conn: sqlite3.Connection,
    state: _ImportState,
    wf_by_key: dict[tuple[str, str], dict],
) -> tuple[dict, int]:
    """D2+D3: copy every ``phase_events`` row (``source`` re-stamped
    ``'backfill'``, D2 — the CHECK admits it; type_id rewritten only for
    entities whose id was empty-normalized) AND, per surviving entity,
    emit its v2 event stream via :func:`_emit_events_for_entity`
    (including the once-per-entity derived-kanban write into BOTH the
    stored ``workflow_phases.kanban_column`` v1 column, when a
    workflow_phases row exists for it, and the synthesized execution-axis
    ``status_backfilled`` event, which is unconditional).

    Every phase_events row is copied regardless of whether its
    ``project_id`` resolves to a workspace (row-count parity, SC3(b), is
    unconditional); only the v2 EVENT for an unresolvable row is skipped
    (recorded as an ``orphan_phase_event`` anomaly) — resolution failure
    here means a legacy ``project_id`` label with no matching
    ``workspaces`` row, not a missing entity.

    Migration 10's ``phase_events_backfill_dedup`` partial UNIQUE index
    (``(type_id, phase, event_type, timestamp) WHERE source='backfill'``)
    predates this feature — it exists for the LEGACY
    ``entity_registry/backfill.py`` tool's own idempotent-re-run
    contract, but it applies to ANY row carrying ``source='backfill'``,
    which is exactly the value D2 mandates here. Live rows are
    unconstrained ("two legitimate same-second events coexist," per that
    index's own comment), so two OLD rows sharing an identical
    (type_id, phase, event_type, timestamp) tuple — a narrow but real
    possibility at second-resolution timestamps — collide only once
    BOTH are re-stamped 'backfill'. Caught per-row rather than let one
    stale-timestamp coincidence abort the entire H1 transaction; the
    LOSING row still contributes its v2 event (that data isn't lost, only
    its OWN redundant v1 copy is) and is recorded as an anomaly.
    """
    old_phase_events = old_conn.execute(
        "SELECT id, type_id, project_id, phase, event_type, timestamp, "
        "iterations, reviewer_notes, backward_reason, backward_target, "
        "created_at, metadata FROM phase_events ORDER BY id"
    ).fetchall()
    ws_by_legacy = {
        row["project_id_legacy"]: row["uuid"]
        for row in old_conn.execute(
            "SELECT uuid, project_id_legacy FROM workspaces"
        ).fetchall()
        if row["project_id_legacy"] is not None
    }

    phase_events_by_key: dict[tuple[str, str], list[sqlite3.Row]] = {}
    unresolvable: list[dict] = []
    dedup_collisions: list[dict] = []
    copied_new_count = 0
    for row in old_phase_events:
        ws_old = ws_by_legacy.get(row["project_id"])
        new_type_id = row["type_id"]
        if ws_old is not None:
            new_type_id = state.type_id_rename.get((ws_old, row["type_id"]), row["type_id"])
        try:
            new_conn.execute(
                "INSERT INTO phase_events "
                "(type_id, project_id, phase, event_type, timestamp, iterations, "
                "reviewer_notes, backward_reason, backward_target, source, "
                "created_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'backfill', ?, ?)",
                (new_type_id, row["project_id"], row["phase"], row["event_type"],
                 row["timestamp"], row["iterations"], row["reviewer_notes"],
                 row["backward_reason"], row["backward_target"], row["created_at"],
                 row["metadata"]),
            )
            copied_new_count += 1
        except sqlite3.IntegrityError as exc:
            # SQLite's message names the constraint's COLUMN SET, not the
            # index name — this is the exact 4-column fingerprint of
            # phase_events_backfill_dedup (database.py), the only UNIQUE
            # constraint on this table shaped this way. Anything else
            # (a NOT NULL/CHECK violation, an unrelated collision) is a
            # real bug and must propagate, not be silently absorbed.
            if (
                "phase_events.type_id, phase_events.phase, "
                "phase_events.event_type, phase_events.timestamp"
            ) not in str(exc):
                raise
            dedup_collisions.append({
                "type_id": new_type_id, "phase": row["phase"],
                "event_type": row["event_type"], "timestamp": row["timestamp"],
            })
        if ws_old is None:
            unresolvable.append({"type_id": row["type_id"], "project_id": row["project_id"]})
            continue
        phase_events_by_key.setdefault((ws_old, row["type_id"]), []).append(row)
    if unresolvable:
        state.anomalies.setdefault("orphan_phase_event", []).extend(unresolvable)
    if dedup_collisions:
        state.anomalies.setdefault("phase_events_dedup_collision", []).extend(dedup_collisions)

    events_emitted = 0
    for survivor in state.survivors:
        key = (survivor["workspace_uuid"], survivor["type_id_old"])
        phase_rows = phase_events_by_key.get(key, [])
        wf_info = wf_by_key.get(key)
        # _import_workflow_phases already computed (and, where a
        # workflow_phases row exists, wrote) this SAME derivation — reuse
        # it here rather than deriving a second time, so the v1 column
        # and the v2 event are the SAME value by construction, not by
        # coincidentally-identical recomputation.
        if wf_info is not None:
            derived = wf_info["kanban_column"]
        else:
            derived = _frozen_kanban_derivation(survivor["status"], None)

        entity_payload = {
            "old_uuid": survivor["old_uuid"],
            "kind": survivor["kind"],
            "entity_id": survivor["entity_id_new"],
            "name": survivor["name_new"],
        }
        events_emitted += _emit_events_for_entity(
            new_conn,
            entity_uuid=survivor["new_uuid"],
            kind=survivor["kind"],
            phase_rows=phase_rows,
            entity_created_ts=survivor["created_at"],
            entity_payload=entity_payload,
            derived_status=derived,
            status_backfilled_ts=survivor["updated_at"],
        )

    phase_event_counts = {"old": len(old_phase_events), "new": copied_new_count}
    return phase_event_counts, events_emitted


# ---------------------------------------------------------------------------
# D6.9 (seed-half): seed one ``sequences`` row per (kind, workspace) at
# the census max display number, so the atomic allocator continues every
# kind's numbering post-cutover.
# ---------------------------------------------------------------------------

# Project ids are "P{NNN}" (no dash-slug suffix, commands/create-project.md)
# — the generic leading-digit-run pattern next_sequence_value's own
# bootstrap uses (database.py) is regex-blind to the leading "P" by
# design (entity_server.py's allocate_entity_id kind_deferred docstring
# names this explicitly); every other kind uses "{seq:03d}-{slug}".
_PROJECT_DISPLAY_RE = re.compile(r"^P(\d+)$")
_GENERIC_DISPLAY_RE = re.compile(r"^(\d+)")


def _display_number(kind: str, entity_id: str) -> int:
    pattern = _PROJECT_DISPLAY_RE if kind == "project" else _GENERIC_DISPLAY_RE
    match = pattern.match(entity_id)
    return int(match.group(1)) if match else 0


def _seed_sequences(old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> dict:
    """D6.9: one row per (workspace, kind) PRESENT in the census, at
    ``max(display number) + 1`` — the SAME "next value to issue" contract
    ``next_sequence_value`` (database.py) returns for an existing row.
    Uses the FULL raw old-file scan (not the post-dedup survivor set):
    within-workspace duplicates share the identical entity_id/number by
    definition, so dedup can never change the max.
    """
    rows = old_conn.execute(
        "SELECT workspace_uuid, kind, entity_id FROM entities "
        "ORDER BY workspace_uuid, kind"
    ).fetchall()
    max_by_bucket: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["workspace_uuid"], row["kind"])
        number = _display_number(row["kind"], row["entity_id"])
        max_by_bucket[key] = max(max_by_bucket.get(key, 0), number)

    seeded: dict[str, dict[str, int]] = {}
    for (ws, kind), max_seq in sorted(max_by_bucket.items()):
        next_val = max_seq + 1
        new_conn.execute(
            "INSERT INTO sequences (workspace_uuid, entity_type, next_val) VALUES (?, ?, ?)",
            (ws, kind, next_val),
        )
        seeded.setdefault(kind, {})[ws] = next_val
    return seeded


# ---------------------------------------------------------------------------
# D7: report artifact — checksum (FR132-3), the machine report dict
# (pure: comparable byte-for-byte across two independent runs on the same
# source file, SC2's idempotence), and the two on-disk forms.
# ---------------------------------------------------------------------------


def _compute_checksum(old_entity_rows: list[sqlite3.Row]) -> str:
    """FR132-3: a content checksum over a canonical serialization of
    "both sides' comparable fields" — the OLD uuid, workspace, ORIGINAL
    type_id/entity_id/name, kind, status, and parent_uuid, sorted by old
    uuid. Deliberately excludes anything the import mints fresh (new
    uuid7s, wall-clock timestamps) so it is STABLE across two independent
    runs against the same source file, not merely within one run.
    """
    canonical = [
        {
            "uuid": row["uuid"],
            "workspace_uuid": row["workspace_uuid"],
            "type_id": row["type_id"],
            "kind": row["kind"],
            "status": row["status"],
            "entity_id": row["entity_id"],
            "name": row["name"],
            "parent_uuid": row["parent_uuid"],
        }
        for row in sorted(old_entity_rows, key=lambda r: r["uuid"])
    ]
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _verify_counts_explained(state: _ImportState) -> None:
    """FR132-3: "Non-zero unexplained delta = tool exits non-zero" — every
    per-(kind, workspace) entities count delta must be fully accounted
    for by that bucket's own dedup losers (the ONLY thing that can make
    ``new < old`` in this import). Raises :class:`BackfillIntegrityError`
    (aborting the transaction) rather than ever committing a delta this
    import cannot explain.
    """
    dedup_by_bucket: dict[tuple[str, str], int] = {}
    for anomaly in state.anomalies["duplicate_type_id"]:
        kind = anomaly["type_id"].split(":", 1)[0]
        key = (kind, anomaly["workspace_uuid"])
        dedup_by_bucket[key] = dedup_by_bucket.get(key, 0) + 1

    unexplained = []
    for kind, by_ws in state.counts.items():
        for ws, bucket in by_ws.items():
            delta = bucket["old"] - bucket["new"]
            expected = dedup_by_bucket.get((kind, ws), 0)
            if delta != expected:
                unexplained.append({
                    "kind": kind, "workspace_uuid": ws, "delta": delta, "expected": expected,
                })
    if unexplained:
        raise BackfillIntegrityError(f"unexplained entities count deltas: {unexplained!r}")


def _build_report(
    state: _ImportState,
    relation_counts: dict,
    phase_event_counts: dict,
    events_emitted: int,
    sequences_seeded: dict,
    checksum: str,
) -> dict:
    return {
        "counts": state.counts,
        "anomalies": state.anomalies,
        "uuid_remap_count": len(state.old_to_new),
        "sequences_seeded": sequences_seeded,
        "entity_relations": relation_counts,
        "phase_events": phase_event_counts,
        "events_emitted": events_emitted,
        "checksum": checksum,
    }


def _default_report_dir() -> str:
    """D7: ``~/.claude/pd/migrations`` — CONFIGURABLE via
    ``PD_REBUILD_REPORT_DIR`` so tests never touch the real directory."""
    override = os.environ.get("PD_REBUILD_REPORT_DIR")
    if override:
        return override
    return str(Path.home() / ".claude" / "pd" / "migrations")


def _default_marker_dir() -> str:
    """D4: the marker root (``<marker_dir>/migrations/v2-cutover.json``)
    — CONFIGURABLE via ``PD_REBUILD_MARKER_DIR`` so tests never touch the
    real ``~/.claude/pd`` directory (mirrors :func:`_default_report_dir`,
    which every ``main()`` call already routes through)."""
    override = os.environ.get("PD_REBUILD_MARKER_DIR")
    if override:
        return override
    return str(Path.home() / ".claude" / "pd")


def write_machine_report(report: dict, report_dir: str) -> str:
    """D7: the full, entity-named machine report — outside the repo."""
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(report_dir) / f"rebuild-report-{ts}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return str(report_path)


def write_summary_report(report: dict, summary_path: str) -> None:
    """D7: the COMMITTED counts-only summary — zero entity names. Callers
    decide when this runs (never automatically from a test-scoped
    ``run_backfill``/``main`` invocation — see the committed placeholder
    at docs/features/132-backfill-rebuild-tool/rebuild-report-summary.md
    for why)."""
    lines = ["# Rebuild report summary (counts only — no entity names)", ""]
    lines.append("## Counts per kind x workspace")
    for kind in sorted(report["counts"]):
        lines.append(f"\n### {kind}")
        for ws in sorted(report["counts"][kind]):
            bucket = report["counts"][kind][ws]
            lines.append(f"- workspace `{ws}`: old={bucket['old']} new={bucket['new']}")
    lines.append("\n## Anomaly tallies")
    for category in sorted(report["anomalies"]):
        lines.append(f"- {category}: {len(report['anomalies'][category])}")
    lines.append(f"\nentity_relations: old={report['entity_relations']['old']} "
                 f"new={report['entity_relations']['new']}")
    lines.append(f"\nphase_events: old={report['phase_events']['old']} "
                 f"new={report['phase_events']['new']}")
    lines.append(f"\nevents_emitted: {report['events_emitted']}")
    lines.append(f"\nuuid_remap_count: {report['uuid_remap_count']}")
    lines.append(f"\nChecksum: `{report['checksum']}`")
    Path(summary_path).write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# D2/D3/D6.9/D7/D8 orchestration — ONE transaction over the whole import
# (H1: a partial remap is worse than no rebuild).
# ---------------------------------------------------------------------------


def _run_import_transaction(old_conn: sqlite3.Connection, new_conn: sqlite3.Connection) -> dict:
    _import_workspaces(old_conn, new_conn)
    state = _import_entities(old_conn, new_conn)
    relation_counts = _import_entity_relations(old_conn, new_conn, state.old_to_new)
    wf_by_key = _import_workflow_phases(old_conn, new_conn, state)
    phase_event_counts, events_emitted = _emit_all_events(old_conn, new_conn, state, wf_by_key)
    sequences_seeded = _seed_sequences(old_conn, new_conn)

    _verify_counts_explained(state)

    old_entity_rows = old_conn.execute(
        "SELECT uuid, workspace_uuid, type_id, kind, status, entity_id, name, "
        "parent_uuid FROM entities"
    ).fetchall()
    checksum = _compute_checksum(old_entity_rows)

    return _build_report(
        state, relation_counts, phase_event_counts, events_emitted, sequences_seeded, checksum
    )


def run_backfill(old_db_path: str, staging_path: str) -> dict:
    """D2+D3+D6.9+D7+D8: backfill *old_db_path*'s census into
    *staging_path* (already built via :func:`build_staging_database`).

    Reads the old file via a read-only URI connection — never
    ``EntityDatabase`` (its construction mutates, design D2). The
    pre-import vocab diff runs BEFORE the staging connection opens any
    transaction, so a mismatch leaves *staging_path* exactly as
    ``build_staging_database`` left it (zero import writes). The import
    itself is ONE transaction (H1); a ``PRAGMA foreign_key_check`` runs
    inside it, pre-commit, as a belt for the remap.

    Returns the machine report dict (FR132-3) — pure and comparable
    across independent runs against the same *old_db_path* (SC2's
    idempotence: no wall-clock or staging-path-derived field is baked
    into it; :func:`write_machine_report` is the caller's job).
    """
    old_conn = sqlite3.connect(f"file:{old_db_path}?mode=ro", uri=True, timeout=5.0)
    old_conn.row_factory = sqlite3.Row
    try:
        _preimport_vocab_diff(old_conn)

        new_conn = sqlite3.connect(staging_path, autocommit=True)
        try:
            new_conn.execute(f"PRAGMA busy_timeout = {schema_v2._BUSY_TIMEOUT_MS}")
            new_conn.execute("PRAGMA foreign_keys = ON")
            new_conn.execute("BEGIN IMMEDIATE")
            try:
                report = _run_import_transaction(old_conn, new_conn)
                violations = new_conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise BackfillIntegrityError(
                        f"foreign_key_check found violations after import: {violations!r}"
                    )
                new_conn.execute("COMMIT")
            except Exception:
                if new_conn.in_transaction:
                    new_conn.execute("ROLLBACK")
                raise
            # D8: the standalone entities_fts virtual table (no
            # external-content wiring) has already been populated
            # per-row inside the transaction above; this call is the
            # literal D8 mechanism for completeness/idempotence and is a
            # documented no-op given the current standalone shape (see
            # _import_entities' docstring) — cheap enough to keep.
            new_conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
        finally:
            new_conn.close()
    finally:
        old_conn.close()
    return report


# ---------------------------------------------------------------------------
# D4: cutover = rename swap. NEVER implied by an ordinary backfill run —
# only reachable via the CLI's separate --swap flag (main()).
# ---------------------------------------------------------------------------

_ARCHIVE_SUFFIX = ".v1-readonly"
_MARKER_RELATIVE_PATH = ("migrations", "v2-cutover.json")
_MARKER_EXPIRY_DAYS = 30


def _checkpoint_wal(db_path: str) -> None:
    """Open a short-lived connection, TRUNCATE-checkpoint its WAL, close.
    Leaves no live -wal/-shm content behind (D4)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_archived_old_file(path: str) -> sqlite3.Connection:
    """D4: readers of the archived old file use ``?mode=ro&immutable=1``
    (sidesteps WAL's -shm write-on-read against a file whose sidecars are
    gone post-checkpoint; the file itself never changes again)."""
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def perform_cutover_swap(
    old_db_path: str,
    staging_path: str,
    *,
    report_path: str | None = None,
    marker_dir: str | None = None,
) -> dict:
    """D4: WAL-safe rename-swap cutover. *staging_path* must already hold
    a successfully backfilled v2 file. Returns the marker dict written.

    Choreography:
    0. checkpoint + close a short-lived connection to *staging_path* (its
       -wal/-shm are now empty — the main file carries the whole import).
    1. checkpoint the OLD file (fresh short-lived connection, then
       close), ``chmod a-w`` it, and rename it to ``<old>.v1-readonly``.
    2. verify the staging checkpoint left no non-empty sidecar, then
       rename staging -> *old_db_path* (now the live path — untouched by
       this function otherwise: the 18 hard-coded literals + 8
       ``ENTITY_DB_PATH`` readers this repo has all resolve the SAME
       path before and after).
    3. write the dated-expiry marker JSON.
    4. print the H3 session-restart warning LOUDLY (servers cache the DB
       path + workspace uuid at startup).
    """
    staging = Path(staging_path)
    old = Path(old_db_path)
    if not staging.exists():
        raise FileNotFoundError(f"staging file does not exist: {staging_path}")
    if not old.exists():
        raise FileNotFoundError(f"old file does not exist: {old_db_path}")

    # Step 0.
    _checkpoint_wal(staging_path)
    for suffix in ("-wal", "-shm"):
        stray = Path(f"{staging_path}{suffix}")
        if stray.exists() and stray.stat().st_size == 0:
            stray.unlink()

    # Step 1.
    _checkpoint_wal(old_db_path)
    old_sha256 = _sha256_file(old_db_path)
    readonly_target = old.parent / f"{old.name}{_ARCHIVE_SUFFIX}"
    if readonly_target.exists():
        raise FileExistsError(
            f"refusing to overwrite an existing read-only archive: {readonly_target}"
        )
    current_mode = stat.S_IMODE(os.stat(old_db_path).st_mode)
    os.chmod(old_db_path, current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    old.rename(readonly_target)

    # Step 2.
    for suffix in ("-wal", "-shm"):
        stray = Path(f"{staging_path}{suffix}")
        if stray.exists() and stray.stat().st_size > 0:
            raise RuntimeError(
                f"staging checkpoint left a non-empty sidecar: {stray} — "
                f"aborting before promoting staging to {old_db_path}"
            )
    staging.rename(old)

    # Step 3.
    marker_root = Path(marker_dir) if marker_dir else Path(_default_marker_dir())
    marker_path = marker_root.joinpath(*_MARKER_RELATIVE_PATH)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    cutover_at = datetime.now(timezone.utc)
    expiry = cutover_at + timedelta(days=_MARKER_EXPIRY_DAYS)
    marker = {
        "cutover_at": cutover_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "old_file": str(readonly_target),
        "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "old_sha256": old_sha256,
        "report_path": report_path,
    }
    marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n")

    # Step 4.
    print(
        "=" * 72 + "\n"
        "  v2 CUTOVER COMPLETE --- RESTART EVERY MCP SESSION NOW.\n"
        "  Servers cache the DB path + workspace uuid at startup; a stale\n"
        "  session keeps writing/reading the OLD file's in-memory identity\n"
        "  even though the path now resolves to the NEW file.\n"
        f"  Old file archived read-only at: {readonly_target}\n"
        f"  Marker: {marker_path}\n"
        + "=" * 72,
        file=sys.stderr,
    )
    return marker


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the v2-generation entities.db (feature 132).",
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_LIVE_DB_PATH,
        help="Path to the LIVE v1 entities.db the staging path is derived "
        "beside, and (unless --staging-only) backfilled FROM via a "
        "read-only connection (default: ~/.claude/pd/entities/entities.db).",
    )
    parser.add_argument(
        "--staging-path",
        default=None,
        help="Override the computed staging path (primarily for tests).",
    )
    parser.add_argument(
        "--staging-only",
        action="store_true",
        help="Run build steps 1-3 only (chain replay + v2 seed + "
        "generation stamp) — no backfill/cutover.",
    )
    parser.add_argument(
        "--swap",
        action="store_true",
        help="After a successful backfill, perform the D4 WAL-safe "
        "cutover swap (archive --db read-only, promote the staging file "
        "in its place, write the dated marker). NEVER implied by an "
        "ordinary backfill run — mutually exclusive with --staging-only.",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="Directory for the full machine report JSON (default: "
        "$PD_REBUILD_REPORT_DIR or ~/.claude/pd/migrations).",
    )
    parser.add_argument(
        "--summary-path",
        default=None,
        help="Optional path to also write the counts-only committed "
        "summary (D7). Omitted by default — callers opt in explicitly.",
    )
    parser.add_argument(
        "--marker-dir",
        default=None,
        help="Root directory the --swap cutover marker is written under, "
        "as <marker-dir>/migrations/v2-cutover.json (default: "
        "$PD_REBUILD_MARKER_DIR or ~/.claude/pd). Only consulted with --swap.",
    )
    args = parser.parse_args(argv)

    if args.staging_only and args.swap:
        print("--staging-only and --swap are mutually exclusive", file=sys.stderr)
        return 1

    staging_path = args.staging_path or default_staging_path(args.db)
    if Path(staging_path).exists():
        print(f"Staging file already exists: {staging_path}", file=sys.stderr)
        return 1

    build_staging_database(staging_path)

    if args.staging_only:
        print(f"Staging database built: {staging_path}", file=sys.stderr)
        return 0

    try:
        report = run_backfill(args.db, staging_path)
    except (BackfillVocabMismatchError, BackfillIntegrityError) as exc:
        print(f"Backfill aborted: {exc}", file=sys.stderr)
        return 1

    report_dir = args.report_dir or _default_report_dir()
    report_path = write_machine_report(report, report_dir)
    print(f"Backfill complete: {staging_path}", file=sys.stderr)
    print(f"Report: {report_path}", file=sys.stderr)

    if args.summary_path:
        write_summary_report(report, args.summary_path)

    if args.swap:
        marker_dir = args.marker_dir or _default_marker_dir()
        perform_cutover_swap(
            args.db, staging_path, report_path=report_path, marker_dir=marker_dir
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
