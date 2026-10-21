# Retrospective: 039-mcp-bootstrap-race-fix (MCP Bootstrap Race Fix)

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 12 min | 6 | High — scope expansion to 4th server, system-python unification, portability constraints |
| design | 18 min | 5 | Moderate — bash 3.2 constraint, sentinel file semantics, uv-sync vs uv-pip tradeoff |
| create-plan | 17 min | 3 | Clean — TDD ordering unambiguous, 4-phase structure well-defined |
| create-tasks | 16 min | 6 | High — portability micro-blockers: `which` vs `command -v`, subshell isolation, PID capture |
| implement | 40 min | 3 | iter 1 quality issues; iter 2 approved; iter 3 final validation. 22/22 tasks, 0 deviations |
| **Total** | **~107 min** | **23** | Clean implement despite high specify/tasks iterations |

### Review (Qualitative Observations)

1. **Portability precision surfaced progressively across two phases** — Specify and create-tasks both accumulated portability micro-blockers as separate per-iteration issues rather than being caught in a single sweep.

2. **4th server scope expansion handled correctly at specify time** — The PRD identified 3 MCP servers. Specify correctly absorbed `run-ui-server.sh` as a 4th affected script before design, preventing a late-phase scope surprise.

3. **Implementation discoveries were genuine, not false positives** — File-based counters for subshell-safe tallying and `uv pip uninstall` vs `$venv/bin/pip uninstall` were real behavioral differences requiring code changes.

### Tune (Process Recommendations)

1. **Add bash portability pre-flight to spec/task reviewers** — A single checklist (no associative arrays, `command -v` not `which`, `find -mmin` not `stat`, `mkdir` not `flock`, file-based counters if subshells) would save ~4 iterations across downstream phases.

2. **Document uv venv behavioral differences in design** — When design selects `uv venv`, note: pip not installed by default, install via `uv pip install --python`, uninstall via `uv pip uninstall`.

3. **Specify bash test counter architecture in tasks** — File-based counters vs shell variables is a load-bearing decision that belongs in task spec, not implementation discovery.

4. **Propagate shared-library-for-concurrent-bootstrap as prior art** — The bootstrap-venv.sh architecture is reusable for any N-concurrent-process shared resource initialization.

### Act (Knowledge Bank Updates)

- **Patterns:** Shared Bootstrap Library for Concurrent-Process Resource Initialization; File-Based Counters for Cross-Subshell Test Tallying
- **Anti-patterns:** Per-Consumer Dependency Subsets for a Shared Resource
- **Heuristics:** Assume Bash 3.2 Compatibility for Any Script Targeting macOS

## Raw Data

- Total review iterations: 23 (specify: 6, design: 5, create-plan: 3, create-tasks: 6, implement: 3)
- Tasks: 22/22 complete, 0 deviations
- Files created: bootstrap-venv.sh (~264 lines), test_bootstrap_venv.sh (~1196 lines)
- Files refactored: 4 run-*.sh wrappers (~21 lines each, down from 32-41)
- Test deepening: 13 tests added across 5 dimensions
