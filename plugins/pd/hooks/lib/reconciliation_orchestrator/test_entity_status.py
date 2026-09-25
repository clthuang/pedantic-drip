"""Unit tests for reconciliation_orchestrator.entity_status — brainstorm registration.

Design W1.1 deleted the feature/project ``.meta.json`` status and archive
passes and the brainstorm archive of a missing ``.prd.md``; what remains
registers the checkout's new brainstorms and reads nothing else back.
"""
import json
import os
from unittest.mock import patch

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace, workspace_uuid_for
from reconciliation_orchestrator import entity_status
from reconciliation_orchestrator.entity_status import sync_entity_statuses
from entity_registry.test_helpers import identity_kwargs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> EntityDatabase:
    """Return a fresh in-memory EntityDatabase.

    Feature 108 Migration 11: pre-bootstraps a workspaces row for
    "test-project" (the legacy id used across this test module) so calls
    that pass project_id="test-project" resolve.
    """
    from entity_registry.test_helpers import bootstrap_test_workspace
    db = EntityDatabase(":memory:")
    bootstrap_test_workspace(db, "test-project")
    return db


def write_meta_json(directory: str, status: str) -> None:
    """Write a minimal .meta.json with the given status into directory."""
    os.makedirs(directory, exist_ok=True)
    meta = {"status": status}
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump(meta, f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMissingDirectoryHandled:
    """test_missing_directory_handled: brainstorms/ dir doesn't exist → empty results."""

    def test_missing_directory_handled(self, tmp_path):
        db = make_db()
        # tmp_path has no brainstorms/ subdir

        result = sync_entity_statuses(db, str(tmp_path))

        assert result == {"registered": 0, "skipped": 0, "warnings": []}


# ---------------------------------------------------------------------------
# _sync_brainstorm_entities tests
# ---------------------------------------------------------------------------


def seed_brainstorm(db: EntityDatabase, entity_id: str, status: str = "active",
                    artifact_path: str = "", project_id: str = "test-project") -> None:
    """Register a brainstorm entity in the workspace seeded as ``project_id``."""
    db.register_entity(
        entity_type="brainstorm",
        **identity_kwargs("brainstorm", entity_id),
        name=entity_id,
        status=status,
        artifact_path=artifact_path,
        workspace_uuid=workspace_uuid_for(db, project_id),
    )


class TestSyncBrainstormEntities:
    """Tests for entity_status._sync_brainstorm_entities (AC-8, AC-9)."""

    def test_new_brainstorm_registered(self, tmp_path):
        """A .prd.md file with no entity in registry -> entity registered as active."""
        db = make_db()
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "20260101-000018-foo.prd.md").touch()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["registered"] == 1
        entity = db.get_entity("brainstorm:20260101-000018-foo")
        assert entity is not None
        assert entity["status"] == "active"

    def test_existing_brainstorm_skipped(self, tmp_path):
        """Already-registered brainstorm -> skipped, no duplicate created."""
        db = make_db()
        seed_brainstorm(db, "20260101-000018-foo")
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "20260101-000018-foo.prd.md").touch()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["skipped"] == 1
        # No duplicate entity created
        entities = db.list_entities(entity_type="brainstorm")
        assert len(entities) == 1


class TestBrainstormAdversarial:
    """Adversarial tests for brainstorm sync edge cases."""

    def test_gitkeep_not_registered_as_brainstorm(self, tmp_path):
        """Adversarial: .gitkeep file in brainstorms/ dir is not registered.
        derived_from: dimension:adversarial (false positive file)
        """
        # Given a brainstorms dir with only .gitkeep
        db = make_db()
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / ".gitkeep").touch()

        # When brainstorm sync runs
        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        # Then no entity registered
        assert result["registered"] == 0
        assert db.list_entities(entity_type="brainstorm") == []


class TestMutationMindset:
    """Mutation-mindset tests: would swapping operators break things?"""

    def test_project_root_derivation_when_empty(self, tmp_path):
        """Mutation: if project_root derivation logic was removed, assertion would fire.
        derived_from: dimension:mutation_mindset (conditional branch — empty project_root)
        """
        # Given full_artifacts_path ends with artifacts_root and project_root is empty
        db = make_db()
        full_path = str(tmp_path / "docs")
        os.makedirs(full_path, exist_ok=True)

        # When sync_entity_statuses is called with empty project_root
        result = sync_entity_statuses(
            db, full_path, project_id="test-project",
            artifacts_root="docs", project_root="",
        )

        # Then it derives project_root successfully (no assertion error)
        # and returns valid results
        assert isinstance(result, dict)
        assert "registered" in result


# ---------------------------------------------------------------------------
# Unified sync integration test (Task 4.3)
# ---------------------------------------------------------------------------


class TestUnifiedSync:
    """Integration test: sync_entity_statuses reads only brainstorm files."""

    def test_unified_sync_registers_brainstorms_only(self, tmp_path):
        """A checkout with a drifted feature projection, a project projection
        and a new brainstorm file: only the brainstorm is registered (W1.1),
        and the result carries the brainstorm helper's keys."""
        db = make_db()

        # 1) Feature: seed as active, a stale .meta.json says completed
        feature_folder = "042-test"
        db.register_entity(
            entity_type="feature", **identity_kwargs("feature", feature_folder),
            name=feature_folder, status="active", workspace_uuid=workspace_uuid_for(db, "test-project"),
        )
        write_meta_json(str(tmp_path / "features" / feature_folder), status="completed")

        # 2) Project: .meta.json present, no entity in DB
        project_folder = "test-proj"
        (tmp_path / "projects" / project_folder).mkdir(parents=True)
        write_meta_json(str(tmp_path / "projects" / project_folder), status="active")

        # 3) Brainstorm: .prd.md file, no entity in DB -> registered
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "20260101-000002-bar.prd.md").touch()

        result = sync_entity_statuses(
            db, str(tmp_path),
            project_id="test-project",
            artifacts_root="docs",
            project_root=str(tmp_path),
        )

        assert result == {"registered": 1, "skipped": 0, "warnings": []}

        # The feature projection is not read back: the status stays active
        entity = db.get_entity(f"feature:{feature_folder}")
        assert entity["status"] == "active"
        assert db.get_entity(f"project:{project_folder}") is None

        # Brainstorm should have been registered
        assert db.get_entity("brainstorm:20260101-000002-bar") is not None


# ---------------------------------------------------------------------------
# A3 — reconciliation is non-destructive and workspace-scoped
# ---------------------------------------------------------------------------


class _WriteSpy:
    """Record every mutating call reconciliation makes on the db.

    Survival of a row is NOT evidence of non-deletion: every live entity
    has an ``events`` row and ``delete_entity`` raises
    ``sqlite3.IntegrityError`` unconditionally (database.py), so rows
    survive a deletion attempt regardless. Only the call count
    discriminates.
    """

    _METHODS = ("delete_entity", "upsert_entity", "register_entity", "update_entity")

    def __init__(self, db):
        self.db = db
        self.calls: dict[str, list] = {m: [] for m in self._METHODS}
        self._orig: dict[str, object] = {}

    def __enter__(self):
        for name in self._METHODS:
            orig = getattr(self.db, name)
            self._orig[name] = orig

            def wrapper(*a, _orig=orig, _sink=self.calls[name], **kw):
                _sink.append((a, kw))
                return _orig(*a, **kw)

            setattr(self.db, name, wrapper)
        return self

    def __exit__(self, *exc):
        for name, orig in self._orig.items():
            setattr(self.db, name, orig)
        return False

    @property
    def deletes(self):
        return self.calls["delete_entity"]

    @property
    def creates(self):
        return self.calls["upsert_entity"] + self.calls["register_entity"]


class TestReconciliationIsNonDestructive:
    """A3: zero deletions under every scoping and data condition."""

    def test_workspace_scoped_invocation_deletes_nothing(self, tmp_path):
        """Fixture 1: workspace_uuid set, project_id suppressed."""
        db = EntityDatabase(":memory:")
        ws = bootstrap_test_workspace(db, "ws-a-legacy")
        db.register_entity(entity_type="backlog", seq=42, slug="backlog",
                           name="legacy five-digit", status="open",
                           workspace_uuid=ws)
        db.register_entity(entity_type="backlog", seq=77, slug="modern-slug",
                           name="modern slug id", status="open",
                           workspace_uuid=ws)

        with _WriteSpy(db) as spy:
            result = sync_entity_statuses(
                db, str(tmp_path), project_id="ws-a-legacy",
                project_root=str(tmp_path), workspace_uuid=ws,
            )

        assert spy.deletes == []
        assert result == {"registered": 0, "skipped": 0, "warnings": []}
        # Both id shapes survive: neither is "junk".
        assert db.get_entity("backlog:042-backlog") is not None
        assert db.get_entity("backlog:077-modern-slug") is not None

    def test_missing_display_row_and_missing_source_survive(self, tmp_path):
        """Fixture 3: no entity_display row AND no artifact on disk.

        FORWARD GUARD — this cannot go red against the pre-A1 code, because
        neither the old nor the new implementation uses this criterion. It
        exists because "absent display row + absent source" is the tempting
        replacement criterion for the text-shape one A1 removed, and 180
        legitimate live entities match it. It goes red the moment someone
        adopts it.
        """
        db = EntityDatabase(":memory:")
        ws = bootstrap_test_workspace(db, "ws-a-legacy")
        entity_uuid = db.register_entity(
            entity_type="backlog", seq=53, slug="backlog",
            name="no display row, no file", status="open", workspace_uuid=ws,
        )
        # Registration always writes a display row; drop it for the legacy
        # rows' shape.
        db._conn.execute("DELETE FROM entity_display WHERE uuid = ?", (entity_uuid,))
        assert db._conn.execute(
            "SELECT COUNT(*) c FROM entity_display d "
            "JOIN entities e ON e.uuid = d.uuid WHERE e.entity_id = '053-backlog'"
        ).fetchone()["c"] == 0, "fixture precondition: no display row"

        with _WriteSpy(db) as spy:
            sync_entity_statuses(
                db, str(tmp_path), project_id="ws-a-legacy",
                project_root=str(tmp_path), workspace_uuid=ws,
            )

        assert spy.deletes == []
        assert db.get_entity("backlog:053-backlog") is not None

    def test_reconciliation_creates_nothing_from_a_projection(self, tmp_path):
        """A1 amendment: zero creations, not merely zero deletions.

        docs/backlog.md is a rendered projection whose ID column is
        re-padded to five digits, so parsing it back minted a fresh entity
        for every row whose padded id did not resolve. Zero-deletes alone
        passes while that happens.
        """
        db = EntityDatabase(":memory:")
        ws = bootstrap_test_workspace(db, "ws-a-legacy")
        db.register_entity(entity_type="backlog", seq=278, slug="entity-rename",
                           name="live item", status="open", workspace_uuid=ws)
        # The projection renders seq 278 as "00278" — a string that resolves
        # to no entity. Reconciliation must not treat it as an import source.
        (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backlog.md").write_text(
            "# Backlog\n\n| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            "| 00278 | 2026-01-01T00:00:00Z | live item |\n"
            "| 00003 | 2026-01-01T00:00:00Z | belongs to another workspace |\n"
        )
        before = db._conn.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"]

        with _WriteSpy(db) as spy:
            sync_entity_statuses(
                db, str(tmp_path), project_id="ws-a-legacy",
                project_root=str(tmp_path), workspace_uuid=ws,
            )

        after = db._conn.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"]
        assert spy.deletes == []
        assert spy.creates == [], f"reconciliation created entities: {spy.creates}"
        assert after == before, f"entity count changed {before} -> {after}"
        assert db.get_entity("backlog:00278") is None
        assert db.get_entity("backlog:00003") is None

    def test_a_failing_brainstorm_helper_is_returned_as_a_warning(self, tmp_path):
        """A3: a helper failure never escapes sync_entity_statuses.

        Three helpers ran before W1.1, each isolated so that one failing
        could not abort the others. The brainstorm helper is the one left;
        its failure is still returned as a warning, never raised, so
        session start carries on.
        """
        db = EntityDatabase(":memory:")
        ws = bootstrap_test_workspace(db, "ws-a-legacy")
        (tmp_path / "brainstorms").mkdir(parents=True)

        original = db.upsert_entity

        def exploding_upsert(*a, **kw):
            if kw.get("entity_type") == "brainstorm":
                raise RuntimeError("brainstorm helper blew up")
            return original(*a, **kw)

        (tmp_path / "brainstorms" / "boom.prd.md").touch()
        with patch.object(db, "upsert_entity", side_effect=exploding_upsert):
            result = sync_entity_statuses(
                db, str(tmp_path), project_id="ws-a-legacy",
                project_root=str(tmp_path), workspace_uuid=ws,
            )

        assert result == {
            "registered": 0, "skipped": 0,
            "warnings": ["brainstorms: brainstorm helper blew up"],
        }
        assert db.get_entity("brainstorm:boom") is None
