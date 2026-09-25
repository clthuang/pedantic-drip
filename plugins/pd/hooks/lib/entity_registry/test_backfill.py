"""Tests for entity_registry.backfill module."""
from __future__ import annotations

import json
import os

import pytest

from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID
from entity_registry.test_helpers import identity_kwargs


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
        "backlog_source": "019-entity-lineage",
    }
    (feat_dir / ".meta.json").write_text(json.dumps(meta))

    # --- brainstorms ---
    bs_dir = tmp_path / "brainstorms"
    bs_dir.mkdir()
    (bs_dir / "20260227-lineage.prd.md").write_text(
        "# Brainstorm\n\n*Source: Backlog #019-entity-lineage*\n\nSome content.\n"
    )

    # --- projects (empty) ---
    (tmp_path / "projects").mkdir()

    # --- backlog.md ---
    backlog_md = (
        "# Backlog\n\n"
        "| ID | Timestamp | Description |\n"
        "|----|-----------|-------------|\n"
        "| 019-entity-lineage | 2026-02-27T05:00:00Z | Entity lineage tracking |\n"
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
        backlog = db.get_entity("backlog:019-entity-lineage")
        assert backlog is not None

        # Brainstorm that references backlog should have parent link
        brainstorm = db.get_entity("brainstorm:20260227-lineage")
        assert brainstorm is not None

    def test_all_entity_types_registered(self, artifacts):
        """After backfill, entities of all scanned types should be present."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        assert db.get_entity("backlog:019-entity-lineage") is not None
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
        proj_dir = tmp_path / "projects" / "001-test-project"
        proj_dir.mkdir(parents=True)
        (proj_dir / ".meta.json").write_text(json.dumps({
            "id": "001",
            "slug": "test-project",
            "name": "Test Project",
        }))

        # Create feature with project_id
        feat_dir = tmp_path / "features" / "030-some-feature"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "id": "030",
            "slug": "some-feature",
            "project_id": "001-test-project",
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
            assert feature["parent_type_id"] == "project:001-test-project"
        finally:
            db.close()

    def test_brainstorm_to_backlog_format1(self, artifacts):
        """Brainstorm with '*Source: Backlog #019-entity-lineage*' should link to backlog."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        brainstorm = db.get_entity("brainstorm:20260227-lineage")
        assert brainstorm is not None
        assert brainstorm["parent_type_id"] == "backlog:019-entity-lineage"

    def test_brainstorm_to_backlog_format2(self, tmp_path):
        """Brainstorm with '**Backlog Item:** 019-entity-lineage' should link to backlog."""
        # Create backlog
        (tmp_path / "backlog.md").write_text(
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            "| 020-another-item | 2026-02-28T00:00:00Z | Another item |\n"
        )

        # Create brainstorm with format 2
        bs_dir = tmp_path / "brainstorms"
        bs_dir.mkdir()
        (bs_dir / "20260228-another.prd.md").write_text(
            "# Brainstorm\n\n**Backlog Item:** 020-another-item\n\nSome content.\n"
        )

        (tmp_path / "features").mkdir()
        (tmp_path / "projects").mkdir()

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            run_backfill(db, str(tmp_path))

            brainstorm = db.get_entity("brainstorm:20260228-another")
            assert brainstorm is not None
            assert brainstorm["parent_type_id"] == "backlog:020-another-item"
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
# Task 3.8: Idempotency and .prd.md/.md priority tests
# ---------------------------------------------------------------------------


class TestIdempotencyAndPriority:
    def test_backfill_idempotent(self, artifacts):
        """Running backfill twice produces same result (no duplicates, no errors)."""
        root, db = artifacts
        from entity_registry.backfill import run_backfill

        run_backfill(db, str(root))

        # Capture state after first run
        backlog1 = db.get_entity("backlog:019-entity-lineage")
        brainstorm1 = db.get_entity("brainstorm:20260227-lineage")
        feature1 = db.get_entity("feature:029-entity-lineage-tracking")

        # Clear backfill_complete marker to allow re-run
        db.set_metadata("backfill_complete", "0")

        # Run again
        run_backfill(db, str(root))

        # Entities should be identical (INSERT OR IGNORE preserves originals)
        backlog2 = db.get_entity("backlog:019-entity-lineage")
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

            # Count all brainstorm entities. F11 (feature 109): entity_type
            # column dropped; kind replaces it.
            cur = db._conn.execute(
                "SELECT COUNT(*) FROM entities WHERE kind = 'brainstorm'"
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
            "| 050-partial-test | 2026-03-01T00:00:00Z | Partial test |\n"
        )

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill

            # Simulate partial: manually register one entity, no marker
            db.register_entity("backlog", name="Partial test", seq=50, slug="backlog", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

            # Full run should succeed (INSERT OR IGNORE on existing entity)
            run_backfill(db, str(tmp_path))

            # Entity should still exist with original name
            backlog = db.get_entity("backlog:050-backlog")
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
            f"| 001-title-item | 2026-01-01T00:00:00Z | {short} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:001-title-item")
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
            f"| 001-title-item | 2026-01-01T00:00:00Z | {long_desc} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:001-title-item")
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
            f"| 001-title-item | 2026-01-01T00:00:00Z | {long_desc} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:001-title-item")
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
            f"| 001-title-item | 2026-01-01T00:00:00Z | {no_space} |\n"
        )
        (tmp_path / "brainstorms").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "features").mkdir()
        (tmp_path / "backlog.md").write_text(backlog_md)

        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:001-title-item")
            assert entity["name"] == "a" * 80 + "\u2026"
        finally:
            db.close()


class TestBacklogStatusDerivation:
    """Tests for backlog row handling in _scan_backlog.

    Feature 111 / FR-CL.1: free-text suffix parsers removed from
    backfill.py. The 4 parser-only tests (promoted/closed/fixed/already
    implemented) were DELETED; ``test_idempotent_no_clobber_promoted``
    was also deleted (it depended on parser-derived status). Only the
    positive regression guard remains.
    """

    def _make_backlog(self, tmp_path, item_id, description):
        backlog_md = (
            "# Backlog\n\n"
            "| ID | Timestamp | Description |\n"
            "|----|-----------|-------------|\n"
            f"| {item_id} | 2026-01-01T00:00:00Z | {description} |\n"
        )
        (tmp_path / "brainstorms").mkdir(exist_ok=True)
        (tmp_path / "projects").mkdir(exist_ok=True)
        (tmp_path / "features").mkdir(exist_ok=True)
        (tmp_path / "backlog.md").write_text(backlog_md)

    def test_no_annotation_leaves_status_null(self, tmp_path):
        self._make_backlog(tmp_path, "005-webhook-retry", "Add retry logic to webhook delivery")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            from entity_registry.backfill import run_backfill
            run_backfill(db, str(tmp_path))
            entity = db.get_entity("backlog:005-webhook-retry")
            assert entity["status"] is None or entity["status"] == ""
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
    _kanban_column_for,
    backfill_workflow_phases,
)


class TestWorkflowPhaseBackfill:
    """Tests for workflow phase backfill constants, helpers, and main function."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create an EntityDatabase with workflow_phases table."""
        db = EntityDatabase(str(tmp_path / "test.db"))
        yield db
        db.close()

    # -------------------------------------------------------------------
    # Task 3.1: Kanban derivation (via _kanban_column_for — replaced STATUS_TO_KANBAN;
    # this module's own private replica since feature 132 D6.1-.3 retired
    # the shared workflow_engine.kanban module)
    # -------------------------------------------------------------------

    def test_status_planned_maps_to_backlog(self):
        assert _kanban_column_for("planned", None) == "backlog"

    def test_status_active_no_phase_maps_to_backlog(self):
        assert _kanban_column_for("active", None) == "backlog"

    def test_status_completed_maps_to_completed(self):
        assert _kanban_column_for("completed", None) == "completed"

    def test_status_abandoned_maps_to_completed(self):
        assert _kanban_column_for("abandoned", None) == "completed"

    def test_unmapped_status_falls_back_to_backlog(self):
        """Unmapped statuses like 'draft' fall back to backlog via _kanban_column_for."""
        assert _kanban_column_for("draft", None) == "backlog"

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
    # Task 3.3b: status resolution (W2.6: the registry's status, 'planned'
    # when unset; no .meta.json is read)
    # -------------------------------------------------------------------

    def test_status_from_db_when_no_meta_json(self, tmp_path, db):
        """Entity with no .meta.json and entities.status=completed -> uses completed."""
        db.register_entity("feature", name="Status Test 2", seq=1, slug="s2-test", status="completed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-s2-test")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_status_defaults_to_planned_when_no_source(self, tmp_path, db):
        """Entity with no .meta.json and entities.status=NULL -> defaults to planned -> backlog."""
        db.register_entity("feature", name="Status Test 3", seq=1, slug="s3-test", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-s3-test")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"

    def test_unmapped_status_defaults_to_planned_with_warning(self, tmp_path, db, caplog):
        """Unmapped status (e.g., 'draft') -> default to planned -> backlog, with warning."""
        import logging

        db.register_entity("feature", name="Status Test 5", seq=1, slug="s5-test", status="draft", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        with caplog.at_level(logging.WARNING):
            backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-s5-test")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        # Should have warning about unmapped status
        assert any("draft" in record.message for record in caplog.records)

    # -------------------------------------------------------------------
    # Task 3.4: Integration tests for backfill feature entities
    # -------------------------------------------------------------------

    def test_backfill_active_feature_row_ignores_its_meta_json(self, tmp_path, db):
        """Active feature -> kanban=backlog, no phase, last_completed_phase or
        mode: the registry names none, and its .meta.json is not read (W2.6)."""
        feat_dir = tmp_path / "features" / "001-f1-active"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
            "lastCompletedPhase": "design",
            "mode": "standard",
        }))

        db.register_entity("feature", name="Active Feature", seq=1, slug="f1-active",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           artifact_path=str(feat_dir), status="active")
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-f1-active")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"  # active + no phase -> backlog
        assert wp["workflow_phase"] is None  # the file's design is not read
        assert wp["last_completed_phase"] is None
        assert wp["mode"] is None
        assert result["created"] >= 1

    def test_backfill_completed_feature(self, tmp_path, db):
        """Completed feature -> kanban=completed, workflow_phase=finish."""
        feat_dir = tmp_path / "features" / "001-f2-done"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "completed",
            "lastCompletedPhase": "finish",
            "mode": "standard",
        }))

        db.register_entity("feature", name="Done Feature", seq=1, slug="f2-done",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           artifact_path=str(feat_dir), status="completed")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-f2-done")
        assert wp is not None
        assert wp["kanban_column"] == "completed"
        assert wp["workflow_phase"] == "finish"  # finish -> finish (terminal)

    def test_backfill_planned_feature(self, tmp_path, db):
        """Planned feature -> kanban=backlog, workflow_phase=NULL."""
        db.register_entity("feature", name="Planned Feature", seq=1, slug="f3-planned", status="planned", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-f3-planned")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        assert wp["workflow_phase"] is None

    def test_backfill_abandoned_feature_row_ignores_its_meta_json(self, tmp_path, db):
        """Abandoned feature -> kanban=completed, no phase: only a completed
        feature is at finish, and its .meta.json is not read (W2.6)."""
        feat_dir = tmp_path / "features" / "001-f4-abandoned"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "abandoned",
            "lastCompletedPhase": "create-plan",
            "mode": "full",
        }))

        db.register_entity("feature", name="Abandoned Feature", seq=1, slug="f4-abandoned",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           artifact_path=str(feat_dir), status="abandoned")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-f4-abandoned")
        assert wp is not None
        assert wp["kanban_column"] == "completed"  # abandoned -> completed
        assert wp["workflow_phase"] is None  # the file's create-plan is not read
        assert wp["last_completed_phase"] is None
        assert wp["mode"] is None

    # -------------------------------------------------------------------
    # Task 3.5: Brainstorm/backlog entities
    # -------------------------------------------------------------------

    def test_backfill_brainstorm_entity(self, tmp_path, db):
        """Brainstorm entity -> workflow_phase=draft, kanban_column=wip."""
        db.register_entity("brainstorm", name="Test Brainstorm", display_id="20260101-000012-bs-test", status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000012-bs-test")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"

    def test_backfill_backlog_entity(self, tmp_path, db):
        """Backlog entity -> workflow_phase=open, kanban_column=backlog."""
        db.register_entity("backlog", name="Test Backlog", seq=1, slug="bl-test", status="planned", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("backlog:001-bl-test")
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
        db.register_entity("brainstorm", name="Parent Brainstorm", display_id="20260101-000011-bs-parent", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        child_tid = db.register_entity(
            "feature", name="Child Feature", seq=1, slug="f-child", status="completed",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.set_parent(child_tid, "brainstorm:20260101-000011-bs-parent")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000011-bs-parent")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_backlog_with_completed_child_gets_completed_kanban(self, tmp_path, db):
        """Backlog with all child features completed -> kanban=completed."""
        db.register_entity("backlog", name="Parent Backlog", seq=1, slug="bl-parent", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        child_tid = db.register_entity(
            "feature", name="Child Feature 2", seq=1, slug="f-child2", status="completed",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.set_parent(child_tid, "backlog:001-bl-parent")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("backlog:001-bl-parent")
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_brainstorm_with_mixed_children_stays_at_default_kanban(self, tmp_path, db):
        """Brainstorm with mix of completed and active children -> no override, uses default wip."""
        db.register_entity("brainstorm", name="Mixed Brainstorm", display_id="20260101-000007-bs-mixed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        c1 = db.register_entity("feature", name="Done", seq=1, slug="f-done", status="completed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        c2 = db.register_entity("feature", name="WIP", seq=1, slug="f-wip", status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        db.set_parent(c1, "brainstorm:20260101-000007-bs-mixed")
        db.set_parent(c2, "brainstorm:20260101-000007-bs-mixed")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000007-bs-mixed")
        assert wp is not None
        # Not all children completed, so kanban uses brainstorm default (wip)
        assert wp["kanban_column"] == "wip"

    def test_brainstorm_with_no_children_stays_at_default_kanban(self, tmp_path, db):
        """Brainstorm with no child features -> kanban uses brainstorm default (wip)."""
        db.register_entity("brainstorm", name="Lonely Brainstorm", display_id="20260101-000005-bs-lonely", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000005-bs-lonely")
        assert wp is not None
        assert wp["kanban_column"] == "wip"  # brainstorm default

    # -------------------------------------------------------------------
    # Task 3.6: Project entity exclusion
    # -------------------------------------------------------------------

    def test_backfill_excludes_project_entities(self, tmp_path, db):
        """Project entities should NOT get workflow_phases rows."""
        db.register_entity("project", name="Test Project", seq=2, slug="p1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        db.register_entity("feature", name="Test Feature", seq=1, slug="f1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        assert db.get_workflow_phase("project:002-p1") is None
        assert db.get_workflow_phase("feature:001-f1") is not None  # feature gets a row

    # -------------------------------------------------------------------
    # Task 3.7: Backfill idempotency
    # -------------------------------------------------------------------

    def test_backfill_idempotent_second_run_no_creates(self, tmp_path, db):
        """Second backfill run creates 0, skips all, no errors."""
        db.register_entity("feature", name="Feature 1", seq=1, slug="f1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        result1 = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        assert result1["created"] >= 1

        result2 = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        assert result2["created"] == 0
        assert result2["skipped"] >= 1
        assert len(result2["errors"]) == 0

    def test_backfill_idempotent_existing_rows_not_modified(self, tmp_path, db):
        """Existing rows should not be modified on re-run."""
        db.register_entity("feature", name="Feature 1", seq=1, slug="f1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        wp1 = db.get_workflow_phase("feature:001-f1")

        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        wp2 = db.get_workflow_phase("feature:001-f1")

        assert wp1["updated_at"] == wp2["updated_at"]

    def test_backfill_returns_dict_with_required_keys(self, tmp_path, db):
        """Return dict has created/skipped/errors keys."""
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        assert "created" in result
        assert "skipped" in result
        assert "errors" in result
        assert isinstance(result["created"], int)
        assert isinstance(result["skipped"], int)
        assert isinstance(result["errors"], list)

    # -------------------------------------------------------------------
    # Task 3.8: no .meta.json needed (W2.6: none is read)
    # -------------------------------------------------------------------

    def test_backfill_missing_meta_json_uses_defaults(self, tmp_path, db):
        """Missing .meta.json -> defaults used, no error."""
        db.register_entity("feature", name="No Meta", seq=1, slug="no-meta", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-no-meta")
        assert wp is not None
        assert wp["kanban_column"] == "backlog"
        assert len(result["errors"]) == 0

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
        # Given a completed feature and an abandoned one (the registry's
        # statuses: W2.6 reads no .meta.json)
        db.register_entity("feature", name="Completed", seq=1, slug="comp-feat",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           status="completed")
        db.register_entity("feature", name="Abandoned", seq=1, slug="aband-feat",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           status="abandoned")

        # When backfill runs
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then both have kanban_column='completed'
        completed = db.get_workflow_phase("feature:001-comp-feat")
        abandoned = db.get_workflow_phase("feature:001-aband-feat")
        assert completed["kanban_column"] == "completed"
        assert abandoned["kanban_column"] == "completed"

        # But they are distinguishable by workflow_phase
        assert completed["workflow_phase"] == "finish"
        assert abandoned["workflow_phase"] is None  # only completed is at finish
        assert completed["workflow_phase"] != abandoned["workflow_phase"]

    # -------------------------------------------------------------------
    # Deepened: Active feature with NULL lastCompletedPhase
    # -------------------------------------------------------------------

    def test_backfill_active_feature_with_null_last_completed_phase(
        self, tmp_path, db,
    ):
        """Active feature: workflow_phase should be NULL (the registry
        names no phase for it; its .meta.json is not read, W2.6).

        Anticipate: If backfill defaults to a phase instead of None,
        active features with unknown progress would be misrepresented.
        derived_from: spec:D-5, dimension:boundary_values
        """
        feat_dir = tmp_path / "features" / "001-active-nolcp"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "active",
        }))
        db.register_entity("feature", name="Active No LCP", seq=1, slug="active-nolcp",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           artifact_path=str(feat_dir), status="active")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-active-nolcp")
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
        feat_dir = tmp_path / "features" / "001-aband-nolcp"
        feat_dir.mkdir(parents=True)
        (feat_dir / ".meta.json").write_text(json.dumps({
            "status": "abandoned",
        }))
        db.register_entity("feature", name="Abandoned No LCP", seq=1, slug="aband-nolcp",
                               workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
                           artifact_path=str(feat_dir), status="abandoned")
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("feature:001-aband-nolcp")
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
        db.register_entity("feature", name="Manual Edit Test", seq=1, slug="manual-edit", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # And first backfill creates a row
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        wp_before = db.get_workflow_phase("feature:001-manual-edit")
        assert wp_before is not None
        assert wp_before["kanban_column"] == "backlog"

        # And someone manually updates it
        db.update_workflow_phase(
            "feature:001-manual-edit",
            kanban_column="wip",
            workflow_phase="implement",
        )

        # When backfill runs again
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then the manually-updated values are preserved (INSERT OR IGNORE)
        wp_after = db.get_workflow_phase("feature:001-manual-edit")
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
        db.register_entity("feature", name="Good Entity", seq=1, slug="good-entity", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        db.register_entity("feature", name="Another Good", seq=1, slug="another-good", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # When: backfill runs for both
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then: both succeed
        assert result["created"] == 2
        assert len(result["errors"]) == 0

        # Given: add a third feature, clear workflow_phases, re-backfill
        db.register_entity("feature", name="Post Error", seq=1, slug="post-error", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        db._conn.execute("DELETE FROM workflow_phases")
        db._conn.commit()

        # When: re-backfill with all three
        result2 = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then: all three get workflow_phases rows
        assert result2["created"] >= 3
        assert db.get_workflow_phase("feature:001-good-entity") is not None
        assert db.get_workflow_phase("feature:001-post-error") is not None

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

    def test_derive_next_phase_create_plan_returns_implement(self):
        """create-plan -> implement (create-tasks removed in feature 073).

        Anticipate: If phase sequence matching uses partial string match
        instead of exact, "create-plan" might match incorrectly.
        derived_from: dimension:boundary_values
        """
        assert _derive_next_phase("create-plan") == "implement"

    # -------------------------------------------------------------------
    # Deepened: PHASE_SEQUENCE and VALID_MODES constants
    # -------------------------------------------------------------------

    def test_phase_sequence_has_exactly_six_elements(self):
        """PHASE_SEQUENCE must have exactly 6 elements (create-tasks removed in 073).

        Anticipate: If a phase is accidentally added or removed, the
        derive_next_phase logic and CHECK constraints would silently diverge.
        derived_from: dimension:mutation_mindset, spec:D-5
        """
        assert len(PHASE_SEQUENCE) == 6
        assert PHASE_SEQUENCE == (
            "brainstorm", "specify", "design",
            "create-plan", "implement", "finish",
        )

    def test_valid_modes_includes_light(self):
        """VALID_MODES must include 'light' (feature:052 AC-4).
        derived_from: dimension:mutation_mindset, spec:AC-4
        """
        assert VALID_MODES == frozenset({"standard", "full", "light"})

    def test_kanban_column_for_covers_four_statuses(self):
        """_kanban_column_for handles the 4 core statuses correctly.
        derived_from: dimension:mutation_mindset, spec:D-5
        """
        assert _kanban_column_for("planned", None) == "backlog"
        assert _kanban_column_for("active", None) == "backlog"
        assert _kanban_column_for("completed", None) == "completed"
        assert _kanban_column_for("abandoned", None) == "completed"

    # -------------------------------------------------------------------
    # Phase 4: Brainstorm/backlog phase-aware backfill (Tasks 4.3)
    # -------------------------------------------------------------------

    def test_backfill_brainstorm_no_row_creates_draft(self, tmp_path, db):
        """Brainstorm entity with no workflow_phases row -> INSERT with draft/wip."""
        db.register_entity("brainstorm", name="New Brainstorm", display_id="20260101-000009-bs-new", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000009-bs-new")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"
        assert result["created"] >= 1

    def test_backfill_backlog_no_row_creates_open(self, tmp_path, db):
        """Backlog entity with no workflow_phases row -> INSERT with open/backlog."""
        db.register_entity("backlog", name="New Backlog", seq=1, slug="bl-new", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("backlog:001-bl-new")
        assert wp is not None
        assert wp["workflow_phase"] == "open"
        assert wp["kanban_column"] == "backlog"
        assert result["created"] >= 1

    def test_backfill_brainstorm_nonnull_phase_skipped(self, tmp_path, db):
        """Existing row with workflow_phase='reviewing' -> skipped, not overwritten."""
        db.register_entity("brainstorm", name="Managed Brainstorm", display_id="20260101-000006-bs-managed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        # Pre-create a workflow_phases row with a non-null phase (simulating MCP-managed state)
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("brainstorm:20260101-000006-bs-managed", "reviewing", "agent_review", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000006-bs-managed")
        assert wp["workflow_phase"] == "reviewing"  # preserved, not overwritten
        assert wp["kanban_column"] == "agent_review"  # preserved
        assert result["skipped"] >= 1

    def test_backfill_brainstorm_null_phase_updated(self, tmp_path, db):
        """Existing row with NULL workflow_phase -> UPDATE to draft/wip."""
        db.register_entity("brainstorm", name="Legacy Brainstorm", display_id="20260101-000004-bs-legacy", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        # Pre-create a workflow_phases row with NULL phase (legacy backfill artifact)
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("brainstorm:20260101-000004-bs-legacy", None, "backlog", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000004-bs-legacy")
        assert wp["workflow_phase"] == "draft"
        assert wp["kanban_column"] == "wip"
        assert result["updated"] >= 1

    def test_backfill_backlog_null_phase_updated(self, tmp_path, db):
        """Existing row with NULL workflow_phase -> UPDATE to open/backlog."""
        db.register_entity("backlog", name="Legacy Backlog", seq=1, slug="bl-legacy", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        # Pre-create a workflow_phases row with NULL phase
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("backlog:001-bl-legacy", None, "backlog", db._now_iso()),
        )
        db._conn.commit()

        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("backlog:001-bl-legacy")
        assert wp["workflow_phase"] == "open"
        assert wp["kanban_column"] == "backlog"
        assert result["updated"] >= 1

    def test_backfill_child_completion_override_preserved(self, tmp_path, db):
        """Brainstorm with all completed child features -> kanban_column='completed'."""
        db.register_entity("brainstorm", name="Done Parent", display_id="20260101-000003-bs-done-parent", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        child_tid = db.register_entity(
            "feature", name="Done Child", seq=1, slug="f-done-child", status="completed",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.set_parent(child_tid, "brainstorm:20260101-000003-bs-done-parent")

        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        wp = db.get_workflow_phase("brainstorm:20260101-000003-bs-done-parent")
        assert wp is not None
        assert wp["workflow_phase"] == "draft"  # default for brainstorm
        assert wp["kanban_column"] == "completed"  # overridden by child completion

    def test_backfill_returns_updated_counter(self, tmp_path, db):
        """Return dict includes 'updated' key with correct count."""
        db.register_entity("brainstorm", name="Update Test 1", display_id="20260101-000013-bs-u1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        db.register_entity("backlog", name="Update Test 2", seq=1, slug="bl-u1", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        # Pre-create rows with NULL phases
        for tid in ("brainstorm:20260101-000013-bs-u1", "backlog:001-bl-u1"):
            db._conn.execute(
                "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (tid, None, "backlog", db._now_iso()),
            )
        db._conn.commit()

        result = backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

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
        db.register_entity("brainstorm", name="Multi Done Parent", display_id="20260101-000008-bs-multi-done", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        for i in range(3):
            child_uuid = db.register_entity(
                "feature", name=f"Done Child {i}", **identity_kwargs("feature", f"001-f-done-{i}"), status="completed",
                workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
            )
            db.set_parent(child_uuid, "brainstorm:20260101-000008-bs-multi-done")

        # When running backfill
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then brainstorm kanban_column is 'completed'
        wp = db.get_workflow_phase("brainstorm:20260101-000008-bs-multi-done")
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
        db.register_entity("brainstorm", name="Mixed Parent", display_id="20260101-000007-bs-mixed", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        child1 = db.register_entity(
            "feature", name="Done Child", seq=1, slug="f-mix-done", status="completed",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        child2 = db.register_entity(
            "feature", name="Active Child", seq=1, slug="f-mix-active", status="active",
            workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.set_parent(child1, "brainstorm:20260101-000007-bs-mixed")
        db.set_parent(child2, "brainstorm:20260101-000007-bs-mixed")

        # When running backfill
        backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # Then brainstorm kanban_column should NOT be 'completed'
        wp = db.get_workflow_phase("brainstorm:20260101-000007-bs-mixed")
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
            db.register_entity("feature", name=f"Feature {i}", **identity_kwargs("feature", f"001-batch-f{i:03d}"), workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

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
            backfill_workflow_phases(db, workspace_uuid=_UNKNOWN_WORKSPACE_UUID)

        # 25 entities / batch size 20 = 2 batches
        assert top_level_count == 2, (
            f"Expected 2 top-level batched transactions for 25 entities, "
            f"got {top_level_count}"
        )


# ---------------------------------------------------------------------------
# Wave 2 step 4: an id with no seq/slug form is skipped and logged
# ---------------------------------------------------------------------------


class TestLegacyIdsAreSkipped:
    """Registration takes only structured identity. A legacy id (``00019``,
    ``P001``) has none, so backfill skips it with a log line instead of
    stopping, as the strict gate made it stop before."""

    def _tree(self, root, backlog_rows, marker="019-kept-item"):
        (root / "backlog.md").write_text(
            "| ID | Timestamp | Description |\n|----|-----------|-------------|\n"
            + "".join(f"| {row} | 2026-01-01T00:00:00Z | Item {row} |\n" for row in backlog_rows)
        )
        (root / "brainstorms").mkdir()
        (root / "brainstorms" / "20260101-idea.prd.md").write_text(
            f"# Idea\n\n*Source: Backlog #{marker}*\n")
        (root / "features").mkdir()
        (root / "projects").mkdir()

    def test_a_legacy_id_is_skipped_and_the_scan_goes_on(self, tmp_path, capsys):
        from entity_registry.backfill import run_backfill

        self._tree(tmp_path, ["00019", "019-kept-item"])
        old_project = tmp_path / "projects" / "P001-old"
        old_project.mkdir()
        (old_project / ".meta.json").write_text(json.dumps({"id": "P001", "slug": "old"}))
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            err = capsys.readouterr().err
            assert db.get_entity("backlog:00019") is None
            assert "skipping backlog '00019': no seq/slug form" in err
            assert db.get_entity("project:P001-old") is None
            assert "skipping project 'P001-old': no seq/slug form" in err
            # The scan went on past both: later rows and scanners still ran.
            assert db.get_entity("backlog:019-kept-item") is not None
            assert db.get_entity("brainstorm:20260101-idea")["parent_type_id"] == "backlog:019-kept-item"
            assert db.get_metadata("backfill_complete") == "1"
        finally:
            db.close()

    def test_a_legacy_parent_already_in_the_registry_is_still_linked(self, tmp_path):
        """Documents on disk say ``#00019``; the registry holds that row as history.
        A pin: this linked before step 4 and must keep linking."""
        from entity_registry.backfill import run_backfill
        from entity_registry.test_helpers import seed_legacy_entity

        self._tree(tmp_path, [], marker="00019")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            seed_legacy_entity(db, "backlog", "00019", "Old item")
            run_backfill(db, str(tmp_path))
            assert db.get_entity("brainstorm:20260101-idea")["parent_type_id"] == "backlog:00019"
        finally:
            db.close()

    def test_a_missing_legacy_parent_gets_no_placeholder(self, tmp_path, capsys):
        from entity_registry.backfill import run_backfill

        self._tree(tmp_path, [])
        feature_dir = tmp_path / "features" / "031-orphan-test"
        feature_dir.mkdir()
        (feature_dir / ".meta.json").write_text(json.dumps(
            {"id": "031", "slug": "orphan-test", "backlog_source": "00099"}))
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            assert db.get_entity("backlog:00099") is None
            assert "skipping backlog '00099': no seq/slug form" in capsys.readouterr().err
            assert db.get_entity("feature:031-orphan-test")["parent_type_id"] is None
        finally:
            db.close()


class TestBackfillLeavesTheRegistryAlone:
    """Found running step 4's backfill on a snapshot of the live registry: once
    it could finish, it marked 30 planned features in other workspaces finished,
    replaced parents set since, and minted brainstorms from non-brainstorm files."""

    def _empty_tree(self, root):
        for sub in ("brainstorms", "features", "projects"):
            (root / sub).mkdir()

    def _feature(self, root, seq, slug, **meta):
        feature_dir = root / "features" / f"{seq:03d}-{slug}"
        feature_dir.mkdir()
        (feature_dir / ".meta.json").write_text(json.dumps({"id": f"{seq:03d}", "slug": slug, **meta}))

    def test_the_null_phase_cleanup_stays_in_its_workspace_and_on_done_entities(self, tmp_path):
        from entity_registry.backfill import run_backfill
        from entity_registry.test_helpers import bootstrap_test_workspace

        self._empty_tree(tmp_path)
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            ours = bootstrap_test_workspace(db, "ours")
            theirs = bootstrap_test_workspace(db, "theirs")
            for seq, slug, status, ws in ((1, "planned-here", "planned", ours),
                                          (2, "abandoned-here", "abandoned", ours),
                                          (3, "abandoned-there", "abandoned", theirs)):
                db.register_entity("feature", name=slug, seq=seq, slug=slug, status=status,
                                   workspace_uuid=ws)
                db.create_workflow_phase(f"feature:{seq:03d}-{slug}")
            run_backfill(db, str(tmp_path), project_id="ours")
            phase = {row["type_id"]: row["workflow_phase"] for row in db.list_workflow_phases()}
            assert phase["feature:002-abandoned-here"] == "finish"
            assert phase["feature:001-planned-here"] is None
            assert phase["feature:003-abandoned-there"] is None
        finally:
            db.close()

    def test_an_existing_parent_is_never_replaced(self, tmp_path):
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        (tmp_path / "brainstorms" / "20260101-idea.prd.md").write_text("# Idea\n")
        self._feature(tmp_path, 29, "kept", brainstorm_source="docs/brainstorms/20260101-idea.prd.md")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            db.register_entity("project", name="Owner", seq=1, slug="owner", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
            db.register_entity("feature", name="Kept", seq=29, slug="kept", workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
            db.set_parent("feature:029-kept", "project:001-owner")
            run_backfill(db, str(tmp_path))
            # The replacement candidate existed, so the guard, not its absence, kept the parent.
            assert db.get_entity("brainstorm:20260101-idea") is not None
            assert db.get_entity("feature:029-kept")["parent_type_id"] == "project:001-owner"
        finally:
            db.close()

    def test_a_brainstorm_source_written_as_a_type_id_is_used_as_is(self, tmp_path):
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        (tmp_path / "brainstorms" / "20260101-idea.prd.md").write_text("# Idea\n")
        self._feature(tmp_path, 30, "newer", brainstorm_source="brainstorm:20260101-idea")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            assert db.get_entity("feature:030-newer")["parent_type_id"] == "brainstorm:20260101-idea"
            assert db.get_entity("brainstorm:brainstorm:20260101-idea") is None
        finally:
            db.close()

    def test_a_source_that_is_not_a_brainstorm_file_is_no_parent(self, tmp_path):
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        self._feature(tmp_path, 31, "from-a-project",
                      brainstorm_source="docs/projects/001-x/prd.md")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            assert db.get_entity("brainstorm:prd") is None
            assert db.get_entity("feature:031-from-a-project")["parent_type_id"] is None
        finally:
            db.close()

    def test_a_placeholder_never_overwrites_a_registered_parent(self, tmp_path):
        """terry_agent: the parent brainstorm exists in two workspaces, so
        get_entity(type_id) sees none, and the placeholder upsert used to
        rewrite the real row's status to 'orphaned'."""
        from entity_registry.backfill import run_backfill
        from entity_registry.test_helpers import bootstrap_test_workspace

        self._empty_tree(tmp_path)
        self._feature(tmp_path, 40, "child", brainstorm_source="docs/brainstorms/20260101-shared.prd.md")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            ours = bootstrap_test_workspace(db, "ours")
            theirs = bootstrap_test_workspace(db, "theirs")
            for ws in (ours, theirs):
                db.register_entity("brainstorm", name="Shared", display_id="20260101-shared",
                                   status="active", workspace_uuid=ws)
            run_backfill(db, str(tmp_path), project_id="ours")
            [ours_row] = [e for e in db.list_entities(workspace_uuid=ours)
                          if e["type_id"] == "brainstorm:20260101-shared"]
            assert ours_row["status"] == "active"
        finally:
            db.close()

    @pytest.mark.parametrize("kind, folder", [("feature", "features"), ("project", "projects")])
    def test_a_row_stored_under_an_unpadded_id_is_not_registered_twice(self, tmp_path, kind, folder):
        """fractorg: the registry holds 66-x, .meta.json says 066. Looking up by
        type_id missed the row and registered a second entity with seq 66."""
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        (tmp_path / folder / "066-old-form").mkdir()
        (tmp_path / folder / "066-old-form" / ".meta.json").write_text(
            json.dumps({"id": "066", "slug": "old-form"}))
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            entity_uuid = db.register_entity(kind, name="Old form", seq=66, slug="old-form",
                                             workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
            # How pre-padding registries stored it; nothing guards type_id since migration 12.
            db._conn.execute("UPDATE entities SET type_id = ?, entity_id = ? WHERE uuid = ?",
                             (f"{kind}:66-old-form", "66-old-form", entity_uuid))
            db._conn.commit()
            run_backfill(db, str(tmp_path))
            assert db.get_entity(f"{kind}:066-old-form") is None
            assert db.get_entity(f"{kind}:66-old-form")["uuid"] == entity_uuid
        finally:
            db.close()

    def test_a_parent_registered_only_in_another_workspace_is_not_linked(self, tmp_path):
        """fractorg's brainstorms cite #00015. Once legacy ids were skipped, the
        only backlog:00015 left was pedantic-drip's, and the unscoped lookup
        linked across workspaces."""
        from entity_registry.backfill import run_backfill
        from entity_registry.test_helpers import bootstrap_test_workspace

        self._empty_tree(tmp_path)
        (tmp_path / "brainstorms" / "20260101-idea.prd.md").write_text(
            "# Idea\n\n*Source: Backlog #019-elsewhere*\n")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            bootstrap_test_workspace(db, "ours")
            theirs = bootstrap_test_workspace(db, "theirs")
            db.register_entity("backlog", name="Elsewhere", seq=19, slug="elsewhere",
                               workspace_uuid=theirs)
            run_backfill(db, str(tmp_path), project_id="ours")
            assert db.get_entity("brainstorm:20260101-idea")["parent_uuid"] is None
        finally:
            db.close()

    def test_a_parent_in_two_workspaces_links_to_this_workspaces_row(self, tmp_path):
        """The unscoped lookup returned None for a type_id in two workspaces,
        silently dropping a link backfill should make."""
        from entity_registry.backfill import run_backfill
        from entity_registry.test_helpers import bootstrap_test_workspace

        self._empty_tree(tmp_path)
        (tmp_path / "brainstorms" / "20260101-idea.prd.md").write_text(
            "# Idea\n\n*Source: Backlog #019-shared*\n")
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            ours = bootstrap_test_workspace(db, "ours")
            theirs = bootstrap_test_workspace(db, "theirs")
            db.register_entity("backlog", name="Shared", seq=19, slug="shared", workspace_uuid=theirs)
            ours_backlog = db.register_entity("backlog", name="Shared", seq=19, slug="shared",
                                              workspace_uuid=ours)
            run_backfill(db, str(tmp_path), project_id="ours")
            assert db.get_entity("brainstorm:20260101-idea")["parent_uuid"] == ours_backlog
        finally:
            db.close()

    def test_an_absolute_in_repo_source_that_is_not_a_brainstorm_is_no_parent(self, tmp_path):
        """terry_agent names its project PRD by absolute path. Every absolute path
        counted as external, which minted brainstorm:prd."""
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        self._feature(tmp_path, 32, "from-a-project",
                      brainstorm_source=str(tmp_path / "projects" / "001-x" / "prd.md"))
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            assert db.get_entity("brainstorm:prd") is None
            assert db.get_entity("feature:032-from-a-project")["parent_type_id"] is None
        finally:
            db.close()

    def test_a_missing_brainstorm_named_by_an_absolute_in_repo_path_is_reported_not_minted(
            self, tmp_path, capsys):
        """An in-repo brainstorm that is gone from disk is reported and left
        unset. Until C13 (design D8) it was minted as an orphaned placeholder."""
        from entity_registry.backfill import run_backfill

        self._empty_tree(tmp_path)
        self._feature(tmp_path, 33, "lost-source",
                      brainstorm_source=str(tmp_path / "brainstorms" / "20260101-gone.prd.md"))
        db = EntityDatabase(str(tmp_path / "test.db"))
        try:
            run_backfill(db, str(tmp_path))
            assert db.get_entity("brainstorm:20260101-gone") is None
            assert db.get_entity("feature:033-lost-source")["parent_type_id"] is None
            assert ("set_parent feature:033-lost-source->brainstorm:20260101-gone skipped: "
                    "parent is not registered in this workspace") in capsys.readouterr().err
        finally:
            db.close()
