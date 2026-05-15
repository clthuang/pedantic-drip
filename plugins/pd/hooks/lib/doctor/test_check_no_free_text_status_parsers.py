"""Tests for the doctor ``check_no_free_text_status_parsers`` health check.

Feature 111 / AC-CL.4: doctor grep-audit that surfaces any re-introduction
of free-text status suffix parsers at the three production paths:

- ``plugins/pd/hooks/lib/entity_registry/backfill.py``
- ``plugins/pd/hooks/lib/doctor/checks.py``
- ``plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py``

The check uses ``PROJECT_ROOT`` env var → ``git rev-parse --show-toplevel``
fallback so it works regardless of CWD (verified by the 2-CWD test).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from doctor.check_no_free_text_status_parsers import (
    check_no_free_text_status_parsers,
)
from doctor.models import CheckResult


# Resolve the project root once for all tests.
def _project_root() -> Path:
    out = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    return Path(out)


PROJECT_ROOT = _project_root()


def test_check_no_free_text_status_parsers_passes_on_production() -> None:
    """Smoke test: against the current codebase (post-Group-E cleanup),
    the check returns a CheckResult with passed=True and no issues."""
    result = check_no_free_text_status_parsers(project_root=str(PROJECT_ROOT))
    assert isinstance(result, CheckResult)
    assert result.name == "no_free_text_status_parsers"
    assert result.passed is True, (
        "check_no_free_text_status_parsers reported unexpected violations: "
        + "\n".join(i.message for i in result.issues)
    )
    assert result.issues == []


def test_check_no_free_text_status_parsers_detects_synthetic_regression(
    tmp_path: Path,
) -> None:
    """Inject a parser-marker into a *copy* of backfill.py inside a fake
    project root; the check must FAIL when scanning that fake root.

    Pattern: build a directory mirroring the production layout
    (plugins/pd/hooks/lib/{entity_registry,doctor,reconciliation_orchestrator})
    and copy each target file. Append a synthetic parser line to backfill.py.
    Point the check at the fake root via the ``project_root`` kwarg.
    """
    # Build the fake project root with the 3 target paths.
    fake = tmp_path / "fake-project"
    er_dir = fake / "plugins/pd/hooks/lib/entity_registry"
    doc_dir = fake / "plugins/pd/hooks/lib/doctor"
    rec_dir = fake / "plugins/pd/hooks/lib/reconciliation_orchestrator"
    for d in (er_dir, doc_dir, rec_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Copy the actual files (preserving content; we only need them to exist).
    shutil.copy(
        PROJECT_ROOT / "plugins/pd/hooks/lib/entity_registry/backfill.py",
        er_dir / "backfill.py",
    )
    shutil.copy(
        PROJECT_ROOT / "plugins/pd/hooks/lib/doctor/checks.py",
        doc_dir / "checks.py",
    )
    shutil.copy(
        PROJECT_ROOT / "plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
        rec_dir / "entity_status.py",
    )

    # Inject a synthetic parser line into the fake backfill.py.
    with open(er_dir / "backfill.py", "a") as f:
        f.write('\n# synthetic regression: (closed: this should be flagged)\n')

    result = check_no_free_text_status_parsers(project_root=str(fake))
    assert result.passed is False, (
        "Expected FAIL when synthetic '(closed:' marker is injected"
    )
    assert len(result.issues) >= 1
    assert any("closed:" in i.message for i in result.issues), (
        f"Expected an issue mentioning 'closed:'; got: "
        f"{[i.message for i in result.issues]}"
    )


def test_check_no_free_text_status_parsers_works_from_project_root(
    tmp_path: Path,
) -> None:
    """AC-CL.4 (part 1): when called from PROJECT_ROOT as CWD, the check
    PASSES on the production codebase."""
    # Run the check as a subprocess so CWD is honored end-to-end.
    plugin_root = PROJECT_ROOT / "plugins" / "pd"
    venv_python = plugin_root / ".venv" / "bin" / "python"
    pythonpath = plugin_root / "hooks" / "lib"

    code = (
        "from doctor.check_no_free_text_status_parsers import "
        "check_no_free_text_status_parsers; "
        "r = check_no_free_text_status_parsers(); "
        "import sys; sys.exit(0 if r.passed else 1)"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(pythonpath),
        # Unset PROJECT_ROOT so the check falls back to git rev-parse.
    }
    env.pop("PROJECT_ROOT", None)
    proc = subprocess.run(
        [str(venv_python), "-c", code],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"From project root CWD, check failed.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_check_no_free_text_status_parsers_works_from_subdirectory(
    tmp_path: Path,
) -> None:
    """AC-CL.4 (part 2): when called from a SUBDIRECTORY, the check still
    PASSES on the production codebase (PROJECT_ROOT resolution survives).

    The check's path resolution uses PROJECT_ROOT env var → git rev-parse
    fallback, so CWD must not matter.
    """
    plugin_root = PROJECT_ROOT / "plugins" / "pd"
    venv_python = plugin_root / ".venv" / "bin" / "python"
    pythonpath = plugin_root / "hooks" / "lib"

    # Use a real subdirectory inside the project.
    sub_cwd = plugin_root / "hooks"
    assert sub_cwd.is_dir(), f"Expected subdir to exist: {sub_cwd}"

    code = (
        "from doctor.check_no_free_text_status_parsers import "
        "check_no_free_text_status_parsers; "
        "r = check_no_free_text_status_parsers(); "
        "import sys; sys.exit(0 if r.passed else 1)"
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(pythonpath),
    }
    env.pop("PROJECT_ROOT", None)
    proc = subprocess.run(
        [str(venv_python), "-c", code],
        cwd=str(sub_cwd),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"From subdirectory CWD {sub_cwd}, check failed.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def test_check_no_free_text_status_parsers_respects_project_root_env_var(
    tmp_path: Path,
) -> None:
    """If PROJECT_ROOT is set, the check uses it (bypassing git rev-parse)."""
    fake = tmp_path / "fake-project"
    er_dir = fake / "plugins/pd/hooks/lib/entity_registry"
    doc_dir = fake / "plugins/pd/hooks/lib/doctor"
    rec_dir = fake / "plugins/pd/hooks/lib/reconciliation_orchestrator"
    for d in (er_dir, doc_dir, rec_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Three clean files (no markers).
    (er_dir / "backfill.py").write_text("# clean\n")
    (doc_dir / "checks.py").write_text("# clean\n")
    (rec_dir / "entity_status.py").write_text("# clean\n")

    # Set PROJECT_ROOT env var; check should use it.
    result = check_no_free_text_status_parsers(
        env={"PROJECT_ROOT": str(fake)}
    )
    assert result.passed is True, (
        "Expected PASS when PROJECT_ROOT env var points to a clean tree"
    )
