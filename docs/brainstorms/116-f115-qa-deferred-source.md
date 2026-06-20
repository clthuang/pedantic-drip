# Feature 116 Brainstorm Source: F115 QA-Gate Deferred Hardening

**Source:** 8 HIGH findings deferred to F116 carry-forward, documented in
`docs/features/115-pd-data-model-followups/qa-override.md`. F115 landed
the full 5-cluster implementation (atomic emit invariant, cross-workspace
gates, triage tool, writer CLI quality gates, hash recompute), but the
post-merge 4-reviewer adversarial QA gate identified 8 HIGH-severity
test-coverage and observability gaps. F116 closes those gaps without
introducing new functional surface — it is a coverage + hygiene feature
sitting on top of F115's structural changes.

## Problem Statement

F115's QA gate (Step 5b 4-reviewer adversarial dispatch) flagged 2
implementation-reviewer blockers and 6 test-deepener HIGH gaps:

1. **AC-Sev.1 / AC-Sev.2 / AC-E-115.2 unmet** — doctor JSON output lacks
   a `severity_summary` rollup field. Models has `error_count` +
   `warning_count` but no aggregated `{error: N, warning: N, info: N}`
   block the spec calls for.
2. **M6 / M7 abort-path regression tests missing (T3b.3a/b/c, T3b.4)** —
   the bounded-count + identity spot-check semantics are implemented in
   `database.py` migrations and the fresh-DB no-op semantics pass via
   `test_migration_v3`, but the dedicated abort-path regression tests for
   populated-DB over-bounds (T3b.3a), identity-mismatch (T3b.3b),
   IO-error abort (T3b.3c), and M7 observation-reset abort (T3b.4)
   are not in the test suite.
3. **T2b.5 9-case cross-workspace gate matrix missing** — all 9 pairings
   of parent×child entity-type combinations for the cross-workspace gate
   need coverage (currently exercised only via steady-state happy-path
   and a single error path).
4. **T2b.8 `check_severity_vocab.py` AST check missing** — the
   closed-set severity vocabulary (`{error, warning, info}`) is enforced
   by code review only. An AST/grep check should reject any doctor check
   emitting strings outside the closed set.
5. **T2a.7 4-decision triage tests missing** — `_fix_triage_cross_workspace_link`
   has 4 decision branches (allowlist add / reparent / detach / skip);
   only one branch has happy-path coverage.
6. **T1.10 M15 preservation test missing** — M15 initializes
   `audit_log.counter` baseline; the preservation invariant (idempotent
   across re-runs, no double-counting) isn't pinned by a regression test.
7. **`check_cross_workspace_parent_uuid` inlined vs design rev 2 spec** —
   shipped as in-line predicate rather than the separately-named helper
   that design rev 2 called for. Behavior matches; structure differs.
8. **Adversarial parsing for `fix_hint`** in the triage tool — the parser
   handles documented inputs but doesn't exhaustively validate adversarial
   whitespace / unicode / shell-meta inputs. No CVE-class risk (the field
   is user-typed input that doesn't reach a shell), but defensive parsing
   is still spec-required.

These are test-completeness + observability gaps, not functional bugs.
F115 invariants hold; F116 makes them auditable + regression-proof.

## Scope (8 items in 3 themes)

**Theme A — Severity rollup + closed-set vocabulary (items 1, 4)**
- Add `severity_summary` block to `doctor` JSON output, populated from
  per-check severity counts.
- Add `check_severity_vocab.py` AST check: grep doctor check files for
  any string literal in the `severity=` position outside `{error,
  warning, info}`. Fail-fast at session-start.

**Theme B — Migration regression coverage (items 2, 6)**
- T3b.3a: M6 abort on over-bounds populated DB (count > expected_max).
- T3b.3b: M6 abort on identity-mismatch spot-check (hash collision
  beyond 5% tolerance).
- T3b.3c: M6 abort path under sqlite3 OperationalError mid-transaction.
- T3b.4: M7 observation_count reset abort on bounds violation.
- T1.10: M15 audit-counter preservation test — run M15 twice on a
  populated entities.db, assert counter unchanged on second run.

**Theme C — Cross-workspace coverage completeness (items 3, 5, 7, 8)**
- T2b.5: 9-case cross-workspace gate matrix — for each (parent_kind,
  child_kind) pair across the 3 production kinds (feature, backlog,
  brainstorm), assert the gate fires on cross-workspace link.
- T2a.7: 4-decision triage tests for `_fix_triage_cross_workspace_link`
  branches (allowlist add / reparent / detach / skip), each with
  side-effect verification.
- Extract `check_cross_workspace_parent_uuid` into a named helper in
  `doctor/checks.py` (or its own module) matching design rev 2
  structure. Pure refactor — same behavior.
- Adversarial `fix_hint` parser tests — leading/trailing whitespace,
  unicode normalization, shell metacharacters (`;|&\``), nul-byte
  injection. Reject malformed input with `InvalidFixHintError`.

## Empirical Pins (carried from F115 retro + qa-override.md)

| Pin | Source-of-truth |
|-----|-----------------|
| 19 doctor checks registered (post-F115) | `CHECK_ORDER` in `doctor/__init__.py` |
| `audit_log.counter` initialized to 0 by M15 | `database.py` M15 body |
| 3 production cross-workspace allowlist rows expected post-M17 | `migration_17_cross_workspace_allowlist` |
| F115 final merge commit | `515cfdda` |
| F115 QA gate override commit | `f9e53fb1` |

## Out of Scope (explicit Non-Goals)

- No new functional surface. F116 is coverage + observability only.
- No new migrations. The existing M15/M16/M17 are sufficient.
- No new MCP tools. Severity rollup is doctor-internal.
- No retroactive backfill of audit log. The counter starts at 0 by design.
- No changes to the cross-workspace allowlist schema or semantics.

## Risk + Resolution Strategy

1. **LOW — Test fixture sweep cost**. Adding 9-case matrix + 4-decision
   triage + M-migration abort tests could touch many fixtures.
   Mitigation: use parametrized pytest (`@pytest.mark.parametrize`)
   with table-driven test cases; one fixture, many cases.

2. **LOW — Severity vocab AST check false positives**. Doctor checks
   may construct severity strings dynamically. Mitigation: AST check
   only flags `Constant(value=...)` in `severity=` kwarg position;
   variable assignments and function calls pass through.

3. **LOW — Renaming `check_cross_workspace_parent_uuid` from inline to
   helper changes test names**. Mitigation: pure mechanical refactor;
   tests assert on output structure, not function name.

## Reference Files

F115 artifacts are the canonical evidence base — F116 spec/design should
reference rather than re-derive:

- F115 spec: `docs/features/115-pd-data-model-followups/spec.md`
- F115 design: `docs/features/115-pd-data-model-followups/design.md`
- F115 retro: `docs/features/115-pd-data-model-followups/retro.md`
- F115 qa-override: `docs/features/115-pd-data-model-followups/qa-override.md`

## Implementation Strategy

Recommended ordering for safest landing:

1. **Theme A first** (low blast radius). `severity_summary` is additive
   to JSON output; `check_severity_vocab.py` is a new file. Land both.
2. **Theme B second** (migration regression). Add abort-path tests
   without touching migration code. Pure test addition.
3. **Theme C third** (refactor + matrix coverage). Extract
   `check_cross_workspace_parent_uuid` first (mechanical refactor),
   then add 9-case matrix, 4-decision triage tests, adversarial
   `fix_hint` parser tests.

## YOLO Mode Constraints

User instructions for this feature:
- Run full ritual (brainstorm → specify → design → create-plan → implement → finish).
- Merge to develop (NEVER main).
- Compress reviewer iterations where reasonable.
- F115's `qa-override.md` is the carry-forward source-of-truth — do NOT
  re-derive the gap list.
- Skip CLARIFY/RESEARCH stages — all clarification + evidence already
  in F115 artifacts.
