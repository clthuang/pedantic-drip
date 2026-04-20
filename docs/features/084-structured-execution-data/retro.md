# Feature 084 Retrospective — Structured Execution Data

**Retroactive retro, authored 2026-04-19 as part of feature 088 Bundle K.**

Feature 084 shipped on 2026-04-18 without a retro, violating the `mode=full` process requirement (`workflow_state_server.py:691` artifact-completeness check includes `retro.md`). Feature 088's Bundle K backfills this retro with lessons derived from (a) the git log of 084's commits, (b) the 5 QA backlog items surfaced immediately post-release (#00080–#00084), and (c) the 21 additional findings surfaced by 088's adversarial review (#00117–#00137).

## Aims

Feature 084 set out to extract structured workflow execution data from the `entities.metadata` JSON blob into a proper queryable DB table. The original backlog entry (#00051) stated that per-phase timing, iteration counts, reviewer notes, mode, branch, brainstorm_source, skipped_phases, and backward_history were all crammed into a single TEXT column, making cross-feature queries impossible without JSON parsing. The feature was scoped to produce a `phase_events` table with structured columns, an MCP analytics API (`query_phase_analytics`, `record_backward_event`), a dual-write contract keeping `.meta.json` regeneration working, and a migration (10) that backfilled historical events.

## Outcomes

Delivered:
- `phase_events` schema (migration 10) with 12 columns, CHECK constraints on `event_type` and `source`, indexes on `type_id` and `project_id`.
- `insert_phase_event` DB method with dual-write ordering inside `with db.transaction()`.
- `query_phase_events` read API with filters and a 500-row cap.
- 3 new MCP tools: `query_phase_analytics` (4 query types: phase_duration, iteration_summary, backward_frequency, raw_events), `record_backward_event`, plus extensions to `transition_phase`/`complete_phase` for dual-write.
- `_compute_durations` helper computing per-phase runtime via started/completed pairing.
- 21 new ACs passing at ship time; backfill executed on existing features.
- SKILL.md integration via `workflow-transitions` to invoke `record_backward_event` on backward transitions.

Not delivered at ship time:
- retro.md (this file, backfilled 2026-04-19).
- Adversarial-quality test coverage — many mutation-resistance holes surfaced only when feature 088 ran 8 parallel reviewers.

## Reflections

What went well:
- **Additive surface.** No existing MCP tool or entity-registry method was broken. `_project_meta_json()` continued reading from `entities.metadata` as source of truth; `phase_events` is pure append-only analytics.
- **Schema discipline.** Migration 10 used explicit column lists for INSERTs (no `SELECT *` on write side) and CHECK constraints on enums. This caught a class of bugs the feature 082/045 retros had flagged.
- **Dual-write pattern identified.** The feature team correctly recognized that `phase_events` writes are secondary to `.meta.json` regeneration — analytics is additive, not load-bearing.

What went wrong:
- **Dual-write placed INSIDE the main transaction.** Found by feature 088 finding #00124. When `insert_phase_event` raises `sqlite3.IntegrityError` (e.g., on a NOT NULL violation for `project_id`), the bare `except` catches the error but the transaction is already in an aborted state. The subsequent `db.update_entity(metadata)` then raises `InterfaceError`, rolling back BOTH writes. Caller sees success response (built from data computed earlier) but the transaction was silently rolled back. Feature 088's Bundle E moves the phase_events INSERT OUTSIDE the transaction commit boundary.
- **`query_phase_analytics` defaulted to cross-project scope.** Finding #00117. Every sibling `list_features_*` tool in `workflow_state_server.py:1314,1347` defaults to the current `_project_id`; `query_phase_analytics` did not. In a multi-project environment with a shared `~/.claude/pd/entities/entities.db`, a default call from project A exfiltrates phase-events metadata (feature names, timestamps, reviewer_notes) from project B. Feature 088 adds server-side default scoping with explicit `project_id="*"` opt-in.
- **`record_backward_event` accepted `project_id` from the caller with zero validation.** Finding #00119. Combined with the default-cross-project-scope issue, this allowed event forgery into any project's analytics. Feature 088 removes the caller-visible parameter and resolves project_id server-side via `_db.get_entity(type_id)`.
- **Migration 10 had a concurrent-duplicate backfill race.** Finding #00118. Two MCP server processes starting simultaneously both read `schema_version=9`, both called `_migration_10_phase_events`, and both executed the backfill loop with unconditional `INSERT`. AC-18 only tested the `_migrate()` wrapper's idempotency (via `schema_version` check) — not the raw migration function. Feature 088 adds a partial UNIQUE index on `source='backfill'` rows + switches backfill to `INSERT OR IGNORE` + adds a schema_version re-check inside the migration's `BEGIN IMMEDIATE` block.
- **`SELECT *` slipped into runtime query.** Finding #00121. `query_phase_events` at `database.py:~2985` used `SELECT * FROM phase_events{where}` despite the feature 082/045 retros explicitly flagging this as a regression source. If a future migration reorders columns, consumer dict shapes silently change.
- **New MCP handlers skipped `_check_db_available`.** Finding #00120. Every other MCP tool in the file uses `_check_db_available()` as the first guard; `record_backward_event` and `query_phase_analytics` went straight to `if _db is None`, returning a non-standard error shape in degraded mode.
- **`_compute_durations` silently dropped unpaired events.** Findings #00123 and #00136 (zip-truncation sub-item). Only iterating `groups_s.keys()` meant any (type_id, phase) with `completed` events but no `started` events (common in legacy backfill) was silently omitted. `zip(s_list, c_list)` further truncated imbalanced pairs within a group.
- **SKILL.md used an undefined variable.** Finding #00122. `workflow-transitions/SKILL.md::handleReviewerResponse` called `record_backward_event(..., project_id=project_id)` but `project_id` was not assigned anywhere in `handleReviewerResponse`'s scope. Upstream root cause of finding #00080's `__unknown__` sentinel pollution in analytics queries.
- **AC-19 metadata preservation test was vacuous.** Finding #00131. The test only asserted key presence in `phase_timing`, not that `iterations` and `reviewerNotes` survived the dual-write round-trip. A subtle regression overwriting metadata with a reduced dict would pass.
- **Reconciliation was `phase_events`-unaware.** Finding #00135. `reconcile_check` has zero references to `phase_events`. Metadata-vs-phase_events drift accumulates silently over time with no visibility.
- **No retro at ship time.** The `mode=full` artifact-completeness check should have blocked `/finish-feature` but either the check was bypassed or the check itself was permissive. Process gap that feature 088 addresses explicitly.

## Tune (What to change)

These corrections are encoded into the knowledge bank so future features avoid the same pitfalls.

- **Anti-pattern: dual-write INSIDE a transaction.** When splitting a write into primary + analytics legs, ALWAYS place the analytics write OUTSIDE the main transaction commit. Otherwise an IntegrityError in analytics rolls back the primary write silently. Primary should commit first; analytics leg runs in its own try/except with a `{entity}_write_failed: true` response field and a stderr warning.
- **Anti-pattern: `SELECT *` in runtime queries.** Always use explicit column lists in queries that return dicts consumed by Python code. `SELECT *` is acceptable ONLY in ad-hoc schema-inspection code. Feature 082's retro called this out; feature 084 regressed. Feature 088 re-fixes it.
- **Anti-pattern: new MCP handler without `_check_db_available()` as first statement.** Every MCP tool in `workflow_state_server.py` MUST start with `err = _check_db_available(); if err: return err`. Degraded-mode response shape consistency is load-bearing for client retry logic.
- **Anti-pattern: caller-supplied identifier used as a trust boundary.** If the server can resolve an ID (e.g., `project_id` from an entity lookup), do not accept it from the caller. Trusting caller input for identifiers that can be resolved server-side enables cross-project data forgery.
- **Anti-pattern: migration idempotency via `_migrate()` wrapper alone.** Concurrent migration invocation (two processes, same schema_version) requires storage-layer idempotency: UNIQUE indexes + `INSERT OR IGNORE`, or an inside-transaction schema_version re-check. The outer `_migrate()` wrapper check is necessary but not sufficient.
- **Anti-pattern: declaring a dual-write contract without reconciliation support.** When a feature introduces a new source of truth (or secondary store), reconciliation tooling must be updated in the same feature. Drift that nothing detects accumulates forever.
- **Heuristic: skill-layer pseudocode must compile.** `SKILL.md::handleReviewerResponse` referenced an undefined variable `project_id` — the pseudocode was never parse-checked. For skill files that drive runtime dispatch, variables used in code blocks must have explicit resolution steps earlier in the procedure. Reviewing skill-layer diffs with the same rigor as code diffs avoids this.
- **Heuristic: retro.md is a `mode=full` artifact.** If the mode-full artifact-completeness check at `workflow_state_server.py:691` is being bypassed at `/finish-feature`, the check is not enforceable. Either tighten the check or remove retro.md from the required-artifact list. Do not leave it as aspirational.

## Adopt (What to keep doing)

- **Dual-write pattern overall** — but ONLY with the analytics INSERT outside the main transaction commit. The feature team's instinct to keep `.meta.json` regeneration load-bearing was correct; only the transactional placement needed correction.
- **Explicit column lists in migrations.** Migration 10's backfill inserts used named columns — this is the right pattern. The regression was only at the query side, not the write side.
- **CHECK constraints on enum columns.** `event_type` and `source` are enumerations; constraining them at the schema layer caught a class of bugs. Keep doing this.
- **Additive schema evolution.** The `phase_events` table is append-only analytics — no deletions, no updates. This simplifies reasoning about concurrency and recovery.
- **Dedicated MCP tools per query shape.** `query_phase_analytics` chose 4 distinct `query_type` values rather than one generic query builder. This keeps the tool's contract small and testable.

## Verified-False-Alarms

Feature 088's adversarial review surfaced 43 findings; two were verified as false alarms after investigation:

- **#00134 — `insert_phase_event` unconditional `_commit()`.** Test-deepener claimed the method calls `self._commit()` unconditionally and thus cannot participate in an outer transaction. Investigation showed `_commit()` at `database.py:1551-1554` already guards on `self._in_transaction` (an instance attribute set by the `transaction()` context manager), so participation in an outer transaction is already correct. Feature 088 added a pin test (AC-16) to prevent regression but no code change was required.

## Known Deferred (to backlog #00138)

Feature 088 addresses all 43 new findings in-scope for its FR-1 through FR-11 categories, but a subset of sub-items within findings #00116 and #00136 (low-priority test hardening that does not pin a correctness bug) are deferred to backlog item #00138. These are mutation-resistance improvements for test coverage, not correctness gaps.

## Retro Lessons Encoded

These lessons are captured as knowledge-bank entries via `/pd:remember` during feature 088's retro phase:
1. Dual-write analytics INSERT MUST be outside the primary transaction commit boundary.
2. New MCP handlers MUST call `_check_db_available()` as the first statement.
3. `SELECT *` is prohibited in runtime queries; use explicit column lists.
4. Caller-supplied identifiers that the server can resolve are a trust boundary violation — resolve server-side.
5. Migration idempotency under concurrent invocation requires storage-layer guarantees (UNIQUE index + `INSERT OR IGNORE`), not just a `_migrate()` wrapper check.
6. Features in `mode=full` that skip retro.md violate the artifact-completeness contract — either enforce the check or remove the requirement.
