"""Hook-target DiffPlan generator.

Per design C-6 / I-5 / FR-3-hook:

- `validate_feasibility(feasibility) -> (bool, Optional[str])` — schema check
  on the LLM's feasibility JSON. Rejects empty tools list, non-list tools,
  unknown tool enum values, unknown event, unknown check_kind, and empty
  check_expression. Returns a precise reason on failure so the skill can
  re-ask the LLM.

- `generate(entry, target_meta, *, plugin_root) -> DiffPlan` emits THREE
  FileEdits:
    0. `plugins/pd/hooks/{slug}.sh` (or `-2`, `-3`... on collision)
    1. `plugins/pd/hooks/tests/test-{slug}.sh` — deterministic TD-7 verifier
       with POSITIVE_INPUT (must block / exit non-zero inside the hook) and
       NEGATIVE_INPUT (must pass / exit zero inside the hook).
    2. `plugins/pd/hooks/hooks.json` — patched copy registering the new hook
       for the specified event + tools; preserves every existing entry.

  Every generated artifact carries a TD-8 marker comment near the top
  referencing the KB entry name.

Design intent: deterministic skeleton generation. No LLM calls here — the
LLM only produces the `feasibility` dict upstream (step 1), which this module
validates and then uses as input to fixed templates.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pattern_promotion.types import DiffPlan, FileEdit


# Closed enums per spec FR-3-hook step 1.
_ALLOWED_EVENTS = {"PreToolUse", "PostToolUse"}
_ALLOWED_TOOLS = {
    "Edit",
    "Bash",
    "Write",
    "Read",
    "Glob",
    "Grep",
    "MultiEdit",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Task",
    "Skill",
}
_ALLOWED_CHECK_KINDS = {
    "file_path_regex",
    "content_regex",
    "json_field",
    "composite",
}
_REQUIRED_KEYS = ("event", "tools", "check_kind", "check_expression")

# Characters / substrings that enable shell command substitution when
# embedded into a shell script, even inside single-quoted / escaped strings
# once the value is spliced into a jq program. Rejecting them up front keeps
# the generator templates simple and safe.
_CHECK_EXPR_FORBIDDEN = ("`", "$(", "\x00", "\n", "\r")


# Feature 085 FR-7: regex-aware test stub generation.
#
# Substrings whose presence in a regex makes constructing a matching
# sample via stdlib verify-then-fallback unreliable. Classifier is a
# pure substring / single-regex test — NO `sre_parse` dependency (that
# module is deprecated in Python 3.12+). False-positives are acceptable
# because the fallback for "complex" regexes is the safe generic stub
# + a comment.
_COMPLEX_REGEX_MARKERS: tuple[str, ...] = (
    "(?=", "(?!", "(?<=", "(?<!", "(?P", "(?#",
    "\\1", "\\2", "\\3", "\\4", "\\5",
    "\\6", "\\7", "\\8", "\\9",
)
# Inline-flag detector catches `(?i)`, `(?s)`, `(?is)`, `(?imsx)` etc.
_INLINE_FLAG_RE = re.compile(r"\(\?[aiLmsux]+\)")

# Marker comment injected into the generated test script when the
# classifier treats a regex as complex. Exact text is asserted by
# ACs H9 / E11 / E12.
_COMPLEX_REGEX_NOTE = (
    "# NOTE: regex too complex for auto-embedded POSITIVE_INPUT — review manually"
)

# Generic stub values used when the classifier falls back to complex.
_GENERIC_POSITIVE_FILE_PATH = "relative/path/file.txt"
_GENERIC_NEGATIVE_FILE_PATH = "/absolute/path/file.txt"
_GENERIC_POSITIVE_CONTENT = "TRIGGERING content here"
_GENERIC_NEGATIVE_CONTENT = "safe content here"

# Regex metacharacters used by Strategy 1 (no-metachar) and Strategy 5
# (strip-all) in `_construct_matching_sample`.
_REGEX_METACHARS = set(".^$*+?{}[]|()\\")


def _is_complex_regex(expr: str) -> bool:
    """Classify a regex as complex (lookaround, inline flag, backref)."""
    for marker in _COMPLEX_REGEX_MARKERS:
        if marker in expr:
            return True
    if _INLINE_FLAG_RE.search(expr):
        return True
    return False


def _construct_matching_sample(expr: str) -> Optional[str]:
    """Return a string that matches ``expr`` via stdlib-only strategies.

    Returns ``None`` if no simple strategy yields a verified match.
    The caller (``_render_test_sh``) MUST still re-check by running
    ``re.search(expr, candidate)`` before using the sample — this
    helper may return candidates that pass verification but the
    outer caller enforces contract.

    Strategies tried in order; first verified match wins:
      1. No regex metachars → use ``expr`` verbatim.
      2. Strip leading ``^`` / trailing ``$`` anchors, decode simple
         escapes like ``\\.`` → ``.``; also try padded variant
         ``"x{body}x"`` for non-anchored cases.
      3. Alternation ``A|B`` → recurse on leftmost branch ``A``.
      4. Character class ``[abc...]`` → substitute first concrete
         character of the class (skipping ranges and negation),
         recurse on the remainder.
      5. Last resort: strip all metachars and pad → ``"x{stripped}x"``.
    """
    candidates: list[str] = []

    # Strategy 1: no metachars.
    if not any(c in _REGEX_METACHARS for c in expr):
        candidates.append(expr)

    # Strategy 2: strip anchors + decode single-char escapes.
    # The candidate is a plain string; whether its characters happen to
    # overlap with regex metacharacters is irrelevant — what matters is
    # whether `re.search(original_expr, candidate)` matches. The verify
    # loop at the bottom of this function decides; we just enumerate
    # plausible candidates.
    stripped = expr
    if stripped.startswith("^"):
        stripped = stripped[1:]
    if stripped.endswith("$") and not stripped.endswith(r"\$"):
        stripped = stripped[:-1]
    # Decode simple escapes like \. → . (but not \d, \w, \s class shorthands).
    decoded = re.sub(r"\\([.^$*+?{}\[\]|()\\])", r"\1", stripped)
    if decoded:
        candidates.append(decoded)
        # Padded variant helps when the regex lacks explicit anchors
        # and `re.search` would still find the decoded body within.
        candidates.append(f"x{decoded}x")

    # Strategy 3: leftmost alternation branch.
    if "|" in expr and not expr.startswith("\\|"):
        first_branch = expr.split("|", 1)[0]
        if first_branch:
            sub = _construct_matching_sample(first_branch)
            if sub is not None:
                candidates.append(sub)

    # Strategy 4: character class substitution.
    class_match = re.search(r"\[([^\]]+)\]", expr)
    if class_match:
        klass = class_match.group(1)
        # Skip negated classes and empty classes for simplicity.
        if klass and not klass.startswith("^"):
            concrete = klass[0]
            substituted = expr[: class_match.start()] + concrete + expr[class_match.end():]
            sub = _construct_matching_sample(substituted)
            if sub is not None:
                candidates.append(sub)

    # Strategy 4b: drop quantifiers that follow a single literal /
    # character-class. `a+` → `a`, `foo*` → `foo` (trailing char kept).
    # Applied AFTER Strategy 4 so the class-substituted expression has
    # already made the quantified base a plain char.
    quant_stripped = re.sub(r"([^\\])[+*?]", r"\1", expr)
    if quant_stripped != expr:
        sub = _construct_matching_sample(quant_stripped)
        if sub is not None:
            candidates.append(sub)

    # Strategy 5: last-resort strip-all-metachars + pad.
    all_stripped = "".join(c for c in expr if c not in _REGEX_METACHARS)
    if all_stripped:
        candidates.append(f"x{all_stripped}x")

    # Verify candidates; return the first that matches.
    for cand in candidates:
        try:
            if re.search(expr, cand):
                return cand
        except re.error:
            return None
    return None


# ---------------------------------------------------------------------------
# Feasibility validator
# ---------------------------------------------------------------------------


def validate_feasibility(
    feasibility: dict,
) -> tuple[bool, Optional[str]]:
    """Validate the LLM-produced feasibility dict against FR-3-hook schema.

    Returns (True, None) on success, else (False, human-readable reason).
    """
    if not isinstance(feasibility, dict):
        return False, "feasibility must be a JSON object"

    for key in _REQUIRED_KEYS:
        if key not in feasibility:
            return False, f"missing required key: {key!r}"

    event = feasibility["event"]
    tools = feasibility["tools"]
    check_kind = feasibility["check_kind"]
    check_expression = feasibility["check_expression"]

    if event not in _ALLOWED_EVENTS:
        return (
            False,
            f"event {event!r} is not one of {sorted(_ALLOWED_EVENTS)}",
        )
    if not isinstance(tools, list):
        return False, "tools must be an array"
    if len(tools) == 0:
        return (
            False,
            "tools array must contain at least one tool name from the enum",
        )
    for t in tools:
        if t not in _ALLOWED_TOOLS:
            return (
                False,
                f"unknown tool {t!r}; expected one of {sorted(_ALLOWED_TOOLS)}",
            )
    if check_kind not in _ALLOWED_CHECK_KINDS:
        return (
            False,
            f"check_kind {check_kind!r} not in {sorted(_ALLOWED_CHECK_KINDS)}",
        )
    if not isinstance(check_expression, str) or not check_expression.strip():
        return False, "check_expression must be a non-empty string"
    for bad in _CHECK_EXPR_FORBIDDEN:
        if bad in check_expression:
            return (
                False,
                f"check_expression contains forbidden substring {bad!r} "
                "(shell command substitution / control characters are rejected)",
            )

    return True, None


def _shell_double_quote_escape(s: str) -> str:
    """Escape a string for safe embedding inside a bash double-quoted context.

    Escapes the four characters that retain meaning inside double quotes:
    backslash, double quote, dollar sign, and backtick. Order matters —
    backslash must be escaped first.
    """
    return (
        s.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace('"', '\\"')
    )


def _shell_single_quote_escape(s: str) -> str:
    """Escape a string for safe embedding inside a bash single-quoted literal.

    Uses the classic close-quote / escape-quote / reopen-quote technique.
    """
    return s.replace("'", "'\\''")


# ---------------------------------------------------------------------------
# Slug derivation
# ---------------------------------------------------------------------------


_STRIP_PREFIXES = ("anti-pattern: ", "pattern: ", "heuristic: ")


def _slugify(entry_name: str) -> str:
    """Deterministic kebab-case slug derived from the entry name.

    - lowercase
    - replace runs of non-alphanumeric with single hyphen
    - strip leading/trailing hyphens
    - strip known markdown-style prefixes before slugging
    """
    stripped = entry_name.lower().strip()
    for pfx in _STRIP_PREFIXES:
        if stripped.startswith(pfx):
            stripped = stripped[len(pfx):]
            break
    slug = re.sub(r"[^a-z0-9]+", "-", stripped)
    slug = slug.strip("-")
    return slug or "promoted-hook"


def _resolve_collision(
    hooks_dir: Path, slug: str
) -> str:
    """Return an unused slug in `hooks_dir`, suffixing `-2`, `-3`, ... if needed.

    Collision means `{slug}.sh` exists.
    """
    if not (hooks_dir / f"{slug}.sh").exists():
        return slug
    i = 2
    while (hooks_dir / f"{slug}-{i}.sh").exists():
        i += 1
    return f"{slug}-{i}"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _render_hook_sh(
    entry_name: str, slug: str, feasibility: dict
) -> str:
    """Render the hook shell script body.

    The template is intentionally minimal: it reads stdin JSON, extracts the
    relevant field by check_kind, applies the regex, and exits non-zero with
    an explanation on match (block). Non-match exits 0 (allow).
    """
    event = feasibility["event"]
    tools_csv = ", ".join(feasibility["tools"])
    check_kind = feasibility["check_kind"]
    check_expr = feasibility["check_expression"]

    # jq filter: extract the field to test based on check_kind.
    # - file_path_regex: tool input .file_path, .path, or .pattern (first match)
    # - content_regex:   tool input .content or .new_string
    # - json_field:      user-supplied jq path literal
    # - composite:       concatenate file_path + content
    if check_kind == "file_path_regex":
        extractor = ".tool_input.file_path // .tool_input.path // .tool_input.pattern // \"\""
    elif check_kind == "content_regex":
        extractor = ".tool_input.content // .tool_input.new_string // \"\""
    elif check_kind == "json_field":
        # Treat check_expression as both extractor path AND the regex source.
        # For json_field we expect check_expression to be a jq path; the regex
        # is ".+" (any value present = match). Keep template simple; the LLM
        # producing this path owns correctness.
        extractor = check_expr
    else:  # composite
        extractor = (
            "((.tool_input.file_path // .tool_input.path // \"\") + \" \" "
            "+ (.tool_input.content // .tool_input.new_string // \"\"))"
        )

    # For json_field, match succeeds if the extracted value is non-empty.
    if check_kind == "json_field":
        regex_literal = ".+"
    else:
        regex_literal = check_expr

    # Escape user-controlled strings for their embedding contexts.
    # regex_literal and extractor are embedded inside single-quoted shell
    # literals: close-quote-escape-reopen the embedded apostrophe.
    # entry_name appears in bash COMMENT lines and inside a double-quoted
    # echo. Comment lines must not carry newlines; the double-quoted echo
    # must escape ", $, `, and \.
    esc_regex = _shell_single_quote_escape(regex_literal)
    esc_extractor = _shell_single_quote_escape(extractor)
    entry_name_comment = entry_name.replace("\r", " ").replace("\n", " ")
    entry_name_dq = _shell_double_quote_escape(entry_name_comment)

    return (
        f"#!/usr/bin/env bash\n"
        f"# Promoted from KB entry: {entry_name_comment}\n"
        f"# Event: {event}  Tools: {tools_csv}  check_kind: {check_kind}\n"
        f"# Auto-generated by /pd:promote-pattern. Review and refine as needed.\n"
        f"set -eu\n"
        f"\n"
        f"INPUT=$(cat)\n"
        f"FIELD=$(echo \"$INPUT\" | jq -r '{esc_extractor}' 2>/dev/null || echo \"\")\n"
        f"REGEX='{esc_regex}'\n"
        f"\n"
        f"if [[ -n \"$FIELD\" ]] && echo \"$FIELD\" | grep -Eq \"$REGEX\"; then\n"
        f"  echo \"[{slug}] blocked by promoted pattern: {entry_name_dq}\" >&2\n"
        f"  echo \"  matched field: $FIELD\" >&2\n"
        f"  exit 2\n"
        f"fi\n"
        f"exit 0\n"
    )


def _render_test_sh(
    entry_name: str, slug: str, hook_rel_path: str, feasibility: dict
) -> str:
    """Render the TD-7 positive/negative test script.

    POSITIVE_INPUT: crafted to match the check (hook must exit non-zero).
    NEGATIVE_INPUT: crafted to NOT match (hook must exit 0).
    The test script fails if either case produces the wrong verdict.

    Feature 085 FR-7: for ``file_path_regex`` and ``content_regex``
    checks, attempt to construct a POSITIVE_INPUT that actually matches
    the supplied ``check_expression``. Fall back to a generic stub
    with a reviewer-facing comment when the regex is classified as
    complex (lookarounds, inline flags, backreferences) or when
    construction fails to produce a verified match.
    """
    check_kind = feasibility["check_kind"]
    check_expression = feasibility.get("check_expression", "")
    complex_comment_block = ""

    # Build synthetic stdin bodies for each case. Keep them simple and
    # illustrative — operators are expected to tune them before relying on
    # the test in CI. The important invariants are:
    #   POSITIVE_INPUT → hook exit != 0
    #   NEGATIVE_INPUT → hook exit == 0
    if check_kind == "file_path_regex":
        negative = '{"tool_input":{"file_path":"/absolute/path/file.txt"}}'
        sample = None
        if not _is_complex_regex(check_expression):
            sample = _construct_matching_sample(check_expression)
        if sample is not None and re.search(check_expression, sample):
            positive = f'{{"tool_input":{{"file_path":"{sample}"}}}}'
        else:
            positive = f'{{"tool_input":{{"file_path":"{_GENERIC_POSITIVE_FILE_PATH}"}}}}'
            complex_comment_block = _COMPLEX_REGEX_NOTE + "\n"
    elif check_kind == "content_regex":
        negative = f'{{"tool_input":{{"content":"{_GENERIC_NEGATIVE_CONTENT}"}}}}'
        sample = None
        if not _is_complex_regex(check_expression):
            sample = _construct_matching_sample(check_expression)
        if sample is not None and re.search(check_expression, sample):
            positive = f'{{"tool_input":{{"content":"{sample}"}}}}'
        else:
            positive = f'{{"tool_input":{{"content":"{_GENERIC_POSITIVE_CONTENT}"}}}}'
            complex_comment_block = _COMPLEX_REGEX_NOTE + "\n"
    elif check_kind == "json_field":
        positive = '{"tool_input":{"field":"any-value"}}'
        negative = '{"tool_input":{}}'
    else:  # composite
        positive = (
            '{"tool_input":{"file_path":"relative/path","content":"x"}}'
        )
        negative = (
            '{"tool_input":{"file_path":"/ok/path","content":"ok"}}'
        )

    entry_name_comment = entry_name.replace("\r", " ").replace("\n", " ")

    return (
        f"#!/usr/bin/env bash\n"
        f"# Promoted from KB entry: {entry_name_comment}\n"
        f"# TD-7 feasibility check for {slug}: deterministic positive+negative.\n"
        f"# Exits non-zero if either case produces the wrong verdict.\n"
        f"set -u\n"
        f"\n"
        f"SCRIPT_DIR=\"$(cd \"$(dirname \"${{BASH_SOURCE[0]}}\")\" && pwd)\"\n"
        f"HOOK=\"$SCRIPT_DIR/../{Path(hook_rel_path).name}\"\n"
        f"\n"
        f"{complex_comment_block}"
        f"POSITIVE_INPUT='{positive}'\n"
        f"NEGATIVE_INPUT='{negative}'\n"
        f"\n"
        f"fail=0\n"
        f"\n"
        f"# POSITIVE_INPUT must be blocked (hook exits non-zero)\n"
        f"if echo \"$POSITIVE_INPUT\" | bash \"$HOOK\" >/dev/null 2>&1; then\n"
        f"  echo \"FAIL [{slug}]: POSITIVE_INPUT was not blocked\" >&2\n"
        f"  fail=1\n"
        f"fi\n"
        f"\n"
        f"# NEGATIVE_INPUT must be allowed (hook exits 0)\n"
        f"if ! echo \"$NEGATIVE_INPUT\" | bash \"$HOOK\" >/dev/null 2>&1; then\n"
        f"  echo \"FAIL [{slug}]: NEGATIVE_INPUT was incorrectly blocked\" >&2\n"
        f"  fail=1\n"
        f"fi\n"
        f"\n"
        f"if [[ $fail -eq 0 ]]; then\n"
        f"  echo \"OK [{slug}]: positive blocked, negative allowed\"\n"
        f"fi\n"
        f"exit $fail\n"
    )


def _patch_hooks_json(
    existing_text: str,
    event: str,
    tools: list[str],
    hook_command: str,
) -> str:
    """Insert a hook registration for `event`+`tools` into an existing hooks.json.

    The matcher combines tools with `|` (regex alternation) consistent with
    the existing file's conventions. Preserves all existing entries.
    """
    parsed = json.loads(existing_text)
    if "hooks" not in parsed or not isinstance(parsed["hooks"], dict):
        parsed["hooks"] = {}
    buckets = parsed["hooks"]
    if event not in buckets or not isinstance(buckets[event], list):
        buckets[event] = []

    matcher = "|".join(tools)
    new_block = {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": hook_command}],
    }
    buckets[event].append(new_block)
    return json.dumps(parsed, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Public: generate
# ---------------------------------------------------------------------------


def generate(
    entry,  # KBEntry (avoid import cycle at type level)
    target_meta: dict,
    *,
    plugin_root: Optional[Path] = None,
) -> DiffPlan:
    """Produce a 3-FileEdit DiffPlan for a hook target.

    Parameters
    ----------
    entry : KBEntry
        The KB entry being promoted. `entry.name` is used in TD-8 markers.
    target_meta : dict
        Must contain key `"feasibility"` holding the validated feasibility
        dict (event, tools, check_kind, check_expression).
    plugin_root : Path, optional
        Defaults to `plugins/pd` relative to cwd. Tests override this to a
        tmp_path so slug-collision scanning is hermetic.

    Raises
    ------
    ValueError
        If target_meta lacks "feasibility" or feasibility fails validation.
    """
    if "feasibility" not in target_meta:
        raise ValueError("target_meta must contain 'feasibility' key")

    feasibility = target_meta["feasibility"]
    ok, reason = validate_feasibility(feasibility)
    if not ok:
        raise ValueError(f"feasibility validation failed: {reason}")

    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    hooks_dir = plugin_root / "hooks"
    tests_dir = hooks_dir / "tests"
    hooks_json_path = hooks_dir / "hooks.json"

    base_slug = _slugify(entry.name)
    slug = _resolve_collision(hooks_dir, base_slug)

    sh_path = hooks_dir / f"{slug}.sh"
    test_path = tests_dir / f"test-{slug}.sh"

    # Render file bodies
    sh_body = _render_hook_sh(entry.name, slug, feasibility)
    # Use ${CLAUDE_PLUGIN_ROOT} so the command string inside hooks.json is
    # portable across installed/dev locations — consistent with the existing
    # hooks.json entries.
    hook_cmd = f"${{CLAUDE_PLUGIN_ROOT}}/hooks/{slug}.sh"
    # Relative path for the test script to locate its sibling hook
    test_body = _render_test_sh(entry.name, slug, sh_path.name, feasibility)

    # hooks.json: read existing (or empty stub) and patch
    if hooks_json_path.exists():
        existing = hooks_json_path.read_text(encoding="utf-8")
    else:
        existing = json.dumps({"hooks": {}}, indent=2) + "\n"
    patched = _patch_hooks_json(
        existing,
        event=feasibility["event"],
        tools=list(feasibility["tools"]),
        hook_command=hook_cmd,
    )

    edits = [
        FileEdit(
            path=sh_path,
            action="create",
            before=None,
            after=sh_body,
            write_order=0,
        ),
        FileEdit(
            path=test_path,
            action="create",
            before=None,
            after=test_body,
            write_order=1,
        ),
        FileEdit(
            path=hooks_json_path,
            action="modify",
            before=existing,
            after=patched,
            write_order=2,
        ),
    ]

    return DiffPlan(
        edits=edits,
        target_type="hook",
        target_path=sh_path,
    )
