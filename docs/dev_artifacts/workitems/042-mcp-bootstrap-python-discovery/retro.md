# Retrospective: 042-mcp-bootstrap-python-discovery

## AORTA Analysis

### Observe

| Phase | Iterations | Notes |
|-------|------------|-------|
| specify | 2 | RC-5 silently dropped in iter 1; 3 blockers fixed |
| design | 2 | 3 blockers: uv syntax, injection risk, check_mcp_health placement |
| plan | 2 | 2 blockers: version comparison rejected Python 4.x; SENTINEL_PATH forward ref |
| tasks | 1 | 2 blockers self-corrected before second review |
| implement | 1 | All 3 reviewers approved; security fix applied post-review |

13 commits, 12 files changed, +2,072/-83 lines. 24 new tests (bootstrap +14, hooks +10).

### Review

1. **RCA-to-requirement gap** — RC-5 mentioned in problem statement but dropped from requirements. Spec reviewer forced a coverage audit.
2. **Bash version comparison recurring failure** — `(major == 3 && minor < 12)` appeared in design and plan drafts, required correction in both. Correct: `(major < 3 || (major == 3 && minor < 12))`.
3. **Python injection caught late** — `python3 -c` with shell variable interpolation specified in design, caught only at implement security review.

### Tune

1. **Add RCA-coverage audit to spec-reviewer** — enumerate all numbered root causes, verify each maps to a requirement, blocker if unmapped.
2. **Add version comparison checklist** — flag `major == N && minor < M` without `major > N` handling.
3. **Flag `python3 -c` interpolation at design phase** — require injection-risk note before approval.
4. **Annotate module-level variable dependencies in tasks** — explicit "Requires: VAR set in TX.Y" annotations.
5. **Early-phase review investment validated** — implement passed first review after 8 upstream iterations.

### Act

**Patterns:** RCA-driven development, two-tier Python discovery, JSONL error log for silent failures, sentinel metadata format.
**Anti-patterns:** python3-c injection, bash version comparison gap, soft first-run messages.
**Heuristics:** RCA-coverage audit, module-level variable dependencies, design-phase security flagging.
