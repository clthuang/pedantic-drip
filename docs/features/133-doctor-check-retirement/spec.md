# Spec: 133-doctor-check-retirement

## Problem & evidence

- P004 FR-12 + prd.md:47: doctor session-start warnings on a healthy workspace → **0** (from 601). prd.md:22: ~96% of live warnings are DB↔`.meta.json`/filesystem **dual-truth drift** — a surface made structurally impossible by the shipped chain: 126 (lossless projection) → 127 (deny-by-default guard, `_project_meta_json` sole writer) → 128 (degraded mutations fail loud, fallback writer deleted) → 132 (rebuild + fail-closed dual-write). The checks don't crash — every table they query still exists (132 replays the v1 chain; schema_v2 core is dark) — they are **vacuous defenders of an extinct drift class**.
- 19 checks at HEAD: `CHECK_ORDER` (doctor/__init__.py:41-77), `_ENTITY_DB_CHECKS` 9-member skip-gate (:80-90), runner :114-253. The count is pinned by CONTENT-equality (test_doctor.py:19-49 `expected_names`), not a numeric constant.
- **The PRD's "12 of 21" is a dated literal** (author-restated-literal discipline applied to the PRD itself): it was authored at the 21-check census, and TWO checks of exactly this class are ALREADY deleted — `check_project_attribution` (131) and `check_cross_workspace_parent_uuid` (129, spec.md:25 "count 20 → 19"). Membership below is pinned by CRITERION; the resulting count is derived, not inherited.
- Live-warning profile (129-era capture `.doctor-after.txt`, refreshed at implement): 674 warnings ≈ 99% from four retire-candidates (`entity_orphans` 289, `feature_status` 253, `workflow_phase` 140, `brainstorm_status` 5).

## Functional Requirements

- **FR133-1 (retirement criterion + membership):** Retire every check whose queried surface is (a) DB↔file dual-truth drift (extinct per the 126/127/128/132 chain) or (b) the retired 108-era workspace-identity/split-brain class, or (c) the 132-deleted audit-counter increment path. Membership — **TEN** checks, each with surface evidence:
  1. `check_feature_status` (checks.py:722) — `.meta.json`↔`entities.status` drift (a)
  2. `check_workflow_phase` (:876) — `.meta.json`↔`workflow_phases` drift via `check_workflow_drift` (a)
  3. `check_branch_consistency` (:1284) — `.meta.json` branch ↔ git ↔ DB drift (a)
  4. `check_entity_orphans` (:1448) — DB↔filesystem orphan drift; the 320-false-positive bucket the PRD names (a)
  5. `check_brainstorm_status` (:1038) — promotion-linkage sync drift, reconciler-era noise (a-adjacent; skeptic adjudicates)
  6. `check_backlog_status` (:1196) — closure-linkage sync, info-severity (a-adjacent; skeptic adjudicates)
  7. `check_workspace_uuid_consistency` (:362) — 108-era split-brain identity (b); the live fail-loud guard is `_validated_provided_workspace_uuid` (database.py, re-homed at 132)
  8. `check_unknown_workspace_orphans` (:598) — `_UNKNOWN_WORKSPACE_UUID` era (b)
  9. `check_audit_emit_failed_count` (:2134) — counter's ONLY increment path deleted at 132 (database.py:7940-7946 comment names this check as 133's concern); counter is structurally 0 forever (c)
  10. `check_audit_counter_write_path` (check_audit_counter_write_path.py) — AST guard over the same dead counter; only `_migration_15` writes remain, which it permits (c)
  **EXPLICITLY RETAINED despite the PRD's era-count:** `check_referential_integrity` (:1657 — live parent_uuid/FK/tags integrity, not drift) and `check_missed_cascade` (:1830 — 124's live cascade class). With the two already-deleted era checks, the PRD's "12" reconciles as 10 here + 2 shipped earlier.
  Each retirement deletes atomically: the check fn, its `CHECK_ORDER` + `_ENTITY_DB_CHECKS` entries, its fix actions + `fixer.py` `_SAFE_PATTERNS` rows (enumerate the exact fn set at design from fix_actions/__init__.py:43-449), and its test classes (survey-mapped; the four sibling-file checks carry their own test files).
- **FR133-2 (129 carry-forwards, charter-named):** (i) `export_entities_json` (database.py:8754-8760) gains `workspace_uuid` filtering symmetric with the query surface (legacy `project_id` param RETAINED per 132 #082's descope precedent — additive, not a signature break); (ii) `reconcile_check` (workflow_state_server.py:2231-2238) threads `workspace_uuid=_workspace_uuid or None` exactly like its three siblings (:2255/:2270/:2285).
- **FR133-3 (132 parked dispositions):** (i) audit-counter subsystem: the two checks retire (FR133-1.9/.10) but **migration 15's body stays byte-untouched** — chain-replay DDL identity is 132's SC1 contract; the counter row remains as inert `_metadata` (deletion is v1-retirement work). (ii) `test_schema_v2.py` ships-dark guard: its premise (v2 modules have no live importers) died at 132 when database.py became a sanctioned importer — disposition at design: retire-with-record or re-scope to non-sanctioned-importers-only; silent retention forbidden. (iii) **The one ADDITIVE item** (132 design.md:37/:84 parked it here): a marker-aware `check_v2_cutover_window` reading `~/.claude/pd/migrations/v2-cutover.json` + the `entities.db.v1-readonly` file — silent when no marker (pre-cutover state, the shipping default), info within the 30-day window, warning past expiry (old file still present after the escape-hatch window closes).
- **FR133-4 (doc-count sweep, docs-sync gotcha):** `plugins/pd/commands/doctor.md:7` is STALE at "21" today — all count sites move to the FINAL count in one sweep: doctor.md, README.md:36/:117, plugins/pd/README.md:83 (per CLAUDE.md these drifted silently at 129 AND 131); the stale test-class names `TestOrchestratorReportHas14Checks`/`TestCliJsonOutputHas14Checks` rename in the same change; 129's `.qa-gate-low-findings.md:6` refresh note is satisfied. README.md:36's separate "12 environment checks" is a DIFFERENT surface (system-prereq doctor) — must NOT be conflated or edited.

## Success Criteria

- **SC1 (the PRD's number, non-vacuous):** a doctor run on a HEALTHY seeded workspace (fresh tmp DB + consistent projections) reports 0 errors + 0 warnings (info permitted). Non-vacuity control: the same fixture WITH a seeded live-surface fault (e.g. a self-referential parent_uuid) still fires the RETAINED `check_referential_integrity` — proving the zero comes from retirement, not a broken runner.
- **SC2 (membership pin):** test_doctor.py's content-equality list = exactly the 9 survivors + `check_v2_cutover_window` = **10 checks**; `_ENTITY_DB_CHECKS` correspondingly pruned.
- **SC3 (zero dangling references):** for EVERY retired check fn name and every deleted fix-action fn name: `git grep -F '<name>' -- plugins/pd/` → exit 1 (tracked source; docs/features/** + CHANGELOG historical prose exempt by construction).
- **SC4 (carry-forward pins, facts true only on the new paths):** workspace-scoped `export_entities_json` excludes other-workspace entities from the export (asserted on content, not just no-exception); `reconcile_check` resolves under a provided workspace_uuid where the unthreaded call would have fallen to the legacy path (assert scoping-visible difference).
- **SC5 (marker check three-state pin):** no marker → check emits NOTHING (not even info — pre-cutover is the healthy default and SC1 depends on it); fresh marker → info naming the expiry date; past-expiry marker + v1-readonly file still present → warning naming the file.
- **SC6 (chain-replay identity):** 132's chain-replay DDL-identity test re-run green (migration 15 byte-untouched).
- **SC7 (repo gates):** full suite + hooks 67/67 + validate 0 errors; all four doc count sites agree on the SAME final number (grep-verified in one gate).

## Hazards

- **H1 (session-start coupling):** `session-start.sh:542-584` runs `python -m doctor --fix` and sums counts — verify it holds no retired-check or fix-action NAME coupling (it appears count-based; verify at design).
- **H2 (fixer ordering):** `_SAFE_PATTERNS` is first-match-wins (fixer.py:34-57) — deletions must not re-order surviving prefixes' match semantics; pin with a survivor-fix test.
- **H3 (atomic membership edits):** the content-equality pin makes every membership change a coupled code+test edit; land per-check or as one atomic sweep, never half.
- **H4 (silent consumers of retired checks):** grep for programmatic consumers of retired check ids/output keys (reconciler, hooks, UI) before deletion — a consumer reading a missing key must fail loud or be swept in the same change (#078 call-graph-first).
- **H5 (marker-check fs semantics):** the check reads the REAL `~/.claude/pd/migrations/` only in production; tests must use tmp-path isolation (132's PD_REBUILD_MARKER_DIR precedent).

## Non-goals

- Executing the v1→v2 cutover or #085's census cleaning (post-merge, manual).
- #082's project_id kwarg retirement; deleting migration 15 or the counter row (v1-retirement track).
- PRD/brainstorm planning-prose count refresh (docs/projects/**, docs/brainstorms/** stay historical).
- The "12 environment checks" prereq surface (different command; README.md:36 conflation guard).

## Open questions

- **OQ-1:** brainstorm_status/backlog_status/entity_orphans membership — the skeptic adjudicates each against the criterion (backlog #060's interim manual-backlog reality argues backlog_status's linkage checking is already moot; entity_orphans is the PRD's own named false-positive bucket).
- **OQ-2:** marker-check severity ladder confirmed at design (SC5's proposal is the default).
- **OQ-3:** ships-dark guard disposition (FR133-3.ii) — design picks retire-with-record vs re-scope.
