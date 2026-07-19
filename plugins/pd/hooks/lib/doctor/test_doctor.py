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
        "check_referential_integrity",
        "check_missed_cascade",
        "check_config_validity",
        "check_security_review_command",
        "check_stale_worktrees",
        "check_status_write_path",
        "check_no_free_text_status_parsers",
        "check_severity_vocab",
        "check_v2_cutover_window",
    ]
    actual_names = [c.__name__ for c in CHECK_ORDER]
    assert actual_names == expected_names, (
        f"CHECK_ORDER drift: expected {expected_names}, got {actual_names}"
    )
    # The v2 cutover-window check reads a marker FILE, not the DB, and must
    # run (silently) even on a DB-less workspace, so it is deliberately NOT
    # gated behind the entity-DB prerequisite set.
    assert "check_v2_cutover_window" not in _ENTITY_DB_CHECKS
