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

**Where git cannot answer** for a ``.git`` file, the checkout may be a
worktree git no longer resolves:

- **orphaned:** a worktree whose ``<main>/.git/worktrees/<name>`` is gone,
  as an orphaned ``.pd-worktrees/*`` directory's is;
- **a .git file naming a missing gitdir,** outside any repository;
- **a failing git** and **a git older than 2.31** (PATH shims), in a healthy
  worktree.

**The scripts under test** are this checkout's ``hooks/lib/common.sh``,
``scripts/doctor.sh``, ``hooks/sync-cache.sh`` and
``hooks/lib/session-start-helpers.sh``, run by bash from the directory a
session starts in, the way the hooks run them.

**Isolation.** Every subprocess gets a temp HOME and no ``GIT_*`` variables.
sync-cache publishes into the cache that HOME's
``.claude/plugins/installed_plugins.json`` names, so the sync-cache tests'
HOME names a temp cache. The session-start tests run against a temp registry.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import shlex
import shutil
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


def _write_executable(path: str, text: str) -> None:
    _write(path, text)
    os.chmod(path, 0o755)


# A git that fails every command.
_FAILING_GIT = "#!/bin/bash\necho 'git: failing on purpose' >&2\nexit 1\n"


def _git_older_than_2_31() -> str:
    """A git older than 2.31: its rev-parse prints an option it does not
    know, ``--path-format=absolute``, back as a line of its own. Every
    other argument goes to the real git."""
    real_git = shutil.which("git")
    assert real_git, "no git on PATH"
    return (
        "#!/bin/bash\n"
        "arguments=()\n"
        'for argument in "$@"; do\n'
        '    if [[ "$argument" == --path-format=* ]]; then\n'
        "        printf '%s\\n' \"$argument\"\n"
        "    else\n"
        '        arguments+=("$argument")\n'
        "    fi\n"
        "done\n"
        f'exec {shlex.quote(real_git)} "${{arguments[@]}}"\n'
    )


def _with_git_shim(base: str, script: str) -> dict[str, str]:
    """Env overrides that put *script* first on PATH as ``git``."""
    shim_dir = os.path.join(base, "git-shim")
    _write_executable(os.path.join(shim_dir, "git"), script)
    return {"PATH": shim_dir + os.pathsep + os.environ["PATH"]}


def _orphan(worktree: str) -> None:
    """Remove a linked worktree's ``<main>/.git/worktrees/<name>``, as an
    orphaned ``.pd-worktrees/*`` directory has lost its: the worktree's
    ``.git`` file then names nothing, and git fails there."""
    with open(os.path.join(worktree, ".git")) as f:
        admin_dir = f.read().strip().removeprefix("gitdir: ")
    shutil.rmtree(admin_dir)


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


def _run_sync_cache(cwd: str, home: str, **env_overrides: str):
    """Run sync-cache.sh as SessionStart does: in *cwd*, with HOME *home*.

    *home* is never the account's home: sync-cache would publish into its
    real plugin cache.
    """
    account_home = pwd.getpwuid(os.getuid()).pw_dir
    assert os.path.realpath(home) != os.path.realpath(account_home), home
    return subprocess.run(
        ["bash", _SYNC_CACHE_SH], cwd=cwd,
        env=_subprocess_env(home, **env_overrides),
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


def _checkout_git_cannot_answer_for(
    shape: str, repository: dict[str, str], tmp_path,
) -> tuple[str, dict[str, str]]:
    """The directory a session starts in for *shape*, a checkout whose
    ``.git`` is a file git cannot answer for, and the env overrides it runs
    under. Each checkout holds a pd plugin of its own."""
    base = os.path.realpath(str(tmp_path))
    if shape == "orphaned nested worktree":
        _orphan(repository["nested"])
        return repository["nested"], {}
    if shape == "git file naming a missing gitdir":
        checkout = os.path.join(base, "dangling")
        missing_gitdir = os.path.join(base, "pruned", ".git", "worktrees", "dangling")
        _write(os.path.join(checkout, ".git"), f"gitdir: {missing_gitdir}\n")
        _write(os.path.join(checkout, "plugins", "pd", ".claude-plugin", "plugin.json"),
               _plugin_json("dangling checkout"))
        return checkout, {}
    git = _FAILING_GIT if shape == "failing git" else _git_older_than_2_31()
    return repository["sibling"], _with_git_shim(base, git)


@pytest.mark.parametrize("shape", [
    "orphaned nested worktree",
    "git file naming a missing gitdir",
    "failing git",
    "git older than 2.31",
])
def test_sync_cache_publishes_nothing_at_a_git_file_git_cannot_answer_for(
    repository, home, tmp_path, shape,
):
    """W4.5 (premortem story 9), where git cannot answer: at a ``.git``
    FILE git cannot answer for, which may be a worktree, sync-cache
    publishes nothing. The failing git and the git older than 2.31 run in
    a healthy sibling worktree.

    Red on 8dcd406a: ``is_linked_worktree`` read git's silence as "not
    linked", so each checkout published its own plugin over the cache. The
    same install, under the same git, then takes the main checkout's
    plugin, so the first half cannot pass on an install nothing publishes
    into.
    """
    install = _install_pd_into(home)
    cache_before = _files_under(install["plugins"])
    start, env_overrides = _checkout_git_cannot_answer_for(shape, repository, tmp_path)

    from_start = _run_sync_cache(start, home, **env_overrides)

    assert from_start.returncode == 0, from_start.stderr
    assert json.loads(from_start.stdout) == _EMPTY_SESSION_START_OUTPUT
    assert _files_under(install["plugins"]) == cache_before

    main = repository["main"]
    from_main = _run_sync_cache(main, home, **env_overrides)

    assert from_main.returncode == 0, from_main.stderr
    assert _read_bytes(install["cache_plugin_json"]) == _read_bytes(
        os.path.join(main, "plugins", "pd", ".claude-plugin", "plugin.json"))


def test_sync_cache_and_the_hook_tests_skip_share_one_decision():
    """W4.5: sync-cache.sh and test-hooks.sh's skip for Tests 13b and 13c ask
    one common.sh helper, ``may_publish_plugin_cache``, so the skip keeps
    matching what sync-cache publishes. The behaviour is pinned above; no
    G1 test runs test-hooks.sh, whose Test 12 publishes into HOME's cache.

    Red on 8dcd406a: both asked ``is_linked_worktree``, which answered
    "not linked" wherever git could not answer.
    """
    sources = {}
    for name, path in (
        ("common", _COMMON_SH),
        ("sync_cache", _SYNC_CACHE_SH),
        ("test_hooks", os.path.join(_HOOKS_DIR, "tests", "test-hooks.sh")),
    ):
        with open(path) as f:
            sources[name] = f.read()

    assert re.search(r"^may_publish_plugin_cache\(\) \{$", sources["common"], re.MULTILINE)
    assert re.search(r'^if ! may_publish_plugin_cache "\$SOURCE_ROOT"; then$',
                     sources["sync_cache"], re.MULTILINE)
    assert re.search(r'^    if ! may_publish_plugin_cache "\$PROJECT_ROOT"; then$',
                     sources["test_hooks"], re.MULTILINE)
    assert [name for name, source in sources.items() if "is_linked_worktree" in source] == []


def test_sync_cache_copies_marketplace_json_only_with_the_pd_plugin(
    repository, home, tmp_path,
):
    """sync-cache copies a checkout's ``.claude-plugin/marketplace.json``
    over pd's marketplace cache only when the checkout holds pd's plugin,
    the check its rsync makes, so another plugin repository's main checkout
    leaves pd's cache alone.

    Red on 8dcd406a: the copy made no such check, so the other repository's
    marketplace.json replaced pd's. The main checkout then publishes it as
    before, so the first half cannot pass on an install nothing publishes
    into.
    """
    install = _install_pd_into(home)
    cache_before = _files_under(install["plugins"])
    env = _subprocess_env(home)
    other = os.path.join(os.path.realpath(str(tmp_path)), "another-plugin-repository")
    _git(env, "init", "-q", "-b", "main", other)
    _write(os.path.join(other, ".claude-plugin", "marketplace.json"),
           json.dumps({"name": "another marketplace"}) + "\n")
    _write(os.path.join(other, "plugins", "another", ".claude-plugin", "plugin.json"),
           json.dumps({"name": "another"}) + "\n")
    _git(env, "-C", other, "add", ".claude-plugin", "plugins")
    _git(env, "-C", other, "commit", "-q", "-m", "another plugin")

    from_other = _run_sync_cache(other, home)

    assert from_other.returncode == 0, from_other.stderr
    assert json.loads(from_other.stdout) == _EMPTY_SESSION_START_OUTPUT
    assert _files_under(install["plugins"]) == cache_before

    main = repository["main"]
    from_main = _run_sync_cache(main, home)

    assert from_main.returncode == 0, from_main.stderr
    assert _read_bytes(install["cache_marketplace_json"]) == _read_bytes(
        os.path.join(main, ".claude-plugin", "marketplace.json"))


def _session_start(project_root: str, db_path: str, home: str, **env_overrides: str) -> dict:
    """Run the orchestrator as session-start.sh does; return its summary."""
    proc = subprocess.run(
        [sys.executable, "-m", _ORCHESTRATOR,
         "--project-root", project_root,
         "--artifacts-root", "docs",
         "--entity-db", db_path],
        cwd=project_root,
        env=_subprocess_env(home, ENTITY_DB_PATH=db_path, PYTHONPATH=_HOOKS_LIB,
                            **env_overrides),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _plugin_root_on_this_interpreter(tmp_path) -> str:
    """A plugin root for ``ensure_workspace_uuid``, which runs
    ``$PLUGIN_ROOT/.venv/bin/python`` on ``$PLUGIN_ROOT/hooks/lib``: its
    ``.venv`` is this test's interpreter's, its ``hooks`` this checkout's."""
    plugin_root = os.path.join(os.path.realpath(str(tmp_path)), "plugin-root")
    os.makedirs(plugin_root)
    os.symlink(sys.prefix, os.path.join(plugin_root, ".venv"))
    os.symlink(_HOOKS_DIR, os.path.join(plugin_root, "hooks"))
    venv_python = os.path.join(plugin_root, ".venv", "bin", "python")
    assert os.access(venv_python, os.X_OK), f"{sys.prefix} holds no bin/python"
    return plugin_root


def _ensure_workspace_uuid(project_root: str, plugin_root: str, env: dict[str, str]):
    """session-start.sh's ``ensure_workspace_uuid "$PROJECT_ROOT"``, run
    in *project_root*."""
    return _bash(
        'source "$1/hooks/lib/common.sh" && '
        'source "$1/hooks/lib/session-start-helpers.sh" && '
        'PLUGIN_ROOT="$1" && '
        'PD_WORKSPACE_PROJECT_ROOT="$2" ensure_workspace_uuid "$2"',
        project_root, env, plugin_root, project_root,
    )


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

    assert _changed_tables(rows_before, rows_after) == [], (
        f"brainstorms (entity_id, status, is_archived): {_brainstorm_states(db_path)}"
    )
    # It ran rooted at the worktree: the older commit holds one brainstorm,
    # registered already, so it skipped one and registered none.
    assert (in_worktree["entity_sync"]["registered"],
            in_worktree["entity_sync"]["skipped"]) == (0, 1), in_worktree
    assert in_worktree["errors"] == [], in_worktree


def _changed_tables(rows_before: dict, rows_after: dict) -> list[str]:
    return sorted(
        table for table in rows_before.keys() | rows_after.keys()
        if rows_before.get(table) != rows_after.get(table)
    )


@pytest.mark.parametrize("shape", ["orphaned", "git older than 2.31"])
def test_session_start_in_a_worktree_git_cannot_answer_for_creates_no_workspace(
    tmp_path, home, shape,
):
    """W4.4, where git cannot answer: a session start in a nested worktree
    whose ``.git`` file git cannot answer for creates no workspace. The worktree
    is orphaned (its ``<main>/.git/worktrees/<name>`` is gone), or healthy
    under a git older than 2.31.

    The repository tracks a ``.claude/`` file, as this one does, so the
    worktree has ``.claude/``. The session takes session-start.sh's identity
    steps: ``detect_project_root``, ``ensure_workspace_uuid``, then the
    orchestrator. Beforehand, the same steps resolve the repository's
    workspace in the worktree while git still answers there.

    Red on 8dcd406a: rooted at the worktree, ``_repository_root`` kept the
    worktree's own path where git could not answer, so
    ``resolve_workspace_uuid`` minted a workspace for it: a second
    workspaces row and ``<worktree>/.claude/pd/workspace.json``.
    """
    env = _subprocess_env(home)
    base = os.path.realpath(str(tmp_path))
    db_path = os.path.join(base, "registry", "entities.db")
    os.makedirs(os.path.dirname(db_path))
    session_env = _subprocess_env(home, ENTITY_DB_PATH=db_path)
    plugin_root = _plugin_root_on_this_interpreter(tmp_path)
    main = os.path.join(base, "repo")
    _git(env, "init", "-q", "-b", "main", main)
    _write(os.path.join(main, ".gitignore"), ".claude/pd/\n")
    _write(os.path.join(main, ".claude", "pd.local.md"), "---\nartifacts_root: docs\n---\n")
    _write(os.path.join(main, "docs", "brainstorms", "20260901-an-idea.prd.md"), "# An idea\n")
    _git(env, "-C", main, "add", ".gitignore", ".claude", "docs")
    _git(env, "-C", main, "commit", "-q", "-m", "a pd project that tracks .claude/")

    in_main = _ensure_workspace_uuid(main, plugin_root, session_env)
    assert in_main.returncode == 0, in_main.stderr
    repository_uuid = in_main.stdout.strip()
    assert _session_start(main, db_path, home)["entity_sync"]["registered"] == 1

    worktree = os.path.join(main, ".pd-worktrees", "task")
    _git(env, "-C", main, "worktree", "add", "-q", "-b", "task", worktree)
    while_git_answers = _ensure_workspace_uuid(
        _detect_project_root(_COMMON_SH, worktree, env), plugin_root, session_env)
    assert (while_git_answers.returncode, while_git_answers.stdout.strip()) == (
        0, repository_uuid)

    if shape == "orphaned":
        _orphan(worktree)
        git_overrides = {}
    else:
        git_overrides = _with_git_shim(base, _git_older_than_2_31())
    root = _detect_project_root(_COMMON_SH, worktree, env)

    assert root == worktree

    rows_before = _registry_rows(db_path)
    ensured = _ensure_workspace_uuid(root, plugin_root, {**session_env, **git_overrides})
    in_worktree = _session_start(root, db_path, home, **git_overrides)
    rows_after = _registry_rows(db_path)

    assert _changed_tables(rows_before, rows_after) == [], (
        f"workspaces: {rows_after.get('workspaces')}")
    assert not os.path.exists(os.path.join(worktree, ".claude", "pd", "workspace.json"))
    assert (ensured.returncode != 0, ensured.stdout) == (True, ""), ensured
    assert [error for error in in_worktree["errors"]
            if "a file git cannot answer for" in error], in_worktree
