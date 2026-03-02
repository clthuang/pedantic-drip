"""SQLite database layer for the entity registry system."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid as uuid_mod
from collections.abc import Callable
from datetime import datetime, timezone

_UUID_V4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)


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


# Ordered mapping of version -> migration function.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_initial_schema,
    2: _migrate_to_uuid_pk,
    3: _create_workflow_phases_table,
}

# Sentinel object to distinguish "not provided" from explicit ``None``.
_UNSET = object()


class EntityDatabase:
    """SQLite-backed storage for entity registry.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file, or ``":memory:"`` for an
        in-memory database.
    """

    VALID_ENTITY_TYPES = ("backlog", "brainstorm", "project", "feature")

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, timeout=5.0)
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
            One of: backlog, brainstorm, project, feature.
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
        self._conn.execute(
            "INSERT OR IGNORE INTO entities "
            "(uuid, type_id, entity_type, entity_id, name, status, "
            "parent_type_id, parent_uuid, artifact_path, "
            "created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_uuid, type_id, entity_type, entity_id, name, status,
             parent_type_id, parent_uuid, artifact_path, now, now,
             metadata_json),
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

        # Circular reference detection via UUID-based CTE
        cur = self._conn.execute(
            """
            WITH RECURSIVE anc(uid) AS (
                SELECT parent_uuid FROM entities WHERE uuid = :parent_uuid
                UNION ALL
                SELECT e.parent_uuid FROM entities e
                JOIN anc a ON e.uuid = a.uid
                WHERE e.parent_uuid IS NOT NULL
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
                # Shallow merge with existing — fetch current metadata
                row = self._conn.execute(
                    "SELECT metadata FROM entities WHERE uuid = ?",
                    (entity_uuid,),
                ).fetchone()
                existing_meta = {}
                if row and row["metadata"] is not None:
                    existing_meta = json.loads(row["metadata"])
                existing_meta.update(metadata)
                set_parts.append("metadata = ?")
                params.append(json.dumps(existing_meta))

        params.append(entity_uuid)
        sql = f"UPDATE entities SET {', '.join(set_parts)} WHERE uuid = ?"
        self._conn.execute(sql, params)
        self._conn.commit()

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
            clauses.append("kanban_column = ?")
            params.append(kanban_column)
        if workflow_phase is not None:
            clauses.append("workflow_phase = ?")
            params.append(workflow_phase)

        sql = "SELECT * FROM workflow_phases"
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
