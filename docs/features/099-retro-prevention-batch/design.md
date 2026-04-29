# Design: Retrospective Prevention Batch (099)

## Architecture Overview

This feature ships 8 prevention measures across 6 pd subsystems. Each FR is independently shippable (NFR-8) — design groups changes by FILE so implementation tasks can run in parallel without contention.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Pre-Flight Enforcement Layer                     │
├─────────────────────────────────────────────────────────────────────┤
│ Spec time          Edit time            Session start    Pre-merge │
│ ──────────         ─────────            ─────────────    ───────── │
│ FR-2 spec-rev   FR-5 unicode hook    FR-3 stale brnch    FR-1 gate │
│ FR-7 empirical                       FR-4 doc fresh                │
│                                      FR-6b backlog                 │
│                                                                    │
│ FR-6a /pd:cleanup-backlog (on-demand)                              │
│ FR-8 /pd:test-debt-report (on-demand)                              │
└─────────────────────────────────────────────────────────────────────┘
```

## Prior Art Research

Per spec's Source Findings + Cross-references (see `spec.md` line 580+), all 8 FRs reference established pd patterns. Light verification at design time:

| FR | Prior-art reference (verified) |
|----|-------------------------------|
| FR-1 | `docs/dev_guides/qa-gate-procedure.md` §4 `bucket()` lines 116-145 — verified at spec time + reconfirmed in design-time codebase grep. Extension is additive (default-False kwarg). |
| FR-2 | `plugins/pd/skills/specifying/SKILL.md` Self-Check at line 187 (8 existing items including #00288 closure). Append pattern matches existing items. |
| FR-3 | `plugins/pd/scripts/doctor.sh` 11 existing `check_*` functions (lines 139-419), `pass`/`warn`/`info`/`fail` helpers verified at lines 75-105. `HAS_BLOCKER` counter at line 29. New checks plug into `run_all_checks()` (line 425). |
| FR-4 | Same as FR-3. Source-monitoring paths reuse the convention from `plugins/pd/commands/finish-feature.md` Step 2b (verified at spec time). |
| FR-5 | `plugins/pd/hooks/meta-json-guard.sh` as sibling pattern. `hooks.json` PreToolUse `Write|Edit` matcher at lines 87-95 (verified). |
| FR-6a | New file pattern. No direct prior art for sectioned-archival commands. Closest: `plugins/pd/commands/promote-pattern.md` for confirmation-gate UX. |
| FR-6b | Same as FR-3. |
| FR-7 | Same as FR-2. Self-application of empirical-verification already demonstrated in `spec.md` Empirical Verifications block. |
| FR-8 | New file pattern. Read-only aggregator like `plugins/pd/commands/show-status.md` is closest. |

**Research outcome:** Skip parallel codebase-explorer + internet-researcher dispatches — every claim is grounded in existing pd code already cross-referenced in spec.

**Spot-checked at design time (2026-04-29):**
- `bucket(` defined in `docs/dev_guides/qa-gate-procedure.md` at line 123 (verified via `grep -n "^def bucket"`).
- `read_config_field(` defined in `plugins/pd/scripts/doctor.sh` at line 59 (verified via `grep -n "^read_config_field"`).
- `pass()`, `warn()`, `info()`, `fail()`, `HAS_BLOCKER` helpers verified in doctor.sh lines 75-105.
- `## What You MUST Challenge` section in `plugins/pd/agents/spec-reviewer.md` at line 98 (verified via `grep -n "^## "`).
- `hooks.json` PreToolUse `Write|Edit` matcher precedent at line 88 of `plugins/pd/hooks/hooks.json`.

These spot-checks satisfy the design-time independent verification requirement without requiring full research agent dispatches.

Research-stage time-savings: ~3-5 min agent dispatches avoided.

## Components Map

```
plugins/pd/
├── commands/
│   ├── cleanup-backlog.md         (NEW) FR-6a entry point — orchestration + AskUserQuestion
│   └── test-debt-report.md         (NEW) FR-8 entry point — read-only aggregator
├── scripts/
│   ├── doctor.sh                   (MOD) FR-3, FR-4, FR-6b — 3 new check_* functions + Project Hygiene section
│   ├── cleanup_backlog.py          (NEW) FR-6a parser/writer/counter
│   └── test_debt_report.py         (NEW) FR-8 aggregator
├── skills/specifying/
│   └── SKILL.md                    (MOD) FR-2, FR-7 — 2 new Self-Check items
├── agents/
│   └── spec-reviewer.md            (MOD) FR-2, FR-7 — 2 new "What You MUST Challenge" categories
├── hooks/
│   ├── pre-edit-unicode-guard.sh   (NEW) FR-5 hook
│   └── hooks.json                  (MOD) FR-5 — register new PreToolUse Write|Edit entry
└── (no .venv changes — stdlib only)

docs/dev_guides/
└── qa-gate-procedure.md            (MOD) FR-1 — extend §4 bucket() with test-only-mode

(One config field per pd.local.md — projects opt-in)
.claude/pd.local.md                  (DOC) FR-4 thresholds + tier_doc_root + source paths
```

**Independence groupings (per NFR-8) — revised after design-reviewer iter 1:**

| Group | FR(s) | Files touched | Can ship without others? |
|-------|-------|---------------|---------------------------|
| A. Gate | FR-1 | qa-gate-procedure.md, finish-feature.md | YES (fully independent) |
| B. Specify discipline | FR-2, FR-7 | specifying/SKILL.md, spec-reviewer.md | YES (single file each) |
| C. Doctor (independent checks) | FR-3, FR-4 | doctor.sh | YES (additive `check_*` functions) |
| C′. Doctor backlog check | FR-6b | doctor.sh | NO — couples to Group E (calls cleanup_backlog.py via subprocess). Cannot ship until E. |
| D. Hook | FR-5 | new files + hooks.json | YES (fully independent) |
| E. Commands | FR-6a, FR-8 | new files (commands + scripts) | FR-6a/FR-6b together (E + C′); FR-8 fully independent. |

**Implementation order (revised, accounting for C′↔E coupling):**
1. Group D (hook) — fully independent, simplest
2. Group A (gate) — extends one function in one doc + finish-feature.md edit
3. Group B (specify) — two SKILL.md additions + two reviewer additions
4. Group C (FR-3 + FR-4) — additive doctor checks, no cross-deps
5. Group E (FR-6a + FR-8) — new files; FR-6a creates `cleanup_backlog.py` with `is_item_closed` + `--count-active` CLI surface
6. Group C′ (FR-6b) — wires doctor → cleanup_backlog.py subprocess. MUST come after step 5.

## Technical Decisions

### TD-1: doctor invokes `cleanup_backlog.py --count-active` via subprocess CLI (not import)

**Decision:** `is_item_closed(line: str) -> bool` is defined ONCE in `plugins/pd/scripts/cleanup_backlog.py`. The doctor's `check_active_backlog_size` invokes it indirectly via subprocess: `python3 ${SCRIPT_DIR}/cleanup_backlog.py --count-active --backlog-path <path>` where `${SCRIPT_DIR}` is `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. NOT via `python3 -c "from cleanup_backlog import ..."` — that would require PYTHONPATH manipulation that breaks under the cache-installed plugin path.

**Why:**
- AC-X1 already exercises the `--count-active` CLI surface; doctor reusing the same path means one canonical code-flow tested by ONE assertion.
- Avoids PYTHONPATH gymnastics under the two-location plugin glob (cache vs dev workspace).
- `cleanup_backlog.py` is a stdlib-only Python script — invocable by any `python3` regardless of venv state (NFR-3 stdlib-only doctor).
- Subprocess fork+exec adds ~80ms (same as inline import would). No performance regression.

**Trade-off:** One subprocess per doctor run (cheap, bounded). Versus an in-process import which would still need same subprocess startup since doctor is bash. No real downside.

**Bash invocation snippet (canonical for I-2 doctor `check_active_backlog_size`):**
```bash
local script_dir
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # resolves to plugins/pd/scripts under both cache + dev paths
local backlog_path="${PROJECT_ROOT}/docs/backlog.md"
local count
count=$(python3 "${script_dir}/cleanup_backlog.py" --count-active --backlog-path "${backlog_path}" 2>/dev/null || echo 0)
```

### TD-2: hook split into bash wrapper + python module file (revised after design review)

**Decision (revised):** `pre-edit-unicode-guard.sh` is a thin bash wrapper that pipes stdin to `pre-edit-unicode-guard.py` (separate module). Python file holds all logic with a clean `main()` entrypoint and unit-testable `scan_field(text: str) -> list[int]` helper.

**Why (revised):**
- Inline Python heredoc was not testable cleanly via `python3 -m py_compile` (heredoc isn't a real importable module).
- Splitting into `.py` allows AC-15(b) compile-check + future unit tests at `plugins/pd/hooks/tests/test_pre_edit_unicode_guard.py`.
- Same number of process startups in both designs — bash spawns python3 once either way.
- Stderr discipline (Blocker 2 from design-reviewer iter 1): the bash wrapper redirects python3's UNHANDLED stderr to /dev/null while preserving the script's intentional `print(file=sys.stderr)` warnings via a tempfile pattern (see I-3 below).

**Trade-off:** Two files instead of one. Net win on testability + AC-15 compliance.

### TD-3: Doctor's "Project Hygiene" section as new run_all_checks group

**Decision:** Add a new section heading `Project Hygiene` to `run_all_checks()` between `Memory System` and `Project Context`. Three checks group there: `check_stale_feature_branches`, `check_tier_doc_freshness`, `check_active_backlog_size`.

**Why:** Existing sections (System, Plugin, Embedding, Memory, Project Context) are about INSTALLATION health. New checks are about PROJECT-STATE health — distinct conceptual category. Future hygiene checks (e.g., #00040 entity status drift) can join.

**Trade-off:** One more printed section. Negligible UX impact.

### TD-4: FR-1 module-level constants in qa-gate-procedure.md

**Decision:** `TEST_FILE_RE` and `_LOC_LINE_SUFFIX_RE` defined as module-level `re.compile()` constants. `_location_matches_test_path()` is a module-level function (not nested in bucket()).

**Why:** `bucket()` runs N times per gate exercise (once per finding). Per-call regex compilation is wasteful; pre-compile once.

**Reference:** spec FR-1 implementation notes (line 139-142) already mandate this — design just reaffirms.

### TD-5: FR-4 source-path config reads use existing `read_config_field()`

**Decision:** Doctor reads `tier_doc_root`, `tier_doc_source_paths_user_guide`, etc. via the existing `read_config_field()` helper (doctor.sh line 59).

**Why:** Consistent with all other doctor config reads. No new config-parsing code paths to maintain.

**Trade-off:** None — `read_config_field()` returns string; multi-path values are handled by the caller via space-split.

### TD-6: FR-8 inlined `normalize_location()` (NOT imported from elsewhere)

**Decision:** `test_debt_report.py` defines its OWN copy of `normalize_location()` matching the qa-gate-procedure.md §4 contract exactly. No cross-module import.

**Why:** qa-gate-procedure.md §4 is documentation, not a Python module — there's no importable Python implementation today (the pseudocode lives in markdown). Inlining keeps test-debt-report self-contained.

**Trade-off:** If §4's helper ever changes, FR-8 must be updated explicitly. Spec acknowledges this (line 470-471). Acceptable as an explicit pinning, not silent drift.

### TD-7: Hook short-circuit retained as testable code path

**Decision:** `pre-edit-unicode-guard.sh` MUST include both short-circuits (hook_event_name check + tool_name check) even though hooks.json routing makes them unreachable in production.

**Why:** AC-6c, AC-6d test these defensively via stdin pipe. Removing the short-circuits would break those ACs. Pattern matches `meta-json-guard.sh`.

**Reference:** spec FR-5 implementation note (line 258-259). Design reaffirms.

## Interfaces

Most interfaces are pinned in spec.md. This section consolidates them and adds the small gaps (Self-Check item text, reviewer challenge category text).

### I-1: bucket() (qa-gate-procedure.md §4) — extended

```python
import re

# Module-level constants (compile once)
TEST_FILE_RE = re.compile(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$')
_LOC_LINE_SUFFIX_RE = re.compile(r':\d+$')

def _location_matches_test_path(location: str) -> bool:
    """Strip optional ':<digits>' suffix, then check against TEST_FILE_RE."""
    return bool(TEST_FILE_RE.search(_LOC_LINE_SUFFIX_RE.sub('', location)))

def bucket(finding, all_findings, *, is_test_only_refactor: bool = False) -> str:
    # See spec FR-1 for full body.
    ...
```

### I-2: doctor.sh check functions — signatures

```bash
# Helper: resolve base branch (FR-3 needs this for merge-base check).
# Reads pd.local.md `base_branch` field; if 'auto', resolves via git symbolic-ref;
# fallback to 'main' if all else fails.
_pd_resolve_base_branch() {
    local config_file="${1:-${PROJECT_ROOT}/.claude/pd.local.md}"
    local base
    base=$(read_config_field "${config_file}" "base_branch" "auto")
    if [[ "${base}" == "auto" ]]; then
        base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
        [[ -z "${base}" ]] && base="main"
    fi
    printf '%s' "${base}"
}

check_stale_feature_branches() {
    # Per spec FR-3 + design TD: iterate refs/heads/feature/*, severity-split.
    # Base resolution: _pd_resolve_base_branch (NOT hardcoded 'main').
    # Tier 1 (completed/cancelled/abandoned/archived) → warn() with `git branch -D` hint
    # Tier 2 (no entity / unknown) → info() with non-destructive guidance
    # Active/planned/paused/in_progress OR merged → silent
    # Returns exit code 0 always (warnings/info don't block).
}

check_tier_doc_freshness() {
    # Per spec FR-4: read tier_doc_root + per-tier source paths from pd.local.md;
    # awk-extract last-updated frontmatter; python3 datetime diff;
    # warn if gap_days > tier_doc_staleness_days threshold (default 30).
}

check_active_backlog_size() {
    # Per spec FR-6b + TD-1 (revised): invoke cleanup_backlog.py via subprocess CLI
    # (NOT Python import). Single canonical surface tested by AC-X1.
    local script_dir config_file backlog_path threshold count
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    config_file="${PROJECT_ROOT}/.claude/pd.local.md"  # explicit local — does not assume run_all_checks prelude
    backlog_path="${PROJECT_ROOT}/docs/backlog.md"
    threshold=$(read_config_field "${config_file}" "backlog_active_threshold" "30")
    count=$(python3 "${script_dir}/cleanup_backlog.py" --count-active --backlog-path "${backlog_path}" 2>/dev/null || echo 0)
    if (( count > threshold )); then
        warn "Active backlog: ${count} items (threshold ${threshold}). Run /pd:cleanup-backlog to archive closed sections."
    else
        pass "Active backlog: ${count} items"
    fi
}
```

Wired in `run_all_checks()` after `check_memory_store` and before `check_project_context`:
```bash
printf "\n${BOLD}Project Hygiene${NC}\n"
check_stale_feature_branches || true
check_tier_doc_freshness || true
check_active_backlog_size || true
```

### I-3: pre-edit-unicode-guard — bash wrapper + python module (revised TD-2)

**Files:**
- `plugins/pd/hooks/pre-edit-unicode-guard.sh` — bash wrapper
- `plugins/pd/hooks/pre-edit-unicode-guard.py` — python logic (importable for unit tests)

**Input (stdin):** JSON object per CC PreToolUse hook protocol (see spec FR-5 §Input contract).

**Output (stdout):** Always `{"continue": true}` followed by newline.

**Output (stderr):** Empty if no codepoints > 127 in any of `tool_input.{old_string, new_string, content}`. Otherwise one warning line per non-empty field with codepoints, format per spec FR-5 step 5. **CRITICAL:** Python's own startup/import errors MUST NOT leak to stderr (would violate AC-E4); only intentional warnings reach stderr.

**Exit code:** Always 0.

**bash wrapper skeleton:**
```bash
#!/usr/bin/env bash
# pre-edit-unicode-guard.sh — non-blocking warning hook for Edit|Write Unicode codepoints
# ALWAYS emits {"continue": true} to stdout regardless of any failure path.
set +e  # Never let any failure block the hook

emit_continue() { printf '%s\n' '{"continue": true}'; }
trap emit_continue EXIT  # Belt + suspenders

if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
guard_py="${script_dir}/pre-edit-unicode-guard.py"

if [[ ! -f "${guard_py}" ]]; then
    exit 0
fi

# Stderr discipline: python3 internal errors (Import/Syntax) → /dev/null.
# Intentional warnings written to a tempfile by the python script, then bash cats them to stderr.
warn_file="$(mktemp -t pd-unicode-guard.XXXXXX)" || { exit 0; }
trap 'rm -f "${warn_file}"; emit_continue' EXIT

python3 "${guard_py}" --warn-file "${warn_file}" 2>/dev/null

if [[ -s "${warn_file}" ]]; then
    cat "${warn_file}" >&2
fi

exit 0
```

**python module skeleton (`pre-edit-unicode-guard.py`):**
```python
#!/usr/bin/env python3
"""PreToolUse Unicode codepoint guard — non-blocking warning."""
import argparse
import json
import sys

MAX_FIELDS_REPORTED = 5  # cap per FR-5 step 4

def scan_field(text: str) -> list[int]:
    """Return UNIQUE codepoints > 127 in first-occurrence order, capped at MAX_FIELDS_REPORTED."""
    seen: list[int] = []
    for c in text or "":
        cp = ord(c)
        if cp > 127 and cp not in seen:
            seen.append(cp)
            if len(seen) >= MAX_FIELDS_REPORTED:
                break
    return seen

def format_warning(field_name: str, codepoints: list[int]) -> str:
    """Per spec FR-5 step 5."""
    pairs = ", ".join(f"(0x{cp:04x}, {chr(cp)!r})" for cp in codepoints)
    first_cp = codepoints[0]
    return (
        f'[pd] Unicode codepoint(s) detected in {field_name}: [{pairs}]. '
        f'Edit/Write may strip these silently. Use Python read-modify-write '
        f'with chr(0x{first_cp:04x}) runtime generation. '
        f'See plugins/pd/skills/systematic-debugging/SKILL.md → "Tooling Friction Escape Hatches".'
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--warn-file', required=True, help='Tempfile for stderr warnings (controlled by bash wrapper)')
    args = parser.parse_args()

    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # AC-E4: silent on malformed JSON

    # Short-circuit (TD-7 testability) — covered by AC-6c, AC-6d
    if data.get("hook_event_name") != "PreToolUse":
        return 0
    if data.get("tool_name") not in ("Edit", "Write"):
        return 0

    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        return 0

    warnings = []
    for field in ("old_string", "new_string", "content"):
        value = ti.get(field) or ""
        if not isinstance(value, str):
            continue
        cps = scan_field(value)
        if cps:
            warnings.append(format_warning(field, cps))

    if warnings:
        with open(args.warn_file, 'w', encoding='utf-8') as wf:
            for w in warnings:
                wf.write(w + '\n')
    return 0

if __name__ == '__main__':
    sys.exit(main())
```

**Why the tempfile pattern (resolves Blocker 2 from design-reviewer iter 1):** if Python crashes during startup (missing import, syntax error), its tracebacks go to /dev/null via the `2>/dev/null` redirect. Intentional warnings are written to the controlled tempfile. Bash then `cat`s the tempfile to stderr only if non-empty. AC-E4 (silent stderr on malformed JSON) holds because the python script returns 0 without writing to the tempfile. The wrapper's `EXIT` trap removes the tempfile.

**Empty/closed stdin handling:** `json.load(sys.stdin)` blocks until EOF; if stdin is empty (immediate EOF), `json.JSONDecodeError` is raised and caught by the bare `except`, returning 0. Test harnesses must close stdin (which `printf ... |` does naturally).

### I-4: cleanup_backlog.py — public API

```python
"""Module-level shared API."""

def is_item_closed(line: str) -> bool:
    """Canonical predicate. Used by both FR-6a archival and FR-6b doctor count."""
    if line.startswith('- ~~'):
        return True
    return any(marker in line for marker in (
        '(closed:', '(promoted →', '(fixed in feature:', '**CLOSED'
    ))

def count_active(backlog_path: str) -> int:
    """Per FR-6b: count active backlog items."""

def parse_sections(content: str) -> list[dict]:
    """Per FR-6a: parse `## From ` sections from backlog.md content."""

# CLI entry point (argparse):
#   --dry-run       Default mode. Print archivable-section table.
#   --apply         Perform archival (write to backlog-archive.md, remove from backlog).
#   --count-active  Print count to stdout (single integer for AC-X1).
#   --backlog-path PATH    Override default backlog path.
#   --archive-path PATH    Override default archive path.
```

**Archive byte-level write contract (resolves spec AC-9(b)/(c) discrepancy):**

The design pins the canonical interpretation: 4-line standalone header + ONE blank between header and first section. Total header overhead on first creation = 4 lines (NOT 5). The "PLUS one trailing blank" mentioned in spec AC-9(b) is the trailing blank of the FIRST section, NOT a leading blank.

**Concrete first-creation byte sequence after one section archived:**
```
# Backlog Archive          ← line 1 (H1)
                            ← line 2 (blank)
Closed sections moved from backlog.md by /pd:cleanup-backlog.   ← line 3 (body)
                            ← line 4 (blank — header terminator)
## From Feature 086 QA      ← line 5 (first section header, no leading blank)
                            ← line 6 (blank after section header)
- **#00085** ...            ← line 7+ (item lines)
                            ← (last line of section is trailing blank)
```

So `archive_total_lines = 4 (header) + sum(section_total_lines)` where `section_total_lines` includes the section's trailing blank. AC-9(c) formula reduces to: `4 + sum(section_lines_per_archived)` — drop the `+ N_archived_sections` redundancy that double-counted the trailing blanks.

**Tracked task for implement phase:** Add a tasks.md entry under Group E for FR-6a: "Reconcile AC-9(c) line-count formula by adding clarifying note in spec.md that section_lines includes trailing blank, OR amend AC-9(c) to drop the +N_archived_sections term." This carry-forward prevents the spec/design discrepancy from being lost between phases.

### I-5: test_debt_report.py — public API

```python
"""Read-only aggregator."""

import re

_NORMALIZE_LOC_RE = re.compile(r'([^/\s]+\.[a-zA-Z0-9]+:\d+)')

def normalize_location(loc: str) -> str:
    """Inlined per spec FR-8 + TD-6. Pinned copy of qa-gate-procedure.md §4 helper."""
    m = _NORMALIZE_LOC_RE.search(loc)
    if m:
        return m.group(1)
    return loc.strip().lower()

def derive_category(finding: dict) -> str:
    """Per spec FR-8 Category derivation rule."""
    if 'category' in finding:
        return finding['category']
    reviewer = finding.get('reviewer', '')
    return {
        'pd:test-deepener': 'testability',
        'pd:security-reviewer': 'security',
        'pd:code-quality-reviewer': 'quality',
        'pd:implementation-reviewer': 'implementation',
    }.get(reviewer, 'uncategorized')

def aggregate(features_dir: str, backlog_path: str) -> list[dict]:
    """Returns rows: [{location, category, count, sources}]"""

def render_table(rows: list[dict]) -> str:
    """Markdown table per spec FR-8 output."""

# CLI entry point (no flags needed — pure read-aggregator).
```

### I-6: specifying/SKILL.md Self-Check additions (FR-2 + FR-7)

Two new bullet items appended to existing Self-Check list (after the #00288 closure item):

```markdown
- [ ] If any FR text grep-matches `Test[A-Z][\w]+|test_[\w]+` (references existing test classes/functions), the spec includes explicit answer to: "Is this scope recursive test-hardening? Behavioral coverage at production call sites is the architectural alternative — see qa-override.md template (`docs/features/097-iso8601-test-pin-v2/qa-override.md`)." Surface either (a) acknowledgement of architectural rationale, OR (b) explicit framing as test-only refactor.
- [ ] If any FR or AC references stdlib runtime behavior — including but not limited to: regex flags via `.flags` / `re.compile()` / `re.ASCII` / `re.UNICODE`; `re`, `sys`, `pkgutil`, `inspect`, `unicodedata`, `datetime`, `json`, `pathlib`, `subprocess` module APIs; encoding semantics like `str.isspace`, `str.isdigit`, `str.isascii`, `unicodedata.category`, `unicodedata.normalize` — include a Python REPL verification line inline using format `>>> <expr> → <result>`. Empirical evidence at spec time prevents iteration-deferred blockers.
```

### I-7: spec-reviewer.md additions (FR-2 + FR-7)

**Insertion anchor:** Append both sub-sections to the END of the existing `## What You MUST Challenge` section in `plugins/pd/agents/spec-reviewer.md` (which ends at line ~177 in current file, before `## Review Process` at line 178). Insertion is between the existing `### Feasibility Verification` sub-section and the next H2 heading. Two new sub-sections added under existing `## What You MUST Challenge`:

```markdown
### Recursive Test-Hardening (FR-2 prevention)

- [ ] Detect: regex search FR text for `Test[A-Z][\w]+|test_[\w]+` references.
- [ ] If detected AND no architectural-rationale acknowledgement present → emit `severity: warning` with category `recursive-test-hardening` and suggestion: "Acknowledge whether scope is intentional test-hardening (with rationale per qa-override.md template) OR reframe as behavioral coverage at production call sites."

### Empirical Verification (FR-7 prevention)

- [ ] Detect (judgment-based, not auto-emit): scan FRs for trigger keywords `re\.|pkgutil\.|inspect\.|unicodedata\.|sys\.|datetime\.|json\.|pathlib\.|subprocess\.|str\.is\w+`.
- [ ] If trigger keyword appears AND its behavior is load-bearing for an AC (i.e., AC pass/fail depends on the runtime semantics) AND spec contains no `>>>` lines or `Empirical:` markers → emit `severity: warning` with category `empirical-verification` and suggestion: "Add a Python REPL verification line near the FR demonstrating the runtime contract."
- [ ] Mode is judgment-based: prose mentions ("see re.compile docs") without load-bearing AC do NOT trigger.
```

## Cross-File Invariants

| Invariant | Enforced where | Verified by |
|-----------|---------------|-------------|
| `is_item_closed()` defined in cleanup_backlog.py is the SOLE predicate for "closed item" | TD-1 | AC-X1 (cross-FR agreement test) |
| `_location_matches_test_path()` strips `:line` before TEST_FILE_RE | TD-4 | AC-2 helper assertions |
| Hook short-circuits retained as testable defensive code | TD-7 | AC-6c, AC-6d |
| Doctor checks add to "Project Hygiene" section, not other sections | TD-3 | AC-4, AC-5, AC-10 grep `Project Hygiene` |
| `normalize_location()` inlined in test_debt_report.py matches qa-gate-procedure.md §4 contract | TD-6 | AC-15(b) compile-check + spec empirical block |
| All hook + script files use `${CLAUDE_PLUGIN_ROOT}` or relative paths (no hardcoded absolutes) | NFR-1 | AC-16 validate.sh portability check |
| All Python files target stdlib only (no PyYAML for doctor) | NFR-3 + spec FR-4 fix | Lint check (AC-15) + manual review |

## Risk Matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Hook performance exceeds 200ms budget on large file_path edits | Medium | Low | Cap codepoint scan at 5 unique per field (FR-5 step 4); python3 startup ~80ms is fixed cost; total scan O(N) on input string. |
| AC-X1 subprocess invocation fails due to python3 PATH issues or missing cleanup_backlog.py | Medium | Low | TD-1 uses `${BASH_SOURCE[0]}`-relative resolution → `${script_dir}/cleanup_backlog.py`. Falls back to `echo 0` on subprocess error (`2>/dev/null \|\| echo 0`), so doctor never crashes. Verified portable across cache + dev workspace plugin paths via the design-time spot-check. |
| FR-3 destructive `git branch -D` hint causes user to lose uncommitted work | High | Low | Severity-split (TD/spec FR-3): only Tier 1 known-terminal states get the `-D` hint; Tier 2 unknown gets non-destructive guidance. Merged branches always silent. |
| Doctor performance regression — 3 new checks add up to 5s+ on large project | Medium | Medium | Per NFR-3 budget 3s combined. Each check has bounded inputs (≤20 branches, ≤30 docs, ≤200 backlog lines). Measure during implement. |
| FR-1 regex misclassifies novel test-file naming conventions | Low | Low | Anchored to `.py` only (intentional per spec). Non-Python tests get standard AC-5b path (HIGH→MED), not the new HIGH→LOW. Fail-safe. |
| Hook fires on Edit/Write to non-source files (e.g., binary blobs) | Low | Low | Hook always exits 0 with `{"continue": true}` regardless of scan outcome. No blocking. |
| FR-6a archives a section the user didn't intend (e.g., partially-closed) | High | Low | "100% items closed" predicate is strict. Empty-section case excluded (item count > 0 required). Dry-run is default — must explicitly `--apply`. |
| FR-7 false positives generate spec-review noise on prose mentions | Low | Medium | Mode is judgment-based, not auto-emit (per spec FR-7 + I-7 reaffirm). Reviewer applies load-bearing-for-AC test. |
| Cross-version drift between FR-8 normalize_location and qa-gate-procedure.md §4 | Medium | Low | TD-6 + spec line 470-471 explicitly accept the pinning. Drift is doctor-detectable in retrospect (debug via test fixture parity check during implement). |
| Concurrent doctor invocations (multiple sessions running `bash doctor.sh` simultaneously) | Low | Low | All checks are read-only (no write to .meta.json or DB). Worst case: duplicated stdout output in two terminals. No file corruption possible. |
| FR-6a `--apply` runs while user has another git op in flight | Medium | Low | Single-process invocation; user-driven (must explicitly run `--apply`). No cron or background dispatch in scope. Git's own atomicity covers the commit step. If `git commit` fails, script exits non-zero leaving backlog.md in modified state for user inspection. |
| FR-3 race condition: branches created/deleted during the `for-each-ref` loop | Low | Low | `git for-each-ref` snapshots refs at invocation time. Race is theoretical (sub-millisecond window). Subsequent merge-base check on a deleted branch fails non-fatally; doctor logs `info` and continues. |
| FR-5 hook scan time on multi-MB Write content (e.g., base64 binary) | Low | Low | First-occurrence dedup caps work at 5 unique codepoints per field — full scan stops early once cap hit. Cold scan of 1MB string is ~10-30ms in CPython. NFR-4 budget 200ms. If a future ≥10MB Write occurs, performance degrades linearly but doesn't crash. Document in I-3 as "scan terminates after 5 unique codepoints found per field". |

## Out of Scope (reaffirmed)

- KB ↔ semantic-memory DB divergence (#00018, #00053)
- Promote-pattern enhancements (#00064-66)
- Phase-iteration analytics dashboard
- Auto-deletion of orphan branches
- Migrating existing meta-json-guard.sh PreToolUse matcher
- `--check <name>` CLI flag for doctor.sh

## Dependencies

- `entity-registry` MCP — read-only (FR-3 active-feature lookup; filesystem `.meta.json` fallback acceptable per spec FR-3).
- `qa-gate-procedure.md` §4 `bucket()` — extension target (FR-1).
- `pd.local.md` config — new fields (FR-4 thresholds, FR-6b threshold) optional with documented defaults.
- Python 3.10+ stdlib (`re`, `json`, `datetime`, `pathlib`, `argparse`, `pkgutil`).
- POSIX shell utilities (`awk`, `grep`, `git`).

## Open Questions

- None. All decisions resolved at design time via spec contracts + light codebase verification.
