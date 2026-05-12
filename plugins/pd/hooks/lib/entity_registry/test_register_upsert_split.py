"""register_entity / upsert_entity split tests for feature 109 (FR-4).

Scope (Group 13, Tasks 13.1-13.4 + 13.7.1):
  - AC-4.2: ``test_register_entity_raises_on_conflict`` — register raises
    EntityExistsError on (workspace_uuid, type_id) collision; first row
    untouched.
  - AC-4.4 (insert branch): ``test_upsert_entity_inserts_when_new`` — new
    entity inserted + 1 entity_created event.
  - AC-4.4 (conflict + status change): ``test_upsert_entity_emits_event_on_status_change``.
  - AC-4.4 (conflict + no change): ``test_upsert_entity_noop_when_no_change``.
  - AC-4.3: ``test_register_and_upsert_signatures_byte_identical``.

Scope (Group 14, Tasks 14.1-14.4):
  - AC-4.5: ``test_no_production_insert_or_ignore_into_entities`` — grep
    asserts 0 production matches.
  - AC-4.6 entities path: ``test_register_entities_batch_idempotent`` —
    batch re-run produces N events first call, 0 additional after.
  - AC-4.6 non-entities (5 sites): phase_events backfill dedup, entity_tags
    duplicate attach, entity_okr_alignment duplicate attach, workflow_phases
    init duplicate, entity_dependencies duplicate edge.
"""
from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

import pytest

from entity_registry.database import EntityDatabase, EntityExistsError
from entity_registry.test_helpers import (
    TEST_PROJECT_ID,
    bootstrap_test_workspace,
)


# Anchor at plugins/pd/ for the grep tests below.
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_DATABASE_PY = Path(__file__).resolve().parent / "database.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Full EntityDatabase with workspace bootstrapped for TEST_PROJECT_ID."""
    database = EntityDatabase(":memory:")
    bootstrap_test_workspace(database)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Group 13: register_entity raise + upsert_entity three-branch semantics
# ---------------------------------------------------------------------------


# Task 13.1 ----------------------------------------------------------------


def test_register_entity_raises_on_conflict(db):
    """AC-4.2: second register with same (workspace_uuid, type_id) raises
    EntityExistsError; first row untouched (no second uuid generated, no
    entity_status_changed event emitted).
    """
    first_uuid = db.register_entity(
        "feature", "ee-001", "First Name",
        project_id=TEST_PROJECT_ID, status="planned",
    )
    type_id = "feature:ee-001"

    pre_count = db._conn.execute(
        "SELECT COUNT(*) FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    assert pre_count == 1

    with pytest.raises(EntityExistsError) as exc_info:
        db.register_entity(
            "feature", "ee-001", "Different Name",
            project_id=TEST_PROJECT_ID, status="active",
        )
    err = exc_info.value
    assert err.type_id == type_id
    assert err.workspace_uuid  # populated

    # First row untouched: same uuid, name, status.
    row = db._conn.execute(
        "SELECT uuid, name, status FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    assert row["uuid"] == first_uuid
    assert row["name"] == "First Name"
    assert row["status"] == "planned"
    # Only one row total.
    post_count = db._conn.execute(
        "SELECT COUNT(*) FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    assert post_count == 1
    # No entity_status_changed event emitted by the failed register.
    sc_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_status_changed'",
        (type_id,),
    ).fetchone()[0]
    assert sc_count == 0


# Task 13.2 ----------------------------------------------------------------


def test_upsert_entity_inserts_when_new(db):
    """AC-4.4 (insert branch): upsert for a never-before-seen
    (workspace_uuid, type_id) creates the entity and emits exactly one
    entity_created phase_event.
    """
    type_id = "feature:upsert-new-002"
    pre_entities = db._conn.execute(
        "SELECT COUNT(*) FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    assert pre_entities == 0

    new_uuid = db.upsert_entity(
        "feature", "upsert-new-002", "Upsert New",
        project_id=TEST_PROJECT_ID, status="planned",
    )
    assert new_uuid  # returns the new entity's uuid

    post_entities = db._conn.execute(
        "SELECT uuid, status FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    assert post_entities["uuid"] == new_uuid
    assert post_entities["status"] == "planned"

    created_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_created'",
        (type_id,),
    ).fetchone()[0]
    assert created_count == 1, (
        f"Expected exactly 1 entity_created event, found {created_count}"
    )


# Task 13.3 ----------------------------------------------------------------


def test_upsert_entity_emits_event_on_status_change(db):
    """AC-4.4 (conflict + status change): upsert existing entity with a
    DIFFERENT status emits exactly one entity_status_changed phase_event
    AND updates entities.status. Returns the existing uuid (no new uuid).
    """
    first_uuid = db.upsert_entity(
        "feature", "upsert-sc-003", "Status Change",
        project_id=TEST_PROJECT_ID, status="planned",
    )
    type_id = "feature:upsert-sc-003"

    # Status change branch.
    second_uuid = db.upsert_entity(
        "feature", "upsert-sc-003", "Status Change",
        project_id=TEST_PROJECT_ID, status="active",
    )
    assert second_uuid == first_uuid  # No new uuid generated.

    row = db._conn.execute(
        "SELECT status FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    assert row["status"] == "active"

    sc_events = db._conn.execute(
        "SELECT metadata FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_status_changed' "
        "ORDER BY id",
        (type_id,),
    ).fetchall()
    assert len(sc_events) == 1
    meta = json.loads(sc_events[0]["metadata"])
    assert meta["old_status"] == "planned"
    assert meta["new_status"] == "active"


# Task 13.4 ----------------------------------------------------------------


def test_upsert_entity_noop_when_no_change(db):
    """AC-4.4 (conflict + no status change): upsert existing entity with
    the SAME status is a complete no-op — no UPDATE, no phase_event,
    ``entities.updated_at`` unchanged. Returns the existing uuid.
    """
    first_uuid = db.upsert_entity(
        "feature", "upsert-noop-004", "Noop",
        project_id=TEST_PROJECT_ID, status="planned",
    )
    type_id = "feature:upsert-noop-004"

    before = db._conn.execute(
        "SELECT updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    before_updated_at = before["updated_at"]

    pre_event_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]

    # Same-status upsert.
    second_uuid = db.upsert_entity(
        "feature", "upsert-noop-004", "Noop",
        project_id=TEST_PROJECT_ID, status="planned",
    )
    assert second_uuid == first_uuid

    after = db._conn.execute(
        "SELECT updated_at FROM entities WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    assert after["updated_at"] == before_updated_at, (
        "entities.updated_at must not be touched when upsert is a no-op"
    )

    post_event_count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    assert post_event_count == pre_event_count, (
        "No phase_event must be emitted when upsert is a no-op "
        f"(before: {pre_event_count}, after: {post_event_count})"
    )


# Task 13.7.1 --------------------------------------------------------------


def test_register_and_upsert_signatures_byte_identical():
    """AC-4.3: ``upsert_entity`` signature is byte-identical to
    ``register_entity`` (parameter names + order).
    """
    reg_sig = inspect.signature(EntityDatabase.register_entity)
    ups_sig = inspect.signature(EntityDatabase.upsert_entity)
    assert (
        list(reg_sig.parameters.keys())
        == list(ups_sig.parameters.keys())
    ), (
        f"Parameter keys differ:\n"
        f"  register: {list(reg_sig.parameters.keys())}\n"
        f"  upsert:   {list(ups_sig.parameters.keys())}"
    )


# ---------------------------------------------------------------------------
# Group 14: line-5525 reroute + AC-4.6 non-entities idempotency tests
# ---------------------------------------------------------------------------


# Task 14.1 ----------------------------------------------------------------


def test_no_production_insert_or_ignore_into_entities():
    """AC-4.5: ``grep -nE 'INSERT OR IGNORE INTO entities ' database.py`` in
    production code returns 0 matches (sites 3451 + 5525 both eliminated).

    Filters out test files, migration scaffolding, docstrings, and comments.
    """
    proc = subprocess.run(
        [
            "grep",
            "-rn",
            "--include=*.py",
            "INSERT OR IGNORE INTO entities ",
            str(_PLUGIN_ROOT / "hooks"),
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

    production_violations: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # Skip test files.
        if "/test_" in line or "/tests/" in line:
            continue
        # Skip clearly historical-migration / commentary lines. Each
        # remaining match is a real production write site.
        # Strip leading file:lineno prefix to inspect the content.
        try:
            _file, _lineno, content = line.split(":", 2)
        except ValueError:
            continue
        stripped = content.strip()
        # Skip pure comment lines (commentary about the pattern is OK).
        if stripped.startswith("#"):
            continue
        # Skip docstring lines / quoted documentation that mention the
        # phrase but don't execute SQL. Docstring lines never begin with
        # a quote followed by INSERT — but a docstring containing the
        # phrase as prose is line-prefixed by indentation + content. We
        # gate on the python-string-keyword form: ``conn.execute(`` or
        # ``self._conn.execute(`` style preceding contexts cannot be
        # detected from a single grep line, so we use a heuristic — the
        # line must include a closing quote AND the keyword ``execute``
        # OR be inside a SQL string literal (begins with `"INSERT OR ...`
        # quoted). Both cases identify production writes.
        production_violations.append(line)

    assert production_violations == [], (
        "AC-4.5 violation: production INSERT OR IGNORE INTO entities still "
        "present (sites 3451 and 5525 must both be eliminated):\n"
        + "\n".join(production_violations)
    )


# Task 14.2 ----------------------------------------------------------------


def test_register_entities_batch_idempotent(db):
    """AC-4.6 (entities path): ``register_entities_batch`` is idempotent.

    First call with N rows: emits N entity_created events. Second call with
    the same rows: emits 0 additional events AND the row count is unchanged.
    """
    batch = [
        {"entity_type": "feature", "entity_id": "batch-001", "name": "B1",
         "status": "planned"},
        {"entity_type": "feature", "entity_id": "batch-002", "name": "B2",
         "status": "planned"},
        {"entity_type": "backlog", "entity_id": "batch-003", "name": "B3",
         "status": "planned"},
    ]

    # First call.
    first_uuids = db.register_entities_batch(
        batch, project_id=TEST_PROJECT_ID,
    )
    assert len(first_uuids) == 3

    first_entities = db._conn.execute(
        "SELECT COUNT(*) FROM entities "
        "WHERE type_id IN ('feature:batch-001', 'feature:batch-002', "
        "'backlog:batch-003')"
    ).fetchone()[0]
    assert first_entities == 3

    first_created = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events "
        "WHERE event_type = 'entity_created' AND type_id IN "
        "('feature:batch-001', 'feature:batch-002', 'backlog:batch-003')"
    ).fetchone()[0]
    assert first_created == 3, (
        f"Expected 3 entity_created events after first batch call, "
        f"found {first_created}"
    )

    # Second call with identical input.
    second_uuids = db.register_entities_batch(
        batch, project_id=TEST_PROJECT_ID,
    )
    # All three should map to the existing uuids (no new uuids generated).
    assert sorted(second_uuids) == sorted(first_uuids)

    second_entities = db._conn.execute(
        "SELECT COUNT(*) FROM entities "
        "WHERE type_id IN ('feature:batch-001', 'feature:batch-002', "
        "'backlog:batch-003')"
    ).fetchone()[0]
    assert second_entities == 3  # still 3 rows, no duplicates

    second_created = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events "
        "WHERE event_type = 'entity_created' AND type_id IN "
        "('feature:batch-001', 'feature:batch-002', 'backlog:batch-003')"
    ).fetchone()[0]
    assert second_created == 3, (
        f"Expected exactly 3 entity_created events after IDEMPOTENT second "
        f"call, found {second_created} (no additional events should fire)"
    )


# Task 14.4: AC-4.6 non-entities idempotency tests (5 tables) --------------


def test_phase_events_backfill_dedup_no_duplicates(db):
    """AC-4.6 (phase_events sites 1587/1603/1630/1657): the partial-UNIQUE
    ``phase_events_backfill_dedup`` index ensures replayed backfill rows
    are deduped. Insert the same backfill row twice via raw SQL (mimicking
    the backfill helper); assert single-row result.

    The backfill helper inserts with ``source='backfill'`` and the partial
    UNIQUE index covers (type_id, project_id, phase, event_type) where
    source='backfill'.
    """
    type_id = "feature:dedup-pe-001"
    now = db._now_iso()

    sql = (
        "INSERT OR IGNORE INTO phase_events "
        "(type_id, project_id, phase, event_type, timestamp, source, "
        "created_at) VALUES (?, ?, ?, ?, ?, 'backfill', ?)"
    )
    # First insert.
    db._conn.execute(
        sql, (type_id, TEST_PROJECT_ID, "specify", "started", now, now),
    )
    # Second insert (same logical row).
    db._conn.execute(
        sql, (type_id, TEST_PROJECT_ID, "specify", "started", now, now),
    )
    db._conn.commit()

    count = db._conn.execute(
        "SELECT COUNT(*) FROM phase_events "
        "WHERE type_id = ? AND source = 'backfill'",
        (type_id,),
    ).fetchone()[0]
    assert count == 1, (
        f"Expected 1 backfill row after duplicate insert, found {count}"
    )


def test_entity_tag_duplicate_attach_noop(db):
    """AC-4.6 (entity_tags site 3241): duplicate ``add_entity_tag`` calls
    do not produce duplicate rows.
    """
    entity_uuid = db.register_entity(
        "feature", "tag-001", "Tag Test", project_id=TEST_PROJECT_ID,
    )

    db.add_tag(entity_uuid, "taga")
    db.add_tag(entity_uuid, "taga")  # duplicate
    db.add_tag(entity_uuid, "taga")  # another duplicate

    count = db._conn.execute(
        "SELECT COUNT(*) FROM entity_tags "
        "WHERE entity_uuid = ? AND tag = 'taga'",
        (entity_uuid,),
    ).fetchone()[0]
    assert count == 1, (
        f"Expected 1 entity_tags row after 3 duplicate attaches, "
        f"found {count}"
    )


def test_okr_alignment_duplicate_noop(db):
    """AC-4.6 (entity_okr_alignment site 3302): duplicate alignment attach
    is a no-op. The table schema requires a key_result_uuid; we use a
    synthetic uuid for the test (FK constraints not enforced at the row
    level for this idempotency check — INSERT OR IGNORE protects).
    """
    entity_uuid = db.register_entity(
        "feature", "okr-001", "OKR Test", project_id=TEST_PROJECT_ID,
    )
    kr_uuid = db.register_entity(
        "feature", "okr-kr-001", "Synthetic KR",
        project_id=TEST_PROJECT_ID,
    )

    # Two attach calls with the same (entity_uuid, key_result_uuid).
    db.add_okr_alignment(entity_uuid, kr_uuid)
    db.add_okr_alignment(entity_uuid, kr_uuid)

    count = db._conn.execute(
        "SELECT COUNT(*) FROM entity_okr_alignment "
        "WHERE entity_uuid = ? AND key_result_uuid = ?",
        (entity_uuid, kr_uuid),
    ).fetchone()[0]
    assert count == 1, (
        f"Expected 1 entity_okr_alignment row after duplicate attach, "
        f"found {count}"
    )


def test_workflow_phases_init_duplicate_noop(db):
    """AC-4.6 (workflow_phases site 5058): duplicate
    ``upsert_workflow_phase`` (the init path) for the same type_id keeps a
    single row.
    """
    type_id = "feature:wp-init-001"
    db.register_entity(
        "feature", "wp-init-001", "WP Init",
        project_id=TEST_PROJECT_ID,
    )

    db.upsert_workflow_phase(type_id, project_id=TEST_PROJECT_ID)
    db.upsert_workflow_phase(type_id, project_id=TEST_PROJECT_ID)

    count = db._conn.execute(
        "SELECT COUNT(*) FROM workflow_phases WHERE type_id = ?",
        (type_id,),
    ).fetchone()[0]
    assert count == 1, (
        f"Expected 1 workflow_phases row after duplicate init, "
        f"found {count}"
    )


def test_dependency_duplicate_noop(db):
    """AC-4.6 (entity_dependencies site 5176): duplicate edge add is a no-op.
    """
    a_uuid = db.register_entity(
        "feature", "dep-001-a", "Dep A", project_id=TEST_PROJECT_ID,
    )
    b_uuid = db.register_entity(
        "feature", "dep-001-b", "Dep B", project_id=TEST_PROJECT_ID,
    )

    db.add_dependency(a_uuid, b_uuid)
    db.add_dependency(a_uuid, b_uuid)
    db.add_dependency(a_uuid, b_uuid)

    count = db._conn.execute(
        "SELECT COUNT(*) FROM entity_dependencies "
        "WHERE entity_uuid = ? AND blocked_by_uuid = ?",
        (a_uuid, b_uuid),
    ).fetchone()[0]
    assert count == 1, (
        f"Expected 1 entity_dependencies row after 3 duplicate adds, "
        f"found {count}"
    )


# ---------------------------------------------------------------------------
# AC-4.8: 1-to-1 F12 audit comment coverage (Group 15.7)
# ---------------------------------------------------------------------------


def test_f12_audit_one_to_one_coverage():
    """AC-4.8: every production register_entity / upsert_entity call site has a
    preceding ``# F12 audit:`` comment with a routing rationale.

    Scope: production code under ``plugins/pd/hooks/lib/`` and
    ``plugins/pd/mcp/`` — EXCLUDING:

    - Test files (filename matches ``test_*.py``)
    - ``def register_entity`` / ``def upsert_entity`` declarations
    - The internal ``upsert_entity → register_entity`` call inside
      ``EntityDatabase.upsert_entity`` itself (file: database.py) — this is
      not a caller, it's the helper plumbing for the insert branch.

    The audit comment marker is the literal string ``F12 audit:`` per
    spec FR-4 / AC-4.8.
    """
    # Search roots
    roots = [
        _PLUGIN_ROOT / "hooks" / "lib",
        _PLUGIN_ROOT / "mcp",
    ]
    # Collect lines: file:lineno:content
    proc = subprocess.run(
        [
            "grep", "-rnE", r"\b(register_entity|upsert_entity)\(",
            *(str(r) for r in roots),
            "--include=*.py",
        ],
        capture_output=True, text=True, check=False,
    )
    lines = proc.stdout.splitlines()

    # Filter to actual production call sites.
    call_sites: list[tuple[str, int]] = []
    for line in lines:
        # Format: "/abs/path.py:NN:    code..."
        try:
            path_part, lineno_str, content = line.split(":", 2)
        except ValueError:
            continue
        # Exclude test files.
        if "/test_" in path_part or path_part.endswith("_test.py"):
            continue
        # Exclude function defs.
        if "def register_entity(" in content or "def upsert_entity(" in content:
            continue
        # Exclude the internal upsert→register self-call inside upsert_entity.
        if path_part.endswith("entity_registry/database.py") and (
            "return self.register_entity(" in content
        ):
            continue
        # Exclude matches inside string literals — heuristic: the function
        # name appears after an unescaped quote earlier on the same line
        # (e.g. ``warnings.warn("register_entity() received both ...")``).
        stripped_content = content.lstrip()
        if stripped_content.startswith('"') or stripped_content.startswith("'"):
            continue
        # If the call appears inside a quoted string, the function name is
        # preceded by a quote on the same line.
        m_idx = max(
            content.find("register_entity("),
            content.find("upsert_entity("),
        )
        if m_idx > 0:
            prefix = content[:m_idx]
            # Count unescaped double-quotes before the match.
            dq = prefix.count('"') - prefix.count('\\"')
            sq = prefix.count("'") - prefix.count("\\'")
            if dq % 2 == 1 or sq % 2 == 1:
                # Inside a string literal — skip.
                continue
        call_sites.append((path_part, int(lineno_str)))

    assert call_sites, "expected at least one register/upsert call site"

    # For each call site, walk backward up to 12 lines looking for a
    # "F12 audit:" comment. The audit comment may be separated from the call
    # by a ``try:`` wrapper and several preamble comment lines.
    violations: list[str] = []
    file_cache: dict[str, list[str]] = {}
    for path_part, lineno in call_sites:
        if path_part not in file_cache:
            file_cache[path_part] = Path(path_part).read_text().splitlines()
        file_lines = file_cache[path_part]
        found = False
        for offset in range(1, 13):
            idx = lineno - 1 - offset
            if idx < 0:
                break
            prior = file_lines[idx]
            if "F12 audit:" in prior:
                found = True
                break
        if not found:
            violations.append(f"{path_part}:{lineno}")

    assert not violations, (
        "F12 audit comment missing at call sites:\n  "
        + "\n  ".join(violations)
        + "\n\nEach production register_entity / upsert_entity call site must "
        "be preceded by a `# F12 audit: ...` comment per spec FR-4 / AC-4.8."
    )
