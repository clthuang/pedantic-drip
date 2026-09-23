"""The census walker finds every call shape and puts each in its category."""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import census_register_sites as census  # noqa: E402


def test_every_call_shape_lands_in_its_category(tmp_path):
    tests = tmp_path / "hooks" / "lib" / "test_shapes.py"
    tests.parent.mkdir(parents=True)
    tests.write_text(textwrap.dedent("""\
        db.register_entity("feature", "001-alpha", "n")
        db.register_entity("feature", "1-alpha", "n")
        db.register_entity("backlog", "000-v1", "n")
        db.upsert_entity(entity_type="brainstorm", entity_id="bs-mixed", name="n")
        db.register_entity("feature", f"00{i}-c", "n")
        db.register_entities_batch([{"entity_id": "001-x"}])
        db._register_entity_no_display("feature", "solo", "n")
    """))
    database = tmp_path / "hooks" / "lib" / "entity_registry" / "database.py"
    database.parent.mkdir(parents=True)
    database.write_text("self.register_entity(entity_type, entity_id, name)\n")

    sites = census.find_sites(tmp_path)
    in_tests = [s for s in sites if s.is_test]
    # A round-trips; B re-pads; B again (seq 0 refused); C brainstorm;
    # D dynamic; E no entity_id argument; F the display-less helper.
    assert [census.category(s) for s in in_tests] == list("ABBCDEF")
    assert [s.path for s in sites if not s.is_test] == [census.DEFINING_MODULE]
    assert all(s.is_internal for s in sites if not s.is_test)
