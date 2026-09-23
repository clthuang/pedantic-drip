"""Immutable-trigger removal tests for feature 109 (FR-3).

Scope (Group 3, Tasks 3.5+3.6 — trigger removal verification):
  - ``test_enforce_immutable_entity_type_source_removed`` (Task 3.5a, AC-3.1):
    subprocess grep of ``database.py`` returns 0 CREATE TRIGGER definitions
    for ``enforce_immutable_entity_type`` outside permitted exceptions.
  - ``test_enforce_immutable_type_id_source_removed`` (Task 3.5b, AC-3.1):
    same as above for ``enforce_immutable_type_id``.
  - ``test_immutable_triggers_dropped_at_runtime`` (Task 3.6, AC-3.1):
    against ``make_v12_db()``, ``sqlite_master`` lists neither
    ``enforce_immutable_entity_type`` nor ``enforce_immutable_type_id``.

"""
from __future__ import annotations

import subprocess
from pathlib import Path

from entity_registry.test_helpers import make_v12_db


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_DATABASE_PY = Path(__file__).resolve().parent / "database.py"


def _grep_create_trigger(trigger_name: str) -> list[str]:
    """Return CREATE TRIGGER lines mentioning ``trigger_name`` from
    ``database.py``, EXCLUDING:

    - ``DROP TRIGGER`` lines (permitted defensive guards inside migration 12).
    - Lines inside ``_migration_12_polymorphic_taxonomy_and_events_down``
      (the canonical down-migration recreation site permitted by spec
      AC-5.1 / design TD-9).

    The returned list is the violation set — empty means the source has
    no remaining forward-migration definitions.
    """
    # Use `grep -n` so violation messages include line numbers for
    # bisect-friendly output.
    result = subprocess.run(
        [
            "grep",
            "-nE",
            f"CREATE TRIGGER.*{trigger_name}",
            str(_DATABASE_PY),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep returns exit-1 when no matches — that's the GREEN state.
    if result.returncode == 1:
        return []
    if result.returncode != 0:
        raise RuntimeError(
            f"grep failed (rc={result.returncode}): {result.stderr!r}"
        )

    # Compute the line range of the down-migration function so we can
    # filter out lines that fall inside it (permitted by AC-5.1).
    src_text = _DATABASE_PY.read_text()
    src_lines = src_text.splitlines()
    down_start = None
    down_end = None
    for idx, line in enumerate(src_lines, start=1):
        if line.startswith(
            "def _migration_12_polymorphic_taxonomy_and_events_down"
        ):
            down_start = idx
        elif down_start and down_end is None and line.startswith("def "):
            down_end = idx - 1
            break
    if down_start and down_end is None:
        down_end = len(src_lines)

    lines = result.stdout.splitlines()
    # Filter: ``DROP TRIGGER IF EXISTS <name>`` lines may also include
    # the name but are not CREATE statements. Also exclude lines inside
    # the down-migration function.
    out: list[str] = []
    for ln in lines:
        if "DROP TRIGGER" in ln:
            continue
        try:
            lineno = int(ln.split(":", 1)[0])
        except (ValueError, IndexError):
            out.append(ln)
            continue
        if down_start and down_start <= lineno <= (down_end or lineno):
            continue
        out.append(ln)
    return out


# ---------------------------------------------------------------------------
# Task 3.5: source-grep zero for both immutable triggers
# ---------------------------------------------------------------------------


def test_enforce_immutable_entity_type_source_removed() -> None:
    """AC-3.1: ``database.py`` defines zero ``enforce_immutable_entity_type``
    triggers after Task 3.7 removes the 6 historical CREATE TRIGGER blocks.

    The trigger blocks ``entity_type`` UPDATEs (immutability guard from
    feature 052-era); F11 backfills ``entity_type → kind`` and Group 7
    drops the column entirely, so the trigger is incompatible with both
    operations and must be removed at every schema-creation epoch.
    """
    violations = _grep_create_trigger("enforce_immutable_entity_type")
    assert violations == [], (
        f"AC-3.1 violation: enforce_immutable_entity_type CREATE TRIGGER "
        f"definitions still present in database.py:\n"
        + "\n".join(violations)
    )


def test_enforce_immutable_type_id_source_removed() -> None:
    """AC-3.1: ``database.py`` defines zero ``enforce_immutable_type_id``
    triggers after Task 3.8 removes the 6 historical CREATE TRIGGER blocks.

    The trigger blocked ``type_id`` UPDATEs, which feature 109's
    ``promote_entity`` needed, so it was removed at every schema-creation
    epoch. ``promote_entity`` itself was removed on 2026-09-23 without ever
    having had a caller.
    """
    violations = _grep_create_trigger("enforce_immutable_type_id")
    assert violations == [], (
        f"AC-3.1 violation: enforce_immutable_type_id CREATE TRIGGER "
        f"definitions still present in database.py:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Task 3.6: runtime trigger zero
# ---------------------------------------------------------------------------


def test_immutable_triggers_dropped_at_runtime() -> None:
    """AC-3.1: after migration 12, ``sqlite_master`` lists neither
    ``enforce_immutable_entity_type`` nor ``enforce_immutable_type_id``.

    The triggers are removed by Group 3's copy-rename block (which
    intentionally omits them from the trigger-recreation loop) AND by
    defensive ``DROP TRIGGER IF EXISTS`` guards (Task 3.8) that catch
    any orphan trigger surviving the table rebuild.
    """
    conn = make_v12_db()
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='trigger' AND name IN "
        "('enforce_immutable_entity_type', 'enforce_immutable_type_id')"
    ).fetchall()
    names = [r[0] for r in rows]
    assert names == [], (
        f"AC-3.1 violation: immutable triggers still installed at runtime "
        f"after migration 12: {names!r}"
    )
