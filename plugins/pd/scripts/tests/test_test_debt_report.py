"""Tests for FR-8 test_debt_report.py.

Lazy imports per T21 DoD — `import test_debt_report` inside test bodies only,
so pytest --collect-only succeeds before T20 implementation lands.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "test_debt_report.py"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "qa-gate-fixtures"


@pytest.fixture
def synthetic_features_dir(tmp_path):
    """Build a tmp features dir with controlled .qa-gate.json fixtures."""
    features = tmp_path / "features"
    f1 = features / "f001-test-feature"
    f1.mkdir(parents=True)
    (f1 / ".qa-gate.json").write_text(json.dumps({
        "head_sha": "abc123",
        "findings": [
            {"reviewer": "pd:test-deepener", "severity": "warning",
             "location": "test_database.py:2354", "description": "test gap"},
            {"reviewer": "pd:security-reviewer", "severity": "warning",
             "securitySeverity": "medium", "location": "auth.py:42",
             "description": "weak token check"},
        ],
    }))
    f2 = features / "f002-another"
    f2.mkdir()
    (f2 / ".qa-gate.json").write_text(json.dumps({
        "head_sha": "def456",
        "findings": [
            {"reviewer": "pd:test-deepener", "severity": "suggestion",
             "location": "test_database.py:2354", "description": "another test gap"},
        ],
    }))
    return features


@pytest.fixture
def empty_backlog(tmp_path):
    bl = tmp_path / "backlog.md"
    bl.write_text("# Backlog\n\n(no items)\n")
    return bl


@pytest.fixture
def synthetic_backlog(tmp_path):
    bl = tmp_path / "backlog.md"
    bl.write_text("""# Backlog

## From Feature 086 QA

- **#99100** [MED/testability] Some testability gap.
- ~~**#99101**~~ Closed test debt.

""")
    return bl


def _run_script(features_dir, backlog_path):
    """Invoke test_debt_report.py CLI."""
    cmd = [sys.executable, str(SCRIPT_PATH),
           "--features-dir", str(features_dir),
           "--backlog-path", str(backlog_path)]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_ac13_non_empty_data_row(synthetic_features_dir, synthetic_backlog):
    """AC-13: data row from synthetic .qa-gate.json + backlog testability tag."""
    result = _run_script(synthetic_features_dir, synthetic_backlog)
    assert result.returncode == 0
    out = result.stdout
    # Header present.
    assert "| File or Module | Category | Open Count | Source Features |" in out
    # At least one data row beyond header/separator/footer.
    data_rows = [line for line in out.splitlines()
                 if line.startswith("|") and "---" not in line and "Category" not in line]
    assert len(data_rows) >= 1


def test_ac14_four_column_schema(synthetic_features_dir, synthetic_backlog):
    """AC-14: header has exactly 4 columns (5 pipes)."""
    result = _run_script(synthetic_features_dir, synthetic_backlog)
    assert result.returncode == 0
    header_lines = [line for line in result.stdout.splitlines() if "File or Module" in line]
    assert len(header_lines) == 1
    assert header_lines[0].count("|") == 5


def test_ace8_empty_inputs(tmp_path, empty_backlog):
    """AC-E8: zero qa-gate.json + zero backlog testability → empty table + footer."""
    empty_features = tmp_path / "empty-features"
    empty_features.mkdir()
    result = _run_script(empty_features, empty_backlog)
    assert result.returncode == 0
    assert "Total: 0 open items across 0 files" in result.stdout
    # Header still present.
    assert "| File or Module |" in result.stdout


def test_normalize_location_parity():
    """Inlined normalize_location matches qa-gate-procedure.md §4 contract."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))  # add scripts/ to path
    from test_debt_report import normalize_location  # lazy import inside test
    assert normalize_location("plugins/pd/lib/foo.py:42") == "foo.py:42"
    assert normalize_location("test_database.py:2354") == "test_database.py:2354"
    assert normalize_location("Architecture-level note") == "architecture-level note"
    assert normalize_location("") == ""
    # Widened regex per design fix — uppercase extensions:
    assert normalize_location("page.tsx:99") == "page.tsx:99"
    assert normalize_location("config.JSON:1") == "config.JSON:1"
