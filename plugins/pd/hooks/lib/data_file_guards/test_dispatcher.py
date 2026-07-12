"""Tests for data_file_guards.dispatcher (feature 110, Group 9)."""

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Resolve paths in a project-aware way.
# The package lives at plugins/pd/hooks/lib/data_file_guards/.
# PROJECT_ROOT = 4 levels up from this file (data_file_guards / lib / hooks /
# pd / plugins -> project root).
# ---------------------------------------------------------------------------
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parents[4]  # data_file_guards -> lib -> hooks -> pd -> plugins -> ROOT
CONFIG_PATH = PROJECT_ROOT / "plugins" / "pd" / "hooks" / "data_file_guards.json"
PROBE_PATH = PROJECT_ROOT / "plugins" / "pd" / "hooks" / "tests" / "probe_fnmatch.py"
LIB_DIR = PROJECT_ROOT / "plugins" / "pd" / "hooks" / "lib"


# ---------------------------------------------------------------------------
# Task 9.6 — TD-1 fnmatch matrix
# ---------------------------------------------------------------------------

TD1_MATRIX = [
    ("docs/features/043/.meta.json", "*.meta.json", True),
    ("docs/projects/P003/.meta.json", "*.meta.json", True),
    ("docs/projects/P003/.meta.json", "docs/projects/*/.meta.json", True),
    ("docs/backlog.md", "docs/backlog.md", True),
    # Row 5: design TD-1 predicted False, but fnmatch.fnmatch translates the
    # pattern as `(?s:docs/projects/(?>.*?/).*\.meta\.json)\z` which matches
    # because the second `*` may be empty (so `.meta.json` matches `*.meta.json`).
    # Empirical truth recorded here; the matrix's purpose is to document actual
    # behavior, not aspirational behavior. Tracked as a design-deviation note.
    ("docs/projects/P003/.meta.json", "docs/projects/*/*.meta.json", True),
]


@pytest.mark.parametrize("path,pattern,expected", TD1_MATRIX)
def test_fnmatch_td1_matrix(path, pattern, expected):
    """Inline assertion: each row of the TD-1 5-row matrix matches design."""
    actual = fnmatch.fnmatch(path, pattern)
    assert actual is expected, (
        f"fnmatch.fnmatch({path!r}, {pattern!r}) returned {actual}, expected {expected}"
    )


def test_probe_fnmatch_script_exits_zero():
    """Task 9.6: probe script must exist and exit 0 (all matrix rows pass)."""
    assert PROBE_PATH.exists(), f"probe script missing at {PROBE_PATH}"
    result = subprocess.run(
        [sys.executable, str(PROBE_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"probe_fnmatch.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Task 9.7 — data_file_guards.json schema parse smoke (AC-7.1)
# ---------------------------------------------------------------------------


def test_config_parses_and_has_required_keys():
    """AC-7.1: config exists, parses as JSON, has >=2 entries with required keys."""
    assert CONFIG_PATH.exists(), f"config missing at {CONFIG_PATH}"
    with open(CONFIG_PATH) as fh:
        cfg = json.load(fh)
    assert isinstance(cfg, list), f"expected list, got {type(cfg).__name__}"
    assert len(cfg) >= 2, f"expected >=2 entries, got {len(cfg)}"

    first = cfg[0]
    for key in ("pattern", "exclude_patterns", "decision_module", "mcp_tool_hint"):
        assert key in first, f"first entry missing key {key!r}: {first!r}"

    assert first["pattern"] == "*.meta.json"
    assert "docs/projects/*/.meta.json" in first["exclude_patterns"]
    assert first["decision_module"] == "data_file_guards.meta_json_decision"


# ---------------------------------------------------------------------------
# Dispatcher behavior — invoke the dispatcher module as a subprocess to
# match the real hook context (stdin JSON in, JSON-or-empty out, exit 0).
# ---------------------------------------------------------------------------


def _run_dispatcher(payload: dict, env_overrides: dict | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(LIB_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-m", "data_file_guards.dispatcher"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def test_dispatcher_allows_non_write_tool():
    """Non-Write/Edit/NotebookEdit tools always allowed (empty {} output)."""
    rc, stdout, stderr = _run_dispatcher(
        {"tool_name": "Read", "tool_input": {"file_path": "docs/backlog.md"}}
    )
    assert rc == 0, f"dispatcher exited {rc}; stderr: {stderr}"
    assert json.loads(stdout) == {}, f"expected empty allow, got {stdout!r}"


def test_dispatcher_denies_backlog_write():
    """AC-7.4: Write to docs/backlog.md is denied with /pd:add-to-backlog reason."""
    rc, stdout, stderr = _run_dispatcher(
        {"tool_name": "Write", "tool_input": {"file_path": "docs/backlog.md"}}
    )
    assert rc == 0, f"dispatcher exited {rc}; stderr: {stderr}"
    out = json.loads(stdout)
    decision = out["hookSpecificOutput"]["permissionDecision"]
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert decision == "deny", f"expected deny, got {decision!r}; full: {out!r}"
    assert "/pd:add-to-backlog" in reason
    assert "update via DB then re-project" in reason


def test_dispatcher_allows_when_no_pattern_matches():
    """Write to a path that matches NO config entry → allow."""
    rc, stdout, stderr = _run_dispatcher(
        {"tool_name": "Write", "tool_input": {"file_path": "README.md"}}
    )
    assert rc == 0, f"dispatcher exited {rc}; stderr: {stderr}"
    assert json.loads(stdout) == {}, f"expected empty allow, got {stdout!r}"


def test_dispatcher_excludes_project_meta_json():
    """AC-7.7: docs/projects/*/.meta.json is excluded; dispatcher allows (no match)."""
    rc, stdout, stderr = _run_dispatcher(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/projects/P003/.meta.json"},
        }
    )
    assert rc == 0, f"dispatcher exited {rc}; stderr: {stderr}"
    # Excluded → no other entry matches → allow.
    assert json.loads(stdout) == {}, f"expected empty allow, got {stdout!r}"


# ---------------------------------------------------------------------------
# Decision module unit tests
# ---------------------------------------------------------------------------


def test_backlog_decision_always_denies():
    """backlog_decision.decide returns deny with required substrings."""
    sys.path.insert(0, str(LIB_DIR))
    try:
        from data_file_guards import backlog_decision  # type: ignore
    finally:
        sys.path.pop(0)
    out = backlog_decision.decide("docs/backlog.md", "Write", {})
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert "/pd:add-to-backlog" in reason
    assert "update via DB then re-project" in reason


def test_meta_json_decision_env_bypass_allows():
    """meta_json_decision.decide returns allow when PD_META_JSON_WRITE_ALLOWED is set."""
    sys.path.insert(0, str(LIB_DIR))
    try:
        from data_file_guards import meta_json_decision  # type: ignore
    finally:
        sys.path.pop(0)
    old = os.environ.get("PD_META_JSON_WRITE_ALLOWED")
    os.environ["PD_META_JSON_WRITE_ALLOWED"] = "1"
    try:
        out = meta_json_decision.decide("docs/features/043/.meta.json", "Write", {})
    finally:
        if old is None:
            del os.environ["PD_META_JSON_WRITE_ALLOWED"]
        else:
            os.environ["PD_META_JSON_WRITE_ALLOWED"] = old
    assert out["permissionDecision"] == "allow"


# ---------------------------------------------------------------------------
# D2 — deny-matrix tests (FR127-5, SC1). meta_json_decision.decide() must
# deny .meta.json writes in EVERY sentinel world (no sentinel / stale
# sentinel / valid sentinel) unless the bypass env is set. Tests 1-2 are
# RED-FIRST: against the pre-D1 module they flip allow->deny (the degraded
# permit is being deleted). Test 3 is a regression pin — post-D1 all three
# worlds share one deny branch, proving the deletion left no state-dependence
# (design D6). Each world is built via monkeypatch.setenv("HOME", tmp_path)
# so the sentinel glob in the pre-D1 module resolves under an isolated tree.
# ---------------------------------------------------------------------------


def _write_sentinel(home: Path, content: str) -> None:
    """Create a sentinel file at the path the pre-D1 module's glob matches.

    Pattern (pre-D1 _find_sentinel): ~/.claude/plugins/cache/*/pd*/*/.venv/
    .bootstrap-complete.
    """
    sentinel = (
        home
        / ".claude"
        / "plugins"
        / "cache"
        / "marketplace"
        / "pd-plugin"
        / "1.0.0"
        / ".venv"
        / ".bootstrap-complete"
    )
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(content)


def _assert_meta_json_deny(out: dict) -> None:
    """SC1: every deny reason must name all three FR127-2 elements."""
    assert out["permissionDecision"] == "deny", f"expected deny, got {out!r}"
    reason = out["permissionDecisionReason"]
    assert "_project_meta_json" in reason, reason
    assert "PD_META_JSON_WRITE_ALLOWED" in reason, reason
    assert "doctor" in reason, reason


def test_meta_json_deny_no_sentinel(monkeypatch, tmp_path):
    """FR127-1/SC1: no sentinel anywhere -> deny.

    RED-FIRST (design D2 item 1): against the pre-D1 module, `_find_sentinel()`
    finds nothing under the monkeypatched empty HOME and step 2's fail-open
    branch (meta_json_decision.py:86-88, pre-rewrite) returns allow. This
    test must FAIL (allow instead of deny) until the D1 rewrite lands.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PD_META_JSON_WRITE_ALLOWED", raising=False)
    sys.path.insert(0, str(LIB_DIR))
    try:
        from data_file_guards import meta_json_decision  # type: ignore
    finally:
        sys.path.pop(0)
    out = meta_json_decision.decide("docs/features/043/.meta.json", "Write", {})
    _assert_meta_json_deny(out)


def test_meta_json_deny_stale_sentinel(monkeypatch, tmp_path):
    """FR127-1/SC1: sentinel content names a non-executable interpreter -> deny.

    RED-FIRST (design D2 item 2): against the pre-D1 module, `_sentinel_is_valid()`
    returns False for a non-executable interpreter path, so step 3's degraded
    permit (meta_json_decision.py:96-97, pre-rewrite) returns allow. This test
    must FAIL (allow instead of deny) until the D1 rewrite lands.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PD_META_JSON_WRITE_ALLOWED", raising=False)
    _write_sentinel(tmp_path, "/nonexistent/not-a-real-interpreter:3.14.4")
    sys.path.insert(0, str(LIB_DIR))
    try:
        from data_file_guards import meta_json_decision  # type: ignore
    finally:
        sys.path.pop(0)
    out = meta_json_decision.decide("docs/features/043/.meta.json", "Write", {})
    _assert_meta_json_deny(out)


def test_meta_json_deny_valid_sentinel(monkeypatch, tmp_path):
    """FR127-1/SC1: sentinel names a real executable -> deny (regression pin).

    NOT red-first (design D2 item 3): the pre-D1 module already denies here
    (`_sentinel_is_valid` returns True for sys.executable) — cannot flip,
    since it's already the deny outcome. Post-D1, all three sentinel worlds
    share one deny branch; this pins that the deletion left this world's
    outcome unchanged.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PD_META_JSON_WRITE_ALLOWED", raising=False)
    _write_sentinel(tmp_path, f"{sys.executable}:3.14.4")
    sys.path.insert(0, str(LIB_DIR))
    try:
        from data_file_guards import meta_json_decision  # type: ignore
    finally:
        sys.path.pop(0)
    out = meta_json_decision.decide("docs/features/043/.meta.json", "Write", {})
    _assert_meta_json_deny(out)
