# Plan: pd Data-Model + Memory Followups (Feature 115)

**Source design:** `docs/features/115-pd-data-model-followups/design.md`
**Source spec:** `docs/features/115-pd-data-model-followups/spec.md`
**Status:** Draft rev 1

## Tier Rationale (Why this order)

- **Tier 0 → Tier 1**: AC-PRE verifies FR-D landed (114 prerequisite for FR-C emit correctness). Without Tier 0 passing, Tier 1's emit could misroute on legacy workspace UUIDs.
- **Tier 1 → Tier 2a**: Cluster C audit emit is highest correctness value (FM-1 mitigation locks in atomicity) and independent of E.2. Tier 1 first because tier-2a depends on doctor infrastructure that C touches (audit counter + AST checks).
- **Tier 2a → Tier 2b**: E.2 (triage tool + M17 allowlist) is prerequisite for E (cross-workspace gates) per PRD; gates need the allowlist table to exist before they can consult it.
- **Tier 2b → Tier 3a**: E completes correctness work. Tier 3a (B-H3) is hygiene; lower risk.
- **Tier 3a → Tier 3b**: B-H3 (CLI gate extraction) is prerequisite for B-H4's hash-recompute helper which writes via the same gate path.

## Implementation Order (matches design §6 + spec §8)

```
[Tier 0]  Prereq verification — AC-PRE.1 + AC-PRE.2 (rg checks, no code changes)
   ↓
[Tier 1]  Cluster C — atomicity guards + emit + M15 + AST audit check
            ├─ C17.1, C17.2 atomicity guard scripts staged BEFORE C10
            ├─ C10-115.1/.2 single-commit (FR-C-115.1 marker)
            ├─ C10-115.3 M15 migration
            ├─ C10-115.4 check_audit_counter_write_path.py
            └─ C17.3 validate.sh stanza
   ↓
[Tier 2a] Cluster E.2 — M16 stub → M17 allowlist → fix_actions sub-package → triage tool
            ├─ C16 (M16 no-op stub) — separate commit BEFORE M17
            ├─ check_migration_contiguity.sh
            ├─ C13-115.2 M17 (cross_workspace_allowlist table)
            ├─ TD-115-5 sub-package promotion (rg discovery + explicit re-export)
            └─ C14-115 triage fix_action + IF-115-4 _interactive_triage_loop helper
   ↓
[Tier 2b] Cluster E — gates + envelope + new doctor check
            ├─ C13-115.1 _assert_same_workspace_pairwise + CrossWorkspaceError
            ├─ 3 MCP handler gates (_process_set_parent, _process_add_dependency, _process_add_okr_alignment)
            ├─ Envelope translator branch for cross_workspace_forbidden
            ├─ C13-115.3 check_cross_workspace_parent_uuid doctor check
            └─ C15-115.1 severity vocab AST check
   ↓
[Tier 3a] Cluster B-H3 — writer CLI quality gates (114 C7 unchanged)
            ├─ Extract _apply_quality_gates from _process_store_memory
            └─ writer.py:main invokes _apply_quality_gates pre-upsert
   ↓
[Tier 3b] Cluster B-H4 — recompute helper + M6 + M7
            ├─ C8-115.1 recompute_source_hash.py with report() + recompute_all_with_conn()
            ├─ Dry-run --report against live memory.db; verify pins H-115/I-115
            ├─ C8-115.2 M6 body (DELETE + hash unify, both gated)
            └─ C8-115.3 M7 body (observation reset, gated)
```

**80/20 fallback** (canonical, cross-ref spec §8): floor = Tier 0 + Tier 1 + Tier 2a + Tier 2b. Drop order: Tier 3a first, then Tier 3b. C+E+E.2 are non-negotiable.

## AC Coverage Matrix (expanded — every individual AC mapped)

Task IDs reference `tasks.md` task headers (e.g., T0.1 = "T0.1: Verify FR-D inheritance intact").

| AC | Task(s) | Verification | MCP Required? |
|---|---|---|---|
| AC-PRE.1 | T0.1 | bash rg | no |
| AC-PRE.2 | T0.2 | bash rg | no |
| AC-C.1 (114, 17 callers) | T1.8 (per-callsite tests) | pytest direct-Python (17 tests) | no |
| AC-C.2 (114 fail-open) | T1.7 implicit + new test in T1.8 (mock append_phase_event raise) | pytest | no |
| AC-C.3 (114 whitelist) | DEFERRED to 116 | n/a | n/a |
| AC-C.4 (114 no-op write) | T1.8 sub-case (same-status update produces 0 events) | pytest | no |
| AC-C.5 (114 doctor warn) | T1.12 | direct doctor invocation | no |
| AC-C.6 (114 test sweep) | DEFERRED to 116 | n/a | n/a |
| AC-C.7a (114 M15 reset) | T1.9 | migration runner test | no |
| AC-C.7b (114 M15 preservation) | T1.10 | synthetic _migration_test_99 test | no |
| AC-C.7c (114 AST audit) | T1.11 | check_audit_counter_write_path test | no |
| AC-C-115.1 (atomicity) | T1.4 (script stage) + T1.4a (symlink) + T1.6 (single commit) + T1.13 (validate.sh stanza) + T1.13b (self-test) | content-aware git log + bash | no |
| AC-C-115.2 (single-emit COUNT==1) | T1.5a (failing test) → T1.6 (impl) → T1.7 (passes) | pytest direct-Python on `_process_complete_phase` | no |
| AC-C-115.3 (closed_by_uuid optional) | T1.5a assertion shape | pytest | no |
| AC-C-115.deferred (no whitelist tasks) | plan-phase guard at end of plan.md | grep | no |
| AC-E.1 (114, 3 gates reject cross-ws) | T2b.5 (case A: cross-ws → envelope) | pytest direct-Python | no |
| AC-E.2 (114, same-ws succeed) | T2b.5 (case B) | pytest | no |
| AC-E.3 (114, allowlist exempt) | T2b.5 (case C: seeded allowlist) | pytest | no |
| AC-E.4 (114, envelope shape) | T2b.3 | direct response inspection | no |
| AC-E.5 (114, post-triage COUNT==0) | T2a.8 | SQL direct | no |
| AC-E.6 (114, hard-error out-of-scope) | T2b.7 (no severity='error' emitted) | AST + integration | no |
| AC-E.2.1 (114, allowlist schema) | T2a.3 | PRAGMA table_info | no |
| AC-E.2.2 (114, triage UX) | T2a.7 | pytest with mocked AskUserQuestion | no |
| AC-E.2.3 (114, 4 decision options) | T2a.7 (4 sub-cases) | pytest | no |
| AC-E-115.1 (severity vocab AST) | T2b.8 + T2b.9 | AST scan via tests | no |
| AC-E-115.2 (count assert ≥21 warning) | T2b.7 (seeded 21-row fixture) | direct doctor invocation | no |
| AC-E-115.3 (no 'suggestion') | T2b.8 + T2b.9 | AST scan | no |
| AC-B-H3.1 (writer.py:main single _apply call) | T3a.2 + T3a.3 (AST verify) | AST + pytest | no |
| AC-B-H3.2 (single-source-of-truth literals) | T3a.3 | AST scan memory_server.py | no |
| AC-B-H3.3 (empty desc exit !=0) | T3a.4 | CLI integration | no |
| AC-B-H3.4 (near-dup exit !=0) | T3a.4 | CLI integration | no |
| AC-B-H4.1 (114 post-backfill inflated==0) | T3b.7 (end-to-end) | SQL direct | no |
| AC-B-H4.2 (114 hashes match recompute) | T3b.3b + T3b.7 | SQL direct | no |
| AC-B-H4-115.1 (M6 count_drift abort) | T3b.3a Test 1 + Test 2 | pytest with seeded out-of-range fixture | no |
| AC-B-H4-115.2 (M7 count_drift abort) | T3b.4 (failing tests pre-impl), T3b.5 (impl satisfies) | pytest | no |
| AC-B-H4-115.3 (M6 DELETE result COUNT==0) | T3b.3a Test 3 + T3b.7 | SQL post-migration | no |
| AC-B-H4-115.4 (M7 inflated reset COUNT==0) | T3b.4 Test 3 + T3b.7 | SQL post-migration | no |
| AC-B-H4-115.5 (recompute --report) | T3b.2 | CLI invocation + value validation | no |
| AC-Migrations-115.1 (dict keys present) | T1.9 (M15) + T2a.2 (M16) + T2a.3 (M17) + T3b.3c (M6) + T3b.5 (M7) | grep + dict inspection | no |
| AC-Migrations-115.2 (grep counts) | T2a.2 + T3b.3c + T3b.5 | bash grep | no |
| AC-Sev.1 (114, exit 0 + JSON warn>0) | T2b.10 | direct doctor invocation | no |
| AC-Sev.2 (114, JSON schema) | T2b.10 | JSON schema validation | no |
| AC-Sev.3 (114, vocab error/warning/info) | T2b.8 + T2b.9 | AST scan | no |

**MCP-required ACs**: NONE. All 36 ACs satisfiable via direct-Python invocation per spec §3 Test Execution Context.

## Risks → Plan Mitigations

| Risk | Mitigation in Plan |
|---|---|
| FM-1 (double-emit) | T1.3 (atomicity script staging) BEFORE T1.4 (FR-C-115.1 commit); T1.13 validate.sh check |
| FM-2 (doctor escalation) | T2b.9 AST scan enforces closed-set; T2b.8 integration test |
| FM-3 (B-H4 silent over-deletion) | T3b.3a/T3b.6 bounded-count tests with out-of-range fixtures (T3b.3a covers M6 ops, T3b.6 covers M7) |
| FM-4 (whitelist accidental removal) | T-DEFERRAL-CHECK runs at plan-reviewer time per spec §8 |
| FM-5 (DELETE silently dropped from 115) | T3b.5 explicit AC assertion 'count==0 post-M6' |
| R-115-1 (rebase/amend splits) | T1.13 validate.sh post-merge gate |
| R-115-2 (bounded-count residual) | Accepted trade-off (spec §7); operator-recovery path documented |
| R-115-3 (sub-package wildcard) | T2a.4/.5 explicit re-export list per rg discovery |

## Risk Acknowledgements

**Session-time risk**: 114 retro flagged 7-cluster scope as over-ambitious for single-session work. 115 has 5 clusters with inheritance reducing per-cluster cost. If session time runs out mid-Tier-3, drop B-H3 first then B-H4. Floor (C+E+E.2) is achievable in 2-3 hours of focused implementation; Tier 3 adds 1-2 hours more.

**MCP unavailability**: Implement runs without MCP entity-registry (M12 stub-trap state). All tests use direct-Python invocation per spec §3 Test Execution Context. The end-to-end MCP-mediated tests (`test_register_entity_handler_concise_message` and similar) continue to pass via existing test infrastructure.

**Test fixture sweep absent**: Per spec §6 Non-Goals, 114 FR-C.5 (test sweep) deferred to 116. 115 does NOT touch `_PERMITTED_TEST_FILES` or `check_status_write_path.py:37` whitelist. Plan-reviewer enforces via grep guard at end of this document.

## Plan-Reviewer Guard (deferred-to-116 protection)

Per spec §8 Plan-phase guard:
```bash
grep -iE "(FR-C\.4|FR-C\.5|_PERMITTED_TEST_FILES|check_status_write_path\.py:37|AST whitelist|test-fixture sweep|whitelist removal|_PERMITTED_ENCLOSING_DEFS)" docs/features/115-pd-data-model-followups/tasks.md
```
MUST return 0 hits. plan-reviewer asserts this when reviewing tasks.md.

## References

- Spec: `docs/features/115-pd-data-model-followups/spec.md`
- Design: `docs/features/115-pd-data-model-followups/design.md`
- 114 spec rev 4 (inherited): `docs/features/114-pd-data-model-hardening/spec.md`
- 114 design rev 2 (inherited): `docs/features/114-pd-data-model-hardening/design.md`
