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
        entity_server.register_entity(entity_type="feature", entity_id="f1", name="n")
    """))
    database = tmp_path / "hooks" / "lib" / "entity_registry" / "database.py"
    database.parent.mkdir(parents=True)
    database.write_text("self.register_entity(entity_type, entity_id, name)\n")

    sites = census.find_sites(tmp_path)
    in_tests = [s for s in sites if s.is_test]
    # A round-trips; B re-pads; B again (seq 0 refused); C brainstorm;
    # D dynamic; E no entity_id argument; F the display-less helper;
    # B through the MCP tool, the only call marked as one.
    assert [census.category(s) for s in in_tests] == list("ABBCDEFB")
    assert [s.is_mcp_tool for s in in_tests] == [False] * 7 + [True]
    assert [s.path for s in sites if not s.is_test] == [census.DEFINING_MODULE]
    assert all(s.is_internal for s in sites if not s.is_test)


def test_ids_that_reach_registration_indirectly_are_entries(tmp_path):
    tests = tmp_path / "hooks" / "lib" / "test_routes.py"
    tests.parent.mkdir(parents=True)
    tests.write_text(textwrap.dedent("""\
        def _reg(db, kind, entity_id, name="n"):
            return db.register_entity(kind, entity_id, name)

        def _live(db, entity_id, *, kind="feature"):
            db.upsert_entity(kind, entity_id, "n")

        class TestRoutes:
            def _feature(self, eid):
                self.db.register_entity("feature", eid, "n")

            def test_it(self):
                self._feature("f1")
                _reg(db, "backlog", "00042")
                _reg(db, kind="project", entity_id="P001")
                db.register_entities_batch([{"entity_type": "feature", "entity_id": "1-a"}])
                _reg(db, "feature", f"e{i}")
                _live(db, "lone")
                _live(db, "bs-x", kind="brainstorm")
    """))

    entries = census.find_entries(tmp_path)
    # A method helper drops self; kind and id arrive by position or keyword;
    # a batch dict carries its own kind; a dynamic argument is still found;
    # a keyword-only kind falls back to its default when the call omits it.
    assert [(s.route, s.kind, s.literal) for s in entries] == [
        ("helper", "feature", "f1"),
        ("helper", "backlog", "00042"),
        ("helper", "project", "P001"),
        ("dict", "feature", "1-a"),
        ("helper", "feature", None),
        ("helper", "feature", "lone"),
        ("helper", "brainstorm", "bs-x"),
    ]
    assert [census.category(s) for s in entries] == list("BBBBDBC")
