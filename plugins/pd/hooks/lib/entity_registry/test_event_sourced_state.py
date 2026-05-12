"""Event-sourced state tests for feature 109 (F2).

Currently scope:
  - ``test_no_production_insert_phase_event_callers`` (Task 0.5.1 RED): asserts
    that no production code under ``plugins/pd/`` calls the legacy
    ``insert_phase_event(...)`` symbol. The symbol has been renamed to
    ``append_phase_event`` (feature 109 Group 0.5). Test files and the
    definition line itself are excluded — those are tracked separately and
    the definition is renamed mechanically in Task 0.5.2.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


# Anchor at the repo's ``plugins/pd/`` directory regardless of the cwd this
# test runs from. ``__file__`` is .../plugins/pd/hooks/lib/entity_registry/
# test_event_sourced_state.py, so parents[3] is plugins/pd/.
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]


def test_no_production_insert_phase_event_callers() -> None:
    """No production code may call the legacy ``insert_phase_event(`` symbol.

    Search strategy (subprocess grep):
      - Recurse ``plugins/pd/``.
      - Match the pattern ``insert_phase_event(`` (call site, parens included
        to avoid matching the method-definition substring).
      - Exclude the definition line itself (``def insert_phase_event``) — that
        will be renamed by Task 0.5.2.
      - Exclude any path containing ``test_`` — test fixtures are renamed
        mechanically by Task 0.5.4.

    DoD: zero matches in production code after Task 0.5.3 lands.
    """
    # Use grep -rn with a fixed-string pattern. ``--include='*.py'`` keeps
    # noise (md/json/etc.) out of the result. ``2>/dev/null`` suppresses any
    # permission-denied stderr that would corrupt subprocess output.
    proc = subprocess.run(
        [
            "grep",
            "-rn",
            "--include=*.py",
            "insert_phase_event(",
            str(_PLUGIN_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep exit code 1 = no matches (acceptable); 0 = matches found; >1 = err.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"grep failed (rc={proc.returncode}): {proc.stderr}"
        )

    production_matches: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # Skip the definition line(s) — the symbol still exists at the
        # definition site after rename only if Task 0.5.2 has not landed.
        if "def insert_phase_event" in line:
            continue
        # Skip every path containing a ``test_`` segment.
        # Use the path before the first ``:`` to isolate file path from match
        # content (line numbers come before content separated by colons).
        path_part = line.split(":", 1)[0]
        if "test_" in Path(path_part).name:
            continue
        production_matches.append(line)

    assert len(production_matches) == 0, (
        "Production code still references legacy 'insert_phase_event(' "
        "(feature 109 Group 0.5 — rename to append_phase_event). "
        "Offending sites:\n" + "\n".join(production_matches)
    )
