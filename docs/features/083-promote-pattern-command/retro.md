# Retrospective: 083-promote-pattern-command

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|-----------:|-------|
| specify | ~13 min | 3 | Threshold calibration + CLAUDE.md exclusion + error-table completeness |
| design | ~3 hr elapsed | 2 | Iter 2 added Pipeline Stage Ownership + Subprocess Serialization Contract (resolved 2 reviewer blockers) |
| create-plan | ~15 min | 3 | Iter 3 delivered task renumbering + TDD red/green ordering inversion fix |
| implement | ~9.5 hr elapsed | 3 | Iter 1: 3 blockers (FR-5 Stage 4 baseline-delta, FR-4 change-target, NFR-3 2-attempt cap). Iter 2: 5 warnings (3 quality + 2 security). Iter 3: all addressed, 177 tests green. |

**Totals:** standard mode, 11 review iterations across 4 phases. Final artifacts: 10 Python modules + 10 test modules (177 tests), promoting-patterns SKILL.md (469 lines), promote-pattern.md command, 5 docs-sync files updated, validate.sh extended with pattern_promotion coverage. 0 errors at close; 10 pre-existing warnings untouched.

### Review (Qualitative Observations)

1. **Adversarial implementation-reviewer caught genuine spec deviations that the executor self-reported as "deferred."** Phase 3 Deviations said the baseline-delta `validate.sh` invocation was deferred to Phase 4a. Implementation-reviewer iter 1 flagged this as BLOCKER 1 (FR-5 Stage 4 baseline-delta missing). The executor's own audit did not catch this — demonstrates the value of a separate reviewer dispatch over self-review.

2. **Security-reviewer surfaced two distinct injection classes in LLM-orchestrated output** in iter 2:
   - Shell injection in `hook.py::_render_hook_sh` and `_render_test_sh` via unescaped `entry_name` spliced into bash templates.
   - Markdown structural injection in `_md_insert.py::_render_block` via raw `entry.description` (triple-backtick code fences, leading `#` headings, `---` frontmatter delimiters, unbounded length). Both are live prompt-injection surfaces because the generated artifacts are read by future Claude sessions.

3. **Design pre-work front-loaded integration risk.** The Pipeline Stage Ownership table and Subprocess Serialization Contract were added in design iter 2 (resolving two design-reviewer blockers). Implementation then executed 5 phases across 177 tests with zero "how do skill and Python communicate?" discoveries.

### Tune (Process Recommendations)

1. **TDD ordering sanity check in creating-plan skill or plan-reviewer** — for every task tagged `[TDD: red]`, verify the matching `[TDD: green]` task appears later in tasks.md. Mechanical grep.
2. **Treat self-reported "deferred" in implementer deviations as a phase-gate blocker** unless the deferred FR has a concrete task in a named downstream phase.
3. **LLM-consumed output injection check in code-quality-reviewer and security-reviewer prompts** — when an artifact is generated from LLM-provided input AND consumed by future LLM or shell, require explicit sanitization (denylist + escape + length cap).
4. **Promote Subprocess Serialization Contract to a reusable design pattern** — document in designing skill for any pd skill that orchestrates Python helpers via Bash.
5. **TD-8 marker pattern as a heuristic for atomic-write flows** — any multi-file atomic-write system should embed a machine-scannable provenance marker per artifact for SIGINT-class recovery.

### Act (Knowledge Bank Updates)

**Patterns:**
- **Subprocess Serialization Contract** — compact status JSON on stdout + bulky artifacts in sandbox dir + status-only stderr. Skill reads sandbox via Read tool; exit code 0=ok/need-input, non-zero=error.
- **TD-8 Partial-Run Collision Markers** — every generated artifact carries a scannable provenance comment; pre-flight scan refuses writes on collision.
- **Adversarial Implementation Review Catches Self-Reported Deferrals** — reviewer re-validates spec FR coverage independently of implementer's "Deviations" section.

**Anti-patterns:**
- **Unsanitized Interpolation of LLM/User Input Into Generated Shell Scripts** — backticks, `$(`, unescaped quotes, CR/LF in comment lines are live injection primitives.
- **Unsanitized Interpolation of LLM/User Input Into Markdown Consumed by Future LLM Sessions** — triple-backticks, leading `#`/`---`/`===`, unbounded length corrupt target files and enable prompt injection.

**Heuristics:**
- **Pipeline Stage Ownership Table** — during design, map every FR sub-step to named executor (skill markdown OR Python module function).
- **Skill-backing criterion for pd commands** — warrant a backing skill when workflow has (a) >1 LLM call in sequence, (b) stateful approval loops, OR (c) rollback semantics.
- **Baseline-Delta Validation** — for atomic-write flows gated by slow validators, compare baseline error count + categories vs post-write, rollback only on NEW errors or categories.

## Raw Data

- Feature: 083-promote-pattern-command
- Mode: standard
- Branch: feature/083-promote-pattern-command
- Total review iterations: 11 (3 + 2 + 3 + 3)
- Tests landed: 177 passing
- Final validate.sh: 0 errors, 10 pre-existing warnings
