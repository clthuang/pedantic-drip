"""Regression tests surviving Feature 129's cross-workspace-allowlist deletion.

Feature 129 deleted ``_fix_triage_cross_workspace_link`` (the grandfather /
re-attribute-parent / re-attribute-child / delete-relation fixer for
cross-workspace ``parent_uuid`` links) along with its FR-9 adversarial
fix_hint validator (``_normalize_and_validate_fix_hint`` /
``_parse_triage_choice``) and this module's 4-decision triage coverage — the
fixer was orphaned (never registered in ``fixer.py``'s ``_SAFE_PATTERNS``)
and the cross-workspace allowlist mechanism it triaged no longer exists.

Feature 133 retired the module's other coverage area (the Task #7 workspace
split-brain fix-action tests) along with the two doctor checks whose
fix_hints they served (the workspace-identity split-brain detector and the
unknown-workspace orphan claimer).

The sole remaining coverage area:

- ``test_canonical_trigger_sql_matches_production_source``: F117 TA.4 / R-1
  drift guard pinning ``_CANONICAL_TRIGGER_SQL`` against the
  ``enforce_immutable_workspace_uuid`` trigger body in
  ``entity_registry/database.py``.
"""
from __future__ import annotations


# F117 TA.1: canonical CREATE TRIGGER SQL for enforce_immutable_workspace_uuid.
# MUST be byte-identical to plugins/pd/hooks/lib/entity_registry/database.py
# lines 2042-2046 inside _migration_11_workspace_identity. The em-dash below
# is U+2014 (HORIZONTAL EM-DASH) — load-bearing per F117 design R-1.
# Drift detector: see test_canonical_trigger_sql_matches_production_source.
_CANONICAL_TRIGGER_SQL = """
            CREATE TRIGGER enforce_immutable_workspace_uuid
            BEFORE UPDATE OF workspace_uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'workspace_uuid is immutable — use re-attribution API'); END
        """


def test_canonical_trigger_sql_matches_production_source():
    """F117 TA.4 / R-1 mitigation: detect drift between _CANONICAL_TRIGGER_SQL
    in this test module and the source-of-truth in entity_registry/database.py
    (_migration_11_workspace_identity, lines ~2042-2046). Substring scan +
    whitespace normalization tolerates indentation drift but catches body changes.
    """
    import re
    from pathlib import Path

    db_source_path = (
        Path(__file__).parent.parent / "entity_registry" / "database.py"
    )
    db_source = db_source_path.read_text(encoding="utf-8")

    pattern = re.compile(
        r"CREATE TRIGGER enforce_immutable_workspace_uuid\s+"
        r"BEFORE UPDATE OF workspace_uuid ON entities\s+"
        r"BEGIN SELECT RAISE\(ABORT,\s*"
        r"'workspace_uuid is immutable — use re-attribution API'\s*"
        r"\); END",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(db_source)
    assert match is not None, (
        "Migration-11 CREATE TRIGGER enforce_immutable_workspace_uuid not "
        f"found in {db_source_path} — has the canonical source moved?"
    )

    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    assert _normalize(match.group(0)) == _normalize(_CANONICAL_TRIGGER_SQL), (
        "Canonical trigger SQL in test_fix_actions.py drifted from production "
        "source at database.py. Re-sync _CANONICAL_TRIGGER_SQL to match the "
        "CREATE TRIGGER block in _migration_11_workspace_identity."
    )
