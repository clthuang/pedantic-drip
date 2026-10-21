# Design: Phase Transition Summary

## Prior Art Research

### Codebase Patterns
- **Existing inline summary**: `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` — emitted after review learnings in all 5 commands. Establishes the convention for non-interactive status output before the next prompt.
- **create-tasks Output precedent**: `"Tasks created. {n} tasks across {m} phases, {p} parallel groups."` — per-phase stats already appear inline.
- **commitAndComplete structure**: Currently Step 1 (Auto-Commit) + Step 2 (Update State). Clear insertion point for Step 3 after state is finalized.
- **implement special case**: Calls only the state update step of commitAndComplete (no auto-commit). Step 3 must work regardless of whether Step 1 executed.

### External Patterns
- CLIG.dev: "If you change state, tell the user" — phase completion is a state change that should be reported.
- GitHub Actions Job Summaries: Append-only markdown summary built during execution, rendered at phase boundary.
- CLI UX: ASCII-safe, plain text for terminal compatibility. Avoid emoji in structured output.

## Architecture Overview

### Component Structure

This feature modifies two component types:

1. **workflow-transitions SKILL.md** — Add Step 3 (Phase Summary) to `commitAndComplete()`
2. **5 command files** — Update call sites to pass `iterations` and `reviewerNotes[]`

No new components are created. No Python code, MCP tools, or hooks are involved.

### Data Flow

```
Command review loop
  → computes iterations (int) and reviewerNotes[] (objects)
  → calls commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])
      → Step 1: Auto-Commit (unchanged)
      → Step 2: Update State via complete_phase MCP (now uses caller-provided iterations/reviewer_notes)
      → Step 3: NEW — Format and output summary block
  → Command's Completion Message section
      → AskUserQuestion (unchanged)
```

### Technical Decisions

**TD-1: Summary in commitAndComplete vs. command files**

Decision: In `commitAndComplete()` Step 3.

Rationale: Single implementation point. All 5 commands converge through commitAndComplete, so placing the summary there avoids duplication. The command files only need to pass the data; formatting is centralized.

**TD-2: Parameter passing vs. reading from .meta.json**

Decision: Pass `iterations` and `reviewerNotes[]` as parameters.

Rationale: The data is already available at call-site in each command's review loop. Reading from .meta.json after Step 2 would couple the summary to the MCP tool's write behavior and add fragility. Direct parameter passing is explicit and testable.

**TD-3: reviewerNotes as structured objects vs. flat strings**

Decision: Array of `{"severity": "...", "description": "..."}` objects.

Rationale: The summary needs severity to sort and prefix items (`[W]` vs `[S]`). Flat strings would require parsing. The reviewer JSON response already provides severity — it's cheaper to preserve it than to discard and re-derive.

**TD-4: YOLO mode summary behavior**

Decision: Summary is still output in YOLO mode — no suppression.

Rationale: The spec scopes out "adding summary to YOLO mode auto-transitions (no user prompt to prepend to)" — but the summary is output by commitAndComplete, which runs in both modes. The AskUserQuestion is what gets skipped in YOLO, not the preceding output. The summary provides useful context in logs even when the prompt is auto-answered. No YOLO-specific gating is implemented; the summary incidentally appears in YOLO output.

## Interfaces

### commitAndComplete Extended Signature

```
commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])
```

Parameters:
- `phaseName` (string): Phase name for commit message and summary header. Unchanged.
- `artifacts[]` (string[]): File paths for git staging. Unchanged. When empty, Step 1 (Auto-Commit) still runs (commits .meta.json and .review-history.md only).
- `iterations` (integer): Combined review loop counter at exit. New. For single-reviewer phases: the loop counter value. For dual-reviewer phases (specify, design): `step1_iterations + phase_iterations` (e.g., 2 spec-reviewer + 1 phase-reviewer = 3). For reset cases ("Fix and rerun"): counter from the final run only.
- `capReached` (boolean): Whether any reviewer stage hit its max iteration limit. New. The command file sets this to `true` if any stage exited at `iteration == max` without approval. This decouples cap detection from the iterations count. **Note:** This parameter was added during design review to fix a spec ambiguity where `iterations == max` cannot reliably detect cap-reached in dual-reviewer phases (combined count can equal max without any cap). The spec's `iterations == max` rule is replaced by this explicit boolean.
- `reviewerNotes[]` (object[]): Unresolved reviewer issues. New. Each object:
  ```
  {
    "severity": "blocker" | "warning" | "suggestion",
    "description": string  // max ~200 chars from reviewer
  }
  ```

### Step 3: Phase Summary (new section in SKILL.md)

Output format (plain text, max 12 lines):

```
{PhaseName} complete ({N} iteration(s)). {outcome}.
Artifacts: {file1}, {file2}
{feedback_section}
```

Where:
- `outcome` decision table (first match wins):
  1. `capReached == true` → "Review cap reached."
  2. `iterations == 1` AND `reviewerNotes` empty → "Approved on first pass."
  3. `iterations > 1` AND `reviewerNotes` empty → "Approved after {N} iterations."
  4. `reviewerNotes` non-empty → "Approved with notes."

- `feedback_section` (when `reviewerNotes` non-empty):
  ```
  Remaining feedback ({W} warnings, {S} suggestions):
    [W] {description, truncated at 100 chars}
    [S] {description, truncated at 100 chars}
  ```
  - Cap-reached variant: header becomes `"Unresolved issues carried forward:"`
  - Max 5 items, warnings first, then `"...and {N} more"` if truncated

- `feedback_section` (when `reviewerNotes` empty):
  ```
  All reviewer issues resolved.
  ```

- Artifacts line omitted when `artifacts[]` is empty (implement phase)

### Call Site Changes per Command

| Command | Current Call | New Call |
|---------|-------------|---------|
| specify.md | `commitAndComplete("specify", ["spec.md"])` | `commitAndComplete("specify", ["spec.md"], iteration + phase_iteration, capReached, reviewerNotes)` |
| design.md | `commitAndComplete("design", ["design.md"])` | `commitAndComplete("design", ["design.md"], iteration + phase_iteration, capReached, reviewerNotes)` |
| create-plan.md | `commitAndComplete("create-plan", ["plan.md"])` | `commitAndComplete("create-plan", ["plan.md"], iteration, capReached, reviewerNotes)` |
| create-tasks.md | `commitAndComplete("create-tasks", ["tasks.md"])` | `commitAndComplete("create-tasks", ["tasks.md"], iteration, capReached, reviewerNotes)` |
| implement.md | State update step only | Full `commitAndComplete("implement", [], iteration, capReached, reviewerNotes)` — empty artifacts[] causes Step 1 to commit .meta.json/.review-history.md accumulated during review loop; Step 2 then updates .meta.json again via MCP (acceptable — captures pre-completion state) |

**Iteration counter computation:**
- Single-reviewer phases (create-plan, create-tasks, implement): `iterations = iteration` (the loop counter)
- Dual-reviewer phases (specify, design): `iterations = iteration + phase_iteration` (sum of both stage counters)
- Reset case ("Fix and rerun reviews"): each retry resets counters to 1; the passed value is from the final run only

**capReached computation:**
- `capReached = true` if the review loop exited because `iteration == max` (without approval) in any stage
- For dual-reviewer phases: `capReached = (step1 hit cap) OR (step2 hit cap)`

### reviewerNotes Construction (in each command file)

Before calling `commitAndComplete()`:

```
0. If last reviewer response lacks .issues[] or is not valid JSON:
     reviewerNotes = []
     Log warning to .review-history.md: "Malformed reviewer response — no issues extracted"
1. Let finalIssues = last reviewer's JSON response .issues[]
2. If capReached:
     reviewerNotes = finalIssues.map(i => {severity: i.severity, description: i.description})
   Else:
     reviewerNotes = finalIssues
       .filter(i => i.severity == "warning" || i.severity == "suggestion")
       .map(i => {severity: i.severity, description: i.description})
3. For dual-reviewer phases (specify, design):
     Use only phase-reviewer's final issues[]
4. For implement (3 concurrent reviewers):
     Merge all 3 reviewers' final issues[] into a single array.
     Apply step 2 filter. Deduplicate: if two issues describe the same
     concern about the same code, keep only the higher-severity one.
```

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Summary exceeds 12-line limit with many issues | Low | Low | Hard cap at 5 items + "...and N more" |
| Reviewer response lacks issues[] array | Low | Medium | Default to empty reviewerNotes if parsing fails |
| implement.md doesn't call full commitAndComplete | Known | Medium | implement.md now calls full commitAndComplete with empty artifacts[] — Step 1 commits .meta.json/.review-history.md, Step 3 outputs summary |

## Dependencies

- No external dependencies
- No new tools, MCP endpoints, or Python modules
- Changes are entirely within SKILL.md and command .md files
