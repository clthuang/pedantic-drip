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
docs/features/{id}/qa-override.md (USER-WRITTEN) ┘     (last is user-written)
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

### TD-3: Trimmed byte-count for `qa-override.md` rationale

**Decision:** Bypass check uses `sed -e '/^---$/,/^---$/d' -e '/^<!-- User: write your rationale here/d' qa-override.md | wc -c` ≥ 50. The user must write ≥50 bytes of *new* content; the gate-written frontmatter + comment placeholder do not count.

**Alternatives rejected:**
- *Raw `wc -c < qa-override.md` ≥ 50.* The gate-written frontmatter alone exceeds 50 bytes (~150-200 chars typical). User could create the file with empty rationale and bypass succeed.
- *Require the user to delete the comment placeholder.* Too easy to miss; comment placeholder is a UX hint, not a flag.
- *Require ≥50 chars in a specific named section.* More structural complexity for marginal benefit.

**Rationale:** Forces the user to actually articulate rationale. Pre-mortem advisor flagged "override normalization" as the dominant gate-collapse failure mode for single-developer YOLO. Making the override path painful is the antidote. The sed pipeline is portable across macOS/Linux.

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

### TD-6: Parallel dispatch via single Claude message (not sequential or async)

**Decision:** Step 5b prose instructs Claude to dispatch all 4 reviewers in **one message** with 4 `Task` tool calls. Claude (the orchestrator) waits for all 4 responses before evaluating severity buckets.

**Alternatives rejected:**
- *Sequential dispatch* (1 reviewer at a time). Wall-clock is 4× slower (~4 min instead of ~60-90s). Defeats <5-min NFR-1.
- *Background dispatch with later collection.* Claude's harness supports background agents but the gate logic needs all results before deciding. Background adds polling complexity for no latency win in this case.

**Rationale:** All 4 reviewers fit in `max_concurrent_agents: 5`. Wall-clock matches industry parallel-LLM-reviewer norms (~60-90s). Single-message dispatch is the canonical pattern from CLAUDE.md "If you intend to call multiple tools and there are no dependencies between them, make all independent tool calls in parallel."

### TD-7: Backlog ID extraction — file-scan regex with sequential reservation

**Decision:** Algorithm:
1. `grep -oE '^- \*\*#[0-9]{5}\*\*' docs/backlog.md | grep -oE '[0-9]{5}' | sort -n | tail -1` to find max ID.
2. `next_id = max + 1` (zero-padded to 5 digits via `printf '%05d'`).
3. For batch MED filing in one run: reserve IDs sequentially `next_id, next_id+1, ...` in the order the gate processes findings (deterministic).
4. Append (not insert) to backlog.md to preserve chronological sectioning.

**Alternatives rejected:**
- *Naive `grep -E '#\d{5}'`.* Over-counts: cross-references like `(see #00193)` inside finding descriptions would inflate the max.
- *Track next-id in a separate state file.* Adds another sidecar; no benefit over scanning the source-of-truth.

**Rationale:** Anchored regex `^- \*\*#(\d{5})\*\*` matches only top-of-list entries (the canonical entry start). Cross-references inside descriptions (which never start a list item) are excluded by the `^- ` anchor. Deterministic sequential reservation makes multi-MED runs reproducible.

### TD-8: JSON parse with fenced-block extraction + balanced-brace fallback + schema validation

**Decision:** Per-reviewer JSON parse contract (FR-10):
1. **Primary:** extract first ```` ```json ... ``` ```` fenced block.
2. **Fallback:** scan for first balanced `{ ... }` block, parse with `json.loads`.
3. **Validate:** check required fields per FR-2 table for each reviewer.
4. **INCOMPLETE iff** all three fail OR schema validation fails.

**Alternatives rejected:**
- *Strict JSON-only (require fenced block).* Reviewers often respond with prose preamble + JSON; rejecting this is overly punitive. Reviewers would have to be re-prompted, doubling wall-clock.
- *Lenient text-extraction with regex.* Brittle; can't validate schema; risks accepting malformed responses.

**Rationale:** Two-step extraction handles both well-behaved (fenced) and prose-mixed responses. Schema validation catches truncated or wrong-shaped responses (e.g., test-deepener returning `gaps:[]` instead of `issues:[]`). INCOMPLETE on schema failure is the correct posture per FR-10.

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
- `test_finish_feature_step_5b_present` — 8 grep assertions per AC-14
- `test_finish_feature_under_600_lines` — file size constraint per AC-18
- `test_qa_gate_procedure_doc_exists` — procedure doc exists with FR markers per AC-18 + suggestion 1
**Size constraint:** ~30 lines added

### C5: Runtime-generated sidecars

**Owner:** Step 5b prose (Claude generates at runtime via Bash)  
**Responsibility:** persist gate state (`.qa-gate.json`), audit/telemetry (`.qa-gate.log`), and LOW findings (`.qa-gate-low-findings.md`) per the schemas in interface section below  
**Lifecycle:** `.qa-gate.json` survives across runs (cache); `.qa-gate.log` and `.qa-gate-low-findings.md` are consumed and deleted by C3 during retro

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

**Bypass check pseudocode:**
```bash
trimmed_count=$(sed -e '/^---$/,/^---$/d' -e '/^<!-- User: write your rationale here/d' qa-override.md | wc -c)
[[ -f qa-override.md && "$trimmed_count" -ge 50 ]]
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

### I-6: Severity bucket logic (pseudocode)

```python
def bucket(reviewer_name, finding):
    sev = finding.get("severity")
    sec_sev = finding.get("securitySeverity")
    high = sev == "blocker" or sec_sev in {"critical", "high"}
    med = sev == "warning" or sec_sev == "medium"
    low = sev == "suggestion" or sec_sev == "low"

    # AC-5b narrowed remap for test-deepener
    if reviewer_name == "pd:test-deepener" and high:
        if not finding.get("mutation_caught", True) and not _cross_confirmed(finding["location"]):
            return "MED"  # coverage-debt only

    if high: return "HIGH"
    if med:  return "MED"
    if low:  return "LOW"
    return "MED"  # default for missing severity field

def _cross_confirmed(location):
    return any(other_finding.location == location
               for other_finding in findings_by_reviewer
               if other_finding.reviewer != "pd:test-deepener")
```

## Risks

- **R-1 [HIGH]** — Override normalization in YOLO + single-developer (pre-mortem + antifragility advisors). **Mitigated by:** TD-3 (trimmed-count requires ≥50 user-authored chars); FR-11 (YOLO HIGH always exits non-zero, no AskUserQuestion); git-history audit log of all overrides. **Residual:** if user writes "lgtm, false positive, ship it" 50+ times, gate degrades. Open Question 1 revisit trigger (false-block rate >15%) is the structural backstop.
- **R-2 [MED]** — Idempotency cache silent-skip after force-push (pre-mortem advisor). **Mitigated by:** SHA-mismatch always invalidates cache (FR-8 step 3); skip event always logged to `.qa-gate.log` (AC-7); retrospecting skill folds the audit log into retro for visibility.
- **R-3 [MED]** — test-deepener output shape ambiguity (first-principles + pre-mortem). **Mitigated by:** AC-5b narrowed remap; FR-10 schema validation rejects mis-shaped output; FR-4 explicit Step A invocation prompt.
- **R-4 [MED]** — Cross-feature interaction bugs invisible to diff-scoped reviewers (first-principles). **Not mitigated by this feature.** Documented as out-of-scope; would require a post-merge gate or full-codebase pass. Filed as future-consideration.
- **R-5 [LOW]** — Large-diff degradation (antifragility). **Mitigated by:** NFR-1 size warning; gate proceeds, does not auto-skip.
- **R-6 [LOW]** — Spec-absent feature path (antifragility). **Mitigated by:** AC-15 fallback prompt string; design spec-absent features to use the literal fallback text.

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
6. Dogfood self-test (DoD): inject synthetic HIGH into a sample file, run `/pd:finish-feature` self-dispatch, confirm at least one reviewer flags it; remove synthetic injection.

All in one commit (~80 prod prose + ~30 test LOC + new ~180-line doc). Followed by post-merge adversarial QA per the new gate itself (eat-own-dog-food validation).

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
| AC-15 (fallback prompt string) | `test_finish_feature_step_5b_present` could grep this; OR check via procedure doc |
| AC-16 (diff range token) | Source-file grep for literal `{pd_base_branch}...HEAD` |
| AC-17 (per-reviewer count pattern) | Regex `^count: \[(pd:[a-z-]+)\]: HIGH=\d+ MED=\d+ LOW=\d+$` — manual |
| AC-18 (file <600 + procedure exists) | `test_finish_feature_under_600_lines` + `test_qa_gate_procedure_doc_exists` |
| AC-19 (backlog ID extraction) | Manual: trigger MED, verify new entry with correct max+1 ID |
| AC-20 (no new deps) | `validate.sh` passes; no new pip/brew/npm files added |

**Manual Verification Gate** (per AC-5b/8/9/10/11/13/17/19): a `## Manual Verification` checklist appended to retro.md after dogfood self-test. Responsible party: feature implementer. Environment: develop branch, current shell. Each item ticked off with the specific command run + observation.

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
