"""The step-1 rewrite maps each id once, rewrites only where allowed, and the gate sees leftovers."""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rewrite_test_ids as rw  # noqa: E402


def test_mapping_rewrites_and_gate(tmp_path):
    tests = tmp_path / "hooks" / "lib"
    tests.mkdir(parents=True)
    (tests / "test_ids.py").write_text(textwrap.dedent("""\
        db.register_entity("feature", "1-a", "n")
        db.register_entity("feature", "001-a", "n")
        db.register_entity("backlog", "00042", "n")
        db.register_entity("project", "P001", "n")
        db.register_entity("brainstorm", "bs-mixed", "n")
        db.register_entity("backlog", "000-v1", "n")
        db._register_entity_no_display("feature", "solo", "n")
        assert get("project:P001") and get("1-a") and get("solo")
        note = "see 1-a"
        sql = "SELECT 1 WHERE type_id = 'feature:1-a'"
        near = "feature:1-alpha"
        msg = f"got {x} for project:P001"
        multi = ("UPDATE x SET a = 1 "
                 "WHERE type_id = 'feature:1-a'")
    """))
    (tests / "test_other.py").write_text('render("project:P001")\n')

    regs = rw.registrations(tmp_path)
    mapping = rw.build_mapping(regs)
    # Re-pad; a clash with an id the same file registers steps the seq; kind
    # names an all-digit id; a leading letter gets 001-; a brainstorm gets the
    # fixture date; seq 0 is refused for a person to decide.
    assert mapping.new == {
        ("feature", "1-a"): "002-a",
        ("backlog", "00042"): "042-backlog",
        ("project", "P001"): "001-p001",
        ("brainstorm", "bs-mixed"): "20260101-000001-bs-mixed",
        ("feature", "solo"): "001-solo",
    }
    assert mapping.refused == {("backlog", "000-v1"): "seq 0"}

    edits, reviews = rw.plan_edits(regs, mapping, tmp_path)
    rw.apply(edits, tmp_path)
    assert (tests / "test_ids.py").read_text() == textwrap.dedent("""\
        db.register_entity("feature", "002-a", "n")
        db.register_entity("feature", "001-a", "n")
        db.register_entity("backlog", "042-backlog", "n")
        db.register_entity("project", "001-p001", "n")
        db.register_entity("brainstorm", "20260101-000001-bs-mixed", "n")
        db.register_entity("backlog", "000-v1", "n")
        db.register_entity("feature", "001-solo", "n")
        assert get("project:001-p001") and get("002-a") and get("solo")
        note = "see 1-a"
        sql = "SELECT 1 WHERE type_id = 'feature:002-a'"
        near = "feature:1-alpha"
        msg = f"got {x} for project:001-p001"
        multi = ("UPDATE x SET a = 1 "
                 "WHERE type_id = 'feature:002-a'")
    """)
    # A kind:id token inside SQL (one line or several) or an f-string moves too, but never inside a
    # longer id; a file that never registers the id keeps its copy.
    assert (tests / "test_other.py").read_text() == 'render("project:P001")\n'
    # The refused id and the plain-word copy wait for a person; the gate finds
    # the id left in a sentence and the copy the unregistering file kept.
    assert [(r.line, r.literal, r.reason) for r in reviews] == [
        (6, "000-v1", "refused"), (8, "solo", "plain word")]
    left = rw.leftovers({lit for _, lit in mapping.new}, tmp_path)
    assert [(r.path, r.line, r.literal) for r in left] == [
        ("hooks/lib/test_ids.py", 9, "1-a"), ("hooks/lib/test_other.py", 1, "P001")]
    # Only the file that registers the id is gated; the other file's copy is its own text.
    mapping_file = tmp_path / "mapping.tsv"
    rw.write_mapping(mapping, mapping_file)
    registering = rw.registering_files(tmp_path, mapping_file)
    assert [(r.path, r.literal) for r in left if r.path in registering[r.literal]] == [
        ("hooks/lib/test_ids.py", "1-a")]
