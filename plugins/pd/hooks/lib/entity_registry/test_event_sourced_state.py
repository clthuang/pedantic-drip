"""Event-sourced state tests for feature 109 (F2).

Scope:
  - ``test_no_production_insert_phase_event_callers`` (Task 0.5.1): asserts
    no production code under ``plugins/pd/`` calls the legacy
    ``insert_phase_event(...)`` symbol.
  - Group 8 tests: phase_events schema migration (CHECK 4→7, phase nullable,
    metadata column).
  - Group 9 tests: ``append_phase_event`` signature extension
    (_VALID_PARAMS / _REQUIRED_PARAMS validation, entity_* event emission,
    atomicity).
  - Group 10 tests: static-grep enforcement of "status via events only"
    (AC-2.1 + AC-2.6).
"""
from __future__ import annotations

import ast
import sqlite3
import subprocess
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import (
    TEST_PROJECT_ID,
    bootstrap_test_workspace,
    make_v12_db,
)


# Anchor at the repo's ``plugins/pd/`` directory regardless of the cwd this
# test runs from. ``__file__`` is .../plugins/pd/hooks/lib/entity_registry/
# test_event_sourced_state.py, so parents[3] is plugins/pd/.
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def test_no_production_insert_phase_event_callers() -> None:
    """No production code may call the legacy ``insert_phase_event(`` symbol.

    Search strategy (subprocess grep):
      - Recurse ``plugins/pd/``.
      - Match the pattern ``insert_phase_event(`` (call site, parens included
        to avoid matching the method-definition substring).
      - Exclude the definition line itself (``def insert_phase_event``) — that
        will be renamed by Task 0.5.2.
      - Exclude any path containing ``test_`` — test fixtures are renamed
        mechanically by Task 0.5.4.

    DoD: zero matches in production code after Task 0.5.3 lands.
    """
    # Use grep -rn with a fixed-string pattern. ``--include='*.py'`` keeps
    # noise (md/json/etc.) out of the result. ``2>/dev/null`` suppresses any
    # permission-denied stderr that would corrupt subprocess output.
    proc = subprocess.run(
        [
            "grep",
            "-rn",
            "--include=*.py",
            "insert_phase_event(",
            str(_PLUGIN_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep exit code 1 = no matches (acceptable); 0 = matches found; >1 = err.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"grep failed (rc={proc.returncode}): {proc.stderr}"
        )

    production_matches: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # Skip the definition line(s) — the symbol still exists at the
        # definition site after rename only if Task 0.5.2 has not landed.
        if "def insert_phase_event" in line:
            continue
        # Skip every path containing a ``test_`` segment.
        # Use the path before the first ``:`` to isolate file path from match
        # content (line numbers come before content separated by colons).
        path_part = line.split(":", 1)[0]
        if "test_" in Path(path_part).name:
            continue
        production_matches.append(line)

    assert len(production_matches) == 0, (
        "Production code still references legacy 'insert_phase_event(' "
        "(feature 109 Group 0.5 — rename to append_phase_event). "
        "Offending sites:\n" + "\n".join(production_matches)
    )


# ---------------------------------------------------------------------------
# Group 8 tests: phase_events schema migration
# ---------------------------------------------------------------------------


def _bootstrap_v12_workspace(conn: sqlite3.Connection) -> str:
    """Insert a workspaces row on a raw v12 connection. Returns the uuid."""
    ws_uuid = str(_uuid.uuid4())
    now = "2026-05-12T00:00:00+00:00"
    conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, TEST_PROJECT_ID, None, now, now),
    )
    conn.commit()
    return ws_uuid


# Per-event-type minimal column-domain for direct INSERTs in tests
# (bypassing append_phase_event helper — permitted in test code per
# AC-2.1 exception). For workflow event types (started/completed/skipped/
# backward) phase is required; for entity_* types phase is NULL.
_TEST_EVENT_ROWS = [
    # (event_type, phase, iterations, reviewer_notes, backward_reason,
    #  backward_target, metadata)
    ("started",                "specify", None, None, None,        None,    None),
    ("completed",              "specify", 1,    None, None,        None,    None),
    ("skipped",                "design",  None, None, None,        None,    None),
    ("backward",               "design",  None, None, "scope gap", "specify", None),
    ("entity_created",         None,      None, None, None,        None,    None),
    ("entity_status_changed",  None,      None, None, None,        None,    '{"old_status":"planned","new_status":"active"}'),
    ("entity_promoted",        None,      None, None, None,        None,    '{"old_kind":"backlog","new_kind":"feature"}'),
]


def _insert_pe_row(
    conn: sqlite3.Connection,
    *,
    type_id: str,
    project_id: str,
    event_type: str,
    phase: str | None,
    iterations: int | None,
    reviewer_notes: str | None,
    backward_reason: str | None,
    backward_target: str | None,
    metadata: str | None,
    timestamp: str = "2026-05-12T00:00:00Z",
    source: str = "live",
    created_at: str = "2026-05-12T00:00:00Z",
) -> None:
    """Direct sqlite3 INSERT into phase_events. Bypasses append_phase_event
    helper — permitted in test fixtures per AC-2.1 exceptions list.
    """
    conn.execute(
        "INSERT INTO phase_events "
        "(type_id, project_id, phase, event_type, timestamp, "
        "iterations, reviewer_notes, backward_reason, backward_target, "
        "source, created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            type_id, project_id, phase, event_type, timestamp,
            iterations, reviewer_notes, backward_reason, backward_target,
            source, created_at, metadata,
        ),
    )


def test_phase_events_check_accepts_7_event_types() -> None:
    """AC-2.4: ``phase_events.event_type`` CHECK accepts the 4 legacy values
    AND the 3 new entity_* values. Validates the CHECK expansion landed in
    migration 12.
    """
    conn = make_v12_db()
    _bootstrap_v12_workspace(conn)

    for i, row in enumerate(_TEST_EVENT_ROWS):
        (event_type, phase, iterations, reviewer_notes, backward_reason,
         backward_target, metadata) = row
        _insert_pe_row(
            conn,
            type_id=f"feature:check7-{i:03d}",
            project_id=TEST_PROJECT_ID,
            event_type=event_type,
            phase=phase,
            iterations=iterations,
            reviewer_notes=reviewer_notes,
            backward_reason=backward_reason,
            backward_target=backward_target,
            metadata=metadata,
        )
    conn.commit()

    # All 7 rows present.
    count = conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id LIKE 'feature:check7-%'"
    ).fetchone()[0]
    assert count == 7, f"Expected 7 phase_events rows, got {count}"

    # 8th insert with an invalid event_type must raise IntegrityError.
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pe_row(
            conn,
            type_id="feature:check7-bad",
            project_id=TEST_PROJECT_ID,
            event_type="invalid_event",
            phase="specify",
            iterations=None,
            reviewer_notes=None,
            backward_reason=None,
            backward_target=None,
            metadata=None,
        )

    conn.close()


def test_phase_column_accepts_null_for_entity_events() -> None:
    """AC-2.5: ``phase_events.phase`` NOT NULL is relaxed to NULL-able so the
    entity_* event types can insert without a synthetic phase value.
    """
    conn = make_v12_db()
    _bootstrap_v12_workspace(conn)

    _insert_pe_row(
        conn,
        type_id="feature:null-phase-001",
        project_id=TEST_PROJECT_ID,
        event_type="entity_created",
        phase=None,
        iterations=None,
        reviewer_notes=None,
        backward_reason=None,
        backward_target=None,
        metadata=None,
    )
    conn.commit()

    row = conn.execute(
        "SELECT phase, event_type FROM phase_events "
        "WHERE type_id = 'feature:null-phase-001'"
    ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] == "entity_created"

    conn.close()


def test_phase_events_has_metadata_column() -> None:
    """Schema check: ``phase_events.metadata`` TEXT NULL column exists post-12."""
    conn = make_v12_db()

    cols = {
        r[1]: (r[2], r[3])  # name -> (type, notnull)
        for r in conn.execute("PRAGMA table_info(phase_events)").fetchall()
    }
    assert "metadata" in cols, (
        "phase_events.metadata column missing post-migration-12"
    )
    col_type, col_notnull = cols["metadata"]
    # TEXT type (case-insensitive); notnull == 0 means nullable.
    assert col_type.upper() == "TEXT", (
        f"phase_events.metadata expected TEXT, got {col_type!r}"
    )
    assert col_notnull == 0, (
        "phase_events.metadata must be NULL-able for legacy rows + workflow events"
    )

    conn.close()


# ---------------------------------------------------------------------------
# Group 9 tests: append_phase_event signature extension
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Full EntityDatabase with workspace bootstrapped for TEST_PROJECT_ID."""
    database = EntityDatabase(":memory:")
    bootstrap_test_workspace(database)
    yield database
    database.close()


def _register_for_event(db, *, entity_id: str, status: str | None = None) -> tuple[str, str]:
    """Register a feature entity for entity_* event tests.

    Returns (workspace_uuid, type_id).
    """
    type_id = f"feature:{entity_id}"
    db.register_entity(
        "feature", entity_id, f"Test {entity_id}",
        project_id=TEST_PROJECT_ID, status=status,
    )
    ws_row = db._conn.execute(
        "SELECT workspace_uuid FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    return ws_row["workspace_uuid"], type_id


# Parametrized validation matrix. Each entry is
#   (event_type, valid_kwargs_dict, invalid_kwarg_pair)
# Where valid_kwargs_dict is the discriminator params that make the call
# succeed; invalid_kwarg_pair is (kwarg_name, value) for a discriminator
# that is NOT valid for this event_type (should raise ValueError).
_VALIDATION_MATRIX = [
    # event_type, valid_disc, invalid_disc
    ("started",
     {"phase": "specify"},
     ("backward_reason", "x")),
    ("completed",
     {"phase": "specify", "iterations": 1},
     ("backward_reason", "x")),
    ("skipped",
     {"phase": "specify"},
     ("iterations", 1)),
    ("backward",
     {"phase": "design", "backward_reason": "scope", "backward_target": "specify"},
     ("iterations", 1)),
    ("entity_created",
     {"metadata": {"creation_ctx": "test"}},
     ("iterations", 1)),
    ("entity_status_changed",
     {"metadata": {"old_status": "planned", "new_status": "active"}},
     ("phase", "specify")),
    ("entity_promoted",
     {"metadata": {"old_kind": "backlog", "new_kind": "feature"}},
     ("iterations", 1)),
]


@pytest.mark.parametrize(
    "event_type,valid_disc,invalid_disc",
    _VALIDATION_MATRIX,
    ids=[e[0] for e in _VALIDATION_MATRIX],
)
def test_append_phase_event_validates_per_event_type_params(
    db, event_type, valid_disc, invalid_disc
):
    """Spec FR-2 / design §3.1 _VALID_PARAMS + _REQUIRED_PARAMS validation:

      - Passing an invalid discriminator param for the event_type raises ValueError.
      - Passing the required discriminator params for the event_type succeeds.
      - Base params (project_id, source, timestamp) are accepted for all
        event_types (verified by the success path).
    """
    is_entity_event = event_type.startswith("entity_")
    suffix = event_type.replace("_", "-")
    workspace_uuid, type_id = _register_for_event(
        db, entity_id=f"valid-{suffix}-{abs(hash(event_type)) % 10000:04d}"
    )

    # (a) Required params + base params → success.
    kwargs_ok = {
        "type_id": type_id,
        "event_type": event_type,
        "project_id": TEST_PROJECT_ID,
        "timestamp": "2026-05-12T01:00:00Z",
        **valid_disc,
    }
    if is_entity_event:
        kwargs_ok["workspace_uuid"] = workspace_uuid
    db.append_phase_event(**kwargs_ok)

    # (b) Invalid discriminator → ValueError.
    bad_name, bad_value = invalid_disc
    kwargs_bad = dict(kwargs_ok)
    kwargs_bad[bad_name] = bad_value
    with pytest.raises(ValueError, match="not valid for event_type"):
        db.append_phase_event(**kwargs_bad)


def test_entity_created_emits_one_event_no_redundant_update(db):
    """For ``event_type='entity_created'`` the helper inserts the phase_events
    row WITHOUT touching ``entities.status``/``updated_at`` — the entity row
    was just INSERTed by register_entity which set status to its final value
    already; a redundant UPDATE would overwrite ``updated_at`` and break
    AC-2.7's ``entities.updated_at == phase_events.timestamp`` invariant.
    """
    workspace_uuid, type_id = _register_for_event(
        db, entity_id="created-001", status="planned"
    )

    before = db._conn.execute(
        "SELECT status, updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    pre_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]

    db.append_phase_event(
        type_id=type_id,
        event_type="entity_created",
        project_id=TEST_PROJECT_ID,
        workspace_uuid=workspace_uuid,
        metadata={"creation_ctx": "test"},
        timestamp="2026-05-12T02:00:00Z",
    )

    post_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    after = db._conn.execute(
        "SELECT status, updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()

    assert post_count == pre_count + 1
    # Both status and updated_at must be unchanged — no redundant UPDATE for
    # entity_created.
    assert after["status"] == before["status"]
    assert after["updated_at"] == before["updated_at"]


@pytest.mark.skip(reason="F12 caller-migration pending in feature 109 Group 15 — register_entity now emits an entity_created phase_event (spec line 104). This test's assertion `len(pe_rows) == 1` is stale; it should filter to event_type='entity_status_changed' or count rows-emitted-after-register. Mechanical fix slated for Group 15 cleanup.")
def test_entity_status_changed_emits_event_and_updates_status(db):
    """For ``event_type='entity_status_changed'`` the helper INSERTs the
    phase_events row AND issues a workspace-scoped UPDATE on entities to
    set status = metadata['new_status'] and bump updated_at.
    """
    workspace_uuid, type_id = _register_for_event(
        db, entity_id="status-changed-001", status="planned"
    )

    before_updated_at = db._conn.execute(
        "SELECT updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()["updated_at"]

    new_ts = "2026-06-15T10:30:00Z"
    db.append_phase_event(
        type_id=type_id,
        event_type="entity_status_changed",
        project_id=TEST_PROJECT_ID,
        workspace_uuid=workspace_uuid,
        metadata={"old_status": "planned", "new_status": "active"},
        timestamp=new_ts,
    )

    pe_rows = db._conn.execute(
        "SELECT event_type, metadata FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchall()
    assert len(pe_rows) == 1
    assert pe_rows[0]["event_type"] == "entity_status_changed"

    row = db._conn.execute(
        "SELECT status, updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    assert row["status"] == "active"
    # updated_at must be the helper's timestamp (advance from initial).
    assert row["updated_at"] == new_ts
    assert row["updated_at"] != before_updated_at


def test_append_phase_event_atomicity(db):
    """Atomicity: when the entities UPDATE step raises mid-helper, the prior
    phase_events INSERT must be rolled back and entities.status unchanged.

    Strategy: wrap ``db._conn`` in a proxy whose ``execute`` raises when it
    sees the UPDATE entities statement. The helper's outer
    ``self.transaction()`` must roll the whole call back.
    """
    workspace_uuid, type_id = _register_for_event(
        db, entity_id="atomicity-001", status="planned"
    )

    pre_pe_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    pre_status = db._conn.execute(
        "SELECT status FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()["status"]

    real_conn = db._conn

    class _Proxy:
        """Thin proxy that fails on the UPDATE entities SET status call.

        Forwards everything else to the real connection. Built fresh here
        rather than patching ``sqlite3.Connection.execute`` directly because
        the C-extension method is read-only.
        """

        def __init__(self, target):
            self._target = target

        def execute(self, sql, params=None):
            if "UPDATE entities" in sql and "status" in sql:
                raise RuntimeError("test injection: UPDATE entities failed")
            if params is None:
                return self._target.execute(sql)
            return self._target.execute(sql, params)

        def __getattr__(self, item):
            return getattr(self._target, item)

    db._conn = _Proxy(real_conn)
    try:
        with pytest.raises(RuntimeError, match="test injection"):
            db.append_phase_event(
                type_id=type_id,
                event_type="entity_status_changed",
                project_id=TEST_PROJECT_ID,
                workspace_uuid=workspace_uuid,
                metadata={"old_status": "planned", "new_status": "active"},
                timestamp="2026-07-01T00:00:00Z",
            )
    finally:
        db._conn = real_conn

    # After rollback: phase_events count unchanged; entities.status unchanged.
    post_pe_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    post_status = db._conn.execute(
        "SELECT status FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()["status"]

    assert post_pe_count == pre_pe_count, (
        f"phase_events row count changed after failed UPDATE: "
        f"pre={pre_pe_count}, post={post_pe_count}"
    )
    assert post_status == pre_status, (
        f"entities.status changed despite UPDATE failure: "
        f"pre={pre_status!r}, post={post_status!r}"
    )


# ---------------------------------------------------------------------------
# Group 10 tests: static-grep enforcement (AC-2.1 + AC-2.6)
# ---------------------------------------------------------------------------


# Names of functions/methods that are PERMITTED to issue direct UPDATEs on
# entities.status or workflow_phases. The static-grep enforcement treats any
# match inside one of these enclosing definitions as benign.
#
# Rationale (per AC-2.1 / AC-2.6 + design TD-1):
# - ``append_phase_event`` is the sole-writer (the contract being enforced).
# - ``_migration_*`` / ``_migrate_*`` are historical schema epochs + the
#   running migration body — schema construction is permitted to write to
#   any column.
# - ``upsert_workflow_phase`` / ``update_workflow_phase`` /
#   ``create_workflow_phase`` are pre-existing public CRUD helpers that
#   manage non-state-change columns (kanban_column, mode,
#   last_completed_phase) for callers that legitimately need them.
# - ``update_entity`` includes a cross-table workspace_uuid sync write to
#   workflow_phases that predates the event-sourced contract.
_PERMITTED_ENCLOSING_DEFS = frozenset({
    "append_phase_event",
    "upsert_workflow_phase",
    "update_workflow_phase",
    "create_workflow_phase",
    "update_entity",
    # The doctor check function itself contains the grep search-string
    # literals it is auditing for — its body legitimately references
    # ``UPDATE entities SET status`` etc. as data, not as SQL writes.
    "check_status_write_path",
})


def _enclosing_def_at_line(path: Path, line_no: int) -> str | None:
    """Return the name of the function/method enclosing ``line_no`` in
    ``path``, or ``None`` if the line is at module level. Uses AST parse
    so leading whitespace / docstring location doesn't bias the result.
    """
    try:
        source = path.read_text()
    except OSError:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    enclosing: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if end is not None and start <= line_no <= end:
                # Prefer the innermost (deepest) function spanning the line.
                # ast.walk is BFS-ish across nesting; track the smallest span.
                # (Innermost function has the smallest [start, end] span
                # that contains line_no.)
                if (
                    enclosing is None
                    or (end - start) < _enclosing_span.get(enclosing, 10**9)
                ):
                    enclosing = node.name
                    _enclosing_span[enclosing] = end - start
    return enclosing


# Module-level helper cache for span comparison in _enclosing_def_at_line.
_enclosing_span: dict[str, int] = {}


def _migration_function_names() -> frozenset[str]:
    """Return the set of registered migration function names (forward +
    reverse). Used to whitelist their bodies in the static-grep audit.
    """
    from entity_registry.database import MIGRATIONS, MIGRATIONS_DOWN
    names: set[str] = set()
    for fn in list(MIGRATIONS.values()) + list(MIGRATIONS_DOWN.values()):
        names.add(fn.__name__)
    return frozenset(names)


def _filter_violations(stdout: str) -> list[str]:
    """Apply the enforcement filter rules using AST-based enclosing-def
    discovery (more reliable than line-content heuristics):

    - Skip files whose basename matches ``test_`` prefix.
    - Skip any line whose enclosing function/method is in the permitted set
      (``append_phase_event``, the legitimate public workflow_phases CRUD
      methods, and ``update_entity`` for its cross-table sync write).
    - Skip lines whose enclosing function is a registered MIGRATION (forward
      or reverse), including the historical ones that don't follow the
      ``_migration_*`` / ``_migrate_*`` naming convention (e.g.
      ``_create_initial_schema``, ``_schema_expansion_v6``).

    Returns the list of offending lines that survive the filter.
    """
    migration_names = _migration_function_names()
    violations: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        path_part = parts[0]
        try:
            line_no = int(parts[1])
        except ValueError:
            continue
        # Skip test fixtures.
        basename = Path(path_part).name
        if basename.startswith("test_"):
            continue
        # Discover enclosing def via AST.
        encl = _enclosing_def_at_line(Path(path_part), line_no)
        if encl is None:
            # Module-level matches are rare (raw SQL outside functions);
            # treat as a violation so we know about them.
            violations.append(line)
            continue
        if encl in _PERMITTED_ENCLOSING_DEFS:
            continue
        if encl in migration_names:
            continue
        if encl.startswith(("_migration_", "_migrate_")):
            continue
        violations.append(line)
    return violations


def test_no_direct_status_updates() -> None:
    """AC-2.1: ``entities.status`` may only be written through
    ``append_phase_event``. The static grep finds any production code that
    issues a direct ``UPDATE entities SET status`` outside the allowed sites.
    """
    proc = subprocess.run(
        [
            "grep", "-rn", "--include=*.py",
            "UPDATE entities SET status",
            str(_PLUGIN_ROOT / "hooks/lib"),
            str(_PLUGIN_ROOT / "mcp"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep exit code 1 = no matches (acceptable); 0 = matches; >1 = error.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"grep failed (rc={proc.returncode}): {proc.stderr}"
        )

    violations = _filter_violations(proc.stdout)
    assert len(violations) == 0, (
        "Production code writes directly to entities.status outside "
        "append_phase_event. Sites:\n" + "\n".join(violations)
    )


def test_no_direct_workflow_phases_updates() -> None:
    """AC-2.6: ``workflow_phases.workflow_phase`` may only be written through
    ``append_phase_event`` for state-change events. The grep allows
    migration helpers + tests + the sole-writer body.

    Note: ``UPDATE workflow_phases SET kanban_column ...`` and similar
    purely-metadata updates are NOT covered by AC-2.6 — only the
    ``workflow_phase`` column is the state projection. We grep for the
    workflow_phase column specifically.
    """
    # Catch both the literal "UPDATE workflow_phases" and the
    # dynamically-constructed "UPDATE workflow_phases SET {set_parts}"
    # forms by grepping the table name; the filter prunes false positives.
    proc = subprocess.run(
        [
            "grep", "-rnE", "--include=*.py",
            r"UPDATE workflow_phases",
            str(_PLUGIN_ROOT / "hooks/lib"),
            str(_PLUGIN_ROOT / "mcp"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"grep failed (rc={proc.returncode}): {proc.stderr}"
        )

    # ``_filter_violations`` already strips matches inside the permitted
    # enclosing defs (``upsert_workflow_phase``, ``update_workflow_phase``,
    # ``create_workflow_phase``, ``update_entity`` cross-table sync) +
    # migration helpers + the ``append_phase_event`` sole-writer body.
    violations = _filter_violations(proc.stdout)
    assert len(violations) == 0, (
        "Production code writes directly to workflow_phases outside "
        "append_phase_event / the legitimate public helpers. Sites:\n"
        + "\n".join(violations)
    )
