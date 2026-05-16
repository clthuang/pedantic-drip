# Spec: pd Data-Model + Memory Hardening (Feature 114)

**Source PRD:** `docs/features/114-pd-data-model-hardening/prd.md`
**Status:** Draft rev 2 (spec-reviewer iter 1 corrections applied)
**Cluster Sequencing:** A‖A-M11 → D → C → B-H4 → B-H3‖B-H2 → E‖E.2 (from PRD)

## 1. Problem Restated

Post-P003 hardening across 5 clusters (7 sub-clusters total). Three load-bearing findings:

1. **M12 stub trap** — `_metadata.schema_version=12` on installed DBs without the post-M12 schema body applied. Migration 13 aborts on every MCP startup. Affects all users who installed during commit-`6722191a` window. The "deferred remediation" referenced in 4 error messages was never implemented.
2. **Audit invariant never held** — production has 945 phase_events rows, **0** are `entity_status_changed`. `db.update_entity` bypasses `append_phase_event`; AST audit whitelists `update_entity` at `check_status_write_path.py:37`.
3. **Workspace isolation never enforced** — F108 stated Goal 1 was structural isolation; **3** MCP write paths (`set_parent`, `add_dependency`, `add_okr_alignment`) have NO cross-workspace gate. (Note: PRD listed 4; `add_entity_tag` was incorrectly included — its signature is `(type_id, tag: str)` with no second entity reference. Confirmed via `entity_server.py:1087-1095`.) Production has **21 live cross-workspace `parent_uuid` links** today.

Plus memory-system noise (29% capture-hook noise, 91% CLI-bypass) and workspace mismatch caller-resolution (`_workspace_uuid or ""` at 3 sites).

## 2. Functional Requirements

### FR-A — M12 Stub Recovery

- **FR-A.1**: M12 idempotency guard at `database.py:2683` MUST verify entities table layout (presence of `type`, `kind`, `lifecycle_class` AND absence of `entity_type`) before early-return. If `schema_version >= 12` AND layout is post-M12, return; if stamp >= 12 AND layout is pre-M12, FALL THROUGH and execute the migration body.
- **FR-A.2**: A new `python -m plugins.pd.hooks.lib.entity_registry.remediate_m12` CLI subcommand MUST detect the stub-trap state and execute the M12 body. Behavior on partial-application is governed by FR-A.5.
- **FR-A.3**: A new doctor `fix_action` (`fix_m12_stub_trap`) MUST detect the stub-trap state during session-start and offer remediation via AskUserQuestion ("Detected M12 stub trap. Apply recovery now? (Recommended)"). YOLO mode: existing `yolo-guard.sh` intercepts and auto-accepts safe data-recovery prompts (no special-case logic).
- **FR-A.4**: All RuntimeError messages from M13 pre-flight (currently 4 sites in `database.py`, locatable via `rg -n "feature-109 deferred remediation" plugins/pd/hooks/lib/entity_registry/database.py` — expected lines: 4027, 4052, 4088, 4112) MUST embed the exact CLI command: `python -m plugins.pd.hooks.lib.entity_registry.remediate_m12`. No naked references to "deferred remediation" without the actionable command.
- **FR-A.5** (partial-application handling — **checksum-based detector**, replaces previous boolean-enumeration approach): The remediation CLI MUST compute a schema fingerprint via `_compute_schema_fingerprint(conn) -> str` defined as:
  ```python
  def _compute_schema_fingerprint(conn) -> str:
      import hashlib
      def _normalize_sql(s: str) -> str:
          # Lowercase keywords, strip line comments, collapse whitespace.
          # Provides stability across SQLite versions and quote-style variations.
          import re
          s = re.sub(r'--[^\n]*', '', s or '')  # strip -- comments
          s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)  # strip /* */ comments
          return ' '.join(s.split())
      # (1) entities columns: sorted by name only (NOT cid) so cid drift across ALTER TABLE/CREATE TABLE doesn't shift fingerprint
      cols = sorted([(r[1], r[2]) for r in conn.execute("PRAGMA table_info('entities')").fetchall()])
      # (2) phase_events CHECK constraint text: extract from sqlite_master.sql, normalize
      pe_sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='phase_events'").fetchone()
      pe_sql = _normalize_sql(pe_sql_row[0] if pe_sql_row else '')
      # (3) transitional table presence: sorted list of names from set {entities_new, entities_relations, entities_drop, phase_events_new}
      transitional = sorted([r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('entities_new','entities_relations','entities_drop','phase_events_new')").fetchall()])
      # (4) FTS5 triggers: sorted by trigger name; trigger bodies normalized
      triggers = sorted([(r[0], _normalize_sql(r[1] or '')) for r in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'").fetchall()])
      blob = f"{cols!r}|{pe_sql}|{transitional!r}|{triggers!r}"
      return hashlib.sha256(blob.encode('utf-8')).hexdigest()
  ```
  Two known-good fingerprints are pinned in code as constants `_PRE_M12_FINGERPRINT` and `_POST_M12_FINGERPRINT`, computed at implement time by running `_compute_schema_fingerprint` against the FR-A.6 fixtures (`pre_m12.sql` and `post_m12.sql` loaded into temp SQLite DBs) and hardcoding the two SHA-256 hex strings. CLI behavior:
  - fingerprint == `_PRE_M12_FINGERPRINT` AND schema_version == 12 (stub-trap): run M12 body → expect `_POST_M12_FINGERPRINT` post-run.
  - fingerprint == `_POST_M12_FINGERPRINT` AND schema_version == 12 (already recovered): no-op, exit 0.
  - any other fingerprint (partial-application or unknown state): abort with diagnostic listing the divergent schema objects between observed and expected `_PRE_M12_FINGERPRINT` AND between observed and `_POST_M12_FINGERPRINT`. No mutation.
  Rationale: avoids enumerating partial states the reviewer correctly flagged as unbounded; uses single fingerprint check that's exhaustive over schema-object identity.

- **FR-A.6** (fixture creation): Implement MUST create the following fixture SQL scripts (referenced by Pin A.fix and consumed by AC-A.* tests):
  - `plugins/pd/hooks/lib/entity_registry/fixtures/m12_stub_trap.sql` — produces a DB at `schema_version=12, pre-M12 layout` (entity_type column present; type/kind/lifecycle_class absent). Used by AC-A.1, AC-A.3, AC-A.5b's setup.
  - `plugins/pd/hooks/lib/entity_registry/fixtures/pre_m11.sql` — produces a DB at `schema_version=10, pre-M11 layout` (no workspace_uuid column). Used by AC-A.2, AC-M11.1.
  - `plugins/pd/hooks/lib/entity_registry/fixtures/post_m12.sql` — produces a DB at `schema_version=12, post-M12 layout` (type/kind/lifecycle_class present; entity_type absent). Used by AC-A.5b ("already-recovered").
  - `plugins/pd/hooks/lib/entity_registry/fixtures/m12_partial.sql` — produces a DB at `schema_version=12` with partial schema state (e.g., type column present but kind absent). Used by AC-A.5a (abort-with-diagnostic).
  All fixtures MUST be deterministic: same SQL → same fingerprint. Fixtures MUST seed at least 3 entity rows so subsequent schema operations exercise data-path branches.

### FR-M11 — M11 Same-Trap Guard (renamed from FR-A.2 to avoid numbering collision)

- **FR-M11.1**: M11 idempotency guards at `database.py:1818,1899` MUST verify the entities table has the `workspace_uuid` column before early-return. If stamp >= 11 AND `workspace_uuid` absent, FALL THROUGH and execute M11 body.
- **FR-M11.2** (conditional on Open Question 7): If implementation reveals partial-M11 state is empirically reachable (probe the existing production DBs at session-start to detect; if zero found, treat as unreachable), ship a `remediate_m11` CLI mirroring FR-A.5's fingerprint-detector pattern. Otherwise: document the limitation in design.md and ship guard tightening only.

### FR-B — Memory System Cleanup

#### FR-B-H2 (capture hook noise)

- **FR-B-H2.1**: `plugins/pd/hooks/capture-tool-failure.sh` MUST have the `PostToolUse` heuristic-detection branch (lines 147-157) deleted entirely. **Hook registration source**: implement-phase MUST locate the canonical hook registration (likely `plugins/pd/.claude-plugin/plugin.json` or similar plugin-shipped manifest, NOT `.claude/settings.local.json` which is per-developer/gitignored). Once located, MUST update to ONLY register for `PostToolUseFailure`. If implement-phase discovery reveals user-local registration (would be unexpected for a pd-shipped hook), implement MUST pause and surface the finding via spec-revision request before adding the fix_action. Self-amendment of spec during implement is NOT permitted.
- **FR-B-H2.2**: A one-shot cleanup query MUST be executed during the Cluster B migration: `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'`. Expected row count: 464 ± 50 (verified via dry-run BEFORE execution; abort if outside range).

#### FR-B-H3 (CLI bypasses MCP gates)

- **FR-B-H3.1**: A new helper `_apply_quality_gates(description: str, db: MemoryDatabase, config: Config) -> QualityGateResult` MUST be extracted from `_process_store_memory` in `memory_server.py:92-147`. The helper consolidates: (a) 20-char minimum length gate, (b) 0.95 near-dup rejection, (c) 0.90 dedup-merge.
- **FR-B-H3.2**: `writer.py:main` MUST call `_apply_quality_gates(...)` exactly once before any `db.upsert_entry(...)` call. Return code on rejection: non-zero with stderr describing which gate fired.
- **FR-B-H3.3**: `_process_store_memory` MUST be refactored to call `_apply_quality_gates` as its single source of truth. No inline duplicate of the gate logic remains in `_process_store_memory` after refactor.

#### FR-B-H4 (hash drift backfill)

- **FR-B-H4.1**: `semantic_memory/writer.py:72` and `semantic_memory/importer.py:86` MUST agree on hash input. Canonical choice: `source_hash(description)` (matches writer's current behavior; deterministic). Importer's `source_hash(raw_chunk)` is replaced.
- **FR-B-H4.2** (**frozen manifest**, implement-phase produced): The hash-shift manifest is produced during implement (not specify), with the following strict ordering:
  1. **Step 1 (implement)**: Write a standalone helper `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py` that computes the new hash for every row WITHOUT writing it back. Helper outputs `shifted_ids` (rows whose stored hash differs from recomputed hash).
  2. **Step 2 (implement)**: Run the helper dry against `~/.claude/pd/memory/memory.db`. Capture `shifted_ids`.
  3. **Step 3 (implement)**: Freeze the result into `plugins/pd/hooks/lib/semantic_memory/fixtures/hash_shift_manifest.json` containing `{"shifted_ids": [...], "expected_count": N, "captured_at": "ISO8601", "memory_db_sha256": "..."}` where `memory_db_sha256` pins the DB hash at freeze time.
  4. **Step 4 (implement)**: Commit fixture before writing migration body.
  5. **Step 5 (implement)**: Write migration body that READS the fixture at runtime. Migration behavior:
     - Compute `n_shifted, shifted_ids` against the running DB.
     - Compare `shifted_ids` against `frozen_shifted_id_set` from the fixture.
     - Proceed ONLY if `shifted_ids ⊆ frozen_shifted_id_set` AND `10 ≤ len(shifted_ids) ≤ 50`.
     - Abort otherwise with a diff: rows in observed-but-not-frozen, rows in frozen-but-not-observed.
  Rationale: prevents legitimate-looking drift from passing the gate; binds the migration to the empirical state captured at freeze time. Specify cannot run this because (a) memory MCP is disconnected this session, (b) the production memory.db is the canonical input to the dry-run.
- **FR-B-H4.3**: One-shot cleanup query MUST be executed during the same Cluster B migration: `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`. Expected row count: 10 (the cluster identified in deep-dive — Pin I).

### FR-C — Audit Invariant (update_entity emits entity_status_changed)

- **FR-C.1**: `db.update_entity` (`database.py:7094-7236`) MUST emit `append_phase_event(event_type='entity_status_changed', ...)` when `status is not None` AND new status differs from current value. No-op writes (same status) MUST NOT emit.
- **FR-C.2** (fail-open): The emit MUST be wrapped in try/except. On failure: emit stderr line matching regex `pd\.audit\.emit_failed: \{.+\}` where the JSON portion contains keys `{type_id, old_status, new_status, exception_class}` with non-null values; increment `entities.db _metadata.audit_emit_failed_count`; do NOT re-raise. The status UPDATE proceeds regardless.
- **FR-C.3**: A new doctor health-check MUST surface `audit_emit_failed_count` as `severity=warning` if value > 0 since last reset. Reset condition: **Migration 15** (`_migration_15_audit_emit_counter`) MUST set `INSERT OR REPLACE INTO _metadata(key, value) VALUES ("audit_emit_failed_count", "0")` as part of its body. Migration 15 is the ONLY mechanism that resets this counter; subsequent migrations MUST NOT touch this key; doctor MUST NOT auto-reset.
- **FR-C.4** (AST whitelist removal): `plugins/pd/hooks/lib/doctor/check_status_write_path.py:37` MUST remove `update_entity` from `_PERMITTED_ENCLOSING_DEFS`. Precondition: all 17 production callers verified emit-route post-FR-C.1; test fixtures swept (FR-C.5).
- **FR-C.5** (test fixture sweep): All test files that call `db.update_entity(..., status=...)` directly MUST be either: (a) updated to use `upsert_entity` or `promote_entity`, OR (b) granted explicit allowlist entry in `_PERMITTED_TEST_FILES` (new frozenset). **Identifier format**: `_PERMITTED_TEST_FILES` is a `frozenset[str]` of project-root-relative POSIX path strings (e.g., `"plugins/pd/hooks/lib/entity_registry/test_database.py"`). Matching is by exact string equality after normalizing observed paths via `Path(p).resolve().relative_to(project_root).as_posix()`. Bounds check: if the multi-line rg (Pin F command) returns >20 production-path results during implement re-verification, pause and surface count to user before proceeding with whitelist removal.

### FR-D — Workspace Mismatch Caller-Resolution

- **FR-D.1** (**explicit ordered pseudocode**, replaces previous code-block + prose contradiction): `db.resolve_entity_uuid` returns `tuple[str | None, str | None]` (verified at `database.py:5922-5941`). Returns `(None, None)` on miss. The fallback logic:
  ```python
  # In _process_complete_phase (workflow_state_server.py:1184)
  # _workspace_uuid may be: None, "" (empty string), _UNKNOWN_WORKSPACE_UUID, or a real UUID.
  # Falsy values (None, "") normalize to _UNKNOWN_WORKSPACE_UUID.
  _primary_ws = _workspace_uuid or _UNKNOWN_WORKSPACE_UUID

  from_uuid, caller_ws = db.resolve_entity_uuid(_primary_ws, feature_type_id)

  if from_uuid is None and _primary_ws != _UNKNOWN_WORKSPACE_UUID:
      # Pass 2 fires ONLY when pass 1 used a real (non-_UNKNOWN) UUID and missed.
      # Strictly gated to _UNKNOWN_WORKSPACE_UUID — never tries arbitrary workspaces.
      from_uuid, caller_ws = db.resolve_entity_uuid(_UNKNOWN_WORKSPACE_UUID, feature_type_id)
      if from_uuid is not None:
          log_stderr_json("pd.workspace.legacy_fallback", {
              "call_site": "complete_phase",
              "type_id": feature_type_id,
              "primary_ws": _primary_ws,
              "fallback_ws": _UNKNOWN_WORKSPACE_UUID,
          })

  if from_uuid is None:
      raise EntityNotFoundError(...)
  ```
  Gating predicate: pass 2 suppressed when `_primary_ws == _UNKNOWN_WORKSPACE_UUID` (pass 1 already tried). Edge cases pinned:
  - `_workspace_uuid is None` → `_primary_ws = _UNKNOWN_WORKSPACE_UUID`, pass 2 suppressed
  - `_workspace_uuid == ""` (falsy) → same as None
  - `_workspace_uuid == _UNKNOWN_WORKSPACE_UUID` → same as None (pass 2 suppressed)
  - `_workspace_uuid == <real UUID>` → pass 2 fires if pass 1 misses
- **FR-D.2**: `plugins/pd/mcp/entity_server.py:562, 704` MUST replace `resolved_workspace_uuid = workspace_uuid or _workspace_uuid or ""` with:
  ```python
  resolved_workspace_uuid = workspace_uuid or _workspace_uuid or _UNKNOWN_WORKSPACE_UUID
  ```
  (Single-pass at these sites; the fallback semantic at FR-D.1 is specific to `complete_phase` caller-resolution.)
- **FR-D.3**: The fallback path at FR-D.1 MUST log `pd.workspace.legacy_fallback` to stderr per the pseudocode above. AC-D.4 below pins the JSON-shape contract.
- **FR-D.4**: A test fixture variant MUST exercise the failure path: real-UUID `_workspace_uuid` against legacy `_UNKNOWN_WORKSPACE_UUID` entity. Pre-FR-D.1 baseline asserts EntityNotFoundError. Post-FR-D.1 asserts success.

### FR-E — Cross-Workspace Isolation Gates (3 gates, not 4)

- **FR-E.1**: A new helper `_assert_same_workspace_uuids(db, *entity_uuids: str, caller_ws: str, op_name: str) -> None` MUST be added to `entity_registry/database.py`. Behavior: for each uuid, fetch the entity's workspace_uuid; if any differs from `caller_ws`, raise typed `CrossWorkspaceError(op_name, mismatched_uuids: list[tuple[uuid, ws_a, ws_b]])`.
- **FR-E.2**: MCP handlers MUST invoke the assertion before mutation:
  - `_process_set_parent` (`entity_server.py:842` / `server_helpers.py:483`): assert child + parent share workspace
  - `_process_add_dependency` (`entity_server.py:1149`): assert entity + blocked_by share workspace
  - `_process_add_okr_alignment` (`entity_server.py:1281`): assert entity + key_result share workspace
- **FR-E.3**: `CrossWorkspaceError` MUST translate to a typed JSON error envelope (`error_type=cross_workspace_forbidden`, `recovery_hint="Re-attribute one endpoint or grandfather via cross_workspace_allowlist"`) consistent with F111's `EntityNotFoundError` pattern.
- **FR-E.4** (allowlist exemption): Gates MUST consult `cross_workspace_allowlist` table (schema defined below in FR-E.2.1) and skip the assertion if the pair is allowlisted.
- **FR-E.5** (doctor check, warning-only): A new doctor check MUST flag existing `entities.parent_uuid` rows where child and parent reside in different workspaces. Severity: `warning` (NOT `error`). Suppresses for allowlisted pairs.
- **FR-E.6**: Hard-error escalation is **explicitly out of scope** (non-goal). Doctor check remains warning-only at end of this feature.
- **FR-E.7** (**severity reporting contract** — output-JSON-based, NOT exit-code-based): The existing doctor contract at `plugins/pd/hooks/lib/doctor/__main__.py:8` is "Exit code is always 0." This contract is **preserved**. Severity is communicated via the JSON output payload only: doctor's output JSON MUST include `severity_summary: {error: N, warning: N, suggestion: N}` and per-issue records MUST have `severity` field. Callers reading exit codes see 0 regardless; callers parsing JSON see the severity distribution. New Cluster C/E checks emit `severity=warning` consistently and do NOT escalate exit code.

#### FR-E.2 — Cross-Workspace Triage Tool

- **FR-E.2.1** (allowlist table schema): A new migration MUST create:
  ```sql
  CREATE TABLE cross_workspace_allowlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_uuid TEXT NOT NULL,
    child_uuid TEXT NOT NULL,
    reason TEXT NOT NULL,
    grandfathered_by TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_uuid, child_uuid),
    FOREIGN KEY (parent_uuid) REFERENCES entities(uuid) ON DELETE CASCADE,
    FOREIGN KEY (child_uuid) REFERENCES entities(uuid) ON DELETE CASCADE
  );
  ```
  **CASCADE semantics accepted**: When an entity is deleted via F109's `delete_entity`, its allowlist rows auto-remove (the relation no longer exists). If the entity is recreated with the same uuid, operator MUST re-grandfather. Documented behavior, not a bug.
- **FR-E.2.2** (triage UX): A new doctor fix_action `triage_cross_workspace_links` MUST list each cross-workspace `parent_uuid` row and prompt via AskUserQuestion per link: (a) re-attribute parent to child's workspace, (b) re-attribute child to parent's workspace, (c) delete relation (set `parent_uuid=NULL`), (d) grandfather via allowlist with operator-supplied reason.
- **FR-E.2.3**: After triage completes for all 21 existing rows, the doctor check (FR-E.5) MUST report 0 unallowlisted cross-workspace links. Verified via SQL query in AC-E.5.

## 3. Acceptance Criteria

### AC-A (M12 Recovery)

- **AC-A.1**: Synthetic fixture (see Pin A.fix) at `schema_version=12, pre-M12 layout` → invoke remediation CLI → `schema_version=12 + post-M12 layout (type/kind/lifecycle_class present, entity_type absent)`. Verified via `PRAGMA table_info(entities)`.
- **AC-A.2**: Synthetic fixture at `schema_version=11, pre-M11 layout` → MCP startup auto-runs M11+M12 (real bodies) → `schema_version=12 + post-M12 layout`. Verifies tightened guards on both M11 and M12.
- **AC-A.3**: Doctor at session-start on stub-trap fixture → AskUserQuestion fires with "Apply recovery now?" prompt → YES → DB recovers. (YOLO mode: yolo-guard.sh auto-accepts.)
- **AC-A.4**: Every M13 abort RuntimeError text now includes the literal string `"Run: python -m plugins.pd.hooks.lib.entity_registry.remediate_m12"`. Verified by grep against current `database.py`.
- **AC-A.5a** (partial-application — abort): Synthetic fixture `m12_partial.sql` (per FR-A.6) at `schema_version=12, has_type=True, has_kind=False, has_lifecycle_class=False` → remediation CLI detects fingerprint != `_PRE_M12_FINGERPRINT` AND != `_POST_M12_FINGERPRINT` → abort with stderr line matching regex `pd\.remediate\.m12_partial: \{.+\}` where JSON portion's keys exactly equal `{"observed_fingerprint", "pre_m12_fingerprint", "post_m12_fingerprint", "divergent_objects_vs_pre", "divergent_objects_vs_post"}` and `divergent_objects_*` are lists of schema-object name strings. Exit code != 0. No data mutation (verified by post-call `PRAGMA table_info` matching pre-call).
- **AC-A.5b** (already-recovered — no-op): Synthetic fixture at `schema_version=12, post-M12 layout` → remediation CLI detects fingerprint == `_POST_M12_FINGERPRINT` → exit 0 with "already-recovered" message. No data mutation.
- **AC-A.5c** (pristine v11 — refuse): Synthetic fixture at `schema_version=11, pre-M11 layout` → remediation CLI exits with "schema_version != 12, nothing to remediate". No data mutation.

### AC-M11 (M11 Guard)

- **AC-M11.1**: Synthetic fixture at `schema_version=11, no workspace_uuid column` → MCP startup → M11 re-runs body → `workspace_uuid` column present. Conditional on FR-M11.2 trigger.

### AC-B (Memory Hygiene)

- **AC-B-H2.1**: After feature ship: in the canonical hook registration file resolved by FR-B-H2.1 (the plugin-shipped manifest, e.g., `plugins/pd/.claude-plugin/plugin.json` or equivalent — implement-phase locates it), the count of `PostToolUse` hook registrations (excluding `PostToolUseFailure`) is 0 for `capture-tool-failure.sh`. Secondary advisory check against `.claude/settings.local.json` if relevant.
- **AC-B-H2.2**: After cleanup query: `SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%' == 0`.
- **AC-B-H3.1**: AST verification on `writer.py:main`: exactly one call to `_apply_quality_gates(...)` AND that call precedes every reachable `db.upsert_entry(...)` invocation.
- **AC-B-H3.2** (single-source-of-truth): AST/grep verification on `memory_server.py`: the 20-char-minimum / 0.95 / 0.90 thresholds appear EXACTLY ONCE in the file, inside `_apply_quality_gates`. No inline duplicates remain in `_process_store_memory`.
- **AC-B-H3.3**: Integration test: CLI input with `description=""` (0 chars, below 20-char min) returns exit code != 0.
- **AC-B-H3.4**: Integration test: CLI input with description matching an existing entry at cosine ≥ 0.95 returns exit code != 0 with stderr matching `near-dup rejection`.
- **AC-B-H4.1**: After backfill migration: `SELECT COUNT(*) FROM entries WHERE source='import' AND observation_count > 100 == 0`.
- **AC-B-H4.2**: After backfill: every row's `source_hash` matches a fresh recomputation of `source_hash(description)` (verified by re-running hash over all rows and comparing column-equality).
- **AC-B-H4.3** (manifest gate): Dry-run mode reports `{n_shifted, n_unchanged, shifted_ids}` and aborts unless `shifted_ids ⊆ Pin I.2 frozen-manifest set` AND `10 ≤ n_shifted ≤ 50`.

### AC-C (Audit Invariant)

- **AC-C.1** (per-callsite emit): For each of the 17 production call sites enumerated in Pin F.1, an integration test exercises the call site (or stubs the entity into the documented status-mutation state) and asserts exactly one new `phase_events` row with `event_type='entity_status_changed'` AND `metadata.type_id` matching, AND `metadata.old_status` / `metadata.new_status` consistent with the call. Test name pattern: `test_audit_emit_{file}_{line}`. For reconciliation callers (#13-15 in Pin F.1: `reconciliation_orchestrator/entity_status.py`), stub the entity into the pre-mutation status directly and call the orchestrator method under test; full reconciliation cycle NOT required. **Special handling for entry #3** (workflow_state_server.py:1339): when FR-C.1 lands, the manual `db.append_phase_event(event_type='entity_status_changed')` block at workflow_state_server.py:1344-1356 MUST be removed (the new emit inside `db.update_entity` supersedes it). AC-C.1's "exactly one" assertion enforces this deduplication.
- **AC-C.2** (fail-open): Mock `append_phase_event` to raise `RuntimeError("simulated")`. Invoke `db.update_entity(uuid, status='completed')` against an entity at `status='active'`. Verify: (a) `entities.status` is now `'completed'`, (b) stderr line matches regex `pd\.audit\.emit_failed: \{.+\}` and the JSON portion's keys exactly equal `{"type_id", "old_status", "new_status", "exception_class"}` with non-null values AND `exception_class == "RuntimeError"`, (c) `_metadata.audit_emit_failed_count` is incremented by 1, (d) no exception propagated.
- **AC-C.3**: AST whitelist removed at `check_status_write_path.py:37`. Verified: `update_entity` NOT in `_PERMITTED_ENCLOSING_DEFS`.
- **AC-C.4** (no-op write): `db.update_entity(uuid, status='active')` against entity already at `status='active'` produces 0 new `entity_status_changed` rows.
- **AC-C.5**: Doctor health-check at session-start: if `audit_emit_failed_count > 0`, emit `severity=warning` issue with the failure count.
- **AC-C.6** (test sweep): All test files calling `update_entity(status=...)` either refactored to `upsert_entity`/`promote_entity` OR allowlisted in `_PERMITTED_TEST_FILES`; full `pytest plugins/pd/` passes; AST check passes (no test-file violations).
- **AC-C.7a** (migration reset): After Migration 15 runs on a DB with `audit_emit_failed_count=5`, the value is `0`.
- **AC-C.7b** (preservation invariant): Integration test creates a synthetic migration `_migration_test_99` that touches `_metadata` for an unrelated key, runs it against a DB where `audit_emit_failed_count=3`, then asserts `audit_emit_failed_count` is still `3`.
- **AC-C.7c** (AST audit): A new doctor check `check_audit_counter_write_path` (AST-based, analogous to `check_status_write_path`) rejects any migration body that mutates `_metadata.audit_emit_failed_count` outside of `_migration_15_audit_emit_counter`. Verified by integration test with a synthetic violating migration body asserted to fail the AST check.

### AC-D (Workspace Fallback)

- **AC-D.1**: Setup: entity registered with `workspace_uuid=_UNKNOWN_WORKSPACE_UUID`, server `_workspace_uuid=<fresh real UUID>`. Call `complete_phase(closes=[...])` → succeeds (pass 1 misses, pass 2 hits `_UNKNOWN_WORKSPACE_UUID`).
- **AC-D.2** (baseline): Same setup, pre-FR-D.1 code: `EntityNotFoundError`. Documents the regression.
- **AC-D.3** (negative): Setup: entity registered with `workspace_uuid=<workspace-A>`, server `_workspace_uuid=<workspace-B>` (BOTH real UUIDs, neither is `_UNKNOWN_WORKSPACE_UUID`). Call `complete_phase(closes=[...])` → `EntityNotFoundError` (fallback only fires for `_UNKNOWN_WORKSPACE_UUID`, never arbitrary cross-workspace).
- **AC-D.4** (log shape): Whenever fallback fires, stderr contains a line matching regex `pd\.workspace\.legacy_fallback: \{.+\}` AND the JSON portion's keys exactly equal `{"call_site", "type_id", "primary_ws", "fallback_ws"}` with non-null values.

### AC-E (Cross-Workspace Gates)

- **AC-E.1**: For each of the 3 gated MCP paths (`set_parent`, `add_dependency`, `add_okr_alignment`): call with cross-workspace UUIDs → JSON error envelope `error_type=cross_workspace_forbidden`. Status code != 0.
- **AC-E.2**: Same paths called with same-workspace UUIDs → succeed as before.
- **AC-E.3**: Allowlisted pair (manually inserted into `cross_workspace_allowlist`) → gate skips, mutation succeeds.
- **AC-E.4**: Doctor check reports cross-workspace `parent_uuid` rows as `severity=warning`. NOT `error`. Existing 21 rows → 21 warnings (pre-triage).
- **AC-E.5** (post-triage):
  ```sql
  SELECT COUNT(*) FROM entities e
  LEFT JOIN entities p ON e.parent_uuid = p.uuid
  LEFT JOIN cross_workspace_allowlist a
    ON a.parent_uuid = p.uuid AND a.child_uuid = e.uuid
  WHERE e.parent_uuid IS NOT NULL
    AND e.workspace_uuid != p.workspace_uuid
    AND a.id IS NULL
  ```
  Result MUST be 0 after triage completes.

### AC-E.2 (Triage Tool)

- **AC-E.2.1**: `cross_workspace_allowlist` table exists post-migration with the schema in FR-E.2.1. CHECK: `PRAGMA table_info(cross_workspace_allowlist)` returns the 6 columns.
- **AC-E.2.2**: Triage doctor fix_action lists all unallowlisted cross-workspace rows and prompts per-row.
- **AC-E.2.3**: Each of (a)/(b)/(c)/(d) decision options produces the expected mutation:
  - (a) re-attribute parent: `entities.workspace_uuid` UPDATE on parent
  - (b) re-attribute child: `entities.workspace_uuid` UPDATE on child
  - (c) delete relation: `entities.parent_uuid = NULL` UPDATE
  - (d) grandfather: INSERT into `cross_workspace_allowlist`

### AC-Sev (Severity Reporting Contract)

- **AC-Sev.1**: Doctor invocation against a DB with cross-workspace `parent_uuid` rows + `audit_emit_failed_count > 0` returns exit code 0 AND output JSON contains `severity_summary.warning > 0`.
- **AC-Sev.2**: Doctor output JSON's `severity_summary` field is present in all invocations. Schema (additive — MAY include extra severity keys for forward-compat): `{"severity_summary": {"error": int, "warning": int, "suggestion": int, ...}}` with non-negative integer values. Consumers MUST tolerate additional keys (e.g., `info`).
- **AC-Sev.3**: Per-issue record schema in doctor JSON output: `{"severity": "error"|"warning"|"suggestion", ...}`. Verified by JSON schema validation against all emitted issue records.

## 4. Empirical SUT Pins (production-DB-verified at spec time + frozen fixture references)

| Pin | Statement | Verification |
|-----|-----------|--------------|
| **A.evidence** | Production `~/.claude/pd/entities/entities.db` was observed at `schema_version=12, pre-M12 layout` before manual rollback to 11 on 2026-05-16T18:40Z. Evidence-only; tests use Pin A.fix. | `git log -- ~/.claude/pd/entities/entities.db.pre-m12-recovery-*.bak` |
| **A.fix** | Synthetic fixture script `plugins/pd/hooks/lib/entity_registry/fixtures/m12_stub_trap.sql` (created in this feature) deterministically builds a pre-M12-layout DB with `schema_version=12` for test runs. All AC-A* repros use this fixture, NOT the live DB. | fixture file shipped + integration test asserts state-after-fixture-load |
| **C** | 457 entities, 945 phase_events in production DB (snapshot 2026-05-16) | `SELECT COUNT(*) FROM entities; SELECT COUNT(*) FROM phase_events` |
| **D** | 0 `entity_status_changed` rows out of 945 — audit invariant has never held | `SELECT COUNT(*) FROM phase_events WHERE event_type='entity_status_changed'` |
| **E** | 21 cross-workspace `parent_uuid` rows (joined entities table to itself) | join query per AC-E.5 |
| **F.1** | **17 distinct production `update_entity(status=...)` callers** at the following file:line locations (frozen at spec time, 2026-05-16):<br>1. `plugins/pd/scripts/cleanup_backlog.py:224`<br>2. `plugins/pd/mcp/entity_server.py:369-373` (multi-line, `_process_update_entity` — single canonical mutation site)<br>3. `plugins/pd/mcp/workflow_state_server.py:1339-1344` (multi-line, F111 closure — **NOTE: already emits `entity_status_changed` manually at 1344-1356 with `closed_by_uuid` metadata key; after FR-C.1 lands, MUST remove the manual emit to avoid double-emit. **Accepted trade-off**: FR-C.1's emit inside `db.update_entity` cannot include `closed_by_uuid` (not available in update_entity signature). Loss of `closed_by_uuid` in closure events is accepted as part of the observability-grade fail-open audit model. Operators needing the closer-uuid for closures can correlate via the closure's `fixes` relation in `entity_relations` table (F111 IF-2 step 7).**)<br>4. `plugins/pd/hooks/lib/doctor/fix_actions.py:177` (promoted)<br>5. `plugins/pd/hooks/lib/doctor/fix_actions.py:185` (dropped)<br>6. `plugins/pd/hooks/lib/workflow_engine/entity_engine.py:371` (abandoned)<br>7. `plugins/pd/hooks/lib/workflow_engine/entity_engine.py:398` (child abandoned)<br>8. `plugins/pd/hooks/lib/workflow_engine/entity_engine.py:477` (completed)<br>9. `plugins/pd/hooks/lib/workflow_engine/engine.py:180` (feature completed)<br>10. `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py:93` (promoted)<br>11. `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py:200` (generic)<br>12. `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py:338` (active)<br>13. `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:53-55` (multi-line, archived)<br>14. `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:83-85` (multi-line, meta_status)<br>15. `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py:209-211` (multi-line, archived)<br>16. `plugins/pd/hooks/lib/entity_registry/dependencies.py:109` (planned)<br>17. `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:183` (target_phase)<br><br>**Excluded from count** (verified wrappers, not distinct mutation sites): `plugins/pd/mcp/entity_server.py:969-971` is a forwarder to `_process_update_entity` (entry #2 above); a single test covers both. | `rg -nU "update_entity\\([^)]*status=" plugins/pd/ -g '!test_*.py' -g '!**/tests/**' -g '!.venv/**' -g '*.py'` |
| **F.2** | M13 abort sites: 4 occurrences of `"feature-109 deferred remediation"` in `database.py`. Lines: 4027, 4052, 4088, 4112. (Spec previously said 7; corrected.) | `rg -n "feature-109 deferred remediation" plugins/pd/hooks/lib/entity_registry/database.py` |
| **G** | 3 `_workspace_uuid or ""` sites: `entity_server.py:562`, `entity_server.py:704`, `workflow_state_server.py:1184` | `grep -rn '_workspace_uuid or ""' plugins/pd/` |
| **H** | 464 `Tool failure:` rows in `~/.claude/pd/memory/memory.db` (29% of 1581) | `SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` |
| **I.1** | 10 entries at `observation_count=1438`, all `source='import'`, `created_at=2026-03-19`. Top inflated entry IDs: collected at spec time | `SELECT id FROM entries WHERE source='import' AND observation_count > 100` |
| **I.2** | **Hash-shift frozen manifest** — implement runs the FR-B-H4.2 dry-run during implementation and freezes the resulting `shifted_ids` set into a fixture at `plugins/pd/hooks/lib/semantic_memory/fixtures/hash_shift_manifest.json`. The migration consumes this fixture. Spec time cannot run this without the memory MCP active; implement-phase verification documented in plan. | implement-phase action |
| **J** | M12 stub commit: `6722191a1ae196fbaaa26ee660fd0712c924f389` | `git show --stat 6722191a` |
| **K** | `_PERMITTED_ENCLOSING_DEFS` at `check_status_write_path.py:32-40` includes `update_entity` at line 37 | grep |
| **L** | M11 same-trap guards at `database.py:1818, 1899` | grep |
| **M** | issue_spawn gate template at `entity_server.py:734-739` (replicate to 3 missing paths in FR-E.2) | grep |
| **N** | `add_entity_tag` signature confirmed single-entity at `entity_server.py:1087` — takes `(type_id, tag: str)`, no second entity reference. Excluded from FR-E.2 gates. | `entity_server.py:1087-1095` |
| **O** | **Migration numbering** for this feature's new migrations (M14 is current head; new migrations queue after):<br>- **M15** = `_migration_15_audit_emit_counter` (FR-C.3 reset) — sequenced under Cluster C<br>- **M16** = `_migration_16_hash_unify_and_cleanup` (FR-B-H4 backfill + FR-B-H2.2 cleanup query) — sequenced under Cluster B-H4<br>- **M17** = `_migration_17_cross_workspace_allowlist` (FR-E.2.1 schema) — sequenced under Cluster E.2<br>Cluster A (M12 fingerprint guard, FR-A.6 fixtures, remediation CLI) introduces NO new migration — it tightens M12's existing guard and ships an out-of-band CLI/fix_action. Migration order matches Cluster Sequencing order. **Implement-phase guard**: verify M14 is still the current head via `grep -cE "_migration_1[5-9]" plugins/pd/hooks/lib/entity_registry/database.py` == 0 before assigning M15/M16/M17. If head has advanced (rare for develop branch), renumber and update all FR/AC references in a pre-implement spec amendment. | reference |

## 5. Out-of-Scope (Non-Goals)

Per PRD Non-Goals (carried forward verbatim):
- H1 capture-hook `ask-first` mode handling
- H5 `init_entity_workflow` accepts bug/task
- H7 `lifecycle_class` no CHECK constraint
- H9a F111 mixed-semantics boundary observability
- Hard-error escalation for Cluster E (deferred until 21 triage complete + operator-confidence builds)
- Full event-sourcing audit retrofit (this feature: observability-grade fail-open emit only)

Additional scope-creep guards (each annotated with the FR it constrains):
- Do NOT add new entity types or workspace concepts (constrains FR-E* — gates use new helper, not schema changes to entities table)
- Do NOT change `_KIND_TO_TYPE_LIFECYCLE` mapping (constrains FR-A — recovery preserves taxonomy)
- Do NOT extend `_CLOSES_TERMINAL` dictionary (constrains FR-D — fallback doesn't touch closure logic)
- Do NOT modify F111's `complete_phase(closes=...)` behavior beyond FR-D fixes (constrains FR-D)
- Do NOT touch FTS5 rebuild logic (constrains FR-A — fingerprint detector reads FTS triggers but does not rewrite)
- Do NOT change `register_entity` raise-on-conflict semantics (constrains FR-E — gates intercept BEFORE register_entity)

## 6. Risks Carried Forward (PRD section)

All 10 PRD Risk-table rows apply to this spec. Key items implementation must respect:

1. Emit fail-open is mandatory; transactional coupling is anti-goal (FR-C.2).
2. Cluster C emit depends on Cluster D landing first — sequencing constraint (Section 8).
3. AST whitelist removal sweeps test fixtures BEFORE the whitelist is touched (FR-C.4 precondition).
4. Hash backfill is dry-run-gated against expected-shift manifest (FR-B-H4.2 + Pin I.2).
5. Workspace fallback strictly gated to `_UNKNOWN_WORKSPACE_UUID` only (FR-D.1).
6. M11 partial-state detection conditional on Open Question 7 (FR-M11.2).
7. Cluster E doctor check ships warning-only; hard-error escalation is non-goal (FR-E.6).

## 7. Open Questions (for design phase)

(Carried from PRD.)
1. M12 remediation: prompt vs silent? (Default: prompt, YOLO auto-accepts)
2. Cross-workspace triage UX: CLI or doctor fix_action? (Default: doctor fix_action)
3. Hash backfill scope: all or subset? (Default: all, with frozen manifest gate per Pin I.2)
4. update_entity emit on metadata-only changes? (Default: no, status-change-only)
5. AST whitelist removal: before or after Cluster C lands? (Default: after, sweep tests first)
6. `_UNKNOWN_WORKSPACE_UUID` data migration: re-attribute? (Default: defer)
7. Partial-M11 recovery code: detect or document? (Default: detect-and-skip if zero cost; ship only if probe finds reachable state)

## 8. Cluster Sequencing (Implementation Order)

```
[1] FR-A         (M12 guard + remediation CLI + fingerprint detector)
[1] FR-A.6       (fixtures m12_stub_trap.sql / pre_m11.sql / post_m12.sql / m12_partial.sql)
[1] FR-M11       (M11 guard tightening, parallel with A)
        ↓
[2] FR-D         (workspace fallback — needed by FR-C)
        ↓
[3] FR-C         (audit invariant emit, Migration 15 reset, AST audit check)
        ↓
[4-pre] FR-B-H4.0  (write recompute_source_hash helper + dry-run + freeze hash_shift_manifest.json + commit) — prerequisite for [4]
        ↓
[4] FR-B-H4      (Migration 16: hash unification backfill consuming frozen manifest + observation_count cleanup)
        ↓
[5] FR-B-H3      (writer CLI gate extraction, single source of truth)
[5] FR-B-H2      (capture hook simplification, parallel with B-H3)
        ↓
[6] FR-E         (cross-workspace gates 3 sites, warning-only output-JSON)
[6] FR-E.2       (Migration 17: cross_workspace_allowlist + triage tool, parallel with E)
[6] FR-Sev       (output-JSON severity_summary contract + tests, parallel)
```

**Migration order**: M15 (under [3]) → M16 (under [4]) → M17 (under [6]). Matches Pin O.

Plan phase will produce a task DAG honoring this order.
