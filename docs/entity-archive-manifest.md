# Entity Archive Manifest

**Generated:** 2026-09-21 from `~/.claude/pd/entities/entities.db` (read-only).

Every entity that is **already archived** or that **lacks an `entity_display` row**. The second group is the set a clean-break archival would touch: having no display row is exactly what makes an entity "legacy", because its sequence number and slug exist only inside its `entity_id` text.

## Recovery

**Archived entities are recoverable.** Archival sets `status` and adds a tag; it never deletes. Deletion is in fact impossible for any entity here — every one has an `events` row, and `events` has a `NOT NULL` foreign key to `entities(uuid)` with no `ON DELETE`, so `delete_entity` raises `IntegrityError` unconditionally.

Verified round-trip on a snapshot:

```python
db.update_entity(type_id, status="archived")          # archive
db.add_tag(uuid, "legacy-archived-2026-09")           # mark
db.update_entity(type_id, status="open")              # restore — row intact
db.remove_tag(uuid, "legacy-archived-2026-09")
```

Restoration is a forward write through the sanctioned path, not a rollback. Two costs: each archive/restore pair leaves ~2 permanently immutable `events` rows (the table has update/delete triggers that abort), and the sequence number is never released.

**This file is the index that makes recovery possible** — it is the only record of *which* rows were legacy before the break, since after archival the marker alone cannot distinguish "archived by the break" from "already terminal".

## Summary by workspace

`live` = status `open`/`active`/`planned`/NULL. Everything else (`dropped`, `completed`, `promoted`, `abandoned`, `archived`) is finished work whose archival changes nothing anyone is using.

| Workspace | No display row | Already archived | **live, no display row** |
|---|---:|---:|---:|
| `/Users/terry/projects/cast-below` | 2 | 0 | **1** |
| `/Users/terry/projects/pedantic-drip` | 175 | 156 | **11** |
| `/Users/terry/projects/project_illium` | 0 | 1 | **0** |
| `/Users/terry_agent` | 3 | 0 | **3** |
| **Total** | **180** | **157** | **15** |

The last column is the one that matters: the rows a clean break would archive that someone might still be relying on. Everything else is already finished.

### The live rows, in full

| Workspace | kind | entity_id | status | kids | name |
|---|---|---|---|--:|---|
| `cast-below` | brainstorm | `original-ideation-prd` | *(NULL)* |  | 🎣 Cast Below |
| `pedantic-drip` | backlog | `00059` | open |  | Pre-review lint for curly-brace template place |
| `pedantic-drip` | backlog | `00060` | open |  | Structured Git Operations Reference for design |
| `pedantic-drip` | backlog | `00177` | open |  | [LOW/security] `_resolve_project_id()` emits s |
| `pedantic-drip` | backlog | `00180` | open |  | [LOW/correctness] `_detect_phase_events_drift` |
| `pedantic-drip` | backlog | `00183` | open |  | [LOW/implementation] AC-5 allowlist test missi |
| `pedantic-drip` | backlog | `00190` | open |  | [LOW/test-gap] AC-5 rejection test misses non- |
| `pedantic-drip` | project | `P001` | *(NULL)* |  | P001 |
| `pedantic-drip` | project | `P001-openclaw-gap-analysis` | active |  | Openclaw Gap Analysis |
| `pedantic-drip` | project | `P002` | active | 5 | memory-flywheel |
| `pedantic-drip` | project | `P003` | active | 4 | entity-system-redesign |
| `pedantic-drip` | project | `P004-entity-db-redesign` | active | 16 | Entity Db Redesign |
| `terry_agent` | feature | `unnamed-b43fd0f1` | *(NULL)* |  | unnamed-b43fd0f1 |
| `terry_agent` | project | `P001` | active | 12 | agent-orchestrator |
| `terry_agent` | project | `P001-agent-orchestrator` | active | 3 | Agent Orchestrator |

## Detail — every row

### `/Users/terry/projects/cast-below`

| kind | entity_id | status | disp | kids | parent | name |
|---|---|---|:--:|--:|---|---|
| brainstorm | `original-ideation-prd` | *(NULL)* | — |  |  | 🎣 Cast Below |
| project | `P001` | completed | — | 29 | 20260223-222936-world-readable | P001 |

### `/Users/terry/projects/pedantic-drip`

| kind | entity_id | status | disp | kids | parent | name |
|---|---|---|:--:|--:|---|---|
| backlog | `00008` | dropped | — |  |  | add product manager, product owner team (agents, ski |
| backlog | `00012` | dropped | — |  |  | fix the secretary AskUserQuestion formatting. The us |
| backlog | `00014` | dropped | — |  |  | Security Scanning — static rule-based security scann |
| backlog | `00015` | dropped | — |  |  | Cross-Platform Hooks — port Bash hooks to Node.js fo |
| backlog | `00017` | dropped | — |  |  | Unified Central Context Management — expand the know |
| backlog | `00018` | dropped | — |  |  | Knowledge Bank Auto-Logging — upgrade knowledge bank |
| backlog | `00020` | promoted | — |  |  | Consider renaming the plugin/repository to `pedantic |
| backlog | `00024` | dropped | — |  |  | Add `remove_entry` method to the entity registry and |
| backlog | `00026` | dropped | — |  |  | Add feature subfiles into the entity DB to facilitat |
| backlog | `00027` | promoted | — |  |  | Simplify secretary by removing aware and orchestrate |
| backlog | `00028` | dropped | — |  |  | Add software-architect, product-manager, devops-infr |
| backlog | `00029` | dropped | — |  |  | Remove project lifetime soft constraint from create- |
| backlog | `00030` | dropped | — |  |  | Fix register_entity MCP tool to correctly process me |
| backlog | `00031` | promoted | — |  |  | Handle DB write lock and concurrent write — ensure e |
| backlog | `00032` | dropped | — |  |  | Fix the workflow progression such that if a PRD is m |
| backlog | `00033` | promoted | — |  |  | Reduce diff comparison for deploying reviewers. Phas |
| backlog | `00034` | promoted | — |  |  | Update code simplifier to use Claude Code's native s |
| backlog | `00035` | dropped | — |  |  | Enrich secretary problem solving frameworks and brai |
| backlog | `00036` | dropped | — |  |  | Add system design architect and solution architect s |
| backlog | `00038` | promoted | — |  |  | Knowledge bank markdown-to-DB sync gap — markdown KB |
| backlog | `00039` | dropped | — |  |  | show-status and list-features should filter out brai |
| backlog | `00040` | promoted | — |  |  | Close entity registry status tracking gaps — project |
| backlog | `00044` | promoted | — | 1 |  | 5D stage context accumulation: Each 5D stage (discov |
| backlog | `00045` | promoted | — |  |  | Fix pd SQLite DB locking bugs: (1) MemoryDatabase mi |
| backlog | `00046` | dropped | — |  |  | Add brainstorm review cycle to brainstorm |
| backlog | `00047` | promoted | — |  |  | reconciliation_orchestrator does not detect stale bl |
| backlog | `00048` | dropped | — |  |  | release.sh: add pre-push tag existence check (git ls |
| backlog | `00049` | promoted | — | 1 |  | Phase transition summary with reviewer feedback |
| backlog | `00050` | dropped | — |  |  | Add lightweight pre-push git hook that validates .me |
| backlog | `00051` | promoted | — |  |  | Extract workflow execution data from metadata JSON b |
| backlog | `00052` | promoted | — | 1 |  | Active real-time mistake monitor — Add a PostToolUse |
| backlog | `00053` | promoted | — | 2 |  | Memory flywheel — close the self-improvement loop. C |
| backlog | `00059` | open | — |  |  | Pre-review lint for curly-brace template placeholder |
| backlog | `00060` | open | — |  |  | Structured Git Operations Reference for design phase |
| backlog | `00063` | archived | — |  |  | Entity rename tooling or convention for scope-pivote |
| backlog | `00064` | archived | — |  |  | /pd:promote-pattern classifier is too keyword-heavy. |
| backlog | `00065` | archived | — |  |  | Add "enforceability" filter to /pd:promote-pattern e |
| backlog | `00066` | archived | — |  |  | /pd:promote-pattern bare-CLI ergonomics: arg mismatc |
| backlog | `00067` | archived | — |  |  | Security: `entry_name` not sanitized before TD-8 HTM |
| backlog | `00068` | archived | — |  |  | Security: `~/.claude/pd/memory/influence-debug.log`  |
| backlog | `00069` | archived | — |  |  | Operability: influence-debug.log has no size cap or  |
| backlog | `00070` | archived | — |  |  | Code quality: `_warn_and_default`/`_ranker_warn_and_ |
| backlog | `00071` | archived | — |  |  | Code quality: `_emit_influence_diagnostic` log schem |
| backlog | `00072` | archived | — |  |  | Code quality: MCP wrapper `record_influence_by_conte |
| backlog | `00073` | archived | — |  |  | Code quality: hook generator test-script stubs for ` |
| backlog | `00074` | archived | — |  |  | Testability: AC-7 / AC-7b / AC-11 grep assertions fr |
| backlog | `00075` | archived | — |  |  | No timeout cap when gtimeout/timeout absent in sessi |
| backlog | `00076` | archived | — |  |  | Equal decay thresholds + rapid sequential calls = do |
| backlog | `00077` | archived | — |  |  | AC-22 test covers file-missing only; not SyntaxError |
| backlog | `00078` | archived | — |  |  | `_select_candidates` accesses `db._conn` directly fo |
| backlog | `00079` | archived | — |  |  | `updated_at IS NULL` guard in `_execute_chunk` SQL i |
| backlog | `00080` | archived | — |  |  | `__unknown__` project_id sentinel from `record_backw |
| backlog | `00081` | archived | — |  |  | Unknown `query_type` in `query_phase_analytics` retu |
| backlog | `00082` | archived | — |  |  | Missing negative tests: CHECK constraint rejection f |
| backlog | `00083` | archived | — |  |  | `_compute_durations` silently drops timestamp pairs  |
| backlog | `00084` | archived | — |  |  | AC-16 only tests transition_phase failure resilience |
| backlog | `00085` | archived | — |  |  | **[HIGH/security]** ReDoS in... |
| backlog | `00086` | archived | — |  |  | **[HIGH/concurrency]** Async coroutine umask race in |
| backlog | `00087` | archived | — |  |  | **[HIGH/testability]** FR-6 caller-passed threshold  |
| backlog | `00088` | archived | — |  |  | **[MED/correctness]** Missing JSON escaping in... |
| backlog | `00089` | dropped | — |  |  | **[MED/quality]** Rotation failure permanently silen |
| backlog | `00090` | dropped | — |  |  | **[MED/quality]** Pytest global-state pollution — `_ |
| backlog | `00091` | dropped | — |  |  | **[MED/quality]** FR-4 completeness gap — `cfg.get(' |
| backlog | `00092` | dropped | — |  |  | **[MED/testability]** 10 MB rotation boundary off-by |
| backlog | `00093` | dropped | — |  |  | **[MED/testability]** Shell-vs-Python regex semantic |
| backlog | `00094` | dropped | — |  |  | **[LOW/observation]** SC-9(a) source grep fragile to |
| backlog | `00095` | dropped | — |  |  | **[HIGH/security]** Python heredoc injection in... |
| backlog | `00096` | dropped | — |  |  | **[HIGH/security]** OverflowError escape from `timed |
| backlog | `00097` | dropped | — |  |  | **[HIGH/security]** Symlink-clobber on `influence-de |
| backlog | `00098` | dropped | — |  |  | **[HIGH/quality]** `_resolve_int_config` clamp path  |
| backlog | `00099` | dropped | — |  |  | **[HIGH/correctness]** isoformat() vs strftime() tim |
| backlog | `00100` | dropped | — |  |  | **[HIGH/implementation]** AC-11 spec requires stderr |
| backlog | `00101` | dropped | — |  |  | **[HIGH/implementation]** AC-10 spec text still says |
| backlog | `00102` | dropped | — |  |  | **[MED/security]** `memory_decay_*` config keys miss |
| backlog | `00103` | dropped | — |  |  | **[MED/security]** CLI `--project-root` in `maintena |
| backlog | `00104` | dropped | — |  |  | **[MED/quality]** Test file `test_maintenance.py` ha |
| backlog | `00105` | dropped | — |  |  | **[MED/quality]** Duplicate `_warn_and_default` / `_ |
| backlog | `00106` | dropped | — |  |  | **[MED/quality]** Dead `now_iso` parameter in `_sele |
| backlog | `00107` | dropped | — |  |  | **[MED/security]** Unbounded SELECT in `_select_cand |
| backlog | `00108` | dropped | — |  |  | **[MED/implementation]** AC-20b-1/20b-2 spec targets |
| backlog | `00109` | dropped | — |  |  | **[MED/implementation]** FR-2 spec NULL-branch text  |
| backlog | `00110` | dropped | — |  |  | **[MED/implementation]** Retro EQP file `agent_sandb |
| backlog | `00111` | dropped | — |  |  | **[MED/quality]** Module-level `NOW = datetime(...)` |
| backlog | `00112` | dropped | — |  |  | **[MED/security]** `run_memory_decay` in `session-st |
| backlog | `00113` | dropped | — |  |  | **[MED/testability]** Boundary-equality (`last_recal |
| backlog | `00114` | dropped | — |  |  | **[MED/testability]** Tz-naive `now` handling silent |
| backlog | `00115` | dropped | — |  |  | **[MED/testability]** Zero cross-feature integration |
| backlog | `00116` | dropped | — |  |  | **[LOW/testability]** Additional gaps: empty-DB / si |
| backlog | `00117` | dropped | — |  |  | **[HIGH/security]** Cross-project data leakage in `q |
| backlog | `00118` | dropped | — |  |  | **[HIGH/security]** Migration 10 concurrent-invocati |
| backlog | `00119` | dropped | — |  |  | **[HIGH/security]** `record_backward_event` accepts  |
| backlog | `00120` | dropped | — |  |  | **[HIGH/quality]** Both `record_backward_event` and  |
| backlog | `00121` | dropped | — |  |  | **[HIGH/quality]** `query_phase_events` uses `SELECT |
| backlog | `00122` | dropped | — |  |  | **[HIGH/implementation]** `SKILL.md:402-412` calls ` |
| backlog | `00123` | dropped | — |  |  | **[HIGH/implementation]** `_compute_durations:1752`  |
| backlog | `00124` | dropped | — |  |  | **[MED/correctness]** Dual-write `insert_phase_event |
| backlog | `00125` | dropped | — |  |  | **[MED/security]** Unbounded JSON round-trip on `rev |
| backlog | `00126` | dropped | — |  |  | **[MED/security]** Raw `str(e)` exception leak in `r |
| backlog | `00127` | dropped | — |  |  | **[MED/security]** Migration 10 backfill (`database. |
| backlog | `00128` | dropped | — |  |  | **[MED/quality]** `_compute_durations:1737` defers s |
| backlog | `00129` | dropped | — |  |  | **[MED/quality]** Migration 10 top-level `except Exc |
| backlog | `00130` | dropped | — |  |  | **[MED/quality]** `test_workflow_state_server.py:807 |
| backlog | `00131` | dropped | — |  |  | **[MED/implementation]** AC-19 test only asserts key |
| backlog | `00132` | dropped | — |  |  | **[MED/implementation]** iteration_summary applies l |
| backlog | `00133` | dropped | — |  |  | **[LOW/suggestion]** `phase_duration`/`backward_freq |
| backlog | `00134` | dropped | — |  |  | **[HIGH/testability]** `insert_phase_event` uncondit |
| backlog | `00135` | dropped | — |  |  | **[HIGH/testability]** Reconciliation is `phase_even |
| backlog | `00136` | dropped | — |  |  | **[MED/testability]** Additional gaps: `.meta.json`  |
| backlog | `00137` | dropped | — |  |  | **[MED/process]** Feature 084 has no `retro.md` desp |
| backlog | `00138` | dropped | — |  |  | Deferred 082/084 test-gap sub-items not addressed by |
| backlog | `00139` | dropped | — |  |  | [HIGH/security] `_coerce_bool` at `config.py:59` is  |
| backlog | `00140` | dropped | — |  |  | [HIGH/security] `execute_test_sql_for_testing`, `fet |
| backlog | `00141` | dropped | — |  |  | [HIGH/correctness] `_iso_utc(dt)` at `maintenance.py |
| backlog | `00142` | dropped | — |  |  | [HIGH/correctness] Migration 10 at `database.py:1411 |
| backlog | `00143` | dropped | — |  |  | [HIGH/security] `query_phase_analytics` at `workflow |
| backlog | `00144` | dropped | — |  |  | [HIGH/correctness] `execute_test_sql_for_testing` at |
| backlog | `00145` | dropped | — |  |  | [HIGH/spec-drift] AC-23 LOC target violated. Baselin |
| backlog | `00146` | dropped | — |  |  | [HIGH/correctness] Bundle L `_detect_phase_events_dr |
| backlog | `00147` | dropped | — |  |  | [MED/consistency] `backward_frequency` query at `wor |
| backlog | `00148` | dropped | — |  |  | [MED/duplication] `refresh.py:180` formats timestamp |
| backlog | `00149` | dropped | — |  |  | [MED/quality] `_TRUE_VALUES`/`_FALSE_VALUES` module- |
| backlog | `00150` | dropped | — |  |  | [MED/performance] `_detect_phase_events_drift` N+1 q |
| backlog | `00151` | dropped | — |  |  | [MED/correctness] `entity.get('project_id') or '__un |
| backlog | `00152` | dropped | — |  |  | [MED/consistency] Migration 10 writes schema_version |
| backlog | `00153` | dropped | — |  |  | [MED/correctness] PATH pinning in `run_memory_decay` |
| backlog | `00154` | dropped | — |  |  | [MED/security] O_NOFOLLOW + fchmod log-open has TOCT |
| backlog | `00155` | dropped | — |  |  | [MED/testability] `_warn_and_default` module-state ( |
| backlog | `00156` | dropped | — |  |  | [MED/spec-drift] AC-10 `strftime` grep-verification  |
| backlog | `00157` | dropped | — |  |  | [MED/spec-drift] AC-34b targets function name `_coer |
| backlog | `00158` | dropped | — |  |  | [MED/spec-drift] AC-22 "line-for-line identical" not |
| backlog | `00159` | dropped | — |  |  | [MED/quality] `plugins/pd/mcp/test_workflow_state_se |
| backlog | `00160` | dropped | — |  |  | [MED/testability] `_coerce_bool` tested only for `'F |
| backlog | `00161` | dropped | — |  |  | [MED/testability] `_iso_utc(dt)` direct unit test mi |
| backlog | `00162` | dropped | — |  |  | [MED/testability] `scan_limit=0` edge untested. Prod |
| backlog | `00163` | dropped | — |  |  | [MED/testability] `run_memory_decay` Python-subproce |
| backlog | `00164` | dropped | — |  |  | [MED/testability] `record_backward_event` server-sid |
| backlog | `00165` | dropped | — |  |  | [MED/testability] Dual-write retry semantics after f |
| backlog | `00166` | dropped | — |  |  | [MED/testability] Migration-10 concurrent with live  |
| backlog | `00167` | dropped | — |  |  | [MED/testability] `reconcile_check → manual-fix → re |
| backlog | `00168` | dropped | — |  |  | [MED/testability] `_warn_unknown_keys` dedup behavio |
| backlog | `00169` | dropped | — |  |  | [MED/testability] `_detect_phase_events_drift` error |
| backlog | `00170` | dropped | — |  |  | [MED/testability] `reviewer_notes` boundary at MCP e |
| backlog | `00171` | dropped | — |  |  | [MED/testability] Bundle L ↔ Bundle E integration un |
| backlog | `00172` | dropped | — |  |  | [HIGH/implementation] AC-21 `test_decay_python_subpr |
| backlog | `00173` | dropped | — |  |  | [MED/security] `_assert_testing_context()` at... |
| backlog | `00174` | dropped | — |  |  | [MED/correctness] Migration 10 schema_version crash  |
| backlog | `00175` | dropped | — |  |  | [MED/correctness] `query_phase_events_bulk(event_typ |
| backlog | `00176` | dropped | — |  |  | [MED/test-drift] AC-22 test... |
| backlog | `00177` | open | — |  |  | [LOW/security] `_resolve_project_id()` emits stderr  |
| backlog | `00178` | dropped | — |  |  | [LOW/security] `reset_warning_state()` public in bot |
| backlog | `00179` | dropped | — |  |  | [LOW/security] `trap 'export PATH="$PATH_OLD"' RETUR |
| backlog | `00180` | open | — |  |  | [LOW/correctness] `_detect_phase_events_drift` with  |
| backlog | `00181` | dropped | — |  |  | [LOW/quality] `_coerce_bool` int-literal branches (c |
| backlog | `00182` | dropped | — |  |  | [LOW/quality] Test parametrize sentinel `"default"`  |
| backlog | `00183` | open | — |  |  | [LOW/implementation] AC-5 allowlist test missing exp |
| backlog | `00184` | dropped | — |  |  | [LOW/implementation] AC-7 `test_influence_log_refuse |
| backlog | `00185` | dropped | — |  |  | [LOW/implementation] AC-10... |
| backlog | `00186` | dropped | — |  |  | [LOW/implementation] AC-1 `test_coerce_bool_routed_f |
| backlog | `00187` | dropped | — |  |  | [LOW/test-gap] AC-28 boundary test misses compound-t |
| backlog | `00188` | dropped | — |  |  | [LOW/test-gap] AC-18 parametrize omits load-bearing  |
| backlog | `00189` | dropped | — |  |  | [LOW/test-gap] AC-7 TOCTOU fd-fstat defense at `main |
| backlog | `00190` | open | — |  |  | [LOW/test-gap] AC-5 rejection test misses non-string |
| backlog | `00191` | dropped | — |  |  | [LOW/test-gap] Fixture asymmetry: `test_refresh.py`  |
| backlog | `00217` | promoted | — | 1 |  | Backlog #00217 |
| backlog | `00246` | promoted | — | 1 |  | Backlog #00246 |
| backlog | `00277` | promoted | — | 1 |  | Backlog #00277 |
| brainstorm | `20260324-000000-causal-inference-training` | archived | yes |  |  | 20260324-000000-causal-inference-training |
| brainstorm | `original_claude_code_special_force_design` | abandoned | — |  |  | original_claude_code_special_force_design |
| brainstorm | `vast-mixing-lerdorf` | promoted | — | 1 |  | External: /Users/terry/.claude/plans/vast-mixing-ler |
| feature | `001-entity-uuid-primary-key-migrat` | archived | yes |  | P001 | Entity Uuid Primary Key Migrat |
| feature | `002-change-workflow-ordering` | archived | yes |  |  | Change Workflow Ordering |
| feature | `002-markdown-entity-file-header-sc` | archived | yes |  | P001 | Markdown Entity File Header Sc |
| feature | `003-bidirectional-uuid-sync-betwee` | archived | yes |  | P001 | Bidirectional Uuid Sync Betwee |
| feature | `003-workflow-orchestration` | archived | yes |  |  | Workflow Orchestration |
| feature | `004-status-taxonomy-design-and-sch` | archived | yes |  | P001 | Status Taxonomy Design And Sch |
| feature | `004-update-documentation-step` | archived | yes |  |  | Update Documentation Step |
| feature | `005-make-specs-executable` | archived | yes |  |  | Make Specs Executable |
| feature | `005-workflowphases-table-with-dual` | archived | yes |  | P001 | Workflowphases Table With Dual |
| feature | `006-retro-before-cleanup` | archived | yes |  |  | Retro Before Cleanup |
| feature | `006-transition-guard-audit-and-rul` | archived | yes |  | P001 | Transition Guard Audit And Rul |
| feature | `007-add-to-backlog-command` | archived | yes |  |  | Add To Backlog Command |
| feature | `007-python-transition-control-gate` | archived | yes |  | P001 | Python Transition Control Gate |
| feature | `008-update-command-references` | archived | yes |  |  | Update Command References |
| feature | `008-workflowstateengine-core` | archived | yes |  | P001 | Workflowstateengine Core |
| feature | `009-harden-brainstorm-workflow` | archived | yes |  | 20260131-120900-harden-e2e-brainstorm-workflow | Harden Brainstorm Workflow |
| feature | `009-state-engine-mcp-tools-phase-r` | archived | yes |  | P001 | State Engine Mcp Tools Phase R |
| feature | `010-backlog-to-feature-link` | archived | yes |  | 20260131-124500-backlog-to-feature-link | Backlog To Feature Link |
| feature | `010-graceful-degradation-to-metajs` | archived | yes |  | P001 | Graceful Degradation To Metajs |
| feature | `011-plugin-distribution-versioning` | archived | yes |  | 20260131-144632-plugin-distribution-versioning | Plugin Distribution Versioning |
| feature | `011-reconciliation-mcp-tool` | archived | yes |  | P001 | Reconciliation Mcp Tool |
| feature | `012-full-text-entity-search-mcp-to` | archived | yes |  | P001 | Full Text Entity Search Mcp To |
| feature | `012-two-plugin-coexistence` | archived | yes |  | 20260201-072847-two-plugin-coexistence | Two Plugin Coexistence |
| feature | `013-enhanced-brainstorm-to-prd` | archived | yes |  | 20260202-enhanced-brainstorm-to-prd | Enhanced Brainstorm To Prd |
| feature | `013-entity-context-export-mcp-tool` | archived | yes |  | P001 | Entity Context Export Mcp Tool |
| feature | `014-hook-migration-yolo-stopsh-and` | archived | yes |  | P001 | Hook Migration Yolo Stopsh And |
| feature | `014-secretary-agent` | archived | yes |  | 20260204-secretary-agent | Secretary Agent |
| feature | `015-agent-write-control` | archived | yes |  | 20260204-agent-write-control | Agent Write Control |
| feature | `015-small-command-migration-finish` | archived | yes |  | P001 | Small Command Migration Finish |
| feature | `016-large-command-migration-specif` | archived | yes |  | P001 | Large Command Migration Specif |
| feature | `016-rca-agent` | archived | yes |  | 20260205-002937-rca-agent | Rca Agent |
| feature | `017-command-cleanup-and-pseudocode` | archived | yes |  | P001 | Command Cleanup And Pseudocode |
| feature | `017-evidence-grounded-phases` | archived | yes |  | vast-mixing-lerdorf | Evidence Grounded Phases |
| feature | `018-structured-problem-solving` | archived | yes |  | 20260207-structured-problem-solving | Structured Problem Solving |
| feature | `018-unified-iflow-ui-server-with-s` | archived | yes |  | P001 | Unified Iflow Ui Server With S |
| feature | `019-game-design-skill` | archived | yes |  | 20260207-111029-game-design-skill | Game Design Skill |
| feature | `020-crypto-domain-skills` | archived | yes |  | 20260208-050000-crypto-domain-skills | Crypto Domain Skills |
| feature | `020-entity-list-and-detail-views` | archived | yes |  | P001 | Entity List And Detail Views |
| feature | `021-lineage-dag-visualization` | archived | yes |  | P001 | Lineage Dag Visualization |
| feature | `021-project-level-workflow` | archived | yes |  | 20260210-114052-project-level-workflow | Project Level Workflow |
| feature | `022-context-and-review-hardening` | archived | yes |  | 20260213-102414-artifact-context-layer | Context And Review Hardening |
| feature | `023-cross-project-persistent-memory` | archived | yes |  | 20260217-011805-cross-project-persistent-memory | Cross Project Persistent Memory |
| feature | `024-memory-semantic-search` | archived | yes |  |  | Memory Semantic Search |
| feature | `025-manual-learning-command` | archived | yes |  | 20260221-012305-manual-learning-command | Manual Learning Command |
| feature | `026-test-deepening-agent` | archived | yes |  | 20260222-015904-test-deepening-agent | Test Deepening Agent |
| feature | `027-prompt-intelligence-system` | archived | yes |  | 20260224-001355-prompt-intelligence-system | Prompt Intelligence System |
| feature | `028-enriched-documentation-phase` | archived | yes |  | 20260225-165342-enriched-documentation-phase | Enriched Documentation Phase |
| feature | `029-entity-lineage-tracking` | archived | yes |  | 20260227-054029-entity-lineage-tracking | Entity Lineage Tracking |
| feature | `030-token-efficiency-improvements` | archived | yes |  |  | Token Efficiency Improvements |
| feature | `031-prompt-caching-reviewer-reuse` | archived | yes |  |  | Prompt Caching Reviewer Reuse |
| feature | `032-promptimize-skill-redesign` | archived | yes |  |  | Promptimize Skill Redesign |
| feature | `033-comprehensive-prompt-refactor` | archived | yes |  | 20260228-192547-comprehensive-prompt-refactor | Comprehensive Prompt Refactor |
| feature | `034-enforced-state-machine` | archived | yes |  | 20260308-204500-enforced-state-machine | Enforced State Machine |
| feature | `035-brainstorm-backlog-state-track` | archived | yes |  | 20260309-160000-brainstorm-backlog-state-tracking | Brainstorm Backlog State Track |
| feature | `035-slim-watchdog-self-mgmt` | archived | yes |  |  | Slim Watchdog Self Mgmt |
| feature | `036-kanban-column-lifecycle-fix` | archived | yes |  |  | Kanban Column Lifecycle Fix |
| feature | `037-iflow-migration-tool` | archived | yes |  |  | Iflow Migration Tool |
| feature | `038-yolo-dep-aware-selection` | archived | yes |  |  | Yolo Dep Aware Selection |
| feature | `039-mcp-bootstrap-race-fix` | archived | yes |  |  | Mcp Bootstrap Race Fix |
| feature | `040-complete-phase-missing-completed` | archived | yes |  |  | Complete Phase Missing Completed |
| feature | `041-meta-json-guard-degradation` | archived | yes |  |  | Meta Json Guard Degradation |
| feature | `042-mcp-bootstrap-python-discovery` | archived | yes |  |  | Mcp Bootstrap Python Discovery |
| feature | `043-state-consistency-consolid` | archived | yes |  |  | State Consistency Consolid |
| feature | `044-harden-complete-phase-timest` | archived | yes |  |  | Harden Complete Phase Timest |
| feature | `045-mcp-audit-token-efficiency` | archived | yes |  |  | Mcp Audit Token Efficiency |
| feature | `046-register-entity-metadata-coerce` | archived | yes |  |  | Register Entity Metadata Coerce |
| feature | `047-entity-delete-api` | archived | yes |  |  | Entity Delete Api |
| feature | `048-rename-pedantic-drip` | archived | yes |  |  | Rename Pedantic Drip |
| feature | `049-fix-memory-search-fts5` | archived | yes |  |  | Fix Memory Search Fts5 |
| feature | `051-entity-depth-fixes` | archived | yes |  |  | Entity Depth Fixes |
| feature | `052-reactive-entity-consistency` | archived | yes |  |  | Reactive Entity Consistency |
| feature | `053-fix-memory-server-pipefail` | archived | yes |  |  | Fix Memory Server Pipefail |
| feature | `054-fix-fts-metadata-text-mismatch` | archived | yes |  |  | Fix Fts Metadata Text Mismatch |
| feature | `055-memory-feedback-loop` | archived | yes |  |  | Memory Feedback Loop |
| feature | `056-sqlite-write-contention-fix` | archived | yes |  |  | Sqlite Write Contention Fix |
| feature | `057-memory-phase2-quality` | archived | yes |  |  | Memory Phase2 Quality |
| feature | `058-sqlite-db-locking-fix` | archived | yes |  |  | Sqlite Db Locking Fix |
| feature | `059-pd-doctor-diagnostic-tool` | archived | yes |  |  | Pd Doctor Diagnostic Tool |
| feature | `060-pd-doctor-autofix` | archived | yes |  |  | Pd Doctor Autofix |
| feature | `061-memory-phase3-feedback` | archived | yes |  |  | Memory Phase3 Feedback |
| feature | `063-mcp-stale-lock-prevention` | archived | yes |  |  | Mcp Stale Lock Prevention |
| feature | `064-memory-feedback-loop` | archived | yes |  |  | Memory Feedback Loop |
| feature | `065-cross-project-entity-scoping` | archived | yes |  |  | Cross Project Entity Scoping |
| feature | `066-stale-dependency-cleanup` | archived | yes |  |  | Stale Dependency Cleanup |
| feature | `067-native-simplify` | archived | yes |  |  | Native Simplify |
| feature | `068-simplify-secretary-modes` | archived | yes |  |  | Simplify Secretary Modes |
| feature | `069-reviewer-token-efficiency` | archived | yes |  |  | Reviewer Token Efficiency |
| feature | `070-phase-transition-summary` | archived | yes |  | 00049 | Phase Transition Summary |
| feature | `071-subagent-ras` | archived | yes |  | 20260331-074435-subagent-ras | Subagent Ras |
| feature | `073-yolo-relevance-gate` | archived | yes |  | 20260401-230441-turbo-mode-phase-merge | Yolo Relevance Gate |
| feature | `074-unify-entity-reconciliation` | archived | yes |  |  | Unify Entity Reconciliation |
| feature | `075-phase-context-accumulation` | archived | yes |  | 20260402-081126-phase-context-accumulation | Phase Context Accumulation |
| feature | `076-memory-feedback-loop-hardening` | archived | yes |  |  | Memory Feedback Loop Hardening |
| feature | `077-insights-driven-hardening` | archived | yes |  | 20260406-120000-insights-driven-improvement | Insights Driven Hardening |
| feature | `078-cc-native-integration` | archived | yes |  | 20260412-134500-cc-native-integration | Cc Native Integration |
| feature | `079-fts5-backfill-and-trigger-sync` | archived | yes |  | P002 | Fts5 Backfill And Trigger Sync |
| feature | `080-influence-wiring` | archived | yes |  | P002 | Influence tuning + diagnostics |
| feature | `081-mid-session-memory-refresh-hoo` | archived | yes |  | P002 | Orchestrator mid-session refresh |
| feature | `082-recall-tracking-and-confidence` | archived | yes |  | P002 | Confidence decay job |
| feature | `083-promote-pattern-command` | archived | yes |  | P002 | /pd:promote-pattern MVP (hook/skill/agent/command ta |
| feature | `084-structured-execution-data` | archived | yes |  |  | Structured Execution Data |
| feature | `085-memory-server-hardening` | archived | yes |  | 20260419-105300-memory-server-hardening | Memory Server Hardening |
| feature | `086-memory-server-qa-round-2` | archived | yes |  |  | Memory Server Qa Round 2 |
| feature | `087-cache-and-hook-schema-hardening` | archived | yes |  |  | Cache And Hook Schema Hardening |
| feature | `088-082-084-qa-hardening` | archived | yes |  |  | 082 084 Qa Hardening |
| feature | `089-088-qa-round-3-hotfix` | archived | yes |  |  | 088 Qa Round 3 Hotfix |
| feature | `090-089-qa-round-3-residual` | archived | yes |  |  | 089 Qa Round 3 Residual |
| feature | `091-082-qa-residual-cleanup` | archived | yes |  | 20260420-145644-082-qa-residual-hotfix | 082 Qa Residual Cleanup |
| feature | `092-091-qa-residual-hotfix` | archived | yes |  | 20260420-225051-091-qa-residual-hotfix | 091 Qa Residual Hotfix |
| feature | `093-092-qa-residual-hotfix` | archived | yes |  | 20260424-111837-092-qa-residual-hotfix | 092 Qa Residual Hotfix |
| feature | `094-pre-release-qa-gate` | archived | yes |  | 20260429-024953-pre-release-qa-gate | Pre Release Qa Gate |
| feature | `095-test-hardening-iso8601` | archived | yes |  | 20260429-110407-test-hardening-iso8601 | Test Hardening Iso8601 |
| feature | `096-iso8601-pattern-relocation` | archived | yes |  | 20260429-140126-iso8601-pattern-relocation | Iso8601 Pattern Relocation |
| feature | `097-iso8601-test-pin-v2` | archived | yes |  |  | Iso8601 Test Pin V2 |
| feature | `098-tier-doc-frontmatter-sweep` | archived | yes |  |  | Tier Doc Frontmatter Sweep |
| feature | `099-retro-prevention-batch` | archived | yes |  |  | Retro Prevention Batch |
| feature | `100-residual-functional-cleanup` | archived | yes |  |  | Residual Functional Cleanup |
| feature | `101-memory-flywheel` | archived | yes |  | 20260430-030912-memory-flywheel | Memory Flywheel |
| feature | `102-memory-capture-closure` | archived | yes |  | 20260501-192713-memory-capture-closure | Memory Capture Closure |
| feature | `104-batch-b-test-hardening` | archived | yes |  | 20260503-053000-batch-b-test-hardening | Batch B Test Hardening |
| feature | `105-codex-routing-coverage-extension` | archived | yes |  |  | Codex Routing Coverage Extension |
| feature | `106-qa-findings-batch-cleanup` | archived | yes |  |  | Qa Findings Batch Cleanup |
| feature | `107-fix-sessionstart-broken-pipe` | archived | yes |  |  | Fix Sessionstart Broken Pipe |
| feature | `108-workspace-identity-foundation` | archived | yes |  | P003 | Workspace Identity Foundation |
| feature | `109-polymorphic-taxonomy-and-event` | archived | yes |  | P003 | Polymorphic Taxonomy and Event-Sourced State |
| feature | `112-workspace-identity-cleanup` | archived | yes |  | P003-entity-system-redesign | Workspace Identity Cleanup |
| feature | `113-feature-112-qa-followups` | archived | yes |  |  | Feature 112 Qa Followups |
| project | `P001` | *(NULL)* | — |  |  | P001 |
| project | `P001-openclaw-gap-analysis` | active | — |  |  | Openclaw Gap Analysis |
| project | `P002` | active | — | 5 | 20260415-100000-memory-flywheel | memory-flywheel |
| project | `P002-memory-flywheel` | archived | — |  |  | Memory Flywheel |
| project | `P003` | active | — | 4 | 20260510-152932-entity-system-redesign | entity-system-redesign |
| project | `P003-entity-system-redesign` | archived | — | 1 |  | Entity System Redesign |
| project | `P004-entity-db-redesign` | active | — | 16 | 20260710-153600-entity-db-redesign | Entity Db Redesign |

### `/Users/terry/projects/project_illium`

| kind | entity_id | status | disp | kids | parent | name |
|---|---|---|:--:|--:|---|---|
| brainstorm | `001-illium-target-architecture` | archived | yes | 1 |  | Illium Target Architecture |

### `/Users/terry_agent`

| kind | entity_id | status | disp | kids | parent | name |
|---|---|---|:--:|--:|---|---|
| feature | `unnamed-b43fd0f1` | *(NULL)* | — |  |  | unnamed-b43fd0f1 |
| project | `P001` | active | — | 12 | 20260416-000000-simplify-agent-architecture | agent-orchestrator |
| project | `P001-agent-orchestrator` | active | — | 3 |  | Agent Orchestrator |

## Regenerating

```sql
SELECT w.project_root, e.kind, e.entity_id, e.status, e.name,
       (d.uuid IS NULL) AS no_display_row
FROM entities e
JOIN workspaces w ON w.uuid = e.workspace_uuid
LEFT JOIN entity_display d ON d.uuid = e.uuid
WHERE d.uuid IS NULL OR e.status = 'archived'
ORDER BY w.project_root, e.kind, e.entity_id;
```
