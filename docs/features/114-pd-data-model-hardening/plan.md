# Plan: pd Data-Model + Memory Hardening (Feature 114)

**Source:** `spec.md` (rev 4) + `design.md` (rev 2)

## Build Order (Topological)

Six implementation tiers honoring spec Section 8 cluster sequencing:

```
Tier 1: A (M12 guard) ‖ A.6 (fixtures) ‖ M11 (M11 guard)         — foundational, no deps
   ↓
Tier 2: D (workspace fallback)                                    — needed by Tier 3
   ↓
Tier 3: C (audit invariant: emit + M15 + AST check + whitelist)   — sweeps test fixtures first
   ↓
Tier 4-pre: B-H4.0 (recompute helper + freeze manifest)           — prereq for B-H4
   ↓
Tier 4: B-H4 (M6 hash unify + M7 cleanup)                         — depends on manifest
   ↓
Tier 5: B-H3 (_apply_quality_gates) ‖ B-H2 (capture hook)         — independent
   ↓
Tier 6: E (cross-workspace gates) ‖ E.2 (triage tool + M17 alllowlist) ‖ E-Sev (severity_summary)
```

## TDD Strategy

Per cluster:

- **A / A.6 / M11**: Test fixtures shipped FIRST (RED) — each `m12_stub_trap.sql` / `pre_m11.sql` / `post_m12.sql` / `m12_partial.sql` produces a known schema state. Then guard logic + remediation CLI written to recognize them (GREEN). Refactor to share `_compute_schema_fingerprint`.
- **D**: Test fixture variant first (real-UUID `_workspace_uuid` against legacy `_UNKNOWN_WORKSPACE_UUID` entity, expect `EntityNotFoundError`). Then implement two-pass fallback (GREEN). Negative test for arbitrary cross-workspace stays in RED.
- **C**: Mock `append_phase_event` to raise → write fail-open test (RED). Add emit + try/except (GREEN). Then sweep test fixtures + remove AST whitelist. C10.1 + C10.2 are atomic — same commit.
- **B-H4.0**: Helper produces deterministic output against fixture; manifest freeze step is implement-only, not TDD.
- **B-H4**: Migration consumes frozen manifest; dry-run gate tests injected drift in fixture row.
- **B-H3 / B-H2**: Helper extraction is refactor-with-tests (existing _process_store_memory tests guide). Hook deletion: integration test asserts no `Tool failure:` rows after hook runs.
- **E / E.2**: Cross-workspace error tests (RED) → assert helper + 3 gate calls (GREEN). Allowlist exemption test. Triage tool: per-option mutation tests.

## Validation Strategy

- **Unit tests**: per-component (C1-C15), in adjacent test files (`test_database.py`, `test_workflow_state_server.py`, `test_doctor_fixes.py` etc.)
- **Integration tests**: per cluster — end-to-end through MCP boundary for D, C, E.
- **Schema-fingerprint regression tests**: compute `_PRE_M12_FINGERPRINT` and `_POST_M12_FINGERPRINT` at test setup via fixture load; pin against constants.
- **Manifest freeze test**: dry-run `recompute_all` against fixture memory.db, assert frozen-set matches.
- **AST audit tests**: integration test seeds a violating migration body, asserts new doctor checks fail.
- **Full regression**: `pytest plugins/pd/` from project root post-implement; 0 failures required.

## AC-to-Task Coverage Matrix

Each spec AC mapped to the task that exercises it.

| AC | Test Layer | Task | MCP-required? |
|----|-----------|------|---------------|
| AC-A.1 | integration (fixture-DB) | T2.10 | No |
| AC-A.2 | integration (fixture-DB) | T3.1 | No |
| AC-A.3 | integration (doctor harness) | T2.14 | No (doctor uses entities_conn directly) |
| AC-A.4 | unit (grep) | T2.8 | No |
| AC-A.5a/b/c | integration (fixture-DB) | T2.10 | No |
| AC-M11.1 | integration (fixture-DB) | T3.1 | No |
| AC-B-H2.1 | unit (grep canonical manifest) | T13.2-T13.3 | No |
| AC-B-H2.2 | integration (memory-DB) | T13.5 (M6 cleanup query) | No |
| AC-B-H3.1 | AST check | T12.10 | No |
| AC-B-H3.2 | AST check (single-source) | T12.10 | No |
| AC-B-H3.3 | integration (CLI) | T12.8 | No |
| AC-B-H3.4 | integration (CLI) | T12.9 | No |
| AC-B-H4.1 | integration (memory-DB) | T11.3 | No |
| AC-B-H4.2 | integration (memory-DB) | T11.1 | No |
| AC-B-H4.3 | integration (manifest gate) | T11.1-T11.2 | No |
| AC-C.1 | integration (per-callsite) | T5.1 | Mostly No (DB-level); 4 callers via MCP path |
| AC-C.2 | unit (mock raise) | T5.2 | No |
| AC-C.3 | AST check | T9.6 (whitelist removed) | No |
| AC-C.4 | unit (no-op) | T5.3 | No |
| AC-C.5 | integration (doctor) | added in C10 detection step | No |
| AC-C.6 | unit (pytest pass) | T9.8 | No |
| AC-C.7a/b/c | integration (M99 + AST) | T7.1-T7.3, T8.1 | No |
| AC-D.1 | integration (MCP) | T4.2 | **YES** (MCP boundary) |
| AC-D.2 | integration (MCP, baseline) | implied pre-fix | **YES** |
| AC-D.3 | integration (MCP) | T4.3 | **YES** |
| AC-D.4 | unit (stderr) | T4.4 | No (capture via subprocess) |
| AC-E.1 | integration (MCP) | T14.7-T14.9 | **YES** |
| AC-E.2 | integration (MCP) | implicit (existing same-ws tests pass) | **YES** |
| AC-E.3 | integration (MCP + DB) | T14.4 | No (db-layer) |
| AC-E.4 | integration (doctor) | T15.11 detection | No |
| AC-E.5 | integration (SQL) | T15.7 (deletion option) | No |
| AC-E.2.1-3 | integration (doctor) | T15.5-T15.8 | No |
| AC-Sev.1-3 | integration (doctor JSON) | T16.1-T16.3 | No |

**MCP-required ACs that face the disconnected-MCP wall this session**: AC-D.1, AC-D.2, AC-D.3, AC-E.1, AC-E.2 (6 ACs). Implementer can run these tests as in-process MCP harness fixtures (the MCP servers can run in-process via direct `_process_*` function calls bypassing the JSON-RPC layer — see existing `test_complete_phase_closes.py` pattern at `wss._workspace_uuid = ...`). If even in-process tests fail to load due to import-cycle or schema state, defer the affected ACs to a post-merge verification run.

## Risks and Mitigations

Carried from design Section 4 risk list. Implementation-phase additions:

- **R-P1**: Tier 4 (B-H4.0 + B-H4) is sequential due to manifest dependency. Cannot parallelize within tier 4.
- **R-P2**: Tier 3 has internal dependency: C10.1 (emit) → C10.4 (AST audit check) → AC-C.7c verification → C11 (whitelist removal). Implementer must sequence within the same cluster.
- **R-P3**: MCP servers disconnected this session; integration tests that need MCP startup must be deferred or stubbed. Pure DB-level tests (database.py changes) run fine.

## Out-of-Scope (carry-forward)

Per spec Section 5 + design Section 3.X. Implement must NOT:
- Change entity types or workspace concepts
- Modify `_KIND_TO_TYPE_LIFECYCLE`, `_CLOSES_TERMINAL`
- Touch F111 `complete_phase(closes=...)` semantics beyond FR-D
- Touch FTS5 rebuild logic
- Migrate existing stderr-print calls to `log_stderr_json`
- Modify `register_entity` raise-on-conflict semantics
