"""Tests for the top-level ``doctor`` package wiring (CHECK_ORDER, membership sets).

F116 TC.2 / FR-8: pins the post-extraction CHECK_ORDER sequence so that future
refactors don't silently reorder doctor checks.
"""
from __future__ import annotations


def test_check_order_preserved_post_f116():
    """F116 FR-8 / AC-2.1 / AC-8.2: ensure FR-8 extraction (TC.1) + FR-2
    new check (TA.6) don't disturb existing CHECK_ORDER ordering — only
    append at end."""
    from doctor import CHECK_ORDER, _ENTITY_DB_CHECKS
    expected_names = [
        "check_db_readiness",
        "check_feature_status",
        "check_workflow_phase",
        "check_brainstorm_status",
        "check_backlog_status",
        "check_branch_consistency",
        "check_entity_orphans",
        "check_referential_integrity",
        "check_stale_dependencies",
        "check_project_attribution",
        "check_config_validity",
        "check_security_review_command",
        "check_stale_worktrees",
        "check_status_write_path",
        "check_no_free_text_status_parsers",
        "check_cross_workspace_parent_uuid",
        "check_audit_counter_write_path",
        "check_audit_emit_failed_count",
        "check_severity_vocab",
        "check_workspace_uuid_consistency",
        "check_unknown_workspace_orphans",
    ]
    actual_names = [c.__name__ for c in CHECK_ORDER]
    assert actual_names == expected_names, (
        f"CHECK_ORDER drift: expected {expected_names}, got {actual_names}"
    )
    assert "check_cross_workspace_parent_uuid" in _ENTITY_DB_CHECKS
    assert "check_audit_emit_failed_count" in _ENTITY_DB_CHECKS
    # The workspace-consistency check self-guards a missing DB and its
    # fresh-checkout warning is meaningful without one, so it is deliberately
    # NOT gated behind the entity-DB prerequisite set.
    assert "check_workspace_uuid_consistency" not in _ENTITY_DB_CHECKS
    # The unknown-workspace orphan check also self-guards a missing/locked DB,
    # so it is likewise NOT gated behind the entity-DB prerequisite set.
    assert "check_unknown_workspace_orphans" not in _ENTITY_DB_CHECKS
