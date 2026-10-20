# Feature 108 — Workspace Identity Foundation — Retrospective (AORTA)

- **Branch:** `feature/108-workspace-identity-foundation`
- **Project:** P003-entity-system-redesign (feature 1 of 4)
- **Baseline SHA:** `afe19a6` (2026-05-10T20:23:15Z)
- **Final SHA range:** `afe19a6` → `df6ff6f2` (16 commits)
- **Phases completed:** specify → design → create-plan → implement

---

## A — Activities

**Specify (6 iterations, ~48 min)**
- Produced 797-line spec.md with 41 ACs / 18 FRs / 8 NFRs.
- Pinned `_UNKNOWN_WORKSPACE_UUID = "6250c8a6-5306-443f-b225-477a040016ea"`
  (deterministic SHA-256 of `"pd-test-fixture-unknown-workspace"`).
- Captured F6 (UUIDv7) conditional adoption per `pyproject.toml` floor.
- Closed at 3 non-blocking suggestions (FR-3 fractional numbering, AC-8/AC-38/39
  overlap, FR-7 uuid4 pin).

**Design (5 iterations, ~37 min)**
- Produced 1080-line design.md with 12 decisions and 13 components.
- 17-step Migration 11 forward + 16-step reverse with full DDL.
- `wp_autofill_workspace_uuid` + `wp_reject_orphaned_insert` trigger pair.
- `fcntl.flock(LOCK_EX)` cross-process atomic workspace.json write.
- Invented `MIGRATIONS_DOWN` dispatcher pattern (no codebase precedent).

**Create-plan (3 iterations, ~39 min)**
- Produced 381-line plan.md + 1610-line tasks.md (78 tasks across 8 phases A–H).
- task-reviewer APPROVED at iteration 2 with 3 suggestions.
- 3 non-blocking phase-reviewer warnings deferred to implement phase.

**Implement (5 dispatches, ~9 hours)**
- Phase A+B (`8e952ce`): bootstrap constants + 17-step Migration 11 forward.
- Phase C+D (`6dea91a`): `MIGRATIONS_DOWN` reverse + `resolve_workspace_uuid`.
- Phase E partial + F6 deferral (`2a3f4f5`, `64060aa`): MCP signature work +
  F6 FAILS-path closeout (backlog #00359 filed).
- Per-method flips (`88e85f4` → `dd7f91e`): register / read / lineage /
  dependency / workflow_phase / sequence each flipped independently with
  `project_id` deprecation alias.
- Final dispatch (`3f6f6bb`) + late hardening (`df6ff6f`): fixture bootstraps,
  workflow_state_server lazy global, `__unknown__` workspace bucket for
  feature_lifecycle, hook test `.claude/` existence gate.

---

## O — Observations

**Phase metrics**

| Phase | Iterations | Wall-clock | Reviewer notes |
|---|---:|---:|---|
| specify | 6 | ~48 min | 3 non-blocking |
| design | 5 | ~37 min | 3 non-blocking |
| create-plan | 3 | ~39 min | 3 suggestions + 3 editorial fixes |
| implement | 5 dispatches | ~9 hours | per-method incremental rollout |

**Test deltas (entity_registry/ pytest)**
- Baseline (post Migration-11, pre flip): 606F / 485P / 62E.
- After per-method flips: **1162P / 0F** (entity_registry/).
- Wider plugin (`mcp`, `doctor`, `workflow_engine`, `ui`, `semantic_memory`):
  baseline 621F / 1605P / 112E → final **4F (pre-existing) / 3817P / ~0E**.
- Net swing: **+931 passing**, all pre-existing failures unrelated to 108.

**Validation gates**
- `migration-11-schema-diff.txt` artifact: 0 bytes (byte-identical round-trip).
- `validate.sh`: green at HEAD.
- F6 gate result: `policy_gate_decision = DEFER` (pyproject floor 3.12 < stdlib
  3.14 uuid7); FAILS-path tasks 7.6 + 7.7 executed; PASSES path skipped.

**Production callers fixed downstream of the flip**
- `mcp/entity_server.py:449` (register_entity dispatch).
- `entity_registry/server_helpers.py:262`.
- `workflow_engine/{reconciliation.py:331,task_promotion.py:346,feature_lifecycle.py}`.
- `mcp/workflow_state_server.py` lazy global pattern mirrored from
  `entity_server.py`.

---

## R — Reflections

**Wins**
1. **Multi-round adversarial review caught the SoT pain points before code.**
   Round 1 (system-architect) surfaced 12 fixes; the symptom-to-fix coverage
   matrix verification programmatically confirmed every reported pain had a
   resolving proposal before feature creation.
2. **MIGRATIONS_DOWN dispatcher is reusable.** The pattern (mirror dict +
   `_migrate_down(conn, target_version)`) lets every future schema bump ship
   with byte-identical round-trip verification baked in. Migration 11 is the
   reference implementation.
3. **Per-method incremental rollout absorbed the ~1661-reference blast
   radius without a Big Bang week.** Each commit was independently revertable
   and validate.sh stayed green across the whole sequence.
4. **Late `.claude/` existence gate caught the only real production hazard.**
   Without it, `resolve_workspace_uuid` would have silently auto-created
   `.claude/pd/workspace.json` for any cwd that happened to run a pd hook
   (e.g. inside `agent_sandbox/`).
5. **fcntl.flock convergence test (AC-37) was worth writing.** Multiprocessing
   race convergence — re-read after own rename — would have been a Heisenbug
   in prod.

**Issues**
1. **Plan optimism on the production signature flip.** tasks.md did not
   enumerate `database.py` method signature flips as separate tasks; if the
   bulk-sed dispatcher had executed naively, ~600 TypeError failures would
   have landed at once. Mitigated mid-flight by switching to per-method
   incremental rollout, but the planning step missed it.
2. **`detect_project_id` rename had no alias.** Hooks calling the old name
   would have broken silently; caught during Phase D, but a deprecation
   wrapper would have been cheap insurance.
3. **`agent_sandbox/2026-05-10/feature-108/` audit artifacts were never
   reconciled.** The form-enumeration audit captured 2000+ callsites but the
   subsequent dispatches relied on grep rather than the audit. The audit
   files were eventually superseded but lingered.

**Surprises**
1. **Python 3.14 runtime had `uuid.uuid7` but the pyproject floor was 3.12.**
   Treating the gate as *policy-floor-driven* (not runtime-driven) was the
   correct call, but the runtime/policy mismatch is non-obvious — flagged in
   backlog #00359 for re-engagement when the floor moves.
2. **Codex reviewers were unavailable for the deep-dive round.** "Model
   availability error" hit twice. Fallback to Claude-only review + manual
   sqlite3/grep verification worked, but the comparison-of-review-paths the
   user originally requested could not be completed.
3. **Pre-existing failures in `semantic_memory::TestMergeDuplicatePromotion`
   surfaced during the wider-plugin sweep.** Unrelated to 108 but caught by
   the broader test run. Filed mentally for the next session's "tidier
   ground" pass.

---

## T — Takeaways

### Pattern 1 — Multi-round adversarial review for system-wide redesigns
**When:** Cross-cutting changes that span 3+ packages or invalidate >100
call sites.
**How:** Round 1 system-architect surfaces fixes; Round 2 independent
reviewer (codex when available) repeats investigation; programmatic coverage
matrix maps every user-reported symptom to a resolving proposal before
feature creation.
**Why:** Stops scope drift and confirms full root-cause resolution rather
than symptom suppression. Verified on this feature: 12 fixes / 4 features
emerged from the user's 5-pain-point seed list.

### Pattern 2 — Per-method incremental rollout with deprecation alias
**When:** Method signature flip cascades into hundreds of call sites across
production + tests.
**How:** Add new kwarg as `T | None = None`; keep old kwarg as deprecated
alias with explicit resolution rules (`_resolve_workspace_uuid_kwargs`);
flip one method per commit; gate each commit on `validate.sh` + scoped
pytest; drop alias only after all callers migrated.
**Why:** Each commit is independently revertable. The Big Bang alternative
(~3 days focused work, ~3–5 review iterations) is too risky for a critical-
path migration. Reference impl: `database.py` flips `88e85f4` → `dd7f91e`.

### Anti-pattern 3 — Plan optimism on production-side cascade
**Symptom:** tasks.md frames "flip database.py method signatures" as one
task, masking the cascade into ~1661 `project_id` references + ~648
`parent_type_id` references across 20+ files.
**Why it bites:** Single-dispatch budget can't accommodate the actual blast
radius; a naive sed sweep would land ~600 TypeError failures at once.
**Counter-rule:** Before approving a tasks.md that touches a widely-imported
method, run `grep -rn 'method_name(' | wc -l` and require the planner to
either decompose by call-site cluster or explicitly call out the
mitigation strategy (per-method rollout / deprecation alias / etc.).

### Heuristic 4 — Empty-schema-diff gate for reversible migrations
**Rule:** Reversible schema migrations must produce a byte-identical
round-trip artifact (`schema_v{N-1}.sql` → forward → reverse → diff against
original = 0 bytes). Ship the diff artifact in the feature directory.
**Why:** Confidence that the reverse migration is genuinely lossless, not
just "looks right by eyeball". Saved this feature: Migration 11's
`parent_type_id` reconstruction via `parent_uuid → uuid → type_id` JOIN
turned out to be subtle (NULL semantics around orphans), and the diff would
have flagged any drift instantly.

### Heuristic 5 — `.claude/` existence gate for hook-initiated writes
**Rule:** Any function that creates state under `.claude/` MUST first
verify `.claude/` itself exists (via `os.path.isdir`). If missing, raise
explicitly rather than `os.makedirs` it.
**Why:** Hooks fire in arbitrary cwds (agent_sandbox subdirs, tmpdirs,
worktree clones). Silently creating `.claude/` outside the project root is
the worst kind of side effect — invisible, persistent, and easy to commit
accidentally. Reference impl: `project_identity.resolve_workspace_uuid`
step 4 gate (`df6ff6f`).

---

## A — Actions

**Backlog filed**
- **#00359** — F6 (UUIDv7) re-engagement when pyproject `requires-python`
  floor moves to ≥3.14. Re-runs tasks 7.2 → 7.5 (raise floor, `_new_uuid()`
  helper, substitute register sites, EXPLAIN audit + CI matrix).

**Process changes**
- Future cross-cutting refactors must ship with a `grep -rn` callsite
  audit in `agent_sandbox/{date}/feature-{id}/`, and tasks.md must
  reference it explicitly (per Anti-pattern 3).
- When introducing a new MIGRATIONS_*` dispatcher pattern, the feature
  directory MUST include a `migration-{N}-schema-diff.txt` artifact
  (per Heuristic 4).

**Follow-ups (not in scope for 108)**
- Features 109 / 110 / 111 (per project P003 roadmap) depend on 108 and
  can now start. Each is independently scoped (composite-ID rename via
  `entity_display`, backlog→feature promotion robustness, multi-store SoT
  enforcement).
- `agent_sandbox/2026-05-10/feature-108/` audit artifacts are obsolete;
  next session should sweep them.
- Pre-existing `semantic_memory::TestMergeDuplicatePromotion` failures
  (4 failed in wider plugin sweep) need triage in an unrelated session.
