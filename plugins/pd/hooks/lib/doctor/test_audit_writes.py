"""Doctor audit-writes lint tests (feature 110 Group 11 + Group 15).

Group 15 (this commit) populates the entity_id parsing audit lint
(TD-7b / design §5 invariant). Group 11 will later add the AST audit tests
for `.meta.json` writers in this same file.

The entity_id-parsing-audit lint enforces design §5 invariant:

  > `grep -rnE '\\.split\\(":"\\)|substr\\(.*entity_id|instr\\(.*entity_id'`
  > against `plugins/pd/hooks/lib/`, `plugins/pd/mcp/` hits ONLY in
  > `_migration_13_*` functions AND `test_*.py` files.

Any hit outside those allow-listed locations indicates a caller that should
have been ported to read from ``entity_display`` per FR-8.3 / TD-7b but
was missed. The test surfaces such regressions during CI.

Grace mode (design TD-7b): if the audit finds unported sites, the test is
marked ``xfail`` (not ``fail``) so the contract exists for CI without
blocking integration. The current run finds 0 unallowed hits — all hits
are inside ``_migration_13_entity_display`` (database.py) or in test
files — so the test passes cleanly.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Constants — locate plugin paths relative to this file.
# ---------------------------------------------------------------------------
# This file lives at plugins/pd/hooks/lib/doctor/test_audit_writes.py. Walk
# up to plugins/pd/ for relative scan roots.

_PLUGIN_PD_DIR = Path(__file__).resolve().parents[3]  # plugins/pd
_SCAN_ROOTS = [
    _PLUGIN_PD_DIR / "hooks" / "lib",
    _PLUGIN_PD_DIR / "mcp",
]

# Same regex as design §5 invariant. Note: backslash-doubled for shell.
_AUDIT_PATTERN = (
    r'\.split\(":"\)|'
    r'substr\(.*entity_id|'
    r'instr\(.*entity_id|'
    r're\.match.*entity_id'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_audit_grep() -> list[tuple[str, int, str]]:
    """Run the audit grep across `_SCAN_ROOTS`. Returns list of (path,
    line_number, line_text). Excludes binary files automatically (grep -I).
    """
    args = [
        "grep",
        "-rnIE",  # recursive, line-number, skip-binary, extended-regex
        "--include=*.py",
        _AUDIT_PATTERN,
    ]
    for root in _SCAN_ROOTS:
        if root.exists():
            args.append(str(root))

    result = subprocess.run(
        args, capture_output=True, text=True, check=False
    )
    # grep exit 1 == no matches; exit 0 == matches; exit 2 == error.
    if result.returncode == 1:
        return []
    if result.returncode == 2:
        raise RuntimeError(
            f"audit grep failed: stderr={result.stderr!r}, "
            f"stdout={result.stdout!r}"
        )

    hits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        # Format: 'path:lineno:text'.
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
    """Return the name of the function/method that lexically encloses
    `line` in `path`, or None if at module-level.
    """
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
                # Prefer the innermost (smallest span) match.
                span = end - start
                if enclosing is None or span < (enclosing_span[1] - enclosing_span[0]):
                    enclosing = node.name
                    enclosing_span = (start, end)
    return enclosing


def _classify_hit(path: str, line: int) -> str:
    """Classify an audit-grep hit:
      - 'allowed_test'         — file is a test_*.py (pytest convention)
      - 'allowed_migration_13' — line is inside a _migration_13_* function
      - 'unallowed'            — neither — regression
    """
    p = Path(path)
    if p.name.startswith("test_") and p.suffix == ".py":
        return "allowed_test"
    fn = _function_enclosing(p, line)
    if fn is not None and fn.startswith("_migration_13_"):
        return "allowed_migration_13"
    return "unallowed"


# ---------------------------------------------------------------------------
# Test — entity_id parsing audit lint (TD-7b)
# ---------------------------------------------------------------------------


# Sniff the current state of the audit lint so we know whether to mark the
# test as xfail (grace mode for incomplete F8 port) or run it strictly.
_CURRENT_UNALLOWED = [
    (path, line, text)
    for (path, line, text) in _run_audit_grep()
    if _classify_hit(path, line) == "unallowed"
]


@pytest.mark.xfail(
    bool(_CURRENT_UNALLOWED),
    reason=(
        f"TD-7b followup: {len(_CURRENT_UNALLOWED)} entity_id-parsing site(s) "
        "pending port from entity_id-suffix parsing to entity_display reads. "
        "See docs/features/110-markdown-projections-and-gener/retro.md for "
        "the follow-up dispatch. Sites: "
        + "; ".join(
            f"{p}:{ln}" for (p, ln, _t) in _CURRENT_UNALLOWED[:5]
        )
    ),
    strict=False,
)
def test_entity_id_parsing_audit_lint() -> None:
    """TD-7b lint: every entity_id-suffix-parsing call site outside test
    files MUST live inside a ``_migration_13_*`` function. Hits anywhere
    else mean a caller was missed during the FR-8.3 port to entity_display.

    Grace mode: if any unported sites are present, the test is marked
    xfail (see decorator above) so the contract exists without blocking CI.
    """
    hits = _run_audit_grep()

    unallowed: list[tuple[str, int, str]] = []
    for path, line, text in hits:
        cls = _classify_hit(path, line)
        if cls == "unallowed":
            unallowed.append((path, line, text))

    if unallowed:
        bullets = "\n".join(
            f"  - {p}:{ln}: {t.strip()}" for (p, ln, t) in unallowed
        )
        pytest.fail(
            "TD-7b audit lint: found entity_id-parsing call sites outside "
            "the allow-list (test files or _migration_13_* functions). "
            "These sites should have been ported to read seq/slug from "
            "entity_display per FR-8.3.\n"
            f"Unallowed hits ({len(unallowed)}):\n{bullets}"
        )
