"""Fixtures shared by the hook tests under hooks/lib/ and hooks/tests/."""
import json
import os
import subprocess

import pytest

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # plugins/pd


@pytest.fixture
def gate_home(tmp_path):
    """A temporary HOME holding an empty `.claude/pd/gate/`."""
    home = tmp_path / "home"
    (home / ".claude" / "pd" / "gate").mkdir(parents=True)
    return home


@pytest.fixture
def run_hook(gate_home):
    """run_hook(script, payload, env=None) -> (exit code, stderr): pipes the HookInput JSON into the hook."""
    def run(script, payload, env=None):
        full_env = {**os.environ, "HOME": str(gate_home), "CLAUDE_PLUGIN_ROOT": PLUGIN_ROOT, **(env or {})}
        r = subprocess.run(["bash", str(script)], input=json.dumps(payload), capture_output=True, text=True, env=full_env)
        return r.returncode, r.stderr
    return run
