"""W5.6: an MCP server's process bookkeeping (its PID file and its
parent-PID watchdog) belongs to the server process, never to a test.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W5 change 6
("Server lifecycle"). Before it, each server's lifespan wrote
``~/.claude/pd/run/<server>.pid`` and started the parent-PID watchdog, and
tests run those lifespans in-process:

- ``server_lifecycle.PID_DIR`` is computed from HOME at import, so a test
  that did not patch it wrote the process HOME's ``run/`` (and removed a
  live server's PID file on the way out);
- the watchdog ``os._exit(0)``s its process when the parent PID changes, so
  it could end a re-parented pytest run: a truncated run reporting success.

Each server's entry point (``if __name__ == "__main__":``) now does the
bookkeeping, and a lifespan does none. So:

- **in-process:** a lifespan writes no PID file and starts no watchdog;
- **a real server** (keep-green, the behaviour it had before): writes its
  PID file under its HOME's ``run/``, removes it on a clean exit, and is
  ended by the watchdog when its parent dies;
- **no test patches** ``PID_DIR``, a watchdog or the PID helpers by hand:
  nothing needs it any more.
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
import server_lifecycle  # noqa: E402
import workflow_state_server  # noqa: E402
from test_create_feature_lanes import (  # noqa: E402
    _ENTITY_SERVER_GLOBALS,
    _WORKFLOW_SERVER_GLOBALS,
    make_pd_repo,
)

_SERVERS = {
    "entity_server": entity_server,
    "workflow_state_server": workflow_state_server,
}
_SERVER_GLOBALS = {
    "entity_server": _ENTITY_SERVER_GLOBALS,
    "workflow_state_server": _WORKFLOW_SERVER_GLOBALS,
}
_START_SECONDS = 60
# start_parent_watchdog polls every 10 seconds.
_WATCHDOG_SECONDS = 40
_PLUGIN_DIR = os.path.normpath(os.path.join(_MCP_DIR, ".."))
# A hand patch of the process bookkeeping: a setattr or mock.patch target
# naming one of these (quoted, with or without a module prefix), or an
# assignment to it. A read such as ``server_lifecycle.PID_DIR / name`` is
# neither.
_BOOKKEEPING_NAMES = (
    "PID_DIR", "start_parent_watchdog", "start_lifetime_watchdog",
    "write_pid", "remove_pid",
)
_HAND_PATCH = re.compile(
    r"[\"'](?:[\w.]*\.)?(?:" + "|".join(_BOOKKEEPING_NAMES) + r")[\"']"
    r"|\.(?:" + "|".join(_BOOKKEEPING_NAMES) + r")\s*=(?!=)"
)


def _parent_watchdogs() -> set[int]:
    return {
        thread.ident for thread in threading.enumerate()
        if thread.name == "parent-watchdog"
    }


def _names_this_process(pid_file: Path) -> bool:
    try:
        return pid_file.read_text().strip() == str(os.getpid())
    except FileNotFoundError:
        return False


def _wait_for(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _real_server_env(tmp_path) -> dict:
    """The environment ``run-*-server.sh`` gives a server, with a temp
    HOME, a temp registry and a temp pd repo as the project."""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    make_pd_repo(project)
    env = {
        key: value for key, value in os.environ.items()
        if key not in ("ENTITY_WORKSPACE_UUID", "WORKSPACE_UUID")
    }
    env.update({
        "HOME": str(home),
        "ENTITY_DB_PATH": str(tmp_path / "registry" / "entities.db"),
        "PROJECT_ROOT": str(project),
        "PYTHONPATH": _HOOKS_LIB,
        "PYTHONUNBUFFERED": "1",
    })
    return env


@pytest.mark.parametrize("server_name", sorted(_SERVERS))
def test_a_lifespan_run_in_process_writes_no_pid_file_and_starts_no_watchdog(tmp_path, monkeypatch, server_name):
    """The lifespan runs against a temp HOME, registry and project, with
    nothing in ``server_lifecycle`` patched. While it runs, the process
    HOME's PID file does not name this process, the temp HOME has no
    ``run/``, and no parent-PID watchdog has started.

    The first and last checks fail on the base. The ``run/`` check holds
    there too, because ``PID_DIR`` is fixed at import; it guards a later
    change that reads HOME at call time, where the first check would look
    in the wrong directory."""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    make_pd_repo(project)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENTITY_DB_PATH", str(tmp_path / "registry" / "entities.db"))
    monkeypatch.setenv("PROJECT_ROOT", str(project))
    monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)
    module = _SERVERS[server_name]
    for name in _SERVER_GLOBALS[server_name]:
        monkeypatch.setattr(module, name, getattr(module, name))
    process_home_pid_file = server_lifecycle.PID_DIR / f"{server_name}.pid"
    watchdogs_before = _parent_watchdogs()
    during = {}

    async def start_and_stop():
        async with module.lifespan(None):
            during["pid_file_names_this_process"] = _names_this_process(process_home_pid_file)
            during["temp_home_has_run_dir"] = (home / ".claude" / "pd" / "run").exists()
            during["new_parent_watchdogs"] = len(_parent_watchdogs() - watchdogs_before)

    asyncio.run(start_and_stop())

    assert during == {
        "pid_file_names_this_process": False,
        "temp_home_has_run_dir": False,
        "new_parent_watchdogs": 0,
    }


@pytest.mark.parametrize("server_name", sorted(_SERVERS))
def test_a_real_server_writes_its_pid_file_under_its_home_and_removes_it_on_exit(tmp_path, server_name):
    """Started as ``run-*-server.sh`` starts it (the script as __main__),
    the server writes its PID into ``$HOME/.claude/pd/run``. When its
    client closes stdin it shuts down cleanly and removes the file."""
    env = _real_server_env(tmp_path)
    pid_file = Path(env["HOME"]) / ".claude" / "pd" / "run" / f"{server_name}.pid"
    stderr_path = tmp_path / f"{server_name}.stderr"
    with open(stderr_path, "wb") as stderr:
        server = subprocess.Popen(
            [sys.executable, os.path.join(_MCP_DIR, f"{server_name}.py")],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=stderr,
            env=env, cwd=env["PROJECT_ROOT"],
        )
    try:
        assert _wait_for(
            lambda: pid_file.exists() and pid_file.read_text().strip() == str(server.pid),
            _START_SECONDS,
        ), stderr_path.read_text()
        server.stdin.close()
        assert server.wait(timeout=_START_SECONDS) == 0, stderr_path.read_text()
        assert not pid_file.exists()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()


# The launcher starts each server with stdin on an inherited pipe, waits for
# every PID file, and exits, orphaning the servers. The test holds the
# pipe's write end, so no server sees end-of-file: only the watchdog can end
# it.
_LAUNCHER = """
import os, subprocess, sys, time
stdin_fd, run_dir, log_dir, scripts = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
names = [os.path.splitext(os.path.basename(script))[0] for script in scripts]
for script, name in zip(scripts, names):
    with open(os.path.join(log_dir, name + ".stderr"), "wb") as stderr:
        subprocess.Popen([sys.executable, script], stdin=stdin_fd,
                         stdout=subprocess.DEVNULL, stderr=stderr)
deadline = time.monotonic() + float(os.environ["LAUNCHER_SECONDS"])
while time.monotonic() < deadline:
    if all(os.path.exists(os.path.join(run_dir, name + ".pid")) for name in names):
        sys.exit(0)
    time.sleep(0.05)
sys.exit(1)
"""


@pytest.mark.slow
def test_the_parent_watchdog_ends_real_servers_whose_parent_died(tmp_path):
    """Both servers' parent exits once their PID files exist. Within the
    watchdog's poll interval each server is gone, and its PID file is
    still there: ``os._exit`` ended it, not a clean shutdown."""
    env = _real_server_env(tmp_path)
    env["LAUNCHER_SECONDS"] = str(_START_SECONDS)
    run_dir = Path(env["HOME"]) / ".claude" / "pd" / "run"
    names = sorted(_SERVERS)
    stdin_read, stdin_write = os.pipe()
    pids: dict[str, int] = {}
    try:
        launcher = subprocess.run(
            [sys.executable, "-c", _LAUNCHER, str(stdin_read), str(run_dir),
             str(tmp_path), *(os.path.join(_MCP_DIR, f"{name}.py") for name in names)],
            pass_fds=(stdin_read,), env=env, cwd=env["PROJECT_ROOT"],
            timeout=_START_SECONDS + 30,
        )
        os.close(stdin_read)
        stdin_read = -1
        logs = {name: (tmp_path / f"{name}.stderr").read_text() for name in names}
        assert launcher.returncode == 0, logs
        pids = {name: int((run_dir / f"{name}.pid").read_text()) for name in names}

        assert _wait_for(
            lambda: not any(_alive(pid) for pid in pids.values()), _WATCHDOG_SECONDS,
        ), {name: _alive(pid) for name, pid in pids.items()}
        assert all((run_dir / f"{name}.pid").exists() for name in names)
    finally:
        if stdin_read != -1:
            os.close(stdin_read)
        os.close(stdin_write)
        for pid in pids.values():
            if _alive(pid):
                os.kill(pid, signal.SIGKILL)


def _test_files_under_the_plugin():
    for directory, subdirectories, files in os.walk(_PLUGIN_DIR):
        subdirectories[:] = [
            name for name in subdirectories
            if name not in (".venv", "__pycache__", "node_modules")
        ]
        for name in files:
            if name.endswith(".py") and (name.startswith("test_") or name == "conftest.py"):
                yield os.path.join(directory, name)


def test_no_test_patches_the_process_bookkeeping_by_hand():
    """Every test file and conftest under the plugin is scanned for a hand
    patch of ``PID_DIR``, a watchdog or the PID helpers. A lifespan and a
    plain ``main()`` touch none of them now, so a patch is dead weight that
    hides whether the structural guarantee still holds."""
    this_file = os.path.abspath(__file__)
    patches = []
    for path in _test_files_under_the_plugin():
        if os.path.abspath(path) == this_file:
            continue
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if _HAND_PATCH.search(line):
                    patches.append(f"{os.path.relpath(path, _PLUGIN_DIR)}:{number}: {line.strip()}")
    assert patches == [], (
        "Lifespans and ui main() no longer write PID files or start watchdogs "
        "(W5.6); delete these patches:\n" + "\n".join(patches)
    )
