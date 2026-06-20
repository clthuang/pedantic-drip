# PRD: F117 — pd Post-F116 Production Hygiene

## Status
- Created: 2026-05-18
- Last updated: 2026-05-18
- Status: Approved (brainstorm-reviewer 2026-05-18 — 0 blockers, 2 cosmetic suggestions applied as rev 2.2)
- Problem Type: Technical/Architecture
- Archetype: fixing-something-broken
- Mode: YOLO (Stage 1 CLARIFY + Stage 2 RESEARCH skipped per user — empirically pinned via doctor JSON + entity DB queries at session start)

## Problem Statement

After F116 closed F115's 8 HIGH carry-forwards, a post-merge audit (doctor JSON output + entity DB queries, 2026-05-18) surfaced **5 actionable items** that the F116 retro identified but did not address (out of scope for coverage-only feature):

1. **Production bug** in `_fix_triage_cross_workspace_link` re-attribute branches (caught by F116 TC.4 but deliberately masked in fixture).
2. **2 doctor "errors"** that are stale check-constants (db_readiness expects schema 11, actual 17; memory_health expects 4, actual 7) — false positives.
3. **21 cross-workspace `parent_uuid` links** still warning-only post-F115 (blocked on item 1's triage tool being broken).
4. **4 stuck-active brainstorms** that never transitioned to `promoted` (F114/F115/F116 brainstorm sources + 1 older).
5. **~261 doctor warnings** (132 `feature_status` + 129 `workflow_phase`) from 3 sessions of MCP-unavailable drift accumulating across F108-F116.

F117 bundles all 5 into 3 themes that share a common character (state-reconciliation + version-pin debt; small fixes). Scope discipline: **no new MCP tools, no new migrations, no new exception classes** — F117 adds one bug-fix in an existing function (Theme A) + mechanical test sweep (Theme B) + operational invocations (Theme C). Theme A's bug-fix is genuinely new code surface but is bounded to the existing `_fix_triage_cross_workspace_link` function body.

### Evidence

- Doctor output 2026-05-18: **537 issues** (2 error / 534 warning / 1 info) — Evidence: `python -m doctor` JSON
- `db_readiness` actual=17 vs expected=11 — Evidence: doctor message "Entity DB schema_version is 17, expected 11"
- `memory_health` actual=7 vs expected=4 — Evidence: doctor message "Memory DB schema_version is 7, expected 4"
- `_fix_triage_cross_workspace_link` issues `UPDATE entities SET workspace_uuid = ?` at lines 472-482 without dropping `enforce_immutable_workspace_uuid` trigger — Evidence: `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:472-482` + F116 retro production-gap appendix
- Correct pattern exists at `claim_unknown_entities:7956-7975` — Evidence: `plugins/pd/hooks/lib/entity_registry/database.py:7956-7975`
- 4 stuck-active brainstorms — Evidence: `sqlite3 entities.db "SELECT entity_id, status FROM entities WHERE kind='brainstorm' AND status='active'"` returns 4 rows
- 21 cross-workspace links unchanged from F115-time pin — Evidence: doctor `cross_workspace_parent_uuid` count = 21
- F115 retro KB candidate #6 predicted "Test sweep cost grows linearly with migration registrations" — F116 incurred 14 sites for 1 check; F117 will incur 2 doctor checks + ~30 test assertions

## Goals

1. **Restore triage tool to production-working state** — Theme A: `_fix_triage_cross_workspace_link` re-attribute branches survive against trigger-active DB.
2. **Eliminate version-pin debt** — Theme B: doctor checks + ~30 test assertions use `max(MIGRATIONS.keys())` dynamically. F115 retro KB candidate #6 finally landed.
3. **Flush accumulated MCP-drift state** — Theme C: `reconcile_apply` to clear 261 doctor warnings; 4 brainstorms transitioned; 21 cross-workspace links triaged.

## Success Criteria

- [ ] `_fix_triage_cross_workspace_link` re-attribute branches succeed against a trigger-active fixture (new regression test that does NOT drop the trigger in setup).
- [ ] Trigger is restored to its captured SQL definition after the UPDATE (post-condition: `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` returns the snapshotted text — genuinely byte-identical because the fix function re-issues the captured text rather than a hand-written CREATE TRIGGER).
- [ ] Existing F116 TC.4 tests pass unchanged (no behavior regression — they explicitly drop the trigger so the new logic is a no-op for them).
- [ ] `db_readiness` doctor check uses `max(MIGRATIONS.keys())` for `entity_registry`; emits OK (severity=info) when actual matches dynamic expected.
- [ ] `memory_health` doctor check uses `max(MIGRATIONS.keys())` for `semantic_memory`; emits OK when matches.
- [ ] All hardcoded `schema_version == "N"` assertions in `test_database.py` (entities + semantic_memory) replaced with `max(MIGRATIONS.keys())` references.
- [ ] All hardcoded `len(CHECK_ORDER) == N` assertions in `test_checks.py` replaced with dynamic references (length comparison via the canonical pinned list, not a magic number).
- [ ] `reconcile_check` dry-run captured + reviewed (no destructive writes without explicit acknowledgment).
- [ ] `reconcile_apply` invoked successfully.
- [ ] 4 stuck-active brainstorms transitioned to `promoted` status via `update_entity`.
- [ ] 21 cross-workspace links triaged via `_fix_triage_cross_workspace_link` invocations (interactive mode — operator picks per link; YOLO break authorized per YOLO Mode Exceptions below).
- [ ] Doctor post-F117: 0 errors. Total issues reduction ≥ 280 (≥261 from reconcile + 21 from triage + auto-resolved orphans where they share root cause with phase drift). Reduction count is rationale-grounded (not an arbitrary final-count threshold).
- [ ] `validate.sh` 0 errors after F117.
- [ ] F115 + F116 regression: 0 tests fail in F115/F116 scope after F117 lands.

## User Stories

### Story 1: Restore Triage Tool to Working State
**As a** pd plugin operator running `pd doctor --fix` against a production entities.db **I want** the cross-workspace re-attribute branches to actually succeed **So that** I can clear the 21 cross-workspace links without manually editing the DB.
**Acceptance criteria:**
- `re-attribute parent` and `re-attribute child` choices succeed against any post-Migration-11 DB.
- `enforce_immutable_workspace_uuid` trigger is restored byte-identical after the UPDATE.
- Existing TC.4 tests + adversarial FR-9 tests continue passing.

### Story 2: Doctor Version Pinning + Test Fixture Sweep
**As a** pd maintainer adding migrations or doctor checks **I want** hardcoded `schema_version == "N"` and `len(CHECK_ORDER) == N` assertions to use `max(MIGRATIONS.keys())` dynamically **So that** future migrations don't require linear sweep cost (per F115 retro KB candidate #6 + F116 cost evidence: 14 sites for 1 check).
**Acceptance criteria:**
- `db_readiness` and `memory_health` checks use `max(MIGRATIONS.keys())`.
- All ~30 hardcoded version sites converted (verify via grep returning 0 remaining hardcoded `schema_version == "N"` outside production migrations themselves).
- Pytest 0 regressions.

### Story 3: State Reconciliation Flush
**As a** pd maintainer **I want** `reconcile_apply` + targeted brainstorm + triage cleanup **So that** post-F117 doctor reports < 50 issues (down from 537) and the entity DB matches `.meta.json` source-of-truth across all features.
**Acceptance criteria:**
- `reconcile_check` dry-run captured; diff reviewed for unexpected writes.
- `reconcile_apply` reports >250 fixes.
- 4 brainstorms transitioned (`update_entity status='promoted'`).
- 21 cross-workspace links triaged (operator-chosen per link, interactive).
- Post-F117 doctor < 50 issues.

## Use Cases

### UC-1: Trigger-active re-attribute (Theme A core)

**Actors:** pd doctor `--fix` operator | **Preconditions:** entities.db has `enforce_immutable_workspace_uuid` trigger active; a cross-workspace link exists.

**Flow:**
1. Operator runs `pd doctor --fix`; doctor surfaces cross-workspace link warning.
2. Harness presents 4-choice triage; operator selects "re-attribute parent".
3. `_fix_triage_cross_workspace_link` enters re-attribute branch.
4. **NEW:** Function opens a savepoint, drops `enforce_immutable_workspace_uuid` trigger, issues `UPDATE entities SET workspace_uuid = ?`, recreates the trigger from its canonical SQL definition, commits the savepoint.
5. Doctor re-runs cross-workspace check; violation cleared.

**Postconditions:** Parent's `workspace_uuid` matches child's; trigger exists with byte-identical SQL definition.

**Edge cases:**
- SQL error mid-UPDATE → savepoint rollback restores trigger + original parent_uuid.
- Recreating trigger fails (e.g., trigger name already exists due to partial rollback) → outer transaction rolls back; explicit error message: "Trigger restoration failed; DB rolled back to pre-update state. Manual recovery required."
- Concurrent writer → savepoint deadlock or sqlite3.OperationalError; propagates uncaught.

### UC-2: Dynamic doctor version check (Theme B core)

**Actors:** Session-start doctor invocation | **Preconditions:** Both DBs at current schema_version (17 entities, 7 memory).

**Flow:**
1. `db_readiness` reads actual `_metadata.schema_version` (= 17).
2. Computes expected via `from entity_registry.database import MIGRATIONS; max(MIGRATIONS.keys())` (= 17).
3. Actual == expected → emit `Issue(severity='info', message='Entity DB schema_version 17 matches expected')` OR no issue.
4. Same for `memory_health` with semantic_memory MIGRATIONS.

**Postconditions:** Doctor's 2 stale-version errors eliminated; check is forward-compatible with any future migration without code change.

### UC-3: Reconcile flush (Theme C core)

**Actors:** pd maintainer | **Preconditions:** MCP entity-server available (was unavailable across F114-F116; available 2026-05-18).

**Flow:**
1. Operator runs `reconcile_check` (dry-run) via MCP.
2. Output captured to retro for review (counts of feature_status + workflow_phase + entity_orphan corrections).
3. If diff acceptable → `reconcile_apply` invoked.
4. Apply reports >250 entity status / phase updates.
5. Operator runs `update_entity` 4 times for stuck brainstorms.
6. Operator runs `_fix_triage_cross_workspace_link` 21 times for cross-workspace links (interactive).
7. Final doctor invocation: < 50 issues; severity_summary `{error: 0, warning: <50, info: ~3}`.

**Postconditions:** Entity DB ↔ `.meta.json` consistency restored; 4 brainstorms in correct lifecycle state; 21 cross-workspace links either re-attributed, deleted, or grandfathered per operator judgment.

**Edge cases:**
- `reconcile_apply` produces unexpected writes (e.g., archives a still-active feature) → operator intervention required; YOLO break acceptable.
- Triage tool refuses a re-attribute mid-loop due to a different trigger we didn't anticipate → flagged as separate finding; remaining links continue processing.

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Re-attribute UPDATE fails mid-tx after trigger drop | Savepoint rollback restores trigger AND original parent_uuid | Atomicity invariant; the trigger MUST never be missing post-tx |
| Trigger recreation fails (e.g., name collision) | Outer tx rollback; explicit error; operator manual recovery | Catastrophic case but recoverable; don't silently leave DB without the immutability guard |
| `reconcile_apply` reports > 500 changes | Pause + ask operator (interactive break of YOLO) | Magnitude indicates either accumulated drift OR a bug; user judgment needed |
| Doctor version constants accidentally use semantic_memory MIGRATIONS for entity_registry check (or vice versa) | Test asserts each check imports from the right module | Common copy-paste error |
| `max(MIGRATIONS.keys())` returns 0 (empty dict during pytest hot-reload edge) | Check emits Issue with severity='warning', not 'error' | Don't conflate "couldn't read" with "schema drift" |
| Cross-workspace link triage encounters a link where both workspaces are valid | Operator selects "grandfather" with reason; allowlist row inserted | Existing F115 workflow; no new behavior |
| Brainstorm status update fails (entity not found) | Log warning; continue | Brainstorm slug may have changed; recovery via re-promotion |

## Constraints

### Behavioral Constraints (Must NOT do)

- **Must NOT introduce new MCP tools** — Theme A/B/C are all use existing tools.
- **Must NOT introduce new migrations** — schema unchanged; only check + test references updated.
- **Must NOT introduce new exception classes** — re-attribute fix uses existing `RuntimeError` / `ValueError` semantics + sqlite3 errors.
- **Must NOT change F115/F116 invariants** — atomicity post-merge gate, severity_summary, 4-triage branches all preserved.
- **Must NOT change `CHECK_ORDER` sequence** — F116's 20-name byte-identical order preserved.
- **Must NOT delete the `enforce_immutable_workspace_uuid` trigger permanently** — Theme A drops + recreates within a single transaction.
- **Must NOT remove F115's `--db` flag from `recompute_source_hash.py`** — out of scope; F115 retro LOW sidecar item #1 if revisited.

### Technical Constraints

- Python ≥ 3.12 (per `pyproject.toml`) — Evidence: F116 spec rev 7
- SQLite 3.35+ for migrations — Evidence: F115 design rev 2
- pytest framework — Evidence: existing test infrastructure
- Trigger recreation SQL MUST be byte-identical to the original `CREATE TRIGGER enforce_immutable_workspace_uuid` definition — Evidence: `database.py` trigger definition source

## Requirements

### Functional

- **FR-A.1 (Re-attribute trigger-drop wrapper):** `_fix_triage_cross_workspace_link` re-attribute branches MUST adopt — and strengthen — the trigger drop/recreate sequence demonstrated at `claim_unknown_entities:7956-7975`. The reference function uses an inline `DROP TRIGGER IF EXISTS … / try / UPDATE / finally / CREATE TRIGGER IF NOT EXISTS …` pattern with a *hardcoded* trigger SQL literal. F117 strengthens that pattern by replacing the hardcoded literal with `sqlite_master` capture/replay: (a) before drop, snapshot the trigger's original SQL via `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'`; (b) `DROP TRIGGER IF EXISTS`; (c) issue the `UPDATE` inside a `try`; (d) in the `finally`, re-issue the snapshotted SQL via `conn.execute(snapshot_sql)` so the recreate fires even if the UPDATE fails. **Rationale for strengthening:** the reference's hardcoded literal would silently diverge from `database.py`'s canonical CREATE TRIGGER source if that source is ever edited; capture/replay guarantees true byte-identity against the live trigger definition at call time. Using `CREATE TRIGGER IF NOT EXISTS` with a hand-written body is **NOT** acceptable for FR-A.1 — must re-issue the exact captured SQL string. (Future hygiene: backport this same capture/replay strengthening into `claim_unknown_entities` is a candidate for the F117 retro KB, not in F117 scope.)
- **FR-A.2 (Atomicity invariant):** A SQL error mid-UPDATE MUST result in the trigger being restored. The `try/finally` ensures recreate fires; the outer transaction rollback (when M-level mode is wrapped in `BEGIN ... COMMIT`) ensures parent_uuid is unchanged. A `pytest.raises(Exception)` test must verify post-condition: trigger exists with the snapshotted SQL + parent_uuid unchanged.
- **FR-A.3 (Regression test against trigger-active DB):** New test `test_re_attribute_against_trigger_active_db` MUST NOT drop the trigger in fixture (inverts F116 TC.4 fixture polarity which masked this bug). Asserts re-attribute succeeds; `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` post-update matches pre-update verbatim (semantically equivalent via captured-SQL replay — genuinely byte-identical because we re-issue the captured text).
- **FR-A.4 (Existing F116 test compatibility):** F116 TC.4 re-attribute tests MUST continue passing without modification (they drop the trigger in fixture, so the new logic is a no-op for them — verify via test re-run post-F117).

- **FR-B.1 (Dynamic doctor version constants):** `db_readiness` MUST use `max(MIGRATIONS.keys())` from `entity_registry.database` for its expected version. `memory_health` MUST do the same from `semantic_memory.database`. Hardcoded `ENTITY_SCHEMA_VERSION=11` and `MEMORY_SCHEMA_VERSION=4` constants at `checks.py:14-15` removed. **Use lazy import** (inside the check function body, not module-level) to avoid any potential circular-import risk with `doctor` → `entity_registry`/`semantic_memory`. Verify via `pytest --collect-only` after change.
- **FR-B.2a (Convert current-schema sanity asserts to dynamic):** Hardcoded `schema_version == "<latest>"` assertions in `plugins/pd/hooks/lib/{entity_registry,semantic_memory}/test_database.py` that exist to verify "current state matches latest migration" MUST use `max(MIGRATIONS.keys())` reference. Estimated 6-10 sites total (will be enumerated at spec time via grep).
- **FR-B.2b (Preserve migration-safety pinned sites):** Historical-version assertions that intentionally pin to a specific migration version to exercise upgrade paths MUST remain hardcoded. The canonical examples — verified 2026-05-18 via grep — live in `plugins/pd/hooks/lib/entity_registry/test_migration_13_safety.py`:
    - Line 194: `assert v is not None and v[0] == "13", f"schema_version drifted on replay: {v}"` (post-replay drift check)
    - Line 205: `assert v is not None and v[0] == "13", f"Expected schema_version=13; got {v}"` (post-migration stamp)
    - Line 224: `assert stamp_idx >= 0, "migration 13 must stamp schema_version=13"` (static source check)

    Similar sites exist in `test_migration_14_safety.py` and `test_migration_safety.py` (enumeration deferred to spec phase). These assertions pin to a specific migration's terminal version and are LOAD-BEARING for migration safety — substituting `max(MIGRATIONS.keys())` would mask the very drift they exist to catch.

    Setter statements such as `"INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '12')"` in test fixture setup (e.g., `test_migration_13_safety.py:70, 88`) are NOT in the sweep regex — they don't match `schema_version\s*==\s*"N"` — so no special exclusion needed. They appear in the iteration-1 reviewer's flag (`test_database.py:4573/6743/8164/8215`) only because the reviewer pattern-matched on the string `'schema_version'`, not on the assertion form; correction propagated here.

    Spec phase MUST enumerate every assertion-form site via grep `'schema_version\s*==\s*"(1[0-9]|[0-9])"'` and review-decision each: dynamic OK (FR-B.2a) vs migration-safety pin (FR-B.2b).
- **FR-B.3 (CHECK_ORDER assertion verification):** Verify zero hardcoded `len(CHECK_ORDER) == N` patterns remain via `grep -rn 'len(CHECK_ORDER)\s*==\s*\d' plugins/pd` → expect 0 matches. The canonical CHECK_ORDER pin lives at `test_doctor.py:14-39` as an explicit name list (NOT a `len() == N` magic number); F117 does NOT modify `CHECK_ORDER` (per NFR-5) so this list assertion remains unchanged. F116 retro reported 14 sites swept (per ".meta.json implement notes") — those were `len(report.checks) == 19` assertions in `test_checks.py` that F116's TA implementer already converted to `== 20`. F117's job is to verify they're now consistent + add a doctor count check (`max(MIGRATIONS.keys())`-style) if any remain.
- **FR-B.4 (AST check forward-compat):** F115's `check_audit_counter_write_path` AST check MUST continue passing; it's source-code-level so dynamic version migration doesn't affect it.

- **FR-C.1 (Reconcile dry-run capture):** `reconcile_check` invoked first; output captured to `docs/features/117-post-f116-hygiene/reconcile-dry-run.json` for retro reference.
- **FR-C.2 (Reconcile apply):** `reconcile_apply` invoked; post-apply doctor check confirms < 50 remaining issues.
- **FR-C.3 (Brainstorm transitions):** 4 specific brainstorms transitioned via `update_entity(type_id=..., status='promoted')`. Specific brainstorm IDs (verified 2026-05-18 via `sqlite3 ~/.claude/pd/entities/entities.db "SELECT entity_id FROM entities WHERE kind='brainstorm' AND status='active'"`): `20260516-210137-pd-followups`, `20260516-184258-pd-data-model-hardening`, `20260517-053927-f115-qa-deferred`, `20260327-050000-phase-transition-summary`.
- **FR-C.4 (Cross-workspace link triage — operator interactive):** `_fix_triage_cross_workspace_link` invoked for each of 21 links. Interactive mode (YOLO break authorized per YOLO Mode Exceptions) — operator selects per link. Post-triage acceptance: `remaining_cross_workspace_count == new_allowlist_row_count` (i.e., the only remaining cross-workspace links are those the operator explicitly grandfathered with allowlist rows; the rest are deleted or re-attributed). This is a falsifiable invariant; a count threshold like "< 5" was rejected because it lacks rationale.
- **FR-C.5 (Post-fix doctor sanity check):** Doctor invoked; total issues < 50; 0 errors; severity_summary present.

### Non-Functional

- **NFR-1:** All tests run under `plugins/pd/.venv/bin/python -m pytest`.
- **NFR-2:** `validate.sh` 0 errors after F117.
- **NFR-3:** Theme A test additions stay focused on regression coverage (~3-7 new tests covering: trigger-active re-attribute success, post-update trigger SQL pin, mid-UPDATE rollback safety, trigger recreation failure, optional concurrent-writer behavior). Theme B is mechanical refactor — no new tests required, ~10 sites converted (per FR-B.2a count; final number determined at spec phase).
- **NFR-4:** No new config keys.
- **NFR-5:** Doctor check count remains 20 (F116 added the 20th; F117 does not add or remove).

## Non-Goals

- **NOT investigating 250 `entity_orphans`** — most should auto-resolve via reconcile; remainder is separate scope.
- **NOT closing 20 open F088/F089 backlog items** — all LOW; separate scope; some may be obsolete.
- **NOT addressing 17 F116 MED test-deepener findings** — separate scope (F118 candidate).
- **NOT releasing v4.18.3** — release triggered manually after F117 lands on develop (matches F116 pattern).
- **NOT changing M15 INSERT-OR-REPLACE semantics** — F116 documented this; out of scope.
- **NOT removing `enforce_immutable_workspace_uuid` trigger** — production safety guard; only temporarily dropped within a transaction.

### YOLO Mode Exceptions

- **Theme C cross-workspace triage loop authorizes interactive operator decisions** (one decision per link × 21 links). This is the existing F115 triage UX by design; not a YOLO violation. Expected wall-clock: 5-15 min.
- **`reconcile_apply` magnitude > 500 changes** authorizes a one-time operator review pause before applying. Diff captured for retro.

## Out of Scope (This Release)

- **Entity_orphan investigation** — 250 warnings; needs targeted analysis of valid vs invalid parents. Future F118 candidate after reconcile flush reduces count.
- **Backlog F088/F089 cleanup** — 20 LOW items from April 2026; separate hygiene pass.
- **F116 MED test-deepener gaps** — separate coverage feature (F118 candidate with single coverage-matrix FR per F116 retro Tune #5).

## Research Summary

*(Skipped per YOLO mode — all evidence empirically pinned via doctor JSON + entity DB queries at session start 2026-05-18.)*

### Codebase Analysis (verified at session start)

- F116 retro: `docs/features/116-f115-qa-deferred/retro.md` (production gap appendix + KB predictions)
- F116 spec: `docs/features/116-f115-qa-deferred/spec.md` (FR-7 + FR-9 semantics)
- F115 retro: `docs/features/115-pd-data-model-followups/retro.md` (KB candidate #6: dynamic fixture refactor)
- F115 design: `docs/features/115-pd-data-model-followups/design.md` (C13/C14 cross-workspace components)
- F117 source: `docs/brainstorms/117-pd-post-f116-hygiene-source.md`
- Production fix function: `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:472-482`
- Correct pattern reference: `plugins/pd/hooks/lib/entity_registry/database.py:7956-7975` (`claim_unknown_entities`)

### Existing Capabilities

- F116 `_fix_triage_cross_workspace_link` + `_normalize_and_validate_fix_hint` — reused; only the re-attribute SQL pattern changes.
- F116 `_make_fix_ctx` test helper — reused for FR-A.3 regression test.
- `reconcile_apply` MCP tool — available now (MCP entity-server reachable post plugin reload).
- `update_entity` MCP tool — available.
- F115 `MIGRATIONS` module-level dicts — entry point for FR-B dynamic constants.

## Strategic Analysis

*(Inline risk assessment per F115/F116 pattern.)*

### Risk Assessment

- **HIGH — Theme A regression test must reproduce production behavior.** F116 TC.4 drops the trigger in fixture; that masked the bug. Mitigation: invert fixture polarity — new test does NOT drop the trigger.
- **MED — Theme B sed-replace risk:** ~40 sites; could miss patterns. Mitigation: grep verification post-sweep (assert 0 matches for hardcoded patterns).
- **MED — `reconcile_apply` could produce unexpected writes.** Mitigation: dry-run via `reconcile_check` first; capture diff to retro.
- **MED — 21 cross-workspace link triage requires YOLO break.** Mitigation: explicit operator interactive step; YOLO break is acceptable per F116 retro's note that triage UX is operator-decision by design.
- **LOW — Trigger recreation SQL drift.** Mitigation: compare post-tx trigger definition byte-for-byte against pre-tx via `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'`.

## Review History

### Review 1 (2026-05-18 — prd-reviewer iteration 1)

**Findings:**
- [blocker] Framing contradiction: "no new functional surface" vs Theme A code-surface change
- [blocker] FR-B.3 site count (~14+16) fabricated — grep returns 0 for `len(CHECK_ORDER) == N`
- [blocker] FR-B.2 blanket sweep would corrupt migration-safety tests (e.g., entity_registry test_database.py:4573, 6743, 8164, 8215)
- [warning] FR-A.1 atomicity ambiguous (savepoint vs try/finally)
- [warning] Byte-identical trigger SQL over-specified
- [warning] Theme C YOLO break not explicitly authorized
- [warning] FR-B.1 module-level import circular-risk
- [warning] Success Criteria < 50 issues arithmetic unclear given 250 orphans OUT of scope
- [suggestion] FR-C.3 brainstorm IDs lack Evidence provenance
- [suggestion] NFR-3 ≤ 5 test cap leaves no headroom
- [suggestion] ATTACH DB edge case missing
- [suggestion] FR-B.3 in F116 was 14 sites of `len(report.checks) == 19` (different pattern), not CHECK_ORDER pin

**Corrections Applied:**
- Reworded problem statement: scope discipline = "no new MCP tools/migrations/exception classes" + acknowledgment that Theme A is bounded new code surface — Reason: blocker on framing contradiction
- Split FR-B.2 → FR-B.2a (current-schema sanity → dynamic) + FR-B.2b (allowlist intentional migration-safety pins) with explicit pinned-line enumeration deferred to spec phase — Reason: blocker on blanket sweep corruption
- Rewrote FR-B.3 to "verify zero hardcoded patterns remain (grep: 0 currently); the F116 sweep was `len(report.checks) == 19` → ==20 in test_checks.py, a different pattern" — Reason: blocker on fabricated count
- Rewrote FR-A.1 + FR-A.2 + FR-A.3 to use the captured-SQL replay pattern from `claim_unknown_entities:7956-7975` with try/finally semantics — Reason: warning on atomicity ambiguity + byte-identical claim
- Added YOLO Mode Exceptions section under Non-Goals authorizing Theme C operator-interactive triage + reconcile_apply review pause — Reason: warning on Theme C YOLO break
- FR-B.1 specifies lazy import to avoid circular risk — Reason: warning on module-level import
- Success Criteria threshold changed from "< 50 issues" to "reduction ≥ 280" (rationale-grounded) — Reason: warning on arithmetic
- FR-C.3 added Evidence query — Reason: suggestion on provenance
- NFR-3 dropped hard cap, kept focus narrative — Reason: suggestion on test count headroom
- FR-C.4 acceptance changed from "< 5 remaining" to "remaining_cross_workspace_count == new_allowlist_row_count" (falsifiable invariant) — Reason: warning on Success Criteria measurability
- Skipped: ATTACH DB edge case (low-likelihood, defensive only; defer to spec phase if pursued)

### Review 2 (2026-05-18 — prd-reviewer iteration 2)

**Findings:**
- [warning] FR-A.1 claims pattern-match with `claim_unknown_entities:7956-7975`, but verification shows the reference uses inline `CREATE TRIGGER IF NOT EXISTS` with hardcoded SQL — exactly the form FR-A.1 explicitly forbade. The captured-SQL replay is a *stricter* pattern, not a pattern-match.
- [warning] FR-B.2b cited `entity_registry/test_database.py:4573, 6743, 8164, 8215` as migration-safety pinned assertion sites that must remain hardcoded, but those lines are `INSERT INTO _metadata` setter statements (fixture setup), not assertions. The genuine migration-safety pinned assertions live at `test_migration_13_safety.py:194, 205, 224`.

**Corrections Applied (rev 2.1):**
- Reworded FR-A.1 to acknowledge the reference uses inline hardcoded SQL and frame F117's `sqlite_master` capture/replay as a *strengthening* (byte-identity against future trigger SQL drift in `database.py`). Noted potential backport to `claim_unknown_entities` as F117 retro KB candidate, not in scope — Reason: warning on framing accuracy.
- Replaced FR-B.2b's example line-number citations with the verified `test_migration_13_safety.py:194/205/224` assertion sites. Added clarification that the prior reviewer's `test_database.py:4573/6743/8164/8215` citations were INSERT setter statements (not assertions), out of sweep regex scope, no special exclusion required — Reason: warning on line-number provenance.

### Review 3 (2026-05-18 — prd-reviewer iteration 3, FINAL)

**Result:** APPROVED for promotion. 0 blockers, 0 warnings, 2 non-blocking suggestions (both flagged for spec phase awareness, no PRD changes required):

1. The prescribed sweep regex `'schema_version\s*==\s*"\d+"'` (FR-B.2b line 184) won't match the actual assertion form `db.get_metadata("schema_version") == "17"`. Spec phase should broaden enumeration regex to `'get_metadata\("schema_version"\)\s*==\s*"\d+"'` (plus `_read_schema_version\(…\)\s*==\s*"\d+"`). Verified sites: 5 in entity_registry/test_database.py (lines 370, 678, 2688, 2890, 3081) + 1-2 in semantic_memory — broadly matches FR-B.2a's "6-10 sites" estimate.
2. Line 182's example setter SQL (`INSERT OR REPLACE INTO _metadata...`) is illustrative; the actual setter at `test_database.py:4570-4574` is `INSERT … ON CONFLICT(key) DO UPDATE SET value = excluded.value`. Both are setter-equivalent, neither matches the assertion sweep regex; the substance of FR-B.2b is unaffected.

Both suggestions are spec-phase work, not PRD logic defects. Promotion proceeds.

### Review 4 (2026-05-18 — brainstorm-reviewer Stage 6 gate)

**Result:** APPROVED for promotion. 0 blockers, 0 warnings, 2 cosmetic suggestions (both applied as rev 2.2):

1. Status field flipped from `Draft` → `Approved` (with reviewer provenance).
2. Removed superseded Success Criterion bullet `< 50 issues remaining` (line 52) — it conflicted with the rationale-grounded `reduction ≥ 280` criterion that replaced it in rev 1. Rewrote remaining criteria to drop the parenthetical "removed in favor of..." note (no longer needed).

Stage 6 disposition: **promote to /pd:create-feature with --prd flag**.

## Open Questions

*(All resolved inline.)*

## Next Steps

Ready for `/pd:create-feature --prd=docs/brainstorms/20260518-021209-post-f116-hygiene.prd.md` to begin implementation. Mode: Standard (per YOLO override). Merge target: `develop` (per user memory).
