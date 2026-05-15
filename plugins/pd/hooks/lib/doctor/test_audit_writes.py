"""Feature 110 AST audit scaffold (AC-1.1, AC-1.2).

Walks the source trees enumerated in spec FR-4.1 + design §2.3 to
assert that ``.meta.json`` and ``docs/backlog.md`` writes are confined
to the allow-listed projection / annotation surfaces.

This file is a **scaffold** added by Group 12 (feature 110); Group 11
(next dispatch) implements the full AST walk + comment-proximity
checks per AC-1.1b. The scaffold's purpose is to:
  1. Reserve the module path used by `docs/features/110-.../spec.md`
     §8 verification mapping (test file = `test_audit_writes.py`).
  2. Lock in the allow-list values so future regressions surface
     during code review even before Group 11 lands.
  3. Guarantee CI passes during Group 12 (no false-positive failures
     from a missing test module).

The stub assertions are PASS-by-construction (they verify the
allow-list constants exist and are non-empty). Group 11 replaces them
with real AST walks. Per Task 12.5 DoD: "stub assertions return PASS
(so Group 12 doesn't break CI)".
"""
from __future__ import annotations

from pathlib import Path

# Repo-relative anchors used by future AST walks. Stored as module-level
# constants so Group 11 can reuse them without re-deriving paths.
_DOCTOR_DIR = Path(__file__).resolve().parent           # plugins/pd/hooks/lib/doctor
_HOOKS_LIB = _DOCTOR_DIR.parent                          # plugins/pd/hooks/lib
_HOOKS_DIR = _HOOKS_LIB.parent                           # plugins/pd/hooks
_PLUGIN_ROOT = _HOOKS_DIR.parent                         # plugins/pd
_REPO_ROOT = _PLUGIN_ROOT.parent.parent                  # repo root


# Allow-list for `.meta.json` writes per spec FR-4.1 + design TD-11.
META_JSON_WRITER_ALLOWLIST: tuple[str, ...] = (
    "_project_meta_json",          # MCP projection (canonical write path)
    "_write_meta_json_fallback",   # degraded-mode writer (engine.py)
    "init_project_state",          # project-type writer (deferred to feature 111)
    # Doctor fix actions per design §2.3 (replaced with MCP-routing wrappers
    # in Group 11, but the wrapper names are retained for the AST walk).
    "_fix_last_completed_phase",
    "_fix_completed_timestamp",
)


# Allow-list for `docs/backlog.md` writes per spec FR-4.3.
BACKLOG_MD_WRITER_ALLOWLIST: tuple[str, ...] = (
    "_project_backlog_md",     # MCP projection (canonical write path)
    "_fix_backlog_annotation", # annotation-only (F4-AUDIT) doctor fix
)


# Source trees the AST walk inspects (spec AC-1.1 enumerates these).
AUDIT_TREES: tuple[Path, ...] = (
    _HOOKS_LIB / "workflow_engine",
    _PLUGIN_ROOT / "mcp",
    _HOOKS_LIB / "doctor",
)


# ---------------------------------------------------------------------------
# Stub tests (Group 12 scaffold — Group 11 replaces with full AST walks)
# ---------------------------------------------------------------------------


def test_no_unaudited_meta_json_writes() -> None:
    """AC-1.1 scaffold — Group 11 implements full AST walk.

    For Group 12, we just assert the allow-list is non-empty and the
    target source trees exist. This guarantees CI passes; the real
    walk lands in Group 11.
    """
    assert len(META_JSON_WRITER_ALLOWLIST) > 0, (
        "META_JSON_WRITER_ALLOWLIST must be populated per spec FR-4.1."
    )
    for tree in AUDIT_TREES:
        assert tree.exists(), (
            f"Audit tree missing — AST walk cannot proceed: {tree}"
        )


def test_no_unaudited_backlog_md_writes() -> None:
    """AC-1.2 scaffold — Group 11 implements full AST walk.

    Verifies the BACKLOG_MD_WRITER_ALLOWLIST exists and contains the
    two expected entries per spec FR-4.3:
      * ``_project_backlog_md`` (projection)
      * ``_fix_backlog_annotation`` (F4-AUDIT annotation-only)

    Group 12 (this dispatch) ports the three pre-port backlog writers
    (``add-to-backlog.md``, ``finish-feature.md`` Step 5b,
    ``cleanup_backlog.py``) to register-then-project. Post-port, no
    other write surface should remain. Group 11's AST walk will
    enforce this empirically.
    """
    assert "_project_backlog_md" in BACKLOG_MD_WRITER_ALLOWLIST, (
        "Spec FR-4.3 — projection must be on the allow-list."
    )
    assert "_fix_backlog_annotation" in BACKLOG_MD_WRITER_ALLOWLIST, (
        "Spec FR-4.3 — F4-AUDIT annotation writer retained per design §2.3."
    )
    # Sanity: no surprise entries beyond the two design-pinned writers.
    assert len(BACKLOG_MD_WRITER_ALLOWLIST) == 2, (
        f"Unexpected backlog allow-list size: "
        f"{BACKLOG_MD_WRITER_ALLOWLIST}. Spec FR-4.3 expects exactly two."
    )
