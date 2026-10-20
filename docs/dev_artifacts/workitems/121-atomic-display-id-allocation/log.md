<!-- Append-only history of 121-atomic-display-id-allocation. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-07-10 11:07+00:00 note entity_created
Status: closed (legacy)
- kind: feature
- name: Atomic Display Id Allocation
- status: planned

## 2026-07-10 15:26+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: planned
- new_status: archived

## 2026-07-10 16:00+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: archived
- new_status: planned

## 2026-07-11 00:00+00:00 review legacy — Specify Phase (2026-07-11)
Status: closed (legacy)
### Spec review — iteration 1 (pd:spec-reviewer, opus, fresh) — approved=FALSE, 1 blocker + 3 warnings + 4 suggestions, ALL ABSORBED
Reviewer verified every file:line claim at source (incl. correcting nothing — the spec had already repointed the PRD's stale `:9360` to `:9310`). Findings:
- **Blocker (FIXED by pulling IN, then re-decided at iter-2):** the spec's own SC2 audit grep surfaced `create-project.md:26-31` — a project-kind filesystem allocator FR-5's "all kinds" covers; spec neither rewired nor scoped it out.
- **W1 (FIXED):** FR-5's "name/slug" has two halves; the slug half (`"!!!"` → empty slug) was routed to a design lean that could resolve against rejection. Decoupled into an independent SC1 pin.
- **W2 (FIXED):** cross-workspace independence branch had no distinct named test (symmetric-branch guardrail, 130 class). Named in SC1.
- **W3 (FIXED):** the v2 allocator's compose-mode borrowed `append_event`'s analogy, but INSERT-only composition does not transfer to READ-MODIFY-WRITE (DEFERRED caller → `SQLITE_BUSY_SNAPSHOT` on lock upgrade, no retry). Write-lock precondition made contractual + contention-tested (SC4).
- **S1-S4 (ALL ABSORBED):** decomposing single-slugify pin (local prose rules diverge from `_slugify` on hyphen-boundary truncation → topological remap breakage); `entity_server.py:580-581` truthy-guard subsumption; bootstrap safety argument; SC5 zero-prior-events pin.

### Spec review — iteration 2 (pd:spec-reviewer, opus, fresh) — approved=FALSE, 2 blockers + 1 warning + 2 suggestions, ALL ABSORBED
All four iteration-1 fixes verified at source and held. NEW findings — both introduced by iteration 1's own fixes:
- **B1 (FIXED):** SC2's bare-`"highest"` audit grep under-enumerated the sanctioned set by 5 prose files (secretary.md ×2, advisor files, test-specialist template) — unpassable without forbidden scope creep. Rewritten to allocation-specific phrasings (`"Find highest number"`, backticked ``"highest `NNN`"``) + positive presence pins.
- **B2 (FIXED by scoping OUT):** iteration 1's create-project pull-IN would deterministically re-mint P001 — the shared v1 bootstrap seeds by `re.match(r"^(\d+)", entity_id)` (database.py:9368) and projects register as `P`-leading ids (feature_lifecycle.py:275-278, documented outside the numeric-prefix contract), so `max_seq` stays 0. Reviewer also caught the boundary text misdiagnosing the cause as DB-coverage (it is id FORMAT). Scoped OUT with the technical rationale; #054(c) cutover-checklist item filed in docs/backlog-manual.md; D-5 added (allocate tool rejects `entity_type="project"` loudly until 132).
- **W (FIXED):** workspace-resolution seam — mirroring `register_entity`'s auto_id path would collapse context-less workspaces to `_UNKNOWN_WORKSPACE_UUID` (entity_server.py:575, database.py:5880-5881) and SHARE a sequence, failing SC1's independence pin. Contract pinned to the RESOLVED workspace_uuid.
- **S1 (FIXED):** SC2 decomposing clause was absence-only — positive presence-grep added (symmetric with create-feature).
- **S2 (FIXED):** "no sequence consumed" pins made structural — standalone `_slugify` pre-check BEFORE any `generate_entity_id` call (it consumes the seq at :62 BEFORE slugifying at :63).

### Spec review — iteration 3 (pd:spec-reviewer, opus, fresh) — approved=TRUE, 0 blockers, 1 warning + 1 suggestion fixed post-approval
Every iteration-2 fix source-verified: out-of-scope rationale "airtight"; SC2 greps non-zero now → 0 after deletion, no over-match; D-5 ↔ #054(c) bidirectionally coherent; `_slugify("!!!")` → `""` traced; no scope leaks to 132/120/122. Post-approval absorptions:
- **W (FIXED):** feature-kind bootstrap DB-completeness is load-bearing AND guaranteed-live (live sequences table has zero feature rows — fires on FIRST post-rewire allocation per workspace). Boundary now forces design to pick a stance: pre-allocation sanity assertion vs explicit 132-gate delegation.
- **S (FIXED):** plumbing leaning added — call `next_sequence_value(workspace_uuid=..., entity_type=...)` directly (kwarg exists at :9315); passing a workspace_uuid through `generate_entity_id`'s `project_id` positional would hit the `project_id_legacy` JOIN and raise (:5882-5883).

**Skeptic gate result: PASS at iteration 3 of 3.**

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=FALSE (1 blocker + 1 warning), round 2 approved=TRUE (0 issues)
- **Blocker (FIXED):** the iteration-3 post-approval plumbing leaning contradicted item 1's unrevised "via the existing generate_entity_id" headline — two answers to the spec's most concrete implementation question, in one paragraph (the half-swept-restatement class, self-inflicted). Headline rewritten to ONE mechanism (direct `next_sequence_value` + `_slugify`, format-compatible, explicitly NOT calling `generate_entity_id`); reviewer round 2 swept SC1/D-3/Problem restatements — none imply the call.
- **Warning (FIXED):** Verification Approach misattributed `_reset_ddl_registry` + the 30-trial harness to `test_events.py` — they live in `test_schema_v2.py` (:90, :708-709); only compose-vs-standalone (:263) is a `test_events.py` idiom. Attribution corrected; round 2 spot-checked all three line cites at source.

**SPECIFY PHASE: COMPLETE.** (skeptic PASS iter 3; phase gate PASS round 2.)

## 2026-07-11 00:00+00:00 review-2 legacy — Design Phase (2026-07-11)
Status: closed (legacy)
### Design review — iteration 1 (pd:design-reviewer, opus, fresh) — approved=FALSE, 1 blocker + 3 warnings + 3 suggestions, ALL ABSORBED
Dark-track decisions (D5-D8) verified clean at source (INSERT/UPDATE columns constructible vs schema_v2 DDL; append_event call shape; with_retry signature; in_transaction reasoning). Findings:
- **Blocker (FIXED):** D2's "tool wrapper catches ValueError → envelope" could never fire — `_process_register_entity` swallows ALL non-OperationalError exceptions into a PLAIN string (server_helpers.py:319-320, docstring "Never raises" :240). Rewritten: envelope pre-check at the TOP of the register tool body, REPLACING the :580-581 truthy guard, BEFORE the auto_id branch (also closes the sequence-burn the guard deletion would have caused); server_helpers untouched; upsert verified to have NO MCP surface.
- **W1 (FIXED):** spec "ALL write paths" vs design's update_entity carve-out — resolved by pulling update_entity's name branch (:7393) IN + spec item-3/SC3 reconciliation (absent ≠ blank).
- **W2 (FIXED):** degraded-startup risk note claimed an `_UNKNOWN` fallback the code never performs — D1 gains an `if not _workspace_uuid:` workspace_unresolved envelope guard.
- **W3 (FIXED):** inventory named nonexistent `plugins/pd/mcp/tests/test_entity_server.py` — real module is `hooks/lib/entity_registry/test_entity_server.py`.
- **S1-S3 (ABSORBED):** in_transaction wording; auto_id no-consumption (folded into blocker fix); FR-11 registry gains nameFrom/nameTo.

### Design review — iteration 2 (pd:design-reviewer, opus, fresh) — approved=FALSE, 1 blocker + 1 warning + 2 suggestions, ALL ABSORBED
All iter-1 fixes verified holding; update_entity callers swept (none pass blank names). Findings:
- **Blocker (FIXED):** the iter-1 update_entity pull-in was HALF-SWEPT — Error Handling still declared update_entity "outside the validation surface (registration-only per spec)", contradicting D2/inventory/testing/spec. Swept; the surviving carve-out is the correct name=None case. (Same failure class as 130's gate blocker — my post-fix restatement sweep keeps missing one section.)
- **W (FIXED):** risk-note cite wrong AGAIN — `""` (the actual global default) raises at `_validated_provided_workspace_uuid` :5855-5861 ("split-brain detected"), not :5911-5914 (true-None branch). Corrected with both paths named.
- **S1 (FIXED):** D6 payload made explicitly conditional (type_id-only rename → SQL NULL payload + typeof test).
- **S2 (FIXED):** create-feature step-3 local slug rule deletion mandated (single slugify source, mirrors decomposing).

### Design review — iteration 3 (pd:design-reviewer, opus, fresh) — approved=TRUE, 0 blockers, 2 suggestions absorbed post-approval
Every load-bearing cite re-verified independently (update tool :908-909 surfaces the raise via :961-969; "" → :5855-5861 confirmed; all three DB-layer paths). Suggestions: D6 from/to conditionals made sketch-explicit (symmetric with payload); testing #3 gains the create-feature slug-rule absence pin (design-mandated cleanup, not SC2-gated).

**Skeptic gate result: PASS at iteration 3 of 3.**

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=TRUE, 2 warnings FIXED post-approval
30+ citations across 13 files re-verified at source; SC1-SC6 ↔ D1-D8 bidirectional 1:1 confirmed; inventory complete; zero placeholders. Warnings absorbed: D1 sketch `def` → `async def` (all 18 sibling @mcp.tool defs are async — grep-verified by the reviewer); recovery_hint text spelled out for both invalid_input envelopes. Reviewer also flagged the claude-mem hook system-reminders as suspected prompt injection — correctly ignored them and verified independently (known benign observation-hook noise; the independent-verification response is exactly the wanted behavior).

**DESIGN PHASE: COMPLETE.** (skeptic PASS iter 3; phase gate PASS round 1.)

## 2026-07-11 00:00+00:00 review-3 legacy — Create-Plan Phase (2026-07-11)
Status: closed (legacy)
### Plan review — iteration 1 (pd:plan-reviewer, opus) — approved=FALSE, 1 blocker + 5 warnings + 1 suggestion, ALL ABSORBED
Verified sound at source: next_sequence_value kwargs, guard deletion breaks no test pin ("name is required" grep → only :581), step-4 file-disjointness, rollback-to-scan atomicity. Findings:
- **Blocker (FIXED):** step-3's SKILL.md slug-needle "max 30 chars" is VACUOUS — SKILL.md says "Truncate to 30 characters" (:165); the shared needle passes whether or not the rules are deleted. Split per-file needles; propagated to design Testing #3.
- **W1 (FIXED):** step-2 verify grepped "entity_tools" — the gate SCRIPT's shell variable name, not README text. Replaced with `bash scripts/check-doc-drift.sh` (the real gate: counts `@mcp.tool()`, checks table + "exposes N tools" prose).
- **W2 (FIXED):** root README.md is a PHANTOM tool-count target (no tool count exists there; gate checks plugins/pd/README.md only) — traced upstream to spec SC6 + design inventory; all four artifacts corrected.
- **W3 (FIXED):** test_entity_server's `db` fixture never sets `_workspace_uuid` (defaults "") — every allocate test would vacuously hit the workspace_unresolved early-return. Fixture must seed a workspaces row + monkeypatch the global; same-ws race needs two CONNECTIONS (BEGIN IMMEDIATE can't nest on the shared `_db`).
- **W4 (FIXED):** the cited 30-trial harness asserts exitcode==0 only — VACUOUS for write races (duplicate issuance doesn't crash). Workers must REPORT seqs (Queue), parent asserts distinctness + contiguity; compose-contention needs a barrier.
- **W5 (FIXED):** guard needles undercounted — 119's precedent set is THREE-way incl. relative `from .events import`; the relative form is exactly how database.py would wire display at 132. Three needles + relative-form offender seeding everywhere.
- **S (FIXED):** rollback direction — revert step 3 before step 2.

### Task review — iteration 1 (pd:task-reviewer, sonnet) — approved=FALSE, 1 blocker + 2 warnings + 5 suggestions, ALL ABSORBED
All line anchors spot-verified current. Findings: **Blocker** — same root-README phantom (independent convergence with plan W2). **W1** — backslash-escaped backticks inside single-quoted grep (implementation-defined on BSD) → backslashes dropped. **W2** — task-4 verify dropped plan's red-then-green non-vacuity callout → restored. **S1-S5** — inventory "10 rows" → name-based 11 files; create-feature renumber clause vacuous (step 3 is last) → dropped; SKILL.md surviving steps 5-7 DO need renumbering → added; sibling-count comment 18→19; D7 traceability note (bare int, no format composition in display.py).

### Relevance-verifier — round 1 approved=FALSE (2 blockers + 2 warnings), ALL FIXED; round 2 approved=TRUE clean
- **B1 (FIXED):** needle-count incoherence — spec item-6/SC6 + design Testing #6 + plan Risks still said "both" spellings while D8/plan-step-4/tasks said THREE (my sweep missed three restatements — the half-swept class AGAIN). All artifacts now say three; verifier round 2 swept all 13 remaining "both" occurrences — none imply 2 spellings.
- **B2 (FIXED):** plan step-5 "10 rows" stale vs design's 11-row inventory — plan now names the 11 files (identical order to tasks).
- **W1 (FIXED):** tasks' "design's stale 18" rationale was itself stale (design already said 19). **W2 (FIXED):** the single-quoted grep forms still carried copied backslashes — dropped; spec/design's double-quoted+backslash forms verified correct for double quotes and mutually byte-identical. Cites tightened: events.py FR-11 block :18-28; check-doc-drift :40-47.

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=TRUE, 1 warning FIXED post-approval
Extensive source spot-verification held on every checked cite (incl. 19 = decorators = table rows = prose; the 3-way needle precedent; the vacuous-harness claim; the fixture gap). Warning absorbed: task-2 verify now runs `bash scripts/check-doc-drift.sh` directly (plan prescribed it; tasks had deferred the docs-sync check to task 5).

**CREATE-PLAN PHASE: COMPLETE.** (plan-reviewer 1 iter; task-reviewer 1 iter; relevance-verifier PASS round 2; phase gate PASS round 1.)

## 2026-07-11 00:00+00:00 review-4 legacy — Implement Phase (2026-07-11)
Status: closed (legacy)
### Execution (5 tasks, serial; pd:implementer sonnet ×3 + orchestrator ran tasks 3 & 5)
- Task 1 (5fee50c7): DB blank-name validation ×3 paths via shared `_BLANK_NAME_ERROR` constant (sanctioned deviation — identical-message contract by construction); 8 tests RED(6 DID-NOT-RAISE)→GREEN; suite 1440.
- Task 2 (c1440871): allocate_entity_id per D1 sketch (guard order exact); register truthy guard → whitespace-aware envelope pre-check (sequence-burn closed); README 19→20; 12 tests red-first (AttributeError/JSONDecodeError evidence); doc-drift OK entity_tools=20.
- Task 3 (2f47c8da, orchestrator): both scan allocators deleted; STOP-on-error + drift cross-check landed; Stage 5 renumbered; all SC2 greps green.
- Task 4 (44c11873): dark display.py + rename_entity; TRIPLE red evidence (test-file ImportError; the guard ITSELF caught display.py pre-allowlisting — proving non-vacuity incidentally; teeth red pre-needles). 17+3 tests; suite 1472.
- Task 5 (orchestrator): full suite 3541 passed / 3 skipped (+40 = exactly the new tests); validate.sh 0 errors / 23 warnings; hooks 67/67 + 5/5; diff = 11-file inventory + docs + sanctioned #054(c) edit.

### Test deepening (pd:test-deepener, sonnet) — 8 tests, 3 empirically mutation-verified (b634b998)
Kind-gate case/whitespace slips PINNED as behavior ("Project"/" project " mint distinct kind sequences — literal gate per D-5); seq>999 width growth; truncation through the tool path; OperationalError propagates unhandled (pinned); cross-(ws,kind) UPDATE isolation (WHERE-drop kill); rename updated_at advance — a mutation INVISIBLE to all 9 pre-existing sibling rename tests. Consciously-skipped list included envelope exact-key equality (already full-dict ==).

### 3-reviewer battery — iteration 1: ALL THREE APPROVED (6th feature, 5th consecutive clean battery — basis: all-approved-at-iteration-1 across 118, 129, 119, 130, 121)
- **implementation-reviewer (opus): approved=TRUE, 2 nits both ADJUDICATED acceptable-by-design.** Every SC walked at file:line with non-vacuity checks (no-consumption asserts genuinely SELECT the sequences table; Queue-harness contiguity assert real; rollback-injection snapshot proves the UPDATE applied then vanished). Deepener findings ruled: kind-gate literal is D-5-conformant and the miss-path is a harmless orphan sequence (NOT the P001 class, which IS gated); unhandled OperationalError is design-sanctioned loud-not-silent (arguably better than siblings' swallow-to-envelope). Independent CPython-doc verification of autocommit/in_transaction semantics.
- **code-quality (sonnet): approved=TRUE, 1 warning FIXED + 4 nits (1 fixed, 3 recorded).** Warning (11779af9): the MCP envelope message was a hand-typed duplicate of `_BLANK_NAME_ERROR` — the author-restated-literal class IN CODE; now references the constant. Nit fixed: "(19 today)" magic-number comment dropped. Recorded: envelope-builder extraction (design-sketch-shaped, readable), update_entity guard placement (stylistic), SKILL.md sub-bullet density (both files clear).
- **security (opus): approved=TRUE, 1 nit RECORDED.** All six vectors verified at installed source: every SQL value a bound `?` (incl. _rename's fixed-allowlist SET clauses); slug alphabet strictly [a-z0-9-] → no traversal/shell/git-hostile chars in entity_id (feeds mkdir/branch); _slugify regexes linear (ReDoS-checked); payload json.dumps/loads never eval; envelopes reflect no caller input. Nit: no name length cap — defense-in-depth only under the local threat model.

### 360° relevance-verifier (pd:relevance-verifier, sonnet) — approved=TRUE, 0 blockers, 0 reconciliations
All 4 deviations adjudicated ADDITIVE (shared constant STRENGTHENS design's one-contract requirement; MCP constant-reference reinforces spec's no-fork rule; _rename/@with_retry("entities") is the correct table-appropriate extension; comment cosmetic). Reverse sweep via 3 converging static proxies → zero stray footprint. doc-drift entity_tools=20 independently recomputed. Warnings: dynamic figures not re-runnable by the verifier (orchestrator's own runs stand); .meta.json phase lag (expected pre-completion state).

### Process Notes (retro Tune-5 convention)
- **claude-mem observation-hook injection noise at scale:** SIX separate subagents this feature (design gate, relevance rounds, both implementers, deepener, quality reviewer) independently flagged the PreToolUse:Read observation reminders as suspected prompt injection — including one asserting a FABRICATED blocker ("nameFrom/nameTo missing from events.py") that two agents disproved at source. Every agent correctly ignored the claims and verified independently (the wanted behavior), but the noise now costs a paragraph of every report and one fabricated-claim disproof per dispatch. Candidate backlog item: suppress or clearly label the hook's output in subagent contexts.

**IMPLEMENT PHASE: COMPLETE.** (5 tasks; deepener 3/3 empirical kills; battery 3/3 approved iteration 1; 360° PASS round 1; QA: 3541 full suite, validate 0 errors, hooks 67/67, doc-drift entity_tools=20.)

## 2026-07-11 09:49+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: planned
- new_status: active

## 2026-07-11 10:39+00:00 phase start -> specify
Status: closed (legacy)

## 2026-07-11 10:40+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 3
"{\"skeptic\": \"opus x3 fresh \u2014 iter1 FALSE (1 blocker: project-kind scan unscoped; 3 warnings incl. compose-mode lock-upgrade + slug-half decoupling; 4 suggestions), iter2 FALSE (2 blockers BOTH introduced by iter1 fixes: bare-highest grep unpassable; project pull-IN would re-mint P001 via regex-blind bootstrap database.py:9368 vs P-leading ids \u2014 scoped OUT with #054(c) filed + D-5 reject-guard), iter3 TRUE (0 blockers; bootstrap-completeness warning + direct-plumbing suggestion absorbed post-approval)\", \"phase_gate\": \"sonnet round1 FALSE (my post-approval plumbing edit contradicted the unrevised via-generate_entity_id headline \u2014 half-swept restatement in ONE paragraph; + harness idioms misattributed to test_events.py vs test_schema_v2.py) round2 TRUE 0 issues, all line cites spot-checked\", \"shape\": \"two-track live/dark mirroring 118/119; live: MCP allocate tool + create-feature/decomposing scan kills + DB-layer name/slug validation; dark: v2 next_display_seq (write-lock precondition contractual) + rename-with-event helper + guard extension\"}"

## 2026-07-11 11:23+00:00 phase specify -> design
Status: closed (legacy)

## 2026-07-11 11:23+00:00 review design — legacy
Status: closed (legacy)
Iterations: 3
"{\"design_skeptic\": \"opus x3 fresh \u2014 iter1 FALSE (blocker: MCP envelope translation point nonexistent, _process_register_entity swallows to plain string server_helpers.py:319-320 \u2192 tool-level pre-check replacing :580-581 guard; update_entity pulled into validation; workspace_unresolved guard; test path fix), iter2 FALSE (blocker: Error Handling half-swept the update_entity pull-in \u2014 same class as 130's gate catch; risk-note cite wrong again '' \u2192 :5855-5861 split-brain not :5911-5914), iter3 TRUE 0 blockers (2 suggestions absorbed: D6 from/to conditional symmetry, create-feature slug-rule absence pin)\", \"phase_gate\": \"sonnet round1 TRUE \u2014 30+ cites re-verified across 13 files, SC\u2194D bidirectional 1:1; 2 warnings absorbed post-approval (async def convention 18/18 siblings, recovery_hint texts spelled); reviewer independently flagged+ignored claude-mem hook noise correctly\", \"decisions\": \"D1 direct next_sequence_value(workspace_uuid) MCP tool w/ kind-gate; D2 three-path DB validation + tool pre-check; D3 id_generator untouched (001-unnamed pinned); D4 rewires incl. step-3 slug-rule deletions; D5 dark display.py MAX+update-all convergence, write-lock precondition contractual; D6 rename+event one txn, camelCase registry keys; D7 {seq}-{slug} stays, F-1042 is rendering; D8 guard allowlist\"}"

## 2026-07-11 12:14+00:00 phase design -> create-plan
Status: closed (legacy)

## 2026-07-11 12:14+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 1
"{\"plan_review\": \"opus iter1 FALSE\u2192fixed (blocker: vacuous SKILL.md slug needle 'max 30 chars' never in file; W: vacuous entity_tools grep, root-README phantom target, fixture never sets _workspace_uuid \u2192 vacuous-green risk, exitcode-only harness vacuous for write races, guard needles 2-vs-3)\", \"task_review\": \"sonnet iter1 FALSE\u2192fixed (blocker: root-README phantom converged; backtick escaping; red-then-green callout; renumbering; D7 traceability)\", \"relevance\": \"round1 FALSE (needle-count both-vs-THREE across 3 artifacts \u2014 my half-sweep again; stale 10-rows) \u2192 round2 TRUE clean, all 13 residual 'both' occurrences adjudicated\", \"phase_gate\": \"round1 TRUE, 1 warning absorbed (task-2 runs check-doc-drift.sh directly)\", \"shape\": \"5 serial tasks: DB validation \u2192 MCP tool+pre-check+README \u2192 command/skill rewires \u2192 dark display.py+guard \u2192 integration QA\"}"

## 2026-07-11 13:43+00:00 phase create-plan -> implement
Status: closed (legacy)

## 2026-07-11 13:44+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 1
"{\"tasks\": \"5 serial (5fee50c7 DB validation shared-constant, c1440871 MCP tool + envelope pre-check, 2f47c8da scan-allocator kills, 44c11873 dark display.py TRIPLE-red evidence, task-5 QA 3541 passed)\", \"deepener\": \"8 tests 3 empirical kills incl. rename updated_at mutation invisible to all 9 sibling tests; kind-gate case-slips PINNED as D-5-conformant behavior\", \"battery\": \"iteration 1 ALL approved \u2014 5th consecutive clean (118,129,119,130,121). impl (opus): 2 nits adjudicated acceptable-by-design w/ CPython-doc verification. quality (sonnet): 1 warning FIXED (MCP message was hand-typed duplicate of _BLANK_NAME_ERROR \u2014 restated-literal class in code, now references constant, 11779af9) + magic-number comment dropped, 3 nits recorded. security (opus): all 6 vectors safe at source (bound params incl. dynamic SET allowlist, slug alphabet, linear regexes, no reflection), 1 defense-in-depth nit recorded\", \"relevance_360\": \"approved 0 blockers 0 reconciliations \u2014 all 4 deviations additive; zero stray footprint via 3 converging static proxies\", \"process_note\": \"claude-mem injection noise flagged by 6 subagents incl. one fabricated blocker disproven twice \u2014 backlog candidate\"}"

## 2026-07-11 22:21+08:00 qa legacy .qa-gate.json
Status: closed (legacy)
```json
{
  "feature": "121-atomic-display-id-allocation",
  "gate_date": "2026-07-11",
  "lanes": {
    "code_adversarial": {
      "verdict": "PASS",
      "findings": {
        "HIGH": 0,
        "MED": 1,
        "LOW": 1
      }
    },
    "artifact_claims": {
      "verdict": "PASS",
      "findings": {
        "HIGH": 0,
        "MED": 1,
        "LOW": 1
      }
    },
    "regression_merge": {
      "verdict": "PASS",
      "findings": {
        "HIGH": 0,
        "MED": 1,
        "LOW": 1
      }
    }
  },
  "dispositions": {
    "MED_dark_rename_blank_fields": "FIXED at gate \u2014 rename_entity strip() guards (blank name/type_id -> ValueError before any I/O) + 3 tests; the FR-5 vector on the v2 rename path, live at 132, missed by battery+360+deepener; execution-probe find",
    "MED_retro_fabricated_cite": "FIXED \u2014 facilitator's :900 cite was fabricated (unrelated body code); corrected with explicit marker; two real sites (:880/:1900) stand",
    "MED_test_stray_pollution": "MITIGATED+FILED \u2014 plugins/**/.claude/ gitignore line (deliberately not root .claude/); root cause = pre-existing feature-108 writer, backlog #066",
    "LOW_all": "see .qa-gate-low-findings.md sidecar; phantom-kind sequences + cluster-label informality + tracked pollution instance recorded"
  },
  "verification": {
    "full_suite_post_fix": "3552 passed, 3 skipped",
    "validate_sh": "0 errors, 23 warnings (baseline)",
    "hook_tests": "67/67 + 5/5",
    "merge_base": "9c4cacbe == develop HEAD (no drift; clean merge)",
    "execution_probes": "4-proc x25 allocation contention distinct+contiguous both paths; bootstrap 001..133 -> 134; '0121' -> 121 decimal"
  },
  "final_verdict": "PASS \u2014 merge approved after fix-at-gate items"
}
```

## 2026-07-11 14:23+00:00 phase implement -> finish
Status: closed (legacy)

## 2026-07-11 14:23+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: active
- new_status: completed

## 2026-07-11 14:23+00:00 review finish — legacy
Status: closed (legacy)
Iterations: 1
"{\"qa_gate\": \"3 adversarial lanes ALL PASS with fix-at-gate MEDs \u2014 code lane's execution probe found dark rename_entity accepting blank display fields (FR-5 vector on the v2 path, live at 132, missed by battery+360+deepener) FIXED w/ guards+3 tests; artifact lane caught a FABRICATED line-cite in the facilitator retro draft (corrected+marked); regression lane found pre-existing nested-.claude test pollution (gitignore mitigation + #066 filed)\", \"retro\": \"campaign-high 10 blockers, 50% self-inflicted \u2014 fresh-vs-self-inflicted tagging adopted; CLAUDE.md scope-widening + mechanical-sweep guardrails; retro corrected my briefing figures a second consecutive feature\", \"merge\": \"641a57be --no-ff; develop 3552 passed post-merge; pushed; branch deleted\", \"backlog\": \"#054(c) cutover rewire, #056 skipped_phases addendum, #065 claude-mem noise, #066 stray writer\"}"
