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

- **#061 — append_event factory-contract guard before feature 120** *(source: 119 QA gate C2, LOW)*
  The "conn MUST come from connect_v2" contract is purely advisory — a bare
  `sqlite3.connect` silently skips FK enforcement and can write a PERMANENT orphan
  into the immutable events table. Before 120/132 wire consumers: add a cheap
  structural guard (`PRAGMA foreign_keys` == 1 assert at append_event entry, or a
  connect_v2 sentinel attribute), and update the FK-pair test's bare-connection half.

- **#062 — schema_version write is OR IGNORE (write-once) — upsert at 132** *(source: 119 QA gate C3, LOW)*
  Bumping V2_SCHEMA_VERSION and re-bootstrapping keeps the stale recorded version
  while new DDL applies — silent mismatch. When 132's migration story lands: ON
  CONFLICT DO UPDATE (or read-compare-write) + a version-bump re-bootstrap test.
  Until then the write-once behavior is correct for V2_SCHEMA_VERSION=1.

## Completed / Promoted

(none tracked here yet — historical items live in the entity DB)

## #063 — Watch: code-quality-reviewer fix-rate on UI-track features
**Filed:** 2026-07-11 (130 retro Tune-3). **Type:** process watch-item.
In 130's implement battery, code-quality-reviewer was the only member with zero actionable fixes (4 nits, all consciously recorded-not-churned; implementation + security reviewers each produced a shipped fix). Do NOT downgrade yet — track its fix-rate across the next 2-3 UI-track (routes/templates-only) features. **Check at feature 125 (kanban-axis-rewire, the next UI-heavy feature):** if still zero actionable findings on UI-track work, consider a lighter/summary-only quality pass for that track while keeping it fully gating on DB/engine-track features. n=1 as of filing.

## #064 — Sentinel workspace renders as cryptic dropdown option in the UI switcher
**Filed:** 2026-07-11 (130 finish QA, code lane). **Type:** UX wart, LOW.
`_UNKNOWN_WORKSPACE_UUID` gets a real `workspaces` row (database.py:5826, project_root=NULL); when any entity is registered under it (real live-board fallback for un-mappable project_ids), `list_workspaces_with_entities()` surfaces it and the switcher renders a selectable `6250c8a6 (N)` option (NULL-root → uuid-prefix label rule). Truthful and functional but cryptic, and visually collides in concept with the transient fourth-state `unknown workspace · 6250c8a6` option. Candidate fix at 132 (backfill dedupes junk) or a dedicated label for the sentinel uuid ("unassigned entities"). Verified by probe during 130's QA gate.

## #065 — claude-mem observation-hook noise misleads subagents at scale
**Filed:** 2026-07-11 (121 implement Process Notes). **Type:** tooling friction, MED.
The PreToolUse:Read observation hook injects "prior observation" system-reminders into every file read. During feature 121, SIX separate subagents independently flagged them as suspected prompt injection, and one injected observation asserted a FABRICATED blocker ("nameFrom/nameTo missing from events.py docstring") that two agents had to disprove at source. All agents behaved correctly (ignore + verify independently), but the noise costs a paragraph of every subagent report, a disproof detour per dispatch, and trains agents to distrust system-reminders wholesale. Candidate fixes: suppress the hook for subagent sessions; or label its output explicitly as non-authoritative local memory; or stop echoing observation TITLES (the fabrication vector — titles written by a summarizer, not verified facts).
