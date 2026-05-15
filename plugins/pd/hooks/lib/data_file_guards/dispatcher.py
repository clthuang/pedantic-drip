"""Dispatcher entry point for the generalized data-file guard (feature 110).

Reads stdin JSON describing a PreToolUse event, looks up the file_path against
a config-driven pattern table, and delegates the allow/deny decision to a
per-pattern decision module.

Contract (design §4.3):
    main() reads stdin -> emits hook JSON to stdout -> exits 0.

Path semantics:
    - Config path defaults to plugins/pd/hooks/data_file_guards.json (relative to
      CLAUDE_PLUGIN_ROOT or PWD), overridable via PD_DATA_FILE_GUARDS_CONFIG.
    - Decision module import root defaults to plugins/pd/hooks/lib,
      overridable via PD_DATA_FILE_GUARDS_LIB.
    - Patterns use fnmatch.fnmatch semantics (Python 3.12 floor; no `**`).
"""
from __future__ import annotations

import fnmatch
import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})
_DEFAULT_CONFIG_REL = "plugins/pd/hooks/data_file_guards.json"
_DEFAULT_LIB_REL = "plugins/pd/hooks/lib"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Resolve the project root for path defaults.

    Prefers CLAUDE_PLUGIN_ROOT (when set, falls back to its parent if it
    appears to point inside the plugin). Otherwise uses the current working
    directory. Both branches are project-aware — no hardcoded paths.
    """
    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root_env:
        p = Path(plugin_root_env).resolve()
        # If CLAUDE_PLUGIN_ROOT points at plugins/pd, project root is two up.
        if p.name == "pd" and p.parent.name == "plugins":
            return p.parent.parent
        return p
    return Path(os.environ.get("PWD", os.getcwd())).resolve()


def _resolve_path(env_val: str | None, default_rel: str) -> Path:
    """Resolve a config path: absolute -> as-is; relative -> joined to project root."""
    raw = env_val if env_val else default_rel
    p = Path(raw)
    if p.is_absolute():
        return p
    return _project_root() / p


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> list[dict[str, Any]]:
    """Load and parse the guard config. Returns [] if missing (fail-open)."""
    if not config_path.is_file():
        return []
    try:
        with config_path.open() as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        # Fail-open: a malformed config should not block writes. The data-file
        # guard is a defense-in-depth measure, not the source of truth.
        return []
    if not isinstance(data, list):
        return []
    return data


# ---------------------------------------------------------------------------
# Module import (TD-3: sys.path.insert + pop, via context manager)
# ---------------------------------------------------------------------------

@contextmanager
def _prepended_path(p: str) -> Iterator[None]:
    """Insert p at sys.path[0] for the duration of the context, then pop it."""
    sys.path.insert(0, p)
    try:
        yield
    finally:
        # Safe: we inserted at index 0, no other thread mutated in between
        # (this is a one-shot CLI invocation).
        if sys.path and sys.path[0] == p:
            sys.path.pop(0)


def _invoke_decision(
    module_name: str,
    lib_dir: Path,
    file_path: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Import the decision module and call its decide() function."""
    with _prepended_path(str(lib_dir)):
        module = importlib.import_module(module_name)
    return module.decide(file_path, tool_name, tool_input)


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------

def _emit(obj: dict[str, Any]) -> None:
    json.dump(obj, sys.stdout)
    sys.stdout.write("\n")


def _emit_allow() -> None:
    _emit({})


def _emit_decision(decision: dict[str, Any]) -> None:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision.get("permissionDecision", "allow"),
            "permissionDecisionReason": decision.get("permissionDecisionReason", ""),
        }
    }
    _emit(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Entry point: read stdin, dispatch, emit, exit 0."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _emit_allow()
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""

    if tool_name not in _WRITE_TOOLS:
        _emit_allow()
        return 0

    config_path = _resolve_path(os.environ.get("PD_DATA_FILE_GUARDS_CONFIG"), _DEFAULT_CONFIG_REL)
    lib_dir = _resolve_path(os.environ.get("PD_DATA_FILE_GUARDS_LIB"), _DEFAULT_LIB_REL)

    config = load_config(config_path)

    for entry in config:
        pattern = entry.get("pattern", "")
        if not pattern:
            continue
        if not fnmatch.fnmatch(file_path, pattern):
            continue
        excludes = entry.get("exclude_patterns") or []
        if any(fnmatch.fnmatch(file_path, ex) for ex in excludes):
            continue
        module_name = entry.get("decision_module", "")
        if not module_name:
            continue
        try:
            decision = _invoke_decision(module_name, lib_dir, file_path, tool_name, tool_input)
        except Exception:
            # Fail-open on decision module errors (per R6 pattern).
            _emit_allow()
            return 0
        _emit_decision(decision)
        return 0

    _emit_allow()
    return 0


if __name__ == "__main__":
    sys.exit(main())
