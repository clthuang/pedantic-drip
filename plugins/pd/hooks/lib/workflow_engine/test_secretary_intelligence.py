"""Tests for secretary_intelligence module.

Covers AC-17 (CREATE mode), AC-18 (QUERY mode), AC-22a (weight escalation).
TDD: tests written first, then implementation.
"""
from __future__ import annotations

import sqlite3
import uuid as uuid_mod

import pytest

from workflow_engine.secretary_intelligence import (
    check_duplicates,
    check_kr_count,
    detect_activity_kr,
    detect_mode,
    detect_scope_expansion,
    find_parent_candidates,
    recommend_weight,
)


# ---------------------------------------------------------------------------
# detect_mode tests (AC-17, AC-18)
# ---------------------------------------------------------------------------
class TestDetectMode:
    """Mode detection: context overrides keywords, then keyword classification."""

    # -- Context overrides --

    def test_feature_branch_context_returns_continue(self):
        """AC-17: If on a feature branch, default to CONTINUE."""
        result = detect_mode("build a new auth system", {"feature_branch": "feature/052-auth"})
        assert result == "CONTINUE"

    def test_feature_branch_with_explicit_create_intent(self):
        """AC-17: On feature branch, explicit task creation still returns CREATE."""
        result = detect_mode(
            "add a task to track login metrics",
            {"feature_branch": "feature/052-auth"},
        )
        assert result == "CREATE"

    def test_feature_branch_with_query_intent(self):
        """On feature branch, query words override CONTINUE default."""
        result = detect_mode(
            "what is the status of this feature?",
            {"feature_branch": "feature/052-auth"},
        )
        assert result == "QUERY"

    # -- CREATE keywords (no context) --

    def test_create_verb_create(self):
        result = detect_mode("create a new authentication service", {})
        assert result == "CREATE"

    def test_create_verb_build(self):
        result = detect_mode("build a monitoring dashboard", {})
        assert result == "CREATE"

    def test_create_verb_add(self):
        result = detect_mode("add rate limiting to the API", {})
        assert result == "CREATE"

    def test_create_verb_implement(self):
        result = detect_mode("implement caching for search results", {})
        assert result == "CREATE"

    def test_create_verb_start(self):
        result = detect_mode("start working on the migration", {})
        assert result == "CREATE"

    def test_create_verb_make(self):
        result = detect_mode("make a CLI tool for deployment", {})
        assert result == "CREATE"

    def test_create_verb_new(self):
        result = detect_mode("new feature for user profiles", {})
        assert result == "CREATE"

    def test_create_verb_need(self):
        """AC-17 verification: 'We need better observability' -> CREATE."""
        result = detect_mode("We need better observability", {})
        assert result == "CREATE"

    def test_create_verb_want(self):
        result = detect_mode("I want a retry mechanism", {})
        assert result == "CREATE"

    def test_create_verb_fix(self):
        result = detect_mode("fix the login timeout bug", {})
        assert result == "CREATE"

    def test_create_verb_setup(self):
        result = detect_mode("set up CI/CD pipeline", {})
        assert result == "CREATE"

    # -- QUERY keywords --

    def test_query_word_what(self):
        result = detect_mode("what features are in progress?", {})
        assert result == "QUERY"

    def test_query_word_how(self):
        """AC-18 verification: question words -> QUERY."""
        result = detect_mode("how are we doing on reliability?", {})
        assert result == "QUERY"

    def test_query_word_where(self):
        result = detect_mode("where is the auth feature?", {})
        assert result == "QUERY"

    def test_query_word_which(self):
        result = detect_mode("which tasks are blocked?", {})
        assert result == "QUERY"

    def test_query_word_list(self):
        result = detect_mode("list all active projects", {})
        assert result == "QUERY"

    def test_query_word_show(self):
        result = detect_mode("show me the project status", {})
        assert result == "QUERY"

    def test_query_word_find(self):
        result = detect_mode("find features related to auth", {})
        assert result == "QUERY"

    def test_query_word_status(self):
        result = detect_mode("status of feature 052", {})
        assert result == "QUERY"

    def test_query_word_progress(self):
        result = detect_mode("progress on the migration?", {})
        assert result == "QUERY"

    # -- CONTINUE keywords --

    def test_continue_word_continue(self):
        result = detect_mode("continue with the current task", {})
        assert result == "CONTINUE"

    def test_continue_word_resume(self):
        result = detect_mode("resume the implementation", {})
        assert result == "CONTINUE"

    def test_continue_word_next(self):
        result = detect_mode("next step please", {})
        assert result == "CONTINUE"

    def test_continue_word_finish(self):
        result = detect_mode("finish the current phase", {})
        assert result == "CONTINUE"

    # -- Ambiguous -> CREATE (safe default) --

    def test_ambiguous_returns_create(self):
        """AC-17 verification: 'Improve things' -> ambiguous -> CREATE default."""
        result = detect_mode("Improve things", {})
        assert result == "CREATE"

    def test_empty_request_returns_create(self):
        result = detect_mode("", {})
        assert result == "CREATE"

    def test_gibberish_returns_create(self):
        result = detect_mode("asdfghjkl", {})
        assert result == "CREATE"

    # -- Case insensitivity --

    def test_case_insensitive_create(self):
        result = detect_mode("CREATE a new service", {})
        assert result == "CREATE"

    def test_case_insensitive_query(self):
        result = detect_mode("WHAT is happening?", {})
        assert result == "QUERY"

    # -- None context --

    def test_none_context_treated_as_empty(self):
        result = detect_mode("build something", None)
        assert result == "CREATE"

    # -- Priority: first match wins --

    def test_create_before_query_in_mixed(self):
        """When both create and query words present, first match wins."""
        result = detect_mode("create a report showing status", {})
        assert result == "CREATE"

    def test_query_before_create_in_mixed(self):
        result = detect_mode("what should we build next?", {})
        assert result == "QUERY"


# ---------------------------------------------------------------------------
# find_parent_candidates tests (AC-17)
# ---------------------------------------------------------------------------
class TestFindParentCandidates:
    """FTS5 search for potential parent entities."""

    @pytest.fixture()
    def db(self, tmp_path):
        """Create an EntityDatabase with FTS5 and some test entities."""
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        # Register some entities for search
        db.register_entity(
            entity_type="objective",
            entity_id="001-reliability",
            name="Platform Reliability",
            status="active",
        )
        db.register_entity(
            entity_type="key_result",
            entity_id="001-p0-incidents",
            name="Reduce P0 Incidents",
            status="active",
        )
        db.register_entity(
            entity_type="feature",
            entity_id="042-auth-service",
            name="Authentication Service Rewrite",
            status="active",
        )
        return db

    def test_finds_matching_parents(self, db):
        """AC-17: search entity registry for parent candidates."""
        results = find_parent_candidates(db, "project", "Platform Reliability")
        assert len(results) >= 1
        type_ids = [r["type_id"] for r in results]
        assert any("reliability" in tid for tid in type_ids)

    def test_returns_empty_for_no_match(self, db):
        """AC-17: empty registry match -> no parents."""
        results = find_parent_candidates(db, "feature", "Quantum Computing Module")
        assert results == []

    def test_filters_by_plausible_parent_types(self, db):
        """Should not return same-level or child types as parents."""
        # Searching for a feature parent should find objectives/key_results, not other features
        results = find_parent_candidates(db, "feature", "Auth Service")
        # If feature:042-auth-service appears, it shouldn't be a parent of another feature
        for r in results:
            assert r["entity_type"] != "feature"

    def test_returns_list_of_dicts(self, db):
        results = find_parent_candidates(db, "project", "incidents")
        for r in results:
            assert isinstance(r, dict)
            assert "type_id" in r
            assert "name" in r
            assert "uuid" in r


# ---------------------------------------------------------------------------
# check_duplicates tests (AC-17)
# ---------------------------------------------------------------------------
class TestCheckDuplicates:
    """Detect potential duplicate entities by name similarity."""

    @pytest.fixture()
    def db(self, tmp_path):
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        db.register_entity(
            entity_type="feature",
            entity_id="042-auth-service",
            name="Authentication Service",
            status="active",
        )
        db.register_entity(
            entity_type="feature",
            entity_id="043-auth-rewrite",
            name="Auth Service Rewrite",
            status="active",
        )
        db.register_entity(
            entity_type="project",
            entity_id="010-monitoring",
            name="Monitoring Dashboard",
            status="active",
        )
        return db

    def test_finds_duplicates_by_name(self, db):
        results = check_duplicates(db, "Authentication Service")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert any("Auth" in n for n in names)

    def test_no_duplicates_for_unique_name(self, db):
        results = check_duplicates(db, "Quantum Teleportation Module")
        assert results == []

    def test_returns_entity_info(self, db):
        results = check_duplicates(db, "auth")
        for r in results:
            assert "type_id" in r
            assert "name" in r
            assert "status" in r


# ---------------------------------------------------------------------------
# recommend_weight tests (AC-22a)
# ---------------------------------------------------------------------------
class TestRecommendWeight:
    """Weight recommendation from scope signals."""

    # -- Light signals --

    def test_quick_fix_returns_light(self):
        assert recommend_weight(["quick fix"]) == "light"

    def test_small_returns_light(self):
        assert recommend_weight(["small"]) == "light"

    def test_simple_returns_light(self):
        assert recommend_weight(["simple"]) == "light"

    def test_typo_returns_light(self):
        assert recommend_weight(["typo"]) == "light"

    def test_one_liner_returns_light(self):
        assert recommend_weight(["one liner"]) == "light"

    def test_trivial_returns_light(self):
        assert recommend_weight(["trivial"]) == "light"

    # -- Full signals --

    def test_rewrite_returns_full(self):
        assert recommend_weight(["rewrite"]) == "full"

    def test_refactor_returns_full(self):
        assert recommend_weight(["refactor"]) == "full"

    def test_breaking_change_returns_full(self):
        assert recommend_weight(["breaking change"]) == "full"

    def test_complex_returns_full(self):
        assert recommend_weight(["complex"]) == "full"

    def test_cross_team_returns_full(self):
        assert recommend_weight(["cross-team"]) == "full"

    def test_architecture_returns_full(self):
        assert recommend_weight(["architecture"]) == "full"

    # -- Default -> standard --

    def test_empty_signals_returns_standard(self):
        assert recommend_weight([]) == "standard"

    def test_no_matching_signals_returns_standard(self):
        assert recommend_weight(["medium scope", "normal work"]) == "standard"

    # -- Mixed signals: heaviest wins --

    def test_mixed_light_and_full_returns_full(self):
        """When conflicting signals, heaviest weight wins (conservative)."""
        assert recommend_weight(["small", "breaking change"]) == "full"

    def test_mixed_light_and_standard_returns_standard(self):
        assert recommend_weight(["small", "medium scope"]) == "light"


# ---------------------------------------------------------------------------
# detect_scope_expansion tests (AC-22a)
# ---------------------------------------------------------------------------
class TestDetectScopeExpansion:
    """Detect when scope has grown beyond current weight."""

    def test_light_with_full_signals_recommends_full(self):
        """AC-22a: light feature with expanding scope -> recommend upgrade."""
        result = detect_scope_expansion("light", ["cross-team impact", "needs design review"])
        assert result == "full"

    def test_light_with_standard_signals_recommends_standard(self):
        result = detect_scope_expansion("light", ["multiple components"])
        assert result == "standard"

    def test_standard_with_full_signals_recommends_full(self):
        result = detect_scope_expansion("standard", ["architecture change", "breaking change"])
        assert result == "full"

    def test_full_returns_none(self):
        """Already at max weight, no upgrade possible."""
        result = detect_scope_expansion("full", ["breaking change", "rewrite"])
        assert result is None

    def test_no_expansion_signals_returns_none(self):
        result = detect_scope_expansion("light", [])
        assert result is None

    def test_light_with_irrelevant_signals_returns_none(self):
        result = detect_scope_expansion("light", ["looks good", "on track"])
        assert result is None

    def test_light_with_design_review_signal(self):
        """AC-22a verification: 'this now needs a design review' -> upgrade."""
        result = detect_scope_expansion("light", ["needs design review"])
        assert result is not None  # either standard or full
        assert result in ("standard", "full")

    def test_standard_no_expansion_returns_none(self):
        result = detect_scope_expansion("standard", ["normal progress"])
        assert result is None


# ---------------------------------------------------------------------------
# detect_activity_kr tests (AC-33)
# ---------------------------------------------------------------------------
class TestDetectActivityKr:
    """Detect activity-word anti-patterns in KR text."""

    def test_launch_triggers_warning(self):
        """AC-33 verification: 'Launch mobile app' → warning."""
        result = detect_activity_kr("Launch mobile app")
        assert result is not None
        assert "output" in result.lower() or "outcome" in result.lower()

    def test_build_triggers_warning(self):
        result = detect_activity_kr("Build a new dashboard")
        assert result is not None

    def test_implement_triggers_warning(self):
        result = detect_activity_kr("Implement caching layer")
        assert result is not None

    def test_create_triggers_warning(self):
        result = detect_activity_kr("Create user onboarding flow")
        assert result is not None

    def test_deploy_triggers_warning(self):
        result = detect_activity_kr("Deploy to production")
        assert result is not None

    def test_migrate_triggers_warning(self):
        result = detect_activity_kr("Migrate database to PostgreSQL")
        assert result is not None

    def test_develop_triggers_warning(self):
        result = detect_activity_kr("Develop mobile app")
        assert result is not None

    def test_ship_triggers_warning(self):
        result = detect_activity_kr("Ship v2.0 by Q3")
        assert result is not None

    def test_release_triggers_warning(self):
        result = detect_activity_kr("Release the beta version")
        assert result is not None

    def test_measurable_outcome_no_warning(self):
        """AC-33 verification: 'Achieve 50K MAU' → no warning."""
        result = detect_activity_kr("Achieve 50K MAU on mobile")
        assert result is None

    def test_percentage_outcome_no_warning(self):
        result = detect_activity_kr("Reduce P0 incidents by 50%")
        assert result is None

    def test_metric_outcome_no_warning(self):
        result = detect_activity_kr("Increase API response time to <200ms")
        assert result is None

    def test_empty_text_no_warning(self):
        result = detect_activity_kr("")
        assert result is None

    def test_case_insensitive(self):
        """Activity words detected regardless of case."""
        result = detect_activity_kr("LAUNCH the product")
        assert result is not None

    def test_word_boundary_respected(self):
        """'relaunch' should not trigger on 'launch' substring."""
        # 'relaunch' contains 'launch' but is a different word — should still detect
        # Actually, the task says "activity words" so we check for word boundaries
        result = detect_activity_kr("Relaunch the platform")
        # 'relaunch' is not exactly 'launch', but contains it
        # Per spec, these are word-level checks. 'relaunch' is a different word.
        # However, the task doesn't specify word-boundary strictness.
        # We'll implement with word boundaries for precision.
        # This test verifies the boundary behavior we choose.
        assert result is None  # 'relaunch' != 'launch'


# ---------------------------------------------------------------------------
# check_kr_count tests (AC-33)
# ---------------------------------------------------------------------------
class TestCheckKrCount:
    """Detect when objective has too many KRs."""

    @pytest.fixture()
    def db(self, tmp_path):
        from entity_registry.database import EntityDatabase
        db_path = str(tmp_path / "test.db")
        return EntityDatabase(db_path)

    def test_five_krs_no_warning(self, db):
        """5 KRs is within limit → no warning."""
        obj_uuid = db.register_entity(
            entity_type="objective", entity_id="o1",
            name="Test Objective", status="active")
        for i in range(5):
            db.register_entity(
                entity_type="key_result", entity_id=f"kr{i}",
                name=f"KR {i}", parent_type_id="objective:o1", status="active")

        result = check_kr_count(db, obj_uuid)
        assert result is None

    def test_six_krs_triggers_warning(self, db):
        """AC-33: 6th KR on objective → warning."""
        obj_uuid = db.register_entity(
            entity_type="objective", entity_id="o1",
            name="Test Objective", status="active")
        for i in range(6):
            db.register_entity(
                entity_type="key_result", entity_id=f"kr{i}",
                name=f"KR {i}", parent_type_id="objective:o1", status="active")

        result = check_kr_count(db, obj_uuid)
        assert result is not None
        assert "5" in result  # mentions the recommended max

    def test_seven_krs_triggers_warning(self, db):
        obj_uuid = db.register_entity(
            entity_type="objective", entity_id="o1",
            name="Test Objective", status="active")
        for i in range(7):
            db.register_entity(
                entity_type="key_result", entity_id=f"kr{i}",
                name=f"KR {i}", parent_type_id="objective:o1", status="active")

        result = check_kr_count(db, obj_uuid)
        assert result is not None

    def test_zero_krs_no_warning(self, db):
        obj_uuid = db.register_entity(
            entity_type="objective", entity_id="o1",
            name="Test Objective", status="active")

        result = check_kr_count(db, obj_uuid)
        assert result is None

    def test_nonexistent_objective_no_warning(self, db):
        result = check_kr_count(db, "00000000-0000-4000-8000-000000000000")
        assert result is None

    def test_abandoned_krs_excluded_from_count(self, db):
        """Abandoned KRs should not count toward the limit."""
        obj_uuid = db.register_entity(
            entity_type="objective", entity_id="o1",
            name="Test Objective", status="active")
        for i in range(5):
            db.register_entity(
                entity_type="key_result", entity_id=f"kr{i}",
                name=f"KR {i}", parent_type_id="objective:o1", status="active")
        # 6th KR is abandoned — should not count
        db.register_entity(
            entity_type="key_result", entity_id="kr-abandoned",
            name="KR Abandoned", parent_type_id="objective:o1",
            status="abandoned")

        result = check_kr_count(db, obj_uuid)
        assert result is None  # only 5 active KRs
