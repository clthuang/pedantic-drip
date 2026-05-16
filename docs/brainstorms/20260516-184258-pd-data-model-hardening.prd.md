# PRD: pd Data-Model + Memory Hardening (Feature 112)

## Status

- Created: 2026-05-16
- Brainstorm source: `docs/brainstorms/112-pd-data-model-hardening-source.md`
- Mode: Standard (YOLO)
- Problem Type: Technical/Architecture
- Archetype: exploring-an-idea
- Lineage: post-P003 (entity-system-redesign) hardening — closes invariants stated by features 108-111 but never actually held in production

## Problem

Project P003 landed major schema and MCP changes (features 108-111). A post-ship deep-dive review surfaced 13 HIGH findings, narrowed to 7 HIGH after concrete reproduction and production-data verification. Three of these are **load-bearing**:

1. **The entity DB is stuck mid-migration** on installed users' machines. Commit `6722191a` (May 12, 2026) shipped Migration 12 as a stub that stamped `_metadata.schema_version=12` without doing any schema work. Subsequent commits added the real schema body, but M12's idempotency early-return at `database.py:2683` reads the stamp and returns immediately — bypassing the actual schema transformation. Migration 13 then aborts with `"Run feature-109 deferred remediation first"`, a remediation script that **was never written**. — Evidence: `~/.claude/pd/entities/entities.db` reproduces this exact state; ui-server.log traceback; git show `6722191a` confirms zero `ALTER TABLE`/`CREATE TABLE entities_new` lines.

2. **The audit-trail invariant has never held in production.** F111 designed `entity_status_changed` events as the sole signal of status mutations. Production phase_events: 565 `completed`, 307 `started`, 73 `skipped`, **0 `entity_status_changed`** out of 945 total. Root cause: `db.update_entity` (`database.py:7094-7236`) does direct `UPDATE entities SET status=?` without calling `append_phase_event`, and is whitelisted in the AST audit (`check_status_write_path.py:37`) hiding the violation. — Evidence: SQL queries against `~/.claude/pd/entities/entities.db`. Production call sites passing `status=` (enumerated for implement to re-verify; estimated ~16-18 including multi-line invocations not visible to single-line grep):
   - `plugins/pd/hooks/lib/workflow_engine/entity_engine.py:371,398,477`
   - `plugins/pd/hooks/lib/workflow_engine/engine.py:180`
   - `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py:93,200,338`
   - `plugins/pd/hooks/lib/entity_registry/dependencies.py:109`
   - `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:183`
   - `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:53,83,209` (multi-line)
   - `plugins/pd/hooks/lib/doctor/fix_actions.py:177,185`
   - `plugins/pd/mcp/entity_server.py:369` (multi-line `_process_update_entity` forwarder)
   - `plugins/pd/mcp/workflow_state_server.py:1339` (multi-line, inside closure block — note: forced status terminal)
   - `plugins/pd/scripts/cleanup_backlog.py:224`

   Verification command (multi-line aware): `rg -nU "update_entity\([^)]*status=" plugins/pd/ --type=py -g '!test_*.py' -g '!**/tests/**' -g '!.venv/**'`. The implement phase must enumerate the call-site list as a binary count before refactoring.

3. **The F108 isolation goal was never actually achieved.** F108 stated "structural workspace isolation" as Goal 1. F111 added the cross-workspace gate at `issue_spawn` (`entity_server.py:734-739`) and `complete_phase(closes=)`. But **all four** older MCP write paths lack the gate: `set_parent`, `add_dependency`, `add_okr_alignment`, `add_entity_tag` (broader than source doc's three). Production has **21 live cross-workspace `parent_uuid` links** today. — Evidence: codebase-explorer scan + production DB query.

Additional findings, lower severity but high noise: H8 (caller-resolution failure for legacy `__unknown__` workspaces — manifests via the `_workspace_uuid or ""` pattern at three sites: `entity_server.py:562, 704`, `workflow_state_server.py:1184`); H2/H3/H4 (memory DB is 91% CLI-bypassed entries; 29% noise from over-eager capture hook; 10 entries inflated to `observation_count=1438` from cross-writer hash drift).

## Goals / Success Criteria

1. **Recovery**: Any installed user with the M12-stub trap can recover via `/pd:doctor --fix` without manual SQL. M12 cannot be silently bypassed again (idempotency guard verifies schema state before trusting stamp).
2. **Audit invariant (observability-grade)**: Every `update_entity(status=...)` either emits `entity_status_changed` OR emits a stderr warning tagged `pd.audit.emit_failed` containing JSON fields `{type_id, old_status, new_status, exception_class}`. **Strict transactional coupling is explicitly NOT a goal** (per FM-1 fail-open mitigation — see Strategic Analysis). Doctor surfaces emit-failure rate as a health-check metric so silent degradation is visible.
3. **Legacy compatibility**: `complete_phase(closes=...)` and other entity-resolution paths succeed for legacy `__unknown__`-workspace features. Two-pass fallback strictly gated to `_UNKNOWN_WORKSPACE_UUID` only; any other miss raises `ValueError`.
4. **Isolation enforcement** (binary measure): Post-feature `SELECT COUNT(*) FROM entities WHERE parent_uuid IS NOT NULL AND parent.workspace_uuid != child.workspace_uuid = 0`. Each of the 21 existing cross-workspace links is one of: (a) re-attributed so both endpoints share a workspace, (b) deleted with operator approval, or (c) grandfathered via an explicit allowlist row in a new `cross_workspace_allowlist` table.
5. **Memory hygiene** (binary measure):
   - PostToolUse heuristic branch deleted from `capture-tool-failure.sh:147-157` (future entries from heuristic detection = 0).
   - 464 historical noise rows pruned via one-shot cleanup: `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'`.
   - 10 inflated entries reset: `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`.
   - `writer.py:main` contains exactly one call to `_apply_quality_gates(...)` before any `db.upsert_entry(...)`; integration test asserts CLI input failing the 20-char minimum returns non-zero exit code.

## Non-Goals

Explicitly out of scope for this feature (deferred to future hardening):

- **H1 — capture hook ignores `ask-first` mode** (MED, latent — user doesn't have `ask-first` set; will fold into next memory feature)
- **H5 — `init_entity_workflow` accepts bug/task** (LOW, no first-party caller hits it; latent gap)
- **H7 — `lifecycle_class` no CHECK constraint** (LOW, column doesn't exist in pre-M12 DBs; revisit post-M12-recovery if regressions observed)
- **H9a — F111 mixed-semantics boundary observability** (MED, F088 architectural trade-off; observability-only doctor check could fold here if implementation budget allows, otherwise defer)
- **Hard-error escalation for Cluster E cross-workspace gates** (defer to a follow-up feature once the 21 existing links are triaged and operator confidence builds — this feature ships gates in `severity=warning` observation mode only)
- **Full event-sourcing audit retrofit** (this feature retrofits the audit *invariant* via fail-open emit, not a full event-sourced state reconstruction — see Strategic Analysis "Audit invariant retrofit" point)

## Approaches Considered

**Approach 1 (chosen): Single feature, 5 clusters with internal sequencing + observation-mode rollout for risky clusters**
- Pro: Cohesive — all 5 clusters touch the same database layer or its closely-coupled audit/MCP surface
- Pro: Single reviewer cycle (~25 dispatches per P003 baseline) vs ~54+ for 3-feature decomposition
- Pro: Matches user's "in one go" directive
- Con: Implementation surface larger; needs explicit cluster sequencing (see below) and per-cluster risk mitigations
- **Mitigation strategy baked in**: emit fail-open (FM-1), warning-only doctor check (FM-3), backfill migration (FM-4), strictly-gated fallback (FM-5), auto-invoke remediation via doctor (FM-2)

**Approach 2 (rejected): 3-feature decomposition (M12+audit, workspace, memory)**
- Con: 3× brainstorm/specify/design/create-plan/implement/finish overhead; estimated 54+ pre-implement reviewer iterations vs ~25
- Con: User explicitly requested bundled execution

**Approach 3 (rejected): Ship only blockers (A + D + B-H2), defer rest**
- Con: User explicitly requested all-in-one
- Con: Audit invariant (C) and isolation gaps (E) continue to silently degrade

**Approach 4 (rejected): Auto-detect-and-fix at session start silently**
- Con: Silent mutation of user DB without consent gate
- Hybrid adopted: doctor surfaces M12 fix as a recommended action with one-click consent via AskUserQuestion

## Cluster Sequencing (Implementation Order)

Strict ordering constraints, derived from inter-cluster dependencies:

```
[1] Cluster A         (M12 guard + remediation CLI — must land FIRST)
[1] Cluster A.2       (M11 same-trap guard tightening — parallel with A; same mechanism)
        ↓
[2] Cluster D         (workspace fallback fix — landing helper used by Cluster E doctor check)
        ↓
[3] Cluster C         (audit invariant emit — depends on D being deployed first; C's emit path
                       routes through workspace resolution that D fixes for __unknown__ entities)
        ↓
[4] Cluster B-H4      (hash unification backfill migration — MUST land before H3 refactor;
                       otherwise unified gate sees hash-drifted entries as duplicates)
        ↓
[5] Cluster B-H3      (writer CLI gate extraction — depends on H4 backfill)
[5] Cluster B-H2      (capture hook simplification — parallel with B-H3; independent)
        ↓
[6] Cluster E         (cross-workspace gates — depends on D; ships as warning-only observation)
[6] Cluster E.2       (cross-workspace triage tool — parallel with E; doctor fix_action with
                       per-link interactive prompt)
```

Rationale: Cluster A unblocks DB access for any test that hits the real entities.db. Cluster D's workspace helper is reused by Cluster C's emit (project_id resolution) and Cluster E's gate (caller workspace identification). Cluster B's H4 backfill MUST precede H3 to avoid silent re-import. Cluster E ships in observation mode because the 21 existing links need triage before hard-fail is safe.

## Per-Cluster Scope Boundaries

### Cluster A — M12 stub recovery
**In scope:** Tighten M12 guard (`database.py:2683`) to verify column layout before trusting stamp; implement `python -m entity_registry.remediate_m12` CLI subcommand AND doctor `fix_action`; auto-invoke via doctor at session-start with AskUserQuestion consent gate (YOLO compatibility: `yolo-guard.sh` intercepts AskUserQuestion in YOLO mode and auto-accepts safe data-recovery prompts — no special-case needed); embed exact CLI command in any error messages that fire.
**Out of scope:** Rewriting M12's actual body (already done, just bypassed); rolling back to user_version-based versioning.

### Cluster A.2 — M11 same-trap guard
**In scope:** Audit and tighten M11 guard at `database.py:1818, 1899` (same stub-then-fill mechanism). Acceptance: M11 cannot be silently bypassed — guard verifies `workspace_uuid` column exists before early-return. Partial-M11 recovery shares the same idempotency detector pattern as A's partial-M12 CLI (see Risks table "Partially-completed M11 or M12 state").
**Out of scope:** Reworking M11's body or down-migration logic. If partial-M11 state is empirically unobserved in field reports, design phase may document the limitation rather than ship untested recovery code (Open Question 7).

### Cluster B — Memory hygiene (H2/H3/H4)
**In scope:** Drop PostToolUse heuristic branch (`capture-tool-failure.sh:147-157`); extract `_apply_quality_gates(description, db, config)` from `_process_store_memory` in `memory_server.py` and have `writer.py:main` call it; unify `source_hash` input across `writer.py:72` and `importer.py:86` (both hash `description`); backfill migration that recomputes stored source_hash for existing entries WITHOUT re-importing content; one-shot cleanup queries for the 464 noise rows and 10 inflated rows.
**Out of scope:** Capture-mode `ask-first` semantics (H1 — non-goal); rewriting the embedding provider; changing FTS5 configuration.

### Cluster C — Audit invariant (H6)
**In scope:** Add `append_phase_event(event_type='entity_status_changed')` inside `update_entity` when `status is not None` AND status differs from current value (skip no-op writes); fail-open with stderr warning tagged `pd.audit.emit_failed` on emit failure; remove `update_entity` from AST whitelist at `check_status_write_path.py:37` AFTER all callers verified; sweep test fixtures that call `update_entity(status=...)` directly and update or whitelist them; doctor check that surfaces `pd.audit.emit_failed` rate as `severity=warning` health metric (counter persisted in entities.db `_metadata` table, key `audit_emit_failed_count`; **reset condition pinned**: the Cluster C migration sets `audit_emit_failed_count = 0` as part of migration execution — not as a side-effect of doctor runs); **bounds check**: if multi-line rg re-verification of `update_entity(status=...)` callers returns >20 results, pause and surface count to user before proceeding with whitelist removal.
**Out of scope:** Reconstructing historical `entity_status_changed` events from existing `updated_at` data; changing the doctor AST check's enclosing-def matching algorithm.

### Cluster D — Workspace fallback (H8)
**In scope:** Audit all three `_workspace_uuid or ""` sites (`entity_server.py:562, 704`; `workflow_state_server.py:1184`); replace with `_resolve_workspace_uuid_kwargs` consistent pattern OR two-pass fallback strictly gated to `_UNKNOWN_WORKSPACE_UUID` (any other miss raises `ValueError`); test fixture variant that uses real-UUID `_workspace_uuid` against legacy `_UNKNOWN_WORKSPACE_UUID` entity.
**Out of scope:** Full data migration to re-attribute `_UNKNOWN_WORKSPACE_UUID` entities to current workspace (deferred — see Open Question 6).

### Cluster E — Cross-workspace gates (H9b)
**In scope:** Extract `_assert_same_workspace_uuids(db, *uuids, caller_ws, op_name)` helper; apply at `_process_set_parent`, `_process_add_dependency`, `_process_add_okr_alignment`, `_process_add_entity_tag`; doctor check that flags existing cross-workspace `parent_uuid` rows in `severity=warning` mode; gates raise typed `CrossWorkspaceError` envelope.
**Out of scope:** Hard-error escalation (non-goal — deferred to follow-up); auto-deletion of the 21 existing links.

### Cluster E.2 — Cross-workspace triage tool
**In scope:** Doctor `fix_action` with per-link interactive prompt offering (a) re-attribute parent, (b) delete relation, (c) grandfather via `cross_workspace_allowlist` table. **Schema sketch** for the allowlist table (specify phase to refine): `CREATE TABLE cross_workspace_allowlist (id INTEGER PRIMARY KEY AUTOINCREMENT, parent_uuid TEXT NOT NULL, child_uuid TEXT NOT NULL, reason TEXT NOT NULL, grandfathered_by TEXT NOT NULL DEFAULT 'operator', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(parent_uuid, child_uuid))`. The Cluster E doctor check joins against this table to suppress warnings on allowlisted pairs.
**Out of scope:** Bulk triage UX, automated decision logic.

## Strategic Analysis

### Pre-Mortem Advisor

**Top 5 failure modes if shipped naively:**

- **FM-1 (CRITICAL) — Cluster C partial rollout**: 16 production callers of `update_entity(status=...)` span multiple subsystems. If the new `append_phase_event` emit path can't resolve `project_id` for some callers (e.g., `__unknown__` workspace context), MCP startup crashes on every call. Mitigation: **emit must fail-open** (try/except around phase_event insert; log warning; do not re-raise). Counterexample considered: doctor fix_action could introduce circular import on session-start before doctor itself is initialized — pinned for design phase.
- **FM-2 (HIGH) — Remediation CLI races with MCP startup**: Error message says "Run feature-109 deferred remediation first" but doesn't embed the CLI command. User runs pd normally → MCP aborts → no actionable recovery. Mitigation: remediation must be auto-invoked at session-start via doctor `fix_actions`; error message must include exact CLI command.
- **FM-3 (HIGH) — Cluster E hard-error blocks 21 existing links**: F108 was aspirational about isolation; 21 existing cross-workspace parent links may be intentional. Hard-error doctor check would blockade all sessions. Mitigation: **doctor check launches as `severity=warning`, never `error`**; triage tool (Cluster E.2) ships BEFORE gates harden.
- **FM-4 (MEDIUM) — Hash unification silently re-imports all memory**: Cluster B's "unify source_hash" can shift all existing entries' hashes. Mitigation: hash change is a schema migration — backfill recomputes stored hashes for existing rows; dry-run gate reports `{n_shifted, n_unchanged}` and proceeds if `n_shifted` matches expected set (10 inflated import rows + writer-vs-importer drift rows enumerated in spec), aborts otherwise.
- **FM-5 (MEDIUM) — Cluster D fallback introduces scope bleed**: Ungated two-pass workspace fallback could silently permit cross-workspace mutations from stale cached UUIDs. Mitigation: fallback strictly gated to canonical `_UNKNOWN_WORKSPACE_UUID` only; any other miss fails fast with `ValueError`. Log warning whenever fallback fires.

— Evidence Quality: strong (cross-checked against codebase verification)

### Opportunity-Cost Advisor

**Verdict on bundling all 5 clusters:** The user explicitly asked "do them all in one go", so this isn't a scope-reduction proposal. The advisor's risk calibration is load-bearing for implementation strategy:

- **Confirmed workflow blockers:** Cluster A (M12 recovery) and Cluster D (workspace mismatch — `complete_phase(closes=...)` broken for pre-F108 entities).
- **Bleeding hygiene (high leverage, low effort):** Cluster B H2 (10-15 LoC, stops 29% noise accumulation).
- **Structural correctness (medium effort, no current user pain):** Cluster C. 16 callers create blast radius; emit must fail-open.
- **Hardening with prerequisite triage:** Cluster E. 21 prod links need user-triage tooling before gates can fire. Triage tool ships in this feature (Cluster E.2); gates default to warning-only.
- **Defer-safe under bundle:** Cluster B H3 (writer CLI gate extraction) and H4 (hash unification) — structural correctness; ship with backfill migration to prevent FM-4.

Counterexample considered: what if the bundled feature's blast radius produces an unrecoverable QA-gate failure that none of the per-cluster fixes individually would have caused? Mitigation: cluster sequencing (above) explicitly orders changes to keep each stage's blast radius small.

— Evidence Quality: strong

## Constraints

- **No backward compatibility** (per CLAUDE.md — delete old code, no shims)
- **Production data preservation**: 457 entities + 945 phase_events in the affected DB must survive; cannot lose any
- **21 cross-workspace `parent_uuid` links may be intentional** — must NOT be silently rejected/deleted; require triage (Cluster E.2)
- **Audit-invariant change affects 16 callers** — emit path must be fail-open, not transactional (Goal 2 explicitly observability-grade)
- **YOLO mode autonomous execution** — reviewer iteration cap = 3
- **Merge to develop, never main** — per user memory
- **Use complete_phase MCP**, never manual `.meta.json` edits — per user memory
- **macOS/Bash 3.2 + SQLite ≥ 3.35** target (per pd-wide constraints)

## Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| 16-caller audit-invariant emit can crash MCP if `project_id` unresolvable | CRITICAL | Emit path fail-open with stderr warning; do not re-raise |
| **Cluster C emit depends on Cluster D landing first** (sequencing-coupled) | HIGH | Cluster Sequencing section makes D → C strict; create-plan must respect ordering |
| Remediation CLI never gets invoked because user doesn't know about it | HIGH | Auto-invoke via doctor at session-start with one-click consent gate |
| Hard-error isolation check blockades 21 existing links | HIGH | Doctor check launches as `severity=warning`; triage tool ships in this feature; hard-error escalation deferred |
| **AST whitelist removal fires on existing test fixtures** | HIGH | Sweep `test_*.py` callers BEFORE removing whitelist; update tests or whitelist test files explicitly |
| **Partially-completed M12 state** (stamp set + some columns added + some not) | HIGH | Remediation CLI must idempotently detect partial-application — not just "stamp says 12 → run body fresh". M11 partial-state detection is conditional on Open Question 7. |
| Hash-input change silently re-imports/prunes 1581 memory entries | MEDIUM | Treat as schema migration; backfill recomputes stored hashes; dry-run gate reports n_shifted, proceeds only if shifted matches expected set |
| Two-pass workspace fallback enables silent cross-workspace mutation | MEDIUM | Fallback strictly gated to canonical `_UNKNOWN_WORKSPACE_UUID` UUID only; log warning when fired |
| M11 has the same stub-trap pattern at `database.py:1818, 1899` | MEDIUM | Cluster A.2 audits and tightens M11 guard (committed in-scope) |
| 4 (not 3) MCP write paths lack workspace gates | LOW | Cluster E covers all four (`add_okr_alignment` + `add_entity_tag` included) |

## Open Questions (deferred to specify phase)

1. **Auto-invoke vs prompt for M12 remediation**: Does doctor execute the fix silently if detected, or prompt? **Default proposal**: prompt at session-start via AskUserQuestion, one-click YES.
2. **Cross-workspace triage UX**: CLI subcommand or doctor fix_action? **Default**: doctor fix_action with interactive prompt per link (Cluster E.2).
3. **Hash backfill scope**: Re-hash ALL 1581 entries, or only `source='import'` and `source='session-capture'`? **Default**: all; dry-run reports shifted-set, proceed if matches expected (the 10 known inflated + writer/importer drift rows).
4. **`update_entity` emit gating**: Skip emit if status is unchanged (no-op write)? **Default**: skip — matches `upsert_entity:6699-6708` precedent. **Edge case**: if `metadata` is changing but status isn't, still no emit (status-change-only event).
5. **AST whitelist removal timing**: Before or after Cluster C emit lands? **Default**: after — emit must be verified working across all 16 callers first; then sweep tests; then remove whitelist.
6. **Data migration for `_UNKNOWN_WORKSPACE_UUID` entities**: Re-attribute to current workspace if exactly one workspace exists for the project? **Default**: defer to a follow-up feature unless implementation reveals it's small.
7. **Partial-M11 recovery code**: Does Cluster A.2 ship a partial-M11 idempotency detector, or document the limitation if partial-M11 state is empirically unobserved? **Default**: detect-and-skip — share the partial-M12 detector pattern (one helper, two registrations) only if implementation reveals zero cost.

## Next Steps

→ Promote to Feature → `/pd:specify` to crystallize FRs and ACs across the 5 clusters (8 sub-deliverables including A.2 and E.2) → `/pd:design` to lock implementation contracts → `/pd:create-plan` honoring cluster sequencing → `/pd:implement` → `/pd:finish-feature`.

## Reference Files

- Brainstorm source: `docs/brainstorms/112-pd-data-model-hardening-source.md` (full evidence base, repro scripts cited)
- Key code paths:
  - `plugins/pd/hooks/lib/entity_registry/database.py:2683` (M12 guard), `:1818,1899` (M11 same trap — Cluster A.2), `:7094-7236` (update_entity), `:455` (observation_count bump)
  - `plugins/pd/mcp/workflow_state_server.py:1184` (H8 site 3)
  - `plugins/pd/mcp/entity_server.py:562, 704` (H8 sites 1+2), `:734-739` (issue_spawn gate — pattern to replicate), `:807,1149,1281,1087` (4 missing gates)
  - `plugins/pd/hooks/capture-tool-failure.sh:34,147-157` (H2 mode gate + heuristic branch)
  - `plugins/pd/hooks/lib/semantic_memory/writer.py:300-328` (CLI bypass), `importer.py:86,91,114` (hash drift)
  - `plugins/pd/hooks/lib/doctor/check_status_write_path.py:37` (AST whitelist)
  - `plugins/pd/hooks/lib/doctor/fixer.py:36`, `fix_actions.py` (precedent pattern for new fix_action)

## Review History

### Review 2 (2026-05-16) — pd:prd-reviewer
**Findings:** 3 warnings + 2 suggestions (0 blockers; all iter-1 blockers verified resolved)
- [warning, evidence] '16 callers' count cannot be replicated by the pinned single-line grep — multi-line invocations not visible
- [warning, testability] Goal 2 'stderr warning' lacks measurable bar — no structured marker
- [warning, decomposition] Cluster A.2 partial-M11 state not addressed analogous to partial-M12
- [suggestion, scope] Goal 5 fourth bullet 'goes through' is structural not binary
- [suggestion, constraint] A.2 / partial-state risk row cross-reference

**Corrections Applied:**
- Enumerated call sites by file:line in Problem section + replaced pinned grep with multi-line `rg -nU` command (16 single-line + multi-line callers enumerated; implement re-verifies)
- Tightened Goal 2 to require stderr warning tagged `pd.audit.emit_failed` with JSON fields `{type_id, old_status, new_status, exception_class}`; doctor surfaces emit-failure rate as health-check metric
- Extended Risks partial-M12 row to cover partial-M11; shared idempotency detector pattern referenced
- Tightened Goal 5 last bullet to binary: 'exactly one call to `_apply_quality_gates(...)` before any `db.upsert_entry(...)`' + integration-test assertion
- Cluster A.2 scope boundary cross-references the partial-state risk row explicitly
- Added Open Question 7 covering partial-M11 detect-vs-document decision

### Review 1 (2026-05-16) — pd:prd-reviewer
**Findings:** 4 blockers + 4 warnings + 2 suggestions
- [blocker, evidence] `_workspace_uuid or ""` pattern claim was factually wrong — confirmed exists at 3 sites
- [blocker, scope] Missing Non-Goals + Scope Boundary per cluster
- [blocker, testability] Goals 4 & 5 fuzzy; needed binary count-based criteria
- [blocker, decomposition] Missing Cluster Sequencing
- [warning, evidence] "28 callers" claim — actually 16 (test files excluded); methodology pinned
- [warning, risk] Missing: Cluster C depends on D, AST whitelist test-fixture risk, partially-completed M12
- [warning, constraint] Goal 2 observability-vs-transactional trade-off needed surfacing
- [warning, scope] M11 silent scope expansion → made explicit as Cluster A.2

**Corrections Applied:**
- Restored correct `_workspace_uuid or ""` claim with 3 sites
- Corrected caller count 28 → 16 with pinned grep command
- Added Non-Goals section explicitly listing H1, H5, H7, H9a deferred items + hard-error Cluster E escalation
- Added Cluster Sequencing section with strict order: A‖A.2 → D → C → B-H4 → B-H3‖B-H2 → E‖E.2
- Added Per-Cluster Scope Boundaries section for all 7 sub-clusters
- Rewrote Goal 4 with binary "0 cross-workspace links" criterion + 3-option triage outcomes
- Rewrote Goal 5 with binary counts (464 prune, 10 reset, deleted branch)
- Rewrote Goal 2 to explicitly call out observability-grade trade-off
- Added 3 new Risk rows: emit-D-coupling, AST-whitelist-tests, partial-M12
- Made Cluster A.2 (M11) explicit with its own scope boundary
- Counterexamples-considered bullets added under both advisor sections
- Tightened dry-run gate to expected-set match (not >0)
