"""Doctor audit-writes lint tests (feature 110, Group 11 + Group 15).

Combines four audit lints:

1. **`.meta.json` write allow-list (AC-1.1).** AST walk over
   ``plugins/pd/hooks/lib/workflow_engine/``, ``plugins/pd/mcp/``,
   ``plugins/pd/hooks/lib/doctor/`` (excluding tests / conftest). Any
   ``open(..., 'w')`` / ``Path(...).write_text(...)`` / ``json.dump(fp, ...)``
   that targets ``.meta.json`` MUST live inside a function whose name is in
   ``META_JSON_WRITER_ALLOWLIST``.

2. **`docs/backlog.md` write allow-list (AC-1.2).** Same AST walk pattern,
   allow-listing ``_project_backlog_md`` (the sole writer post-feature-133).

3. **Audit comment proximity (AC-1.1b).** Each allow-listed writer's
   enclosing function MUST have a ``# F4-AUDIT:`` comment within 5 source
   lines.

4. **TD-7b entity_id parsing audit lint (Group 15 / design §5 invariant).**
   Enforces that all ``entity_id``-suffix parsing call sites either live
   inside a ``_migration_13_*`` function or in a test file. Hits anywhere
   else indicate a caller that should have been ported to read seq/slug
   from ``entity_display`` per FR-8.3 but was missed.

Grace mode (design TD-7b): if the entity_id audit finds unported sites,
the lint test is marked ``xfail`` (not ``fail``) so the contract exists
for CI without blocking integration.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Constants — locate plugin paths relative to this file.
# ---------------------------------------------------------------------------

_DOCTOR_DIR = Path(__file__).resolve().parent           # plugins/pd/hooks/lib/doctor
_HOOKS_LIB = _DOCTOR_DIR.parent                          # plugins/pd/hooks/lib
_HOOKS_DIR = _HOOKS_LIB.parent                           # plugins/pd/hooks
_PLUGIN_ROOT = _HOOKS_DIR.parent                         # plugins/pd
_PLUGIN_PD_DIR = _PLUGIN_ROOT                            # alias for clarity
_REPO_ROOT = _PLUGIN_ROOT.parent.parent                  # repo root


# Allow-list for `.meta.json` writes per spec FR-4.1 + design TD-11.
# Per-entry rationale below pinned by feature 127 design D3 / spec FR127-3.
# Feature 133 retired the two MCP-routing-only fix fns that were kept here
# for symbol-level continuity (their TD-11 drift-routing helper retired too).
META_JSON_WRITER_ALLOWLIST: tuple[str, ...] = (
    "_project_meta_json",          # sole FEATURE-meta projection writer -- the sole-truth entry
    "init_project_state",          # PROJECT-meta writer, feature_lifecycle.py:305-306 -- out of 127 scope
)


# Allow-list for `docs/backlog.md` writes per spec FR-4.3.
# Feature 133 retired the annotation-only doctor fix that used to share this
# allow-list; `_project_backlog_md` is now the sole writer.
BACKLOG_MD_WRITER_ALLOWLIST: tuple[str, ...] = (
    "_project_backlog_md",     # MCP projection (canonical write path)
)


# Source trees the AST walk inspects (spec AC-1.1 enumerates these).
AUDIT_TREES: tuple[Path, ...] = (
    _HOOKS_LIB / "workflow_engine",
    _PLUGIN_ROOT / "mcp",
    _HOOKS_LIB / "doctor",
)


# ---------------------------------------------------------------------------
# AST walk helpers (Group 11 — replace stub tests)
# ---------------------------------------------------------------------------


def _iter_python_files(roots: tuple[Path, ...]) -> list[Path]:
    """Yield every .py file under roots, excluding tests and conftest."""
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            # Skip test files and conftests; spec AC-1.1 excludes `*/tests/*`.
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            # Skip any tests/ directories (defensive).
            if "tests" in path.parts:
                continue
            out.append(path)
    return out


def _string_contains_marker(node: ast.AST | None, marker: str) -> bool:
    """Check whether an AST expression is/contains a string constant w/ marker."""
    if node is None:
        return False
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            if marker in inner.value:
                return True
    return False


def _extract_open_mode(call: ast.Call) -> str | None:
    """Return the mode string passed to open() if syntactically determinable.

    Recognizes:
        open(path)             -> 'r' (default)
        open(path, 'w')        -> 'w'
        open(path, mode='w')   -> 'w'
        open(path, 'w', ...)   -> 'w'
    """
    if not call.args and not call.keywords:
        return None
    # Positional mode arg.
    if len(call.args) >= 2:
        mode_node = call.args[1]
        if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
            return mode_node.value
    # Keyword mode arg.
    for kw in call.keywords:
        if (
            kw.arg == "mode"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    # Default mode is 'r' (read).
    return "r"


def _call_func_name(call: ast.Call) -> tuple[str | None, str | None]:
    """Return (root_name, attr_name) describing the call target.

    Examples:
        open(...)            -> ('open', None)
        json.dump(...)       -> ('json', 'dump')
        path.write_text(...) -> (None, 'write_text')
    """
    func = call.func
    if isinstance(func, ast.Name):
        return func.id, None
    if isinstance(func, ast.Attribute):
        # foo.bar(...) -- attr is 'bar'; root only available for Name receivers.
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        return None, func.attr
    return None, None


def _enclosing_function(
    tree: ast.AST, lineno: int
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Return the innermost function/async-function enclosing the line."""
    enclosing = None
    enclosing_span = (0, 10**9)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = node.end_lineno or start
            if start <= lineno <= end:
                span = end - start
                if span < (enclosing_span[1] - enclosing_span[0]):
                    enclosing = node
                    enclosing_span = (start, end)
    return enclosing


def _collect_writes_for_marker(path: Path, marker: str):
    """Return list of (call_node, enclosing_function_node) writing files
    whose path string contains *marker*.

    Detects three patterns:

    1. ``open(<path-with-marker>, 'w')``
    2. ``<path>.write_text(...)`` where path expression contains marker
       as a string literal
    3. ``json.dump(obj, fp)`` where ``fp`` was bound to an
       ``open(<marker>, 'w')`` call in the SAME function body
       (intra-function fp tracking).
    """
    try:
        src = path.read_text()
    except OSError:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    hits = []

    # Pass 1 — for json.dump fp tracking, scan each function body for
    # fp = open(..., 'w') assignments (or `with open(...) as fp:`) where
    # the path string contains the marker.
    func_fp_bindings: dict[int, set[str]] = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fp_bindings: set[str] = set()
        for sub in ast.walk(fn):
            # Direct assignment: fp = open(<path-with-marker>, 'w')
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
                call = sub.value
                root, attr = _call_func_name(call)
                if root == "open" and attr is None:
                    mode = _extract_open_mode(call)
                    if (
                        mode in ("w", "wb", "w+", "wb+", "a")
                        and call.args
                        and _string_contains_marker(call.args[0], marker)
                    ):
                        for tgt in sub.targets:
                            if isinstance(tgt, ast.Name):
                                fp_bindings.add(tgt.id)
            # `with open(<marker>, 'w') as fp:` — track fp.
            if isinstance(sub, (ast.With, ast.AsyncWith)):
                for item in sub.items:
                    if (
                        isinstance(item.context_expr, ast.Call)
                        and item.optional_vars is not None
                    ):
                        call = item.context_expr
                        root, attr = _call_func_name(call)
                        if root == "open" and attr is None:
                            mode = _extract_open_mode(call)
                            if (
                                mode in ("w", "wb", "w+", "wb+", "a")
                                and call.args
                                and _string_contains_marker(call.args[0], marker)
                                and isinstance(item.optional_vars, ast.Name)
                            ):
                                fp_bindings.add(item.optional_vars.id)
        func_fp_bindings[id(fn)] = fp_bindings

    # Pass 2 — scan for actual write Call nodes.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        root, attr = _call_func_name(node)

        # Pattern 1: open(<path>, 'w') -- direct call (incl. as context mgr).
        if root == "open" and attr is None:
            mode = _extract_open_mode(node)
            if (
                mode in ("w", "wb", "w+", "wb+", "a")
                and node.args
                and _string_contains_marker(node.args[0], marker)
            ):
                fn = _enclosing_function(tree, node.lineno)
                hits.append((node, fn))
                continue

        # Pattern 2: x.write_text(...) where receiver expression contains
        # a literal string with the marker.
        if attr in ("write_text", "write_bytes"):
            func = node.func
            if isinstance(func, ast.Attribute):
                if _string_contains_marker(func.value, marker):
                    fn = _enclosing_function(tree, node.lineno)
                    hits.append((node, fn))
                    continue

        # Pattern 3: json.dump(obj, fp) where fp was bound to a marker-open.
        if root == "json" and attr == "dump" and len(node.args) >= 2:
            fp_arg = node.args[1]
            if isinstance(fp_arg, ast.Name):
                fn = _enclosing_function(tree, node.lineno)
                if fn is not None and fp_arg.id in func_fp_bindings.get(id(fn), set()):
                    hits.append((node, fn))
                    continue

    return hits


# ---------------------------------------------------------------------------
# AC-1.1 / AC-1.2 — full AST walks
# ---------------------------------------------------------------------------


def test_no_unaudited_meta_json_writes() -> None:
    """AC-1.1: every .meta.json write must live in an allow-listed function."""
    violations: list[str] = []
    for py_file in _iter_python_files(AUDIT_TREES):
        for call, fn in _collect_writes_for_marker(py_file, ".meta.json"):
            fn_name = fn.name if fn is not None else "<module-level>"
            if fn_name not in META_JSON_WRITER_ALLOWLIST:
                violations.append(
                    f"{py_file.relative_to(_REPO_ROOT)}:{call.lineno} "
                    f"in function {fn_name!r} (allow-list: {META_JSON_WRITER_ALLOWLIST})"
                )
    if violations:
        bullets = "\n".join(f"  - {v}" for v in violations)
        pytest.fail(
            "AC-1.1: found unaudited `.meta.json` writes outside the "
            f"FR-4.1 allow-list ({len(violations)} hits):\n{bullets}"
        )


def test_meta_json_allowlist_exact_membership() -> None:
    """FR127-3 / SC2: META_JSON_WRITER_ALLOWLIST is pinned to its EXACT
    2-member set (shrunk from 4 at feature 133 -- the two MCP-routing-only
    fix fns retired with their TD-11 drift-routing helper). set() coercion
    is mandatory -- the allowlist is a tuple and a literal tuple == set
    comparison is always False (design D3, pinned at design iteration 2).
    Set EQUALITY (not subset) means any NEW writer symbol added to an
    audited tree goes red without an explicit allowlist edit, extending
    128's outliving-teeth posture to the whole sole-writer claim.
    """
    assert set(META_JSON_WRITER_ALLOWLIST) == {
        "_project_meta_json",
        "init_project_state",
    }


def test_scratch_offender_function_is_detected_by_the_ast_walker(tmp_path) -> None:
    """FR128-5: post-128 the allow-list no longer names the deleted
    engine fallback writer -- the audit's teeth must still catch a
    hypothetical FUTURE offender reappearing in the engine. This plants a
    synthetic, non-allow-listed .meta.json writer in a SCRATCH file (never
    touches the real engine.py) and drives it through
    _collect_writes_for_marker -- the same detection primitive
    test_no_unaudited_meta_json_writes walks the real tree with -- proving
    the teeth still bite. Red-first proof the audit mechanism still works,
    not just that today's real tree happens to be clean (a vacuous-green
    risk: FR128-1 deleting the writer could have been paired with an audit
    regression and this suite would stay green either way without this
    test).
    """
    offender = tmp_path / "fake_engine.py"
    offender.write_text(
        "import os\n"
        "\n"
        "def _reintroduced_fallback_writer(artifacts_root, feature_type_id, data):\n"
        "    with open(\n"
        "        os.path.join(\n"
        "            artifacts_root, 'features', feature_type_id, '.meta.json'\n"
        "        ),\n"
        "        'w',\n"
        "    ) as f:\n"
        "        f.write(data)\n"
    )

    hits = _collect_writes_for_marker(offender, ".meta.json")

    assert len(hits) == 1, f"expected the AST walker to flag exactly one write, got {hits}"
    _call_node, fn_node = hits[0]
    assert fn_node is not None
    assert fn_node.name == "_reintroduced_fallback_writer"
    assert fn_node.name not in META_JSON_WRITER_ALLOWLIST, (
        "the synthetic offender must NOT be allow-listed -- if it were, "
        "this test would be proving nothing"
    )


def test_no_unaudited_backlog_md_writes() -> None:
    """AC-1.2: every backlog.md write must live in an allow-listed function."""
    violations: list[str] = []
    for py_file in _iter_python_files(AUDIT_TREES):
        for call, fn in _collect_writes_for_marker(py_file, "backlog.md"):
            fn_name = fn.name if fn is not None else "<module-level>"
            if fn_name not in BACKLOG_MD_WRITER_ALLOWLIST:
                violations.append(
                    f"{py_file.relative_to(_REPO_ROOT)}:{call.lineno} "
                    f"in function {fn_name!r} (allow-list: {BACKLOG_MD_WRITER_ALLOWLIST})"
                )
    if violations:
        bullets = "\n".join(f"  - {v}" for v in violations)
        pytest.fail(
            "AC-1.2: found unaudited `docs/backlog.md` writes outside the "
            f"FR-4.3 allow-list ({len(violations)} hits):\n{bullets}"
        )


# ---------------------------------------------------------------------------
# AC-1.1b — audit comment proximity check
# ---------------------------------------------------------------------------


def _function_lookup(
    path: Path,
) -> dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]]:
    """Return mapping of function-name -> [function nodes] (handles overloads)."""
    try:
        src = path.read_text()
    except OSError:
        return {}
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return {}
    out: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(node)
    return out


def _function_has_audit_comment(
    path: Path,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    marker: str = "# F4-AUDIT:",
) -> bool:
    """Check whether the F4-AUDIT comment appears within 5 lines of the def line.

    Window: [def_lineno - 5, def_lineno + 5] inclusive (1-indexed source lines).
    """
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return False
    start = max(0, fn.lineno - 5 - 1)  # 0-indexed; def_lineno is 1-indexed
    end = min(len(lines), fn.lineno + 5)
    for i in range(start, end):
        if marker in lines[i]:
            return True
    return False


def test_audit_comments_present() -> None:
    """AC-1.1b: every allow-listed writer must carry a F4-AUDIT comment
    within 5 lines of its `def` line.

    Projection functions (`_project_meta_json`, `_project_backlog_md`)
    are EXEMPT — they ARE the canonical write path, not residual writers
    that need an audit comment.

    Feature 133 retired the three fix_actions.py writers that used to be
    named here (their checks and TD-11 drift-routing helper retired too);
    `init_project_state` is the sole remaining allow-listed writer outside
    the exempt projection functions.
    """
    expected_names = [
        "init_project_state",         # feature_lifecycle.py
    ]
    missing: list[str] = []
    found_any: set[str] = set()

    for py_file in _iter_python_files(AUDIT_TREES):
        fn_map = _function_lookup(py_file)
        for name in expected_names:
            for fn in fn_map.get(name, []):
                rel = str(py_file.relative_to(_REPO_ROOT))
                found_any.add(name)
                if not _function_has_audit_comment(py_file, fn):
                    missing.append(
                        f"{name} at {rel}:{fn.lineno} — F4-AUDIT comment "
                        "not within 5 lines"
                    )

    # Every expected writer must be found at least once.
    for name in expected_names:
        if name not in found_any:
            missing.append(
                f"{name} — symbol not located in any AUDIT_TREES file"
            )

    if missing:
        bullets = "\n".join(f"  - {m}" for m in missing)
        pytest.fail(
            "AC-1.1b: missing F4-AUDIT proximity comments on writer "
            f"functions ({len(missing)}):\n{bullets}"
        )


# ---------------------------------------------------------------------------
# Identity-text inference inventory (replaces the TD-7b grep lint)
# ---------------------------------------------------------------------------
#
# The previous lint grepped four fixed patterns, keyed on the literal name
# ``entity_id``, and carried ``@pytest.mark.xfail(strict=False)`` — so it
# could not fail, and found none of the 25 real sites. It was satisfied by
# its own blindness.
#
# This replaces it with an INVENTORY, not an emptiness check. The detected
# set must EQUAL the list below:
#
#   * a new parsing site appears        -> fails (nobody can add one)
#   * a listed site is fixed but not
#     removed from this list            -> fails (shrinkage must be declared)
#
# So the tree is green at every point in the migration, and the list is the
# migration checklist. Done is when only the SANCTIONED entries remain —
# the clean-break boundary parse, which reads a legacy sequence number out
# of id text exactly once so a counter can be raised above it.
#
# Regenerate the detected set with:
#   python -c "import sys;sys.path[:0]=['plugins/pd/hooks/lib'];\
#   from pathlib import Path;from doctor.identity_inference import scan_roots;\
#   [print(s) for s in scan_roots([Path('plugins/pd/hooks/lib'),Path('plugins/pd/mcp')])]"

from doctor.identity_inference import scan_roots  # noqa: E402

_INFERENCE_SCAN_ROOTS = [
    _PLUGIN_PD_DIR / "hooks" / "lib",
    _PLUGIN_PD_DIR / "mcp",
    # B2: the UI is where a wrongly-inferred kind becomes something a person
    # acts on, so templates are in scope exactly as .py files are.
    _PLUGIN_PD_DIR / "ui" / "templates",
]

# (relative path, lineno, idiom, owning task)
#
# Owner assignment for the three formerly-UNOWNED sites (B3b, 2026-09-22):
#
#   database.py:929        sits inside _schema_expansion_v6 (v1 migration 6),
#                          seeding next_seq_{type} from historical entity_id
#                          text at migration time. Same class as :2756, :4199
#                          and :4262. Sanctioned; relabelled, not fixed.
#
#   feature_lifecycle.py:97  _validate_feature_type_id splits type_id on ":"
#                          to build {artifacts_root}/features/{slug}. The path
#                          belongs in entities.artifact_path -> C11. NOTE it is
#                          a TRUST BOUNDARY: it rejects NUL and does a realpath
#                          containment check. A stored artifact_path is not
#                          more trustworthy than a parsed slug -- C11 must move
#                          the source WITHOUT removing the containment check.
#
#   reconciliation.py:787  row["type_id"].startswith("feature:") filters
#                          list_workflow_phases output by kind -> C8. NOTE the
#                          query LEFT JOINs entities, so orphan rows (e.uuid IS
#                          NULL, retained deliberately for anomaly visibility)
#                          get entity_type=None while the current text check
#                          still classifies them as features. C8 must decide
#                          that deliberately and fixture it, not let the join
#                          change it silently.
_KNOWN_INFERENCE_SITES: list[tuple[str, int, str, str]] = [
    ("entity_registry/backfill.py",           756, "split",       "C13 missing-parent policy"),
    ("entity_registry/clean_break.py",        59, "regex",       "B4 SANCTIONED - the one legacy parse"),
    ("entity_registry/clean_break.py",        61, "regex",       "B4 SANCTIONED - the one legacy parse"),
    ("entity_registry/clean_break.py",        64, "regex",       "B4 SANCTIONED - the one legacy parse"),
    ("entity_registry/database.py",           929, "split",       "migration internal - sanctioned"),
    ("entity_registry/database.py",           2756, "sql",         "migration internal - sanctioned"),
    ("entity_registry/database.py",           4199, "sql",         "migration internal - sanctioned"),
    ("entity_registry/database.py",           4262, "sql",         "migration internal - sanctioned"),
    ("entity_registry/database.py",           7577, "regex",       "C6 delete registration parsers"),
    ("entity_registry/database.py",           7711, "slice",       "C6 delete registration parsers"),
    ("entity_registry/database.py",           7712, "slice",       "C6 delete registration parsers"),
    ("entity_registry/database.py",           7713, "slice",       "C6 delete registration parsers"),
    ("entity_registry/frontmatter_inject.py", 82, "split",       "C9 seq/slug from entity_display"),
    ("entity_registry/frontmatter_inject.py", 103, "split",       "C10 parent kind + opaque identity"),
    ("entity_registry/frontmatter_sync.py",   109, "split",       "C8 kind from entities.kind"),
    ("entity_registry/rebuild_tool.py",       1060, "regex",       "C19/C20b rebuild seeds from structure"),
    ("entity_registry/rebuild_tool.py",       1169, "split",       "C19 rebuild seeds from structure"),
    ("workflow_engine/engine.py",             376, "split",       "C11 artifact path"),
    ("workflow_engine/feature_lifecycle.py",  97, "split",       "C11 artifact path"),
    ("workflow_engine/reconciliation.py",     787, "startswith",  "C8 kind from entities.kind"),
    ("workflow_engine/router.py",             358, "split",       "C8 kind from entities.kind"),
    ("workflow_engine/router.py",             421, "split",       "C8 kind from entities.kind"),
    ("../mcp/workflow_state_server.py",       485, "split",       "C9 seq/slug from entity_display"),
    ("../mcp/workflow_state_server.py",       707, "split",       "C9 seq/slug from entity_display"),
    ("../mcp/workflow_state_server.py",       1147, "startswith",  "C8 kind from entities.kind"),
    ("../mcp/workflow_state_server.py",       1429, "startswith",  "C8 kind from entities.kind"),
    ("../ui/templates/_card.html",            4, "split",       "C8 kind - template, view must pass kind"),
    ("../ui/templates/_card.html",            10, "split",       "C8 kind - template, view must pass kind"),
]


def _relative_site_key(path: str) -> str:
    lib = (_PLUGIN_PD_DIR / "hooks" / "lib").resolve()
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(lib))
    except ValueError:
        return "../" + str(resolved.relative_to(_PLUGIN_PD_DIR.resolve()))


def test_identity_inference_inventory_is_exact() -> None:
    """The detected inference sites must EQUAL the declared inventory.

    Not "must be empty" — that would be red for the whole migration and
    would simply get skipped. Not "must be a subset" either: a site fixed
    without being struck off the list would leave the inventory
    permanently overstating the work remaining, and the list is the
    checklist.
    """
    detected = {
        (_relative_site_key(s.path), s.lineno, s.idiom)
        for s in scan_roots(_INFERENCE_SCAN_ROOTS)
    }
    declared = {(p, ln, idiom) for (p, ln, idiom, _owner) in _KNOWN_INFERENCE_SITES}

    added = sorted(detected - declared)
    resolved = sorted(declared - detected)

    problems = []
    if added:
        problems.append(
            "NEW identity-text inference site(s) — read the value from a "
            "column instead (entities.kind, entity_display.seq/slug, "
            "parent_uuid):\n"
            + "\n".join(f"  + {p}:{ln} [{i}]" for (p, ln, i) in added)
        )
    if resolved:
        owners = {(p, ln): o for (p, ln, _i, o) in _KNOWN_INFERENCE_SITES}
        problems.append(
            "Site(s) no longer detected. If you fixed them, delete them from "
            "_KNOWN_INFERENCE_SITES in this file. If a line number merely "
            "shifted, update it:\n"
            + "\n".join(
                f"  - {p}:{ln} [{i}] ({owners.get((p, ln), '?')})"
                for (p, ln, i) in resolved
            )
        )
    if problems:
        pytest.fail("\n\n".join(problems))


# High-water mark for the inventory. It moves UP only when the detector's
# reach widens and the newly-visible sites were always there; it moves DOWN
# whenever a site is actually removed, and never back up for that reason.
#
#   28  initial, scanning hooks/lib + mcp
#   30  B2 (2026-09-22) added ui/templates, surfacing _card.html:4 and :10
#   29  C2 (2026-09-22) removed next_sequence_value's text parse; not lowered until 2026-09-23
#   28  promote_entity deleted (2026-09-23), taking its type_id split (C12) with it
#
# Raising this is a deliberate act with a line in that table, not a way to
# quiet a red test. If the number rose because production grew a NEW parser,
# the entry belongs in the diff being reviewed, not here.
_INVENTORY_HIGH_WATER = 28


def test_inventory_shrinks_to_zero_eventually() -> None:
    """A tripwire on the finish line, not a check of today's count.

    Asserting an exact total here would make every migration step edit two
    places. This only pins the direction: the inventory never grows past
    the high-water mark, and the mark only moves when DETECTION widens.

    The distinction matters. B2 took this from 28 to 30 without a single new
    parser being written — the two template sites predate the effort and were
    invisible because the scan roots did not include ``ui/templates``. A
    tripwire that cannot tell "we found more" from "we wrote more" reports
    the first as a regression and trains its reader to raise the number.
    """
    assert len(_KNOWN_INFERENCE_SITES) <= _INVENTORY_HIGH_WATER, (
        f"the identity-inference inventory grew past its high-water mark "
        f"({_INVENTORY_HIGH_WATER}); it is only allowed to shrink. If a new "
        f"scan root made previously-invisible sites visible, raise the mark "
        f"and add a line to its table. If production grew a new parser, do "
        f"not."
    )
