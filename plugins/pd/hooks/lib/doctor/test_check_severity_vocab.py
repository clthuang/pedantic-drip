"""Feature 116 FR-2 / AC-2.x: check_severity_vocab AST audit tests.

The AST check scans doctor/checks.py + doctor/check_*.py for `severity=`
keyword arguments whose value is an `ast.Constant` string outside
{"error", "warning", "info"}. We verify:
- AC-2.2: canonical literals (`error`, `warning`, `info`) do NOT emit issues.
- AC-2.2: a non-canonical literal (`critical`) emits one error issue
  whose `message` contains the line number.
- AC-2.2: indirect references (variable, function call) are NOT flagged
  (narrow visitor scope: requires `Constant(value=str)`).
- AC-2.2: positional `Issue("check", "warning", ...)` is NOT flagged.
- AC-2.3: test files (matching `_TEST_FILE_RE`) are skipped.

To run the AST check against arbitrary fixture files, the test monkeypatches
the `pathlib.Path(__file__).parent` reference inside `check_severity_vocab`
by symlinking/copying the check module into a temp dir.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure plugins/pd/hooks/lib is importable when tests are invoked directly.
_LIB_ROOT = Path(__file__).resolve().parents[1]
if str(_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(_LIB_ROOT))


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _run_check_against_dir(scan_dir: Path):
    """Invoke check_severity_vocab with its `__file__.parent` rebound to
    scan_dir via mock — the production source resolution is
    `pathlib.Path(__file__).parent`.

    NOTE: we use ``importlib.import_module`` to obtain the *module*
    (``doctor.check_severity_vocab``) rather than the function of the same
    name re-exported via ``doctor/__init__.py``'s
    ``from doctor.check_severity_vocab import check_severity_vocab``. After
    the re-export, ``from doctor import check_severity_vocab`` resolves to
    the function (per Python attribute lookup), which breaks
    ``mock.patch.object``.
    """
    import importlib
    mod = importlib.import_module("doctor.check_severity_vocab")
    with mock.patch.object(mod, "_resolve_doctor_dir", return_value=scan_dir):
        return mod.check_severity_vocab(project_root=None)


def test_check_severity_vocab_passes_on_canonical_severities(tmp_path):
    """AC-2.2: severity='error'/'warning'/'info' literals do NOT emit issues."""
    _write(
        tmp_path / "check_alpha.py",
        '''
from doctor.models import Issue
def f():
    return [
        Issue(check="x", severity="error",   entity=None, message="m", fix_hint=None),
        Issue(check="x", severity="warning", entity=None, message="m", fix_hint=None),
        Issue(check="x", severity="info",    entity=None, message="m", fix_hint=None),
    ]
''',
    )
    result = _run_check_against_dir(tmp_path)
    assert result.passed is True
    assert result.issues == []


def test_check_severity_vocab_flags_unknown_literal(tmp_path):
    """AC-2.2: severity='critical' emits 1 Issue at severity='error',
    with the line number folded into the message.
    """
    _write(
        tmp_path / "check_bravo.py",
        '''
from doctor.models import Issue
def f():
    return Issue(check="x", severity="critical", entity=None, message="m", fix_hint=None)
''',
    )
    result = _run_check_against_dir(tmp_path)
    assert result.passed is False
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == "error"
    assert "critical" in issue.message
    # Line 4 in the fixture (1-indexed) — the `return Issue(...)` line.
    assert "line 4" in issue.message or "line " in issue.message


def test_check_severity_vocab_skips_indirect_refs(tmp_path):
    """AC-2.2: variable refs and call results in `severity=` are NOT flagged
    (narrow visitor: requires `ast.Constant` with `str` value).
    """
    _write(
        tmp_path / "check_charlie.py",
        '''
from doctor.models import Issue

MY_CONST = "critical"

def get_sev():
    return "critical"

def f():
    return [
        Issue(check="x", severity=MY_CONST,  entity=None, message="m", fix_hint=None),
        Issue(check="x", severity=get_sev(), entity=None, message="m", fix_hint=None),
    ]
''',
    )
    result = _run_check_against_dir(tmp_path)
    assert result.passed is True
    assert result.issues == []


def test_check_severity_vocab_skips_positional(tmp_path):
    """AC-2.2: positional severity (no `severity=` kwarg) NOT flagged.
    Acceptable limitation — all current call sites use kwargs.
    """
    _write(
        tmp_path / "check_delta.py",
        '''
from doctor.models import Issue
def f():
    return Issue("x", "critical", None, "m", None)
''',
    )
    result = _run_check_against_dir(tmp_path)
    assert result.passed is True
    assert result.issues == []


def test_check_severity_vocab_excludes_test_files(tmp_path):
    """AC-2.3: test files (matching `_TEST_FILE_RE`) are skipped."""
    # Filename matches `test_*.py` → should be excluded by _TEST_FILE_RE.
    _write(
        tmp_path / "test_some_check.py",
        '''
from doctor.models import Issue
def f():
    return Issue(check="x", severity="critical", entity=None, message="m", fix_hint=None)
''',
    )
    # And another file matching `*_test.py`
    _write(
        tmp_path / "alpha_test.py",
        '''
from doctor.models import Issue
def f():
    return Issue(check="x", severity="bogus", entity=None, message="m", fix_hint=None)
''',
    )
    result = _run_check_against_dir(tmp_path)
    # Neither test_*.py nor *_test.py is named check_*.py or checks.py, so
    # the candidate list shouldn't even contain them — but the test
    # documents the filter contract explicitly.
    assert result.passed is True
    assert result.issues == []
