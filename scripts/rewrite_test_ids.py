"""Wave 2 step 1 — rewrite every registered test id to round-trip form.

One repo-wide mapping, keyed on (kind, literal), is built from the census
(census_register_sites.py). String constants in test and conftest files under
plugins/pd are rewritten in the three positions the plan's D4 allows:

1. the id a registration receives: a family call's argument, a dict's
   "entity_id" value, a test helper's argument (first hop);
2. a constant exactly "{kind}:{literal}", in a file that registers the literal;
3. a bare constant equal to the literal, in a file that registers it, when the
   literal holds a digit or hyphen and every kind that file registers it under
   maps it to the same new id.

The 25 _register_entity_no_display calls become plain register_entity calls
(with strict off that changes nothing). What it declines in a registering file
is listed for hand review; files that never register a literal are left alone,
since their copies are mostly unrelated text (a mermaid node, an empty string).
After review, --check is the gate: no old literal holding a digit or hyphen may
stay in any test string constant unless ALLOWED says why.

    plugins/pd/.venv/bin/python scripts/rewrite_test_ids.py [--review PATH]   # dry run
    plugins/pd/.venv/bin/python scripts/rewrite_test_ids.py --apply
    plugins/pd/.venv/bin/python scripts/rewrite_test_ids.py --check
"""
from __future__ import annotations

import argparse
import ast
import collections
import dataclasses
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import census_register_sites as census  # noqa: E402
from entity_registry.id_generator import NON_SEQUENCE_KINDS  # noqa: E402

MAPPING = Path(__file__).with_name("wave2_step1_mapping.tsv")
# Brainstorm stems in production start with a date; fixtures get a fixed one.
BRAINSTORM_DATE = 20260101
HELPER = "_register_entity_no_display"
_EDGE = r"A-Za-z0-9_-"
_SEQ_SLUG = re.compile(r"(\d+)-(.+)")
# Occurrences --check tolerates after hand review: (path, line, old literal) -> why.
ALLOWED: dict[tuple[str, int, str], str] = {}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def needs_rewrite(kind: str | None, literal: str) -> bool:
    if kind in NON_SEQUENCE_KINDS:
        return not census.STRICT_ID_RE.match(literal)
    return not census.round_trips(literal)


def candidate(kind: str | None, literal: str, brainstorm_n: int | None) -> str | None:
    """The new id for one registered literal, or None when a person must decide.

    ``brainstorm_n`` is set only for literals registered solely as brainstorms.
    """
    if brainstorm_n is not None:
        slug = slugify(literal)
        return f"{BRAINSTORM_DATE}-{brainstorm_n:06d}-{slug}" if slug else None
    if match := _SEQ_SLUG.fullmatch(literal):
        return f"{int(match[1]):03d}-{match[2]}" if int(match[1]) >= 1 else None
    if literal.isdigit():
        return f"{int(literal):03d}-{kind}" if int(literal) >= 1 and kind else None
    if literal[:1].isdigit():
        return None
    slug = slugify(literal)
    return f"001-{slug}" if slug else None


def _bump(new_id: str) -> str:
    match = _SEQ_SLUG.fullmatch(new_id)
    return f"{int(match[1]) + 1:03d}-{match[2]}"


def registrations(root: Path = census.PLUGIN) -> list[census.Site]:
    """Test sites and entries whose id is a literal; a missing kind is filled in
    when the same file registers that literal under exactly one kind."""
    regs = [s for s in census.find_sites(root) + census.find_entries(root)
            if s.is_test and s.literal is not None]
    known = collections.defaultdict(set)
    for s in regs:
        if s.kind:
            known[(s.path, s.literal)].add(s.kind)
    return [dataclasses.replace(s, kind=next(iter(known[(s.path, s.literal)])))
            if s.kind is None and len(known[(s.path, s.literal)]) == 1 else s
            for s in regs]


@dataclasses.dataclass
class Mapping:
    new: dict[tuple[str | None, str], str]
    refused: dict[tuple[str | None, str], str]
    stepped: list[tuple[str | None, str]]


def build_mapping(regs: list[census.Site]) -> Mapping:
    """Every (kind, literal) whose literal is not yet in target form under some kind."""
    kinds_of, files_of, texts_in = (collections.defaultdict(set) for _ in range(3))
    for s in regs:
        kinds_of[s.literal].add(s.kind)
        files_of[s.literal].add(s.path)
        texts_in[s.path].add(s.literal)
    todo = sorted(lit for lit, kinds in kinds_of.items() if any(needs_rewrite(k, lit) for k in kinds))
    only_brainstorm = [lit for lit in todo if kinds_of[lit] <= NON_SEQUENCE_KINDS]
    brainstorm_n = {lit: n for n, lit in enumerate(only_brainstorm, 1)}
    mapping = Mapping({}, {}, [])
    new_in_file = collections.defaultdict(dict)   # path -> {new id: literal}
    new_of_kind = collections.defaultdict(dict)   # kind -> {new id: literal}
    for lit in todo:
        sequence_kinds = sorted(k for k in kinds_of[lit] if k and k not in NON_SEQUENCE_KINDS)
        for kind in sorted(kinds_of[lit], key=lambda k: k or ""):
            # A literal also registered under a sequence kind takes that kind's id
            # as a brainstorm too, so its bare references stay unambiguous.
            as_kind = kind if kind not in NON_SEQUENCE_KINDS or not sequence_kinds else sequence_kinds[0]
            new = candidate(as_kind, lit, brainstorm_n.get(lit))
            if new is None:
                mapping.refused[(kind, lit)] = ("kind unknown" if kind is None else
                                                "seq 0" if lit[:1] == "0" and lit.strip("0-")[:1] != lit[:1] else
                                                "no slug or no rule")
                continue
            first = new

            def taken(new_id: str) -> bool:
                return (new_of_kind[kind].get(new_id, lit) != lit
                        or any(new_id in texts_in[f] and new_id != lit for f in files_of[lit])
                        or any(new_in_file[f].get(new_id, lit) != lit for f in files_of[lit]))

            while taken(new):
                new = _bump(new)
            if new != first:
                mapping.stepped.append((kind, lit))
            mapping.new[(kind, lit)] = new
            new_of_kind[kind][new] = lit
            for f in files_of[lit]:
                new_in_file[f][new] = lit
    return mapping


@dataclasses.dataclass(frozen=True)
class Edit:
    path: str
    line: int
    col: int        # UTF-8 byte offsets, as ast reports them
    end_col: int
    old: str        # source text replaced
    new: str
    position: str   # "1", "2", "3", or "helper call"


@dataclasses.dataclass(frozen=True)
class Review:
    path: str
    line: int
    literal: str
    reason: str


def _test_files(root: Path):
    yield from census._parse(root, tests_only=True)


def plan_edits(regs: list[census.Site], mapping: Mapping, root: Path = census.PLUGIN):
    reg_at = {(s.path, s.entity_id.lineno, s.entity_id.col_offset): (s.kind, s.literal) for s in regs}
    registered = collections.defaultdict(lambda: collections.defaultdict(set))  # path -> literal -> kinds
    for s in regs:
        registered[s.path][s.literal].add(s.kind)
    composite = {f"{kind}:{lit}": (lit, f"{kind}:{new}") for (kind, lit), new in mapping.new.items() if kind}
    mapped = {lit for _, lit in mapping.new} | {lit for _, lit in mapping.refused}
    edits, reviews = [], []
    for rel, tree in _test_files(root):
        source = (root / rel).read_text(encoding="utf-8").splitlines()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == HELPER):
                func = node.func
                edits.append(Edit(rel, func.end_lineno, func.end_col_offset - len(HELPER),
                                  func.end_col_offset, HELPER, "register_entity", "helper call"))
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            value = node.value
            key = (rel, node.lineno, node.col_offset)
            new = None
            if key in reg_at and reg_at[key] in mapping.new:
                new, position = mapping.new[reg_at[key]], "1"
            elif value in composite and composite[value][0] in registered[rel]:
                new, position = composite[value][1], "2"
            elif value in registered[rel] and value in mapped:
                news = {mapping.new.get((k, value)) for k in registered[rel][value]}
                if len(news) == 1 and None not in news and re.search(r"[\d-]", value):
                    new, position = news.pop(), "3"
                else:
                    reviews.append(Review(rel, node.lineno, value,
                                          "plain word" if not re.search(r"[\d-]", value) else
                                          "refused" if None in news else "kinds disagree"))
            if new is None:
                continue
            segment = _segment(source, node)
            quote = segment[:1]
            if node.lineno != node.end_lineno or segment != f"{quote}{value}{quote}" or quote not in "'\"":
                reviews.append(Review(rel, node.lineno, value, "unusual literal syntax"))
                continue
            edits.append(Edit(rel, node.lineno, node.col_offset, node.end_col_offset,
                              segment, f"{quote}{new}{quote}", position))
    return edits, reviews


def _segment(source: list[str], node: ast.expr) -> str:
    if node.lineno != node.end_lineno:
        return ""
    raw = source[node.lineno - 1].encode("utf-8")
    return raw[node.col_offset:node.end_col_offset].decode("utf-8", errors="replace")


def apply(edits: list[Edit], root: Path = census.PLUGIN) -> None:
    by_path = collections.defaultdict(list)
    for edit in edits:
        by_path[edit.path].append(edit)
    for rel, file_edits in by_path.items():
        path = root / rel
        lines = path.read_text(encoding="utf-8").split("\n")
        for edit in sorted(file_edits, key=lambda e: (e.line, e.col), reverse=True):
            raw = lines[edit.line - 1].encode("utf-8")
            assert raw[edit.col:edit.end_col].decode("utf-8") == edit.old, edit
            lines[edit.line - 1] = (raw[:edit.col] + edit.new.encode("utf-8") + raw[edit.end_col:]).decode("utf-8")
        path.write_text("\n".join(lines), encoding="utf-8")


def write_mapping(mapping: Mapping, path: Path = MAPPING) -> None:
    rows = ["kind\told\tnew"] + [f"{kind or ''}\t{lit}\t{new}" for (kind, lit), new in sorted(
        mapping.new.items(), key=lambda item: (item[0][1], item[0][0] or ""))]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def read_old_literals(path: Path = MAPPING) -> set[str]:
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return {row.split("\t")[1] for row in rows}


def leftovers(old_literals: set[str], root: Path = census.PLUGIN) -> list[Review]:
    """Token-bounded hits of old literals holding a digit or hyphen, in test string constants."""
    gated = sorted((lit for lit in old_literals if re.search(r"[\d-]", lit)), key=len, reverse=True)
    if not gated:
        return []
    pattern = re.compile(rf"(?<![{_EDGE}])(?:{'|'.join(map(re.escape, gated))})(?![{_EDGE}])")
    hits = []
    for rel, tree in _test_files(root):
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for match in pattern.finditer(node.value):
                    hits.append(Review(rel, node.lineno, match[0], "left after step 1"))
    return sorted(set(hits), key=lambda r: (r.path, r.line, r.literal))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--review", type=Path, help="write the hand-review list here (TSV)")
    args = parser.parse_args(argv)
    if args.check:
        hits = [h for h in leftovers(read_old_literals())
                if (h.path, h.line, h.literal) not in ALLOWED]
        for h in hits:
            print(f"{h.path}:{h.line}\t{h.literal}")
        print(f"{len(hits)} old ids left outside ALLOWED ({len(ALLOWED)} allowed)")
        return 1 if hits else 0
    regs = registrations()
    mapping = build_mapping(regs)
    edits, reviews = plan_edits(regs, mapping)
    positions = collections.Counter(e.position for e in edits)
    reasons = collections.Counter(r.reason for r in reviews)
    print(f"mapping     {len(mapping.new)} (kind, literal) pairs, {len(mapping.stepped)} stepped past a collision, "
          f"{len(mapping.refused)} refused")
    for (kind, lit), why in sorted(mapping.refused.items(), key=lambda i: i[0][1]):
        print(f"  refused   {kind or '?'}:{lit!r}  {why}")
    print("edits       " + "  ".join(f"{p}={n}" for p, n in sorted(positions.items())))
    print("review      " + "  ".join(f"{r}={n}" for r, n in sorted(reasons.items())))
    if args.review:
        args.review.write_text("".join(f"{r.path}:{r.line}\t{r.literal}\t{r.reason}\n"
                                       for r in sorted(reviews, key=lambda r: (r.path, r.line))), encoding="utf-8")
    if args.apply:
        apply(edits)
        write_mapping(mapping)
        print(f"applied {len(edits)} edits; mapping written to {MAPPING.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
