#!/usr/bin/env python3
"""C22: recreate the live remainder of the legacy registry, in the new shape.

Sources: the structural-identity completion plan
(docs/plans/2026-09-22-structural-identity-completion-plan.md), decisions 2
and 3 and correction 3, and parent plan section C22
(docs/plans/2026-09-20-display-id-ownership-implementation.md).

**Scope.** One workspace: the one whose ``workspaces.project_root`` is
``--workspace-root``. Its live legacy rows (``is_legacy = 1``, not archived,
status open/active/planned/NULL: the archive manifest's predicate,
``clean_break.LegacyRow.is_live``) are recreated. Each becomes a new entity
with a fresh uuid, an ``entity_display`` row and a newly issued number.

- **Groups.** Rows that share ``(kind, legacy sequence)`` are one thing
  registered more than once. The sequence comes from
  ``clean_break.parse_legacy_seq``, the one sanctioned legacy parse. A group
  collapses onto its **survivor**, the row with the later ``created_at``, and
  becomes one entity.
- **Children** of every row in a group move onto that entity
  (``reparent_entity``).
- **Originals** are archived afterwards (``set_archived``: ``is_archived``
  only, status untouched).
- **A different project** sharing the group's legacy number
  (``ARCHIVED_WITHOUT_REPLACEMENT``, with its reason) is archived the same
  way, but the group's new entity does not record it as an original. It
  must hold no children.
- **brainstorm_source** of a project is the survivor's; when the survivor
  has none, its pair's archived half's (an archived row of the group, left
  as it is). The manifest names where it came from.
- **Out of scope:** archived legacy rows stay as they are, children included
  (decision 3's residue). So does every other workspace.

**Modes.**

- ``--plan``: read-only. Prints the manifest as JSON: every original, its
  group and survivor, the rows archived without a replacement and why, the
  new entity's name, slug and brainstorm_source and where each came from,
  the children to move, the residue, the archive list, and any difference
  from ``LOCKED_SCOPE``.
- ``--apply``: recreates, moves and archives, then verifies. Refuses unless
  the derivation reproduces ``LOCKED_SCOPE``. Idempotent and resumable: each
  step checks whether it is already done, so a second run writes nothing and
  an interrupted run finishes on the next.

**Every write is a production path.** The MCP tool functions are called
in-process with their module globals set as each server's startup sets them;
otherwise it is the ``EntityDatabase`` method a tool would call.

- **backlog:** ``entity_server.register_entity(entity_type="backlog",
  auto_id=True, name, status="open", metadata)``, then
  ``workflow_state_server.init_entity_workflow(workflow_phase="open",
  kanban_column="backlog")``. These are ``/pd:add-to-backlog`` steps 3 and 4.
- **project:** ``entity_server.allocate_entity_id``, then
  ``workflow_state_server.init_project_state``. These are
  ``/pd:create-project`` steps 3 and 6, with step 4's directory-number stop.
- **the replacement record** (below): inside the backlog item's registration
  metadata. For a project it is ``EntityDatabase.update_entity(metadata=...)``
  right after ``init_project_state``, which takes no metadata of its own.
- **children:** ``EntityDatabase.reparent_entity``.
- **originals:** ``EntityDatabase.set_archived``.

The script's own SQL only reads.

**The replacement record.** A replacement stores the uuids of the originals
it replaces under the registered metadata key ``RECREATED_FROM_KEY``. A
re-run reads it to know an original is done; a row archived without a
replacement is done once it is archived. A project registered by an
interrupted run before its record was written is recognized by what
``init_project_state`` wrote (its directory, slug and parent) and adopted,
not registered a second time. Its directory is compared by where it
resolves; an unrecorded project with that slug and parent at any other
directory is refused.

**Guard.** A ``--db`` that reaches the live registry directory
``.claude/pd`` is refused in either mode unless
``--i-mean-the-live-registry`` is given. The directory is looked for under
two homes: ``$HOME``'s, and the account's own from the password database,
because a rehearsal points HOME at a scratch directory while the account's
registry stays where it is. "Reaches" means the directory, anything under
it, or its registry file under another name, compared by resolved path and
by file identity, so case variants, firmlinks and hard links are refused
too. ``plan_only`` and ``apply`` enforce it themselves (keyword
``live_registry_confirmed``), so an importer gets the same refusal.

Usage::

    plugins/pd/.venv/bin/python scripts/c22_recreate_live_remainder.py \\
        --db PATH --workspace-root PATH --artifacts-root PATH (--plan | --apply)
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import datetime
import json
import os
import pwd
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path
from types import ModuleType

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "pd"
for _import_root in (_PLUGIN_ROOT / "hooks" / "lib", _PLUGIN_ROOT / "mcp"):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from doctor.checks import check_display_row_invariant  # noqa: E402
from entity_registry.clean_break import parse_legacy_seq, select_legacy_entities  # noqa: E402
from entity_registry.id_generator import _slugify, render_display_id  # noqa: E402
from entity_registry.metadata import RECREATED_FROM_KEY  # noqa: E402
from entity_registry.project_identity import _compute_legacy_project_id  # noqa: E402
from entity_registry.schema_v2 import V2_SCHEMA_VERSION  # noqa: E402

# The live registry's directory, under a home directory. Two homes are
# checked (live_registry_directories): $HOME's and the account's own.
LIVE_REGISTRY_DIR = ".claude/pd"
# The registry file in it, relative to it: ENTITY_DB_PATH's default. A hard
# link to this file is the live registry under a name outside the directory.
LIVE_REGISTRY_FILE = "entities/entities.db"
LIVE_REGISTRY_FLAG = "--i-mean-the-live-registry"

EXIT_OK = 0
EXIT_FAILED = 1           # a production path returned an error, or verification failed
EXIT_REFUSED = 2          # nothing was written
EXIT_SCOPE_DIFFERS = 3    # nothing was written

# The kinds C22 recreates, in the order --apply takes them.
RECREATED_KINDS = ("backlog", "project")

# /pd:add-to-backlog: a new item's status, and step 4's workflow row.
BACKLOG_STATUS = "open"
BACKLOG_WORKFLOW_PHASE = "open"
BACKLOG_KANBAN_COLUMN = "backlog"
# init_project_state's default status for every project it registers.
PROJECT_STATUS = "active"
# A recreated project's features and milestones as init_project_state
# takes them (JSON text). Its children carry the relationship instead.
NO_FEATURES = "[]"
NO_MILESTONES = "[]"

# A legacy project directory is P{NNN}-{slug}. parse_legacy_seq checks the
# number; this pattern only drops the prefix to leave the slug's source.
_LEGACY_PROJECT_DIRECTORY_PREFIX = re.compile(r"^P\d+-")
# /pd:create-project step 4 counts both shapes of project directory on disk:
# {NNN}-{slug} and the legacy P{NNN}-{slug}.
_PROJECT_DIRECTORY_NUMBER = re.compile(r"^P?(\d+)-")

# Decisions 2 and 3 as locked in the completion plan on 2026-09-22, with
# the P001 lineage settled on 2026-09-24 (ARCHIVED_WITHOUT_REPLACEMENT): the
# groups C22 recreates in pedantic-drip. Each is keyed by its survivor's
# type_id, with the rows it absorbs (its replacement records them), the rows
# of its group archived with no replacement (key present only where there
# are any), and the children it holds (on its originals, plus on its
# replacement once moved, so a re-run counts the same). --apply refuses
# unless the derivation reproduces this exactly. Correction 3 says derive at
# execution time; a difference is reported, not guessed around.
LOCKED_SCOPE: dict[str, dict] = {
    "backlog:00059": {"absorbs": [], "children": 0},
    "backlog:00060": {"absorbs": [], "children": 0},
    "backlog:00177": {"absorbs": [], "children": 0},
    "backlog:00180": {"absorbs": [], "children": 0},
    "backlog:00183": {"absorbs": [], "children": 0},
    "backlog:00190": {"absorbs": [], "children": 0},
    "project:P001": {"absorbs": [],
                     "archived_without_replacement": ["project:P001-openclaw-gap-analysis"],
                     "children": 0},
    "project:P002": {"absorbs": [], "children": 5},
    "project:P003": {"absorbs": [], "children": 4},
    "project:P004-entity-db-redesign": {"absorbs": [], "children": 16},
}

# Rows that share a group's legacy number but are a different project from
# its survivor: archived with no replacement, so no replacement's
# RECREATED_FROM_KEY names them (the orchestrator's decision of 2026-09-24
# on decision 2's P001 pair: the outcome stands, both rows archived and one
# new project, but the lineage is accurate). Keyed by type_id; the value is
# the reason --plan's manifest gives. Such a row must hold no children:
# nothing would take them.
ARCHIVED_WITHOUT_REPLACEMENT: dict[str, str] = {
    "project:P001-openclaw-gap-analysis": (
        "a different project from project:P001, registered in this workspace by mistake: "
        "OpenClaw gap analysis is terry_agent's work. Its brainstorm "
        "(docs/brainstorms/20260326-030832-openclaw-gap-analysis.prd.md) is not in this "
        "repository and it has no directory here (docs/projects/P001-openclaw-gap-analysis "
        "does not exist), while project:P001 is the iflow architectural-evolution project "
        "(docs/projects/P001-iflow-arch-evolution/ holds its prd.md and roadmap.md). Decision "
        "2's outcome stands, both rows archived and one new project, but that project's "
        "record names project:P001 alone."
    ),
}

_ENTITY_COLUMNS = ("uuid", "workspace_uuid", "type_id", "entity_id", "kind", "name", "status",
                   "is_archived", "is_deleted", "created_at", "parent_uuid", "artifact_path",
                   "metadata")


class Refusal(Exception):
    """A reason to write nothing."""


class ScopeDiffers(Exception):
    """The derivation does not reproduce LOCKED_SCOPE; nothing was written."""

    def __init__(self, differences: list[str]):
        super().__init__("; ".join(differences))
        self.differences = differences


class ApplyError(Exception):
    """A production path returned an error. The run stops where it is; a
    re-run resumes from there."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def live_registry_directories() -> list[Path]:
    """The live registry's directory (``LIVE_REGISTRY_DIR``) under each home
    a run can mean:

    - **``$HOME``'s**, the one ``~`` expands to.
    - **The account's own**, from the password database. A rehearsal points
      HOME at a scratch directory, which moves ``~`` but not the registry
      the account's pd writes: an absolute ``--db`` under the account's
      home still reaches it.
    """
    homes = [Path(os.path.expanduser("~"))]
    with contextlib.suppress(KeyError):  # this uid has no password entry
        homes.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    return list(dict.fromkeys(home / LIVE_REGISTRY_DIR for home in homes))


def live_registry_reached(db_path: str) -> Path | None:
    """The live registry directory *db_path* reaches, if any: one of
    ``live_registry_directories`` itself, anything under it, or its registry
    file under another name.

    The resolved text (symlinks followed) is compared first. It misses other
    spellings of the same place, so file identity (``os.path.samefile``) is
    compared as well:

    - **Case.** APFS is case-insensitive by default, and ``Path.resolve``
      keeps the case as typed: ``~/.Claude/PD`` is the same directory.
    - **Firmlinks.** ``/System/Volumes/Data/Users/...`` is ``/Users/...``.
    - **Hard links.** A hard link to the registry file can have any name.

    A path that does not exist yet is judged by those of its ancestors that do.
    """
    target = Path(os.path.expanduser(db_path)).absolute()
    resolved_target = target.resolve()
    for live_dir in live_registry_directories():
        resolved_live = live_dir.resolve()
        if resolved_target == resolved_live or resolved_live in resolved_target.parents:
            return live_dir
        same_file_checks = [(ancestor, live_dir) for ancestor in (target, *target.parents)]
        same_file_checks.append((target, live_dir / LIVE_REGISTRY_FILE))
        for path, live in same_file_checks:
            with contextlib.suppress(OSError):  # either side missing
                if os.path.samefile(path, live):
                    return live_dir
    return None


def refuse_the_live_registry(db_path: str, *, live_registry_confirmed: bool) -> None:
    """Raise Refusal for a *db_path* that reaches the live registry, unless
    the caller confirmed it (``--i-mean-the-live-registry``)."""
    live_dir = live_registry_reached(db_path)
    if live_dir is not None and not live_registry_confirmed:
        raise Refusal(f"{db_path} reaches the live registry {live_dir} (under $HOME or the "
                      f"account's home, compared by path and by file identity). A rehearsal "
                      f"runs on a copy; to write the live file, pass {LIVE_REGISTRY_FLAG}.")


def open_read_only(db_path: str, *, other_connection_open: bool = False) -> sqlite3.Connection:
    """A connection that cannot write.

    With no ``-wal`` beside the file and no other connection open, this is
    ``immutable=1``: plain ``mode=ro`` there fails (SQLite 3.51) or creates
    ``-wal`` and ``-shm`` (3.53). Otherwise it is ``mode=ro``, which reads
    the WAL; ``immutable=1`` would miss another connection's writes.
    """
    live_wal = other_connection_open or os.path.exists(f"{db_path}-wal")
    query = "mode=ro" if live_wal else "mode=ro&immutable=1"
    conn = sqlite3.connect(f"file:{urllib.parse.quote(db_path)}?{query}", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def decoded_metadata(raw) -> dict:
    """The ``metadata`` column as a dict.

    Some April-generation backlog rows hold their metadata JSON-encoded twice:
    a JSON string whose content is the object. ``parse_metadata`` reads that
    as ``{}``; decoding a string result once more recovers the description.
    """
    value = raw
    for _ in range(2):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


@dataclasses.dataclass(frozen=True)
class Row:
    """An entity row as C22 reads it."""

    uuid: str
    workspace_uuid: str
    type_id: str
    entity_id: str
    kind: str
    name: str | None
    status: str | None
    is_archived: bool
    is_deleted: bool
    created_at: str
    parent_uuid: str | None
    artifact_path: str | None
    metadata: dict

    @classmethod
    def of(cls, record: sqlite3.Row) -> "Row":
        values = {column: record[column] for column in _ENTITY_COLUMNS}
        values["is_archived"] = bool(values["is_archived"])
        values["is_deleted"] = bool(values["is_deleted"])
        values["metadata"] = decoded_metadata(values["metadata"])
        return cls(**values)

    def summary(self) -> dict:
        return {"uuid": self.uuid, "type_id": self.type_id, "name": self.name,
                "status": self.status, "is_archived": self.is_archived,
                "created_at": self.created_at, "parent_uuid": self.parent_uuid,
                "artifact_path": self.artifact_path}


def _select(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return ", ".join(f"{prefix}{column}" for column in _ENTITY_COLUMNS)


def _entity_by_uuid(conn: sqlite3.Connection, entity_uuid: str) -> Row | None:
    record = conn.execute(f"SELECT {_select()} FROM entities WHERE uuid = ?",
                          (entity_uuid,)).fetchone()
    return Row.of(record) if record is not None else None


def _children_of(conn: sqlite3.Connection, parent_uuid: str) -> list[Row]:
    return [Row.of(r) for r in conn.execute(
        f"SELECT {_select()} FROM entities WHERE parent_uuid = ? ORDER BY type_id",
        (parent_uuid,))]


def check_schema(conn: sqlite3.Connection) -> None:
    """Refuse a file this build's EntityDatabase would migrate on open."""
    stated = dict(conn.execute(
        "SELECT key, value FROM _metadata WHERE key IN ('schema_generation', 'schema_version')"
    ).fetchall())
    expected = {"schema_generation": "v2", "schema_version": str(V2_SCHEMA_VERSION)}
    if stated != expected:
        raise Refusal(f"the file states {stated}; this build reads and writes {expected} "
                      f"and would migrate anything else on open")


@dataclasses.dataclass(frozen=True)
class Workspace:
    uuid: str
    root: str
    legacy_project_id: str


def find_workspace(conn: sqlite3.Connection, workspace_root: str) -> Workspace:
    """The workspaces row for *workspace_root*, cross-checked against what a
    server started there resolves: ``project_id`` from git
    (``_compute_legacy_project_id``) and ``workspace_uuid`` from
    ``.claude/pd/workspace.json``. A disagreement would make the in-process
    tools allocate in one workspace and register in another."""
    root = os.path.abspath(workspace_root)
    rows = conn.execute("SELECT uuid, project_id_legacy FROM workspaces WHERE project_root = ?",
                        (root,)).fetchall()
    if len(rows) != 1:
        raise Refusal(f"{len(rows)} workspaces rows have project_root {root!r}; C22 needs one")
    workspace = Workspace(rows[0]["uuid"], root, rows[0]["project_id_legacy"])
    computed = _compute_legacy_project_id(root)
    if computed != workspace.legacy_project_id:
        raise Refusal(f"workspace {workspace.uuid} records project_id_legacy "
                      f"{workspace.legacy_project_id!r}, but {root} computes {computed!r}")
    sharing = conn.execute("SELECT COUNT(*) FROM workspaces WHERE project_id_legacy = ?",
                           (workspace.legacy_project_id,)).fetchone()[0]
    if sharing != 1:
        raise Refusal(f"{sharing} workspaces share project_id_legacy "
                      f"{workspace.legacy_project_id!r}; allocation by it is ambiguous")
    workspace_file = Path(root, ".claude", "pd", "workspace.json")
    if workspace_file.is_file():
        stated = json.loads(workspace_file.read_text(encoding="utf-8")).get("workspace_uuid")
        if stated != workspace.uuid:
            raise Refusal(f"{workspace_file} names workspace {stated!r}, the registry row "
                          f"for {root} is {workspace.uuid!r}")
    return workspace


def recorded_replacements(conn: sqlite3.Connection, workspace: Workspace) -> dict[str, Row]:
    """Original uuid -> the replacement whose record names it."""
    found: dict[str, Row] = {}
    for record in conn.execute(
            f"SELECT {_select()} FROM entities WHERE workspace_uuid = ? AND is_legacy = 0 "
            f"AND kind IN ({', '.join('?' for _ in RECREATED_KINDS)})",
            (workspace.uuid, *RECREATED_KINDS)):
        row = Row.of(record)
        originals = row.metadata.get(RECREATED_FROM_KEY)
        if originals is None:
            continue
        if not isinstance(originals, list) or not all(isinstance(u, str) for u in originals):
            raise Refusal(f"{row.type_id}'s {RECREATED_FROM_KEY} is not a list of uuids: "
                          f"{originals!r}")
        if row.is_deleted:
            raise Refusal(f"replacement {row.type_id} is deleted; restore it or resolve its "
                          f"originals by hand before re-running")
        for original_uuid in originals:
            if original_uuid in found:
                raise Refusal(f"both {found[original_uuid].type_id} and {row.type_id} record "
                              f"that they replace {original_uuid}")
            found[original_uuid] = row
    return found


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Group:
    kind: str
    legacy_seq: int
    survivor: Row
    absorbed: list[Row]
    # In scope, a different project (ARCHIVED_WITHOUT_REPLACEMENT): archived,
    # recorded by no replacement.
    archived_without_replacement: list[Row]
    left_as_is: list[Row]            # same (kind, legacy seq), out of scope
    children: list[Row]              # of the survivor and absorbed rows: they move
    residue: dict[str, list[Row]]    # a left_as_is row's type_id -> its children: they stay
    new: dict                        # the replacement, as it will be created
    replacement: Row | None          # a recorded replacement: recreated already
    unrecorded_project: tuple[Row, int] | None  # registered before its record, and its seq
    flags: list[str]

    @property
    def originals(self) -> list[Row]:
        return [self.survivor, *self.absorbed]


@dataclasses.dataclass
class Plan:
    workspace: Workspace
    artifacts_root: str
    buckets: dict[str, dict]
    legacy_numbers: dict[str, set[int]]
    groups: list[Group]


def _created(row: Row) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(row.created_at)
    except (TypeError, ValueError):
        raise Refusal(f"{row.type_id} has an unreadable created_at {row.created_at!r}") from None


def _bucket_marks(conn: sqlite3.Connection, workspace: Workspace, kind: str) -> tuple[dict, set[int]]:
    counter = conn.execute("SELECT next_val FROM sequences WHERE workspace_uuid = ? "
                           "AND entity_type = ?", (workspace.uuid, kind)).fetchone()
    legacy_numbers = {parse_legacy_seq(kind, r["entity_id"]) for r in conn.execute(
        "SELECT entity_id FROM entities WHERE workspace_uuid = ? AND kind = ? AND is_legacy = 1",
        (workspace.uuid, kind))} - {None}
    display_high_water = conn.execute(
        "SELECT MAX(d.seq) FROM entity_display d JOIN entities e ON e.uuid = d.uuid "
        "WHERE e.workspace_uuid = ? AND e.kind = ?", (workspace.uuid, kind)).fetchone()[0]
    marks = {"counter": counter["next_val"] if counter else None,
             "legacy_high_water": max(legacy_numbers, default=None),
             "display_high_water": display_high_water}
    return marks, legacy_numbers


def _backlog_spec(survivor: Row) -> tuple[dict, list[str]]:
    if not (survivor.name or "").strip():
        raise Refusal(f"{survivor.type_id} has no name to carry over")
    description = survivor.metadata.get("description")
    if isinstance(description, str) and description.strip():
        description_source, flags = "metadata", []
    else:
        description, description_source = survivor.name, "name"
        flags = [f"{survivor.type_id} has no metadata description; its name is carried as the "
                 f"description (a /pd:add-to-backlog item always has one)"]
    return {
        "entity_type": "backlog",
        "name": survivor.name,
        # What register_entity's auto_id derives from the name.
        "slug": _slugify(survivor.name) or "unnamed",
        "status": BACKLOG_STATUS,
        "description": description,
        "description_source": description_source,
    }, flags


def _directory_of(row: Row) -> str:
    if not row.artifact_path:
        return ""
    return os.path.basename(row.artifact_path.rstrip("/"))


def _brainstorm_source_of(row: Row) -> str | None:
    value = row.metadata.get("brainstorm_source")
    return value if isinstance(value, str) and value else None


def _carried_brainstorm_source(survivor: Row, parent: Row | None, absorbed: list[Row],
                               left_as_is: list[Row]) -> tuple[str | None, str, list[str]]:
    """The replacement's brainstorm_source, where it came from, and flags.

    - **The survivor's own**, when its metadata has one.
    - **Else its pair's archived half's**: an archived row of the group,
      left as it is. It is the same project registered twice, and its
      metadata holds the value the survivor's lacks (the orchestrator's
      decision of 2026-09-24, for P002 and P003). It is flagged when it does
      not name the artifact of the survivor's parent brainstorm.
    - **Not an absorbed row's** (flagged), and never a row archived without
      a replacement: that is another project, and is not consulted.
    """
    own = _brainstorm_source_of(survivor)
    if own is not None:
        return own, f"the metadata of {survivor.type_id}, the survivor", []
    flags = [f"brainstorm_source {value!r} of {row.type_id} is not carried: it comes from the "
             f"survivor's metadata, or else from an archived half of its pair"
             for row in absorbed if (value := _brainstorm_source_of(row)) is not None]
    archived_halves = {row.type_id: value for row in left_as_is
                       if row.is_archived and not row.is_deleted
                       and (value := _brainstorm_source_of(row)) is not None}
    if len(set(archived_halves.values())) > 1:
        raise Refusal(f"the archived halves of {survivor.type_id}'s pair carry different "
                      f"brainstorm_source values {archived_halves}, and its own metadata has "
                      f"none: there is no one value to carry")
    if not archived_halves:
        return None, (f"none: neither {survivor.type_id}'s metadata nor an archived half of "
                      f"its pair has one"), flags
    value = next(iter(archived_halves.values()))
    halves = ", ".join(archived_halves)
    origin = (f"the metadata of {halves}, the archived half of {survivor.type_id}'s pair: "
              f"{survivor.type_id}'s own metadata has none")
    if parent is not None and parent.artifact_path == value:
        origin += f". It names the artifact of {survivor.type_id}'s parent, {parent.type_id}"
    else:
        flags.append(f"brainstorm_source {value!r}, carried from {halves}, does not name the "
                     f"artifact of {survivor.type_id}'s parent "
                     + (f"{parent.type_id} ({parent.artifact_path!r})" if parent else
                        "(it has none)"))
    return value, origin, flags


def _project_spec(conn: sqlite3.Connection, workspace: Workspace, group_seq: int,
                  survivor: Row, absorbed: list[Row],
                  left_as_is: list[Row]) -> tuple[dict, list[str]]:
    directory = _directory_of(survivor)
    if parse_legacy_seq("project", directory) != group_seq:
        raise Refusal(f"{survivor.type_id}'s artifact_path {survivor.artifact_path!r} does not "
                      f"end in a P{group_seq:03d}-<slug> directory to name its replacement from")
    slug_source = _LEGACY_PROJECT_DIRECTORY_PREFIX.sub("", directory, count=1)
    slug = _slugify(slug_source)
    if not slug:
        raise Refusal(f"{survivor.type_id}'s directory {directory!r} leaves no slug")
    parent = None
    if survivor.parent_uuid:
        parent = _entity_by_uuid(conn, survivor.parent_uuid)
        if parent is None or parent.is_deleted or parent.workspace_uuid != workspace.uuid:
            raise Refusal(f"{survivor.type_id}'s parent {survivor.parent_uuid} is missing, "
                          f"deleted or in another workspace")
    flags = []
    for other in (*absorbed, *left_as_is):
        if _directory_of(other) != directory:
            flags.append(
                f"{other.type_id} (status {other.status!r}, directory {_directory_of(other)!r}) "
                f"is grouped with {survivor.type_id} (status {survivor.status!r}, directory "
                f"{directory!r}) by legacy number {group_seq}: the directories name different "
                f"projects")
    brainstorm_source, brainstorm_source_origin, brainstorm_flags = _carried_brainstorm_source(
        survivor, parent, absorbed, left_as_is)
    flags.extend(brainstorm_flags)
    if survivor.status != PROJECT_STATUS:
        flags.append(f"{survivor.type_id} has status {survivor.status!r}; init_project_state "
                     f"registers its replacement {PROJECT_STATUS!r}")
    listed = survivor.metadata.get("features")
    if isinstance(listed, list) and listed:
        flags.append(f"{survivor.type_id}'s metadata lists {len(listed)} features; its "
                     f"replacement starts with features {NO_FEATURES} and its children are "
                     f"re-parented instead")
    return {
        "entity_type": "project",
        "slug": slug,
        "slug_source": f"{directory!r}, the directory of {survivor.type_id}'s artifact_path, "
                       f"without its legacy P-number prefix",
        # How init_project_state names a project; --apply reports the registered name.
        "name": slug.replace("-", " ").title(),
        "status": PROJECT_STATUS,
        "parent_uuid": survivor.parent_uuid,
        "parent": parent.type_id if parent else None,
        "brainstorm_source": brainstorm_source,
        "brainstorm_source_origin": brainstorm_source_origin,
        "features": json.loads(NO_FEATURES),
        "milestones": json.loads(NO_MILESTONES),
    }, flags


def _unrecorded_project(conn: sqlite3.Connection, workspace: Workspace, artifacts_root: str,
                        new: dict) -> tuple[Row, int] | None:
    """A project an interrupted run registered with init_project_state but
    did not record: same workspace, slug and parent, and the artifact_path
    init_project_state records for the number it holds.

    - **Directories compare by where they resolve** (``os.path.realpath``,
      as init_project_state's containment check does), so a resume that
      spells ``--artifacts-root`` through a symlink still finds the project.
    - **Anywhere else is refused.** An unrecorded project with this slug and
      parent at a directory this run's artifacts root does not reach would
      otherwise be passed over: the allocator would issue a second number
      for the same originals and leave the first project unrecorded.
    """
    found, elsewhere = [], []
    for record in conn.execute(
            f"SELECT {_select('e')}, d.seq AS display_seq, d.slug AS display_slug "
            f"FROM entities e JOIN entity_display d ON d.uuid = e.uuid "
            f"WHERE e.workspace_uuid = ? AND e.kind = 'project' AND e.is_legacy = 0 "
            f"AND e.is_deleted = 0 AND d.slug = ?", (workspace.uuid, new["slug"])):
        row = Row.of(record)
        if RECREATED_FROM_KEY in row.metadata or row.parent_uuid != new["parent_uuid"]:
            continue
        directory = os.path.join(artifacts_root, "projects",
                                 render_display_id("project", record["display_seq"],
                                                   record["display_slug"]))
        if row.artifact_path and os.path.realpath(row.artifact_path) == os.path.realpath(directory):
            found.append((row, record["display_seq"]))
        else:
            elsewhere.append((row, directory))
    if elsewhere:
        raise Refusal("; ".join(
            f"{row.type_id} has the slug {new['slug']!r} and parent {new['parent']!r} of a "
            f"planned replacement and no record, but is registered at {row.artifact_path!r}, "
            f"not at {directory!r} under this run's --artifacts-root. If an interrupted run "
            f"registered it, re-run with that run's --artifacts-root; otherwise resolve it by hand"
            for row, directory in elsewhere))
    if len(found) > 1:
        raise Refusal(f"{len(found)} unrecorded projects look like the replacement for slug "
                      f"{new['slug']!r}: {[row.type_id for row, _ in found]}")
    return found[0] if found else None


def derive_plan(conn: sqlite3.Connection, workspace_root: str, artifacts_root: str) -> Plan:
    """Everything --apply will do, read from the registry. Writes nothing."""
    workspace = find_workspace(conn, workspace_root)
    rows = {r["uuid"]: Row.of(r) for r in conn.execute(
        f"SELECT {_select()} FROM entities WHERE workspace_uuid = ? AND is_legacy = 1",
        (workspace.uuid,))}
    recorded = recorded_replacements(conn, workspace)
    # An archived row stays in scope once C22 has done it, so a re-run
    # derives the same groups: an original a replacement records, or a row
    # C22 archives without a replacement.
    in_scope = {
        legacy.uuid for legacy in select_legacy_entities(conn)
        if legacy.workspace_uuid == workspace.uuid and legacy.is_live
        and not rows[legacy.uuid].is_deleted
        and (not rows[legacy.uuid].is_archived or legacy.uuid in recorded
             or rows[legacy.uuid].type_id in ARCHIVED_WITHOUT_REPLACEMENT)
    }

    keyed: dict[tuple[str, int], list[Row]] = {}
    for row in rows.values():
        legacy_seq = parse_legacy_seq(row.kind, row.entity_id)
        if row.uuid in in_scope:
            if row.kind not in RECREATED_KINDS:
                raise Refusal(f"live legacy row {row.type_id} is a {row.kind}; C22 recreates "
                              f"{' and '.join(RECREATED_KINDS)} rows only")
            if legacy_seq is None:
                raise Refusal(f"live legacy row {row.type_id} carries no legacy sequence to "
                              f"group it by")
        if legacy_seq is not None:
            keyed.setdefault((row.kind, legacy_seq), []).append(row)

    buckets: dict[str, dict] = {}
    legacy_numbers: dict[str, set[int]] = {}
    for kind in RECREATED_KINDS:
        buckets[kind], legacy_numbers[kind] = _bucket_marks(conn, workspace, kind)

    groups = []
    group_keys = {(rows[u].kind, parse_legacy_seq(rows[u].kind, rows[u].entity_id)) for u in in_scope}
    for kind, legacy_seq in sorted(group_keys, key=lambda k: (RECREATED_KINDS.index(k[0]), k[1])):
        members = sorted(keyed[(kind, legacy_seq)], key=lambda r: r.type_id)
        latest = max(_created(r) for r in members)
        at_latest = [r for r in members if _created(r) == latest]
        if len(at_latest) > 1:
            raise Refusal(f"{[r.type_id for r in at_latest]} share the latest created_at of "
                          f"their group; no survivor")
        survivor = at_latest[0]
        if survivor.uuid not in in_scope:
            raise Refusal(
                f"the later-created row of {kind} group {legacy_seq}, {survivor.type_id}, is out "
                f"of scope (archived, finished or deleted) while "
                f"{[r.type_id for r in members if r.uuid in in_scope]} are live: the survivor "
                f"rule would pick a row decision 2 does not recreate")
        if survivor.type_id in ARCHIVED_WITHOUT_REPLACEMENT:
            raise Refusal(f"the later-created row of {kind} group {legacy_seq}, "
                          f"{survivor.type_id}, is to be archived without a replacement "
                          f"(ARCHIVED_WITHOUT_REPLACEMENT): the survivor rule would recreate it")
        others = [r for r in members if r.uuid in in_scope and r is not survivor]
        absorbed = [r for r in others if r.type_id not in ARCHIVED_WITHOUT_REPLACEMENT]
        archived_without_replacement = [r for r in others
                                        if r.type_id in ARCHIVED_WITHOUT_REPLACEMENT]
        left_as_is = [r for r in members if r.uuid not in in_scope]
        for row in archived_without_replacement:
            held = _children_of(conn, row.uuid)
            if held:
                raise Refusal(f"{row.type_id} is to be archived without a replacement, but holds "
                              f"children {[c.type_id for c in held]}: nothing would take them")

        children = []
        for original in (survivor, *absorbed):
            for child in _children_of(conn, original.uuid):
                if child.is_deleted or child.workspace_uuid != workspace.uuid:
                    raise Refusal(f"child {child.type_id} of {original.type_id} is deleted or in "
                                  f"another workspace; reparent_entity cannot move it")
                children.append(child)
        residue = {r.type_id: _children_of(conn, r.uuid) for r in left_as_is}
        residue = {parent: kids for parent, kids in residue.items() if kids}

        if kind == "backlog":
            new, flags = _backlog_spec(survivor)
        else:
            new, flags = _project_spec(conn, workspace, legacy_seq, survivor, absorbed,
                                       left_as_is)

        replacements = {recorded[r.uuid].uuid: recorded[r.uuid]
                        for r in (survivor, *absorbed) if r.uuid in recorded}
        if len(replacements) > 1:
            raise Refusal(f"the originals of {survivor.type_id}'s group record different "
                          f"replacements: {sorted(r.type_id for r in replacements.values())}")
        replacement = next(iter(replacements.values()), None)
        if replacement is not None:
            expected = sorted(r.uuid for r in (survivor, *absorbed))
            if sorted(replacement.metadata[RECREATED_FROM_KEY]) != expected or \
                    replacement.kind != kind:
                raise Refusal(f"{replacement.type_id} records {replacement.metadata[RECREATED_FROM_KEY]} "
                              f"but {survivor.type_id}'s group is {expected}")
        unrecorded = None
        if replacement is None and kind == "project":
            unrecorded = _unrecorded_project(conn, workspace, artifacts_root, new)

        groups.append(Group(kind, legacy_seq, survivor, absorbed, archived_without_replacement,
                            left_as_is, children, residue, new, replacement, unrecorded, flags))
    return Plan(workspace, artifacts_root, buckets, legacy_numbers, groups)


def plan_manifest(plan: Plan) -> dict:
    def replacement_of(group: Group) -> dict | None:
        if group.replacement is not None:
            return {"type_id": group.replacement.type_id, "uuid": group.replacement.uuid,
                    "recorded": True}
        if group.unrecorded_project is not None:
            row, _seq = group.unrecorded_project
            return {"type_id": row.type_id, "uuid": row.uuid, "recorded": False,
                    "note": "registered by an interrupted run before its record; --apply adopts it"}
        return None

    return {
        "workspace": dataclasses.asdict(plan.workspace),
        "artifacts_root": plan.artifacts_root,
        "buckets": plan.buckets,
        "groups": [{
            "kind": g.kind,
            "legacy_seq": g.legacy_seq,
            "survivor": g.survivor.summary(),
            "absorbed": [r.summary() for r in g.absorbed],
            "archived_without_replacement": [
                {**r.summary(), "reason": ARCHIVED_WITHOUT_REPLACEMENT[r.type_id]}
                for r in g.archived_without_replacement],
            "left_as_is": [r.summary() for r in g.left_as_is],
            "children_to_move": [{"uuid": c.uuid, "type_id": c.type_id} for c in g.children],
            "residue": [{"parent": parent, "children": [c.type_id for c in kids]}
                        for parent, kids in g.residue.items()],
            "new": g.new,
            "replacement": replacement_of(g),
            "flags": g.flags,
        } for g in plan.groups],
        "archive": sorted(r.type_id for g in plan.groups
                          for r in (*g.originals, *g.archived_without_replacement)),
    }


def scope_differences(conn: sqlite3.Connection, plan: Plan, locked_scope: dict) -> list[str]:
    derived = {}
    for group in plan.groups:
        children = len(group.children)
        if group.replacement is not None:
            children += len(_children_of(conn, group.replacement.uuid))
        derived[group.survivor.type_id] = {
            "absorbs": [r.type_id for r in group.absorbed],
            "archived_without_replacement": [r.type_id
                                             for r in group.archived_without_replacement],
            "children": children}
    differences = []
    for survivor in sorted(set(derived) | set(locked_scope)):
        if survivor not in derived:
            differences.append(f"{survivor}: locked, not derived")
        elif survivor not in locked_scope:
            differences.append(f"{survivor}: derived, not locked")
        else:
            found, locked = derived[survivor], locked_scope[survivor]
            if sorted(found["absorbs"]) != sorted(locked["absorbs"]):
                differences.append(f"{survivor}: absorbs {found['absorbs']}, "
                                   f"locked {locked['absorbs']}")
            locked_unreplaced = locked.get("archived_without_replacement", [])
            if sorted(found["archived_without_replacement"]) != sorted(locked_unreplaced):
                differences.append(f"{survivor}: archives without a replacement "
                                   f"{found['archived_without_replacement']}, "
                                   f"locked {locked_unreplaced}")
            if found["children"] != locked["children"]:
                differences.append(f"{survivor}: {found['children']} children, "
                                   f"locked {locked['children']}")
    return differences


def _project_directory_numbers(artifacts_root: str) -> dict[str, int]:
    projects = Path(artifacts_root, "projects")
    if not projects.is_dir():
        return {}
    numbers = {}
    for entry in projects.iterdir():
        match = _PROJECT_DIRECTORY_NUMBER.match(entry.name)
        if entry.is_dir() and match:
            numbers[entry.name] = int(match.group(1))
    return numbers


def _refuse_numbers_at_or_below_directories(artifacts_root: str, seq: int) -> None:
    """/pd:create-project step 4: a number at or below an existing project
    directory's is sequence drift. Stop before anything is created with it."""
    blocking = sorted(name for name, number in _project_directory_numbers(artifacts_root).items()
                      if number >= seq)
    if blocking:
        raise Refusal(f"project number {seq} is at or below existing project directories "
                      f"{blocking} under {artifacts_root}/projects: sequence drift; correct the "
                      f"workspace's project counter first")


def preflight(plan: Plan) -> None:
    """Refusals that need no write to detect."""
    for kind in RECREATED_KINDS:
        pending = [g for g in plan.groups if g.kind == kind
                   and g.replacement is None and g.unrecorded_project is None]
        if not pending:
            continue
        marks = plan.buckets[kind]
        if marks["counter"] is None:
            raise Refusal(f"the {kind} bucket has no sequences counter; B4's high-water sweep "
                          f"has not run on this file")
        if marks["legacy_high_water"] is not None and marks["counter"] <= marks["legacy_high_water"]:
            raise Refusal(f"the {kind} counter {marks['counter']} does not clear its legacy "
                          f"high-water mark {marks['legacy_high_water']}; B4 has not run")
        if kind == "project":
            _refuse_numbers_at_or_below_directories(plan.artifacts_root, marks["counter"])


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Context:
    db: object                        # entity_registry.database.EntityDatabase
    entity_server: ModuleType
    workflow_state_server: ModuleType
    reader: sqlite3.Connection
    workspace: Workspace
    artifacts_root: str


_SERVER_GLOBALS = ("_db", "_db_unavailable", "_project_root", "_artifacts_root", "_project_id",
                   "_workspace_uuid")


@contextlib.contextmanager
def running_servers(db_path: str, workspace: Workspace, artifacts_root: str):
    """Both MCP servers' module globals, set as their startup sets them, over
    one EntityDatabase; restored on exit.

    Startup's other work (upserting the git project row, claiming
    ``__unknown__`` entities, the artifact backfills, the workflow engines)
    is not needed by the tools called here and is not run: it writes, and
    none of it is C22's to do. ``_artifacts_root`` is ``--artifacts-root``
    rather than the workspace config's, so a rehearsal writes its project
    directories to a scratch root.
    """
    saved_environment = {name: os.environ.get(name) for name in ("ENTITY_DB_PATH", "PROJECT_ROOT")}
    os.environ["ENTITY_DB_PATH"] = db_path
    os.environ["PROJECT_ROOT"] = workspace.root
    import entity_server
    import workflow_state_server
    from entity_registry.database import EntityDatabase
    from pd_config.config import read_config

    modules = (entity_server, workflow_state_server)
    saved_globals = [{name: getattr(module, name) for name in _SERVER_GLOBALS} for module in modules]
    saved_config = entity_server._config
    db = EntityDatabase(db_path)
    reader = None
    try:
        for module in modules:
            module._db = db
            module._db_unavailable = False
            module._project_root = workspace.root
            module._artifacts_root = artifacts_root
            module._project_id = workspace.legacy_project_id
            module._workspace_uuid = workspace.uuid
        entity_server._config = read_config(workspace.root)
        reader = open_read_only(db_path, other_connection_open=True)
        yield Context(db, entity_server, workflow_state_server, reader, workspace, artifacts_root)
    finally:
        if reader is not None:
            reader.close()
        for module, values in zip(modules, saved_globals):
            for name, value in values.items():
                setattr(module, name, value)
        entity_server._config = saved_config
        db.close()
        for name, value in saved_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _run_tool(coroutine) -> str:
    return asyncio.run(coroutine)


def _tool_reply(result: str) -> dict:
    """A tool's JSON reply; a reply that is not a JSON object is an error text."""
    try:
        value = json.loads(result)
    except ValueError:
        return {"error": True, "message": result}
    return value if isinstance(value, dict) else {"error": True, "message": result}


def _find_replacement(context: Context, group: Group) -> Row:
    replacement = recorded_replacements(context.reader, context.workspace).get(group.survivor.uuid)
    if replacement is None:
        raise ApplyError(f"no recorded replacement for {group.survivor.type_id} after creating it")
    return replacement


def _register_backlog_item(context: Context, group: Group) -> Row:
    new = group.new
    result = _run_tool(context.entity_server.register_entity(
        entity_type="backlog", auto_id=True, name=new["name"], status=new["status"],
        metadata={"description": new["description"],
                  RECREATED_FROM_KEY: [o.uuid for o in group.originals]},
    ))
    if not result.startswith("Registered: "):
        raise ApplyError(f"register_entity for {group.survivor.type_id}: {result}")
    return _find_replacement(context, group)


def _ensure_backlog_workflow(context: Context, replacement: Row) -> None:
    exists = context.reader.execute("SELECT 1 FROM workflow_phases WHERE type_id = ?",
                                    (replacement.type_id,)).fetchone()
    if exists:
        return
    reply = _tool_reply(_run_tool(context.workflow_state_server.init_entity_workflow(
        type_id=replacement.type_id, workflow_phase=BACKLOG_WORKFLOW_PHASE,
        kanban_column=BACKLOG_KANBAN_COLUMN)))
    if reply.get("error"):
        raise ApplyError(f"init_entity_workflow for {replacement.type_id}: {reply}")


def _record_replacement(context: Context, replacement_uuid: str, originals: list[Row]) -> None:
    context.db.update_entity(replacement_uuid,
                             metadata={RECREATED_FROM_KEY: [o.uuid for o in originals]},
                             workspace_uuid=context.workspace.uuid)


def _init_project(context: Context, group: Group, entity_id: str, slug: str,
                  project_dir: str | None = None) -> str:
    """init_project_state for the allocated *entity_id*, in *project_dir*
    (by default ``{artifacts_root}/projects/{entity_id}``); returns the
    project uuid."""
    new = group.new
    arguments = {
        "project_dir": project_dir or os.path.join(context.artifacts_root, "projects", entity_id),
        # init_project_state composes {project_id}-{slug}: pass the number as
        # the allocator rendered it, not the full id (create-project step 6).
        "project_id": entity_id.removesuffix(f"-{slug}"),
        "slug": slug,
        "features": NO_FEATURES,
        "milestones": NO_MILESTONES,
        "brainstorm_source": new["brainstorm_source"],
        "parent_uuid": new["parent_uuid"],
    }
    reply = _tool_reply(_run_tool(context.workflow_state_server.init_project_state(**arguments)))
    if reply.get("error") or not reply.get("created"):
        raise ApplyError(f"init_project_state for {group.survivor.type_id}: {reply}")
    return reply["project_uuid"]


def _create_project(context: Context, group: Group) -> Row:
    reply = _tool_reply(_run_tool(context.entity_server.allocate_entity_id(
        entity_type="project", name=group.new["slug"])))
    if reply.get("error"):
        raise ApplyError(f"allocate_entity_id for {group.survivor.type_id}: {reply}")
    if reply["slug"] != group.new["slug"]:
        raise ApplyError(f"allocate_entity_id returned slug {reply['slug']!r}, the plan says "
                         f"{group.new['slug']!r}; number {reply['seq']} is spent, nothing registered")
    try:
        _refuse_numbers_at_or_below_directories(context.artifacts_root, reply["seq"])
    except Refusal as drift:
        raise ApplyError(f"{drift}; number {reply['seq']} is spent, nothing registered") from None
    project_uuid = _init_project(context, group, reply["entity_id"], reply["slug"])
    _record_replacement(context, project_uuid, group.originals)
    return _find_replacement(context, group)


def _adopt_project(context: Context, group: Group) -> Row:
    """Finish a project an interrupted run registered but did not record:
    the same init_project_state call resumes its own registration. It is
    given the directory as that run recorded it, because init_project_state
    resumes only a row whose artifact_path is the project_dir it is given."""
    row, seq = group.unrecorded_project
    project_uuid = _init_project(context, group, render_display_id("project", seq, group.new["slug"]),
                                 group.new["slug"], project_dir=row.artifact_path)
    if project_uuid != row.uuid:
        raise ApplyError(f"init_project_state resumed {project_uuid}, expected {row.uuid}")
    _record_replacement(context, project_uuid, group.originals)
    return _find_replacement(context, group)


def _recreate_group(context: Context, group: Group) -> dict:
    """One group, end to end: its replacement, its children, its originals,
    then its rows archived without a replacement."""
    if group.replacement is not None:
        replacement, how = group.replacement, "already recreated"
    elif group.kind == "backlog":
        replacement, how = _register_backlog_item(context, group), "created"
    elif group.unrecorded_project is not None:
        replacement, how = _adopt_project(context, group), "adopted"
    else:
        replacement, how = _create_project(context, group), "created"
    if group.kind == "backlog":
        _ensure_backlog_workflow(context, replacement)

    moved = []
    for child in group.children:
        context.db.reparent_entity(child.uuid, replacement.uuid,
                                   workspace_uuid=context.workspace.uuid)
        moved.append(child.type_id)
    archived = []
    for original in group.originals:
        if not original.is_archived:
            context.db.set_archived(original.type_id, workspace_uuid=context.workspace.uuid)
            archived.append(original.type_id)
    archived_without_replacement = []
    for row in group.archived_without_replacement:
        if not row.is_archived:
            context.db.set_archived(row.type_id, workspace_uuid=context.workspace.uuid)
            archived_without_replacement.append(row.type_id)
    return {"group": group.survivor.type_id,
            "originals": [o.type_id for o in group.originals],
            "replacement": replacement.type_id,
            "replacement_uuid": replacement.uuid,
            "name": replacement.name,
            "how": how,
            "children_moved": moved,
            "archived": archived,
            "archived_without_replacement": archived_without_replacement}


# ---------------------------------------------------------------------------
# Verifying
# ---------------------------------------------------------------------------


def verify(conn: sqlite3.Connection, plan: Plan) -> list[str]:
    """Every C22 Verify clause that the registry can show, against the plan
    derived before this run wrote anything. Returns the failures."""
    failures = []
    recorded = recorded_replacements(conn, plan.workspace)
    for group in plan.groups:
        owners = {recorded[o.uuid].uuid for o in group.originals if o.uuid in recorded}
        if len(owners) != 1 or any(o.uuid not in recorded for o in group.originals):
            failures.append(f"{group.survivor.type_id}: {len(owners)} recorded replacements")
            continue
        replacement = recorded[group.survivor.uuid]
        display = conn.execute("SELECT seq, slug FROM entity_display WHERE uuid = ?",
                               (replacement.uuid,)).fetchone()
        if display is None:
            failures.append(f"{replacement.type_id} has no entity_display row")
            continue
        if f"{group.kind}:{render_display_id(group.kind, display['seq'], display['slug'])}" \
                != replacement.type_id:
            failures.append(f"{replacement.type_id}'s display row renders otherwise")
        high_water = plan.buckets[group.kind]["legacy_high_water"]
        if high_water is not None and display["seq"] <= high_water:
            failures.append(f"{replacement.type_id}: {display['seq']} does not clear the legacy "
                            f"high-water mark {high_water}")
        if display["seq"] in plan.legacy_numbers[group.kind]:
            failures.append(f"{replacement.type_id} reuses legacy number {display['seq']}")
        holders = conn.execute(
            "SELECT COUNT(*) FROM entity_display d JOIN entities e ON e.uuid = d.uuid "
            "WHERE e.workspace_uuid = ? AND e.kind = ? AND d.seq = ?",
            (plan.workspace.uuid, group.kind, display["seq"])).fetchone()[0]
        if holders != 1:
            failures.append(f"{replacement.type_id}: {holders} entities hold number {display['seq']}")
        for archived in (*group.originals, *group.archived_without_replacement):
            now = _entity_by_uuid(conn, archived.uuid)
            if not now.is_archived:
                failures.append(f"{archived.type_id} is not archived")
            if now.status != archived.status:
                failures.append(f"{archived.type_id}'s status moved {archived.status!r} -> "
                                f"{now.status!r}")
        for row in group.archived_without_replacement:
            if row.uuid in recorded:
                failures.append(f"{row.type_id} is recorded as replaced by "
                                f"{recorded[row.uuid].type_id}; it is archived without a "
                                f"replacement")
        on_replacement = {c.uuid for c in _children_of(conn, replacement.uuid)}
        for child in group.children:
            if child.uuid not in on_replacement:
                failures.append(f"{child.type_id} did not move onto {replacement.type_id}")
        for parent_type_id, kids in group.residue.items():
            for kid in kids:
                now = _entity_by_uuid(conn, kid.uuid)
                if now.parent_uuid != kid.parent_uuid:
                    failures.append(f"residue child {kid.type_id} left {parent_type_id}")
        if group.kind == "backlog":
            workflow = conn.execute("SELECT workflow_phase, kanban_column FROM workflow_phases "
                                    "WHERE type_id = ?", (replacement.type_id,)).fetchone()
            if workflow is None or tuple(workflow) != (BACKLOG_WORKFLOW_PHASE, BACKLOG_KANBAN_COLUMN):
                failures.append(f"{replacement.type_id} lacks its backlog workflow row")
        elif not Path(replacement.artifact_path or "", ".meta.json").is_file():
            failures.append(f"{replacement.type_id} has no .meta.json at {replacement.artifact_path}")

    for group in plan.groups:
        for archived in (*group.originals, *group.archived_without_replacement):
            stranded = _children_of(conn, archived.uuid)
            if stranded:
                failures.append(f"{[c.type_id for c in stranded]} still point at "
                                f"{archived.type_id}")
    invariant = check_display_row_invariant(conn)
    if not invariant.passed:
        failures.extend(f"display_row_invariant: {issue.message}" for issue in invariant.issues)
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        failures.append(f"integrity_check: {integrity}")
    foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        failures.append(f"foreign_key_check: {[tuple(r) for r in foreign_keys]}")
    return failures


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def plan_only(db_path: str, workspace_root: str, artifacts_root: str, *,
              live_registry_confirmed: bool = False) -> dict:
    refuse_the_live_registry(db_path, live_registry_confirmed=live_registry_confirmed)
    with contextlib.closing(open_read_only(db_path)) as conn:
        check_schema(conn)
        plan = derive_plan(conn, workspace_root, artifacts_root)
        manifest = plan_manifest(plan)
        manifest["locked_scope_differences"] = scope_differences(conn, plan, LOCKED_SCOPE)
    return manifest


def apply(db_path: str, workspace_root: str, artifacts_root: str, *,
          locked_scope: dict | None, live_registry_confirmed: bool = False) -> dict:
    refuse_the_live_registry(db_path, live_registry_confirmed=live_registry_confirmed)
    with contextlib.closing(open_read_only(db_path)) as conn:
        check_schema(conn)
        plan = derive_plan(conn, workspace_root, artifacts_root)
        if locked_scope is not None:
            differences = scope_differences(conn, plan, locked_scope)
            if differences:
                raise ScopeDiffers(differences)
    preflight(plan)

    actions = []
    with running_servers(db_path, plan.workspace, artifacts_root) as context:
        for group in plan.groups:
            actions.append(_recreate_group(context, group))

    with contextlib.closing(open_read_only(db_path)) as conn:
        failures = verify(conn, plan)
    return {"workspace": dataclasses.asdict(plan.workspace),
            "actions": actions,
            "verification": {"passed": not failures, "failures": failures}}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="C22: recreate a workspace's live legacy rows in the new shape.")
    parser.add_argument("--db", required=True, help="the registry file")
    parser.add_argument("--workspace-root", required=True,
                        help="the workspace's project_root, as the workspaces table records it")
    parser.add_argument("--artifacts-root", required=True,
                        help="where init_project_state creates projects/{NNN}-{slug}/")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="read-only: print the manifest")
    mode.add_argument("--apply", action="store_true", help="recreate, move, archive, verify")
    parser.add_argument(LIVE_REGISTRY_FLAG, dest="live_registry_confirmed", action="store_true",
                        help=f"allow a --db that reaches {LIVE_REGISTRY_DIR} under $HOME or "
                             f"under the account's home")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = os.path.abspath(args.db)
    artifacts_root = os.path.abspath(args.artifacts_root)
    confirmed = args.live_registry_confirmed
    try:
        # plan_only and apply refuse the live registry themselves; checking
        # first here makes that refusal, not "not a file", name a missing
        # path that reaches it.
        refuse_the_live_registry(db_path, live_registry_confirmed=confirmed)
        if not os.path.isfile(db_path):
            raise Refusal(f"{db_path} is not a file")
        if args.plan:
            manifest = plan_only(db_path, args.workspace_root, artifacts_root,
                                 live_registry_confirmed=confirmed)
            print(json.dumps(manifest, indent=2))
            return EXIT_OK
        report = apply(db_path, args.workspace_root, artifacts_root, locked_scope=LOCKED_SCOPE,
                       live_registry_confirmed=confirmed)
    except Refusal as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return EXIT_REFUSED
    except ScopeDiffers as differs:
        print("refused: the derivation differs from LOCKED_SCOPE (decisions 2 and 3); "
              "nothing was written:\n  " + "\n  ".join(differs.differences), file=sys.stderr)
        return EXIT_SCOPE_DIFFERS
    except ApplyError as error:
        print(f"stopped: {error}. Re-running resumes from here.", file=sys.stderr)
        return EXIT_FAILED
    print(json.dumps(report, indent=2))
    return EXIT_OK if report["verification"]["passed"] else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
