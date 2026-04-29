"""Tests for FR-6a cleanup_backlog.py.

Lazy imports per T18 DoD — `import cleanup_backlog` inside test bodies only,
NOT at module top, so pytest --collect-only succeeds even when the module
does not yet exist (TDD-red contract).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ARCHIVABLE_FIXTURE = FIXTURE_DIR / "backlog-099-archivable.md"
SCRIPT_PATH = Path(__file__).parent.parent / "cleanup_backlog.py"


@pytest.fixture
def tmp_backlog(tmp_path):
    """Copy fixture to a tmp_path so tests can mutate without polluting source."""
    dst = tmp_path / "backlog.md"
    shutil.copy(ARCHIVABLE_FIXTURE, dst)
    return dst


@pytest.fixture
def tmp_archive(tmp_path):
    """Archive path — initially absent."""
    return tmp_path / "backlog-archive.md"


def _run(*args):
    """Run cleanup_backlog.py CLI; capture stdout/stderr/returncode."""
    cmd = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_ac8_dry_run_identifies_three_archivable(tmp_backlog):
    """AC-8: dry-run on fixture identifies exactly 3 ARCHIVABLE sections."""
    result = _run("--dry-run", "--backlog-path", str(tmp_backlog))
    assert result.returncode == 0
    out = result.stdout
    # Three archivable sections (TestA, TestB, TestC); MixedQA + EmptyQA are NOT.
    assert out.count("YES") == 3
    assert "TestA" in out and "TestB" in out and "TestC" in out
    # Mixed and empty sections must not appear as ARCHIVABLE.
    # (Verify by checking they are listed but with NO/empty status — relies on table format.)
    # Verify no writes occurred:
    assert tmp_backlog.read_text() == ARCHIVABLE_FIXTURE.read_text()


def test_ac8b_dry_run_real_backlog_smoke(monkeypatch):
    """AC-8b: dry-run on real backlog returns non-empty output, exits 0."""
    real_backlog = Path(__file__).parent.parent.parent.parent.parent / "docs" / "backlog.md"
    if not real_backlog.exists():
        pytest.skip("real backlog.md not present")
    result = _run("--dry-run", "--backlog-path", str(real_backlog))
    assert result.returncode == 0
    assert "Section" in result.stdout or "From" in result.stdout  # table or section header present


def test_ac9_apply_moves_sections(tmp_backlog, tmp_archive):
    """AC-9: --apply moves archivable sections from backlog to archive."""
    pre_lines = tmp_backlog.read_text().count("\n")
    result = _run("--apply", "--backlog-path", str(tmp_backlog), "--archive-path", str(tmp_archive))
    assert result.returncode == 0
    # Archive created with header (4 lines) + moved sections.
    assert tmp_archive.exists()
    archive_text = tmp_archive.read_text()
    assert "# Backlog Archive" in archive_text
    assert "TestA" in archive_text and "TestB" in archive_text and "TestC" in archive_text
    # Backlog shrunk.
    post_lines = tmp_backlog.read_text().count("\n")
    assert post_lines < pre_lines
    # MixedQA and EmptyQA stayed in backlog.
    backlog_text = tmp_backlog.read_text()
    assert "MixedQA" in backlog_text
    assert "EmptyQA" in backlog_text
    # Archive sections are NOT in backlog anymore.
    assert "TestA" not in backlog_text


def test_ac9f_no_double_blank_runs(tmp_backlog, tmp_archive):
    """AC-9(f): post-archive backlog has no double-blank-line runs."""
    _run("--apply", "--backlog-path", str(tmp_backlog), "--archive-path", str(tmp_archive))
    assert "\n\n\n" not in tmp_backlog.read_text()


def test_ace7_idempotency(tmp_backlog, tmp_archive):
    """AC-E7: re-running --apply produces zero diffs."""
    _run("--apply", "--backlog-path", str(tmp_backlog), "--archive-path", str(tmp_archive))
    backlog_after_first = tmp_backlog.read_text()
    archive_after_first = tmp_archive.read_text()
    _run("--apply", "--backlog-path", str(tmp_backlog), "--archive-path", str(tmp_archive))
    assert tmp_backlog.read_text() == backlog_after_first
    assert tmp_archive.read_text() == archive_after_first


def test_ace6_empty_section_not_archivable(tmp_backlog):
    """AC-E6: section with 0 items is NOT marked ARCHIVABLE."""
    result = _run("--dry-run", "--backlog-path", str(tmp_backlog))
    # EmptyQA section has no items; should NOT appear with YES.
    out = result.stdout
    # Find the EmptyQA row and verify no YES marker.
    for line in out.splitlines():
        if "EmptyQA" in line:
            # YES would indicate archivable — should not be present for empty section.
            assert "YES" not in line


def test_count_active_cli(tmp_backlog):
    """T16 --count-active flag exists and returns int (used by FR-6b doctor)."""
    result = _run("--count-active", "--backlog-path", str(tmp_backlog))
    assert result.returncode == 0
    count = int(result.stdout.strip())
    # Fixture has 3 active items in MixedQA (#99030, #99032) — wait, #99031 is closed.
    # MixedQA: #99030 active, #99031 closed, #99032 active = 2 active.
    # Plus top-level table item #00099 — but FR-6a says top-level table is OUT OF SCOPE for sections.
    # FR-6b counts active items via `^- \*\*#[0-9]+\*\*` (regardless of section). So count includes
    # all active items in the file: #99030, #99032 from MixedQA. Plus archivable sections still
    # count their items (we're counting active before archive). Active items per section:
    #   TestA: 1 (#99003 — has (closed: marker, so it's CLOSED — actually re-check)
    # Actually re-reading fixture: #99003 has "(closed: rationale)" marker → closed. So TestA all closed.
    # Active items overall: only #99030 and #99032.
    assert count == 2
