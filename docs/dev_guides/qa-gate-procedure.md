# Pre-Release Adversarial QA Gate — Procedure Reference

> **Source:** Feature 094 (`docs/features/094-pre-release-qa-gate/`). This file contains procedural detail for **Step 5b** in `plugins/pd/commands/finish-feature.md`. The command file keeps only the dispatch shape, severity rubric, and decision tree inline; everything else lives here.
>
> **When you read this:** when running `/pd:finish-feature` Step 5b, follow this document for full dispatch prompts, JSON parse contract, severity bucketing, override mechanics, and edge cases.

## §1 — Dispatch prompt template (FR-3, I-5)

For each of the 4 reviewers, construct the dispatch prompt with the following structure.

### Common context block (all 4 reviewers)

```
## Required Context
- Feature: {feature_id}-{slug}
- Spec: {feature_path}/spec.md
  [If spec.md does NOT exist, replace the path with the literal fallback: "no spec.md found — review for general defects against the diff; do not synthesize requirements"]
- Diff (from develop merge-base to HEAD):
{output of `git diff {pd_base_branch}...HEAD`}

## Severity Rubric
- HIGH: severity == "blocker" OR securitySeverity in {"critical", "high"}
- MED:  severity == "warning"  OR securitySeverity == "medium"
- LOW:  severity == "suggestion" OR securitySeverity == "low"

## Output Location Format
Output `location` as `file:line` (e.g., `database.py:1055`) when the issue maps to a specific source line. For non-line issues (e.g., architecture-level), use `file` only. This format enables cross-confirmation across the 4 reviewer outputs.

## Iteration Context
This is a pre-release gate (Step 5b). You are reviewing the full feature diff before merge. Do NOT modify any files; return findings only.
```

### Per-reviewer output instruction

Each reviewer gets the common context block plus a role-specific output instruction:

- `pd:security-reviewer`: "Return JSON in a ```json fenced block matching `{approved, issues[{severity, securitySeverity, category, location, description, suggestion}], summary}`."
- `pd:code-quality-reviewer`: "Return JSON in a ```json fenced block matching `{approved, issues[{severity, location, description, suggestion}], summary}`."
- `pd:implementation-reviewer`: "Return JSON in a ```json fenced block matching `{approved, issues[{severity, level, category, description, location, suggestion}], summary}`."
- `pd:test-deepener`: see §2 below for Step A invocation.

### Large-diff fallback (R-7)

If `git diff {pd_base_branch}...HEAD | wc -l` > 2000, replace the inline diff with a file-list summary:

```
Diff is large ({N} lines). File list:
{output of `git diff --stat {pd_base_branch}...HEAD`}

Request specific files via your output's `clarification_needed` field if you need full content.
```

Wall-clock budget extends to 10 min for this path (vs the standard 5 min for ≤500 LOC).

## §2 — test-deepener Step A invocation (FR-4)

The dispatch prompt to `pd:test-deepener` MUST open with:

```
**Run Step A (Outline Generation) ONLY. Do NOT write tests.**

Refer to `plugins/pd/agents/test-deepener.md` Step A for the outline format. Output JSON in a ```json fenced block matching `{gaps[{severity, mutation_caught, location, description, suggested_test}], summary}`.

For each gap, the `mutation_caught` field MUST be a boolean indicating whether the existing test suite catches a mutation in the location described. This drives the AC-5b narrowed-remap predicate (see §4).
```

## §3 — JSON parse contract (FR-10, TD-8)

Each reviewer's raw output is piped through this Bash + Python heredoc. Schema validation per role; failure → INCOMPLETE block.

```bash
python3 -c '
import sys, json, re
text = sys.stdin.read()
# Primary: fenced ```json block
m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
if m:
    payload = m.group(1)
else:
    # Fallback: first balanced {...}
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
required = {
    "pd:security-reviewer":      ["approved", "issues", "summary"],
    "pd:code-quality-reviewer":  ["approved", "issues", "summary"],
    "pd:implementation-reviewer":["approved", "issues", "summary"],
    "pd:test-deepener":          ["gaps", "summary"],
}
for f in required.get(role, []):
    if f not in obj:
        sys.exit(f"schema_missing: {f}")
print(json.dumps(obj))
' "$REVIEWER_ROLE" <<< "$REVIEWER_OUTPUT"
```

If `python3` exits non-zero, gate emits `INCOMPLETE: {reviewer} parse failure: {stderr}` and blocks merge per §9.

## §4 — Severity bucket two-phase (FR-5, AC-5b, I-6)

**Phase 1 — Collection:** After all 4 reviewers respond and pass §3, collect all findings into a single list `all_findings`. Each entry: `{reviewer, severity, securitySeverity, location, description, suggestion, mutation_caught}`. Run `normalize_location()` on each `location` before insertion.

**Phase 2 — Bucketing:** For each finding, run:

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

**`normalize_location(loc)`:** extract `{filename_basename}:{line_number}` if `loc` matches `[^/\s]+\.[a-z]+:\d+` anywhere in string (e.g., `plugins/pd/hooks/lib/foo.py:42` → `foo.py:42`). Else return `loc.strip().lower()`. Reviewer prompts (per §1) require `file:line` format, making cross-confirmation viable.

## §5 — MED auto-file to backlog (FR-7a, AC-19, TD-7)

### Per-feature section heading

```markdown
## From Feature {feature_id} Pre-Release QA Findings ({date})
```

### ID extraction algorithm

```bash
# Find max existing 5-digit ID anchored to start-of-list-line
max_id=$(grep -oE '^- \*\*#[0-9]{5}\*\*' docs/backlog.md | grep -oE '[0-9]{5}' | sort -n | tail -1)
next_id=$(printf '%05d' $((10#$max_id + 1)))
```

For batch MED filing in one run: reserve IDs sequentially (`next_id`, `next_id+1`, ...) in the order the gate processes findings.

### Insertion algorithm

1. Search `docs/backlog.md` for `^## From Feature {feature_id} Pre-Release QA`.
2. If found: append entries inside that section (after the heading, before next `## ` heading).
3. If not found: insert new section heading + entries immediately before the first existing `## ` heading (places near top, inverse-chronological per existing convention).

### Entry template

```markdown
- **#{NNNNN}** [{MED|MED-quality|MED-security}] {description}. (surfaced by feature:{feature_id} pre-release QA)
```

## §6 — LOW auto-file to sidecar (FR-7a)

Append to `docs/features/{id}-{slug}/.qa-gate-low-findings.md` (create if absent):

```markdown
### LOW: {short title}
- Reviewer: {agent-name}
- Location: {file:line}
- Description: {description}
- Suggested fix: {suggestion}
```

Append-only sections; consumed and deleted by `pd:retrospecting` skill (Step 2c).

## §7 — Idempotency cache (FR-8, TD-5)

### `.qa-gate.json` schema

```json
{
  "head_sha": "abcdef0123456789...",
  "gate_passed_at": "2026-04-29T03:14:00Z",
  "summary": {"high": 0, "med": 2, "low": 5}
}
```

### Logic

1. Compute current HEAD SHA: `git rev-parse HEAD`.
2. If `.qa-gate.json` exists AND parses as JSON AND has all required fields AND `head_sha` matches current → SKIP dispatch, append `skip: HEAD {sha} at {iso}` line to `.qa-gate.log`, proceed to Step 5a-bis.
3. **Corruption handling:** if `.qa-gate.json` exists but does not parse as JSON OR is missing `head_sha`/`gate_passed_at`/`summary` → treat as cache-miss, re-dispatch, append `cache-corrupt: re-dispatching at HEAD {sha}` to `.qa-gate.log`.
4. Cache miss (HEAD differs OR file absent OR corrupt): dispatch reviewers. **Do NOT delete existing `.qa-gate.json` yet.** Only on PASS, atomically overwrite via temp file + `mv`:

```bash
python3 -c "import json,sys; print(json.dumps({'head_sha':'$HEAD','gate_passed_at':'$ISO','summary':{'high':$H,'med':$M,'low':$L}}))" > .qa-gate.json.tmp
mv .qa-gate.json.tmp .qa-gate.json
```

5. On INCOMPLETE or HIGH-block, leave previous cache untouched (re-run on a subsequent fix-commit will mismatch SHA and re-dispatch).

### Step 5a→5b ordering

Step 5b only writes `.qa-gate.json` after Step 5a (`validate.sh`) passes in the same `/pd:finish-feature` invocation. Cache represents "full pre-merge gate passed at this HEAD"; partial passes do not write cache. Step 5b reads cache regardless of 5a outcome (skip-if-match logic), but a stale cache from a prior 5a-passing run stays valid until HEAD changes.

## §8 — Override path (FR-9, TD-3)

### First-override file format

When the gate first emits HIGH-block on a feature, it creates `docs/features/{id}-{slug}/qa-override.md` with:

```markdown
---
gate_run_at: 2026-04-29T03:14:00Z
findings:
  - reviewer: pd:security-reviewer
    severity: HIGH
    location: database.py:42
    description: SQL LIMIT accepts negative values
---

## Override 1 (2026-04-29)

<!-- User: write your rationale here (≥50 chars). Why is this finding a false positive or acceptable risk? -->
```

User fills the rationale below the comment placeholder, then re-runs `/pd:finish-feature`.

### Nth-override append (N ≥ 2)

If the file already exists and the gate fires on a different HIGH:

1. **Do NOT modify the top-level frontmatter** (preserves first-invocation record).
2. Compute N: `(max integer found in existing headings matching ^## Override (\d+)) + 1`; if none found, N = 1.
3. Append a new H2 section:

```markdown

## Override {N} (2026-04-29)

Findings this run:
- reviewer: pd:code-quality-reviewer, severity: HIGH, location: foo.py:99, description: ...

<!-- User: write your rationale here (≥50 chars). -->
```

User fills rationale; re-run gate.

### Per-section bypass check (TD-3)

The bypass measures the **latest** Override section's user-authored content only — Override 1's rationale does NOT satisfy Override 2.

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

`awk '/pattern/,0'` extracts pattern-to-EOF (BSD + GNU portable).

## §9 — Incomplete-run policy (FR-10)

If any of 4 reviewers fails the §3 JSON parse + schema contract:

- Treat as INCOMPLETE — never silent-pass.
- Print: `QA gate INCOMPLETE: {n} of 4 reviewers failed: [{reviewer}: {reason}, ...]. Re-run or override via qa-override.md.`
- Exit non-zero (block merge).

The "block on partial" posture is critical — silent-pass on 3-of-4 coverage is worse than the post-release status quo.

## §10 — YOLO surfacing (FR-11)

In YOLO mode (`yolo_mode: true` in `.claude/pd.local.md`):

- **HIGH findings:** gate prints findings to stdout and exits the `finish-feature` command with non-zero status. Does NOT invoke `AskUserQuestion` (preserves YOLO non-interactive contract). User discovers the block via the failed `finish-feature` artifact / next CLI session.
- **MED findings:** auto-file to backlog without prompt (per §5).
- **LOW findings:** auto-file to sidecar without prompt (per §6).

This is the **one explicit YOLO exception** in `finish-feature.md` — pre-mortem advisor identified YOLO HIGH-override as the dominant gate-collapse failure mode.

## §11 — Large-diff fallback (R-7)

When `git diff {pd_base_branch}...HEAD | wc -l` > 2000:

1. Use file-list-summary instead of full diff in dispatch prompts (per §1).
2. Each reviewer prompt includes: "If you need full file content for a specific file, indicate via `clarification_needed` field in your output."
3. Wall-clock budget widens from 5 min (≤500 LOC) to 10 min (>2000 LOC) — design-level extension of spec NFR-1.
4. Optionally, for diffs >5000 LOC, gate emits warning to retro: `large-diff: coverage confidence reduced (LOC=N)`.

This mitigation is **mandatory** — without it, R-7 (context-window saturation) stays unmitigated.

## §12 — Override-storm warning (R-1)

After every gate run, count `^## Override [0-9]+` headings in `qa-override.md` (if exists). If count ≥ 3:

1. Append `## Override-Storm Warning ({date})` H2 section to `retro.md` (create section if absent under `## Pre-release QA notes`).
2. Content: `Feature {id} has {N} override sections in qa-override.md — gate is being overridden repeatedly. Escalate for human review of override discipline before next release.`

This is the structural forcing function for R-1 (override normalization). If the user routinely writes "lgtm 50 chars" rationales, the storm-warning surfaces the pattern in retro for self-review. Structural backstop deferred to Open Question 1 (consensus weighting after 3 features ship).

---

## References

- **PRD:** `docs/features/094-pre-release-qa-gate/prd.md` (Source: Backlog #00217)
- **Spec:** `docs/features/094-pre-release-qa-gate/spec.md` (21 ACs, 12 FRs)
- **Design:** `docs/features/094-pre-release-qa-gate/design.md` (7 TDs, 5 components, 6 interfaces, 7 risks)
- **Plan:** `docs/features/094-pre-release-qa-gate/plan.md` (T0..T6 implementation order + AC Coverage Matrix)
