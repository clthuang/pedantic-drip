# Tasks: Feature 094 — Pre-Release Adversarial QA Gate

**Direct-orchestrator execution** (per 091/092/093 surgical template) — tight scope (4 files, ~80 prose + ~35 test LOC + new ~180-line doc) lands in a single atomic commit. Full task detail co-located in `plan.md` (Implementation Order + AC Coverage Matrix); this file is the compact task index.

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| T1 | Insert Step 5b into finish-feature.md | `plugins/pd/commands/finish-feature.md` | none |
| T2 | Create qa-gate-procedure.md (NEW) | `docs/dev_guides/qa-gate-procedure.md` | T1 (cross-references) |
| T3 | Update retrospecting/SKILL.md (FR-7b sidecar fold) | `plugins/pd/skills/retrospecting/SKILL.md` | none |
| T4 | Add 3 test-hooks anti-drift functions | `plugins/pd/hooks/tests/test-hooks.sh` | T1, T2 (both files must exist) |
| T5 | Quality gates (validate.sh + test-hooks.sh) | — | T1, T2, T3, T4 |
| T6 | Dogfood self-test (3 phases) | `retro.md` | T5 |

T1, T3 are independent — could run parallel, but direct-orchestrator runs sequentially for atomicity.

## T1 — Insert Step 5b

**File:** `plugins/pd/commands/finish-feature.md`  
**Action:** Insert new "Step 5b: Pre-Release Adversarial QA Gate" between Step 5a end and Step 5a-bis start (currently ~lines 373/374).

**Inline content (~50 lines):**
1. H2 heading: `## Step 5b: Pre-Release Adversarial QA Gate`
2. YOLO exception comment: `# YOLO exception: HIGH findings always exit non-zero; gate never prompts; MED/LOW auto-file silently.`
3. Dispatch instruction with literal phrase: "In a single Claude message, **dispatch all 4 reviewers in parallel** using the Task tool. Do NOT dispatch sequentially."
4. 4-row dispatch table per design FR-2 (subagent_type, model, output shape).
5. Severity rubric (AC-5 + AC-5b inline):
   - HIGH: `severity == "blocker"` OR `securitySeverity in {"critical", "high"}` (with test-deepener narrowed remap clause)
   - MED: `severity == "warning"` OR `securitySeverity == "medium"`
   - LOW: `severity == "suggestion"` OR `securitySeverity == "low"`
6. Decision tree: HIGH → block (FR-6); MED → file to backlog (FR-7a); LOW → file to sidecar (FR-7a).
7. References: spec-absent fallback string `no spec.md found — review for general defects against the diff; do not synthesize requirements` (AC-15); diff token `{pd_base_branch}...HEAD` (AC-16); idempotency cache `.qa-gate.json` (AC-6); sidecar `.qa-gate-low-findings.md` (AC-12).
8. Pointer: "See `docs/dev_guides/qa-gate-procedure.md` for full dispatch prompts, JSON parse contract, severity bucketing logic, override path, and per-feature backlog sectioning."

**DoD:** all 10 grep assertions in `test_finish_feature_step_5b_present` pass + `wc -l < plugins/pd/commands/finish-feature.md` < 600.

## T2 — Create qa-gate-procedure.md (NEW)

**File:** `docs/dev_guides/qa-gate-procedure.md`  
**Action:** Create new file with 12 sections (§1..§12) per plan.md Step 2.

**Critical content (per design TDs):**
- §3 must contain literal `import sys, json, re` (TD-8 JSON parse heredoc — full snippet from design TD-8 lines 178-230).
- §4 must contain `normalize_location` + `cross_confirmed` predicates (design I-6).
- §5 must contain regex `^- \*\*#[0-9]{5}\*\*` for backlog ID extraction (TD-7).
- §5 must contain section heading template `## From Feature {feature_id} Pre-Release QA Findings ({date})`.
- §7 must contain atomic-rename pseudocode `tmp file + mv` (TD-5).
- §8 must contain awk pipeline `awk "/^## Override ${last_n} /,0"` for per-section trimmed-count (TD-3).
- §11 must document >2000 LOC threshold + file-list-summary fallback (R-7).
- §12 must document override-storm warning trigger (R-1).

**DoD:**
- File exists at correct path
- `grep -c '^##\s§[0-9]+' docs/dev_guides/qa-gate-procedure.md` >= 12
- `grep -q 'import sys, json, re' docs/dev_guides/qa-gate-procedure.md` exit 0
- `grep -q 'FR-3\|FR-8\|FR-9' docs/dev_guides/qa-gate-procedure.md` exit 0 (test_qa_gate_procedure_doc_exists check)

## T3 — Update retrospecting/SKILL.md (FR-7b)

**File:** `plugins/pd/skills/retrospecting/SKILL.md`  
**Action:** Add a step to the existing skill (anywhere before retro.md final write) that:
1. For each sidecar in `{feature_dir}/`: `.qa-gate-low-findings.md` and `.qa-gate.log`:
   - If exists: read content, append under `## Pre-release QA notes` H2 in `retro.md` (create section if absent), with sub-heading `### LOW findings` for the .md file and `### Audit log` for the .log file, then `rm` the sidecar.
2. Note: each sidecar may exist independently (per FR-7b design note).
3. If neither present: skip silently (no-op).

**Size:** ~15 lines added.

**DoD:**
- `grep -q 'qa-gate-low-findings\.md' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'qa-gate\.log' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'Pre-release QA notes' plugins/pd/skills/retrospecting/SKILL.md` exit 0

## T4 — Add 3 test-hooks functions

**File:** `plugins/pd/hooks/tests/test-hooks.sh`  
**Action:** Add 3 functions per plan.md Step 4 (full snippet there) and register them in the runner section. Functions:
1. `test_finish_feature_step_5b_present` (10 grep assertions per design C4)
2. `test_finish_feature_under_600_lines` (file size constraint per AC-18)
3. `test_qa_gate_procedure_doc_exists` (procedure doc existence + FR markers)

**DoD:**
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0
- New PASS count = baseline + 3

## T5 — Quality gates

```bash
./validate.sh                                    # exit 0
bash plugins/pd/hooks/tests/test-hooks.sh        # exit 0, +3 tests
```

**DoD:** Both green; total test count = baseline + 3.

## T6 — Dogfood self-test

Per plan.md Step 6 — three phases:

**(a) Self-dispatch:** invoke 4 reviewers manually (via Task tool) against current branch diff. Document outcome in retro.md "Manual Verification" section. Verify gate would NOT have blocked (or correctly remapped self-references).

**(b) Synthetic-HIGH injection:** scratch branch with synthetic HIGH (e.g., `LIMIT -1` SQL or shell-injection f-string). Re-dispatch reviewers. Verify ≥1 reviewer flags HIGH. Discard scratch branch.

**(c) Cleanup:** verify no synthetic injection leaked to feature branch.

**DoD:** All 3 phases documented in `docs/features/094-pre-release-qa-gate/retro.md` "Manual Verification" section before merge.

## Manual ACs (per design.md Manual Verification Gate)

11 ACs (AC-5, AC-5b, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-13, AC-17, AC-19) require manual confirmation during T6 dogfood. Each tracked as a checkbox in retro.md "Manual Verification" section per design lines 460-490.
