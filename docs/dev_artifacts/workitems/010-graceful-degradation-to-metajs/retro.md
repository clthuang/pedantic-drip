# Retrospective: Feature 010 — Graceful Degradation to meta.json

## Quantitative Summary

| Metric | Value |
|--------|-------|
| Total phases | 5 (specify, design, create-plan, create-tasks, implement) |
| Total review iterations | 26 (specify: 3, design: 8, create-plan: 10, create-tasks: 5, implement: 5) |
| Phase-reviewer caps hit | 2 (create-plan planReview: 5, create-plan chainReview: 5) |
| Files changed | 11 |
| Lines added | 6,356 |
| Lines removed | 204 |
| Test count | 269 (184 engine + 85 server) |
| Implementation commits | 16 (task commits + review fix commits) |
| Duration | ~8 hours (17:00–01:00 +08:00) |
| Dependency | Feature 008 (WorkflowStateEngine core) |

## Achievements

### A1: Complete Graceful Degradation Coverage
All 6 engine operations (get_state, transition_phase, complete_phase, validate_prerequisites, list_by_phase, list_by_status) now fall back to .meta.json when the database is unavailable. Each operation degrades independently with explicit `source` tracking.

### A2: Structured Error Responses Throughout MCP Layer
Migrated all MCP tool error returns from ad-hoc strings to structured `_make_error()` responses with error_type, message, and recovery_hint fields. This enables programmatic error handling by callers.

### A3: TransitionResponse Dataclass for Degradation Signaling
Introduced `TransitionResponse(results, degraded)` to carry degradation state through the transition pipeline without altering the existing `TransitionResult` contract. Clean separation between gate evaluation results and operational metadata.

### A4: Comprehensive Test Coverage at 4.7:1 Ratio
269 tests (184 engine, 85 server) covering all degradation paths, DB health checks, filesystem scanning, and MCP error routing. Test-to-code ratio matches the 4-5:1 heuristic established in Feature 008.

### A5: Zero-Deviation Implementation Despite Plan-Reviewer Caps
Both create-plan reviewers hit the 5-iteration cap with approved:false, yet the 7 reviewer notes were specific enough to guide clean implementation. All 22 tasks executed without deviation, confirming the "front-loaded investment" pattern from Feature 007.

## Obstacles

### O1: Plan-Reviewer Cap in Both Review Stages
The create-plan phase consumed 10 iterations (5 planReview + 5 chainReview) — the most of any phase. Six specific reviewer notes (call-site enumeration, fd.close() contradiction, TDD atomicity, consumer audit scope, pre-implementation grep, error-path test count) captured the unresolved concerns that guided implementation.

### O2: Static Line Number References in Plan
Plan referred to specific line numbers (605, 622, 640, 659, etc.) for call-site modifications, but these became stale by implementation time. The chainReview note "line numbers are static approximations — engineer should run pre-commit grep at START" directly addressed this.

### O3: Message Format Inconsistency in _catch_value_error
Quality reviewer flagged `f"Error: {exc}"` producing double-prefixed messages (e.g., "Error: Error: Feature not found") across 3 review iterations before the fix was identified. Root cause: `str(exc)` already contained descriptive text, and the f-string added a redundant "Error:" prefix.

### O4: Design Handoff Review Reached 5 Iterations
The handoff review required 5 iterations to resolve try/finally complexity concerns and source provenance tracking for read-back failures. Two reviewer notes carried forward as implementation guidance.

## Risks

### R1: .meta.json Write Conflicts Under Concurrent Access
The fallback writes to .meta.json without file locking. If multiple processes attempt degraded writes simultaneously, last-write-wins semantics could lose state. Mitigated by: degradation is a temporary failure mode, and concurrent MCP sessions are rare.

### R2: Filesystem Scanning Performance for Large Feature Sets
`_scan_features_filesystem()` and `_scan_features_by_status()` glob the entire features directory. Projects with 100+ features could see degraded list operations become slow. Not a concern at current scale (~20 features).

### R3: DB Health Check Timing
`_check_db_health()` uses a simple SELECT 1 probe. A slow but responsive database would pass the health check but still cause timeouts on actual queries. The 5-second PRAGMA timeout provides a bounded fallback trigger.

### R4: Degraded Mode State Drift
When operating in degraded mode, .meta.json writes accumulate state changes that are not reflected in the database. On DB recovery, the engine reads from DB (stale) rather than .meta.json (current). No reconciliation mechanism exists yet (planned as Feature 011).

### R5: Error Message Classification Fragility
`_catch_value_error` classifies errors by checking `"not found" in msg.lower()` — a string-matching heuristic. If upstream code changes error message wording, classification could route to the wrong error_type.

## Takeaways

### T1: Plan-Reviewer Caps Produce Implementation-Ready Plans
Confirms Pattern "Zero-Deviation Implementation After Phase-Reviewer Cap Iterations" — now observed in both Feature 007 and Feature 010. The 10-iteration create-plan investment produced 22 tasks that executed without deviation.

### T2: Static Line Numbers in Plans Are Anti-Patterns
Line number references in plans become stale between plan creation and implementation. The chainReview note to "run pre-commit grep at START" is the correct mitigation — always resolve line numbers dynamically at implementation time.

### T3: Error Message Format Requires Systematic Sweep
The `f"Error: {exc}"` double-prefix bug persisted across 3 quality review iterations because each iteration found it in a different location. Sibling-sweep pattern (from Feature 008) should be applied: when fixing a message format, grep for all instances of the same pattern.

### T4: Handoff Reviewer Notes Are Implementation Contracts
The 2 handoff reviewer notes and 6 plan reviewer notes functioned as binding implementation guidance. When review caps are hit, the accumulated reviewer notes become the spec for implementation.

### T5: Structured Error Responses Enable Programmatic Handling
Moving from ad-hoc error strings to `_make_error()` with typed error_type fields enables callers to handle errors programmatically. This pattern should be applied to all MCP server tools.

## Actions

### ACT-1: Knowledge Bank Update — Pattern Reinforcement
Update "Zero-Deviation Implementation After Phase-Reviewer Cap Iterations" pattern with Feature 010 as second observation (count: 1→2).

### ACT-2: Knowledge Bank Update — New Anti-Pattern
Add "Approximate Call-Site Counts in Migration Plans" to anti-patterns: plans referencing specific line numbers or approximate counts that become stale by implementation time.

### ACT-3: Knowledge Bank Update — New Heuristic
Add "Live Line Numbers Expire Before Implementation — Pre-Step Grep Required" to heuristics: always resolve line/location references dynamically at the start of implementation steps.

### ACT-4: Reconciliation Feature Planning
Feature 011 (Reconciliation MCP Tool) will address R4 (degraded mode state drift) by providing a mechanism to sync .meta.json state back to the database on recovery.

### ACT-5: Error Classification Hardening
Consider replacing string-matching error classification with explicit error subclasses or error codes to address R5 (error message classification fragility).
