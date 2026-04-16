# Retrospective: 081-mid-session-memory-refresh-hoo

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Iterations | Notes |
|-------|-----------:|-------|
| specify | 3 | Iter 1 found 4 blockers (fake "reuse" claim, next_phase terminal behavior, MCP-server boundary crossing, latency pre-emption infeasibility); iter 2 + 3 polish |
| design | 3 | Iter 1 found 4 blockers (EntityDatabase vs MemoryDatabase conflation, missing `_config` module global, TD-1 parity ambiguity, undefined `REFRESH_OVERSAMPLE_FACTOR`); iter 2 added shared helper strategy; iter 3 signature refinement |
| create-plan | 2 | Iter 1 plan+task reviewers found 8 blockers combined (TDD bundling, Phase 6 sequencing interleave requirement, signature ambiguity, stderr prefix regex precision, monkeypatch pattern, etc.); iter 2 approved |
| implement | 1 | Clean — implementation-reviewer approved all 4 levels with 1 non-blocking suggestion (hybrid_retrieve kwarg extension beyond TD-1 signature) |

**Totals:** 9 review iterations. Medium scope: ~400 LOC net across `refresh.py` (new, ~260 LOC), `test_refresh.py` (new, ~400 LOC), `workflow_state_server.py` (+3 globals, +25 LOC lifespan, +15 LOC gate), `memory_server.py` (small refactor, net-zero LOC), 3 config/docs files.

**Tests landed:** 3430 passing, test-hooks 101/101, validate.sh 0 errors and 6 warnings unchanged from baseline.

### Review (Qualitative Observations)

1. **EntityDatabase vs MemoryDatabase conflation was a near-miss** that would have been a production-time crash if design-reviewer hadn't caught it in iter 1. The two SQLite files (`~/.claude/pd/entities/entities.db` vs `~/.claude/pd/memory/memory.db`) have distinct schemas and APIs; `workflow_state_server.py` had no connection to the latter today. Caught exclusively because the reviewer dropped into `workflow_state_server.py:73` to verify the claimed `db` type — a shallow review would have missed it.

2. **Plan-reviewer caught a Phase ordering bug that would have broken Phase 4 mid-execution.** The initial plan had Phase 4 (integration gate) before Phase 6 (existing-test remediation), meaning the moment the gate inserted a `memory_refresh` field into complete_phase responses, exact-dict equality tests would break. Resolution: interleave Phase 6 between Task 4.4 (red tests) and Task 4.5 (gate). As it turned out at implementation time, zero existing tests actually broke (audit returned `<none>`) because the gate short-circuits on `_memory_db is None` in unit-test contexts — but the defensive sequencing cost nothing and protected the feature.

3. **TD-1 "skip the refactor, parity is automatic" was wrong in iter 1.** Initial design claimed both `_process_search_memory` and `refresh_memory_digest` instantiated the same `RetrievalPipeline + RankingEngine` independently, so parity was "automatic." Design-reviewer correctly argued this depends on caller discipline (same `project=` arg, same `entries_by_id` dict build, same `limit`) — a future regression could silently diverge the two paths. Resolution: extract `hybrid_retrieve()` as a shared function both callers invoke. Parity becomes structural.

4. **Spec-reviewer caught `_derive_next_phase('finish') == 'finish'` semantic mismatch.** The entity_registry's existing helper returns `'finish'` for the terminal phase (valid for entity state machines) but that's semantically wrong for a refresh query (nothing comes after finish; query should be just the feature slug). Resolution: inline `_NEXT_PHASE` mapping with explicit `finish → ""` rather than importing the existing helper. This avoided a subtle query-construction bug.

5. **Implementation-reviewer noted hybrid_retrieve signature drift from design.** The as-built signature added optional `project`/`category` kwargs beyond design TD-1 to preserve memory_server's pre-existing pre-rank filter semantics. Not a design failure — a reasonable extension during refactor — but worth tracking: design.md now has an inline NOTE in I-1 pointing to the authoritative task-level signature.

### Tune (Process Recommendations)

1. **When a feature crosses MCP-subprocess boundaries, design-reviewer should explicitly verify type signatures of shared globals** (Confidence: high)
   - Signal: the EntityDatabase vs MemoryDatabase mistake was caught only because reviewer dropped into the file; a shallower review would have missed it.
   - Recommendation: add to design-reviewer heuristics: "If the feature references `db`, `_provider`, `_config`, or similar common global names that exist in MULTIPLE files, verify the name in the target file's scope resolves to the expected type."

2. **Plan-reviewer should systematically check Phase ordering against the "existing-test fragility" anti-pattern** (Confidence: high)
   - Signal: inserting a new field into a response format that existing tests assert exact-dict equality on is a reliably-missed regression path.
   - Recommendation: when a plan introduces a new response-shape field, plan-reviewer should verify that Phase 6 (or equivalent existing-test remediation) is sequenced BEFORE the integration phase that enables the field — not after.

3. **Keep the "structural parity via shared function" pattern as an AORTA heuristic** (Confidence: high)
   - Signal: TD-1 iter 1 claimed parity was automatic; iter 2 made it structural by extracting `hybrid_retrieve()`.
   - Recommendation: add to heuristics — "When two code paths must produce identical outputs on identical inputs, prefer extracting a shared function they both invoke over relying on caller-discipline to keep them in sync."

### Act (Knowledge Bank Updates)

**Patterns:**
- **Structural Parity via Shared Function Extraction** — when two code paths must produce identical outputs (e.g., two MCP callers to a ranking pipeline), extract a shared function they both invoke rather than relying on caller-discipline. Makes parity a compile-time property, not a review-time one.

**Anti-patterns:**
- **Same-Name-Different-Type Shared Globals Across MCP Subprocesses** — `db` can be `EntityDatabase` in one subprocess and `MemoryDatabase` in another; silent type confusion at the integration point is a real risk.
- **New Response-Field Insertion Before Existing-Test Audit** — adding a new key to a response shape breaks existing exact-dict-equality assertions; Phase 6 remediation must precede Phase 4 integration, not follow it.

**Heuristics:**
- **Separate Entity Registry Terminal Semantics From Workflow Terminal Semantics** — existing helpers like `_derive_next_phase('finish') == 'finish'` are valid for state-machine entity tracking but semantically wrong for content-retrieval queries. Use an inline mapping for refresh queries.

## Raw Data
- Feature: 081-mid-session-memory-refresh-hoo
- Mode: standard
- Branch: feature/081-mid-session-memory-refresh-hoo
- Total review iterations: 9 (3 specify + 3 design + 2 create-plan + 1 implement)
- Tests landed: 3430 (27 new in test_refresh.py + 3 integration in test_workflow_state_server.py)
- Final validate.sh: 0 errors, 6 warnings (= baseline)
