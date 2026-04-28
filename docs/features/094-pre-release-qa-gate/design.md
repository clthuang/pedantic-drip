# Design: Feature 094 — Pre-Release Adversarial QA Gate

## Status
- Created: 2026-04-29
- Phase: design
- Upstream: prd.md (12 FRs, 21 ACs, 4 NFRs); spec.md (passed at iteration 5: spec-reviewer 2 + phase-reviewer 3)

## Prior Art Research

Research collected during brainstorm Stage 2 (already documented in PRD Research Summary section). Key findings folded into design:

**Codebase patterns** (`pd:codebase-explorer`):
- Insertion point: `plugins/pd/commands/finish-feature.md:373-374` between Step 5a (validate.sh) and Step 5a-bis (/security-review)
- All 4 reviewer agents exist with documented JSON output schemas (`security-reviewer.md:106`, `code-quality-reviewer.md:61`, `implementation-reviewer.md:147-195`)
- No existing parallel reviewer dispatch in command layer — feature 094 establishes the first such pattern (closest precedent: `pd:researching` skill dispatches 2 agents in parallel)
- Idempotency-via-stored-SHA precedent: `implement.md:1140`
- Diff convention: `{base}...HEAD` three-dot (per `implement.md:250`)
- Block-with-override UX precedents: 4 instances in finish-feature/workflow-transitions/implement

**Industry patterns** (`pd:internet-researcher`):
- Semgrep Monitor/Comment/Block trichotomy maps directly to HIGH/MED/LOW
- Snyk per-severity break-config: critical+high block, medium warn, low advisory
- 4 parallel LLM reviewers wall-clock ≈ 60-90s
- GitHub Copilot review is advisory by design; merge-blocking requires CI wrapper

**Existing capabilities** (`pd:skill-searcher`):
- `pd:capturing-learnings` writes to `~/.claude/pd/memory`, NOT to `docs/backlog.md` — auto-filing must be implemented inline in the gate prose
- `pd:reviewing-artifacts` provides severity vocabulary, not orchestration
- `pd:retrospecting` skill is the natural place to fold sidecar files into retro.md (FR-7b update target)

## Architecture

### One change, three artifacts touched, two new files

```
plugins/pd/commands/finish-feature.md           ┐
  Step 5b heading + dispatch table              │
  + severity rubric inline                      │
  + decision tree                                ├──> Step 5b inserted
  + reference to procedure doc                  │     between line 373/374
                                                 │
docs/dev_guides/qa-gate-procedure.md  (NEW)     ┐
  Procedural detail extracted (FR-3..FR-11)     │
  All 11 sub-pieces concretized                  ├──> Always extracted
                                                 │     per AC-18/NFR-4
plugins/pd/skills/retrospecting/SKILL.md        ┐
  + sidecar fold step (FR-7b)                   │
  reads .qa-gate-low-findings.md, .qa-gate.log   ├──> Fold + delete
  appends under ## Pre-release QA notes          │     during retro run
                                                 │
plugins/pd/hooks/tests/test-hooks.sh            ┐
  + test_finish_feature_step_5b_present (8 greps)│
  + test_finish_feature_under_600_lines          ├──> Anti-drift assertions
  + test_qa_gate_procedure_doc_exists            │
                                                 │
docs/features/{id}/.qa-gate.json (RUNTIME)      ┐
docs/features/{id}/.qa-gate.log (RUNTIME)       ├──> Sidecar files written
docs/features/{id}/.qa-gate-low-findings.md     │     by gate at runtime
docs/features/{id}/qa-override.md               ┘     (gate-initiated, user-completed)
```

**No production Python or shell paths change.** The gate is **prose interpreted by Claude at run-time** in `finish-feature.md` (which Claude reads when the user invokes `/pd:finish-feature`).

## Technical Decisions

### TD-1: Always extract procedural detail to a referenced helper file

**Decision:** Step 5b in `finish-feature.md` keeps only the dispatch table (FR-2), severity rubric (FR-5 + AC-5b), and decision tree (HIGH→block / MED→file / LOW→sidecar). All other procedural detail (FR-3 prompt construction, FR-7a backlog write, FR-7b retrospecting update, FR-8 cache logic, FR-9 override mechanics, FR-10 JSON parse contract) extracted to `docs/dev_guides/qa-gate-procedure.md`. Step 5b prose contains an explicit reference link.

**Alternatives rejected:**
- *Inline everything in finish-feature.md.* The file is currently 508 lines; spec-reviewer estimated 120-180 lines of new content needed for full inline detail, pushing total to 600-700 lines. Conditional extraction (NFR-4 v1) introduces a branch in the design — implementers may not extract correctly. Always-extract removes the branch.
- *Extract to multiple helper files (one per FR).* Splits the procedure unnecessarily; one file keeps the gate procedure cohesive and discoverable.

**Rationale:** Single source of truth for the procedure. `finish-feature.md` stays under 600 lines (asserted by `test_finish_feature_under_600_lines`). Helper file is greppable, version-controlled, and references explicit FR/AC numbers for traceability.

### TD-2: Sidecar files (3) instead of one consolidated audit log

**Decision:** Use three distinct sidecars in the feature directory, each with a single concern:
- `.qa-gate.json` — idempotency cache (HEAD SHA + summary), POSIX atomic-rename writes
- `.qa-gate.log` — append-only audit + telemetry (skip events, per-reviewer counts)
- `.qa-gate-low-findings.md` — append-only LOW findings (markdown sections)

**Alternatives rejected:**
- *One unified `.qa-gate.log` with all events.* Mixing JSON cache state with markdown findings + audit lines breaks each consumer. Retrospecting skill would have to parse three sub-formats.
- *Embed all gate state in `.meta.json`.* Pollutes the feature metadata schema; the workflow-engine MCP layer has its own contract for `.meta.json`. Sidecars are filesystem-isolated.

**Rationale:** Each sidecar has one writer (gate), one consumer (retrospecting for `.log` + `-low-findings`; gate itself for `.json`). Clear ownership. Gate's own re-run logic only needs `.qa-gate.json`; retrospect only needs the other two. Independent file existence is explicit (per spec FR-7b note).

### TD-3: Per-section trimmed byte-count for `qa-override.md` rationale

**Decision:** Bypass check measures the **latest `## Override N (date)` section specifically**, NOT total file bytes. The user must write ≥50 bytes of new rationale per HIGH-block event; prior overrides' rationale does not satisfy a new gate failure.

**Algorithm:**
```bash
# Extract content from the highest-numbered Override section to EOF
last_n=$(grep -oE '^## Override [0-9]+' qa-override.md | grep -oE '[0-9]+' | sort -n | tail -1)
trimmed=$(awk "/^## Override ${last_n} /,0" qa-override.md \
  | sed -e '/^---$/,/^---$/d' \
        -e "/^## Override ${last_n} /d" \
        -e '/^<!-- User: write your rationale here/d' \
        -e '/^Findings this run:/d' \
        -e '/^- reviewer:/d' \
  | wc -c)
[[ "$trimmed" -ge 50 ]]
```

**Alternatives rejected:**
- *Raw `wc -c < qa-override.md` ≥ 50.* Gate-written frontmatter exceeds 50 bytes; empty-rationale files would auto-bypass.
- *File-level trimmed byte-count* (v1 of this TD). Auto-bypass on Override 2+ because Override 1's rationale already exceeds 50. Design-reviewer iter 1 blocker 3.
- *Require the user to delete the comment placeholder.* Too easy to miss; comment placeholder is a UX hint, not a flag.

**Rationale:** Per-section measurement is the only way to keep each new HIGH-block forcing fresh rationale. Pre-mortem advisor flagged "override normalization" as the dominant gate-collapse failure mode; allowing one rationale to satisfy multiple HIGHs would defeat the gate. The sed/awk pipeline is portable across macOS/Linux (`awk '/pattern/,0'` extracts pattern-to-EOF; available in BSD + GNU awk).

### TD-4: test-deepener narrowed remap (AC-5b) — coverage-debt vs cross-confirmed risk

**Decision:** test-deepener gaps remap HIGH→MED **only when** (a) `mutation_caught == false` AND (b) no other reviewer flagged the same `location`. If either condition fails, gap stays HIGH. Implemented as a deterministic predicate in the severity-bucket logic.

**Alternatives rejected:**
- *Always remap test-deepener HIGH→MED (v1 spec).* First-principles + antifragility advisors flagged: a security-critical untested path that test-deepener flags HIGH IS a production-bug-class risk if no other reviewer covered it. Blanket remap silently weakens detection of exactly the post-release class the gate was built for.
- *Never remap.* test-deepener routinely flags mutation-resistance gaps that ARE coverage-debt (e.g., "no test pins `[0-9]` literal vs `\d`"). Treating these as merge-blocking would condition override normalization (antifragility risk).

**Rationale:** Cross-confirmation is the antifragility signal — if security-reviewer also flagged the location, the gap is real. If only test-deepener flagged it AND mutation isn't caught, it's coverage-debt → MED.

### TD-5: HEAD-SHA-keyed cache with atomic-rename writes; stale-cache-untouched on block

**Decision:** `.qa-gate.json` writes use `tmp` file + `mv` for POSIX atomic-rename semantics. On INCOMPLETE or HIGH-block, the previous (passing) cache is left untouched — only successful PASS overwrites it.

**Alternatives rejected:**
- *Delete cache at dispatch start.* Crash mid-dispatch leaves no cache; subsequent re-run unnecessarily re-dispatches. Worse on YOLO crash recovery.
- *Update cache on every dispatch (regardless of outcome).* Loses the "skip if same HEAD passed before" property. Re-dispatching after a block then PASS would overwrite the original PASS state but cache would still be SHA-matched — confusing.

**Rationale:** Re-run on a fix-commit (different HEAD) naturally invalidates cache via SHA mismatch. Re-run on the same HEAD always implies the prior outcome is still valid (no code changed). Atomic-rename ensures observers never see partial JSON.

**Corruption handling:** If `.qa-gate.json` exists but does not parse as JSON OR is missing any of the required fields (`head_sha`, `gate_passed_at`, `summary`), treat as cache-miss and re-dispatch. Append warning to `.qa-gate.log`: `cache-corrupt: re-dispatching at HEAD {sha}`. Prevents silent skip on corrupted state.

**Step ordering dependency:** Step 5b only writes `.qa-gate.json` after Step 5a (validate.sh) has passed in the same `/pd:finish-feature` invocation. The cache represents "full pre-merge gate passed at this HEAD"; partial passes do not write cache. Step 5b reads cache at start (skip-if-match logic in FR-8 step 2) regardless of 5a outcome — but a stale cache from a prior 5a-passing run stays valid until HEAD changes.

### TD-6: Parallel dispatch via single Claude message (not sequential or async)

**Decision:** Step 5b prose instructs Claude to dispatch all 4 reviewers in **one message** with 4 `Task` tool calls. Claude (the orchestrator) waits for all 4 responses before evaluating severity buckets.

**Alternatives rejected:**
- *Sequential dispatch* (1 reviewer at a time). Wall-clock is 4× slower (~4 min instead of ~60-90s). Defeats <5-min NFR-1.
- *Background dispatch with later collection.* Claude's harness supports background agents but the gate logic needs all results before deciding. Background adds polling complexity for no latency win in this case.

**Rationale:** All 4 reviewers fit in `max_concurrent_agents: 5`. Wall-clock matches industry parallel-LLM-reviewer norms (~60-90s). Single-message dispatch is the canonical pattern from CLAUDE.md "If you intend to call multiple tools and there are no dependencies between them, make all independent tool calls in parallel."

### TD-7: Backlog ID extraction + per-feature sectioning

**ID extraction algorithm:**
1. `grep -oE '^- \*\*#[0-9]{5}\*\*' docs/backlog.md | grep -oE '[0-9]{5}' | sort -n | tail -1` to find max ID.
2. `next_id = max + 1` (zero-padded to 5 digits via `printf '%05d'`).
3. For batch MED filing in one run: reserve IDs sequentially `next_id, next_id+1, ...` in the order the gate processes findings (deterministic).

**Verification of regex coverage:** Run `grep -cE '^- \*\*#[0-9]{5}\*\*' docs/backlog.md` and compare against expected entry count documented in C2. As of 2026-04-29 the regex matches 100% of entries (all of #00001..#00263 follow this format — verified by spec-reviewer iter 1 audit). If a future entry uses a different format, broaden regex or pre-normalize.

**Section integration (per existing convention seen at backlog.md:222-340):**

The gate creates (if absent) a section heading near the top of `docs/backlog.md` for the running feature:
```markdown
## From Feature {feature_id} Pre-Release QA Findings ({date})

```
Subsequent runs of the same feature append within this section. Different features get their own section. Mirrors the existing 091/092/093 post-release structure.

**Insertion algorithm:**
1. Search `docs/backlog.md` for `^## From Feature {feature_id} Pre-Release QA`.
2. If found: append entries inside that section (after the heading, before the next `## ` heading).
3. If not found: insert new section heading + entries immediately before the first existing `## ` heading. (This places the new section near the top, in inverse-chronological order matching existing convention.)

**Alternatives rejected:**
- *Append to file EOF.* Breaks per-feature grouping convention; flat append-only structure mixes 094's findings into older sections.
- *Naive `grep -E '#\d{5}'`.* Over-counts cross-references like `(see #00193)` inside descriptions.
- *Track next-id in a separate state file.* Adds a sidecar with no benefit over scanning the source-of-truth.

**Rationale:** Anchored regex matches only top-of-list entries; sectioning matches existing 091/092/093 convention; inverse-chronological top-of-file insertion makes recent findings discoverable.

### TD-8: JSON parse via inline `python3 -c` heredoc with stdlib only

**Decision:** Step 5b prose tells Claude to invoke a single `Bash` call with `python3 -c '...'` heredoc that performs extraction + schema validation per reviewer. Claude pipes each reviewer's raw output text into stdin; Python returns either a parsed JSON object on stdout or exits non-zero with an error reason on stderr.

**Concrete shell snippet (template — full version in C2 procedure doc):**

```bash
python3 -c '
import sys, json, re
text = sys.stdin.read()
# Primary: fenced ```json block
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
if m:
    payload = m.group(1)
else:
    # Fallback: first balanced {...} (greedy enough for simple shapes)
    start = text.find("{")
    if start == -1:
        sys.exit("no_json_found")
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                payload = text[start:i+1]
                break
        i += 1
    else:
        sys.exit("unbalanced_braces")
try:
    obj = json.loads(payload)
except json.JSONDecodeError as e:
    sys.exit(f"json_decode_error: {e}")
# Schema validation per reviewer role (passed as $1)
role = sys.argv[1] if len(sys.argv) > 1 else ""
required = {"pd:security-reviewer": ["approved", "issues", "summary"],
            "pd:code-quality-reviewer": ["approved", "issues", "summary"],
            "pd:implementation-reviewer": ["approved", "issues", "summary"],
            "pd:test-deepener": ["gaps", "summary"]}
for f in required.get(role, []):
    if f not in obj:
        sys.exit(f"schema_missing: {f}")
print(json.dumps(obj))
' "$REVIEWER_ROLE" <<< "$REVIEWER_OUTPUT"
```

**Alternatives rejected:**
- *Claude performs extraction + validation cognitively.* Spec-reviewer iter 1 + design-reviewer iter 1 both flagged this as ambiguous. LLM "schema check" is non-deterministic; a malformed response could slip through if Claude pattern-matches loosely.
- *Strict JSON-only (require fenced block).* Reviewers often emit prose preamble + JSON; rejecting trips the INCOMPLETE path unnecessarily.
- *Adding `jq` dependency.* `jq` isn't guaranteed across all environments; `python3` is already required by pd's other shell scripts.

**Rationale:** stdlib `json` + `re` are deterministic, fast (<10ms per parse), and produce traceable failure reasons in the INCOMPLETE message. The snippet runs once per reviewer (4 invocations total per gate run); no measurable overhead.

## Architecture Components

### C1: Step 5b dispatch prose (in finish-feature.md)

**Owner:** finish-feature.md  
**Responsibility:** orchestrate the parallel 4-reviewer dispatch, evaluate severity buckets, route findings to block/file/note actions  
**Interfaces:** reads `.meta.json` for feature_id; writes `.qa-gate.json`, `.qa-gate.log`, `.qa-gate-low-findings.md`, optionally appends to `docs/backlog.md`, optionally writes `qa-override.md`  
**Size constraint:** ≤90 lines (Step 5b heading + 4-row dispatch table + severity predicates + decision tree + procedure doc reference + YOLO exception comment)

### C2: Procedure document (NEW)

**Owner:** docs/dev_guides/qa-gate-procedure.md  
**Responsibility:** concrete procedural detail for FR-3 (prompt construction) through FR-11 (YOLO behavior)  
**Interfaces:** referenced from C1; consumed by Claude when running Step 5b  
**Size constraint:** ~150-200 lines (one section per FR, with templates and examples)

### C3: retrospecting skill update (FR-7b)

**Owner:** plugins/pd/skills/retrospecting/SKILL.md  
**Responsibility:** during retro run, fold `.qa-gate.log` (with `### Audit log` sub-heading) and `.qa-gate-low-findings.md` (with `### LOW findings` sub-heading) into `retro.md` under `## Pre-release QA notes`, then delete each consumed sidecar  
**Edge cases:** either sidecar may be absent independently; missing both is a no-op  
**Size constraint:** ~15 lines added

### C4: test-hooks anti-drift assertions

**Owner:** plugins/pd/hooks/tests/test-hooks.sh  
**Responsibility:** prevent silent removal of Step 5b dispatch via 3 new test functions:
- `test_finish_feature_step_5b_present` — **10 grep assertions** (8 per AC-14 + 2 added per design-reviewer iter 1: the "dispatch all 4 reviewers in parallel" literal phrase per AC-3, and the AC-15 fallback string `no spec.md found — review for general defects`)
- `test_finish_feature_under_600_lines` — file size constraint per AC-18
- `test_qa_gate_procedure_doc_exists` — procedure doc exists with FR markers per AC-18 + suggestion 1
**Size constraint:** ~35 lines added (10 greps × ~3 lines each + 2 helper tests)

### C5: Runtime-generated sidecars

**Owner:** Step 5b prose (Claude generates at runtime via Bash) for `.qa-gate.json`, `.qa-gate.log`, `.qa-gate-low-findings.md`. **Gate-initiated, user-completed** for `qa-override.md` (gate writes frontmatter + scaffolding on first HIGH-block; user fills rationale; gate appends new H2 section on subsequent blocks).  
**Responsibility:** persist gate state (`.qa-gate.json`), audit/telemetry (`.qa-gate.log`), LOW findings (`.qa-gate-low-findings.md`), and HIGH-block scaffolding (`qa-override.md`)  
**Lifecycle:** `.qa-gate.json` survives across runs (cache); `.qa-gate.log` and `.qa-gate-low-findings.md` are consumed and deleted by C3 during retro; `qa-override.md` persists across feature lifetime as audit trail (committed to git).

## Interfaces

### I-1: `.qa-gate.json` schema

```json
{
  "head_sha": "abcdef0123456789...",
  "gate_passed_at": "2026-04-29T03:14:00Z",
  "summary": {
    "high": 0,
    "med": 2,
    "low": 5
  }
}
```

**Constraints:**
- `head_sha`: 40-char lowercase hex (matches `^[0-9a-f]{40}$`)
- `gate_passed_at`: ISO-8601 Z timestamp (matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`)
- `summary`: integers ≥ 0
- File only exists after a PASS run

### I-2: `.qa-gate.log` line formats

**Skip event** (per AC-7):
```
skip: HEAD abcdef0123456789... at 2026-04-29T03:14:00Z
```
Pattern: `^skip: HEAD [0-9a-f]{40} at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`

**Per-reviewer count** (per AC-17):
```
count: [pd:security-reviewer]: HIGH=0 MED=2 LOW=1
```
Pattern: `^count: \[(pd:[a-z-]+)\]: HIGH=\d+ MED=\d+ LOW=\d+$`

Append-only. One line per event; multiple counts per dispatch (one per reviewer).

### I-3: `.qa-gate-low-findings.md` format

```markdown
### LOW: {short title}
- Reviewer: {agent-name}
- Location: {file:line}
- Description: {description}
- Suggested fix: {suggestion}

### LOW: ...
```

Append-only sections; consumed and deleted by retrospecting skill.

### I-4: `qa-override.md` format

**First override:**
```markdown
---
gate_run_at: 2026-04-29T03:14:00Z
findings:
  - reviewer: pd:security-reviewer
    severity: HIGH
    location: plugins/pd/hooks/lib/foo.py:42
    description: SQL LIMIT accepts negative values
---

## Override 1 (2026-04-29)

<!-- User: write your rationale here (≥50 chars). Why is this finding a false positive or acceptable risk? -->
This is a test-only path; SQL is parameterized and the negative value is validated upstream by ...
```

**Nth override** (file already exists, gate fires on a different finding):
```markdown
[... existing frontmatter + Override 1..N-1 sections preserved ...]

## Override N (date)

Findings this run:
- reviewer: pd:code-quality-reviewer, severity: HIGH, location: ..., description: ...

<!-- User: write your rationale here (≥50 chars). -->
{user-written rationale}
```

**Bypass check pseudocode (per-section per TD-3):**
```bash
[[ -f qa-override.md ]] || exit_block
last_n=$(grep -oE '^## Override [0-9]+' qa-override.md | grep -oE '[0-9]+' | sort -n | tail -1)
trimmed=$(awk "/^## Override ${last_n} /,0" qa-override.md \
  | sed -e '/^---$/,/^---$/d' \
        -e "/^## Override ${last_n} /d" \
        -e '/^<!-- User: write your rationale here/d' \
        -e '/^Findings this run:/d' \
        -e '/^- reviewer:/d' \
  | wc -c)
[[ "$trimmed" -ge 50 ]]
```

### I-5: Reviewer dispatch prompt template

For each of the 4 reviewers, the dispatch prompt (in C1 referencing C2 detail) includes:

```
## Required Context
- Feature: {id}-{slug}
- Spec: {feature_path}/spec.md  [OR fallback: "no spec.md found — review for general defects against the diff; do not synthesize requirements"]
- Diff: {output of `git diff {pd_base_branch}...HEAD`}

## Severity Rubric
- HIGH: severity == "blocker" OR securitySeverity in {"critical", "high"}
- MED:  severity == "warning"  OR securitySeverity == "medium"
- LOW:  severity == "suggestion" OR securitySeverity == "low"

## Iteration Context
This is a pre-release gate (Step 5b). You are reviewing the full feature diff before merge.

## Output
Return JSON in a ```json fenced block matching the schema for your reviewer role:
{schema-per-reviewer-from-FR-2-table}
```

For `pd:test-deepener`, the prompt additionally states: "Run **Step A** (Outline Generation) ONLY. Do NOT write tests. Output gaps with `mutation_caught` boolean."

### I-6: Severity bucket logic — two-phase

**Phase 1 — Collection:** After all 4 reviewers respond, parse each per FR-10 and collect `(reviewer, severity, securitySeverity, location, description, suggestion, mutation_caught)` tuples into a single list `all_findings`. Normalize each `location` field via `normalize_location()` defined below before insertion.

**Phase 2 — Bucketing:** For each finding, run `bucket(finding, all_findings)`:

```python
def bucket(finding, all_findings):
    sev = finding.get("severity")
    sec_sev = finding.get("securitySeverity")
    high = sev == "blocker" or sec_sev in {"critical", "high"}
    med = sev == "warning" or sec_sev == "medium"
    low = sev == "suggestion" or sec_sev == "low"

    # AC-5b narrowed remap for test-deepener
    if finding["reviewer"] == "pd:test-deepener" and high:
        mutation_caught = finding.get("mutation_caught", True)
        cross_confirmed = any(
            other["location"] == finding["location"]
            and other["reviewer"] != "pd:test-deepener"
            for other in all_findings
        )
        if not mutation_caught and not cross_confirmed:
            return "MED"  # coverage-debt only

    if high: return "HIGH"
    if med:  return "MED"
    if low:  return "LOW"
    return "MED"  # default for missing severity field
```

**`normalize_location(loc: str) -> str`:**
- Extract `{filename_basename}:{line_number}` if `loc` matches `[^/\s]+\.[a-z]+:\d+` (basename + line).
- Match anywhere in the string (not anchored), e.g. `"plugins/pd/hooks/lib/foo.py:42"` → `"foo.py:42"`.
- If no match, return `loc.strip().lower()` as a coarse fallback.
- Document this rule in C2 (procedure doc) so reviewer prompts can request `file:line` format from agents that emit free-form locations.

**Reviewer prompt addendum (in I-5):** All 4 reviewer dispatch prompts MUST include:
> Output `location` as `file:line` (e.g., `database.py:1055`) when the issue maps to a specific source line. For non-line issues (e.g., architecture-level), use `file` only.

This makes cross-confirmation viable across reviewer output schemas.

## Risks

- **R-1 [HIGH]** — Override normalization in YOLO + single-developer (pre-mortem + antifragility advisors). **Partially mitigated by:** TD-3 (per-section trimmed-count forces ≥50 fresh chars per HIGH-block — Override 1's rationale does NOT satisfy Override 2). FR-11 (YOLO HIGH always exits non-zero, no AskUserQuestion). **Audit observability (not mitigation):** git history records all override invocations; `.qa-gate.log` records skips. **Honest residual:** if the user writes "lgtm shipping it false positive 50 chars" each time, gate degrades to advisory. **Forcing function (added per design-reviewer warning 12):** if 3 consecutive `## Override` sections appear in the same `qa-override.md`, gate emits warning to retro escalating for review. Implementation: gate counts `^## Override [0-9]+` headings; if ≥3, append `## Override-Storm Warning` H2 to retro.md flagging the feature for human escalation. Structural backstop deferred to Open Question 1 (consensus weighting after 3 features ship through gate).
- **R-2 [MED]** — Idempotency cache silent-skip after force-push (pre-mortem advisor). **Mitigated by:** SHA-mismatch always invalidates cache (FR-8 step 3); skip event always logged to `.qa-gate.log` (AC-7); retrospecting skill folds the audit log into retro for visibility. Corrupted-cache (invalid JSON) handled by treating as cache-miss (TD-5 corruption clause below).
- **R-3 [MED]** — test-deepener output shape ambiguity (first-principles + pre-mortem). **Mitigated by:** AC-5b narrowed remap with two-phase ordering (I-6); FR-10 schema validation via python3 heredoc (TD-8); FR-4 explicit Step A invocation prompt; location-normalization rule (I-6) enables cross-confirmation across heterogeneous reviewer schemas.
- **R-4 [MED]** — Cross-feature interaction bugs invisible to diff-scoped reviewers (first-principles). **Not mitigated by this feature.** Documented as out-of-scope; would require a post-merge gate or full-codebase pass. Filed as future-consideration.
- **R-5 [MED]** — Large-diff degradation (antifragility). **Mitigated by:** NFR-1 size warning; gate proceeds, does not auto-skip.
- **R-6 [LOW]** — Spec-absent feature path (antifragility). **Mitigated by:** AC-15 fallback prompt string; design spec-absent features to use the literal fallback text.
- **R-7 [MED]** — Context-window saturation on very large diffs (pre-mortem advisor — surfaced in design-reviewer iter 1). At >2000 LOC, the diff text alone could exceed reviewer context budget when sent to 4 agents in parallel. **Mitigated by:** documented per-reviewer budget hint in C2 (procedure doc): if `git diff {pd_base_branch}...HEAD | wc -l` > 2000, the dispatch prompt includes a file-list summary instead of full diff, and instructs each reviewer to request specific files via clarification rather than reviewing all in one pass. Wall-clock budget widened to 10 min above this threshold (design-level extension of spec NFR-1; spec amendment not required since the warning-but-proceed behavior is preserved). **C2 obligation:** procedure doc MUST document the >2000 LOC threshold + file-list-summary fallback explicitly; without it this risk stays unmitigated.

## Out of Scope

Same as PRD + spec — no expansion. Notable items deferred:
- Consensus weighting (≥2 of 4 must agree on HIGH) — Open Question 1
- Reviewer feedback loop (gate findings → KB) — Open Question 3
- AC-12 post-merge retirement — Open Question 2
- Cross-feature interaction-bug detection — R-4

## Implementation Order

Direct-orchestrator pattern fits (per 091/092/093 surgical template). All edits land in one atomic commit:

1. Edit `plugins/pd/commands/finish-feature.md` lines 373/374: insert Step 5b heading + dispatch table + severity rubric + decision tree + reference link (C1).
2. Create `docs/dev_guides/qa-gate-procedure.md` with FR-3..FR-11 procedural detail (C2).
3. Edit `plugins/pd/skills/retrospecting/SKILL.md`: add sidecar fold step (C3).
4. Edit `plugins/pd/hooks/tests/test-hooks.sh`: add 3 new test functions and register them (C4).
5. Quality gates: `validate.sh`, `test-hooks.sh` (with the 3 new tests passing), spec ACs binary verified.
6. **Dogfood self-test (DoD), two-phase:**
   - **(a) Self-dispatch:** Run `/pd:finish-feature` on feature 094's own branch — confirm gate dispatches all 4 reviewers against the prose diff, completes, and writes `.qa-gate.json` if no HIGHs found.
   - **(b) Synthetic-HIGH injection:** In a scratch sub-branch, inject a HIGH-equivalent (e.g., add `LIMIT -1` unbounded SQL query or `subprocess.Popen(shell=True, ...)` with f-string) into a Python file. Run gate; confirm at least one reviewer flags HIGH and gate exits non-zero. Discard the scratch branch.
   - **(c) Cleanup:** Remove synthetic injection if any leaked back to the feature branch.

All in one commit (~80 prod prose + ~35 test LOC + new ~180-line doc). Followed by post-merge adversarial QA per the new gate itself (eat-own-dog-food validation).

## Test Strategy

| AC | How tested |
|----|------------|
| AC-1 (Step 5b heading) | `test_finish_feature_step_5b_present` grep |
| AC-2..AC-5 (4 names + parallel + Step A + severity predicates) | Same test, 8 distinct greps |
| AC-5b (test-deepener narrowed remap) | Manual review of severity-bucket prose; not auto-grep-able (semantic) — captured as `## Manual Verification` checklist in retro |
| AC-6 (`.qa-gate.json` schema) | Regex assertions on schema fields (per I-1 patterns) — manual at first dogfood run |
| AC-7 (skip pattern) | Regex `^skip: HEAD [0-9a-f]{40} at ...$` — manual at first dogfood run |
| AC-8 (qa-override trimmed-count) | Manual: create file with empty rationale, verify gate still blocks; add 50+ chars, verify bypass |
| AC-9 (override-N counting) | Manual: trigger 2 separate override events, verify Override 1 + Override 2 sections both present |
| AC-10 (incomplete-run) | Manual: simulate reviewer error, verify gate exits non-zero |
| AC-11 (YOLO surfacing) | Manual: trigger HIGH in YOLO, verify no AskUserQuestion + non-zero exit |
| AC-12 (`.qa-gate-low-findings.md` path) | `test_finish_feature_step_5b_present` grep |
| AC-13 (retrospecting fold) | Manual: place sidecar, run /pd:retrospect, verify retro.md gains section |
| AC-14 (8 distinct greps) | `test_finish_feature_step_5b_present` itself (recursive — the test verifies its own AC) |
| AC-15 (fallback prompt string) | `test_finish_feature_step_5b_present` grep (10th assertion per C4) |
| AC-16 (diff range token) | Source-file grep for literal `{pd_base_branch}...HEAD` |
| AC-17 (per-reviewer count pattern) | Regex `^count: \[(pd:[a-z-]+)\]: HIGH=\d+ MED=\d+ LOW=\d+$` — manual |
| AC-18 (file <600 + procedure exists) | `test_finish_feature_under_600_lines` + `test_qa_gate_procedure_doc_exists` |
| AC-19 (backlog ID extraction) | Manual: trigger MED, verify new entry with correct max+1 ID |
| AC-20 (no new deps) | `validate.sh` passes; no new pip/brew/npm files added |

**Manual Verification Gate** (per AC-5b/8/9/10/11/13/17/19): a `## Manual Verification` checklist appended to retro.md after dogfood self-test. Responsible party: feature implementer. Environment: develop branch, current shell. Each item ticked off with the specific command run + observation.

## Review History

### Iteration 1 — design-reviewer (opus, 2026-04-29)

**Findings:** 5 blockers + 7 warnings + 3 suggestions

**Corrections applied:**
- TD-3 — switched `qa-override.md` bypass check from file-level trimmed-count to **per-section** (latest `## Override N` to EOF) trimmed-count. Override 1's rationale no longer satisfies Override 2. Reason: Blocker 3.
- I-6 — restructured to two-phase (Phase 1 collect, Phase 2 bucket); added `normalize_location()` rule for cross-confirmation across heterogeneous reviewer schemas; added I-5 prompt addendum requiring `file:line` location format. Reason: Blockers 1 + 2.
- TD-8 — concretized JSON parse mechanism as inline `python3 -c` heredoc with stdlib only; removed ambiguity about who runs json.loads. Reason: Blocker 4.
- TD-7 — added per-feature sectioning (`## From Feature {feature_id} Pre-Release QA Findings (date)`) per existing 091/092/093 backlog convention; added regex-coverage verification step. Reason: Blocker 5 + warning 10.
- R-7 NEW — added context-window saturation risk (>2000 LOC) with file-list-summary mitigation in C2; widened NFR-1 wall-clock budget. Reason: Warning 6.
- C5 — clarified ownership of `qa-override.md` as gate-initiated/user-completed; updated Architecture diagram annotation. Reason: Warning 7.
- TD-5 — added corrupted-cache handling (treat as cache-miss, log warning); explicit Step 5a→5b ordering dependency. Reason: Warning 8 + suggestion 13.
- C4 — extended `test_finish_feature_step_5b_present` from 8 to 10 grep assertions (added AC-3 literal phrase + AC-15 fallback string). Reason: Warning 9 + suggestion 15.
- R-1 — restructured: explicitly downgraded to "partially mitigated"; added override-storm forcing function (3+ overrides emits warning to retro for human escalation); kept honest residual statement. Reason: Warning 12.
- Implementation Order step 6 — split into two-phase dogfood: (a) self-dispatch on own branch, (b) synthetic-HIGH injection in scratch branch, (c) cleanup. Reason: Warning 11.
- Sidecar consolidation — declined; kept 3 sidecars per TD-2 (different lifecycles justify separate files). Suggestion 14 acknowledged but not adopted.

### Iteration 1 — phase-reviewer (sonnet, 2026-04-29)

**Findings:** approved=true with 1 warning + 2 suggestions

**Corrections applied:**
- I-4 — replaced bypass-check pseudocode with the per-section awk pipeline from TD-3 (was inadvertently file-level, contradicting TD-3 and silently defeating override-friction goal). Reason: Warning 1.
- Test Strategy table AC-15 row — changed to unambiguous "test_finish_feature_step_5b_present grep (10th assertion per C4)". Reason: Suggestion 1.
- R-7 — added explicit C2 obligation language ("procedure doc MUST document the >2000 LOC threshold... without it this risk stays unmitigated"). Reason: Suggestion 2.

## Manual Verification Gate

**Responsible party:** feature 094 implementer  
**Environment:** macOS dev shell on `feature/094-pre-release-qa-gate` branch, after all edits committed  
**Procedure:** for each manual-only AC above, run the listed observation command and capture the output to retro.md "Manual Verification" section before merge.

```markdown
## Manual Verification

### AC-5b — test-deepener narrowed remap semantic check
- [ ] Reviewed bucket() pseudocode at design.md I-6 → semantically aligns with AC-5b "mutation_caught == false AND no cross-confirm"
- [ ] Procedure doc Section "FR-5" contains the literal narrowing rule

### AC-8 — qa-override trimmed-count
- [ ] Created qa-override.md with frontmatter only (no user prose) → gate blocks (trimmed-count < 50)
- [ ] Added 50+ chars rationale → gate bypasses

### AC-9 — Override-N counting
- [ ] Triggered Override 1, then triggered different finding → Override 2 section appended without modifying frontmatter

### AC-10 — Incomplete-run policy
- [ ] Simulated 1-of-4 reviewer error (e.g., bogus subagent_type) → gate exits non-zero with INCOMPLETE message

### AC-11 — YOLO surfacing
- [ ] Triggered HIGH in YOLO → stdout findings + non-zero exit; no AskUserQuestion

### AC-13 — retrospecting fold
- [ ] Placed test sidecar files → ran /pd:retrospect → retro.md gained "Pre-release QA notes" section + sub-headings; sidecars deleted

### AC-17 — per-reviewer count pattern
- [ ] Ran clean dispatch → .qa-gate.log contains 4 lines matching `^count: \[pd:.*\]: HIGH=\d+ MED=\d+ LOW=\d+$`

### AC-19 — backlog ID extraction
- [ ] Triggered 2 MEDs → both filed at max+1 and max+2 of pre-existing IDs; descriptions correct
```
