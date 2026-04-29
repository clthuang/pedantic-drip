"""Canonical Python implementation + assertions for FR-1 bucketing.

This file IS the executable source-of-truth for AC-1, AC-2, AC-E1.
qa-gate-procedure.md §4 markdown is documentation that mirrors this implementation.
T05's DoD includes a grep-based byte-match sync check between the two.
"""
import re

# Module-level constants per design TD-4 — compile once.
TEST_FILE_RE = re.compile(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$')
_LOC_LINE_SUFFIX_RE = re.compile(r':\d+$')


def _location_matches_test_path(location: str) -> bool:
    """Strip optional ':<digits>' suffix, then check against TEST_FILE_RE."""
    return bool(TEST_FILE_RE.search(_LOC_LINE_SUFFIX_RE.sub('', location)))


def is_test_only_refactor(diff_paths: list[str]) -> bool:
    """FR-1 trigger: True iff non-empty AND every path matches TEST_FILE_RE."""
    if not diff_paths:
        return False
    return all(TEST_FILE_RE.search(p) for p in diff_paths)


def bucket(finding, all_findings, *, is_test_only_refactor: bool = False) -> str:
    """Severity bucket per qa-gate-procedure.md §4 + FR-1 extension."""
    sev = finding.get("severity")
    sec_sev = finding.get("securitySeverity")
    high = sev == "blocker" or sec_sev in {"critical", "high"}
    med = sev == "warning" or sec_sev == "medium"
    low = sev == "suggestion" or sec_sev == "low"
    # AC-5b narrowed remap for test-deepener (existing behavior, preserved).
    if finding.get("reviewer") == "pd:test-deepener" and high:
        mutation_caught = finding.get("mutation_caught", True)
        cross_confirmed = any(
            other.get("location") == finding.get("location")
            and other.get("reviewer") != "pd:test-deepener"
            for other in all_findings
        )
        if not mutation_caught and not cross_confirmed:
            # FR-1 NEW: test-only refactor with location in test file → LOW.
            if is_test_only_refactor and _location_matches_test_path(finding.get("location", "")):
                return "LOW"
            return "MED"  # existing AC-5b path
    if high:
        return "HIGH"
    if med:
        return "MED"
    if low:
        return "LOW"
    return "MED"


# ============================================================================
# Tests (run with: pytest plugins/pd/scripts/tests/test_qa_gate_bucket.py)
# ============================================================================

def test_ac1_test_only_refactor_predicate():
    """AC-1: predicate on diff path lists."""
    assert is_test_only_refactor(["test_database.py", "plugins/pd/skills/specifying/test_self_check.py"])
    assert not is_test_only_refactor(["test_foo.py", "database.py"])
    assert not is_test_only_refactor(["plugins/pd/hooks/tests/test-hooks.sh"])  # .sh not .py
    assert not is_test_only_refactor([])  # AC-E1: empty diff vacuous-truth not allowed


def test_ac2_helper_assertions():
    """AC-2: _location_matches_test_path() with/without :line suffix."""
    assert _location_matches_test_path("test_database.py:2354")
    assert _location_matches_test_path("test_database.py")
    assert _location_matches_test_path("plugins/pd/tests/test_foo.py:42")
    assert not _location_matches_test_path("database.py:1055")
    assert not _location_matches_test_path("plugins/pd/hooks/tests/test-hooks.sh:10")
    assert not _location_matches_test_path("")


def test_ac2_bucket_test_only_refactor_path():
    """AC-2: bucket() returns LOW when is_test_only_refactor=True + test location."""
    finding = {
        "reviewer": "pd:test-deepener", "severity": "blocker",
        "location": "test_database.py:2354", "mutation_caught": False,
    }
    assert bucket(finding, [], is_test_only_refactor=True) == "LOW"


def test_ac2_bucket_existing_ac5b_preserved():
    """AC-2: kwarg-False preserves existing AC-5b HIGH→MED path."""
    finding = {
        "reviewer": "pd:test-deepener", "severity": "blocker",
        "location": "test_database.py:2354", "mutation_caught": False,
    }
    assert bucket(finding, [], is_test_only_refactor=False) == "MED"
    # Default kwarg (no kwarg passed) — backward compat.
    assert bucket(finding, []) == "MED"


def test_ac2_bucket_non_test_location_with_kwarg():
    """AC-2: even with kwarg=True, prod-file location → MED (existing AC-5b)."""
    finding = {
        "reviewer": "pd:test-deepener", "severity": "blocker",
        "location": "database.py:1055", "mutation_caught": False,
    }
    assert bucket(finding, [], is_test_only_refactor=True) == "MED"


def test_ac2_bucket_cross_confirmed_stays_high():
    """Truth table row: cross_confirm=True → HIGH regardless of kwarg."""
    finding = {
        "reviewer": "pd:test-deepener", "severity": "blocker",
        "location": "test_database.py:2354", "mutation_caught": False,
    }
    other = {"reviewer": "pd:security-reviewer", "location": "test_database.py:2354"}
    assert bucket(finding, [other], is_test_only_refactor=True) == "HIGH"


def test_ac2_bucket_mutation_caught_stays_high():
    """Truth table row: mutation_caught=True → HIGH regardless of kwarg."""
    finding = {
        "reviewer": "pd:test-deepener", "severity": "blocker",
        "location": "test_database.py:2354", "mutation_caught": True,
    }
    assert bucket(finding, [], is_test_only_refactor=True) == "HIGH"


def test_severity_warning_med():
    assert bucket({"severity": "warning"}, []) == "MED"


def test_severity_suggestion_low():
    assert bucket({"severity": "suggestion"}, []) == "LOW"
