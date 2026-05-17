# Plan: F116 — F115 QA-Gate Deferred Hardening

**Source design:** `docs/features/116-f115-qa-deferred/design.md` rev 4
**Source spec:** `docs/features/116-f115-qa-deferred/spec.md` rev 7
**Status:** Draft rev 1

## 1. Goal

Close 8 HIGH carry-forward items from F115's qa-override.md via 4 code-surface deltas (C16-116/C19-116/C20-116/C21-116) + ~25 parametrized tests across 7 test files. Theme A (rollup + AST vocab) → Theme B (migration regression tests) → C0 pre-implementation grep gate → Theme C (refactor + matrix + adversarial parser).

## 2. Plan Items (Themed)

### Theme A — Severity Rollup + Vocab AST

| # | Plan Item | Spec FR | Files touched | Est | Depends on |
|---|---|---|---|---|---|
| P-A.1 | Add `severity_summary` field with default_factory to DiagnosticReport; promote `elapsed_ms` to default-valued | FR-1 | `doctor/models.py` | 10 min | — |
| P-A.2 | Write integration test pinning aggregation rule + invariant `severity_summary["error"] == error_count` | FR-1 | `doctor/test_severity_summary.py` (NEW) | 25 min | P-A.1 |
| P-A.3 | Populate `severity_summary` at `DiagnosticReport(...)` construction site in `run_diagnostics` (~line 294) | FR-1 | `doctor/__init__.py` | 10 min | P-A.2 |
| P-A.4 | Write tests for FR-2 AST visitor (positive cases pass through; negative cases emit error severity) | FR-2 | `doctor/test_check_severity_vocab.py` (NEW) | 30 min | — |
| P-A.5 | Implement `check_severity_vocab.py` (new file) with `__file__`-relative source resolution + AST visitor | FR-2 | `doctor/check_severity_vocab.py` (NEW) | 25 min | P-A.4 |
| P-A.6 | Register `check_severity_vocab` at CHECK_ORDER position 20 in `doctor/__init__.py` | FR-2 | `doctor/__init__.py` | 5 min | P-A.5 |

### Theme B — Migration Regression Coverage

| # | Plan Item | Spec FR | Files touched | Est | Depends on |
|---|---|---|---|---|---|
| P-B.1 | Add `_build_memory_db_at_v5` + `_build_memory_db_at_v6` + `_seed_tool_failure_rows` + `_seed_inflated_import_rows` helpers (with `source_hash` NOT NULL column) | FR-3, FR-4 | `semantic_memory/test_database.py` | 30 min | — |
| P-B.2 | Implement T3b.3a (parametrized bounded-count abort: above + below cases) | FR-3 | same | 15 min | P-B.1 |
| P-B.3 | Implement T3b.3b (pre-freeze ratio abort: 425 pre + 25 post = 450 total) | FR-3 | same | 15 min | P-B.1 |
| P-B.4 | Implement T3b.3c (`_MidTxFailingConnection` proxy + `OperationalError` propagation + defensive `proxied._injected` assertion) | FR-3 | same | 25 min | P-B.1 |
| P-B.5 | Implement T3b.4 (M7 bounds violation: 20 import rows × observation_count=200) | FR-4 | same | 15 min | P-B.1 |
| P-B.6 | Add `_build_entities_db_at_v14` helper + T1.10 (M15 INSERT-OR-REPLACE reset semantics; uses `isolation_level=None` to avoid M15 BEGIN IMMEDIATE collision) | FR-5 | `entity_registry/test_database.py` | 25 min | — |

### Theme C0 — Pre-Implementation Audit Gate (BLOCKING)

| # | Plan Item | Spec FR | Files touched | Est | Depends on |
|---|---|---|---|---|---|
| P-C0.1 | Run FM-2 grep audit: `grep -rno "fix_hint=" plugins/pd/hooks/lib/doctor/ \| awk -F: '{print length($0)}' \| sort -n \| tail -1`. If observed > 800 bytes, raise `_MAX_LEN` cap above 1024 before C21-116 implementation. | FR-9 (precondition) | (audit only — no file change) | 5 min | (none) |
| P-C0.2 | Run FM-7 grep audit: `grep -c "_parse_triage_choice(" plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` — expect 2 (definition + 1 call). If > 2, expand FR-9 integration to all call sites. | FR-9 (precondition) | (audit only) | 5 min | (none) |

### Theme C — Cross-Workspace Coverage Completeness

| # | Plan Item | Spec FR | Files touched | Est | Depends on |
|---|---|---|---|---|---|
| P-C.1 | Refactor: move `check_cross_workspace_parent_uuid` from `checks.py:2259` to new `check_cross_workspace_parent_uuid.py` (verbatim body + minimum imports) | FR-8 | `doctor/checks.py`, `doctor/check_cross_workspace_parent_uuid.py` (NEW), `doctor/__init__.py` | 15 min | C0 |
| P-C.2 | Add CHECK_ORDER preservation regression test pinning full 20-name byte-identical sequence | FR-8 | `doctor/test_doctor.py` | 10 min | P-C.1, P-A.6 |
| P-C.3 | Write tests for FR-6: 9-case parametrized matrix (3 handlers × 3 ACs); add `entity_db` session-scoped fixture + 3 pair fixtures returning dict-shape `{parent:{type_id,uuid}, child:{type_id,uuid}}` | FR-6 | `entity_registry/test_cross_workspace_matrix.py` (NEW) | 40 min | C0 |
| P-C.4 | Write tests for FR-7: 4-decision triage tests + grandfather-no-reason + unknown-choice negative; add `_make_fix_ctx` helper | FR-7 | `doctor/test_fix_actions.py` (NEW) | 30 min | C0 |
| P-C.7a | Write FR-9 adversarial tests FIRST (TDD red): nul, cyrillic, shell-metas in uuid, $/backtick/semicolon-&/parens in reason, over-length, unknown-segment. Each asserts ValueError from `_normalize_and_validate_fix_hint`. **Tests fail at this point (helper not yet implemented).** | FR-9 | `doctor/test_fix_actions.py` (extended) | 20 min | C0, P-C.4 |
| P-C.5 | Implement `_normalize_and_validate_fix_hint` helper in `fix_actions/__init__.py` (segment-aware grammar: UUID-like, choice-allowlist, reason-denylist `[\x00-\x1f;&()`$\\]`). **Re-run P-C.7a tests — expect all pass (TDD green).** | FR-9 | `fix_actions/__init__.py` | 25 min | P-C.7a |
| P-C.6 | Wire normalizer into `_fix_triage_cross_workspace_link` (line 445: pass normalized string to `_parse_triage_choice`). **Re-run P-C.4 FR-7 tests — verify they still pass with normalizer in the path; the legitimate reason "operator approved cross-org link" satisfies the new denylist (no chars in `[\x00-\x1f;&()`$\\]`).** | FR-9 | `fix_actions/__init__.py` | 5 min | P-C.5 |
| P-C.7b | Write AC-9.3 happy-path regression test `test_fr9_legitimate_grandfather_with_reason_preserves_behavior` — confirms wiring did not break the legitimate-grandfather path. | FR-9 | `doctor/test_fix_actions.py` (extended) | 5 min | P-C.6 |

### Closure

| # | Plan Item | Spec FR | Files touched | Est | Depends on |
|---|---|---|---|---|---|
| P-Z.1 | Append F116 carry-forward resolution table to F115's qa-override.md (commits referenced) | (spec §10) | `docs/features/115-pd-data-model-followups/qa-override.md` | 5 min | All Themes A/B/C |
| P-Z.2 | Run `./validate.sh` + full pytest; assert 0 errors, no F115 regressions | AC-Validate, AC-Regress | (verification only) | 10 min | All |

## 3. Total Estimate

~5 hours of implementation work. Reasonably-sized parallel batches: P-A.{1,2,4} can run together; P-B.{1,6} can run together; P-C.{1,3,4} can run together; P-C.{5,6,7} serialize (parser implementation feeds adversarial tests).

## 4. Risks (carried from design §6)

| # | Risk | Mitigation in plan |
|---|---|---|
| R-1 | Forgotten `severity_summary` population at construction site | P-A.2 invariant test runs before P-A.3 implementation (TDD) |
| R-2 | FR-8 refactor disturbs CHECK_ORDER ordering | P-C.2 regression test pins full 20-name sequence |
| R-3 | FR-9 over-length cap rejects legitimate fix_hint | P-C0.1 grep audit raises cap if needed BEFORE P-C.5 |
| R-4 | FR-9 grammar tightens reason field behavior | P-C.7 includes AC-9.3 happy-path regression test |
| R-5 | Migration fixture compile fails | P-B.1 lands before P-B.{2,3,4,5} so fixtures are verifiable in isolation |
| R-6 | `_seed_tool_failure_rows` IntegrityError on NOT NULL columns | P-B.1 fixture body uses verified column list including `source_hash` |
| R-9 | M15 transaction collision | P-B.6 uses `isolation_level=None` per spec rev 7 fix |

## 5. TDD Order Compliance

All Theme A/B/C plan items follow TDD: tests written before implementation.

- P-A.4 (test for AST visitor) before P-A.5 (visitor implementation)
- P-A.2 (test for severity_summary invariant) before P-A.3 (population code)
- P-B.{2,3,4,5,6} are pure test additions consuming existing migration code — TDD-trivially satisfied
- P-C.4 (triage 4-decision tests) before P-C.6 (normalizer wiring — normalizer alone doesn't require P-C.4)
- P-C.7a (adversarial tests for `_normalize_and_validate_fix_hint`) BEFORE P-C.5 (helper implementation) — true TDD red→green: tests fail at P-C.7a; pass at P-C.5
- P-C.7b (AC-9.3 happy-path regression) after P-C.6 — confirms wiring preserves legitimate inputs

## 6. Out of Scope

Inherited from spec §9 — no plan items for telemetry log JSON schema pinning, no CHECK_ORDER content assertion across all sites beyond P-C.2, no dynamic `max(MIGRATIONS.keys())` refactor.
