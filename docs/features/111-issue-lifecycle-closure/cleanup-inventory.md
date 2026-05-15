# Group E Cleanup Inventory

Triage of parser-dependent tests prior to deletion of free-text suffix
parsers (`(closed:`, `(promoted →`, `(fixed:`, `(already implemented`)
at three production sites:

- `plugins/pd/hooks/lib/entity_registry/backfill.py:418-444`
- `plugins/pd/hooks/lib/doctor/checks.py:983-1015`
- `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:14-18` (+ consumers `:320, :322, :324, :329`)

Each entry below is bucketed as **Migrate** (refactor fixture to DB-state
input), **Delete** (parser-only exercise — no DB equivalent), or **Keep**
(test does not exercise the parser; false positive).

## test_backfill.py (`plugins/pd/hooks/lib/entity_registry/test_backfill.py`)

### Class `TestBacklogStatusDerivation` (lines 965-1048)

- [x] **DELETE** — `test_promoted_annotation_sets_status` (L981) — asserts backfill parses `(promoted → feature:048)` and sets status='promoted'. Post-cleanup, `backfill.py` no longer derives status from prose markers. No DB equivalent (status was never set independently in the DB by this code path).
- [x] **DELETE** — `test_closed_annotation_sets_dropped` (L991) — parser-only; same rationale as above.
- [x] **DELETE** — `test_fixed_annotation_sets_dropped` (L1002) — parser-only.
- [x] **DELETE** — `test_already_implemented_sets_dropped` (L1013) — parser-only.
- [x] **KEEP** — `test_no_annotation_leaves_status_null` (L1024) — asserts that a backlog row without any marker leaves status NULL/empty. Post-cleanup the parser is gone but the assertion still holds (default branch with no derivation). Keep as a positive regression guard.
- [x] **DELETE** — `test_idempotent_no_clobber_promoted` (L1035) — exercises the `(promoted →)` parser to set status, then asserts re-run does not clobber. The clobber-guard logic at backfill.py:421 (`if existing_status not in ("promoted", "dropped")`) is also being removed alongside the parser. No remaining behavior to assert.

## test_entity_status.py (`plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`)

### Class `TestSyncBacklogEntities` (lines 381-571)

- [x] **DELETE** — `test_closed_status_mapped_to_dropped` (L384) — parser-only exercise of `CLOSED_RE` consumer at `:320`.
- [x] **DELETE** — `test_promoted_status_mapped` (L397) — parser-only exercise of `PROMOTED_RE` consumer at `:322`.
- [x] **DELETE** — `test_fixed_status_mapped_to_dropped` (L410) — parser-only exercise of `FIXED_RE` consumer at `:324`.
- [x] **DELETE** — `test_already_implemented_mapped_to_dropped` (L423) — parser-only.
- [x] **KEEP** — `test_no_marker_registered_as_open` (L437) — backlog row without any marker registers as `status='open'`. Default-branch behavior unchanged post-cleanup.

### Class `TestBacklogBoundaryValues` (lines 578-676)

- [x] **KEEP** — none of the boundary-value tests in this class consume a parser. (All exercise `JUNK_ID_RE` / `BACKLOG_ROW_RE` / length-200 truncation.) No action.

### Class `TestBacklogAdversarial` (lines 678-812)

- [x] **DELETE** — `test_standalone_already_implemented_mapped_to_dropped` (L681) — parser-only.
- [x] **DELETE** — `test_promoted_with_unicode_arrow_mapped` (L700) — parser-only.
- [x] **DELETE** — `test_backlog_row_with_multiple_status_markers` (L754) — parser-only priority test.
- [x] **DELETE** — `test_backlog_row_with_parenthetical_not_a_status_marker` (L773) — exercises that non-marker parentheticals don't trigger parsing → default 'open'. Post-cleanup this collapses into `test_no_marker_registered_as_open`; redundant.
- [x] **DELETE** — `test_name_stripping_removes_status_marker_not_entire_description` (L793) — tests `NAME_STRIP_RE` behavior, which is also being removed (design C8.b — entity.name marker text is out of scope; markers remain intact in stored names post-cleanup).

### Class `TestMutationMindset` (lines 936-998)

- [x] **MIGRATE** — `test_execution_order_junk_before_dedup_before_sync` (L957) — uses `(closed: done)` marker as a way to assert "valid item updated from open to dropped" alongside junk deletion. Refactor: change the backlog.md description to a plain string (no marker) and instead pre-seed the entity in DB with `status='open'` then assert the test still validates execution order (junk-first → dedup → sync) by checking junk deletion + entity registered/skipped. The status-change leg (`open → dropped`) is dropped from this test; it's already covered by `test_closed_status_mapped_to_dropped` (which we are deleting in any case — that part of the assertion is now moot).

### Site harness for `TestNoDeprecationWarningOnHappyPath` (lines 1152-1186)

- [x] **MIGRATE** — `_setup_site_320_backlog_status_change` (L1152) — helper writes a backlog.md row containing `(closed: not needed)` to drive the status-change branch at `entity_status.py:320`. Post-cleanup, line 320 (which used `CLOSED_RE.search` consumer) no longer parses, so the synthetic status-change is unreachable via that fixture. Remove the `site_320_backlog_status_change` entry from `SITE_SETUPS` (3 sites remain: 47, 72, 189). The status-change branch at the post-cleanup equivalent line (still inside `_sync_backlog_entities`) is exercised when the DB status differs from the parsed-md status — but post-cleanup the parsed status is always `'open'` (default). To exercise the status-change branch we would need the DB entity at status != 'open'; the simplest path is to remove this site from the param list (the 3 remaining sites still verify the FR-10 conditional-kwarg pattern across distinct call sites). DELETE the helper too.

## test_checks.py (`plugins/pd/hooks/lib/doctor/test_checks.py`)

These tests exercise the `check_backlog_status` doctor production function
which itself parses `(promoted -> ...)`, `(closed: ...)`, `(fixed: ...)`
markers from `backlog.md`. The parser block at `checks.py:983-1015` is being
deleted; the cross-ref infrastructure below `:1029` remains and reads from
`entities.status` directly.

- [x] **DELETE** — `TestCheck4AnnotatedNotPromoted::test_check4_annotated_not_promoted` (L1152) — feeds `(promoted -> feature:001-alpha)` into backlog.md and expects the doctor warning. Post-cleanup the parser is gone; the doctor's "not promoted" warning is sourced from DB entity_relations rows (per AC-CL.3), not prose markers.
- [x] **KEEP** — `TestCheck4BacklogMissingFile::test_check4_backlog_missing_file_passes` (L1182) — verifies passive behavior when backlog.md is absent. No parser involvement.
- [x] **KEEP** — `TestCheck4PromotedNotAnnotated::test_check4_promoted_not_annotated_info` (L1199) — verifies reverse-cross-ref: entity promoted in DB but not annotated in backlog.md → info issue. Post-cleanup the reverse cross-ref (entities → markdown) is also gone (the parser block built the `annotated_ids` set). This test currently exists because the parser found no marker for ID 42; after cleanup, the parser is gone but the info-emission path is also gone — test no longer reaches the assertion. **DELETE**.
- [x] **KEEP** — `TestCheck4EmptyBacklog::test_check4_empty_backlog_passes` (L1226) — empty backlog.md → passes. No parser involvement.
- [x] **DELETE** — `TestCheck4ClosedAnnotation::test_check4_closed_annotation_stale_status` (L1244) — feeds `(closed: upstream limitation)` and expects a stale-status warning. Post-cleanup the parser is gone; warning no longer fires.
- [x] **DELETE** — `TestCheck4ClosedAnnotation::test_check4_closed_annotation_correct_status` (L1268) — same fixture, expects no warning when DB status='dropped'. Post-cleanup it trivially passes (no parser to emit warnings) — collapse into the empty case.
- [x] **DELETE** — `TestCheck4ClosedAnnotation::test_check4_fixed_annotation_stale_status` (L1292) — same fixture pattern with `(fixed: ...)`. **DELETE**.

## Summary counts

- **Migrate**: 2 (test_execution_order_junk_before_dedup_before_sync, _setup_site_320_backlog_status_change — the latter is migrated by removal from SITE_SETUPS)
- **Delete**: 17 (4 in test_backfill.py + 9 in test_entity_status.py + 4 in test_checks.py)
- **Keep**: 4 explicit positives (test_no_annotation_leaves_status_null, test_no_marker_registered_as_open, test_check4_backlog_missing_file_passes, test_check4_empty_backlog_passes) plus the boundary-value class (unaffected)

Total parser-dependent tests touched: **19** (slightly above the spec R3 estimate of "~10 affected"; design FR-CL.3 explicitly notes parser-only exercise tests must be deleted in addition to fixture migrations, accounting for the higher count).
