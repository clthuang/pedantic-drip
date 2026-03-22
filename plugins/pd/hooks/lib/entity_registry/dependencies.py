"""Dependency cycle detection and management for entity relationships.

Task 1b.6: DependencyManager with cycle detection via recursive CTE,
cascade unblock on entity completion.
"""
from __future__ import annotations

from entity_registry.database import EntityDatabase


class CycleError(ValueError):
    """Raised when adding a dependency would create a cycle."""
    pass


class DependencyManager:
    """Manages entity dependencies (blocked_by relationships).

    Uses the entity_dependencies table created in migration 6.
    Cycle detection via recursive CTE with max depth 20.
    """

    MAX_DEPTH = 20

    def add_dependency(
        self, db: EntityDatabase, entity_uuid: str, blocked_by_uuid: str
    ) -> None:
        """Add a dependency: entity_uuid is blocked by blocked_by_uuid.

        Parameters
        ----------
        db:
            Open EntityDatabase instance.
        entity_uuid:
            UUID of the entity that is blocked.
        blocked_by_uuid:
            UUID of the entity that blocks it.

        Raises
        ------
        CycleError
            If the dependency would create a cycle (including self-dependency).
        ValueError
            If either entity does not exist.
        """
        # Self-dependency check
        if entity_uuid == blocked_by_uuid:
            raise CycleError("Cannot add self-dependency")

        # Existence checks
        if db.get_entity_by_uuid(entity_uuid) is None:
            raise ValueError(f"Entity not found: {entity_uuid}")
        if db.get_entity_by_uuid(blocked_by_uuid) is None:
            raise ValueError(f"Entity not found: {blocked_by_uuid}")

        # Cycle detection
        self._check_cycle(db, entity_uuid, blocked_by_uuid)

        # Insert (IGNORE for idempotency on duplicate)
        db._conn.execute(
            "INSERT OR IGNORE INTO entity_dependencies "
            "(entity_uuid, blocked_by_uuid) VALUES (?, ?)",
            (entity_uuid, blocked_by_uuid),
        )
        db._conn.commit()

    def _check_cycle(
        self, db: EntityDatabase, entity_uuid: str, blocked_by_uuid: str
    ) -> None:
        """Check if adding entity_uuid -> blocked_by_uuid creates a cycle.

        Uses a recursive CTE to walk the dependency graph starting from
        blocked_by_uuid's blockers, checking if we can reach entity_uuid.
        If so, adding this edge would create a cycle.

        Max traversal depth: 20.
        """
        # Walk from blocked_by_uuid upward through its blockers.
        # If entity_uuid is reachable, adding entity_uuid -> blocked_by_uuid
        # would create a cycle.
        row = db._conn.execute(
            """
            WITH RECURSIVE dep_chain(uid, depth) AS (
                -- Start: what does blocked_by_uuid depend on?
                SELECT blocked_by_uuid, 0
                FROM entity_dependencies
                WHERE entity_uuid = :blocked_by
                UNION ALL
                SELECT ed.blocked_by_uuid, dc.depth + 1
                FROM entity_dependencies ed
                JOIN dep_chain dc ON ed.entity_uuid = dc.uid
                WHERE dc.depth < :max_depth
            )
            SELECT 1 FROM dep_chain WHERE uid = :target
            LIMIT 1
            """,
            {
                "blocked_by": blocked_by_uuid,
                "target": entity_uuid,
                "max_depth": self.MAX_DEPTH,
            },
        ).fetchone()

        if row is not None:
            raise CycleError(
                f"Adding dependency would create a cycle: "
                f"{entity_uuid} -> {blocked_by_uuid} creates a back-edge"
            )

    def remove_dependency(
        self, db: EntityDatabase, entity_uuid: str, blocked_by_uuid: str
    ) -> None:
        """Remove a dependency. No-op if it doesn't exist."""
        db._conn.execute(
            "DELETE FROM entity_dependencies "
            "WHERE entity_uuid = ? AND blocked_by_uuid = ?",
            (entity_uuid, blocked_by_uuid),
        )
        db._conn.commit()

    def cascade_unblock(
        self, db: EntityDatabase, completed_uuid: str
    ) -> list[str]:
        """Remove completed entity from all blocked_by lists.

        Returns list of entity UUIDs that are now fully unblocked
        (have zero remaining blockers after this removal).
        """
        # Find all entities that were blocked by the completed entity
        blocked_rows = db._conn.execute(
            "SELECT entity_uuid FROM entity_dependencies "
            "WHERE blocked_by_uuid = ?",
            (completed_uuid,),
        ).fetchall()

        if not blocked_rows:
            return []

        affected_uuids = [row["entity_uuid"] for row in blocked_rows]

        # Remove all deps where blocked_by = completed_uuid
        db._conn.execute(
            "DELETE FROM entity_dependencies WHERE blocked_by_uuid = ?",
            (completed_uuid,),
        )
        db._conn.commit()

        # Check which affected entities are now fully unblocked
        fully_unblocked = []
        for uid in affected_uuids:
            remaining = db._conn.execute(
                "SELECT 1 FROM entity_dependencies WHERE entity_uuid = ? LIMIT 1",
                (uid,),
            ).fetchone()
            if remaining is None:
                fully_unblocked.append(uid)

        return fully_unblocked

    def get_blockers(
        self, db: EntityDatabase, entity_uuid: str
    ) -> list[str]:
        """Return UUIDs of entities that block the given entity."""
        rows = db._conn.execute(
            "SELECT blocked_by_uuid FROM entity_dependencies "
            "WHERE entity_uuid = ?",
            (entity_uuid,),
        ).fetchall()
        return [row["blocked_by_uuid"] for row in rows]

    def get_dependents(
        self, db: EntityDatabase, entity_uuid: str
    ) -> list[str]:
        """Return UUIDs of entities blocked by the given entity."""
        rows = db._conn.execute(
            "SELECT entity_uuid FROM entity_dependencies "
            "WHERE blocked_by_uuid = ?",
            (entity_uuid,),
        ).fetchall()
        return [row["entity_uuid"] for row in rows]
