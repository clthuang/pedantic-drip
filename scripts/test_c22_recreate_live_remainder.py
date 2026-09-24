"""C22: ``scripts/c22_recreate_live_remainder.py`` recreates a workspace's live legacy rows.

The fixture is the live registry's C22 shapes in miniature, on a v2 file:

- **Backlog** — two open legacy items in scope (one with no metadata, one
  whose description is JSON-encoded twice), one open item already archived
  by hand and one completed item, both out of scope.
- **Projects** — ``P001`` with a later ``created_at`` than
  ``P001-openclaw-gap-analysis`` (both unarchived, sharing legacy number 1;
  the openclaw row is a different project, archived with no replacement,
  and holds no child); ``P002`` and ``P003`` whose other halves are
  archived (out of scope, each carrying the ``brainstorm_source`` its
  survivor lacks; ``P003-entity-system-redesign`` keeps its child as
  residue); ``P004-entity-db-redesign`` unpaired with three children.
- **Another workspace** holding a live legacy project and its child, which
  C22 cannot reach.

HOME and the account's home in the password database point at two
different scratch directories, as in a rehearsal run with a scratch HOME.

``test_rehearsal_on_a_snapshot_copy`` repeats the run on a copy of a live
registry snapshot and asserts the file's full diff. It runs only when
``C22_SNAPSHOT_DB`` names that snapshot; the snapshot is never written.
"""
from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import json
import os
import pwd
import re
import shutil
import sqlite3
import sys
import uuid as uuid_module
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import c22_recreate_live_remainder as c22  # noqa: E402  (puts plugins/pd/hooks/lib on sys.path)

from doctor.checks import check_display_row_invariant  # noqa: E402
# Imported at collection time: it registers the v2 DDL that the fixture's
# build_staging_database replays (see test_c22a_reparent_entity.py).
from entity_registry import rebuild_tool, schema_v2  # noqa: E402
from entity_registry.clean_break import establish_high_water, parse_legacy_seq  # noqa: E402
from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle  # noqa: E402
from entity_registry.metadata import RECREATED_FROM_KEY  # noqa: E402
from entity_registry.project_identity import _compute_legacy_project_id  # noqa: E402

SNAPSHOT_ENV = "C22_SNAPSHOT_DB"
LIVE_WORKSPACE_ROOT = "/Users/terry/projects/pedantic-drip"

NAME_00059 = (
    "Pre-review lint for curly-brace template placeholders (e.g. `{actual_headers}`) "
    "inside code-fenced shell commands in tasks.md. Signal from feature 031 retro"
)
NAME_00177 = "[LOW/security] `_resolve_project_id()` emits stderr warning per call for..."
DESCRIPTION_00177 = (
    "[LOW/security] `_resolve_project_id()` emits stderr warning per call for "
    "empty-project-id entities. No dedup across 3 hot-path call sites."
)
P004_BRAINSTORM_SOURCE = "docs/brainstorms/20260710-153600-entity-db-redesign.prd.md"
OPENCLAW_BRAINSTORM_SOURCE = "docs/brainstorms/20260326-030832-openclaw-gap-analysis.prd.md"
# The archived halves' values, which their survivors (P002, P003) lack.
MEMORY_FLYWHEEL_BRAINSTORM_SOURCE = "docs/brainstorms/20260415-100000-memory-flywheel.prd.md"
ENTITY_SYSTEM_BRAINSTORM_SOURCE = "docs/brainstorms/20260510-152932-entity-system-redesign.prd.md"

# P001's pair: a different project, archived with no replacement
# (c22.ARCHIVED_WITHOUT_REPLACEMENT).
OPENCLAW = "project:P001-openclaw-gap-analysis"

# The fixture's own locked scope, in the shape of c22.LOCKED_SCOPE.
FIXTURE_SCOPE = {
    "backlog:00059": {"absorbs": [], "children": 0},
    "backlog:00177": {"absorbs": [], "children": 0},
    "project:P001": {"absorbs": [], "archived_without_replacement": [OPENCLAW], "children": 0},
    "project:P002": {"absorbs": [], "children": 2},
    "project:P003": {"absorbs": [], "children": 2},
    "project:P004-entity-db-redesign": {"absorbs": [], "children": 3},
}
IN_SCOPE = sorted(["backlog:00059", "backlog:00177", "project:P001", OPENCLAW, "project:P002",
                   "project:P003", "project:P004-entity-db-redesign"])
REPLACEMENT_OF = {
    "backlog:00059": "backlog:279-pre-review-lint-for-curly",
    "backlog:00177": "backlog:280-low-security-resolve-project",
    "project:P001": "project:005-iflow-arch-evolution",
    "project:P002": "project:006-memory-flywheel",
    "project:P003": "project:007-entity-system-redesign",
    "project:P004-entity-db-redesign": "project:008-entity-db-redesign",
}
CHILDREN_OF = {  # original -> its children's type_ids, as the fixture builds them
    "project:P002": ["feature:079-fts5-backfill", "feature:080-influence-wiring"],
    "project:P003": ["feature:108-workspace-identity", "feature:110-markdown-projections"],
    "project:P003-entity-system-redesign": ["feature:112-workspace-identity-cleanup"],
    "project:P004-entity-db-redesign": ["feature:118-uuidv7-identity",
                                        "feature:119-append-only-event-log",
                                        "feature:120-state-projection-views"],
}
# The child _hang_a_child_on_the_openclaw_row gives the openclaw row.
OPENCLAW_CHILD = "feature:070-openclaw-survey"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def _set_account_home(monkeypatch, account_home: Path) -> None:
    """Make the password database name *account_home* as this uid's home
    (HOME is left alone). Every other field is the real entry's."""
    getpwuid = pwd.getpwuid

    def with_account_home(uid):
        entry = getpwuid(uid)
        if uid != os.getuid():
            return entry
        return pwd.struct_passwd((entry.pw_name, entry.pw_passwd, entry.pw_uid, entry.pw_gid,
                                  entry.pw_gecos, str(account_home), entry.pw_shell))

    monkeypatch.setattr(pwd, "getpwuid", with_account_home)


@pytest.fixture(autouse=True)
def _isolate_from_the_live_registry(monkeypatch, tmp_path):
    """No code path may reach ``~/.claude/pd``: HOME, the account's home in
    the password database and ENTITY_DB_PATH all point into this test's
    directory (repo-root scripts/ has no conftest doing it). HOME and the
    account's home are different directories, as in a rehearsal."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _set_account_home(monkeypatch, tmp_path / "account-home")
    monkeypatch.setenv("ENTITY_DB_PATH", str(tmp_path / "throwaway-entities.db"))
    monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)


@pytest.fixture(autouse=True)
def _reset_ddl_registry_for_v2_fixtures():
    """build_staging_database registers v2 DDL as production behaviour;
    restore the registry around each test (test_c22a_reparent_entity.py)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


# ---------------------------------------------------------------------------
# The fixture registry
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Registry:
    db_path: Path
    workspace_root: Path
    artifacts_root: Path
    workspace_uuid: str
    other_workspace_uuid: str


def _insert_workspace(db: EntityDatabase, root: Path) -> str:
    workspace_uuid = str(uuid_module.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (workspace_uuid, _compute_legacy_project_id(str(root)), str(root), now, now),
    )
    db._conn.commit()
    return workspace_uuid


def _legacy(db: EntityDatabase, workspace_uuid: str, kind: str, legacy_id: str, name: str,
            status: str | None, created_at: str, *, artifact_path: str | None = None,
            metadata: str | None = None, parent_uuid: str | None = None,
            archived: bool = False) -> str:
    """A pre-cutover row as history left it: is_legacy = 1, no display row."""
    entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
    entity_uuid = str(uuid_module.uuid4())
    db._conn.execute(
        "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, "
        "lifecycle_class, is_legacy, is_archived) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (entity_uuid, workspace_uuid, f"{kind}:{legacy_id}", legacy_id, name, status,
         parent_uuid, artifact_path, created_at, created_at, metadata, entity_type, kind,
         lifecycle_class, 1 if archived else 0),
    )
    db._conn.commit()
    return entity_uuid


def _feature(db: EntityDatabase, workspace_uuid: str, display_id: str, parent_uuid: str) -> str:
    seq_text, _, slug = display_id.partition("-")
    return db.register_entity(
        "feature", name=slug.replace("-", " "), seq=int(seq_text), slug=slug,
        status="completed", parent_uuid=parent_uuid, workspace_uuid=workspace_uuid,
    )


def _build_registry(root: Path, *, archived_half_created_later: bool = False,
                    p001_pair_created_together: bool = False,
                    openclaw_created_later: bool = False) -> Registry:
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "entities.db"
    rebuild_tool.build_staging_database(str(db_path))
    workspace_root = root / "workspace"
    other_root = root / "other-workspace"
    workspace_root.mkdir()
    other_root.mkdir()
    db = EntityDatabase(str(db_path))
    try:
        ws = _insert_workspace(db, workspace_root)
        other = _insert_workspace(db, other_root)

        _legacy(db, ws, "backlog", "00059", NAME_00059, "open",
                "2026-04-15T14:10:49.847865+00:00", artifact_path="docs/backlog.md")
        _legacy(db, ws, "backlog", "00177", NAME_00177, "open",
                "2026-04-20T04:47:28.599282+00:00", artifact_path="docs/backlog.md",
                metadata=json.dumps(json.dumps({"description": DESCRIPTION_00177})))
        _legacy(db, ws, "backlog", "00063", "Entity rename tooling", "open",
                "2026-04-15T14:10:49.848706+00:00", archived=True)
        _legacy(db, ws, "backlog", "00010", "A finished item", "completed",
                "2026-04-15T14:10:49.840000+00:00")
        db.register_entity("backlog", name="Entity rename tooling or convention", seq=278,
                           slug="entity-rename-tooling-or", status="open", workspace_uuid=ws)

        memory_flywheel_brainstorm = db.register_entity(
            "brainstorm", display_id="20260415-100000-memory-flywheel",
            name="memory flywheel", workspace_uuid=ws,
            artifact_path=MEMORY_FLYWHEEL_BRAINSTORM_SOURCE)
        entity_system_brainstorm = db.register_entity(
            "brainstorm", display_id="20260510-152932-entity-system-redesign",
            name="entity system redesign", workspace_uuid=ws,
            artifact_path=ENTITY_SYSTEM_BRAINSTORM_SOURCE)
        entity_db_brainstorm = db.register_entity(
            "brainstorm", display_id="20260710-153600-entity-db-redesign",
            name="entity db redesign", workspace_uuid=ws, artifact_path=P004_BRAINSTORM_SOURCE)

        p001_created_at = "2026-03-26T14:54:54.133536+00:00"
        _legacy(db, ws, "project", "P001", "P001", None, p001_created_at,
                artifact_path=f"{workspace_root}/docs/projects/P001-iflow-arch-evolution")
        _legacy(
            db, ws, "project", "P001-openclaw-gap-analysis", "Openclaw Gap Analysis", "active",
            "2026-03-27T00:00:00+00:00" if openclaw_created_later
            else p001_created_at if p001_pair_created_together
            else "2026-03-26T01:27:55.096791+00:00",
            artifact_path="docs/projects/P001-openclaw-gap-analysis",
            metadata=json.dumps({"id": "P001", "slug": "openclaw-gap-analysis", "features": [],
                                 "milestones": [], "brainstorm_source": OPENCLAW_BRAINSTORM_SOURCE}))
        p002_times = ["2026-04-15T14:33:36.847774+00:00", "2026-04-15T14:33:06.935622+00:00"]
        if archived_half_created_later:
            p002_times.reverse()
        p002 = _legacy(db, ws, "project", "P002", "memory-flywheel", "active", p002_times[0],
                       artifact_path="docs/projects/P002-memory-flywheel/",
                       parent_uuid=memory_flywheel_brainstorm,
                       metadata=json.dumps({"progress": 1.0, "traffic_light": "GREEN"}))
        _legacy(db, ws, "project", "P002-memory-flywheel", "Memory Flywheel", "active",
                p002_times[1], artifact_path="docs/projects/P002-memory-flywheel",
                archived=True,
                metadata=json.dumps({"id": "P002", "slug": "memory-flywheel", "features": [],
                                     "milestones": [],
                                     "brainstorm_source": MEMORY_FLYWHEEL_BRAINSTORM_SOURCE}))
        p003 = _legacy(db, ws, "project", "P003", "entity-system-redesign", "active",
                       "2026-05-10T07:32:33.194377+00:00",
                       artifact_path="docs/projects/P003-entity-system-redesign/",
                       parent_uuid=entity_system_brainstorm)
        p003_archived_half = _legacy(
            db, ws, "project", "P003-entity-system-redesign", "Entity System Redesign",
            "active", "2026-05-10T07:32:22.383141+00:00",
            artifact_path="docs/projects/P003-entity-system-redesign", archived=True,
            metadata=json.dumps({"id": "P003", "slug": "entity-system-redesign", "features": [],
                                 "milestones": [],
                                 "brainstorm_source": ENTITY_SYSTEM_BRAINSTORM_SOURCE}))
        p004 = _legacy(
            db, ws, "project", "P004-entity-db-redesign", "Entity Db Redesign", "active",
            "2026-07-10T10:45:20.309399+00:00",
            artifact_path="docs/projects/P004-entity-db-redesign",
            parent_uuid=entity_db_brainstorm,
            metadata=json.dumps({"id": "P004", "slug": "entity-db-redesign",
                                 "features": ["118-uuidv7-identity"], "milestones": [],
                                 "brainstorm_source": P004_BRAINSTORM_SOURCE}))

        parents = {"project:P002": p002, "project:P003": p003,
                   "project:P003-entity-system-redesign": p003_archived_half,
                   "project:P004-entity-db-redesign": p004}
        for parent_type_id, children in CHILDREN_OF.items():
            for child in children:
                _feature(db, ws, child.partition(":")[2], parents[parent_type_id])

        elsewhere = _legacy(db, other, "project", "P001", "agent-orchestrator", "active",
                            "2026-06-01T00:00:00+00:00",
                            artifact_path="docs/projects/P001-agent-orchestrator")
        _feature(db, other, "001-orchestrator-core", elsewhere)

        establish_high_water(db._conn)  # B4: every bucket's counter clears its legacy numbers
    finally:
        db.close()
    return Registry(db_path, workspace_root, root / "artifacts", ws, other)


@pytest.fixture
def registry(tmp_path) -> Registry:
    return _build_registry(tmp_path / "registry")


def _args(registry: Registry, mode: str, *, db: Path | None = None) -> list[str]:
    return ["--db", str(db or registry.db_path), "--workspace-root", str(registry.workspace_root),
            "--artifacts-root", str(registry.artifacts_root), mode]


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) if Path(f"{db_path}-wal").exists() \
        else sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _file_fingerprint(db_path: Path) -> tuple:
    """The file's bytes and every file beside it (a -wal or -shm appearing is a write)."""
    return (hashlib.sha256(db_path.read_bytes()).hexdigest(),
            sorted(p.name for p in db_path.parent.iterdir()))


# ---------------------------------------------------------------------------
# Whole-registry diff (shared with the snapshot rehearsal)
# ---------------------------------------------------------------------------


def _table_keys(conn: sqlite3.Connection, table: str) -> list[str]:
    if table == "sqlite_sequence":  # no declared key; one row per AUTOINCREMENT table
        return ["name"]
    columns = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    primary_key = [c["name"] for c in sorted(columns, key=lambda c: c["pk"]) if c["pk"]]
    return primary_key or [c["name"] for c in columns]


def registry_rows(db_path: Path) -> dict[str, dict[tuple, dict]]:
    """Every row of every table, keyed by primary key. FTS shadow tables are
    left out; the ``entities_fts`` virtual table stands for them."""
    conn = _connect(db_path)
    try:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
            if not r["name"].startswith("entities_fts_")]
        rows: dict[str, dict[tuple, dict]] = {}
        for table in tables:
            if table == "entities_fts":
                keys, select = ["rowid"], "SELECT rowid, * FROM entities_fts"
            else:
                keys, select = _table_keys(conn, table), f"SELECT * FROM '{table}'"
            rows[table] = {tuple(dict(r)[k] for k in keys): dict(r) for r in conn.execute(select)}
        return rows
    finally:
        conn.close()


def diff_registries(before: dict, after: dict) -> dict[str, dict]:
    diff: dict[str, dict] = {}
    for table in sorted(set(before) | set(after)):
        old, new = before.get(table, {}), after.get(table, {})
        changed = {
            key: {col: (old[key].get(col), new[key].get(col))
                  for col in set(old[key]) | set(new[key]) if old[key].get(col) != new[key].get(col)}
            for key in set(old) & set(new) if old[key] != new[key]
        }
        added = {key: new[key] for key in set(new) - set(old)}
        removed = {key: old[key] for key in set(old) - set(new)}
        if added or removed or changed:
            diff[table] = {"added": added, "removed": removed, "changed": changed}
    return diff


def summarize(diff: dict) -> dict:
    """Counts by what changed — the shape a reviewer checks."""
    summary: dict = {}
    for table, change in diff.items():
        summary[table] = {
            "added": len(change["added"]),
            "removed": len(change["removed"]),
            "changed_columns": dict(Counter(
                tuple(sorted(cols)) for cols in change["changed"].values())),
        }
    for table, column in (("events", "event_type"), ("phase_events", "event_type")):
        if table in diff:
            summary[table]["added_by_type"] = dict(Counter(
                row[column] for row in diff[table]["added"].values()))
    return summary


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def _entity(conn, workspace_uuid: str, type_id: str) -> sqlite3.Row:
    return conn.execute("SELECT * FROM entities WHERE workspace_uuid = ? AND type_id = ?",
                        (workspace_uuid, type_id)).fetchone()


def _children(conn, parent_uuid: str) -> list[str]:
    return sorted(r["type_id"] for r in conn.execute(
        "SELECT type_id FROM entities WHERE parent_uuid = ?", (parent_uuid,)))


def _replacements(conn, workspace_uuid: str) -> dict[str, sqlite3.Row]:
    """Replacement type_id -> row, for every entity carrying the C22 record."""
    found = {}
    for row in conn.execute(
            "SELECT e.*, d.seq, d.slug FROM entities e LEFT JOIN entity_display d ON d.uuid = e.uuid "
            "WHERE e.workspace_uuid = ? AND e.is_legacy = 0", (workspace_uuid,)):
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        if RECREATED_FROM_KEY in metadata:
            found[row["type_id"]] = row
    return found


def _type_id_of(conn, entity_uuid: str) -> str:
    return conn.execute("SELECT type_id FROM entities WHERE uuid = ?", (entity_uuid,)).fetchone()[0]


# ---------------------------------------------------------------------------
# --plan
# ---------------------------------------------------------------------------


def test_plan_writes_nothing_and_names_every_choice(registry, capsys):
    before = _file_fingerprint(registry.db_path)

    assert c22.main(_args(registry, "--plan")) == 0

    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()
    manifest = json.loads(capsys.readouterr().out)
    groups = {g["survivor"]["type_id"]: g for g in manifest["groups"]}
    assert sorted(groups) == sorted(FIXTURE_SCOPE)
    # P001's pair shares its legacy number, is a different project, and is
    # archived with no replacement: the manifest says so, and why.
    p001 = groups["project:P001"]
    assert p001["absorbed"] == []
    [unreplaced] = p001["archived_without_replacement"]
    assert unreplaced["type_id"] == OPENCLAW
    assert unreplaced["reason"] == c22.ARCHIVED_WITHOUT_REPLACEMENT[OPENCLAW]
    assert "terry_agent" in unreplaced["reason"]
    assert p001["new"]["slug"] == "iflow-arch-evolution"
    # The openclaw row's brainstorm is another project's: not carried.
    assert p001["new"]["brainstorm_source"] is None
    assert p001["children_to_move"] == []
    assert p001["flags"] == [
        "project:P001 has status None; init_project_state registers its replacement 'active'"]
    assert [m["type_id"] for m in groups["project:P002"]["left_as_is"]] == \
        ["project:P002-memory-flywheel"]
    # A survivor with no brainstorm_source takes its pair's archived half's,
    # and the manifest names where it came from.
    for survivor, (value, archived_half, parent) in {
            "project:P002": (MEMORY_FLYWHEEL_BRAINSTORM_SOURCE, "project:P002-memory-flywheel",
                             "brainstorm:20260415-100000-memory-flywheel"),
            "project:P003": (ENTITY_SYSTEM_BRAINSTORM_SOURCE, "project:P003-entity-system-redesign",
                             "brainstorm:20260510-152932-entity-system-redesign")}.items():
        new = groups[survivor]["new"]
        assert new["brainstorm_source"] == value, survivor
        assert archived_half in new["brainstorm_source_origin"], survivor
        assert f"names the artifact of {survivor}'s parent, {parent}" in \
            new["brainstorm_source_origin"], survivor
        assert groups[survivor]["flags"] == [], survivor
    assert groups["project:P004-entity-db-redesign"]["new"]["brainstorm_source_origin"] == \
        "the metadata of project:P004-entity-db-redesign, the survivor"
    assert groups["project:P003"]["residue"] == [{
        "parent": "project:P003-entity-system-redesign",
        "children": ["feature:112-workspace-identity-cleanup"]}]
    assert groups["project:P004-entity-db-redesign"]["new"]["brainstorm_source"] == \
        P004_BRAINSTORM_SOURCE
    assert groups["backlog:00177"]["new"]["description"] == DESCRIPTION_00177
    assert groups["backlog:00059"]["new"]["description_source"] == "name"
    assert manifest["archive"] == IN_SCOPE
    # The fixture is not the live registry, so the locked scope names differences.
    assert manifest["locked_scope_differences"] != []


# ---------------------------------------------------------------------------
# The live-registry guard
# ---------------------------------------------------------------------------


def _live_registry_copy(registry: Registry, *, home: Path | None = None) -> Path:
    """The fixture registry, copied to the live registry's place under *home*
    (this test's HOME unless given)."""
    live_dir = (home or Path(os.environ["HOME"])) / ".claude" / "pd" / "entities"
    live_dir.mkdir(parents=True)
    live_db = live_dir / "entities.db"
    shutil.copy(registry.db_path, live_db)
    return live_db


def test_refuses_a_database_under_the_live_registry_directory(registry, tmp_path, capsys):
    live_db = _live_registry_copy(registry)
    alias = tmp_path / "alias.db"
    alias.symlink_to(live_db)
    before = _file_fingerprint(live_db)

    for db in (live_db, alias):
        for mode in ("--plan", "--apply"):
            assert c22.main(_args(registry, mode, db=db)) == 2
            assert "--i-mean-the-live-registry" in capsys.readouterr().err
    assert _file_fingerprint(live_db) == before

    # The flag, and only the flag, lets the same run through.
    assert c22.main(_args(registry, "--plan", db=live_db) + ["--i-mean-the-live-registry"]) == 0
    assert json.loads(capsys.readouterr().out)["groups"]
    assert _file_fingerprint(live_db) == before


def _spellings_text_cannot_see(live_db: Path, tmp_path: Path, *,
                               home: Path | None = None) -> dict[str, Path]:
    """Paths that reach the live registry *live_db* under *home* (this test's
    HOME unless given) although their resolved text is not under its
    ``.claude/pd``. A hard link works on any filesystem; the case variants
    need a case-insensitive one (APFS's default), and the firmlink needs
    macOS's ``/System/Volumes/Data``."""
    home = home or Path(os.environ["HOME"])
    spellings = {"hard link": tmp_path / "hard-link.db"}
    os.link(live_db, spellings["hard link"])
    case_variant = home / ".Claude" / "PD" / "entities" / "entities.db"
    if case_variant.exists():
        spellings["case variant"] = case_variant
        spellings["new file in a case-variant directory"] = home / ".Claude" / "PD" / "new.db"
    firmlink = Path("/System/Volumes/Data" + str(live_db))
    if firmlink.exists() and os.path.samefile(firmlink, live_db):
        spellings["firmlink"] = firmlink
    live_dir = (home / ".claude" / "pd").resolve()
    for label, path in spellings.items():  # the resolved text alone lets each one through
        assert live_dir not in path.resolve().parents, label
    return spellings


def test_the_guard_compares_file_identity_not_path_text(registry, tmp_path, capsys):
    live_db = _live_registry_copy(registry)
    before = _file_fingerprint(live_db)
    spellings = _spellings_text_cannot_see(live_db, tmp_path)

    for label, db in spellings.items():
        for mode in ("--plan", "--apply"):
            assert c22.main(_args(registry, mode, db=db)) == 2, (label, mode)
            assert "--i-mean-the-live-registry" in capsys.readouterr().err, (label, mode)
    assert _file_fingerprint(live_db) == before
    assert not registry.artifacts_root.exists()


def test_the_guard_refuses_the_accounts_registry_while_home_points_elsewhere(
        registry, tmp_path, monkeypatch, capsys):
    """A rehearsal runs with HOME at a scratch directory, where ``~`` then
    expands. The registry under the account's own home, as the password
    database names it, is still the live one: a --db reaching it is refused
    in both modes however it is spelled, and nothing is written."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)  # unrefused, --apply would write
    account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert account_home != Path(os.environ["HOME"])
    live_db = _live_registry_copy(registry, home=account_home)
    before = _file_fingerprint(live_db)
    alias = tmp_path / "alias.db"
    alias.symlink_to(live_db)
    spellings = {
        "the file": live_db,
        "a symlink to it": alias,
        "a '..' spelling": account_home / "elsewhere" / ".." / ".claude" / "pd" / "entities"
                           / "entities.db",
        "a new file in its directory": account_home / ".claude" / "pd" / "new.db",
        **_spellings_text_cannot_see(live_db, tmp_path, home=account_home),
    }

    for label, db in spellings.items():
        for mode in ("--plan", "--apply"):
            assert c22.main(_args(registry, mode, db=db)) == 2, (label, mode)
            assert "--i-mean-the-live-registry" in capsys.readouterr().err, (label, mode)
    assert _file_fingerprint(live_db) == before
    assert not registry.artifacts_root.exists()

    # The flag, and only the flag, lets the same run through.
    assert c22.main(_args(registry, "--plan", db=live_db) + ["--i-mean-the-live-registry"]) == 0
    assert json.loads(capsys.readouterr().out)["groups"]
    assert _file_fingerprint(live_db) == before


def test_plan_only_and_apply_refuse_the_live_registry_when_called_directly(registry, capsys):
    """The guard is not main()'s alone: an importer calling the entry points
    gets the same refusal, and only the keyword lets the call through."""
    live_db = _live_registry_copy(registry)
    before = _file_fingerprint(live_db)
    arguments = (str(live_db), str(registry.workspace_root), str(registry.artifacts_root))

    with pytest.raises(c22.Refusal, match="--i-mean-the-live-registry"):
        c22.plan_only(*arguments)
    with pytest.raises(c22.Refusal, match="--i-mean-the-live-registry"):
        c22.apply(*arguments, locked_scope=None)
    assert _file_fingerprint(live_db) == before
    assert not registry.artifacts_root.exists()

    assert c22.plan_only(*arguments, live_registry_confirmed=True)["groups"]
    assert _file_fingerprint(live_db) == before


# ---------------------------------------------------------------------------
# --apply
# ---------------------------------------------------------------------------


@pytest.fixture
def applied(registry, monkeypatch, capsys):
    """The fixture registry after one --apply under its own locked scope."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    before = registry_rows(registry.db_path)
    assert c22.main(_args(registry, "--apply")) == 0
    report = json.loads(capsys.readouterr().out)
    return before, report


def test_each_group_becomes_one_new_entity_with_a_display_row(registry, applied):
    _before, report = applied
    conn = _connect(registry.db_path)
    replacements = _replacements(conn, registry.workspace_uuid)

    assert sorted(replacements) == sorted(set(REPLACEMENT_OF.values()))
    for type_id, row in replacements.items():
        assert row["is_legacy"] == 0 and row["is_archived"] == 0
        assert row["seq"] is not None, f"{type_id} has no entity_display row"
        assert f"{row['kind']}:{row['seq']:03d}-{row['slug']}" == type_id
    recorded = {type_id: sorted(_type_id_of(conn, u)
                                for u in json.loads(row["metadata"])[RECREATED_FROM_KEY])
                for type_id, row in replacements.items()}
    expected: dict[str, list[str]] = {}
    for original, replacement in REPLACEMENT_OF.items():
        expected.setdefault(replacement, []).append(original)
    assert recorded == {k: sorted(v) for k, v in expected.items()}
    assert {a["replacement"]: a["how"] for a in report["actions"]} == \
        {r: "created" for r in set(REPLACEMENT_OF.values())}
    assert report["verification"] == {"passed": True, "failures": []}


def test_backlog_items_keep_their_name_and_description(registry, applied):
    conn = _connect(registry.db_path)
    for original, description in (("backlog:00059", NAME_00059),
                                  ("backlog:00177", DESCRIPTION_00177)):
        source = _entity(conn, registry.workspace_uuid, original)
        new = _entity(conn, registry.workspace_uuid, REPLACEMENT_OF[original])
        assert new["name"] == source["name"]
        assert new["status"] == "open"
        assert json.loads(new["metadata"]) == {"description": description,
                                               RECREATED_FROM_KEY: [source["uuid"]]}
        # /pd:add-to-backlog step 4
        workflow = conn.execute("SELECT workflow_phase, kanban_column FROM workflow_phases "
                                "WHERE type_id = ?", (new["type_id"],)).fetchone()
        assert tuple(workflow) == ("open", "backlog")


def test_projects_take_slug_and_name_from_the_survivors_directory(registry, applied):
    conn = _connect(registry.db_path)
    expectations = {
        # Not the openclaw row's brainstorm: that row is another project.
        "project:005-iflow-arch-evolution": ("Iflow Arch Evolution", None, None),
        # Carried from the pair's archived half; the survivor has none.
        "project:006-memory-flywheel": ("Memory Flywheel", "20260415-100000-memory-flywheel",
                                        MEMORY_FLYWHEEL_BRAINSTORM_SOURCE),
        "project:007-entity-system-redesign": ("Entity System Redesign",
                                               "20260510-152932-entity-system-redesign",
                                               ENTITY_SYSTEM_BRAINSTORM_SOURCE),
        "project:008-entity-db-redesign": ("Entity Db Redesign",
                                           "20260710-153600-entity-db-redesign",
                                           P004_BRAINSTORM_SOURCE),
    }
    for type_id, (name, parent_stem, brainstorm_source) in expectations.items():
        row = _entity(conn, registry.workspace_uuid, type_id)
        assert (row["name"], row["status"]) == (name, "active")
        parent = _type_id_of(conn, row["parent_uuid"]) if row["parent_uuid"] else None
        assert parent == (f"brainstorm:{parent_stem}" if parent_stem else None)
        metadata = json.loads(row["metadata"])
        assert (metadata["features"], metadata["milestones"]) == ([], [])
        assert metadata.get("brainstorm_source") == brainstorm_source
        directory = registry.artifacts_root / "projects" / type_id.partition(":")[2]
        meta = json.loads((directory / ".meta.json").read_text())
        assert (meta["features"], meta["milestones"], meta["status"]) == ([], [], "active")
        assert meta.get("brainstorm_source") == brainstorm_source
        assert row["artifact_path"] == str(directory)


def test_the_openclaw_row_is_archived_with_no_replacement_recording_it(registry, applied):
    """Decision 2's outcome stands (both P001 rows archived, one new
    project), and the lineage is accurate: 005 records P001 alone, and the
    openclaw row, a different project, is archived with its status as it
    was and no replacement claiming it."""
    _before, report = applied
    conn = _connect(registry.db_path)
    ws = registry.workspace_uuid
    p001, openclaw = _entity(conn, ws, "project:P001"), _entity(conn, ws, OPENCLAW)
    replacements = _replacements(conn, ws)

    assert json.loads(replacements["project:005-iflow-arch-evolution"]["metadata"])[
        RECREATED_FROM_KEY] == [p001["uuid"]]
    assert not any(openclaw["uuid"] in json.loads(row["metadata"])[RECREATED_FROM_KEY]
                   for row in replacements.values())
    assert (openclaw["is_archived"], openclaw["status"]) == (1, "active")
    [action] = [a for a in report["actions"] if a["group"] == "project:P001"]
    assert (action["originals"], action["archived"], action["archived_without_replacement"]) \
        == (["project:P001"], ["project:P001"], [OPENCLAW])


def test_without_the_decision_the_pair_collapses_onto_its_survivor(registry, monkeypatch, capsys):
    """The decision alone keeps the openclaw row out of 005's record. With no
    row decided otherwise, a live pair collapses as correction 3 says: the
    replacement records both rows and takes the absorbed row's child."""
    monkeypatch.setattr(c22, "ARCHIVED_WITHOUT_REPLACEMENT", {})
    monkeypatch.setattr(c22, "LOCKED_SCOPE", {
        **FIXTURE_SCOPE, "project:P001": {"absorbs": [OPENCLAW], "children": 1}})
    _hang_a_child_on_the_openclaw_row(registry)

    assert c22.main(_args(registry, "--apply")) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["verification"] == {"passed": True, "failures": []}
    conn = _connect(registry.db_path)
    ws = registry.workspace_uuid
    new = _entity(conn, ws, "project:005-iflow-arch-evolution")
    assert sorted(json.loads(new["metadata"])[RECREATED_FROM_KEY]) == sorted(
        _entity(conn, ws, type_id)["uuid"] for type_id in ("project:P001", OPENCLAW))
    assert _children(conn, new["uuid"]) == [OPENCLAW_CHILD]
    assert _entity(conn, ws, OPENCLAW)["is_archived"] == 1


def test_a_carried_brainstorm_source_naming_another_brainstorm_is_flagged(registry, capsys):
    """The archived half's value is carried as decided, and the manifest
    flags it when it does not name the survivor's parent brainstorm."""
    _write_with_entity_database(registry, lambda db: db.update_entity(
        db.resolve_ref("project:P002-memory-flywheel", workspace_uuid=registry.workspace_uuid),
        metadata={"brainstorm_source": "docs/brainstorms/elsewhere.prd.md"},
        workspace_uuid=registry.workspace_uuid))

    assert c22.main(_args(registry, "--plan")) == 0

    p002 = next(g for g in json.loads(capsys.readouterr().out)["groups"]
                if g["survivor"]["type_id"] == "project:P002")
    assert p002["new"]["brainstorm_source"] == "docs/brainstorms/elsewhere.prd.md"
    assert "names the artifact" not in p002["new"]["brainstorm_source_origin"]
    assert p002["flags"] == [
        "brainstorm_source 'docs/brainstorms/elsewhere.prd.md', carried from "
        "project:P002-memory-flywheel, does not name the artifact of project:P002's parent "
        f"brainstorm:20260415-100000-memory-flywheel ({MEMORY_FLYWHEEL_BRAINSTORM_SOURCE!r})"]


def test_every_issued_number_clears_the_legacy_high_water_and_reuses_nothing(registry, applied):
    before, _report = applied
    conn = _connect(registry.db_path)
    for type_id, row in _replacements(conn, registry.workspace_uuid).items():
        bucket = [r for r in before["entities"].values()
                  if r["kind"] == row["kind"] and r["workspace_uuid"] == registry.workspace_uuid]
        legacy_numbers = {parse_legacy_seq(r["kind"], r["entity_id"])
                          for r in bucket if r["is_legacy"]} - {None}
        display_numbers = {before["entity_display"][(r["uuid"],)]["seq"]
                           for r in bucket if (r["uuid"],) in before["entity_display"]}
        assert row["seq"] > max(legacy_numbers), type_id
        assert row["seq"] not in legacy_numbers | display_numbers, type_id
        holders = conn.execute(
            "SELECT COUNT(*) FROM entity_display d JOIN entities e ON e.uuid = d.uuid "
            "WHERE e.workspace_uuid = ? AND e.kind = ? AND d.seq = ?",
            (registry.workspace_uuid, row["kind"], row["seq"])).fetchone()[0]
        assert holders == 1, type_id
    counters = dict(conn.execute("SELECT entity_type, next_val FROM sequences "
                                 "WHERE workspace_uuid = ?", (registry.workspace_uuid,)).fetchall())
    assert (counters["backlog"], counters["project"]) == (281, 9)


def test_children_follow_their_group_and_archived_halves_keep_theirs(registry, applied):
    conn = _connect(registry.db_path)
    ws = registry.workspace_uuid
    moved: dict[str, list[str]] = {}
    for original, children in CHILDREN_OF.items():
        if original in REPLACEMENT_OF:
            moved.setdefault(REPLACEMENT_OF[original], []).extend(children)
    for replacement, children in moved.items():
        assert _children(conn, _entity(conn, ws, replacement)["uuid"]) == sorted(children)
    for original in IN_SCOPE:
        assert _children(conn, _entity(conn, ws, original)["uuid"]) == []
    # Decision 3's residue: the archived half keeps its child.
    assert _children(conn, _entity(conn, ws, "project:P003-entity-system-redesign")["uuid"]) == \
        ["feature:112-workspace-identity-cleanup"]
    # Another workspace's legacy project is out of reach.
    elsewhere = _entity(conn, registry.other_workspace_uuid, "project:P001")
    assert elsewhere["is_archived"] == 0
    assert _children(conn, elsewhere["uuid"]) == ["feature:001-orchestrator-core"]
    events = conn.execute("SELECT entity_uuid, from_value, to_value, actor FROM events "
                          "WHERE event_type = 'reparented'").fetchall()
    assert sorted((_type_id_of(conn, e["entity_uuid"]), _type_id_of(conn, e["from_value"]),
                   _type_id_of(conn, e["to_value"]), e["actor"]) for e in events) == sorted(
        (child, original, REPLACEMENT_OF[original], "live:reparent_entity")
        for original, children in CHILDREN_OF.items() if original in REPLACEMENT_OF
        for child in children)


def test_the_diff_is_exactly_what_c22_owns(registry, applied):
    before, _report = applied
    diff = diff_registries(before, registry_rows(registry.db_path))
    summary = summarize(diff)
    assert summary == {
        "entities": {"added": 6, "removed": 0, "changed_columns": {
            ("is_archived", "updated_at"): 7, ("parent_uuid", "updated_at"): 7}},
        "entities_fts": {"added": 6, "removed": 0, "changed_columns": {}},
        "entity_display": {"added": 6, "removed": 0, "changed_columns": {}},
        "events": {"added": 13, "removed": 0, "changed_columns": {},
                   "added_by_type": {"entity_created": 6, "reparented": 7}},
        "phase_events": {"added": 6, "removed": 0, "changed_columns": {},
                         "added_by_type": {"entity_created": 6}},
        "sequences": {"added": 0, "removed": 0, "changed_columns": {("next_val",): 2}},
        "sqlite_sequence": {"added": 0, "removed": 0, "changed_columns": {("seq",): 1}},
        "workflow_phases": {"added": 2, "removed": 0, "changed_columns": {}},
    }
    changed = diff["entities"]["changed"]
    archived = sorted(before["entities"][key]["type_id"]
                      for key, cols in changed.items() if "is_archived" in cols)
    assert archived == IN_SCOPE
    assert all(cols["is_archived"] == (0, 1) for cols in changed.values() if "is_archived" in cols)
    reparented = sorted(before["entities"][key]["type_id"]
                        for key, cols in changed.items() if "parent_uuid" in cols)
    assert reparented == sorted(child for original, children in CHILDREN_OF.items()
                                if original in REPLACEMENT_OF for child in children)


def test_the_registry_passes_its_invariants_after_apply(registry, applied):
    conn = _connect(registry.db_path)
    assert check_display_row_invariant(conn).passed
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def _artifacts_tree(root: Path) -> dict[str, tuple]:
    return {str(p.relative_to(root)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def test_a_second_apply_changes_nothing(registry, applied, capsys):
    rows_after_first = registry_rows(registry.db_path)
    tree_after_first = _artifacts_tree(registry.artifacts_root)

    assert c22.main(_args(registry, "--apply")) == 0

    assert diff_registries(rows_after_first, registry_rows(registry.db_path)) == {}
    assert _artifacts_tree(registry.artifacts_root) == tree_after_first
    report = json.loads(capsys.readouterr().out)
    assert {a["how"] for a in report["actions"]} == {"already recreated"}
    assert all(a["children_moved"] == [] and a["archived"] == []
               and a["archived_without_replacement"] == [] for a in report["actions"])
    assert report["verification"] == {"passed": True, "failures": []}


def _end_state(registry: Registry) -> dict:
    """The registry and artifacts with uuids and clock times normalized away,
    so two runs on identical fixtures compare equal."""
    rows = registry_rows(registry.db_path)
    base = str(registry.db_path.parent)

    def relative(text):
        return text.replace(base, "<fixture>") if isinstance(text, str) else text

    type_ids = {r["uuid"]: r["type_id"] for r in rows["entities"].values()}
    roots = {r["uuid"]: relative(r["project_root"]) for r in rows["workspaces"].values()}
    entities = set()
    for row in rows["entities"].values():
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        if RECREATED_FROM_KEY in metadata:
            metadata[RECREATED_FROM_KEY] = sorted(type_ids[u] for u in metadata[RECREATED_FROM_KEY])
        display = rows["entity_display"].get((row["uuid"],))
        entities.add((roots[row["workspace_uuid"]], row["type_id"], row["name"], row["status"],
                      row["is_archived"], type_ids.get(row["parent_uuid"]),
                      (display["seq"], display["slug"]) if display else None,
                      json.dumps(metadata, sort_keys=True), relative(row["artifact_path"])))
    events = Counter((r["event_type"], type_ids[r["entity_uuid"]], type_ids.get(r["from_value"]),
                      type_ids.get(r["to_value"])) for r in rows["events"].values())
    meta_files = {}
    for path in sorted(registry.artifacts_root.rglob(".meta.json")):
        meta = json.loads(path.read_text())
        meta.pop("created")
        meta_files[str(path.relative_to(registry.artifacts_root))] = meta
    return {
        "entities": entities,
        "sequences": {(roots[r["workspace_uuid"]], r["entity_type"], r["next_val"])
                      for r in rows["sequences"].values()},
        "events": events,
        "phase_events": Counter((r["type_id"], r["event_type"]) for r in rows["phase_events"].values()),
        "workflow_phases": {(r["type_id"], r["workflow_phase"], r["kanban_column"])
                            for r in rows["workflow_phases"].values()},
        "meta_files": meta_files,
    }


def test_an_apply_interrupted_after_the_backlog_half_resumes_to_the_same_end_state(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    straight = _build_registry(tmp_path / "straight")
    interrupted = _build_registry(tmp_path / "interrupted")
    assert c22.main(_args(straight, "--apply")) == 0

    recreate_group = c22._recreate_group

    def stop_at_the_first_project(context, group):
        if group.kind == "project":
            raise KeyboardInterrupt
        return recreate_group(context, group)

    monkeypatch.setattr(c22, "_recreate_group", stop_at_the_first_project)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(interrupted, "--apply"))

    midway = _connect(interrupted.db_path)
    replacements = _replacements(midway, interrupted.workspace_uuid)
    assert sorted(replacements) == ["backlog:279-pre-review-lint-for-curly",
                                    "backlog:280-low-security-resolve-project"]
    archived = {r["type_id"] for r in midway.execute(
        "SELECT type_id FROM entities WHERE workspace_uuid = ? AND is_archived = 1 AND is_legacy = 1",
        (interrupted.workspace_uuid,))}
    assert {"backlog:00059", "backlog:00177"} <= archived
    assert not archived & {"project:P001", "project:P002", "project:P004-entity-db-redesign"}
    midway.close()

    monkeypatch.setattr(c22, "_recreate_group", recreate_group)
    capsys.readouterr()
    assert c22.main(_args(interrupted, "--apply")) == 0
    report = json.loads(capsys.readouterr().out)
    assert sorted({a["how"] for a in report["actions"]}) == ["already recreated", "created"]

    assert _end_state(interrupted) == _end_state(straight)


def test_an_apply_stopped_before_archiving_the_openclaw_row_archives_it_on_resume(
        tmp_path, monkeypatch, capsys):
    """A run that stopped after 005 was created and P001 archived, before the
    openclaw row was archived: the re-run takes the group as recreated and
    archives the openclaw row, still with no replacement recording it."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    straight = _build_registry(tmp_path / "straight")
    interrupted = _build_registry(tmp_path / "interrupted")
    assert c22.main(_args(straight, "--apply")) == 0
    set_archived = EntityDatabase.set_archived

    def stop_at_the_openclaw_row(self, type_id, *args, **kwargs):
        if type_id == OPENCLAW:
            raise KeyboardInterrupt
        return set_archived(self, type_id, *args, **kwargs)

    monkeypatch.setattr(EntityDatabase, "set_archived", stop_at_the_openclaw_row)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(interrupted, "--apply"))

    midway = _connect(interrupted.db_path)
    assert "project:005-iflow-arch-evolution" in _replacements(midway, interrupted.workspace_uuid)
    assert _entity(midway, interrupted.workspace_uuid, "project:P001")["is_archived"] == 1
    assert _entity(midway, interrupted.workspace_uuid, OPENCLAW)["is_archived"] == 0
    midway.close()

    monkeypatch.setattr(EntityDatabase, "set_archived", set_archived)
    capsys.readouterr()
    assert c22.main(_args(interrupted, "--apply")) == 0
    report = json.loads(capsys.readouterr().out)
    [action] = [a for a in report["actions"] if a["group"] == "project:P001"]
    assert (action["how"], action["archived"], action["archived_without_replacement"]) == \
        ("already recreated", [], [OPENCLAW])
    assert report["verification"] == {"passed": True, "failures": []}
    assert _end_state(interrupted) == _end_state(straight)


def _stop_before_the_first_record(monkeypatch) -> list[str]:
    """Stop the run once, between the first project's init_project_state and
    its record; returns the uuid of the project left unrecorded."""
    record_replacement = c22._record_replacement
    stopped: list[str] = []

    def stop_once(context, replacement_uuid, originals):
        if not stopped:
            stopped.append(replacement_uuid)
            raise KeyboardInterrupt
        return record_replacement(context, replacement_uuid, originals)

    monkeypatch.setattr(c22, "_record_replacement", stop_once)
    return stopped


def test_a_project_registered_before_its_record_is_adopted_not_duplicated(
        registry, monkeypatch, capsys):
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    crashes = _stop_before_the_first_record(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(registry, "--apply"))
    capsys.readouterr()

    assert c22.main(_args(registry, "--apply")) == 0

    report = json.loads(capsys.readouterr().out)
    adopted = [a for a in report["actions"] if a["how"] == "adopted"]
    assert [a["replacement"] for a in adopted] == ["project:005-iflow-arch-evolution"]
    assert adopted[0]["replacement_uuid"] == crashes[0]
    conn = _connect(registry.db_path)
    projects = conn.execute("SELECT type_id FROM entities WHERE workspace_uuid = ? "
                            "AND kind = 'project' AND is_legacy = 0",
                            (registry.workspace_uuid,)).fetchall()
    assert sorted(r[0] for r in projects) == sorted(
        {v for v in REPLACEMENT_OF.values() if v.startswith("project:")})
    counter = conn.execute("SELECT next_val FROM sequences WHERE workspace_uuid = ? "
                           "AND entity_type = 'project'", (registry.workspace_uuid,)).fetchone()[0]
    assert counter == 9  # four numbers issued, none burned by the crash
    assert report["verification"] == {"passed": True, "failures": []}


def test_an_apply_stopped_before_a_backlog_items_workflow_row_gives_it_one_on_resume(
        tmp_path, monkeypatch, capsys):
    """/pd:add-to-backlog step 4 on the resume path: a run that stopped after
    register_entity and before init_entity_workflow leaves a recorded item
    with no workflow row. The re-run takes the item as already recreated and
    still writes its row."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    straight = _build_registry(tmp_path / "straight")
    interrupted = _build_registry(tmp_path / "interrupted")
    assert c22.main(_args(straight, "--apply")) == 0
    first_item = "backlog:279-pre-review-lint-for-curly"

    ensure_backlog_workflow = c22._ensure_backlog_workflow

    def stop_before_the_workflow_row(context, replacement):
        raise KeyboardInterrupt

    monkeypatch.setattr(c22, "_ensure_backlog_workflow", stop_before_the_workflow_row)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(interrupted, "--apply"))

    midway = _connect(interrupted.db_path)
    assert sorted(_replacements(midway, interrupted.workspace_uuid)) == [first_item]
    assert midway.execute("SELECT COUNT(*) FROM workflow_phases WHERE type_id = ?",
                          (first_item,)).fetchone()[0] == 0
    assert _entity(midway, interrupted.workspace_uuid, "backlog:00059")["is_archived"] == 0
    midway.close()

    monkeypatch.setattr(c22, "_ensure_backlog_workflow", ensure_backlog_workflow)
    capsys.readouterr()
    assert c22.main(_args(interrupted, "--apply")) == 0
    report = json.loads(capsys.readouterr().out)
    assert {a["group"]: a["how"] for a in report["actions"]}["backlog:00059"] == "already recreated"
    conn = _connect(interrupted.db_path)
    assert tuple(conn.execute("SELECT workflow_phase, kanban_column FROM workflow_phases "
                              "WHERE type_id = ?", (first_item,)).fetchone()) == ("open", "backlog")
    conn.close()
    assert _end_state(interrupted) == _end_state(straight)


def _with_artifacts_root(args: list[str], artifacts_root: Path) -> list[str]:
    args = list(args)
    args[args.index("--artifacts-root") + 1] = str(artifacts_root)
    return args


def test_a_resume_through_a_symlinked_artifacts_root_adopts_the_unrecorded_project(
        registry, tmp_path, monkeypatch, capsys):
    """Adoption compares where the directories resolve, as init_project_state's
    own containment check does, and resumes the registration under the
    directory the earlier run recorded."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    stopped = _stop_before_the_first_record(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(registry, "--apply"))
    capsys.readouterr()
    alias = tmp_path / "artifacts-alias"
    alias.symlink_to(registry.artifacts_root, target_is_directory=True)

    assert c22.main(_with_artifacts_root(_args(registry, "--apply"), alias)) == 0

    report = json.loads(capsys.readouterr().out)
    assert [(a["replacement"], a["replacement_uuid"]) for a in report["actions"]
            if a["how"] == "adopted"] == [("project:005-iflow-arch-evolution", stopped[0])]
    conn = _connect(registry.db_path)
    projects = conn.execute("SELECT type_id FROM entities WHERE workspace_uuid = ? "
                            "AND kind = 'project' AND is_legacy = 0",
                            (registry.workspace_uuid,)).fetchall()
    assert sorted(r[0] for r in projects) == sorted(
        {v for v in REPLACEMENT_OF.values() if v.startswith("project:")})
    assert _entity(conn, registry.workspace_uuid, "project:005-iflow-arch-evolution")[
        "artifact_path"] == str(registry.artifacts_root / "projects" / "005-iflow-arch-evolution")
    assert report["verification"] == {"passed": True, "failures": []}


def test_a_resume_with_another_artifacts_root_refuses_rather_than_register_twice(
        registry, tmp_path, monkeypatch, capsys):
    """A project with the planned slug and parent, unrecorded, at a directory
    this run's artifacts root does not reach: the allocator would issue a
    second number for the same originals. The run refuses instead."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    _stop_before_the_first_record(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        c22.main(_args(registry, "--apply"))
    capsys.readouterr()
    elsewhere = tmp_path / "elsewhere"
    before = _file_fingerprint(registry.db_path)

    for mode in ("--plan", "--apply"):
        assert c22.main(_with_artifacts_root(_args(registry, mode), elsewhere)) == 2
        err = capsys.readouterr().err
        assert "project:005-iflow-arch-evolution" in err, mode
        assert str(registry.artifacts_root / "projects" / "005-iflow-arch-evolution") in err, mode
    assert _file_fingerprint(registry.db_path) == before
    assert not elsewhere.exists()


# ---------------------------------------------------------------------------
# verify(): the run's own last check, and --apply's exit code
# ---------------------------------------------------------------------------


def test_apply_exits_1_and_names_a_child_it_failed_to_move(registry, monkeypatch, capsys):
    """A production path that quietly did not do its part is caught by
    verify(), which sets the exit code; the re-run finishes the move."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    conn = _connect(registry.db_path)
    left_behind = _entity(conn, registry.workspace_uuid, "feature:118-uuidv7-identity")["uuid"]
    conn.close()
    reparent_entity = EntityDatabase.reparent_entity

    def skip_one_child(self, type_id, new_parent_uuid, **kwargs):
        if type_id == left_behind:
            return type_id
        return reparent_entity(self, type_id, new_parent_uuid, **kwargs)

    monkeypatch.setattr(EntityDatabase, "reparent_entity", skip_one_child)
    assert c22.main(_args(registry, "--apply")) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["verification"] == {"passed": False, "failures": [
        "feature:118-uuidv7-identity did not move onto project:008-entity-db-redesign",
        "['feature:118-uuidv7-identity'] still point at project:P004-entity-db-redesign",
    ]}

    monkeypatch.setattr(EntityDatabase, "reparent_entity", reparent_entity)
    assert c22.main(_args(registry, "--apply")) == 0
    report = json.loads(capsys.readouterr().out)
    assert [(a["replacement"], a["children_moved"]) for a in report["actions"]
            if a["children_moved"]] == [("project:008-entity-db-redesign",
                                         ["feature:118-uuidv7-identity"])]
    assert report["verification"] == {"passed": True, "failures": []}


def _plan_before_apply(registry: Registry) -> c22.Plan:
    with contextlib.closing(c22.open_read_only(str(registry.db_path))) as conn:
        return c22.derive_plan(conn, str(registry.workspace_root), str(registry.artifacts_root))


def _write_with_entity_database(registry: Registry, write) -> None:
    db = EntityDatabase(str(registry.db_path))
    try:
        write(db)
    finally:
        db.close()


def _write_sql(registry: Registry, statement: str, parameters: tuple = ()) -> None:
    """A write no production path makes: it stands for damage."""
    conn = sqlite3.connect(registry.db_path)
    try:
        conn.execute(statement, parameters)
        conn.commit()
    finally:
        conn.close()


# Each breaks one fact after a clean apply and returns the start of every
# failure verify() must then report, in its order. Production paths where
# one exists; else the file, an artifact, or the plan verify compares with.
def _unarchive_an_original(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.set_archived(
        "project:P002", archived=False, workspace_uuid=registry.workspace_uuid))
    return ["project:P002 is not archived"]


def _change_an_originals_status(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.update_entity(
        uuid_of["project:P002"], status="completed", workspace_uuid=registry.workspace_uuid))
    return ["project:P002's status moved 'active' -> 'completed'"]


def _move_a_child_back_onto_its_original(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.reparent_entity(
        uuid_of["feature:079-fts5-backfill"], uuid_of["project:P002"],
        workspace_uuid=registry.workspace_uuid))
    return ["feature:079-fts5-backfill did not move onto project:006-memory-flywheel",
            "['feature:079-fts5-backfill'] still point at project:P002"]


def _move_the_residue_child(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.reparent_entity(
        uuid_of["feature:112-workspace-identity-cleanup"],
        uuid_of["project:007-entity-system-redesign"], workspace_uuid=registry.workspace_uuid))
    return ["residue child feature:112-workspace-identity-cleanup left "
            "project:P003-entity-system-redesign"]


def _empty_a_replacements_record(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.update_entity(
        uuid_of["project:006-memory-flywheel"], metadata={RECREATED_FROM_KEY: []},
        workspace_uuid=registry.workspace_uuid))
    return ["project:P002: 0 recorded replacements"]


def _delete_a_backlog_items_workflow_row(registry, plan, uuid_of):
    _write_sql(registry, "DELETE FROM workflow_phases WHERE type_id = ?",
               ("backlog:279-pre-review-lint-for-curly",))
    return ["backlog:279-pre-review-lint-for-curly lacks its backlog workflow row"]


def _remove_a_projects_meta_json(registry, plan, uuid_of):
    directory = registry.artifacts_root / "projects" / "006-memory-flywheel"
    (directory / ".meta.json").unlink()
    return [f"project:006-memory-flywheel has no .meta.json at {directory}"]


def _delete_a_features_display_row(registry, plan, uuid_of):
    child = uuid_of["feature:079-fts5-backfill"]
    _write_sql(registry, "DELETE FROM entity_display WHERE uuid = ?", (child,))
    return [f"display_row_invariant: Entity '{child}' (feature:079-fts5-backfill) has no "
            f"entity_display row"]


def _raise_the_project_high_water_mark_to_the_first_issued_number(registry, plan, uuid_of):
    plan.buckets["project"]["legacy_high_water"] = 5
    return ["project:005-iflow-arch-evolution: 5 does not clear the legacy high-water mark 5"]


def _count_an_issued_number_as_legacy(registry, plan, uuid_of):
    plan.legacy_numbers["backlog"].add(280)
    return ["backlog:280-low-security-resolve-project reuses legacy number 280"]


def _unarchive_the_openclaw_row(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.set_archived(
        OPENCLAW, archived=False, workspace_uuid=registry.workspace_uuid))
    return [f"{OPENCLAW} is not archived"]


def _change_the_openclaw_rows_status(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.update_entity(
        uuid_of[OPENCLAW], status="completed", workspace_uuid=registry.workspace_uuid))
    return [f"{OPENCLAW}'s status moved 'active' -> 'completed'"]


def _record_the_openclaw_row_as_replaced(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.update_entity(
        uuid_of["project:005-iflow-arch-evolution"],
        metadata={RECREATED_FROM_KEY: [uuid_of["project:P001"], uuid_of[OPENCLAW]]},
        workspace_uuid=registry.workspace_uuid))
    return [f"{OPENCLAW} is recorded as replaced by project:005-iflow-arch-evolution"]


def _give_the_openclaw_row_a_child(registry, plan, uuid_of):
    _write_with_entity_database(registry, lambda db: db.reparent_entity(
        uuid_of["feature:079-fts5-backfill"], uuid_of[OPENCLAW],
        workspace_uuid=registry.workspace_uuid))
    return ["feature:079-fts5-backfill did not move onto project:006-memory-flywheel",
            f"['feature:079-fts5-backfill'] still point at {OPENCLAW}"]


@pytest.mark.parametrize("break_one_fact", [
    _unarchive_an_original,
    _change_an_originals_status,
    _move_a_child_back_onto_its_original,
    _move_the_residue_child,
    _empty_a_replacements_record,
    _delete_a_backlog_items_workflow_row,
    _remove_a_projects_meta_json,
    _delete_a_features_display_row,
    _raise_the_project_high_water_mark_to_the_first_issued_number,
    _count_an_issued_number_as_legacy,
    _unarchive_the_openclaw_row,
    _change_the_openclaw_rows_status,
    _record_the_openclaw_row_as_replaced,
    _give_the_openclaw_row_a_child,
], ids=lambda breaker: breaker.__name__.strip("_"))
def test_verify_names_each_fact_that_does_not_hold(registry, monkeypatch, capsys, break_one_fact):
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    plan = _plan_before_apply(registry)
    assert c22.main(_args(registry, "--apply")) == 0
    capsys.readouterr()
    with contextlib.closing(c22.open_read_only(str(registry.db_path))) as conn:
        assert c22.verify(conn, plan) == []
        uuid_of = {r["type_id"]: r["uuid"] for r in conn.execute(
            "SELECT type_id, uuid FROM entities WHERE workspace_uuid = ?",
            (registry.workspace_uuid,))}

    expected = break_one_fact(registry, plan, uuid_of)

    with contextlib.closing(c22.open_read_only(str(registry.db_path))) as conn:
        failures = c22.verify(conn, plan)
    assert len(failures) == len(expected), failures
    for failure, start in zip(failures, expected):
        assert failure.startswith(start), failures


# ---------------------------------------------------------------------------
# Refusals: each writes nothing
# ---------------------------------------------------------------------------


def test_apply_refuses_when_the_derivation_differs_from_the_locked_scope(registry, capsys):
    before = _file_fingerprint(registry.db_path)

    assert c22.main(_args(registry, "--apply")) == 3

    err = capsys.readouterr().err
    assert "project:P004-entity-db-redesign: 3 children, locked 16" in err
    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()


def test_apply_refuses_when_the_rows_archived_without_a_replacement_differ_from_the_lock(
        registry, monkeypatch, capsys):
    """The locked scope pins which rows a group archives without a
    replacement; a derivation that differs writes nothing."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", {
        **FIXTURE_SCOPE, "project:P001": {"absorbs": [], "children": 0}})
    before = _file_fingerprint(registry.db_path)

    assert c22.main(_args(registry, "--apply")) == 3

    assert f"project:P001: archives without a replacement ['{OPENCLAW}'], locked []" in \
        capsys.readouterr().err
    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()


def test_refuses_a_group_whose_later_row_is_out_of_scope(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    registry = _build_registry(tmp_path / "registry", archived_half_created_later=True)
    before = _file_fingerprint(registry.db_path)

    for mode in ("--plan", "--apply"):
        assert c22.main(_args(registry, mode)) == 2
        assert "project:P002-memory-flywheel" in capsys.readouterr().err
    assert _file_fingerprint(registry.db_path) == before


def test_refuses_a_group_with_no_single_latest_row(tmp_path, monkeypatch, capsys):
    """The survivor is the row with the later created_at; two rows at the
    group's latest created_at leave no survivor to pick."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    registry = _build_registry(tmp_path / "registry", p001_pair_created_together=True)
    before = _file_fingerprint(registry.db_path)

    for mode in ("--plan", "--apply"):
        assert c22.main(_args(registry, mode)) == 2
        err = capsys.readouterr().err
        assert "['project:P001', 'project:P001-openclaw-gap-analysis'] share the latest " \
               "created_at of their group; no survivor" in err, mode
    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()


def test_refuses_when_the_survivor_rule_picks_the_openclaw_row(tmp_path, monkeypatch, capsys):
    """A row decided to be archived without a replacement cannot be its
    group's survivor: the survivor rule would recreate it."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    registry = _build_registry(tmp_path / "registry", openclaw_created_later=True)
    before = _file_fingerprint(registry.db_path)

    for mode in ("--plan", "--apply"):
        assert c22.main(_args(registry, mode)) == 2, mode
        assert (f"the later-created row of project group 1, {OPENCLAW}, is to be archived "
                f"without a replacement") in capsys.readouterr().err, mode
    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()


def test_refuses_when_a_project_directory_already_holds_the_next_number(
        registry, monkeypatch, capsys):
    """/pd:create-project step 4: a number at or below an existing project
    directory's, legacy P-prefixed directories included, creates nothing."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    (registry.artifacts_root / "projects" / "P005-already-on-disk").mkdir(parents=True)
    before = _file_fingerprint(registry.db_path)

    assert c22.main(_args(registry, "--apply")) == 2

    assert "P005-already-on-disk" in capsys.readouterr().err
    assert _file_fingerprint(registry.db_path) == before


# Each puts the fixture in a state C22 must refuse; the test then shows the
# refusal names that state and writes nothing.
def _state_schema_version_6(registry):
    _write_sql(registry, "UPDATE _metadata SET value = '6' WHERE key = 'schema_version'")


def _record_another_checkouts_project_id(registry):
    _write_sql(registry, "UPDATE workspaces SET project_id_legacy = 'another-checkout' "
                         "WHERE uuid = ?", (registry.workspace_uuid,))


def _name_the_other_workspace_in_workspace_json(registry):
    workspace_file = registry.workspace_root / ".claude" / "pd" / "workspace.json"
    workspace_file.parent.mkdir(parents=True)
    workspace_file.write_text(json.dumps({"workspace_uuid": registry.other_workspace_uuid}))


def _record_one_replacement_for_two_groups(registry):
    def register(db):
        originals = [db.resolve_ref(type_id, workspace_uuid=registry.workspace_uuid)
                     for type_id in ("backlog:00059", "backlog:00177")]
        db.register_entity("backlog", name="made by hand", seq=400, slug="made-by-hand",
                           status="open", workspace_uuid=registry.workspace_uuid,
                           metadata={RECREATED_FROM_KEY: originals})
    _write_with_entity_database(registry, register)


def _lower_the_backlog_counter_to_its_legacy_high_water(registry):
    _write_sql(registry, "UPDATE sequences SET next_val = 177 WHERE workspace_uuid = ? "
                         "AND entity_type = 'backlog'", (registry.workspace_uuid,))


def _drop_the_project_counter(registry):
    _write_sql(registry, "DELETE FROM sequences WHERE workspace_uuid = ? "
                         "AND entity_type = 'project'", (registry.workspace_uuid,))


def _hang_a_child_on_the_openclaw_row(registry):
    _write_with_entity_database(registry, lambda db: _feature(
        db, registry.workspace_uuid, OPENCLAW_CHILD.partition(":")[2],
        db.resolve_ref(OPENCLAW, workspace_uuid=registry.workspace_uuid)))


def _archive_another_p002_half_with_another_brainstorm(registry):
    _write_with_entity_database(registry, lambda db: _legacy(
        db, registry.workspace_uuid, "project", "P002-memory-flywheel-again", "Memory Flywheel",
        "active", "2026-04-15T14:30:00.000000+00:00",
        artifact_path="docs/projects/P002-memory-flywheel", archived=True,
        metadata=json.dumps({"brainstorm_source": "docs/brainstorms/elsewhere.prd.md"})))


@pytest.mark.parametrize("put_in_state, modes, reason", [
    (_state_schema_version_6, ("--plan", "--apply"),
     "would migrate anything else on open"),
    (_record_another_checkouts_project_id, ("--plan", "--apply"),
     "records project_id_legacy 'another-checkout'"),
    (_name_the_other_workspace_in_workspace_json, ("--plan", "--apply"),
     "workspace.json names workspace"),
    (_record_one_replacement_for_two_groups, ("--plan", "--apply"),
     "but backlog:00059's group is"),
    (_lower_the_backlog_counter_to_its_legacy_high_water, ("--apply",),
     "the backlog counter 177 does not clear its legacy high-water mark 177"),
    (_drop_the_project_counter, ("--apply",),
     "the project bucket has no sequences counter"),
    (_hang_a_child_on_the_openclaw_row, ("--plan", "--apply"),
     f"{OPENCLAW} is to be archived without a replacement, but holds children "
     f"['{OPENCLAW_CHILD}']"),
    (_archive_another_p002_half_with_another_brainstorm, ("--plan", "--apply"),
     "the archived halves of project:P002's pair carry different brainstorm_source values"),
], ids=lambda value: value.__name__.strip("_") if callable(value) else None)
def test_each_refusal_names_its_reason_and_writes_nothing(
        registry, monkeypatch, capsys, put_in_state, modes, reason):
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    put_in_state(registry)
    before = _file_fingerprint(registry.db_path)

    for mode in modes:
        assert c22.main(_args(registry, mode)) == 2, mode
        assert reason in capsys.readouterr().err, mode
    assert _file_fingerprint(registry.db_path) == before
    assert not registry.artifacts_root.exists()


def test_a_project_directory_appearing_after_preflight_stops_before_registering(
        registry, monkeypatch, capsys):
    """The number allocate_entity_id issued is checked against the project
    directories again before init_project_state, so a directory that
    appeared after preflight (another /pd:create-project) stops the run: the
    number is spent, nothing is registered under it."""
    monkeypatch.setattr(c22, "LOCKED_SCOPE", FIXTURE_SCOPE)
    preflight = c22.preflight
    appeared = registry.artifacts_root / "projects" / "P005-appeared-meanwhile"

    def a_directory_appears_after_preflight(plan):
        preflight(plan)
        appeared.mkdir(parents=True)

    monkeypatch.setattr(c22, "preflight", a_directory_appears_after_preflight)
    assert c22.main(_args(registry, "--apply")) == 1

    err = capsys.readouterr().err
    assert "P005-appeared-meanwhile" in err and "number 5 is spent, nothing registered" in err
    conn = _connect(registry.db_path)
    assert conn.execute("SELECT COUNT(*) FROM entities WHERE workspace_uuid = ? AND kind = 'project' "
                        "AND is_legacy = 0", (registry.workspace_uuid,)).fetchone()[0] == 0
    assert conn.execute("SELECT next_val FROM sequences WHERE workspace_uuid = ? "
                        "AND entity_type = 'project'", (registry.workspace_uuid,)).fetchone()[0] == 6
    conn.close()
    assert [p.name for p in (registry.artifacts_root / "projects").iterdir()] == [appeared.name]


def test_the_script_holds_no_sql_that_writes():
    """Every write goes through a production path; the script's own SQL only reads."""
    tree = ast.parse(Path(c22.__file__).read_text())
    docstrings = {
        id(node.body[0].value) for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    literals = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings]
    write_statement = re.compile(
        r"^\s*(INSERT|UPDATE|DELETE|REPLACE|UPSERT|CREATE|DROP|ALTER|BEGIN|COMMIT)\b", re.I)
    # The scan sees the script's SQL at all: its reads are there.
    assert any(re.match(r"\s*SELECT\b", s) for s in literals)
    assert [s for s in literals if write_statement.match(s)] == []
    assert "executescript" not in Path(c22.__file__).read_text()


# ---------------------------------------------------------------------------
# The rehearsal on a live snapshot (opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get(SNAPSHOT_ENV),
                    reason=f"{SNAPSHOT_ENV} does not name a live registry snapshot")
def test_rehearsal_on_a_snapshot_copy(tmp_path, capsys):
    snapshot = Path(os.environ[SNAPSHOT_ENV])
    rehearsal = tmp_path / "rehearsal.db"
    shutil.copyfile(snapshot, rehearsal)
    artifacts = tmp_path / "artifacts"
    args = ["--db", str(rehearsal), "--workspace-root", LIVE_WORKSPACE_ROOT,
            "--artifacts-root", str(artifacts), "--apply"]

    assert c22.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["verification"] == {"passed": True, "failures": []}

    before = registry_rows(snapshot)
    after = registry_rows(rehearsal)
    diff = diff_registries(before, after)
    assert summarize(diff) == {
        "entities": {"added": 10, "removed": 0, "changed_columns": {
            ("is_archived", "updated_at"): 11, ("parent_uuid", "updated_at"): 25}},
        "entities_fts": {"added": 10, "removed": 0, "changed_columns": {}},
        "entity_display": {"added": 10, "removed": 0, "changed_columns": {}},
        "events": {"added": 35, "removed": 0, "changed_columns": {},
                   "added_by_type": {"entity_created": 10, "reparented": 25}},
        "phase_events": {"added": 10, "removed": 0, "changed_columns": {},
                         "added_by_type": {"entity_created": 10}},
        "sequences": {"added": 0, "removed": 0, "changed_columns": {("next_val",): 2}},
        "sqlite_sequence": {"added": 0, "removed": 0, "changed_columns": {("seq",): 1}},
        "workflow_phases": {"added": 6, "removed": 0, "changed_columns": {}},
    }
    workspace = next(r["uuid"] for r in before["workspaces"].values()
                     if r["project_root"] == LIVE_WORKSPACE_ROOT)
    advanced = {key[1]: (row["next_val"][0], row["next_val"][1])
                for key, row in diff["sequences"]["changed"].items()}
    assert {kind: new - old for kind, (old, new) in advanced.items()} == {"backlog": 6, "project": 4}
    assert all(key[0] == workspace for key in diff["sequences"]["changed"])
    for cols in diff["entities"]["changed"].values():
        assert "status" not in cols

    conn = _connect(rehearsal)
    by_type_id = {r["type_id"]: r for r in conn.execute(
        "SELECT * FROM entities WHERE workspace_uuid = ?", (workspace,))}
    p004_new = _replacements(conn, workspace)["project:008-entity-db-redesign"]
    assert len(_children(conn, p004_new["uuid"])) == 16
    assert _children(conn, by_type_id["project:P004-entity-db-redesign"]["uuid"]) == []
    assert len(_children(conn, _replacements(conn, workspace)["project:006-memory-flywheel"]["uuid"])) == 5
    assert len(_children(conn, _replacements(conn, workspace)["project:007-entity-system-redesign"]["uuid"])) == 4
    assert _children(conn, by_type_id["project:P003-entity-system-redesign"]["uuid"]) == \
        ["feature:112-workspace-identity-cleanup"]
    # The P001 lineage: 005 records P001 alone; the openclaw row is archived,
    # its status as it was, and no replacement records it.
    replacements = _replacements(conn, workspace)
    assert json.loads(replacements["project:005-iflow-arch-evolution"]["metadata"])[
        RECREATED_FROM_KEY] == [by_type_id["project:P001"]["uuid"]]
    openclaw = by_type_id[OPENCLAW]
    assert (openclaw["is_archived"], openclaw["status"]) == (1, "active")
    assert not any(openclaw["uuid"] in json.loads(row["metadata"])[RECREATED_FROM_KEY]
                   for row in replacements.values())
    # brainstorm_source: the survivor's own, else its pair's archived half's.
    for type_id, brainstorm_source in {
            "project:005-iflow-arch-evolution": None,
            "project:006-memory-flywheel": MEMORY_FLYWHEEL_BRAINSTORM_SOURCE,
            "project:007-entity-system-redesign": ENTITY_SYSTEM_BRAINSTORM_SOURCE,
            "project:008-entity-db-redesign": P004_BRAINSTORM_SOURCE}.items():
        project = replacements[type_id]
        assert json.loads(project["metadata"]).get("brainstorm_source") == brainstorm_source
        meta = json.loads(Path(project["artifact_path"], ".meta.json").read_text())
        assert meta.get("brainstorm_source") == brainstorm_source
    assert check_display_row_invariant(conn).passed
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()

    # A second run changes nothing.
    assert c22.main(args) == 0
    capsys.readouterr()
    assert diff_registries(after, registry_rows(rehearsal)) == {}
