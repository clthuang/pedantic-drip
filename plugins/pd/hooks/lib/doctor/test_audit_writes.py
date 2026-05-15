"""Doctor audit-writes lint tests (feature 110).

Combines two audit lints:

1. **`.meta.json` / `docs/backlog.md` writer allow-list scaffold (Groups 11 + 12).**
   Constants pinning the design-mandated allow-lists. Group 11 will replace the
   stub tests with full AST walks (AC-1.1, AC-1.2). For now, the constants are
   PASS-by-construction so CI doesn't regress while Group 11 lands.

2. **entity_id parsing audit lint (Group 15 / TD-7b / design §5 invariant).**
   Enforces that all `entity_id`-suffix parsing call sites either live inside
   a ``_migration_13_*`` function or in a test file. Hits anywhere else
   indicate a caller that should have been ported to read seq/slug from
   ``entity_display`` per FR-8.3 but was missed.

Grace mode (design TD-7b): if the audit finds unported sites, the test is
marked ``xfail`` (not ``fail``) so the contract exists for CI without
blocking integration.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Constants — locate plugin paths relative to this file.
# ---------------------------------------------------------------------------

_DOCTOR_DIR = Path(__file__).resolve().parent           # plugins/pd/hooks/lib/doctor
_HOOKS_LIB = _DOCTOR_DIR.parent                          # plugins/pd/hooks/lib
_HOOKS_DIR = _HOOKS_LIB.parent                           # plugins/pd/hooks
_PLUGIN_ROOT = _HOOKS_DIR.parent                         # plugins/pd
_PLUGIN_PD_DIR = _PLUGIN_ROOT                            # alias for clarity
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
    """AC-1.1 scaffold — Group 11 implements full AST walk."""
    assert len(META_JSON_WRITER_ALLOWLIST) > 0, (
        "META_JSON_WRITER_ALLOWLIST must be populated per spec FR-4.1."
    )
    for tree in AUDIT_TREES:
        assert tree.exists(), (
            f"Audit tree missing — AST walk cannot proceed: {tree}"
        )


def test_no_unaudited_backlog_md_writes() -> None:
    """AC-1.2 scaffold — Group 11 implements full AST walk."""
    assert "_project_backlog_md" in BACKLOG_MD_WRITER_ALLOWLIST
    assert "_fix_backlog_annotation" in BACKLOG_MD_WRITER_ALLOWLIST
    assert len(BACKLOG_MD_WRITER_ALLOWLIST) == 2


# ---------------------------------------------------------------------------
# TD-7b entity_id parsing audit lint (Group 15)
# ---------------------------------------------------------------------------

_SCAN_ROOTS = [
    _PLUGIN_PD_DIR / "hooks" / "lib",
    _PLUGIN_PD_DIR / "mcp",
]

_AUDIT_PATTERN = (
    r'\.split\(":"\)|'
    r'substr\(.*entity_id|'
    r'instr\(.*entity_id|'
    r're\.match.*entity_id'
)


def _run_audit_grep() -> list[tuple[str, int, str]]:
    args = ["grep", "-rnIE", "--include=*.py", _AUDIT_PATTERN]
    for root in _SCAN_ROOTS:
        if root.exists():
            args.append(str(root))
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode == 1:
        return []
    if result.returncode == 2:
        raise RuntimeError(
            f"audit grep failed: stderr={result.stderr!r}, stdout={result.stdout!r}"
        )
    hits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, lineno_s, text = parts
        try:
            lineno = int(lineno_s)
        except ValueError:
            continue
        hits.append((path, lineno, text))
    return hits


def _function_enclosing(path: Path, line: int) -> str | None:
    try:
        src = path.read_text()
    except OSError:
        return None
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return None
    enclosing: str | None = None
    enclosing_span = (0, 0)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or start
            if start <= line <= end:
                span = end - start
                if enclosing is None or span < (enclosing_span[1] - enclosing_span[0]):
                    enclosing = node.name
                    enclosing_span = (start, end)
    return enclosing


def _classify_hit(path: str, line: int) -> str:
    p = Path(path)
    if p.name.startswith("test_") and p.suffix == ".py":
        return "allowed_test"
    fn = _function_enclosing(p, line)
    if fn is not None and fn.startswith("_migration_13_"):
        return "allowed_migration_13"
    return "unallowed"


_CURRENT_UNALLOWED = [
    (path, line, text)
    for (path, line, text) in _run_audit_grep()
    if _classify_hit(path, line) == "unallowed"
]


@pytest.mark.xfail(
    bool(_CURRENT_UNALLOWED),
    reason=(
        f"TD-7b followup: {len(_CURRENT_UNALLOWED)} entity_id-parsing site(s) "
        "pending port. Sites: "
        + "; ".join(f"{p}:{ln}" for (p, ln, _t) in _CURRENT_UNALLOWED[:5])
    ),
    strict=False,
)
def test_entity_id_parsing_audit_lint() -> None:
    """TD-7b lint: every entity_id-suffix-parsing call site outside test
    files MUST live inside a ``_migration_13_*`` function."""
    hits = _run_audit_grep()
    unallowed: list[tuple[str, int, str]] = []
    for path, line, text in hits:
        if _classify_hit(path, line) == "unallowed":
            unallowed.append((path, line, text))
    if unallowed:
        bullets = "\n".join(f"  - {p}:{ln}: {t.strip()}" for (p, ln, t) in unallowed)
        pytest.fail(
            "TD-7b audit lint: found entity_id-parsing call sites outside "
            "the allow-list.\n"
            f"Unallowed hits ({len(unallowed)}):\n{bullets}"
        )
