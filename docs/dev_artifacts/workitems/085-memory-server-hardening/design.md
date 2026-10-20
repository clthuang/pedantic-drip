# Design: Memory Server Hardening (Feature 085)

## Status
- Created: 2026-04-19
- Upstream: `prd.md` (8 FRs), `spec.md` (14 SCs + 24 ACs)
- Research step skipped: spec.md already encodes Stage 2 brainstorm research with verified file:line refs (see `prd.md` Codebase Analysis + Feasibility Assessment). Design grounds the same map in concrete interfaces.

## Architecture Overview

Three modules change; one new module is added. No cross-package topology shifts. pd's inline-test convention is preserved — every test file is co-located with its SUT (Source Under Test) in the same directory.

```
plugins/pd/
├── hooks/lib/
│   ├── semantic_memory/
│   │   ├── config.py                 (unchanged)
│   │   ├── config_utils.py           ← NEW — shared resolve_float_config helper
│   │   ├── ranking.py                ← MODIFIED — imports from config_utils
│   │   ├── test_config_utils.py      ← NEW — FR-4 shared helper tests (bool-handling, clamp, warn-once)
│   │   └── test_ranking.py           ← MODIFIED — migrate 6 call sites (lines 80,85,97,109,124,137)
│   └── pattern_promotion/generators/
│       ├── _md_insert.py             ← MODIFIED — FR-1 entry_name sanitizer
│       ├── test_md_insert.py         ← MODIFIED — APPEND FR-1 sanitization tests to existing file (do NOT create new)
│       ├── hook.py                   ← MODIFIED — FR-7 regex-aware test stubs
│       └── test_hook.py              ← MODIFIED — APPEND FR-7 regex-aware stub tests to existing file
├── mcp/
│   ├── memory_server.py              ← MODIFIED — FR-2/3/5/6 (log perm + rotation + diagnostic schema + single-resolution)
│   └── test_memory_server.py         ← MODIFIED — migrate 6 tuple-unpack sites (lines 1775,1796,1819,1836,1951,2051); update INFLUENCE_DEBUG_LOG_PATH mocks; add FR-3 rotation test
└── hooks/tests/                      ← CROSS-MODULE SNAPSHOT LOCATION (matches spec SC-14)
    ├── test_feature_085_snapshots.py ← NEW — golden-file snapshot tests for _render_block + insert_block
    └── fixtures/feature_085_snapshots/
        ├── input_kb.md
        ├── render_block.md
        └── md_insert.md

validate.sh                           ← MODIFIED — FR-8 docs-sync guards + circular-import smoke test
```

**Test migration discipline:** `test_md_insert.py` and `test_hook.py` already exist at the generators/ paths above — extending them avoids pytest nondeterministic collection from duplicate module names and keeps FR-specific tests co-located with their SUT per pd convention (spec.md Feasibility line 221). New tests for new code (`test_config_utils.py`) are created only where no file exists.

**SC-14 snapshot location:** Golden files live at `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/` per spec SC-14 (cross-module snapshot tests naturally live outside any one package — the SUT spans `pattern_promotion/generators/_md_insert.py` for rendering). Pytest collects `plugins/pd/hooks/tests/test_feature_085_snapshots.py`. Classifier snapshot is DROPPED (see TD-13): `pattern_promotion` has no `classify_entries` top-level function; `classify_keywords(entry)` operates per-entry. Snapshots cover only `_render_block` and `insert_block` outputs, which are the user-facing markdown-writing surfaces.

### Data Flow: pre-PR vs post-PR

**Float-config resolution (pre-PR):**
```
mcp/memory_server.py:319         → _resolve_float_config(key, default)  [local]
mcp/memory_server.py:771-775     → _resolve_float_config(key, default)  [local, 2nd call, redundant]
hooks/lib/semantic_memory/ranking.py → _resolve_weight(config, key, default, *, warned) [local, different signature]
```

**Float-config resolution (post-PR):**
```
semantic_memory/config_utils.py  → resolve_float_config(config, key, default, *, prefix, warned, clamp=None)
                                   ↑           ↑
                    mcp/memory_server.py    semantic_memory/ranking.py
                    (single call site)      (single call site)
                    returns dict with
                    resolved_threshold
                    consumed by MCP
                    wrapper
```

**Influence diagnostic log (post-PR):**
```
_emit_influence_diagnostic:
  1. If log exists and size >= 10 MB:
       try: os.rename(log, log + ".1")    [atomic on POSIX; overwrites any prior .1]
       except OSError: _influence_debug_write_failed (one-shot); skip this write; return
  2. Temporarily umask=0
  3. os.open(log, O_APPEND|O_CREAT|O_WRONLY, 0o600) → os.fdopen(fd, "a", encoding="utf-8")
  4. Restore umask
  5. Write JSON line (no `recorded` field)
  6. Close
```

**HTML comment marker sanitization (post-PR):**
```
_render_block(entry_name, description, mode):
  for bad in _ENTRY_NAME_FORBIDDEN:  # ("-->", "<!--", "```")
    if bad in entry_name:
      raise ValueError(f"entry_name contains forbidden substring: {bad!r}")
  # existing logic: interpolate entry_name into marker, call _sanitize_description(description)
```

**Regex-aware test stub generation (post-PR):**
```
_render_test_sh(feasibility):
  if feasibility["check_kind"] in ("file_path_regex", "content_regex"):
    expr = feasibility["check_expression"]
    if _is_complex_regex(expr):
      positive = GENERIC_POSITIVE_STUB
      comment = "# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually"
    else:
      positive = _construct_matching_sample(expr)
      comment = ""
    ...
```

## Components

### Component 1: `config_utils.py` (new)

**Responsibility:** Single canonical float-config resolver with bool rejection, type coercion, clamp, and one-shot warning.

**Dependencies (hard constraint):** stdlib only + optionally `semantic_memory/config.py` for default lookup convenience. NO imports from `semantic_memory.ranking`, `semantic_memory.database`, `semantic_memory.retrieval_types`, or any `plugins/pd/mcp/*`. Verified at CI by FR-8 circular-import smoke test.

**Public API:**
```python
def resolve_float_config(
    config: dict,
    key: str,
    default: float,
    *,
    prefix: str,
    warned: set,
    clamp: tuple[float, float] | None = None,
) -> float:
    """Resolve a float from config with bool rejection, type coercion, and optional clamp.

    Returns `default` (NOT bool-coerced value) for bool inputs.
    Returns parsed float for valid numeric strings.
    Returns `default` with one-shot warning for invalid types / ValueError.

    Order of type checks (critical — see pre-mortem):
      1. isinstance(raw, bool) → return default with warning  (MUST precede int/float check)
      2. isinstance(raw, (int, float)) → return float(raw), clamp if specified
      3. isinstance(raw, str) → try float(raw); on ValueError → default+warn
      4. else (None, dict, list, custom) → default+warn

    `warned` is a shared set tracking per-key one-shot state; mutated in place.
    `prefix` is the stderr warning prefix (e.g., "[memory-server]", "[ranker]").
    """
```

**Module structure:**
```python
# plugins/pd/hooks/lib/semantic_memory/config_utils.py
from __future__ import annotations
import sys
from typing import Final

__all__ = ["resolve_float_config"]


def _warn_once(key: str, raw: object, default: float, *, prefix: str, warned: set) -> float:
    """Internal helper — one-shot stderr warning per (prefix, key) pair."""
    token = (prefix, key)
    if token not in warned:
        warned.add(token)
        print(
            f"{prefix} config key {key!r} has invalid value {raw!r}; using default {default}",
            file=sys.stderr,
        )
    return default


def resolve_float_config(
    config: dict,
    key: str,
    default: float,
    *,
    prefix: str,
    warned: set,
    clamp: tuple[float, float] | None = None,
) -> float:
    raw = config.get(key, default)
    # Order matters: bool <: int in Python; check bool FIRST.
    if isinstance(raw, bool):
        return _warn_once(key, raw, default, prefix=prefix, warned=warned)
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw)
        except ValueError:
            return _warn_once(key, raw, default, prefix=prefix, warned=warned)
    else:
        return _warn_once(key, raw, default, prefix=prefix, warned=warned)
    if clamp is not None:
        lo, hi = clamp
        if value < lo or value > hi:
            value = max(lo, min(hi, value))
    return value
```

### Component 2: `mcp/memory_server.py` modifications

**FR-4 caller migration:** Delete `_warn_and_default` (lines 428-441) and `_resolve_float_config` (lines 444-463). Replace with:
```python
from semantic_memory.config_utils import resolve_float_config

_warned_fields: set = set()
```
Call-site migration: `_process_record_influence_by_content` (line 319) changes to `resolve_float_config(_config, "memory_influence_threshold", 0.55, prefix="[memory-server]", warned=_warned_fields, clamp=(0.01, 1.0))`. **Clamp preservation**: existing code clamps `memory_influence_threshold` to `[0.01, 1.0]` (line 321 and :778); design preserves this exact range — `clamp=(0.01, 1.0)`, NOT `(0.0, 1.0)`. The second call at wrapper lines 771-775 is deleted per FR-6 (single resolution, consumed via tuple unpack).

**FR-6 single-resolution (tuple return, minimal-scope change):** Verified current function shape at `memory_server.py:293-383`: `_process_record_influence_by_content` currently returns `str` (JSON-encoded via `json.dumps(...)`) with 6 return sites (1 happy-path at :383 + 5 early-return paths at :315, :324, :331, :343, :355). Signature change to tuple minimizes risk vs a dict-shape rewrite:

```python
@with_retry("memory")
def _process_record_influence_by_content(...) -> tuple[str, float]:
    """Returns (json_body_str, resolved_threshold)."""
    if not injected_entry_names:
        return json.dumps({"matched": [], "skipped": 0}), 0.0

    if threshold is None:
        threshold = resolve_float_config(
            _config,
            "memory_influence_threshold",
            0.55,
            prefix="[memory-server]",
            warned=_warned_fields,
            clamp=(0.01, 1.0),   # preserve existing [0.01, 1.0] clamp — NOT a behavior change
        )
    else:
        threshold = max(0.01, min(1.0, threshold))  # preserve caller-passed clamp too

    if np is None:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "numpy unavailable"}), threshold
    if provider is None:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "embedding provider unavailable"}), threshold
    ...  # existing body unchanged
    if not chunks:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "no valid chunks"}), threshold
    ...
    if not chunk_embeddings:
        return json.dumps({"matched": [], "skipped": len(injected_entry_names), "warning": "chunk embedding failed"}), threshold
    ...
    return json.dumps({"matched": matched, "skipped": skipped}), threshold  # happy path
```

Early-return paths that fire BEFORE threshold resolution (only the `not injected_entry_names` case at `:315`) return `0.0` as `resolved_threshold` (unused by wrapper in that case — no diagnostic emission happens with zero entries). All other return paths return the resolved threshold.

The MCP wrapper `record_influence_by_content` (:716-786) unpacks the tuple:
```python
try:
    result_json, resolved_threshold = _process_record_influence_by_content(...)
except Exception as exc:
    return json.dumps({"error": str(exc)})
...
if _config.get("memory_influence_debug", False):
    try:
        parsed = json.loads(result_json)
        matched_count = len(parsed.get("matched", [])) if isinstance(parsed, dict) else 0
    except (json.JSONDecodeError, TypeError):
        matched_count = 0
    _emit_influence_diagnostic(
        matched=matched_count,
        resolved_threshold=resolved_threshold,
        agent_role=agent_role,
        feature_type_id=feature_type_id,
        injected_entry_names=injected_entry_names,
    )
return result_json
```
Delete lines 771-778 (the redundant resolution + independent clamp).

**Test migration (6 call sites):** `plugins/pd/mcp/test_memory_server.py` call sites at lines 1775, 1796, 1819, 1836, 1951, 2051 currently bind `result_json = _process_record_influence_by_content(...)`. Migrate to `result_json, _ = _process_record_influence_by_content(...)` (ignore threshold with `_`) where the test doesn't assert on it. For any test specifically verifying threshold resolution, unpack both and assert.

**`with_retry` decorator interaction:** `with_retry` imported via `from sqlite_retry import with_retry` at `memory_server.py` (current import; relative via `sys.path` insertion) from `plugins/pd/hooks/lib/sqlite_retry.py`. The decorator is return-shape agnostic — it re-invokes the wrapped function on transient SQLite errors and returns whatever the wrapped function returns. Tuple return works identically to str return.

**FR-2 + FR-3 + FR-5:** Rewrite `_emit_influence_diagnostic` (lines 466-500). **Schema preservation:** `injected` field remains `int` (count) per existing test assertion `test_memory_server.py:1906` `assert parsed["injected"] == 3`. Only `recorded` is removed (FR-5). No other JSON keys change.

```python
import os
import json
import sys

_INFLUENCE_DEBUG_ROTATE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
_influence_debug_write_failed: bool = False  # one-shot warning flag


def _emit_influence_diagnostic(
    *,
    agent_role: str,
    injected: int,              # PRESERVED as int count (not list) — matches existing schema
    matched: int,
    resolved_threshold: float,   # NEW — passed by wrapper after single resolution (FR-6)
    feature_type_id: str | None,
) -> None:
    global _influence_debug_write_failed
    path = INFLUENCE_DEBUG_LOG_PATH

    try:
        # FR-3: rotate if size >= 10 MB (POSIX only; best-effort single-writer).
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size >= _INFLUENCE_DEBUG_ROTATE_BYTES:
            os.rename(str(path), str(path) + ".1")  # atomic on POSIX, overwrites .1

        # FR-2: create with 0o600 atomically under umask=0.
        path.parent.mkdir(parents=True, exist_ok=True)
        old_umask = os.umask(0)
        try:
            fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        finally:
            os.umask(old_umask)

        # FR-5: omit `recorded` field (was duplicate of `matched` per TD-4).
        # Schema: {ts, agent_role, injected (int count), matched (int count), threshold, feature_type_id}
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": _utc_now_iso(),
                "agent_role": agent_role,
                "injected": injected,       # int — PRESERVED from pre-PR schema
                "matched": matched,          # int — PRESERVED; `recorded` key DROPPED
                "threshold": resolved_threshold,
                "feature_type_id": feature_type_id,
            }) + "\n")
    except (OSError, IOError) as exc:
        if not _influence_debug_write_failed:
            _influence_debug_write_failed = True
            print(f"[memory-server] influence-debug.log write failed ({exc}); skipping subsequent writes for this process", file=sys.stderr)
```

**Wrapper call preservation:** The MCP wrapper continues to pass `injected=len(injected_entry_names)` (current behavior at `memory_server.py:781`); no test assertion breaks.

### Component 3: `semantic_memory/ranking.py` modifications

**FR-4 caller migration:** Delete `_ranker_warn_and_default` (lines 20-34) and `_resolve_weight` (lines 37-63). Replace imports:
```python
from semantic_memory.config_utils import resolve_float_config

_warned_weights: set = set()
```
All call sites change from `_resolve_weight(config, key, default, warned=_warned_weights)` to `resolve_float_config(config, key, default, prefix="[ranker]", warned=_warned_weights, clamp=(0.0, 1.0))`.

### Component 4: `pattern_promotion/generators/_md_insert.py` modifications

**FR-1 entry_name sanitization:** Add constant and validator at top of `_render_block` (line 114):
```python
_ENTRY_NAME_FORBIDDEN: Final[tuple[str, ...]] = ("-->", "<!--", "```")


def _render_block(entry_name: str, description: str, mode: InsertionMode) -> list[str]:
    for bad in _ENTRY_NAME_FORBIDDEN:
        if bad in entry_name:
            raise ValueError(
                f"entry_name contains forbidden substring {bad!r}; refusing to render"
            )
    # ... existing logic unchanged ...
```

No changes to `_sanitize_description` (description is body content, not comment content — per AC-E1 rationale in spec).

### Component 5: `pattern_promotion/generators/hook.py` modifications

**FR-7 regex-aware test stubs:** Add a complex-regex detector + sample constructor, integrated into `_render_test_sh` (line 269):

```python
import re

# Non-inline-flag substring markers (simple literals).
_COMPLEX_REGEX_MARKERS: Final[tuple[str, ...]] = (
    "(?=", "(?!", "(?<=", "(?<!", "(?P", "(?#",
    "\\1", "\\2", "\\3", "\\4", "\\5", "\\6", "\\7", "\\8", "\\9",
)
# Inline-flag detector catches `(?i)`, `(?s)`, `(?is)`, `(?imsx)` etc.
_INLINE_FLAG_RE: Final[re.Pattern] = re.compile(r"\(\?[aiLmsux]+\)")


def _is_complex_regex(expr: str) -> bool:
    if any(marker in expr for marker in _COMPLEX_REGEX_MARKERS):
        return True
    if _INLINE_FLAG_RE.search(expr):
        return True
    return False


# Known-good samples for the simple-regex ACs (AC-H6/H7/H8) — the constructor
# tries each strategy in order; first match wins; otherwise degrades to "complex".
_REGEX_METACHARS = set(".^$*+?{}[]|()")


def _construct_matching_sample(expr: str) -> str | None:
    """Return a string that matches `expr`, or None if no simple strategy works.

    CONTRACT: Every candidate MUST pass `re.search(expr, candidate)` before
    being returned; on exhaustion without a match, returns None. Caller (verify-
    then-fallback) MUST still re-check before trusting — helper may return a
    candidate that coincidentally matches via regex laxity (e.g., greedy `.*`).

    Worked example for `expr = "^foo$"`:
      - Strategy 1 (no-metachars): fails — expr contains `^`, `$`.
      - Strategy 2 (anchor-strip): candidate = "foo"; re.search("^foo$", "foo") → match; return "foo".

    Worked example for `expr = r"\\.env$"`:
      - Strategy 1 fails (contains `.`, `$`).
      - Strategy 2 strips anchors → `\\.env` (still has `\\.` escape). Candidate construction: `foo.env`.
        Verify `re.search(r"\\.env$", "foo.env")` → match; return "foo.env".

    Worked example for `expr = r"foo|bar"`:
      - Strategy 1 fails (contains `|`).
      - Strategy 3 (alternation) picks leftmost branch `"foo"`.
        Verify → match; return "foo".

    Worked example for `expr = r"[a-z]+@example\\.com"`:
      - Strategies 1,2 fail.
      - Strategy 4 (character class) picks `a` from `[a-z]`, substitutes concrete char,
        recurses on remainder → candidate = "a@example.com".
        Verify → match; return "a@example.com".
    """
    import re
    candidates: list[str] = []

    # Strategy 1: no metachars → use expr verbatim.
    if not any(c in _REGEX_METACHARS for c in expr):
        candidates.append(expr)

    # Strategy 2: strip leading/trailing anchors + decode escapes.
    stripped = expr
    if stripped.startswith("^"):
        stripped = stripped[1:]
    if stripped.endswith("$") and not stripped.endswith(r"\$"):
        stripped = stripped[:-1]
    # Decode simple escapes like \. → .  (but leave \d, \w alone; those fail Strategy 2)
    stripped = re.sub(r"\\([.^$*+?{}\[\]|()])", r"\1", stripped)
    if stripped and not any(c in _REGEX_METACHARS for c in stripped):
        candidates.append(stripped)
    # Also try with padding ("foo" → "xxfooxx") for non-anchored patterns:
    if stripped:
        candidates.append(f"x{stripped}x")

    # Strategy 3: alternation — leftmost branch (recurse on it).
    if "|" in expr and not expr.startswith("\\|"):
        branches = expr.split("|", 1)
        if branches[0]:
            sub_candidate = _construct_matching_sample(branches[0])
            if sub_candidate is not None:
                candidates.append(sub_candidate)

    # Strategy 4: character class — substitute a concrete char.
    class_match = re.search(r"\[([^\]]+)\]", expr)
    if class_match:
        klass = class_match.group(1)
        # Pick first char of class (skip ranges for simplicity; "a-z" → "a")
        concrete = klass[0] if klass and klass[0] != "^" else ""
        if concrete:
            candidate = expr[:class_match.start()] + concrete + expr[class_match.end():]
            # Recurse if remainder still has metachars
            sub = _construct_matching_sample(candidate)
            if sub is not None:
                candidates.append(sub)

    # Strategy 5: best-effort — strip all metachars, pad.
    stripped_all = "".join(c for c in expr if c not in _REGEX_METACHARS)
    if stripped_all:
        candidates.append(f"x{stripped_all}x")

    # Verify each candidate and return the first match.
    for cand in candidates:
        try:
            if re.search(expr, cand):
                return cand
        except re.error:
            # Invalid regex — let caller fall back to complex.
            return None
    return None


def _render_test_sh(feasibility: dict) -> str:
    ...
    check_kind = feasibility.get("check_kind")
    check_expression = feasibility.get("check_expression", "")
    comment_line = ""
    if check_kind in ("file_path_regex", "content_regex"):
        if _is_complex_regex(check_expression):
            positive_input = GENERIC_POSITIVE_STUB
            comment_line = "# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually\n"
        else:
            sample = _construct_matching_sample(check_expression)
            if sample is None or not re.search(check_expression, sample):
                positive_input = GENERIC_POSITIVE_STUB
                comment_line = "# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually\n"
            else:
                positive_input = sample
    ...
```

**Invariant relaxation clarified:** Spec AC-H6/H7/H8 ("simple regex → no complex-regex comment") is BEST-EFFORT, not guaranteed. If `_construct_matching_sample` fails or the verify step misses, the classifier emits the comment (safe fallback). This is correct by design: a generic POSITIVE_INPUT that doesn't match the regex would make the generated test fail — the comment preempts that.

**Decision rule for spec-update trigger:** After implementation, run the AC-H6/H7/H8 test cases. If `_construct_matching_sample` returns a verified match for each (comment absent), spec ACs stand unchanged. If any case triggers fallback (comment emitted), update spec AC-H6/H7/H8 wording to read "the comment MAY be absent" (best-effort) before merging. Do NOT leave the spec/implementation mismatched.

## Interfaces

### I-1: `resolve_float_config` (new, Component 1)
**Signature:** see Component 1. Callers: `mcp/memory_server.py`, `semantic_memory/ranking.py`.

**Invariants:**
- bool inputs (including subclasses) always return default.
- int/float inputs return `float(raw)` with optional clamp.
- string inputs parse via `float()`; ValueError → default + warn.
- Unknown types (None, dict, list, custom) → default + warn.
- Warning is one-shot per `(prefix, key)` tuple across the process lifetime.
- No return value exceeds clamp bounds when `clamp` supplied.

### I-2: `_process_record_influence_by_content` return shape (changed, Component 2)
**Pre-PR:** returns `str` (JSON-encoded body via `json.dumps(...)`). Six return paths — 1 happy (line :383) + 5 early (:315, :324, :331, :343, :355).
**Post-PR:** returns `tuple[str, float]` — `(json_body_str, resolved_threshold)`. All six return paths updated in-place; JSON body semantics unchanged. The MCP wrapper `record_influence_by_content` unpacks the tuple. The first early-return path (`not injected_entry_names`) fires before threshold resolution — returns `0.0` as placeholder; wrapper's diagnostic emission is guarded by `_config.get("memory_influence_debug")` and in practice never emits for zero-entry calls. Test migration required at 6 call sites in `test_memory_server.py` (lines 1775, 1796, 1819, 1836, 1951, 2051): change `result_json = _process...(...)` to `result_json, _ = _process...(...)`.

### I-3: `_emit_influence_diagnostic` (reworked, Component 2)
**Signature (changed from pre-PR):**
```python
def _emit_influence_diagnostic(
    *,
    agent_role: str,
    injected: int,                 # PRESERVED: int count (matches current schema)
    matched: int,                  # PRESERVED
    resolved_threshold: float,     # NEW parameter (was internally re-resolved pre-PR)
    feature_type_id: str | None,
) -> None:
```
Pre-PR signature had `threshold: float` and `injected: int`. Post-PR renames `threshold` → `resolved_threshold` (indicating FR-6's single-resolution contract) and keeps `injected` as int count. Wrapper call-site change: `threshold=effective` → `resolved_threshold=effective` (same value; passed from helper tuple unpack).

**Invariants:**
- Log file mode is 0o600 at creation (tested under umask 0o022).
- Pre-existing log files keep their mode (O_CREAT no-op).
- Rotation to `.1` occurs when `stat().st_size >= 10 MB` prior to each write.
- JSON schema POST-PR: `{ts, agent_role, injected (int), matched (int), threshold, feature_type_id}` — identical to pre-PR except the `recorded` field is DROPPED. `injected` is an int count, NOT a list (schema preservation).
- All OSError / IOError in the write path are caught; first failure emits a one-shot stderr warning; subsequent calls in same process silently skip diagnostic writes.

### I-4: `_render_block` (modified, Component 4)
**Invariant added:** Raises `ValueError` with message `"entry_name contains forbidden substring '{bad}'; refusing to render"` if `entry_name` contains any of `"-->"`, `"<!--"`, or "```". No other behavior change; existing `_sanitize_description` call chain preserved.

### I-5: `_render_test_sh` (modified, Component 5)
**Pre-PR:** POSITIVE_INPUT / NEGATIVE_INPUT use generic strings unrelated to `check_expression`.
**Post-PR:** For `check_kind in {"file_path_regex", "content_regex"}`:
- Simple `check_expression` (no marker from `_COMPLEX_REGEX_MARKERS`): POSITIVE_INPUT is a constructed string matching `re.search(check_expression, POSITIVE_INPUT)`. Empty comment.
- Complex `check_expression`: POSITIVE_INPUT falls back to generic; inject `# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually` comment into the generated script.

### I-6: `validate.sh` additions (FR-8)
New section after line 824, runs on every invocation:
```bash
# --- docs-sync regression guards (from feature 080 AC-7/AC-11) ---
bad_threshold=$(grep -rE --include='*.py' --exclude='test_*.py' \
    'threshold=0\.70' plugins/pd/ | wc -l | tr -d ' ')
[ "$bad_threshold" = "0" ] || {
    echo "FAIL: threshold=0.70 literal resurfaced ($bad_threshold occurrences)"
    exit 1
}
influence_refs=$(grep -c 'memory_influence_' README_FOR_DEV.md || echo 0)
[ "$influence_refs" -ge 3 ] || {
    echo "FAIL: memory_influence_* docs in README_FOR_DEV.md dropped below 3 ($influence_refs)"
    exit 1
}

# --- circular-import smoke test ---
PYTHONPATH=plugins/pd/hooks/lib python3 -c 'from semantic_memory import config_utils; from semantic_memory import ranking' || {
    echo "FAIL: circular import detected in semantic_memory.config_utils"
    exit 1
}
```

## Technical Decisions

| # | Decision | Alternative Considered | Rationale |
|---|----------|------------------------|-----------|
| TD-1 | Place `config_utils.py` in `semantic_memory/` package | Place in `plugins/pd/hooks/lib/` top-level | `memory_server.py` already imports from `semantic_memory.config`; leaf-module precedent; zero new sys.path insertions. |
| TD-2 | `_construct_matching_sample` uses verify-then-fallback | Parse-tree construction via `sre_parse` | `sre_parse` deprecated Python 3.12+; substring detection + verify-via-`re.search` is dependency-light and future-proof. |
| TD-3 | Temporarily force umask=0 via `os.umask(0)` around `os.open` | Rely on operator umask | Umask masks the mode arg of `os.open`; forcing 0 guarantees exact 0o600 per OpenStack guidance. Per-process, no race risk. |
| TD-4 | Rotation is best-effort single-writer; `.1` overwrite on POSIX | File-locking via `fcntl.flock` | Diagnostic log is opt-in debug-only; torn-write consequence is one-line loss, not corruption. fcntl adds complexity for minimal gain on personal tooling. |
| TD-5 | Do NOT migrate `_warn_and_default` int-variant in `refresh.py`/`maintenance.py` | Unify all config helpers into one generic | Return-type differs (int vs float); different clamp semantics; widens scope beyond 8 backlog items. Filed as follow-up consideration. |
| TD-6 | `validate.sh` docs-sync guards use `--exclude='test_*.py'` not `--exclude-dir=tests` | `--exclude-dir=tests` | pd test files are inline (co-located with source in same dir, e.g., `semantic_memory/test_dedup.py`), not in `tests/` subdirs. `--exclude-dir` would miss them. |
| TD-7 | Circular-import smoke test is automated in `validate.sh`, not one-time | Manual dev-only verification | FR-8 SC-7 committed to automated CI enforcement; catches any future `config_utils.py` import violation at every validate run. |
| TD-8 | Entry_name sanitizer raises `ValueError` (fail loud) | Silent escape / replacement | Caller logic needs to know a KB entry was rejected; raising preserves data integrity (refuse to render rather than emit malformed markdown). |
| TD-9 | Snapshot tests (FR-14) use golden files, not property-based | `hypothesis` or similar | NFR-3 bans new deps. Golden files are stdlib pytest; expected outputs baseline-captured during implementation. |
| TD-10 | FR-6 return-shape change uses `tuple[str, float]` | Change to dict; add out-param; keep str + sidechannel attr | Tuple preserves all 6 current return paths' JSON body semantics (least-disruption migration); wrapper unpacks cleanly; tests update by adding `, _` to unpack. Preserving `_process_record_influence_by_content` as str-only would require sidechannel for threshold, which is un-Pythonic. |
| TD-11 | Threshold clamp preserved at `[0.01, 1.0]` | Change to `[0.0, 1.0]` | Current code clamps at `[0.01, 1.0]` (line 321 and :778). Design preserves existing behavior; `threshold=0.0` would match everything, an observable semantic change not justified by the 8-item scope. |
| TD-12 | Inline-flag detection uses `re.Pattern` not literal-substring list | Exact literals like `"(?i)"`, `"(?s)"` | Combined forms like `(?is)`, `(?imsx)` would slip past exact-literal detection. A single regex `\(\?[aiLmsux]+\)` catches all combinations. |
| TD-13 | Drop classifier snapshot from SC-14 | Snapshot every intermediate output | `pattern_promotion.classifier` exposes `classify_keywords(entry)` per-entry, not a document-level `classify_entries`. Snapshotting at the correct granularity (`_render_block`, `insert_block`) covers the user-facing markdown outputs; classifier output is an internal intermediate with no separate user-facing contract. |
| TD-14 | New tests EXTEND existing inline test files; never duplicate module names | Create net-new files under `hooks/tests/` | `test_md_insert.py` and `test_hook.py` already exist at `plugins/pd/hooks/lib/pattern_promotion/generators/`. pd's inline-test convention co-locates tests with SUT. Duplicate module names would cause pytest collection nondeterminism and import-path collisions. Only genuinely new SUT (`config_utils.py`) gets a new test file (`test_config_utils.py` alongside it). |

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R-1 | Bool check-order regression in `resolve_float_config` (pre-mortem's top risk) silently coerces `True`→`1.0` / `False`→`0.0`. | Medium | Medium (ranking drift, no crash) | SC-6 dedicated bool test + SC-7 circular-import smoke; bool check precedes int check in Component 1 implementation. |
| R-2 | Circular import in `config_utils.py`. | Low | High (startup failure) | Hard constraint: config_utils.py imports stdlib + config.py only. Enforced by FR-8 smoke test. |
| R-3 | Rotation race between concurrent MCP processes. | Low | Low (one line in `.1` instead of primary) | Acceptable per AC-E5; POSIX `os.rename` atomicity bounds worst-case loss. |
| R-4 | Mode 0o600 change breaks test mocks that patch `INFLUENCE_DEBUG_LOG_PATH.open`. | Medium | Low (test-only) | Test migration: update mocks to match `os.open`+`os.fdopen` chain. Snapshot tests catch regressions. |
| R-5 | Complex-regex classifier false-positive (treats simple regex as complex). | Medium | Very Low (generic stub is still valid test) | Acceptable; fallback is safe. |
| R-6 | Complex-regex classifier false-negative (constructs sample that doesn't match). | Low | Low | Verify-then-fallback: if `re.search(expr, sample)` misses, caller falls back to complex path. |
| R-7 | `validate.sh` count guard false-passes on renames. | Medium | Low (requires human correction at rename time) | Document in FR-8; acceptable tradeoff per feasibility advisor. |
| R-8 | Test migration incomplete — dangling imports to deleted symbols. | Low | Medium (test failures) | SC-5 dual grep (def-absence + symbol-reference absence) catches dangling refs. |

## Prior Art Research

Stage 2 brainstorm research (2026-04-19) already mapped:
- Atomic write precedent: `workflow_engine/feature_lifecycle.py:30-51` (NTF+replace; inspiration, not direct reuse since we need mode bits).
- Forbidden-substring pattern precedent: `pattern_promotion/generators/hook.py:65` (`_CHECK_EXPR_FORBIDDEN`); FR-1 `_ENTRY_NAME_FORBIDDEN` mirrors.
- Description sanitizer: `_md_insert.py:27-74`; explicitly does NOT handle HTML comment markers (confirmed in spec).
- FTS5 sanitizer: `database.py:17`; different shape (regex-strip-then-rebuild); not reused.
- Test conventions: `tmp_path` fixture, module-level dict constants, NO conftest fixtures (per `test_database.py` / `test_hook.py` idiom).

No new external library or pattern introduced. Design is pure stdlib and follows existing pd conventions.

## Sequencing (implementation order)

Per feasibility advisor + spec Test Migration section:

0. **SC-14 snapshots (FIRST — MUST precede any behavior-affecting change)**: Capture golden-file baselines at `plugins/pd/hooks/tests/fixtures/feature_085_snapshots/` (matches spec SC-14). Run `_render_block(<clean_entry>, <clean_description>, mode)` and `_md_insert.insert_block(<target_md>, <block_lines>)` against the PRE-PR codebase with inputs from `input_kb.md` fixture; write outputs to `render_block.md` and `md_insert.md`. Classifier snapshot DROPPED (TD-13): `pattern_promotion.classifier` exposes only `classify_keywords(entry: KBEntry)` — per-entry, not per-document — so a document-level snapshot has no corresponding public API. The user-facing surfaces (`_render_block`, `insert_block`) are the correct snapshot targets. Commit snapshots and snapshot-test file (new: `plugins/pd/hooks/tests/test_feature_085_snapshots.py`) as part of step 0.
1. **FR-4 foundation**: Create `config_utils.py`. Update `memory_server.py` + `ranking.py` imports + callers. Delete local helpers. Migrate test files (`test_memory_server.py` ~10 refs, `test_ranking.py` ~6 refs). Run pytest to confirm green.
2. **FR-2 + FR-5 + FR-6 batch**: All touch `memory_server.py` around `_emit_influence_diagnostic`. Apply in order: (a) FR-5 remove `recorded` key; (b) FR-6 change `_process_record_influence_by_content` to return `tuple[str, float]`, update wrapper to unpack, delete lines 771-775 redundant resolution, migrate 6 test callers to unpack; (c) FR-2 `os.open + fdopen` with `os.umask(0)` guard. Run pytest.
3. **FR-3 rotation**: Extend `_emit_influence_diagnostic` with size-check + `os.rename`. Add rotation test. Run pytest.
4. **FR-1 + FR-7 generators**: Add `_ENTRY_NAME_FORBIDDEN` to `_md_insert.py`. Add `_is_complex_regex` + `_construct_matching_sample` + integration in `_render_test_sh` to `hook.py`. Create `test_md_insert.py` + `test_hook.py` + `test_config_utils.py`. Run pytest.
5. **FR-8 validate.sh**: Add docs-sync grep section + circular-import smoke test step. Run `./validate.sh` on clean tree.
6. **SC-14 snapshot re-verification**: Re-run snapshot-producing code against POST-PR codebase. Expect byte-identical outputs to baselines captured in step 0. Any drift requires explicit justification in commit message (only FR-1 could plausibly change output if a snapshot fixture contains a forbidden entry_name — fixtures are constructed to avoid this).
7. **Backlog annotations**: Append `(fixed in feature:085-memory-server-hardening)` to all 8 backlog rows (#00067-#00074). Verify via SC-1 shell checks.
8. **Final**: Bump `plugins/pd/plugin.json` dev version. Commit series. Open PR to `develop`.

## Open Questions / Design-Phase Ambiguities
- None. All ambiguities resolved through 3 spec-review iterations and 2 brainstorm-review iterations. Implementation has fully specified signatures, data flow, test mechanisms, and sequencing.
