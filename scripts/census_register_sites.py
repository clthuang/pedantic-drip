"""Census of register_entity-family call sites — Wave 2's one definition.

Every Wave 2 step that counts or classifies call sites re-derives from this
module instead of writing its own walker: two ad-hoc walkers disagreed by
one site during the Wave 2 review. Categories are the plan's D4 table
(docs/plans/2026-09-22-structural-identity-completion-plan.md).

    plugins/pd/.venv/bin/python scripts/census_register_sites.py
"""
from __future__ import annotations

import ast
import collections
import dataclasses
import os
import re
import sys
import warnings
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "pd"
sys.path.insert(0, str(PLUGIN / "hooks" / "lib"))
from entity_registry import database  # noqa: E402
from entity_registry.id_generator import (  # noqa: E402
    NON_SEQUENCE_KINDS,
    render_display_id,
)

CALLEES = frozenset({
    "register_entity",
    "upsert_entity",
    "register_entities_batch",
    "_register_entity_no_display",
})
# Calls inside the module that defines the family are delegations between
# its own methods, not callers.
DEFINING_MODULE = "hooks/lib/entity_registry/database.py"
# The strict gate's own regex; C6 deletes it, after which C no longer splits.
STRICT_ID_RE = getattr(database, "_ENTITY_ID_FORMAT_RE", None)
_SEQ_SLUG = re.compile(r"^(\d+)-(.+)$")


@dataclasses.dataclass(frozen=True)
class Site:
    path: str                   # relative to plugins/pd
    line: int
    callee: str
    kind: str | None            # the entity_type literal, else None
    entity_id: ast.expr | None  # positional second argument or keyword

    @property
    def is_test(self) -> bool:
        name = self.path.rsplit("/", 1)[-1]
        return (name.startswith("test_") or name == "conftest.py"
                or "/tests/" in f"/{self.path}")

    @property
    def is_internal(self) -> bool:
        return self.path == DEFINING_MODULE

    @property
    def literal(self) -> str | None:
        arg = self.entity_id
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        return None


def find_sites(root: Path = PLUGIN) -> list[Site]:
    """Every call to a CALLEES name under ``root``, in (path, line) order."""
    sites = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".venv", "__pycache__"}]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            path = Path(dirpath, filename)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            rel = path.relative_to(root).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name not in CALLEES:
                    continue
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                kind = node.args[0] if node.args else kw.get("entity_type")
                entity_id = node.args[1] if len(node.args) >= 2 else kw.get("entity_id")
                sites.append(Site(
                    rel, node.lineno, name,
                    kind.value if isinstance(kind, ast.Constant) and isinstance(kind.value, str) else None,
                    entity_id,
                ))
    return sorted(sites, key=lambda s: (s.path, s.line))


def round_trips(entity_id: str) -> bool:
    """True iff ``render_display_id`` reproduces ``entity_id`` byte for byte."""
    match = _SEQ_SLUG.match(entity_id)
    if not match:
        return False
    try:
        # The rendering is the same for every sequence kind.
        return render_display_id("feature", int(match[1]), match[2]) == entity_id
    except ValueError:  # seq < 1
        return False


def category(site: Site) -> str:
    """The plan's D4 category, A-F."""
    if site.callee == "_register_entity_no_display":
        return "F"
    if site.entity_id is None:
        return "E"
    if site.literal is None:
        return "D"
    if site.kind in NON_SEQUENCE_KINDS:
        return "C"
    return "A" if round_trips(site.literal) else "B"


def multi_file_literals(sites: list[Site]) -> dict[str, list[str]]:
    """Test literals registered in more than one file."""
    files = collections.defaultdict(set)
    for site in sites:
        if site.is_test and site.literal:
            files[site.literal].add(site.path)
    return {lit: sorted(paths) for lit, paths in files.items() if len(paths) > 1}


def main() -> int:
    sites = find_sites()
    prod = [s for s in sites if not s.is_test]
    test = [s for s in sites if s.is_test]
    internal = sum(s.is_internal for s in prod)
    print(f"production  {len(prod) - internal} external callers, {internal} internal delegations")
    print(f"test        {len(test)} call sites across {len({s.path for s in test})} files")
    cats = collections.Counter(category(s) for s in test)
    print("categories  " + "  ".join(f"{c}={cats[c]}" for c in "ABCDEF"))
    if STRICT_ID_RE is not None:
        rejected = sum(1 for s in test if category(s) == "C" and not STRICT_ID_RE.match(s.literal))
        print(f"            C: {cats['C'] - rejected} pass the strict regex, {rejected} rewritten at step 1")
    multi = multi_file_literals(sites)
    print(f"test literals registered in 2+ files: {len(multi)}")
    for lit, paths in sorted(multi.items()):
        print(f"  {lit!r:30} {', '.join(p.rsplit('/', 1)[-1] for p in paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
