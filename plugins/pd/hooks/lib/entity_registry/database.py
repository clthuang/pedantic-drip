"""SQLite database layer for the entity registry system."""
# Audit 062: 20 _commit() call sites found, 3 wrapped in transaction()
# Wrapped: register_entity (2 writes), update_entity (3 writes),
#          upsert_workflow_phase (2 writes)
# Already atomic: delete_entity (BEGIN IMMEDIATE), register_entities_batch (BEGIN IMMEDIATE)
# Single-statement (skip): add_tag, remove_tag, add_okr_alignment,
#   remove_okr_alignment, set_parent, insert_workflow_phase,
#   update_workflow_phase, delete_workflow_phase, set_metadata,
#   add_dependency, remove_dependency
# Infrastructure (skip): _migrate (2 sites)
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid as uuid_mod
import warnings
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone

_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)

# Tag format: lowercase letters, digits, hyphens. 1-50 chars. No leading/trailing hyphens.
_TAG_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$')


# ---------------------------------------------------------------------------
# Feature 109 (polymorphic taxonomy): F11 mapping helpers.
# ---------------------------------------------------------------------------
# Migration 12 backfilled the legacy ``entity_type`` column into the new
# (``type``, ``kind``, ``lifecycle_class``) triple per spec FR-1. After Group 7
# drops the legacy column, production paths still accept ``entity_type`` as a
# kwarg/parameter name (public API stability — see TD-8 / AC-1.4) but the
# stored column is ``kind``. This mapping is the single source of truth for
# deriving (type, lifecycle_class) from a legacy entity_type value at INSERT
# time and for reconstructing the legacy ``entity_type`` field in result dicts
# from the ``kind`` column.
#
# Note: ``entity_type`` and ``kind`` values are byte-identical for the 5
# production kinds (feature/backlog/brainstorm/project/workspace) — see spec
# FR-1 backfill table. The mapping below therefore uses kind as the key.
_KIND_TO_TYPE_LIFECYCLE: dict[str, tuple[str, str]] = {
    "feature":    ("work",       "feature_flow"),
    "backlog":    ("work",       "work_flow"),
    "brainstorm": ("brainstorm", "brainstorm_flow"),
    "project":    ("container",  "container_flow"),
    "workspace":  ("workspace",  "none"),
    # 5D kinds (zero production rows per spec §1, retained in
    # VALID_ENTITY_TYPES for test fixture / forward-compat with feature
    # 111 issue_spawn). All map to type='work' which the composite CHECK
    # constraint permits.
    "initiative": ("work",       "work_flow"),
    "objective":  ("work",       "work_flow"),
    "key_result": ("work",       "work_flow"),
    # Feature 111 FR-BL.3 / FR-MR.5: task remapped from 'work_flow' to
    # 'task_flow' so _CLOSES_TERMINAL can derive the closes= terminal
    # without colliding with backlog (which keeps 'work_flow' → 'dropped').
    "task":       ("work",       "task_flow"),
    # Feature 111 FR-9.2: new 'bug' kind for spontaneous mid-flight issue
    # capture (issue_spawn MCP). Status-only model — see FR-BL.
    "bug":        ("work",       "bug_flow"),
}


# Feature 111 FR-10.3 step 3 / IF-7: closure terminal-state derivation by
# lifecycle_class. Single source of truth for complete_phase(closes=). Keys
# absent from this dict raise InvalidCloseTargetError when passed via closes=.
# Future relation kinds extend this dict without touching dispatch logic.
_CLOSES_TERMINAL: dict[str, str] = {
    "bug_flow":  "closed",   # bug terminal via closes= (resolved/wont_fix via update_entity)
    "task_flow": "closed",   # task terminal (only terminal in task machine)
    "work_flow": "dropped",  # backlog terminal — "subsumed by feature"
    # feature_flow → NOT in dict → raise InvalidCloseTargetError (TD-1)
    # brainstorm_flow, container_flow, etc. → NOT in dict → raise
}


def _derive_type_and_lifecycle(kind: str) -> tuple[str, str]:
    """Return (type, lifecycle_class) for an F11 kind value.

    See ``_KIND_TO_TYPE_LIFECYCLE`` for the full mapping table. Unknown
    kinds fall back to ``type='work', lifecycle_class='work_flow'``;
    the composite CHECK on ``entities`` will reject the INSERT loudly
    if the kind is also not in the permitted enum.
    """
    return _KIND_TO_TYPE_LIFECYCLE.get(kind, ("work", "work_flow"))


# ---------------------------------------------------------------------------
# Feature 108 (workspace identity foundation): workspace constants & DDL.
# ---------------------------------------------------------------------------
# FR-4: deterministic UUID for production __unknown__ rows AND test fixtures.
# DO NOT MODIFY THE SEED — changing it reassigns every __unknown__ entity.
_UNKNOWN_WORKSPACE_UUID_SEED: str = "pd-test-fixture-unknown-workspace"


def _compute_unknown_workspace_uuid() -> str:
    """Compute the canonical __unknown__ workspace UUID per FR-4 / Decision 3.

    Algorithm: SHA-256 of seed → first 32 hex chars → format as 8-4-4-4-12,
    forcing version nibble (idx 12) to '4' and variant nibble (idx 16) to
    {'8','9','a','b'} per RFC 4122 §4.4.
    """
    digest = hashlib.sha256(_UNKNOWN_WORKSPACE_UUID_SEED.encode()).hexdigest()
    h = digest[:32]
    return (
        f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-"
        f"{('8','9','a','b')[int(h[16],16) % 4]}{h[17:20]}-{h[20:32]}"
    )


_UNKNOWN_WORKSPACE_UUID: str = _compute_unknown_workspace_uuid()

# Pinned literal (asserted at import time). Tests assert byte-equality against
# this literal, NOT recompute-and-compare.
assert _UNKNOWN_WORKSPACE_UUID == "6250c8a6-5306-443f-b225-477a040016ea", (
    f"_UNKNOWN_WORKSPACE_UUID drift: got {_UNKNOWN_WORKSPACE_UUID}; "
    f"expected pinned literal — seed must not be mutated."
)

# FR-4: workspaces table DDL (used by Migration 11 step 5).
_WORKSPACES_TABLE_DDL: str = """
    CREATE TABLE workspaces (
        uuid               TEXT NOT NULL PRIMARY KEY,
        project_id_legacy  TEXT UNIQUE,
        project_root       TEXT,
        created_at         TEXT NOT NULL,
        updated_at         TEXT NOT NULL
    )
"""

_WORKSPACES_INDEX_DDL: str = (
    "CREATE INDEX idx_workspaces_legacy ON workspaces(project_id_legacy)"
)


def flatten_metadata(metadata: dict | None) -> str:
    """Flatten metadata JSON to space-separated string of all leaf scalar values.

    Recursively traverses dicts (values only) and lists (elements).
    None/null values are skipped. Scalars are converted via str().
    Returns empty string for None input or empty structures.
    """
    if metadata is None:
        return ""
    parts: list[str] = []

    def _collect(value):
        if value is None:
            return
        if isinstance(value, dict):
            for v in value.values():
                _collect(v)
        elif isinstance(value, list):
            for item in value:
                _collect(item)
        else:
            parts.append(str(value))

    _collect(metadata)
    return " ".join(parts)


def _create_initial_schema(conn: sqlite3.Connection) -> None:
    """Migration 1: create entities and _metadata tables, triggers, indexes."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            type_id        TEXT PRIMARY KEY,
            entity_type    TEXT NOT NULL CHECK(entity_type IN ('backlog','brainstorm','project','feature')),
            entity_id      TEXT NOT NULL,
            name           TEXT NOT NULL,
            status         TEXT,
            parent_type_id TEXT REFERENCES entities(type_id),
            artifact_path  TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            metadata       TEXT
        );

        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- Immutability triggers
        -- enforce_immutable_type_id and enforce_immutable_entity_type
        -- triggers removed in migration 12 (feature 109 FR-3): they
        -- blocked the type_id rewrite in promote_entity and the
        -- entity_type → kind backfill in migration 12.

        CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
        BEFORE UPDATE OF created_at ON entities
        BEGIN
            SELECT RAISE(ABORT, 'created_at is immutable');
        END;

        -- Self-parent prevention triggers
        CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
        BEFORE INSERT ON entities
        WHEN NEW.parent_type_id = NEW.type_id
        BEGIN
            SELECT RAISE(ABORT, 'entity cannot be its own parent');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
        BEFORE UPDATE OF parent_type_id ON entities
        WHEN NEW.parent_type_id = NEW.type_id
        BEGIN
            SELECT RAISE(ABORT, 'entity cannot be its own parent');
        END;

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
        CREATE INDEX IF NOT EXISTS idx_parent_type_id ON entities(parent_type_id);
        CREATE INDEX IF NOT EXISTS idx_status ON entities(status);
    """)


def _migrate_to_uuid_pk(conn):
    """Migration 2: Add UUID primary key, retain type_id as UNIQUE.

    This migration manages its own transaction (BEGIN IMMEDIATE / COMMIT /
    ROLLBACK). The outer _migrate() commit is a no-op. Future migrations
    MUST follow this same pattern if they perform DDL operations.
    """
    # OUTSIDE try — PRAGMA cannot run inside transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Pre-migration FK check (rollback handled by except block below)
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"FK violations found before migration: {fk_violations}"
            )

        conn.execute("""
            CREATE TABLE entities_new (
                uuid           TEXT NOT NULL PRIMARY KEY,
                type_id        TEXT NOT NULL UNIQUE,
                entity_type    TEXT NOT NULL CHECK(entity_type IN (
                    'backlog','brainstorm','project','feature')),
                entity_id      TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_type_id TEXT REFERENCES entities_new(type_id),
                parent_uuid    TEXT REFERENCES entities_new(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT
            )
        """)

        # Step 1: Read all existing rows
        rows = conn.execute("SELECT * FROM entities").fetchall()

        # Step 2: Generate UUID per row
        row_uuids = {}
        for row in rows:
            row_uuids[row["type_id"]] = str(uuid_mod.uuid4())

        # Step 3: INSERT into entities_new (parent_uuid omitted — defaults NULL)
        for row in rows:
            conn.execute(
                "INSERT INTO entities_new (uuid, type_id, entity_type, "
                "entity_id, name, status, parent_type_id, artifact_path, "
                "created_at, updated_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row_uuids[row["type_id"]], row["type_id"],
                 row["entity_type"], row["entity_id"], row["name"],
                 row["status"], row["parent_type_id"], row["artifact_path"],
                 row["created_at"], row["updated_at"], row["metadata"]),
            )

        # Step 4: Populate parent_uuid from parent_type_id
        for row in rows:
            if row["parent_type_id"] is not None:
                parent_uuid = row_uuids.get(row["parent_type_id"])
                if parent_uuid:
                    conn.execute(
                        "UPDATE entities_new SET parent_uuid = ? "
                        "WHERE type_id = ?",
                        (parent_uuid, row["type_id"]),
                    )

        conn.execute("DROP TABLE entities")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("ALTER TABLE entities_new RENAME TO entities")

        # Recreate triggers (enforce_immutable_type_id and
        # enforce_immutable_entity_type removed in migration 12 per
        # feature 109 FR-3).
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
            BEFORE UPDATE OF created_at ON entities
            BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
            BEFORE INSERT ON entities
            WHEN NEW.parent_type_id IS NOT NULL
                 AND NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
            BEFORE UPDATE OF parent_type_id ON entities
            WHEN NEW.parent_type_id IS NOT NULL
                 AND NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_uuid
            BEFORE UPDATE OF uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_insert
            BEFORE INSERT ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_update
            BEFORE UPDATE OF parent_uuid ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)

        # Recreate all 4 indexes
        conn.execute(
            "CREATE INDEX idx_entity_type ON entities(entity_type)"
        )
        conn.execute("CREATE INDEX idx_status ON entities(status)")
        conn.execute(
            "CREATE INDEX idx_parent_type_id ON entities(parent_type_id)"
        )
        conn.execute(
            "CREATE INDEX idx_parent_uuid ON entities(parent_uuid)"
        )

        # Update schema_version inside transaction (atomic with DDL/DML)
        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Re-enable FKs — runs on both success and failure
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-migration FK check — outside try, after commit
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"FK violations after migration: {post_violations}"
        )


def _create_workflow_phases_table(conn: sqlite3.Connection) -> None:
    """Migration 3: Create workflow_phases table with dual-dimension status model.

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    The outer _migrate() performs a second schema_version upsert + commit
    after this function returns. Both writes set version=3, so the second
    write is a no-op at the data level but does execute a SQL statement
    and commit.
    """
    # OUTSIDE try — PRAGMA cannot run inside transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Pre-migration FK check (rollback handled by except block below)
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"FK violations found before migration: {fk_violations}"
            )

        # CREATE TABLE with columns, CHECK constraints, FK, DEFAULT values
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_phases (
                type_id                    TEXT PRIMARY KEY
                                           REFERENCES entities(type_id),
                workflow_phase             TEXT CHECK(workflow_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish'
                                           ) OR workflow_phase IS NULL),
                kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                                           CHECK(kanban_column IN (
                                               'backlog','prioritised','wip',
                                               'agent_review','human_review',
                                               'blocked','documenting','completed'
                                           )),
                last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish'
                                           ) OR last_completed_phase IS NULL),
                mode                       TEXT CHECK(mode IN ('standard', 'full')
                                               OR mode IS NULL),
                backward_transition_reason TEXT,
                updated_at                 TEXT NOT NULL
            )
        """)

        # Immutability trigger for type_id
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_wp_type_id
            BEFORE UPDATE OF type_id ON workflow_phases
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
            END
        """)

        # Indexes for query performance
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_kanban_column "
            "ON workflow_phases(kanban_column)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_workflow_phase "
            "ON workflow_phases(workflow_phase)"
        )

        # Update schema_version inside transaction (atomic with DDL)
        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Re-enable FKs — runs on both success and failure
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-migration FK check — outside try, after commit
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"FK violations after migration: {post_violations}"
        )


def _create_fts_index(conn: sqlite3.Connection) -> None:
    """Migration 4: Create FTS5 virtual table and backfill from existing entities."""
    try:
        conn.execute("BEGIN IMMEDIATE")

        conn.execute("DROP TABLE IF EXISTS entities_fts")

        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text, "
                "content='entities', content_rowid='rowid')"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError("FTS5 extension not available") from exc
            raise

        # Backfill existing entities into FTS index
        rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in rows:
            metadata_text = flatten_metadata(
                json.loads(row[5]) if row[5] else None
            )
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
            )

        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '4') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _expand_workflow_phase_check(conn: sqlite3.Connection) -> None:
    """Migration 5: Expand CHECK constraint on workflow_phases.

    Widens workflow_phase and last_completed_phase to accept brainstorm/backlog
    lifecycle phases (draft, reviewing, promoted, abandoned, open, triaged,
    dropped) alongside the existing 7 feature phases.

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    The outer _migrate() performs a second schema_version upsert + commit
    after this function returns. Both writes set version=5, so the second
    write is a no-op at the data level.
    """
    # OUTSIDE try — PRAGMA cannot run inside transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Pre-migration FK check
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"FK violations found before migration: {fk_violations}"
            )

        # Recreate workflow_phases with expanded CHECK constraints
        conn.execute("""
            CREATE TABLE workflow_phases_new (
                type_id                    TEXT PRIMARY KEY
                                           REFERENCES entities(type_id),
                workflow_phase             TEXT CHECK(workflow_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped'
                                           ) OR workflow_phase IS NULL),
                kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                                           CHECK(kanban_column IN (
                                               'backlog','prioritised','wip',
                                               'agent_review','human_review',
                                               'blocked','documenting','completed'
                                           )),
                last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped'
                                           ) OR last_completed_phase IS NULL),
                mode                       TEXT CHECK(mode IN ('standard', 'full')
                                               OR mode IS NULL),
                backward_transition_reason TEXT,
                updated_at                 TEXT NOT NULL
            )
        """)

        # Copy all existing data (explicit column list for forward-compat)
        conn.execute(
            "INSERT INTO workflow_phases_new "
            "(type_id, workflow_phase, kanban_column, "
            "last_completed_phase, mode, backward_transition_reason, updated_at) "
            "SELECT type_id, workflow_phase, kanban_column, "
            "last_completed_phase, mode, backward_transition_reason, updated_at "
            "FROM workflow_phases"
        )

        # Drop old table and rename
        conn.execute("DROP TABLE workflow_phases")
        conn.execute(
            "ALTER TABLE workflow_phases_new RENAME TO workflow_phases"
        )

        # Recreate trigger
        conn.execute("""
            CREATE TRIGGER enforce_immutable_wp_type_id
            BEFORE UPDATE OF type_id ON workflow_phases
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
            END
        """)

        # Recreate indexes
        conn.execute(
            "CREATE INDEX idx_wp_kanban_column "
            "ON workflow_phases(kanban_column)"
        )
        conn.execute(
            "CREATE INDEX idx_wp_workflow_phase "
            "ON workflow_phases(workflow_phase)"
        )

        # Update schema_version inside transaction (atomic with DDL)
        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '5') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Re-enable FKs — runs on both success and failure
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-migration FK check — outside try, after commit
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"FK violations after migration: {post_violations}"
        )


def _schema_expansion_v6(conn: sqlite3.Connection) -> None:
    """Migration 6: Entity type expansion, 5D phases, light mode, junction tables.

    14-step DDL sequence:
    1. PRAGMA foreign_keys=OFF
    2. BEGIN IMMEDIATE
    3. Rebuild entities table (drop entity_type CHECK constraint)
    4. Rebuild workflow_phases (expand CHECK, add uuid column with backfill)
    5. Rebuild entities_fts virtual table
    6. CREATE entity_tags table
    7. CREATE entity_dependencies table
    8. CREATE entity_okr_alignment table
    9. INSERT next_seq_{type} entries into _metadata
    10. PRAGMA foreign_key_check
    11. Data integrity check A: backfill orphaned parent_uuid
    12. Data integrity check B: check orphaned workflow_phases / NULL uuids
    13. COMMIT
    14. PRAGMA foreign_keys=ON

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    """
    # --- Step 1: PRAGMA foreign_keys=OFF ---
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        # --- Step 2: BEGIN IMMEDIATE ---
        conn.execute("BEGIN IMMEDIATE")

        # Pre-migration FK check
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"FK violations found before migration: {fk_violations}"
            )

        # --- Step 3: Rebuild entities table (drop entity_type CHECK) ---
        conn.execute("""
            CREATE TABLE entities_new (
                uuid           TEXT NOT NULL PRIMARY KEY,
                type_id        TEXT NOT NULL UNIQUE,
                entity_type    TEXT NOT NULL,
                entity_id      TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_type_id TEXT REFERENCES entities_new(type_id),
                parent_uuid    TEXT REFERENCES entities_new(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT
            )
        """)

        conn.execute(
            "INSERT INTO entities_new "
            "SELECT uuid, type_id, entity_type, entity_id, name, status, "
            "parent_type_id, parent_uuid, artifact_path, created_at, "
            "updated_at, metadata FROM entities"
        )

        conn.execute("DROP TABLE entities")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("ALTER TABLE entities_new RENAME TO entities")

        # Recreate triggers on entities (enforce_immutable_type_id and
        # enforce_immutable_entity_type removed in migration 12 per
        # feature 109 FR-3).
        conn.execute("""
            CREATE TRIGGER enforce_immutable_created_at
            BEFORE UPDATE OF created_at ON entities
            BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent
            BEFORE INSERT ON entities
            WHEN NEW.parent_type_id IS NOT NULL
                 AND NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent_update
            BEFORE UPDATE OF parent_type_id ON entities
            WHEN NEW.parent_type_id IS NOT NULL
                 AND NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_immutable_uuid
            BEFORE UPDATE OF uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent_uuid_insert
            BEFORE INSERT ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent_uuid_update
            BEFORE UPDATE OF parent_uuid ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)

        # Recreate indexes on entities
        conn.execute(
            "CREATE INDEX idx_entity_type ON entities(entity_type)"
        )
        conn.execute("CREATE INDEX idx_status ON entities(status)")
        conn.execute(
            "CREATE INDEX idx_parent_type_id ON entities(parent_type_id)"
        )
        conn.execute(
            "CREATE INDEX idx_parent_uuid ON entities(parent_uuid)"
        )

        # --- Step 4: Rebuild workflow_phases (expand CHECK, add uuid column) ---
        # All valid workflow phases: existing 7 + brainstorm/backlog lifecycle + 5D
        conn.execute("""
            CREATE TABLE workflow_phases_new (
                type_id                    TEXT PRIMARY KEY
                                           REFERENCES entities(type_id),
                workflow_phase             TEXT CHECK(workflow_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR workflow_phase IS NULL),
                kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                                           CHECK(kanban_column IN (
                                               'backlog','prioritised','wip',
                                               'agent_review','human_review',
                                               'blocked','documenting','completed'
                                           )),
                last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR last_completed_phase IS NULL),
                mode                       TEXT CHECK(mode IN (
                                               'standard', 'full', 'light'
                                           ) OR mode IS NULL),
                backward_transition_reason TEXT,
                updated_at                 TEXT NOT NULL,
                uuid                       TEXT
            )
        """)

        # Copy existing data (uuid defaults to NULL, backfilled below)
        conn.execute(
            "INSERT INTO workflow_phases_new "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at) "
            "SELECT type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at FROM workflow_phases"
        )

        # Backfill uuid from entities table
        conn.execute(
            "UPDATE workflow_phases_new SET uuid = ("
            "  SELECT e.uuid FROM entities e "
            "  WHERE e.type_id = workflow_phases_new.type_id"
            ")"
        )

        conn.execute("DROP TABLE workflow_phases")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(
            "ALTER TABLE workflow_phases_new RENAME TO workflow_phases"
        )

        # Recreate trigger on workflow_phases
        conn.execute("""
            CREATE TRIGGER enforce_immutable_wp_type_id
            BEFORE UPDATE OF type_id ON workflow_phases
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
            END
        """)

        # Recreate indexes on workflow_phases
        conn.execute(
            "CREATE INDEX idx_wp_kanban_column "
            "ON workflow_phases(kanban_column)"
        )
        conn.execute(
            "CREATE INDEX idx_wp_workflow_phase "
            "ON workflow_phases(workflow_phase)"
        )
        conn.execute(
            "CREATE INDEX idx_wp_uuid ON workflow_phases(uuid)"
        )

        # --- Step 5: Rebuild entities_fts virtual table ---
        conn.execute("DROP TABLE IF EXISTS entities_fts")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text, "
                "content='entities', content_rowid='rowid')"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError("FTS5 extension not available") from exc
            raise

        # Backfill FTS from entities
        rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in rows:
            metadata_text = flatten_metadata(
                json.loads(row[5]) if row[5] else None
            )
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
            )

        # --- Step 6: CREATE entity_tags table ---
        conn.execute("""
            CREATE TABLE entity_tags (
                entity_uuid TEXT NOT NULL,
                tag         TEXT NOT NULL,
                UNIQUE(entity_uuid, tag)
            )
        """)
        conn.execute(
            "CREATE INDEX idx_et_entity_uuid ON entity_tags(entity_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_et_tag ON entity_tags(tag)"
        )

        # --- Step 7: CREATE entity_dependencies table ---
        conn.execute("""
            CREATE TABLE entity_dependencies (
                entity_uuid     TEXT NOT NULL,
                blocked_by_uuid TEXT NOT NULL,
                UNIQUE(entity_uuid, blocked_by_uuid)
            )
        """)
        conn.execute(
            "CREATE INDEX idx_ed_entity_uuid "
            "ON entity_dependencies(entity_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_ed_blocked_by_uuid "
            "ON entity_dependencies(blocked_by_uuid)"
        )

        # --- Step 8: CREATE entity_okr_alignment table ---
        conn.execute("""
            CREATE TABLE entity_okr_alignment (
                entity_uuid      TEXT NOT NULL,
                key_result_uuid  TEXT NOT NULL,
                UNIQUE(entity_uuid, key_result_uuid)
            )
        """)
        conn.execute(
            "CREATE INDEX idx_eoa_entity_uuid "
            "ON entity_okr_alignment(entity_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_eoa_key_result_uuid "
            "ON entity_okr_alignment(key_result_uuid)"
        )

        # --- Step 9: INSERT next_seq_{type} entries into _metadata ---
        # Bootstrap from max existing sequential IDs for each entity type
        entity_types = conn.execute(
            "SELECT DISTINCT entity_type FROM entities"
        ).fetchall()
        for (etype,) in entity_types:
            key = f"next_seq_{etype}"
            # Only bootstrap if key doesn't already exist
            existing = conn.execute(
                "SELECT value FROM _metadata WHERE key = ?", (key,)
            ).fetchone()
            if existing is None:
                # Extract max numeric prefix from entity_id values
                rows = conn.execute(
                    "SELECT entity_id FROM entities WHERE entity_type = ?",
                    (etype,),
                ).fetchall()
                max_seq = 0
                for (eid,) in rows:
                    # entity_id format: {seq}-{slug} or legacy formats
                    parts = eid.split("-", 1)
                    try:
                        seq_val = int(parts[0])
                        if seq_val > max_seq:
                            max_seq = seq_val
                    except (ValueError, IndexError):
                        pass
                conn.execute(
                    "INSERT INTO _metadata(key, value) VALUES(?, ?)",
                    (key, str(max_seq)),
                )

        # --- Step 10: PRAGMA foreign_key_check ---
        # NOTE: Deferred to post-commit. During the transaction, PRAGMA
        # foreign_key_check reports false positives because CREATE TABLE
        # FKs reference the pre-rename table name (entities_new). The
        # post-commit check below (after PRAGMA foreign_keys=ON) validates
        # correctly against the final table names.

        # --- Step 11: Data integrity check A — backfill orphaned parent_uuid ---
        conn.execute("""
            UPDATE entities SET parent_uuid = (
                SELECT e2.uuid FROM entities e2
                WHERE e2.type_id = entities.parent_type_id
            )
            WHERE parent_type_id IS NOT NULL AND parent_uuid IS NULL
        """)

        # --- Step 12: Data integrity check B — orphaned workflow_phases / NULL uuids ---
        orphaned_wp = conn.execute(
            "SELECT wp.type_id FROM workflow_phases wp "
            "LEFT JOIN entities e ON wp.type_id = e.type_id "
            "WHERE e.type_id IS NULL"
        ).fetchall()
        if orphaned_wp:
            # Delete orphaned workflow_phases rows (no matching entity)
            for (tid,) in orphaned_wp:
                conn.execute(
                    "DELETE FROM workflow_phases WHERE type_id = ?", (tid,)
                )

        null_uuid_wp = conn.execute(
            "SELECT type_id FROM workflow_phases WHERE uuid IS NULL"
        ).fetchall()
        if null_uuid_wp:
            # Re-attempt backfill for any remaining NULL uuids
            conn.execute(
                "UPDATE workflow_phases SET uuid = ("
                "  SELECT e.uuid FROM entities e "
                "  WHERE e.type_id = workflow_phases.type_id"
                ") WHERE uuid IS NULL"
            )

        # Update schema_version inside transaction (atomic with DDL)
        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '6') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )

        # --- Step 13: COMMIT ---
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # --- Step 14: PRAGMA foreign_keys=ON ---
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-migration FK check — outside try, after commit
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"FK violations after migration: {post_violations}"
        )


def _fix_fts_content_mode(conn: sqlite3.Connection) -> None:
    """Migration 7: Remove external-content mode from entities_fts.

    Drops and recreates entities_fts as a standalone content-bearing
    FTS5 table, then backfills from all existing entities.
    """
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("DROP TABLE IF EXISTS entities_fts")
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE entities_fts USING fts5("
            "name, entity_id, entity_type, status, metadata_text)"
        )
    except sqlite3.OperationalError as exc:
        if "no such module: fts5" in str(exc):
            raise RuntimeError("FTS5 extension not available") from exc
        raise
    rows = conn.execute(
        "SELECT rowid, name, entity_id, entity_type, status, metadata "
        "FROM entities"
    ).fetchall()
    for row in rows:
        metadata_text = flatten_metadata(
            json.loads(row[5]) if row[5] else None
        )
        conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
        )
    conn.commit()


def _add_project_scoping(conn: sqlite3.Connection) -> None:
    """Migration 8: Add project scoping — projects table, sequences table, entities.project_id.

    14-step DDL sequence (see design I-7):
    1. PRAGMA foreign_keys=OFF
    2. BEGIN IMMEDIATE
    3. CREATE projects table (13 columns)
    4. CREATE sequences table
    5. CREATE entities_new (with project_id, UNIQUE(project_id, type_id),
       no parent_type_id FK, parent_uuid FK preserved)
    6. Data copy with '__unknown__' for project_id
    7. DROP + RENAME
    8. Recreate 9 triggers (8 existing + enforce_immutable_project_id)
    9. Recreate 6 indexes (4 existing + idx_project_id + idx_project_entity_type)
    10. Migrate _metadata next_seq_* to sequences table
    11. Rebuild FTS5
    12. Update schema_version to 8
    13. COMMIT
    14. PRAGMA foreign_keys=ON

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    """
    # --- Step 1: PRAGMA foreign_keys=OFF ---
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        # --- Step 2: BEGIN IMMEDIATE ---
        conn.execute("BEGIN IMMEDIATE")

        # --- Step 3: CREATE projects table ---
        conn.execute("""
            CREATE TABLE projects (
                project_id      TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                root_commit_sha TEXT,
                remote_url      TEXT,
                normalized_url  TEXT,
                remote_host     TEXT,
                remote_owner    TEXT,
                remote_repo     TEXT,
                default_branch  TEXT,
                project_root    TEXT,
                is_git_repo     INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)

        # --- Step 4: CREATE sequences table ---
        conn.execute("""
            CREATE TABLE sequences (
                project_id  TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                next_val    INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (project_id, entity_type)
            )
        """)

        # --- Step 5: CREATE entities_new ---
        conn.execute("""
            CREATE TABLE entities_new (
                uuid           TEXT NOT NULL PRIMARY KEY,
                type_id        TEXT NOT NULL,
                project_id     TEXT NOT NULL DEFAULT '__unknown__',
                entity_type    TEXT NOT NULL,
                entity_id      TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_type_id TEXT,
                parent_uuid    TEXT REFERENCES entities_new(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT,
                UNIQUE(project_id, type_id)
            )
        """)

        # --- Step 6: Data copy ---
        conn.execute(
            "INSERT INTO entities_new (uuid, type_id, project_id, entity_type, "
            "entity_id, name, status, parent_type_id, parent_uuid, "
            "artifact_path, created_at, updated_at, metadata) "
            "SELECT uuid, type_id, '__unknown__', entity_type, entity_id, "
            "name, status, parent_type_id, parent_uuid, artifact_path, "
            "created_at, updated_at, metadata "
            "FROM entities"
        )

        # --- Step 7: DROP + RENAME ---
        conn.execute("DROP TABLE entities")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("ALTER TABLE entities_new RENAME TO entities")

        # --- Step 8: Recreate triggers ---
        # enforce_immutable_type_id and enforce_immutable_entity_type
        # removed in migration 12 (feature 109 FR-3).
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
            BEFORE UPDATE OF created_at ON entities
            BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_uuid
            BEFORE UPDATE OF uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_project_id
            BEFORE UPDATE OF project_id ON entities
            BEGIN SELECT RAISE(ABORT, 'project_id is immutable — use re-attribution API'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
            BEFORE INSERT ON entities
            WHEN NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
            BEFORE UPDATE OF parent_type_id ON entities
            WHEN NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_insert
            BEFORE INSERT ON entities
            WHEN NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_update
            BEFORE UPDATE OF parent_uuid ON entities
            WHEN NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)

        # --- Step 9: Recreate 6 indexes ---
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON entities(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_type_id ON entities(parent_type_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_uuid ON entities(parent_uuid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_id ON entities(project_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_entity_type "
            "ON entities(project_id, entity_type)"
        )

        # --- Step 9b: Rebuild workflow_phases to remove FK on entities(type_id) ---
        # type_id is no longer UNIQUE in entities (composite UNIQUE now),
        # so the FK REFERENCES entities(type_id) would cause FK mismatch errors.
        conn.execute("""
            CREATE TABLE workflow_phases_new (
                type_id                    TEXT PRIMARY KEY,
                workflow_phase             TEXT CHECK(workflow_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR workflow_phase IS NULL),
                kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                                           CHECK(kanban_column IN (
                                               'backlog','prioritised','wip',
                                               'agent_review','human_review',
                                               'blocked','documenting','completed'
                                           )),
                last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','create-tasks',
                                               'implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR last_completed_phase IS NULL),
                mode                       TEXT CHECK(mode IN (
                                               'standard', 'full', 'light'
                                           ) OR mode IS NULL),
                backward_transition_reason TEXT,
                updated_at                 TEXT NOT NULL,
                uuid                       TEXT
            )
        """)
        conn.execute(
            "INSERT INTO workflow_phases_new "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at, uuid) "
            "SELECT type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at, uuid "
            "FROM workflow_phases"
        )
        conn.execute("DROP TABLE workflow_phases")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(
            "ALTER TABLE workflow_phases_new RENAME TO workflow_phases"
        )
        # Recreate workflow_phases trigger and indexes
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_wp_type_id
            BEFORE UPDATE OF type_id ON workflow_phases
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
            END
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_kanban_column "
            "ON workflow_phases(kanban_column)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_workflow_phase "
            "ON workflow_phases(workflow_phase)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_uuid "
            "ON workflow_phases(uuid)"
        )

        # --- Step 10: Migrate _metadata counters to sequences ---
        seq_rows = conn.execute(
            "SELECT key, value FROM _metadata WHERE key LIKE 'next_seq_%'"
        ).fetchall()
        for row in seq_rows:
            key = row[0]
            value = row[1]
            entity_type = key[len("next_seq_"):]
            conn.execute(
                "INSERT INTO sequences(project_id, entity_type, next_val) "
                "VALUES(?, ?, ?)",
                ("__unknown__", entity_type, int(value)),
            )
            conn.execute(
                "DELETE FROM _metadata WHERE key = ?", (key,)
            )

        # --- Step 11: Rebuild FTS5 ---
        conn.execute("DROP TABLE IF EXISTS entities_fts")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text)"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError("FTS5 extension not available") from exc
            raise
        rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in rows:
            metadata_text = flatten_metadata(
                json.loads(row[5]) if row[5] else None
            )
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
            )

        # --- Step 12: Update schema_version ---
        conn.execute(
            "INSERT INTO _metadata (key, value) VALUES ('schema_version', '8') "
            "ON CONFLICT(key) DO UPDATE SET value = '8'"
        )

        # --- Step 13: COMMIT ---
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # --- Step 14: PRAGMA foreign_keys=ON ---
        conn.execute("PRAGMA foreign_keys = ON")


def _migration_9_remove_create_tasks(conn: sqlite3.Connection) -> None:
    """Migration 9: Remove 'create-tasks' from workflow_phases CHECK constraints.

    Feature 073 merges create-tasks into create-plan. This migration:
    1. Rebuilds workflow_phases table with updated CHECK constraints
       (6 feature phases instead of 7).
    2. Migrates existing rows: create-tasks -> create-plan.

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    The outer _migrate() performs a second schema_version upsert + commit
    after this function returns.
    """
    # OUTSIDE try — PRAGMA cannot run inside transaction
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
        )
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Pre-migration FK check
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"FK violations found before migration: {fk_violations}"
            )

        # Migrate data BEFORE rebuilding table (while old CHECK still allows create-tasks)
        conn.execute(
            "UPDATE workflow_phases SET workflow_phase = 'create-plan' "
            "WHERE workflow_phase = 'create-tasks'"
        )
        conn.execute(
            "UPDATE workflow_phases SET last_completed_phase = 'create-plan' "
            "WHERE last_completed_phase = 'create-tasks'"
        )

        # Recreate workflow_phases with updated CHECK constraints (no create-tasks)
        conn.execute("""
            CREATE TABLE workflow_phases_new (
                type_id                    TEXT PRIMARY KEY,
                workflow_phase             TEXT CHECK(workflow_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR workflow_phase IS NULL),
                kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                                           CHECK(kanban_column IN (
                                               'backlog','prioritised','wip',
                                               'agent_review','human_review',
                                               'blocked','documenting','completed'
                                           )),
                last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                               'brainstorm','specify','design',
                                               'create-plan','implement','finish',
                                               'draft','reviewing','promoted','abandoned',
                                               'open','triaged','dropped',
                                               'discover','define','deliver','debrief'
                                           ) OR last_completed_phase IS NULL),
                mode                       TEXT CHECK(mode IN (
                                               'standard', 'full', 'light'
                                           ) OR mode IS NULL),
                backward_transition_reason TEXT,
                updated_at                 TEXT NOT NULL,
                uuid                       TEXT
            )
        """)

        # Copy all existing data
        conn.execute(
            "INSERT INTO workflow_phases_new "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at, uuid) "
            "SELECT type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at, uuid "
            "FROM workflow_phases"
        )

        # Drop old table and rename
        conn.execute("DROP TABLE workflow_phases")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(
            "ALTER TABLE workflow_phases_new RENAME TO workflow_phases"
        )

        # Recreate trigger
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_wp_type_id
            BEFORE UPDATE OF type_id ON workflow_phases
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases.type_id is immutable');
            END
        """)

        # Recreate indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_kanban_column "
            "ON workflow_phases(kanban_column)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_workflow_phase "
            "ON workflow_phases(workflow_phase)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_uuid "
            "ON workflow_phases(uuid)"
        )

        # Update schema_version inside transaction (atomic with DDL)
        conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Re-enable FKs — runs on both success and failure
        conn.execute("PRAGMA foreign_keys = ON")

    # Post-migration FK check — outside try, after commit
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"FK violations after migration: {post_violations}"
        )


def _migration_10_phase_events(conn: sqlite3.Connection) -> None:
    """Create phase_events table + composite indexes + backfill from metadata.

    Feature 088 hardening:
    - FR-6.4: ``BEGIN IMMEDIATE`` is inside the try block, eliminating the
      window where an exception between BEGIN and try leaves an open
      transaction.
    - FR-2.2: schema_version re-check as first statement inside try
      (double-check after BEGIN IMMEDIATE serializes concurrent runners);
      partial UNIQUE index on backfill rows + ``INSERT OR IGNORE`` so a
      concurrent double-invocation produces the same row count as a single
      run.
    - FR-2.6: each timestamp read from metadata is validated via
      ``datetime.fromisoformat``; rows with unparseable timestamps are
      skipped with a stderr warning. ``backward_reason`` and
      ``backward_target`` are truncated to 500 chars before INSERT.
    """
    try:
        conn.execute("BEGIN IMMEDIATE")

        # FR-2.2: schema_version re-check as first statement inside try.
        # If another process completed migration 10 between the caller's
        # version check and our BEGIN IMMEDIATE, early-return as a no-op.
        try:
            v_row = conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchone()
            if v_row is not None:
                try:
                    current_version = int(v_row[0])
                except (TypeError, ValueError):
                    current_version = 0
                if current_version >= 10:
                    conn.rollback()
                    return
        except sqlite3.OperationalError as e:
            # Feature 089 FR-1.4 / AC-4 (#00142): narrow the catch so only the
            # "_metadata table does not yet exist" case is swallowed — any
            # other OperationalError (e.g. ``database is locked``) must
            # propagate so callers see the real failure.
            if 'no such table' not in str(e).lower():
                raise
            # _metadata table does not yet exist — safe to proceed.

        # Existing DDL (unchanged per design — deployed schema).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS phase_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id         TEXT NOT NULL,
                project_id      TEXT NOT NULL,
                phase           TEXT NOT NULL,
                event_type      TEXT NOT NULL CHECK(event_type IN (
                    'started', 'completed', 'skipped', 'backward'
                )),
                timestamp       TEXT NOT NULL,
                iterations      INTEGER,
                reviewer_notes  TEXT,
                backward_reason TEXT,
                backward_target TEXT,
                source          TEXT NOT NULL DEFAULT 'live' CHECK(
                    source IN ('live', 'backfill')
                ),
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pe_lookup ON phase_events(type_id, phase, event_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pe_project ON phase_events(project_id, event_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pe_timestamp ON phase_events(timestamp)"
        )

        # FR-2.2: scoped dedup of rows from prior concurrent-race backfills
        # (before creating the UNIQUE index, which would otherwise fail).
        # Only source='backfill' rows can have re-run duplicates; live rows
        # are append-only analytics with naturally-unique created_at.
        conn.execute(
            "DELETE FROM phase_events "
            "WHERE source = 'backfill' AND id NOT IN ("
            "    SELECT MIN(id) FROM phase_events "
            "    WHERE source = 'backfill' "
            "    GROUP BY type_id, phase, event_type, timestamp"
            ")"
        )

        # FR-2.2: partial UNIQUE index on backfill rows only. Live writes
        # are not constrained — two legitimate same-second events coexist.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS phase_events_backfill_dedup "
            "ON phase_events(type_id, phase, event_type, timestamp) "
            "WHERE source = 'backfill'"
        )

        # Backfill from existing metadata.
        # Feature 108 Migration 11: when invoked AFTER Migration 11 (e.g. by
        # tests that reset phase_events on a post-11 DB), the entities table
        # no longer has a ``project_id`` column. Detect and JOIN to the
        # workspaces table for the legacy id.
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entity_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()
        }
        if "project_id" in entity_cols:
            rows = conn.execute(
                "SELECT type_id, project_id, metadata, created_at "
                "FROM entities WHERE metadata IS NOT NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.type_id AS type_id, "
                "w.project_id_legacy AS project_id, "
                "e.metadata AS metadata, e.created_at AS created_at "
                "FROM entities e "
                "LEFT JOIN workspaces w ON e.workspace_uuid = w.uuid "
                "WHERE e.metadata IS NOT NULL"
            ).fetchall()

        def _valid_iso(ts: str | None) -> bool:
            """FR-2.6: reject unparseable timestamps via datetime.fromisoformat."""
            if not ts or not isinstance(ts, str):
                return False
            try:
                # fromisoformat pre-3.11 does not accept 'Z' suffix.
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return True
            except (ValueError, TypeError):
                return False

        for row in rows:
            type_id, project_id, meta_str, created_at = (
                row[0], row[1], row[2], row[3],
            )
            try:
                meta = json.loads(meta_str)
            except (json.JSONDecodeError, TypeError):
                print(
                    f"[entity-registry] migration 10: skipping malformed "
                    f"metadata for {type_id}",
                    file=sys.stderr,
                )
                continue

            phase_timing = meta.get("phase_timing", {})
            if not isinstance(phase_timing, dict):
                phase_timing = {}
            for phase, timing in phase_timing.items():
                if not isinstance(timing, dict):
                    continue
                started_ts = timing.get("started")
                if started_ts:
                    if not _valid_iso(started_ts):
                        print(
                            f"[migration-10] skipping unparseable timestamp "
                            f"{started_ts} for {type_id}:{phase}",
                            file=sys.stderr,
                        )
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO phase_events "
                            "(type_id, project_id, phase, event_type, timestamp, "
                            "source, created_at) "
                            "VALUES (?, ?, ?, 'started', ?, 'backfill', ?)",
                            (type_id, project_id, phase, started_ts, now),
                        )
                completed_ts = timing.get("completed")
                if completed_ts:
                    if not _valid_iso(completed_ts):
                        print(
                            f"[migration-10] skipping unparseable timestamp "
                            f"{completed_ts} for {type_id}:{phase}",
                            file=sys.stderr,
                        )
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO phase_events "
                            "(type_id, project_id, phase, event_type, timestamp, "
                            "iterations, reviewer_notes, source, created_at) "
                            "VALUES (?, ?, ?, 'completed', ?, ?, ?, 'backfill', ?)",
                            (
                                type_id, project_id, phase,
                                completed_ts,
                                timing.get("iterations"),
                                json.dumps(timing.get("reviewerNotes"))
                                if timing.get("reviewerNotes") else None,
                                now,
                            ),
                        )

            skipped_list = meta.get("skipped_phases", [])
            if not isinstance(skipped_list, list):
                skipped_list = []
            for skipped in skipped_list:
                skipped_ts = created_at or now
                if not _valid_iso(skipped_ts):
                    print(
                        f"[migration-10] skipping unparseable timestamp "
                        f"{skipped_ts} for {type_id}:{skipped}",
                        file=sys.stderr,
                    )
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO phase_events "
                    "(type_id, project_id, phase, event_type, timestamp, "
                    "source, created_at) "
                    "VALUES (?, ?, ?, 'skipped', ?, 'backfill', ?)",
                    (type_id, project_id, skipped, skipped_ts, now),
                )

            for bh in meta.get("backward_history", []):
                if not isinstance(bh, dict):
                    continue
                bh_ts = bh.get("timestamp", now)
                if not _valid_iso(bh_ts):
                    src_phase_name = bh.get("source_phase", "unknown")
                    print(
                        f"[migration-10] skipping unparseable timestamp "
                        f"{bh_ts} for {type_id}:{src_phase_name}",
                        file=sys.stderr,
                    )
                    continue
                # FR-2.6: truncate backward_reason / backward_target to 500 chars.
                bh_reason = bh.get("reason")
                if isinstance(bh_reason, str):
                    bh_reason = bh_reason[:500]
                bh_target = bh.get("target_phase")
                if isinstance(bh_target, str):
                    bh_target = bh_target[:500]
                conn.execute(
                    "INSERT OR IGNORE INTO phase_events "
                    "(type_id, project_id, phase, event_type, timestamp, "
                    "backward_reason, backward_target, source, created_at) "
                    "VALUES (?, ?, ?, 'backward', ?, ?, ?, 'backfill', ?)",
                    (
                        type_id, project_id,
                        bh.get("source_phase", "unknown"),
                        bh_ts,
                        bh_reason,
                        bh_target,
                        now,
                    ),
                )

        # Feature 090 FR-3 / AC-3 (#00174): restore the in-function
        # ``schema_version=10`` stamp so the DDL/DML body AND the stamp
        # commit atomically in a single transaction.  Feature 089 Bundle
        # C.4 removed this in favour of letting the outer ``_migrate()``
        # loop (``database.py`` around line 3919) perform the upsert, but
        # that left a crash window: a process killed (SIGKILL, OOM) between
        # the migration's ``conn.commit()`` and the outer loop's stamp
        # commit leaves the DB with phase_events populated at
        # schema_version=9, which would re-run migration 10 on the next
        # open.  With the stamp inside the same transaction as the DDL,
        # that window is eliminated — schema + stamp are either both
        # present or both absent.  The outer loop's subsequent upsert is
        # a no-op idempotent write (same key, same value) on ``ON CONFLICT
        # DO UPDATE``.
        conn.execute("INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '10')")
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise


def _atomic_write_workspace_mapping(
    workspace_root: str, mapping: dict[str, str]
) -> str:
    """Atomic-write the migration-11 workspace mapping audit JSON.

    Writes ``<workspace_root>/.claude/pd/migrations/migration-11-workspace-mapping.json``
    using the same-directory tempfile + os.replace pattern (NFR-7 atomicity).

    Parameters
    ----------
    workspace_root:
        Absolute path of the directory that owns ``.claude/``.
    mapping:
        ``{old_project_id_hex: new_workspace_uuid}`` dict.

    Returns
    -------
    str
        Absolute path to the emitted file.
    """
    import tempfile as _tempfile

    target_dir = os.path.join(
        workspace_root, ".claude", "pd", "migrations"
    )
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "migration-11-workspace-mapping.json")

    fd, tmp_path = _tempfile.mkstemp(
        prefix=".migration-11-workspace-mapping.", suffix=".json", dir=target_dir,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return target_path


def _migration_11_workspace_identity(conn: sqlite3.Connection) -> None:
    """Migration 11: workspaces table + entities.workspace_uuid + drop parent_type_id.

    Per spec FR-7 / design §7.1, this is a single transactional unit replicating
    Migration 10's in-tx schema_version stamp pattern (database.py:1604-1618)
    plus the concurrent re-check guard (database.py:1396-1418).

    17 steps:
      0. Pre-tx: workspace mapping audit (writes JSON file).
      1. PRAGMA foreign_keys = OFF (outside transaction).
      2. BEGIN IMMEDIATE.
      3. Concurrent re-check guard.
      4. Pre-migration FK check.
      5. Bootstrap workspaces table.
      6. Pre-migration parent_type_id orphan assertion.
      7-8. Build entities_new + JOIN backfill + DROP/RENAME.
      9-10. Recreate triggers (7) + indexes (5).
      11. workflow_phases.workspace_uuid ALTER + autofill + reject triggers.
      12. Rebuild sequences keyed on workspace_uuid.
      13. Rebuild projects with workspace_uuid NOT NULL.
      14. Rebuild entities_fts.
      15. UPDATE _metadata SET schema_version='11' (in-tx stamp).
      16. COMMIT.
      17. PRAGMA foreign_keys = ON; post-FK check.

    Raises:
        RuntimeError on FK violations (pre or post) or
        on parent_type_id orphan assertion failure.
    """
    # ----------------------------------------------------------------------
    # Pre-step 0: outer-level early-return guard.
    # ----------------------------------------------------------------------
    # If the schema is already at version 11, step 0 (which reads the
    # legacy ``project_id`` column) would crash with OperationalError.
    # The in-tx re-check guard (step 3) cannot help because step 0 runs
    # pre-transaction. Bail out early — this also makes the migration
    # idempotent for callers outside the outer ``_migrate()`` loop.
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is not None:
            try:
                current_version = int(v_row[0])
            except (TypeError, ValueError):
                current_version = 0
            if current_version >= 11:
                # Feature 114 FR-M11.1: verify schema state matches stamp
                # before trusting it. Same stub-trap-style defense as M12.
                try:
                    cols = {
                        r[1] for r in conn.execute(
                            "PRAGMA table_info(entities)"
                        ).fetchall()
                    }
                    if "workspace_uuid" in cols:
                        return  # genuine post-M11 state
                    # Stamp present but column missing — fall through.
                except sqlite3.OperationalError:
                    pass
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            raise

    # ----------------------------------------------------------------------
    # Step 0: workspace mapping audit (PRE-TRANSACTION)
    # ----------------------------------------------------------------------
    # Compute the mapping {legacy_project_id: new_workspace_uuid} for every
    # distinct project_id present in entities.
    distinct_pids = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT project_id FROM entities"
        ).fetchall()
    ]
    mapping: dict[str, str] = {}
    unknown_count = 0
    for pid in distinct_pids:
        if pid == "__unknown__":
            mapping[pid] = _UNKNOWN_WORKSPACE_UUID
            unknown_count = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE project_id = '__unknown__'"
            ).fetchone()[0]
        else:
            mapping[pid] = str(uuid_mod.uuid4())

    # Feature 132 (D6.5 call-half): the workspace-mapping audit JSON
    # write (_atomic_write_workspace_mapping) is REMOVED here — a
    # filesystem side effect inside a migration body, incompatible with
    # the rebuild tool's step-1 chain replay running this same function
    # against an empty staging file (spec FR132-5b; #066's root cause).
    # DDL/DML is unchanged: `mapping` (built above) still seeds the
    # `workspaces` table below; only the JSON emission is gone. The now
    # callerless `_atomic_write_workspace_mapping` function body is
    # retained (feature 132 task 5 deletes it).

    if unknown_count:
        print(
            f"[migration-11] WARN: {unknown_count} entities with "
            f"project_id='__unknown__' attributed to canonical "
            f"unknown-workspace UUID; review with claim_unknown_entities "
            f"post-migration.",
            file=sys.stderr,
        )

    # ----------------------------------------------------------------------
    # Step 1: PRAGMA foreign_keys = OFF (outside transaction)
    # ----------------------------------------------------------------------
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 11"
        )

    try:
        # ------------------------------------------------------------------
        # Step 2: BEGIN IMMEDIATE
        # ------------------------------------------------------------------
        conn.execute("BEGIN IMMEDIATE")

        # ------------------------------------------------------------------
        # Step 3: concurrent re-check guard
        # ------------------------------------------------------------------
        # Replicates Migration 10 pattern at database.py:1396-1418. If
        # another process completed migration 11 between our caller's
        # check and our BEGIN IMMEDIATE, early-return as a no-op.
        try:
            v_row = conn.execute(
                "SELECT value FROM _metadata WHERE key='schema_version'"
            ).fetchone()
            if v_row is not None:
                try:
                    current_version = int(v_row[0])
                except (TypeError, ValueError):
                    current_version = 0
                if current_version >= 11:
                    # Feature 114 FR-M11.1: in-transaction re-check also
                    # verifies the schema state. Stamp without column =
                    # stub trap; fall through to body.
                    cols = {
                        r[1] for r in conn.execute(
                            "PRAGMA table_info(entities)"
                        ).fetchall()
                    }
                    if "workspace_uuid" in cols:
                        conn.rollback()
                        return
                    # else: stub trap, fall through
        except sqlite3.OperationalError as e:
            # Narrow catch — only the "_metadata table does not exist"
            # case is acceptable here; anything else (e.g., 'database is
            # locked') must propagate.
            if "no such table" not in str(e).lower():
                raise

        # ------------------------------------------------------------------
        # Step 4: pre-migration FK check (must be empty)
        # ------------------------------------------------------------------
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"pre-migration FK check non-empty: {fk_violations}"
            )

        # ------------------------------------------------------------------
        # Step 5: bootstrap workspaces table
        # ------------------------------------------------------------------
        conn.execute(_WORKSPACES_TABLE_DDL)
        conn.execute(_WORKSPACES_INDEX_DDL)

        now = datetime.now(timezone.utc).isoformat()
        for legacy_pid, new_uuid in mapping.items():
            # Pull project_root from projects (matched by project_id) when
            # available; default to NULL.
            proot_row = conn.execute(
                "SELECT project_root FROM projects WHERE project_id = ?",
                (legacy_pid,),
            ).fetchone()
            project_root = proot_row[0] if proot_row else None
            conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (new_uuid, legacy_pid, project_root, now, now),
            )

        # ------------------------------------------------------------------
        # Step 6: pre-migration parent_type_id orphan assertion
        # ------------------------------------------------------------------
        offender_row = conn.execute(
            "SELECT COUNT(*) AS n, GROUP_CONCAT(uuid) AS offenders "
            "FROM entities "
            "WHERE parent_uuid IS NULL AND parent_type_id IS NOT NULL"
        ).fetchone()
        n_off = offender_row[0]
        if n_off > 0:
            offenders = offender_row[1]
            raise RuntimeError(
                f"Migration 11 aborted: {n_off} parent_type_id-only "
                f"orphans: {offenders}"
            )

        # ------------------------------------------------------------------
        # Steps 7-8: build entities_new + JOIN backfill + DROP/RENAME
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE entities_new (
                uuid           TEXT NOT NULL PRIMARY KEY,
                workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid),
                type_id        TEXT NOT NULL,
                entity_type    TEXT NOT NULL,
                entity_id      TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_uuid    TEXT REFERENCES entities_new(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT,
                UNIQUE(workspace_uuid, type_id)
            )
        """)

        pre_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        conn.execute(
            "INSERT INTO entities_new "
            "(uuid, workspace_uuid, type_id, entity_type, entity_id, name, "
            "status, parent_uuid, artifact_path, created_at, updated_at, metadata) "
            "SELECT e.uuid, w.uuid, e.type_id, e.entity_type, e.entity_id, "
            "e.name, e.status, e.parent_uuid, e.artifact_path, "
            "e.created_at, e.updated_at, e.metadata "
            "FROM entities e "
            "JOIN workspaces w ON e.project_id = w.project_id_legacy"
        )
        post_count = conn.execute(
            "SELECT COUNT(*) FROM entities_new"
        ).fetchone()[0]
        if post_count != pre_count:
            raise RuntimeError(
                f"Migration 11 data copy mismatch: "
                f"entities pre={pre_count}, entities_new post={post_count}"
            )
        conn.execute("DROP TABLE entities")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("ALTER TABLE entities_new RENAME TO entities")

        # ------------------------------------------------------------------
        # Steps 9-10: recreate 7 triggers + 5 indexes on entities
        # ------------------------------------------------------------------
        # Drop legacy triggers that the rename did not carry over.
        conn.execute("DROP TRIGGER IF EXISTS enforce_no_self_parent")
        conn.execute("DROP TRIGGER IF EXISTS enforce_no_self_parent_update")
        conn.execute("DROP TRIGGER IF EXISTS enforce_immutable_project_id")

        conn.execute("""
            CREATE TRIGGER enforce_immutable_uuid
            BEFORE UPDATE OF uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END
        """)
        # enforce_immutable_type_id and enforce_immutable_entity_type
        # removed in migration 12 (feature 109 FR-3).
        conn.execute("""
            CREATE TRIGGER enforce_immutable_created_at
            BEFORE UPDATE OF created_at ON entities
            BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_immutable_workspace_uuid
            BEFORE UPDATE OF workspace_uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'workspace_uuid is immutable — use re-attribution API'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent_uuid_insert
            BEFORE INSERT ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_no_self_parent_uuid_update
            BEFORE UPDATE OF parent_uuid ON entities
            WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)

        # Drop legacy indexes (entities table rename carried them via
        # auto-recreation in some cases; explicit drop is idempotent).
        conn.execute("DROP INDEX IF EXISTS idx_project_id")
        conn.execute("DROP INDEX IF EXISTS idx_project_entity_type")
        conn.execute("DROP INDEX IF EXISTS idx_parent_type_id")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_type "
            "ON entities(entity_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON entities(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_uuid "
            "ON entities(parent_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_workspace_uuid ON entities(workspace_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_workspace_entity_type "
            "ON entities(workspace_uuid, entity_type)"
        )

        # ------------------------------------------------------------------
        # Step 11: workflow_phases.workspace_uuid ALTER + backfill + triggers
        # ------------------------------------------------------------------
        conn.execute(
            "ALTER TABLE workflow_phases ADD COLUMN workspace_uuid TEXT "
            "REFERENCES workspaces(uuid)"
        )
        conn.execute(
            "UPDATE workflow_phases SET workspace_uuid = ("
            "  SELECT e.workspace_uuid FROM entities e "
            "  WHERE e.type_id = workflow_phases.type_id"
            ")"
        )
        conn.execute(
            "CREATE INDEX idx_wp_workspace_uuid "
            "ON workflow_phases(workspace_uuid)"
        )
        # Two triggers form a complementary pair:
        # 1) AFTER INSERT: autofill from entities.workspace_uuid when
        #    NEW.workspace_uuid IS NULL AND a matching entity exists.
        # 2) BEFORE INSERT: ABORT when NEW.workspace_uuid IS NULL AND
        #    no matching entity exists (orphaned phase row).
        conn.execute("""
            CREATE TRIGGER wp_autofill_workspace_uuid
            AFTER INSERT ON workflow_phases
            WHEN NEW.workspace_uuid IS NULL
                 AND EXISTS (
                     SELECT 1 FROM entities e WHERE e.type_id = NEW.type_id
                 )
            BEGIN
                UPDATE workflow_phases
                SET workspace_uuid = (
                    SELECT e.workspace_uuid FROM entities e
                    WHERE e.type_id = NEW.type_id
                )
                WHERE rowid = NEW.rowid;
            END
        """)
        conn.execute("""
            CREATE TRIGGER wp_reject_orphaned_insert
            BEFORE INSERT ON workflow_phases
            WHEN NEW.workspace_uuid IS NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM entities e WHERE e.type_id = NEW.type_id
                 )
            BEGIN
                SELECT RAISE(ABORT, 'workflow_phases insert references unknown entity type_id (orphaned phase row); pass workspace_uuid explicitly or register the entity first');
            END
        """)

        # ------------------------------------------------------------------
        # Step 12: rebuild sequences keyed on workspace_uuid
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE sequences_new (
                workspace_uuid TEXT NOT NULL,
                entity_type    TEXT NOT NULL,
                next_val       INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (workspace_uuid, entity_type),
                FOREIGN KEY (workspace_uuid) REFERENCES workspaces(uuid)
            )
        """)
        conn.execute(
            "INSERT INTO sequences_new (workspace_uuid, entity_type, next_val) "
            "SELECT w.uuid, s.entity_type, s.next_val "
            "FROM sequences s "
            "JOIN workspaces w ON s.project_id = w.project_id_legacy"
        )
        conn.execute("DROP TABLE sequences")
        conn.execute("ALTER TABLE sequences_new RENAME TO sequences")

        # ------------------------------------------------------------------
        # Step 13: rebuild projects with workspace_uuid NOT NULL
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE projects_new (
                project_id      TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                root_commit_sha TEXT,
                remote_url      TEXT,
                normalized_url  TEXT,
                remote_host     TEXT,
                remote_owner    TEXT,
                remote_repo     TEXT,
                default_branch  TEXT,
                project_root    TEXT,
                is_git_repo     INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                workspace_uuid  TEXT NOT NULL REFERENCES workspaces(uuid)
            )
        """)
        conn.execute(
            "INSERT INTO projects_new "
            "(project_id, name, root_commit_sha, remote_url, normalized_url, "
            "remote_host, remote_owner, remote_repo, default_branch, "
            "project_root, is_git_repo, created_at, updated_at, workspace_uuid) "
            "SELECT p.project_id, p.name, p.root_commit_sha, p.remote_url, "
            "p.normalized_url, p.remote_host, p.remote_owner, p.remote_repo, "
            "p.default_branch, p.project_root, p.is_git_repo, "
            "p.created_at, p.updated_at, w.uuid "
            "FROM projects p "
            "JOIN workspaces w ON p.project_id = w.project_id_legacy"
        )
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_new RENAME TO projects")

        # ------------------------------------------------------------------
        # Step 14: rebuild entities_fts
        # ------------------------------------------------------------------
        conn.execute("DROP TABLE IF EXISTS entities_fts")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text)"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError("FTS5 extension not available") from exc
            raise
        rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in rows:
            metadata_text = flatten_metadata(
                json.loads(row[5]) if row[5] else None
            )
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
            )

        # ------------------------------------------------------------------
        # Step 15: stamp schema_version=11 INSIDE the transaction
        # ------------------------------------------------------------------
        # Replicates Migration 10's in-tx stamp pattern at
        # database.py:1604-1618. Eliminates the SIGKILL/OOM crash window
        # between migration body commit and outer-loop stamp commit.
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '11')"
        )

        # ------------------------------------------------------------------
        # Step 16: COMMIT
        # ------------------------------------------------------------------
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        # Re-enable FKs whether success or failure.
        conn.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------------------
    # Step 17: post-transaction FK check
    # ----------------------------------------------------------------------
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"Migration 11 post-FK check non-empty: {post_violations}"
        )


def _migration_11_workspace_identity_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 11. Restores exact pre-11 schema.

    Per spec FR-8 / design §7.2, this is a 16-step reverse migration packaged
    as a single transactional unit. Mirrors the forward envelope (PRAGMA OFF
    outside tx; BEGIN IMMEDIATE; in-tx schema_version=10 stamp; COMMIT;
    PRAGMA ON; post-FK check).

    Steps:
      0. Pre-tx: SQLite ≥ 3.35 assertion (DROP COLUMN requirement).
      1. PRAGMA foreign_keys = OFF.
      2. BEGIN IMMEDIATE; reverse re-check guard.
      3. Pre-down assertion (cross-workspace parent_uuid edges).
      4. Pre-migration FK check.
      5. Build entities_old (pre-11 schema).
      6. Restore project_id via JOIN on workspaces.project_id_legacy.
      7. Restore parent_type_id via parent_uuid → uuid → type_id JOIN.
      8. DROP entities; RENAME entities_old → entities.
      9. Recreate 9 pre-11 triggers + 6 pre-11 indexes.
     10. Reverse workflow_phases (drop triggers, drop index,
         DROP COLUMN workspace_uuid).
     11. Reverse sequences (rebuild keyed on project_id).
     12. Reverse projects (drop workspace_uuid column).
     13. Rebuild entities_fts.
     14. DROP workspaces table + idx_workspaces_legacy.
     15. UPDATE _metadata SET schema_version='10' INSIDE tx.
     16. COMMIT; PRAGMA foreign_keys = ON; post-FK check.

    Raises:
        AssertionError: SQLite < 3.35.0 (DROP COLUMN unavailable).
        RuntimeError: cross-workspace parent_uuid edges; FK violations.
    """
    # ----------------------------------------------------------------------
    # Step 0: SQLite version assertion (defense in depth)
    # ----------------------------------------------------------------------
    # ALTER TABLE DROP COLUMN was added in SQLite 3.35.0 (March 2021). The
    # workflow_phases.workspace_uuid drop in step 10 requires it. Python 3.12+
    # ships sqlite >= 3.43, so this is documentation/safety more than a real
    # gate.
    assert sqlite3.sqlite_version_info >= (3, 35, 0), (
        "Migration 11 reverse requires SQLite 3.35+ for "
        "ALTER TABLE DROP COLUMN; current version: "
        f"{sqlite3.sqlite_version}"
    )

    # ----------------------------------------------------------------------
    # Step 1: PRAGMA foreign_keys = OFF (outside transaction)
    # ----------------------------------------------------------------------
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 11 reverse"
        )

    try:
        # ------------------------------------------------------------------
        # Step 2: BEGIN IMMEDIATE; reverse re-check guard
        # ------------------------------------------------------------------
        conn.execute("BEGIN IMMEDIATE")
        # Reverse re-check guard: if schema_version is already <= 10,
        # someone (or another process) already applied the reverse — no-op.
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise RuntimeError(
                "Migration 11 reverse: _metadata.schema_version missing"
            )
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Migration 11 reverse: invalid schema_version {v_row[0]!r}"
            ) from exc
        if current_version <= 10:
            conn.rollback()
            return

        # ------------------------------------------------------------------
        # Step 3: Pre-down assertion — cross-workspace parent_uuid edges
        # ------------------------------------------------------------------
        # Cross-workspace parent_uuid references cannot be reversed losslessly
        # into pre-11 parent_type_id text format (text references are
        # workspace-scoped via the old UNIQUE(project_id, type_id)). Abort if
        # any such edges exist.
        cross_n = conn.execute(
            "SELECT COUNT(*) FROM entities e WHERE EXISTS ("
            "  SELECT 1 FROM entities p "
            "  WHERE p.uuid = e.parent_uuid "
            "    AND p.workspace_uuid != e.workspace_uuid"
            ")"
        ).fetchone()[0]
        if cross_n > 0:
            raise RuntimeError(
                f"Cannot reverse Migration 11: {cross_n} cross-workspace "
                "parent_uuid edges exist; operator must prune them before "
                "reversing"
            )

        # ------------------------------------------------------------------
        # Step 4: pre-migration FK check
        # ------------------------------------------------------------------
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"Migration 11 reverse pre-FK check non-empty: "
                f"{fk_violations}"
            )

        # ------------------------------------------------------------------
        # Pre-step 5: drop triggers that reference `entities` so that the
        # subsequent DROP TABLE entities does not fire them.
        # ------------------------------------------------------------------
        # The wp_autofill_workspace_uuid + wp_reject_orphaned_insert pair
        # references entities via subqueries in their WHEN clauses; SQLite
        # otherwise re-evaluates them during the rebuild. We will recreate
        # the workflow_phases-side cleanup in step 10.
        conn.execute("DROP TRIGGER IF EXISTS wp_autofill_workspace_uuid")
        conn.execute("DROP TRIGGER IF EXISTS wp_reject_orphaned_insert")

        # ------------------------------------------------------------------
        # Step 5: Build entities_old (pre-11 schema)
        # ------------------------------------------------------------------
        # Mirrors the post-Migration-8 entities table layout exactly:
        # 13 columns, project_id NOT NULL DEFAULT '__unknown__',
        # parent_type_id, parent_uuid (FK to self), UNIQUE(project_id, type_id).
        conn.execute("""
            CREATE TABLE entities_old (
                uuid           TEXT NOT NULL PRIMARY KEY,
                type_id        TEXT NOT NULL,
                project_id     TEXT NOT NULL DEFAULT '__unknown__',
                entity_type    TEXT NOT NULL,
                entity_id      TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_type_id TEXT,
                parent_uuid    TEXT REFERENCES entities_old(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT,
                UNIQUE(project_id, type_id)
            )
        """)

        # ------------------------------------------------------------------
        # Step 6: Restore project_id via JOIN on workspaces.project_id_legacy
        # ------------------------------------------------------------------
        pre_count = conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO entities_old "
            "(uuid, type_id, project_id, entity_type, entity_id, name, "
            "status, parent_type_id, parent_uuid, artifact_path, "
            "created_at, updated_at, metadata) "
            "SELECT e.uuid, e.type_id, w.project_id_legacy, e.entity_type, "
            "e.entity_id, e.name, e.status, NULL, e.parent_uuid, "
            "e.artifact_path, e.created_at, e.updated_at, e.metadata "
            "FROM entities e "
            "JOIN workspaces w ON e.workspace_uuid = w.uuid"
        )
        post_count = conn.execute(
            "SELECT COUNT(*) FROM entities_old"
        ).fetchone()[0]
        if post_count != pre_count:
            raise RuntimeError(
                f"Migration 11 reverse data copy mismatch: "
                f"entities pre={pre_count}, entities_old post={post_count}"
            )

        # ------------------------------------------------------------------
        # Step 7: Restore parent_type_id via parent_uuid → uuid → type_id JOIN
        # ------------------------------------------------------------------
        conn.execute(
            "UPDATE entities_old SET parent_type_id = ("
            "  SELECT type_id FROM entities_old AS p "
            "  WHERE p.uuid = entities_old.parent_uuid"
            ") WHERE parent_uuid IS NOT NULL"
        )

        # ------------------------------------------------------------------
        # Step 8: DROP entities; RENAME entities_old → entities
        # ------------------------------------------------------------------
        conn.execute("DROP TABLE entities")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute("ALTER TABLE entities_old RENAME TO entities")

        # ------------------------------------------------------------------
        # Step 9: Recreate 9 pre-11 triggers + 6 pre-11 indexes
        # ------------------------------------------------------------------
        # Drop any post-11 triggers that the rename did not carry over.
        conn.execute("DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid")
        conn.execute("DROP TRIGGER IF EXISTS enforce_no_self_parent_uuid_insert")
        conn.execute("DROP TRIGGER IF EXISTS enforce_no_self_parent_uuid_update")

        # 9 pre-11 triggers (mirrors post-Migration-8 trigger set):
        # enforce_immutable_type_id and enforce_immutable_entity_type
        # removed in migration 12 (feature 109 FR-3). Per design TD-9,
        # the down-migration does NOT restore them in source (only the
        # runtime DROP TRIGGER guards in migration 12 are inverted).
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
            BEFORE UPDATE OF created_at ON entities
            BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_uuid
            BEFORE UPDATE OF uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_project_id
            BEFORE UPDATE OF project_id ON entities
            BEGIN SELECT RAISE(ABORT, 'project_id is immutable — use re-attribution API'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
            BEFORE INSERT ON entities
            WHEN NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
            BEFORE UPDATE OF parent_type_id ON entities
            WHEN NEW.parent_type_id = NEW.type_id
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_insert
            BEFORE INSERT ON entities
            WHEN NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_update
            BEFORE UPDATE OF parent_uuid ON entities
            WHEN NEW.parent_uuid = NEW.uuid
            BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END
        """)

        # Drop post-11 indexes (rename may or may not have carried them).
        conn.execute("DROP INDEX IF EXISTS idx_workspace_uuid")
        conn.execute("DROP INDEX IF EXISTS idx_workspace_entity_type")

        # 6 pre-11 indexes:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_type "
            "ON entities(entity_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON entities(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_type_id "
            "ON entities(parent_type_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent_uuid "
            "ON entities(parent_uuid)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_id "
            "ON entities(project_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_entity_type "
            "ON entities(project_id, entity_type)"
        )

        # ------------------------------------------------------------------
        # Step 10: Reverse workflow_phases (drop idx + column)
        # ------------------------------------------------------------------
        # Triggers were dropped pre-step 5 because they reference entities.
        conn.execute("DROP INDEX IF EXISTS idx_wp_workspace_uuid")
        conn.execute(
            "ALTER TABLE workflow_phases DROP COLUMN workspace_uuid"
        )

        # ------------------------------------------------------------------
        # Step 11: Reverse sequences (rebuild keyed on project_id)
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE sequences_old (
                project_id  TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                next_val    INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (project_id, entity_type)
            )
        """)
        conn.execute(
            "INSERT INTO sequences_old (project_id, entity_type, next_val) "
            "SELECT w.project_id_legacy, s.entity_type, s.next_val "
            "FROM sequences s "
            "JOIN workspaces w ON s.workspace_uuid = w.uuid"
        )
        conn.execute("DROP TABLE sequences")
        conn.execute("ALTER TABLE sequences_old RENAME TO sequences")

        # ------------------------------------------------------------------
        # Step 12: Reverse projects (drop workspace_uuid column)
        # ------------------------------------------------------------------
        # Rebuild without workspace_uuid (mirror of forward step 13).
        conn.execute("""
            CREATE TABLE projects_old (
                project_id      TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                root_commit_sha TEXT,
                remote_url      TEXT,
                normalized_url  TEXT,
                remote_host     TEXT,
                remote_owner    TEXT,
                remote_repo     TEXT,
                default_branch  TEXT,
                project_root    TEXT,
                is_git_repo     INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO projects_old "
            "(project_id, name, root_commit_sha, remote_url, normalized_url, "
            "remote_host, remote_owner, remote_repo, default_branch, "
            "project_root, is_git_repo, created_at, updated_at) "
            "SELECT project_id, name, root_commit_sha, remote_url, "
            "normalized_url, remote_host, remote_owner, remote_repo, "
            "default_branch, project_root, is_git_repo, created_at, updated_at "
            "FROM projects"
        )
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_old RENAME TO projects")

        # ------------------------------------------------------------------
        # Step 13: Rebuild entities_fts (mirror of forward step 14)
        # ------------------------------------------------------------------
        conn.execute("DROP TABLE IF EXISTS entities_fts")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text)"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError("FTS5 extension not available") from exc
            raise
        rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in rows:
            metadata_text = flatten_metadata(
                json.loads(row[5]) if row[5] else None
            )
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, "
                "entity_type, status, metadata_text) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
            )

        # ------------------------------------------------------------------
        # Step 14: DROP workspaces + idx_workspaces_legacy
        # ------------------------------------------------------------------
        conn.execute("DROP INDEX IF EXISTS idx_workspaces_legacy")
        conn.execute("DROP TABLE workspaces")

        # ------------------------------------------------------------------
        # Step 15: stamp schema_version=10 INSIDE the transaction
        # ------------------------------------------------------------------
        # Mirrors forward Migration 11 step 15 + Migration 10's pattern at
        # database.py:1604-1618.
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '10')"
        )

        # ------------------------------------------------------------------
        # Step 16: COMMIT
        # ------------------------------------------------------------------
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        # Re-enable FKs whether success or failure.
        conn.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------------------
    # Post-transaction FK check
    # ----------------------------------------------------------------------
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"Migration 11 reverse post-FK check non-empty: "
            f"{post_violations}"
        )


def _migration_12_polymorphic_taxonomy_and_events(
    conn: sqlite3.Connection,
) -> None:
    """Migration 12: polymorphic taxonomy (F11) + event-sourced state (F2/F3/F12).

    **Stub body — Feature 109 Group 0 (Task 0.2).** This stub establishes the
    transaction envelope, idempotency guard, concurrent re-check, pre-/post-flight
    FK checks, and ``schema_version=12`` stamp. The actual schema changes
    (type/kind/lifecycle_class columns, phase_events CHECK expansion, trigger
    drops, ``upsert_entity`` / ``promote_entity`` API additions) are filled in
    by subsequent Groups 1-11 of feature 109.

    Skeleton mirrors :func:`_migration_11_workspace_identity` exactly:
      - Pre-step: idempotency early-return (read schema_version >= 12 → return).
      - Step 1: ``PRAGMA foreign_keys = OFF`` outside try, verify it took effect.
      - Step 2: ``BEGIN IMMEDIATE`` inside try.
      - Step 3: concurrent re-check guard (re-read schema_version in tx).
      - Step 4: pre-migration ``PRAGMA foreign_key_check`` (raise on violations).
      - Step 5: (RESERVED for body — currently empty.)
      - Step N-2: in-transaction post-flight ``PRAGMA foreign_key_check``
        immediately before stamping schema_version=12 (critical safety from
        commit 0.2 onwards — guards against any future body addition that
        creates FK violations).
      - Step N-1: stamp ``schema_version=12`` INSIDE the transaction.
      - Step N: COMMIT.
      - except → ROLLBACK + raise.
      - finally → ``PRAGMA foreign_keys = ON``.
      - Post-commit: defensive post-flight ``PRAGMA foreign_key_check`` outside
        the transaction.

    Raises:
        RuntimeError on FK violations (pre, in-transaction, or post) or
        any in-transaction failure.
    """
    # ----------------------------------------------------------------------
    # Pre-step 0: outer-level idempotency early-return guard.
    # ----------------------------------------------------------------------
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is not None:
            try:
                current_version = int(v_row[0])
            except (TypeError, ValueError):
                current_version = 0
            if current_version >= 12:
                # Feature 114 FR-A.1: verify schema state matches stamp before
                # trusting it. Pre-114, this guard only checked the stamp,
                # creating the M12 stub trap when the stamp was applied without
                # the body running (commit 6722191a window).
                try:
                    cols = {
                        r[1] for r in conn.execute(
                            "PRAGMA table_info(entities)"
                        ).fetchall()
                    }
                    if (
                        "type" in cols
                        and "kind" in cols
                        and "lifecycle_class" in cols
                        and "entity_type" not in cols
                    ):
                        return  # genuine post-M12 state
                    # Stamp present but body never ran (stub trap) — fall
                    # through and execute the M12 body. The body's own
                    # idempotency around individual ALTER TABLE / CREATE
                    # TABLE statements handles re-execution safely.
                except sqlite3.OperationalError:
                    # entities table missing — falls through to body which
                    # will fail-fast with a clearer error.
                    pass
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            raise

    # ----------------------------------------------------------------------
    # Step 1: PRAGMA foreign_keys = OFF (outside transaction)
    # ----------------------------------------------------------------------
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 12"
        )

    try:
        # ------------------------------------------------------------------
        # Step 2: BEGIN IMMEDIATE
        # ------------------------------------------------------------------
        conn.execute("BEGIN IMMEDIATE")

        # ------------------------------------------------------------------
        # Step 3: concurrent re-check guard
        # ------------------------------------------------------------------
        try:
            v_row = conn.execute(
                "SELECT value FROM _metadata WHERE key='schema_version'"
            ).fetchone()
            if v_row is not None:
                try:
                    current_version = int(v_row[0])
                except (TypeError, ValueError):
                    current_version = 0
                if current_version >= 12:
                    # Feature 114 FR-A.1: in-transaction re-check also
                    # verifies the schema state, not just the stamp. If
                    # stamp says 12 but schema is pre-M12 (stub trap),
                    # fall through and execute the body.
                    cols = {
                        r[1] for r in conn.execute(
                            "PRAGMA table_info(entities)"
                        ).fetchall()
                    }
                    if (
                        "type" in cols
                        and "kind" in cols
                        and "lifecycle_class" in cols
                        and "entity_type" not in cols
                    ):
                        conn.rollback()
                        return  # genuine post-M12 state, concurrent run won
                    # else: stub trap detected, fall through to body
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e).lower():
                raise

        # ------------------------------------------------------------------
        # Step 4: pre-migration FK check (must be empty)
        # ------------------------------------------------------------------
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise RuntimeError(
                f"Migration 12 pre-FK check non-empty: {fk_violations}"
            )

        # ------------------------------------------------------------------
        # Step 5a: Pre-flight collision audit (Group 1, Task 1.2, AC-1.10)
        # ------------------------------------------------------------------
        # Detect (workspace_uuid, numeric suffix) collisions between backlog
        # and feature entities. Non-blocking — emit one INFO line per
        # collision to stderr so operators see them up-front; AC-3.6 raises
        # ``PromotionConflictError`` at promotion time for the same case.
        collision_rows = conn.execute(
            "SELECT workspace_uuid, "
            "SUBSTR(type_id, INSTR(type_id, ':') + 1) AS suffix "
            "FROM entities WHERE type_id LIKE 'backlog:%' "
            "INTERSECT "
            "SELECT workspace_uuid, "
            "SUBSTR(type_id, INSTR(type_id, ':') + 1) AS suffix "
            "FROM entities WHERE type_id LIKE 'feature:%'"
        ).fetchall()
        for row in collision_rows:
            ws = row[0]
            suffix = row[1]
            print(
                f"INFO: Migration 12 pre-flight collision: "
                f"workspace={ws}, suffix={suffix}",
                file=sys.stderr,
            )

        # ------------------------------------------------------------------
        # Step 5b: AC-5.3 pre-migration cleanup (Group 1, Task 1.4)
        # ------------------------------------------------------------------
        # Remove the known malformed ``workflow_phases`` row whose type_id is
        # the literal string 'feature:' (empty after colon — observed in
        # the live DB on 2026-05-12). Detection runs first so we can emit a
        # single audit log entry; the DELETE is unconditional but a no-op
        # when no malformed row exists.
        malformed_count = conn.execute(
            "SELECT COUNT(*) FROM workflow_phases WHERE type_id = 'feature:'"
        ).fetchone()[0]
        if malformed_count > 0:
            print(
                f"INFO: Migration 12 removed malformed workflow_phases row: "
                f"feature: (count={malformed_count})",
                file=sys.stderr,
            )
        conn.execute(
            "DELETE FROM workflow_phases WHERE type_id = 'feature:'"
        )

        # ------------------------------------------------------------------
        # Step 5c: F11 column additions (Group 2, Task 2.3)
        # ------------------------------------------------------------------
        # Add ``type``, ``kind``, ``lifecycle_class`` columns to ``entities``
        # with placeholder NOT NULL DEFAULTs. Defaults are corrected by the
        # backfill UPDATEs in step 5d. The composite CHECK constraint is
        # added later by Group 3's copy-rename.
        #
        # Concurrent-runner safety: SQLite has no ``ADD COLUMN IF NOT
        # EXISTS``. Under WAL-mode concurrent migration (multiple processes
        # racing v11→v12 init), the in-tx re-check above can miss a freshly
        # committed peer because the read snapshot is established at
        # BEGIN IMMEDIATE acquisition. We additionally guard each ALTER by
        # introspecting ``PRAGMA table_info(entities)`` so a losing-racer
        # skips the column add idempotently. The cross-process safety is
        # otherwise unchanged — only one writer can hold the lock at a
        # time; the loser just no-ops its body.
        existing_cols = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        }
        if "type" not in existing_cols:
            conn.execute(
                "ALTER TABLE entities ADD COLUMN type TEXT NOT NULL "
                "DEFAULT 'work'"
            )
        if "kind" not in existing_cols:
            conn.execute(
                "ALTER TABLE entities ADD COLUMN kind TEXT NOT NULL "
                "DEFAULT 'feature'"
            )
        if "lifecycle_class" not in existing_cols:
            conn.execute(
                "ALTER TABLE entities ADD COLUMN lifecycle_class TEXT "
                "NOT NULL DEFAULT 'feature_flow'"
            )

        # ------------------------------------------------------------------
        # Step 5d: F11 backfill UPDATEs (Group 2, Task 2.4)
        # ------------------------------------------------------------------
        # Map the 4 production ``entity_type`` values plus the (unused at
        # v11 but defined for forward compat) ``workspace`` value onto
        # (type, kind, lifecycle_class) per spec FR-1 mapping table.
        #
        # Concurrent-runner safety: Group 7 drops ``entity_type`` later in
        # this same migration body. A racing peer process may have already
        # completed migration 12 (column dropped, schema_version=12
        # stamped) while this process was waiting on BEGIN IMMEDIATE.
        # When that happens, the re-check guard above SHOULD short-circuit
        # — but the BEGIN IMMEDIATE snapshot can predate the peer commit.
        # Guard each entity_type read by introspecting the column list at
        # runtime; skip the backfill when the column is already gone.
        backfill_cols = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        }
        entity_type_present = "entity_type" in backfill_cols

        if entity_type_present:
            conn.execute(
                "UPDATE entities SET type='work', kind='feature', "
                "lifecycle_class='feature_flow' WHERE entity_type='feature'"
            )
            conn.execute(
                "UPDATE entities SET type='work', kind='backlog', "
                "lifecycle_class='work_flow' WHERE entity_type='backlog'"
            )
            conn.execute(
                "UPDATE entities SET type='brainstorm', kind='brainstorm', "
                "lifecycle_class='brainstorm_flow' WHERE entity_type='brainstorm'"
            )
            conn.execute(
                "UPDATE entities SET type='container', kind='project', "
                "lifecycle_class='container_flow' WHERE entity_type='project'"
            )
            conn.execute(
                "UPDATE entities SET type='workspace', kind='workspace', "
                "lifecycle_class='none' WHERE entity_type='workspace'"
            )

            # ------------------------------------------------------------------
            # Step 5e: Defensive abort on unmapped entity_type rows (Task 2.5)
            # ------------------------------------------------------------------
            # If any row has an ``entity_type`` that the 5 UPDATEs above did not
            # cover (e.g. a stray value like 'unknown' that bypassed
            # register_entity validation), abort the migration loudly so the
            # operator can investigate.
            #
            # Note on implementation: the original spec wording proposed
            # ``WHERE type IS NULL`` — but the ALTER TABLE statements above
            # populate ``type`` for existing rows from the NOT NULL DEFAULT,
            # so that predicate never fires. Detecting an unmapped row requires
            # a direct check against the mapping enum, which is what the
            # backfill UPDATEs use. The set of mapped ``entity_type`` values is
            # fixed by FR-1; rows outside that set are the anomaly.
            unmapped = conn.execute(
                "SELECT COUNT(*) FROM entities WHERE entity_type NOT IN "
                "('feature','backlog','brainstorm','project','workspace')"
            ).fetchone()[0]
            if unmapped > 0:
                raise RuntimeError(
                    f"Migration 12: unmapped entity_type rows: {unmapped}"
                )

        # ------------------------------------------------------------------
        # Step 5f: F11 composite CHECK via copy-rename + consolidated
        #          immutable-trigger removal (Group 3, Tasks 3.2-3.4 +
        #          consolidated FR-3 trigger drops; Group 4, Task 4.2
        #          adds idx_entities_type_kind).
        # ------------------------------------------------------------------
        # SQLite cannot ALTER TABLE to add a CHECK constraint, so we
        # rebuild ``entities`` with the composite (type, kind) clause via
        # the documented copy-rename pattern
        # (https://www.sqlite.org/lang_altertable.html § 8). This is the
        # same idiom used by ``_expand_workflow_phase_check`` (migration 5
        # at database.py:464-577).
        #
        # Per design §1 sub-step 5 the rebuild is dynamic: column list,
        # indexes, and triggers are discovered from sqlite_master so the
        # block is resilient to silent schema drift (e.g. a future column
        # added by feature 108 that this design did not anticipate).
        # The immutable triggers ``enforce_immutable_entity_type`` and
        # ``enforce_immutable_type_id`` are intentionally OMITTED from
        # the trigger-recreation loop — FR-3 drops them at all 12 source
        # sites; this block ensures the runtime trigger registry matches.
        #
        # Idempotency: if the rebuild already ran (e.g. a previous
        # interrupted v12 attempt left ``idx_entities_type_kind`` behind
        # but stamped no version), the CHECK is already in place. We
        # detect that by probing ``sqlite_master`` for the index name —
        # the index is created at the END of this block so its presence
        # implies the block completed previously.
        idx_already = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='index' AND name='idx_entities_type_kind'"
        ).fetchone()
        if idx_already is None:
            # Capture pre-rebuild column metadata so we can build a
            # dynamic INSERT-SELECT column list. (cid, name, type,
            # notnull, dflt_value, pk) per the SQLite PRAGMA contract.
            entities_cols = conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
            col_names = [c[1] for c in entities_cols]
            # Capture pre-rebuild row count for parity check.
            pre_count = conn.execute(
                "SELECT COUNT(*) FROM entities"
            ).fetchone()[0]
            # Capture user-defined indexes (auto-indexes from PRIMARY KEY
            # / UNIQUE will be re-generated automatically by SQLite when
            # the new table is created).
            saved_indexes = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='entities' "
                    "AND sql IS NOT NULL"
                ).fetchall()
            ]
            # Capture triggers, excluding the 2 immutable triggers that
            # FR-3 drops (defense in depth — at this point they should
            # already be absent from sqlite_master because Group-3
            # source-level removal ran before make_v11_db built the
            # baseline; but tests may inject them, so filter explicitly).
            saved_triggers = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' AND tbl_name='entities' "
                    "AND sql IS NOT NULL "
                    "AND name NOT IN ("
                    "'enforce_immutable_entity_type', "
                    "'enforce_immutable_type_id')"
                ).fetchall()
            ]

            # Capture cross-table triggers that reference ``entities`` so
            # we can re-create them after the rebuild. Migration 11 added
            # ``wp_autofill_workspace_uuid`` and ``wp_reject_orphaned_insert``
            # on ``workflow_phases`` whose bodies do
            # ``SELECT ... FROM entities``; the SQLite RENAME-table
            # validator scans every trigger SQL and aborts if any
            # reference resolves to a missing table during the swap
            # (intermediate state: old ``entities`` dropped, ``entities_new``
            # not yet renamed). Drop them now; recreate after RENAME.
            cross_triggers = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' "
                    "AND tbl_name <> 'entities' "
                    "AND sql LIKE '%entities%' "
                    "AND sql IS NOT NULL"
                ).fetchall()
            ]
            for trg_name, _ in cross_triggers:
                conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

            # Build entities_new with the composite CHECK constraint.
            # The column list mirrors the v11 schema (preserved as-is —
            # ``entity_type`` is dropped later by Group 7, NOT here) so
            # the new table is a strict superset of the constraint set:
            # original PRIMARY KEY, UNIQUE(workspace_uuid, type_id), FK
            # to workspaces, plus the new composite CHECK on (type, kind).
            conn.execute("""
                CREATE TABLE entities_new (
                    uuid           TEXT NOT NULL PRIMARY KEY,
                    workspace_uuid TEXT NOT NULL
                                   REFERENCES workspaces(uuid),
                    type_id        TEXT NOT NULL,
                    entity_type    TEXT NOT NULL,
                    entity_id      TEXT NOT NULL,
                    name           TEXT NOT NULL,
                    status         TEXT,
                    parent_uuid    TEXT REFERENCES entities_new(uuid),
                    artifact_path  TEXT,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL,
                    metadata       TEXT,
                    type           TEXT NOT NULL DEFAULT 'work',
                    kind           TEXT NOT NULL DEFAULT 'feature',
                    lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow',
                    UNIQUE(workspace_uuid, type_id),
                    CHECK (
                        (type='workspace' AND kind='workspace') OR
                        (type='brainstorm' AND kind='brainstorm') OR
                        (type='container' AND kind='project') OR
                        (type='work' AND kind IN (
                            'feature','backlog',
                            -- 5D kinds (initiative/objective/key_result/
                            -- task) have 0 production rows per spec §1
                            -- but VALID_ENTITY_TYPES retains them for
                            -- forward compat (OKR alignment test
                            -- fixtures, future feature 111 issue_spawn).
                            -- Permit them under type='work' so
                            -- register_entity callers using these
                            -- legacy kinds satisfy the CHECK; feature
                            -- 111 narrows this when bug/task get
                            -- first-class CHECK pairs.
                            'initiative','objective','key_result','task'
                        ))
                    )
                )
            """)
            # Defensive: confirm the discovered column set is a subset
            # of the new table's columns (otherwise the INSERT-SELECT
            # would lose data). The new table's columns are the v11
            # set + the 3 polymorphic columns; any column outside that
            # set is unexpected (probably an in-flight migration race).
            new_cols = {
                r[1] for r in conn.execute(
                    "PRAGMA table_info(entities_new)"
                ).fetchall()
            }
            unknown_cols = [c for c in col_names if c not in new_cols]
            if unknown_cols:
                raise RuntimeError(
                    f"Migration 12 copy-rename: unexpected columns in "
                    f"existing entities table not present in entities_new: "
                    f"{unknown_cols!r}"
                )
            # Build dynamic INSERT-SELECT: copy all old columns by name.
            col_list_sql = ",".join(col_names)
            conn.execute(
                f"INSERT INTO entities_new ({col_list_sql}) "
                f"SELECT {col_list_sql} FROM entities"
            )
            post_count = conn.execute(
                "SELECT COUNT(*) FROM entities_new"
            ).fetchone()[0]
            if post_count != pre_count:
                raise RuntimeError(
                    f"Migration 12 copy-rename row-count mismatch: "
                    f"pre={pre_count}, post={post_count}"
                )

            # Swap tables.
            conn.execute("DROP TABLE entities")
            conn.execute("PRAGMA legacy_alter_table = OFF")
            conn.execute("ALTER TABLE entities_new RENAME TO entities")

            # Recreate captured user-defined indexes verbatim from the
            # stored ``sql`` text. SQLite stores CREATE INDEX statements
            # without trailing semicolons; ``CREATE INDEX IF NOT EXISTS``
            # variants (if any) are preserved as-stored.
            for idx_name, idx_sql in saved_indexes:
                if idx_sql:
                    conn.execute(idx_sql)

            # Recreate captured triggers (immutable triggers already
            # filtered out by the SELECT above).
            for trg_name, trg_sql in saved_triggers:
                if trg_sql:
                    conn.execute(trg_sql)

            # Group 4 / Task 4.2: composite index for polymorphic
            # queries (AC-1.6).
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entities_type_kind "
                "ON entities(type, kind)"
            )

            # Recreate cross-table triggers we temporarily dropped to
            # allow the entities-table rename. The captured SQL still
            # references the table name ``entities`` which is now the
            # renamed table.
            for _, trg_sql in cross_triggers:
                if trg_sql:
                    conn.execute(trg_sql)

            # Defensive runtime DROP TRIGGER guards (FR-3 / Task 3.8):
            # idempotent removal of any orphan immutable trigger that
            # might survive the rebuild (e.g. via a CREATE TRIGGER ...
            # IF NOT EXISTS reissued by a concurrent process between
            # the BEGIN IMMEDIATE acquisition and the table rebuild).
            conn.execute(
                "DROP TRIGGER IF EXISTS enforce_immutable_entity_type"
            )
            conn.execute(
                "DROP TRIGGER IF EXISTS enforce_immutable_type_id"
            )

        # ------------------------------------------------------------------
        # Step 5g: F11 FTS5 virtual-table rebuild (Group 5, Tasks 5.3 + 5.4)
        # ------------------------------------------------------------------
        # AC-1.8 / design §1 sub-step 6 + TD-7: the FTS5 search column
        # changes from ``entity_type`` to ``kind``. Migration 4's
        # ``_create_fts_index`` and migration 7's ``_fix_fts_content_mode``
        # produced the v11-shape table whose column list includes
        # ``entity_type``; that table is also potentially out-of-sync with
        # the entities table because Group 3's copy-rename above rebuilt
        # ``entities`` (its rowids may not match the FTS5 rowids if they
        # were assigned by external-content linkage, though the v11
        # standalone form decouples them).
        #
        # Steps:
        #   1. DROP existing entities_fts (stale post-Group-3 rebuild).
        #   2. CREATE the new virtual table with ``kind`` replacing
        #      ``entity_type``. The full column list is discovered
        #      dynamically from sqlite_master rather than hard-coded,
        #      per design TD-7 (resilience to silent column drift in
        #      historical FTS5 definitions).
        #   3. Python backfill loop: enumerate rows from the rebuilt
        #      ``entities`` table and INSERT each into entities_fts with
        #      ``kind`` populated from ``entities.kind`` (which Group 2
        #      backfilled from ``entity_type``). Pre-Group-11
        #      ``register_entity`` still writes ``entity_type``-only and
        #      does NOT yet populate ``kind`` on insert; for migration-12
        #      this is moot because the backfill UPDATEs in step 5d
        #      already populated ``kind`` for all existing rows.
        #
        # Idempotency: probe sqlite_master for entities_fts whose CREATE
        # SQL contains ``kind`` (the new column) and does NOT reference
        # ``entity_type`` (the old column). If matched, the block already
        # ran in a prior interrupted v12 attempt — skip the rebuild.
        fts_existing = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='entities_fts'"
        ).fetchone()
        fts_already_v12 = (
            fts_existing is not None
            and fts_existing[0] is not None
            and "kind" in fts_existing[0]
            and "entity_type" not in fts_existing[0]
        )
        if not fts_already_v12:
            # Capture cross-table triggers that reference ``entities_fts``
            # so we can re-create them after the rebuild — same safeguard
            # the entities copy-rename above uses for cross-table triggers
            # referencing ``entities``. None are known to exist at v11 but
            # the discovery is cheap and future-proofs the migration.
            fts_cross_triggers = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' "
                    "AND tbl_name <> 'entities_fts' "
                    "AND sql LIKE '%entities_fts%' "
                    "AND sql IS NOT NULL"
                ).fetchall()
            ]
            for trg_name, _ in fts_cross_triggers:
                conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

            # Step 1: drop the stale v11-shape table.
            conn.execute("DROP TABLE IF EXISTS entities_fts")

            # Step 2: create the new virtual table. The column list is
            # the v11 standalone shape (per migration 7's
            # ``_fix_fts_content_mode``) with ``entity_type`` replaced by
            # ``kind``. The historical column list at the most recent
            # production CREATE (migration 11 step 14 at
            # database.py:2113-2116) reads:
            #   name, entity_id, entity_type, status, metadata_text
            # We substitute entity_type → kind, keeping the rest stable.
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE entities_fts USING fts5("
                    "name, entity_id, kind, status, metadata_text)"
                )
            except sqlite3.OperationalError as exc:
                if "no such module: fts5" in str(exc):
                    raise RuntimeError(
                        "FTS5 extension not available — "
                        "cannot complete migration 12 FTS5 rebuild"
                    ) from exc
                raise

            # Step 3: Python backfill loop. Read each entities row and
            # INSERT into the new entities_fts using ``kind`` (backfilled
            # by step 5d) in place of the legacy entity_type slot.
            rows = conn.execute(
                "SELECT rowid, name, entity_id, kind, status, metadata "
                "FROM entities"
            ).fetchall()
            for row in rows:
                metadata_text = flatten_metadata(
                    json.loads(row[5]) if row[5] else None
                )
                conn.execute(
                    "INSERT INTO entities_fts ("
                    "rowid, name, entity_id, kind, status, metadata_text"
                    ") VALUES (?, ?, ?, ?, ?, ?)",
                    (row[0], row[1], row[2], row[3], row[4] or "",
                     metadata_text),
                )

            # Recreate any cross-table triggers we dropped above.
            for _, trg_sql in fts_cross_triggers:
                if trg_sql:
                    conn.execute(trg_sql)

        # ------------------------------------------------------------------
        # Step 5h: F11 DROP COLUMN entity_type (Group 7, Task 7.3)
        # ------------------------------------------------------------------
        # AC-1.4: after the FTS5 rebuild (step 5g) has switched the search
        # column from ``entity_type`` to ``kind``, the legacy
        # ``entity_type`` column on ``entities`` is no longer needed —
        # production readers (Group 6) now consult ``kind`` instead.
        # Drop the column to enforce the cut-over at the schema level.
        #
        # SQLite 3.35.0+ supports native ``ALTER TABLE ... DROP COLUMN``.
        # Older SQLite falls back to a copy-rename block. The check is
        # performed at runtime against ``sqlite3.sqlite_version`` (the
        # bundled engine version, not the Python ``sqlite3`` module
        # version).
        #
        # Idempotency: probe ``PRAGMA table_info(entities)`` for the
        # ``entity_type`` column — skip the DROP if already absent (e.g.
        # a prior interrupted migration completed step 5h but failed
        # before stamping schema_version=12).
        entities_cols_post = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        }
        if "entity_type" in entities_cols_post:
            # Drop ``idx_entity_type`` first if present — SQLite refuses
            # to DROP COLUMN if any index references the column, and the
            # fallback CREATE TABLE block would also need this gone.
            conn.execute(
                "DROP INDEX IF EXISTS idx_entity_type"
            )
            # ``idx_workspace_entity_type`` (created by migration 11
            # step 6) is a compound index spanning workspace_uuid +
            # entity_type. SQLite refuses native DROP COLUMN while it
            # exists. Drop it; if a compound index over the surviving
            # columns is needed, that's spec FR-1's
            # ``idx_entities_type_kind`` which step 5f already created.
            conn.execute(
                "DROP INDEX IF EXISTS idx_workspace_entity_type"
            )
            sqlite_version_tuple = tuple(
                int(x) for x in sqlite3.sqlite_version.split(".")[:3]
            )
            if sqlite_version_tuple >= (3, 35, 0):
                # Native DROP COLUMN (SQLite 3.35+ supports this directly).
                conn.execute(
                    "ALTER TABLE entities DROP COLUMN entity_type"
                )
            else:
                # Copy-rename fallback for older SQLite. Build a new
                # ``entities`` table omitting ``entity_type``, INSERT-SELECT
                # the surviving columns, DROP old, RENAME new. Preserves
                # the composite CHECK constraint, all indexes, and all
                # triggers that step 5f's copy-rename already restored.
                survive_cols = [
                    c for c in conn.execute(
                        "PRAGMA table_info(entities)"
                    ).fetchall()
                    if c[1] != "entity_type"
                ]
                survive_names = [c[1] for c in survive_cols]

                # Capture indexes + triggers so we can restore them after
                # the rebuild.
                saved_indexes_2 = [
                    (r[0], r[1])
                    for r in conn.execute(
                        "SELECT name, sql FROM sqlite_master "
                        "WHERE type='index' AND tbl_name='entities' "
                        "AND sql IS NOT NULL"
                    ).fetchall()
                ]
                saved_triggers_2 = [
                    (r[0], r[1])
                    for r in conn.execute(
                        "SELECT name, sql FROM sqlite_master "
                        "WHERE type='trigger' AND tbl_name='entities' "
                        "AND sql IS NOT NULL"
                    ).fetchall()
                ]

                # Build the new CREATE TABLE statement with the same
                # composite CHECK constraint from step 5f, omitting
                # entity_type.
                conn.execute("""
                    CREATE TABLE entities_drop (
                        uuid           TEXT NOT NULL PRIMARY KEY,
                        workspace_uuid TEXT NOT NULL
                                       REFERENCES workspaces(uuid),
                        type_id        TEXT NOT NULL,
                        entity_id      TEXT NOT NULL,
                        name           TEXT NOT NULL,
                        status         TEXT,
                        parent_uuid    TEXT REFERENCES entities_drop(uuid),
                        artifact_path  TEXT,
                        created_at     TEXT NOT NULL,
                        updated_at     TEXT NOT NULL,
                        metadata       TEXT,
                        type           TEXT NOT NULL DEFAULT 'work',
                        kind           TEXT NOT NULL DEFAULT 'feature',
                        lifecycle_class TEXT NOT NULL
                                       DEFAULT 'feature_flow',
                        UNIQUE(workspace_uuid, type_id),
                        CHECK (
                            (type='workspace' AND kind='workspace') OR
                            (type='brainstorm' AND kind='brainstorm') OR
                            (type='container' AND kind='project') OR
                            (type='work' AND kind IN (
                                'feature','backlog',
                                'initiative','objective',
                                'key_result','task'
                            ))
                        )
                    )
                """)
                col_list_sql = ",".join(survive_names)
                conn.execute(
                    f"INSERT INTO entities_drop ({col_list_sql}) "
                    f"SELECT {col_list_sql} FROM entities"
                )
                conn.execute("DROP TABLE entities")
                conn.execute(
                    "ALTER TABLE entities_drop RENAME TO entities"
                )
                # Recreate indexes + triggers (filter out
                # ``idx_entity_type`` which references the dropped
                # column — would fail to CREATE).
                for idx_name, idx_sql in saved_indexes_2:
                    if idx_sql and "entity_type" not in idx_sql:
                        conn.execute(idx_sql)
                for trg_name, trg_sql in saved_triggers_2:
                    if trg_sql and "entity_type" not in trg_sql:
                        conn.execute(trg_sql)

        # ------------------------------------------------------------------
        # Step 5i: F2 phase_events copy-rename (Group 8, Tasks 8.4 + 8.5)
        # ------------------------------------------------------------------
        # Expand ``phase_events`` schema along three dimensions:
        #   1. ``event_type`` CHECK widens from 4 → 7 values: adds the three
        #      entity_* discriminators (entity_created, entity_status_changed,
        #      entity_promoted) per spec FR-2 / AC-2.4.
        #   2. ``phase`` is relaxed from NOT NULL to NULL-able (the new
        #      entity_* event types have no meaningful phase value per the
        #      per-event-type column-domain table).
        #   3. NEW ``metadata`` TEXT NULL column — JSON payload for the new
        #      event types (e.g. ``{"old_status": ..., "new_status": ...}``).
        #
        # SQLite cannot ALTER TABLE to widen a CHECK or relax NOT NULL, so we
        # use the documented copy-rename idiom
        # (https://www.sqlite.org/lang_altertable.html § 8).
        #
        # Idempotency: probe ``PRAGMA table_info(phase_events)`` for the
        # ``metadata`` column AND inspect the CHECK SQL from ``sqlite_master``
        # for the new entity_* values. If both are present, the block already
        # ran in a prior interrupted v12 attempt — skip the rebuild.
        pe_cols = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(phase_events)"
            ).fetchall()
        }
        pe_master = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='phase_events'"
        ).fetchone()
        pe_check_sql = pe_master[0] if pe_master else ""
        pe_has_metadata = "metadata" in pe_cols
        pe_has_entity_created = (
            "entity_created" in (pe_check_sql or "")
        )
        if not (pe_has_metadata and pe_has_entity_created):
            # Capture pre-rebuild row count for parity check.
            pe_pre_count = conn.execute(
                "SELECT COUNT(*) FROM phase_events"
            ).fetchone()[0]
            # Capture user-defined indexes (incl. the partial-UNIQUE
            # backfill-dedup index) so we can recreate them post-RENAME.
            # SQLite auto-drops indexes when the underlying table is
            # dropped; CREATE INDEX statements stored in sqlite_master are
            # the canonical source we re-issue.
            pe_saved_indexes = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='phase_events' "
                    "AND sql IS NOT NULL"
                ).fetchall()
            ]
            # Capture triggers on phase_events (none expected at v11, but
            # discover-don't-hardcode per design §1 sub-step 5).
            pe_saved_triggers = [
                (r[0], r[1])
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' AND tbl_name='phase_events' "
                    "AND sql IS NOT NULL"
                ).fetchall()
            ]

            # Build phase_events_new with widened CHECK, NULL-able phase,
            # and the new metadata TEXT column. Column order preserves the
            # legacy layout for the INSERT-SELECT below, then appends
            # ``metadata`` as the last column.
            conn.execute("""
                CREATE TABLE phase_events_new (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    type_id         TEXT NOT NULL,
                    project_id      TEXT NOT NULL,
                    phase           TEXT,
                    event_type      TEXT NOT NULL CHECK(event_type IN (
                        'started', 'completed', 'skipped', 'backward',
                        'entity_created', 'entity_status_changed',
                        'entity_promoted'
                    )),
                    timestamp       TEXT NOT NULL,
                    iterations      INTEGER,
                    reviewer_notes  TEXT,
                    backward_reason TEXT,
                    backward_target TEXT,
                    source          TEXT NOT NULL DEFAULT 'live' CHECK(
                        source IN ('live', 'backfill')
                    ),
                    created_at      TEXT NOT NULL,
                    metadata        TEXT
                )
            """)
            # INSERT-SELECT preserves all existing rows; metadata defaults
            # to NULL for legacy rows.
            conn.execute(
                "INSERT INTO phase_events_new "
                "(id, type_id, project_id, phase, event_type, timestamp, "
                "iterations, reviewer_notes, backward_reason, "
                "backward_target, source, created_at, metadata) "
                "SELECT id, type_id, project_id, phase, event_type, "
                "timestamp, iterations, reviewer_notes, backward_reason, "
                "backward_target, source, created_at, NULL "
                "FROM phase_events"
            )
            pe_post_count = conn.execute(
                "SELECT COUNT(*) FROM phase_events_new"
            ).fetchone()[0]
            if pe_post_count != pe_pre_count:
                raise RuntimeError(
                    f"Migration 12 phase_events copy-rename row-count "
                    f"mismatch: pre={pe_pre_count}, post={pe_post_count}"
                )

            # Swap tables.
            conn.execute("DROP TABLE phase_events")
            conn.execute(
                "ALTER TABLE phase_events_new RENAME TO phase_events"
            )

            # Recreate captured indexes verbatim (the partial-UNIQUE
            # ``phase_events_backfill_dedup`` is included in this set per
            # the original migration-10 DDL at database.py:1517-1532).
            for idx_name, idx_sql in pe_saved_indexes:
                if idx_sql:
                    conn.execute(idx_sql)

            # Recreate captured triggers (none expected; future-proof).
            for trg_name, trg_sql in pe_saved_triggers:
                if trg_sql:
                    conn.execute(trg_sql)

        # ------------------------------------------------------------------
        # Step N-2: in-transaction post-flight FK check
        # ------------------------------------------------------------------
        # CRITICAL SAFETY (per design §1 sub-step 12): catches FK violations
        # introduced by the migration body BEFORE the schema_version stamp.
        # Any future body addition that creates FK violations will fail here
        # rather than leaving the DB in a half-migrated state.
        in_tx_fk_violations = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if in_tx_fk_violations:
            raise RuntimeError(
                f"Migration 12 in-transaction FK check non-empty: "
                f"{in_tx_fk_violations}"
            )

        # ------------------------------------------------------------------
        # Step N-1: stamp schema_version=12 INSIDE the transaction
        # ------------------------------------------------------------------
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '12')"
        )

        # ------------------------------------------------------------------
        # Step N: COMMIT
        # ------------------------------------------------------------------
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        # Re-enable FKs whether success or failure.
        conn.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------------------
    # Post-transaction defensive FK check
    # ----------------------------------------------------------------------
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"Migration 12 post-FK check non-empty: {post_violations}"
        )


def _migration_12_polymorphic_taxonomy_and_events_down(
    conn: sqlite3.Connection,
) -> None:
    """Reverse Migration 12 (feature 109 FR-5 / design TD-9).

    One-shot rollback only — restores runtime schema state to the v11
    baseline. Source-code state (trigger definitions, register_entity SQL,
    upsert_entity / promote_entity / append_phase_event helpers) is NOT
    touched — operators restore source via git-history per spec AC-5.1.

    Reverse sub-steps (mirror forward §1 in REVERSE order):
      1. PRAGMA foreign_keys = OFF outside try; BEGIN IMMEDIATE inside try.
      2. Idempotency check: if schema_version <= 11, no-op early-return.
      3. Drop ``idx_entities_type_kind``.
      4. ADD COLUMN ``entity_type`` to entities; backfill from ``kind`` via
         the REVERSE mapping (kind='feature' → 'feature', kind='backlog' →
         'backlog', kind='project' → 'project', kind='brainstorm' →
         'brainstorm', kind='workspace' → 'workspace').
      5. Rebuild ``entities_fts`` to use the legacy ``entity_type`` column
         instead of ``kind``.
      6. Drop new entities columns (type, kind, lifecycle_class) via
         copy-rename.
      7. Reverse phase_events copy-rename: narrow CHECK back to the 4
         legacy event_types, restore ``phase NOT NULL``, drop ``metadata``
         column.
      8. Recreate ``enforce_immutable_entity_type`` and
         ``enforce_immutable_type_id`` triggers at ONE canonical site each
         (runtime DDL only; not 6 source-code definitions — those are
         git-history-restored).
      9. Stamp ``schema_version=11`` inside the transaction; COMMIT.
     10. Finally: PRAGMA foreign_keys = ON.

    Raises:
        RuntimeError on FK violations or in-transaction failures.
    """
    # ----------------------------------------------------------------------
    # Step 1: PRAGMA foreign_keys = OFF (outside transaction)
    # ----------------------------------------------------------------------
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise RuntimeError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 12 reverse"
        )

    try:
        # ------------------------------------------------------------------
        # Step 2: BEGIN IMMEDIATE; idempotency check
        # ------------------------------------------------------------------
        conn.execute("BEGIN IMMEDIATE")
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise RuntimeError(
                "Migration 12 reverse: _metadata.schema_version missing"
            )
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Migration 12 reverse: invalid schema_version {v_row[0]!r}"
            ) from exc
        if current_version <= 11:
            conn.rollback()
            return

        # ------------------------------------------------------------------
        # Step 3: drop idx_entities_type_kind
        # ------------------------------------------------------------------
        conn.execute("DROP INDEX IF EXISTS idx_entities_type_kind")

        # ------------------------------------------------------------------
        # Step 4: restore entity_type column + backfill from kind
        # ------------------------------------------------------------------
        existing_cols = {
            r[1] for r in conn.execute(
                "PRAGMA table_info(entities)"
            ).fetchall()
        }
        if "entity_type" not in existing_cols:
            # ALTER TABLE ADD COLUMN with a placeholder default so NOT NULL
            # constraint is satisfied during the ADD (live rows backfill
            # immediately below).
            conn.execute(
                "ALTER TABLE entities ADD COLUMN entity_type TEXT "
                "NOT NULL DEFAULT 'feature'"
            )
        # Backfill via REVERSE mapping. kind 'feature'/'backlog'/'project'/
        # 'brainstorm'/'workspace' → entity_type with the same value (the
        # forward mapping was lossy on type=work split into kind=feature vs
        # kind=backlog; reversing just uses kind directly as entity_type).
        conn.execute(
            "UPDATE entities SET entity_type = kind "
            "WHERE kind IN ('feature', 'backlog', 'project', 'brainstorm', "
            "'workspace')"
        )

        # ------------------------------------------------------------------
        # Step 5: (entities_fts rebuild deferred — performed below in
        # step 6 after the entities table swap, because the FTS5
        # contentless rowids must re-link to the post-rename entities.)
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # Step 6: drop new columns (type, kind, lifecycle_class) via
        # copy-rename. ALTER TABLE DROP COLUMN is blocked by the composite
        # CHECK constraint that references (type, kind), so we rebuild the
        # entities table without those columns and without the CHECK.
        # ------------------------------------------------------------------
        # Capture entities-related indexes and triggers so we can rebuild
        # them on the new table.
        ent_saved_indexes = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='entities' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        ent_saved_triggers = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='entities' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        ent_pre_count = conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]

        # Recreate the pre-12 entities shape: uuid PK, workspace_uuid FK,
        # type_id, entity_id, entity_type, name, status, parent_uuid (FK to
        # entities.uuid), artifact_path, created_at, updated_at, metadata.
        conn.execute("""
            CREATE TABLE entities_old (
                uuid           TEXT NOT NULL PRIMARY KEY,
                workspace_uuid TEXT NOT NULL
                               REFERENCES workspaces(uuid),
                type_id        TEXT NOT NULL,
                entity_id      TEXT NOT NULL,
                entity_type    TEXT NOT NULL,
                name           TEXT NOT NULL,
                status         TEXT,
                parent_uuid    TEXT REFERENCES entities_old(uuid),
                artifact_path  TEXT,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                metadata       TEXT,
                UNIQUE(workspace_uuid, type_id)
            )
        """)
        conn.execute(
            "INSERT INTO entities_old "
            "(uuid, workspace_uuid, type_id, entity_id, entity_type, name, "
            "status, parent_uuid, artifact_path, created_at, updated_at, "
            "metadata) "
            "SELECT uuid, workspace_uuid, type_id, entity_id, entity_type, "
            "name, status, parent_uuid, artifact_path, created_at, "
            "updated_at, metadata "
            "FROM entities"
        )
        ent_post_count = conn.execute(
            "SELECT COUNT(*) FROM entities_old"
        ).fetchone()[0]
        if ent_post_count != ent_pre_count:
            raise RuntimeError(
                f"Migration 12 reverse entities copy-rename row-count "
                f"mismatch: pre={ent_pre_count}, post={ent_post_count}"
            )

        # Drop entities_fts since its rowid links to the old entities;
        # we rebuild against the renamed table below.
        conn.execute("DROP TABLE IF EXISTS entities_fts")

        # Drop triggers on workflow_phases that reference entities via
        # subquery — SQLite re-validates these during DROP TABLE entities
        # and complains "no such table: main.entities". Capture their
        # source so we recreate them after the rename.
        wp_saved_triggers = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='workflow_phases' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        for trg_name, _trg_sql in wp_saved_triggers:
            conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

        # Swap tables — DROP old entities and rename. Note FK references
        # to entities (e.g. workflow_phases via direct type_id text and
        # several triggers) survive because they are reference-by-name
        # rather than table_oid.
        conn.execute("DROP TABLE entities")
        conn.execute("ALTER TABLE entities_old RENAME TO entities")

        # Recreate workflow_phases triggers.
        for _trg_name, trg_sql in wp_saved_triggers:
            if trg_sql:
                conn.execute(trg_sql)

        # Recreate captured entities indexes that don't reference dropped
        # columns. idx_entities_type_kind (already dropped in step 3) is
        # filtered out by name; the rest are restored verbatim.
        for idx_name, idx_sql in ent_saved_indexes:
            if not idx_sql:
                continue
            if idx_name == "idx_entities_type_kind":
                continue
            # Skip any index whose SQL references the dropped columns.
            if " type " in idx_sql or " kind " in idx_sql or " lifecycle_class " in idx_sql:
                continue
            conn.execute(idx_sql)

        # Recreate captured entities triggers (other than the immutable
        # triggers we re-add in step 8). Filter the immutable pair out so
        # the step-8 recreate is the canonical site.
        for trg_name, trg_sql in ent_saved_triggers:
            if not trg_sql:
                continue
            if trg_name in (
                "enforce_immutable_entity_type",
                "enforce_immutable_type_id",
            ):
                continue
            conn.execute(trg_sql)

        # Rebuild entities_fts (pre-12 shape with entity_type) since the
        # entities table was swapped — its FTS5 contentless rowids must
        # re-link to the new table.
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE entities_fts USING fts5("
                "name, entity_id, entity_type, status, metadata_text)"
            )
        except sqlite3.OperationalError as exc:
            if "no such module: fts5" in str(exc):
                raise RuntimeError(
                    "FTS5 extension not available — "
                    "cannot complete migration 12 reverse FTS5 rebuild"
                ) from exc
            raise
        fts_rebuild_rows = conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for row in fts_rebuild_rows:
            md = row[5]
            metadata_text = flatten_metadata(
                json.loads(md) if md else None
            )
            conn.execute(
                "INSERT INTO entities_fts ("
                "rowid, name, entity_id, entity_type, status, metadata_text"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4], metadata_text),
            )

        # ------------------------------------------------------------------
        # Step 7: reverse phase_events copy-rename — narrow CHECK + restore
        # phase NOT NULL + drop metadata column.
        # ------------------------------------------------------------------
        # Discover existing phase_events indexes/triggers so we can rebuild
        # them on the new table.
        pe_pre_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]
        pe_saved_indexes = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='phase_events' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        pe_saved_triggers = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='phase_events' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]

        # Pre-down assertion: every existing row must have a non-NULL phase
        # and an event_type in the legacy 4-value set — otherwise the
        # narrowed schema would reject the INSERT-SELECT below.
        bad_rows = conn.execute(
            "SELECT COUNT(*) FROM phase_events "
            "WHERE phase IS NULL OR event_type NOT IN ("
            "  'started', 'completed', 'skipped', 'backward'"
            ")"
        ).fetchone()[0]
        if bad_rows > 0:
            raise RuntimeError(
                f"Migration 12 reverse: {bad_rows} phase_events row(s) "
                "incompatible with v11 schema (NULL phase or new "
                "event_type). Operator must prune them before reversing."
            )

        conn.execute("""
            CREATE TABLE phase_events_old (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id         TEXT NOT NULL,
                project_id      TEXT NOT NULL,
                phase           TEXT NOT NULL,
                event_type      TEXT NOT NULL CHECK(event_type IN (
                    'started', 'completed', 'skipped', 'backward'
                )),
                timestamp       TEXT NOT NULL,
                iterations      INTEGER,
                reviewer_notes  TEXT,
                backward_reason TEXT,
                backward_target TEXT,
                source          TEXT NOT NULL DEFAULT 'live' CHECK(
                    source IN ('live', 'backfill')
                ),
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO phase_events_old "
            "(id, type_id, project_id, phase, event_type, timestamp, "
            "iterations, reviewer_notes, backward_reason, "
            "backward_target, source, created_at) "
            "SELECT id, type_id, project_id, phase, event_type, "
            "timestamp, iterations, reviewer_notes, backward_reason, "
            "backward_target, source, created_at "
            "FROM phase_events"
        )
        pe_post_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events_old"
        ).fetchone()[0]
        if pe_post_count != pe_pre_count:
            raise RuntimeError(
                f"Migration 12 reverse phase_events copy-rename row-count "
                f"mismatch: pre={pe_pre_count}, post={pe_post_count}"
            )
        conn.execute("DROP TABLE phase_events")
        conn.execute(
            "ALTER TABLE phase_events_old RENAME TO phase_events"
        )
        # Recreate captured indexes verbatim.
        for idx_name, idx_sql in pe_saved_indexes:
            if idx_sql:
                conn.execute(idx_sql)
        # Recreate captured triggers verbatim.
        for trg_name, trg_sql in pe_saved_triggers:
            if trg_sql:
                conn.execute(trg_sql)

        # ------------------------------------------------------------------
        # Step 8: recreate immutable triggers at ONE canonical site each
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_entity_type
            BEFORE UPDATE OF entity_type ON entities
            BEGIN
                SELECT RAISE(ABORT, 'entity_type is immutable');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_type_id
            BEFORE UPDATE OF type_id ON entities
            BEGIN
                SELECT RAISE(ABORT, 'type_id is immutable');
            END
        """)

        # ------------------------------------------------------------------
        # Step 9: in-transaction FK check + stamp schema_version=11
        # ------------------------------------------------------------------
        in_tx_fk_violations = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if in_tx_fk_violations:
            raise RuntimeError(
                f"Migration 12 reverse in-transaction FK check non-empty: "
                f"{in_tx_fk_violations}"
            )
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '11')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        # Step 10: re-enable FKs whether success or failure.
        conn.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------------------
    # Post-transaction defensive FK check
    # ----------------------------------------------------------------------
    post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_violations:
        raise RuntimeError(
            f"Migration 12 reverse post-FK check non-empty: "
            f"{post_violations}"
        )


# ---------------------------------------------------------------------------
# Feature 110 (Group 2 Task 2.0): entity_id format validation.
# ---------------------------------------------------------------------------
# Migration 13 introduces ``entity_display(uuid, seq, slug)`` populated by
# parsing ``entities.entity_id`` as ``{seq}-{slug}`` (numeric prefix + dash +
# slug suffix). Post-migration, ``register_entity`` must enforce this format
# on insert so the 1:1 invariant between entities and entity_display is
# preserved for new rows. Existing test fixtures with non-conformant
# entity_ids may use the ``_register_entity_no_display`` escape hatch (see
# EntityDatabase) which bypasses both the regex check and the entity_display
# INSERT — appropriate ONLY for tests that need to exercise the pre-migration
# fixture shape directly.
_ENTITY_ID_FORMAT_RE = re.compile(r"^\d+-.+")


class EntityIdFormatError(ValueError):
    """Raised when ``entity_id`` does not match the ``{seq}-{slug}`` format
    (feature 110 FR-8 / Group 2 Task 2.0).

    Production callers must supply ``entity_id`` matching ``^\\d+-.+`` so
    Migration 13's backfill SQL (CAST + substr on the dash position) yields
    a well-formed ``(seq, slug)`` tuple. Tests that need non-conformant
    fixture ids use ``EntityDatabase._register_entity_no_display`` which
    skips both the regex check and the entity_display INSERT.
    """

    def __init__(self, entity_id: str):
        super().__init__(
            f"Invalid entity_id format: {entity_id!r}. "
            f"Must match '^\\d+-.+' (numeric prefix + dash + slug suffix). "
            f"Test fixtures using non-standard ids should use "
            f"_register_entity_no_display."
        )
        self.entity_id = entity_id


# ---------------------------------------------------------------------------
# Feature 110 (Groups 1+2+3): Migration 13 — entity_display + migration_audit_log.
# ---------------------------------------------------------------------------
def _migration_13_entity_display(conn: sqlite3.Connection) -> None:
    """Migration 13: entity_display(uuid, seq, slug) + migration_audit_log.

    Feature 110 Groups 1+2+3 combined function body. Order per spec
    FR-8 / Task 2.2 execution-order note:

      1. Pre-flight gate (3 checks; see TD-6):
         - schema_version (codebase analogue of PRAGMA user_version,
           stored in ``_metadata.schema_version``) == 12.
         - schema_version stamp consistent with the entities-table layout.
         - PRAGMA table_info(entities) confirms ``entity_type`` ABSENT and
           ``type``/``kind``/``lifecycle_class`` PRESENT.
      2. Runtime PRAGMA introspection: assert ``uuid``, ``entity_id``,
         ``metadata`` columns exist in entities (FR-5.6).
      3. Idempotency early-return if entity_display table exists AND
         schema_version >= 13.
      4. BEGIN IMMEDIATE.
      5. CREATE TABLE entity_display + idx_entity_display_seq.
      6. CREATE TABLE migration_audit_log IF NOT EXISTS.
      7. Pre-audit query (FR-8.2-pre): rows where metadata.slug != entity_id
         suffix. Each logged to migration_audit_log (mismatch_row).
      8. Env-var bypass check (PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS). If
         mismatches > 0 and bypass NOT set → raise. If set → log
         bypass_acknowledged forensic row.
      9. Backfill INSERT: entity_display(uuid, seq, slug) from
         CAST(substr(...)) parse of entity_id.
     10. In-tx PRAGMA foreign_key_check.
     11. Stamp _metadata.schema_version='13'.
     12. COMMIT.

    Note on PRAGMA user_version vs _metadata.schema_version: spec FR-5.5
    references ``PRAGMA user_version``, but the existing codebase uses the
    ``_metadata.schema_version`` row for migration tracking (set by every
    prior migration; see ``_migrate``). We honour the codebase convention.
    The pre-flight semantics are equivalent: a single canonical source of
    truth for "what schema version is this DB?".

    Idempotency: re-running this migration on a v13 DB is a no-op
    early-return (FR-5.2 / AC-5.2).
    """
    # ----------------------------------------------------------------------
    # Step 0: Outer-level idempotency early-return (FR-5.2 / AC-5.2).
    # ----------------------------------------------------------------------
    # If entity_display table already exists AND schema_version >= 13, this
    # is a replay against an already-migrated DB → no-op early-return BEFORE
    # the pre-flight gate runs (since the gate expects schema_version == 12).
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            raise RuntimeError(
                "Migration 13 aborted: _metadata table missing. Cannot read "
                "schema_version. Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-109 deferred remediation)."
            ) from e
        raise

    if v_row is not None:
        try:
            preview_version = int(v_row[0])
        except (TypeError, ValueError):
            preview_version = 0
        if preview_version >= 13:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='entity_display'"
            ).fetchone()
            if table_row is not None:
                return

    # ----------------------------------------------------------------------
    # Step 1: Pre-flight gate (FR-5.5 / TD-6).
    # ----------------------------------------------------------------------
    #
    # Check 1: _metadata.schema_version exists and equals '12'.
    if v_row is None:
        raise RuntimeError(
            "Migration 13 aborted: _metadata.schema_version row missing. "
            "Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-109 deferred remediation)."
        )
    try:
        current_version = int(v_row[0])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Migration 13 aborted: invalid schema_version {v_row[0]!r}. "
            "Manual reconciliation required."
        ) from exc

    if current_version != 12:
        # The _metadata row says we're not at 12. Look at the column layout
        # to give a precise error.
        existing_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()
        }
        # If the column layout LOOKS like post-12 (entity_type absent +
        # type/kind/lifecycle_class present), it's a version-divergence
        # case: schema migrated but stamp lagging.
        is_v12_layout = (
            "entity_type" not in existing_cols
            and "type" in existing_cols
            and "kind" in existing_cols
            and "lifecycle_class" in existing_cols
        )
        if is_v12_layout and current_version < 12:
            raise RuntimeError(
                f"Migration 13 aborted: schema_version table version="
                f"{current_version} disagrees with PRAGMA user_version=12 "
                f"(entities column layout is post-12). "
                f"Manual reconciliation required."
            )
        # Otherwise this is just "schema not at 12 yet" — common stale-pre-12
        # path. Use the user_version mismatch error per TD-6 check 1.
        raise RuntimeError(
            f"Migration 13 aborted: user_version={current_version}, "
            f"expected 12. Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-109 deferred remediation)."
        )

    # Check 3 (TD-6): column layout assertion.
    existing_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()
    }
    entity_type_present = "entity_type" in existing_cols
    type_present = "type" in existing_cols
    kind_present = "kind" in existing_cols
    lifecycle_class_present = "lifecycle_class" in existing_cols

    if entity_type_present or not (
        type_present and kind_present and lifecycle_class_present
    ):
        raise RuntimeError(
            f"Migration 13 aborted: entities table schema mismatch. "
            f"Detected entity_type="
            f"{'present' if entity_type_present else 'absent'}, "
            f"type={'present' if type_present else 'absent'}, "
            f"kind={'present' if kind_present else 'absent'}, "
            f"lifecycle_class="
            f"{'present' if lifecycle_class_present else 'absent'}. "
            f"Expected post-migration-12 layout. "
            f"Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-109 deferred remediation)."
        )

    # ----------------------------------------------------------------------
    # Step 2: Runtime PRAGMA column-presence introspection (FR-5.6).
    # ----------------------------------------------------------------------
    for required in ("uuid", "entity_id", "metadata"):
        if required not in existing_cols:
            raise RuntimeError(
                f"Migration 13 aborted: entities table missing required "
                f"column {required!r}. Cannot backfill entity_display."
            )

    # ----------------------------------------------------------------------
    # Step 4: BEGIN IMMEDIATE.
    # ----------------------------------------------------------------------
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Concurrent re-check guard.
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is not None:
            try:
                in_tx_version = int(v_row[0])
            except (TypeError, ValueError):
                in_tx_version = 0
            if in_tx_version >= 13:
                conn.rollback()
                return

        # Pre-DDL FK check.
        pre_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if pre_fk:
            raise RuntimeError(
                f"Migration 13 pre-FK check non-empty: {pre_fk}"
            )

        # ------------------------------------------------------------------
        # Step 5: CREATE TABLE entity_display + index.
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entity_display (
                uuid TEXT PRIMARY KEY,
                seq  INTEGER NOT NULL,
                slug TEXT NOT NULL,
                FOREIGN KEY (uuid) REFERENCES entities(uuid) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_display_seq "
            "ON entity_display(seq)"
        )

        # ------------------------------------------------------------------
        # Step 6: CREATE TABLE migration_audit_log (TD-2).
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE IF NOT EXISTS migration_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # ------------------------------------------------------------------
        # Step 7: Pre-audit query — mismatch detection (FR-8.2-pre).
        # ------------------------------------------------------------------
        # Detect entities where metadata.slug differs from entity_id
        # suffix. Per spec FR-8.2-pre exact SQL.
        mismatch_rows = conn.execute("""
            SELECT uuid, entity_id,
                   json_extract(metadata, '$.id')   AS meta_id,
                   json_extract(metadata, '$.slug') AS meta_slug
            FROM entities
            WHERE json_extract(metadata, '$.slug') IS NOT NULL
              AND json_extract(metadata, '$.slug') !=
                  substr(entity_id, instr(entity_id, '-') + 1)
        """).fetchall()

        now_iso = datetime.now(timezone.utc).isoformat()
        for m_row in mismatch_rows:
            payload = json.dumps({
                "uuid": m_row[0],
                "entity_id": m_row[1],
                "meta_id": m_row[2],
                "meta_slug": m_row[3],
            })
            conn.execute(
                "INSERT INTO migration_audit_log "
                "(migration_version, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (13, "mismatch_row", payload, now_iso),
            )

        # ------------------------------------------------------------------
        # Step 8: Env-var bypass check (FR-8.2-pre).
        # ------------------------------------------------------------------
        if mismatch_rows:
            bypass = os.environ.get("PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS")
            if bypass != "1":
                uuid_list = [row[0] for row in mismatch_rows]
                raise RuntimeError(
                    f"Migration 13 aborted: {len(mismatch_rows)} entity_id / "
                    f"metadata.slug mismatch(es) detected. "
                    f"UUIDs: {uuid_list}. Reconcile manually OR set "
                    f"PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1 to accept "
                    f"entity_id as canonical (logged forensically in "
                    f"migration_audit_log)."
                )
            # Bypass set — log a forensic acknowledgement row.
            try:
                import getpass
                user = getpass.getuser()
            except Exception:
                user = "unknown"
            bypass_payload = json.dumps({
                "mismatch_count": len(mismatch_rows),
                "user": user,
                "ts": now_iso,
            })
            conn.execute(
                "INSERT INTO migration_audit_log "
                "(migration_version, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                (13, "bypass_acknowledged", bypass_payload, now_iso),
            )

        # ------------------------------------------------------------------
        # Step 9: Backfill INSERT (FR-8.2).
        # ------------------------------------------------------------------
        # Use INSERT OR IGNORE so a partial prior run's rows don't cause
        # PRIMARY KEY conflict on uuid (idempotency contributor).
        conn.execute("""
            INSERT OR IGNORE INTO entity_display (uuid, seq, slug)
            SELECT uuid,
                   CAST(substr(entity_id, 1, instr(entity_id, '-') - 1)
                        AS INTEGER) AS seq,
                   substr(entity_id, instr(entity_id, '-') + 1) AS slug
            FROM entities
            WHERE instr(entity_id, '-') > 0
        """)

        # ------------------------------------------------------------------
        # Step 10: In-tx FK check (FR-5.1).
        # ------------------------------------------------------------------
        in_tx_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if in_tx_fk:
            raise RuntimeError(
                f"Migration 13 in-transaction FK check non-empty: {in_tx_fk}"
            )

        # ------------------------------------------------------------------
        # Step 11: Stamp schema_version=13 INSIDE the transaction.
        # ------------------------------------------------------------------
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '13')"
        )

        # ------------------------------------------------------------------
        # Step 12: COMMIT.
        # ------------------------------------------------------------------
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise

    # ----------------------------------------------------------------------
    # Post-transaction defensive FK check.
    # ----------------------------------------------------------------------
    post_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_fk:
        raise RuntimeError(
            f"Migration 13 post-FK check non-empty: {post_fk}"
        )


def _migration_13_entity_display_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 13 (feature 110 FR-5.4 / Task 15.1).

    Drops:
      - entity_display table.
      - idx_entity_display_seq index.
      - migration_audit_log table (IF EXISTS).
      - Stamps schema_version back to 12.

    Runtime-only: source-code restore of removed callers is via git history
    (precedent: feature 109 retro / TD-8).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise RuntimeError(
                "Migration 13 reverse: _metadata.schema_version missing"
            )
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Migration 13 reverse: invalid schema_version {v_row[0]!r}"
            ) from exc
        if current_version <= 12:
            # Already at or below 12 → no-op early-return.
            conn.rollback()
            return

        conn.execute("DROP INDEX IF EXISTS idx_entity_display_seq")
        conn.execute("DROP TABLE IF EXISTS entity_display")
        conn.execute("DROP TABLE IF EXISTS migration_audit_log")

        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '12')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise


# ---------------------------------------------------------------------------
# Feature 111 (Group A): Migration 14 — entity_relations table + CHECK widenings.
# ---------------------------------------------------------------------------
# Adds:
#   - entity_relations table (FR-MR.1) + 3 indices.
#   - Widens entities (type, kind) CHECK to admit kind='bug' (FR-MR.2).
#   - Widens phase_events.event_type CHECK to admit 'spawned_child' (FR-MR.3).
#   - Remaps any existing kind='task' rows from lifecycle_class='work_flow'
#     to 'task_flow' (FR-MR.5; operational no-op per spec Pin I).
#
# MigrationError + _append_migration_audit_log helper are introduced here to
# back the FR-MR.6 / FR-MR.9 pre-flight gates (which raise structured errors
# that downstream tests assert by class). Prior migrations (12, 13) raised
# RuntimeError; this feature standardises on MigrationError for new gates and
# leaves the legacy RuntimeError sites untouched (no backward-compat shim per
# CLAUDE.md "No backward compatibility").


class MigrationError(Exception):
    """Raised by migration pre-flight gates and safety checks.

    Used by Migration 14 (and forward) to signal structured migration
    failures: schema-version drift, required-table-absent, required-table-
    present (idempotency violation), or down-migration safety blockers.

    Tests assert the class type + message substring (per spec
    AC-MR.4/5/10/11).
    """


def _append_migration_audit_log(
    conn: sqlite3.Connection,
    *,
    version: int,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """Append a structured audit log row to migration_audit_log.

    Centralises the INSERT pattern Migration 13 emits inline (lines
    4184-4188, 4217-4220). Migration 14 (and forward migrations) use this
    helper for consistency.

    The migration_audit_log table is created by Migration 13. Callers
    invoking this helper from a Migration 14+ body can assume the table
    exists (Migration 14's pre-flight asserts so).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload or {})
    conn.execute(
        "INSERT INTO migration_audit_log "
        "(migration_version, event_type, payload, created_at) "
        "VALUES (?, ?, ?, ?)",
        (version, event_type, payload_json, now_iso),
    )


# Post-migration-12 entities table column list (the 14 columns produced by
# Migration 12 Group 7's entity_type drop). Used by Migration 14's copy-rename
# to build the INSERT-SELECT column list and to declare the new table.
_V14_ENTITIES_COLUMNS: tuple[str, ...] = (
    "uuid",
    "workspace_uuid",
    "type_id",
    "entity_id",
    "name",
    "status",
    "parent_uuid",
    "artifact_path",
    "created_at",
    "updated_at",
    "metadata",
    "type",
    "kind",
    "lifecycle_class",
)


def _copy_rename_entities_for_v14(conn: sqlite3.Connection) -> None:
    """Migration 14 helper — widen entities (type, kind) CHECK to admit 'bug'.

    Replicates the Migration 12 Group 3 copy-rename idiom
    (database.py:2866-3083): capture pre-rebuild indexes + triggers +
    cross-table triggers, build entities_new with widened CHECK, INSERT-
    SELECT all rows, DROP old, RENAME new, recreate indexes + triggers.

    Widened (type, kind) CHECK per FR-MR.2 — work-kind enum becomes:
        'feature','backlog','bug','initiative','objective','key_result','task'
    ('bug' inserted between 'backlog' and 'initiative'; AC-MR.2 pins the
    exact substring).

    Idempotency: probes sqlite_master for the literal substring
    ``'bug'`` (with quotes) inside the entities CHECK SQL. If present, the
    block already ran in a prior interrupted v14 attempt — skip.
    """
    entities_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='entities'"
    ).fetchone()
    entities_sql = entities_sql_row[0] if entities_sql_row else ""
    # The literal "'bug'" (with quotes) appears only when the widened CHECK
    # is in place. Comment-text mentions of "bug" (added by feature 109's
    # source code) don't include the surrounding quotes.
    if "'bug'" in (entities_sql or ""):
        return

    # Capture pre-rebuild row count for parity check.
    pre_count = conn.execute(
        "SELECT COUNT(*) FROM entities"
    ).fetchone()[0]

    # Capture user-defined indexes on entities.
    saved_indexes = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='entities' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]

    # Capture triggers ON entities.
    saved_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='entities' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]

    # Capture cross-table triggers that reference ``entities`` (SQLite
    # RENAME-table validator scans every trigger SQL and aborts if any
    # reference resolves to a missing table during the swap).
    cross_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' "
            "AND tbl_name <> 'entities' "
            "AND sql LIKE '%entities%' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for trg_name, _ in cross_triggers:
        conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

    # Build entities_new with the widened (type, kind) CHECK. Column
    # ordering matches the post-migration-12 layout (14 columns); the
    # CHECK enum substring per FR-MR.2 / AC-MR.2 is literal.
    conn.execute("""
        CREATE TABLE entities_new (
            uuid           TEXT NOT NULL PRIMARY KEY,
            workspace_uuid TEXT NOT NULL
                           REFERENCES workspaces(uuid),
            type_id        TEXT NOT NULL,
            entity_id      TEXT NOT NULL,
            name           TEXT NOT NULL,
            status         TEXT,
            parent_uuid    TEXT REFERENCES entities_new(uuid),
            artifact_path  TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            metadata       TEXT,
            type           TEXT NOT NULL DEFAULT 'work',
            kind           TEXT NOT NULL DEFAULT 'feature',
            lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow',
            UNIQUE(workspace_uuid, type_id),
            CHECK (
                (type='workspace' AND kind='workspace') OR
                (type='brainstorm' AND kind='brainstorm') OR
                (type='container' AND kind='project') OR
                (type='work' AND kind IN (
                    'feature','backlog','bug','initiative','objective','key_result','task'
                ))
            )
        )
    """)

    # Defensive: confirm the source column set matches what we expect.
    src_cols = [
        r[1] for r in conn.execute(
            "PRAGMA table_info(entities)"
        ).fetchall()
    ]
    expected = set(_V14_ENTITIES_COLUMNS)
    if set(src_cols) != expected:
        unknown = [c for c in src_cols if c not in expected]
        missing = [c for c in expected if c not in src_cols]
        raise MigrationError(
            f"Migration 14 entities copy-rename: column-set mismatch. "
            f"unknown={unknown!r}, missing={missing!r}"
        )

    col_list_sql = ",".join(_V14_ENTITIES_COLUMNS)
    conn.execute(
        f"INSERT INTO entities_new ({col_list_sql}) "
        f"SELECT {col_list_sql} FROM entities"
    )
    post_count = conn.execute(
        "SELECT COUNT(*) FROM entities_new"
    ).fetchone()[0]
    if post_count != pre_count:
        raise MigrationError(
            f"Migration 14 entities copy-rename row-count mismatch: "
            f"pre={pre_count}, post={post_count}"
        )

    # Swap tables.
    conn.execute("DROP TABLE entities")
    conn.execute("PRAGMA legacy_alter_table = OFF")
    conn.execute("ALTER TABLE entities_new RENAME TO entities")

    # Recreate captured user-defined indexes verbatim.
    for _, idx_sql in saved_indexes:
        if idx_sql:
            conn.execute(idx_sql)

    # Recreate captured triggers ON entities verbatim.
    for _, trg_sql in saved_triggers:
        if trg_sql:
            conn.execute(trg_sql)

    # Recreate cross-table triggers we temporarily dropped to allow the
    # entities-table rename. Captured SQL still references the table name
    # ``entities`` which is now the renamed table.
    for _, trg_sql in cross_triggers:
        if trg_sql:
            conn.execute(trg_sql)


def _copy_rename_phase_events_for_v14(conn: sqlite3.Connection) -> None:
    """Migration 14 helper — widen phase_events.event_type CHECK to admit
    'spawned_child'.

    Replicates the Migration 12 Group 8 copy-rename idiom
    (database.py:3329-3456): capture pre-rebuild indexes + triggers, build
    phase_events_new with widened CHECK (8 event_types incl. 'spawned_child'),
    INSERT-SELECT all rows, DROP old, RENAME new, recreate indexes + triggers.

    Widened event_type CHECK per FR-MR.3 — 8 values:
        'started','completed','skipped','backward',
        'entity_created','entity_status_changed','entity_promoted',
        'spawned_child'

    Idempotency: probes sqlite_master for ``'spawned_child'`` substring
    in the phase_events CHECK SQL. If present, the block already ran in a
    prior interrupted v14 attempt — skip.
    """
    pe_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='phase_events'"
    ).fetchone()
    pe_sql = pe_sql_row[0] if pe_sql_row else ""
    if "'spawned_child'" in (pe_sql or ""):
        return

    pe_pre_count = conn.execute(
        "SELECT COUNT(*) FROM phase_events"
    ).fetchone()[0]

    # Capture user-defined indexes on phase_events.
    pe_saved_indexes = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='phase_events' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]

    # Capture triggers ON phase_events (none expected, future-proof).
    pe_saved_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='phase_events' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]

    # Capture cross-table triggers referencing phase_events.
    pe_cross_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' "
            "AND tbl_name <> 'phase_events' "
            "AND sql LIKE '%phase_events%' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for trg_name, _ in pe_cross_triggers:
        conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

    # Build phase_events_new with widened event_type CHECK. Column order
    # matches the post-migration-12 layout.
    conn.execute("""
        CREATE TABLE phase_events_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id         TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            phase           TEXT,
            event_type      TEXT NOT NULL CHECK(event_type IN (
                'started', 'completed', 'skipped', 'backward',
                'entity_created', 'entity_status_changed',
                'entity_promoted', 'spawned_child'
            )),
            timestamp       TEXT NOT NULL,
            iterations      INTEGER,
            reviewer_notes  TEXT,
            backward_reason TEXT,
            backward_target TEXT,
            source          TEXT NOT NULL DEFAULT 'live' CHECK(
                source IN ('live', 'backfill')
            ),
            created_at      TEXT NOT NULL,
            metadata        TEXT
        )
    """)

    conn.execute(
        "INSERT INTO phase_events_new "
        "(id, type_id, project_id, phase, event_type, timestamp, "
        "iterations, reviewer_notes, backward_reason, "
        "backward_target, source, created_at, metadata) "
        "SELECT id, type_id, project_id, phase, event_type, "
        "timestamp, iterations, reviewer_notes, backward_reason, "
        "backward_target, source, created_at, metadata "
        "FROM phase_events"
    )
    pe_post_count = conn.execute(
        "SELECT COUNT(*) FROM phase_events_new"
    ).fetchone()[0]
    if pe_post_count != pe_pre_count:
        raise MigrationError(
            f"Migration 14 phase_events copy-rename row-count mismatch: "
            f"pre={pe_pre_count}, post={pe_post_count}"
        )

    conn.execute("DROP TABLE phase_events")
    conn.execute(
        "ALTER TABLE phase_events_new RENAME TO phase_events"
    )

    # Recreate captured indexes verbatim.
    for _, idx_sql in pe_saved_indexes:
        if idx_sql:
            conn.execute(idx_sql)

    # Recreate captured triggers ON phase_events verbatim.
    for _, trg_sql in pe_saved_triggers:
        if trg_sql:
            conn.execute(trg_sql)

    # Recreate cross-table triggers.
    for _, trg_sql in pe_cross_triggers:
        if trg_sql:
            conn.execute(trg_sql)


def _v14_schema_already_applied(conn: sqlite3.Connection) -> bool:
    """Return True if all three v14 DDL artifacts are already in place.

    Probes the SCHEMA (sqlite_master), not _metadata.schema_version — the
    outer ``_migrate`` loop clobbers schema_version after each migration_fn
    returns, so under concurrent-runner conditions the racer's schema_version
    may read as 13 even when the peer has fully applied v14 DDL. The schema
    artifacts (entity_relations table + widened CHECKs) are the stable
    racer-tolerant fingerprint.

    Used by Migration 14's step 0 and step 3 to short-circuit silently when
    a peer process has already applied the migration — preserves the
    concurrent-runner safety established by Migration 11.
    """
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "entity_relations" not in tables:
        return False
    entities_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='entities'"
    ).fetchone()
    entities_sql = entities_sql_row[0] if entities_sql_row else ""
    pe_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='phase_events'"
    ).fetchone()
    pe_sql = pe_sql_row[0] if pe_sql_row else ""
    # Quoted-literal probes — distinguishes CHECK-enum entries from
    # comment-text mentions.
    return "'bug'" in entities_sql and "'spawned_child'" in pe_sql


def _migration_14_issue_lifecycle_closure(conn: sqlite3.Connection) -> None:
    """Migration 14 — Feature 111 issue lifecycle closure (DDL).

    Creates:
        entity_relations table + 3 indices (FR-MR.1)

    Widens:
        entities.(type, kind) CHECK to admit kind='bug' (FR-MR.2)
        phase_events.event_type CHECK to admit 'spawned_child' (FR-MR.3)

    Remaps:
        UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task'
        AND lifecycle_class='work_flow' (FR-MR.5; operational no-op per Pin I)

    Pre-flight (FR-MR.6):
        _metadata.schema_version = 13 (codebase analogue of schema_migrations
                                       per Migration 13 docstring TD-6 note).
        entity_display table present.
        migration_audit_log table present.
        entity_relations table ABSENT (only when schema is genuinely v13;
        racer-replay scenarios short-circuit before this gate via
        :func:`_v14_schema_already_applied`).

    Replay-safe (FR-MR.8): early-return if already at v14 OR if schema
    artifacts indicate a concurrent peer has already applied v14 DDL
    (concurrent-runner safety; the outer ``_migrate`` clobbers
    ``_metadata.schema_version`` after each migration_fn return, so the
    SCHEMA fingerprint is the racer-tolerant idempotency signal).
    """
    # ----------------------------------------------------------------------
    # Step 0: Outer-level idempotency early-return (FR-MR.8).
    # ----------------------------------------------------------------------
    try:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            raise MigrationError(
                "Migration 14 aborted: _metadata table missing. Cannot read "
                "schema_version. Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-109/110 deferred remediation) "
                "first."
            ) from e
        raise

    if v_row is not None:
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError):
            current_version = 0
        if current_version >= 14:
            return

    # Concurrent-runner short-circuit: peer process has already applied
    # v14 DDL even though our outer _migrate just stamped schema_version
    # back to 13.
    if _v14_schema_already_applied(conn):
        return

    # ----------------------------------------------------------------------
    # Step 1: PRAGMA foreign_keys = OFF (outside transaction)
    # ----------------------------------------------------------------------
    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise MigrationError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 14"
        )

    try:
        # ------------------------------------------------------------------
        # Step 2: BEGIN IMMEDIATE
        # ------------------------------------------------------------------
        conn.execute("BEGIN IMMEDIATE")

        # ------------------------------------------------------------------
        # Step 3: Concurrent re-check guard
        # ------------------------------------------------------------------
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is not None:
            try:
                in_tx_version = int(v_row[0])
            except (TypeError, ValueError):
                in_tx_version = 0
            if in_tx_version >= 14:
                conn.rollback()
                return

        # Racer-tolerant re-check at the SCHEMA level: peer process may
        # have applied v14 DDL between our step-0 probe and BEGIN IMMEDIATE
        # acquisition. Short-circuit silently to preserve concurrent-runner
        # safety (the outer ``_migrate`` clobbers schema_version after each
        # migration_fn return, so the schema fingerprint is the stable
        # idempotency signal under this race).
        if _v14_schema_already_applied(conn):
            conn.rollback()
            return

        # ------------------------------------------------------------------
        # Step 4: Pre-flight gates (FR-MR.6)
        # ------------------------------------------------------------------
        # Gate 1: schema_version == 13 (codebase analogue per Migration 13
        # docstring TD-6 — _metadata.schema_version is the source of truth).
        if v_row is None:
            raise MigrationError(
                "Migration 14 requires schema_version=13; current=None. "
                "Run prior migrations first."
            )
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise MigrationError(
                "Migration 14 requires schema_version=13; "
                f"current={v_row[0]!r} (unparseable). "
                "Run prior migrations first."
            ) from exc
        if current_version != 13:
            raise MigrationError(
                f"Migration 14 requires schema_version=13; "
                f"current={current_version}. Run prior migrations first."
            )

        # Gate 2-4: table-presence checks.
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "entity_display" not in tables:
            raise MigrationError(
                "Migration 14 requires entity_display table (feature 110). "
                "Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-110 deferred remediation)."
            )
        if "migration_audit_log" not in tables:
            raise MigrationError(
                "Migration 14 requires migration_audit_log table "
                "(feature 110). Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12 (feature-110 deferred remediation)."
            )
        if "entity_relations" in tables:
            # Racer short-circuit at step 3 should have caught the
            # concurrent-runner case; reaching this branch means
            # entity_relations exists WITHOUT the rest of v14 DDL — an
            # unexpected partial-prior-run state. AC-MR.5 pins the message.
            raise MigrationError(
                "Migration 14 entity_relations table already exists. "
                "Drop or replay-detect."
            )

        # ------------------------------------------------------------------
        # Step 5a: CREATE entity_relations + 3 indices (FR-MR.1).
        # ------------------------------------------------------------------
        conn.execute("""
            CREATE TABLE entity_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_uuid TEXT NOT NULL,
                to_uuid TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('fixes')),
                created_at TEXT NOT NULL,
                FOREIGN KEY (from_uuid) REFERENCES entities(uuid)
                    ON DELETE CASCADE,
                FOREIGN KEY (to_uuid) REFERENCES entities(uuid)
                    ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE UNIQUE INDEX idx_entity_relations_unique "
            "ON entity_relations(from_uuid, to_uuid, kind)"
        )
        conn.execute(
            "CREATE INDEX idx_entity_relations_from "
            "ON entity_relations(from_uuid)"
        )
        conn.execute(
            "CREATE INDEX idx_entity_relations_to "
            "ON entity_relations(to_uuid)"
        )

        # ------------------------------------------------------------------
        # Step 5b: Task lifecycle_class remap (FR-MR.5).
        # ------------------------------------------------------------------
        # Operational no-op per spec Pin I (0 task entities in production
        # live DB). Test fixtures exercise the remap path. Restricted to
        # rows that still hold the legacy work_flow tag so a re-run remains
        # idempotent against rows already at task_flow.
        conn.execute(
            "UPDATE entities SET lifecycle_class = 'task_flow' "
            "WHERE kind = 'task' AND lifecycle_class = 'work_flow'"
        )

        # ------------------------------------------------------------------
        # Step 5c: Copy-rename entities to widen (type, kind) CHECK (FR-MR.2).
        # ------------------------------------------------------------------
        _copy_rename_entities_for_v14(conn)

        # ------------------------------------------------------------------
        # Step 5d: Copy-rename phase_events to widen event_type CHECK (FR-MR.3).
        # ------------------------------------------------------------------
        _copy_rename_phase_events_for_v14(conn)

        # ------------------------------------------------------------------
        # Step 6: Pre-commit FK check (in-transaction).
        # ------------------------------------------------------------------
        in_tx_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if in_tx_fk:
            raise MigrationError(
                f"Migration 14 in-transaction FK check non-empty: {in_tx_fk}"
            )

        # ------------------------------------------------------------------
        # Step 7: Stamp schema_version=14 + audit log entry.
        # ------------------------------------------------------------------
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '14')"
        )
        _append_migration_audit_log(
            conn,
            version=14,
            event_type="success",
            payload={"feature": "111-issue-lifecycle-closure"},
        )

        # ------------------------------------------------------------------
        # Step 8: COMMIT.
        # ------------------------------------------------------------------
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        # Re-enable FKs whether success or failure.
        conn.execute("PRAGMA foreign_keys = ON")

    # ----------------------------------------------------------------------
    # Post-transaction defensive FK check.
    # ----------------------------------------------------------------------
    post_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_fk:
        raise MigrationError(
            f"Migration 14 post-FK check non-empty: {post_fk}"
        )


def _copy_rename_entities_to_v13(conn: sqlite3.Connection) -> None:
    """Migration 14 reverse helper — narrow entities (type, kind) CHECK
    back to the pre-feature-111 enum.

    Mirror image of :func:`_copy_rename_entities_for_v14` — work-kind enum
    becomes:
        'feature','backlog','initiative','objective','key_result','task'
    (no 'bug').

    Caller (``_migration_14_down``) is responsible for the FR-MR.9
    pre-flight (no kind='bug' rows survive) — INSERT-SELECT into the
    narrowed CHECK would otherwise fail.
    """
    entities_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='entities'"
    ).fetchone()
    entities_sql = entities_sql_row[0] if entities_sql_row else ""
    # Idempotency probe: if 'bug' (quoted) is absent, the narrowing already
    # happened.
    if "'bug'" not in (entities_sql or ""):
        return

    pre_count = conn.execute(
        "SELECT COUNT(*) FROM entities"
    ).fetchone()[0]

    saved_indexes = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='entities' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    saved_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='entities' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    cross_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' "
            "AND tbl_name <> 'entities' "
            "AND sql LIKE '%entities%' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for trg_name, _ in cross_triggers:
        conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

    conn.execute("""
        CREATE TABLE entities_new (
            uuid           TEXT NOT NULL PRIMARY KEY,
            workspace_uuid TEXT NOT NULL
                           REFERENCES workspaces(uuid),
            type_id        TEXT NOT NULL,
            entity_id      TEXT NOT NULL,
            name           TEXT NOT NULL,
            status         TEXT,
            parent_uuid    TEXT REFERENCES entities_new(uuid),
            artifact_path  TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            metadata       TEXT,
            type           TEXT NOT NULL DEFAULT 'work',
            kind           TEXT NOT NULL DEFAULT 'feature',
            lifecycle_class TEXT NOT NULL DEFAULT 'feature_flow',
            UNIQUE(workspace_uuid, type_id),
            CHECK (
                (type='workspace' AND kind='workspace') OR
                (type='brainstorm' AND kind='brainstorm') OR
                (type='container' AND kind='project') OR
                (type='work' AND kind IN (
                    'feature','backlog','initiative','objective','key_result','task'
                ))
            )
        )
    """)

    col_list_sql = ",".join(_V14_ENTITIES_COLUMNS)
    conn.execute(
        f"INSERT INTO entities_new ({col_list_sql}) "
        f"SELECT {col_list_sql} FROM entities"
    )
    post_count = conn.execute(
        "SELECT COUNT(*) FROM entities_new"
    ).fetchone()[0]
    if post_count != pre_count:
        raise MigrationError(
            f"Migration 14 down entities narrow row-count mismatch: "
            f"pre={pre_count}, post={post_count}"
        )

    conn.execute("DROP TABLE entities")
    conn.execute("PRAGMA legacy_alter_table = OFF")
    conn.execute("ALTER TABLE entities_new RENAME TO entities")

    for _, idx_sql in saved_indexes:
        if idx_sql:
            conn.execute(idx_sql)
    for _, trg_sql in saved_triggers:
        if trg_sql:
            conn.execute(trg_sql)
    for _, trg_sql in cross_triggers:
        if trg_sql:
            conn.execute(trg_sql)


def _copy_rename_phase_events_to_v13(conn: sqlite3.Connection) -> None:
    """Migration 14 reverse helper — narrow phase_events.event_type CHECK
    back to the pre-feature-111 7-value enum.

    Mirror image of :func:`_copy_rename_phase_events_for_v14`. Drops
    'spawned_child' from the enum.

    Caller (``_migration_14_down``) is responsible for DELETEing
    phase_events rows with event_type='spawned_child' BEFORE invoking this
    helper — otherwise the INSERT-SELECT into the narrowed CHECK fails.
    """
    pe_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='phase_events'"
    ).fetchone()
    pe_sql = pe_sql_row[0] if pe_sql_row else ""
    if "'spawned_child'" not in (pe_sql or ""):
        return

    pe_pre_count = conn.execute(
        "SELECT COUNT(*) FROM phase_events"
    ).fetchone()[0]

    pe_saved_indexes = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name='phase_events' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    pe_saved_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' AND tbl_name='phase_events' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    pe_cross_triggers = [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='trigger' "
            "AND tbl_name <> 'phase_events' "
            "AND sql LIKE '%phase_events%' "
            "AND sql IS NOT NULL"
        ).fetchall()
    ]
    for trg_name, _ in pe_cross_triggers:
        conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

    conn.execute("""
        CREATE TABLE phase_events_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id         TEXT NOT NULL,
            project_id      TEXT NOT NULL,
            phase           TEXT,
            event_type      TEXT NOT NULL CHECK(event_type IN (
                'started', 'completed', 'skipped', 'backward',
                'entity_created', 'entity_status_changed',
                'entity_promoted'
            )),
            timestamp       TEXT NOT NULL,
            iterations      INTEGER,
            reviewer_notes  TEXT,
            backward_reason TEXT,
            backward_target TEXT,
            source          TEXT NOT NULL DEFAULT 'live' CHECK(
                source IN ('live', 'backfill')
            ),
            created_at      TEXT NOT NULL,
            metadata        TEXT
        )
    """)

    conn.execute(
        "INSERT INTO phase_events_new "
        "(id, type_id, project_id, phase, event_type, timestamp, "
        "iterations, reviewer_notes, backward_reason, "
        "backward_target, source, created_at, metadata) "
        "SELECT id, type_id, project_id, phase, event_type, "
        "timestamp, iterations, reviewer_notes, backward_reason, "
        "backward_target, source, created_at, metadata "
        "FROM phase_events"
    )
    pe_post_count = conn.execute(
        "SELECT COUNT(*) FROM phase_events_new"
    ).fetchone()[0]
    if pe_post_count != pe_pre_count:
        raise MigrationError(
            f"Migration 14 down phase_events narrow row-count mismatch: "
            f"pre={pe_pre_count}, post={pe_post_count}"
        )

    conn.execute("DROP TABLE phase_events")
    conn.execute(
        "ALTER TABLE phase_events_new RENAME TO phase_events"
    )

    for _, idx_sql in pe_saved_indexes:
        if idx_sql:
            conn.execute(idx_sql)
    for _, trg_sql in pe_saved_triggers:
        if trg_sql:
            conn.execute(trg_sql)
    for _, trg_sql in pe_cross_triggers:
        if trg_sql:
            conn.execute(trg_sql)


def _migration_14_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 14 (feature 111 FR-MR.7 / FR-MR.9).

    Order (mirror of up-migration):
      0. Pre-flight refuse on bug entities or entity_relations rows.
      1. DROP entity_relations + 3 indices.
      2. DELETE phase_events WHERE event_type='spawned_child' (destructive
         after pre-flight — caller waved the safety per AC-MR.7 docstring
         contract).
      3. Copy-rename phase_events to narrowed CHECK.
      4. Copy-rename entities to narrowed CHECK.
      5. Revert task lifecycle_class remap (task_flow → work_flow).
      6. Stamp schema_version back to 13.

    Caller MUST additionally revert source-code changes to
    ``VALID_ENTITY_TYPES``, ``_KIND_TO_TYPE_LIFECYCLE``, ``_CLOSES_TERMINAL``,
    and the feature-111 exception classes (these live in source code per
    Group B and are reverted only by reverting that commit). Same precedent
    as features 109/110 down-migrations (which similarly omit Python-
    constant reversion).
    """
    # ----------------------------------------------------------------------
    # Step 0: FR-MR.9 pre-flight refuse.
    # ----------------------------------------------------------------------
    # Refuse if any kind='bug' entities or entity_relations rows exist;
    # CHECK narrowing would otherwise fail mid-copy-rename.
    bug_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE kind='bug'"
    ).fetchone()[0]
    rel_count = conn.execute(
        "SELECT COUNT(*) FROM entity_relations"
    ).fetchone()[0]
    if bug_count > 0 or rel_count > 0:
        raise MigrationError(
            f"Cannot down-migrate v14: {bug_count} bug entities + "
            f"{rel_count} entity_relations rows exist. "
            "Delete or remap before down-migration."
        )

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Concurrent re-check guard.
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise MigrationError(
                "Migration 14 reverse: _metadata.schema_version missing"
            )
        try:
            current_version = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise MigrationError(
                f"Migration 14 reverse: invalid schema_version "
                f"{v_row[0]!r}"
            ) from exc
        if current_version <= 13:
            # Already at or below 13 → no-op early-return.
            conn.rollback()
            return

        # ------------------------------------------------------------------
        # Step 1: Drop entity_relations + 3 indices.
        # ------------------------------------------------------------------
        conn.execute("DROP INDEX IF EXISTS idx_entity_relations_to")
        conn.execute("DROP INDEX IF EXISTS idx_entity_relations_from")
        conn.execute("DROP INDEX IF EXISTS idx_entity_relations_unique")
        conn.execute("DROP TABLE IF EXISTS entity_relations")

        # ------------------------------------------------------------------
        # Step 2: Delete spawned_child phase_events (destructive after
        #          FR-MR.9 pre-flight per AC-MR.7 docstring).
        # ------------------------------------------------------------------
        conn.execute(
            "DELETE FROM phase_events WHERE event_type = 'spawned_child'"
        )

        # ------------------------------------------------------------------
        # Step 3: Copy-rename phase_events back to 7-event_type CHECK.
        # ------------------------------------------------------------------
        _copy_rename_phase_events_to_v13(conn)

        # ------------------------------------------------------------------
        # Step 4: Copy-rename entities back to 6-work-kind CHECK.
        # ------------------------------------------------------------------
        _copy_rename_entities_to_v13(conn)

        # ------------------------------------------------------------------
        # Step 5: Revert task lifecycle_class remap.
        # ------------------------------------------------------------------
        conn.execute(
            "UPDATE entities SET lifecycle_class = 'work_flow' "
            "WHERE kind = 'task' AND lifecycle_class = 'task_flow'"
        )

        # Audit log entry (best-effort — migration_audit_log may have
        # been dropped by a prior _migration_13_entity_display_down call,
        # but at v14→v13 it's still present per FR-MR.6 pre-flight).
        _append_migration_audit_log(
            conn,
            version=14,
            event_type="down",
            payload={"feature": "111-issue-lifecycle-closure"},
        )

        # ------------------------------------------------------------------
        # Step 6: Stamp schema_version back to 13.
        # ------------------------------------------------------------------
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '13')"
        )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


# Feature 115 C10-115.3: Migration 15 — initialize audit_emit_failed_count.
def _migration_15_audit_emit_counter(conn: sqlite3.Connection) -> None:
    """Initialize the audit_emit_failed_count counter to 0.

    Per spec FR-C.3: counter is touched only by the FR-C-115.1 fail-open
    emit path in db.update_entity (on emit failure). Migration 15 is the
    ONLY initializer; subsequent migrations MUST NOT touch this key
    (enforced by check_audit_counter_write_path AST check, C10-115.4).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
            ("audit_emit_failed_count", "0"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES (?, ?)",
            ("schema_version", "15"),
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def _migration_15_audit_emit_counter_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 15: remove counter and stamp schema_version=14."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM _metadata WHERE key='audit_emit_failed_count'")
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '14')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# Feature 115 FR-Migrations-115.2: Migration 16 is a NO-OP STUB.
# 114 spec Pin O originally reserved M16 = hash-unify, but 114 deferred B-H4
# entirely and 115 placed hash-unify at memory.db M6 instead. This entities.db
# slot is kept as a no-op for migration-runner contiguity (runner uses
# range(current+1, target+1) at database.py forward dispatcher; vacating M16
# would raise KeyError when upgrading past it).
def _migration_16_reserved(conn: sqlite3.Connection) -> None:
    """Reserved during 115 planning; intentionally empty body.

    The migration runner stamps schema_version=16 immediately after this
    function returns. No schema work is performed.
    """
    pass


def _migration_16_reserved_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 16: no schema change to undo, but MUST stamp 15 in-tx
    per the down-migration framework's defensive guard.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '15')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# Feature 115 C13-115.2: Migration 17 — cross_workspace_allowlist table.
# Per 114 spec FR-E.2.1 schema; supports E.2 triage tool grandfathering.
def _migration_17_cross_workspace_allowlist(conn: sqlite3.Connection) -> None:
    """Create the cross_workspace_allowlist table for 115 Cluster E.2.

    Schema per 114 spec FR-E.2.1. CASCADE FKs on entity delete: allowlist
    rows auto-remove when an entity is deleted (documented trade-off — if
    the entity is recreated with the same uuid, operator must re-grandfather).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_workspace_allowlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_uuid TEXT NOT NULL,
                child_uuid TEXT NOT NULL,
                reason TEXT NOT NULL,
                grandfathered_by TEXT NOT NULL DEFAULT 'operator',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(parent_uuid, child_uuid),
                FOREIGN KEY (parent_uuid) REFERENCES entities(uuid) ON DELETE CASCADE,
                FOREIGN KEY (child_uuid) REFERENCES entities(uuid) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '17')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def _migration_17_cross_workspace_allowlist_down(conn: sqlite3.Connection) -> None:
    """Reverse Migration 17: DROP TABLE + stamp schema_version=16."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DROP TABLE IF EXISTS cross_workspace_allowlist")
        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '16')"
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# Feature 124 (C-124.1): Migration 18 — unify the dependency store.
# Widens entity_relations.kind to admit 'blocks', copies entity_dependencies
# rows + resolvable depends_on_features metadata refs into it as blocks
# rows, then drops entity_dependencies. FORWARD-ONLY — no MIGRATIONS_DOWN
# entry (see the carve-out on the comment above MIGRATIONS_DOWN): unifying
# two stores into one is lossy at the table-drop step, so un-dropping is
# not implementable. 132 owns the physical v2 cutover.
def _migration_18_unify_dependency_store(conn: sqlite3.Connection) -> None:
    """Migration 18 — unify entity_dependencies into entity_relations.

    Four steps in ONE ``BEGIN IMMEDIATE`` / single ``COMMIT`` (a step-1-only
    commit would strand a half-applied run):

    1. Copy-rename rebuild of ``entity_relations`` widening
       ``CHECK(kind IN ('fixes'))`` to ``CHECK(kind IN ('fixes', 'blocks'))``.
       Mirrors the :func:`_copy_rename_entities_for_v14` idiom: capture
       indices, rebuild with the widened CHECK, INSERT-SELECT all rows
       (byte-identical columns otherwise), drop old, rename new, recreate
       indices.
    2. Unification copy: every ``entity_dependencies`` row becomes a
       ``blocks`` row — ``from_uuid = blocked_by_uuid`` (the blocker),
       ``to_uuid = entity_uuid`` (the blocked). Rows whose either uuid is
       missing from ``entities`` (the old table has no FK) are skipped
       with a stderr note each; self-edges
       (``entity_uuid == blocked_by_uuid``) are also skipped with a note
       (the guarded ``DependencyManager`` path rejects self-deps via
       ``check_dependency_cycle``, but this raw copy bypasses it).
    3. ``depends_on_features`` metadata materialization: for every entity
       whose metadata carries the key, resolve each ``feature:{id}-{slug}``
       ref to a uuid within the SAME workspace and ``INSERT OR IGNORE`` a
       ``blocks`` row (same self-edge filter). Unresolvable refs warn to
       stderr; metadata is left untouched (audit trail).
    4. ``DROP TABLE entity_dependencies`` (+ its 2 indices). Migration 6's
       CREATE (this file, Step 7 of ``_schema_expansion_v6``) is untouched.

    Pragma bracketing per the Migration 14 ``finally`` idiom:
    ``foreign_keys=OFF`` (verified) BEFORE ``BEGIN IMMEDIATE``;
    ``foreign_key_check`` pre-commit inside the transaction;
    ``foreign_keys=ON`` restored in a ``finally`` AFTER the single COMMIT;
    defensive post-transaction ``foreign_key_check``.

    Replay-safe: the fingerprint is ``entity_dependencies`` ABSENT from
    ``sqlite_master`` — only true after step 4 completes, so probing it
    before this function does any work reflects genuine completion (unlike
    a CHECK-based fingerprint, which would already be set after step 1).

    Forward-only: no reverse migration is registered for 18 (unification
    is lossy at the table-drop step — un-dropping is not implementable).
    """
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "entity_dependencies" not in tables:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_status != 0:
        raise MigrationError(
            "PRAGMA foreign_keys = OFF did not take effect — "
            "aborting migration 18"
        )

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Racer-tolerant re-check: a concurrent peer may have completed
        # migration 18 between our table probe and BEGIN IMMEDIATE
        # acquisition.
        tables_in_tx = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "entity_dependencies" not in tables_in_tx:
            conn.rollback()
            return

        # --------------------------------------------------------------
        # Step 1: Copy-rename rebuild of entity_relations, widening the
        # kind CHECK to admit 'blocks'.
        # --------------------------------------------------------------
        saved_indexes = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='entity_relations' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]

        src_cols = [
            r[1] for r in conn.execute(
                "PRAGMA table_info(entity_relations)"
            ).fetchall()
        ]
        expected_cols = {"id", "from_uuid", "to_uuid", "kind", "created_at"}
        if set(src_cols) != expected_cols:
            raise MigrationError(
                "Migration 18 entity_relations copy-rename: column-set "
                f"mismatch. found={src_cols!r}"
            )

        conn.execute("""
            CREATE TABLE entity_relations_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_uuid TEXT NOT NULL,
                to_uuid TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('fixes', 'blocks')),
                created_at TEXT NOT NULL,
                FOREIGN KEY (from_uuid) REFERENCES entities(uuid)
                    ON DELETE CASCADE,
                FOREIGN KEY (to_uuid) REFERENCES entities(uuid)
                    ON DELETE CASCADE
            )
        """)
        conn.execute(
            "INSERT INTO entity_relations_new "
            "(id, from_uuid, to_uuid, kind, created_at) "
            "SELECT id, from_uuid, to_uuid, kind, created_at "
            "FROM entity_relations"
        )
        conn.execute("DROP TABLE entity_relations")
        conn.execute("PRAGMA legacy_alter_table = OFF")
        conn.execute(
            "ALTER TABLE entity_relations_new RENAME TO entity_relations"
        )
        for _, idx_sql in saved_indexes:
            if idx_sql:
                conn.execute(idx_sql)

        # --------------------------------------------------------------
        # Step 2: Unification copy from entity_dependencies.
        # --------------------------------------------------------------
        migration_ts = datetime.now(timezone.utc).isoformat()

        orphan_rows = conn.execute(
            "SELECT ed.entity_uuid, ed.blocked_by_uuid "
            "FROM entity_dependencies ed "
            "LEFT JOIN entities e1 ON e1.uuid = ed.entity_uuid "
            "LEFT JOIN entities e2 ON e2.uuid = ed.blocked_by_uuid "
            "WHERE e1.uuid IS NULL OR e2.uuid IS NULL"
        ).fetchall()
        for entity_uuid, blocked_by_uuid in orphan_rows:
            print(
                "[migration-18] skipping orphan entity_dependencies row "
                f"entity_uuid={entity_uuid!r} "
                f"blocked_by_uuid={blocked_by_uuid!r} "
                "(uuid not found in entities)",
                file=sys.stderr,
            )

        self_edge_rows = conn.execute(
            "SELECT ed.entity_uuid FROM entity_dependencies ed "
            "JOIN entities e ON e.uuid = ed.entity_uuid "
            "WHERE ed.entity_uuid = ed.blocked_by_uuid"
        ).fetchall()
        for (self_uuid,) in self_edge_rows:
            print(
                "[migration-18] skipping self-edge entity_dependencies "
                f"row uuid={self_uuid!r}",
                file=sys.stderr,
            )

        conn.execute(
            "INSERT OR IGNORE INTO entity_relations "
            "(from_uuid, to_uuid, kind, created_at) "
            "SELECT ed.blocked_by_uuid, ed.entity_uuid, 'blocks', ? "
            "FROM entity_dependencies ed "
            "JOIN entities e1 ON e1.uuid = ed.entity_uuid "
            "JOIN entities e2 ON e2.uuid = ed.blocked_by_uuid "
            "WHERE ed.entity_uuid != ed.blocked_by_uuid",
            (migration_ts,),
        )

        # --------------------------------------------------------------
        # Step 3: depends_on_features metadata materialization.
        # --------------------------------------------------------------
        from entity_registry.metadata import parse_metadata

        meta_rows = conn.execute(
            "SELECT uuid, workspace_uuid, type_id, metadata FROM entities "
            "WHERE metadata LIKE '%depends_on_features%'"
        ).fetchall()
        for entity_uuid, workspace_uuid, type_id, raw_metadata in meta_rows:
            meta = parse_metadata(raw_metadata)
            refs = meta.get("depends_on_features") or []
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if not isinstance(ref, str):
                    continue
                ref_row = conn.execute(
                    "SELECT uuid FROM entities "
                    "WHERE type_id = ? AND workspace_uuid = ?",
                    (ref, workspace_uuid),
                ).fetchone()
                if ref_row is None:
                    print(
                        "[migration-18] unresolvable depends_on_features "
                        f"ref {ref!r} on entity {type_id!r} "
                        f"({entity_uuid}) — metadata left intact",
                        file=sys.stderr,
                    )
                    continue
                resolved_uuid = ref_row[0]
                if resolved_uuid == entity_uuid:
                    print(
                        "[migration-18] skipping self-referential "
                        f"depends_on_features ref {ref!r} on entity "
                        f"{type_id!r} ({entity_uuid})",
                        file=sys.stderr,
                    )
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO entity_relations "
                    "(from_uuid, to_uuid, kind, created_at) "
                    "VALUES (?, ?, 'blocks', ?)",
                    (resolved_uuid, entity_uuid, migration_ts),
                )

        # --------------------------------------------------------------
        # Step 4: Drop the legacy entity_dependencies table + indices.
        # --------------------------------------------------------------
        conn.execute("DROP INDEX IF EXISTS idx_ed_entity_uuid")
        conn.execute("DROP INDEX IF EXISTS idx_ed_blocked_by_uuid")
        conn.execute("DROP TABLE entity_dependencies")

        # --------------------------------------------------------------
        # Pre-commit FK check (in-transaction).
        # --------------------------------------------------------------
        in_tx_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if in_tx_fk:
            raise MigrationError(
                f"Migration 18 in-transaction FK check non-empty: {in_tx_fk}"
            )

        conn.execute(
            "INSERT OR REPLACE INTO _metadata (key, value) "
            "VALUES ('schema_version', '18')"
        )

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    post_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    if post_fk:
        raise MigrationError(
            f"Migration 18 post-FK check non-empty: {post_fk}"
        )


# Feature 124 (Task 2 addendum, D3): Migration 19 — widen phase_events'
# event_type CHECK to admit 'cascade_ready'. D3 pins the cascade flip's
# atomic record as a phase_events row with event_type='cascade_ready'
# (from_value/to_value/actor carried in metadata, mirroring the
# entity_status_changed convention); the live CHECK (widened to 8 values by
# Migration 14's _copy_rename_phase_events_for_v14) does not admit it, and
# SQLite CHECKs are immutable in place. Forward-only (no MIGRATIONS_DOWN
# entry): a pure widen has no data to lose, and 132 owns the physical v2
# cutover -- adding a reverse here would touch the MIGRATIONS_DOWN keys
# pin (test_database.py) for no functional benefit, mirroring Migration
# 18's own forward-only precedent.
def _migration_19_widen_phase_events_cascade_ready(
    conn: sqlite3.Connection,
) -> None:
    """Migration 19 — widen phase_events.event_type CHECK to admit
    'cascade_ready'.

    Mirrors the Migration 14 copy-rename idiom
    (_copy_rename_phase_events_for_v14, database.py:4637): capture indexes
    + triggers, rebuild with the widened CHECK (9 values, adds
    'cascade_ready'), INSERT-SELECT all rows (byte-identical columns;
    the m18-style column-set pre-flight assertion is intentionally omitted
    -- phase_events' shape is stable and the explicit column list fails
    loudly on mismatch),
    DROP old, RENAME new, recreate indexes + triggers. No FK pragma
    bracketing needed -- phase_events carries no FK constraints (unlike
    Migration 18's entity_relations rebuild).

    Replay-safe: probes sqlite_master for a `'cascade_ready'` substring in
    the phase_events CHECK SQL; if present, a prior interrupted attempt
    already completed the rebuild -- skip.
    """
    pe_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='phase_events'"
    ).fetchone()
    if "'cascade_ready'" in (pe_sql_row[0] if pe_sql_row else ""):
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Racer-tolerant re-check: a concurrent peer may have completed
        # migration 19 between our probe and BEGIN IMMEDIATE acquisition.
        pe_sql_row_tx = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='phase_events'"
        ).fetchone()
        if "'cascade_ready'" in (pe_sql_row_tx[0] if pe_sql_row_tx else ""):
            conn.rollback()
            return

        pe_pre_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        pe_saved_indexes = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='phase_events' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        pe_saved_triggers = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' AND tbl_name='phase_events' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        pe_cross_triggers = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' "
                "AND tbl_name <> 'phase_events' "
                "AND sql LIKE '%phase_events%' "
                "AND sql IS NOT NULL"
            ).fetchall()
        ]
        for trg_name, _ in pe_cross_triggers:
            conn.execute(f"DROP TRIGGER IF EXISTS {trg_name}")

        conn.execute("""
            CREATE TABLE phase_events_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id         TEXT NOT NULL,
                project_id      TEXT NOT NULL,
                phase           TEXT,
                event_type      TEXT NOT NULL CHECK(event_type IN (
                    'started', 'completed', 'skipped', 'backward',
                    'entity_created', 'entity_status_changed',
                    'entity_promoted', 'spawned_child', 'cascade_ready'
                )),
                timestamp       TEXT NOT NULL,
                iterations      INTEGER,
                reviewer_notes  TEXT,
                backward_reason TEXT,
                backward_target TEXT,
                source          TEXT NOT NULL DEFAULT 'live' CHECK(
                    source IN ('live', 'backfill')
                ),
                created_at      TEXT NOT NULL,
                metadata        TEXT
            )
        """)

        conn.execute(
            "INSERT INTO phase_events_new "
            "(id, type_id, project_id, phase, event_type, timestamp, "
            "iterations, reviewer_notes, backward_reason, "
            "backward_target, source, created_at, metadata) "
            "SELECT id, type_id, project_id, phase, event_type, "
            "timestamp, iterations, reviewer_notes, backward_reason, "
            "backward_target, source, created_at, metadata "
            "FROM phase_events"
        )
        pe_post_count = conn.execute(
            "SELECT COUNT(*) FROM phase_events_new"
        ).fetchone()[0]
        if pe_post_count != pe_pre_count:
            raise MigrationError(
                f"Migration 19 phase_events copy-rename row-count "
                f"mismatch: pre={pe_pre_count}, post={pe_post_count}"
            )

        conn.execute("DROP TABLE phase_events")
        conn.execute("ALTER TABLE phase_events_new RENAME TO phase_events")

        for _, idx_sql in pe_saved_indexes:
            if idx_sql:
                conn.execute(idx_sql)
        for _, trg_sql in pe_saved_triggers:
            if trg_sql:
                conn.execute(trg_sql)
        for _, trg_sql in pe_cross_triggers:
            if trg_sql:
                conn.execute(trg_sql)

        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


def _upsert_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert one ``_metadata`` key/value pair (ON CONFLICT DO UPDATE).

    Feature 132 #062: a plain ``INSERT OR IGNORE`` would silently skip a
    version bump against an existing cell. Takes a raw connection (not an
    ``EntityDatabase`` instance) so both schema generations' stamp-write
    sites share this one implementation: ``EntityDatabase._migrate()``'s
    per-version write (v1, below) and the v2 rebuild tool's
    staging-connection generation stamp (``entity_registry.rebuild_tool``,
    design 132 D1 step 3).
    """
    conn.execute(
        "INSERT INTO _metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


# Ordered mapping of version -> migration function.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_initial_schema,
    2: _migrate_to_uuid_pk,
    3: _create_workflow_phases_table,
    4: _create_fts_index,
    5: _expand_workflow_phase_check,
    6: _schema_expansion_v6,
    7: _fix_fts_content_mode,
    8: _add_project_scoping,
    9: _migration_9_remove_create_tasks,
    10: _migration_10_phase_events,
    11: _migration_11_workspace_identity,
    12: _migration_12_polymorphic_taxonomy_and_events,
    13: _migration_13_entity_display,
    14: _migration_14_issue_lifecycle_closure,
    15: _migration_15_audit_emit_counter,
    16: _migration_16_reserved,
    17: _migration_17_cross_workspace_allowlist,
    18: _migration_18_unify_dependency_store,
    19: _migration_19_widen_phase_events_cascade_ready,
}

# Reverse-migration registry (FR-8 / design §6.7). Migrations 1-10 are
# forward-only; calling _migrate_down() with target_version < 10 raises
# NotImplementedError. Schema versions 11-17 are reversible; 18 is
# forward-only (unifying entity_dependencies into entity_relations is lossy
# at the table-drop step — un-dropping is not implementable; 132 owns the
# physical v2 cutover).
MIGRATIONS_DOWN: dict[int, Callable[[sqlite3.Connection], None]] = {
    11: _migration_11_workspace_identity_down,
    12: _migration_12_polymorphic_taxonomy_and_events_down,
    13: _migration_13_entity_display_down,
    14: _migration_14_down,
    15: _migration_15_audit_emit_counter_down,
    16: _migration_16_reserved_down,
    17: _migration_17_cross_workspace_allowlist_down,
}


def _migrate_down(conn: sqlite3.Connection, target_version: int) -> None:
    """Reverse-migration dispatcher (test-only in this feature).

    Iterates ``MIGRATIONS_DOWN`` keys in **descending** order, applying each
    reverse migration until ``_metadata.schema_version == target_version``.

    Each reverse migration manages its own transaction (BEGIN IMMEDIATE /
    COMMIT) and stamps the new (lower) schema_version INSIDE that transaction
    — mirroring the forward Migration 10 / Migration 11 pattern.

    Currently only schema_version 11 is reversible. Calling with
    ``target_version < 10`` raises ``NotImplementedError`` naming the missing
    reverse migration.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    target_version:
        Desired post-reverse schema_version. Must be >= the smallest
        reversible version - 1 (i.e., 10 currently).

    Raises
    ------
    NotImplementedError
        If a reverse migration would be required for a version that has
        no entry in ``MIGRATIONS_DOWN``.
    """
    while True:
        v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if v_row is None:
            raise RuntimeError(
                "_migrate_down: _metadata.schema_version missing"
            )
        try:
            current = int(v_row[0])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"_migrate_down: invalid schema_version {v_row[0]!r}"
            ) from exc
        if current <= target_version:
            return
        # Need to reverse from `current` -> `current - 1`.
        if current not in MIGRATIONS_DOWN:
            raise NotImplementedError(
                f"Reverse migration for schema_version {current} not "
                "implemented"
            )
        MIGRATIONS_DOWN[current](conn)
        # After each reverse migration the version must be lower; if not,
        # something is wrong with the reverse function (it should stamp
        # in-tx). Defensive guard against infinite loop.
        new_v_row = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        if new_v_row is None or int(new_v_row[0]) >= current:
            raise RuntimeError(
                f"_migrate_down: schema_version did not decrement after "
                f"reversing from {current}"
            )

# Sentinel object to distinguish "not provided" from explicit ``None``.
_UNSET = object()

# Export format version — separate from the DB schema version.
EXPORT_SCHEMA_VERSION = 1

# FR-6.2 (feature 088): explicit column list for phase_events SELECTs.
# Replaces ``SELECT *`` so schema evolution cannot silently leak columns.
# Feature 109 Group 8 added ``metadata`` (TEXT NULL) — included here so all
# query paths surface it for the new entity_* event types.
PHASE_EVENTS_COLS = (
    "id, type_id, project_id, phase, event_type, timestamp, "
    "iterations, reviewer_notes, backward_reason, backward_target, "
    "source, created_at, metadata"
)


# Feature 109 Group 9 — per-event-type discriminator validation (design §3.1).
#
# ``_VALID_PARAMS`` enumerates the discriminator kwargs that ARE allowed for
# each event_type. Base parameters (``project_id``, ``source``, ``timestamp``)
# are accepted for every event_type and are NOT listed here.
#
# ``_REQUIRED_PARAMS`` enumerates the subset of discriminator kwargs that
# MUST be present (non-None) for each event_type. Passing one of the keys in
# ``_VALID_PARAMS[event_type]`` but with value None is allowed unless the key
# is also in ``_REQUIRED_PARAMS[event_type]``.
_VALID_PARAMS: dict[str, set[str]] = {
    "started":              {"phase", "iterations", "reviewer_notes"},
    "completed":            {"phase", "iterations", "reviewer_notes"},
    "skipped":              {"phase", "reviewer_notes"},
    "backward":             {"phase", "reviewer_notes",
                             "backward_reason", "backward_target"},
    "entity_created":       {"metadata"},
    "entity_status_changed":{"metadata"},
    "entity_promoted":      {"metadata"},
    # Feature 111 FR-9.3 / FR-MR.3: spawned_child event_type emitted by
    # issue_spawn on the parent (no phase change, only an audit-trail
    # marker with child metadata). NOT added to _REQUIRED_PARAMS — the
    # sole caller (issue_spawn) guarantees metadata application-side; a
    # future non-issue_spawn caller can promote to required when needed
    # (plan-reviewer iter 3 S3 downgrade).
    "spawned_child":        {"metadata"},
    # Feature 124 D3/Migration 19: cascade_ready is the atomic flip record
    # emitted by DependencyManager._evaluate_and_flip (blocked -> ready).
    # metadata carries from_value/to_value/actor -- required, since the
    # event is meaningless without that payload (unlike spawned_child,
    # which has exactly one caller that already guarantees it).
    "cascade_ready":        {"metadata"},
}
_REQUIRED_PARAMS: dict[str, set[str]] = {
    "started":              {"phase"},
    "completed":            {"phase", "iterations"},
    "skipped":              {"phase"},
    "backward":             {"phase", "backward_reason", "backward_target"},
    "entity_status_changed":{"metadata"},
    "entity_promoted":      {"metadata"},
    "cascade_ready":        {"metadata"},
}

# Discriminator kwargs visible to validation (must match the union of all
# values in ``_VALID_PARAMS`` plus any historical discriminator). This is
# the closed set the validation logic iterates over.
_DISCRIMINATOR_KWARGS: tuple[str, ...] = (
    "phase", "iterations", "reviewer_notes",
    "backward_reason", "backward_target", "metadata",
)

# Feature 132 D5/D3: the LIVE half of the axis-mapping table design D3
# pins for the backfill (rebuild_tool.py's ``_classify_phase_event``,
# which this mirrors byte-for-byte in rule, not by import -- rebuild_tool.py
# imports FROM this module, so importing back would be circular).
_V2_PHASE_NAMED_EVENT_TYPES = frozenset({"started", "completed", "skipped", "backward"})


def _v2_classify_phase_event(
    kind: str, event_type: str, phase: str | None, metadata: dict | None
) -> tuple[str, str | None]:
    """Route one ``append_phase_event`` call onto its v2 (axis, to_value).

    Phase-named event_types go to the ``pipeline`` axis (122's 6-value
    vocab) for feature-kind entities, ``lifecycle`` (vocab-free) for every
    other kind -- matching FR132-2b / D3's table. Every other event_type
    (``entity_created``, ``entity_status_changed``, ``entity_promoted``,
    ``spawned_child``, ``cascade_ready``) goes to ``lifecycle`` with
    ``to_value`` set to ``metadata['new_status']`` when present, else
    NULL -- NEVER the ``execution`` axis (that axis is backfill-only: the
    one-time ``status_backfilled`` synthesis, D3). Same rule
    rebuild_tool.py's ``_classify_phase_event`` applies to copied rows, so
    a live-written event and a backfilled event of the same shape land on
    the same axis with the same to_value.
    """
    if event_type in _V2_PHASE_NAMED_EVENT_TYPES:
        axis = "pipeline" if kind == "feature" else "lifecycle"
        return axis, phase
    return "lifecycle", (metadata or {}).get("new_status")


# ---------------------------------------------------------------------------
# Custom exception classes (feature 109 FR-3 / FR-4 / TD-4)
# ---------------------------------------------------------------------------
#
# Per design TD-4: custom exceptions live in their domain file (codebase
# precedent — CycleError in dependencies.py, WorkspaceCorruptedError in
# project_identity.py, FrontmatterUUIDMismatch in frontmatter.py). No shared
# ``exceptions.py`` module exists.
#
# Base class is ``ValueError`` because both errors represent semantic-
# validation failures (duplicate key, identity collision), not runtime
# errors.


class EntityExistsError(ValueError):
    """Raised by ``register_entity`` when ``(workspace_uuid, type_id)`` conflict
    occurs (feature 109 FR-4 / AC-4.1 / AC-4.2).

    Replaces the pre-feature-109 silent ``INSERT OR IGNORE`` no-op. Callers
    that need idempotent semantics use ``upsert_entity`` instead.
    """

    def __init__(self, workspace_uuid: str, type_id: str):
        super().__init__(
            f"Entity already exists: workspace_uuid={workspace_uuid!r}, "
            f"type_id={type_id!r}"
        )
        self.workspace_uuid = workspace_uuid
        self.type_id = type_id


class EntityNotFoundError(ValueError):
    """Raised when a referenced entity does not exist (feature 111 FR-EX.1).

    Used by F10 complete_phase(closes=) when:
    - caller's type_id resolves to no entity row (FR-10.2)
    - closure target uuid resolves to no entity row (FR-10.3 step 2)
    """
    pass


class InvalidCloseTargetError(ValueError):
    """Raised when a closure target is structurally incompatible
    (feature 111 FR-EX.2).

    Used by F10 complete_phase(closes=) for:
    - lifecycle_class not in _CLOSES_TERMINAL (FR-10.3 step 3)
    - already terminal with different prior closer (FR-10.3 step 4)
    - already terminal with no prior closer record (FR-10.3 step 4)
    """
    pass


class PromotionConflictError(ValueError):
    """Raised by ``promote_entity`` when the post-promotion ``type_id`` would
    collide with an existing row in the same workspace (feature 109 FR-3 /
    AC-3.6 / AC-4.1).
    """

    def __init__(
        self,
        workspace_uuid: str,
        old_type_id: str,
        new_type_id: str,
    ):
        super().__init__(
            f"Promotion would create a UNIQUE conflict: "
            f"workspace_uuid={workspace_uuid!r}, "
            f"old_type_id={old_type_id!r}, "
            f"new_type_id={new_type_id!r} (already exists)"
        )
        self.workspace_uuid = workspace_uuid
        self.old_type_id = old_type_id
        self.new_type_id = new_type_id


class EntityDatabase:
    """SQLite-backed storage for entity registry.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file, or ``":memory:"`` for an
        in-memory database.
    """

    VALID_ENTITY_TYPES = (
        "backlog", "brainstorm", "project", "feature",
        "initiative", "objective", "key_result", "task",
        # Feature 111 FR-MR.4: new 'bug' kind for spontaneous mid-flight
        # issue capture via issue_spawn MCP.
        "bug",
    )

    def __init__(self, db_path: str, *, check_same_thread: bool = True) -> None:
        self._in_transaction = False
        self._conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=check_same_thread)
        self._conn.row_factory = sqlite3.Row
        self._set_pragmas()
        self._migrate()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _commit(self):
        """Commit unless inside an explicit transaction()."""
        if not self._in_transaction:
            self._conn.commit()

    # ------------------------------------------------------------------
    # Internal: workspace_uuid kwarg resolution (Feature 108 transition)
    # ------------------------------------------------------------------

    def _ensure_unknown_workspace_row(self) -> None:
        """Insert the canonical ``__unknown__`` workspaces row if absent.

        Required so the FK ``entities.workspace_uuid → workspaces.uuid`` is
        satisfiable for entities written via the legacy
        ``project_id='__unknown__'`` alias on a fresh post-Migration-11 DB.
        """
        existing = self._conn.execute(
            "SELECT 1 FROM workspaces WHERE uuid = ?",
            (_UNKNOWN_WORKSPACE_UUID,),
        ).fetchone()
        if existing is None:
            now = self._now_iso()
            self._conn.execute(
                "INSERT INTO workspaces "
                "(uuid, project_id_legacy, project_root, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (_UNKNOWN_WORKSPACE_UUID, "__unknown__", None, now, now),
            )
            self._commit()

    def _validated_provided_workspace_uuid(
        self, workspace_uuid: str, _caller: str
    ) -> str:
        """Confirm a caller-supplied workspace_uuid actually exists.

        Previously a provided uuid was returned unchecked, so an orphaned
        identity (the split-brain: workspace.json points at a uuid with no
        ``workspaces`` row) surfaced only as a bare ``FOREIGN KEY constraint
        failed`` deep in the INSERT. Fail loudly here with a fix that points
        at the recovery path instead.

        The canonical ``__unknown__`` uuid is bootstrapped (not an error) so
        callers that pass it directly behave like the ``project_id`` path.
        """
        if workspace_uuid == _UNKNOWN_WORKSPACE_UUID:
            self._ensure_unknown_workspace_row()
            return workspace_uuid
        # Read-only membership probe — safe inside any open transaction
        # (no BEGIN/COMMIT added here).
        row = self._conn.execute(
            "SELECT 1 FROM workspaces WHERE uuid = ?", (workspace_uuid,)
        ).fetchone()
        if row is None:
            raise ValueError(
                f"{_caller}(): workspace_uuid={workspace_uuid!r} not present "
                f"in the workspaces table — workspace.json/DB split-brain "
                f"detected. Run pd:doctor --fix, then restart the session "
                f"(MCP servers cache the workspace UUID at startup)."
            )
        return workspace_uuid

    def _resolve_workspace_uuid_kwargs(
        self,
        workspace_uuid: str | None,
        project_id: str | None,
        *,
        _caller: str = "register_entity",
    ) -> str:
        """Resolve the (workspace_uuid, project_id) kwarg pair to a canonical
        workspace_uuid.

        Compatibility shim for Feature 108 Migration 11 transition window.

        Resolution rules
        ----------------
        * Both supplied → ``workspace_uuid`` wins; emits DeprecationWarning.
        * Only ``workspace_uuid`` → returned as-is.
        * Only ``project_id == "__unknown__"`` → returns canonical
          ``_UNKNOWN_WORKSPACE_UUID`` and ensures the workspaces row exists.
        * Only ``project_id == "<other>"`` → JOIN on
          ``workspaces.project_id_legacy``; raises if no row matches.
        * Neither → ``ValueError``.

        Returns
        -------
        str
            The resolved workspace_uuid (FK target satisfied).

        Raises
        ------
        ValueError
            If neither kwarg is supplied, or if a non-``__unknown__``
            ``project_id`` cannot be resolved against the workspaces table.
        """
        if workspace_uuid is not None and project_id is not None:
            warnings.warn(
                f"{_caller}() received both workspace_uuid and project_id; "
                f"workspace_uuid wins. project_id is deprecated.",
                DeprecationWarning,
                stacklevel=3,
            )
            return self._validated_provided_workspace_uuid(
                workspace_uuid, _caller
            )
        if workspace_uuid is not None:
            return self._validated_provided_workspace_uuid(
                workspace_uuid, _caller
            )
        if project_id is None:
            raise ValueError(
                f"{_caller}() requires workspace_uuid or project_id"
            )
        # Legacy project_id path
        if project_id == "__unknown__":
            self._ensure_unknown_workspace_row()
            return _UNKNOWN_WORKSPACE_UUID
        row = self._conn.execute(
            "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ValueError(
                f"{_caller}(): project_id={project_id!r} has no matching "
                f"workspaces.project_id_legacy row. Either pass "
                f"workspace_uuid directly or pre-register the workspace."
            )
        return row["uuid"]

    def _resolve_optional_workspace_filter(
        self,
        workspace_uuid: str | None,
        project_id: str | None,
        *,
        _caller: str,
    ) -> str | None:
        """Resolve an optional (workspace_uuid, project_id) scope filter.

        Variant of :meth:`_resolve_workspace_uuid_kwargs` for read paths
        that treat ``None`` as "no scoping" rather than an error. Used by
        ``list_entities``, ``search_entities``, ``_resolve_identifier``,
        ``resolve_ref``, etc.

        Resolution rules
        ----------------
        * Both supplied → ``workspace_uuid`` wins; emits DeprecationWarning.
        * Only ``workspace_uuid`` → returned as-is.
        * Only ``project_id == "__unknown__"`` → canonical
          ``_UNKNOWN_WORKSPACE_UUID`` (workspaces row is read-only here, so
          we do NOT bootstrap it).
        * Only ``project_id == "<other>"`` → JOIN on
          ``workspaces.project_id_legacy``; raises ``ValueError`` if no
          matching row exists.
        * Both ``None`` → returns ``None`` (callers omit the WHERE clause).

        Returns
        -------
        str | None
            Resolved workspace_uuid, or None for "no filter".
        """
        if workspace_uuid is not None and project_id is not None:
            warnings.warn(
                f"{_caller}() received both workspace_uuid and project_id; "
                f"workspace_uuid wins. project_id is deprecated.",
                DeprecationWarning,
                stacklevel=3,
            )
            return workspace_uuid
        if workspace_uuid is not None:
            return workspace_uuid
        if project_id is None:
            return None
        if project_id == "__unknown__":
            return _UNKNOWN_WORKSPACE_UUID
        row = self._conn.execute(
            "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ValueError(
                f"{_caller}(): project_id={project_id!r} has no matching "
                f"workspaces.project_id_legacy row. Either pass "
                f"workspace_uuid directly or pre-register the workspace."
            )
        return row["uuid"]

    # ------------------------------------------------------------------
    # Internal: identifier resolution
    # ------------------------------------------------------------------

    def _resolve_identifier(
        self,
        identifier: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> tuple[str, str]:
        """Resolve a UUID or type_id to a (uuid, type_id) tuple.

        Parameters
        ----------
        identifier:
            Either a UUID string or a type_id string.
        workspace_uuid:
            If provided, restrict type_id lookup to this workspace.
            UUID lookups are unchanged (UUID is globally unique).
            If None, type_id must be globally unique or an ambiguity
            error is raised listing the workspaces that contain it.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        tuple[str, str]
            (uuid, type_id) of the found entity.

        Raises
        ------
        ValueError
            If no entity matches the identifier, or if the type_id
            is ambiguous across workspaces (when neither kwarg is
            provided).
        """
        if _UUID_RE.match(identifier.lower()):
            row = self._conn.execute(
                "SELECT uuid, type_id FROM entities WHERE uuid = ?",
                (identifier.lower(),),
            ).fetchone()
            if row is None:
                raise ValueError(f"Entity not found: {identifier!r}")
            return (row["uuid"], row["type_id"])

        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="_resolve_identifier"
        )

        # type_id path: optionally scoped by workspace_uuid
        if ws_uuid is not None:
            row = self._conn.execute(
                "SELECT uuid, type_id FROM entities "
                "WHERE type_id = ? AND workspace_uuid = ?",
                (identifier, ws_uuid),
            ).fetchone()
            if row is None:
                raise ValueError(f"Entity not found: {identifier!r}")
            return (row["uuid"], row["type_id"])

        # No scope: must be globally unique
        rows = self._conn.execute(
            "SELECT uuid, type_id, workspace_uuid FROM entities "
            "WHERE type_id = ?",
            (identifier,),
        ).fetchall()
        if len(rows) == 0:
            raise ValueError(f"Entity not found: {identifier!r}")
        if len(rows) == 1:
            return (rows[0]["uuid"], rows[0]["type_id"])
        # Ambiguous: list workspaces
        workspaces = [r["workspace_uuid"] for r in rows]
        raise ValueError(
            f"Ambiguous type_id {identifier!r} exists in multiple "
            f"workspaces: {workspaces}. Specify workspace_uuid (or the "
            f"deprecated project_id alias) to disambiguate."
        )

    # ------------------------------------------------------------------
    # UUID lookup and flexible ref resolution (Task 1b.3a)
    # ------------------------------------------------------------------

    def get_entity_by_uuid(self, uuid: str) -> dict | None:
        """Retrieve a single entity by UUID.

        Returns entity dict or None if not found (or input is not a valid UUID).

        Feature 108: enriches the row dict with a resolved ``parent_type_id``
        (looked up via ``parent_uuid``) and ``project_id`` (from
        ``workspaces.project_id_legacy``) so callers retain the legacy fields
        even though Migration 11 dropped the underlying columns.
        """
        row = self._conn.execute(
            "SELECT e.*, e.kind AS entity_type, "
            "p.type_id AS parent_type_id, "
            "w.project_id_legacy AS project_id "
            "FROM entities e "
            "LEFT JOIN entities p ON e.parent_uuid = p.uuid "
            "LEFT JOIN workspaces w ON e.workspace_uuid = w.uuid "
            "WHERE e.uuid = ?",
            (uuid,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Feature 111 helpers — closure-transaction primitives used by F10
    # complete_phase(closes=) and (for resolve_entity_uuid) F9 issue_spawn.
    # ------------------------------------------------------------------

    def get_prior_closer(self, to_uuid: str) -> str | None:
        """Return the ``from_uuid`` of the prior 'fixes' relation to ``to_uuid``,
        or ``None`` if no such relation exists (feature 111 IF-2 step 4).

        Used by F10 complete_phase(closes=) idempotency check to detect
        same-closer replay vs cross-closer conflict (FR-10.3 step 4 /
        FR-10.5).
        """
        row = self._conn.execute(
            "SELECT from_uuid FROM entity_relations "
            "WHERE to_uuid = ? AND kind = 'fixes' LIMIT 1",
            (to_uuid,),
        ).fetchone()
        return row[0] if row is not None else None

    def insert_entity_relation(
        self,
        from_uuid: str,
        to_uuid: str,
        kind: str,
        on_conflict: str = "raise",
    ) -> bool:
        """Insert a row into ``entity_relations`` (feature 111 FR-10.3 step 7).

        Parameters
        ----------
        from_uuid, to_uuid, kind:
            The triple making up the composite UNIQUE on entity_relations.
        on_conflict:
            ``"raise"`` (default) — INSERT without ON CONFLICT; SQLite raises
            ``sqlite3.IntegrityError`` if the composite UNIQUE is violated.
            ``"ignore"`` — append ``ON CONFLICT(from_uuid, to_uuid, kind)
            DO NOTHING`` so the INSERT is idempotent. Returns ``False`` when
            a conflict was skipped, ``True`` when a row was actually inserted.

        Returns
        -------
        bool
            ``True`` if a new row was inserted, ``False`` if the conflict
            branch was taken (``on_conflict='ignore'`` only).
        """
        if on_conflict not in ("raise", "ignore"):
            raise ValueError(
                f"on_conflict must be 'raise' or 'ignore'; got {on_conflict!r}"
            )
        now = self._now_iso()
        sql = (
            "INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, ?, ?)"
        )
        if on_conflict == "ignore":
            sql += " ON CONFLICT(from_uuid, to_uuid, kind) DO NOTHING"
        cur = self._conn.execute(sql, (from_uuid, to_uuid, kind, now))
        # ``rowcount`` is 1 on real insert, 0 when ON CONFLICT DO NOTHING fires.
        return cur.rowcount > 0

    def resolve_entity_uuid(
        self,
        workspace_uuid: str,
        type_id: str,
    ) -> tuple[str | None, str | None]:
        """Resolve ``(workspace_uuid, type_id)`` to ``(uuid, workspace_uuid)``
        (feature 111 IF-2 step 1).

        Returns ``(None, None)`` if no entity matches. Used by F10
        complete_phase(closes=) to resolve the caller's ``from_uuid`` and
        ``caller_workspace_uuid`` before any writes (FR-10.2).
        """
        row = self._conn.execute(
            "SELECT uuid, workspace_uuid FROM entities "
            "WHERE workspace_uuid = ? AND type_id = ?",
            (workspace_uuid, type_id),
        ).fetchone()
        if row is None:
            return (None, None)
        return (row[0], row[1])

    def resolve_ref(
        self,
        ref: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> str:
        """Resolve a flexible reference to a single entity UUID.

        Resolution order:
        1. If ref looks like a UUID (36 chars, has dashes), look up by uuid.
        2. Try as exact type_id (scoped by workspace_uuid if provided).
        3. Try as type_id prefix (scoped by workspace_uuid if provided).
           - Single match: return that uuid.
           - Multiple matches: raise ValueError with candidate list.
           - No matches: raise ValueError.

        Parameters
        ----------
        ref:
            UUID string, full type_id, or type_id prefix.
        workspace_uuid:
            If provided, restrict type_id and prefix lookups to this
            workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        str
            The resolved entity UUID.

        Raises
        ------
        ValueError
            If ref is ambiguous (multiple prefix matches) or not found.
        """
        # 1. Try as UUID (globally unique, scoping not needed)
        if _UUID_RE.match(ref.lower()):
            entity = self.get_entity_by_uuid(ref.lower())
            if entity is not None:
                return entity["uuid"]
            raise ValueError(f"No entity found matching ref: {ref!r}")

        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="resolve_ref"
        )

        # 2. Try as exact type_id
        if ws_uuid is not None:
            row = self._conn.execute(
                "SELECT uuid FROM entities "
                "WHERE type_id = ? AND workspace_uuid = ?",
                (ref, ws_uuid),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT uuid FROM entities WHERE type_id = ?", (ref,)
            ).fetchone()
        if row is not None:
            return row["uuid"]

        # 3. Try as prefix (forward the already-resolved ws_uuid to avoid
        # double-resolution / double-deprecation-warning).
        matches = self.search_by_type_id_prefix(
            ref, workspace_uuid=ws_uuid
        )
        if len(matches) == 1:
            return matches[0]["uuid"]
        if len(matches) > 1:
            candidates = [m["type_id"] for m in matches]
            raise ValueError(
                f"Multiple entities match ref {ref!r}: {candidates}"
            )

        raise ValueError(f"No entity found matching ref: {ref!r}")

    def get_children_by_uuid(self, parent_uuid: str) -> list[dict]:
        """Retrieve all entities whose parent_uuid matches.

        Parameters
        ----------
        parent_uuid:
            The UUID of the parent entity.

        Returns
        -------
        list[dict]
            List of child entity dicts.  Empty list if no children found.
        """
        # F11 (Group 6): project ``kind`` to the legacy ``entity_type`` dict
        # key for caller compatibility (TD-8 public API surface).
        rows = self._conn.execute(
            "SELECT *, kind AS entity_type FROM entities WHERE parent_uuid = ?",
            (parent_uuid,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Prefix search and transaction helpers (Task 1b.3b)
    # ------------------------------------------------------------------

    def search_by_type_id_prefix(
        self,
        prefix: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """Search for entities whose type_id starts with the given prefix.

        Parameters
        ----------
        prefix:
            The type_id prefix to match (e.g. "feature:05").
        workspace_uuid:
            If provided, restrict results to this workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        list[dict]
            List of matching entity dicts.
        """
        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="search_by_type_id_prefix"
        )
        # Use LIKE with escaped prefix for efficient prefix search.
        # Escape backslash first (it's the ESCAPE char), then % and _.
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if ws_uuid is not None:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type_id LIKE ? ESCAPE '\\' "
                "AND workspace_uuid = ?",
                (escaped + "%", ws_uuid),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM entities WHERE type_id LIKE ? ESCAPE '\\'",
                (escaped + "%",),
            ).fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def begin_immediate(self):
        """Context manager that wraps a block in BEGIN IMMEDIATE.

        .. deprecated:: Use ``transaction()`` instead for new code.
            ``transaction()`` supports re-entrancy (safe for nested calls),
            while this method raises RuntimeError on nesting. Specifically:
            - ``transaction()`` inside ``begin_immediate()`` works (re-entrant no-op)
            - ``begin_immediate()`` inside ``transaction()`` raises RuntimeError

        Commits on success, rolls back on exception. Yields the connection.
        Sets ``_in_transaction`` so that ``_commit()`` calls inside the block
        are suppressed (matching ``transaction()`` semantics).

        Usage::

            with db.begin_immediate() as conn:
                conn.execute("UPDATE ...")
        """
        if self._in_transaction:
            raise RuntimeError("Nested transactions not supported")
        self._conn.commit()  # flush pending implicit transactions
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            self._in_transaction = False

    @contextmanager
    def transaction(self):
        """Context manager for atomic multi-step writes.
        Uses BEGIN IMMEDIATE to acquire write lock upfront.
        Suppresses _commit() calls inside the block.
        Re-entrant: if already inside a transaction, yields without
        starting a new one (the outer transaction handles atomicity).
        """
        if self._in_transaction:
            yield
            return
        self._conn.commit()  # flush implicit transactions
        self._conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        try:
            yield
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            self._in_transaction = False

    # ------------------------------------------------------------------
    # Entity tagging (Task 1b.9a)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_tag(tag: str) -> None:
        """Validate tag format: lowercase, hyphens, digits, 1-50 chars."""
        if not tag or not _TAG_RE.match(tag):
            raise ValueError(
                f"Invalid tag {tag!r}: must be 1-50 chars, lowercase "
                f"letters, digits, and hyphens (no leading/trailing hyphens)"
            )

    def add_tag(self, entity_uuid: str, tag: str) -> None:
        """Add a tag to an entity. Idempotent (duplicate is ignored).

        Parameters
        ----------
        entity_uuid:
            UUID of the entity to tag.
        tag:
            Tag string (lowercase, hyphens, max 50 chars).

        Raises
        ------
        ValueError
            If tag format is invalid.
        """
        self._validate_tag(tag)
        self._conn.execute(
            "INSERT OR IGNORE INTO entity_tags (entity_uuid, tag) "
            "VALUES (?, ?)",
            (entity_uuid, tag),
        )
        self._commit()

    def remove_tag(self, entity_uuid: str, tag: str) -> None:
        """Remove a tag from an entity. Silent if tag not present."""
        self._conn.execute(
            "DELETE FROM entity_tags WHERE entity_uuid = ? AND tag = ?",
            (entity_uuid, tag),
        )
        self._commit()

    def get_tags(self, entity_uuid: str) -> list[str]:
        """Return all tags for an entity, sorted alphabetically."""
        rows = self._conn.execute(
            "SELECT tag FROM entity_tags WHERE entity_uuid = ? ORDER BY tag",
            (entity_uuid,),
        ).fetchall()
        return [row["tag"] for row in rows]

    def query_by_tag(self, tag: str) -> list[dict]:
        """Return all entities with a given tag, across all types.

        Parameters
        ----------
        tag:
            The tag to query by.

        Returns
        -------
        list[dict]
            List of entity dicts for entities carrying this tag.
        """
        # F11 (Group 6): project ``e.kind`` to the legacy ``entity_type``
        # dict-key for caller compatibility (TD-8 public API surface).
        rows = self._conn.execute(
            "SELECT e.*, e.kind AS entity_type "
            "FROM entities e "
            "JOIN entity_tags et ON e.uuid = et.entity_uuid "
            "WHERE et.tag = ? "
            "ORDER BY e.kind, e.name",
            (tag,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # OKR alignment (Task 6.5)
    # ------------------------------------------------------------------

    def add_okr_alignment(self, entity_uuid: str, key_result_uuid: str) -> None:
        """Link an entity to a key result for lateral OKR alignment.

        Idempotent (duplicate is ignored via INSERT OR IGNORE).

        Parameters
        ----------
        entity_uuid:
            UUID of the entity to align.
        key_result_uuid:
            UUID of the key_result entity to align with.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO entity_okr_alignment "
            "(entity_uuid, key_result_uuid) VALUES (?, ?)",
            (entity_uuid, key_result_uuid),
        )
        self._commit()

    def remove_okr_alignment(self, entity_uuid: str, key_result_uuid: str) -> None:
        """Remove an OKR alignment. Silent if alignment not present."""
        self._conn.execute(
            "DELETE FROM entity_okr_alignment "
            "WHERE entity_uuid = ? AND key_result_uuid = ?",
            (entity_uuid, key_result_uuid),
        )
        self._commit()

    def get_okr_alignments(self, entity_uuid: str) -> list[dict]:
        """Return all key_result entities aligned to the given entity.

        Parameters
        ----------
        entity_uuid:
            UUID of the entity to query alignments for.

        Returns
        -------
        list[dict]
            List of key_result entity dicts. Empty list if none found.
        """
        # F11 (Group 6): project ``e.kind`` to the legacy ``entity_type``
        # dict-key for caller compatibility (TD-8 public API surface).
        rows = self._conn.execute(
            "SELECT e.*, e.kind AS entity_type "
            "FROM entities e "
            "JOIN entity_okr_alignment eoa ON e.uuid = eoa.key_result_uuid "
            "WHERE eoa.entity_uuid = ? "
            "ORDER BY e.name",
            (entity_uuid,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    # Feature 121 FR-5 / design D2: single source of truth for the
    # blank/whitespace-name rejection message so register_entity,
    # upsert_entity, and update_entity's name branch raise byte-identical
    # text (blank display fields corrupt the registry).
    _BLANK_NAME_ERROR = (
        "entity name must be non-empty "
        "(feature 121 FR-5: blank display fields corrupt the registry)"
    )

    def register_entity(
        self,
        entity_type: str,
        entity_id: str,
        name: str,
        *,
        workspace_uuid: str | None = None,
        project_id: str | None = None,
        artifact_path: str | None = None,
        status: str | None = None,
        parent_uuid: str | None = None,
        parent_type_id: str | None = None,
        metadata: dict | None = None,
        _strict_id_format: bool | None = None,
    ) -> str:
        """Register a new entity. Raises :class:`EntityExistsError` on
        ``(workspace_uuid, type_id)`` conflict.

        Feature 109 FR-4 / AC-4.2: the pre-feature-109 silent
        ``INSERT OR IGNORE`` no-op is removed. Callers that need idempotent
        semantics use :meth:`upsert_entity` instead.

        Feature 110 Group 2 (Task 2.0): ``entity_id`` MUST match the
        ``^\\d+-.+`` regex (numeric prefix + dash + slug suffix) so the
        ``entity_display(uuid, seq, slug)`` table — populated in the same
        transaction — receives a well-formed (seq, slug) tuple. Test fixtures
        that need to bypass this constraint use
        :meth:`_register_entity_no_display`.

        Parameters
        ----------
        entity_type:
            One of the VALID_ENTITY_TYPES (backlog, brainstorm, project,
            feature, initiative, objective, key_result, task).
        entity_id:
            Unique identifier within the entity_type namespace.
        name:
            Human-readable name.
        workspace_uuid:
            Workspace identity for the entity. Post-Migration-11 the entities
            table is keyed on (workspace_uuid, type_id). Required unless the
            deprecated ``project_id`` alias is supplied.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved to a
            workspace_uuid via JOIN on ``workspaces.project_id_legacy``.
            ``"__unknown__"`` maps to the canonical
            ``_UNKNOWN_WORKSPACE_UUID``. Other values without an existing
            workspaces row will raise ``ValueError``.
        artifact_path:
            Optional filesystem path to the entity's artifact.
        status:
            Optional status string.
        parent_uuid:
            Optional UUID of the parent entity. The post-Migration-11 way
            to express a parent edge.
        parent_type_id:
            DEPRECATED — legacy alias resolved to ``parent_uuid`` via
            :meth:`_resolve_identifier` (workspace-scoped). Provided for
            test-fixture compatibility during the Feature 108 transition.
            If both ``parent_uuid`` and ``parent_type_id`` are supplied,
            ``parent_uuid`` wins and a DeprecationWarning is emitted.
        metadata:
            Optional dict stored as JSON TEXT.

        Returns
        -------
        str
            The UUID of the newly registered entity.

        Raises
        ------
        ValueError
            If neither ``workspace_uuid`` nor ``project_id`` is provided,
            or if ``parent_type_id`` cannot be resolved to an entity.
        EntityExistsError
            If ``(workspace_uuid, type_id)`` already exists. Callers that
            relied on the pre-feature-109 silent no-op semantics must
            migrate to :meth:`upsert_entity`.

        Behavior change (feature 109 Group 13)
        --------------------------------------
        The previous on-duplicate ``parent_uuid`` fixup branch (which
        backfilled ``parent_uuid`` on an existing row when caller supplied
        one) is **removed**. The branch became unreachable after this
        method began raising on conflict. Callers that need that
        behaviour should catch ``EntityExistsError`` and call
        :meth:`update_entity` explicitly, or use the existing
        :meth:`set_parent` API.
        """
        # Feature 121 FR-5 / design D2: reject blank/whitespace names
        # before any write.
        if not name or not name.strip():
            raise ValueError(self._BLANK_NAME_ERROR)

        self._validate_entity_type(entity_type)

        # Feature 110 Group 2 (Task 2.0): fail-fast entity_id format check.
        #
        # Resolution order for _strict_id_format:
        #   1. Explicit kwarg (None means "use default resolution").
        #   2. Env var PD_REGISTER_ENTITY_STRICT_ID_FORMAT
        #      ('1' = strict, '0' = permissive).
        #   3. Default: True (strict — matches spec FR-8 / Task 2.0 DoD).
        #
        # The env var is a transition-window escape hatch so legacy tests
        # whose fixtures use non-conformant ids (e.g., 'test-bs') can be
        # run without per-call _register_entity_no_display rewrites. Test
        # suites that opt out (via conftest setenv) MUST be migrated to
        # conformant ids in a follow-up. Production callers do NOT set the
        # env var → they get strict mode by default.
        if _strict_id_format is None:
            env_flag = os.environ.get("PD_REGISTER_ENTITY_STRICT_ID_FORMAT")
            if env_flag is None:
                strict = True
            else:
                strict = env_flag != "0"
        else:
            strict = _strict_id_format

        if strict and not _ENTITY_ID_FORMAT_RE.match(entity_id):
            raise EntityIdFormatError(entity_id)

        type_id = f"{entity_type}:{entity_id}"
        now = self._now_iso()
        metadata_json = json.dumps(metadata) if metadata is not None else None

        # Validate metadata if provided
        if metadata is not None:
            from entity_registry.metadata import validate_metadata
            for w in validate_metadata(entity_type, metadata):
                print(f"metadata warning: {w}", file=sys.stderr)

        ws_uuid = self._resolve_workspace_uuid_kwargs(
            workspace_uuid, project_id, _caller="register_entity"
        )

        # Compat shim (Feature 108 transition): resolve deprecated
        # parent_type_id alias to parent_uuid. workspace-scoped resolution.
        # Pre-Migration-11 stored parent_type_id as a denormalized string even
        # when the parent did not exist (parent_uuid NULL). Post-migration the
        # column is gone, so we keep parent_uuid NULL on resolution failure
        # rather than raising.
        if parent_type_id is not None:
            if parent_uuid is not None:
                warnings.warn(
                    "register_entity() received both parent_uuid and "
                    "parent_type_id; parent_uuid wins. parent_type_id is "
                    "deprecated.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            else:
                try:
                    resolved_parent_uuid, _ = self._resolve_identifier(
                        parent_type_id,
                        workspace_uuid=ws_uuid,
                    )
                    parent_uuid = resolved_parent_uuid
                except ValueError:
                    # Parent does not exist; preserve pre-Migration-11
                    # tolerant behaviour by leaving parent_uuid as NULL.
                    parent_uuid = None

        # F11 derivation (feature 109 Group 6): the legacy ``entity_type``
        # kwarg maps to (type, kind, lifecycle_class) via the FR-1 mapping.
        # The kind column equals entity_type byte-identically for the 5
        # production values (feature/backlog/brainstorm/project/workspace).
        _type, _lifecycle = _derive_type_and_lifecycle(entity_type)

        # Resolve a project_id label for the entity_created phase_event.
        # Use the explicit project_id kwarg when provided; otherwise look up
        # ``workspaces.project_id_legacy`` for the resolved workspace.
        resolved_project_id = project_id
        if resolved_project_id is None:
            ws_row = self._conn.execute(
                "SELECT project_id_legacy FROM workspaces WHERE uuid = ?",
                (ws_uuid,),
            ).fetchone()
            if ws_row is not None and ws_row["project_id_legacy"]:
                resolved_project_id = ws_row["project_id_legacy"]
            else:
                resolved_project_id = "__unknown__"

        from entity_registry.uuid7 import generate_uuid7
        entity_uuid = generate_uuid7()
        with self.transaction():
            # Plain INSERT (no OR IGNORE). UNIQUE conflict on
            # (workspace_uuid, type_id) raises sqlite3.IntegrityError, which
            # we translate to EntityExistsError. Per SQLite semantics
            # (https://www.sqlite.org/lang_transaction.html) a failed
            # statement inside an explicit BEGIN does NOT auto-rollback the
            # transaction; the surrounding transaction() context manager
            # propagates the exception and rolls back cleanly.
            try:
                self._conn.execute(
                    "INSERT INTO entities "
                    "(uuid, workspace_uuid, type_id, kind, entity_id, "
                    "name, status, parent_uuid, artifact_path, "
                    "created_at, updated_at, metadata, "
                    "type, lifecycle_class) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (entity_uuid, ws_uuid, type_id, entity_type, entity_id,
                     name, status, parent_uuid, artifact_path,
                     now, now, metadata_json,
                     _type, _lifecycle),
                )
            except sqlite3.IntegrityError as exc:
                # Translate UNIQUE conflicts on (workspace_uuid, type_id) to
                # the typed EntityExistsError. Other IntegrityError
                # variants (e.g. NOT NULL violation, FK violation) bubble
                # unchanged.
                msg = str(exc).lower()
                if "unique" in msg and (
                    "type_id" in msg or "entities.type_id" in msg
                    or "workspace_uuid" in msg
                ):
                    raise EntityExistsError(
                        workspace_uuid=ws_uuid, type_id=type_id,
                    ) from exc
                raise

            # FTS5 sync (only on successful INSERT).
            row = self._conn.execute(
                "SELECT rowid FROM entities WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()
            metadata_text = flatten_metadata(
                json.loads(metadata_json) if metadata_json else None
            )
            self._conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, "
                "kind, status, metadata_text) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], name, entity_id, entity_type, status or "",
                 metadata_text),
            )

            # Feature 110 Group 2 (Task 2.0): entity_display 1:1 invariant.
            # Insert seq + slug parsed from entity_id in the same transaction
            # so AC-8.2 (entity_display row count == entities row count)
            # holds for new rows. Pre-migration-13 databases lack the
            # entity_display table — swallow that specific OperationalError
            # so register_entity remains functional in the transition window.
            # The strict regex match above guarantees a dash separator and a
            # numeric prefix, so the parse is well-defined.
            if strict:
                dash_idx = entity_id.index("-")
                _seq = int(entity_id[:dash_idx])
                _slug = entity_id[dash_idx + 1:]
                try:
                    self._conn.execute(
                        "INSERT INTO entity_display (uuid, seq, slug) "
                        "VALUES (?, ?, ?)",
                        (entity_uuid, _seq, _slug),
                    )
                except sqlite3.OperationalError as exc:
                    if "no such table" not in str(exc).lower():
                        raise
                    # Pre-migration-13: entity_display table does not exist
                    # yet. The migration-13 backfill INSERT-SELECT covers
                    # rows registered before the table existed. Silent skip.

            # entity_created phase_event emission (feature 109 FR-2 /
            # spec line 104). The append_phase_event helper INSERTs the
            # event row WITHOUT redundantly UPDATE-ing entities.status —
            # see helper docstring step 4 ("SKIP this UPDATE for
            # event_type='entity_created'") which preserves the
            # AC-2.7 ``entities.updated_at == phase_events.timestamp``
            # invariant.
            self.append_phase_event(
                type_id=type_id,
                project_id=resolved_project_id,
                event_type="entity_created",
                workspace_uuid=ws_uuid,
                metadata={
                    "kind": entity_type,
                    "name": name,
                    "status": status,
                },
                timestamp=now,
            )

            # Feature 124 D7 (FR124-3 dual-write): auto-materialize each
            # resolvable `depends_on_features` metadata ref as a `blocks`
            # row (from_uuid=blocker, to_uuid=this entity, per D1's
            # mapping). Runs inside this same transaction so
            # add_dependency's own _commit() is suppressed -- one atomic
            # write alongside the entity row. upsert_entity's insert
            # branch delegates to this method via a re-entrant
            # transaction(), so it is covered too; its conflict branches
            # never touch metadata, so no separate hook is needed there.
            # The RAW db.add_dependency (kwargs form REQUIRED -- the live
            # signature is arg1=blocked, arg2=blocker) has no cycle-raise,
            # so an unresolvable or self-referential ref warns to stderr
            # and is skipped WITHOUT blocking registration (decomposing
            # SKILL.md:231/:248 stay byte-unchanged).
            if metadata is not None:
                for ref in metadata.get("depends_on_features") or []:
                    if not isinstance(ref, str):
                        continue
                    try:
                        blocker_uuid = self.resolve_ref(
                            ref, workspace_uuid=ws_uuid,
                        )
                    except ValueError as exc:
                        print(
                            f"[register_entity] unresolvable "
                            f"depends_on_features ref {ref!r} on entity "
                            f"{type_id!r} ({entity_uuid}): {exc}",
                            file=sys.stderr,
                        )
                        continue
                    if blocker_uuid == entity_uuid:
                        print(
                            "[register_entity] skipping self-referential "
                            f"depends_on_features ref {ref!r} on entity "
                            f"{type_id!r} ({entity_uuid})",
                            file=sys.stderr,
                        )
                        continue
                    self.add_dependency(
                        entity_uuid=entity_uuid,
                        blocked_by_uuid=blocker_uuid,
                    )

        return entity_uuid

    def _register_entity_no_display(
        self,
        entity_type: str,
        entity_id: str,
        name: str,
        *,
        workspace_uuid: str | None = None,
        project_id: str | None = None,
        artifact_path: str | None = None,
        status: str | None = None,
        parent_uuid: str | None = None,
        parent_type_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Test-only escape hatch (feature 110 Group 2 Task 2.0).

        Bypasses the ``^\\d+-.+`` entity_id format check AND the
        ``entity_display(uuid, seq, slug)`` INSERT. Used by legacy test
        fixtures whose entity_ids predate the feature-110 format contract.

        DO NOT use in production code paths. The corresponding entity row
        will be missing from ``entity_display`` — any downstream query
        joining on ``entity_display.uuid`` will not return this row.
        """
        return self.register_entity(
            entity_type, entity_id, name,
            workspace_uuid=workspace_uuid,
            project_id=project_id,
            artifact_path=artifact_path,
            status=status,
            parent_uuid=parent_uuid,
            parent_type_id=parent_type_id,
            metadata=metadata,
            _strict_id_format=False,
        )

    def upsert_entity(
        self,
        entity_type: str,
        entity_id: str,
        name: str,
        *,
        workspace_uuid: str | None = None,
        project_id: str | None = None,
        artifact_path: str | None = None,
        status: str | None = None,
        parent_uuid: str | None = None,
        parent_type_id: str | None = None,
        metadata: dict | None = None,
        _strict_id_format: bool | None = None,
    ) -> str:
        """Idempotent insert-or-status-update. Signature byte-identical to
        :meth:`register_entity` (feature 109 FR-4 / AC-4.3).

        Three semantic branches (AC-4.4):

        - **Insert branch** (no conflict): same as :meth:`register_entity`
          — emits one ``entity_created`` phase_event.
        - **Conflict + status change**: emits one ``entity_status_changed``
          phase_event with ``metadata={'old_status': ..., 'new_status': ...}``;
          ``entities.status`` and ``updated_at`` are updated via
          :meth:`append_phase_event`.
        - **Conflict + no status change**: no UPDATE issued, no
          phase_event emitted, ``entities.updated_at`` unchanged.

        Does NOT update ``name``, ``parent_uuid``, or ``metadata`` on the
        conflict branch — callers needing those use :meth:`update_entity`.

        Returns
        -------
        str
            The entity's UUID (newly generated on insert branch; existing
            on conflict branches).
        """
        # Feature 121 FR-5 / design D2: reject blank/whitespace names
        # before any write.
        if not name or not name.strip():
            raise ValueError(self._BLANK_NAME_ERROR)

        type_id = f"{entity_type}:{entity_id}"
        with self.transaction():
            try:
                # Try the insert branch via register_entity. On success,
                # it emits entity_created and returns the new uuid.
                return self.register_entity(
                    entity_type, entity_id, name,
                    workspace_uuid=workspace_uuid,
                    project_id=project_id,
                    artifact_path=artifact_path,
                    status=status,
                    parent_uuid=parent_uuid,
                    parent_type_id=parent_type_id,
                    metadata=metadata,
                    _strict_id_format=_strict_id_format,
                )
            except EntityExistsError:
                # Conflict branch: workspace-scoped direct SELECT (PRD Goal 1
                # workspace-isolation invariant). Do NOT use get_entity() —
                # that helper raises ValueError on cross-workspace ambiguity
                # (database.py get_entity body); upsert knows the workspace
                # so we scope the lookup explicitly.
                ws_uuid = self._resolve_workspace_uuid_kwargs(
                    workspace_uuid, project_id, _caller="upsert_entity"
                )
                row = self._conn.execute(
                    "SELECT uuid, status FROM entities "
                    "WHERE workspace_uuid = ? AND type_id = ?",
                    (ws_uuid, type_id),
                ).fetchone()
                if row is None:
                    # Defensive: register raised EntityExistsError so the
                    # row must exist. If it doesn't, the conflict was on
                    # something else — re-raise.
                    raise
                existing_uuid = row["uuid"]
                existing_status = row["status"]

                # No-op branch: status unchanged (or caller passed None).
                if status is None or existing_status == status:
                    return existing_uuid

                # Status-change branch: emit one entity_status_changed event.
                # append_phase_event handles the entities.status UPDATE
                # atomically (workspace-scoped per FR-2 helper step 3).
                # Resolve project_id for the phase_events row.
                resolved_project_id = project_id
                if resolved_project_id is None:
                    ws_row = self._conn.execute(
                        "SELECT project_id_legacy FROM workspaces "
                        "WHERE uuid = ?",
                        (ws_uuid,),
                    ).fetchone()
                    if ws_row is not None and ws_row["project_id_legacy"]:
                        resolved_project_id = ws_row["project_id_legacy"]
                    else:
                        resolved_project_id = "__unknown__"

                self.append_phase_event(
                    type_id=type_id,
                    project_id=resolved_project_id,
                    event_type="entity_status_changed",
                    workspace_uuid=ws_uuid,
                    metadata={
                        "old_status": existing_status,
                        "new_status": status,
                    },
                )
                return existing_uuid

    def set_parent(
        self,
        type_id: str,
        parent_type_id: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> str:
        """Set or change the parent of an entity.

        Parameters
        ----------
        type_id:
            The entity to update (UUID or type_id).
        parent_type_id:
            The new parent entity (UUID or type_id, must exist). Despite
            the name (kept for API compatibility), a UUID is also
            accepted; the kwarg is the *parent identifier*, not strictly
            a type_id.
        workspace_uuid:
            If provided, scope both ``type_id`` and ``parent_type_id``
            lookups to this workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        str
            The UUID of the updated child entity.

        Raises
        ------
        ValueError
            If either entity is not found, or if the assignment would
            create a circular reference.
        """
        child_uuid, _child_type_id = self._resolve_identifier(
            type_id,
            project_id=project_id,
            workspace_uuid=workspace_uuid,
        )
        parent_uuid, _parent_type_id_resolved = self._resolve_identifier(
            parent_type_id,
            project_id=project_id,
            workspace_uuid=workspace_uuid,
        )

        # Self-parent check using UUIDs
        if child_uuid == parent_uuid:
            raise ValueError("entity cannot be its own parent")

        # Circular reference detection via UUID-based CTE (depth-guarded)
        cur = self._conn.execute(
            """
            WITH RECURSIVE anc(uid, depth) AS (
                SELECT parent_uuid, 0 FROM entities WHERE uuid = :parent_uuid
                UNION ALL
                SELECT e.parent_uuid, a.depth + 1 FROM entities e
                JOIN anc a ON e.uuid = a.uid
                WHERE e.parent_uuid IS NOT NULL
                  AND a.depth < 10
            )
            SELECT 1 FROM anc WHERE uid = :child_uuid
            """,
            {"parent_uuid": parent_uuid, "child_uuid": child_uuid},
        )
        if cur.fetchone() is not None:
            raise ValueError(
                f"Circular reference detected: setting {parent_type_id!r} "
                f"as parent of {type_id!r} would create a cycle"
            )

        self._conn.execute(
            "UPDATE entities SET parent_uuid = ?, updated_at = ? "
            "WHERE uuid = ?",
            (parent_uuid, self._now_iso(), child_uuid),
        )
        self._commit()
        return child_uuid

    def promote_entity(
        self,
        uuid: str,
        new_kind: str,
        new_lifecycle_class: str,
        *,
        project_id: str | None = None,
    ) -> dict:
        """Atomic kind/lifecycle_class change with ``type_id`` prefix rewrite.

        Feature 109 FR-3 / AC-3.2-AC-3.6. Performs in a single transaction:

        1. Read existing row by ``uuid`` (via :meth:`get_entity_by_uuid`).
        2. Derive ``new_type_id`` by splitting on the FIRST colon
           (``type_id.split(":", 1)``); subsequent colons in the suffix are
           preserved verbatim.
        3. UNIQUE-safety pre-flight: raise :class:`PromotionConflictError`
           if ``(workspace_uuid, new_type_id)`` already exists.
        4. ``UPDATE entities SET kind, lifecycle_class, type_id, updated_at``.
        5. Emit ``entity_promoted`` phase_event (via
           :meth:`append_phase_event`) with the POST-promotion ``type_id``
           and metadata containing both ``old_*`` and ``new_*`` fields.

        The ``enforce_immutable_entity_type`` and ``enforce_immutable_type_id``
        triggers are dropped in migration 12, so the UPDATE succeeds without
        trigger interference.

        Parameters
        ----------
        uuid:
            The entity UUID to promote.
        new_kind:
            The post-promotion ``kind`` value (e.g. ``'feature'``).
        new_lifecycle_class:
            The post-promotion ``lifecycle_class`` value (e.g. ``'feature_flow'``).
        project_id:
            Optional legacy project_id; resolved to ``workspaces.project_id_legacy``
            for the phase_events row. If ``None``, derived from the entity's
            workspace_uuid.

        Returns
        -------
        dict
            The updated entity row (post-promotion state).

        Raises
        ------
        ValueError
            If ``uuid`` does not resolve to an entity.
        PromotionConflictError
            If ``(workspace_uuid, new_type_id)`` already exists in the same
            workspace.
        """
        with self.transaction():
            # Step 1: read existing via the EXISTING public helper.
            existing = self.get_entity_by_uuid(uuid)
            if not existing:
                raise ValueError(f"Entity not found: {uuid}")

            # Step 2: derive new_type_id (first-colon split rule).
            old_type_id = existing["type_id"]
            entity_id_suffix = old_type_id.split(":", 1)[1]
            new_type_id = f"{new_kind}:{entity_id_suffix}"

            ws_uuid = existing["workspace_uuid"]

            # Step 3: UNIQUE-safety pre-flight (AC-3.6). Only check if the
            # prefix actually changes — same-kind same-suffix is a no-op
            # rewrite and cannot collide with a different row.
            if old_type_id != new_type_id:
                collision = self._conn.execute(
                    "SELECT 1 FROM entities "
                    "WHERE workspace_uuid = ? AND type_id = ? AND uuid != ?",
                    (ws_uuid, new_type_id, uuid),
                ).fetchone()
                if collision:
                    raise PromotionConflictError(
                        workspace_uuid=ws_uuid,
                        old_type_id=old_type_id,
                        new_type_id=new_type_id,
                    )

            # Resolve project_id for the phase_events row. If the caller did
            # not pass one, derive from the workspace's project_id_legacy.
            resolved_project_id = project_id
            if resolved_project_id is None:
                ws_row = self._conn.execute(
                    "SELECT project_id_legacy FROM workspaces WHERE uuid = ?",
                    (ws_uuid,),
                ).fetchone()
                if ws_row is not None and ws_row["project_id_legacy"]:
                    resolved_project_id = ws_row["project_id_legacy"]
                else:
                    # Fall back to a sentinel: phase_events.project_id is
                    # NOT NULL; "__unknown__" is the canonical fallback.
                    resolved_project_id = "__unknown__"

            # Step 4: UPDATE entities.
            self._conn.execute(
                "UPDATE entities "
                "SET kind = ?, lifecycle_class = ?, type_id = ?, "
                "updated_at = ? "
                "WHERE uuid = ?",
                (new_kind, new_lifecycle_class, new_type_id,
                 self._now_iso(), uuid),
            )

            # Step 5: emit entity_promoted event (post-promotion identity).
            self.append_phase_event(
                type_id=new_type_id,
                project_id=resolved_project_id,
                event_type="entity_promoted",
                workspace_uuid=ws_uuid,
                metadata={
                    "old_kind": existing["kind"],
                    "new_kind": new_kind,
                    "old_lifecycle_class": existing["lifecycle_class"],
                    "new_lifecycle_class": new_lifecycle_class,
                    "old_type_id": old_type_id,
                    "new_type_id": new_type_id,
                },
            )

            # Step 6: return updated entity dict via EXISTING helper.
            return self.get_entity_by_uuid(uuid)

    def get_entity(self, type_id: str) -> dict | None:
        """Retrieve a single entity by UUID or type_id.

        Returns ``None`` if not found.

        Feature 108: enriches the row dict with a resolved ``parent_type_id``
        (looked up via ``parent_uuid``) and ``project_id`` (from
        ``workspaces.project_id_legacy``) so callers retain the legacy fields
        even though Migration 11 dropped the underlying columns.
        """
        try:
            uuid, _ = self._resolve_identifier(type_id)
        except ValueError:
            return None
        row = self._conn.execute(
            "SELECT e.*, e.kind AS entity_type, "
            "p.type_id AS parent_type_id, "
            "w.project_id_legacy AS project_id "
            "FROM entities e "
            "LEFT JOIN entities p ON e.parent_uuid = p.uuid "
            "LEFT JOIN workspaces w ON e.workspace_uuid = w.uuid "
            "WHERE e.uuid = ?",
            (uuid,),
        ).fetchone()
        return dict(row) if row else None

    def list_entities(
        self,
        entity_type: str | None = None,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """Return all entities, optionally filtered by entity_type and workspace.

        Parameters
        ----------
        entity_type:
            If provided, only return entities of this type.
            If None, return all entity types.
        workspace_uuid:
            If provided, only return entities in this workspace.
            If None, return entities across all workspaces.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        list[dict]
            List of entity dicts with same keys as ``get_entity``.
        """
        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="list_entities"
        )
        conditions: list[str] = []
        params: list[str] = []
        if entity_type is not None:
            # F11: filter on kind (the legacy entity_type column was dropped
            # by migration 12 Group 7; kind values are byte-identical to the
            # 5 production entity_type values per FR-1).
            conditions.append("e.kind = ?")
            params.append(entity_type)
        if ws_uuid is not None:
            conditions.append("e.workspace_uuid = ?")
            params.append(ws_uuid)

        # Feature 108: enrich rows with resolved ``parent_type_id`` (via
        # parent_uuid JOIN) and ``project_id`` (via workspaces JOIN) so
        # callers retain the legacy fields post-Migration-11.
        # Feature 109 Group 6: ``e.kind AS entity_type`` projects the
        # F11 column back to the legacy dict-key name expected by
        # downstream callers (TD-8: public API surface preserved).
        sql = (
            "SELECT e.*, e.kind AS entity_type, "
            "p.type_id AS parent_type_id, "
            "w.project_id_legacy AS project_id "
            "FROM entities e "
            "LEFT JOIN entities p ON e.parent_uuid = p.uuid "
            "LEFT JOIN workspaces w ON e.workspace_uuid = w.uuid"
        )
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    def get_lineage(
        self,
        type_id: str,
        direction: str = "up",
        max_depth: int = 10,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """Traverse the entity hierarchy.

        Parameters
        ----------
        type_id:
            Starting entity.
        direction:
            ``"up"`` walks toward the root (result is root-first).
            ``"down"`` walks toward leaves (BFS order).
        max_depth:
            Maximum levels to traverse (default 10).
        workspace_uuid:
            If provided, scope ``type_id`` resolution to this workspace.
            Lineage traversal itself follows ``parent_uuid`` chains
            which are workspace-scoped by FK.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        list[dict]
            Ordered list of entity dicts. Empty if type_id not found.
        """
        try:
            resolved_uuid, _ = self._resolve_identifier(
                type_id,
                project_id=project_id,
                workspace_uuid=workspace_uuid,
            )
        except ValueError:
            return []

        if direction == "up":
            return self._lineage_up(resolved_uuid, max_depth)
        elif direction == "down":
            return self._lineage_down(resolved_uuid, max_depth)
        else:
            raise ValueError(f"Invalid direction: {direction!r} (expected 'up' or 'down')")

    def _lineage_up(self, resolved_uuid: str, max_depth: int) -> list[dict]:
        """Walk up the tree from uuid to root, return root-first."""
        cur = self._conn.execute(
            """
            WITH RECURSIVE ancestors(uid, depth) AS (
                SELECT ?, 0
                UNION ALL
                SELECT e.parent_uuid, a.depth + 1
                FROM entities e
                JOIN ancestors a ON e.uuid = a.uid
                WHERE e.parent_uuid IS NOT NULL
                  AND a.depth < ?
            )
            SELECT e.* FROM ancestors a
            JOIN entities e ON e.uuid = a.uid
            ORDER BY a.depth DESC
            """,
            (resolved_uuid, max_depth),
        )
        return [dict(row) for row in cur.fetchall()]

    def _lineage_down(self, resolved_uuid: str, max_depth: int) -> list[dict]:
        """Walk down the tree from uuid to leaves, BFS order."""
        cur = self._conn.execute(
            """
            WITH RECURSIVE descendants(uid, depth) AS (
                SELECT ?, 0
                UNION ALL
                SELECT e.uuid, d.depth + 1
                FROM entities e
                JOIN descendants d ON e.parent_uuid = d.uid
                WHERE d.depth < ?
            )
            SELECT e.* FROM descendants d
            JOIN entities e ON e.uuid = d.uid
            ORDER BY d.depth ASC
            """,
            (resolved_uuid, max_depth),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_entity(
        self,
        type_id: str,
        name: str | None = None,
        status: str | None = None,
        artifact_path: str | None = None,
        metadata: dict | None = None,
        project_id: str | None = None,
        new_project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> None:
        """Update mutable fields of an existing entity.

        Parameters
        ----------
        type_id:
            The entity to update (UUID or type_id).
        name:
            New name (if provided).
        status:
            New status (if provided).
        artifact_path:
            New artifact_path (if provided).
        metadata:
            If provided, shallow-merges with existing metadata.
            An empty dict ``{}`` clears metadata to None.
        workspace_uuid:
            If provided, scope type_id resolution to this workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.
        new_project_id:
            DEPRECATED — pre-Migration-11 re-attribution kwarg. Still
            accepted; raises ``NotImplementedError`` if used because the
            ``project_id`` column no longer exists post-Migration-11.
            Re-attribution will move to a workspace-aware API in a later
            phase of feature 108.

        Raises
        ------
        ValueError
            If the entity does not exist, or if ``name`` is supplied but
            blank/whitespace-only (feature 121 FR-5 — ``name=None`` is
            fine; that means "not updating name").
        NotImplementedError
            If ``new_project_id`` is supplied (re-attribution path
            disabled until the workspace-aware replacement lands).
        """
        # Resolve identifier directly (accepts both UUID and type_id).
        # Lets ValueError propagate naturally if entity not found.
        entity_uuid, _ = self._resolve_identifier(
            type_id, project_id=project_id, workspace_uuid=workspace_uuid,
        )

        # FTS sync: capture old values before UPDATE.
        # F11 (feature 109 Group 6): ``kind`` replaces the legacy
        # ``entity_type`` column.
        old_row = self._conn.execute(
            "SELECT rowid, name, entity_id, kind, status, metadata "
            "FROM entities WHERE uuid = ?",
            (entity_uuid,),
        ).fetchone()

        set_parts: list[str] = ["updated_at = ?"]
        params: list = [self._now_iso()]

        # Feature 121 FR-5 / design D2: reject a supplied-but-blank name
        # before any write. name=None ("not updating name") stays legal —
        # absent is not the same as blank.
        if name is not None and not name.strip():
            raise ValueError(self._BLANK_NAME_ERROR)

        if name is not None:
            set_parts.append("name = ?")
            params.append(name)

        if status is not None:
            set_parts.append("status = ?")
            params.append(status)

        if artifact_path is not None:
            set_parts.append("artifact_path = ?")
            params.append(artifact_path)

        if metadata is not None:
            if len(metadata) == 0:
                # Empty dict clears metadata
                set_parts.append("metadata = ?")
                params.append(None)
            else:
                # Shallow merge with existing (old_row already has metadata)
                # Use try/except to handle corrupted JSON gracefully
                try:
                    existing_meta = (
                        json.loads(old_row["metadata"])
                        if old_row["metadata"] else {}
                    )
                except (json.JSONDecodeError, ValueError):
                    existing_meta = {}
                existing_meta.update(metadata)
                set_parts.append("metadata = ?")
                params.append(json.dumps(existing_meta))

                # Validate merged metadata. F11 (Group 6): the validator
                # still takes the legacy entity_type string; we read it
                # from ``kind`` (which holds the same value for the 5
                # production kinds — feature/backlog/brainstorm/project/
                # workspace — per FR-1).
                entity_row = self._conn.execute(
                    "SELECT kind FROM entities WHERE uuid = ?",
                    (entity_uuid,),
                ).fetchone()
                if entity_row:
                    from entity_registry.metadata import validate_metadata
                    for w in validate_metadata(entity_row["kind"], existing_meta):
                        print(f"metadata warning: {w}", file=sys.stderr)

        # Audit 062: 3 write SQL statements — wrapped in transaction() for BEGIN IMMEDIATE
        params.append(entity_uuid)
        sql = f"UPDATE entities SET {', '.join(set_parts)} WHERE uuid = ?"
        with self.transaction():
            self._conn.execute(sql, params)

            # Re-read post-UPDATE values from DB rather than deriving them in
            # Python. This avoids replicating the metadata-merge logic (None/keep,
            # {}/clear, dict/shallow-merge) and uses the DB as single source of
            # truth. If new FTS-indexed fields are added, update both the
            # old-value SELECT and the FTS insert columns.
            # F11 (Group 6): read ``kind`` in place of legacy ``entity_type``.
            new_row = self._conn.execute(
                "SELECT name, entity_id, kind, status, metadata "
                "FROM entities WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()
            new_meta_text = flatten_metadata(
                json.loads(new_row["metadata"]) if new_row["metadata"] else None
            )
            # Standalone FTS: use DELETE FROM (not external-content VALUES('delete',...))
            # INVARIANT: rowid must match entities table rowid
            self._conn.execute(
                "DELETE FROM entities_fts WHERE rowid = ?", (old_row["rowid"],)
            )
            self._conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, kind, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (old_row["rowid"], new_row["name"], new_row["entity_id"],
                 new_row["kind"], new_row["status"] or "",
                 new_meta_text),
            )
            self._commit()  # no-op inside transaction(); commit handled by context manager

            # Feature 115 FR-C-115.1 / Feature 132 FR132-4b + D5: audit
            # invariant emit. When status mutates (status is not None AND
            # status != old), emit an entity_status_changed phase_event
            # (which itself dual-writes a v2 events row per Step 6 of
            # append_phase_event, above). Per spec AC-C.4: no-op writes
            # (same status) do NOT emit.
            #
            # MOVED in-transaction and made FAIL-CLOSED (feature 132):
            # previously this ran AFTER the block above committed, wrapped
            # in a swallow-everything except (fail-open per old spec FR-C.2
            # / 114 TD-2, incrementing an `audit_emit_failed_count` counter
            # on failure) -- meaning the status UPDATE could commit while
            # its audit trail silently vanished, exactly the #055/#060
            # acknowledged-but-lost class FR132-4b closes at cutover. Now a
            # failure here (e.g. the emit raising, or the 122 vocab trigger
            # rejecting an out-of-vocabulary value) propagates and rolls
            # back the status UPDATE too, via this same self.transaction().
            # The audit_emit_failed_count counter-increment/except-swallow
            # that used to live here is DELETED, confined to this block
            # only -- the doctor check_audit_emit_failed_count check, the
            # check_audit_counter_write_path AST guard, and Migration 15's
            # counter row are feature 133's concern and are untouched (the
            # AST guard scopes only `_migration_*` functions, so this
            # deletion cannot break it).
            if status is not None and old_row is not None and old_row["status"] != status:
                # Resolve type_id + workspace_uuid for the emit. project_id is
                # derived from workspace_uuid via the workspaces JOIN (post-F109).
                entity_meta = self._conn.execute(
                    "SELECT type_id, workspace_uuid FROM entities WHERE uuid = ?",
                    (entity_uuid,),
                ).fetchone()
                if entity_meta is not None:
                    # project_id from workspaces table (legacy field still required
                    # by append_phase_event signature).
                    ws_row = self._conn.execute(
                        "SELECT project_id_legacy FROM workspaces WHERE uuid = ?",
                        (entity_meta["workspace_uuid"],),
                    ).fetchone()
                    _project_id = (
                        ws_row["project_id_legacy"]
                        if ws_row and ws_row["project_id_legacy"]
                        else "__unknown__"
                    )
                    self.append_phase_event(
                        type_id=entity_meta["type_id"],
                        project_id=_project_id,
                        workspace_uuid=entity_meta["workspace_uuid"],
                        event_type="entity_status_changed",
                        phase=None,
                        metadata={
                            "old_status": old_row["status"],
                            "new_status": status,
                        },
                    )

        # Cascade unblock: when an entity reaches a resolved status for its
        # kind (feature 124 D4's per-kind terminal table -- e.g. 'completed'
        # for features/5D kinds, but ALSO 'closed' for closes=-closed tasks/
        # bugs, which the old =='completed' check missed), flip dependents
        # whose blockers are now all resolved. Edges SURVIVE (FR124-4c);
        # flip target is 'ready' (FR124-4a) -- idempotent, since a dependent
        # already flipped to 'ready' no longer satisfies the 'blocked' guard
        # inside _evaluate_and_flip, so a repeat terminal write re-flips
        # nothing.
        # Placed AFTER transaction exits (TD-1) to avoid nested transactions.
        # Fail-open: Layers 2 (reconciliation) and 3 (doctor) catch stale edges.
        if status is not None and old_row is not None:
            from entity_registry.dependencies import (
                DependencyManager,
                _blocker_completed,
            )
            if _blocker_completed({"kind": old_row["kind"], "status": status}):
                try:
                    DependencyManager().cascade_unblock(self, entity_uuid)
                except Exception as exc:
                    print(
                        f"cascade_unblock failed (recovered by doctor): "
                        f"{type(exc).__name__}",
                        file=sys.stderr,
                    )

        # Re-attribution (TD-8): post-Migration-11 the column is workspace_uuid.
        # We accept the legacy ``new_project_id`` kwarg, resolve it to a
        # workspace_uuid via ``workspaces.project_id_legacy`` (auto-bootstrap
        # the canonical __unknown__ row when needed), then UPDATE the
        # workspace_uuid column under a temporary trigger drop.
        if new_project_id is not None:
            # Resolve the target workspace, bootstrapping the canonical
            # __unknown__ row when applicable. For arbitrary legacy ids we
            # require an existing workspaces row (callers must pre-register).
            target_ws_uuid = self._resolve_workspace_uuid_kwargs(
                None, new_project_id, _caller="update_entity"
            )
            self._conn.commit()  # flush implicit transaction
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid"
                )
                self._conn.execute(
                    "UPDATE entities SET workspace_uuid = ?, updated_at = ? "
                    "WHERE uuid = ?",
                    (target_ws_uuid, self._now_iso(), entity_uuid),
                )
                # Cascade to workflow_phases so per-workspace queries stay
                # in sync. (We use type_id since workflow_phases.type_id is
                # the natural join key; multi-workspace duplicates would
                # need more care, but this matches the pre-Migration-11
                # contract.)
                wp_type = self._conn.execute(
                    "SELECT type_id FROM entities WHERE uuid = ?",
                    (entity_uuid,),
                ).fetchone()
                if wp_type is not None:
                    self._conn.execute(
                        "UPDATE workflow_phases SET workspace_uuid = ?, "
                        "updated_at = ? WHERE type_id = ?",
                        (target_ws_uuid, self._now_iso(), wp_type["type_id"]),
                    )
                # Recreate the immutability trigger.
                self._conn.execute(
                    "CREATE TRIGGER enforce_immutable_workspace_uuid "
                    "BEFORE UPDATE OF workspace_uuid ON entities "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'workspace_uuid is immutable — use re-attribution API'); "
                    "END"
                )
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                # Best-effort: ensure the trigger exists even if we rolled
                # back mid-flight. Wrap in try in case the trigger is
                # already present (rollback may have restored it).
                try:
                    self._conn.execute(
                        "CREATE TRIGGER IF NOT EXISTS "
                        "enforce_immutable_workspace_uuid "
                        "BEFORE UPDATE OF workspace_uuid ON entities "
                        "BEGIN SELECT RAISE(ABORT, "
                        "'workspace_uuid is immutable — use re-attribution "
                        "API'); END"
                    )
                except sqlite3.Error:
                    pass
                raise

    def backfill_project_ids(
        self,
        project_root: str,
        project_id: str,
        workspace_uuid: str | None = None,
    ) -> int:
        """Claim ``__unknown__`` entities whose artifact_path is under *project_root*.

        Temporarily drops the ``enforce_immutable_project_id`` trigger to allow
        the UPDATE, then recreates it.  This is the same trigger-drop pattern
        used by re-attribution in :meth:`update_entity` (TD-8).

        Parameters
        ----------
        project_root:
            Absolute path to the project root directory.
        project_id:
            Project identifier to assign to the claimed entities.
        workspace_uuid:
            When supplied (the lifespan-resolved identity), it is the
            authoritative claim target — entities are claimed into it directly,
            bypassing the legacy ``project_id`` lookup. This prevents
            cross-attribution into a stale legacy-keyed row when the canonical
            identity is already known. A competing ``project_root`` row is
            adopted rather than duplicated. When ``None``, the target is
            resolved by legacy ``project_id`` → single ``project_root`` match →
            fresh mint.

        Returns
        -------
        int
            Number of entities whose ``project_id`` was updated.
        """
        if not project_root or not os.path.isabs(project_root):
            raise ValueError(
                f"project_root must be a non-empty absolute path, got {project_root!r}"
            )
        if self._in_transaction:
            raise RuntimeError(
                "backfill_project_ids cannot be called inside an active transaction"
            )
        # Feature 108 Migration 11: project_id column dropped. The workspace-
        # aware replacement is ``claim_unknown_entities``. We resolve the
        # caller-supplied project_id to a workspace_uuid (auto-bootstrap a
        # workspaces row if absent), then claim entities whose
        # workspace_uuid is the canonical __unknown__ AND whose
        # artifact_path lies under project_root.
        # Escape LIKE special characters in project_root.
        escaped = (
            project_root
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        # Canonicalize root for workspaces-row ops (match validate_or_adopt).
        root_abs = os.path.abspath(project_root)

        def _single_root_or_raise():
            rows = self._conn.execute(
                "SELECT uuid FROM workspaces "
                "WHERE project_root IS NOT NULL AND project_root = ?",
                (root_abs,),
            ).fetchall()
            if len(rows) == 1:
                return rows[0]["uuid"]
            if len(rows) == 0:
                return None
            raise ValueError(
                f"backfill_project_ids(): project_root={root_abs!r} is "
                f"claimed by {len(rows)} workspace rows; refusing to attribute "
                f"entities ambiguously. Manual repair required (run pd:doctor)."
            )

        # Resolve / bootstrap target workspace. This runs BEFORE the
        # BEGIN IMMEDIATE trigger-drop block below — keep that block minimal.
        if workspace_uuid is not None:
            # Authoritative identity: ensure its row exists and claim into it.
            from entity_registry.project_identity import (
                _insert_workspace_row_if_absent,
            )
            outcome = _insert_workspace_row_if_absent(
                self._conn, workspace_uuid, root_abs, project_id
            )
            if outcome == "conflict-root":
                # conflict-root guarantees ≥1 row; None is unreachable here.
                target_ws_uuid = _single_root_or_raise()
            else:
                target_ws_uuid = workspace_uuid
            self._conn.commit()
        else:
            ws_row = self._conn.execute(
                "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
                (project_id,),
            ).fetchone()
            if ws_row is not None:
                target_ws_uuid = ws_row["uuid"]
            else:
                # Adopt a single project_root match (raise on multi-row);
                # mint only when the root is genuinely unclaimed.
                target_ws_uuid = _single_root_or_raise()
                if target_ws_uuid is None:
                    from entity_registry.uuid7 import generate_uuid7
                    target_ws_uuid = generate_uuid7()
                    now = self._now_iso()
                    self._conn.execute(
                        "INSERT INTO workspaces "
                        "(uuid, project_id_legacy, project_root, created_at, "
                        "updated_at) VALUES (?, ?, ?, ?, ?)",
                        (target_ws_uuid, project_id, root_abs, now, now),
                    )
                    self._conn.commit()
        if target_ws_uuid == _UNKNOWN_WORKSPACE_UUID:
            return 0  # no-op: cannot claim into the unknown bucket itself
        self._conn.commit()  # flush any implicit transaction
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid"
            )
            cur = self._conn.execute(
                """UPDATE entities SET workspace_uuid = ?, updated_at = ?
                   WHERE workspace_uuid = ?
                     AND artifact_path LIKE ? ESCAPE '\\'""",
                (target_ws_uuid, self._now_iso(),
                 _UNKNOWN_WORKSPACE_UUID, escaped + "%"),
            )
            count = cur.rowcount
            self._conn.execute(
                "CREATE TRIGGER enforce_immutable_workspace_uuid "
                "BEFORE UPDATE OF workspace_uuid ON entities "
                "BEGIN SELECT RAISE(ABORT, "
                "'workspace_uuid is immutable — use re-attribution API'); "
                "END"
            )
            self._conn.execute("COMMIT")
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            try:
                self._conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS "
                    "enforce_immutable_workspace_uuid "
                    "BEFORE UPDATE OF workspace_uuid ON entities "
                    "BEGIN SELECT RAISE(ABORT, "
                    "'workspace_uuid is immutable — use re-attribution "
                    "API'); END"
                )
                self._conn.commit()
            except sqlite3.Error:
                pass
            raise
        return count

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_entity(
        self,
        type_id: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> None:
        """Delete an entity and all associated data.

        Extended cascade (TD-6): deletes entity_tags, entity_okr_alignment,
        workflow_phases, entities_fts, and the entity row itself — all by
        UUID. Dependency edges are removed via entity_relations' FK ON
        DELETE CASCADE (fires when the entity row is deleted below — no
        manual DELETE needed).

        Feature 124 D5.3: this entity's dependents (entities it blocked)
        are re-evaluated post-commit -- a dependent whose ONLY remaining
        blockers are now all resolved (vacuously true if this deletion
        removed its last one) flips 'blocked' -> 'ready', fail-open with a
        stderr warning on failure (same posture as the completion trigger
        in update_entity).

        Feature 132 D5 finding, NOT implemented here (deliberate, recorded
        gap -- flagged for follow-up, not silently dropped): design D5
        classifies this method as an ``entity_deleted`` lifecycle-event
        emitter alongside register_entity/upsert_entity. It is NOT wired
        that way. ``events.entity_uuid`` is ``NOT NULL REFERENCES
        entities(uuid)`` with no ``ON DELETE`` clause, and ``events_no_delete``
        (BEFORE DELETE, immutable) fires even on an FK CASCADE-induced
        delete (verified empirically) -- so ANY events row referencing this
        uuid, from ANY writer, at ANY prior time (not just an emit attempted
        HERE), makes step 6's hard ``DELETE FROM entities`` below
        unconditionally raise ``sqlite3.IntegrityError``, in every
        statement order and with or without ``PRAGMA defer_foreign_keys``
        (all verified). Since ``register_entity``'s existing
        ``entity_created`` dual-write (via append_phase_event) means every
        entity gets an events row at birth on a v2-generation file, this is
        not a corner case: it is a standing incompatibility between "hard-
        delete this row" and "this row has audit history" under the
        current schema, pre-existing this method's own code and NOT fixable
        by any ordering/transaction change within this function. Resolving
        it needs a schema decision (e.g. a nullable ``entity_uuid`` +
        ``ON DELETE SET NULL``, out of this feature's file scope -- events.py
        is not in task 3's diff) or a soft-delete redesign of this method's
        contract (a behavior change beyond "wire an emit", not invented
        unilaterally here). v1 files are unaffected (no ``events`` table
        exists to reference). See feature 132's task-3 implementation
        report for the full analysis; a v2-generation regression test
        (test_database.py) pins the current, honest behavior rather than
        asserting a fabricated success case.

        Parameters
        ----------
        type_id : str
            Entity type_id or UUID.
        workspace_uuid:
            If provided, scope ``type_id`` resolution to this workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Raises
        ------
        ValueError
            If entity does not exist.
        ValueError
            If entity has child entities (must delete children first).
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # 1. Resolve to UUID (workspace-scoped if provided)
            entity_uuid, resolved_type_id = self._resolve_identifier(
                type_id,
                project_id=project_id,
                workspace_uuid=workspace_uuid,
            )

            # Feature 124 D5.3: pre-capture this entity's dependents BEFORE
            # the delete -- entity_relations' FK ON DELETE CASCADE wipes
            # their blocks-edges at commit (step 6 below), so calling
            # get_dependents() afterward would see []. Evaluated post-commit
            # (below): a dependent whose ONLY blocker was this now-deleted
            # entity has zero REMAINING blockers, which is vacuously
            # resolved (`all([]) is True`) -- it flips to 'ready'.
            from entity_registry.dependencies import DependencyManager
            _dep_mgr = DependencyManager()
            _dependents = _dep_mgr.get_dependents(self, entity_uuid)

            # Fetch rowid for FTS cleanup
            row = self._conn.execute(
                "SELECT rowid FROM entities WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()

            # 2. Reject if has children
            child = self._conn.execute(
                "SELECT 1 FROM entities WHERE parent_uuid = ? LIMIT 1",
                (entity_uuid,),
            ).fetchone()
            if child is not None:
                raise ValueError(
                    f"Cannot delete entity with children: {type_id}"
                )

            # 3. Extended cascade: junction tables by UUID (TD-6)
            self._conn.execute(
                "DELETE FROM entity_tags WHERE entity_uuid = ?",
                (entity_uuid,),
            )
            self._conn.execute(
                "DELETE FROM entity_okr_alignment "
                "WHERE entity_uuid = ? OR key_result_uuid = ?",
                (entity_uuid, entity_uuid),
            )

            # 4. Delete FTS entry
            self._conn.execute(
                "DELETE FROM entities_fts WHERE rowid = ?", (row["rowid"],)
            )

            # 5. Delete workflow_phases
            self._conn.execute(
                "DELETE FROM workflow_phases WHERE type_id = ?",
                (resolved_type_id,),
            )

            # 6. Delete entity row by UUID
            self._conn.execute(
                "DELETE FROM entities WHERE uuid = ?", (entity_uuid,)
            )

            self._commit()
        except Exception:
            self._conn.rollback()
            raise

        # Feature 124 D5.3: unblock-on-delete hook, run post-commit (same
        # fail-open posture as the completion trigger in update_entity --
        # a failure here must not undo the already-committed delete).
        try:
            _dep_mgr._evaluate_and_flip(self, _dependents)
        except Exception as exc:
            print(
                f"cascade_unblock failed (recovered by doctor): "
                f"{type(exc).__name__}",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # Re-attribution (Feature 108 Phase F)
    # ------------------------------------------------------------------

    def claim_unknown_entities(
        self,
        workspace_uuid: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
    ) -> int:
        """Re-attribute entities from the canonical unknown-workspace UUID
        to the caller's workspace.

        Migration 11 maps every legacy ``project_id == "__unknown__"``
        entity to the canonical ``_UNKNOWN_WORKSPACE_UUID``. Once a real
        workspace is bootstrapped, callers use this method to claim the
        previously-orphaned entities — moving them out of the "unknown"
        bucket and into a concrete workspace.

        Parameters
        ----------
        workspace_uuid:
            Target workspace_uuid. Must already exist in the
            ``workspaces`` table; FK violation raises ``sqlite3.IntegrityError``.
        entity_type:
            If provided, only claim entities of this entity_type
            (e.g. ``"feature"``).
        limit:
            If provided, claim at most this many entities (oldest first
            by ``created_at``). Useful for batched claims.

        Returns
        -------
        int
            The number of entities re-attributed.

        Raises
        ------
        ValueError
            If ``workspace_uuid`` equals ``_UNKNOWN_WORKSPACE_UUID``
            (no-op self-claim) or is empty.
        """
        if not workspace_uuid:
            raise ValueError(
                "claim_unknown_entities() requires a non-empty workspace_uuid"
            )
        if workspace_uuid == _UNKNOWN_WORKSPACE_UUID:
            raise ValueError(
                "claim_unknown_entities() refuses to re-attribute entities "
                "to the canonical _UNKNOWN_WORKSPACE_UUID (no-op)"
            )

        # Verify the target workspace exists; FK enforcement catches this
        # at UPDATE time too, but a pre-check yields a clearer error.
        target = self._conn.execute(
            "SELECT 1 FROM workspaces WHERE uuid = ?",
            (workspace_uuid,),
        ).fetchone()
        if target is None:
            raise ValueError(
                f"claim_unknown_entities(): workspace_uuid={workspace_uuid!r} "
                f"has no matching workspaces row. Bootstrap the workspace "
                f"first."
            )

        # Build the UPDATE. The immutability trigger
        # `enforce_immutable_workspace_uuid` blocks plain UPDATE OF
        # workspace_uuid statements, so re-attribution must temporarily
        # disable that trigger via a recursive sentinel: we drop the trigger,
        # run the UPDATE, then recreate it.
        select_sql = (
            "SELECT uuid FROM entities WHERE workspace_uuid = ?"
        )
        select_params: list = [_UNKNOWN_WORKSPACE_UUID]
        if entity_type is not None:
            # F11 (Group 6): the legacy ``entity_type`` column was dropped
            # by migration 12; filter on ``kind`` instead (same value for
            # the 5 production kinds per FR-1).
            select_sql += " AND kind = ?"
            select_params.append(entity_type)
        select_sql += " ORDER BY created_at ASC"
        if limit is not None:
            select_sql += " LIMIT ?"
            select_params.append(int(limit))

        with self.transaction():
            rows = self._conn.execute(select_sql, select_params).fetchall()
            if not rows:
                return 0
            uuids = [r["uuid"] for r in rows]

            # Temporarily drop the workspace_uuid immutability trigger so
            # this re-attribution path is allowed. Recreate it afterwards.
            self._conn.execute(
                "DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid"
            )
            try:
                placeholders = ",".join("?" for _ in uuids)
                now = self._now_iso()
                self._conn.execute(
                    f"UPDATE entities SET workspace_uuid = ?, updated_at = ? "
                    f"WHERE uuid IN ({placeholders})",
                    [workspace_uuid, now, *uuids],
                )
            finally:
                self._conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS
                        enforce_immutable_workspace_uuid
                    BEFORE UPDATE OF workspace_uuid ON entities
                    BEGIN SELECT RAISE(ABORT,
                        'workspace_uuid is immutable — use re-attribution API'
                    ); END
                """)
            self._commit()
        return len(uuids)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    _FTS_CHAR_RE = re.compile(r'[*"()+\-^:]')
    _FTS_KEYWORDS = {"OR", "AND", "NOT", "NEAR"}

    def _build_fts_query(self, query: str) -> str | None:
        """Sanitize user input into a safe FTS5 MATCH expression."""
        query = query.strip()
        if not query:
            return None

        # Exact phrase: preserve quoted content
        if query.startswith('"') and query.endswith('"') and len(query) > 2:
            inner = self._FTS_CHAR_RE.sub("", query[1:-1]).strip()
            return f'"{inner}"' if inner else None

        # Strip FTS5 special characters — intentionally replaced with spaces
        # (not removed) to preserve word boundaries. E.g. "name:recon" becomes
        # "name recon" (two tokens) rather than "namerecon" (one token).
        sanitized = self._FTS_CHAR_RE.sub(" ", query)
        tokens = sanitized.split()
        # Remove FTS5 keyword operators (case-sensitive uppercase)
        tokens = [t for t in tokens if t not in self._FTS_KEYWORDS]
        if not tokens:
            return None
        # Append * for prefix matching
        return " ".join(f"{t}*" for t in tokens)

    def search_entities(
        self,
        query: str,
        entity_type: str | None = None,
        limit: int = 20,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """Full-text search over entities.

        Parameters
        ----------
        query:
            Search string (prefix-matched, sanitized).
        entity_type:
            Optional filter by entity_type.
        limit:
            Max results (clamped to 1..100).
        workspace_uuid:
            If provided, restrict results to this workspace.
            If None, search across all workspaces.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        list[dict]
            Matching entities with ``rank`` key, ordered by relevance.

        Raises
        ------
        ValueError
            If FTS index is not available or query is invalid.
        """
        # FTS availability guard
        if self._conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='entities_fts'"
        ).fetchone() is None:
            raise ValueError("fts_not_available")

        if not query or not query.strip():
            return []

        limit = max(1, min(limit, 100))

        fts_query = self._build_fts_query(query)
        if fts_query is None:
            return []

        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="search_entities"
        )

        try:
            # Build WHERE conditions beyond FTS MATCH. F11 (Group 6): filter
            # on ``kind`` since the legacy ``entity_type`` column was dropped
            # by migration 12 (kind values equal the 5 production
            # entity_type values per FR-1).
            extra_conditions: list[str] = []
            extra_params: list = []
            if entity_type is not None:
                extra_conditions.append("e.kind = ?")
                extra_params.append(entity_type)
            if ws_uuid is not None:
                extra_conditions.append("e.workspace_uuid = ?")
                extra_params.append(ws_uuid)

            where_clause = "WHERE entities_fts MATCH ?"
            if extra_conditions:
                where_clause += " AND " + " AND ".join(extra_conditions)

            # Project ``e.kind`` back to the legacy ``entity_type`` dict
            # key for caller compatibility (TD-8 public API surface).
            sql = (
                "SELECT e.*, e.kind AS entity_type, entities_fts.rank "
                "FROM entities_fts "
                "JOIN entities e ON entities_fts.rowid = e.rowid "
                f"{where_clause} "
                "ORDER BY entities_fts.rank "
                "LIMIT ?"
            )
            params = [fts_query] + extra_params + [limit]
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(f"invalid_search_query: {exc}") from exc

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_lineage_markdown(
        self,
        type_id: str | None = None,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> str:
        """Export entity lineage as a markdown tree.

        Parameters
        ----------
        type_id:
            If provided (UUID or type_id), export only the tree rooted
            at this entity.  If None, export all trees (all root entities).
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            ``_resolve_optional_workspace_filter``. If provided, only include
            root entities in the resolved workspace.
        workspace_uuid:
            Workspace scope for root selection. Children are included via
            existing tree-walk from filtered roots.

        Returns
        -------
        str
            Markdown-formatted tree.
        """
        if type_id is not None:
            root_uuid, _ = self._resolve_identifier(
                type_id,
                project_id=project_id,
                workspace_uuid=workspace_uuid,
            )
            return self._export_tree(root_uuid)

        # Find all root entities (no parent).
        # Post-Migration-11: parent_type_id column was dropped; parent_uuid
        # is the single source of truth. Roots are entities with
        # parent_uuid IS NULL.
        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="export_lineage_markdown",
        )
        if ws_uuid is not None:
            cur = self._conn.execute(
                "SELECT uuid FROM entities WHERE parent_uuid IS NULL "
                "AND workspace_uuid = ? ORDER BY kind, name",
                (ws_uuid,),
            )
        else:
            cur = self._conn.execute(
                "SELECT uuid FROM entities WHERE parent_uuid IS NULL "
                "ORDER BY kind, name"
            )
        roots = [row["uuid"] for row in cur.fetchall()]

        if not roots:
            return ""

        parts: list[str] = []
        for root_uuid in roots:
            parts.append(self._export_tree(root_uuid))
        return "\n".join(parts)

    def _export_tree(self, root_uuid: str, max_depth: int = 50) -> str:
        """Export a single entity and its descendants as markdown.

        Uses a single recursive CTE with UUID-based traversal to fetch
        all descendants with their depth level, avoiding N+1 queries.

        Parameters
        ----------
        root_uuid:
            UUID of the root entity for the tree.
        max_depth:
            Maximum tree depth to traverse (default 50).
            When exceeded, a depth-limit indicator is appended.
        """
        cur = self._conn.execute(
            """
            WITH RECURSIVE tree(uid, depth) AS (
                SELECT ?, 0
                UNION ALL
                SELECT e.uuid, t.depth + 1
                FROM entities e
                JOIN tree t ON e.parent_uuid = t.uid
                WHERE t.depth < ?
            )
            SELECT e.*, e.kind AS entity_type, t.depth FROM tree t
            JOIN entities e ON e.uuid = t.uid
            ORDER BY t.depth ASC, e.kind, e.name
            """,
            (root_uuid, max_depth),
        )
        rows = [dict(row) for row in cur.fetchall()]

        if not rows:
            return ""

        # Check if any children were truncated at max_depth
        has_truncated = False
        deepest = max(r["depth"] for r in rows)
        if deepest >= max_depth:
            # Check if there are children beyond the limit
            leaf_ids = [r["uuid"] for r in rows if r["depth"] == deepest]
            for lid in leaf_ids:
                check = self._conn.execute(
                    "SELECT 1 FROM entities WHERE parent_uuid = ? LIMIT 1",
                    (lid,),
                )
                if check.fetchone() is not None:
                    has_truncated = True
                    break

        lines: list[str] = []
        for row in rows:
            depth = row["depth"]
            indent = "  " * depth
            status_str = f" [{row['status']}]" if row["status"] else ""
            line = (
                f"{indent}- **{row['name']}** "
                f"({row['entity_type']}:{row['entity_id']}){status_str}"
            )
            lines.append(line)

        if has_truncated:
            indent = "  " * (deepest + 1)
            lines.append(f"{indent}- ... (depth limit reached)")

        return "\n".join(lines)

    def export_entities_json(
        self,
        entity_type: str | None = None,
        status: str | None = None,
        include_lineage: bool = True,
        project_id: str | None = None,
    ) -> dict:
        """Export entities as a structured dict with schema version metadata.

        Parameters
        ----------
        entity_type:
            Filter by entity type. Must be one of VALID_ENTITY_TYPES if
            provided. Raises ValueError if invalid.
        status:
            Filter by status string. No validation (free-form).
        include_lineage:
            If True, include parent_type_id in each entity dict.
            If False, omit parent_type_id.
        project_id:
            If provided, only export entities from this project.
            If None, export entities across all projects.

        Returns
        -------
        dict
            Export envelope: {schema_version, exported_at, entity_count,
            filters_applied, entities: [...]}.
        """
        # 1. Validate entity_type (only when provided)
        if entity_type is not None:
            self._validate_entity_type(entity_type)

        # 2. Build query conditionally (matches list_entities pattern)
        # Feature 108: post-Migration-11 schema has workspace_uuid + parent_uuid
        # instead of project_id + parent_type_id. JOIN back to recover legacy
        # values for export envelope consumers.
        # F11 (Group 6): project ``e.kind`` to the legacy ``entity_type``
        # dict-key for export envelope consumers (TD-8 public API surface).
        query = (
            "SELECT e.uuid AS uuid, e.type_id AS type_id, "
            "e.kind AS entity_type, e.entity_id AS entity_id, "
            "e.name AS name, e.status AS status, "
            "e.artifact_path AS artifact_path, "
            "p.type_id AS parent_type_id, "
            "e.created_at AS created_at, e.updated_at AS updated_at, "
            "e.metadata AS metadata "
            "FROM entities e "
            "LEFT JOIN entities p ON e.parent_uuid = p.uuid "
            "LEFT JOIN workspaces w ON e.workspace_uuid = w.uuid"
        )
        conditions: list[str] = []
        params: list[str] = []
        if entity_type is not None:
            conditions.append("e.kind = ?")
            params.append(entity_type)
        if status is not None:
            conditions.append("e.status = ?")
            params.append(status)
        if project_id is not None:
            conditions.append("w.project_id_legacy = ?")
            params.append(project_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY e.created_at ASC, e.type_id ASC"

        rows = self._conn.execute(query, params).fetchall()

        # 3. Build entity dicts with metadata normalization
        entities: list[dict] = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            except (json.JSONDecodeError, ValueError):
                metadata = {}
            entity = {
                "uuid": row["uuid"],
                "type_id": row["type_id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "name": row["name"],
                "status": row["status"],
                "artifact_path": row["artifact_path"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": metadata,
            }
            if include_lineage:
                entity["parent_type_id"] = row["parent_type_id"]
            entities.append(entity)

        # 4. Assemble envelope
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now().astimezone().isoformat(),
            "entity_count": len(entities),
            "filters_applied": {
                "entity_type": entity_type,
                "status": status,
            },
            "entities": entities,
        }

    # ------------------------------------------------------------------
    # Phase Events (append-only analytics log)
    # ------------------------------------------------------------------

    def append_phase_event(
        self,
        *,
        type_id: str,
        project_id: str,
        event_type: str,
        timestamp: str | None = None,
        phase: str | None = None,
        iterations: int | None = None,
        reviewer_notes: str | None = None,
        backward_reason: str | None = None,
        backward_target: str | None = None,
        source: str = "live",
        workspace_uuid: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Append a phase event record AND project to the relevant state.

        **Signature history (feature 109):**

        - BEFORE (post-Group-0.5 rename, pre-Group-9 extension): byte-identical
          to legacy ``insert_phase_event`` —
          ``(type_id, project_id, phase, event_type, timestamp, iterations=None,
            reviewer_notes=None, backward_reason=None, backward_target=None,
            source='live')``.
          ``phase`` was positional-required.
        - AFTER (post-Group-9.5): adds ``workspace_uuid`` and ``metadata`` as
          keyword-only kwargs; relaxes ``phase`` to NULL-able (the new
          entity_* event types have no meaningful phase); ``timestamp``
          auto-generates ``_now_iso()`` when None.

        **Validation:** per spec FR-2 / design §3.1, each ``event_type`` accepts
        a closed set of discriminator kwargs (``_VALID_PARAMS``) and may require
        a non-None value for a subset (``_REQUIRED_PARAMS``). Base parameters
        (``project_id``, ``source``, ``timestamp``) are accepted for every
        event_type.

        **Operation order (inside a single ``self.transaction()`` block):**

        1. Validate per-event-type discriminator params (raise ValueError on
           mismatch).
        2. INSERT INTO phase_events.
        3. If ``event_type in {entity_status_changed, entity_promoted}``:
           UPDATE entities SET status, updated_at
           WHERE workspace_uuid = ? AND type_id = ?  ← workspace-scoped per
           PRD Goal 1 (prevent cross-workspace contamination).
        4. If ``event_type == 'entity_created'``: SKIP the entities UPDATE —
           ``register_entity`` already INSERTed the row with its final status
           and updated_at; a redundant UPDATE would overwrite ``updated_at``
           with a slightly later timestamp and break the
           ``entities.updated_at == phase_events.timestamp`` invariant.
        5. If ``event_type in {started, completed, skipped, backward}``:
           UPDATE workflow_phases SET workflow_phase, updated_at
           WHERE type_id = ?.

        Raises
        ------
        ValueError
            If ``event_type`` is unknown OR a kwarg violates ``_VALID_PARAMS``
            / ``_REQUIRED_PARAMS`` for the event_type.
        """
        # ------------------------------------------------------------------
        # Step 1: validate event_type + per-event-type discriminator shape
        # ------------------------------------------------------------------
        if event_type not in _VALID_PARAMS:
            raise ValueError(
                f"Invalid event_type {event_type!r}. Must be one of "
                f"{sorted(_VALID_PARAMS.keys())}"
            )

        # Bundle the discriminator kwargs by name so we can iterate.
        disc_values = {
            "phase": phase,
            "iterations": iterations,
            "reviewer_notes": reviewer_notes,
            "backward_reason": backward_reason,
            "backward_target": backward_target,
            "metadata": metadata,
        }
        allowed = _VALID_PARAMS[event_type]
        required = _REQUIRED_PARAMS.get(event_type, set())

        # (a) Disallow any non-None discriminator kwarg that is NOT in the
        # allowed set for this event_type.
        for key in _DISCRIMINATOR_KWARGS:
            if disc_values[key] is not None and key not in allowed:
                raise ValueError(
                    f"{key!r} is not valid for event_type={event_type!r}"
                )
        # (b) Require non-None for any kwarg in the required set.
        for key in required:
            if disc_values[key] is None:
                raise ValueError(
                    f"{key!r} is required for event_type={event_type!r}"
                )

        # Feature 088 FR-2.4 (defense-in-depth): DB-layer reviewer_notes cap.
        if reviewer_notes is not None and len(reviewer_notes) > 10000:
            raise ValueError("reviewer_notes exceeds 10000 chars")

        # workspace_uuid requirement for entity_* event types: needed for the
        # workspace-scoped UPDATE entities WHERE clause (PRD Goal 1).
        # entity_created is the exception — no UPDATE is issued for that
        # type, so workspace_uuid is informational only.
        if (
            event_type in ("entity_status_changed", "entity_promoted")
            and not workspace_uuid
        ):
            raise ValueError(
                f"workspace_uuid is required for event_type={event_type!r}"
            )

        # Resolve timestamp + JSON-encode metadata.
        if timestamp is None:
            timestamp = self._now_iso()
        metadata_json = (
            json.dumps(metadata) if metadata is not None else None
        )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ------------------------------------------------------------------
        # Steps 2-5: atomic INSERT + projection UPDATE inside one transaction.
        # ------------------------------------------------------------------
        with self.transaction():
            # Step 2: INSERT INTO phase_events.
            self._conn.execute(
                "INSERT INTO phase_events "
                "(type_id, project_id, phase, event_type, timestamp, "
                "iterations, reviewer_notes, backward_reason, "
                "backward_target, source, created_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    type_id, project_id, phase, event_type, timestamp,
                    iterations, reviewer_notes, backward_reason,
                    backward_target, source, now, metadata_json,
                ),
            )

            # Step 3: project entities.status for the two state-change
            # event types. entity_created is intentionally excluded — the
            # row was just INSERTed by register_entity with its final
            # status; a redundant UPDATE here would overwrite updated_at.
            if event_type in ("entity_status_changed", "entity_promoted"):
                # Both event types carry new_status in metadata (per the
                # per-event-type column-domain table) for status_changed;
                # entity_promoted does NOT necessarily carry a new_status
                # (it carries new_kind/new_lifecycle_class/new_type_id).
                # Only issue the status UPDATE when metadata['new_status']
                # is present.
                new_status = (metadata or {}).get("new_status")
                if new_status is not None:
                    self._conn.execute(
                        "UPDATE entities "
                        "SET status = ?, updated_at = ? "
                        "WHERE workspace_uuid = ? AND type_id = ?",
                        (new_status, timestamp, workspace_uuid, type_id),
                    )

            # Step 5: project workflow_phases.workflow_phase for the 4
            # workflow event types.
            elif event_type in (
                "started", "completed", "skipped", "backward"
            ):
                self._conn.execute(
                    "UPDATE workflow_phases "
                    "SET workflow_phase = ?, updated_at = ? "
                    "WHERE type_id = ?",
                    (phase, timestamp, type_id),
                )

            # Step 6 (feature 132 D5): v2 dual-write, same transaction as
            # steps 2-5. Pre-checking ``_is_v2_generation`` (rather than
            # relying solely on ``_emit_v2_event``'s own gate) skips the
            # entity lookup entirely on v1 files -- the overwhelming
            # majority of callers today. Resolve (entity_uuid, kind) from
            # type_id, workspace-scoped when workspace_uuid is known
            # (register_entity / upsert_entity / promote_entity /
            # update_entity / dependencies.py's cascade_ready all pass it).
            # Phase-transition callers (workflow_state_server.py) may pass
            # workspace_uuid=None; the unscoped fallback is exact for them
            # in practice because Step 5's own projection is ALSO keyed on
            # the bare type_id, which create_workflow_phase's UNIQUE
            # constraint makes globally unique in workflow_phases -- the
            # same scoping the v1 write above already relies on.
            if self._is_v2_generation:
                if workspace_uuid is not None:
                    entity_row = self._conn.execute(
                        "SELECT uuid, kind FROM entities "
                        "WHERE workspace_uuid = ? AND type_id = ?",
                        (workspace_uuid, type_id),
                    ).fetchone()
                else:
                    entity_row = self._conn.execute(
                        "SELECT uuid, kind FROM entities WHERE type_id = ?",
                        (type_id,),
                    ).fetchone()
                if entity_row is not None:
                    v2_axis, v2_to_value = _v2_classify_phase_event(
                        entity_row["kind"], event_type, phase, metadata
                    )
                    self._emit_v2_event(
                        entity_uuid=entity_row["uuid"],
                        event_type=event_type,
                        axis=v2_axis,
                        to_value=v2_to_value,
                        actor="live:append_phase_event",
                        payload=metadata if event_type == "entity_created" else None,
                    )

        return None

    def query_phase_events(
        self,
        *,
        type_id: str | None = None,
        project_id: str | None = None,
        phase: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query phase events with optional filters. All filters optional."""
        conditions: list[str] = []
        params: list = []
        if type_id:
            conditions.append("type_id = ?")
            params.append(type_id)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if phase:
            conditions.append("phase = ?")
            params.append(phase)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        # Clamp: limit < 0 is treated as 0 (0 rows, not SQLite LIMIT -1 =
        # unlimited); limit > 500 is capped at 500. ``limit=0`` honors
        # caller intent ("return 0 rows") rather than being coerced up to 1.
        params.append(max(0, min(limit, 500)))

        rows = self._conn.execute(
            f"SELECT {PHASE_EVENTS_COLS} FROM phase_events{where} "
            "ORDER BY timestamp DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def query_phase_events_bulk(
        self,
        type_ids: list[str],
        event_types: list[str] | None = None,
    ) -> list[dict]:
        """Bulk-fetch phase_events rows for multiple entities in O(1) queries.

        Used by the reconciliation drift detector (Feature 089 FR-2.2 /
        AC-9 / #00150) to eliminate an N+1 query pattern: instead of one
        ``query_phase_events`` call per (entity, phase, event_type)
        tuple, callers pass all ``type_ids`` at once and diff the result
        Python-side.

        Parameters
        ----------
        type_ids:
            Entity type_ids to fetch events for. Empty list returns ``[]``
            without issuing any query.
        event_types:
            Optional event-type filter. When ``None``, all event_types
            are returned. When a list, only rows whose ``event_type`` is
            in the list are returned.

        Returns
        -------
        list[dict]
            All matching phase_events rows (no LIMIT applied — caller is
            expected to aggregate in Python). Columns match
            ``PHASE_EVENTS_COLS``.

        Notes
        -----
        Input is chunked at 500 parameters per chunk to stay well under
        SQLite's default ``SQLITE_MAX_VARIABLE_NUMBER`` (999 pre-3.32,
        32766 after). With ``event_types`` also in the IN clause, the
        effective per-chunk budget is ``500 - len(event_types)``.
        """
        if not type_ids:
            return []

        # Feature 090 FR-4 / AC-4 (#00175): explicit empty-list short-circuit.
        # Pre-090 the filter guard was ``if event_types:`` — falsy for both
        # ``None`` and ``[]``, collapsing "no filter, match all" and "filter
        # by empty set, match none" into the same code path.  The correct
        # semantics: ``event_types=None`` means "no filter" (return all
        # event_types); ``event_types=[]`` means "filter by empty set"
        # (return zero rows, since no value can be ``IN ()``).  Returning
        # early here preserves the all-or-nothing SQL contract and avoids
        # issuing a query that would otherwise silently fall through to
        # the unfiltered branch.
        if event_types is not None and not event_types:
            return []

        # Budget accounting: SQLite's default host-parameter cap is 999.
        # We chunk type_ids well below that, reserving room for event_types.
        et_count = len(event_types) if event_types else 0
        chunk_size = max(1, 500 - et_count)

        results: list[dict] = []
        for start in range(0, len(type_ids), chunk_size):
            chunk = type_ids[start:start + chunk_size]
            placeholders_tid = ",".join("?" * len(chunk))
            params: list = list(chunk)
            where = f"type_id IN ({placeholders_tid})"
            if event_types is not None:
                # Empty-list case short-circuited above; here event_types
                # is a non-empty list.
                placeholders_et = ",".join("?" * len(event_types))
                where += f" AND event_type IN ({placeholders_et})"
                params.extend(event_types)
            rows = self._conn.execute(
                f"SELECT {PHASE_EVENTS_COLS} FROM phase_events "
                f"WHERE {where}",
                params,
            ).fetchall()
            results.extend(dict(r) for r in rows)
        return results

    # ------------------------------------------------------------------
    # Workflow Phase CRUD
    # ------------------------------------------------------------------

    def create_workflow_phase(
        self,
        type_id: str,
        *,
        kanban_column: str = "backlog",
        workflow_phase: str | None = None,
        last_completed_phase: str | None = None,
        mode: str | None = None,
        backward_transition_reason: str | None = None,
    ) -> dict:
        """Create a workflow_phases row for an existing entity.

        Parameters
        ----------
        type_id:
            The entity type_id (must exist in the entities table).
        kanban_column:
            Kanban column (default ``"backlog"``).
        workflow_phase:
            Current workflow phase (nullable).
        last_completed_phase:
            Last completed phase (nullable).
        mode:
            Workflow mode — ``"standard"`` or ``"full"`` (nullable).
        backward_transition_reason:
            Reason for backward transition (nullable).

        Returns
        -------
        dict
            The inserted row as a plain dict.

        Raises
        ------
        ValueError
            If the entity does not exist, a row already exists, or a
            CHECK constraint is violated.
        """
        # FK check: entity must exist. uuid + kind are also fetched here
        # (feature 132 D5) so the v2 establishment emit below can resolve
        # entity_uuid and route pipeline-vs-lifecycle without a second query.
        row = self._conn.execute(
            "SELECT type_id, uuid, kind FROM entities WHERE type_id = ?", (type_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Entity not found: {type_id}")

        now = self._now_iso()
        try:
            self._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, workflow_phase, "
                "last_completed_phase, mode, backward_transition_reason, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (type_id, kanban_column, workflow_phase,
                 last_completed_phase, mode, backward_transition_reason,
                 now),
            )
            # Feature 132 D5: the initial-establishment event, in the same
            # implicit transaction as the INSERT above (no self.transaction()
            # wrapper exists here; self._commit() below is the existing
            # atomicity boundary -- emitting before it keeps both writes
            # atomic without introducing a new transaction wrapper). Without
            # this, entities created post-cutover would diverge from a
            # replayed entity at SC3's axis-parity check (every OTHER entity
            # gets its first axis event from register_entity/append_phase_event;
            # this is the one writer of the five that currently emits nothing
            # at all). Pipeline for feature-kind (122's 6-value vocab),
            # lifecycle for every other kind; to_value = the initial
            # workflow_phase, NULL-safe (the vocab trigger's own
            # `to_value IS NOT NULL` guard never fires on NULL).
            self._emit_v2_event(
                entity_uuid=row["uuid"],
                event_type="workflow_established",
                axis="pipeline" if row["kind"] == "feature" else "lifecycle",
                to_value=workflow_phase,
                actor="live:create_workflow_phase",
            )
            self._commit()
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "UNIQUE constraint" in msg:
                raise ValueError(
                    f"Workflow phase already exists for: {type_id}"
                ) from e
            if "CHECK constraint" in msg:
                raise ValueError(f"Invalid value: {e}") from e
            raise ValueError(msg) from e

        result = self._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?", (type_id,)
        ).fetchone()
        return dict(result)

    def get_workflow_phase(self, type_id: str) -> dict | None:
        """Retrieve a workflow_phases row by type_id.

        Returns ``None`` if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?", (type_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def update_workflow_phase(
        self,
        type_id: str,
        *,
        kanban_column=_UNSET,
        workflow_phase=_UNSET,
        last_completed_phase=_UNSET,
        mode=_UNSET,
        backward_transition_reason=_UNSET,
        workspace_uuid: str | None = None,
    ) -> dict:
        """Update mutable fields of an existing workflow_phases row.

        Only fields explicitly passed are updated. Omitted fields (using
        the ``_UNSET`` sentinel) are left unchanged. Passing ``None``
        explicitly sets the column to NULL.

        Feature 132 D5: deliberately EXCLUDED from v2 dual-write duty.
        Per the check_status_write_path doctor guard's own fix_hint
        (``"Use upsert_workflow_phase / update_workflow_phase for
        non-state-change writes (kanban_column, mode, etc.)"``), this
        method is the PRESENTATIONAL sibling of append_phase_event's
        state-change writes -- it has no axis meaning of its own
        (kanban_column/mode/last_completed_phase are display/bookkeeping
        fields, not one of the three v2 axes), so it emits nothing.
        Contrast :meth:`create_workflow_phase`, which DOES emit (the
        INITIAL establishment of the row itself, not a presentational
        field update on an existing one).

        Parameters
        ----------
        type_id:
            The entity type_id (must have a workflow_phases row).
        kanban_column:
            New kanban column value.
        workflow_phase:
            New workflow phase value.
        last_completed_phase:
            New last completed phase value.
        mode:
            New mode value.
        backward_transition_reason:
            New backward transition reason value.
        workspace_uuid:
            Optional read-side workspace assertion (Feature 113 / FR-4.1).
            When non-None, SELECTs the stored ``workspace_uuid`` from
            ``workflow_phases`` and raises ``ValueError`` on mismatch BEFORE
            the UPDATE proceeds. Does NOT appear in the UPDATE SET clause —
            the column is immutable post-Migration-11 (autofill at INSERT
            only via ``wp_autofill_workspace_uuid`` trigger). Default ``None``
            preserves prior no-check behavior.

        Returns
        -------
        dict
            The updated row as a plain dict.

        Raises
        ------
        ValueError
            If the row does not exist, a CHECK constraint is violated, or
            ``workspace_uuid`` is provided and differs from the stored value.
        """
        # Existence check + (FR-4.1) workspace_uuid mismatch assertion
        # in a single SELECT.
        row = self._conn.execute(
            "SELECT type_id, workspace_uuid FROM workflow_phases "
            "WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Workflow phase not found: {type_id}")

        # Feature 113 / FR-4.1: read-side workspace assertion. The kwarg is
        # only checked when the caller opts in by passing a non-None value.
        # The column itself is NOT added to the UPDATE SET clause — it is
        # immutable post-Migration-11.
        if workspace_uuid is not None:
            existing_ws = row["workspace_uuid"]
            if existing_ws != workspace_uuid:
                raise ValueError(
                    f"workspace_uuid mismatch for {type_id}: "
                    f"stored={existing_ws!r}, provided={workspace_uuid!r}"
                )

        set_parts: list[str] = ["updated_at = ?"]
        params: list = [self._now_iso()]

        if kanban_column is not _UNSET:
            set_parts.append("kanban_column = ?")
            params.append(kanban_column)
        if workflow_phase is not _UNSET:
            set_parts.append("workflow_phase = ?")
            params.append(workflow_phase)
        if last_completed_phase is not _UNSET:
            set_parts.append("last_completed_phase = ?")
            params.append(last_completed_phase)
        if mode is not _UNSET:
            set_parts.append("mode = ?")
            params.append(mode)
        if backward_transition_reason is not _UNSET:
            set_parts.append("backward_transition_reason = ?")
            params.append(backward_transition_reason)

        params.append(type_id)
        sql = (
            f"UPDATE workflow_phases SET {', '.join(set_parts)} "
            f"WHERE type_id = ?"
        )
        try:
            self._conn.execute(sql, params)
            self._commit()
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "CHECK constraint" in msg:
                raise ValueError(f"Invalid value: {e}") from e
            raise ValueError(msg) from e

        result = self._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?", (type_id,)
        ).fetchone()
        return dict(result)

    def upsert_workflow_phase(
        self,
        type_id: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
        **kwargs,
    ) -> None:
        """Insert or update a workflow_phases row atomically.

        Uses INSERT OR IGNORE followed by UPDATE to handle both new and
        existing rows in a single call. Column names in *kwargs* are
        validated against an allow-list to prevent SQL injection.

        Feature 132 D5: deliberately EXCLUDED from v2 dual-write duty --
        presentational, same rationale as :meth:`update_workflow_phase`'s
        docstring (kanban_column/mode/etc. carry no axis meaning).

        Parameters
        ----------
        type_id:
            The entity type_id (e.g. ``"feature:my-feat"``).
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            ``_resolve_workspace_uuid_kwargs``. Defaults to ``"__unknown__"``
            when neither this nor ``workspace_uuid`` is supplied.
        workspace_uuid:
            Workspace scope for entity existence check. Post-Migration-11
            the entities table is keyed on (workspace_uuid, type_id).
        **kwargs:
            Mutable columns to set. Allowed keys: ``workflow_phase``,
            ``kanban_column``, ``last_completed_phase``, ``mode``,
            ``backward_transition_reason``, ``updated_at``.

        Raises
        ------
        ValueError
            If entity not found in the specified workspace, or if any
            key in *kwargs* is not in the allow-list.
        """
        ALLOWED_COLUMNS = {
            "workflow_phase",
            "kanban_column",
            "last_completed_phase",
            "mode",
            "backward_transition_reason",
            "updated_at",
        }
        invalid = set(kwargs) - ALLOWED_COLUMNS
        if invalid:
            raise ValueError(f"Invalid workflow_phases columns: {invalid}")

        # Resolve workspace identity (default __unknown__ when both omitted)
        if workspace_uuid is None and project_id is None:
            project_id = "__unknown__"
        try:
            ws_uuid = self._resolve_workspace_uuid_kwargs(
                workspace_uuid, project_id, _caller="upsert_workflow_phase"
            )
        except ValueError:
            # Unknown project_id_legacy → entity is "not found in project"
            raise ValueError(
                f"Entity {type_id!r} not found in project {project_id!r}"
            )

        # Entity existence check scoped by workspace_uuid
        entity_row = self._conn.execute(
            "SELECT uuid FROM entities "
            "WHERE workspace_uuid = ? AND type_id = ?",
            (ws_uuid, type_id),
        ).fetchone()
        if entity_row is None:
            # Compat error message preserves the legacy phrasing.
            scope = project_id if project_id is not None else ws_uuid
            raise ValueError(
                f"Entity {type_id!r} not found in project {scope!r}"
            )

        # Audit 062: 2 write SQL statements — wrapped in transaction() for BEGIN IMMEDIATE
        now = self._now_iso()
        wf = kwargs.get("workflow_phase")
        kc = kwargs.get("kanban_column", "backlog")

        with self.transaction():
            self._conn.execute(
                "INSERT OR IGNORE INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (type_id, wf, kc, now),
            )

            kwargs["updated_at"] = now
            set_parts = []
            params = []
            for key, value in kwargs.items():
                set_parts.append(f"{key} = ?")
                params.append(value)
            params.append(type_id)
            self._conn.execute(
                f"UPDATE workflow_phases SET {', '.join(set_parts)} "
                f"WHERE type_id = ?",
                params,
            )

            self._commit()  # no-op inside transaction(); commit handled by context manager

    def delete_workflow_phase(self, type_id: str) -> None:
        """Delete a workflow_phases row by type_id.

        Raises
        ------
        ValueError
            If no row exists for the given type_id.
        """
        row = self._conn.execute(
            "SELECT type_id FROM workflow_phases WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Workflow phase not found: {type_id}")

        self._conn.execute(
            "DELETE FROM workflow_phases WHERE type_id = ?", (type_id,)
        )
        self._commit()

    def list_workflow_phases(
        self,
        *,
        kanban_column: str | None = None,
        workflow_phase: str | None = None,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """List workflow_phases rows with optional filters.

        Parameters
        ----------
        kanban_column:
            If provided, filter by kanban_column.
        workflow_phase:
            If provided, filter by workflow_phase.
        workspace_uuid:
            If provided, scope to rows whose joined entity belongs to this
            workspace, PLUS orphan rows (workflow_phases rows whose entity
            was deleted — ``e.uuid IS NULL`` post-join). Orphans are
            RETAINED under scope for anomaly visibility (declared output
            change — see design D2/D4). ``None`` preserves today's
            unscoped return exactly.

        Returns
        -------
        list[dict]
            Matching rows as plain dicts. All filters use AND logic.
            Each row also carries ``execution_status`` / ``pipeline_phase``
            aliases of ``kanban_column`` / ``workflow_phase`` (feature 125's
            v1->v2 read bridge; physical columns rename at feature 132).
        """
        clauses: list[str] = []
        params: list = []

        if kanban_column is not None:
            clauses.append("wp.kanban_column = ?")
            params.append(kanban_column)
        if workflow_phase is not None:
            clauses.append("wp.workflow_phase = ?")
            params.append(workflow_phase)
        if workspace_uuid is not None:
            clauses.append("(e.workspace_uuid = ? OR e.uuid IS NULL)")
            params.append(workspace_uuid)

        # F11 (Group 6): project ``e.kind`` to the legacy ``entity_type``
        # result-set key for caller compatibility (TD-8 public API surface).
        # The execution_status/pipeline_phase aliases are feature 125's
        # v1->v2 read bridge (additive; UI reads them, non-UI callers keep
        # the wp.* keys) — collapses when 132 renames the physical columns.
        sql = (
            "SELECT wp.*, wp.kanban_column AS execution_status,"
            " wp.workflow_phase AS pipeline_phase,"
            " e.name AS entity_name, e.kind AS entity_type,"
            " e.artifact_path AS entity_artifact_path"
            " FROM workflow_phases wp"
            " LEFT JOIN entities e ON wp.type_id = e.type_id"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_workspaces_with_entities(self) -> list[dict]:
        """List workspaces that have at least one entity, with counts.

        Cross-workspace directory for the UI switcher (feature 130); the
        INNER JOIN against entities hides workspaces with zero entities.

        Returns
        -------
        list[dict]
            One dict per populated workspace with ``uuid``, ``project_root``,
            and ``entity_count`` keys. Ordered by ``entity_count`` descending,
            then ``project_root`` ascending as a tie-breaker (rows tying on
            BOTH keys -- e.g. split-brain duplicates sharing a project_root
            -- have no further contractual ordering).
        """
        sql = (
            "SELECT w.uuid, w.project_root, COUNT(e.uuid) AS entity_count "
            "FROM workspaces w JOIN entities e ON e.workspace_uuid = w.uuid "
            "GROUP BY w.uuid ORDER BY entity_count DESC, w.project_root"
        )
        rows = self._conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def get_metadata(self, key: str) -> str | None:
        """Read a metadata value by key, or ``None`` if missing."""
        cur = self._conn.execute(
            "SELECT value FROM _metadata WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row[0] if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        """Write a metadata key/value pair (upserts)."""
        self._conn.execute(
            "INSERT INTO _metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._commit()

    def get_schema_version(self) -> int:
        """Return the current schema version (0 if not yet migrated)."""
        return int(self.get_metadata("schema_version") or 0)

    # ------------------------------------------------------------------
    # Dependency management (encapsulates entity_relations kind='blocks')
    # ------------------------------------------------------------------

    def add_dependency(self, entity_uuid: str, blocked_by_uuid: str) -> None:
        """Add a dependency: entity_uuid is blocked by blocked_by_uuid.

        Uses INSERT OR IGNORE for idempotency.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO entity_relations "
            "(from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'blocks', ?)",
            (blocked_by_uuid, entity_uuid, self._now_iso()),
        )
        self._commit()

    def remove_dependency(self, entity_uuid: str, blocked_by_uuid: str) -> None:
        """Remove a single dependency. No-op if it doesn't exist."""
        self._conn.execute(
            "DELETE FROM entity_relations "
            "WHERE to_uuid = ? AND from_uuid = ? AND kind = 'blocks'",
            (entity_uuid, blocked_by_uuid),
        )
        self._commit()

    def query_dependencies(
        self,
        entity_uuid: str | None = None,
        blocked_by_uuid: str | None = None,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[dict]:
        """Query dependencies with flexible filtering.

        Parameters
        ----------
        entity_uuid:
            If provided, filter by the blocked entity.
        blocked_by_uuid:
            If provided, filter by the blocker entity.
        workspace_uuid:
            If provided, restrict results to dependencies whose blocked
            entity (``entity_uuid``) lives in this workspace. Cross-
            workspace edges (post-Migration-11 they should be rare) are
            excluded.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Both None for entity_uuid/blocked_by_uuid returns all dependencies
        (subject to the workspace filter, if any).

        Returns
        -------
        list[dict]
            Each dict has keys: entity_uuid, blocked_by_uuid.
        """
        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="query_dependencies"
        )

        conditions: list[str] = []
        params: list[str] = []
        if entity_uuid is not None:
            conditions.append("er.to_uuid = ?")
            params.append(entity_uuid)
        if blocked_by_uuid is not None:
            conditions.append("er.from_uuid = ?")
            params.append(blocked_by_uuid)
        if ws_uuid is not None:
            conditions.append("e.workspace_uuid = ?")
            params.append(ws_uuid)

        if ws_uuid is not None:
            # JOIN on entities to filter by workspace; the blocked-entity
            # side (to_uuid) carries the workspace identity for filtering.
            sql = (
                "SELECT er.to_uuid AS entity_uuid, "
                "er.from_uuid AS blocked_by_uuid "
                "FROM entity_relations er "
                "JOIN entities e ON e.uuid = er.to_uuid "
                "WHERE er.kind = 'blocks'"
            )
        else:
            sql = (
                "SELECT er.to_uuid AS entity_uuid, "
                "er.from_uuid AS blocked_by_uuid "
                "FROM entity_relations er "
                "WHERE er.kind = 'blocks'"
            )
        if conditions:
            sql += " AND " + " AND ".join(conditions)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def check_dependency_cycle(
        self,
        entity_uuid: str,
        blocked_by_uuid: str,
        max_depth: int = 20,
    ) -> bool:
        """Check if adding entity_uuid -> blocked_by_uuid would create a cycle.

        Uses a recursive CTE to walk from blocked_by_uuid's blockers
        looking for entity_uuid.

        Returns
        -------
        bool
            True if a cycle would be created (including self-dependency).
        """
        if entity_uuid == blocked_by_uuid:
            return True

        row = self._conn.execute(
            """
            WITH RECURSIVE dep_chain(uid, depth) AS (
                SELECT from_uuid, 0
                FROM entity_relations
                WHERE to_uuid = :blocked_by AND kind = 'blocks'
                UNION ALL
                SELECT er.from_uuid, dc.depth + 1
                FROM entity_relations er
                JOIN dep_chain dc ON er.to_uuid = dc.uid
                WHERE dc.depth < :max_depth AND er.kind = 'blocks'
            )
            SELECT 1 FROM dep_chain WHERE uid = :target
            LIMIT 1
            """,
            {
                "blocked_by": blocked_by_uuid,
                "target": entity_uuid,
                "max_depth": max_depth,
            },
        ).fetchone()

        return row is not None

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def scan_entity_ids(
        self,
        entity_type: str,
        project_id: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> list[str]:
        """Return all entity_id values for the given entity_type.

        Parameters
        ----------
        entity_type:
            The entity type to scan (e.g. "feature", "task").
        workspace_uuid:
            If provided, only return IDs from this workspace.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            JOIN on ``workspaces.project_id_legacy``.

        Returns
        -------
        list[str]
            List of entity_id strings.
        """
        # Feature 108: post-Migration-11 the entities table has no
        # ``project_id`` column. Resolve the legacy alias to a workspace_uuid.
        ws_uuid = self._resolve_optional_workspace_filter(
            workspace_uuid, project_id, _caller="scan_entity_ids"
        )
        # Feature 110 (Group 4 / FR-8.3a): prefer entity_display as the
        # source-of-truth for seq/slug identity. JOIN entity_display on
        # entities.uuid and reconstruct entity_id as ``{seq}-{slug}``. This
        # decouples the function from any future ``entities.entity_id`` column
        # rename and matches the design §5 invariant that entity_id parsing
        # only happens in ``_migration_13_*`` functions and test files.
        #
        # Defense-in-depth (per implementer brief): rows whose entity_display
        # row is missing (test fixtures inserted via raw SQL or
        # ``_register_entity_no_display``) fall back to the raw entity_id
        # value with a WARN log so the fixture continues to work during the
        # transition window.
        # F11 (Group 6): the legacy ``entity_type`` column was dropped by
        # migration 12; filter on ``kind`` (same value for the 5 production
        # kinds per FR-1).
        try:
            if ws_uuid is not None:
                rows = self._conn.execute(
                    "SELECT e.entity_id AS entity_id, "
                    "       d.seq AS seq, d.slug AS slug "
                    "FROM entities e "
                    "LEFT JOIN entity_display d ON d.uuid = e.uuid "
                    "WHERE e.kind = ? AND e.workspace_uuid = ?",
                    (entity_type, ws_uuid),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT e.entity_id AS entity_id, "
                    "       d.seq AS seq, d.slug AS slug "
                    "FROM entities e "
                    "LEFT JOIN entity_display d ON d.uuid = e.uuid "
                    "WHERE e.kind = ?",
                    (entity_type,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            # Pre-migration-13: entity_display table does not exist. Degrade
            # to the pre-port query shape so backfill, tests, and any caller
            # invoking scan_entity_ids before migration 13 still works.
            if "no such table" not in str(exc).lower():
                raise
            if ws_uuid is not None:
                rows = self._conn.execute(
                    "SELECT entity_id, NULL AS seq, NULL AS slug "
                    "FROM entities "
                    "WHERE kind = ? AND workspace_uuid = ?",
                    (entity_type, ws_uuid),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT entity_id, NULL AS seq, NULL AS slug "
                    "FROM entities WHERE kind = ?",
                    (entity_type,),
                ).fetchall()

        out: list[str] = []
        for row in rows:
            seq = row["seq"]
            slug = row["slug"]
            if seq is not None and slug is not None:
                out.append(f"{seq}-{slug}")
            else:
                # Defense-in-depth: entity_display row missing (e.g., test
                # fixture used _register_entity_no_display / raw SQL insert).
                sys.stderr.write(
                    f"[entity_registry] scan_entity_ids: no entity_display "
                    f"row for entity_id={row['entity_id']!r} "
                    f"(kind={entity_type}); falling back to entities.entity_id\n"
                )
                out.append(row["entity_id"])
        return out

    def next_sequence_value(
        self,
        project_id: str | None = None,
        entity_type: str | None = None,
        *,
        workspace_uuid: str | None = None,
    ) -> int:
        """Atomic read-increment-write for per-workspace, per-type sequence.

        Bootstraps from entities scan if no sequences row exists.
        Returns the next value to issue (pre-increment semantics:
        first call returns 1, second returns 2, etc.).

        Parameters
        ----------
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            ``_resolve_workspace_uuid_kwargs``. Accepted as the first
            positional arg for backward compat with id_generator and tests.
        entity_type:
            The entity type (e.g. "feature", "task"). Required.
        workspace_uuid:
            The workspace scope for the sequence (post-Migration-11 the
            sequences table is keyed on workspace_uuid).

        Returns
        -------
        int
            The next sequence value to use.
        """
        if entity_type is None:
            raise TypeError(
                "next_sequence_value() requires entity_type"
            )
        ws_uuid = self._resolve_workspace_uuid_kwargs(
            workspace_uuid, project_id, _caller="next_sequence_value"
        )
        self._conn.commit()  # flush any implicit transaction
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT next_val FROM sequences "
                "WHERE workspace_uuid = ? AND entity_type = ?",
                (ws_uuid, entity_type),
            ).fetchone()

            if row is None:
                # Bootstrap: scan entities for max sequence prefix.
                # F11 (Group 6): the entities table no longer has an
                # ``entity_type`` column; filter on ``kind`` (same value
                # for the 5 production kinds per FR-1).
                entity_rows = self._conn.execute(
                    "SELECT entity_id FROM entities "
                    "WHERE workspace_uuid = ? AND kind = ?",
                    (ws_uuid, entity_type),
                ).fetchall()
                max_seq = 0
                for (eid,) in entity_rows:
                    match = re.match(r"^(\d+)", eid)
                    if match:
                        max_seq = max(max_seq, int(match.group(1)))
                next_val = max_seq + 1
                self._conn.execute(
                    "INSERT INTO sequences(workspace_uuid, entity_type, next_val) "
                    "VALUES(?, ?, ?)",
                    (ws_uuid, entity_type, next_val + 1),
                )
            else:
                next_val = row[0]
                self._conn.execute(
                    "UPDATE sequences SET next_val = ? "
                    "WHERE workspace_uuid = ? AND entity_type = ?",
                    (next_val + 1, ws_uuid, entity_type),
                )

            self._conn.execute("COMMIT")
            return next_val
        except Exception:
            try:
                self._conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def get_entity_display(self, entity_uuid: str) -> dict | None:
        """Return the ``entity_display`` row for an entity, or ``None``.

        Feature 110 Group 6 helper: encapsulates the entity_display lookup
        so callers (e.g., ``backfill.py``) need not reach into the private
        ``_conn`` attribute. Degrades gracefully on pre-migration-13 DBs
        where the ``entity_display`` table does not yet exist.

        Returns a dict-like row with ``seq`` and ``slug`` columns, or
        ``None`` if no row exists (or the table is missing).
        """
        if not entity_uuid:
            return None
        try:
            row = self._conn.execute(
                "SELECT seq, slug FROM entity_display WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
        if row is None:
            return None
        # Convert to plain dict for consistency with other return shapes
        # and to insulate callers from the row_factory choice.
        return {"seq": row["seq"], "slug": row["slug"]}

    def is_healthy(self) -> bool:
        """Check if the database connection is alive and usable.

        Returns
        -------
        bool
            True if connection exists and can execute a simple query.
        """
        if self._conn is None:
            return False
        try:
            self._conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    # ------------------------------------------------------------------
    # Batch registration
    # ------------------------------------------------------------------

    def register_entities_batch(
        self,
        entities: list[dict],
        *,
        workspace_uuid: str | None = None,
        project_id: str | None = None,
    ) -> list[str]:
        """Register multiple entities in a single transaction.

        Feature 109 Group 14 / AC-4.5: the raw ``INSERT OR IGNORE INTO
        entities`` statement is replaced by a per-row loop calling
        :meth:`upsert_entity`. Idempotency is preserved by ``upsert_entity``'s
        three-branch semantics (insert / status-change / no-op). Each
        newly-inserted row emits one ``entity_created`` phase_event for
        event-stream parity (AC-2.2).

        Parameters
        ----------
        entities:
            List of dicts, each with keys: entity_type, entity_id, name,
            and optional: artifact_path, status, parent_uuid, metadata.
            ``parent_uuid`` (post-Feature-108) replaces the legacy
            ``parent_type_id`` dict key.
        workspace_uuid:
            Workspace identity applied to every entity in the batch.
            Required unless the deprecated ``project_id`` alias is supplied.
        project_id:
            DEPRECATED — legacy alias for ``workspace_uuid``. Resolved via
            ``workspaces.project_id_legacy``; ``"__unknown__"`` maps to
            the canonical ``_UNKNOWN_WORKSPACE_UUID``.

        Returns
        -------
        list[str]
            UUIDs of all entities (newly inserted OR pre-existing) in batch
            input order.

        Notes
        -----
        Invalid entity_type causes the entire batch to fail (none inserted).
        Duplicate (workspace_uuid, type_id) entries are no-ops via
        ``upsert_entity``'s conflict branch (no new uuid generated, no
        duplicate ``entity_created`` event emitted on replay).
        """
        if not entities:
            return []

        # Validate all entity_types upfront — fail fast on the entire batch.
        for ent in entities:
            self._validate_entity_type(ent["entity_type"])

        # Resolve workspace_uuid once so we pass it consistently to
        # upsert_entity (avoids per-row __unknown__ workspace bootstrap).
        ws_uuid = self._resolve_workspace_uuid_kwargs(
            workspace_uuid, project_id, _caller="register_entities_batch"
        )

        with self.transaction():
            uuids: list[str] = []
            for ent in entities:
                entity_type = ent["entity_type"]
                entity_id = ent["entity_id"]
                name = ent["name"]
                status = ent.get("status")
                artifact_path = ent.get("artifact_path")
                parent_uuid = ent.get("parent_uuid")
                metadata = ent.get("metadata")

                # F12 audit: idempotent bulk backfill → upsert_entity
                row_uuid = self.upsert_entity(
                    entity_type, entity_id, name,
                    workspace_uuid=ws_uuid,
                    status=status,
                    artifact_path=artifact_path,
                    parent_uuid=parent_uuid,
                    metadata=metadata,
                )
                uuids.append(row_uuid)
            return uuids

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC time as ISO-8601 string."""
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _validate_entity_type(cls, entity_type: str) -> None:
        """Raise ValueError if entity_type is not in the allowed set."""
        if entity_type not in cls.VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type {entity_type!r}. "
                f"Must be one of {cls.VALID_ENTITY_TYPES}"
            )

    # ------------------------------------------------------------------
    # Internal: pragmas and migrations
    # ------------------------------------------------------------------

    def _set_pragmas(self) -> None:
        """Set connection-level PRAGMAs for performance and safety."""
        # busy_timeout MUST be set first — journal_mode=WAL requires a write
        # that can be blocked by concurrent connections during init.
        self._conn.execute("PRAGMA busy_timeout = 15000")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA cache_size = -8000")

    def _migrate(self) -> None:
        """Apply any pending schema migrations."""
        # Bootstrap: ensure _metadata table exists so we can read schema_version.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._commit()

        # Feature 132 FR132-1: a v2-generation file's migrations are
        # already fully applied. The rebuild tool's own step-1 chain
        # replay (this very _migrate() call, against the still-unstamped
        # fresh staging file) is the sanctioned initial use — it runs
        # BEFORE the tool's step-3 stamp, so `schema_generation` is unset
        # here and this guard is a no-op for it. Every open AFTER the
        # stamp lands must short-circuit before the loop below: without
        # this guard, a future migration 20+ would silently auto-run
        # against the v2 file (rejected alternative: leaving the file at
        # v1 schema_version=19 with no marker — see spec FR132-1).
        generation_row = self._conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_generation'"
        ).fetchone()
        # Feature 132 D5: cache the v2-generation flag on `self` (NOT a
        # module-level dict keyed by the connection -- sqlite3.Connection
        # supports neither custom attributes nor weakrefs, so an id()-keyed
        # cache would risk a stale hit after id() reuse once a connection is
        # GC'd). One EntityDatabase instance wraps exactly one connection for
        # its whole lifetime and the generation is one-way (nothing ever
        # downgrades a stamped file back to v1), so computing it once here --
        # reusing the `_metadata` read the guard below already performs, no
        # extra query -- is correct for every subsequent `_emit_v2_event`
        # call on this instance.
        self._is_v2_generation = (
            generation_row is not None and generation_row[0] == "v2"
        )
        if self._is_v2_generation:
            return

        current = self.get_schema_version()
        target = max(MIGRATIONS)

        for version in range(current + 1, target + 1):
            migration_fn = MIGRATIONS[version]
            migration_fn(self._conn)
            _upsert_metadata(self._conn, "schema_version", str(version))
            self._commit()

    # ------------------------------------------------------------------
    # Feature 132 D5: v2 dual-write
    # ------------------------------------------------------------------

    def _emit_v2_event(
        self,
        *,
        entity_uuid: str,
        event_type: str,
        axis: str,
        to_value: str | None,
        from_value: str | None = None,
        actor: str,
        payload: dict | None = None,
    ) -> None:
        """Append a v2 ``events`` row alongside a v1 write, same transaction.

        Gated on ``self._is_v2_generation`` (cached once per connection in
        :meth:`_migrate`) -- a REAL branch, not decorative (design D5 /
        plan.md): v1 files have no ``events`` table at all, so an
        unconditional emit would raise ``OperationalError: no such table``
        on every v1 fixture in the suite; a never-emit stub would silently
        fail SC8 on v2 files. ONE shared implementation for every writer
        below so the axis/event_type/to_value mapping can never drift
        between call sites (design D5's explicit rationale for a single
        helper).

        Callers invoke this from INSIDE their own already-open
        ``self.transaction()`` (or, for ``create_workflow_phase``, the
        bare implicit transaction its INSERT opens) -- :func:`append_event`
        composes on ``conn.in_transaction`` and issues a bare parameterized
        INSERT with no COMMIT/ROLLBACK of its own in that case, so this
        call becomes part of the caller's atomic unit: an emit failure
        (e.g. the 122 vocab trigger rejecting an out-of-vocabulary
        ``to_value``, or the D7b uuid-collision guard) propagates and
        rolls back the caller's v1 write too (fail-closed, FR132-4b).
        """
        if not self._is_v2_generation:
            return
        from entity_registry.events import append_event
        append_event(
            self._conn,
            entity_uuid=entity_uuid,
            event_type=event_type,
            axis=axis,
            from_value=from_value,
            to_value=to_value,
            actor=actor,
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Project table operations
    # ------------------------------------------------------------------

    def upsert_project(
        self,
        project_id: str,
        name: str,
        root_commit_sha: str | None,
        remote_url: str | None,
        normalized_url: str | None,
        remote_host: str | None,
        remote_owner: str | None,
        remote_repo: str | None,
        default_branch: str | None,
        project_root: str,
        is_git_repo: bool,
        workspace_uuid: str | None = None,
    ) -> None:
        """Insert or update a project row, preserving created_at on conflict.

        Feature 108 (Decision 5): ``workspace_uuid`` is optional. When
        supplied (e.g. by ``mcp/entity_server.py::_upsert_project`` from the
        lifespan-resolved identity), a matching ``workspaces`` row is ensured
        before the projects INSERT so the FK resolves, and the column is
        written/refreshed on both INSERT and ON CONFLICT UPDATE. When omitted,
        the row is resolved by legacy ``project_id`` → ``project_root`` match
        → fresh mint, in that order.

        Parameters
        ----------
        project_id:
            Unique project identifier (e.g., SHA-based or path-based).
        name:
            Human-readable project name.
        root_commit_sha:
            SHA of the root commit (None for non-git projects).
        remote_url:
            Raw remote URL (None if no remote).
        normalized_url:
            Canonicalized remote URL for cross-machine matching.
        remote_host:
            Remote host (e.g., "github.com").
        remote_owner:
            Remote owner/org.
        remote_repo:
            Remote repository name.
        default_branch:
            Default branch name.
        project_root:
            Absolute path to the project root directory.
        is_git_repo:
            Whether the project is a git repository.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Canonicalize the root for all workspaces-row ops so they match
        # validate_or_adopt_workspace_uuid (which abspath()s) — avoids a silent
        # adoption miss when the caller passes a non-normalized absolute path.
        root_abs = os.path.abspath(project_root) if project_root else project_root

        def _single_root_or_raise(_caller: str):
            """Return the lone workspaces uuid for root_abs, or None if there
            is none. Raise on multi-row corruption (never bind arbitrarily)."""
            rows = self._conn.execute(
                "SELECT uuid FROM workspaces "
                "WHERE project_root IS NOT NULL AND project_root = ?",
                (root_abs,),
            ).fetchall()
            if len(rows) == 1:
                return rows[0]["uuid"]
            if len(rows) == 0:
                return None
            raise ValueError(
                f"{_caller}: project_root={root_abs!r} is claimed by "
                f"{len(rows)} workspace rows; refusing to bind ambiguously. "
                f"Manual repair required (inspect workspaces; run pd:doctor)."
            )

        # Feature 108 Migration 11: projects.workspace_uuid is NOT NULL.
        # Resolve / auto-bootstrap the workspaces row.
        if workspace_uuid is not None:
            # A caller-supplied identity (e.g. the lifespan-resolved
            # _workspace_uuid). Guarantee a matching workspaces row exists
            # BEFORE the projects INSERT or the FK fails (the original
            # split-brain bug: this path skipped row creation entirely).
            # Never mint a competing row for a project_root another uuid
            # already owns — adopt that canonical row instead.
            from entity_registry.project_identity import (
                _insert_workspace_row_if_absent,
            )
            outcome = _insert_workspace_row_if_absent(
                self._conn, workspace_uuid, root_abs, project_id
            )
            if outcome == "conflict-root":
                adopted = _single_root_or_raise("upsert_project()")
                # conflict-root guarantees ≥1 row; None is unreachable here.
                workspace_uuid = adopted
        else:
            # No identity supplied (incl. the lifespan ``_workspace_uuid or
            # None`` empty-string fallback when startup resolution failed).
            row = self._conn.execute(
                "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
                (project_id,),
            ).fetchone()
            if row is not None:
                workspace_uuid = row["uuid"]
            else:
                # Adopt a single project_root match (raise on multi-row);
                # mint only when the root is genuinely unclaimed.
                workspace_uuid = _single_root_or_raise("upsert_project()")
                if workspace_uuid is None:
                    from entity_registry.uuid7 import generate_uuid7
                    workspace_uuid = generate_uuid7()
                    self._conn.execute(
                        "INSERT INTO workspaces "
                        "(uuid, project_id_legacy, project_root, created_at, "
                        "updated_at) VALUES (?, ?, ?, ?, ?)",
                        (workspace_uuid, project_id, root_abs, now, now),
                    )
        self._conn.execute(
            """INSERT INTO projects (
                   project_id, name, root_commit_sha, remote_url,
                   normalized_url, remote_host, remote_owner, remote_repo,
                   default_branch, project_root, is_git_repo,
                   created_at, updated_at, workspace_uuid
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                   name=excluded.name,
                   root_commit_sha=excluded.root_commit_sha,
                   remote_url=excluded.remote_url,
                   normalized_url=excluded.normalized_url,
                   remote_host=excluded.remote_host,
                   remote_owner=excluded.remote_owner,
                   remote_repo=excluded.remote_repo,
                   default_branch=excluded.default_branch,
                   project_root=excluded.project_root,
                   is_git_repo=excluded.is_git_repo,
                   updated_at=excluded.updated_at,
                   workspace_uuid=excluded.workspace_uuid
            """,
            (
                project_id, name, root_commit_sha,
                remote_url, normalized_url, remote_host,
                remote_owner, remote_repo, default_branch,
                project_root, int(is_git_repo),
                now, now, workspace_uuid,
            ),
        )
        self._commit()

    def list_projects(self) -> list[dict]:
        """Return all project rows ordered by created_at.

        Returns
        -------
        list[dict]
            Each dict contains all columns from the projects table.
        """
        rows = self._conn.execute(
            "SELECT * FROM projects ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]
