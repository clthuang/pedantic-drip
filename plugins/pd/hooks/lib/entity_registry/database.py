"""SQLite database layer for the entity registry system."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid as uuid_mod
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone

_UUID_V4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)

# Tag format: lowercase letters, digits, hyphens. 1-50 chars. No leading/trailing hyphens.
_TAG_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$')


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
        CREATE TRIGGER IF NOT EXISTS enforce_immutable_type_id
        BEFORE UPDATE OF type_id ON entities
        BEGIN
            SELECT RAISE(ABORT, 'type_id is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_immutable_entity_type
        BEFORE UPDATE OF entity_type ON entities
        BEGIN
            SELECT RAISE(ABORT, 'entity_type is immutable');
        END;

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

        # Recreate all 8 triggers
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_type_id
            BEFORE UPDATE OF type_id ON entities
            BEGIN SELECT RAISE(ABORT, 'type_id is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS enforce_immutable_entity_type
            BEFORE UPDATE OF entity_type ON entities
            BEGIN SELECT RAISE(ABORT, 'entity_type is immutable'); END
        """)
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

        # Copy all existing data
        conn.execute(
            "INSERT INTO workflow_phases_new SELECT * FROM workflow_phases"
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

        # Recreate all 8 triggers on entities
        conn.execute("""
            CREATE TRIGGER enforce_immutable_type_id
            BEFORE UPDATE OF type_id ON entities
            BEGIN SELECT RAISE(ABORT, 'type_id is immutable'); END
        """)
        conn.execute("""
            CREATE TRIGGER enforce_immutable_entity_type
            BEFORE UPDATE OF entity_type ON entities
            BEGIN SELECT RAISE(ABORT, 'entity_type is immutable'); END
        """)
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


# Ordered mapping of version -> migration function.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_initial_schema,
    2: _migrate_to_uuid_pk,
    3: _create_workflow_phases_table,
    4: _create_fts_index,
    5: _expand_workflow_phase_check,
    6: _schema_expansion_v6,
}

# Sentinel object to distinguish "not provided" from explicit ``None``.
_UNSET = object()

# Export format version — separate from the DB schema version.
EXPORT_SCHEMA_VERSION = 1


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
    )

    def __init__(self, db_path: str, *, check_same_thread: bool = True) -> None:
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

    # ------------------------------------------------------------------
    # Internal: identifier resolution
    # ------------------------------------------------------------------

    def _resolve_identifier(self, identifier: str) -> tuple[str, str]:
        """Resolve a UUID or type_id to a (uuid, type_id) tuple.

        Parameters
        ----------
        identifier:
            Either a UUID v4 string or a type_id string.

        Returns
        -------
        tuple[str, str]
            (uuid, type_id) of the found entity.

        Raises
        ------
        ValueError
            If no entity matches the identifier.
        """
        if _UUID_V4_RE.match(identifier.lower()):
            row = self._conn.execute(
                "SELECT uuid, type_id FROM entities WHERE uuid = ?",
                (identifier.lower(),),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT uuid, type_id FROM entities WHERE type_id = ?",
                (identifier,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Entity not found: {identifier!r}")
        return (row["uuid"], row["type_id"])

    # ------------------------------------------------------------------
    # UUID lookup and flexible ref resolution (Task 1b.3a)
    # ------------------------------------------------------------------

    def get_entity_by_uuid(self, uuid: str) -> dict | None:
        """Retrieve a single entity by UUID.

        Returns entity dict or None if not found (or input is not a valid UUID).
        """
        row = self._conn.execute(
            "SELECT * FROM entities WHERE uuid = ?", (uuid,)
        ).fetchone()
        return dict(row) if row else None

    def resolve_ref(self, ref: str) -> str:
        """Resolve a flexible reference to a single entity UUID.

        Resolution order:
        1. If ref looks like a UUID (36 chars, has dashes), look up by uuid.
        2. Try as exact type_id.
        3. Try as type_id prefix.
           - Single match: return that uuid.
           - Multiple matches: raise ValueError with candidate list.
           - No matches: raise ValueError.

        Parameters
        ----------
        ref:
            UUID string, full type_id, or type_id prefix.

        Returns
        -------
        str
            The resolved entity UUID.

        Raises
        ------
        ValueError
            If ref is ambiguous (multiple prefix matches) or not found.
        """
        # 1. Try as UUID
        if _UUID_V4_RE.match(ref.lower()):
            entity = self.get_entity_by_uuid(ref.lower())
            if entity is not None:
                return entity["uuid"]
            raise ValueError(f"No entity found matching ref: {ref!r}")

        # 2. Try as exact type_id
        row = self._conn.execute(
            "SELECT uuid FROM entities WHERE type_id = ?", (ref,)
        ).fetchone()
        if row is not None:
            return row["uuid"]

        # 3. Try as prefix
        matches = self.search_by_type_id_prefix(ref)
        if len(matches) == 1:
            return matches[0]["uuid"]
        if len(matches) > 1:
            candidates = [m["type_id"] for m in matches]
            raise ValueError(
                f"Multiple entities match ref {ref!r}: {candidates}"
            )

        raise ValueError(f"No entity found matching ref: {ref!r}")

    # ------------------------------------------------------------------
    # Prefix search and transaction helpers (Task 1b.3b)
    # ------------------------------------------------------------------

    def search_by_type_id_prefix(self, prefix: str) -> list[dict]:
        """Search for entities whose type_id starts with the given prefix.

        Parameters
        ----------
        prefix:
            The type_id prefix to match (e.g. "feature:05").

        Returns
        -------
        list[dict]
            List of matching entity dicts.
        """
        # Use LIKE with escaped prefix for efficient prefix search.
        # Escape any existing % or _ in the prefix to prevent SQL injection.
        escaped = prefix.replace("%", "\\%").replace("_", "\\_")
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE type_id LIKE ? ESCAPE '\\'",
            (escaped + "%",),
        ).fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def begin_immediate(self):
        """Context manager that wraps a block in BEGIN IMMEDIATE.

        Commits on success, rolls back on exception. Yields the connection.

        Usage::

            with db.begin_immediate() as conn:
                conn.execute("UPDATE ...")
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

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
        self._conn.commit()

    def remove_tag(self, entity_uuid: str, tag: str) -> None:
        """Remove a tag from an entity. Silent if tag not present."""
        self._conn.execute(
            "DELETE FROM entity_tags WHERE entity_uuid = ? AND tag = ?",
            (entity_uuid, tag),
        )
        self._conn.commit()

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
        rows = self._conn.execute(
            "SELECT e.* FROM entities e "
            "JOIN entity_tags et ON e.uuid = et.entity_uuid "
            "WHERE et.tag = ? "
            "ORDER BY e.entity_type, e.name",
            (tag,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def register_entity(
        self,
        entity_type: str,
        entity_id: str,
        name: str,
        artifact_path: str | None = None,
        status: str | None = None,
        parent_type_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Register an entity with INSERT OR IGNORE semantics.

        Parameters
        ----------
        entity_type:
            One of the VALID_ENTITY_TYPES (backlog, brainstorm, project,
            feature, initiative, objective, key_result, task).
        entity_id:
            Unique identifier within the entity_type namespace.
        name:
            Human-readable name.
        artifact_path:
            Optional filesystem path to the entity's artifact.
        status:
            Optional status string.
        parent_type_id:
            Optional type_id of the parent entity (must exist).
        metadata:
            Optional dict stored as JSON TEXT.

        Returns
        -------
        str
            The UUID of the registered (or already-existing) entity.
        """
        self._validate_entity_type(entity_type)
        type_id = f"{entity_type}:{entity_id}"
        now = self._now_iso()
        metadata_json = json.dumps(metadata) if metadata is not None else None

        # Resolve parent_uuid from parent_type_id if provided
        parent_uuid = None
        if parent_type_id is not None:
            parent_row = self._conn.execute(
                "SELECT uuid FROM entities WHERE type_id = ?",
                (parent_type_id,),
            ).fetchone()
            if parent_row is not None:
                parent_uuid = parent_row["uuid"]

        entity_uuid = str(uuid_mod.uuid4())
        cursor = self._conn.execute(
            "INSERT OR IGNORE INTO entities "
            "(uuid, type_id, entity_type, entity_id, name, status, "
            "parent_type_id, parent_uuid, artifact_path, "
            "created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_uuid, type_id, entity_type, entity_id, name, status,
             parent_type_id, parent_uuid, artifact_path, now, now,
             metadata_json),
        )
        if cursor.rowcount == 1:
            row = self._conn.execute(
                "SELECT rowid FROM entities WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()
            metadata_text = flatten_metadata(
                json.loads(metadata_json) if metadata_json else None
            )
            self._conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, "
                "entity_type, status, metadata_text) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], name, entity_id, entity_type, status or "",
                 metadata_text),
            )
        self._conn.commit()
        result = self._conn.execute(
            "SELECT uuid FROM entities WHERE type_id = ?", (type_id,)
        ).fetchone()
        return result["uuid"]

    def set_parent(self, type_id: str, parent_type_id: str) -> str:
        """Set or change the parent of an entity.

        Parameters
        ----------
        type_id:
            The entity to update (UUID or type_id).
        parent_type_id:
            The new parent entity (UUID or type_id, must exist).

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
        child_uuid, child_type_id = self._resolve_identifier(type_id)
        parent_uuid, parent_type_id_resolved = self._resolve_identifier(
            parent_type_id
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
            "UPDATE entities SET parent_type_id = ?, parent_uuid = ?, "
            "updated_at = ? WHERE uuid = ?",
            (parent_type_id_resolved, parent_uuid, self._now_iso(),
             child_uuid),
        )
        self._conn.commit()
        return child_uuid

    def get_entity(self, type_id: str) -> dict | None:
        """Retrieve a single entity by UUID or type_id.

        Returns ``None`` if not found.
        """
        try:
            uuid, _ = self._resolve_identifier(type_id)
        except ValueError:
            return None
        row = self._conn.execute(
            "SELECT * FROM entities WHERE uuid = ?", (uuid,)
        ).fetchone()
        return dict(row) if row else None

    def list_entities(self, entity_type: str | None = None) -> list[dict]:
        """Return all entities, optionally filtered by entity_type.

        Parameters
        ----------
        entity_type:
            If provided, only return entities of this type.
            If None, return all entities.

        Returns
        -------
        list[dict]
            List of entity dicts with same keys as ``get_entity``.
        """
        if entity_type is not None:
            cur = self._conn.execute(
                "SELECT * FROM entities WHERE entity_type = ?",
                (entity_type,),
            )
        else:
            cur = self._conn.execute("SELECT * FROM entities")
        return [dict(row) for row in cur.fetchall()]

    def get_lineage(
        self,
        type_id: str,
        direction: str = "up",
        max_depth: int = 10,
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

        Returns
        -------
        list[dict]
            Ordered list of entity dicts. Empty if type_id not found.
        """
        try:
            resolved_uuid, _ = self._resolve_identifier(type_id)
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

        Raises
        ------
        ValueError
            If the entity does not exist.
        """
        # Resolve identifier directly (accepts both UUID and type_id).
        # Lets ValueError propagate naturally if entity not found.
        entity_uuid, _ = self._resolve_identifier(type_id)

        # FTS sync: capture old values before UPDATE
        old_row = self._conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities WHERE uuid = ?",
            (entity_uuid,),
        ).fetchone()

        set_parts: list[str] = ["updated_at = ?"]
        params: list = [self._now_iso()]

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
                existing_meta = (
                    json.loads(old_row["metadata"])
                    if old_row["metadata"] else {}
                )
                existing_meta.update(metadata)
                set_parts.append("metadata = ?")
                params.append(json.dumps(existing_meta))

        params.append(entity_uuid)
        sql = f"UPDATE entities SET {', '.join(set_parts)} WHERE uuid = ?"
        self._conn.execute(sql, params)

        # Re-read post-UPDATE values from DB rather than deriving them in
        # Python. This avoids replicating the metadata-merge logic (None/keep,
        # {}/clear, dict/shallow-merge) and uses the DB as single source of
        # truth. If new FTS-indexed fields are added, update both the
        # old-value SELECT and the FTS insert columns.
        new_row = self._conn.execute(
            "SELECT name, entity_id, entity_type, status, metadata "
            "FROM entities WHERE uuid = ?",
            (entity_uuid,),
        ).fetchone()
        old_meta_text = flatten_metadata(
            json.loads(old_row["metadata"]) if old_row["metadata"] else None
        )
        new_meta_text = flatten_metadata(
            json.loads(new_row["metadata"]) if new_row["metadata"] else None
        )
        self._conn.execute(
            "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
            "entity_type, status, metadata_text) "
            "VALUES('delete', ?, ?, ?, ?, ?, ?)",
            (old_row["rowid"], old_row["name"], old_row["entity_id"],
             old_row["entity_type"], old_row["status"] or "",
             old_meta_text),
        )
        self._conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (old_row["rowid"], new_row["name"], new_row["entity_id"],
             new_row["entity_type"], new_row["status"] or "",
             new_meta_text),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_entity(self, type_id: str) -> None:
        """Delete an entity and all associated data (FTS, workflow_phases).

        Parameters
        ----------
        type_id : str
            Entity type_id in format "{entity_type}:{entity_id}".

        Raises
        ------
        ValueError
            If entity does not exist.
        ValueError
            If entity has child entities (must delete children first).
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # 1. Validate + fetch old values for FTS cleanup
            row = self._conn.execute(
                "SELECT uuid, rowid, name, entity_id, entity_type, status, metadata "
                "FROM entities WHERE type_id = ?", (type_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Entity not found: {type_id}")

            # 2. Reject if has children
            child = self._conn.execute(
                "SELECT 1 FROM entities WHERE parent_uuid = ? LIMIT 1",
                (row["uuid"],),
            ).fetchone()
            if child is not None:
                raise ValueError(f"Cannot delete entity with children: {type_id}")

            # 3. FTS5 external-content delete (before row deletion)
            try:
                metadata_text = flatten_metadata(
                    json.loads(row["metadata"]) if row["metadata"] else None
                )
            except (json.JSONDecodeError, TypeError):
                metadata_text = ""  # corrupted metadata — use empty for FTS delete
            self._conn.execute(
                "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
                "entity_type, status, metadata_text) "
                "VALUES('delete', ?, ?, ?, ?, ?, ?)",
                (row["rowid"], row["name"], row["entity_id"],
                 row["entity_type"], row["status"] or "", metadata_text),
            )

            # 4. Delete workflow_phases (FK: must precede entity delete)
            self._conn.execute(
                "DELETE FROM workflow_phases WHERE type_id = ?", (type_id,)
            )

            # 5. Delete entity row
            self._conn.execute(
                "DELETE FROM entities WHERE type_id = ?", (type_id,)
            )

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

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

        try:
            if entity_type is not None:
                rows = self._conn.execute(
                    "SELECT e.*, entities_fts.rank "
                    "FROM entities_fts "
                    "JOIN entities e ON entities_fts.rowid = e.rowid "
                    "WHERE entities_fts MATCH ? AND e.entity_type = ? "
                    "ORDER BY entities_fts.rank "
                    "LIMIT ?",
                    (fts_query, entity_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT e.*, entities_fts.rank "
                    "FROM entities_fts "
                    "JOIN entities e ON entities_fts.rowid = e.rowid "
                    "WHERE entities_fts MATCH ? "
                    "ORDER BY entities_fts.rank "
                    "LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            raise ValueError(f"invalid_search_query: {exc}") from exc

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_lineage_markdown(
        self, type_id: str | None = None
    ) -> str:
        """Export entity lineage as a markdown tree.

        Parameters
        ----------
        type_id:
            If provided (UUID or type_id), export only the tree rooted
            at this entity.  If None, export all trees (all root entities).

        Returns
        -------
        str
            Markdown-formatted tree.
        """
        if type_id is not None:
            root_uuid, _ = self._resolve_identifier(type_id)
            return self._export_tree(root_uuid)

        # Find all root entities (no parent).
        # Uses parent_type_id (not parent_uuid) — both are kept in sync by
        # set_parent(); parent_type_id is the authoritative column for root
        # detection since backfill populates it from artifact metadata.
        cur = self._conn.execute(
            "SELECT uuid FROM entities WHERE parent_type_id IS NULL "
            "ORDER BY entity_type, name"
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
            SELECT e.*, t.depth FROM tree t
            JOIN entities e ON e.uuid = t.uid
            ORDER BY t.depth ASC, e.entity_type, e.name
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
        query = (
            "SELECT uuid, type_id, entity_type, entity_id, name, status, "
            "artifact_path, parent_type_id, created_at, updated_at, metadata "
            "FROM entities"
        )
        conditions: list[str] = []
        params: list[str] = []
        if entity_type is not None:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at ASC, type_id ASC"

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
        # FK check: entity must exist
        row = self._conn.execute(
            "SELECT type_id FROM entities WHERE type_id = ?", (type_id,)
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
            self._conn.commit()
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
    ) -> dict:
        """Update mutable fields of an existing workflow_phases row.

        Only fields explicitly passed are updated. Omitted fields (using
        the ``_UNSET`` sentinel) are left unchanged. Passing ``None``
        explicitly sets the column to NULL.

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

        Returns
        -------
        dict
            The updated row as a plain dict.

        Raises
        ------
        ValueError
            If the row does not exist or a CHECK constraint is violated.
        """
        # Existence check
        row = self._conn.execute(
            "SELECT type_id FROM workflow_phases WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Workflow phase not found: {type_id}")

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
            self._conn.commit()
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "CHECK constraint" in msg:
                raise ValueError(f"Invalid value: {e}") from e
            raise ValueError(msg) from e

        result = self._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?", (type_id,)
        ).fetchone()
        return dict(result)

    def upsert_workflow_phase(self, type_id: str, **kwargs) -> None:
        """Insert or update a workflow_phases row atomically.

        Uses INSERT OR IGNORE followed by UPDATE to handle both new and
        existing rows in a single call. Column names in *kwargs* are
        validated against an allow-list to prevent SQL injection.

        Parameters
        ----------
        type_id:
            The entity type_id (e.g. ``"feature:my-feat"``).
        **kwargs:
            Mutable columns to set. Allowed keys: ``workflow_phase``,
            ``kanban_column``, ``last_completed_phase``, ``mode``,
            ``backward_transition_reason``, ``updated_at``.

        Raises
        ------
        ValueError
            If any key in *kwargs* is not in the allow-list.
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

        now = self._now_iso()
        wf = kwargs.get("workflow_phase")
        kc = kwargs.get("kanban_column", "backlog")

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

        self._conn.commit()

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
        self._conn.commit()

    def list_workflow_phases(
        self,
        *,
        kanban_column: str | None = None,
        workflow_phase: str | None = None,
    ) -> list[dict]:
        """List workflow_phases rows with optional filters.

        Parameters
        ----------
        kanban_column:
            If provided, filter by kanban_column.
        workflow_phase:
            If provided, filter by workflow_phase.

        Returns
        -------
        list[dict]
            Matching rows as plain dicts. Both filters use AND logic.
        """
        clauses: list[str] = []
        params: list = []

        if kanban_column is not None:
            clauses.append("wp.kanban_column = ?")
            params.append(kanban_column)
        if workflow_phase is not None:
            clauses.append("wp.workflow_phase = ?")
            params.append(workflow_phase)

        sql = (
            "SELECT wp.*, e.name AS entity_name, e.entity_type AS entity_type,"
            " e.artifact_path AS entity_artifact_path"
            " FROM workflow_phases wp"
            " LEFT JOIN entities e ON wp.type_id = e.type_id"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        rows = self._conn.execute(sql, params).fetchall()
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
        self._conn.commit()

    def get_schema_version(self) -> int:
        """Return the current schema version (0 if not yet migrated)."""
        return int(self.get_metadata("schema_version") or 0)

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
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA cache_size = -8000")

    def _migrate(self) -> None:
        """Apply any pending schema migrations."""
        # Bootstrap: ensure _metadata table exists so we can read schema_version.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

        current = self.get_schema_version()
        target = max(MIGRATIONS)

        for version in range(current + 1, target + 1):
            migration_fn = MIGRATIONS[version]
            migration_fn(self._conn)
            self._conn.execute(
                "INSERT INTO _metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("schema_version", str(version)),
            )
            self._conn.commit()
