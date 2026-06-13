"""Project identity detection for cross-project entity scoping.

Provides:
- resolve_workspace_uuid(): UUID-based workspace identity (FR-3 precedence)
- _compute_legacy_project_id(): 12-char hex (migration-only helper)
- collect_git_info(): full git metadata as GitProjectInfo dataclass
- normalize_remote_url(): canonical host/owner/repo URL form
"""
from __future__ import annotations

import dataclasses
import fcntl
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import sqlite3
import tempfile
import uuid as uuid_mod
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Phase D: workspace UUID resolution (FR-3 precedence chain).
# ---------------------------------------------------------------------------

# 36-char lowercase hyphenated UUID format. Accepts both v4 and v7 (the
# version nibble is allowed to be any hex digit so a future F6 uuid7 deploy
# does not need to widen this regex).
_WORKSPACE_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$'
)


class WorkspaceCorruptedError(RuntimeError):
    """Raised when ``.claude/pd/workspace.json`` is malformed or has an
    incompatible schema_version."""


def _validate_workspace_uuid(value: str) -> str:
    """Return ``value`` if it matches the 36-char UUID regex, else raise."""
    if not isinstance(value, str) or not _WORKSPACE_UUID_RE.match(value):
        raise ValueError(
            f"Malformed workspace UUID (expected 36-char lowercase "
            f"hyphenated): {value!r}"
        )
    return value


def _atomic_workspace_json_write(target_path: str, uuid_value: str) -> str:
    """Atomic create-if-absent with cross-process consistency.

    Uses ``fcntl.flock(LOCK_EX)`` on a sentinel ``<target_path>.lock`` file
    in the same directory. Caller order:

      1. Acquire exclusive flock on ``<target_path>.lock``.
      2. Re-check existence; if file exists, read and return its UUID
         (loser case — winner's UUID is returned to ALL callers).
      3. Write tempfile (same dir) + ``os.replace``.
      4. Re-read file content for return value.
      5. Release flock.

    Guarantees: under N parallel callers, all return the SAME UUID
    (either the writer's or the existing-file reader's). Re-read-after-rename
    WITHOUT flock is BROKEN because each racer's ``os.replace`` overwrites
    others' tempfiles; the loser would read back its own discarded UUID.

    Parameters
    ----------
    target_path:
        Absolute path to ``.claude/pd/workspace.json``. Parent dir is
        created via ``os.makedirs(..., exist_ok=True)`` if missing.
    uuid_value:
        Candidate UUID to write IFF no existing file is present. Must be a
        valid 36-char lowercase hyphenated UUID.

    Returns
    -------
    str
        The UUID that ended up on disk (winner's or pre-existing).

    Raises
    ------
    OSError: mkdir, open, or rename failure.
    ValueError: candidate uuid_value malformed, or existing file's
        ``workspace_uuid`` field malformed.
    """
    _validate_workspace_uuid(uuid_value)
    parent_dir = os.path.dirname(target_path)
    os.makedirs(parent_dir, exist_ok=True)
    lock_path = target_path + ".lock"

    # Open the lock file (creating if necessary). Use os.open so we can
    # explicitly close it; fcntl.flock requires a file descriptor.
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        # Step 1: acquire exclusive flock (blocks until available).
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # Step 2: re-check existence; loser case returns existing UUID.
        if os.path.exists(target_path):
            with open(target_path, encoding="utf-8") as fh:
                existing = json.load(fh)
            existing_uuid = existing.get("workspace_uuid")
            if not isinstance(existing_uuid, str):
                raise ValueError(
                    f"workspace.json missing 'workspace_uuid' field: "
                    f"{target_path}"
                )
            return _validate_workspace_uuid(existing_uuid)

        # Step 3: tempfile (same dir) + os.replace.
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "workspace_uuid": uuid_value,
            "schema_version": 1,
            "created_at": now_iso,
            "created_by": "session-start.sh",
        }
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".workspace.", suffix=".json.tmp", dir=parent_dir,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target_path)
            tmp_path = None  # success — no cleanup needed
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # Step 4: re-read file content for return value.
        with open(target_path, encoding="utf-8") as fh:
            written = json.load(fh)
        return _validate_workspace_uuid(written["workspace_uuid"])
    finally:
        # Step 5: release flock + close fd.
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _lookup_workspace_uuid_by_project_root(
    conn: sqlite3.Connection, project_root_abs: str
) -> str | None:
    """Look up a single workspace_uuid by project_root match.

    Returns the workspace_uuid for a single matching row; returns ``None``
    if zero rows match, multiple rows match, or ``project_root`` is NULL
    for the candidate row(s).

    Note: requires Migration 11 applied. The caller MUST gate on
    ``_metadata.schema_version >= 11``.
    """
    rows = conn.execute(
        "SELECT uuid FROM workspaces "
        "WHERE project_root IS NOT NULL AND project_root = ?",
        (project_root_abs,),
    ).fetchall()
    if len(rows) == 1:
        return rows[0][0]
    return None


def _read_workspace_json(target_path: str) -> str:
    """Read and validate workspace.json; return its workspace_uuid.

    Raises
    ------
    WorkspaceCorruptedError
        - File present but unreadable / malformed JSON.
        - ``schema_version`` not equal to 1.
        - ``workspace_uuid`` missing or malformed.

    Side effects
    ------------
    Emits a WARN log to stderr if the file contains unknown top-level keys
    (extra keys are tolerated, not aborted).
    """
    try:
        with open(target_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceCorruptedError(
            f"workspace.json unreadable or malformed at {target_path}: "
            f"{exc!r}"
        ) from exc

    if not isinstance(data, dict):
        raise WorkspaceCorruptedError(
            f"workspace.json must be a JSON object: got {type(data).__name__}"
        )
    sv = data.get("schema_version")
    if sv != 1:
        raise WorkspaceCorruptedError(
            f"workspace.json schema_version={sv!r}; expected 1"
        )
    ws_uuid = data.get("workspace_uuid")
    if not isinstance(ws_uuid, str):
        raise WorkspaceCorruptedError(
            "workspace.json missing or non-string 'workspace_uuid'"
        )
    try:
        _validate_workspace_uuid(ws_uuid)
    except ValueError as exc:
        raise WorkspaceCorruptedError(str(exc)) from exc

    # Tolerate (with WARN) unknown top-level keys.
    KNOWN_KEYS = {
        "workspace_uuid", "schema_version", "created_at", "created_by",
        "project_id_legacy",
    }
    extras = set(data.keys()) - KNOWN_KEYS
    if extras:
        print(
            f"[workspace.json] WARN: unknown top-level key(s): "
            f"{sorted(extras)}",
            file=sys.stderr,
        )
    return ws_uuid


def _entities_db_path() -> str:
    """Resolve the entities.db path with the same precedence the MCP servers
    use (``ENTITY_DB_PATH`` env override → global store).

    Kept in lock-step with ``mcp/entity_server.py`` lifespan (and
    ``workflow_state_server.py``): both honour ``ENTITY_DB_PATH``. The runtime
    ``resolve_workspace_uuid`` historically hard-coded the global path, which
    diverged from the servers under test harnesses that set ``ENTITY_DB_PATH``;
    routing every DB touch through this helper removes that split.
    """
    return os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )


def _insert_workspace_row_if_absent(
    conn: sqlite3.Connection,
    workspace_uuid: str,
    project_root: str | None,
    legacy_pid: str | None,
) -> str:
    """Insert a ``workspaces`` row for *workspace_uuid* iff safe to do so.

    Single source of the "create-a-workspace-row" SQL shared by the runtime
    resolver (via :func:`_ensure_workspace_row`), ``upsert_project``, and
    ``backfill_project_ids``. Does NOT open or commit a transaction — the
    caller's transaction/isolation applies (this is required: several callers
    are mid-transaction and a nested ``BEGIN`` would raise).

    Returns
    -------
    str
        - ``"exists"``    — a row with this uuid is already present (no-op).
        - ``"conflict-root"`` — *project_root* is already claimed by one or
          more rows with a DIFFERENT uuid; NO insert performed. The caller
          decides whether to adopt the existing row (single match) or warn
          and fall through (ambiguous multi-match).
        - ``"inserted"``  — a new row was inserted (possibly with
          ``project_id_legacy=NULL`` if the supplied *legacy_pid* collided
          with an existing row — the moved-repo case).

    Raises
    ------
    sqlite3.IntegrityError
        If even the ``legacy_pid=NULL`` retry fails (e.g. the uuid itself
        collided in a concurrent insert) — callers treat this as best-effort
        when wrapped by :func:`_ensure_workspace_row`.
    """
    row = conn.execute(
        "SELECT 1 FROM workspaces WHERE uuid = ?",
        (workspace_uuid,),
    ).fetchone()
    if row is not None:
        return "exists"

    # Our uuid is absent. If project_root is already claimed by other
    # uuid(s), refuse to mint a competing root claim — that is exactly how
    # the split-brain row got created in the first place.
    if project_root is not None:
        claimed = conn.execute(
            "SELECT 1 FROM workspaces "
            "WHERE project_root IS NOT NULL AND project_root = ? LIMIT 1",
            (project_root,),
        ).fetchone()
        if claimed is not None:
            return "conflict-root"

    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO workspaces "
            "(uuid, project_id_legacy, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (workspace_uuid, legacy_pid, project_root, now, now),
        )
    except sqlite3.IntegrityError:
        # The only other UNIQUE besides the uuid PK is project_id_legacy.
        # A legacy pid collision means a row with a different root already
        # owns this legacy id (moved/renamed repo). Insert with NULL legacy
        # so the workspace identity is still recorded; legacy resolution
        # continues to point at the original row.
        if legacy_pid is None:
            raise  # uuid PK collision (concurrent insert) — propagate.
        print(
            f"[workspace.json] WARN: project_id_legacy={legacy_pid!r} already "
            f"claimed; inserting workspace row {workspace_uuid} with NULL "
            f"legacy id",
            file=sys.stderr,
        )
        conn.execute(
            "INSERT INTO workspaces "
            "(uuid, project_id_legacy, project_root, created_at, updated_at) "
            "VALUES (?, NULL, ?, ?, ?)",
            (workspace_uuid, project_root, now, now),
        )
    return "inserted"


def _rewrite_workspace_json_if_matches(
    target_path: str, expected_uuid: str, new_uuid: str
) -> str:
    """Compare-and-swap rewrite of ``workspace.json`` under the file flock.

    Distinct from :func:`_atomic_workspace_json_write` (create-if-absent):
    this rewrites an EXISTING file, but only if its current ``workspace_uuid``
    still equals *expected_uuid* (CAS). Concurrent healers that already
    rewrote the file are no-ops — the loser returns the winner's value.

    Returns the uuid that ends up on disk (``new_uuid`` on a hit, the file's
    current uuid on a CAS miss).

    The written payload intentionally OMITS ``project_id_legacy`` — the
    adopted uuid is the authoritative identity post-heal and the legacy id is
    not meaningful for it (the consistency check's legacy-mismatch branch
    skips when the field is absent).
    """
    lock_path = target_path + ".lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        current = None
        if os.path.exists(target_path):
            try:
                with open(target_path, encoding="utf-8") as fh:
                    current = json.load(fh).get("workspace_uuid")
            except (OSError, json.JSONDecodeError):
                current = None
        if current != expected_uuid:
            # CAS miss — another healer won, or the file changed. Return the
            # current on-disk value if usable, else the expected (best effort).
            return current if isinstance(current, str) else expected_uuid

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "workspace_uuid": new_uuid,
            "schema_version": 1,
            "created_at": now_iso,
            "created_by": "self-heal",
        }
        parent_dir = os.path.dirname(target_path)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".workspace.", suffix=".json.tmp", dir=parent_dir,
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, target_path)
            tmp_path = None
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        return new_uuid
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _ensure_workspace_row(
    db_path: str, workspace_uuid: str, project_root: str | None
) -> str | None:
    """Best-effort: ensure a ``workspaces`` row exists for *workspace_uuid*.

    Opens its own short-lived read-write connection (used from the resolver,
    which is not inside an ``EntityDatabase`` transaction). Gated so it never
    creates the DB file and never touches a pre-Migration-11 schema.

    Returns the :func:`_insert_workspace_row_if_absent` result string
    (``"exists"``/``"inserted"``/``"conflict-root"``), or ``None`` when a gate
    is not met or any error occurs — callers continue with the candidate uuid
    unchanged in that case (the gap self-heals on a later resolve when the DB
    is reachable).
    """
    if not os.path.isfile(db_path):
        return None  # mode=rw must not create the file; bail before connect.
    conn = None
    try:
        # mode=rw (NOT rwc) — fails rather than creating a new empty DB.
        conn = sqlite3.connect(
            f"file:{db_path}?mode=rw", uri=True, timeout=2.0
        )
        conn.execute("PRAGMA busy_timeout = 2000")
        sv_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        try:
            sv = int(sv_row[0]) if sv_row is not None else 0
        except (TypeError, ValueError):
            sv = 0
        if sv < 11:
            return None
        legacy_pid = (
            _compute_legacy_project_id(project_root) if project_root else None
        )
        result = _insert_workspace_row_if_absent(
            conn, workspace_uuid, project_root, legacy_pid
        )
        conn.commit()
        return result
    except (sqlite3.Error, OSError, ValueError):
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass


def validate_or_adopt_workspace_uuid(
    candidate: str, project_root: str | None, db_path: str
) -> str:
    """Canonical "is this workspace uuid real, and if not what should it be?"

    Shared by the runtime resolver (file uuid), the MCP lifespans (inherited
    ``WORKSPACE_UUID`` env), and — indirectly — the write paths. Read-mostly:
    the only write is the missing-row insert via :func:`_ensure_workspace_row`.

    Membership alone is NOT sufficient — a candidate that exists but is bound
    to a DIFFERENT ``project_root`` is foreign (e.g. a workspace.json copied
    between projects, or a stale inherited ``WORKSPACE_UUID``) and must not be
    accepted for this root, or entities would cross-bind to another project's
    workspace.

    Precedence:
      1. Malformed candidate → raise ``ValueError`` (caller's problem).
      2. DB unreachable / pre-M11 → return *candidate* unchanged.
      3. *candidate* present AND its row's ``project_root`` is NULL or equals
         this root → return it (fast path; correctly ours / unscoped).
      4. Otherwise (orphaned, OR present-but-foreign-root) → exactly one row
         matches *project_root* → return that row's uuid (ADOPT).
      5. Orphaned + zero rows match *project_root* → insert a row carrying
         *candidate* and return it.
      6. Can't safely map (present-but-foreign with no/ambiguous root row, or
         orphaned + multiple root rows) → WARN, return *candidate*.
    """
    _validate_workspace_uuid(candidate)
    if not os.path.isfile(db_path):
        return candidate
    root_abs = os.path.abspath(project_root) if project_root else None
    is_member = False
    cand_root: str | None = None
    root_uuids: list[str] = []
    conn = None
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro", uri=True, timeout=2.0
        )
        sv_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        try:
            sv = int(sv_row[0]) if sv_row is not None else 0
        except (TypeError, ValueError):
            sv = 0
        if sv < 11:
            return candidate
        crow = conn.execute(
            "SELECT project_root FROM workspaces WHERE uuid = ?", (candidate,)
        ).fetchone()
        if crow is not None:
            is_member = True
            cand_root = crow[0]
        if root_abs is not None:
            root_uuids = [
                r[0]
                for r in conn.execute(
                    "SELECT uuid FROM workspaces "
                    "WHERE project_root IS NOT NULL AND project_root = ?",
                    (root_abs,),
                ).fetchall()
            ]
    except sqlite3.Error:
        return candidate
    finally:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass

    if is_member and (cand_root is None or cand_root == root_abs):
        return candidate  # correctly ours, or unscoped (NULL root)

    # Either orphaned, or a member bound to a different root (foreign).
    if len(root_uuids) == 1:
        return root_uuids[0]  # adopt this root's canonical row
    if not is_member and len(root_uuids) == 0:
        # Orphaned + this root unclaimed — record the candidate so the FK
        # resolves. (A foreign member is NOT inserted: its uuid already exists
        # elsewhere; we can't claim it here.)
        _ensure_workspace_row(db_path, candidate, project_root)
        return candidate
    why = (
        "present but bound to a different project_root"
        if is_member else "orphaned"
    )
    print(
        f"[workspace.json] WARN: candidate {candidate} is {why} and "
        f"project_root={project_root!r} has {len(root_uuids)} workspace "
        f"row(s); cannot safely adopt — leaving as-is",
        file=sys.stderr,
    )
    return candidate


def resolve_workspace_uuid(
    working_dir: str | None = None, db_path: str | None = None
) -> str:
    """Resolve workspace UUID for the given working directory (FR-3).

    ``db_path`` overrides the entities.db location (defaults to
    :func:`_entities_db_path`); threaded through so callers that already
    resolved a DB path reconcile/insert against the SAME database.

    Precedence chain:
      1. ``ENTITY_WORKSPACE_UUID`` env var (test override).
      2. ``<working_dir>/.claude/pd/workspace.json`` (file-based; project-level)
         — self-healing: an orphaned file uuid is reconciled against the
         workspaces table (adopt the project_root row, or insert the missing
         row) so file and DB stay consistent.
      3. workspaces-table lookup by ``project_root`` match (single row only).
      4. Fresh write — generate uuid4, persist via flock-synchronised atomic
         write, then record the matching workspaces row.

    Parameters
    ----------
    working_dir:
        Directory containing ``.claude/`` (defaults to ``os.getcwd()``).

    Returns
    -------
    str
        Canonical workspace UUID (36-char lowercase hyphenated).

    Raises
    ------
    ValueError: env var present but malformed.
    WorkspaceCorruptedError: workspace.json present but malformed.

    Side effects
    ------------
    Step 4 may write ``<working_dir>/.claude/pd/workspace.json`` and
    ``.claude/pd/workspace.json.lock`` (sentinel for fcntl.flock).
    """
    cwd = os.path.abspath(working_dir or os.getcwd())

    # Step 1: env var.
    env_uuid = os.environ.get("ENTITY_WORKSPACE_UUID")
    if env_uuid:
        return _validate_workspace_uuid(env_uuid)

    target_path = os.path.join(cwd, ".claude", "pd", "workspace.json")
    # ENTITY_DB_PATH-aware (matches the MCP servers); historically this was
    # hard-coded to the global store, which diverged under test harnesses.
    if db_path is None:
        db_path = _entities_db_path()

    # Step 2: file-based, with split-brain self-heal. A workspace.json whose
    # uuid is absent from the workspaces table (the F-incident: file written
    # without a matching DB row) is repaired here instead of being trusted
    # forever: adopt the project_root's canonical row (rewriting the file) or
    # insert the missing row so the FK resolves on the next write.
    if os.path.exists(target_path):
        file_uuid = _read_workspace_json(target_path)  # may raise (corrupt).
        resolved = validate_or_adopt_workspace_uuid(file_uuid, cwd, db_path)
        if resolved != file_uuid:
            print(
                f"[workspace.json] WARN: healed workspace split-brain: "
                f"adopted {resolved} from workspaces table (file had orphan "
                f"{file_uuid})",
                file=sys.stderr,
            )
            return _rewrite_workspace_json_if_matches(
                target_path, file_uuid, resolved
            )
        return resolved

    # Step 3: workspaces-table lookup (best-effort; DB may be missing).
    if os.path.isfile(db_path):
        try:
            conn = sqlite3.connect(
                f"file:{db_path}?mode=ro", uri=True, timeout=2.0,
            )
            try:
                # Gate on schema_version >= 11.
                row = conn.execute(
                    "SELECT value FROM _metadata WHERE key='schema_version'"
                ).fetchone()
                if row is not None:
                    try:
                        sv = int(row[0])
                    except (TypeError, ValueError):
                        sv = 0
                    if sv >= 11:
                        # Multi-row check: if >1 match, fall through with WARN.
                        rows = conn.execute(
                            "SELECT uuid FROM workspaces "
                            "WHERE project_root IS NOT NULL "
                            "  AND project_root = ?",
                            (cwd,),
                        ).fetchall()
                        if len(rows) == 1:
                            recovered = rows[0][0]
                            # Step 2.5: regenerate workspace.json with the
                            # recovered UUID; no WARN emitted.
                            try:
                                _validate_workspace_uuid(recovered)
                            except ValueError:
                                # Unexpected — fall through to step 4.
                                pass
                            else:
                                # Atomic write; under race the loser will
                                # see the existing-file path.
                                return _atomic_workspace_json_write(
                                    target_path, recovered
                                )
                        elif len(rows) > 1:
                            print(
                                "[workspace.json] WARN: workspaces table "
                                "has multiple rows matching project_root="
                                f"{cwd!r}; falling through to fresh write",
                                file=sys.stderr,
                            )
            finally:
                conn.close()
        except sqlite3.Error:
            # Best-effort; any DB error → fall through to step 4.
            pass

    # Step 4: fresh write — but ONLY if `.claude/` already exists in the
    # working directory. This honours the long-standing pd convention that
    # `.claude/` is the marker indicating pd is active for this project;
    # we must not auto-create it (test-hooks: "Config was created despite
    # no .claude/ directory" was failing because os.makedirs on the chain
    # `.claude/pd/workspace.json` was implicitly creating `.claude/`).
    claude_dir = os.path.join(cwd, ".claude")
    if not os.path.isdir(claude_dir):
        raise WorkspaceCorruptedError(
            f"Cannot resolve workspace_uuid: .claude/ directory missing at "
            f"{cwd!r} and no ENTITY_WORKSPACE_UUID env var was set. "
            f"Create .claude/ (e.g., 'mkdir .claude') to enable pd for this "
            f"project, or set ENTITY_WORKSPACE_UUID explicitly."
        )
    fresh_uuid = str(uuid_mod.uuid4())
    # Write the file FIRST (flock decides the race winner and the returned
    # uuid is authoritative), THEN record the matching workspaces row so the
    # file and DB never diverge. Never hold the flock across the DB write.
    written = _atomic_workspace_json_write(target_path, fresh_uuid)
    _ensure_workspace_row(db_path, written, cwd)
    return written


def resolve_startup_workspace_uuid(
    project_root: str, db_path: str | None = None
) -> str:
    """Resolve the workspace identity for an MCP server lifespan.

    Shared by ``entity_server`` and ``workflow_state_server`` startup. The two
    env vars are NOT equivalent:

      * ``ENTITY_WORKSPACE_UUID`` — absolute test/explicit override. Used
        verbatim (format-validated only); never reconciled against the DB.
      * ``WORKSPACE_UUID`` — inherited from the session-start hook. Treated as
        a CANDIDATE: reconciled via :func:`validate_or_adopt_workspace_uuid`
        so a stale value adopts the project_root's canonical row instead of
        being trusted blindly (the env-bypass that would otherwise re-open the
        split-brain even after the resolver/write paths were hardened).

    When both are set, ``ENTITY_WORKSPACE_UUID`` wins (the historical
    short-circuit is preserved). With neither set, falls back to the full
    file→DB→mint :func:`resolve_workspace_uuid` (which self-heals).
    """
    db = db_path if db_path is not None else _entities_db_path()
    env_abs = os.environ.get("ENTITY_WORKSPACE_UUID")
    if env_abs:
        return _validate_workspace_uuid(env_abs)
    env_candidate = os.environ.get("WORKSPACE_UUID")
    if env_candidate:
        resolved = validate_or_adopt_workspace_uuid(
            env_candidate, project_root, db
        )
        if resolved != env_candidate:
            print(
                f"[workspace] WARN: inherited WORKSPACE_UUID {env_candidate} "
                f"reconciled to {resolved} for project_root {project_root!r}",
                file=sys.stderr,
            )
        return resolved
    # No env hint — full file→DB→mint resolution against the SAME db_path.
    return resolve_workspace_uuid(project_root, db_path=db)


@dataclasses.dataclass(frozen=True)
class GitProjectInfo:
    """Immutable git project metadata for the projects table."""

    project_id: str  # 12-char hex
    root_commit_sha: str  # full 40-char or ""
    name: str  # human-readable
    remote_url: str  # raw origin URL or ""
    normalized_url: str  # canonical host/owner/repo or ""
    remote_host: str  # e.g. "github.com" or ""
    remote_owner: str  # e.g. "terry" or ""
    remote_repo: str  # e.g. "pedantic-drip" or ""
    default_branch: str  # e.g. "main" or ""
    project_root: str  # absolute path
    is_git_repo: bool


def normalize_remote_url(raw_url: str) -> str:
    """Normalize a git remote URL to canonical ``host/owner/repo`` form.

    Normalization steps (in order):
    1. Strip scheme (https://, ssh://, git://)
    2. Strip user@ prefix (git@, ssh@)
    3. Replace ``:`` with ``/`` for SCP-style URLs (first ``:`` after host)
    4. Strip trailing ``.git``
    5. Strip trailing ``/``
    6. Lowercase the host portion
    7. Return ``host/owner/repo``

    Empty string input returns empty string.
    """
    if not raw_url:
        return ""

    url = raw_url

    # Step 1: Strip scheme
    url = re.sub(r"^(https?|ssh|git)://", "", url)

    # Step 2: Strip user@ prefix
    url = re.sub(r"^[^@]+@", "", url)

    # Step 3: SCP colon -> slash (only first : after host, when no / precedes it)
    # This handles git@github.com:owner/repo style
    # But not /path/to/repo (local paths start with /)
    if not url.startswith("/"):
        url = re.sub(r"^([^/:]+):", r"\1/", url)

    # Step 4: Strip trailing .git
    url = re.sub(r"\.git$", "", url)

    # Step 5: Strip trailing /
    url = url.rstrip("/")

    # Step 6: Lowercase the host portion
    # Host is everything before the first /
    slash_idx = url.find("/")
    if slash_idx > 0:
        host = url[:slash_idx].lower()
        rest = url[slash_idx:]
        url = host + rest

    return url


def _run_git(args: list[str], working_dir: str) -> subprocess.CompletedProcess:
    """Run a git command with standard safety options."""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        timeout=5,
        cwd=working_dir,
    )


def _compute_legacy_project_id(working_dir: str | None = None) -> str:
    """Migration-time-only helper: compute the legacy 12-char hex project_id.

    Reuses the historical git-SHA fallback chain:

    1. Root commit SHA truncated to 12 chars (skip if shallow clone)
    2. HEAD SHA truncated to 12 chars
    3. SHA-256 of absolute path truncated to 12 chars

    NOT cached. NOT consulted by the runtime ``resolve_workspace_uuid``
    precedence chain — this helper is used ONLY by Migration 11 step 0
    to populate ``workspaces.project_id_legacy`` for entries that pre-date
    feature 108. Per design §3.4 / Decision 5, this helper does NOT read
    any env var (test/CI overrides go via ``ENTITY_WORKSPACE_UUID`` →
    ``resolve_workspace_uuid``, not here).

    Parameters
    ----------
    working_dir:
        Project root directory. Defaults to ``os.getcwd()``.

    Returns
    -------
    str
        12-char lowercase hex string (legacy project_id format).

    Raises
    ------
    Never raises — returns path-hash fallback on any failure.

    Side effects
    ------------
    Subprocess calls to git (rev-parse, rev-list). No file or DB writes.

    Idempotency
    -----------
    Pure function modulo git state. Same git state → same return value.
    """
    cwd = working_dir or os.getcwd()

    try:
        # Check for shallow clone
        shallow_result = _run_git(
            ["rev-parse", "--is-shallow-repository"], cwd
        )
        is_shallow = shallow_result.stdout.strip() == "true"

        if not is_shallow:
            # Try root commit
            try:
                result = _run_git(
                    ["rev-list", "--max-parents=0", "HEAD"], cwd
                )
                if result.returncode == 0 and result.stdout.strip():
                    root_sha = result.stdout.strip().splitlines()[0]
                    return root_sha[:12]
            except (subprocess.TimeoutExpired, OSError):
                pass

        # Fallback: HEAD SHA
        try:
            result = _run_git(["rev-parse", "HEAD"], cwd)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()[:12]
        except (subprocess.TimeoutExpired, OSError):
            pass

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Final fallback: path hash
    return hashlib.sha256(os.path.abspath(cwd).encode()).hexdigest()[:12]


def collect_git_info(working_dir: str | None = None) -> GitProjectInfo:
    """Collect git metadata for the projects table.

    Each field fails independently -- partial git info does not block other
    fields. Non-git directories produce ``is_git_repo=False`` with empty
    git fields.
    """
    cwd = working_dir or os.getcwd()
    abs_cwd = os.path.abspath(cwd)

    # Compute legacy 12-char hex project_id (migration-shape; used here to
    # populate GitProjectInfo.project_id for projects-table writes).
    project_id = _compute_legacy_project_id(cwd)

    # Check if git repo and get project root
    is_git_repo = False
    project_root = abs_cwd
    try:
        result = _run_git(["rev-parse", "--show-toplevel"], cwd)
        if result.returncode == 0 and result.stdout.strip():
            is_git_repo = True
            project_root = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Root commit SHA
    root_commit_sha = ""
    if is_git_repo:
        try:
            result = _run_git(
                ["rev-list", "--max-parents=0", "HEAD"], cwd
            )
            if result.returncode == 0 and result.stdout.strip():
                root_commit_sha = result.stdout.strip().splitlines()[0]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Remote URL
    remote_url = ""
    try:
        result = _run_git(["remote", "get-url", "origin"], cwd)
        if result.returncode == 0 and result.stdout.strip():
            remote_url = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Normalize URL and extract parts
    normalized_url = normalize_remote_url(remote_url)
    remote_host = ""
    remote_owner = ""
    remote_repo = ""
    if normalized_url:
        parts = normalized_url.split("/")
        if len(parts) >= 1:
            remote_host = parts[0]
        if len(parts) >= 2:
            remote_owner = parts[1]
        if len(parts) >= 3:
            remote_repo = parts[2]

    # Default branch
    default_branch = ""
    if is_git_repo:
        try:
            result = _run_git(
                ["symbolic-ref", "refs/remotes/origin/HEAD"], cwd
            )
            if result.returncode == 0 and result.stdout.strip():
                # refs/remotes/origin/HEAD -> refs/remotes/origin/main
                ref = result.stdout.strip()
                default_branch = ref.rsplit("/", 1)[-1]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

    # Name: prefer remote_repo, fall back to dir basename
    name = remote_repo if remote_repo else os.path.basename(project_root)

    return GitProjectInfo(
        project_id=project_id,
        root_commit_sha=root_commit_sha,
        name=name,
        remote_url=remote_url,
        normalized_url=normalized_url,
        remote_host=remote_host,
        remote_owner=remote_owner,
        remote_repo=remote_repo,
        default_branch=default_branch,
        project_root=project_root,
        is_git_repo=is_git_repo,
    )
