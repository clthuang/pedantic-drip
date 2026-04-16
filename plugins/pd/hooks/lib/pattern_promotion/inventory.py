"""Inventory helpers: list skills / agents / commands in the pd plugin.

Two-location glob per CLAUDE.md "Plugin portability" principle:
  1. Primary: `~/.claude/plugins/cache/*/pd*/*/...` (installed plugin)
  2. Fallback: `plugins/pd/...` from a caller-provided project root
     (dev workspace).

Callers in production use `primary`. Tests pass an explicit
`plugin_root` overriding both, keeping them hermetic.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path


PRIMARY_GLOB = os.path.expanduser("~/.claude/plugins/cache/*/pd*/*")
FALLBACK_REL = Path("plugins/pd")


def _resolve_plugin_root(
    plugin_root: Path | None, project_root: Path | None
) -> Path:
    """Resolve the pd plugin root directory.

    Precedence: explicit plugin_root > primary cache glob > project_root fallback.
    """
    if plugin_root is not None:
        return plugin_root

    # Primary: first match of the installed-plugin cache glob.
    matches = sorted(glob.glob(PRIMARY_GLOB))
    for m in matches:
        p = Path(m)
        if p.is_dir() and (p / "skills").is_dir():
            return p

    # Fallback: caller-provided project root (or cwd).
    root = project_root if project_root is not None else Path.cwd()
    candidate = root / FALLBACK_REL
    if candidate.is_dir():
        return candidate

    raise FileNotFoundError(
        f"pd plugin root not found (primary={PRIMARY_GLOB}, fallback={candidate})"
    )


def _list_subdirs_with_file(parent: Path, filename: str) -> list[str]:
    if not parent.is_dir():
        return []
    names: list[str] = []
    for child in sorted(parent.iterdir()):
        if child.is_dir() and (child / filename).is_file():
            names.append(child.name)
    return names


def _list_md_basenames(parent: Path, exclude: set[str] | None = None) -> list[str]:
    if not parent.is_dir():
        return []
    excl = exclude or set()
    names: list[str] = []
    for child in sorted(parent.iterdir()):
        if child.is_file() and child.suffix == ".md" and child.name not in excl:
            names.append(child.stem)
    return names


def list_skills(
    *, plugin_root: Path | None = None, project_root: Path | None = None
) -> list[str]:
    """Skill directory names under `<plugin_root>/skills/` with a SKILL.md."""
    root = _resolve_plugin_root(plugin_root, project_root)
    return _list_subdirs_with_file(root / "skills", "SKILL.md")


def list_agents(
    *, plugin_root: Path | None = None, project_root: Path | None = None
) -> list[str]:
    """Agent markdown basenames under `<plugin_root>/agents/`."""
    root = _resolve_plugin_root(plugin_root, project_root)
    return _list_md_basenames(root / "agents")


def list_commands(
    *, plugin_root: Path | None = None, project_root: Path | None = None
) -> list[str]:
    """Command markdown basenames under `<plugin_root>/commands/`."""
    root = _resolve_plugin_root(plugin_root, project_root)
    return _list_md_basenames(root / "commands")
