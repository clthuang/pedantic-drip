"""W4.4 tests: root detection accepts a ``.git`` file.

Design: ``docs/dev_artifacts/plans/2026-09-25-release-c-followups-design.md``, W4 change 4,
and its Tests ("Root detection").

**The layouts.** Each test builds a temp git repository. Its main checkout's
``.git`` is a directory; a linked worktree's ``.git`` is a file naming
``<main>/.git/worktrees/<name>``. The worktrees are:

- **nested:** under the main checkout, as ``.claude/worktrees/<name>`` and
  ``claude --worktree``'s ``.claude/worktrees/<name>`` are;
- **sibling:** beside the main checkout.

**The script under test** is this checkout's ``hooks/lib/common.sh``, run by
bash from the directory a session starts in, the way the hooks run it.

**Isolation.** Every subprocess gets a temp HOME and no ``GIT_*`` variables.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

_HOOKS_LIB = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_HOOKS_LIB)
_PLUGIN_ROOT = os.path.dirname(_HOOKS_DIR)
_COMMON_SH = os.path.join(_HOOKS_LIB, "common.sh")

# The root finders W4.4 lists, relative to the plugin root. The behavioural
# test below runs common.sh; no test runs the rest, so the sweep test pins them.
_W4_4_ROOT_FINDERS = (
    "hooks/lib/common.sh",
    "hooks/tests/test-hooks.sh",
)

# A bash test that accepts only a .git directory:
# [[ -d "${dir}/.git" ]], [[ ! -d "${root}/.git" ]], [[ ! -d .git ]].
_DIRECTORY_ONLY_GIT_TEST = re.compile(r'\[\[\s*(?:!\s*)?-d\s+"?[^\]"]*\.git"?\s*\]\]')


def _subprocess_env(home: str) -> dict[str, str]:
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


def _detect_project_root(script_path: str, cwd: str, env: dict[str, str]) -> str:
    """``detect_project_root``'s answer in *cwd*, after sourcing *script_path*."""
    proc = subprocess.run(
        ["bash", "-c", 'source "$1" && detect_project_root', "bash", script_path],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def home(tmp_path) -> str:
    path = tmp_path / "home"
    path.mkdir()
    return os.path.realpath(str(path))


@pytest.fixture
def repository(tmp_path, home) -> dict[str, str]:
    """A main checkout with a nested and a sibling linked worktree.

    Paths are real paths: bash reports ``$PWD`` resolved, and macOS's temp
    dir sits behind a symlink.
    """
    env = _subprocess_env(home)
    base = os.path.realpath(str(tmp_path))
    outside = subprocess.run(
        ["git", "-C", base, "rev-parse", "--git-dir"],
        env=env, capture_output=True, text=True,
    )
    assert outside.returncode != 0, (
        f"{base} is inside a git repository: the no-repository case needs "
        "a temp dir outside every repository"
    )
    main = os.path.join(base, "main")
    _git(env, "init", "-q", "-b", "main", main)
    _write(os.path.join(main, "sub", "deeper", "kept.txt"), "kept\n")
    _git(env, "-C", main, "add", "sub")
    _git(env, "-C", main, "commit", "-q", "-m", "a checkout")

    nested = os.path.join(main, ".claude", "worktrees", "nested")
    sibling = os.path.join(base, "sibling")
    _git(env, "-C", main, "worktree", "add", "-q", "-b", "nested", nested)
    _git(env, "-C", main, "worktree", "add", "-q", "-b", "sibling", sibling)

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


def test_root_finders_accept_a_git_file():
    """W4.4 sweep: every root finder the design lists tests ``-e .git``.

    Red on the base: the twelve ``-d`` tests the design lists.
    """
    directory_only_tests = []
    for relative_path in _W4_4_ROOT_FINDERS:
        with open(os.path.join(_PLUGIN_ROOT, relative_path)) as f:
            for number, line in enumerate(f, start=1):
                if _DIRECTORY_ONLY_GIT_TEST.search(line):
                    directory_only_tests.append(f"{relative_path}:{number}: {line.strip()}")
    assert directory_only_tests == []
