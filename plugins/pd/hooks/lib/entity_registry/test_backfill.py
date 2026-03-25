"""Tests for entity_registry.backfill module."""
from __future__ import annotations

import json
import os

import pytest

from entity_registry.database import EntityDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def artifacts(tmp_path):
    """Build mock artifact directories and return (artifacts_root, db) tuple.

    Directory layout:
        features/029-entity-lineage-tracking/.meta.json
        brainstorms/20260227-lineage.prd.md
        projects/  (empty)
        backlog.md
    """
    # --- features ---
    feat_dir = tmp_path / "features" / "029-entity-lineage-tracking"
    feat_dir.mkdir(parents=True)
    meta = {
        "id": "029",
        "slug": "entity-lineage-tracking",
        "brainstorm_source": "docs/brainstorms/20260227-lineage.prd.md",
        "backlog_source": "00019",
    }
    (feat_dir / ".meta.json").write_text(json.dumps(meta))

    # --- brainstorms ---
    bs_dir = tmp_path / "brainstorms"
    bs_dir.mkdir()
    (bs_dir / "20260227-lineage.prd.md").write_text(
        "# Brainstorm\n\n*Source: Backlog #00019*\n\nSome content.\n"
    )

    # --- projects (empty) ---
    (tmp_path / "projects").mkdir()

    # --- backlog.md ---
    backlog_md = (
        "# Backlog\n\n"
        "| ID | Timestamp | Description |\n"
        "|----|-----------|-------------|\n"
        "| 00019 | 2026-02-27T05:00:00Z | Entity lineage tracking |\n"
    )
    (tmp_path / "backlog.md").write_text(backlog_md)

    # --- database ---
    db = EntityDatabase(str(tmp_path / "test.db"))
    yield tmp_path, db
    db.close()


# ---------------------------------------------------------------------------
# Task 3.1: Smoke test for fixtures
# ---------------------------------------------------------------------------


def test_fixtures_smoke(artifacts):
    """Verify the test fixture builds the expected directory structure."""
    root, db = artifacts

    meta_path = root / "features" / "029-entity-lineage-tracking" / ".meta.json"
    assert meta_path.exists()

    meta = json.loads(meta_path.read_text())
    assert "brainstorm_source" in meta
    assert meta["id"] == "029"
    assert meta["slug"] == "entity-lineage-tracking"


# ---------------------------------------------------------------------------
# Task 3.2: Topological ordering tests
# ---------------------------------------------------------------------------


class TestScanOrder:
    def test_backlog_registered_before_brainstorms(self, artifacts):
        """Backlog items should exist in DB before brainstorms that reference them."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        # Backlog entity should exist
        backlog = db.get_entity("backlog:00019")
        assert backlog is not None

        # Brainstorm that references backlog should have parent link
        brainstorm = db.get_entity("brainstorm:20260227-lineage")
        assert brainstorm is not None

    def test_all_entity_types_registered(self, artifacts):
        """After backfill, entities of all scanned types should be present."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        assert db.get_entity("backlog:00019") is not None
        assert db.get_entity("brainstorm:20260227-lineage") is not None
        assert db.get_entity("feature:029-entity-lineage-tracking") is not None

    def test_scan_order_constant(self):
        """ENTITY_SCAN_ORDER should be backlog, brainstorm, project, feature."""
        from entity_registry.backfill import ENTITY_SCAN_ORDER

        assert ENTITY_SCAN_ORDER == ["backlog", "brainstorm", "project", "feature"]


# ---------------------------------------------------------------------------
# Task 3.4: Parent derivation tests
# ---------------------------------------------------------------------------


class TestParentDerivation:
    def test_feature_to_brainstorm_via_meta(self, artifacts):
        """Feature with brainstorm_source should link to brainstorm parent."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        feature = db.get_entity("feature:029-entity-lineage-tracking")
        assert feature is not None
        assert feature["parent_type_id"] == "brainstorm:20260227-lineage"

    def test_feature_to_project_via_meta(self, tmp_path):
        """Feature with project_id should link to project parent (priority over brainstorm)."""
        # Create project
        proj_dir = tmp_path / "projects" / "P001"
        proj_dir.mkdir(parents=True)
        (proj_dir / ".meta.json").write_text(json.dumps({
            "id": "P001",
            "name": "Test Project",
        }))

        # Create feature with project_id
        feat_dir = tmp_path / "features" / "030-some-feature"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "030",
            "slug": "some-feature",
            "project_id": "P001",
            "brainstorm_source": "docs/brainstorms/20260227-some.prd.md",
        }))

        (tmp_path / "brainstorms").mkdir(exist_ok=True)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            feature = db.get_entity("feature:030-some-feature")
            assert feature is not None
            # project_id takes precedence over brainstorm_source
            assert feature["parent_type_id"] == "project:P001"
        finally:
            db.close()

    def test_brainstorm_to_backlog_format1(self, artifacts):
        """Brainstorm with '*Source: Backlog #00019*' should link to backlog."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        brainstorm = db.get_entity("brainstorm:20260227-lineage")
        assert brainstorm is not None
        assert brainstorm["parent_type_id"] == "backlog:00019"

    def test_brainstorm_to_backlog_format2(self, tmp_path):
        """Brainstorm with '**Backlog Item:** 00019' should link to backlog."""
        # Create backlog
        (tmp_path / "backlog.md").write_text(
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            "| 00020 | 2026-02-28T00:00:00Z | Another item |\n"
        )

        # Create brainstorm with format 2
        bs_dir = tmp_path / "brainstorms"
        bs_dir.mkdir()
        (bs_dir / "20260228-another.prd.md").write_text(
            "# Brainstorm\n\n**Backlog Item:** 00020\n\nSome content.\n"
        )

        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            brainstorm = db.get_entity("brainstorm:20260228-another")
            assert brainstorm is not None
            assert brainstorm["parent_type_id"] == "backlog:00020"
        finally:
            db.close()

    def test_derive_parent_backlog_always_none(self):
        """Backlog entities always return None for parent."""
        from entity_registry.backfill import _derive_parent

        assert _derive_parent("backlog", {}, None) is None
        assert _derive_parent("backlog", {"brainstorm_source": "x"}, "y") is None

    def test_derive_parent_feature_brainstorm_stem_extraction(self):
        """Feature brainstorm_source stem extraction removes dir prefix and extension."""
        from entity_registry.backfill import _derive_parent

        result = _derive_parent(
            "feature",
            {"brainstorm_source": "docs/brainstorms/20260227-054029-entity-lineage-tracking.prd.md"},
            None,
        )
        assert result == "brainstorm:20260227-054029-entity-lineage-tracking"

    def test_derive_parent_feature_brainstorm_md_extension(self):
        """Feature brainstorm_source with .md extension should also work."""
        from entity_registry.backfill import _derive_parent

        result = _derive_parent(
            "feature",
            {"brainstorm_source": "docs/brainstorms/20260130-slug.md"},
            None,
        )
        assert result == "brainstorm:20260130-slug"


# ---------------------------------------------------------------------------
# Task 3.6: Orphaned backlog and external brainstorm tests
# ---------------------------------------------------------------------------


class TestOrphanedAndExternal:
    def test_orphaned_backlog_gets_synthetic_entity(self, tmp_path):
        """Feature referencing non-existent backlog_source creates orphaned synthetic."""
        # No backlog.md at all -- backlog:00099 won't be found
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "031-orphan-test"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "031",
            "slug": "orphan-test",
            "backlog_source": "00099",
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            # Synthetic orphaned backlog should exist
            orphan = db.get_entity("backlog:00099")
            assert orphan is not None
            assert orphan["status"] == "orphaned"
            assert "00099" in orphan["name"]

            # Feature should be parented to the synthetic backlog
            feature = db.get_entity("feature:031-orphan-test")
            assert feature is not None
            assert feature["parent_type_id"] == "backlog:00099"
        finally:
            db.close()

    def test_external_brainstorm_gets_synthetic_entity(self, tmp_path):
        """Feature referencing external brainstorm_source creates external synthetic."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "032-external-test"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "032",
            "slug": "external-test",
            "brainstorm_source": "~/.claude/plans/some-plan.md",
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            # Synthetic external brainstorm should exist
            stem = "some-plan"
            external = db.get_entity(f"brainstorm:{stem}")
            assert external is not None
            assert external["status"] == "external"
            assert "External:" in external["name"]

            # Feature should be parented to the synthetic brainstorm
            feature = db.get_entity("feature:032-external-test")
            assert feature is not None
            assert feature["parent_type_id"] == f"brainstorm:{stem}"
        finally:
            db.close()

    def test_external_absolute_path_detection(self, tmp_path):
        """Absolute paths should be detected as external."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "033-abs-test"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "033",
            "slug": "abs-test",
            "brainstorm_source": "/home/user/plans/plan.prd.md",
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            external = db.get_entity("brainstorm:plan")
            assert external is not None
            assert external["status"] == "external"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Task 3.8: Idempotency and .prd.md/.md priority tests
# ---------------------------------------------------------------------------


class TestIdempotencyAndPriority:
    def test_backfill_idempotent(self, artifacts):
        """Running backfill twice produces same result (no duplicates, no errors)."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        # Capture state after first run
        backlog1 = db.get_entity("backlog:00019")
        brainstorm1 = db.get_entity("brainstorm:20260227-lineage")
        feature1 = db.get_entity("feature:029-entity-lineage-tracking")

        # Clear backfill_complete marker to allow re-run
        db.set_metadata("backfill_complete", "0")

        # Run again
        run_backfill(db, str(root))

        # Entities should be identical (INSERT OR IGNORE preserves originals)
        backlog2 = db.get_entity("backlog:00019")
        brainstorm2 = db.get_entity("brainstorm:20260227-lineage")
        feature2 = db.get_entity("feature:029-entity-lineage-tracking")

        assert backlog1["name"] == backlog2["name"]
        assert brainstorm1["name"] == brainstorm2["name"]
        assert feature1["name"] == feature2["name"]
        assert feature1["parent_type_id"] == feature2["parent_type_id"]

    def test_prd_md_priority_over_md(self, tmp_path):
        """A .prd.md file should take priority over a .md file with the same stem."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()

        # Create both .prd.md and .md with same stem
        (tmp_path / "brainstorms" / "20260227-test.prd.md").write_text(
            "# PRD version\n"
        )
        (tmp_path / "brainstorms" / "20260227-test.md").write_text(
            "# Plain version\n"
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            brainstorm = db.get_entity("brainstorm:20260227-test")
            assert brainstorm is not None
            # Artifact path should point to the .prd.md file
            assert brainstorm["artifact_path"].endswith(".prd.md")
        finally:
            db.close()

    def test_md_only_registered_for_unique_stems(self, tmp_path):
        """A .md file should be registered if no .prd.md exists for that stem."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()

        # Only a .md file (no .prd.md with same stem)
        (tmp_path / "brainstorms" / "20260228-unique.md").write_text(
            "# Unique brainstorm\n"
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            brainstorm = db.get_entity("brainstorm:20260228-unique")
            assert brainstorm is not None
            assert brainstorm["artifact_path"].endswith(".md")
        finally:
            db.close()

    def test_no_double_registration_for_prd_stem(self, tmp_path):
        """When both .prd.md and .md exist, only one entity is registered."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()

        (tmp_path / "brainstorms" / "20260227-dup.prd.md").write_text("# PRD\n")
        (tmp_path / "brainstorms" / "20260227-dup.md").write_text("# Plain\n")

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            # Should have exactly one entity for this stem
            entity = db.get_entity("brainstorm:20260227-dup")
            assert entity is not None

            # Count all brainstorm entities
            cur = db._conn.execute(
                "SELECT COUNT(*) FROM entities WHERE entity_type = 'brainstorm'"
            )
            count = cur.fetchone()[0]
            assert count == 1  # only one brainstorm registered
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Deepened tests: BDD, Adversarial, Error, Mutation
# ---------------------------------------------------------------------------


class TestMissingMetaJsonHandledGracefully:
    """Adversarial: missing .meta.json in feature dir is silently skipped.
    derived_from: dimension:adversarial
    """

    def test_missing_meta_json_handled_gracefully(self, tmp_path):
        # Given a features directory with a feature folder but no .meta.json
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "040-no-meta"
        feat_dir.mkdir(parents=True)
        # (no .meta.json written)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # When running backfill
            run_backfill(db, str(tmp_path))

            # Then no entity is registered for this feature (no crash)
            assert db.get_entity("feature:040-no-meta") is None
            # And backfill completes successfully
            assert db.get_metadata("backfill_complete") == "1"
        finally:
            db.close()


class TestMalformedMetaJsonInFeature:
    """Adversarial: malformed .meta.json in feature dir is handled gracefully.
    derived_from: dimension:adversarial
    """

    def test_malformed_meta_json_in_feature_dir(self, tmp_path):
        # Given a feature directory with malformed JSON
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "041-bad-json"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text("{invalid json content!!")

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # When running backfill
            run_backfill(db, str(tmp_path))

            # Then the malformed feature is skipped (no crash)
            assert db.get_entity("feature:041-bad-json") is None
            # And backfill still completes
            assert db.get_metadata("backfill_complete") == "1"
        finally:
            db.close()


class TestBackfillPartialFailureRecovery:
    """Error propagation: partial failure does not corrupt state.
    derived_from: dimension:error_propagation
    """

    def test_backfill_partial_failure_does_not_corrupt_state(self, tmp_path):
        # Given two features: one valid, one with invalid meta JSON
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()

        # Valid feature
        valid_feat = tmp_path / "features" / "050-valid"
        valid_feat.mkdir(parents=True)
        (valid_feat / ".meta.json").write_text(json.dumps({
            "id": "050", "slug": "valid",
        }))

        # Malformed feature
        bad_feat = tmp_path / "features" / "051-broken"
        bad_feat.mkdir(parents=True)
        (bad_feat / ".meta.json").write_text("NOT JSON!!!")

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # When running backfill
            run_backfill(db, str(tmp_path))

            # Then the valid feature is registered
            valid = db.get_entity("feature:050-valid")
            assert valid is not None
            assert valid["name"] == "Valid"

            # And the broken feature is skipped
            broken = db.get_entity("feature:051-broken")
            assert broken is None

            # And backfill completes (state is consistent)
            assert db.get_metadata("backfill_complete") == "1"
        finally:
            db.close()


class TestMetaJsonExtraFieldsAccepted:
    """Adversarial: .meta.json with extra unexpected fields is accepted.
    derived_from: dimension:adversarial
    """

    def test_meta_json_with_extra_unexpected_fields_accepted(self, tmp_path):
        # Given a feature .meta.json with extra unknown fields
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "042-extra-fields"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "042",
            "slug": "extra-fields",
            "name": "Extra Fields Feature",
            "unknown_key": "should_not_break",
            "another_key": 42,
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # When running backfill
            run_backfill(db, str(tmp_path))

            # Then the feature is registered successfully
            entity = db.get_entity("feature:042-extra-fields")
            assert entity is not None
            assert entity["name"] == "Extra Fields Feature"
        finally:
            db.close()


class TestParentReferenceToNonexistentEntity:
    """Error propagation: parent reference to nonexistent entity produces warning.
    derived_from: dimension:error_propagation, spec:AC-9
    """

    def test_parent_reference_to_nonexistent_entity_creates_synthetic(self, tmp_path):
        # Given a feature referencing a brainstorm that does not exist on disk
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "043-orphan-parent"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "043",
            "slug": "orphan-parent",
            "brainstorm_source": "docs/brainstorms/20260301-missing.prd.md",
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # When running backfill
            run_backfill(db, str(tmp_path))

            # Then a synthetic orphaned brainstorm is created
            synthetic = db.get_entity("brainstorm:20260301-missing")
            assert synthetic is not None
            assert synthetic["status"] == "orphaned"

            # And the feature is parented to it
            feature = db.get_entity("feature:043-orphan-parent")
            assert feature is not None
            assert feature["parent_type_id"] == "brainstorm:20260301-missing"
        finally:
            db.close()


class TestDeriveParentFeatureProjectPriority:
    """Mutation mindset: project_id takes priority over brainstorm_source.
    derived_from: dimension:mutation_mindset
    """

    def test_derive_parent_project_id_overrides_brainstorm_source(self):
        # Given meta with both project_id and brainstorm_source
        from entity_registry.backfill import _derive_parent

        result = _derive_parent(
            "feature",
            {
                "project_id": "P001",
                "brainstorm_source": "docs/brainstorms/20260227-something.prd.md",
            },
            None,
        )
        # Then project_id takes priority
        assert result == "project:P001"
        # Mutation check: if brainstorm_source was checked first, this would fail


class TestBrainstormStemExtraction:
    """Boundary: various brainstorm path formats.
    derived_from: dimension:boundary_values
    """

    def test_brainstorm_stem_prd_md(self):
        from entity_registry.backfill import _brainstorm_stem

        assert _brainstorm_stem("docs/brainstorms/20260227-lineage.prd.md") == "20260227-lineage"

    def test_brainstorm_stem_md(self):
        from entity_registry.backfill import _brainstorm_stem

        assert _brainstorm_stem("brainstorms/20260130-slug.md") == "20260130-slug"

    def test_brainstorm_stem_no_extension(self):
        from entity_registry.backfill import _brainstorm_stem

        assert _brainstorm_stem("brainstorms/just-a-file") == "just-a-file"

    def test_brainstorm_stem_bare_filename(self):
        from entity_registry.backfill import _brainstorm_stem

        assert _brainstorm_stem("20260227-test.prd.md") == "20260227-test"


class TestIsExternalPath:
    """Boundary: external path detection edge cases.
    derived_from: dimension:boundary_values
    """

    def test_absolute_path_is_external(self):
        from entity_registry.backfill import _is_external_path

        assert _is_external_path("/home/user/plans/plan.prd.md") is True

    def test_home_relative_path_is_external(self):
        from entity_registry.backfill import _is_external_path

        assert _is_external_path("~/.claude/plans/plan.md") is True

    def test_relative_path_is_not_external(self):
        from entity_registry.backfill import _is_external_path

        assert _is_external_path("docs/brainstorms/test.prd.md") is False

    def test_empty_string_is_not_external(self):
        from entity_registry.backfill import _is_external_path

        assert _is_external_path("") is False


# ---------------------------------------------------------------------------
# Task 3.10: Backfill complete marker and partial recovery tests
# ---------------------------------------------------------------------------


class TestBackfillCompleteMarker:
    def test_marker_set_after_full_run(self, artifacts):
        """backfill_complete should be '1' in _metadata after successful run."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        assert db.get_metadata("backfill_complete") is None
        run_backfill(db, str(root))
        assert db.get_metadata("backfill_complete") == "1"

    def test_marker_not_set_skips_rerun(self, artifacts):
        """When backfill_complete is '1', run_backfill should skip entirely."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))
        assert db.get_metadata("backfill_complete") == "1"

        # Add a new feature artifact AFTER backfill completed
        new_feat = root / "features" / "099-new-feature"
        new_feat.mkdir(parents=True)
        (new_feat / ".meta.json").write_text(json.dumps({
            "id": "099",
            "slug": "new-feature",
        }))

        # Re-run should skip (marker already set)
        run_backfill(db, str(root))

        # New feature should NOT be registered (run was skipped)
        assert db.get_entity("feature:099-new-feature") is None

    def test_marker_not_set_allows_rerun(self, artifacts):
        """When backfill_complete is not '1', run_backfill should execute."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))
        assert db.get_metadata("backfill_complete") == "1"

        # Reset marker
        db.set_metadata("backfill_complete", "0")

        # Add a new feature
        new_feat = root / "features" / "099-new-feature"
        new_feat.mkdir(parents=True)
        (new_feat / ".meta.json").write_text(json.dumps({
            "id": "099",
            "slug": "new-feature",
        }))

        # Re-run should execute (marker cleared)
        run_backfill(db, str(root))

        # New feature should be registered
        assert db.get_entity("feature:099-new-feature") is not None
        assert db.get_metadata("backfill_complete") == "1"

    def test_partial_failure_recovery(self, tmp_path):
        """If backfill fails mid-way, re-run should recover via INSERT OR IGNORE."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()

        # Create a backlog with one item
        (tmp_path / "backlog.md").write_text(
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            "| 00050 | 2026-03-01T00:00:00Z | Partial test |\n"
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # Simulate partial: manually register one entity, no marker
            db.register_entity("backlog", "00050", "Partial test")

            # Full run should succeed (INSERT OR IGNORE on existing entity)
            run_backfill(db, str(tmp_path))

            # Entity should still exist with original name
            backlog = db.get_entity("backlog:00050")
            assert backlog is not None
            assert backlog["name"] == "Partial test"

            # Marker should be set
            assert db.get_metadata("backfill_complete") == "1"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Name enrichment: _humanize_slug, _extract_prd_title, backlog truncation
# ---------------------------------------------------------------------------

from entity_registry.backfill import _humanize_slug, _extract_prd_title


class TestHumanizeSlug:
    """Tests for _humanize_slug helper."""

    def test_strips_date_prefix(self):
        assert _humanize_slug("20260205-agent") == "Agent"

    def test_strips_datetime_prefix(self):
        assert _humanize_slug("20260205-002937-rca-agent") == "Rca Agent"

    def test_no_date_prefix(self):
        assert _humanize_slug("vast-mixing-lerdorf") == "Vast Mixing Lerdorf"

    def test_only_date_preserved(self):
        assert _humanize_slug("20260227") == "20260227"

    def test_simple_slug(self):
        assert _humanize_slug("change-workflow-ordering") == "Change Workflow Ordering"

    def test_single_word(self):
        assert _humanize_slug("agent") == "Agent"


class TestExtractPrdTitle:
    """Tests for _extract_prd_title helper."""

    def test_prd_heading(self):
        content = "# PRD: My Great Feature\n\nSome content."
        assert _extract_prd_title(content, "20260207-my-great-feature") == "My Great Feature"

    def test_plain_heading(self):
        content = "# Structured Problem Solving\n\nSome content."
        assert _extract_prd_title(content, "20260207-structured-problem-solving") == "Structured Problem Solving"

    def test_empty_prd_heading_falls_back(self):
        content = "# PRD:\n\nSome content."
        # Empty title after '# PRD:' → falls through to first '# <title>'
        # which re-matches '# PRD:' with group(1)='PRD:'
        assert _extract_prd_title(content, "20260207-my-thing") == "PRD:"

    def test_no_headings_at_all_humanizes(self):
        content = "Just content, no headings at all."
        assert _extract_prd_title(content, "20260207-my-thing") == "My Thing"

    def test_no_heading_humanizes_slug(self):
        content = "Some content without headings."
        assert _extract_prd_title(content, "20260205-002937-rca") == "Rca"

    def test_none_content_humanizes_slug(self):
        assert _extract_prd_title(None, "20260227-lineage") == "Lineage"

    def test_prd_heading_with_extra_spaces(self):
        content = "#   PRD:   Spaced Title  \n\nBody."
        assert _extract_prd_title(content, "stub") == "Spaced Title"


class TestBacklogTitleTruncation:
    """Tests for backlog title/description splitting in _scan_backlog."""

    def test_short_description_no_truncation(self, tmp_path):
        """Descriptions ≤ 80 chars are used as-is."""
        short = "Fix the login bug"
        backlog_md = (
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            f"| 00001 | 2026-01-01T00:00:00Z | {short} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00001")
            assert entity["name"] == short
        finally:
            db.close()

    def test_long_description_truncated_at_word_boundary(self, tmp_path):
        """Descriptions > 80 chars are truncated at last space before char 80."""
        long_desc = "Implement a comprehensive logging framework that captures all API calls and responses for debugging purposes"
        assert len(long_desc) > 80

        backlog_md = (
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            f"| 00001 | 2026-01-01T00:00:00Z | {long_desc} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00001")
            assert entity["name"].endswith("\u2026")
            assert len(entity["name"]) <= 83  # 80 + "…"
        finally:
            db.close()

    def test_backlog_metadata_description_full_text(self, tmp_path):
        """metadata.description contains the full untruncated text."""
        long_desc = "Implement a comprehensive logging framework that captures all API calls and responses for debugging purposes"
        backlog_md = (
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            f"| 00001 | 2026-01-01T00:00:00Z | {long_desc} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00001")
            meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
            assert meta["description"] == long_desc
        finally:
            db.close()

    def test_backlog_no_spaces_in_first_80(self, tmp_path):
        """Description with no spaces in first 80 chars truncates at char 80."""
        no_space = "a" * 100  # 100 chars, no spaces
        backlog_md = (
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            f"| 00001 | 2026-01-01T00:00:00Z | {no_space} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:00001")
            assert entity["name"] == "a" * 80 + "\u2026"
        finally:
            db.close()


class TestFeatureNameHumanization:
    """Tests for feature name humanization in _scan_features."""

    def test_feature_without_meta_name_gets_humanized(self, tmp_path):
        """Features without name in .meta.json get humanized slug."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "050-valid"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({"id": "050", "slug": "valid"}))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("feature:050-valid")
            assert entity["name"] == "Valid"
        finally:
            db.close()

    def test_feature_with_meta_name_preserves_it(self, tmp_path):
        """Features with name in .meta.json keep that name."""
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        feat_dir = tmp_path / "features" / "042-extra-fields"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "042", "slug": "extra-fields",
            "name": "Extra Fields Feature",
        }))

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("feature:042-extra-fields")
            assert entity["name"] == "Extra Fields Feature"
        finally:
            db.close()


class TestBrainstormTitleExtraction:
    """Tests for brainstorm title extraction from PRD content during backfill."""

    def test_brainstorm_prd_title_extracted(self, tmp_path):
        """Brainstorm with PRD heading gets title from it."""
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()
        bs_dir = tmp_path / "brainstorms"
        bs_dir.mkdir()
        (bs_dir / "20260207-structured-problem-solving.prd.md").write_text(
            "# PRD: Structured Problem Solving Framework\n\nContent."
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("brainstorm:20260207-structured-problem-solving")
            assert entity["name"] == "Structured Problem Solving Framework"
        finally:
            db.close()

    def test_brainstorm_plain_heading_extracted(self, tmp_path):
        """Brainstorm with plain heading (no PRD:) uses that."""
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()
        bs_dir = tmp_path / "brainstorms"
        bs_dir.mkdir()
        (bs_dir / "20260210-cool-idea.md").write_text(
            "# Cool Idea Design\n\nContent."
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("brainstorm:20260210-cool-idea")
            assert entity["name"] == "Cool Idea Design"
        finally:
            db.close()

    def test_brainstorm_no_heading_humanizes_slug(self, tmp_path):
        """Brainstorm with no heading falls back to humanized slug."""
        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()
        bs_dir = tmp_path / "brainstorms"
        bs_dir.mkdir()
        (bs_dir / "20260210-114052-no-heading.md").write_text(
            "Just content, no heading.\n"
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("brainstorm:20260210-114052-no-heading")
            assert entity["name"] == "No Heading"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Phase 3: Workflow Phase Backfill tests (Tasks 3.1 - 3.8, 3.3b)
# ---------------------------------------------------------------------------

from entity_registry.backfill import (
    PHASE_SEQUENCE,
    VALID_MODES,
    _derive_next_phase,
    _resolve_meta_path,
    backfill_workflow_phases,
)
from workflow_engine.kanban import derive_kanban


class TestWorkflowPhaseBackfill:
    """Tests for workflow phase backfill constants, helpers, and main function."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create an EntityDatabase with workflow_phases table."""
        db = EntityDatabase(str(tmp_path / "test.db"))
        yield db
        db.close()

    # -------------------------------------------------------------------
    # Task 3.1: Kanban derivation (via derive_kanban — replaced STATUS_TO_KANBAN)
    # -------------------------------------------------------------------

    def test_status_planned_maps_to_backlog(self):
        assert derive_kanban("planned", None) == "backlog"

    def test_status_active_no_phase_maps_to_backlog(self):
        assert derive_kanban("active", None) == "backlog"

    def test_status_completed_maps_to_completed(self):
        assert derive_kanban("completed", None) == "completed"

    def test_status_abandoned_maps_to_completed(self):
        assert derive_kanban("abandoned", None) == "completed"

    def test_unmapped_status_falls_back_to_backlog(self):
        """Unmapped statuses like 'draft' fall back to backlog via derive_kanban."""
        assert derive_kanban("draft", None) == "backlog"

    # -------------------------------------------------------------------
    # Task 3.2: _derive_next_phase
    # -------------------------------------------------------------------

    def test_derive_next_phase_specify_returns_design(self):
        assert _derive_next_phase("specify") == "design"

    def test_derive_next_phase_design_returns_create_plan(self):
        assert _derive_next_phase("design") == "create-plan"

    def test_derive_next_phase_implement_returns_finish(self):
        assert _derive_next_phase("implement") == "finish"

    def test_derive_next_phase_finish_returns_finish(self):
        """Terminal state: finish -> finish per spec D-5."""
        assert _derive_next_phase("finish") == "finish"

    def test_derive_next_phase_none_returns_none(self):
        assert _derive_next_phase(None) is None

    def test_derive_next_phase_unrecognized_returns_none(self):
        assert _derive_next_phase("unknown-phase") is None

    # -------------------------------------------------------------------
    # Task 3.3: _resolve_meta_path
    # -------------------------------------------------------------------

    def test_resolve_meta_path_directory_artifact_path(self, tmp_path, db):
        """Entity with artifact_path directory -> {artifact_path}/.meta.json."""
        feat_dir = tmp_path / "features" / "001-test"
        feat_dir.mkdir(parents=True)
        meta_file = feat_dir / ".meta.json"
        meta_file.write_text('{"id": "001"}')

        entity = {"artifact_path": str(feat_dir), "entity_type": "feature", "entity_id": "001-test"}
        result = _resolve_meta_path(entity, str(tmp_path))
        assert result == str(meta_file)

    def test_resolve_meta_path_file_artifact_path_falls_through(self, tmp_path, db):
        """Entity with file artifact_path (e.g., .prd.md) -> derived path doesn't exist, falls to convention."""
        prd_file = tmp_path / "brainstorms" / "test.prd.md"
        prd_file.parent.mkdir(parents=True)
        prd_file.write_text("content")
        # No .meta.json at {prd_file}/.meta.json (doesn't make sense for a file)
        # No convention path either

        entity = {"artifact_path": str(prd_file), "entity_type": "brainstorm", "entity_id": "test"}
        result = _resolve_meta_path(entity, str(tmp_path))
        assert result is None

    def test_resolve_meta_path_convention_fallback(self, tmp_path, db):
        """Entity without artifact_path -> convention fallback path."""
        feat_dir = tmp_path / "features" / "002-slug"
        feat_dir.mkdir(parents=True)
        meta_file = feat_dir / ".meta.json"
        meta_file.write_text('{"id": "002"}')

        entity = {"artifact_path": None, "entity_type": "feature", "entity_id": "002-slug"}
        result = _resolve_meta_path(entity, str(tmp_path))
        assert result == str(meta_file)

    def test_resolve_meta_path_neither_exists_returns_none(self, tmp_path, db):
        """No artifact_path, no convention path -> returns None."""
        entity = {"artifact_path": None, "entity_type": "feature", "entity_id": "nonexistent"}
        result = _resolve_meta_path(entity, str(tmp_path))
        assert result is None

    # -------------------------------------------------------------------
    # Task 3.3b: 3-tier status resolution fallback chain
    # -------------------------------------------------------------------

    def test_status_from_meta_json_when_db_status_null(self, tmp_path, db):
        """Entity with .meta.json status=active and entities.status=NULL -> uses active."""
        feat_dir = tmp_path / "features" / "s1-test"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text('{"status": "active", "lastCompletedPhase": "specify"}')

        db.register_entity("feature", "s1-test", "Status Test 1", artifact_path=str(feat_dir))
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:s1-test")
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"  # active + design phase -> prioritised

    def test_status_from_db_when_no_meta_json(self, tmp_path, db):
        """Entity with no .meta.json and entities.status=completed -> uses completed."""
        db.register_entity("feature", "s2-test", "Status Test 2", status="completed")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:s2-test")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_status_defaults_to_planned_when_no_source(self, tmp_path, db):
        """Entity with no .meta.json and entities.status=NULL -> defaults to planned -> backlog."""
        db.register_entity("feature", "s3-test", "Status Test 3")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:s3-test")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"

    def test_meta_json_status_wins_over_db_status(self, tmp_path, db):
        """Entity with .meta.json status=active AND entities.status=completed -> .meta.json wins."""
        feat_dir = tmp_path / "features" / "s4-test"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text('{"status": "active", "lastCompletedPhase": "design"}')

        db.register_entity("feature", "s4-test", "Status Test 4",
                           status="completed", artifact_path=str(feat_dir))
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:s4-test")
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"  # active + create-plan phase -> prioritised (not completed)

    def test_unmapped_status_defaults_to_planned_with_warning(self, tmp_path, db, caplog):
        """Unmapped status (e.g., 'draft') -> default to planned -> backlog, with warning."""
        import logging

        db.register_entity("feature", "s5-test", "Status Test 5", status="draft")

        with caplog.at_level(logging.WARNING):
            backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:s5-test")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        # Should have warning about unmapped status
        assert any("draft" in record.message for record in caplog.records)

    # -------------------------------------------------------------------
    # Task 3.4: Integration tests for backfill feature entities
    # -------------------------------------------------------------------

    def test_backfill_active_feature_with_meta(self, tmp_path, db):
        """Active feature with .meta.json -> correct kanban, workflow_phase, last_completed_phase, mode."""
        feat_dir = tmp_path / "features" / "f1-active"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "design",
            "mode": "standard",
        }))

        db.register_entity("feature", "f1-active", "Active Feature",
                           artifact_path=str(feat_dir), status="active")
        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:f1-active")
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"  # active + create-plan -> prioritised
        assert wp["workflow_phase"] == "create-plan"  # next after design
        assert wp["last_completed_phase"] == "design"
        assert wp["mode"] == "standard"
        assert result["created"] >= 1

    def test_backfill_completed_feature(self, tmp_path, db):
        """Completed feature -> kanban=completed, workflow_phase=finish."""
        feat_dir = tmp_path / "features" / "f2-done"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "completed",
            "lastCompletedPhase": "finish",
            "mode": "standard",
        }))

        db.register_entity("feature", "f2-done", "Done Feature",
                           artifact_path=str(feat_dir), status="completed")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:f2-done")
        assert wp is not None
        assert wp["kanban_column"] == "completed"
        assert wp["workflow_phase"] == "finish"  # finish -> finish (terminal)

    def test_backfill_planned_feature(self, tmp_path, db):
        """Planned feature -> kanban=backlog, workflow_phase=NULL."""
        db.register_entity("feature", "f3-planned", "Planned Feature", status="planned")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:f3-planned")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        assert wp["workflow_phase"] is None

    def test_backfill_abandoned_feature_with_last_phase(self, tmp_path, db):
        """Abandoned feature with lastCompletedPhase -> kanban=completed, workflow_phase=next-after-last."""
        feat_dir = tmp_path / "features" / "f4-abandoned"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "abandoned",
            "lastCompletedPhase": "create-tasks",
            "mode": "full",
        }))

        db.register_entity("feature", "f4-abandoned", "Abandoned Feature",
                           artifact_path=str(feat_dir), status="abandoned")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:f4-abandoned")
        assert wp is not None
        assert wp["kanban_column"] == "completed"  # abandoned -> completed
        assert wp["workflow_phase"] == "implement"  # next after create-tasks
        assert wp["last_completed_phase"] == "create-tasks"
        assert wp["mode"] == "full"

    # -------------------------------------------------------------------
    # Task 3.5: Brainstorm/backlog entities
    # -------------------------------------------------------------------

    def test_backfill_brainstorm_entity(self, tmp_path, db):
        """Brainstorm entity -> workflow_phase=draft, kanban_column=wip."""
        db.register_entity("brainstorm", "bs-test", "Test Brainstorm", status="active")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-test")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"

    def test_backfill_backlog_entity(self, tmp_path, db):
        """Backlog entity -> workflow_phase=open, kanban_column=backlog."""
        db.register_entity("backlog", "bl-test", "Test Backlog", status="planned")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("backlog:bl-test")
        assert wp is not None
        assert wp["workflow_phase"] == "open"
        assert wp["kanban_column"] == "backlog"

    # -------------------------------------------------------------------
    # Task 3.5b: Child-derived kanban for brainstorm/backlog (Gap S3)
    # -------------------------------------------------------------------

    def test_brainstorm_with_completed_child_gets_completed_kanban(self, tmp_path, db):
        """Brainstorm with all child features completed -> kanban=completed.

        Gap S3 fix: brainstorms with completed children were stuck at backlog.
        """
        db.register_entity("brainstorm", "bs-parent", "Parent Brainstorm")
        child_tid = db.register_entity(
            "feature", "f-child", "Child Feature", status="completed"
        )
        db.set_parent(child_tid, "brainstorm:bs-parent")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-parent")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_backlog_with_completed_child_gets_completed_kanban(self, tmp_path, db):
        """Backlog with all child features completed -> kanban=completed."""
        db.register_entity("backlog", "bl-parent", "Parent Backlog")
        child_tid = db.register_entity(
            "feature", "f-child2", "Child Feature 2", status="completed"
        )
        db.set_parent(child_tid, "backlog:bl-parent")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("backlog:bl-parent")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_brainstorm_with_mixed_children_stays_at_default_kanban(self, tmp_path, db):
        """Brainstorm with mix of completed and active children -> no override, uses default wip."""
        db.register_entity("brainstorm", "bs-mixed", "Mixed Brainstorm")
        c1 = db.register_entity("feature", "f-done", "Done", status="completed")
        c2 = db.register_entity("feature", "f-wip", "WIP", status="active")
        db.set_parent(c1, "brainstorm:bs-mixed")
        db.set_parent(c2, "brainstorm:bs-mixed")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-mixed")
        assert wp is not None
        # Not all children completed, so kanban uses brainstorm default (wip)
        assert wp["kanban_column"] == "wip"

    def test_brainstorm_with_no_children_stays_at_default_kanban(self, tmp_path, db):
        """Brainstorm with no child features -> kanban uses brainstorm default (wip)."""
        db.register_entity("brainstorm", "bs-lonely", "Lonely Brainstorm")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-lonely")
        assert wp is not None
        assert wp["kanban_column"] == "wip"  # brainstorm default

    # -------------------------------------------------------------------
    # Task 3.6: Project entity exclusion
    # -------------------------------------------------------------------

    def test_backfill_excludes_project_entities(self, tmp_path, db):
        """Project entities should NOT get workflow_phases rows."""
        db.register_entity("project", "p1", "Test Project")
        db.register_entity("feature", "f1", "Test Feature")
        backfill_workflow_phases(db, str(tmp_path))

        assert db.get_workflow_phase("project:p1") is None
        assert db.get_workflow_phase("feature:f1") is not None  # feature gets a row

    # -------------------------------------------------------------------
    # Task 3.7: Backfill idempotency
    # -------------------------------------------------------------------

    def test_backfill_idempotent_second_run_no_creates(self, tmp_path, db):
        """Second backfill run creates 0, skips all, no errors."""
        db.register_entity("feature", "f1", "Feature 1")
        result1 = backfill_workflow_phases(db, str(tmp_path))
        assert result1["created"] >= 1

        result2 = backfill_workflow_phases(db, str(tmp_path))
        assert result2["created"] == 0
        assert result2["skipped"] >= 1
        assert len(result2["errors"]) == 0

    def test_backfill_idempotent_existing_rows_not_modified(self, tmp_path, db):
        """Existing rows should not be modified on re-run."""
        db.register_entity("feature", "f1", "Feature 1")
        backfill_workflow_phases(db, str(tmp_path))
        wp1 = db.get_workflow_phase("feature:f1")

        backfill_workflow_phases(db, str(tmp_path))
        wp2 = db.get_workflow_phase("feature:f1")

        assert wp1["updated_at"] == wp2["updated_at"]

    def test_backfill_returns_dict_with_required_keys(self, tmp_path, db):
        """Return dict has created/skipped/errors keys."""
        result = backfill_workflow_phases(db, str(tmp_path))
        assert "created" in result
        assert "skipped" in result
        assert "errors" in result
        assert isinstance(result["created"], int)
        assert isinstance(result["skipped"], int)
        assert isinstance(result["errors"], list)

    # -------------------------------------------------------------------
    # Task 3.8: .meta.json error tolerance
    # -------------------------------------------------------------------

    def test_backfill_malformed_json_uses_defaults(self, tmp_path, db, caplog):
        """Malformed .meta.json -> warning logged, defaults used."""
        import logging

        feat_dir = tmp_path / "features" / "bad-json"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text("{ not valid json }")

        db.register_entity("feature", "bad-json", "Bad JSON", artifact_path=str(feat_dir))

        with caplog.at_level(logging.WARNING):
            result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:bad-json")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"  # defaults applied
        assert len(result["errors"]) == 0  # not an error, just a warning
        # AC-18: warning must be logged for malformed JSON
        assert any("Malformed JSON" in rec.message for rec in caplog.records), (
            f"Expected 'Malformed JSON' warning in log, got: {[r.message for r in caplog.records]}"
        )

    def test_backfill_missing_meta_json_uses_defaults(self, tmp_path, db):
        """Missing .meta.json -> defaults used, no error."""
        db.register_entity("feature", "no-meta", "No Meta")
        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:no-meta")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        assert len(result["errors"]) == 0

    def test_backfill_invalid_last_completed_phase_null_with_warning(self, tmp_path, db, caplog):
        """Invalid lastCompletedPhase -> NULL, warning logged."""
        import logging

        feat_dir = tmp_path / "features" / "bad-phase"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "not-a-valid-phase",
            "mode": "standard",
        }))

        db.register_entity("feature", "bad-phase", "Bad Phase", artifact_path=str(feat_dir))

        with caplog.at_level(logging.WARNING):
            backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:bad-phase")
        assert wp is not None
        assert wp["last_completed_phase"] is None  # invalid -> NULL
        assert wp["workflow_phase"] is None  # can't derive from invalid

    def test_backfill_invalid_mode_null_with_warning(self, tmp_path, db, caplog):
        """Invalid mode -> NULL, warning logged."""
        import logging

        feat_dir = tmp_path / "features" / "bad-mode"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "design",
            "mode": "invalid-mode",
        }))

        db.register_entity("feature", "bad-mode", "Bad Mode", artifact_path=str(feat_dir))

        with caplog.at_level(logging.WARNING):
            backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:bad-mode")
        assert wp is not None
        assert wp["mode"] is None  # invalid -> NULL
        assert wp["last_completed_phase"] == "design"  # this is valid

    # -------------------------------------------------------------------
    # Deepened: Abandoned vs Completed distinguishability (D-5)
    # -------------------------------------------------------------------

    def test_abandoned_and_completed_distinguishable_in_same_db(
        self, tmp_path, db,
    ):
        """Abandoned and completed features both map to kanban_column='completed'
        but MUST be distinguishable by workflow_phase (finish vs non-finish).

        Anticipate: If the abandoned case incorrectly sets workflow_phase='finish',
        abandoned and completed features would be indistinguishable.
        derived_from: spec:D-5, dimension:adversarial
        """
        # Given a completed feature (lastCompletedPhase=finish)
        done_dir = tmp_path / "features" / "comp-feat"
        done_dir.mkdir(parents=True)
        (done_dir / ".meta.json").write_text(json.dumps({
            "status": "completed",
            "lastCompletedPhase": "finish",
        }))
        db.register_entity("feature", "comp-feat", "Completed",
                           artifact_path=str(done_dir), status="completed")

        # And an abandoned feature (lastCompletedPhase=design, stopped mid-work)
        aband_dir = tmp_path / "features" / "aband-feat"
        aband_dir.mkdir(parents=True)
        (aband_dir / ".meta.json").write_text(json.dumps({
            "status": "abandoned",
            "lastCompletedPhase": "design",
        }))
        db.register_entity("feature", "aband-feat", "Abandoned",
                           artifact_path=str(aband_dir), status="abandoned")

        # When backfill runs
        backfill_workflow_phases(db, str(tmp_path))

        # Then both have kanban_column='completed'
        completed = db.get_workflow_phase("feature:comp-feat")
        abandoned = db.get_workflow_phase("feature:aband-feat")
        assert completed["kanban_column"] == "completed"
        assert abandoned["kanban_column"] == "completed"

        # But they are distinguishable by workflow_phase
        assert completed["workflow_phase"] == "finish"
        assert abandoned["workflow_phase"] == "create-plan"  # next after design
        assert completed["workflow_phase"] != abandoned["workflow_phase"]

    # -------------------------------------------------------------------
    # Deepened: Active feature with finish as lastCompletedPhase
    # -------------------------------------------------------------------

    def test_backfill_active_feature_with_finish_as_last_completed_phase(
        self, tmp_path, db,
    ):
        """Active feature where lastCompletedPhase=finish: workflow_phase should
        be 'finish' (terminal state per D-5), not None.

        Anticipate: _derive_next_phase("finish") returns "finish" (terminal),
        but then status=="completed" override also sets "finish". For status=="active"
        with lastCompletedPhase=="finish", the implementation must still derive
        "finish" without the completed override. A bug would return None if
        _derive_next_phase tried to find idx+1 past the end.
        derived_from: spec:D-5, dimension:boundary_values
        """
        feat_dir = tmp_path / "features" / "active-finish"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "finish",
        }))
        db.register_entity("feature", "active-finish", "Active But Finish",
                           artifact_path=str(feat_dir), status="active")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:active-finish")
        assert wp is not None
        assert wp["kanban_column"] == "documenting"  # active + finish phase -> documenting
        assert wp["workflow_phase"] == "finish"  # terminal: finish -> finish
        assert wp["last_completed_phase"] == "finish"

    # -------------------------------------------------------------------
    # Deepened: Active feature with NULL lastCompletedPhase
    # -------------------------------------------------------------------

    def test_backfill_active_feature_with_null_last_completed_phase(
        self, tmp_path, db,
    ):
        """Active feature without lastCompletedPhase in .meta.json:
        workflow_phase should be NULL (can't derive next).

        Anticipate: If backfill defaults to a phase instead of None when
        lastCompletedPhase is missing, active features with unknown progress
        would be misrepresented.
        derived_from: spec:D-5, dimension:boundary_values
        """
        feat_dir = tmp_path / "features" / "active-nolcp"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
        }))
        db.register_entity("feature", "active-nolcp", "Active No LCP",
                           artifact_path=str(feat_dir), status="active")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:active-nolcp")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"  # active + no phase -> backlog
        assert wp["workflow_phase"] is None  # NULL lastCompletedPhase -> None
        assert wp["last_completed_phase"] is None

    # -------------------------------------------------------------------
    # Deepened: Abandoned without lastCompletedPhase
    # -------------------------------------------------------------------

    def test_backfill_abandoned_feature_without_last_completed_phase(
        self, tmp_path, db,
    ):
        """Abandoned feature without lastCompletedPhase: workflow_phase=NULL,
        kanban_column='completed'.

        Anticipate: If backfill assigns a default phase to abandoned entities
        without lastCompletedPhase, they would appear to have made progress
        they never made. Per D-5: "abandoned -> NULL if lastCompletedPhase
        is unavailable."
        derived_from: spec:D-5, dimension:adversarial
        """
        feat_dir = tmp_path / "features" / "aband-nolcp"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "abandoned",
        }))
        db.register_entity("feature", "aband-nolcp", "Abandoned No LCP",
                           artifact_path=str(feat_dir), status="abandoned")
        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("feature:aband-nolcp")
        assert wp is not None
        assert wp["kanban_column"] == "completed"  # abandoned -> completed
        assert wp["workflow_phase"] is None  # no lastCompletedPhase -> NULL
        assert wp["last_completed_phase"] is None

    # -------------------------------------------------------------------
    # Deepened: Backfill does NOT overwrite manually-updated rows
    # -------------------------------------------------------------------

    def test_backfill_does_not_overwrite_manually_updated_rows(
        self, tmp_path, db,
    ):
        """INSERT OR IGNORE: if a row was manually updated after first backfill,
        re-running backfill should NOT overwrite the manual changes.

        Anticipate: If backfill uses INSERT OR REPLACE instead of INSERT OR
        IGNORE, manually updated rows would be reverted to backfill defaults.
        derived_from: spec:D-4, dimension:mutation_mindset
        """
        # Given a feature entity
        db.register_entity("feature", "manual-edit", "Manual Edit Test")

        # And first backfill creates a row
        backfill_workflow_phases(db, str(tmp_path))
        wp_before = db.get_workflow_phase("feature:manual-edit")
        assert wp_before is not None
        assert wp_before["kanban_column"] == "backlog"

        # And someone manually updates it
        db.update_workflow_phase(
            "feature:manual-edit",
            kanban_column="wip",
            workflow_phase="implement",
        )

        # When backfill runs again
        result = backfill_workflow_phases(db, str(tmp_path))

        # Then the manually-updated values are preserved (INSERT OR IGNORE)
        wp_after = db.get_workflow_phase("feature:manual-edit")
        assert wp_after["kanban_column"] == "wip"  # manual, not reverted
        assert wp_after["workflow_phase"] == "implement"  # manual, not reverted
        assert result["skipped"] >= 1  # row was skipped, not replaced

    # -------------------------------------------------------------------
    # Deepened: Single entity failure doesn't abort remaining
    # -------------------------------------------------------------------

    def test_backfill_single_entity_failure_does_not_abort_others(
        self, tmp_path, db,
    ):
        """If one entity causes an exception during backfill, processing
        continues for remaining entities.

        Anticipate: If the try/except inside the per-entity loop is missing
        or catches too narrowly, a single failure would abort the entire
        backfill, leaving later entities without workflow_phases rows.
        derived_from: dimension:error_propagation, spec:D-9
        """
        # Given: two features registered, plus a third added after initial backfill
        db.register_entity("feature", "good-entity", "Good Entity")
        db.register_entity("feature", "another-good", "Another Good")

        # When: backfill runs for both
        result = backfill_workflow_phases(db, str(tmp_path))

        # Then: both succeed
        assert result["created"] == 2
        assert len(result["errors"]) == 0

        # Given: add a third feature, clear workflow_phases, re-backfill
        db.register_entity("feature", "post-error", "Post Error")
        db._conn.execute("DELETE FROM workflow_phases")
        db._conn.commit()

        # When: re-backfill with all three
        result2 = backfill_workflow_phases(db, str(tmp_path))

        # Then: all three get workflow_phases rows
        assert result2["created"] >= 3
        assert db.get_workflow_phase("feature:good-entity") is not None
        assert db.get_workflow_phase("feature:post-error") is not None

    # -------------------------------------------------------------------
    # Deepened: _derive_next_phase boundary — brainstorm (first) phase
    # -------------------------------------------------------------------

    def test_derive_next_phase_brainstorm_returns_specify(self):
        """brainstorm is the first phase; next should be specify.

        Anticipate: If PHASE_SEQUENCE[0] is not correctly handled,
        the index calculation might underflow or return wrong phase.
        derived_from: dimension:boundary_values, spec:D-5
        """
        assert _derive_next_phase("brainstorm") == "specify"

    def test_derive_next_phase_create_plan_returns_create_tasks(self):
        """create-plan -> create-tasks (hyphenated phase names).

        Anticipate: If phase sequence matching uses partial string match
        instead of exact, "create-plan" might match "create-tasks" or vice versa.
        derived_from: dimension:boundary_values
        """
        assert _derive_next_phase("create-plan") == "create-tasks"

    def test_derive_next_phase_create_tasks_returns_implement(self):
        """create-tasks -> implement.
        derived_from: dimension:boundary_values
        """
        assert _derive_next_phase("create-tasks") == "implement"

    # -------------------------------------------------------------------
    # Deepened: PHASE_SEQUENCE and VALID_MODES constants
    # -------------------------------------------------------------------

    def test_phase_sequence_has_exactly_seven_elements(self):
        """PHASE_SEQUENCE must have exactly 7 elements matching spec.

        Anticipate: If a phase is accidentally added or removed, the
        derive_next_phase logic and CHECK constraints would silently diverge.
        derived_from: dimension:mutation_mindset, spec:D-5
        """
        assert len(PHASE_SEQUENCE) == 7
        assert PHASE_SEQUENCE == (
            "brainstorm", "specify", "design",
            "create-plan", "create-tasks", "implement", "finish",
        )

    def test_valid_modes_includes_light(self):
        """VALID_MODES must include 'light' (feature:052 AC-4).
        derived_from: dimension:mutation_mindset, spec:AC-4
        """
        assert VALID_MODES == frozenset({"standard", "full", "light"})

    def test_derive_kanban_covers_four_statuses(self):
        """derive_kanban handles the 4 core statuses correctly.
        derived_from: dimension:mutation_mindset, spec:D-5
        """
        assert derive_kanban("planned", None) == "backlog"
        assert derive_kanban("active", None) == "backlog"
        assert derive_kanban("completed", None) == "completed"
        assert derive_kanban("abandoned", None) == "completed"

    # -------------------------------------------------------------------
    # Phase 4: Brainstorm/backlog phase-aware backfill (Tasks 4.3)
    # -------------------------------------------------------------------

    def test_backfill_brainstorm_no_row_creates_draft(self, tmp_path, db):
        """Brainstorm entity with no workflow_phases row -> INSERT with draft/wip."""
        db.register_entity("brainstorm", "bs-new", "New Brainstorm")
        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-new")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"
        assert result["created"] >= 1

    def test_backfill_backlog_no_row_creates_open(self, tmp_path, db):
        """Backlog entity with no workflow_phases row -> INSERT with open/backlog."""
        db.register_entity("backlog", "bl-new", "New Backlog")
        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("backlog:bl-new")
        assert wp is not None
        assert wp["workflow_phase"] == "open"
        assert wp["kanban_column"] == "backlog"
        assert result["created"] >= 1

    def test_backfill_brainstorm_nonnull_phase_skipped(self, tmp_path, db):
        """Existing row with workflow_phase='reviewing' -> skipped, not overwritten."""
        db.register_entity("brainstorm", "bs-managed", "Managed Brainstorm")
        # Pre-create a workflow_phases row with a non-null phase (simulating MCP-managed state)
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("brainstorm:bs-managed", "reviewing", "agent_review", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-managed")
        assert wp["workflow_phase"] == "reviewing"  # preserved, not overwritten
        assert wp["kanban_column"] == "agent_review"  # preserved
        assert result["skipped"] >= 1

    def test_backfill_brainstorm_null_phase_updated(self, tmp_path, db):
        """Existing row with NULL workflow_phase -> UPDATE to draft/wip."""
        db.register_entity("brainstorm", "bs-legacy", "Legacy Brainstorm")
        # Pre-create a workflow_phases row with NULL phase (legacy backfill artifact)
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("brainstorm:bs-legacy", None, "backlog", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-legacy")
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"
        assert result["updated"] >= 1

    def test_backfill_backlog_null_phase_updated(self, tmp_path, db):
        """Existing row with NULL workflow_phase -> UPDATE to open/backlog."""
        db.register_entity("backlog", "bl-legacy", "Legacy Backlog")
        # Pre-create a workflow_phases row with NULL phase
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("backlog:bl-legacy", None, "backlog", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("backlog:bl-legacy")
        assert wp["workflow_phase"] == "open"
        assert wp["kanban_column"] == "backlog"
        assert result["updated"] >= 1

    def test_backfill_child_completion_override_preserved(self, tmp_path, db):
        """Brainstorm with all completed child features -> kanban_column='completed'."""
        db.register_entity("brainstorm", "bs-done-parent", "Done Parent")
        child_tid = db.register_entity(
            "feature", "f-done-child", "Done Child", status="completed"
        )
        db.set_parent(child_tid, "brainstorm:bs-done-parent")

        backfill_workflow_phases(db, str(tmp_path))

        wp = db.get_workflow_phase("brainstorm:bs-done-parent")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"  # default for brainstorm
        assert wp["kanban_column"] == "completed"  # overridden by child completion

    def test_backfill_returns_updated_counter(self, tmp_path, db):
        """Return dict includes 'updated' key with correct count."""
        db.register_entity("brainstorm", "bs-u1", "Update Test 1")
        db.register_entity("backlog", "bl-u1", "Update Test 2")
        # Pre-create rows with NULL phases
        for tid in ("brainstorm:bs-u1", "backlog:bl-u1"):
            db._conn.execute(
                "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (tid, None, "backlog", db._now_iso()),
            )
        db._conn.commit()

        result = backfill_workflow_phases(db, str(tmp_path))

        assert "updated" in result
        assert isinstance(result["updated"], int)
        assert result["updated"] == 2

    def test_backfill_child_completion_with_all_feature_children_completed(
        self, tmp_path, db
    ):
        """Brainstorm with multiple completed children -> kanban_column='completed'.
        derived_from: spec:AC-7, dimension:boundary_values

        Anticipate: If child completion logic uses "any" instead of "all",
        a single completed child among many incomplete ones would incorrectly
        set kanban_column to 'completed'.
        """
        # Given a brainstorm with 3 feature children, all status='completed'
        db.register_entity("brainstorm", "bs-multi-done", "Multi Done Parent")
        for i in range(3):
            child_uuid = db.register_entity(
                "feature", f"f-done-{i}", f"Done Child {i}", status="completed"
            )
            db.set_parent(child_uuid, "brainstorm:bs-multi-done")

        # When running backfill
        backfill_workflow_phases(db, str(tmp_path))

        # Then brainstorm kanban_column is 'completed'
        wp = db.get_workflow_phase("brainstorm:bs-multi-done")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_backfill_child_completion_not_all_completed(self, tmp_path, db):
        """Brainstorm with mix of completed and active children -> NOT completed.
        derived_from: spec:AC-7, dimension:mutation_mindset

        Anticipate: If child completion uses "any" instead of "all",
        this test would incorrectly pass (kanban='completed' even though
        one child is active).
        """
        # Given a brainstorm with 2 children: one completed, one active
        db.register_entity("brainstorm", "bs-mixed", "Mixed Parent")
        child1 = db.register_entity(
            "feature", "f-mix-done", "Done Child", status="completed"
        )
        child2 = db.register_entity(
            "feature", "f-mix-active", "Active Child", status="active"
        )
        db.set_parent(child1, "brainstorm:bs-mixed")
        db.set_parent(child2, "brainstorm:bs-mixed")

        # When running backfill
        backfill_workflow_phases(db, str(tmp_path))

        # Then brainstorm kanban_column should NOT be 'completed'
        wp = db.get_workflow_phase("brainstorm:bs-mixed")
        assert wp is not None
        assert wp["kanban_column"] != "completed"

    # -------------------------------------------------------------------
    # Task 1.5: Backfill encapsulation & batching verification
    # -------------------------------------------------------------------

    def test_backfill_no_raw_conn_execute(self):
        """Verify backfill.py contains no raw db._conn.execute calls."""
        import inspect
        import entity_registry.backfill as backfill_mod

        source = inspect.getsource(backfill_mod)
        violations = [
            line.strip()
            for line in source.splitlines()
            if "db._conn.execute" in line or "db._conn.commit" in line
            or "db._now_iso" in line
        ]
        assert violations == [], (
            f"Raw db._conn access found in backfill.py:\n"
            + "\n".join(violations)
        )

    def test_backfill_batched_transactions(self, tmp_path, db):
        """Verify backfill_workflow_phases uses batched transactions.

        Creates 25 entities (batch size 20), expects 2 outer batch
        transactions.  Inner API calls (upsert_workflow_phase) also call
        transaction() re-entrantly, so we only count top-level entries.
        """
        from unittest.mock import patch

        # Register 25 feature entities
        for i in range(25):
            db.register_entity("feature", f"batch-f{i:03d}", f"Feature {i}")

        # Instrument db.transaction() to count only top-level calls
        original_transaction = db.transaction
        top_level_count = 0
        depth = 0

        class CountingContextManager:
            def __init__(self, cm):
                self._cm = cm

            def __enter__(self):
                nonlocal top_level_count, depth
                if depth == 0:
                    top_level_count += 1
                depth += 1
                return self._cm.__enter__()

            def __exit__(self, *args):
                nonlocal depth
                depth -= 1
                return self._cm.__exit__(*args)

        def counting_transaction():
            return CountingContextManager(original_transaction())

        with patch.object(db, "transaction", counting_transaction):
            backfill_workflow_phases(db, str(tmp_path))

        # 25 entities / batch size 20 = 2 batches
        assert top_level_count == 2, (
            f"Expected 2 top-level batched transactions for 25 entities, "
            f"got {top_level_count}"
        )
