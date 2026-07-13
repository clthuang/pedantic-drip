"""Dependency cycle detection and management for entity relationships.

Task 1b.6: DependencyManager with cycle detection via recursive CTE,
cascade unblock on entity completion.

Feature 124: the store is entity_relations(kind='blocks') (Migration 18
unified the prior dual-representation into this single table). The cascade
flips a resolved-blocker's dependents `blocked -> ready` (not `planned`);
edges SURVIVE completion (FR124-4c) -- only entity_relations' FK ON DELETE
CASCADE removes rows, and only on entity deletion.
"""
from __future__ import annotations

from entity_registry.database import EntityDatabase


class CycleError(ValueError):
    """Raised when adding a dependency would create a cycle."""
    pass


# ---------------------------------------------------------------------------
# Feature 124 D4 -- per-kind completion predicate (design-pinned table, NOT a
# MACHINE_REGISTRY consultation: 'bug' is deliberately absent from that
# registry, so a runtime lookup is impossible). Sourced from ENTITY_MACHINES
# graphs (brainstorm/backlog), _CLOSES_TERMINAL (task/bug closes= terminals,
# database.py:75-78), and the 5D/feature 'completed' execution status.
# ---------------------------------------------------------------------------
_RESOLVED_STATUSES: dict[str, tuple[str, ...]] = {
    "feature": ("completed",),
    "project": ("completed",),
    "initiative": ("completed",),
    "objective": ("completed",),
    "key_result": ("completed",),
    "task": ("completed", "closed"),
    "bug": ("closed", "resolved", "wont_fix"),
    "brainstorm": ("promoted", "abandoned"),
    "backlog": ("promoted", "dropped"),
}


def _blocker_completed(entity: dict) -> bool:
    """Return True if entity's status is a resolved terminal for its kind.

    The single per-kind predicate (spec FR124-5) -- collapses the four
    inline `status == "completed"` sites (database.py's cascade trigger,
    dependency_freshness.py, checks.py's missed-cascade check (task 3),
    and entity_engine.py's deliver-phase gate) onto one design-pinned table.
    """
    kind = entity.get("kind") or entity.get("entity_type")
    return entity.get("status") in _RESOLVED_STATUSES.get(kind, ())


class DependencyManager:
    """Manages entity dependencies (blocked_by relationships).

    Uses entity_relations(kind='blocks') (unified in Migration 18). Cycle
    detection delegated to EntityDatabase.check_dependency_cycle.
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
        """Flip dependents of a resolved blocker from 'blocked' to 'ready'.

        Feature 124 (FR124-4): edges SURVIVE (no tombstoning -- the blocks
        row stays as an audit trail); a dependent flips only when ALL of
        its blockers satisfy `_blocker_completed` (D4), not merely because
        this one completed. Returns the list of flipped entity UUIDs (shape
        preserved from the pre-124 tombstone behavior).
        """
        affected = self.get_dependents(db, completed_uuid)
        if not affected:
            return []
        return self._evaluate_and_flip(db, affected)

    def _all_blockers_resolved(
        self, db: EntityDatabase, entity_uuid: str
    ) -> bool:
        """Return True iff every blocker of entity_uuid is resolved (D4).

        Vacuously True when there are no blockers -- load-bearing for the
        deletion path (D5.3): a dependent whose last blocker was just
        deleted has zero remaining blockers, so it is vacuously resolved
        and flips.
        """
        for blocker_uuid in self.get_blockers(db, entity_uuid):
            blocker = db.get_entity_by_uuid(blocker_uuid)
            if blocker is None or not _blocker_completed(blocker):
                return False
        return True

    def _evaluate_and_flip(
        self, db: EntityDatabase, dependent_uuids: list[str]
    ) -> list[str]:
        """Flip each still-blocked, fully-resolved dependent to 'ready'.

        Shared by cascade_unblock (over get_dependents) and delete_entity's
        unblock-on-delete hook (over its PRE-captured dependents -- the FK
        cascade has already emptied their edges by the time this runs, so
        the hook must NOT call cascade_unblock(deleted_uuid) itself).

        Each flip is its own atomic transaction (FR124-4d): the status
        write and the `cascade_ready` phase_events row land together via a
        RE-ENTRANT `db.transaction()` (never begin_immediate, which raises
        under any caller-held transaction).
        """
        flipped: list[str] = []
        for uid in dependent_uuids:
            entity = db.get_entity_by_uuid(uid)
            if entity is None or entity.get("status") != "blocked":
                continue
            if not self._all_blockers_resolved(db, uid):
                continue
            with db.transaction():
                db.update_entity(entity["type_id"], status="ready")
                db.append_phase_event(
                    type_id=entity["type_id"],
                    project_id=entity.get("project_id") or "__unknown__",
                    workspace_uuid=entity.get("workspace_uuid"),
                    event_type="cascade_ready",
                    phase=None,
                    metadata={
                        "from_value": "blocked",
                        "to_value": "ready",
                        "actor": "system:cascade",
                    },
                )
            flipped.append(uid)
        return flipped

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
