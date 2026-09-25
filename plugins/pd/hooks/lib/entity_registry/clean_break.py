"""Clean-break support: the high-water sweep (B4) and the legacy selector (B5).

Two functions, deliberately split by whether they write:

``select_legacy_entities``  read-only. Which entities the break would touch.
``establish_high_water``    the ONLY sanctioned parse of legacy id text in
                            this effort, and the only writer here.

**Why a parse is sanctioned here and nowhere else.** A legacy entity's
sequence number exists only inside its ``entity_id`` text — that is what
"legacy" means. Reading it once, to raise a counter so the number can never
be reissued, is a migration boundary. Every other read of that text is
inference and is caught by ``doctor.identity_inference``.

After this runs, the counter alone guarantees no reissue and the census is
only a repair floor.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from entity_registry.id_generator import NON_SEQUENCE_KINDS

# The one sanctioned legacy parse. Four historical shapes, in the order a
# real id must be tested:
#   P004-entity-db-redesign / P001   -> 4, 1     (pre-decision project form)
#   134-workflow-rebuild             -> 134
#   00081                            -> 81
#   20260326-030832-some-slug        -> date-shaped; NOT a sequence
_LEGACY_PROJECT = re.compile(r"^P(\d+)")          # deliberately NOT end-anchored:
                                                  # ^P(\d+)$ is the original root
                                                  # cause — it returns nothing for
                                                  # every slug-suffixed project id.
_LEGACY_NUMERIC = re.compile(r"^(\d+)")
_LEGACY_DATE = re.compile(r"^(\d{8})[-T]")

# Kinds whose identity is a timestamp, not a sequence. They have rows in
# ``sequences`` only because an earlier text scan parsed their date prefix
# as a number; no creation path allocates from that counter.
#
# Imported, not redeclared — id_generator owns this fact because it is the
# module that must refuse to compose an id for these kinds (C4).
DATE_SHAPED_KINDS = NON_SEQUENCE_KINDS


def parse_legacy_seq(kind: str, entity_id: str) -> int | None:
    """Return the sequence number encoded in *entity_id*, or None.

    None means "carries no sequence", which is different from 0. The
    previous implementation collapsed both to 0, which is how an
    unparseable id silently lowered a counter.
    """
    if not entity_id:
        return None
    if kind in DATE_SHAPED_KINDS:
        return None
    if _LEGACY_DATE.match(entity_id):
        return None
    m = _LEGACY_PROJECT.match(entity_id) if kind == "project" else None
    if m:
        return int(m.group(1))
    m = _LEGACY_NUMERIC.match(entity_id)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class LegacyRow:
    uuid: str
    workspace_uuid: str
    workspace_root: str | None
    kind: str
    entity_id: str
    status: str | None
    name: str | None

    @property
    def is_live(self) -> bool:
        """Live means someone may still be relying on it.

        Not the complement of a terminal-status set (such as the retired
        brainstorm re-archival guard's): that treats 'dropped' and
        'completed' as live, which counts 133 rows where 15 are actually at
        stake.
        """
        return (self.status or "") in {"open", "active", "planned", ""}


def select_legacy_entities(
    conn: sqlite3.Connection, *, marker_tag: str | None = None
) -> list[LegacyRow]:
    """Every entity flagged ``is_legacy``. Read-only.

    Selection reads the **stated fact** (``entities.is_legacy``, v2
    migration 4), not the absence of an ``entity_display`` row. The
    absence form was the same defect this effort removes — a semantic fact
    derived from a structural accident — and it conflated two unrelated
    populations: an entity whose identity predates the structural model,
    and an entity a buggy non-strict write failed to give a display row.
    Those now differ visibly: the second has ``is_legacy = 0`` and no
    display row, which is a bug, not history — unless its kind has no
    sequence, like a brainstorm, whose identity is its stem and which has
    no display row by design (Wave 2 D3).

    Status cannot be the discriminator either: 165 of the 176 were already
    terminal, so status cannot distinguish "archived by the break" from
    "already dropped".

    Supplying *marker_tag* excludes rows already carrying it; that is the
    idempotence proof.
    """
    sql = """
        SELECT e.uuid, e.workspace_uuid, w.project_root, e.kind, e.entity_id,
               e.status, e.name
        FROM entities e
        LEFT JOIN workspaces w ON w.uuid = e.workspace_uuid
        WHERE e.is_legacy = 1
    """
    params: list[str] = []
    if marker_tag is not None:
        sql += " AND NOT EXISTS (SELECT 1 FROM entity_tags t WHERE t.entity_uuid = e.uuid AND t.tag = ?)"
        params.append(marker_tag)
    sql += " ORDER BY w.project_root, e.kind, e.entity_id"
    return [
        LegacyRow(
            uuid=r["uuid"], workspace_uuid=r["workspace_uuid"],
            workspace_root=r["project_root"], kind=r["kind"],
            entity_id=r["entity_id"], status=r["status"], name=r["name"],
        )
        for r in conn.execute(sql, params)
    ]


def group_by_workspace_kind_status(rows) -> dict[tuple[str | None, str, str], int]:
    """Counts keyed by (workspace_root, kind, status).

    The plan originally asserted the flat total 166+3+1+10. That total is
    measured on a registry 23 other workspaces keep writing to, so it drifts
    and the tempting repair — updating the literal — re-baselines the drift.
    """
    out: dict[tuple[str | None, str, str], int] = {}
    for r in rows:
        key = (r.workspace_root, r.kind, r.status or "(null)")
        out[key] = out.get(key, 0) + 1
    return out


def live_rows_outside(rows, workspace_uuid: str) -> list[LegacyRow]:
    """Live legacy rows belonging to some OTHER workspace.

    A release blocker, not a footnote: the recreate step uses ordinary
    creation commands, which run in the current project's context, so
    nothing recreates another repo's entities.
    """
    return [r for r in rows if r.is_live and r.workspace_uuid != workspace_uuid]


def establish_high_water(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    """Raise every bucket's counter to a value that can never be reissued.

    Returns {(workspace_uuid, kind): next_val} for every bucket present in
    ``entities`` OR ``sequences`` — a bucket with a counter but no surviving
    entity rows still holds a reservation.

    ``next_val = max(stored, parsed_legacy + 1, display_seq + 1)``, never an
    assignment. Assignment and max() are indistinguishable when the function
    is run twice back-to-back, and diverge only when an allocation happens
    in between — at which point assignment lowers the counter below numbers
    already issued. On a shared registry an intervening allocation is the
    expected case, not the edge case.

    The whole sweep is one ``BEGIN IMMEDIATE``. A read-modify-write on
    ``sequences`` racing ``next_sequence_value``'s own BEGIN IMMEDIATE
    silently loses the allocator's increment.
    """
    floors: dict[tuple[str, str], int] = {}

    for r in conn.execute("SELECT workspace_uuid, kind, entity_id FROM entities"):
        seq = parse_legacy_seq(r["kind"], r["entity_id"])
        if seq is None:
            continue
        key = (r["workspace_uuid"], r["kind"])
        floors[key] = max(floors.get(key, 0), seq + 1)

    for r in conn.execute(
        "SELECT e.workspace_uuid, e.kind, d.seq FROM entity_display d "
        "JOIN entities e ON e.uuid = d.uuid"
    ):
        if r["kind"] in DATE_SHAPED_KINDS:
            continue
        key = (r["workspace_uuid"], r["kind"])
        floors[key] = max(floors.get(key, 0), int(r["seq"]) + 1)

    stored = {
        (r["workspace_uuid"], r["entity_type"]): int(r["next_val"])
        for r in conn.execute(
            "SELECT workspace_uuid, entity_type, next_val FROM sequences"
        )
    }

    result: dict[tuple[str, str], int] = {}
    for key in set(floors) | set(stored):
        result[key] = max(floors.get(key, 1), stored.get(key, 1))

    already_in_transaction = conn.in_transaction
    if not already_in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        for (ws, kind), next_val in sorted(result.items()):
            if (ws, kind) in stored:
                conn.execute(
                    "UPDATE sequences SET next_val = ? "
                    "WHERE workspace_uuid = ? AND entity_type = ?",
                    (next_val, ws, kind),
                )
            else:
                conn.execute(
                    "INSERT INTO sequences (workspace_uuid, entity_type, next_val) "
                    "VALUES (?, ?, ?)",
                    (ws, kind, next_val),
                )
        if not already_in_transaction:
            conn.execute("COMMIT")
    except Exception:
        if not already_in_transaction and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    return result
