# Spec: Feature 091 — 082 QA Residual Cleanup

## Status
- Created: 2026-04-20
- Phase: specify (started; spec-reviewer iteration 1 applied)
- Mode: standard
- Source PRD: `docs/features/091-082-qa-residual-cleanup/prd.md`

## Scope

This feature addresses the 27 open Feature 082 backlog items. Codebase verification revealed 23 items are already implemented in features 088/089; 4 items are genuinely open; 1 new finding (`New-082-inv-1`) was discovered during investigation.

**Ground-truth count** (reconciled with PRD):
- **27 items total** (#00075–#00079 + #00095–#00116)
- **23 fixed** in features 088/089 (22 full closure + 1 partial — #00116 a+b only)
- **4 open** (#00076, #00077, #00078, #00079)
- **1 new finding** (`New-082-inv-1` — not in existing backlog; filed post-merge via FR-7)

**In scope:**
- **Backlog hygiene** (FR-1): 22 stale backlog entries gain `(fixed in feature:N)` closure markers; 1 entry (#00116) gains a `(partially fixed in feature:088 — sub-items a, b; c–j deferred)` annotation.
- **Code fixes** (FR-2 through FR-6): 4 genuinely-open backlog items + 1 new finding.
- **Post-Merge Administrative Tasks** (below): file a new backlog entry for `New-082-inv-1` after feature merge.

**Out of scope (deferred — see Out of Scope section):** `_config_utils.py` SPOF mitigation, closure-marker automation, #00116 sub-items c–j, #00110 re-verification (treat as benign).

## Functional Requirements

### FR-1: Backlog hygiene (23 markers)

Annotate entries in `docs/backlog.md` per the existing closure convention (see line 48: `(closed: merged into 00018)`, line 75: `(fixed in feature:085-memory-server-hardening)` — parenthetical inline).

**Ground-truth mapping** — each row below corresponds to exactly one backlog.md line; the marker is appended before the closing `|` of the Description column (for rows inside the table at top of file) or after the finding text (for list-style rows below the table).

| # | Backlog ID | Action | Exact marker text |
|---|-----------|--------|-------------------|
| 1 | #00075 | closure | ` (fixed in feature:089 — Python subprocess fallback with timeout=10)` |
| 2 | #00095 | closure | ` (fixed in feature:088 — sys.argv positional args throughout session-start.sh)` |
| 3 | #00096 | closure | ` (fixed in feature:088, feature:089 — try/except OverflowError + type-exact bool coerce)` |
| 4 | #00097 | closure | ` (fixed in feature:089 — O_NOFOLLOW + uid-check + fstat)` |
| 5 | #00098 | closure | ` (fixed in feature:088 — shared _config_utils.py single source)` |
| 6 | #00099 | closure | ` (fixed in feature:089 — _iso_utc Z-suffix canonical helper)` |
| 7 | #00100 | closure | ` (fixed in feature:088 — spec Amendment C + capsys assertions in AC-11a/b/c)` |
| 8 | #00101 | closure | ` (fixed in feature:088 — spec Amendment A + skipped_floor=2 test assertion)` |
| 9 | #00102 | closure | ` (fixed in feature:088 — all 6 decay DEFAULTS keys in config.py)` |
| 10 | #00103 | closure | ` (fixed in feature:088 — --project-root st_uid check in maintenance.py)` |
| 11 | #00104 | closure | ` (fixed in feature:088 — insert_test_entry_for_testing + execute_test_sql_for_testing helpers)` |
| 12 | #00105 | closure | ` (fixed in feature:088 — _config_utils.py single impl with functools.partial bindings)` |
| 13 | #00106 | closure | ` (fixed in feature:088 — dead now_iso param removed from _select_candidates)` |
| 14 | #00107 | closure | ` (fixed in feature:088 — LIMIT ? with scan_limit clamped to [1000, 500000])` |
| 15 | #00108 | closure | ` (fixed in feature:088 — spec Amendment B for FR-2 NULL-branch)` |
| 16 | #00109 | closure | ` (fixed in feature:088 — spec detailed threading contract at AC-20b)` |
| 17 | #00111 | closure | ` (fixed in feature:088 — _TEST_EPOCH rename with NOW alias)` |
| 18 | #00112 | closure | ` (fixed in feature:089 — PATH pin + venv hard-fail + trap-safe restore)` |
| 19 | #00113 | closure | ` (fixed in feature:088 — test_exact_threshold_boundary_is_not_stale at test_maintenance.py:1735)` |
| 20 | #00114 | closure | ` (fixed in feature:089 — _iso_utc raises ValueError on naive datetime)` |
| 21 | #00115 | closure | ` (fixed in feature:088 — decay×record_influence + decay×FTS5 integration tests)` |
| 22 | #00116 | partial | ` (partially fixed in feature:088 — sub-items (a) empty-DB + (b) special-char FTS5 entry IDs; sub-items (c) update_recall+decay race, (d) NaN/Inf config, (e) session-start double-fire microsecond race, (f) CLI hang-past-timeout, (g) sqlite error during SELECT, (h) update_recall+decay race, (i) promote-decay-promote cycle, (j) last_recalled_at NOT NULL AND recall_count=0 — all deferred to future test-hardening feature)` |

Total: 22 closures + 1 partial annotation = **23 markers for 23 PRD-claimed-fixed IDs**.

**#00110 treatment:** NOT modified by this feature. Per PRD, #00110 is not in the "already fixed" list; the finding text (agent_sandbox/082-eqp.txt stale artifact) is a benign documentation discrepancy with no code impact. Retained in backlog as-is for potential future decision. (Per spec-reviewer warning 6: dropping #00110 from scope eliminates the ambiguity.)

The 4 open items (#00076, #00077, #00078, #00079) receive their `(fixed in feature:091-082-qa-residual-cleanup)` markers as part of this feature's `/pd:finish-feature` retro step — NOT during implement phase. This separation keeps FR-1 focused on retroactive closures only.

### FR-2: #00076 — equal-threshold warning

When `memory_decay_medium_threshold_days` ≤ `memory_decay_high_threshold_days`, maintenance MUST emit an stderr warning (same format as the existing strict-less-than case). Default behavior per PRD Open Question #5: emit warning only; do NOT short-circuit single-tier semantics.

**Required change:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424` change guard from `if med_days < high_days and not _decay_config_warned:` to `if med_days <= high_days and not _decay_config_warned:`. Update warning text to reflect `<=` semantics: replace `f"({med_days}) < memory_decay_high_threshold_days ({high_days});"` with `f"({med_days}) <= memory_decay_high_threshold_days ({high_days});"` and update the downstream sentence to `"medium tier will decay at same pace or faster than high"`.

**Dedup flag handling:** Tests must reset `maintenance._decay_config_warned = False` before each assertion. The existing autouse `reset_decay_state` fixture at `test_maintenance.py:41` already handles this (`monkeypatch.setattr(maintenance, "_decay_config_warned", False)`); new tests in FR-2's acceptance criteria rely on this fixture.

### FR-3: #00077 — AC-22 test expansion

`plugins/pd/hooks/tests/test-hooks.sh` AC-22 at lines 2910-2952 currently tests only the file-missing failure mode. Extend coverage to SyntaxError and ImportError modes.

**Important behavioral constraint (discovered during spec review):** `session-start.sh:719,735` invokes `maintenance.py` with `2>/dev/null || true` — all stderr from the module is suppressed by the shell guard. AC-22 therefore CAN NOT assert stderr content; it can only assert exit status 0 (which proves the guard caught the failure). This is consistent with the existing AC-22 pattern in test-hooks.sh:2910-2952.

**Required behavior:** two new test blocks, each following the AC-22 exit-status pattern:
- **AC-22b (SyntaxError):** back up `plugins/pd/hooks/lib/semantic_memory/maintenance.py`; inject a syntactically invalid line at end of file (e.g., `def broken(:`); run `session-start.sh` (or invoke the `run_memory_decay` function directly via `bash -c 'source session-start.sh; run_memory_decay'`); assert exit 0; restore the file.
- **AC-22c (ImportError):** same pattern, but inject `from nonexistent_module import anything` at the top of `maintenance.py`; assert exit 0; restore.

Both tests MUST use a `trap "cp $BACKUP $TARGET" EXIT` pattern so teardown restores the file even on test failure.

### FR-4: #00078 — public `scan_decay_candidates` method

Add a new public method on `MemoryDatabase` to encapsulate the read path currently at `maintenance.py:259`.

**Anti-pattern context (knowledge-bank HIGH confidence):** This fix addresses "Direct `db._conn` Access in Reconciliation Code" — the exact anti-pattern the new method closes. Design phase will also enumerate the SQL injection surface per "Dynamic SQL Construction Without Design-Time Injection Surface Enumeration" (also HIGH).

**Required method signature:**
```python
def scan_decay_candidates(
    self,
    *,
    not_null_cutoff: str,
    scan_limit: int,
) -> Iterator[sqlite3.Row]:
    """Yield candidate rows for decay confidence processing (generator).

    Encapsulates the read path previously inlined at maintenance.py:259.
    Schema: rows have (id, confidence, source, last_recalled_at, created_at).
    """
```

**Required SQL (pinned verbatim):**
```python
"SELECT id, confidence, source, last_recalled_at, created_at "
"FROM entries "
"WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
"   OR (last_recalled_at IS NULL) "
"LIMIT ?"
```
Parameters bound positionally: `(not_null_cutoff, scan_limit)`. The implementation MUST reproduce this string byte-for-byte (copied from current `maintenance.py:260-266`) — no restructuring, no simplification, no reformatting.

**Edge-case behavior (scan_limit):** Callers are responsible for pre-clamping `scan_limit` to a sensible range. Current production callers (`_select_candidates`) receive the already-clamped value from `_resolve_int_config` which bounds it to `[1000, 500000]`. The new method does NOT re-validate; a caller passing `scan_limit <= 0` receives zero rows (SQLite LIMIT semantics) with no exception. This matches current behavior.

**Required caller update:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:_select_candidates` (lines 259-268) replaces `db._conn.execute(...)` + `for row in cursor: yield row` with `yield from db.scan_decay_candidates(not_null_cutoff=not_null_cutoff, scan_limit=scan_limit)`.

### FR-5: #00079 — remove dead SQL branch

Remove the `updated_at IS NULL OR` clause from `_execute_chunk` SQL.

**Required change:** `plugins/pd/hooks/lib/semantic_memory/database.py:1028` change `f"  AND (updated_at IS NULL OR updated_at < ?)"` to `f"  AND updated_at < ?"`.

**Schema evidence (Assumption A2 verified during spec review):**
- `database.py:114` original schema: `updated_at TEXT NOT NULL`
- `database.py:255` migrated schema: `updated_at TEXT NOT NULL,`
- `database.py:870-871` defensive coercion: `if updated_at is None: updated_at = created_at`
- No `ALTER TABLE entries ADD COLUMN updated_at` without `NOT NULL DEFAULT ...` exists in the migration chain (grep confirmed — the only ALTER TABLE entries ADD COLUMN calls target `source_hash`, `created_timestamp_utc`, `influence_count`, not `updated_at`).

Conclusion: no production path can produce a NULL `updated_at`; the branch is dead.

### FR-6: New-082-inv-1 — test isoformat drift

Replace `.isoformat()` calls with the existing `_iso()` helper in `TestSelectCandidates.test_partitions_six_entries_across_all_buckets`.

**Required change:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:401-410` — remove the local `NOW = datetime(...)` shadow at line 401 and replace the 9 `.isoformat()` calls with calls to `_iso()` (defined at `test_maintenance.py:510-516`).

Before:
```python
def test_partitions_six_entries_across_all_buckets(self, fresh_db):
    NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)
    now_iso = NOW.isoformat()
    high_cutoff = (NOW - timedelta(days=30)).isoformat()
    med_cutoff = (NOW - timedelta(days=60)).isoformat()
    grace_cutoff = (NOW - timedelta(days=14)).isoformat()
    stale_high_ts = (NOW - timedelta(days=100)).isoformat()
    stale_med_ts = (NOW - timedelta(days=100)).isoformat()
    fresh_in_grace_ts = (NOW - timedelta(days=10)).isoformat()
    past_grace_ts = (NOW - timedelta(days=80)).isoformat()
```

After:
```python
def test_partitions_six_entries_across_all_buckets(self, fresh_db):
    # NOW resolves to module-level _TEST_EPOCH alias at line 507
    now_iso = _iso(NOW)
    high_cutoff = _iso(NOW - timedelta(days=30))
    med_cutoff = _iso(NOW - timedelta(days=60))
    grace_cutoff = _iso(NOW - timedelta(days=14))
    stale_high_ts = _iso(NOW - timedelta(days=100))
    stale_med_ts = _iso(NOW - timedelta(days=100))
    fresh_in_grace_ts = _iso(NOW - timedelta(days=10))
    past_grace_ts = _iso(NOW - timedelta(days=80))
```

**Assumption A6 (pinned during spec review):** `_TEST_EPOCH` is defined as `datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)` at `test_maintenance.py:506`, matching the prior local `NOW` shadow exactly. If a future feature modifies `_TEST_EPOCH`, this test's fixture constants will silently change — reviewer of such future feature must re-verify `TestSelectCandidates` assertions.

## Post-Merge Administrative Tasks

These are process items, not code/test changes. Tracked separately to keep FR scope focused on implementation.

### PA-1: File new backlog entry for `New-082-inv-1`

After feature merges (during `/pd:finish-feature` retro step), append a new entry to `docs/backlog.md`:

```markdown
- **#{next-id}** **[LOW/observation]** TestSelectCandidates (now fixed in feature:091) demonstrated that pytest fixtures using `.isoformat()` produce `+00:00` suffix while production `_iso_utc` uses `Z` suffix. Consider a linter or pre-commit check that flags `\.isoformat\(\)` calls inside `test_*.py` files within `semantic_memory/` module. Low priority — tests are already aligned post-feature:091.
```

### PA-2: Append `(fixed in feature:091-082-qa-residual-cleanup)` markers

After merge, append closure markers to backlog entries #00076, #00077, #00078, #00079 matching the FR-1 convention.

## Non-Functional Requirements

### NFR-1: LOC budget
- Net production LOC change: ≤ +250 (primarily `scan_decay_candidates` method body ≈ 15 LOC + generator delegation, `<=` predicate change 1 LOC, SQL edit -1 LOC, warning text update 1 LOC)
- Net test LOC change: ≤ +200 (AC-22b/c ≈ 60 LOC each, equal-threshold warning tests ≈ 30 LOC, scan_decay_candidates tests ≈ 40 LOC)

### NFR-2: Zero regressions
- All tests in `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` pass.
- All tests in `plugins/pd/hooks/lib/semantic_memory/test_database.py` pass.
- `plugins/pd/hooks/tests/test-hooks.sh` full suite passes.

### NFR-3: `./validate.sh` passes
Covers plugin structure, frontmatter, path portability.

### NFR-4: `pd:doctor` passes
Entity registry consistency, orphaned worktrees.

### NFR-5 (aspirational): Reviewer iteration target
**Aspirational target** (not a pass/fail gate): ≤ 2 iterations per reviewer per phase. If exceeded, capture signal in retro.md for the recurring-residual-cycle pattern analysis. No AC enforces this — it is a retrospection metric.

## Acceptance Criteria

### Backlog hygiene

- **AC-1 (exact-count verification):** For each of the 23 IDs in FR-1's mapping table, assert the `docs/backlog.md` line for that ID contains the exact marker text from the table. Implementation: shell loop or awk pass over the mapping table, fail on any mismatch.
- **AC-1b:** `./validate.sh` passes post-edit (no broken table structure).
- **AC-1c:** `grep -cE "^[|\-].*#(0007[59]|009[5-9]|010[0-9]|011[0-6])" docs/backlog.md` equals `27` (no backlog entries lost or duplicated).

### #00076 (FR-2)

- **AC-2:** `grep -cE "if med_days <= high_days" plugins/pd/hooks/lib/semantic_memory/maintenance.py` equals `1`.
- **AC-2b:** `grep -cE "if med_days < high_days" plugins/pd/hooks/lib/semantic_memory/maintenance.py` equals `0` (old strict-less-than predicate removed).
- **AC-3 (equal case):** new test `test_equal_threshold_emits_warning` in `test_maintenance.py` seeds config with `med_days = high_days = 30`, calls `decay_confidence`, asserts `re.search(r"\[memory-decay\].*medium_threshold.*high_threshold", capsys.readouterr().err)` is non-None. Relies on autouse `reset_decay_state` fixture at line 41 to reset `_decay_config_warned`.
- **AC-3b (strict-less case regression):** parallel test `test_strictly_less_threshold_still_emits_warning` pins `med_days=10, high_days=30`, same assertion. Ensures `<=` predicate swap does not regress the prior `<` behavior.

### #00077 (FR-3)

- **AC-4a (SyntaxError):** `test-hooks.sh` contains a test block labeled `AC-22b`. Block backs up `plugins/pd/hooks/lib/semantic_memory/maintenance.py`, injects `def broken(:` at EOF, invokes `bash -c 'source plugins/pd/hooks/session-start.sh; run_memory_decay'`, asserts exit 0, restores the file via `trap` on EXIT.
- **AC-4b (ImportError):** `test-hooks.sh` contains a test block labeled `AC-22c`. Same pattern but injects `import no_such_module_really` at line 1, asserts exit 0, restores via trap.
- **AC-4c:** no stderr assertions — `session-start.sh:719,735` suppresses stderr via `2>/dev/null`, so stderr-based assertions are impossible by design. Tests verify exit-status invariant (which is the actual contract: shell guard always tolerates).

### #00078 (FR-4)

- **AC-5:** `grep -cE "def scan_decay_candidates\(" plugins/pd/hooks/lib/semantic_memory/database.py` equals `1`.
- **AC-5b (SQL pinning):** the method body contains the verbatim SQL string specified in FR-4 (byte-for-byte match, validated via `grep -F` with the 4-line concatenated string).
- **AC-6:** `grep -cE "db\._conn" plugins/pd/hooks/lib/semantic_memory/maintenance.py` equals `0` (was 1 at line 259).
- **AC-7 (bounded LIMIT):** new test `test_scan_decay_candidates_respects_scan_limit` in `test_database.py` seeds 10 rows with distinct IDs, calls `list(db.scan_decay_candidates(not_null_cutoff=..., scan_limit=5))`, asserts length == 5.
- **AC-7b (NULL branch):** new test `test_scan_decay_candidates_includes_null_last_recalled_at` seeds 1 row with `last_recalled_at=None` and 1 row with `last_recalled_at < cutoff`; asserts both returned.
- **AC-7c (generator semantics):** `isinstance(db.scan_decay_candidates(...), collections.abc.Iterator)` — regression test so future refactor doesn't silently return a list.
- **AC-7d (regression):** existing `TestSelectCandidates` tests (6 rows across all buckets) still pass after the caller update — verifies SQL + partition semantics unchanged.

### #00079 (FR-5)

- **AC-8:** `grep -cE "updated_at IS NULL" plugins/pd/hooks/lib/semantic_memory/database.py` equals `0`.
- **AC-8b:** existing test suite at `test_database.py` covering `batch_demote` / `_execute_chunk` still passes (the `updated_at < ?` live branch is unchanged; only the dead `IS NULL` clause is removed).

### New-082-inv-1 (FR-6)

- **AC-9 (scoped grep):** `sed -n '397,495p' plugins/pd/hooks/lib/semantic_memory/test_maintenance.py | grep -cE '\.isoformat\(\)'` equals `0` (no `.isoformat()` calls inside `TestSelectCandidates` class body, which spans lines 397-495).
- **AC-9b:** `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` passes after the swap — verifies semantics unchanged.
- **AC-9c (canonical format pin):** new assertion at top of test: `assert _iso(NOW) == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")` — pins the canonical format the test expects.

### Post-Merge Admin

- **AC-PA-1:** Retro step appends new-finding entry to `docs/backlog.md` (verified during `/pd:finish-feature`).
- **AC-PA-2:** Retro step appends `(fixed in feature:091-082-qa-residual-cleanup)` markers to #00076, #00077, #00078, #00079 in `docs/backlog.md`.

### Structural exit gate (per PRD Structural Success Criterion #1)

- **AC-11 (freeze procedure):** If Stage-5 adversarial reviewer during `/pd:implement` surfaces any finding tagged `[HIGH/*]` that is NOT in the FR-1 through FR-6 scope above, then:
  - (a) no code edits are added to this feature;
  - (b) the new finding is filed as a new backlog entry with sufficient detail for later triage;
  - (c) this feature proceeds to merge with its existing scope and notes the deferral in retro.md.
  - Decider: feature author at merge-review time.

## Assumptions

1. **A1:** `_iso()` helper semantics match `_iso_utc`. Verified in `test_maintenance.py:510-516` — both produce Z-suffix via `strftime("%Y-%m-%dT%H:%M:%SZ")` after `astimezone(timezone.utc)`. Relied on by FR-6.
2. **A2:** Schema `updated_at NOT NULL` predates any production data that could have NULL. Verified: `database.py:114,255` both enforce NOT NULL; no `ALTER TABLE entries ADD COLUMN updated_at` exists; defensive coercion at `database.py:870-871` (`if updated_at is None: updated_at = created_at`). Relied on by FR-5.
3. **A3:** `scan_decay_candidates` has no callers besides `_select_candidates`. Verified by grep — `maintenance.py:259` is the sole current `db._conn.execute` for this predicate.
4. **A4:** `#00110`'s `agent_sandbox/082-eqp.txt` is not consumed by any test or validator. Verified: file referenced only in the 082 retro. Treat as benign — no action this feature.
5. **A5:** `/pd:finish-feature` retro step can append to `docs/backlog.md`. Evidence: feature 090 used `chore: close backlog` commits in retro.
6. **A6:** `_TEST_EPOCH` at `test_maintenance.py:506` matches the prior local `NOW` shadow (`datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)`). Relied on by FR-6 — reviewer of any future feature modifying `_TEST_EPOCH` must re-verify `TestSelectCandidates` assertions.
7. **A7:** Session-start.sh `2>/dev/null` suppression is INTENTIONAL (FR-8/I-1 "errors must not corrupt hook JSON output", noted in-line at session-start.sh:713). Stderr-based assertions are impossible; AC-22b/c limited to exit-status assertions.

## Risks

1. **R1 [MED]:** FR-2 predicate swap `<` → `<=` perturbs existing `<` tests if they assume strict-less-than semantics. **Mitigation:** AC-3b pins the `<` case; full test suite runs before and after.
2. **R2 [LOW]:** FR-4 signature change affects downstream consumers in tests. **Mitigation:** grep confirmed no external callers; AC-5/AC-6 + AC-7d regression guard.
3. **R3 [LOW]:** FR-6 edit surfaces format-dependent latent bugs masked by coincidence. **Mitigation:** run `TestSelectCandidates` before + after; if behavior differs, the test was previously unsound → surface as warning.
4. **R4 [MED]:** Structural exit gate (AC-11) is enforced at `/pd:implement`, not `/pd:specify`. Spec must be tight enough that implement-phase review does not surface structural HIGH findings. **Mitigation:** this spec's test ACs cover mutation-resistance cases (AC-3b, AC-7c).
5. **R5 [LOW]:** FR-3 AC-22b/c tests modify a production file; if teardown fails, the repo is corrupted. **Mitigation:** `trap "cp $BACKUP $TARGET" EXIT` + explicit teardown in finally block; test CI runs in a worktree.

## Out of Scope (Explicit)

The following PRD items are deferred:

1. `_config_utils.py` SPOF mitigation (PRD Open Q #2). Out of scope — file separate backlog entry via PA-1 pattern post-merge.
2. Backlog closure-marker automation (PRD Open Q #1). Out of scope — file separate backlog entry.
3. `#00116` sub-item c (`update_recall + decay` race test) + sub-items d–j. Out of scope — LOW priority, requires race investigation first. Annotated in FR-1's partial-fix marker.
4. `#00110` re-verification. Treat as benign documentation discrepancy; no action.

## Evidence Map

| Requirement | Evidence (codebase, verified during spec review) |
|------------|--------------------------------------------------|
| FR-1 mapping convention | `docs/backlog.md:48,75` |
| FR-2 current predicate | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424` (`if med_days < high_days and not _decay_config_warned:`) |
| FR-2 fixture reset | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:41` (autouse `monkeypatch.setattr(maintenance, "_decay_config_warned", False)`) |
| FR-3 current AC-22 block | `plugins/pd/hooks/tests/test-hooks.sh:2910-2952` |
| FR-3 stderr suppression | `plugins/pd/hooks/session-start.sh:713,719,735` (`2>/dev/null || true`) |
| FR-4 current bypass | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259` |
| FR-4 verbatim SQL source | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:260-266` |
| FR-4 anti-pattern | knowledge-bank "Direct `db._conn` Access in Reconciliation Code" (HIGH) |
| FR-5 dead branch | `plugins/pd/hooks/lib/semantic_memory/database.py:1028` |
| FR-5 schema NOT NULL | `plugins/pd/hooks/lib/semantic_memory/database.py:114,255` |
| FR-5 defensive coercion | `plugins/pd/hooks/lib/semantic_memory/database.py:870-871` |
| FR-6 current isoformat calls | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:402-410` |
| FR-6 `_iso()` helper | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:510-516` |
| FR-6 `_TEST_EPOCH` definition | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:506-507` |
| A3 caller grep | `grep -rn "_conn.execute" plugins/pd/hooks/lib/semantic_memory/maintenance.py` → 1 match at line 259 |
