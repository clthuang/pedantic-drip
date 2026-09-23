"""Census of register_entity-family call sites — Wave 2's one definition.

Every Wave 2 step that counts or classifies call sites re-derives from this
module instead of writing its own walker: two ad-hoc walkers disagreed by
one site during the Wave 2 review. Categories are the plan's D4 table
(docs/plans/2026-09-22-structural-identity-completion-plan.md).

    plugins/pd/.venv/bin/python scripts/census_register_sites.py [--list]

``--list`` adds every dynamic id and every indirect id not yet in round-trip form.
"""
from __future__ import annotations

import ast
import collections
import dataclasses
import os
import re
import sys
import warnings
from collections.abc import Iterator
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
# Tests reach the MCP register_entity tool through this module; the tool keeps
# entity_id until C7 changes its surface, so these calls move separately.
MCP_TOOL_MODULE = "entity_server"
# The strict gate's own regex; C6 deletes it, after which C no longer splits.
STRICT_ID_RE = getattr(database, "_ENTITY_ID_FORMAT_RE", None)
_SEQ_SLUG = re.compile(r"^(\d+)-(.+)$")


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") or name == "conftest.py" or "/tests/" in f"/{path}"


@dataclasses.dataclass(frozen=True)
class Site:
    path: str                    # relative to plugins/pd
    line: int
    callee: str                  # the name called; for an entry, "dict" or the helper
    kind: str | None             # the entity_type literal, else None
    entity_id: ast.expr | None   # positional second argument or keyword
    receiver: str | None = None  # what the call is made on, e.g. "db"
    route: str = "call"          # "call", or how find_entries saw the id arrive

    @property
    def is_test(self) -> bool:
        return _is_test_path(self.path)

    @property
    def is_internal(self) -> bool:
        return self.path == DEFINING_MODULE

    @property
    def is_mcp_tool(self) -> bool:
        return self.receiver == MCP_TOOL_MODULE

    @property
    def literal(self) -> str | None:
        return _literal(self.entity_id)


def _literal(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _parse(root: Path, tests_only: bool = False) -> Iterator[tuple[str, ast.Module]]:
    """(path relative to root, tree) for every .py file under ``root``."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".venv", "__pycache__"}]
        for filename in filenames:
            path = Path(dirpath, filename)
            rel = path.relative_to(root).as_posix()
            if not filename.endswith(".py") or (tests_only and not _is_test_path(rel)):
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                yield rel, ast.parse(path.read_text(encoding="utf-8"), str(path))


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _family_calls(tree: ast.AST) -> Iterator[tuple[ast.Call, ast.expr | None, ast.expr | None]]:
    """(call, kind argument, entity_id argument) for every CALLEES call in ``tree``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _called_name(node) in CALLEES:
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            kind = node.args[0] if node.args else kw.get("entity_type")
            entity_id = node.args[1] if len(node.args) >= 2 else kw.get("entity_id")
            yield node, kind, entity_id


def find_sites(root: Path = PLUGIN) -> list[Site]:
    """Every call to a CALLEES name under ``root``, in (path, line) order."""
    sites = []
    for rel, tree in _parse(root):
        for call, kind, entity_id in _family_calls(tree):
            func = call.func
            sites.append(Site(
                rel, call.lineno, _called_name(call), _literal(kind), entity_id,
                ast.unparse(func.value) if isinstance(func, ast.Attribute) else None,
            ))
    return sorted(sites, key=lambda s: (s.path, s.line))


@dataclasses.dataclass(frozen=True)
class _Param:
    position: int | None  # None for a keyword-only parameter
    name: str
    default: str | None   # its default, when that is a string literal


def _helpers(tree: ast.Module) -> dict[str, tuple[_Param, str | _Param | None]]:
    """Test functions that forward one of their parameters to a family call as its id.

    name -> (id parameter, kind), where kind is the family call's literal or
    the parameter the helper forwards as kind.
    """
    helpers = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = fn.args.posonlyargs + fn.args.args
        defaults = dict(zip([a.arg for a in positional[len(positional) - len(fn.args.defaults):]],
                            fn.args.defaults))
        defaults.update((a.arg, d) for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if d)
        names = [a.arg for a in positional]
        if names[:1] in (["self"], ["cls"]):
            names = names[1:]
        params = {name: _Param(i, name, _literal(defaults.get(name))) for i, name in enumerate(names)}
        params.update((a.arg, _Param(None, a.arg, _literal(defaults.get(a.arg)))) for a in fn.args.kwonlyargs)
        for _, kind, entity_id in _family_calls(fn):
            if isinstance(entity_id, ast.Name) and entity_id.id in params:
                forwarded = _literal(kind)
                if forwarded is None and isinstance(kind, ast.Name):
                    forwarded = params.get(kind.id)
                helpers[fn.name] = (params[entity_id.id], forwarded)
    return helpers


def _argument(call: ast.Call, param: _Param) -> ast.expr | None:
    if param.position is not None and len(call.args) > param.position:
        return call.args[param.position]
    return next((k.value for k in call.keywords if k.arg == param.name), None)


def find_entries(root: Path = PLUGIN) -> list[Site]:
    """Test ids that reach registration without being a family call's argument.

    ``dict``: a dict display with an ``entity_id`` key — register_entities_batch
    entries, and the records tests hand to a production registrar. ``helper``:
    an argument to a test function that forwards it to a family call as the id,
    first hop and same file only. Deeper routes show up only when the suite runs.
    """
    entries = []
    for rel, tree in _parse(root, tests_only=True):
        helpers = _helpers(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                keys = [_literal(k) for k in node.keys]
                if "entity_id" in keys:
                    kind = node.values[keys.index("entity_type")] if "entity_type" in keys else None
                    entries.append(Site(rel, node.lineno, "dict", _literal(kind),
                                        node.values[keys.index("entity_id")], route="dict"))
            elif isinstance(node, ast.Call) and _called_name(node) in helpers:
                id_param, kind = helpers[_called_name(node)]
                entity_id = _argument(node, id_param)
                if isinstance(kind, _Param):
                    passed = _argument(node, kind)
                    kind = _literal(passed) if passed is not None else kind.default
                if entity_id is not None:
                    entries.append(Site(rel, node.lineno, _called_name(node), kind, entity_id,
                                        route="helper"))
    return sorted(entries, key=lambda s: (s.path, s.line))


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


def main(argv: list[str]) -> int:
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
    print(f"            {sum(s.is_mcp_tool for s in test)} call the MCP register_entity tool, not the database")
    # Wave 2 step 3's exit check: only calls to the MCP tool, which moves at
    # step 4, may still pass the entity_id text form.
    text_form = [s for s in test if s.entity_id is not None and not s.is_mcp_tool]
    print(f"            {len(text_form)} other test calls still pass entity_id")
    entries = find_entries()
    routes = collections.Counter(s.route for s in entries)
    kinds = collections.Counter(category(s) for s in entries)
    print(f"entries     {routes['dict']} via a dict, {routes['helper']} via a helper  "
          + "  ".join(f"{c}={kinds[c]}" for c in "ABCD"))
    multi = multi_file_literals(sites)
    print(f"test literals registered in 2+ files: {len(multi)}")
    for lit, paths in sorted(multi.items()):
        print(f"  {lit!r:30} {', '.join(p.rsplit('/', 1)[-1] for p in paths)}")
    if "--list" in argv:
        for s in text_form:
            print(f"  entity_id {s.path}:{s.line}  {ast.unparse(s.entity_id)[:60]}")
        pending = [s for s in test if category(s) == "D"] + [s for s in entries if category(s) != "A"]
        for s in sorted(pending, key=lambda s: (s.path, s.line)):
            print(f"  {category(s)} {s.route:6} {s.path}:{s.line}  {s.kind or '?'}  {ast.unparse(s.entity_id)[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
