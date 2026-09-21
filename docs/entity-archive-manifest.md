# Entity Archive Manifest

**Generated:** 2026-09-22 by `scripts/gen_archive_manifest.py` (read-only).

Every entity flagged **`entities.is_archived`** or **`entities.is_legacy`**. Legacy means the identity predates the structural model, so its sequence number and slug exist only inside its `entity_id` text.

`is_legacy` is a stated column (v2 migration 4), not an inference. It previously meant "has no `entity_display` row", which derived a semantic fact from a structural accident and conflated two unrelated populations: genuine pre-structural rows, and rows a buggy non-strict write failed to give a display row. The second is now visible as `is_legacy = 0` with no display row — a bug, not history.

## Recovery

**Archived entities are recoverable.** Archival sets `status` and adds a tag; it never deletes. Deletion is in fact impossible for every entity here — each has an `events` row, and `events` has a `NOT NULL` foreign key to `entities(uuid)` with no `ON DELETE`, so `delete_entity` raises unconditionally.

```python
db.update_entity(type_id, status="archived")   # archive
db.add_tag(uuid, "legacy-archived-2026-09")    # mark
db.update_entity(type_id, status="open")       # restore — row intact
db.remove_tag(uuid, "legacy-archived-2026-09")
```

Restoration is a forward write through the sanctioned path, not a rollback. Two costs: each archive/restore pair leaves ~2 permanently immutable `events` rows, and the sequence number is never released.

**Legacy-ness lives in `entities.is_legacy`, not in a tag.** The earlier `legacy-archived-2026-09` tag was removed once the column existed: two homes for one fact is the defect this effort removes. `workspace-retired-*` remains because it says something different — a dormant workspace was stood down, and those rows were never legacy.

**Archiving no longer overwrites status** (v2 migration 5). `status` is workflow state; `is_archived` is whether it is put away. Of 170 archived rows, 125 had been `completed` and said so nowhere — archiving had destroyed it. 163 were restored from `phase_events.metadata.old_status`; the remaining 7 have no recorded prior status and keep `status = 'archived'`.

## Summary by workspace

`live` = status `open`/`active`/`planned`/NULL. Everything else is finished work whose archival changes nothing anyone is using.

| Workspace | is_legacy | Archived | **live + legacy** |
|---|---:|---:|---:|
| `/Users/terry/projects/cast-below` | 2 | 1 | **0** |
| `/Users/terry/projects/pedantic-drip` | 175 | 156 | **14** |
| `/Users/terry/projects/project_illium` | 0 | 1 | **0** |
| `/Users/terry_agent` | 3 | 12 | **2** |
| **Total** | **180** | **170** | **16** |

The last column is the one that matters: rows a clean break would archive that someone might still be relying on.

### The live rows, in full

| Workspace | kind | entity_id | status | kids | name |
|---|---|---|---|--:|---|
| `pedantic-drip` | backlog | `00059` | open |  | Pre-review lint for curly-brace template place |
| `pedantic-drip` | backlog | `00060` | open |  | Structured Git Operations Reference for design |
| `pedantic-drip` | backlog | `00063` | open |  | Entity rename tooling or convention for scope- |
| `pedantic-drip` | backlog | `00177` | open |  | [LOW/security] `_resolve_project_id()` emits s |
| `pedantic-drip` | backlog | `00180` | open |  | [LOW/correctness] `_detect_phase_events_drift` |
| `pedantic-drip` | backlog | `00183` | open |  | [LOW/implementation] AC-5 allowlist test missi |
| `pedantic-drip` | backlog | `00190` | open |  | [LOW/test-gap] AC-5 rejection test misses non- |
| `pedantic-drip` | project | `P001` | *(NULL)* |  | P001 |
| `pedantic-drip` | project | `P001-openclaw-gap-analysis` | active |  | Openclaw Gap Analysis |
| `pedantic-drip` | project | `P002` | active | 5 | memory-flywheel |
| `pedantic-drip` | project | `P002-memory-flywheel` | active |  | Memory Flywheel |
| `pedantic-drip` | project | `P003` | active | 4 | entity-system-redesign |
| `pedantic-drip` | project | `P003-entity-system-redesign` | active | 1 | Entity System Redesign |
| `pedantic-drip` | project | `P004-entity-db-redesign` | active | 16 | Entity Db Redesign |
| `terry_agent` | project | `P001` | active | 12 | agent-orchestrator |
| `terry_agent` | project | `P001-agent-orchestrator` | active | 3 | Agent Orchestrator |

## Detail — every row

### `/Users/terry/projects/cast-below`

| kind | entity_id | status | disp | kids | parent | tags | name |
|---|---|---|:--:|--:|---|---|---|
| brainstorm | `original-ideation-prd` | archived | yes | yes | — |  |  |  | 🎣 Cast Below |
| project | `P001` | completed | — | yes | — | 29 | 20260223-222936-world-readable |  | P001 |

### `/Users/terry/projects/pedantic-drip`

| kind | entity_id | status | disp | kids | parent | tags | name |
|---|---|---|:--:|--:|---|---|---|
| backlog | `00008` | dropped | — | yes | — |  |  |  | add product manager, product owner team (agents, |
| backlog | `00012` | dropped | — | yes | — |  |  |  | fix the secretary AskUserQuestion formatting. Th |
| backlog | `00014` | dropped | — | yes | — |  |  |  | Security Scanning — static rule-based security s |
| backlog | `00015` | dropped | — | yes | — |  |  |  | Cross-Platform Hooks — port Bash hooks to Node.j |
| backlog | `00017` | dropped | — | yes | — |  |  |  | Unified Central Context Management — expand the  |
| backlog | `00018` | dropped | — | yes | — |  |  |  | Knowledge Bank Auto-Logging — upgrade knowledge  |
| backlog | `00020` | promoted | — | yes | — |  |  |  | Consider renaming the plugin/repository to `peda |
| backlog | `00024` | dropped | — | yes | — |  |  |  | Add `remove_entry` method to the entity registry |
| backlog | `00026` | dropped | — | yes | — |  |  |  | Add feature subfiles into the entity DB to facil |
| backlog | `00027` | promoted | — | yes | — |  |  |  | Simplify secretary by removing aware and orchest |
| backlog | `00028` | dropped | — | yes | — |  |  |  | Add software-architect, product-manager, devops- |
| backlog | `00029` | dropped | — | yes | — |  |  |  | Remove project lifetime soft constraint from cre |
| backlog | `00030` | dropped | — | yes | — |  |  |  | Fix register_entity MCP tool to correctly proces |
| backlog | `00031` | promoted | — | yes | — |  |  |  | Handle DB write lock and concurrent write — ensu |
| backlog | `00032` | dropped | — | yes | — |  |  |  | Fix the workflow progression such that if a PRD  |
| backlog | `00033` | promoted | — | yes | — |  |  |  | Reduce diff comparison for deploying reviewers.  |
| backlog | `00034` | promoted | — | yes | — |  |  |  | Update code simplifier to use Claude Code's nati |
| backlog | `00035` | dropped | — | yes | — |  |  |  | Enrich secretary problem solving frameworks and  |
| backlog | `00036` | dropped | — | yes | — |  |  |  | Add system design architect and solution archite |
| backlog | `00038` | promoted | — | yes | — |  |  |  | Knowledge bank markdown-to-DB sync gap — markdow |
| backlog | `00039` | dropped | — | yes | — |  |  |  | show-status and list-features should filter out  |
| backlog | `00040` | promoted | — | yes | — |  |  |  | Close entity registry status tracking gaps — pro |
| backlog | `00044` | promoted | — | yes | — | 1 |  |  | 5D stage context accumulation: Each 5D stage (di |
| backlog | `00045` | promoted | — | yes | — |  |  |  | Fix pd SQLite DB locking bugs: (1) MemoryDatabas |
| backlog | `00046` | dropped | — | yes | — |  |  |  | Add brainstorm review cycle to brainstorm |
| backlog | `00047` | promoted | — | yes | — |  |  |  | reconciliation_orchestrator does not detect stal |
| backlog | `00048` | dropped | — | yes | — |  |  |  | release.sh: add pre-push tag existence check (gi |
| backlog | `00049` | promoted | — | yes | — | 1 |  |  | Phase transition summary with reviewer feedback |
| backlog | `00050` | dropped | — | yes | — |  |  |  | Add lightweight pre-push git hook that validates |
| backlog | `00051` | promoted | — | yes | — |  |  |  | Extract workflow execution data from metadata JS |
| backlog | `00052` | promoted | — | yes | — | 1 |  |  | Active real-time mistake monitor — Add a PostToo |
| backlog | `00053` | promoted | — | yes | — | 2 |  |  | Memory flywheel — close the self-improvement loo |
| backlog | `00059` | open | — | yes | — |  |  |  | Pre-review lint for curly-brace template placeho |
| backlog | `00060` | open | — | yes | — |  |  |  | Structured Git Operations Reference for design p |
| backlog | `00063` | open | yes | yes | — |  |  |  | Entity rename tooling or convention for scope-pi |
| backlog | `00064` | promoted | yes | yes | — |  |  |  | /pd:promote-pattern classifier is too keyword-he |
| backlog | `00065` | promoted | yes | yes | — |  |  |  | Add "enforceability" filter to /pd:promote-patte |
| backlog | `00066` | promoted | yes | yes | — |  |  |  | /pd:promote-pattern bare-CLI ergonomics: arg mis |
| backlog | `00067` | dropped | yes | yes | — |  |  |  | Security: `entry_name` not sanitized before TD-8 |
| backlog | `00068` | dropped | yes | yes | — |  |  |  | Security: `~/.claude/pd/memory/influence-debug.l |
| backlog | `00069` | dropped | yes | yes | — |  |  |  | Operability: influence-debug.log has no size cap |
| backlog | `00070` | dropped | yes | yes | — |  |  |  | Code quality: `_warn_and_default`/`_ranker_warn_ |
| backlog | `00071` | dropped | yes | yes | — |  |  |  | Code quality: `_emit_influence_diagnostic` log s |
| backlog | `00072` | dropped | yes | yes | — |  |  |  | Code quality: MCP wrapper `record_influence_by_c |
| backlog | `00073` | dropped | yes | yes | — |  |  |  | Code quality: hook generator test-script stubs f |
| backlog | `00074` | dropped | yes | yes | — |  |  |  | Testability: AC-7 / AC-7b / AC-11 grep assertion |
| backlog | `00075` | dropped | yes | yes | — |  |  |  | No timeout cap when gtimeout/timeout absent in s |
| backlog | `00076` | dropped | yes | yes | — |  |  |  | Equal decay thresholds + rapid sequential calls  |
| backlog | `00077` | dropped | yes | yes | — |  |  |  | AC-22 test covers file-missing only; not SyntaxE |
| backlog | `00078` | dropped | yes | yes | — |  |  |  | `_select_candidates` accesses `db._conn` directl |
| backlog | `00079` | dropped | yes | yes | — |  |  |  | `updated_at IS NULL` guard in `_execute_chunk` S |
| backlog | `00080` | dropped | yes | yes | — |  |  |  | `__unknown__` project_id sentinel from `record_b |
| backlog | `00081` | dropped | yes | yes | — |  |  |  | Unknown `query_type` in `query_phase_analytics`  |
| backlog | `00082` | dropped | yes | yes | — |  |  |  | Missing negative tests: CHECK constraint rejecti |
| backlog | `00083` | dropped | yes | yes | — |  |  |  | `_compute_durations` silently drops timestamp pa |
| backlog | `00084` | dropped | yes | yes | — |  |  |  | AC-16 only tests transition_phase failure resili |
| backlog | `00085` | dropped | yes | yes | — |  |  |  | **[HIGH/security]** ReDoS in... |
| backlog | `00086` | dropped | yes | yes | — |  |  |  | **[HIGH/concurrency]** Async coroutine umask rac |
| backlog | `00087` | dropped | yes | yes | — |  |  |  | **[HIGH/testability]** FR-6 caller-passed thresh |
| backlog | `00088` | dropped | yes | yes | — |  |  |  | **[MED/correctness]** Missing JSON escaping in.. |
| backlog | `00089` | dropped | — | yes | — |  |  |  | **[MED/quality]** Rotation failure permanently s |
| backlog | `00090` | dropped | — | yes | — |  |  |  | **[MED/quality]** Pytest global-state pollution  |
| backlog | `00091` | dropped | — | yes | — |  |  |  | **[MED/quality]** FR-4 completeness gap — `cfg.g |
| backlog | `00092` | dropped | — | yes | — |  |  |  | **[MED/testability]** 10 MB rotation boundary of |
| backlog | `00093` | dropped | — | yes | — |  |  |  | **[MED/testability]** Shell-vs-Python regex sema |
| backlog | `00094` | dropped | — | yes | — |  |  |  | **[LOW/observation]** SC-9(a) source grep fragil |
| backlog | `00095` | dropped | — | yes | — |  |  |  | **[HIGH/security]** Python heredoc injection in. |
| backlog | `00096` | dropped | — | yes | — |  |  |  | **[HIGH/security]** OverflowError escape from `t |
| backlog | `00097` | dropped | — | yes | — |  |  |  | **[HIGH/security]** Symlink-clobber on `influenc |
| backlog | `00098` | dropped | — | yes | — |  |  |  | **[HIGH/quality]** `_resolve_int_config` clamp p |
| backlog | `00099` | dropped | — | yes | — |  |  |  | **[HIGH/correctness]** isoformat() vs strftime() |
| backlog | `00100` | dropped | — | yes | — |  |  |  | **[HIGH/implementation]** AC-11 spec requires st |
| backlog | `00101` | dropped | — | yes | — |  |  |  | **[HIGH/implementation]** AC-10 spec text still  |
| backlog | `00102` | dropped | — | yes | — |  |  |  | **[MED/security]** `memory_decay_*` config keys  |
| backlog | `00103` | dropped | — | yes | — |  |  |  | **[MED/security]** CLI `--project-root` in `main |
| backlog | `00104` | dropped | — | yes | — |  |  |  | **[MED/quality]** Test file `test_maintenance.py |
| backlog | `00105` | dropped | — | yes | — |  |  |  | **[MED/quality]** Duplicate `_warn_and_default`  |
| backlog | `00106` | dropped | — | yes | — |  |  |  | **[MED/quality]** Dead `now_iso` parameter in `_ |
| backlog | `00107` | dropped | — | yes | — |  |  |  | **[MED/security]** Unbounded SELECT in `_select_ |
| backlog | `00108` | dropped | — | yes | — |  |  |  | **[MED/implementation]** AC-20b-1/20b-2 spec tar |
| backlog | `00109` | dropped | — | yes | — |  |  |  | **[MED/implementation]** FR-2 spec NULL-branch t |
| backlog | `00110` | dropped | — | yes | — |  |  |  | **[MED/implementation]** Retro EQP file `agent_s |
| backlog | `00111` | dropped | — | yes | — |  |  |  | **[MED/quality]** Module-level `NOW = datetime(. |
| backlog | `00112` | dropped | — | yes | — |  |  |  | **[MED/security]** `run_memory_decay` in `sessio |
| backlog | `00113` | dropped | — | yes | — |  |  |  | **[MED/testability]** Boundary-equality (`last_r |
| backlog | `00114` | dropped | — | yes | — |  |  |  | **[MED/testability]** Tz-naive `now` handling si |
| backlog | `00115` | dropped | — | yes | — |  |  |  | **[MED/testability]** Zero cross-feature integra |
| backlog | `00116` | dropped | — | yes | — |  |  |  | **[LOW/testability]** Additional gaps: empty-DB  |
| backlog | `00117` | dropped | — | yes | — |  |  |  | **[HIGH/security]** Cross-project data leakage i |
| backlog | `00118` | dropped | — | yes | — |  |  |  | **[HIGH/security]** Migration 10 concurrent-invo |
| backlog | `00119` | dropped | — | yes | — |  |  |  | **[HIGH/security]** `record_backward_event` acce |
| backlog | `00120` | dropped | — | yes | — |  |  |  | **[HIGH/quality]** Both `record_backward_event`  |
| backlog | `00121` | dropped | — | yes | — |  |  |  | **[HIGH/quality]** `query_phase_events` uses `SE |
| backlog | `00122` | dropped | — | yes | — |  |  |  | **[HIGH/implementation]** `SKILL.md:402-412` cal |
| backlog | `00123` | dropped | — | yes | — |  |  |  | **[HIGH/implementation]** `_compute_durations:17 |
| backlog | `00124` | dropped | — | yes | — |  |  |  | **[MED/correctness]** Dual-write `insert_phase_e |
| backlog | `00125` | dropped | — | yes | — |  |  |  | **[MED/security]** Unbounded JSON round-trip on  |
| backlog | `00126` | dropped | — | yes | — |  |  |  | **[MED/security]** Raw `str(e)` exception leak i |
| backlog | `00127` | dropped | — | yes | — |  |  |  | **[MED/security]** Migration 10 backfill (`datab |
| backlog | `00128` | dropped | — | yes | — |  |  |  | **[MED/quality]** `_compute_durations:1737` defe |
| backlog | `00129` | dropped | — | yes | — |  |  |  | **[MED/quality]** Migration 10 top-level `except |
| backlog | `00130` | dropped | — | yes | — |  |  |  | **[MED/quality]** `test_workflow_state_server.py |
| backlog | `00131` | dropped | — | yes | — |  |  |  | **[MED/implementation]** AC-19 test only asserts |
| backlog | `00132` | dropped | — | yes | — |  |  |  | **[MED/implementation]** iteration_summary appli |
| backlog | `00133` | dropped | — | yes | — |  |  |  | **[LOW/suggestion]** `phase_duration`/`backward_ |
| backlog | `00134` | dropped | — | yes | — |  |  |  | **[HIGH/testability]** `insert_phase_event` unco |
| backlog | `00135` | dropped | — | yes | — |  |  |  | **[HIGH/testability]** Reconciliation is `phase_ |
| backlog | `00136` | dropped | — | yes | — |  |  |  | **[MED/testability]** Additional gaps: `.meta.js |
| backlog | `00137` | dropped | — | yes | — |  |  |  | **[MED/process]** Feature 084 has no `retro.md`  |
| backlog | `00138` | dropped | — | yes | — |  |  |  | Deferred 082/084 test-gap sub-items not addresse |
| backlog | `00139` | dropped | — | yes | — |  |  |  | [HIGH/security] `_coerce_bool` at `config.py:59` |
| backlog | `00140` | dropped | — | yes | — |  |  |  | [HIGH/security] `execute_test_sql_for_testing`,  |
| backlog | `00141` | dropped | — | yes | — |  |  |  | [HIGH/correctness] `_iso_utc(dt)` at `maintenanc |
| backlog | `00142` | dropped | — | yes | — |  |  |  | [HIGH/correctness] Migration 10 at `database.py: |
| backlog | `00143` | dropped | — | yes | — |  |  |  | [HIGH/security] `query_phase_analytics` at `work |
| backlog | `00144` | dropped | — | yes | — |  |  |  | [HIGH/correctness] `execute_test_sql_for_testing |
| backlog | `00145` | dropped | — | yes | — |  |  |  | [HIGH/spec-drift] AC-23 LOC target violated. Bas |
| backlog | `00146` | dropped | — | yes | — |  |  |  | [HIGH/correctness] Bundle L `_detect_phase_event |
| backlog | `00147` | dropped | — | yes | — |  |  |  | [MED/consistency] `backward_frequency` query at  |
| backlog | `00148` | dropped | — | yes | — |  |  |  | [MED/duplication] `refresh.py:180` formats times |
| backlog | `00149` | dropped | — | yes | — |  |  |  | [MED/quality] `_TRUE_VALUES`/`_FALSE_VALUES` mod |
| backlog | `00150` | dropped | — | yes | — |  |  |  | [MED/performance] `_detect_phase_events_drift` N |
| backlog | `00151` | dropped | — | yes | — |  |  |  | [MED/correctness] `entity.get('project_id') or ' |
| backlog | `00152` | dropped | — | yes | — |  |  |  | [MED/consistency] Migration 10 writes schema_ver |
| backlog | `00153` | dropped | — | yes | — |  |  |  | [MED/correctness] PATH pinning in `run_memory_de |
| backlog | `00154` | dropped | — | yes | — |  |  |  | [MED/security] O_NOFOLLOW + fchmod log-open has  |
| backlog | `00155` | dropped | — | yes | — |  |  |  | [MED/testability] `_warn_and_default` module-sta |
| backlog | `00156` | dropped | — | yes | — |  |  |  | [MED/spec-drift] AC-10 `strftime` grep-verificat |
| backlog | `00157` | dropped | — | yes | — |  |  |  | [MED/spec-drift] AC-34b targets function name `_ |
| backlog | `00158` | dropped | — | yes | — |  |  |  | [MED/spec-drift] AC-22 "line-for-line identical" |
| backlog | `00159` | dropped | — | yes | — |  |  |  | [MED/quality] `plugins/pd/mcp/test_workflow_stat |
| backlog | `00160` | dropped | — | yes | — |  |  |  | [MED/testability] `_coerce_bool` tested only for |
| backlog | `00161` | dropped | — | yes | — |  |  |  | [MED/testability] `_iso_utc(dt)` direct unit tes |
| backlog | `00162` | dropped | — | yes | — |  |  |  | [MED/testability] `scan_limit=0` edge untested.  |
| backlog | `00163` | dropped | — | yes | — |  |  |  | [MED/testability] `run_memory_decay` Python-subp |
| backlog | `00164` | dropped | — | yes | — |  |  |  | [MED/testability] `record_backward_event` server |
| backlog | `00165` | dropped | — | yes | — |  |  |  | [MED/testability] Dual-write retry semantics aft |
| backlog | `00166` | dropped | — | yes | — |  |  |  | [MED/testability] Migration-10 concurrent with l |
| backlog | `00167` | dropped | — | yes | — |  |  |  | [MED/testability] `reconcile_check → manual-fix  |
| backlog | `00168` | dropped | — | yes | — |  |  |  | [MED/testability] `_warn_unknown_keys` dedup beh |
| backlog | `00169` | dropped | — | yes | — |  |  |  | [MED/testability] `_detect_phase_events_drift` e |
| backlog | `00170` | dropped | — | yes | — |  |  |  | [MED/testability] `reviewer_notes` boundary at M |
| backlog | `00171` | dropped | — | yes | — |  |  |  | [MED/testability] Bundle L ↔ Bundle E integratio |
| backlog | `00172` | dropped | — | yes | — |  |  |  | [HIGH/implementation] AC-21 `test_decay_python_s |
| backlog | `00173` | dropped | — | yes | — |  |  |  | [MED/security] `_assert_testing_context()` at... |
| backlog | `00174` | dropped | — | yes | — |  |  |  | [MED/correctness] Migration 10 schema_version cr |
| backlog | `00175` | dropped | — | yes | — |  |  |  | [MED/correctness] `query_phase_events_bulk(event |
| backlog | `00176` | dropped | — | yes | — |  |  |  | [MED/test-drift] AC-22 test... |
| backlog | `00177` | open | — | yes | — |  |  |  | [LOW/security] `_resolve_project_id()` emits std |
| backlog | `00178` | dropped | — | yes | — |  |  |  | [LOW/security] `reset_warning_state()` public in |
| backlog | `00179` | dropped | — | yes | — |  |  |  | [LOW/security] `trap 'export PATH="$PATH_OLD"' R |
| backlog | `00180` | open | — | yes | — |  |  |  | [LOW/correctness] `_detect_phase_events_drift` w |
| backlog | `00181` | dropped | — | yes | — |  |  |  | [LOW/quality] `_coerce_bool` int-literal branche |
| backlog | `00182` | dropped | — | yes | — |  |  |  | [LOW/quality] Test parametrize sentinel `"defaul |
| backlog | `00183` | open | — | yes | — |  |  |  | [LOW/implementation] AC-5 allowlist test missing |
| backlog | `00184` | dropped | — | yes | — |  |  |  | [LOW/implementation] AC-7 `test_influence_log_re |
| backlog | `00185` | dropped | — | yes | — |  |  |  | [LOW/implementation] AC-10... |
| backlog | `00186` | dropped | — | yes | — |  |  |  | [LOW/implementation] AC-1 `test_coerce_bool_rout |
| backlog | `00187` | dropped | — | yes | — |  |  |  | [LOW/test-gap] AC-28 boundary test misses compou |
| backlog | `00188` | dropped | — | yes | — |  |  |  | [LOW/test-gap] AC-18 parametrize omits load-bear |
| backlog | `00189` | dropped | — | yes | — |  |  |  | [LOW/test-gap] AC-7 TOCTOU fd-fstat defense at ` |
| backlog | `00190` | open | — | yes | — |  |  |  | [LOW/test-gap] AC-5 rejection test misses non-st |
| backlog | `00191` | dropped | — | yes | — |  |  |  | [LOW/test-gap] Fixture asymmetry: `test_refresh. |
| backlog | `00217` | promoted | — | yes | — | 1 |  |  | Backlog #00217 |
| backlog | `00246` | promoted | — | yes | — | 1 |  |  | Backlog #00246 |
| backlog | `00277` | promoted | — | yes | — | 1 |  |  | Backlog #00277 |
| brainstorm | `20260324-000000-causal-inference-training` | archived | yes | — | yes |  |  |  | 20260324-000000-causal-inference-training |
| brainstorm | `original_claude_code_special_force_design` | abandoned | — | yes | — |  |  |  | original_claude_code_special_force_design |
| brainstorm | `vast-mixing-lerdorf` | promoted | — | yes | — | 1 |  |  | External: /Users/terry/.claude/plans/vast-mixing |
| feature | `001-entity-uuid-primary-key-migrat` | completed | yes | — | yes |  | P001 |  | Entity Uuid Primary Key Migrat |
| feature | `002-change-workflow-ordering` | completed | yes | — | yes |  |  |  | Change Workflow Ordering |
| feature | `002-markdown-entity-file-header-sc` | completed | yes | — | yes |  | P001 |  | Markdown Entity File Header Sc |
| feature | `003-bidirectional-uuid-sync-betwee` | completed | yes | — | yes |  | P001 |  | Bidirectional Uuid Sync Betwee |
| feature | `003-workflow-orchestration` | completed | yes | — | yes |  |  |  | Workflow Orchestration |
| feature | `004-status-taxonomy-design-and-sch` | completed | yes | — | yes |  | P001 |  | Status Taxonomy Design And Sch |
| feature | `004-update-documentation-step` | completed | yes | — | yes |  |  |  | Update Documentation Step |
| feature | `005-make-specs-executable` | completed | yes | — | yes |  |  |  | Make Specs Executable |
| feature | `005-workflowphases-table-with-dual` | completed | yes | — | yes |  | P001 |  | Workflowphases Table With Dual |
| feature | `006-retro-before-cleanup` | completed | yes | — | yes |  |  |  | Retro Before Cleanup |
| feature | `006-transition-guard-audit-and-rul` | completed | yes | — | yes |  | P001 |  | Transition Guard Audit And Rul |
| feature | `007-add-to-backlog-command` | completed | yes | — | yes |  |  |  | Add To Backlog Command |
| feature | `007-python-transition-control-gate` | completed | yes | — | yes |  | P001 |  | Python Transition Control Gate |
| feature | `008-update-command-references` | completed | yes | — | yes |  |  |  | Update Command References |
| feature | `008-workflowstateengine-core` | completed | yes | — | yes |  | P001 |  | Workflowstateengine Core |
| feature | `009-harden-brainstorm-workflow` | completed | yes | — | yes |  | 20260131-120900-harden-e2e-brainstorm-workflow |  | Harden Brainstorm Workflow |
| feature | `009-state-engine-mcp-tools-phase-r` | completed | yes | — | yes |  | P001 |  | State Engine Mcp Tools Phase R |
| feature | `010-backlog-to-feature-link` | completed | yes | — | yes |  | 20260131-124500-backlog-to-feature-link |  | Backlog To Feature Link |
| feature | `010-graceful-degradation-to-metajs` | completed | yes | — | yes |  | P001 |  | Graceful Degradation To Metajs |
| feature | `011-plugin-distribution-versioning` | abandoned | yes | — | yes |  | 20260131-144632-plugin-distribution-versioning |  | Plugin Distribution Versioning |
| feature | `011-reconciliation-mcp-tool` | completed | yes | — | yes |  | P001 |  | Reconciliation Mcp Tool |
| feature | `012-full-text-entity-search-mcp-to` | completed | yes | — | yes |  | P001 |  | Full Text Entity Search Mcp To |
| feature | `012-two-plugin-coexistence` | completed | yes | — | yes |  | 20260201-072847-two-plugin-coexistence |  | Two Plugin Coexistence |
| feature | `013-enhanced-brainstorm-to-prd` | completed | yes | — | yes |  | 20260202-enhanced-brainstorm-to-prd |  | Enhanced Brainstorm To Prd |
| feature | `013-entity-context-export-mcp-tool` | completed | yes | — | yes |  | P001 |  | Entity Context Export Mcp Tool |
| feature | `014-hook-migration-yolo-stopsh-and` | completed | yes | — | yes |  | P001 |  | Hook Migration Yolo Stopsh And |
| feature | `014-secretary-agent` | completed | yes | — | yes |  | 20260204-secretary-agent |  | Secretary Agent |
| feature | `015-agent-write-control` | completed | yes | — | yes |  | 20260204-agent-write-control |  | Agent Write Control |
| feature | `015-small-command-migration-finish` | completed | yes | — | yes |  | P001 |  | Small Command Migration Finish |
| feature | `016-large-command-migration-specif` | completed | yes | — | yes |  | P001 |  | Large Command Migration Specif |
| feature | `016-rca-agent` | completed | yes | — | yes |  | 20260205-002937-rca-agent |  | Rca Agent |
| feature | `017-command-cleanup-and-pseudocode` | completed | yes | — | yes |  | P001 |  | Command Cleanup And Pseudocode |
| feature | `017-evidence-grounded-phases` | completed | yes | — | yes |  | vast-mixing-lerdorf |  | Evidence Grounded Phases |
| feature | `018-structured-problem-solving` | completed | yes | — | yes |  | 20260207-structured-problem-solving |  | Structured Problem Solving |
| feature | `018-unified-iflow-ui-server-with-s` | completed | yes | — | yes |  | P001 |  | Unified Iflow Ui Server With S |
| feature | `019-game-design-skill` | completed | yes | — | yes |  | 20260207-111029-game-design-skill |  | Game Design Skill |
| feature | `020-crypto-domain-skills` | completed | yes | — | yes |  | 20260208-050000-crypto-domain-skills |  | Crypto Domain Skills |
| feature | `020-entity-list-and-detail-views` | completed | yes | — | yes |  | P001 |  | Entity List And Detail Views |
| feature | `021-lineage-dag-visualization` | completed | yes | — | yes |  | P001 |  | Lineage Dag Visualization |
| feature | `021-project-level-workflow` | completed | yes | — | yes |  | 20260210-114052-project-level-workflow |  | Project Level Workflow |
| feature | `022-context-and-review-hardening` | completed | yes | — | yes |  | 20260213-102414-artifact-context-layer |  | Context And Review Hardening |
| feature | `023-cross-project-persistent-memory` | completed | yes | — | yes |  | 20260217-011805-cross-project-persistent-memory |  | Cross Project Persistent Memory |
| feature | `024-memory-semantic-search` | completed | yes | — | yes |  |  |  | Memory Semantic Search |
| feature | `025-manual-learning-command` | completed | yes | — | yes |  | 20260221-012305-manual-learning-command |  | Manual Learning Command |
| feature | `026-test-deepening-agent` | completed | yes | — | yes |  | 20260222-015904-test-deepening-agent |  | Test Deepening Agent |
| feature | `027-prompt-intelligence-system` | completed | yes | — | yes |  | 20260224-001355-prompt-intelligence-system |  | Prompt Intelligence System |
| feature | `028-enriched-documentation-phase` | completed | yes | — | yes |  | 20260225-165342-enriched-documentation-phase |  | Enriched Documentation Phase |
| feature | `029-entity-lineage-tracking` | completed | yes | — | yes |  | 20260227-054029-entity-lineage-tracking |  | Entity Lineage Tracking |
| feature | `030-token-efficiency-improvements` | completed | yes | — | yes |  |  |  | Token Efficiency Improvements |
| feature | `031-prompt-caching-reviewer-reuse` | completed | yes | — | yes |  |  |  | Prompt Caching Reviewer Reuse |
| feature | `032-promptimize-skill-redesign` | completed | yes | — | yes |  |  |  | Promptimize Skill Redesign |
| feature | `033-comprehensive-prompt-refactor` | completed | yes | — | yes |  | 20260228-192547-comprehensive-prompt-refactor |  | Comprehensive Prompt Refactor |
| feature | `034-enforced-state-machine` | completed | yes | — | yes |  | 20260308-204500-enforced-state-machine |  | Enforced State Machine |
| feature | `035-brainstorm-backlog-state-track` | completed | yes | — | yes |  | 20260309-160000-brainstorm-backlog-state-tracking |  | Brainstorm Backlog State Track |
| feature | `035-slim-watchdog-self-mgmt` | active | yes | — | yes |  |  |  | Slim Watchdog Self Mgmt |
| feature | `036-kanban-column-lifecycle-fix` | completed | yes | — | yes |  |  |  | Kanban Column Lifecycle Fix |
| feature | `037-iflow-migration-tool` | completed | yes | — | yes |  |  |  | Iflow Migration Tool |
| feature | `038-yolo-dep-aware-selection` | completed | yes | — | yes |  |  |  | Yolo Dep Aware Selection |
| feature | `039-mcp-bootstrap-race-fix` | completed | yes | — | yes |  |  |  | Mcp Bootstrap Race Fix |
| feature | `040-complete-phase-missing-completed` | completed | yes | — | yes |  |  |  | Complete Phase Missing Completed |
| feature | `041-meta-json-guard-degradation` | completed | yes | — | yes |  |  |  | Meta Json Guard Degradation |
| feature | `042-mcp-bootstrap-python-discovery` | completed | yes | — | yes |  |  |  | Mcp Bootstrap Python Discovery |
| feature | `043-state-consistency-consolid` | completed | yes | — | yes |  |  |  | State Consistency Consolid |
| feature | `044-harden-complete-phase-timest` | completed | yes | — | yes |  |  |  | Harden Complete Phase Timest |
| feature | `045-mcp-audit-token-efficiency` | completed | yes | — | yes |  |  |  | Mcp Audit Token Efficiency |
| feature | `046-register-entity-metadata-coerce` | completed | yes | — | yes |  |  |  | Register Entity Metadata Coerce |
| feature | `047-entity-delete-api` | completed | yes | — | yes |  |  |  | Entity Delete Api |
| feature | `048-rename-pedantic-drip` | completed | yes | — | yes |  |  |  | Rename Pedantic Drip |
| feature | `049-fix-memory-search-fts5` | completed | yes | — | yes |  |  |  | Fix Memory Search Fts5 |
| feature | `051-entity-depth-fixes` | completed | yes | — | yes |  |  |  | Entity Depth Fixes |
| feature | `052-reactive-entity-consistency` | completed | yes | — | yes |  |  |  | Reactive Entity Consistency |
| feature | `053-fix-memory-server-pipefail` | completed | yes | — | yes |  |  |  | Fix Memory Server Pipefail |
| feature | `054-fix-fts-metadata-text-mismatch` | completed | yes | — | yes |  |  |  | Fix Fts Metadata Text Mismatch |
| feature | `055-memory-feedback-loop` | completed | yes | — | yes |  |  |  | Memory Feedback Loop |
| feature | `056-sqlite-write-contention-fix` | completed | yes | — | yes |  |  |  | Sqlite Write Contention Fix |
| feature | `057-memory-phase2-quality` | completed | yes | — | yes |  |  |  | Memory Phase2 Quality |
| feature | `058-sqlite-db-locking-fix` | completed | yes | — | yes |  |  |  | Sqlite Db Locking Fix |
| feature | `059-pd-doctor-diagnostic-tool` | completed | yes | — | yes |  |  |  | Pd Doctor Diagnostic Tool |
| feature | `060-pd-doctor-autofix` | completed | yes | — | yes |  |  |  | Pd Doctor Autofix |
| feature | `061-memory-phase3-feedback` | completed | yes | — | yes |  |  |  | Memory Phase3 Feedback |
| feature | `063-mcp-stale-lock-prevention` | completed | yes | — | yes |  |  |  | Mcp Stale Lock Prevention |
| feature | `064-memory-feedback-loop` | completed | yes | — | yes |  |  |  | Memory Feedback Loop |
| feature | `065-cross-project-entity-scoping` | completed | yes | — | yes |  |  |  | Cross Project Entity Scoping |
| feature | `066-stale-dependency-cleanup` | completed | yes | — | yes |  |  |  | Stale Dependency Cleanup |
| feature | `067-native-simplify` | completed | yes | — | yes |  |  |  | Native Simplify |
| feature | `068-simplify-secretary-modes` | completed | yes | — | yes |  |  |  | Simplify Secretary Modes |
| feature | `069-reviewer-token-efficiency` | completed | yes | — | yes |  |  |  | Reviewer Token Efficiency |
| feature | `070-phase-transition-summary` | completed | yes | — | yes |  | 00049 |  | Phase Transition Summary |
| feature | `071-subagent-ras` | completed | yes | — | yes |  | 20260331-074435-subagent-ras |  | Subagent Ras |
| feature | `073-yolo-relevance-gate` | completed | yes | — | yes |  | 20260401-230441-turbo-mode-phase-merge |  | Yolo Relevance Gate |
| feature | `074-unify-entity-reconciliation` | completed | yes | — | yes |  |  |  | Unify Entity Reconciliation |
| feature | `075-phase-context-accumulation` | completed | yes | — | yes |  | 20260402-081126-phase-context-accumulation |  | Phase Context Accumulation |
| feature | `076-memory-feedback-loop-hardening` | completed | yes | — | yes |  |  |  | Memory Feedback Loop Hardening |
| feature | `077-insights-driven-hardening` | completed | yes | — | yes |  | 20260406-120000-insights-driven-improvement |  | Insights Driven Hardening |
| feature | `078-cc-native-integration` | completed | yes | — | yes |  | 20260412-134500-cc-native-integration |  | Cc Native Integration |
| feature | `079-fts5-backfill-and-trigger-sync` | completed | yes | — | yes |  | P002 |  | Fts5 Backfill And Trigger Sync |
| feature | `080-influence-wiring` | completed | yes | — | yes |  | P002 |  | Influence tuning + diagnostics |
| feature | `081-mid-session-memory-refresh-hoo` | completed | yes | — | yes |  | P002 |  | Orchestrator mid-session refresh |
| feature | `082-recall-tracking-and-confidence` | completed | yes | — | yes |  | P002 |  | Confidence decay job |
| feature | `083-promote-pattern-command` | completed | yes | — | yes |  | P002 |  | /pd:promote-pattern MVP (hook/skill/agent/comman |
| feature | `084-structured-execution-data` | completed | yes | — | yes |  |  |  | Structured Execution Data |
| feature | `085-memory-server-hardening` | completed | yes | — | yes |  | 20260419-105300-memory-server-hardening |  | Memory Server Hardening |
| feature | `086-memory-server-qa-round-2` | completed | yes | — | yes |  |  |  | Memory Server Qa Round 2 |
| feature | `087-cache-and-hook-schema-hardening` | completed | yes | — | yes |  |  |  | Cache And Hook Schema Hardening |
| feature | `088-082-084-qa-hardening` | completed | yes | — | yes |  |  |  | 082 084 Qa Hardening |
| feature | `089-088-qa-round-3-hotfix` | completed | yes | — | yes |  |  |  | 088 Qa Round 3 Hotfix |
| feature | `090-089-qa-round-3-residual` | completed | yes | — | yes |  |  |  | 089 Qa Round 3 Residual |
| feature | `091-082-qa-residual-cleanup` | completed | yes | — | yes |  | 20260420-145644-082-qa-residual-hotfix |  | 082 Qa Residual Cleanup |
| feature | `092-091-qa-residual-hotfix` | completed | yes | — | yes |  | 20260420-225051-091-qa-residual-hotfix |  | 091 Qa Residual Hotfix |
| feature | `093-092-qa-residual-hotfix` | completed | yes | — | yes |  | 20260424-111837-092-qa-residual-hotfix |  | 092 Qa Residual Hotfix |
| feature | `094-pre-release-qa-gate` | completed | yes | — | yes |  | 20260429-024953-pre-release-qa-gate |  | Pre Release Qa Gate |
| feature | `095-test-hardening-iso8601` | completed | yes | — | yes |  | 20260429-110407-test-hardening-iso8601 |  | Test Hardening Iso8601 |
| feature | `096-iso8601-pattern-relocation` | completed | yes | — | yes |  | 20260429-140126-iso8601-pattern-relocation |  | Iso8601 Pattern Relocation |
| feature | `097-iso8601-test-pin-v2` | completed | yes | — | yes |  |  |  | Iso8601 Test Pin V2 |
| feature | `098-tier-doc-frontmatter-sweep` | completed | yes | — | yes |  |  |  | Tier Doc Frontmatter Sweep |
| feature | `099-retro-prevention-batch` | completed | yes | — | yes |  |  |  | Retro Prevention Batch |
| feature | `100-residual-functional-cleanup` | completed | yes | — | yes |  |  |  | Residual Functional Cleanup |
| feature | `101-memory-flywheel` | completed | yes | — | yes |  | 20260430-030912-memory-flywheel |  | Memory Flywheel |
| feature | `102-memory-capture-closure` | completed | yes | — | yes |  | 20260501-192713-memory-capture-closure |  | Memory Capture Closure |
| feature | `104-batch-b-test-hardening` | completed | yes | — | yes |  | 20260503-053000-batch-b-test-hardening |  | Batch B Test Hardening |
| feature | `105-codex-routing-coverage-extension` | completed | yes | — | yes |  |  |  | Codex Routing Coverage Extension |
| feature | `106-qa-findings-batch-cleanup` | completed | yes | — | yes |  |  |  | Qa Findings Batch Cleanup |
| feature | `107-fix-sessionstart-broken-pipe` | completed | yes | — | yes |  |  |  | Fix Sessionstart Broken Pipe |
| feature | `108-workspace-identity-foundation` | completed | yes | — | yes |  | P003 |  | Workspace Identity Foundation |
| feature | `109-polymorphic-taxonomy-and-event` | completed | yes | — | yes |  | P003 |  | Polymorphic Taxonomy and Event-Sourced State |
| feature | `112-workspace-identity-cleanup` | completed | yes | — | yes |  | P003-entity-system-redesign |  | Workspace Identity Cleanup |
| feature | `113-feature-112-qa-followups` | completed | yes | — | yes |  |  |  | Feature 112 Qa Followups |
| project | `P001` | *(NULL)* | — | yes | — |  |  |  | P001 |
| project | `P001-openclaw-gap-analysis` | active | — | yes | — |  |  |  | Openclaw Gap Analysis |
| project | `P002` | active | — | yes | — | 5 | 20260415-100000-memory-flywheel |  | memory-flywheel |
| project | `P002-memory-flywheel` | active | yes | yes | — |  |  |  | Memory Flywheel |
| project | `P003` | active | — | yes | — | 4 | 20260510-152932-entity-system-redesign |  | entity-system-redesign |
| project | `P003-entity-system-redesign` | active | yes | yes | — | 1 |  |  | Entity System Redesign |
| project | `P004-entity-db-redesign` | active | — | yes | — | 16 | 20260710-153600-entity-db-redesign |  | Entity Db Redesign |

### `/Users/terry/projects/project_illium`

| kind | entity_id | status | disp | kids | parent | tags | name |
|---|---|---|:--:|--:|---|---|---|
| brainstorm | `001-illium-target-architecture` | archived | yes | — | yes | 1 |  |  | Illium Target Architecture |

### `/Users/terry_agent`

| kind | entity_id | status | disp | kids | parent | tags | name |
|---|---|---|:--:|--:|---|---|---|
| brainstorm | `20260318-025248-three-claws-v2-protocol` | active | yes | — | yes |  |  | workspace-retired-2026-09 | 20260318-025248-three-claws-v2-protocol |
| brainstorm | `20260326-030832-openclaw-gap-analysis` | active | yes | — | yes |  |  | workspace-retired-2026-09 | 20260326-030832-openclaw-gap-analysis |
| feature | `002-assessed-mode-pipeline-fix` | archived | yes | — | yes |  |  | workspace-retired-2026-09 | Assessed Mode Pipeline Fix |
| feature | `003-oc-config-optimizer` | archived | yes | — | yes |  |  | workspace-retired-2026-09 | OCM Config Optimizer Skill |
| feature | `004-rca005-restart-loop-keychain-fix` | archived | yes | — | yes |  |  | workspace-retired-2026-09 | Rca005 Restart Loop Keychain Fix |
| feature | `008-validated-resume` | active | yes | — | yes |  | P001 | workspace-retired-2026-09 | Validated Resume |
| feature | `009-capability-gap-tracking` | planned | yes | — | yes |  | P001 | workspace-retired-2026-09 | Capability Gap Tracking |
| feature | `010-openclawjson-hash-integrity` | planned | yes | — | yes |  | P001 | workspace-retired-2026-09 | Openclawjson Hash Integrity |
| feature | `035-slim-watchdog-self-mgmt` | active | yes | — | yes |  |  | workspace-retired-2026-09 | slim-watchdog-self-mgmt |
| feature | `unnamed-b43fd0f1` | archived | yes | yes | — |  |  |  | unnamed-b43fd0f1 |
| project | `P001` | active | yes | yes | — | 12 | 20260416-000000-simplify-agent-architecture |  | agent-orchestrator |
| project | `P001-agent-orchestrator` | active | yes | yes | — | 3 |  |  | Agent Orchestrator |

