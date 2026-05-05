# Plan: Codex Routing Coverage Extension

## Overview

Extend feature 103's codex reviewer routing to 5 missed dispatch sites. Tighten validate.sh's exclusion guard (FR-2a) and add an allowlist+count assertion (FR-2b). 12 tasks total. All tasks are independent within their phase except for sequential dependencies on baseline capture (T1) and the validate.sh patches sequencing.

## Approach

**Direct-orchestrator execute** — feature 103 is direct prior art with byte-equivalent template available. All tasks are mechanical (text insertion + grep/diff verification). No new agent dispatches needed at implement time other than the standard review loop.

**TDD ordering:** Validate.sh changes (T7-T8) come AFTER preamble insertion (T2-T6) so the new files are present when validate.sh runs the discovery loop. T9 validation runs after all FR-1+FR-2 changes. Baselines (T1) capture state before any FR-1 changes. Manual-checklist tasks (T10-T12) execute after T9 passes.

## Tasks

### Phase 1: Baseline Capture (1 task, sequential prerequisite)

**T1: Capture pre-change baselines**
- Capture pd:security-reviewer dispatch baseline → `/tmp/pd-105-sec-baseline.txt` (per design I-4 a)
- Capture codex-routing-coverage pre-baseline → `/tmp/pd-105-codex-baseline.txt` (per design I-4 b)
- Verify pre-baseline matches the 6 existing files exactly (per design I-4 b acceptance)
- Estimated time: 2 min
- DoD: both /tmp files exist; pre-baseline diff is empty

### Phase 2: Preamble Insertion (5 tasks, parallelizable)

T2-T6 are independent (5 different files, no overlap). Can run in parallel or sequentially. Each task is a near-byte-equivalent copy of the existing `commands/design.md` `## Codex Reviewer Routing` block with site-specific reviewer-name substitutions per design C1.

**T2: Insert codex-routing preamble in commands/secretary.md**
- Insertion position: between line 8 (end of file header description) and line 10 (start of `## Static Reference Tables` H2). Per design R-7 prescriptive position.
- Reviewer name in body: `pd:secretary-reviewer`
- Append R-8 one-sentence note: "Note: Dynamic agent dispatch at Step 7 DELEGATE (line 726) is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site."
- Substitution: "{command|skill|phase}" → "command"
- Estimated time: 5 min
- DoD: AC-1.1 verification snippet passes (extract_codex_section returns non-empty + exclusion clause + heading line ≤ 100)

**T3: Insert codex-routing preamble in commands/taskify.md**
- Insertion position: within first 100 lines, after frontmatter
- Reviewer name in body: `pd:task-reviewer`
- Substitution: "{command|skill|phase}" → "command"
- Estimated time: 5 min
- DoD: AC-1.2 verification snippet passes

**T4: Insert codex-routing preamble in commands/review-ds-code.md**
- Insertion position: within first 100 lines, after frontmatter
- Reviewer name in body: `pd:ds-code-reviewer` (3 dispatch sites at lines 44, 111, 179 — preamble covers all)
- Substitution: "{command|skill|phase}" → "command"
- Estimated time: 5 min
- DoD: AC-1.3 verification snippet passes

**T5: Insert codex-routing preamble in commands/review-ds-analysis.md**
- Insertion position: within first 100 lines, after frontmatter
- Reviewer name in body: `pd:ds-analysis-reviewer` (3 dispatch sites at lines 45, 115, 190)
- Substitution: "{command|skill|phase}" → "command"
- Estimated time: 5 min
- DoD: AC-1.4 verification snippet passes

**T6: Insert codex-routing preamble in skills/decomposing/SKILL.md**
- Insertion position: within first 100 lines, after frontmatter
- Reviewer name in body: `pd:project-decomposition-reviewer`
- Substitution: "{command|skill|phase}" → "skill"
- Estimated time: 5 min
- DoD: AC-1.5 verification snippet passes

### Phase 3: validate.sh Patches (2 tasks, sequential)

**T7: Apply FR-2a patch to validate.sh:871-876**
- Per design I-2: change line 874 from `log_warning` to `log_error` and add `codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))`
- Remove the "(informational only)" parenthetical from the message
- Estimated time: 5 min
- DoD: `grep -n "log_warning.*lacks 'no security review at this phase'" validate.sh` returns 0 matches; `grep -nC 2 "log_error.*lacks 'no security review at this phase'" validate.sh` shows the patched block including the counter increment.

**T8: Insert FR-2b allowlist+count block in validate.sh after line 877**
- Per design I-3: insert the block verbatim (cwd assertion + allowlist + diff + log_error on mismatch + log_info on success)
- Use the alternation-redundancy comment line from the iter 2 design fix
- Estimated time: 5 min
- DoD: `grep -n "Codex routing coverage drift" validate.sh` returns exactly 1 match; the block uses `plugins/pd/references/codex-routing.md\|codex-routing\.md` two-alternation pattern verbatim per spec FR-2b

### Phase 4: Validation (1 task)

**T9: Run validate.sh + AC-3.1 + AC-3.2 + AC-4.1 + AC-4.2**
- Run `./validate.sh` from repo root → expect exit 0
- Verify post-implementation pd:security-reviewer dispatch diff is empty (AC-3.1 acceptance per design I-4 a)
- Run AC-3.2 negative-grep → expect zero matches
- Run AC-4.1 `git diff develop...HEAD --name-only -- plugins/pd/agents/` → expect empty
- Run AC-4.2 diff against existing 6 preamble files → expect zero substantive changes (validate.sh excluded as authorized FR-2a touch)
- Estimated time: 5 min
- DoD: all 5 verifications pass

### Phase 5: Manual Checklist Procedures (3 tasks, after T9 passes)

T10-T12 are evidence-collection tasks per design TD-4. Each pastes terminal output into `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.{N}.txt` (per design I-5 commit-stance: evidence files ARE committed).

**T10 (T-EXEC-AC-2.2): Run AC-2.2 negative-path procedure (FR-2a regression guard)**
- Setup: `TEMP_TEST_DIR=$(mktemp -d -t pd-105-fr2a-test.XXXXXX); trap 'rm -rf "$TEMP_TEST_DIR"' EXIT; cp -R . "$TEMP_TEST_DIR/repo"; cd "$TEMP_TEST_DIR/repo"`
- Mutate: `sed -i.bak '/does NOT dispatch.*pd:security-reviewer/d' plugins/pd/commands/secretary.md && rm -f plugins/pd/commands/secretary.md.bak`
- Sanity check: `! grep -q 'does NOT dispatch.*pd:security-reviewer' plugins/pd/commands/secretary.md || { echo "FAIL: AC-2.2 sed mutation did not take effect"; exit 1; }`
- Run: `./validate.sh; rc=$?` → expect non-zero
- Paste output to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.2.txt`
- Estimated time: 10 min
- DoD: evidence file committed at the documented path containing terminal output showing non-zero exit

**T11 (T-EXEC-AC-2.3): Run AC-2.3 allowlist-drift procedure (both directions)**
- Setup: same temp-clone scaffold as T10
- Direction (a): `echo "See codex-routing.md" > plugins/pd/commands/extra-file.md; ./validate.sh; rc_a=$?` → expect non-zero; cleanup `rm plugins/pd/commands/extra-file.md`
- Direction (b): `mv plugins/pd/commands/taskify.md plugins/pd/commands/taskify.md.disabled; ./validate.sh; rc_b=$?` → expect non-zero; cleanup `mv plugins/pd/commands/taskify.md.disabled plugins/pd/commands/taskify.md`
- Paste output to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.3.txt`
- Estimated time: 10 min
- DoD: evidence file committed at documented path showing both directions produce non-zero exit

**T12 (T-EXEC-AC-3.1): Verify pd:security-reviewer dispatch baseline match (already done in T9)**
- Already executed as part of T9 validation. Document evidence by appending the diff output to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-3.1.txt`
- Estimated time: 2 min
- DoD: evidence file committed showing empty diff against `/tmp/pd-105-sec-baseline.txt`

## Dependency Graph

```
T1 (baselines)
  ↓
T2, T3, T4, T5, T6 (5 preamble insertions; can run in parallel)
  ↓
T7 (FR-2a patch) → T8 (FR-2b allowlist block)
  ↓
T9 (full validation)
  ↓
T10, T11, T12 (manual evidence collection; can run in parallel)
```

## Parallel Execution Groups

- **Group A (5 tasks parallelizable):** T2, T3, T4, T5, T6 — different files, no overlap
- **Group B (3 tasks parallelizable):** T10, T11, T12 — independent evidence collection in temp clones
- **Sequential:** T1 → Group A → T7 → T8 → T9 → Group B

## Risks Inherited from Design

R-1 through R-8 from design.md apply unchanged. R-7 (secretary positioning) is mitigated by T2's prescriptive insertion-position spec. R-8 (dynamic-dispatch loophole) is mitigated by T2's R-8 note.

## Rollback Strategy

If any task fails or validate.sh fails to pass after T9, revert the working tree via `git reset --hard HEAD~N` where N is the commit count for this feature branch. Branch deletion via `/pd:abandon-feature` if rollback is permanent.
