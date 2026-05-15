"""Tests for plugins/pd/scripts/pd_state_diff.py (feature 110 Group 14).

Coverage (AC-6.x + Task 14.8 backfilled-entity defense):
  - test_clean_checkout_emits_no_changes (AC-6.1)
  - test_added_entity_marked (AC-6.2)
  - test_missing_base_ref_exits_0 (AC-6.6)
  - test_performance_median_under_500ms (AC-6.5; @pytest.mark.slow)
  - test_backfilled_entity_defense (Task 14.8)
  - test_empty_tree_emits_literal_line (AC-6.4)
  - test_pre_commit_hook_emits_diff_file (AC-6.3)

The script lives at ``plugins/pd/scripts/pd_state_diff.py``. Tests import it
as a module after prepending the scripts dir to ``sys.path`` so we can call
``generate_diff()`` directly (no subprocess per call → fast unit tests).
The pre-commit hook test exercises the bash wrapper end-to-end.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import _UNKNOWN_WORKSPACE_UUID
from entity_registry.test_helpers import make_v12_db


# ---------------------------------------------------------------------------
# Module-loading helper — pd_state_diff lives under plugins/pd/scripts/.
# ---------------------------------------------------------------------------


def _load_pd_state_diff():
    """Import pd_state_diff.py from plugins/pd/scripts/.

    Inserts the scripts dir at sys.path[0] (and removes it on the way out)
    so the import doesn't pollute other tests.
    """
    repo_root = Path(__file__).resolve().parents[4]
    scripts_dir = repo_root / "plugins" / "pd" / "scripts"
    if not (scripts_dir / "pd_state_diff.py").exists():
        # Fallback: walk up to find the worktree root.
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "plugins" / "pd" / "scripts" / "pd_state_diff.py"
            if candidate.exists():
                scripts_dir = candidate.parent
                break
    sys.path.insert(0, str(scripts_dir))
    try:
        if "pd_state_diff" in sys.modules:
            del sys.modules["pd_state_diff"]
        mod = importlib.import_module("pd_state_diff")
        return mod
    finally:
        # Leave it on sys.path so subsequent test functions don't re-import
        # repeatedly; the module is now cached in sys.modules.
        pass


# ---------------------------------------------------------------------------
# Git-repo fixture: temp dir with `git init` + commit on `develop`.
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp git repo with a single commit on a `develop` branch.

    Returns the repo root. cwd is changed to the repo so ``git log``
    inside ``pd_state_diff.generate_diff`` resolves the base.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)

    # Suppress user-config interactions.
    env_overrides = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)

    subprocess.run(["git", "init", "-q", "-b", "develop"], check=True)
    (repo / "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed commit"],
        check=True,
    )
    return repo


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


def _bootstrap_workspace(conn: sqlite3.Connection) -> None:
    """Insert the canonical __unknown__ workspaces row so FK passes."""
    conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            _UNKNOWN_WORKSPACE_UUID,
            "__unknown__",
            None,
            "2026-05-13T00:00:00+00:00",
            "2026-05-13T00:00:00+00:00",
        ),
    )
    conn.commit()


def _insert_entity_raw(
    conn: sqlite3.Connection,
    *,
    entity_id: str,
    name: str,
    kind: str = "feature",
    created_at: str = "2026-05-13T00:00:00+00:00",
    updated_at: str | None = None,
    status: str = "active",
    parent_uuid: str | None = None,
) -> str:
    """INSERT a row into entities directly (bypasses register_entity).

    Returns the entity uuid.
    """
    entity_uuid = str(_uuid.uuid4())
    type_id = f"{kind}:{entity_id}"
    updated_at = updated_at or created_at
    _bootstrap_workspace(conn)
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, kind, entity_id, name, status, "
        "parent_uuid, artifact_path, created_at, updated_at, metadata, "
        "type, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entity_uuid, _UNKNOWN_WORKSPACE_UUID, type_id, kind, entity_id,
            name, status, parent_uuid, None, created_at, updated_at, None,
            "work", "feature_flow",
        ),
    )
    conn.commit()
    return entity_uuid


def _insert_phase_event(
    conn: sqlite3.Connection,
    *,
    type_id: str,
    event_type: str,
    timestamp: str,
    metadata: dict | None = None,
    phase: str | None = None,
    project_id: str = "__unknown__",
) -> None:
    """INSERT a phase_events row directly."""
    md_json = json.dumps(metadata) if metadata is not None else None
    conn.execute(
        "INSERT INTO phase_events "
        "(type_id, project_id, phase, event_type, timestamp, "
        " source, created_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            type_id, project_id, phase, event_type, timestamp,
            "live", timestamp, md_json,
        ),
    )
    conn.commit()


@pytest.fixture
def empty_db(tmp_path: Path) -> Path:
    """v12 schema DB at tmp_path/empty.db (zero entities)."""
    db_path = tmp_path / "empty.db"
    conn = make_v12_db(db_path)
    _bootstrap_workspace(conn)
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_clean_checkout_emits_no_changes(
    tmp_git_repo: Path,
    empty_db: Path,
) -> None:
    """AC-6.1: clean checkout (no changes vs base) → literal no-changes line."""
    mod = _load_pd_state_diff()
    out = mod.generate_diff(base="develop", db_path=str(empty_db))
    assert "No entity state changes vs develop" in out, (
        f"expected literal no-changes line; got: {out!r}"
    )


def test_added_entity_marked(
    tmp_git_repo: Path,
    tmp_path: Path,
) -> None:
    """AC-6.2: entity created AFTER base_commit_ts is marked (added)."""
    db_path = tmp_path / "added.db"
    conn = make_v12_db(db_path)

    # The base commit was made just now in tmp_git_repo. To guarantee
    # the entity's created_at falls AFTER base_commit_ts even with
    # second-granularity clocks, force a far-future created_at.
    _insert_entity_raw(
        conn,
        entity_id="999-new-feature",
        name="Brand new feature",
        kind="feature",
        created_at="2999-12-31T23:59:59+00:00",
    )
    conn.close()

    mod = _load_pd_state_diff()
    out = mod.generate_diff(base="develop", db_path=str(db_path))
    assert "(added)" in out, f"expected (added) marker; got:\n{out}"
    assert "feature:999-new-feature" in out, (
        f"expected new entity type_id in output; got:\n{out}"
    )
    # Header present.
    assert out.startswith("# pd-state diff vs develop"), (
        f"expected header line first; got:\n{out}"
    )
    # Total counts include 1 added.
    assert "1 added" in out, f"expected '1 added' in totals; got:\n{out}"


def test_missing_base_ref_exits_0(
    tmp_git_repo: Path,
    empty_db: Path,
) -> None:
    """AC-6.6: missing base ref → unavailable line, exit 0 (no exception)."""
    mod = _load_pd_state_diff()
    out = mod.generate_diff(base="nonexistent-branch", db_path=str(empty_db))
    assert "pd-state diff unavailable: base ref 'nonexistent-branch' not found" in out, (
        f"expected base-ref unavailable line; got: {out!r}"
    )

    # And confirm the CLI exit code is 0.
    repo_root = Path(__file__).resolve().parents[4]
    script = repo_root / "plugins" / "pd" / "scripts" / "pd_state_diff.py"
    if not script.exists():
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "plugins" / "pd" / "scripts" / "pd_state_diff.py"
            if candidate.exists():
                script = candidate
                break
    result = subprocess.run(
        [
            sys.executable, str(script),
            "--base", "nonexistent-branch",
            "--db", str(empty_db),
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"expected exit 0 on missing base ref; got rc={result.returncode}, "
        f"stderr={result.stderr!r}"
    )


def test_empty_tree_emits_literal_line(
    tmp_git_repo: Path,
    empty_db: Path,
) -> None:
    """AC-6.4: empty DB (no entities) → literal no-changes line."""
    mod = _load_pd_state_diff()
    out = mod.generate_diff(base="develop", db_path=str(empty_db))
    # The literal line per AC-6.4 (substring match — allow trailing newline).
    assert out.rstrip() == "No entity state changes vs develop", (
        f"expected exactly the literal line; got: {out!r}"
    )


def test_backfilled_entity_defense(
    tmp_git_repo: Path,
    tmp_path: Path,
) -> None:
    """Task 14.8: entity with created_at < base_ts AND NO entity_created
    event → treated as no-change (NOT emitted)."""
    db_path = tmp_path / "backfilled.db"
    conn = make_v12_db(db_path)

    # Entity created BEFORE base commit (relative to far-past created_at).
    _insert_entity_raw(
        conn,
        entity_id="001-backfilled",
        name="Backfilled entity",
        kind="feature",
        created_at="2000-01-01T00:00:00+00:00",
    )
    # No phase_events row inserted → no entity_created event exists.

    conn.close()

    mod = _load_pd_state_diff()
    out = mod.generate_diff(base="develop", db_path=str(db_path))
    # Defense applied → no row for this entity → literal no-changes line.
    assert "No entity state changes vs develop" in out, (
        f"backfilled entity should NOT emit a row; got:\n{out}"
    )
    assert "001-backfilled" not in out, (
        f"backfilled entity uuid should NOT appear; got:\n{out}"
    )


@pytest.mark.slow
def test_performance_median_under_500ms(
    tmp_git_repo: Path,
    tmp_path: Path,
) -> None:
    """AC-6.5: median-of-5 wall-clock < 500ms on 500-row DB. No run > 1500ms.

    Pattern modeled on bench-session-start.sh:
      - 1 warm-up call (discarded)
      - 5 timed calls
      - Assert median < 500ms AND max < 1500ms.
    """
    db_path = tmp_path / "bench.db"
    conn = make_v12_db(db_path)
    _bootstrap_workspace(conn)
    # Seed 500 entities. All BEFORE base ref (no events) → backfilled defense
    # triggers on every row, exercising the hot loop fully.
    for i in range(500):
        _insert_entity_raw(
            conn,
            entity_id=f"{i:05d}-bench-entity",
            name=f"Bench {i}",
            kind="feature" if i % 3 != 0 else "backlog",
            created_at="2000-01-01T00:00:00+00:00",
        )
    conn.close()

    mod = _load_pd_state_diff()

    # Warm-up — JIT caches, module imports, FS read-ahead.
    mod.generate_diff(base="develop", db_path=str(db_path))

    timings_ms: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        mod.generate_diff(base="develop", db_path=str(db_path))
        t1 = time.perf_counter()
        timings_ms.append((t1 - t0) * 1000)

    timings_ms.sort()
    median = timings_ms[2]
    worst = timings_ms[-1]

    assert worst < 1500, (
        f"hard outlier cap exceeded: worst={worst:.1f}ms, "
        f"timings_ms={timings_ms}"
    )
    assert median < 500, (
        f"median exceeded 500ms: median={median:.1f}ms, "
        f"timings_ms={timings_ms}"
    )


# ---------------------------------------------------------------------------
# Pre-commit hook integration (AC-6.3, Task 14.7)
# ---------------------------------------------------------------------------


def test_pre_commit_hook_emits_diff_file(
    tmp_git_repo: Path,
    empty_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6.3: pre-commit-guard.sh invokes pd_state_diff.py and writes
    pd-state.diff.md at the project root.

    Strategy: invoke pre-commit-guard.sh with a synthetic Bash/git commit
    stdin, with cwd == tmp_git_repo. Hook MUST write pd-state.diff.md to
    PROJECT_ROOT. Hook MUST NOT block (exit 0) even if pd_state_diff fails.

    Per Task 14.7 DoD: synthetic stdin = Bash tool + git commit command;
    after invocation, ``pd-state.diff.md`` exists at repo root.
    """
    # Locate the hook script (worktree-aware).
    repo_root = Path(__file__).resolve().parents[4]
    hook = repo_root / "plugins" / "pd" / "hooks" / "pre-commit-guard.sh"
    if not hook.exists():
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "plugins" / "pd" / "hooks" / "pre-commit-guard.sh"
            if candidate.exists():
                hook = candidate
                break
    assert hook.exists(), f"hook not found: {hook}"

    # Stage a .claude/pd.local.md inside the temp repo so the base_branch
    # parser resolves to 'develop' (matching the actual repo config).
    claude_dir = tmp_git_repo / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "pd.local.md").write_text(
        "---\nbase_branch: develop\n---\n", encoding="utf-8",
    )

    # Synthetic Bash hook stdin (matches Claude Code PreToolUse format).
    stdin_payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test'"},
    })

    env = os.environ.copy()
    env["ENTITY_DB_PATH"] = str(empty_db)
    # PROJECT_ROOT detection inside the hook uses git; the repo is fresh.

    result = subprocess.run(
        ["bash", str(hook)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_git_repo),
        timeout=30,
    )
    # Hook MUST NOT block — exit 0 regardless.
    assert result.returncode == 0, (
        f"hook returned non-zero rc={result.returncode}; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    diff_md = tmp_git_repo / "pd-state.diff.md"
    assert diff_md.exists(), (
        f"hook did not write pd-state.diff.md; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    content = diff_md.read_text(encoding="utf-8")
    # Either the no-changes line OR a diff table. Both are valid passes.
    assert (
        "No entity state changes vs develop" in content
        or content.startswith("# pd-state diff vs develop")
        or "pd-state diff unavailable" in content
    ), f"unexpected content in pd-state.diff.md:\n{content}"
