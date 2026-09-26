"""W4.4-W4.5 tests: root detection accepts a ``.git`` file, and sync-cache
publishes only from a main checkout.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W4 changes 4
and 5, and its Tests ("Root detection", "No archive from a worktree root",
"sync-cache").

**The layouts.** Each test builds a temp git repository. Its main checkout's
``.git`` is a directory; a linked worktree's ``.git`` is a file naming
``<main>/.git/worktrees/<name>``. The worktrees are:

- **nested:** under the main checkout, as ``.pd-worktrees/<name>`` and
  ``claude --worktree``'s ``.claude/worktrees/<name>`` are;
- **sibling:** beside the main checkout.

**The scripts under test** are this checkout's ``hooks/lib/common.sh``,
``scripts/doctor.sh`` and ``hooks/sync-cache.sh``, run by bash from the
directory a session starts in, the way the hooks run them.

**Isolation.** Every subprocess gets a temp HOME and no ``GIT_*`` variables.
sync-cache publishes into the cache that HOME's
``.claude/plugins/installed_plugins.json`` names, so the sync-cache test's
HOME names a temp cache. The session-start test runs against a temp registry.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import sqlite3
import subprocess
import sys

import pytest

_HOOKS_LIB = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_HOOKS_LIB)
_PLUGIN_ROOT = os.path.dirname(_HOOKS_DIR)
_COMMON_SH = os.path.join(_HOOKS_LIB, "common.sh")
_DOCTOR_SH = os.path.join(_PLUGIN_ROOT, "scripts", "doctor.sh")
_SYNC_CACHE_SH = os.path.join(_HOOKS_DIR, "sync-cache.sh")
_ORCHESTRATOR = "reconciliation_orchestrator"

# sync-cache.sh's stdout on every path: an empty SessionStart context.
_EMPTY_SESSION_START_OUTPUT = {
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ""},
}

# The root finders W4.4 lists, relative to the plugin root. The behavioural
# tests below run common.sh and doctor.sh's check_project_context; no test
# runs the rest, so the sweep test pins them.
_W4_4_ROOT_FINDERS = (
    "hooks/lib/common.sh",
    "scripts/doctor.sh",
    "scripts/setup.sh",
    "hooks/tests/test-hooks.sh",
    "hooks/tests/test-data-file-guard.sh",
    "hooks/tests/test-promptimize-content.sh",
    "hooks/tests/test-enriched-docs-content.sh",
    "hooks/tests/test-worktree-dispatch.sh",
)

# A bash test that accepts only a .git directory:
# [[ -d "${dir}/.git" ]], [[ ! -d "${root}/.git" ]], [[ ! -d .git ]].
_DIRECTORY_ONLY_GIT_TEST = re.compile(r'\[\[\s*(?:!\s*)?-d\s+"?[^\]"]*\.git"?\s*\]\]')


def _subprocess_env(home: str, **overrides: str) -> dict[str, str]:
    """The test process's environment, with a temp HOME and no git overrides.

    - ``GIT_*`` variables (set when pytest runs inside a git hook) would point
      git at another repository;
    - a stale ``PWD`` would stand in for the directory bash starts in;
    - the workspace overrides would bypass the resolver a session start runs.
    """
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
        and key not in ("PWD", "OLDPWD", "ENTITY_WORKSPACE_UUID", "WORKSPACE_UUID")
    }
    env["HOME"] = home
    env.update(overrides)
    return env


def _git(env: dict[str, str], *args: str) -> str:
    """git with a fixed identity and no signing; returns stripped stdout."""
    proc = subprocess.run(
        ["git", "-c", "user.name=w4", "-c", "user.email=w4@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        env=env, check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _bash(script: str, cwd: str, env: dict[str, str], *args: str):
    """Run *script* with bash in *cwd*; *args* are its ``$1``, ``$2``..."""
    return subprocess.run(
        ["bash", "-c", script, "bash", *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=60,
    )


def _detect_project_root(script_path: str, cwd: str, env: dict[str, str]) -> str:
    """``detect_project_root``'s answer in *cwd*, after sourcing *script_path*."""
    proc = _bash('source "$1" && detect_project_root', cwd, env, script_path)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _plugin_json(source: str) -> str:
    """A plugin.json that names the checkout it was written in."""
    return json.dumps({"name": "pd", "source": source}) + "\n"


@pytest.fixture
def home(tmp_path) -> str:
    path = tmp_path / "home"
    path.mkdir()
    return os.path.realpath(str(path))


@pytest.fixture
def repository(tmp_path, home) -> dict[str, str]:
    """A main checkout with a nested and a sibling linked worktree.

    Each checkout holds a pd plugin whose ``plugin.json`` names that checkout
    (the worktrees' as uncommitted edits), so the cache shows which one
    sync-cache published. Paths are real paths: bash reports ``$PWD``
    resolved, and macOS's temp dir sits behind a symlink.
    """
    env = _subprocess_env(home)
    base = os.path.realpath(str(tmp_path))
    outside = subprocess.run(
        ["git", "-C", base, "rev-parse", "--git-dir"],
        env=env, capture_output=True, text=True,
    )
    assert outside.returncode != 0, (
        f"{base} is inside a git repository: the no-repository cases need "
        "a temp dir outside every repository"
    )
    main = os.path.join(base, "main")
    _git(env, "init", "-q", "-b", "main", main)
    _write(os.path.join(main, "sub", "deeper", "kept.txt"), "kept\n")
    _write(os.path.join(main, "plugins", "pd", ".claude-plugin", "plugin.json"),
           _plugin_json("main checkout"))
    _write(os.path.join(main, ".claude-plugin", "marketplace.json"),
           json.dumps({"name": "main checkout marketplace"}) + "\n")
    _git(env, "-C", main, "add", "sub", "plugins", ".claude-plugin")
    _git(env, "-C", main, "commit", "-q", "-m", "a pd plugin")

    nested = os.path.join(main, ".pd-worktrees", "nested")
    sibling = os.path.join(base, "sibling")
    _git(env, "-C", main, "worktree", "add", "-q", "-b", "nested", nested)
    _git(env, "-C", main, "worktree", "add", "-q", "-b", "sibling", sibling)
    for name, worktree in (("nested", nested), ("sibling", sibling)):
        _write(os.path.join(worktree, "plugins", "pd", ".claude-plugin", "plugin.json"),
               _plugin_json(f"{name} worktree"))

    no_repository = os.path.join(base, "no-repository", "deeper")
    os.makedirs(no_repository)
    return {
        "main": main, "nested": nested, "sibling": sibling,
        "no_repository": no_repository,
    }


def test_detect_project_root_answers_a_nested_worktree_root(repository, home):
    """W4.4, "Root detection": in a nested linked worktree,
    ``detect_project_root`` answers the worktree's root, from its root and
    from a subdirectory.

    Red on the base: ``-d .git`` skips the worktree's ``.git`` file, so a
    nested worktree walks on to the main checkout, and a sibling worktree's
    subdirectory falls back to ``$PWD``. The main checkout and a directory
    outside any repository answer as before.
    """
    env = _subprocess_env(home)
    main, nested, sibling = (repository[key] for key in ("main", "nested", "sibling"))
    start_and_expected_root = {
        "nested worktree root": (nested, nested),
        "nested worktree subdirectory": (os.path.join(nested, "sub", "deeper"), nested),
        "sibling worktree subdirectory": (os.path.join(sibling, "sub", "deeper"), sibling),
        "main checkout root": (main, main),
        "main checkout subdirectory": (os.path.join(main, "sub", "deeper"), main),
        "outside any repository": (repository["no_repository"], repository["no_repository"]),
    }

    answered = {
        label: _detect_project_root(_COMMON_SH, start, env)
        for label, (start, _) in start_and_expected_root.items()
    }

    assert answered == {
        label: expected for label, (_, expected) in start_and_expected_root.items()
    }


def test_doctor_roots_a_nested_worktree_at_the_worktree(repository, home):
    """W4.4, one copy: ``doctor.sh`` sources common.sh's
    ``detect_project_root`` and counts a ``.git`` file as a git project.

    Red on the base: doctor.sh keeps its own ``-d`` copy, so in a nested
    worktree it roots at the main checkout and reports that as the project.
    """
    nested = repository["nested"]
    proc = _bash(
        'source "$1" && detect_project_root && check_project_context',
        nested, _subprocess_env(home), _DOCTOR_SH,
    )

    assert proc.returncode == 0, proc.stderr
    root, _, report = proc.stdout.partition("\n")
    assert root == nested
    assert f"Git project: {nested}" in report
    assert "Not inside a git project" not in report


def test_root_finders_accept_a_git_file():
    """W4.4 sweep: every root finder the design lists tests ``-e .git``, and
    ``doctor.sh`` keeps no copy of ``detect_project_root``.

    Red on the base: the twelve ``-d`` tests the design lists, and doctor.sh's
    own copy.
    """
    directory_only_tests = []
    for relative_path in _W4_4_ROOT_FINDERS:
        with open(os.path.join(_PLUGIN_ROOT, relative_path)) as f:
            for number, line in enumerate(f, start=1):
                if _DIRECTORY_ONLY_GIT_TEST.search(line):
                    directory_only_tests.append(f"{relative_path}:{number}: {line.strip()}")
    with open(_DOCTOR_SH) as f:
        doctor_source = f.read()

    assert directory_only_tests == []
    assert not re.search(r"^\s*detect_project_root\s*\(\)", doctor_source, re.MULTILINE)
    assert re.search(r'^source "\$\{PLUGIN_ROOT\}/hooks/lib/common\.sh"$',
                     doctor_source, re.MULTILINE)


def _install_pd_into(home: str) -> dict[str, str]:
    """A pd install in *home*: ``installed_plugins.json`` naming a temp cache,
    whose plugin and marketplace files hold stale content."""
    plugins = os.path.join(home, ".claude", "plugins")
    cache_plugin = os.path.join(plugins, "cache", "test-marketplace", "pd", "1.0.0")
    cache_marketplace_json = os.path.join(
        plugins, "marketplaces", "test-marketplace", ".claude-plugin", "marketplace.json",
    )
    _write(os.path.join(cache_plugin, ".claude-plugin", "plugin.json"), _plugin_json("stale cache"))
    _write(cache_marketplace_json, json.dumps({"name": "stale marketplace"}) + "\n")
    _write(os.path.join(plugins, "installed_plugins.json"), json.dumps({
        "version": 2,
        "plugins": {"pd@test-marketplace": [
            {"scope": "user", "installPath": cache_plugin, "version": "1.0.0"},
        ]},
    }))
    return {
        "plugins": plugins,
        "cache_plugin_json": os.path.join(cache_plugin, ".claude-plugin", "plugin.json"),
        "cache_marketplace_json": cache_marketplace_json,
    }


def _files_under(root: str) -> dict[str, bytes]:
    """Every file under *root*, by relative path, with its bytes."""
    files = {}
    for directory, _, names in os.walk(root):
        for name in names:
            path = os.path.join(directory, name)
            files[os.path.relpath(path, root)] = _read_bytes(path)
    return files


def _run_sync_cache(cwd: str, home: str):
    """Run sync-cache.sh as SessionStart does: in *cwd*, with HOME *home*.

    *home* is never the account's home: sync-cache would publish into its
    real plugin cache.
    """
    account_home = pwd.getpwuid(os.getuid()).pw_dir
    assert os.path.realpath(home) != os.path.realpath(account_home), home
    return subprocess.run(
        ["bash", _SYNC_CACHE_SH], cwd=cwd, env=_subprocess_env(home),
        capture_output=True, text=True, timeout=60,
    )


@pytest.mark.parametrize("worktree", ["sibling", "nested"])
def test_sync_cache_publishes_nothing_from_a_linked_worktree(
    repository, home, tmp_path, worktree,
):
    """W4.5, "sync-cache": run from a linked worktree, sync-cache publishes
    nothing.

    Red on the base: from the sibling worktree it publishes the worktree's
    plugin (its root falls back to ``$PWD``); from the nested one it
    publishes the main checkout's (``-d .git`` walks on to it). The same
    install then takes the main checkout's plugin, and a ``git archive``
    export's, as before, so the first half cannot pass on an install nothing
    publishes into.
    """
    install = _install_pd_into(home)
    cache_before = _files_under(install["plugins"])

    from_worktree = _run_sync_cache(repository[worktree], home)

    assert from_worktree.returncode == 0, from_worktree.stderr
    assert json.loads(from_worktree.stdout) == _EMPTY_SESSION_START_OUTPUT
    assert _files_under(install["plugins"]) == cache_before

    main = repository["main"]
    from_main = _run_sync_cache(main, home)

    assert from_main.returncode == 0, from_main.stderr
    assert json.loads(from_main.stdout) == _EMPTY_SESSION_START_OUTPUT
    assert _read_bytes(install["cache_plugin_json"]) == _read_bytes(
        os.path.join(main, "plugins", "pd", ".claude-plugin", "plugin.json"))
    assert _read_bytes(install["cache_marketplace_json"]) == _read_bytes(
        os.path.join(main, ".claude-plugin", "marketplace.json"))

    export = os.path.join(os.path.realpath(str(tmp_path)), "export")
    os.makedirs(export)
    archive = subprocess.run(
        ["git", "-C", main, "archive", "HEAD"],
        env=_subprocess_env(home), capture_output=True, check=True,
    )
    subprocess.run(["tar", "-x", "-C", export], input=archive.stdout, check=True)
    _write(install["cache_plugin_json"], _plugin_json("stale cache"))
    from_export = _run_sync_cache(export, home)

    assert from_export.returncode == 0, from_export.stderr
    assert _read_bytes(install["cache_plugin_json"]) == _read_bytes(
        os.path.join(export, "plugins", "pd", ".claude-plugin", "plugin.json"))


def _session_start(project_root: str, db_path: str, home: str) -> dict:
    """Run the orchestrator as session-start.sh does; return its summary."""
    proc = subprocess.run(
        [sys.executable, "-m", _ORCHESTRATOR,
         "--project-root", project_root,
         "--artifacts-root", "docs",
         "--entity-db", db_path],
        cwd=project_root,
        env=_subprocess_env(home, ENTITY_DB_PATH=db_path, PYTHONPATH=_HOOKS_LIB),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _registry_rows(db_path: str) -> dict[str, list[str]]:
    """Every row of every registry table, by table, in a stable order."""
    conn = sqlite3.connect(db_path)
    try:
        tables = [name for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {
            table: sorted(map(repr, conn.execute(f'SELECT * FROM "{table}"')))
            for table in tables
        }
    finally:
        conn.close()


def _brainstorm_states(db_path: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT entity_id, status, is_archived FROM entities "
            "WHERE kind = 'brainstorm' ORDER BY entity_id").fetchall()
    finally:
        conn.close()


def test_session_start_in_an_older_nested_worktree_changes_no_row(tmp_path, home):
    """W4.4, "No archive from a worktree root" (premortem story 1): a session
    start in a nested worktree based on an older commit, rooted at the
    worktree, changes no registry row.

    It takes session-start.sh's two steps: ``detect_project_root`` from the
    directory the session starts in (its ``PROJECT_ROOT``), then the
    orchestrator with that root (``run_reconciliation``).

    - **Red on the base,** at the root: ``-d .git`` roots the session at the
      main checkout.
    - **Passes only with Phase 1 in:** on Phase 1's parent, with the ``-e``
      edit, the orchestrator archives the brainstorm the older commit lacks.
    """
    env = _subprocess_env(home)
    db_path = os.path.join(os.path.realpath(str(tmp_path)), "registry", "entities.db")
    os.makedirs(os.path.dirname(db_path))
    main = os.path.join(os.path.realpath(str(tmp_path)), "repo")
    _git(env, "init", "-q", "-b", "main", main)
    os.makedirs(os.path.join(main, ".claude"))  # pd-enabled: the workspace resolves
    brainstorms = os.path.join(main, "docs", "brainstorms")
    _write(os.path.join(brainstorms, "20260901-old-idea.prd.md"), "# Old idea\n")
    _git(env, "-C", main, "add", "docs")
    _git(env, "-C", main, "commit", "-q", "-m", "older")
    older_commit = _git(env, "-C", main, "rev-parse", "HEAD")
    _write(os.path.join(brainstorms, "20261201-new-idea.prd.md"), "# New idea\n")
    _git(env, "-C", main, "add", "docs")
    _git(env, "-C", main, "commit", "-q", "-m", "newer")

    in_main_checkout = _session_start(main, db_path, home)
    assert in_main_checkout["entity_sync"]["registered"] == 2, in_main_checkout

    worktree = os.path.join(main, ".claude", "worktrees", "older")
    _git(env, "-C", main, "worktree", "add", "-q", "--detach", worktree, older_commit)
    root = _detect_project_root(_COMMON_SH, worktree, env)

    assert root == worktree

    rows_before = _registry_rows(db_path)
    in_worktree = _session_start(root, db_path, home)
    rows_after = _registry_rows(db_path)

    changed_tables = sorted(
        table for table in rows_before.keys() | rows_after.keys()
        if rows_before.get(table) != rows_after.get(table)
    )
    assert changed_tables == [], (
        f"brainstorms (entity_id, status, is_archived): {_brainstorm_states(db_path)}"
    )
    # It ran rooted at the worktree: the older commit holds one brainstorm,
    # registered already, so it skipped one and registered none.
    assert (in_worktree["entity_sync"]["registered"],
            in_worktree["entity_sync"]["skipped"]) == (0, 1), in_worktree
    assert in_worktree["errors"] == [], in_worktree
