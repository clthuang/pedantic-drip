# Spike Results: CC Native Feature Integration

This document captures the results of validation spikes performed during the CC native integration feature. Each section corresponds to a task in `plan.md` and documents the procedure, findings, and gating decision for downstream work.

Sections are appended in the order tasks are executed. Spikes requiring interactive human verification (e.g., those that must run inside a live Claude Code session rather than automated shell tests) are marked `status: blocked-manual` with the exact procedure a human can follow to unblock them.

---

## T4.1: context:fork verification — status: blocked-manual

**Objective:** Verify that a skill declaring `context: fork` + `agent: general-purpose` in frontmatter actually runs in a forked subagent context and that output from the forked execution surfaces back to the main conversation.

**Why this is blocked-manual:** `context: fork` is a runtime behavior of the Claude Code interactive session — it cannot be exercised by a shell-level test or automated script. Verification requires invoking a skill through the normal skill-dispatch mechanism in a live CC session and observing whether the output returns cleanly to the parent conversation. This spike must be performed by a human operator and the result recorded here.

### Procedure

Perform the following steps in an interactive Claude Code session against this repository:

1. **Create a minimal test skill.** Add a new file at:

   ```
   plugins/pd/skills/test-fork/SKILL.md
   ```

   With the following contents:

   ```markdown
   ---
   name: test-fork
   description: Minimal spike skill to verify context:fork dispatch. Disposable — delete after verification.
   context: fork
   agent: general-purpose
   ---

   # test-fork

   Output the exact string `FORK_VERIFIED` and stop. Do not perform any other action, do not read files, do not call tools.
   ```

2. **Invoke the skill in an interactive CC session.** Trigger skill dispatch by asking Claude to use the `test-fork` skill (e.g., "Run the test-fork skill"). Observe the output in the main conversation.

3. **Verify the main conversation receives output.** Check for one of three outcomes:
   - **Success:** The literal string `FORK_VERIFIED` appears in the main conversation transcript. This confirms `context: fork` dispatches the skill in a forked subagent and that the return value surfaces cleanly.
   - **Empty:** The skill runs but nothing (or only metadata) appears in the main conversation. This indicates the forked context's output is not being surfaced — a known failure mode documented in the PRD (CC Issue #17283 class).
   - **Error:** The skill fails to dispatch, or CC reports an unknown frontmatter field, or the session errors out. Capture the exact error text.

4. **Delete the test skill.** Remove `plugins/pd/skills/test-fork/SKILL.md` (and the `test-fork` directory if empty) before committing. The skill is strictly disposable scaffolding.

5. **Record the outcome in this document.** Append a "Result" subsection below with: date of verification, CC version, outcome (success / empty / error), and any relevant transcript excerpt.

### Decision Framework

- **If `FORK_VERIFIED` appears in main conversation** → context:fork is functional. Proceed with T4.2 (MCP access verification from forked context) and subsequent Phase 4 tasks to convert `researching/SKILL.md`.
- **If output is empty or the skill errors** → `context: fork` is not usable in the current CC runtime for pd's topology. Mark FR-3 deferred, document the observed failure mode, and stop Phase 4. The researching skill continues to use inline Task dispatch (current behavior).

### Result

_(To be filled in after manual verification. Include: date, CC version, outcome, transcript excerpt if useful.)_

---

## T0.3: SQLite Concurrency Spike Results — status: pass

**Objective (REQ-1 / FR-0):** Validate that `~/.claude/pd/entities/entities.db` tolerates parallel writes from multiple worktree-style processes under WAL mode + `busy_timeout=15000`, so that FR-1 (worktree-parallel implementer dispatch) is not blocked by SQLite locking.

**Harness:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`

- Creates a throwaway git repo with 3 worktrees (`spike-wt-{1,2,3}`).
- Spawns 3 background Python workers, each `cd`-ed into its worktree, each opening its **own** `EntityDatabase` connection to a **shared** temp SQLite DB.
- Each worker writes 10 entities (unique `proc{N}-entity{M}` IDs so `INSERT OR IGNORE` cannot mask failures) → 30 rows total expected.
- Each worker retries on `sqlite3.OperationalError` with message containing "locked"/"busy" using 100ms/200ms backoff, capped at 3 attempts per entity.
- Wall-clock timing uses `time.monotonic()` via `python3` (macOS `date` lacks `%N`).
- Authoritative row count is queried from the DB after all workers exit; success rate is computed as `rows_in_db / expected_rows`.
- Emits a single-line `METRICS_JSON: {...}` summary for machine parsing alongside a human-readable `metrics:` line.

**Command**

```bash
bash plugins/pd/hooks/tests/test-sqlite-concurrency.sh
```

**Environment**

- macOS 26.3.1 (Darwin 25.3.0)
- `git version 2.50.1 (Apple Git-155)`
- `plugins/pd/.venv/bin/python` → Python 3.14.3
- `entity_registry.database.EntityDatabase` — WAL mode + `busy_timeout=15000` (set by `_set_pragmas()`, `database.py:3505-3506`)
- Worker-level retry: 3 attempts per entity, exponential backoff (100ms, 200ms)
- Temp DB on default tmpfs-equivalent (`$TMPDIR` under `/var/folders/…`)

**Scope note vs. REQ-1 acceptance criteria:** REQ-1 lists two scenarios, (a) shared MCP server instance and (b) separate MCP instances per worktree. This harness targets scenario (b) — each worker opens its own `EntityDatabase` connection, mirroring the "MCP servers are NOT isolated by worktree but each subprocess holds its own connection" topology called out in the design doc. Scenario (a) (single shared MCP process) is trivially serialized at the MCP layer and therefore strictly easier than what is tested here; passing (b) implies (a) is safe. No MCP process was spawned in this spike.

**Runs (3 representative)**

Run 1:
```
TEST: parallel: 3 procs x 10 writes -> 30 rows
  metrics: rows_in_db=30 expected=30 retries=0 worker_errors=0 failed_procs=0 wall_clock=0.060s max_proc_elapsed=0.012s success_rate=100.0%
METRICS_JSON: {"test": "parallel_entity_writes", "num_worktrees": 3, "entities_per_proc": 10, "expected_rows": 30, "rows_in_db": 30, "retries": 0, "worker_errors": 0, "failed_procs": 0, "wall_clock_s": 0.06, "max_proc_elapsed_s": 0.012, "success_rate_pct": 100.0}
Ran: 1 | Passed: 1 | Failed: 0
```

Run 2:
```
TEST: parallel: 3 procs x 10 writes -> 30 rows
  metrics: rows_in_db=30 expected=30 retries=0 worker_errors=0 failed_procs=0 wall_clock=0.063s max_proc_elapsed=0.014s success_rate=100.0%
METRICS_JSON: {"test": "parallel_entity_writes", "num_worktrees": 3, "entities_per_proc": 10, "expected_rows": 30, "rows_in_db": 30, "retries": 0, "worker_errors": 0, "failed_procs": 0, "wall_clock_s": 0.063, "max_proc_elapsed_s": 0.014, "success_rate_pct": 100.0}
Ran: 1 | Passed: 1 | Failed: 0
```

Run 3:
```
TEST: parallel: 3 procs x 10 writes -> 30 rows
  metrics: rows_in_db=30 expected=30 retries=0 worker_errors=0 failed_procs=0 wall_clock=0.062s max_proc_elapsed=0.014s success_rate=100.0%
METRICS_JSON: {"test": "parallel_entity_writes", "num_worktrees": 3, "entities_per_proc": 10, "expected_rows": 30, "rows_in_db": 30, "retries": 0, "worker_errors": 0, "failed_procs": 0, "wall_clock_s": 0.062, "max_proc_elapsed_s": 0.014, "success_rate_pct": 100.0}
Ran: 1 | Passed: 1 | Failed: 0
```

**Aggregate (3 runs, 90 total writes)**

| Metric | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| rows_in_db / expected | 30 / 30 | 30 / 30 | 30 / 30 |
| retries | 0 | 0 | 0 |
| worker_errors | 0 | 0 | 0 |
| failed_procs | 0 | 0 | 0 |
| wall_clock | 0.060s | 0.063s | 0.062s |
| max_proc_elapsed | 0.012s | 0.014s | 0.014s |
| success_rate | 100.0% | 100.0% | 100.0% |

**Decision**

SQLite concurrency = **pass** per REQ-1: 100% success rate across the 30-write parallel test, repeated 3 times for 90 total writes, zero retries, zero errors, zero failed procs. `busy_timeout=15000` absorbed all contention internally — the user-space retry path was never exercised. Wall-clock dominated by Python import/startup (~60ms); per-worker write work completed in 12-14ms.

**Implication for FR-1:** WAL + `busy_timeout=15000` is sufficient as the concurrency strategy for worktree-parallel implementer dispatch at this workload size (3 concurrent writers, tens of writes per batch). FR-1 is **unblocked**. No architectural changes to the entity DB are required for Phase 2.

**Caveats / known limits of this spike**

- Workload is small (30 writes, 3 writers). Larger implementer batches or long-running transactions could still surface contention. The in-script retry path (100ms/200ms backoff, 3 attempts) remains in place as a safety net.
- Scenario (a) (shared MCP server) was not exercised empirically, but is strictly easier than scenario (b) as argued above.
- Temp DB lives on the macOS default temp volume; behavior on network filesystems (NFS, SMB) is out of scope — entity DB lives at `~/.claude/pd/entities/entities.db` on the local disk in normal use.
- The spike exercises raw `register_entity` writes; it does not exercise the full workflow_state transition path (which performs reads-then-writes within a single transaction). Phase 1 regression tests (T1.x) cover that path.

---

## T0.4: Agent Path Compliance Spike — status: blocked-manual

**Objective (REQ-2 / FR-1 precondition):** Verify that a Claude Code Agent, when dispatched with an explicit worktree path directive in its prompt, confines all filesystem operations (Read/Edit/Write/Glob/Grep) to the designated worktree directory and does NOT modify files in the main working tree. This is the second Phase 0 gate for the manual-worktree workaround documented in design.md TD-1 (required because `isolation: worktree` is silently ignored for plugin-defined subagent types per CC Issues #33045, #37030).

**Why this is blocked-manual:** Agent path compliance is a runtime behavior of the Claude Code interactive session — it cannot be exercised by a shell-level test or automated script. The spike requires dispatching a real sub-Agent from an interactive CC session and observing its filesystem writes against a live git worktree. Verification must be performed by a human operator and the result recorded here.

### Procedure

Perform the following steps in an interactive Claude Code session against this repository:

1. **Create the worktree.** From the project root:

   ```bash
   git worktree add .pd-worktrees/spike-test -b spike-test
   ```

2. **Record the main-tree HEAD SHA.** Capture the SHA before dispatching the agent so post-agent drift can be detected:

   ```bash
   BEFORE=$(git rev-parse HEAD)
   ```

3. **Dispatch a sub-Agent with an explicit worktree directive.** In an interactive CC session, invoke the Agent tool with the prompt below. Substitute `{abs_path}` with the absolute path to the project root (e.g., `/Users/terry/projects/pedantic-drip`):

   ```
   Work ONLY in {abs_path}/.pd-worktrees/spike-test/. Use absolute paths for ALL Read/Edit/Write/Glob/Grep. Create a file called spike-marker.txt with content 'hello'.
   ```

4. **Verify path compliance after the agent completes.** Run the following three checks:

   - **Main tree HEAD unchanged:** `git rev-parse HEAD` must equal `$BEFORE`. If it differs, the agent committed to the main tree.
   - **Main tree not modified:** `git diff --name-only` must emit no output. If any files are listed, the agent wrote outside the worktree.
   - **Worktree file created:** `.pd-worktrees/spike-test/spike-marker.txt` must exist with content `hello`. This confirms the agent did write to the intended location.

5. **Cleanup.** Remove the worktree:

   ```bash
   git worktree remove .pd-worktrees/spike-test
   ```

6. **Record the outcome in this document.** Append a "Result" subsection below with: date of verification, CC version, outcomes of the three checks (pass/fail each), and any relevant transcript excerpts or stray-write paths observed.

### Decision Framework

- **If all 3 verifications pass** → worktree approach validated, proceed with Group 2 (Phase 2 worktree parallel dispatch per plan.md).
- **If any fail** → worktree approach blocked, feature requires redesign. Document which check failed and any stray-write paths, then revisit design.md TD-1 for an alternative (e.g., wait for CC Issue #33045 fix, or explore per-task `cd`-based isolation without worktrees).

### Result

_(To be filled in after manual verification. Include: date, CC version, pass/fail for each of the 3 checks, transcript excerpts if useful.)_

---

## T1.5: Behavioral Regression Baseline — status: pass

**Objective (REQ-4 / FR-5 / Task 1.5):** Establish and document the behavioral regression baseline — the committed test assertions in `plugins/pd/hooks/tests/test-workflow-regression.sh` (added T1.1-T1.4) must pass cleanly on current `develop` before any Phase 2 (worktree) or Phase 3 (security-review) integration changes land. This baseline is the "before" snapshot required by spec REQ-4: *"Baseline = committed test assertions that pass on current code. 'Before' means tests pass before FR-1/FR-2. 'After' means same tests still pass post-integration."*

**Harness:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

Covers three workflow phase outcomes plus a skeleton sanity check:
- **Skeleton** — mock feature dir, `.meta.json`, and entity DB path are wired up correctly before any assertions run.
- **(a) Implement phase entity DB state** — register a `task` entity via the plugin's `EntityDB` Python API; assert the row exists with the expected status.
- **(b) Finish-feature `.meta.json`** — invoke `complete_phase(feature_type_id, "specify")`; assert `.meta.json` advances to `phase=design` with a non-null ISO-8601 timestamp.
- **(c) Phase transition guards** — valid transition (`specify -> design`) succeeds after specify completes; invalid transition (`specify -> implement`) is rejected by the state-machine guard.

**Command**

```bash
bash plugins/pd/hooks/tests/test-workflow-regression.sh
```

**Environment**

- macOS 26.3.1 (Darwin 25.3.0)
- `plugins/pd/.venv/bin/python` → Python 3.14.3
- Branch: `develop` (Task 1.5 pre-Phase-2 baseline)
- Date: 2026-04-15

**Runs (3 consecutive, for stability)**

| Run | Exit | Ran | Passed | Failed |
|---|---|---|---|---|
| 1 | 0 | 4 | 4 | 0 |
| 2 | 0 | 4 | 4 | 0 |
| 3 | 0 | 4 | 4 | 0 |

**Full output excerpt (Run 1, raw)**

```
Running test-workflow-regression.sh
Temp dir: /var/folders/61/sch8t_rj6hvfjdwcfr4sl_lw0000gn/T/pd-workflow-regression-XXXXXX.iKHoaDrnmZ

  INFO: Setting up mock feature at: /var/folders/61/.../features/999-mock-feature
  INFO: Mock entity DB path (not yet created): /var/folders/61/.../entities.db
TEST: skeleton: mock feature dir and .meta.json exist; entity DB path is set
  PASS
TEST: entity DB: register task entity via Python library, assert row exists with correct status
  PASS
TEST: complete_phase: advances .meta.json to design with non-null ISO timestamp
  PASS
TEST: phase transition guards: valid (specify -> design) succeeds; invalid (specify -> implement) blocks
  PASS

Ran: 4 | Passed: 4 | Failed: 0
```

(ANSI color codes stripped for readability; raw output wraps INFO lines in `\e[0;33m…\e[0m` and PASS lines in `\e[0;32m…\e[0m`.)

**Decision**

Regression baseline = **pass** per REQ-4: all 4 assertions green on current `develop`, exit 0, zero flakiness across 3 consecutive runs. No test-case bugs surfaced during baseline capture; nothing to fix. The baseline is now the "before" reference that Phase 2 (worktree dispatch) and Phase 3 (security-review) integration changes must preserve.

**Implication for downstream work**

- **Phase 2 (worktree parallel dispatch):** after each substantive change to `implementing/SKILL.md` or related helpers, re-run `bash plugins/pd/hooks/tests/test-workflow-regression.sh` and confirm `Ran: 4 | Passed: 4 | Failed: 0`. Any regression against this baseline blocks the change.
- **Phase 3 (security-review pre-merge):** same rule — the 4 assertions must remain green after `finish-feature.md` / `wrap-up.md` edits.
- **Future test additions:** append new test cases; do not mutate the existing 4 without an ADR, since they are the committed baseline.

**Caveats**

- Baseline is shell + Python (direct `EntityDB` library calls via the plugin venv). It does not exercise the MCP transport layer end-to-end. This is acceptable per spec — REQ-4 explicitly targets phase outcomes (DB state, `.meta.json` fields, transition guards), not MCP transport.
- Tests create a fresh temp dir and temp DB per run; they do not touch `~/.claude/pd/entities/entities.db`. Re-running is idempotent.

---

## T4.2: MCP Access from Forked Context — status: deferred-pending-T4.1

**Objective (REQ-5 / FR-3 precondition):** Verify that a skill running in a forked subagent context (`context: fork` + `agent: general-purpose` frontmatter) can still reach the pd MCP servers — specifically that it can call `search_memory` (memory-server) and `register_entity` (entity-registry) and receive valid responses. This is the second Phase 4 gate for the stretch goal of converting `researching/SKILL.md` to forked context: if MCP access is lost inside the fork, the researching skill would silently lose its knowledge-bank search and influence-tracking capabilities — per REQ-5, that is a feature regression requiring explicit user approval before proceeding, not an acceptable silent adaptation.

### Rationale

This spike is **deferred pending T4.1** because it is a direct extension of the `context: fork` verification in T4.1 and has no value until T4.1 passes:

- **If T4.1 fails** (fork dispatch is broken, output empty, or errors) → `context: fork` is unusable in pd's topology, FR-3 is already blocked, and the MCP-from-fork question is moot. Running T4.2 before T4.1 would burn effort on a path that may be foreclosed.
- **If T4.1 passes** (the literal `FORK_VERIFIED` sentinel surfaces to the main conversation) → the fork runtime is functional, and it becomes meaningful to ask whether MCP tools remain reachable from inside the fork.

Ordering T4.2 after T4.1 also lets the T4.2 test skill reuse the same manual verification scaffolding (interactive CC session, disposable skill under `plugins/pd/skills/`, result appended here) without duplicating setup.

### Procedure

_Prerequisite: T4.1 has been performed and recorded an outcome of **success** (the `FORK_VERIFIED` sentinel appeared in the main conversation). If T4.1 is still `blocked-manual` with no Result, stop — do not run this spike yet._

Perform the following steps in an interactive Claude Code session against this repository, once T4.1 has passed:

1. **Create a minimal MCP-fork test skill.** Add a new file at:

   ```
   plugins/pd/skills/test-fork-mcp/SKILL.md
   ```

   With frontmatter `context: fork` + `agent: general-purpose` and a body that instructs the forked skill to perform two MCP calls in sequence:

   - **(a) `search_memory`** — call the memory-server's `search_memory` tool with a trivial query string (e.g., `"fork-test-query"`). Capture the tool's response (or any error) verbatim.
   - **(b) `register_entity`** — call the entity-registry's `register_entity` tool with a disposable test entity (e.g., `entity_type: "task"`, `entity_id: "fork-mcp-test"`, `status: "active"`, and a clearly-marked disposable metadata field). Capture the response (or any error) verbatim.
   - Instruct the skill to emit a single summary line to the main conversation with the shape `MCP_FORK_RESULT: search_memory=<ok|error:...> register_entity=<ok|error:...>` and then stop.

2. **Invoke the skill in an interactive CC session.** Trigger skill dispatch (e.g., "Run the test-fork-mcp skill"). Observe what surfaces to the main conversation.

3. **Verify both calls succeed.** Check for one of three outcomes:
   - **Both succeed:** The `MCP_FORK_RESULT` line shows `search_memory=ok register_entity=ok`. Forked context inherits MCP server access; FR-3 path is unblocked.
   - **Either fails:** The `MCP_FORK_RESULT` line shows `error:...` for one or both calls. Capture the exact error text (tool-not-found, permission denied, connection refused, etc.).
   - **No output / fork broken:** The skill runs but the `MCP_FORK_RESULT` line never surfaces. This contradicts the T4.1 pass result and indicates a secondary fork failure mode — document it and halt.

4. **Cleanup.** Remove the test skill (`plugins/pd/skills/test-fork-mcp/SKILL.md` and the `test-fork-mcp` directory if empty). If `register_entity` succeeded, delete the disposable `fork-mcp-test` entity via MCP `delete_entity` (or `EntityDB.delete_entity(...)` from the plugin venv) so it does not pollute the global entity DB.

5. **Record the outcome in this document.** Append a "Result" subsection below with: date of verification, CC version, per-call outcome (ok / error text), and any relevant transcript excerpts.

### Decision Framework

- **If both `search_memory` and `register_entity` succeed from the forked context** → forked skills retain full MCP access. T4.3 (convert `researching/SKILL.md` to `context: fork`) can proceed. No user approval required, since no capability is lost.
- **If either call fails** → the researching skill **cannot** use `context: fork` without losing knowledge-bank search and/or entity lineage tracking. Per REQ-5, this is a feature regression that requires explicit user approval before proceeding. Document the failure mode here, mark T4.3 as **blocked**, and surface the trade-off to the user rather than silently adapting. The fallback is to keep `researching/SKILL.md` on inline Task dispatch (current behavior) and defer FR-3.

### Result

_(To be filled in after T4.1 passes and manual verification completes. Include: date, CC version, `search_memory` outcome, `register_entity` outcome, and transcript excerpt of the `MCP_FORK_RESULT` line.)_

---

## T4.3: Researching Skill context:fork Adoption — status: deferred-pending-T4.2

**Objective (REQ-5 / FR-3 / Task 4.3):** Document the minimal, exact change that WOULD be applied to `plugins/pd/skills/researching/SKILL.md` to adopt `context: fork` once the upstream gates (T4.1 runtime verification, T4.2 MCP-from-forked-context verification) pass. Per spec REQ-5 and design I5/C5, the target is to add `context: fork` + `agent: general-purpose` to the researching skill's frontmatter so the skill executes in an isolated subagent context, keeping Phase 1 research dispatches' intermediate findings out of the main conversation window.

**Why this task is documentation-only (not a real edit):** This task sits downstream of two manual-verification tasks:

- **T4.1 (status: `blocked-manual`)** — requires a human operator to confirm in a live CC session that `context: fork` actually dispatches a skill into a forked subagent and that the output surfaces back to the parent conversation. Until T4.1 records a `success` result, `context: fork` behavior on this CC runtime is unverified.
- **T4.2 (status: `deferred-pending-T4.1`)** — verifies that MCP servers (entity-registry, memory-server) remain accessible from inside a forked context. Researching skill Phase 1 calls `search_memory` (line 21 of current SKILL.md) before each Task dispatch; if MCP is lost in the fork, that code path breaks and the `## Relevant Engineering Memory` enrichment disappears — a silent capability regression that REQ-5 acceptance criteria explicitly forbid.

Applying the frontmatter change now would convert a shipped, working skill into one whose runtime behavior depends on two unverified assumptions. Per TD-4 (graceful degradation) and the spec constraint "this is a feature regression, not an acceptable silent adaptation", T4.3 is a **documentation deliverable**: it captures the exact diff that WOULD land once T4.1 and T4.2 both report `pass`, so that applying the change later is mechanical rather than a fresh design decision.

### Current Frontmatter (verbatim excerpt from `plugins/pd/skills/researching/SKILL.md`, lines 1-4)

```markdown
---
name: researching
description: Orchestrates parallel research, analysis, and synthesis into decision-ready summaries. Use when the user says 'research this', 'summarize what we know', 'gather context', or runs /pd:subagent-ras.
---
```

### Target Frontmatter (to apply post-T4.2-pass)

```markdown
---
name: researching
description: Orchestrates parallel research, analysis, and synthesis into decision-ready summaries. Use when the user says 'research this', 'summarize what we know', 'gather context', or runs /pd:subagent-ras.
context: fork
agent: general-purpose
---
```

### Preview Diff (unified format, minimal change)

```diff
--- a/plugins/pd/skills/researching/SKILL.md
+++ b/plugins/pd/skills/researching/SKILL.md
@@ -1,4 +1,6 @@
 ---
 name: researching
 description: Orchestrates parallel research, analysis, and synthesis into decision-ready summaries. Use when the user says 'research this', 'summarize what we know', 'gather context', or runs /pd:subagent-ras.
+context: fork
+agent: general-purpose
 ---
```

Scope: two added lines in frontmatter. No changes to skill body, Phase 1/2/3 prose, `search_memory` calls, or nested Task dispatch blocks. This is the smallest possible change that exercises `context: fork`; if it works, no further edits are required to meet REQ-5. Design.md I5 flags a caveat — forking the whole skill means Phase 1's nested Task dispatches are agents-within-a-fork — so a follow-up task may be needed if that topology misbehaves, but that restructuring is explicitly out of scope for T4.3.

### Decision Framework

- **If T4.1 records `success` (`FORK_VERIFIED` appears in main conversation) AND T4.2 confirms both `search_memory` and `register_entity` succeed from the forked context** → apply the diff above to `plugins/pd/skills/researching/SKILL.md`, then run the researching skill on 2 representative test queries and manually compare output quality against the current inline-dispatch baseline (per REQ-5 acceptance criteria). No code changes beyond the two frontmatter lines.
- **If T4.1 records `empty` or `error`** → FR-3 is deferred (not failed). Do NOT apply the diff. The researching skill retains its current inline Task dispatch (current behavior). Re-open this task only if/when a future CC release documents `context: fork` working for plugin-defined skills.
- **If T4.1 passes but T4.2 reveals that MCP servers are NOT accessible from the forked context** → per spec REQ-5, "document the lost capabilities (memory search, influence tracking) and get explicit user approval before proceeding — this is a feature regression, not an acceptable silent adaptation." Do NOT apply the diff without a recorded user sign-off that accepts the tradeoff. Default behavior: skip the diff, researching skill keeps inline dispatch with working memory enrichment.

### Scope Constraints Honored

- `plugins/pd/skills/researching/SKILL.md` is NOT modified by T4.3. The file remains at its current state (no `context: fork`, no `agent: general-purpose` frontmatter fields). This avoids a speculative, unverifiable change and preserves the documented graceful-degradation posture.
- T4.3's sole artifact is this spike-results.md section. The actual frontmatter edit is a future task (gated on T4.1 and T4.2 Results being filled in above with `pass` outcomes).

### Result

_(To be filled in if/when the diff is applied. Include: date of application, T4.1 Result reference, T4.2 Result reference, and outcome of the 2-test-query quality comparison per REQ-5 acceptance criteria.)_
