"""Feature 116 FR-2 / AC-2.x: AST audit for the closed-set severity vocabulary.

Scans every doctor check source file (``doctor/checks.py`` and every
``doctor/check_*.py`` excluding test files) for ``severity=<literal>`` keyword
arguments whose value is an ``ast.Constant`` string outside the closed set
``{"error", "warning", "info"}``. Each violation is reported as a doctor
``Issue`` with severity ``"error"``. The line number is folded into the
``message`` because ``Issue`` has no ``line`` field.

Visitor scope is intentionally narrow:
- Only ``ast.Call`` keyword arguments named ``severity``.
- Only ``ast.Constant`` values that are ``str``.
- Positional severity arguments (e.g. ``Issue("x", "warning", ...)``) are NOT
  flagged. All current call sites use kwargs (grep-verified at spec time).

Failure mode:
- ``SyntaxError`` from ``ast.parse`` → single error-severity Issue per file.
- Source file missing or unreadable → silently skipped (defensive).

The check follows the same dispatch contract as ``check_status_write_path``
and ``check_audit_counter_write_path`` (``(project_root=None, **_kwargs)
-> CheckResult``) so the doctor runner can invoke it with the standard ``ctx``.
"""
from __future__ import annotations

import ast
import re
import time
from pathlib import Path

from doctor.models import CheckResult, Issue

# Closed-set severity vocabulary per F115 spec FR-Sev-115.1.
CLOSED_SET = {"error", "warning", "info"}

# Test files are excluded — they intentionally embed adversarial literals
# (e.g. ``severity='critical'``) inside fixture strings as test data, not as
# real Issue construction call sites.
_TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def _resolve_doctor_dir() -> Path:
    """Return the directory containing this module.

    Indirection point so tests can monkeypatch the scan target via
    ``mock.patch.object(check_severity_vocab, "_resolve_doctor_dir", ...)``.
    """
    return Path(__file__).parent


def _scan_targets(doctor_dir: Path) -> list[Path]:
    """Return doctor-check source files to scan, excluding test files."""
    candidates = []
    checks_py = doctor_dir / "checks.py"
    if checks_py.exists():
        candidates.append(checks_py)
    candidates.extend(sorted(doctor_dir.glob("check_*.py")))
    return [
        p for p in candidates
        if not _TEST_FILE_RE.search(str(p))
    ]


def _audit_file(path: Path) -> list[Issue]:
    """Audit a single source file for non-canonical severity literals."""
    issues: list[Issue] = []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return issues
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        issues.append(Issue(
            check="check_severity_vocab",
            severity="error",
            entity=str(path),
            message=f"AST parse failed: {path}: {exc}",
            fix_hint=None,
        ))
        return issues

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "severity":
                continue
            if not isinstance(kw.value, ast.Constant):
                continue
            if not isinstance(kw.value.value, str):
                continue
            val = kw.value.value
            if val in CLOSED_SET:
                continue
            issues.append(Issue(
                check="check_severity_vocab",
                severity="error",
                entity=str(path),
                message=(
                    f"line {kw.value.lineno}: severity={val!r} outside "
                    f"closed set {sorted(CLOSED_SET)}"
                ),
                fix_hint=f"change to one of {sorted(CLOSED_SET)}",
            ))
    return issues


def check_severity_vocab(
    project_root: str | None = None,
    **_kwargs: object,
) -> CheckResult:
    """AST audit that every doctor check emits severity literals from the
    closed set ``{"error", "warning", "info"}``.

    Returns a ``CheckResult`` with one ``Issue(severity="error")`` per
    violation. ``validate.sh`` is the CI enforcement layer; session-start
    does not abort on these findings (existing convention, matches
    ``check_status_write_path`` and ``check_audit_counter_write_path``).
    """
    start = time.perf_counter()
    issues: list[Issue] = []

    try:
        doctor_dir = _resolve_doctor_dir()
        for path in _scan_targets(doctor_dir):
            issues.extend(_audit_file(path))
    except Exception as exc:
        # Defensive: emit a single diagnostic error rather than crashing the
        # session-start hook. Matches behavior of peer AST checks.
        issues.append(Issue(
            check="check_severity_vocab",
            severity="error",
            entity=None,
            message=f"check_severity_vocab failed unexpectedly: {exc}",
            fix_hint=None,
        ))

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return CheckResult(
        name="check_severity_vocab",
        passed=(len(issues) == 0),
        issues=issues,
        elapsed_ms=elapsed_ms,
    )
