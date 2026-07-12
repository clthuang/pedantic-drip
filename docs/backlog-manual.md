# Backlog (manual register)

Durable, git-tracked MANUAL backlog. Distinct from `docs/backlog.md` (the
gitignored DB projection, `.gitignore:69`) because the entity-DB backlog
write path is silently lossy — see #060. This file is the source of truth
until #060 is diagnosed / the P004 cutover (feature 132) restores a
reliable DB path; entries then migrate into the DB and this file retires.

## Open

- **#054 — Feature-132 cutover checklist items** *(P004, source: feature 118 QA)*
  At cutover, decide: (a) what replaces the dropped-UNIQUE reliance on human-readable
  fields (v17 consumers that leaned on uniqueness must be enumerated); (b) whether
  mixed uuid4/uuid7 populations get re-minted at backfill or grandfathered;
  (c) *(added at 121 spec, 2026-07-11)* rewire `create-project.md:26-31`'s `P{NNN}`
  filesystem scan to the atomic allocator — deferred from 121 because the v1 bootstrap
  regex `^(\d+)` (database.py:9368) is blind to `P`-leading project ids and would
  deterministically re-mint P001; 132's backfill seeds v2 sequences for every kind
  from the census, so the rewire is a one-line command edit at cutover. Also honor
  121's D-5 lean: the live `allocate_entity_id` MCP tool rejects `entity_type="project"`
  until this lands — remove that guard in the same change.

- **#055 — MCP workflow-state phase-events write path broken (silent data loss)** *(source: feature 118 QA)*
  Every `complete_phase`/`transition_phase` intermittently reports
  `phase_events_write_failed: true` — projections (.meta.json) are correct but the
  `phase_events` rows are lost. **Consequence measured at feature 119's retro:** under
  the projection-lag workaround (transition called at phase END right before complete),
  `.meta.json` started_at collapses into completed_at (11-15s deltas across all four
  phases) — per-phase timing is unrecoverable for retros until this is fixed. Root fix
  is the events-write path, not skill edits. The P004 track (119/120/132) replaces this
  machinery wholesale; fix-forward there rather than patching v1.

- **#056 — complete_phase reviewer_notes ergonomics** *(source: feature 118 QA)*
  `reviewer_notes` requires a doubly-JSON-encoded string (`"[\"...\"]"`) because the
  harness re-parses JSON-shaped args; a plain list is rejected by pydantic. Accept a
  native list (or document the contract in the tool description).
  *(121 retro addendum, 2026-07-11):* `transition_phase`'s `skipped_phases: str | None`
  is the same class — the transport JSON-parses the doubly-encoded string back into a
  list, pydantic rejects it, and NO string form reaches the server intact. Live
  workaround: omit the param entirely; guard G-23 self-detects skipped phases and
  emits a soft warn (verified during 121's specify transition). Fix both params together.

- **#057 — Reviewer severity rubric: split BLOCKER by failure signature** *(source: feature 129 retro Tune 1; owner: workflow-rebuild track)*
  4 of 9 artifact-phase blockers were self-signaling (collection ImportError,
  missing-default TypeError — would fail loudly at the next task's own Verify step);
  5 were silent (dead code, dropped coverage, contradicted contract). Both consume
  identical iteration budget under the 3-cap. Proposal: self-signaling issues downgrade
  to WARNING; BLOCKER reserved for ship-undetected classes. Confidence: medium
  (single-feature sample).

- **#058 — Skip confirmatory phase-gate second rounds when round-1's fix is a small quoted diff** *(source: feature 129 retro Tune 5; owner: workflow-rebuild track)*
  18 reviewer/gate dispatches on 129; the only pure zero-finding rerun was design's
  second phase-gate round reconfirming an already-closed blocker. Proposal: allow the
  orchestrator to close a phase gate without a second dispatch when round-1's sole
  blocker fix is mechanically verifiable inline. Do NOT extend to artifact skeptic
  reviewers (8 of their 9 blockers were real). Feature 119 note: every gate converged
  in 1 round — proposal untested there; weak n=2 signal that the DESIGN gate
  specifically is the lowest-yield dispatch.

- **#059 — Stabilize TestMigration11ConcurrentRunners fork-race flake** *(source: feature 129 QA gate T1, MED)*
  `test_database.py` `test_migration_11_concurrent_runners`: pre-existing flake
  (develop ~5% isolated-rerun fail) measurably worse on the 129 branch (12/19 targeted
  stress reruns; `database is locked` from the forked child's `PRAGMA journal_mode=WAL`
  racing the parent). Test + SUT byte-identical to develop — likely fork-timing shift
  from file growth. Full suite stable (2× identical 3423-pass runs). Options:
  lock-retry/backoff around the race fixture's opens, or serial/isolated marking.
  Watch post-merge CI red rate. (Feature 119's new 30-trial bootstrap harness is a
  DIFFERENT, lock-serialized path — passes 30/30 deterministically.)

- **#060 — Entity-registry register_entity silently loses backlog registrations** *(source: feature 119 finish phase, 2026-07-11)*
  `register_entity(entity_type="backlog", ...)` returned success
  ("Registered: backlog:057-reviewer-severity-rubric" etc. for 057/058/059; same for
  054/055/056 in the prior session) but NO row persisted — invisible to `get_entity`,
  `search_entities` (any project scope), AND raw sqlite over
  `~/.claude/pd/entities/entities.db` (WAL included; 552 entities, zero matches).
  Feature-entity writes from the SAME server session persist fine (129/119 phase
  updates all landed). Suspects: success-before-commit with a rolled-back transaction
  on a post-step, or a divergent DB path for the backlog code path. Same family as
  #055 (acknowledged-but-lost writes). Diagnose before trusting ANY backlog
  registration; this file is the interim source of truth.

- **#062 — schema_version write is OR IGNORE (write-once) — upsert at 132** *(source: 119 QA gate C3, LOW)*
  Bumping V2_SCHEMA_VERSION and re-bootstrapping keeps the stale recorded version
  while new DDL applies — silent mismatch. When 132's migration story lands: ON
  CONFLICT DO UPDATE (or read-compare-write) + a version-bump re-bootstrap test.
  Until then the write-once behavior is correct for V2_SCHEMA_VERSION=1.

- **#068 — `INSERT OR REPLACE` bypasses the events immutability triggers** *(P004, source: feature 122 security battery, 2026-07-12; owned by 119's contract / 132's cutover)*
  REPLACE's implicit delete-half does NOT fire `events_no_delete` (BEFORE DELETE
  triggers skip REPLACE-deletes unless `PRAGMA recursive_triggers` is ON — default
  OFF, and connect_v2/bootstrap_v2 never enable it; verified against
  sqlite.org/lang_conflict.html at 122's security review). A raw
  `INSERT OR REPLACE INTO events (uuid, ...)` on an existing event uuid silently
  delete+reinserts, defeating 119's append-only guarantee. Pre-existing (NOT
  122-introduced — 122's vocab triggers DO fire on the insert half). Remediation
  candidates for 132: enable `recursive_triggers` on connect_v2, or a
  uuid-collision BEFORE INSERT guard trigger, or both; add a teeth test either way.

## Completed / Promoted

- **#061 — append_event factory-contract guard** *(closed by feature 120, 2026-07-12)*
  Shipped as design D3: `PRAGMA foreign_keys` probe as append_event's FIRST
  statement — bare connections raise `ValueError` (naming connect_v2 and this
  item) before any write, on both transaction paths. The sentinel-attribute
  alternative was REJECTED at spec review (would AttributeError the retry-wrapper
  tests). Raw-INSERT orphans remain the documented residual surface
  (`test_events.py:506` preserved as the pin); structural closure is FR-3's
  state-as-view invariant at the 132 cutover.

## #063 — Watch: code-quality-reviewer fix-rate on UI-track features
**Filed:** 2026-07-11 (130 retro Tune-3). **Type:** process watch-item.
In 130's implement battery, code-quality-reviewer was the only member with zero actionable fixes (4 nits, all consciously recorded-not-churned; implementation + security reviewers each produced a shipped fix). Do NOT downgrade yet — track its fix-rate across the next 2-3 UI-track (routes/templates-only) features. **Check at feature 125 (kanban-axis-rewire, the next UI-heavy feature):** if still zero actionable findings on UI-track work, consider a lighter/summary-only quality pass for that track while keeping it fully gating on DB/engine-track features. n=1 as of filing.

## #064 — Sentinel workspace renders as cryptic dropdown option in the UI switcher
**Filed:** 2026-07-11 (130 finish QA, code lane). **Type:** UX wart, LOW.
`_UNKNOWN_WORKSPACE_UUID` gets a real `workspaces` row (database.py:5826, project_root=NULL); when any entity is registered under it (real live-board fallback for un-mappable project_ids), `list_workspaces_with_entities()` surfaces it and the switcher renders a selectable `6250c8a6 (N)` option (NULL-root → uuid-prefix label rule). Truthful and functional but cryptic, and visually collides in concept with the transient fourth-state `unknown workspace · 6250c8a6` option. Candidate fix at 132 (backfill dedupes junk) or a dedicated label for the sentinel uuid ("unassigned entities"). Verified by probe during 130's QA gate.

## #065 — claude-mem observation-hook noise misleads subagents at scale
**Filed:** 2026-07-11 (121 implement Process Notes). **Type:** tooling friction, MED.
The PreToolUse:Read observation hook injects "prior observation" system-reminders into every file read. During feature 121, SIX separate subagents independently flagged them as suspected prompt injection, and one injected observation asserted a FABRICATED blocker ("nameFrom/nameTo missing from events.py docstring") that two agents had to disprove at source. All agents behaved correctly (ignore + verify independently), but the noise costs a paragraph of every subagent report, a disproof detour per dispatch, and trains agents to distrust system-reminders wholesale. Candidate fixes: suppress the hook for subagent sessions; or label its output explicitly as non-authoritative local memory; or stop echoing observation TITLES (the fabrication vector — titles written by a summarizer, not verified facts).

## #066 — Workspace-mapping migration writer pollutes source tree during test runs
**Filed:** 2026-07-11 (121 finish QA, regression lane). **Type:** test hygiene, MED (pre-existing, NOT introduced by 121).
`_atomic_write_workspace_mapping` (database.py:1726, feature-108 migration machinery) writes `{}` marker files to `<cwd-subdir>/.claude/pd/migrations/migration-11-workspace-mapping.json` when suites/imports run from package directories — creating untracked strays under `plugins/**` (a `git add -A` would stage them). Interim fix shipped with 121's gate: `plugins/**/.claude/` gitignore line (deliberately narrower than root `.claude/`, which holds real config). Root-cause fix: redirect the writer's workspace_root to tmp in test fixtures, or gate the write on being under a real project root.
**Root cause located (126 QA lane B, 2026-07-12):** `database.py:1859` —
`workspace_root = os.environ.get("PD_WORKSPACE_ROOT") or os.getcwd()`; no
production caller sets the env var, so test/bootstrap paths write relative to
cwd. test_database.py's migration-11 class balances set/pop correctly (17/17);
the residual stray writer is some other test path not yet isolated. Note: one TRACKED instance (`plugins/pd/.claude/pd/migrations/...`, identical blob on develop) predates 121 — remove alongside the root-cause fix.

## #067 — Carry nested-view scale-benchmark obligation into 132's spec inputs
**Filed:** 2026-07-12 (120 retro Tune-4). **Type:** obligation carrier, LOW-MED.
`entity_state`'s six correlated subqueries recompute the GROUP BY over events on
every read; the query plan through the nested view is UNVERIFIED beyond test
scale (~10^2 events). The obligation — EXPLAIN QUERY PLAN + benchmark at live-DB
scale before wiring the first frequently-polled consumer — currently lives only
in a views.py code comment and a quality-review suggestion (weakest carriers;
echoes 118's SQLITE_LOCKED docstring-only risk that 119 nearly missed). 132's
spec MUST list this as an explicit input/prerequisite alongside #054/#062/#064.
**Measured (120 QA lane A, 2026-07-12):** per-entity `entity_state` lookups are
O(total events in DB), NOT O(that entity's events) — idx_events_entity_axis
covers entity_axis_state's per-entity path but the pivoted view's correlated
subqueries materialize the WHOLE grouped view per lookup (SQLite's AUTOMATIC
PARTIAL COVERING INDEX only kicks in on full-table reads). ~2.5ms/lookup at 5k
events, near-linear in total events (0.22ms@500 → 9.6ms@20k); full-table
`SELECT * FROM entity_state` is fine (6.75ms for 500 rows @ 5k events).
Consumers at 132 should read entity_axis_state per-entity or the pivoted view
full-table; a frequently-polled per-entity entity_state read needs a plan fix.

## #069 — data-file-guard dispatcher: normalize file_path before fnmatch; anchor exclude patterns

**Source:** feature 127 security review (2026-07-12, battery W1). **Owner:** feature-110 dispatcher infra. **Severity:** LOW (defense-in-depth; no confirmed live break).
- fnmatch's `*` crosses `/` (stdlib-documented), so a RELATIVE `docs/projects/../features/043/.meta.json` satisfies the `docs/projects/*/.meta.json` exclude and bypasses the deny; gated today by Write/Edit's absolute-path invariant.
- Corollary: the exclusion is start-anchored so it is ALSO inert for legitimate absolute project-meta paths — mis-anchored in both directions (absolute project-meta writes fall through to the deny).
- Context note (same review, S1): the guard matches Write|Edit only — Bash redirection bypasses the module entirely; pre-existing tool-boundary, backstop is DB-as-truth + doctor/reconciler rebuild.
- Fix shape: os.path.normpath/resolve before fnmatch, reject `..` segments, root-anchor exclude patterns to artifacts_root. Evidence: dispatcher.py:156,171-174; data_file_guards.json:4.

## #070 — _project_meta_json: assert artifact_path resolves inside artifacts_root before writing

**Source:** feature 127 security review (2026-07-12, battery S2). **Owner:** workflow_state_server projection path (pre-existing, shared by 5 call sites incl. reproject_meta_json). **Severity:** LOW (defense-in-depth).
- The projection writes `<entity.artifact_path>/.meta.json` with no containment check; a poisoned artifact_path (via a separate register/update path — those inputs are parameterized but unconstrained) could steer the write outside the tree.
- Fix shape: resolve artifact_path and assert it is within artifacts_root before the open(); warn-and-skip otherwise. Evidence: workflow_state_server.py:401-405.

## #071 — Consolidate duplicate _seed_workflow_row test helper into conftest.py
**Source:** feature 125 battery (code-quality-reviewer S5, pre-existing). `_seed_workflow_row` is defined twice with divergent signatures — a 5-param version in `plugins/pd/ui/tests/test_app.py` (:299) and an 8-param superset in `plugins/pd/ui/tests/test_deepened_app.py` (:22; adds last_completed_phase/backward_transition_reason/updated_at). Consolidate into `plugins/pd/ui/tests/conftest.py` next time either file is churned (candidate: feature 132's seed-token removal sweep). Out of 125's diff scope; does not affect correctness.

## #072 — Generic MCP error handler embeds str(exc) — mirror db_unavailable_error's sanitization
**Source:** feature 123 security battery (pre-existing, not introduced by 123). `workflow_state_server.py:788-793`'s `except sqlite3.Error` branch embeds `f"Database error: {type(exc).__name__}: {exc}"` — a raw sqlite3 error can carry the DB file path or a "database is locked" string into the MCP response. The 128/123 fail-loud path (`db_unavailable_error`, models.py) already does this right: embed only `type(cause).__name__`, never `str(cause)`. Mirror that in the generic handler. Low severity (local tooling, own paths to own caller).
