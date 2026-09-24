"""Unit tests for reconciliation_orchestrator.entity_status — sync functions."""
import json
import os
import tempfile
import warnings
from unittest.mock import patch

import pytest

from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID
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


def seed_feature(db: EntityDatabase, folder: str, status: str) -> None:
    """Register a feature entity with the given folder name and status."""
    db.register_entity(
        entity_type="feature",
        **identity_kwargs("feature", folder),
        name=folder,
        status=status,
        workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
    )


def seed_project(db: EntityDatabase, folder: str, status: str) -> None:
    """Register a project entity with the given folder name and status."""
    db.register_entity(
        entity_type="project",
        **identity_kwargs("project", folder),
        name=folder,
        status=status,
        workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
    )


def write_meta_json(directory: str, status: str) -> None:
    """Write a minimal .meta.json with the given status into directory."""
    os.makedirs(directory, exist_ok=True)
    meta = {"status": status}
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump(meta, f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDriftedStatusUpdated:
    """test_drifted_status_updated: .meta.json status differs from entity status → updated."""

    def test_drifted_status_updated(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="completed")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 1
        assert result["skipped"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []

        # Verify the entity DB was actually updated
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "completed"


class TestNoDriftSkipped:
    """test_no_drift_skipped: matching statuses → no update, counted as skipped."""

    def test_no_drift_skipped(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="active")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert result["skipped"] == 1
        assert result["archived"] == 0
        assert result["warnings"] == []

        # Entity status unchanged
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestMissingMetaJsonArchived:
    """test_missing_meta_json_archived: entity exists, .meta.json missing → archived."""

    def test_missing_meta_json_archived(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        # Create the folder but NOT .meta.json
        feature_dir = tmp_path / "features" / folder
        feature_dir.mkdir(parents=True)

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["archived"] == 1
        assert result["updated"] == 0
        assert result["warnings"] == []

        entity = db.get_entity(f"feature:{folder}")
        assert entity["is_archived"] == 1


class TestMalformedJsonWarned:
    """test_malformed_json_warned: corrupt .meta.json → warning, entity skipped."""

    def test_malformed_json_warned(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        feature_dir = tmp_path / "features" / folder
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{ this is not valid json }")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert len(result["warnings"]) == 1
        assert ".meta.json" in result["warnings"][0]

        # Entity status must not have changed
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestUnknownStatusSkipped:
    """test_unknown_status_skipped: .meta.json status="draft" → warning, entity skipped."""

    def test_unknown_status_skipped(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="draft")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert len(result["warnings"]) == 1
        assert "draft" in result["warnings"][0]

        # Entity unchanged
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestEntityNotInRegistrySkipped:
    """test_entity_not_in_registry_skipped: .meta.json exists, no entity in DB → skipped."""

    def test_entity_not_in_registry_skipped(self, tmp_path):
        db = make_db()
        # No entity registered
        folder = "042-some-feature"

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="active")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["skipped"] == 1
        assert result["updated"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []


class TestMissingDirectoryHandled:
    """test_missing_directory_handled: features/ dir doesn't exist → empty results."""

    def test_missing_directory_handled(self, tmp_path):
        db = make_db()
        # tmp_path has no features/ or projects/ subdirs

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []


class TestProjectsScanned:
    """test_projects_scanned: projects/ dir is scanned with the same sync logic."""

    def test_projects_scanned(self, tmp_path):
        db = make_db()
        folder = "001-my-project"
        seed_project(db, folder, status="active")

        projects_dir = tmp_path / "projects" / folder
        write_meta_json(str(projects_dir), status="completed")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 1
        assert result["warnings"] == []

        entity = db.get_entity(f"project:{folder}")
        assert entity["status"] == "completed"

    def test_projects_missing_meta_json_archived(self, tmp_path):
        """Entity in registry, project folder exists but .meta.json deleted → archived."""
        db = make_db()
        folder = "001-my-project"
        seed_project(db, folder, status="active")

        # Folder exists, no .meta.json
        project_dir = tmp_path / "projects" / folder
        project_dir.mkdir(parents=True)

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["archived"] == 1

        entity = db.get_entity(f"project:{folder}")
        assert entity["is_archived"] == 1


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

    def test_missing_prd_file_archived(self, tmp_path):
        """AC-9: brainstorm entity exists but .prd.md file deleted -> status archived."""
        db = make_db()
        seed_brainstorm(
            db, "20260101-000018-foo", status="active",
            artifact_path="docs/brainstorms/20260101-000018-foo.prd.md",
            project_id="test-project",
        )
        # Do NOT create the file — it should be detected as missing
        # brainstorms dir must exist for the scan to proceed
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["archived"] == 1
        entity = db.get_entity("brainstorm:20260101-000018-foo")
        assert entity["is_archived"] == 1

    def test_terminal_brainstorm_not_rearchived(self, tmp_path):
        """Brainstorm with terminal status (promoted) -> not re-archived even if file missing."""
        db = make_db()
        seed_brainstorm(
            db, "20260101-000018-foo", status="promoted",
            artifact_path="docs/brainstorms/20260101-000018-foo.prd.md",
            project_id="test-project",
        )
        # No file created — but promoted is terminal, should not be touched
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["archived"] == 0
        entity = db.get_entity("brainstorm:20260101-000018-foo")
        assert entity["status"] == "promoted"


class TestBrainstormAdversarial:
    """Adversarial tests for brainstorm sync edge cases."""

    def test_brainstorm_with_empty_artifact_path_not_archived(self, tmp_path):
        """Adversarial: brainstorm entity with empty artifact_path → NOT archived.
        The archival logic requires artifact_path to be non-empty to proceed.
        derived_from: dimension:adversarial (empty artifact_path guard)
        """
        # Given a brainstorm entity with empty artifact_path (no file to check)
        db = make_db()
        seed_brainstorm(db, "20260101-000002-bar", status="active", artifact_path="")
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        # No 20260101-000002-bar.prd.md on disk

        # When brainstorm sync runs
        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        # Then entity is NOT archived (empty artifact_path guard)
        entity = db.get_entity("brainstorm:20260101-000002-bar")
        assert entity["status"] == "active"
        assert result["archived"] == 0

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
        assert "updated" in result


# ---------------------------------------------------------------------------
# Unified sync integration test (Task 4.3)
# ---------------------------------------------------------------------------


class TestUnifiedSync:
    """Integration test: sync_entity_statuses calls all 3 helpers."""

    def test_unified_sync_all_three_types(self, tmp_path):
        """All entity types synced in one call; return dict has all 6 keys."""
        db = make_db()

        # 1) Feature: seed as active, .meta.json says completed -> drift -> updated
        feature_folder = "042-test"
        db.register_entity(
            entity_type="feature", **identity_kwargs("feature", feature_folder),
            name=feature_folder, status="active", workspace_uuid=workspace_uuid_for(db, "test-project"),
        )
        write_meta_json(str(tmp_path / "features" / feature_folder), status="completed")

        # 2) Project: .meta.json present, no entity in DB -> skipped
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

        # All 6 keys must be present
        assert set(result.keys()) == {
            "updated", "skipped", "archived", "registered", "deleted", "warnings",
        }

        # Drifted feature should have been updated
        assert result["updated"] >= 1
        entity = db.get_entity(f"feature:{feature_folder}")
        assert entity["status"] == "completed"

        # Brainstorm should have been registered
        assert result["registered"] >= 1
        assert db.get_entity("brainstorm:20260101-000002-bar") is not None

        # A1: reconciliation deletes nothing, structurally.
        assert result["deleted"] == 0


# ---------------------------------------------------------------------------
# FR-10: conditional-kwarg pattern at 4 update_entity sites (no DeprecationWarning)
# ---------------------------------------------------------------------------


def _setup_site_47_meta_json_archive(db, ws_uuid, tmp_path):
    """Site 47: _sync_meta_json_entities archive branch (missing .meta.json file).

    Register a feature entity scoped to ws_uuid; create the feature folder
    but do NOT write .meta.json. sync_entity_statuses will hit the archive
    branch (line 47) and call db.update_entity(status="archived", ...).

    Returns a verification callable: (db, result) -> bool asserting the
    operation actually happened (proves the DeprecationWarning didn't
    short-circuit the write via the outer try/except).
    """
    folder = "042-archive-me"
    db.register_entity(
        entity_type="feature",
        **identity_kwargs("feature", folder),
        name=folder,
        status="active",
        workspace_uuid=ws_uuid,
    )
    # Folder exists, .meta.json missing → archive branch
    (tmp_path / "features" / folder).mkdir(parents=True)

    def verify(db, result):
        entity = db.get_entity(f"feature:{folder}")
        assert entity["is_archived"] == 1, (
            f"site 47 archive branch did not fire: entity status={entity['status']!r}, "
            f"result={result!r}"
        )

    return verify


def _setup_site_72_meta_json_status_change(db, ws_uuid, tmp_path):
    """Site 72: _sync_meta_json_entities status-change branch (.meta.json status differs from DB).

    Register a feature entity with status=active scoped to ws_uuid; write
    .meta.json with status=completed. sync_entity_statuses will hit the
    status-change branch (line 72) and call db.update_entity(status="completed", ...).
    """
    folder = "043-drift-me"
    db.register_entity(
        entity_type="feature",
        **identity_kwargs("feature", folder),
        name=folder,
        status="active",
        workspace_uuid=ws_uuid,
    )
    features_dir = tmp_path / "features" / folder
    write_meta_json(str(features_dir), status="completed")

    def verify(db, result):
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "completed", (
            f"site 72 status-change branch did not fire: entity status="
            f"{entity['status']!r}, result={result!r}"
        )

    return verify


def _setup_site_189_brainstorm_archive(db, ws_uuid, tmp_path):
    """Site 189: _sync_brainstorm_entities archive branch (missing .prd.md file).

    Register a brainstorm entity scoped to ws_uuid with an artifact_path
    pointing to a .prd.md that does not exist on disk. brainstorms/ dir
    exists but the file is missing — archive branch fires (line 189).
    """
    db.register_entity(
        entity_type="brainstorm",
        display_id="20260101-000001-archived-bs",
        name="20260101-000001-archived-bs",
        status="active",
        artifact_path="docs/brainstorms/archived-bs.prd.md",
        workspace_uuid=ws_uuid,
    )
    # brainstorms dir must exist for scan to proceed; .prd.md absent
    (tmp_path / "brainstorms").mkdir()

    def verify(db, result):
        entity = db.get_entity("brainstorm:20260101-000001-archived-bs")
        assert entity["is_archived"] == 1, (
            f"site 189 brainstorm archive did not fire: entity status="
            f"{entity['status']!r}, result={result!r}"
        )

    return verify


# Feature 111 / FR-CL.1b removed _setup_site_320_backlog_status_change
# (it drove a parser-derived status-change branch via a backlog.md
# marker). Release A then removed the backlog helper entirely — backlog is
# DB-only and backlog.md is a projection — so no backlog site remains. The
# 3 sites here (47, 72, 189) verify the FR-10 conditional-kwarg pattern
# across distinct update_entity call sites.


SITE_SETUPS = {
    "site_47_meta_json_archive": _setup_site_47_meta_json_archive,
    "site_72_meta_json_status_change": _setup_site_72_meta_json_status_change,
    "site_189_brainstorm_archive": _setup_site_189_brainstorm_archive,
}


class TestNoDeprecationWarningOnHappyPath:
    """FR-10: no DeprecationWarning fires when sync_entity_statuses is called
    with a real workspace_uuid at any of the 4 update_entity sites that
    previously passed both project_id and workspace_uuid unconditionally.

    Per design R6: warnings.catch_warnings() + simplefilter('error',
    DeprecationWarning) is scoped to the call body, NOT module-level, to
    prevent filter-bleed into sibling tests.

    Each sub-test also asserts the underlying write actually happened — the
    outer try/except Exception in sync_entity_statuses would otherwise
    swallow the DeprecationWarning-as-error and the test would pass
    vacuously. The site-specific entity-state assertion is the load-bearing
    behavioral pin.
    """

    @pytest.mark.parametrize("site_key", list(SITE_SETUPS.keys()))
    def test_sync_entity_statuses_no_deprecation_warning_on_happy_path(
        self, tmp_path, site_key
    ):
        # Bootstrap a real workspace_uuid (not __unknown__). We use a legacy
        # id (`ws-a-legacy`) so that the brainstorm/backlog helpers'
        # `list_entities(project_id=...)` calls resolve to the same
        # workspace_uuid we register the test entity under.
        legacy_id = "ws-a-legacy"
        db = EntityDatabase(":memory:")
        ws_a = bootstrap_test_workspace(db, legacy_id)

        # Trigger the site-specific state; receive a verify callable that
        # asserts the underlying write actually happened post-call.
        verify = SITE_SETUPS[site_key](db, ws_a, tmp_path)

        # Wrap the call in a scoped filter so any DeprecationWarning fires
        # as an exception. Scoped to this block per design R6.
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            result = sync_entity_statuses(
                db,
                str(tmp_path),
                project_id=legacy_id,
                workspace_uuid=ws_a,
            )

        # Behavioral assertion: the operation that should have happened did
        # happen. If the conditional-kwarg pattern is missing, the inner
        # update_entity raises DeprecationWarning-as-error and the outer
        # try/except in sync_entity_statuses swallows it into
        # result["warnings"], leaving the entity in its pre-call state.
        verify(db, result)

        # Pin: no entry in result["warnings"] should mention the
        # DeprecationWarning text (extra safety against silent swallow).
        deprecation_warnings = [
            w for w in result["warnings"]
            if "deprecated" in w.lower() or "workspace_uuid wins" in w
        ]
        assert deprecation_warnings == [], (
            f"Unexpected DeprecationWarning-derived entries in result['warnings']: "
            f"{deprecation_warnings}"
        )


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
        assert result["deleted"] == 0
        # Both id shapes survive: neither is "junk".
        assert db.get_entity("backlog:042-backlog") is not None
        assert db.get_entity("backlog:077-modern-slug") is not None

    def test_brainstorm_read_is_workspace_scoped(self, tmp_path):
        """Fixture 2 / A2: the same entity_id in two workspaces.

        Scope note: this asserts the READ, because that is the whole of
        A2's guarantee. ``update_entity`` re-resolves its target by
        (workspace_uuid, type_id), so an unscoped read cannot produce a
        cross-workspace WRITE — verified empirically: archiving a shared
        type_id scoped to A leaves B untouched, and a B-only type_id
        written via A raises ValueError (swallowed at entity_status.py's
        archival branch). The damage is wasted iteration over rows this
        invocation does not own, not corruption.
        """
        db = EntityDatabase(":memory:")
        ws_a = bootstrap_test_workspace(db, "ws-a-legacy")
        ws_b = bootstrap_test_workspace(db, "ws-b-legacy")

        own = {}
        for label, ws in (("a", ws_a), ("b", ws_b)):
            own[label] = db.register_entity(
                entity_type="brainstorm", display_id="001-shared",
                name="shared", status="active", workspace_uuid=ws,
                artifact_path="docs/brainstorms/001-shared.prd.md",
            )
        (tmp_path / "brainstorms").mkdir(parents=True)

        seen = []
        original = db.list_entities

        def spy_list(*a, **kw):
            rows = original(*a, **kw)
            if kw.get("entity_type") == "brainstorm":
                seen.append([r["uuid"] for r in rows])
            return rows

        # project_id=None is load-bearing: A2's defect is that an ABSENT
        # legacy filter makes the read unscoped. A resolvable project_id
        # would scope the old code by accident.
        with patch.object(db, "list_entities", side_effect=spy_list):
            sync_entity_statuses(
                db, str(tmp_path), project_id=None,
                project_root=str(tmp_path), workspace_uuid=ws_a,
            )

        assert seen, "brainstorm archival read never ran"
        for rows in seen:
            assert own["b"] not in rows, (
                "sync scoped to workspace A read workspace B's rows: "
                f"{rows}"
            )
            assert rows == [own["a"]], f"expected only workspace A's row, got {rows}"

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

    def test_one_failing_row_does_not_abort_the_remaining_helpers(self, tmp_path):
        """A3: per-helper continuation.

        The junk-cleanup path raised sqlite3.IntegrityError, which the inner
        handler (catching only ValueError) let escape and abort the whole
        backlog sync. Each helper must be isolated.
        """
        db = EntityDatabase(":memory:")
        ws = bootstrap_test_workspace(db, "ws-a-legacy")
        seed_feature_dir = tmp_path / "features" / "042-test"
        db.register_entity(entity_type="feature", seq=42, slug="test",
                           name="042-test", status="active", workspace_uuid=ws)
        write_meta_json(str(seed_feature_dir), status="completed")
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

        # The feature helper still completed despite the brainstorm failure.
        assert db.get_entity("feature:042-test")["status"] == "completed"
        assert any("brainstorm" in w for w in result["warnings"])
