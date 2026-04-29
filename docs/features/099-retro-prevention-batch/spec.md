# Specification: Retrospective Prevention Batch (099)

## Problem Statement

Eight recurring patterns observed across feature cycles 091-098 (recursive test-hardening, branch lifecycle leakage, tier-doc drift, Edit-tool Unicode trap, backlog asymmetry, phase iteration cost, test-debt invisibility) cost release cycles and reviewer iterations despite being documented in retros and KB. Convert documented heuristics into pre-flight enforcement: gate predicates, doctor health checks, PreToolUse hook, Self-Check items, and observability commands.

## Success Criteria

- [ ] QA gate `bucket()` predicate, when invoked on a test-only-refactor diff fixture with test-deepener HIGH gap (mutation_caught=false, no cross-confirm), returns `LOW` (not `MED`) — measurable via fixture invocation.
- [ ] `bash plugins/pd/scripts/doctor.sh` output includes lines for `stale_feature_branches`, `tier_doc_freshness`, and `active_backlog_size` checks under a new "Project Hygiene" section — measurable via grep on doctor stdout.
- [ ] PreToolUse hook fires on Edit/Write tool input containing codepoints > 127 and emits exact warning string (regex-matched) to stderr without blocking the tool call — measurable via stdin-piped test invocation.
- [ ] `/pd:cleanup-backlog --dry-run` on the project's current `docs/backlog.md` identifies ≥3 fully-closed per-feature sections from the 082-097 range — measurable via stdout grep.
- [ ] `/pd:test-debt-report` produces a non-empty 4-column markdown table from the project's existing `*.qa-gate.json` files and active testability backlog entries — measurable via stdout column count and row count.
- [ ] `specifying/SKILL.md` Self-Check section gains 2 new items (recursive-hardening, empirical-verification); `spec-reviewer.md` enforces both — measurable via grep.

## Empirical Verifications (for FRs that reference stdlib runtime)

> Demonstrating FR-7's pattern on this very spec. Each FR that touches stdlib runtime must include a verified one-liner before spec submission. Pin: Python 3.10+.

```text
>>> re.compile(r'foo').flags & re.UNICODE == re.UNICODE   → True   (default flags include UNICODE; robust against version-specific bit padding)
>>> re.ASCII == 256                                        → True   (re.ASCII flag bitmask)
>>> bool(re.search(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$', 'test_database.py'))           → True
>>> bool(re.search(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$', 'database.py'))                → False
>>> bool(re.search(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$', 'plugins/pd/hooks/tests/test-hooks.sh'))  → False  (anchored to .py — shell tests excluded)
>>> bool(re.search(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$', 'conftest.py'))                → False  (root conftest excluded; in-tests/ would match)
>>> bool(re.search(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$', 'tests/conftest.py'))          → True
>>> callable(pkgutil.iter_modules)                        → True
>>> unicodedata.category(chr(0x85))                       → 'Cc'   (control character, not in Z* category)
>>> chr(0x85).isspace()                                   → True   (NEL is whitespace per str.isspace())
>>> chr(0xa0).isspace()                                   → True   (NBSP)
>>> any(ord(c) > 127 for c in chr(0x85))                  → True   (codepoint=133, > 127)
>>> any(ord(c) > 127 for c in 'hello')                    → False
>>> datetime.fromisoformat('2026-04-29T00:00:00Z'.replace('Z', '+00:00')).tzinfo is not None  → True   (FR-4 last-updated parsing)
>>> json.loads('{"continue": true}')                       → {'continue': True}   (FR-5 hook output shape)
>>> '[(0x{:04x}, {!r})]'.format(0x85, chr(0x85))           → "[(0x0085, '\\x85')]"   (FR-5 stderr fragment shape; pins AC-6 regex)
```

These confirm: (a) FR-1 test-file regex correctly excludes non-Python and root conftest, (b) FR-5 codepoint-threshold predicate is correct, (c) FR-4 frontmatter timestamp parsing handles Z-suffix, (d) FR-7 verification format is testable.

## Scope

### In Scope

- **FR-1** QA-gate test-only-mode predicate (`docs/dev_guides/qa-gate-procedure.md` §4 + `plugins/pd/commands/finish-feature.md` Step 5b)
- **FR-2** Spec-reviewer recursive-hardening Self-Check (`plugins/pd/skills/specifying/SKILL.md` + `plugins/pd/agents/spec-reviewer.md`)
- **FR-3** Doctor `check_stale_feature_branches` (`plugins/pd/scripts/doctor.sh`)
- **FR-4** Doctor `check_tier_doc_freshness` (`plugins/pd/scripts/doctor.sh`)
- **FR-5** PreToolUse hook `pre-edit-unicode-guard.sh` (`plugins/pd/hooks/` + `plugins/pd/hooks/hooks.json`)
- **FR-6a** `/pd:cleanup-backlog` command (`plugins/pd/commands/cleanup-backlog.md` + `plugins/pd/scripts/cleanup_backlog.py`)
- **FR-6b** Doctor `check_active_backlog_size` (`plugins/pd/scripts/doctor.sh`)
- **FR-7** Specifying empirical-verification Self-Check (`plugins/pd/skills/specifying/SKILL.md` + `plugins/pd/agents/spec-reviewer.md`)
- **FR-8** `/pd:test-debt-report` command (`plugins/pd/commands/test-debt-report.md` + `plugins/pd/scripts/test_debt_report.py`)

### Out of Scope

- KB ↔ semantic-memory DB divergence (#00018, #00053) — needs project-scope decision.
- Promote-pattern enhancements (#00064-#00066) — orthogonal.
- Phase-iteration analytics dashboard — needs entity DB schema work.
- Migrating existing meta-json-guard.sh PreToolUse matcher — out of scope; leave as-is.
- Adding `--check <name>` CLI flag to doctor.sh — out of scope; AC verification uses full doctor invocation + grep.
- Auto-deletion of orphaned branches by doctor — read-only check only; cleanup remains manual.

## Functional Requirements

### FR-1: QA gate test-only-mode HIGH→LOW downgrade

**Test-file regex (canonical, used in BOTH trigger condition AND location check):**
```
TEST_FILE_RE = r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$'
```
Anchored to `.py` only. Non-Python test files (`.sh`, `.bash`, `.js`) are intentionally NOT classified as "test-only refactor" because their gate handling differs (no test-deepener mutation analysis runs on them). Repo-root `conftest.py` is intentionally excluded because such files are uncommon and rare-case escape from this rule errs on the safe side (HIGH→MED via AC-5b still fires).

**Trigger condition:**
- `IS_TEST_ONLY_REFACTOR = 1` iff `git diff <pd_base_branch>...HEAD --name-only` returns ≥1 path AND `re.search(TEST_FILE_RE, path)` is truthy for **every** returned path.
- Empty diff (zero paths) → `IS_TEST_ONLY_REFACTOR = 0` (vacuous truth not allowed; see AC-E1).
- `re.search` (not `re.match`/`re.fullmatch`) — verified empirically above.

**Location-matching helper (handles `:line` suffix in finding locations):**

Findings emit `location` in the format `file:line` (per `qa-gate-procedure.md` §1 reviewer instruction "emit location as file:line"). The diff-path-trigger uses raw paths like `test_database.py`, but the bucket-time location check sees `test_database.py:2354`. We need a helper that strips the optional line-number suffix before matching:

```python
_LOC_LINE_SUFFIX_RE = re.compile(r':\d+$')

def _location_matches_test_path(location: str) -> bool:
    """Strip optional ':<digits>' suffix, then check against TEST_FILE_RE."""
    path = _LOC_LINE_SUFFIX_RE.sub('', location)
    return bool(re.search(TEST_FILE_RE, path))
```

**Empirical:**
```text
>>> re.sub(r':\d+$', '', 'test_database.py:2354')                      → 'test_database.py'
>>> re.sub(r':\d+$', '', 'plugins/pd/tests/test_foo.py:42')            → 'plugins/pd/tests/test_foo.py'
>>> re.sub(r':\d+$', '', 'database.py:1055')                           → 'database.py'
>>> re.sub(r':\d+$', '', 'test_database.py')                           → 'test_database.py'  # no-suffix case unchanged
>>> bool(re.search(TEST_FILE_RE, 'test_database.py'))                  → True
>>> bool(re.search(TEST_FILE_RE, 'database.py'))                       → False
```

**Bucketing function signature change (qa-gate-procedure.md §4):**
The existing `bucket(finding, all_findings)` is extended with one new keyword-only parameter, default-False to preserve all existing call-sites:
```python
import re

# Module-level constants (compile once)
TEST_FILE_RE = re.compile(r'(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$')
_LOC_LINE_SUFFIX_RE = re.compile(r':\d+$')

def _location_matches_test_path(location: str) -> bool:
    return bool(TEST_FILE_RE.search(_LOC_LINE_SUFFIX_RE.sub('', location)))

def bucket(finding, all_findings, *, is_test_only_refactor: bool = False):
    sev = finding.get("severity")
    sec_sev = finding.get("securitySeverity")
    high = sev == "blocker" or sec_sev in {"critical", "high"}
    med = sev == "warning" or sec_sev == "medium"
    low = sev == "suggestion" or sec_sev == "low"
    # AC-5b narrowed remap for test-deepener (existing, unchanged)
    if finding.get("reviewer") == "pd:test-deepener" and high:
        mutation_caught = finding.get("mutation_caught", True)
        cross_confirmed = any(
            other["location"] == finding["location"]
            and other.get("reviewer") != "pd:test-deepener"
            for other in all_findings
        )
        if not mutation_caught and not cross_confirmed:
            # FR-1 NEW: test-only refactor with location in test file → LOW (sidecar-fold)
            if is_test_only_refactor and _location_matches_test_path(finding.get("location", "")):
                return "LOW"
            return "MED"  # existing AC-5b coverage-debt path (non-test-only or non-test-location)
    if high: return "HIGH"
    if med:  return "MED"
    if low:  return "LOW"
    return "MED"
```

**Implementation notes:**
- The implementation MUST add `import re` at the top of the qa-gate procedure module if not already present.
- `TEST_FILE_RE` and `_LOC_LINE_SUFFIX_RE` MUST be compiled once as module-level constants, NOT re-compiled per `bucket()` invocation (performance — `bucket()` runs N times per gate exercise).
- The `_location_matches_test_path()` helper MUST be unit-tested independently of `bucket()` for AC-2 to be reliably testable in isolation.

**Wiring:** `finish-feature.md` Step 5b computes `IS_TEST_ONLY_REFACTOR` once before the bucketing loop and passes it as `is_test_only_refactor=...` to each `bucket()` call. The default-False parameter ensures any out-of-band caller of `bucket()` (e.g., test fixtures) gets the existing pre-FR-1 behavior. Documentation updated in qa-gate-procedure.md §4 with the extended pseudo-code above.

### FR-2: Spec-reviewer recursive-hardening Self-Check

**Self-Check item (added to `specifying/SKILL.md`):**
> "If any FR text grep-matches `Test[A-Z][\w]+|test_[\w]+` (i.e., references existing test classes or test functions), include explicit answer to: 'Is this scope recursive test-hardening? Behavioral coverage at production call sites is the architectural alternative — see qa-override.md template (`docs/features/097-iso8601-test-pin-v2/qa-override.md`).' Surface either: (a) acknowledgement of architectural rationale for hardening over behavioral coverage, OR (b) explicit framing as test-only refactor."

**Spec-reviewer enforcement (added to `agents/spec-reviewer.md`):**
- New challenge category in "What You MUST Challenge": `Recursive Test-Hardening`
- Detection: regex search FR text for test-class/function references
- If detected AND no acknowledgement of architectural rationale present → emit `severity: warning` (not blocker) with category `recursive-test-hardening`

**Empirical:** `>>> import re; bool(re.search(r'Test[A-Z][\w]+|test_[\w]+', 'TestIso8601PatternSourcePins.test_pattern_source'))` → True.

### FR-3: Doctor `check_stale_feature_branches`

**Function signature:** Add `check_stale_feature_branches()` to `plugins/pd/scripts/doctor.sh`, called from `run_all_checks()` under a new `Project Hygiene` section.

**Orphan-qualifying entity status set (canonical, severity-split):**

Two-tier severity to avoid destructive guidance on uncommitted experimental branches:

- **Tier 1 (warn — likely cleanable):** `{completed, cancelled, abandoned, archived}` — these are explicit terminal states. Doctor emits `warn()` with cleanup hint `git branch -D <branch>`.
- **Tier 2 (info — needs investigation):** `{"no entity", "unknown"}` — `.meta.json` missing OR status not in canonical set. May represent in-progress experimental work that has not been registered. Doctor emits `info()` with non-destructive guidance: `"Branch {branch} has no entity record. Either run /pd:brainstorm to register, or delete if abandoned."`
- **Not orphans (silent):** `{active, planned, paused, in_progress}` — user may resume; no output regardless of merge state.

Reference: `plugins/pd/hooks/lib/entity_lifecycle.py` ENTITY_MACHINES for canonical state names. Doctor reads filesystem `.meta.json` only (no MCP dependency for the check); status set is hardcoded.

**Logic:**
1. Iterate `git for-each-ref --format='%(refname:short)' refs/heads/feature/*`.
2. For each branch, parse feature ID from branch name (regex: `feature/([0-9]+)-([a-z0-9-]+)`).
3. **Unparseable ID path:** If regex fails, emit `info()` line (not warn): `"Branch {branch}: no parsable feature ID — manual classification needed"`. Continue to next branch.
4. Locate matching `.meta.json` at `{artifacts_root}/features/{id}-{slug}/.meta.json`. If missing → status = `"no entity"`.
5. If `.meta.json` exists, read `status` field. If `status` not in canonical set → status = `"unknown"` (treated as orphan-qualifying).
6. Check merge status: `git merge-base --is-ancestor <branch> <base>`. Returns 0 if merged, 1 if unmerged.
7. Apply severity-split:
   - **Tier 1** (status in `{completed, cancelled, abandoned, archived}` AND unmerged) → emit `warn()` with message `"Orphan branch: {branch} (status={status}, unmerged into {base}). Cleanup: git branch -D {branch} if no longer needed."`
   - **Tier 2** (status in `{"no entity", "unknown"}` AND unmerged) → emit `info()` with message `"Branch {branch} has no entity record (status={status}, unmerged into {base}). Either run /pd:brainstorm to register, or delete if abandoned."`
   - **Not orphan** (status in `{active, planned, paused, in_progress}` OR merged into base) → silent (no per-branch output).
8. After loop: emit one summary line:
   - If zero Tier 1 + Tier 2: `pass()` `"No stale feature branches"`.
   - If ≥1 Tier 1: `info()` `"Total: {N1} cleanable orphan(s), {N2} unregistered branch(es)"`.

**Empirical:**
```text
>>> subprocess.run(['git', 'merge-base', '--is-ancestor', 'feature/099-retro-prevention-batch', 'develop'], capture_output=True).returncode  → 1   (unmerged — current branch)
>>> re.match(r'feature/([0-9]+)-([a-z0-9-]+)', 'feature/099-retro-prevention-batch').groups()                                                → ('099', 'retro-prevention-batch')
>>> re.match(r'feature/([0-9]+)-([a-z0-9-]+)', 'feature/no-id-here')                                                                          → None
```

**Performance:** O(N) where N = feature branch count. Each branch check: 1 regex + 1 file stat + 1 git invocation. Typical: <500ms for ≤20 branches.

### FR-4: Doctor `check_tier_doc_freshness`

**Function signature:** Add `check_tier_doc_freshness()` to `plugins/pd/scripts/doctor.sh`, called from `run_all_checks()` under `Project Hygiene`.

**Source-monitoring paths (project-configurable via `pd.local.md`):**

The default mapping (matching the convention in `finish-feature.md` Step 2b "Pre-Computed Git Timestamps") is:
- `user-guide` → `README.md package.json setup.py pyproject.toml bin/`
- `dev-guide` → `src/ test/ Makefile .github/ CONTRIBUTING.md docker-compose.yml`
- `technical` → `src/ docs/technical/`

Projects override via `.claude/pd.local.md`:
```
tier_doc_root: docs                                    # default; root containing user-guide/, dev-guide/, technical/
tier_doc_source_paths_user_guide: README.md plugins/ scripts/
tier_doc_source_paths_dev_guide: plugins/pd/ scripts/ docs/dev_guides/
tier_doc_source_paths_technical: plugins/pd/ docs/technical/
```
If a project does not set these fields, defaults are used (`tier_doc_root: docs`; source paths per the table above). The pd repository (which has no `src/`, `test/`, etc. at root) SHOULD set the source-path fields in its `pd.local.md` to make the check meaningful — recorded as a follow-up implementation step in design phase. Misconfigured `tier_doc_root` (pointing to non-existent directory) emits info `"No docs in tier {tier}"` — fail-quiet by design; configuration drift is a doctor-detectable secondary issue out of scope here.

**Logic:**
1. Read threshold from `pd.local.md` field `tier_doc_staleness_days` (default: `30`).
2. Read per-tier source paths from `pd.local.md` `tier_doc_source_paths_{tier}` fields (default to mapping above).
3. For each tier in `{user-guide, dev-guide, technical}`:
   - Glob `docs/{tier}/*.md`. If glob is empty → info "No docs in tier {tier}".
   - For each doc, parse YAML frontmatter `last-updated:` field via `python3 -c "import yaml,sys; print(yaml.safe_load(open(sys.argv[1]).read().split('---')[1]).get('last-updated',''))"`.
   - Compute source timestamp: `git log -1 --format=%aI -- <space-separated source paths>`.
   - If frontmatter `last-updated` missing → info `"Skipped: {doc} (no last-updated frontmatter)"` (covered by AC-E3).
   - If `git log` returns empty (no commits matching paths) → info `"Skipped: {doc} (tier {tier}: no source commits)"`.
   - If both parsed, compute `gap_days = floor((source_ts - last_updated_ts) / 86400)`.
   - If `gap_days > threshold` → warn `"Tier doc stale: {doc} (last-updated {date}, source modified {gap_days}d later)"`.

**Performance:** O(T*D) where T=3 tiers, D=tier doc count. Each doc: 1 file read (for frontmatter) + 1 python invocation + 1 git invocation. Typical: <2s for ≤30 docs.

### FR-5: PreToolUse hook `pre-edit-unicode-guard.sh`

**File:** `plugins/pd/hooks/pre-edit-unicode-guard.sh` (new)

**Trigger:** PreToolUse, matcher `Write|Edit` (NotebookEdit excluded — not consistently registered in CC at present).

**Input contract (CC PreToolUse hook stdin JSON):**
```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Edit" | "Write",
  "tool_input": {
    "file_path": "...",
    "old_string": "...",        // Edit only
    "new_string": "...",        // Edit only
    "content": "..."            // Write only
  },
  "session_id": "...",
  "transcript_path": "...",
  "cwd": "..."
}
```
Reference: existing `meta-json-guard.sh` reads the same shape; engineering memory entry `"Local PreToolUse hooks must include hookEventName"` confirms the field is required for hook routing.

**Short-circuit gate (must be first step in logic):**
1. If `hook_event_name != "PreToolUse"` → exit 0 with stdout `{"continue": true}`, no stderr.
2. If `tool_name not in ("Edit", "Write")` → exit 0 with stdout `{"continue": true}`, no stderr.
3. Else proceed to scan logic.

**Implementation note (defensive short-circuit retained for testability):**
> Steps 1-2 are defensively redundant in production because hooks.json registration under `PreToolUse` with matcher `"Write|Edit"` already routes only matching events to this hook. However, both short-circuits MUST be retained: (a) AC-6c and AC-6d test the hook by piping JSON directly to stdin, bypassing the CC routing, and require the defensive checks to pass; (b) the same defensive pattern is used in `meta-json-guard.sh` for consistency; (c) future-proofing against potential CC matcher-routing changes. Implementer MUST NOT remove these as "dead code" — they are testable code paths.

**Scan logic:**
4. Use python3 (one-shot subprocess; ~80ms typical) to:
   - Parse stdin JSON.
   - Inspect `tool_input.old_string`, `tool_input.new_string`, `tool_input.content` (each optional; absent → empty string).
   - Collect codepoints `> 127` from each field. Track per-field findings.
   - **Dedup + ordering:** within each field, report unique codepoints in **first-occurrence order**, capped at **5 unique per field** (and 5 fields total → max 15 reported across all fields).
5. If any codepoints found, emit single-line stderr warning per field:
   ```
   [pd] Unicode codepoint(s) detected in {field}: [(0x{cp:04x}, {repr(char)}), ...]. Edit/Write may strip these silently. Use Python read-modify-write with chr(0x{cp:04x}) runtime generation. See plugins/pd/skills/systematic-debugging/SKILL.md → "Tooling Friction Escape Hatches".
   ```
6. Always emit JSON `{"continue": true}` to stdout. Exit 0.

**Failure modes (all silent-pass):**
- JSON parse fails → exit 0, stdout `{"continue": true}`, no stderr.
- python3 missing → exit 0, stdout `{"continue": true}`, no stderr (bash detects missing interpreter, falls through).
- Required keys absent → treated as no-codepoints case.
- Hook NEVER blocks tool execution under any condition.

**Scope of codepoint check:** Codepoints `> 127` only (high-byte Unicode that triggers Edit-tool stripping per heuristics). Control range `0-31` is OUT OF SCOPE — those are typically intentional (`\t`, `\n`, `\r`) and false-positive risk is high.

**Registration:** Add new entry under `PreToolUse` in `plugins/pd/hooks/hooks.json` with matcher `"Write|Edit"`.

**Performance:** Target <200ms wall clock. python3 startup (~80ms) + JSON parse + linear scan over inputs (≤1MB typical).

**Empirical:**
```text
>>> any(ord(c) > 127 for c in chr(0x85))                                                              → True
>>> any(ord(c) > 127 for c in 'hello')                                                                → False
>>> any(ord(c) > 127 for c in '')                                                                     → False
>>> # Dedup + ordering test
>>> seen = []; [seen.append(c) for c in chr(0x85)+chr(0xa0)+chr(0x85)+chr(0x2014)+chr(0x2014) if ord(c)>127 and c not in seen]; [hex(ord(c)) for c in seen[:5]]  → ['0x85', '0xa0', '0x2014']
```

### FR-6a: `/pd:cleanup-backlog` command

**Files (simplified — no skill):**
- `plugins/pd/commands/cleanup-backlog.md` (new — command entry point with thin orchestration)
- `plugins/pd/scripts/cleanup_backlog.py` (new — Python parser + writer)

The command file dispatches directly to the script. A separate skill is unnecessary because the workflow is single-step: parse → preview → optional write. AskUserQuestion (auto-confirmed in YOLO) is invoked from the command body, not a skill.

**Canonical "active item" predicate (shared with FR-6b):**

A line in `backlog.md` is a **backlog item** iff it matches `ITEM_RE = r'^- (~~)?\*\*#\d+\*\*'`. (Both strikethrough and non-strikethrough variants count as items.)

A backlog item is **closed** iff:
- The line starts with `^- ~~` (strikethrough form), OR
- The line contains any of: `(closed:`, `(promoted →`, `(fixed in feature:`, or the marker `**CLOSED` (case-sensitive).

A backlog item is **active** iff it is an item AND not closed.

This predicate is implemented as a shared helper `is_item_closed(line: str) -> bool` in `cleanup_backlog.py`. Doctor `check_active_backlog_size` (FR-6b) uses the same logic via direct grep equivalent (see FR-6b for the regex form).

**Inputs (CLI flags — full enumeration):**

| Flag | Mutex with | Default | Purpose |
|------|------------|---------|---------|
| `--dry-run` | `--apply`, `--count-active` | (default mode) | Preview archivable sections; no writes. Default behavior when no flag is given. |
| `--apply` | `--dry-run`, `--count-active` | – | Perform writes (move sections from backlog to archive, commit). |
| `--count-active` | `--dry-run`, `--apply` | – | Print active-item count to stdout (single integer). Used by AC-X1 cross-check with doctor. |
| `--backlog-path PATH` | – | `{pd_artifacts_root}/backlog.md` | Override backlog source path (used by fixture-backed ACs). |
| `--archive-path PATH` | – | `{pd_artifacts_root}/backlog-archive.md` | Override archive destination path (used by fixture-backed ACs). |

Mode selection: exactly one of `{--dry-run, --apply, --count-active}` may be present. Absence of all three implies `--dry-run` (default). Presence of more than one → exit 2 with usage error.

Reads (default mode): `{pd_artifacts_root}/backlog.md`.

**Logic:**
1. Parse `backlog.md` into sections demarcated by `^## From ` headers (matches both `## From Feature 086 QA` and `## From Features 082 & 084 ...`). Section ends at next `^## ` heading or EOF.
2. For each per-feature section:
   - Apply `ITEM_RE` to enumerate items.
   - Apply `is_item_closed()` to each.
   - Section is `ARCHIVABLE` iff item count > 0 AND 100% of items are closed.
3. **Dry-run output (default behavior of `--dry-run`):** stdout markdown table:
   ```
   | Section | Items | Closed | ARCHIVABLE |
   |---------|-------|--------|------------|
   | From Feature 086 QA | 12 | 12 | YES |
   ...
   Total: K archivable section(s) with M items.
   ```
4. **Live mode** (no `--dry-run`):
   - Confirm via AskUserQuestion in command body (auto-confirmed in YOLO).
   - For each ARCHIVABLE section: append the exact section text (header line + blank line + item lines + trailing blank) to `{pd_artifacts_root}/backlog-archive.md`. If archive file absent, create with header:
     ```
     # Backlog Archive

     Closed sections moved from backlog.md by /pd:cleanup-backlog.

     ```
     (4 lines including trailing blank: H1, blank, body, blank.)
   - Remove the section from `backlog.md` in-place (preserve surrounding blank lines).
   - Single git commit: `docs(backlog): archive {N} fully-closed sections`.

**Idempotency (NFR-5):** Running cleanup-backlog twice in succession produces zero diffs on the second run. Verified: after first run, all `ARCHIVABLE` sections are gone from backlog.md, so the second run finds zero archivable sections and exits without writes.

**Top-level table (any markdown table appearing BEFORE the first `^## From ` heading):** OUT OF SCOPE — left untouched. Only `^## From ` headed sections are evaluated. Items in the top-level table that are closed remain there until manual cleanup. (No line-number coupling — the parser identifies the boundary structurally.)

### FR-6b: Doctor `check_active_backlog_size`

**Function signature:** Add `check_active_backlog_size()` to `plugins/pd/scripts/doctor.sh`, called from `run_all_checks()` under `Project Hygiene`.

**Item predicate (shared with FR-6a, expressed as bash-grep):**

The grep-equivalent of FR-6a's `is_item_closed()`:
- Items: `grep -E '^- (~~)?\*\*#[0-9]+\*\*' backlog.md`
- Active items: items minus closed ones; achieved via `grep -v -E '^- ~~|\(closed:|\(promoted →|\(fixed in feature:|\*\*CLOSED'`

The two predicates (Python in FR-6a, grep here) MUST agree on every line — verified by AC-X1 below.

**Logic:**
1. Read threshold from `pd.local.md` field `backlog_active_threshold` (default: `30`).
2. Count active items in `docs/backlog.md`:
   ```bash
   grep -cE '^- \*\*#[0-9]+\*\*' backlog.md
   # Then subtract closed items count (or use single combined grep with negative lookahead)
   ```
   Implementation may use a single python3 invocation calling the shared `is_item_closed()` helper from `cleanup_backlog.py` to ensure exact agreement with FR-6a.
3. If count > threshold → warn `"Active backlog: {count} items (threshold {threshold}). Run /pd:cleanup-backlog to archive closed sections."`
4. If count ≤ threshold → pass `"Active backlog: {count} items"`.

**Performance:** O(N) lines, single grep or python invocation. <200ms typical.

### FR-7: Specifying empirical-verification Self-Check

**Self-Check item (added to `specifying/SKILL.md`):**
> "If any FR or AC references stdlib runtime behavior — including but not limited to: regex flags via `.flags` / `re.compile()` / `re.ASCII` / `re.UNICODE`; `re`, `sys`, `pkgutil`, `inspect`, `unicodedata`, `datetime`, `json`, `pathlib`, `subprocess` module APIs; encoding semantics like `str.isspace`, `str.isdigit`, `str.isascii`, `unicodedata.category`, `unicodedata.normalize` — include a Python REPL verification line inline using format `>>> <expr> → <result>` (or equivalent block). Empirical evidence at spec time prevents iteration-deferred blockers."

**Spec-reviewer enforcement (added to `agents/spec-reviewer.md`):**
- New challenge category: `Empirical Verification`
- **Trigger keywords** (broadened): `re\.|pkgutil\.|inspect\.|unicodedata\.|sys\.|datetime\.|json\.|pathlib\.|subprocess\.|str\.is\w+`
- **Mode: judgment-based, not auto-emit.** The reviewer applies this check with judgment:
  - If FR text contains a trigger keyword AND that keyword's behavior is **load-bearing for an AC** (i.e., the AC's pass/fail depends on the runtime semantics) → emit `severity: warning` with category `empirical-verification`, suggestion: `"Add a Python REPL verification line near the FR demonstrating the runtime contract."`
  - If the trigger keyword appears only in **prose context** (e.g., "see re.compile docs", "uses datetime to parse") and no AC depends on its semantics → no issue.
- This judgment rule reduces false positives (prose mentions) without missing false negatives (load-bearing claims).

**Self-application:** This very spec includes an "Empirical Verifications" block at the top as proof-of-pattern. Note that this spec mentions `datetime.fromisoformat` (FR-4 frontmatter parsing); the Empirical Verifications block now includes `datetime.fromisoformat('2026-04-29T00:00:00Z'...)` to satisfy the rule on its own load-bearing claim.

### FR-8: `/pd:test-debt-report` command

**Files:**
- `plugins/pd/commands/test-debt-report.md` (new)
- `plugins/pd/scripts/test_debt_report.py` (new)

**Inputs:**
- Glob `{pd_artifacts_root}/features/*/.qa-gate.json` — collect findings with severity in {`MED`, `LOW`, `MEDIUM`}.
- Read `{pd_artifacts_root}/backlog.md` lines matching `^- \*\*#[0-9]+\*\* \[[^/]+/testability\]` (active testability tag, excluding `^- ~~`).

**Category derivation rule:**

For each finding, derive `category` as follows (in priority order):
1. If finding's JSON has explicit `"category"` field → use it as-is.
2. Else, derive from `reviewer` field via this map:
   - `pd:test-deepener` → `"testability"`
   - `pd:security-reviewer` → `"security"`
   - `pd:code-quality-reviewer` → `"quality"`
   - `pd:implementation-reviewer` → `"implementation"`
3. Else → `"uncategorized"`.

For backlog-derived rows, the category comes from the bracketed tag suffix: `[*/testability]` → `testability`. The category column is never expected to be uniformly `"uncategorized"` — qa-gate findings always have a `reviewer` field per qa-gate-procedure.md §1, so the reviewer-name fallback always applies.

**Output:** Single markdown table to stdout:
```
# Test Debt Report ({date})

| File or Module | Category | Open Count | Source Features |
|----------------|----------|------------|-----------------|
| test_database.py:2354 | testability | 3 | 097, 098 |
| ...

Total: {N} open items across {M} files.
```

**Sort:** `Open Count` DESC, then `File or Module` ASC.

**Grouping:** Group by `(normalized_location, category)`. `normalize_location(loc)` semantics (inlined from qa-gate-procedure.md §4 for stability — pinned in this spec to avoid silent drift if upstream helper changes):

```python
import re
_NORMALIZE_LOC_RE = re.compile(r'([^/\s]+\.[a-z]+:\d+)')

def normalize_location(loc: str) -> str:
    """Extract `{filename_basename}:{line_number}` if found; else lowercased strip."""
    m = _NORMALIZE_LOC_RE.search(loc)
    if m:
        return m.group(1)  # e.g., 'plugins/pd/lib/foo.py:42' → 'foo.py:42'
    return loc.strip().lower()
```

**Empirical:**
```text
>>> normalize_location('plugins/pd/lib/foo.py:42')   → 'foo.py:42'
>>> normalize_location('test_database.py:2354')      → 'test_database.py:2354'
>>> normalize_location('Architecture-level note')    → 'architecture-level note'
>>> normalize_location('')                            → ''
```

If qa-gate-procedure.md §4's `normalize_location` ever changes, the FR-8 implementation MUST keep its own pinned copy (per this spec) until intentionally re-aligned in a follow-up feature.

**Read-only:** No writes. Pure aggregator. Exit 0 always.

**Performance:** O(F + B) where F = qa-gate.json files, B = backlog lines. Typical: <500ms for ≤50 files + 250 backlog lines.

## Acceptance Criteria

### Happy Paths

**AC-1 (FR-1 predicate):** Given a fixture diff containing paths `[tests/test_foo.py, plugins/pd/skills/specifying/test_self_check.py]`, when each path is evaluated via `re.search(TEST_FILE_RE, path)` and ALL match, then `IS_TEST_ONLY_REFACTOR=1`. Given fixture `[test_foo.py, database.py]`, then `IS_TEST_ONLY_REFACTOR=0` (database.py does not match). Given fixture `[plugins/pd/hooks/tests/test-hooks.sh]`, then `IS_TEST_ONLY_REFACTOR=0` (regex anchored to .py — shell tests excluded). Given empty fixture `[]`, then `IS_TEST_ONLY_REFACTOR=0` (vacuous truth not allowed; see AC-E1).

**AC-2 (FR-1 bucketing — extended signature with location helper):** Given the new bucket() signature `bucket(finding, all_findings, *, is_test_only_refactor=False)` and the `_location_matches_test_path()` helper:

Helper assertions (independently testable):
- `_location_matches_test_path("test_database.py:2354")` → `True` (suffix stripped, then TEST_FILE_RE matches).
- `_location_matches_test_path("test_database.py")` → `True` (no suffix, direct match).
- `_location_matches_test_path("plugins/pd/tests/test_foo.py:42")` → `True`.
- `_location_matches_test_path("database.py:1055")` → `False` (production file, not test).
- `_location_matches_test_path("plugins/pd/hooks/tests/test-hooks.sh:10")` → `False` (regex anchored to .py).
- `_location_matches_test_path("")` → `False`.

Bucket() call assertions:
- `bucket({reviewer: "pd:test-deepener", severity: "blocker", location: "test_database.py:2354", mutation_caught: false}, [], is_test_only_refactor=True)` → returns `"LOW"`.
- `bucket({...same finding...}, [], is_test_only_refactor=False)` → returns `"MED"` (existing AC-5b path preserved).
- `bucket({...same finding...}, [])` (no kwarg, default applies) → returns `"MED"` (backward-compat default-False).
- `bucket({reviewer: "pd:test-deepener", severity: "blocker", location: "database.py:1055", mutation_caught: false}, [], is_test_only_refactor=True)` → returns `"MED"` (location helper returns False; existing AC-5b applies).

**AC-3 (FR-2 Self-Check + reviewer):** `grep -E "recursive[ -]test[ -]hardening|Test\[A-Z\]" plugins/pd/skills/specifying/SKILL.md` returns ≥1 hit AND `grep -E "recursive[ -]test[ -]hardening|Test\[A-Z\]" plugins/pd/agents/spec-reviewer.md` returns ≥1 hit.

**AC-4 (FR-3 doctor stale branches):** `bash plugins/pd/scripts/doctor.sh 2>&1 | grep -E "stale.*feature.*branch|Project Hygiene"` returns ≥1 hit. With one or more orphan `feature/*` branches present, output contains `"Orphan branch:"` warning line.

**AC-5 (FR-4 doctor tier freshness):** `bash plugins/pd/scripts/doctor.sh 2>&1 | grep -E "tier.*doc|Tier doc"` returns ≥1 hit. With at least one tier doc whose source timestamp exceeds frontmatter `last-updated` by > 30 days, output contains `"Tier doc stale:"` warning line.

**AC-6 (FR-5 hook warning — single codepoint):** Running:
```bash
printf '{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"old_string":"%s"}}' "$(python3 -c 'print(chr(0x85), end="")')" \
  | bash plugins/pd/hooks/pre-edit-unicode-guard.sh
```
produces:
- stderr text matching regex `Unicode codepoint.*0x0085.*chr\(0x0085\)`
- stdout exactly `{"continue": true}`
- exit code 0

**AC-6b (FR-5 hook — dedup + ordering):** Given input with codepoints `[0x85, 0xa0, 0x85, 0x2014, 0x2014, 0x2014, 0x3000]` (NEL, NBSP, NEL repeat, em-dash repeat ×3, ideographic space), the stderr warning lists exactly 5 unique codepoints in first-seen order: `0x0085, 0x00a0, 0x2014, 0x3000` followed by no further entries (only 4 unique present; cap unreached). For 6+ unique input, only first 5 by occurrence order appear.

**AC-6c (FR-5 hook — short-circuit on non-PreToolUse):** Given JSON input with `hook_event_name: "SessionStart"` (not PreToolUse), the hook exits 0 with stdout `{"continue": true}` and EMPTY stderr (no codepoint scan performed regardless of payload).

**AC-6d (FR-5 hook — short-circuit on non-Write/Edit):** Given JSON input with `hook_event_name: "PreToolUse"` AND `tool_name: "Bash"`, the hook exits 0 with stdout `{"continue": true}` and EMPTY stderr.

**AC-7 (FR-5 hook registration):** `python3 -c "import json; d=json.load(open('plugins/pd/hooks/hooks.json')); pre=[h for h in d['hooks']['PreToolUse'] if any('pre-edit-unicode-guard' in c.get('command','') for c in h.get('hooks',[]))]; print(len(pre), pre[0]['matcher'] if pre else '')"` outputs `1 Write|Edit` (exact).

**AC-8 (FR-6a dry-run on FIXTURE):** Given a fixture `tests/fixtures/backlog-099-archivable.md` containing exactly:
- 3 sections with all items closed (mix of strikethrough/`(closed:` markers)
- 1 section with mixed states (≥1 active item)
- 1 section with 0 items (header only)

Running `python3 plugins/pd/scripts/cleanup_backlog.py --dry-run --backlog-path tests/fixtures/backlog-099-archivable.md` prints a markdown table identifying exactly 3 ARCHIVABLE sections (the all-closed ones). The mixed-state and zero-item sections are NOT archivable. No writes to the fixture occur (verified via post-invocation `md5sum` unchanged).

**AC-8b (FR-6a dry-run on REAL backlog):** Running `python3 plugins/pd/scripts/cleanup_backlog.py --dry-run` on the project's actual `docs/backlog.md` exits 0 and prints a non-empty table (≥1 row). The exact archivable-section count is project-state-dependent and NOT asserted (this is a smoke test of the parser against real data, not a stateful assertion).

**AC-9 (FR-6a live — fixture-backed):** Given the same fixture as AC-8 with archive file ABSENT. Running `python3 plugins/pd/scripts/cleanup_backlog.py --apply --backlog-path tests/fixtures/backlog-099-archivable.md --archive-path tests/fixtures/backlog-099-archive.md` (and YOLO auto-confirm if interactive prompt fires):
- (a) Fixture backlog line count DECREASES by AT LEAST `sum(section_lines_per_archived)` where `section_lines_per_archived` is the count from the section's `## From ` header line through the last item line (NOT including the trailing blank line). The actual decrease may exceed this by `N_collapsed_blanks` (number of inter-section blank-line pairs collapsed per rule (f)). Strict invariant: the post-archive backlog has no double-blank-line runs (see (f)).
- (b) Archive file is CREATED with the standard 4-line header (H1 `# Backlog Archive`, blank, body line, blank) PLUS one trailing blank between header and first appended section, PLUS the moved-section content (each section appended with its `## From ` header + items + one trailing blank line for separation).
- (c) Total archive file line count = `4 (header) + sum(section_lines_per_archived) + N_archived_sections (trailing blanks)` for the first-creation case.
- (d) Post-run: re-running with `--apply` produces zero diffs (NFR-5 idempotency).
- (e) Each moved section text appears verbatim in archive (header line and item lines preserved byte-for-byte).
- **(f) Trailing-blank collapse rule:** After section removal, the parser MUST NOT leave consecutive blank-line runs in `backlog.md`. Specifically: if removing a section leaves two adjacent blank lines (one before the removed section, one after), they collapse to a single blank line. Verified post-archive: `grep -c '^$' backlog.md` shows no double-blank runs (`grep -Pzo '\n\n\n' backlog.md` returns empty).
- **(g) Section-removal boundary:** An archived section is removed as a contiguous block from the first character of its `## From ` header through the trailing newline immediately before the next `## ` heading (or EOF if last). Inter-section blank lines are handled by (f).

**AC-10 (FR-6b doctor backlog):** `bash plugins/pd/scripts/doctor.sh 2>&1 | grep -E "Active backlog"` returns ≥1 hit. With current backlog containing >30 active items, output contains `"items (threshold 30)"`. After cleanup-backlog reduces active count below 30, output shifts to pass status.

**AC-11 (FR-7 Self-Check):** `grep -cE "Empirical|empirically.*verif|>>> " plugins/pd/skills/specifying/SKILL.md` returns ≥2.

**AC-12 (FR-7 reviewer):** `grep -E "Empirical Verification|stdlib runtime|>>> " plugins/pd/agents/spec-reviewer.md` returns ≥1 hit.

**AC-13 (FR-8 output):** `python3 plugins/pd/scripts/test_debt_report.py` produces stdout containing the markdown table header (literal `| File or Module | Category | Open Count | Source Features |`) AND ≥1 data row aggregated from the project's existing `.qa-gate.json` files.

**AC-14 (FR-8 schema):** The first non-empty pipe-row in `/pd:test-debt-report` output contains exactly 4 column delimiters (5 pipes when accounting for leading/trailing). Verified via `head -3 | tail -1 | tr -cd '|' | wc -c` returns `5`.

**AC-15 (Lint cleanliness — split per language):**
- (a) Shell: `bash -n plugins/pd/hooks/pre-edit-unicode-guard.sh` returns 0. `bash -n plugins/pd/scripts/doctor.sh` returns 0.
- (b) Python: `python3 -m py_compile plugins/pd/scripts/cleanup_backlog.py` returns 0. `python3 -m py_compile plugins/pd/scripts/test_debt_report.py` returns 0.
- (c) Markdown frontmatter: For each new `.md` file in `plugins/pd/commands/{cleanup-backlog,test-debt-report}.md`, `python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]).read().split('---')[1])"` returns 0 (no parse errors).
- (d) JSON: `python3 -c "import json; json.load(open('plugins/pd/hooks/hooks.json'))"` returns 0 (well-formed after registration).

**AC-16 (Validation):** `./validate.sh` exits 0 on the feature branch HEAD. No portability violations, no broken doctor checks, no malformed JSON in `hooks.json`.

### Error & Boundary Cases

**AC-E1 (FR-1 empty diff):** Given empty diff (`git diff develop..HEAD --name-only` returns nothing), `IS_TEST_ONLY_REFACTOR=0` (vacuous truth not allowed). Bucketing falls through to existing behavior.

**AC-E2 (FR-3 no feature branches):** Given no `refs/heads/feature/*` branches, `check_stale_feature_branches()` emits one `pass()` line: `"No feature branches"`.

**AC-E3 (FR-4 missing frontmatter):** Given a tier doc with no `last-updated` field, `check_tier_doc_freshness()` emits an info() (not warn) line: `"Skipped: {doc} (no last-updated frontmatter)"`.

**AC-E4 (FR-5 invalid JSON):** Given malformed JSON on stdin, the hook exits 0, stderr is silent, stdout is `{"continue": true}`.

**AC-E5 (FR-5 binary content):** Given JSON containing non-printable codepoints in `content`, the hook scans ONLY codepoints `> 127` (per FR-5 step 4 scope). Control range `0-31` is OUT OF SCOPE — not scanned, not flagged. Hook does not crash on binary or non-printable input.

**AC-E9 (FR-3 unparseable branch):** Given a branch named `feature/no-id-here` (no parsable feature ID matching `feature/([0-9]+)-`), `bash plugins/pd/scripts/doctor.sh 2>&1 | grep -E "no-id-here"` returns ≥1 line containing the `info` marker (cyan circle prefix in colored output, or `[INFO]` in stripped output) and NOT containing `Orphan branch:` or `warn` markers.

**AC-X1 (FR-6a/FR-6b predicate agreement):** Given the project's current `docs/backlog.md`, the active-item count from cleanup_backlog.py's `count_active()` helper equals the active-item count from doctor's `check_active_backlog_size`. Verified via:
```bash
python_count=$(python3 plugins/pd/scripts/cleanup_backlog.py --count-active)
# Two-stage extraction: grep pins to "Active backlog: <N>" line; second grep extracts ONLY the digits at end.
# Robust to message-template wording drift as long as the "Active backlog:" prefix remains.
doctor_count=$(bash plugins/pd/scripts/doctor.sh 2>&1 | grep -oE "Active backlog: [0-9]+" | head -1 | grep -oE "[0-9]+$")
[ "$python_count" = "$doctor_count" ] && echo MATCH || echo MISMATCH
```
Expected output: `MATCH`.

**AC-E6 (FR-6a malformed backlog):** Given a `## From ...` section with no items (header only), it is NOT marked ARCHIVABLE (item count = 0).

**AC-E7 (FR-6a re-run):** Running cleanup-backlog twice produces a no-op on the second invocation (NFR-5 idempotency). `git status` after second run shows no modifications.

**AC-E8 (FR-8 empty inputs):** Given zero `.qa-gate.json` files AND zero matching backlog entries, the report emits an empty table with header only and footer `"Total: 0 open items across 0 files."`. Exit code 0.

## State Transitions (Optional)

### FR-1 Bucketing Truth Table (extended)

"location matches test path" below means `_location_matches_test_path(finding.location)` returns True (i.e., after stripping `:line` suffix, TEST_FILE_RE matches).

| reviewer | severity | securitySeverity | mutation_caught | cross_confirm | IS_TEST_ONLY | _loc_matches_test_path | → final |
|----------|----------|------------------|-----------------|---------------|--------------|------------------------|---------|
| pd:test-deepener | blocker | – | false | false | True | True | **LOW** (new) |
| pd:test-deepener | blocker | – | false | false | True | False | MED (existing AC-5b) |
| pd:test-deepener | blocker | – | false | false | False | – | MED (existing AC-5b) |
| pd:test-deepener | blocker | – | false | true | – | – | HIGH |
| pd:test-deepener | blocker | – | true | – | – | – | HIGH |
| any other | blocker | – | – | – | – | – | HIGH |
| any | warning | – | – | – | – | – | MED |
| any | suggestion | – | – | – | – | – | LOW |

## Feasibility Assessment

### Assessment: **Confirmed** (all 8 FRs have working precedents in pd codebase or stdlib).

**Codebase Evidence:**
- FR-1: Bucketing logic exists at `docs/dev_guides/qa-gate-procedure.md:120-143`. Extension is additive.
- FR-2, FR-7: Self-Check pattern at `plugins/pd/skills/specifying/SKILL.md:187-198`. Append items.
- FR-3, FR-4, FR-6b: `check_*` function pattern at `plugins/pd/scripts/doctor.sh:139-419`. 11 existing checks; add 3.
- FR-5: PreToolUse hook pattern at `plugins/pd/hooks/meta-json-guard.sh` + `plugins/pd/hooks/hooks.json:88-95`. Add new entry.
- FR-6a: Bash + Python helper pattern at `plugins/pd/scripts/doctor.sh` + supporting scripts.
- FR-8: Read-only Python aggregator pattern at multiple existing scripts.

**External Evidence:**
- CC PreToolUse hook input format: tool_input fields `file_path`, `old_string`, `new_string`, `content` documented in CC hooks reference. Existing meta-json-guard.sh confirms field availability.
- Python `re`, `pkgutil`, `unicodedata` APIs verified at spec time (see Empirical Verifications above).

**Key Assumptions:**
- (Verified at spec time) Python codepoint inspection via `ord(c) > 127` correctly identifies all non-ASCII codepoints in str input.
- (Verified) `git for-each-ref --format='%(refname:short)' refs/heads/feature/*` returns local branches matching the prefix.
- (Verified) `git merge-base --is-ancestor <branch> <base>` returns 0 for merged ancestors, 1 for unmerged.
- (Verified) `unicodedata.category(chr(0x85))` returns `'Cc'` (control), `chr(0x85).isspace()` returns `True` — i.e., NEL is special-cased as whitespace despite being control category.

**Open Risks:**
- (LOW) NotebookEdit matcher absent from CC hooks ecosystem — handled by excluding it from the Write|Edit matcher.
- (LOW) `last-updated` frontmatter values could be either timezone-aware ISO 8601 or naive — Python `datetime.fromisoformat()` handles both with proper parsing; AC-E3 covers parse-fail case.
- (LOW) Per-feature `## From ...` header parsing in cleanup-backlog: regex must handle both `## From Feature 086 QA (date)` and `## From Features 082 & 084 ...` (compound). The matcher uses `^## From ` prefix only; section ends at next `^## ` heading.

## Non-Functional Requirements

**NFR-1 (Plugin portability):** All new files reference plugin paths via two-location glob (cache + dev fallback) where applicable. NEW shell scripts use `${CLAUDE_PLUGIN_ROOT}` from hook context OR project-relative paths. NO hardcoded `/Users/.../plugins/` absolute paths. Verified via `validate.sh` portability check (AC-16).

**NFR-2 (Backwards compatibility):** Existing AC-5b narrowed-remap logic preserved unchanged. New FR-1 test-only-mode predicate is ADDITIVE — new MED-to-LOW path only fires after existing AC-5b would have produced HIGH→MED. Existing doctor checks unchanged. Existing PreToolUse hooks unchanged. No existing behavior altered.

**NFR-3 (Doctor performance):** New checks (FR-3 + FR-4 + FR-6b) complete within 3 seconds combined on a typical project (≤50 features, ≤200 backlog items, ≤30 tier docs).

**NFR-4 (Hook performance):** `pre-edit-unicode-guard.sh` completes within 200ms on inputs ≤1 MB. Single python3 invocation; no recursive shell spawns.

**NFR-5 (Idempotency):** `/pd:cleanup-backlog` is safe to re-run. After one full archival run, the second run produces zero diffs (git status clean). Achieved by archiving entire sections atomically (header + items together) — re-evaluation finds no remaining ARCHIVABLE sections.

**NFR-6 (Telemetry/observability):** Doctor's existing `pass`/`warn`/`info` counters increment correctly for new checks. Full `bash plugins/pd/scripts/doctor.sh` summary line includes new check outcomes in totals.

**NFR-7 (No regressions in feature 091-098 surfaces):** Running existing test suite (`plugins/pd/.venv/bin/python -m pytest plugins/pd/`) on the feature branch produces zero new failures vs. develop baseline.

**NFR-8 (Independent FR shippability):** Each FR (FR-1 through FR-8) is independently shippable. Partial completion at FR boundary is acceptable — if FR-6a or FR-8 hit unforeseen complexity during implement, those FRs can be deferred to a follow-up feature without blocking the others. Implement-phase task-grouping (per `implementing` skill batching) MUST honor FR boundaries: no task spans two FRs unless explicitly justified in tasks.md. This addresses the breadth concern (8 FRs across 6 subsystems).

## Source Findings (compensates for missing PRD)

| FR | Originating retro/KB entry | One-line motivation |
|----|---------------------------|---------------------|
| FR-1 | `docs/features/097-iso8601-test-pin-v2/qa-override.md` | Recursive test-hardening anti-pattern: gate auto-files MEDs from test-only refactors that don't translate to production exposure. |
| FR-2 | `docs/features/097-iso8601-test-pin-v2/retro.md` Tune #1 + qa-override.md | Surface architectural decision at SPEC time, not after 3 review iterations + override. |
| FR-3 | This session weakness review (W4) — `feature/092-091-qa-residual-hotfix` orphan observed at session start. | Branch-lifecycle leakage despite finish-feature shipping cleanly. |
| FR-4 | `docs/features/098-tier-doc-frontmatter-sweep/retro.md` | Tier-doc drift accumulated across 8 features (079-097); audit cadence reactive. |
| FR-5 | `plugins/pd/skills/systematic-debugging/SKILL.md` Tooling Friction Escape Hatches + features 095/096/097 retros | Edit-tool Unicode-stripping hit 3 release cycles in a row; documented in heuristics but not enforced. |
| FR-6a/6b | This session weakness review (W2); `docs/backlog.md` 219 entries (~190 closed). | Backlog auto-files from QA gate; no decay/triage. |
| FR-7 | `docs/features/097-iso8601-test-pin-v2/retro.md` Tune #2 (specify-time empirical verification) | Spec iter-1 had 4 blockers, all empirically verifiable. |
| FR-8 | This session weakness review (W7) | No aggregated view of test-debt; per-feature `.qa-gate.json` files orphaned after release. |

## Dependencies

- Existing `entity-registry` MCP server (or `.meta.json` filesystem fallback) for FR-3 active-feature lookup.
- Existing `qa-gate-procedure.md` §4 `bucket()` function (extension target).
- Existing `pd.local.md` config-reading pattern (`read_config_field()`) in doctor.sh for new threshold fields.
- Python 3.10+ stdlib (`re`, `json`, `unicodedata`, `pkgutil`, `pathlib`, `datetime`).

## Open Questions

- None. All design decisions resolved at spec time via empirical verification + codebase precedent.

## Provenance

- **Source:** 2026-04-29 weakness review (this session, post-feature-098).
- **Cross-references:**
  - `docs/features/097-iso8601-test-pin-v2/qa-override.md` — recursive test-hardening architectural decision (FR-1, FR-2).
  - `docs/features/097-iso8601-test-pin-v2/retro.md` — empirical-verification Tune (FR-7).
  - `docs/features/098-tier-doc-frontmatter-sweep/retro.md` — tier-doc drift (FR-4).
  - `docs/backlog.md` "From Feature 086 QA" through "From Feature 097 Pre-Release QA Findings" — backlog asymmetry symptoms (FR-6).
  - `plugins/pd/skills/systematic-debugging/SKILL.md` "Tooling Friction Escape Hatches" — Edit-tool Unicode trap (FR-5).
