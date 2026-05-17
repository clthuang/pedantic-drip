# Spec: pd Data-Model + Memory Followups (Feature 115)

**Source PRD:** `docs/features/115-pd-data-model-followups/prd.md`
**Inherits from:** `docs/features/114-pd-data-model-hardening/spec.md` rev 4 (canonical evidence base)
**Status:** Draft rev 1
**Cluster Sequencing:** C → E.2 → E → B-H3 → B-H4 (from PRD)

## 1. Problem Restated

Feature 114 fixed 3 production blockers (Cluster A M12 stub trap, Cluster D workspace fallback, Cluster B-H2 capture-hook source-file deletion) and merged on commit `c692fd16` (develop). It deferred 5 sub-clusters for risk/triage reasons. Feature 115 picks up those 5 clusters as a single bundled feature per user direction:

1. **Cluster C — audit invariant**: `db.update_entity` does not emit `entity_status_changed`; production has **0 such events out of 945 phase_events** (114-time pin; same DB state today). 17 production callers must be covered.
2. **Cluster E — cross-workspace gates**: 3 MCP write paths (`set_parent`, `add_dependency`, `add_okr_alignment`) lack the cross-workspace assertion. **21 live cross-workspace `parent_uuid` links** in production (pin re-verified 2026-05-16T21:17Z — count unchanged).
3. **Cluster E.2 — cross-workspace triage tool**: Doctor fix_action with per-link AskUserQuestion. Prerequisite for E hardening.
4. **Cluster B-H3 — writer CLI quality gates**: 91% of memory entries enter via CLI back door bypassing 20-char min / 0.95 near-dup / 0.90 dedup-merge gates.
5. **Cluster B-H4 — hash unify + 114 B-H2 follow-through**: 10→**12** entries inflated to `observation_count>100` (pin drift +2). Plus **464→468** `Tool failure:%` rows (pin drift +4). **Critical correction**: the DELETE query 114 retro said "shipped in `f60e3f58`" never executed — only the hook source file was deleted. The DELETE migration body was placed inside the deferred `_migration_6_unify_source_hash` per 114 FR-B-H2.2. Grep across the repo for `DELETE FROM entries WHERE source='session-capture'` returns **0 matches** — verified at spec time.

## 2. Inheritance Map

To avoid re-deriving content already canonical in 114, this spec INHERITS the following 114 artifacts and overrides only where 115 explicitly adjusts them. **The inherited 114 sections govern unless explicitly overridden below.**

| 114 spec section | 115 status | Reason |
|---|---|---|
| 114 §2 FR-A (M12 stub recovery, .1-.5) | **Shipped, OUT-OF-SCOPE** | Landed in 114 commit `c71dfa39` (verified: commit message line 12 references "M12 stub-trap permanent fix"). 115 does NOT re-execute. |
| 114 §2 FR-A.6 (fixtures) | **Shipped, OUT-OF-SCOPE** | Landed in `c71dfa39` alongside FR-A. |
| 114 §2 FR-M11 (M11 guard, .1) | **Shipped, OUT-OF-SCOPE** | Landed in 114 commit `c71dfa39` (verified: commit message §2 "M11 guard tightening (FR-M11.1) at database.py:1818,1899: same stub-trap-style defense"). 115 does NOT re-execute. |
| 114 §2 FR-B-H2.1 (hook source deletion) | **Shipped, OUT-OF-SCOPE** | Landed in 114 commit `f60e3f58`. |
| 114 §2 FR-B-H2.2 (`Tool failure:%` DELETE) | **CARRIED FORWARD into 115's M6 body** | Grep confirms DELETE never executed — 114 retro miscount. See §3 FR-B-H4-115.2. |
| 114 §2 FR-D (workspace fallback, .1-.4) | **Shipped, hard prerequisite for 115 FR-C** | Landed in 114 commit `7591cd2b`. Verification check enforced (see §3 FR-PRE.1). |
| 114 §2 FR-C.1 (emit insertion) | **INHERITED + extended (atomicity AC)** | See §3 FR-C-115.1/.2 below. |
| 114 §2 FR-C.2 (fail-open) | **INHERITED, no changes** | Applies as-written. |
| 114 §2 FR-C.3 (Migration 15 + audit_emit_failed_count) | **INHERITED, no changes** | Applies as-written; M15 numbering confirmed in §5 Pin O-115. |
| 114 §2 FR-C.4 (AST whitelist removal at check_status_write_path.py:37) | **DEFERRED to feature 116** | Consequence of FR-C.5 deferral (114 retro TD-7; PRD FM-4 risk-reduction). |
| 114 §2 FR-C.5 (test-fixture sweep + `_PERMITTED_TEST_FILES`) | **DEFERRED to feature 116** | FM-4 risk-reduction; PRD Non-Goal. |
| 114 §2 FR-E.1-.4 (helper + 3 gates + envelope + allowlist consult) | **INHERITED, no changes** | Apply as-written. |
| 114 §2 FR-E.5 (doctor check warning-only) | **INHERITED + extended (severity vocab)** | See §3 FR-E-115.1 below. |
| 114 §2 FR-E.6 (hard-error escalation out of scope) | **INHERITED, no changes** | Non-goal carried forward. |
| 114 §2 FR-E.7 / FR-Sev (severity_summary output JSON contract) | **INHERITED + extended (vocab pin to closed set)** | See §3 FR-Sev-115.1 below. |
| 114 §2 FR-E.2.1-.3 (triage tool: allowlist schema + UX + post-triage check) | **INHERITED** | See §3 FR-E.2-115 below (minor helper-location pin only). |
| 114 §2 FR-B-H3.1-.3 (writer CLI gates) | **INHERITED, no changes** | All sub-FRs apply as-written in 114. |
| 114 §2 FR-B-H4.1 (canonical hash on description) | **INHERITED, no changes** | Applies as-written; M6 body executes the unify. |
| 114 §2 FR-B-H4.2 (frozen manifest model) | **REPLACED with bounded-count gate** | See §3 FR-B-H4-115.1 below. Identity-fidelity loss explicitly acknowledged (§7 FM-3 residual risk note). |
| 114 §2 FR-B-H4.3 (predicate-scoped observation reset) | **INHERITED + bounded-count gate** | See §3 FR-B-H4-115.3 below. |

Acceptance criteria from 114 §3 carry forward identically EXCEPT where overridden in §4 below. Empirical pins from 114 §4 carry forward EXCEPT where re-pinned in §5 below.

## 3. Functional Requirements (115 deltas + additions)

### FR-PRE.1 — Cluster D Inheritance Verification (hard prerequisite for FR-C)

- **FR-PRE.1.1**: Before any FR-C-115 changes land, implement verifies `rg '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | wc -l` returns ≥1. Content-based check (no line-number constraint — line drift between spec time and implement time is expected per §5 Pin F.1-115). Context anchor for human readers: `rg -B5 '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | grep -q _process_complete_phase` confirms the hit is inside the `_process_complete_phase` function body. If 0 hits: ABORT — the FR-D landing has been reverted on develop, and the audit invariant work is unsafe.
- **FR-PRE.1.2**: `entity_server.py:567` and `:710` retain `_workspace_uuid or ""` per 114 retro (FR-D.2 reverted because it broke `test_register_entity_handler_concise_message`). These two sites are NOT regression targets for 115; do NOT re-apply FR-D.2.

### FR-C-115 — Audit Invariant (delta over 114 FR-C)

114 FR-C.1, FR-C.2, FR-C.3, FR-C.6, FR-C.7a, FR-C.7b, FR-C.7c apply as-written. The following 115 additions strengthen FR-C.1 to address FM-1 (double-emit risk):

- **FR-C-115.1 (atomicity, FM-1 mitigation)**: The git commit that inserts the emit in `db.update_entity` (`plugins/pd/hooks/lib/entity_registry/database.py`, exact location pinned during design) MUST also delete the F111 manual-emit block in `plugins/pd/mcp/workflow_state_server.py` (the `db.append_phase_event(event_type="entity_status_changed", metadata={"old_status", "new_status", "closed_by_uuid"})` call inside the closure_targets loop — pin re-verified 2026-05-16T21:17Z at lines 1364-1375, content-based selector preferred over line-range). Commit message MUST begin with the marker line `FR-C-115.1:` (followed by free-form summary) so the AC can locate the commit. **Verification protocol** (used by AC-C-115.1): given the commit SHA found via `git log --all --grep='^FR-C-115.1:' --pretty=format:%H | head -1`:
  - `git show <SHA> --name-only` MUST contain BOTH `plugins/pd/hooks/lib/entity_registry/database.py` AND `plugins/pd/mcp/workflow_state_server.py`.
  - `git show <SHA> -- plugins/pd/hooks/lib/entity_registry/database.py | grep -E '^\+.*append_phase_event.*entity_status_changed'` returns ≥1 line (emit added).
  - `git show <SHA> -- plugins/pd/mcp/workflow_state_server.py | grep -E '^-.*append_phase_event.*entity_status_changed'` returns ≥1 line (manual emit deleted).
- **FR-C-115.2 (atomicity guard script)**: An implement-phase guard script (one-off shell wrapper invoked manually before `git commit`, OR a local `.git/hooks/commit-msg` hook for the message-marker check — NOT the `pre-commit` framework, which only inspects staged diffs at the pre-commit stage and doesn't see commit messages) MUST run against the staged diff (`git diff --cached`) and refuse the commit if EITHER (a) the database.py addition of an `append_phase_event(...event_type="entity_status_changed"...)` block is present but the workflow_state_server.py deletion of the matching block is absent, OR (b) the deletion is present but the addition is absent. The script greps `--cached` for `+.*append_phase_event.*entity_status_changed.*$` lines in database.py and `^-.*append_phase_event.*entity_status_changed.*$` lines in workflow_state_server.py; requires both. The script also asserts the commit message begins with `FR-C-115.1:` per FR-C-115.1 verification protocol (via `commit-msg` hook or manual wrapper). Plan-phase task list MUST encode this as a single atomic task, not two.
- **FR-C-115.3 (FR-C.5 deferral)**: 114 FR-C.5 (test-fixture sweep + `_PERMITTED_TEST_FILES` allowlist authoring) is **DEFERRED to feature 116**. 115 ships the emit + same-commit removal only. 114 FR-C.4 (AST whitelist removal at `check_status_write_path.py:37`) is also DEFERRED to 116. The whitelist stays in place at end of 115 so test fixtures calling `db.update_entity(status=...)` directly continue passing without a sweep.

### FR-E-115 — Cross-Workspace Gates (delta over 114 FR-E)

114 FR-E.1, FR-E.2 (3 handlers), FR-E.3, FR-E.4, FR-E.6 apply as-written. The following 115 addition strengthens FR-E.5 and FR-E.7 to address FM-2 (doctor check escalation risk):

- **FR-E-115.1 (severity vocabulary binding, FM-2 mitigation)**: The new doctor check name is `check_cross_workspace_parent_uuid` (placed at `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py`). Per-issue severity field MUST use the value `"warning"` exclusively — NOT `"error"`, NOT `"info"`, NOT `"suggestion"`. The vocabulary is bound to 114 IF-9's `severity_summary` keys `{"error", "warning", "info"}` — `"suggestion"` is NOT in the contract and MUST NOT be emitted. **Allowlist suppression**: Per inherited 114 FR-E.4, rows present in `cross_workspace_allowlist` are SUPPRESSED entirely before severity assignment — the check never emits records for allowlisted pairs. Hence the singleton `{"warning"}` set covers all emitted issues (allowlisted pairs do not emit, so no `info` is needed for them).
- **FR-E-115.2 (acceptance test)**: An integration test seeds 21 cross-workspace `parent_uuid` rows in a fixture DB, invokes the doctor check, and asserts:
  - `severity_summary.warning >= 21`
  - `severity_summary.error == 0`
  - For each emitted issue with `severity_summary[key] > 0` for `key in {"error", "info"}`, the test fails (no `error`/`info` issues emitted by this check).

### FR-E.2-115 — Triage Tool (delta over 114 FR-E.2)

114 FR-E.2.1, FR-E.2.2, FR-E.2.3 apply as-written. The following pin is added:

- **FR-E.2-115.1 (helper location)**: The `_interactive_triage_loop(items, build_question_fn, apply_fn)` helper (shared between FR-E.2.2 triage and FR-B-H4-115.1 dry-run) MUST be placed at `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py`. Justification: existing `fix_actions.py` houses individual fix actions; the shared helper lives alongside them in a new sub-package OR as a `_interactive.py` module in the same directory (specify-phase picks the second option as lower-disruption).

### FR-B-H4-115 — Hash Drift Backfill (delta over 114 FR-B-H4)

114 FR-B-H4.1 (canonical hash on `description`) and 114 FR-B-H4.3 (predicate scope `source='import' AND observation_count > 100`) apply as-written. The following 115 modifications shape the gate model (FM-3 mitigation):

- **FR-B-H4-115.1 (bounded-count gate + identity spot-check, replaces 114 FR-B-H4.2 frozen-manifest model)**: The frozen-manifest fixture model from 114 (`hash_shift_manifest.json` + memory_db_sha256 + frozen `shifted_ids` set) is REPLACED with a bounded-count gate **augmented by an identity spot-check** to recover the identity-fidelity property the manifest gave for free. Two-stage gate:
  - **Stage 1 — bounded count**: Migration M6 (memory.db, hash unify + Tool-failure DELETE) and M7 (memory.db, observation reset) each pin an expected count from the spec-time DB query (see §5 Pin H-115, Pin I-115). Each migration body, BEFORE applying its mutation, runs the count query and asserts the observed count is within `expected_count ± tolerance`. If outside range: ABORT.
  - **Stage 2 — identity spot-check**: After Stage 1 passes, M6/M7 SELECT the candidate rows pre-mutation and assert the predicate shape is correct:
    - M6 Tool-failure DELETE: SELECT candidate rows; assert at least 95% have `created_at < '2026-05-16'` (the freeze date — older than spec time). If <95% match this temporal anchor, ABORT — drift may include newly-accumulated legitimate-looking rows the predicate-based DELETE cannot distinguish from noise.
    - M7 observation reset: SELECT candidate rows; assert all have `source='import'` AND `observation_count > 100` (re-verifies the predicate). The 12 rows pinned in Pin I-115 are all `created_at=2026-03-19` per 114 spec Pin I.1; M7 additionally asserts at least 95% of candidates have `created_at < '2026-05-16'`.
  - **Abort diagnostic**: On ABORT (either stage), emit stderr line matching regex `pd\.migrate\.m[67]_(count_drift|identity_drift): \{.+\}` with JSON containing keys `{observed, expected, tolerance, stage, recount_command, identity_sample}` where `identity_sample` shows up to 5 candidate rows that failed the spot-check. Instruct operator: "Run: `sqlite3 ~/.claude/pd/memory/memory.db '<recount-SQL>'` to investigate. If drift is legitimate (e.g., hook regression introduced new noise; import-tool regression introduced new inflated rows), amend spec Pin H-115 / Pin I-115 range and re-run."
  - **Residual risk note** (per §7 FM-3 update): Stage 2's 95% threshold tolerates some legitimate-looking row substitution. Choosing 95% (not 100%) accommodates clock skew and edge cases where 1-2 rows fall on the boundary. For 468 candidates that's up to ~23 substitutable rows. For 12 candidates the threshold is effectively strict: 11/12 = 91.7% fails ≥95%, so all 12 must match. M6 retains the small substitution window acknowledged in §7; M7 is functionally strict.
- **FR-B-H4-115.2 (M6 body — NEW WORK, NOT INHERITED)**: Migration 6 body MUST execute BOTH:
  - `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` (114 FR-B-H2.2 carry-forward; grep confirms NEVER previously executed) — bounded-count gate per FR-B-H4-115.1 + Pin H-115.
  - Hash recomputation for rows where `source='import'` (114 FR-B-H4.1 carried forward). **Sub-operation gate**: the hash-recompute count is NOT spec-time-pinned (no upper bound). The FR-B-H4-115.4 dry-run helper's `n_shifted` output IS the implement-phase pin. M6 hash-recompute proceeds if `n_shifted >= 1` (AC-B-H4-115.5 condition (c)); no upper-bound abort needed because the UPDATE is **identity-safe** — it modifies the `source_hash` column on the same rows the dry-run identified, never INSERTs or DELETEs. Re-running M6 against a DB where dry-run produces a different `n_shifted` is acceptable: the migration re-converges to canonical hash on whatever rows currently differ.
- **FR-B-H4-115.3 (M7 body)**: Migration 7 body executes `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100` (114 FR-B-H4.3). Bounded-count gate per Pin I-115. Implement-phase runs the recount immediately before M7 lands to catch drift between spec time and migration time.
- **FR-B-H4-115.4 (helper reuse)**: The dry-run helper `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py` (114 FR-B-H4.2 step 1) is still authored, but it produces count diagnostics only — no frozen manifest fixture. Output: `{n_shifted, n_tool_failure, n_inflated, observed_at}` written to stderr/stdout when run with `--report` flag. Manifests/fixtures are NOT shipped.

### FR-Migrations-115 — Migration Numbering

- **FR-Migrations-115.1**: 115 new migrations (verified against current heads at spec time 2026-05-16T21:17Z):
  - **M15** (entities.db) = `_migration_15_audit_emit_counter` — Cluster C reset (114 FR-C.3 carry-forward).
  - **M17** (entities.db) = `_migration_17_cross_workspace_allowlist` — Cluster E.2 schema (114 FR-E.2.1 carry-forward).
  - **M6** (memory.db) = `_migration_6_unify_source_hash_and_cleanup` — Cluster B-H4 hash unify + Tool-failure DELETE (114 FR-B-H4.1 + FR-B-H2.2 combined; FR-B-H4-115.2 body).
  - **M7** (memory.db) = `_migration_7_reset_inflated_observation_count` — Cluster B-H4 observation reset (114 FR-B-H4.3; FR-B-H4-115.3 body).
- **FR-Migrations-115.2** (M16 no-op stub): The migration runner in `plugins/pd/hooks/lib/entity_registry/database.py` (locate via content selector: the `for version in range(current + 1, target + 1):` block followed by `migration_fn = MIGRATIONS[version]`) REQUIRES contiguous integer keys (verified by spec-reviewer iter 1). Vacating M16 would raise `KeyError: 16` for any DB at schema_version<16 upgrading past it. Therefore M16 MUST be defined as a no-op stub:
  ```python
  def _migration_16_reserved(conn: sqlite3.Connection) -> None:
      """Reserved during 115 planning; intentionally empty.

      114 spec Pin O originally named M16 = hash-unify, but 114 deferred B-H4
      entirely. 115 placed hash-unify at memory.db M6 instead. This entities.db
      slot is kept as a no-op for migration-runner contiguity.
      """
      pass
  ```
  M16 is registered in both `MIGRATIONS` and `MIGRATIONS_DOWN` dicts. Down-migration is also a no-op. **Implement-phase guard**: verify M15, M16, M17 are still unassigned via `grep -cE "def _migration_(15|16|17)_" plugins/pd/hooks/lib/entity_registry/database.py == 0` AND `grep -cE "def _migration_[6-9]_" plugins/pd/hooks/lib/semantic_memory/database.py == 0` before authoring bodies. If any are taken, pause and surface for spec amendment.

### FR-Sev-115 — Severity Reporting (delta over 114 FR-E.7)

114 FR-E.7 ships the output-JSON `severity_summary` contract. The following 115 addition pins vocabulary to a closed set:

- **FR-Sev-115.1**: All NEW doctor checks introduced in 115 (FR-E-115.1's `check_cross_workspace_parent_uuid`; any other new checks from FR-C health-check expansions) MUST emit `severity` values from the closed set `{"error", "warning", "info"}` — NEVER `"suggestion"`. The 114 IF-9 contract is the source of truth. Test: AST/grep verification on each new check's source file confirms `severity=` assignments use only values in this set.

### Test Execution Context (MCP unavailability fallback)

Implement-phase MAY find entity-registry / workflow-engine MCPs disconnected due to the lingering M12 stub-trap state (114 retro line 37-39). All 115 integration ACs are written against **direct-Python invocation** (e.g., `db.update_entity(...)`, `doctor.run()` called from pytest fixtures, M6/M7 invoked via Python migration runner) — NOT MCP-protocol round-trips. Implementer SHOULD verify MCP availability at implement-phase start by attempting a trivial `mcp_call('list_entities', limit=1)`. If unavailable:
- All ACs in §4 are satisfiable via direct invocation.
- Tests for cross-process operator workflows (e.g., simulating the operator-confidence story for triage tool, or end-to-end `complete_phase` from a CLI caller) MAY be marked `pytest.mark.requires_mcp` and skipped; the underlying Python-level coverage from AC-E.2.* + AC-C-115.2 is sufficient for merge.
- Document any AC that cannot be satisfied without MCP and surface for spec amendment via /pd:remember.

## 4. Acceptance Criteria (115 deltas + additions)

114 §3 acceptance criteria apply as-written EXCEPT where overridden below or marked deferred. The following 115-specific ACs strengthen or replace the corresponding 114 ACs.

### AC-PRE (Cluster D Verification)

- **AC-PRE.1**: Content-only verification per §3 FR-PRE.1.1 — `rg '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | wc -l` returns ≥1; function-body anchor `rg -B5 '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | grep -q _process_complete_phase` returns 0 (success). If 0 hits on first check: implement aborts with "FR-D regression detected on develop; cannot land FR-C safely."
- **AC-PRE.2**: `rg '_workspace_uuid or ""' plugins/pd/mcp/entity_server.py | wc -l` returns exactly 2 (intentional 114 retro accepted-reverts inside the `_process_register_entity` and `_process_upsert_entity` helper paths — content anchor, no line-number constraint). If 0 hits: someone re-applied FR-D.2 and broke `test_register_entity_handler_concise_message`; pause and surface.

### AC-C-115 (Audit Invariant — atomicity addition over 114 AC-C)

114 AC-C.1, AC-C.2, AC-C.3, AC-C.4, AC-C.5, AC-C.7a, AC-C.7b, AC-C.7c apply. Replace/extend:

- **AC-C-115.1 (atomicity, content-aware verification)**: Per FR-C-115.1 verification protocol:
  ```bash
  SHA=$(git log --all --grep='^FR-C-115.1:' --pretty=format:%H | head -1)
  test -n "$SHA" || { echo "FAIL: FR-C-115.1 commit not found"; exit 1; }
  git show "$SHA" --name-only | grep -q 'plugins/pd/hooks/lib/entity_registry/database.py' || { echo "FAIL: database.py not in commit"; exit 1; }
  git show "$SHA" --name-only | grep -q 'plugins/pd/mcp/workflow_state_server.py' || { echo "FAIL: workflow_state_server.py not in commit"; exit 1; }
  git show "$SHA" -- plugins/pd/hooks/lib/entity_registry/database.py | grep -qE '^\+.*append_phase_event.*entity_status_changed' || { echo "FAIL: emit insertion not in database.py diff"; exit 1; }
  git show "$SHA" -- plugins/pd/mcp/workflow_state_server.py | grep -qE '^-.*append_phase_event.*entity_status_changed' || { echo "FAIL: manual emit deletion not in workflow_state_server.py diff"; exit 1; }
  ```
  All five assertions MUST pass. If any fail: atomicity invariant is broken — the emit insertion and manual emit deletion are in different commits, or one is missing entirely.
- **AC-C-115.2 (single-emit runtime)**: Integration test `test_complete_phase_closes_emits_exactly_once`: create a feature entity at `status='active'`, call `complete_phase(closes=[feature_type_id])`, assert `SELECT COUNT(*) FROM phase_events WHERE event_type='entity_status_changed' AND type_id=?` == **1** (NOT 0 — neither emit fired; NOT 2 — both emit fired).
- **AC-C-115.3 (closed_by_uuid loss acknowledged)**: For closed entities, `phase_events.metadata` MAY contain `{"old_status", "new_status"}` but the `"closed_by_uuid"` key is no longer guaranteed (lost when F111 manual emit removed). Test does NOT assert absence of `closed_by_uuid` — it MAY appear if the emit happened to retain it via update_entity's own `metadata` parameter; it just is no longer load-bearing. Per 114 retro accepted trade-off.
- **AC-C-115.deferred** (informational, NOT an AC — moved to §8 plan-phase guard): 114 AC-C.3 (whitelist removal) and 114 AC-C.6 (test-fixture sweep) are **DEFERRED to feature 116**. Enforcement via plan-phase guard per §8 (plan-reviewer asserts no task title or description includes deferred-to-116 work).

### AC-E-115 (Cross-Workspace Gates — severity addition over 114 AC-E)

114 AC-E.1, AC-E.2, AC-E.3, AC-E.5 apply. Replace/extend:

- **AC-E-115.1 (severity vocab)**: AST/grep on `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py`: every `severity=` assignment uses a value from the closed set `{"warning"}`. (Stricter than 114 IF-9 — this check uses warning exclusively.)
- **AC-E-115.2 (count assertion)**: Doctor invocation against fixture DB with 21 cross-workspace `parent_uuid` rows returns output JSON with:
  - `severity_summary.warning >= 21`
  - `severity_summary.error == 0`
  - `severity_summary.info == 0` (this check does not emit info)
  Test name: `test_check_cross_workspace_parent_uuid_emits_warning_only`.
- **AC-E-115.3 (forbidden vocab)**: AST/grep verification: file does NOT contain the literal string `"suggestion"` as a severity value. Catches accidental drift to wrong vocab.

### AC-B-H4-115 (Hash Drift — bounded-count gate replacement)

114 AC-B-H4.1, AC-B-H4.2 apply (post-migration row checks). Replace 114 AC-B-H4.3 (manifest gate):

- **AC-B-H4-115.1 (M6 bounded-count gate)**: Migration M6 body, when run against a memory.db where observed `Tool failure:%` count is outside `[Pin H-115 - tolerance, Pin H-115 + tolerance]`, aborts with stderr diagnostic matching regex `pd\.migrate\.m6_count_drift: \{.+\}` where JSON contains keys `{observed, expected, tolerance, recount_command}`. No mutation occurs. Exit code != 0.
- **AC-B-H4-115.2 (M7 bounded-count gate)**: Same as AC-B-H4-115.1 but for M7 against `observation_count > 100` count, with Pin I-115 as expected.
- **AC-B-H4-115.3 (M6 NEW DELETE work)**: After M6 lands on a memory.db where `Tool failure:%` count was 468 ± tolerance, `SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` == 0. Strengthens 114 AC-B-H2.2 (which assumed 114 had run the DELETE) — 115 ACTUALLY runs it.
- **AC-B-H4-115.4 (M7 inflated reset)**: After M7 lands on a memory.db where inflated-row count was 12 ± tolerance, `SELECT COUNT(*) FROM entries WHERE source='import' AND observation_count > 100` == 0.
- **AC-B-H4-115.5 (recompute helper, value-validated)**: `python -m plugins.pd.hooks.lib.semantic_memory.recompute_source_hash --report` against current memory.db returns stdout JSON `{n_shifted: int, n_tool_failure: int, n_inflated: int, observed_at: str}` and exit 0. Values MUST satisfy: (a) `n_tool_failure ∈ [Pin H-115.lower, Pin H-115.upper]` (i.e., 468 ± 50 = [418, 518]), (b) `n_inflated ∈ [Pin I-115.lower, Pin I-115.upper]` (i.e., 12 ± 3 = [9, 15]), (c) `n_shifted >= 1` (hash drift must exist; zero shifted implies the bug is non-existent and 115 has no work to do — implementer surfaces and pauses), (d) `observed_at` parses as ISO 8601. No mutation.

### AC-Migrations-115

- **AC-Migrations-115.1**: After 115 lands, entities.db `MIGRATIONS` dict contains keys `{... 14, 15, 16, 17}` where key 16 maps to the no-op stub `_migration_16_reserved` per FR-Migrations-115.2 (NOT vacant — migration-runner contiguity requires the key be present). memory.db `MIGRATIONS` dict contains keys `{... 5, 6, 7}`.
- **AC-Migrations-115.2**: `grep -cE "def _migration_(15|16|17)_" plugins/pd/hooks/lib/entity_registry/database.py == 3` (M15 audit counter + M16 no-op + M17 allowlist) AND `grep -cE "def _migration_(6|7)_" plugins/pd/hooks/lib/semantic_memory/database.py == 2`.

## 5. Empirical SUT Pins (re-pinned at 115 spec time, Open Question #6 fulfilled)

Pin refresh executed 2026-05-16T21:17Z against current code + DB state.

| Pin | 114 statement | 115 re-pin | Drift |
|-----|---------------|------------|-------|
| **C** | 457 entities, 945 phase_events | UNCHANGED (DB rolled back to v11 but content preserved) | none |
| **D** | 0 `entity_status_changed` rows | UNCHANGED (audit invariant still never held) | none |
| **E-115** | 21 cross-workspace `parent_uuid` rows | **21** | none |
| **F.1-115** | 17 distinct `update_entity(status=...)` callers (locations frozen in 114 spec) | **17 sites confirmed** (some line drift: workflow_state_server.py site moved 1339→1359). Site enumeration list inherited from 114 spec Pin F.1; implement-phase re-greps for exact lines | line drift only |
| **F.3-115** | (new) F111 manual-emit block in workflow_state_server.py | **lines 1364-1375** (114 said 1344-1356, +20 line drift) | yes, content-based selector preferred |

> **Drift footnote**: F.1-115 (update_entity call site at 1359) and F.3-115 (manual emit block at 1364-1375) reflect a single ~+20-line shift in `workflow_state_server.py` between 114-spec-time and 115-spec-time. The two pins are adjacent code in `_process_complete_phase`. FR-C-115.1 already uses content-based selectors (grep for `append_phase_event.*entity_status_changed`); line ranges in this table are documentation aids only.
| **G** | 3 `_workspace_uuid or ""` sites | 2 sites remain at `entity_server.py:567, :710` (intentional 114 retro reverts); `workflow_state_server.py:1184` fixed | partial — see AC-PRE |
| **H-115** | 464 Tool failure:% rows | **468** (drift +4); migration tolerance: 468 ± 50 | yes, accounted in FR-B-H4-115 |
| **I-115** | 10 inflated entries | **12** (drift +2); migration tolerance: 12 ± 3 | yes, accounted in FR-B-H4-115 |
| **J** | M12 stub commit `6722191a` | unchanged | none |
| **L** | M11 guards at database.py:1818, 1899 | unchanged (FR-A landed) | none |
| **M** | issue_spawn gate template at entity_server.py:734-739 | unchanged | none |
| **N** | `add_entity_tag` single-entity signature | unchanged | none |
| **O-115** | M15/M16/M17 reserved for 114 | **M15 + M17 used; M16 vacant** (FR-Migrations-115.2); memory.db M6/M7 added | adjusted per PRD |

Schema heads:
- entities.db: `schema_version=14` (post-114-merge; M12 body applied via FR-A landing; M13/M14 already ran)
- memory.db: `schema_version=5` (no 114 memory-side migrations landed since B-H2 only deleted hook source, not DB rows)

## 6. Out-of-Scope (Non-Goals)

Per PRD Non-Goals:
- Hard-error escalation for Cluster E doctor check (gates remain warning-only at end of 115)
- Full event-sourcing audit retrofit (observability-grade fail-open emit only)
- Re-attribution of `_UNKNOWN_WORKSPACE_UUID` entities
- Fingerprint-based M12 detector (114 column-presence approach kept)
- **AST whitelist removal at `check_status_write_path.py:37` (deferred to feature 116)**
- **114 FR-C.5 test-fixture sweep + `_PERMITTED_TEST_FILES` authoring (deferred to feature 116)**
- **114 FR-C.4 AST whitelist removal (deferred to feature 116; consequence of FR-C.5 deferral)**

Carry-forward scope-creep guards from 114 §5:
- Do NOT add new entity types or workspace concepts
- Do NOT change `_KIND_TO_TYPE_LIFECYCLE` mapping
- Do NOT extend `_CLOSES_TERMINAL` dictionary
- Do NOT modify F111's `complete_phase(closes=...)` behavior beyond FR-C-115 same-commit removal
- Do NOT touch FTS5 rebuild logic
- Do NOT change `register_entity` raise-on-conflict semantics

## 7. Risks Carried Forward (PRD section)

All 7 PRD Risk-table rows apply to this spec. Critical mitigations encoded:

1. **FM-1 CRITICAL — Cluster C double-emit**: FR-C-115.1 + FR-C-115.2 + AC-C-115.1 enforce same-commit atomicity via git log SHA equality + pre-commit assertion + content-match verification.
2. **FM-2 HIGH — Doctor check escalation**: FR-E-115.1 + FR-Sev-115.1 + AC-E-115.1/2/3 bind severity to closed `{warning}` set; AST/grep + integration test catch drift.
3. **FM-3 HIGH — B-H4 silent over-deletion**: FR-B-H4-115.1 enforces a two-stage gate (bounded count + identity spot-check at 95% temporal-anchor threshold) with explicit abort + recovery path; AC-B-H4-115.1/2 verify. **Residual risk** (weaker than 114's frozen-manifest model): the 95% threshold tolerates up to 23 substitutable rows on M6 (468 candidates × 5%). Accepted because the DELETE predicate `source='session-capture' AND name LIKE 'Tool failure:%'` is structurally narrow — substitution requires a legitimate session-capture entry named like a Tool failure, which the (now-deleted) hook source was the only mechanism producing. M7 is functionally strict (12 candidates × 5% = 0 substitutable). If post-115 audit reveals substitution did occur, the affected rows are recoverable from `git log` of the `f60e3f58` commit's pre-state.
4. **FM-5 HIGH — DELETE silently dropped from 115 scope**: FR-B-H4-115.2 + AC-B-H4-115.3 force the DELETE into M6 as NEW work, not inherited.
5. **Pin staleness**: §5 §H-115 + §I-115 re-pinned; FR-B-H4-115.4 dry-run helper provides implement-phase re-verification mechanism.
6. **AST whitelist accidentally removed in 115**: FR-C-115.3 + AC-C-115.deferred explicitly forbid; plan-phase grep verification.

## 8. Cluster Sequencing (Implementation Order — overrides PRD diagram)

```
[Tier 0 — verification gate]
   AC-PRE.1, AC-PRE.2 (Cluster D inheritance check)
        ↓
[Tier 1 — Cluster C]
   FR-C-115.1 (emit + same-commit deletion) + FR-C-115.2 (pre-commit assertion)
   M15 (audit_emit_failed_count counter)
   AC-C.* (114 inherited) + AC-C-115.1/2/3 (atomicity additions)
   FR-C.4 + FR-C.5 explicitly DEFERRED to 116
        ↓
[Tier 2a — Cluster E.2 (must precede E)]
   M17 (cross_workspace_allowlist table)
   FR-E.2.2 triage tool with _interactive_triage_loop helper
   AC-E.2.* (114 inherited)
        ↓
[Tier 2b — Cluster E]
   FR-E.1 (_assert_same_workspace_uuids helper)
   FR-E.2 (3 MCP handler gates)
   FR-E.3 (CrossWorkspaceError envelope)
   FR-E-115.1 (check_cross_workspace_parent_uuid doctor check)
   AC-E.* (114 inherited) + AC-E-115.1/2/3 (severity vocab additions)
        ↓
[Tier 3a — Cluster B-H3]
   FR-B-H3.1/2/3 (writer CLI quality gates)
   AC-B-H3.* (114 inherited)
        ↓
[Tier 3b — Cluster B-H4]
   FR-B-H4-115.4 (recompute helper — produces count diagnostics)
   M6 body (hash unify + Tool-failure DELETE; bounded-count gated)
   M7 body (observation reset; bounded-count gated)
   AC-B-H4-115.1/2/3/4/5 (replaces 114 manifest-gate ACs)
```

**80/20 fallback** (per PRD): floor = Tier 0 + Tier 1 + Tier 2a + Tier 2b. Drop order: Tier 3a first, then Tier 3b. Inverted from PRD original because keeping Tier 3b preserves the 468-row + 12-entry cleanup over the CLI-gate-extraction work. **Forfeited work-sharing**: this inversion gives up the B-H3 ↔ B-H4 cross-validation work-sharing identified in PRD Opportunity-Cost #3 (B-H3's `_apply_quality_gates` could cross-validate B-H4's manifest count). Acceptable because (a) cross-validation was nice-to-have, not load-bearing; (b) historical-noise cleanup is the higher-value drop-protect target. If implement reverses the priority (e.g., prefers cross-validation), drop B-H4 first instead and document the decision in plan.md.

**Plan-phase guard (deferred-to-116 protection)**: When `/pd:create-plan` produces tasks.md, plan-reviewer asserts no task title or description references the deferred-to-116 work: 114 FR-C.4 (AST whitelist removal), 114 FR-C.5 (test-fixture sweep), `check_status_write_path.py:37` whitelist mutation, or `_PERMITTED_TEST_FILES` authoring. If any present: plan-reviewer raises blocker "Task targets deferred-to-116 work; remove from 115 plan." Verification command: `grep -iE "(FR-C\\.4|FR-C\\.5|_PERMITTED_TEST_FILES|check_status_write_path\\.py:37|AST whitelist|test-fixture sweep|whitelist removal|_PERMITTED_ENCLOSING_DEFS)" docs/features/115-pd-data-model-followups/tasks.md` returns 0 hits. Case-insensitive grep catches title-case variants. Pattern is necessary-not-sufficient (a sufficiently obfuscated task description could still slip through); plan-reviewer's prose-level check is the secondary defense.

## 9. Open Questions (for design phase)

Carried from PRD §Open Questions, with specify-phase resolutions:

1. Entities.db M14 head — **CONFIRMED at spec time**: M14 is current head; M15 + M17 free.
2. Memory.db M5 head — **CONFIRMED at spec time**: M5 is current head; M6 + M7 free.
3. B-H4 cleanup-query scope — **RESOLVED**: keep 114 predicate; bounded-count gate per FR-B-H4-115.1.
4. Interactive triage loop helper location — **RESOLVED**: `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py` per FR-E.2-115.1.
5. F111 manual-emit single commit boundary — **RESOLVED**: FR-C-115.1 + AC-C-115.1 encode binary AC.
6. Specify-phase pin refresh — **EXECUTED at spec time**; results in §5.

Remaining for design phase:
7. Where in `db.update_entity` should the emit be inserted (pre-UPDATE or post-UPDATE)? FR-C.2 requires fail-open after UPDATE has committed. Design pins exact line.
8. Whether `_metadata.audit_emit_failed_count` reset (FR-C.3) needs to be transactional with the M15 body or can be a separate statement. Design clarifies.
9. CrossWorkspaceError envelope: does it inherit from EntityNotFoundError's envelope template (F111) or define a new one? Design picks. **Reference**: F111 envelope pattern lives near `plugins/pd/mcp/entity_server.py` issue_spawn gate template (114 spec Pin M, ~line 734-739); design inspects to choose inheritance vs. composition.

## 10. Reference Files

- Feature 114 artifacts: `docs/features/114-pd-data-model-hardening/{prd,spec,design,plan,tasks,retro}.md` (canonical evidence base)
- Brainstorm source: `docs/brainstorms/115-pd-followups-source.md`
- PRD: `docs/features/115-pd-data-model-followups/prd.md`
- 114 commits: A=`c71dfa39`, D=`7591cd2b`, B-H2=`f60e3f58`, merge=`c692fd16`
