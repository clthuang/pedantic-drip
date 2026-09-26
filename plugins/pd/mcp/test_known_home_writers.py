"""W5.6: the test modules that wrote the process HOME leave it alone.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W5 change 6
("Notifications", "Server lifecycle"). A G1 run under a fresh HOME left two
things under its ``.claude/``:

- ``pd/notifications.jsonl``, 14 lines, all from
  ``test_complete_phase_closes.py``: its engine used ``NotificationQueue()``,
  whose default path is ``~/.claude/pd/notifications.jsonl``;
- an empty ``pd/run/``, from ``ui/tests/test_deepened_cli.py`` calling
  ``ui.__main__.main()``, which wrote ``ui_server.pid`` there and removed it
  at exit.

This runs them in a pytest subprocess the way the G1 gate runs them (a
fresh HOME, ``ENTITY_DB_PATH`` unset) and checks that nothing appears under
the fresh HOME's ``.claude/``: the whole notification module, and one of
the CLI module's ``main()`` tests (one whose socket is mocked, so this
never binds a real port).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_KNOWN_WRITERS = (
    str(_PLUGIN_DIR / "mcp" / "test_complete_phase_closes.py"),
    str(_PLUGIN_DIR / "ui" / "tests" / "test_deepened_cli.py")
    + "::test_port_argument_maximum_valid",
)


def test_the_modules_that_wrote_the_process_home_leave_a_fresh_home_alone(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = {key: value for key, value in os.environ.items() if key != "ENTITY_DB_PATH"}
    env["HOME"] = str(home)

    run = subprocess.run(
        [sys.executable, "-m", "pytest", *_KNOWN_WRITERS,
         "-q", "-p", "no:cacheprovider"],
        cwd=str(_PLUGIN_DIR), env=env, capture_output=True, text=True, timeout=600,
    )

    summary = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ""
    assert run.returncode == 0 and " passed" in summary, run.stdout[-3000:] + run.stderr[-3000:]
    written = sorted(
        str(path.relative_to(home)) for path in (home / ".claude").rglob("*")
    ) if (home / ".claude").exists() else []
    assert not (home / ".claude").exists(), written
