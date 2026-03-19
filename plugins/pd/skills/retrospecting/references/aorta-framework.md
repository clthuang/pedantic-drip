# AORTA Framework

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

A retrospective framework designed for agentic coding workflows where every decision, review, and iteration is recorded in structured data.

Unlike traditional retrospective formats (4Ls, Start-Stop-Continue) that rely on participant feelings and memory, AORTA operates on logged evidence: phase timestamps, review iteration counts, reviewer feedback, and artifact metrics.

## Four Phases

### O — Observe (Quantitative)

**Purpose:** Extract hard numbers from the development record.

**Inputs:** `.meta.json` phase data

**What to extract:**
- Phase durations: `phases.{name}.started` → `phases.{name}.completed` timestamps
- Iteration counts: `phases.{name}.iterations` (number of review cycles before approval)
- Circuit breaker hits: any phase that reached max iterations
- Mode: Standard vs Full (affects which phases ran)
- Reviewer notes: `phases.{name}.reviewerNotes` (brief summaries from reviewers)

**Output:** Metrics table and quantitative summary.

### R — Review (Qualitative)

**Purpose:** Extract patterns from reviewer feedback text.

**Inputs:** `.review-history.md` content

**What to extract:**
- Issue categories: group feedback by type (testability, scope, assumptions, clarity, feasibility, security)
- Severity distribution: count blockers vs warnings vs suggestions
- Reviewer coverage: which reviewer agents flagged issues (spec-reviewer, design-reviewer, etc.)
- Resolution patterns: issues fixed on first attempt vs requiring multiple iterations

**Output:** Top 3 qualitative observations with evidence citations.

### T — Tune (Process Signals)

**Purpose:** Synthesize quantitative and qualitative data into process improvement signals.

**Signal patterns to look for:**

| Signal | Threshold | Recommendation Type |
|--------|-----------|-------------------|
| Phase iterations > 2 | 3+ iterations | Skill/prompt tuning |
| Same issue category across phases | 2+ phases | Hook rule or agent instruction update |
| Phase passed first try | 1 iteration | Pattern to reinforce |
| Large artifact + many iterations | 100+ lines, 3+ iterations | Scope or complexity issue |
| Circuit breaker hit | Max iterations reached | Fundamental approach problem |

**Output:** 3-5 actionable recommendations with signal, recommendation, and confidence level.

### A — Act (Knowledge Bank)

**Purpose:** Generate concrete entries for the project knowledge bank.

**Entry types:**

| Type | Target File | What to Capture |
|------|------------|----------------|
| Patterns | `{pd_artifacts_root}/knowledge-bank/patterns.md` | Approaches that worked well |
| Anti-patterns | `{pd_artifacts_root}/knowledge-bank/anti-patterns.md` | Approaches that caused problems |
| Heuristics | `{pd_artifacts_root}/knowledge-bank/heuristics.md` | Rules of thumb discovered |

**Entry format:**

```markdown
### {Type}: {Name}
{Description of the pattern/anti-pattern/heuristic}
- Observed in: Feature {id}-{slug}, {phase} phase
- Evidence: {specific data point or reviewer quote}
- Confidence: {high|medium|low}
```

**Provenance requirements:**
- Every entry must reference the feature ID and phase
- Every entry must cite specific evidence (metric, reviewer quote, or observable outcome)
- Only propose entries with medium or high confidence
- Prefer fewer high-quality entries over many speculative ones

## When Data Is Limited

| Missing Data | Impact | Mitigation |
|-------------|--------|------------|
| No `.meta.json` phase data | Observe phase produces no metrics | Note "insufficient data", focus on qualitative |
| No `.review-history.md` | Review phase has no input | Skip qualitative analysis, Tune uses metrics-only |
| No git data | Cannot calculate branch lifetime | Omit from raw data section |
| Partial phase data | Some phases have timing, others don't | Report what's available, note gaps |
