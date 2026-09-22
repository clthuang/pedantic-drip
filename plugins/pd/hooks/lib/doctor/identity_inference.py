"""Detect code that infers meaning from the TEXT of an entity id.

An entity's identity is structural: ``uuid`` for identity, ``entities.kind``
for kind, ``entity_display(seq, slug)`` for its display number and slug, and
``parent_uuid``/``entity_relations`` for structure. Reading any of those out
of the characters of an ``entity_id`` or ``type_id`` re-derives, by string
surgery, a fact the schema already stores.

The grep this replaces matched four fixed patterns and found none of the
real idioms, because it keyed on the literal variable name ``entity_id``.
Production spells the same value ``eid``, ``feature_type_id``,
``old_type_id``, ``entity["type_id"]``. Recognition here is therefore by
RECEIVER FORM, not by one name — see ``_is_identity_receiver``.

Comments and docstrings cannot produce a site: detection runs over an AST,
so prose naming an idiom is invisible by construction.

There is deliberately no exemption by function-name prefix. A parser hidden
inside a helper whose name happens to start with ``_migration_`` is still a
parser; sanctioned boundaries are named explicitly in the lint's inventory.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Receiver names that denote entity-id TEXT. Suffix-matched so that
# feature_type_id / old_type_id / proj_entity_id / parent_type_id are all
# recognised without enumerating them.
_ID_SUFFIXES = ("entity_id", "type_id")
_ID_ALIASES = frozenset({"eid", "tid"})
_ID_KEYS = frozenset({"entity_id", "type_id"})

# SQL that does the same inference inside a string constant. These never
# appear as Python attribute calls, so the AST walk below inspects string
# literals separately — including module-level constants, which an
# in-function-only walk misses entirely.
_SQL_INFERENCE = re.compile(
    r"substr\s*\(\s*(entity_id|type_id)"
    r"|instr\s*\(\s*(entity_id|type_id)"
    r"|(entity_id|type_id)\s+LIKE\s*'[^']*:",
    re.IGNORECASE,
)

_SEPARATOR_LITERALS = frozenset({":", "-"})


@dataclass(frozen=True)
class InferenceSite:
    path: str
    lineno: int
    idiom: str          # regex | split | slice | startswith | sql
    receiver: str

    def key(self) -> tuple[str, int]:
        return (self.path, self.lineno)

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno} [{self.idiom}] {self.receiver}"


def _name_of(node: ast.AST) -> str | None:
    """Best-effort source-ish name for a receiver expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _name_of(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        base = _name_of(node.value) or "?"
        sl = node.slice
        if isinstance(sl, ast.Constant):
            return f"{base}[{sl.value!r}]"
        return f"{base}[...]"
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return None


def _is_identity_receiver(node: ast.AST) -> bool:
    """True when *node* evaluates to an entity-id / type-id string.

    Four forms, because production uses all four:
      bare name      eid, entity_id, feature_type_id, old_type_id
      subscript      entity["type_id"], row['entity_id']
      .get()         entity.get("type_id")
      attribute      self.entity_id
    """
    if isinstance(node, ast.Name):
        name = node.id
        return name in _ID_ALIASES or name.endswith(_ID_SUFFIXES)
    if isinstance(node, ast.Attribute):
        return node.attr in _ID_ALIASES or node.attr.endswith(_ID_SUFFIXES)
    if isinstance(node, ast.Subscript):
        sl = node.slice
        return isinstance(sl, ast.Constant) and sl.value in _ID_KEYS
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get" and node.args:
            first = node.args[0]
            return isinstance(first, ast.Constant) and first.value in _ID_KEYS
    return False


def _is_separator_split(node: ast.Call) -> bool:
    """``x.split(":")`` / ``.partition("-")`` — a separator, not a general split."""
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and first.value in _SEPARATOR_LITERALS


def iter_inference_sites(tree: ast.AST, path: str) -> Iterator[InferenceSite]:
    """Yield every site in *tree* that derives meaning from id text."""
    for node in ast.walk(tree):
        # --- string constants carrying SQL inference ----------------------
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _SQL_INFERENCE.search(node.value):
                yield InferenceSite(path, node.lineno, "sql", "<sql string>")
            continue

        if not isinstance(node, ast.Call):
            continue
        func = node.func

        if isinstance(func, ast.Attribute):
            recv = func.value
            # --- compiled pattern applied to an id -------------------------
            if func.attr in ("match", "search", "fullmatch"):
                # Two shapes: a compiled pattern applied to an id
                # (``_RE.match(eid)``, id in arg 0) and the module-level
                # form (``re.match(r"^(\d+)", eid)``, id in arg 1). Only
                # checking arg 0 misses every module-level call — which is
                # where database.py's allocator bootstrap parse lives.
                hit = next(
                    (a for a in node.args[:2] if _is_identity_receiver(a)), None
                )
                if hit is not None:
                    yield InferenceSite(
                        path, node.lineno, "regex", _name_of(hit) or "?",
                    )
                    continue
            # --- separator split / partition on an id ----------------------
            if func.attr in ("split", "rsplit", "partition", "rpartition"):
                if _is_identity_receiver(recv) and _is_separator_split(node):
                    yield InferenceSite(
                        path, node.lineno, "split", _name_of(recv) or "?",
                    )
                    continue
            # --- kind sniffing via prefix ----------------------------------
            if func.attr in ("startswith", "endswith"):
                if _is_identity_receiver(recv) and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and ":" in str(first.value):
                        yield InferenceSite(
                            path, node.lineno, "startswith", _name_of(recv) or "?",
                        )
                        continue
            # --- index-of-dash, the precursor to slicing -------------------
            if func.attr in ("index", "find") and _is_identity_receiver(recv):
                if _is_separator_split(node):
                    yield InferenceSite(
                        path, node.lineno, "slice", _name_of(recv) or "?",
                    )
                    continue

    # --- slicing an id: entity_id[:i] / entity_id[i + 1:] -----------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            if _is_identity_receiver(node.value):
                yield InferenceSite(
                    path, node.lineno, "slice", _name_of(node.value) or "?",
                )


def scan_file(path: Path) -> list[InferenceSite]:
    try:
        src = path.read_text()
    except OSError:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    return list(iter_inference_sites(tree, str(path)))


# Jinja expression sites: ``{{ ... }}`` and ``{% set x = ... %}``. A template
# that decomposes a type_id is inferring exactly as a .py file does, and the
# UI is where a wrong kind becomes something a person acts on.
_JINJA_OUTPUT = re.compile(r"\{\{(.*?)\}\}", re.S)
_JINJA_SET = re.compile(r"\{%-?\s*set\s+[A-Za-z_][A-Za-z0-9_]*\s*=(.*?)-?%\}", re.S)


def scan_template(path: Path) -> list[InferenceSite]:
    """Report identity inference inside a Jinja template.

    Each expression is parsed as a Python expression and handed to the same
    ``iter_inference_sites`` the .py path uses, so the two surfaces cannot
    drift apart in what they consider inference.

    Jinja and Python overlap more than they look like they do, so coverage is
    wider than a first guess suggests. Filters (``| upper``, ``| default(x)``)
    parse as Python ``BinOp``; so do ``is defined`` and ``and``/``or`` chains.
    All of those are analysed normally.

    Two Jinja-only forms do NOT parse and are skipped, measured rather than
    assumed:

      * ``~`` string concatenation   -- ``x.type_id.split(':')[0] ~ 'a'``
      * ``if`` without ``else``      -- ``x.type_id.split(':')[0] if cond``

    A site spelled either way goes unreported. That gap is accepted, not
    overlooked: adding a Jinja parser to a lint is more machinery than two
    known sites justify. ``TestTemplateScanning`` pins both forms so the
    blind spot stays a decision on record.
    """
    try:
        src = path.read_text()
    except OSError:
        return []
    sites: list[InferenceSite] = []
    for pattern in (_JINJA_OUTPUT, _JINJA_SET):
        for m in pattern.finditer(src):
            expr = m.group(1).strip()
            if not expr:
                continue
            try:
                tree = ast.parse(expr, mode="eval")
            except SyntaxError:
                continue
            # ast linenos are relative to the snippet; rebase onto the file.
            base = src.count("\n", 0, m.start(1)) + 1
            for site in iter_inference_sites(tree, str(path)):
                sites.append(
                    InferenceSite(
                        path=site.path,
                        lineno=base + site.lineno - 1,
                        idiom=site.idiom,
                        receiver=site.receiver,
                    )
                )
    return sites


def scan_roots(roots, *, skip_tests: bool = True) -> list[InferenceSite]:
    """Scan every ``*.py`` and ``*.html`` under *roots*, sorted by (path, lineno)."""
    sites: list[InferenceSite] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for py in sorted(root.rglob("*.py")):
            if skip_tests and py.name.startswith("test_"):
                continue
            if ".venv" in py.parts:
                continue
            sites.extend(scan_file(py))
        for tpl in sorted(root.rglob("*.html")):
            if ".venv" in tpl.parts:
                continue
            sites.extend(scan_template(tpl))
    return sorted(sites, key=lambda s: (s.path, s.lineno))
