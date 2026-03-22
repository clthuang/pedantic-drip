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
    Cycle detection delegated to EntityDatabase.check_dependency_cycle.
    """

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
        db.add_dependency(entity_uuid, blocked_by_uuid)

    def _check_cycle(
        self, db: EntityDatabase, entity_uuid: str, blocked_by_uuid: str
    ) -> None:
        """Check if adding entity_uuid -> blocked_by_uuid creates a cycle.

        Delegates to EntityDatabase.check_dependency_cycle which uses a
        recursive CTE with max depth 20.
        """
        if db.check_dependency_cycle(entity_uuid, blocked_by_uuid):
            raise CycleError(
                f"Adding dependency would create a cycle: "
                f"{entity_uuid} -> {blocked_by_uuid} creates a back-edge"
            )

    def remove_dependency(
        self, db: EntityDatabase, entity_uuid: str, blocked_by_uuid: str
    ) -> None:
        """Remove a dependency. No-op if it doesn't exist."""
        db.remove_dependency(entity_uuid, blocked_by_uuid)

    def cascade_unblock(
        self, db: EntityDatabase, completed_uuid: str
    ) -> list[str]:
        """Remove completed entity from all blocked_by lists.

        Returns list of entity UUIDs that are now fully unblocked
        (have zero remaining blockers after this removal).
        """
        # Find all entities that were blocked by the completed entity
        affected_deps = db.query_dependencies(blocked_by_uuid=completed_uuid)

        if not affected_deps:
            return []

        affected_uuids = [d["entity_uuid"] for d in affected_deps]

        # Remove all deps where blocked_by = completed_uuid
        db.remove_dependencies_by_blocker(completed_uuid)

        # Check which affected entities are now fully unblocked
        # and update their status from 'blocked' to 'planned' (per design C4/AC-29)
        fully_unblocked = []
        for uid in affected_uuids:
            remaining = db.query_dependencies(entity_uuid=uid)
            if not remaining:
                fully_unblocked.append(uid)
                # Update status: blocked → planned
                entity = db.get_entity_by_uuid(uid)
                if entity and entity.get("status") == "blocked":
                    db.update_entity(entity["type_id"], status="planned")

        return fully_unblocked

    def get_blockers(
        self, db: EntityDatabase, entity_uuid: str
    ) -> list[str]:
        """Return UUIDs of entities that block the given entity."""
        return [d["blocked_by_uuid"] for d in db.query_dependencies(entity_uuid=entity_uuid)]

    def get_dependents(
        self, db: EntityDatabase, entity_uuid: str
    ) -> list[str]:
        """Return UUIDs of entities blocked by the given entity."""
        return [d["entity_uuid"] for d in db.query_dependencies(blocked_by_uuid=entity_uuid)]
