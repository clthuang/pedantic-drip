"""Tests for FR-6a cleanup_backlog.py.

Lazy imports per T18 DoD — `import cleanup_backlog` inside test bodies only,
NOT at module top, so pytest --collect-only succeeds even when the module
does not yet exist (TDD-red contract).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
ARCHIVABLE_FIXTURE = FIXTURE_DIR / "backlog-099-archivable.md"
SCRIPT_PATH = Path(__file__).parent.parent / "cleanup_backlog.py"


@pytest.fixture
def tmp_backlog(tmp_path):
    """Copy fixture to a tmp_path so tests can mutate without polluting source."""
    dst = tmp_path / "backlog.md"
    shutil.copy(ARCHIVABLE_FIXTURE, dst)
    return dst


@pytest.fixture
def tmp_archive(tmp_path):
    """Archive path — initially absent."""
    return tmp_path / "backlog-archive.md"


def _run(*args):
    """Run cleanup_backlog.py CLI; capture stdout/stderr/returncode."""
    cmd = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_ac8_dry_run_identifies_three_archivable(tmp_backlog):
    """AC-8: dry-run on fixture identifies exactly 3 ARCHIVABLE sections."""
    result = _run("--dry-run", "--backlog-path", str(tmp_backlog))
    assert result.returncode == 0
    out = result.stdout
    # Three archivable sections (TestA, TestB, TestC); MixedQA + EmptyQA are NOT.
    assert out.count("YES") == 3
    assert "TestA" in out and "TestB" in out and "TestC" in out
    # Mixed and empty sections must not appear as ARCHIVABLE.
    # (Verify by checking they are listed but with NO/empty status — relies on table format.)
    # Verify no writes occurred:
    assert tmp_backlog.read_text() == ARCHIVABLE_FIXTURE.read_text()


def test_ac8b_dry_run_real_backlog_smoke(monkeypatch):
    """AC-8b: dry-run on real backlog returns non-empty output, exits 0."""
    real_backlog = Path(__file__).parent.parent.parent.parent.parent / "docs" / "backlog.md"
    if not real_backlog.exists():
        pytest.skip("real backlog.md not present")
    result = _run("--dry-run", "--backlog-path", str(real_backlog))
    assert result.returncode == 0
    assert "Section" in result.stdout or "From" in result.stdout  # table or section header present


def test_ac9_apply_routes_through_update_entity(tmp_backlog, tmp_archive, tmp_path):
    """AC-9 (feature 110 FR-4.3 update): --apply no longer writes to the
    standalone archive file. Instead it routes archival through
    ``update_entity(status='archived')`` and re-projects ``backlog.md``.

    This test exercises the apply path against a tmp DB pointer
    (``ENTITY_DB_PATH``) — the path is non-existent so the script's
    lazy-imported DB module either creates an empty DB or surfaces an
    import-time degraded-mode warning. The contract we verify here:
      * exit code is 0 (degraded mode is non-blocking),
      * the standalone archive file is NOT created (deprecated),
      * the backlog file is not corrupted (regardless of DB state).
    """
    fake_db = tmp_path / "isolated_test_db_does_not_exist.db"
    env = {**os.environ, "ENTITY_DB_PATH": str(fake_db)}
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--apply",
        "--backlog-path",
        str(tmp_backlog),
        "--archive-path",
        str(tmp_archive),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # Feature 110 contract: --apply ALWAYS exits 0; DB failures emit to
    # stderr but do NOT propagate as non-zero exit.
    assert result.returncode == 0, (
        f"--apply must exit 0 even under degraded DB conditions; "
        f"got rc={result.returncode}, stderr={result.stderr[:500]}"
    )
    # Feature 110 contract: the standalone archive file is NEVER written.
    assert not tmp_archive.exists(), (
        "Feature 110 FR-4.3 — cleanup_backlog.py must NOT write to the "
        "standalone archive file. Archived rows are identified via DB "
        "status='archived' flag and excluded from _project_backlog_md output."
    )


def test_ac9f_no_double_blank_runs(tmp_backlog, tmp_archive, tmp_path):
    """AC-9(f): post-apply backlog text has no double-blank-line runs.

    Under feature 110 the file is regenerated via ``_project_backlog_md``
    (when the DB is available) or untouched (when degraded). Either way
    the resulting file MUST have no double-blank-line runs.
    """
    fake_db = tmp_path / "isolated_test_db_does_not_exist.db"
    env = {**os.environ, "ENTITY_DB_PATH": str(fake_db)}
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--apply",
        "--backlog-path",
        str(tmp_backlog),
        "--archive-path",
        str(tmp_archive),
    ]
    subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert "\n\n\n" not in tmp_backlog.read_text()


def test_ace7_idempotency(tmp_backlog, tmp_archive, tmp_path):
    """AC-E7: re-running --apply produces zero diffs.

    Feature 110 update: idempotency means re-running the same DB
    flips/re-projection sequence produces the same file output. We test
    this under degraded-DB conditions (the most defensive scenario)
    where the file should remain stable across invocations.
    """
    fake_db = tmp_path / "isolated_test_db_does_not_exist.db"
    env = {**os.environ, "ENTITY_DB_PATH": str(fake_db)}
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--apply",
        "--backlog-path",
        str(tmp_backlog),
        "--archive-path",
        str(tmp_archive),
    ]
    subprocess.run(cmd, capture_output=True, text=True, env=env)
    backlog_after_first = tmp_backlog.read_text()
    subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert tmp_backlog.read_text() == backlog_after_first


def test_ace6_empty_section_not_archivable(tmp_backlog):
    """AC-E6: section with 0 items is NOT marked ARCHIVABLE."""
    result = _run("--dry-run", "--backlog-path", str(tmp_backlog))
    # EmptyQA section has no items; should NOT appear with YES.
    out = result.stdout
    # Find the EmptyQA row and verify no YES marker.
    for line in out.splitlines():
        if "EmptyQA" in line:
            # YES would indicate archivable — should not be present for empty section.
            assert "YES" not in line


def test_count_active_cli(tmp_backlog):
    """T16 --count-active flag exists and returns int (used by FR-6b doctor)."""
    result = _run("--count-active", "--backlog-path", str(tmp_backlog))
    assert result.returncode == 0
    count = int(result.stdout.strip())
    # Three open items in the fixture:
    #   | 00099 |   top-level table row, no closure marker
    #   - **#99030**   MixedQA, active
    #   - **#99032**   MixedQA, active
    # Everything else carries a closure marker or strikethrough.
    #
    # Was 2 until 2026-09-22. count_active matched bullets only, so the
    # top-level table row was invisible to it — and since the real
    # docs/backlog.md is entirely table-form, the check returned 0 for every
    # actual backlog and doctor.sh's FR-6b threshold could never fire.
    # FR-6a's "top-level table is out of scope" governs which SECTIONS are
    # archivable; it does not mean a table row is not an open item.
    assert count == 3


def test_archival_preserves_status_and_sets_the_flag(tmp_backlog, tmp_archive, tmp_path):
    """Archival writes ``is_archived`` and leaves ``status`` alone.

    The sibling AC-9 test points ``ENTITY_DB_PATH`` at a non-existent file,
    so it exercises the degraded path and passes under any writer. This one
    uses a real DB and asserts the two facts that distinguish the writers:
    the flag flipped, and the workflow status the entity actually had is
    still there.

    Before v2 migration 5, archival wrote ``status='archived'`` and so
    destroyed what the entity was — 125 of 170 archived rows had been
    ``completed`` and said so nowhere. The reader moved to ``is_archived``
    in bb0fb55e; this pins the writer to the same column.
    """
    import sqlite3

    sys.path.insert(0, str(SCRIPT_PATH.parent))
    sys.path.insert(0, str(SCRIPT_PATH.parent.parent / "hooks" / "lib"))
    sys.path.insert(0, str(SCRIPT_PATH.parent.parent / "mcp"))
    from entity_registry.database import EntityDatabase

    import cleanup_backlog

    import uuid as _uuid

    db_path = tmp_path / "entities.db"
    db = EntityDatabase(str(db_path))
    ws = str(_uuid.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws, "__cleanup_backlog_test__", str(tmp_path), now, now),
    )
    db._conn.commit()

    # Two items in the fixture's archivable section, registered completed.
    content = tmp_backlog.read_text()
    sections = cleanup_backlog.parse_sections(content)
    archivable = [s for s in sections if s["is_archivable"]]
    item_ids = []
    for sec in archivable:
        item_ids.extend(cleanup_backlog._extract_item_ids(sec["items"]))
    assert item_ids, "fixture must contain archivable items for this test to mean anything"

    for n, item_id in enumerate(item_ids):
        db.register_entity(
            "backlog",
            entity_id=item_id,
            name=f"item {item_id}",
            workspace_uuid=ws,
            status="completed",
            _strict_id_format=False,
        )

    monkey = os.environ.get("ENTITY_DB_PATH")
    os.environ["ENTITY_DB_PATH"] = str(db_path)
    try:
        cleanup_backlog.apply_archival(tmp_backlog, tmp_archive)
    finally:
        if monkey is None:
            os.environ.pop("ENTITY_DB_PATH", None)
        else:
            os.environ["ENTITY_DB_PATH"] = monkey

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    for item_id in item_ids:
        row = conn.execute(
            "SELECT status, is_archived FROM entities WHERE type_id = ?",
            (f"backlog:{item_id}",),
        ).fetchone()
        assert row is not None, f"backlog:{item_id} vanished"
        assert row["is_archived"] == 1, (
            f"backlog:{item_id} was not archived — the flag is the archive surface"
        )
        assert row["status"] == "completed", (
            f"backlog:{item_id} status is {row['status']!r}, not 'completed'. "
            "Archival overwrote workflow state; it must write is_archived only."
        )
    conn.close()


def test_count_active_counts_table_rows_not_only_bullets(tmp_path):
    """FR-6b counted bullets only, so it returned 0 for every real backlog.

    docs/backlog.md is projected from the entity registry and every row is
    table-form unless its metadata says format == "bullet_item" — of which
    there are none. The bullet-only counter therefore reported 0
    unconditionally and doctor.sh's threshold check could never fire.

    Asserting the COUNT rather than "no exception" is the point: the old
    implementation raised nothing and returned a confidently wrong 0.
    """
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    import cleanup_backlog

    backlog = tmp_path / "backlog.md"
    backlog.write_text(
        "# Backlog\n"
        "\n"
        "| ID | Timestamp | Description |\n"
        "|----|-----------|-------------|\n"
        "| 00059 | 2026-04-15T14:10:49+00:00 | legacy-form open item |\n"
        "| 063-watch-the-thing | 2026-07-25T11:23:36+00:00 | modern-form open item |\n"
        "\n"
        "## From Feature TestZ QA (2026-01-01)\n"
        "\n"
        "- **#99001** bullet-form open item\n"
        "- ~~**#99002**~~ bullet-form CLOSED item\n"
    )
    # 2 table rows + 1 open bullet = 3; the struck bullet and the header and
    # separator rows must not count.
    assert cleanup_backlog.count_active(backlog) == 3


def test_reprojection_is_scoped_and_refuses_to_empty_the_file(tmp_path):
    """Covers the two paths the sibling apply test never reaches.

    That test points ENTITY_DB_PATH at a nonexistent file and its tmp_path
    has no .claude/, so apply_archival returns before the re-projection.
    Everything after workspace resolution — scoping, the empty-projection
    guard, the file write — was dead code under test: reverting
    `_project_backlog_md(db, workspace_uuid=...)` to the unscoped call left
    the whole suite green.

    Here the backlog's parent.parent IS a registered workspace holding one
    live item, and a second workspace holds another. The written file must
    contain only the first.
    """
    import sqlite3
    import uuid as _uuid

    sys.path.insert(0, str(SCRIPT_PATH.parent))
    sys.path.insert(0, str(SCRIPT_PATH.parent.parent / "hooks" / "lib"))
    sys.path.insert(0, str(SCRIPT_PATH.parent.parent / "mcp"))
    import cleanup_backlog
    from entity_registry.database import EntityDatabase

    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    backlog = root / "docs" / "backlog.md"
    # The archivable section is load-bearing, not decoration: apply_archival
    # returns at `if not archivable` before ever re-projecting, so without a
    # fully-closed `## From` section this test would pass with the scoping
    # reverted. Verified by mutation.
    backlog.write_text(
        "# Backlog\n\n| ID | Timestamp | Description |\n|----|-----------|-------------|\n"
        "| 001-mine | 2026-07-25T00:00:00+00:00 | mine |\n"
        "\n## From Feature Z QA (2026-01-01)\n\n"
        "- ~~**#99500**~~ closed, makes this section archivable\n"
    )

    db_path = tmp_path / "e.db"
    db = EntityDatabase(str(db_path))
    now = db._now_iso()
    ids = {}
    for tag, proot in (("mine", str(root)), ("theirs", str(tmp_path / "other"))):
        u = str(_uuid.uuid4())
        db._conn.execute(
            "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
            "created_at, updated_at) VALUES (?,?,?,?,?)",
            (u, f"__{tag}__", proot, now, now),
        )
        ids[tag] = u
    db._conn.commit()
    db.register_entity("backlog", entity_id="001-mine", name="mine",
                       workspace_uuid=ids["mine"], status="open",
                       _strict_id_format=False)
    db.register_entity("backlog", entity_id="002-theirs", name="theirs",
                       workspace_uuid=ids["theirs"], status="open",
                       _strict_id_format=False)

    prev = os.environ.get("ENTITY_DB_PATH")
    os.environ["ENTITY_DB_PATH"] = str(db_path)
    try:
        cleanup_backlog.apply_archival(backlog, tmp_path / "archive.md")
    finally:
        if prev is None:
            os.environ.pop("ENTITY_DB_PATH", None)
        else:
            os.environ["ENTITY_DB_PATH"] = prev

    written = backlog.read_text()
    assert "001-mine" in written
    assert "002-theirs" not in written, (
        "the re-projection is unscoped; another workspace's backlog item "
        "was written into this repo's file"
    )


def test_reprojection_refuses_when_it_would_empty_a_populated_file(tmp_path):
    """backlog.md is gitignored and this is its only writer, so an
    overwrite with nothing is unrecoverable.

    Reproduces the reported data loss: a --backlog-path whose parent.parent
    is not a registered workspace. Previously resolve_workspace_uuid minted
    a fresh uuid for it, the projection matched no entities, and a populated
    266-byte file was replaced with a 77-byte empty one.
    """
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    import cleanup_backlog

    root = tmp_path / "elsewhere"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / ".claude").mkdir()
    backlog = root / "docs" / "pd" / "backlog.md"
    backlog.parent.mkdir()
    original = (
        "# Backlog\n\n| ID | Timestamp | Description |\n|----|-----------|-------------|\n"
        "| 00059 | 2026-04-15T00:00:00+00:00 | a real live item |\n"
        "\n## From Feature X QA (2026-01-01)\n\n- ~~**#99001**~~ closed\n"
    )
    backlog.write_text(original)

    prev = os.environ.get("ENTITY_DB_PATH")
    os.environ["ENTITY_DB_PATH"] = str(tmp_path / "empty.db")
    try:
        cleanup_backlog.apply_archival(backlog, tmp_path / "archive.md")
    finally:
        if prev is None:
            os.environ.pop("ENTITY_DB_PATH", None)
        else:
            os.environ["ENTITY_DB_PATH"] = prev

    assert backlog.read_text() == original, "a populated backlog was overwritten"
    assert not (root / "docs" / ".claude" / "pd" / "workspace.json").exists(), (
        "minted a workspace.json in a directory that is not a workspace"
    )
