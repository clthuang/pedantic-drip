# Design: Codex Routing Coverage Extension

## Prior Art Research

**Status:** Skipped per YOLO mode (domain-expert path). Feature 103 (`feature/103-codex-reviewer-routing`, merge commit `1e5b06a`) is direct prior art and is already canonicalized in `plugins/pd/references/codex-routing.md`. The 6 existing preamble sites (`commands/specify.md`, `commands/design.md`, `commands/create-plan.md`, `commands/implement.md`, `commands/finish-feature.md`, `skills/brainstorming/SKILL.md`) provide byte-equivalent templates for the 5 new preambles.

## Architecture Overview

This feature is a coverage extension, not a behavioral change. The architecture is identical to feature 103: dispatching commands/skills include a `## Codex Reviewer Routing` preamble that points readers (and through implicit contract, the orchestrator) to `plugins/pd/references/codex-routing.md`. The orchestrator's existing logic for "if codex installed, route via codex; else fall back to pd reviewer Task" is unchanged. Validate.sh's existing exclusion guard is tightened (FR-2a) and extended (FR-2b) to cover the 5 new sites.

```
┌─────────────────────────────────────────────────────────────────────┐
│  11 Dispatch Sites (existing 6 + new 5)                             │
│                                                                     │
│  Each contains "## Codex Reviewer Routing" preamble pointing to:    │
│                                                                     │
│         plugins/pd/references/codex-routing.md                      │
│                                                                     │
│  Preamble body: byte-equivalent copy from design.md template,       │
│  with site-specific adjustments to reviewer-type list +             │
│  command/skill placeholder text only.                               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  validate.sh: Codex Reviewer Routing exclusion guard                │
│                                                                     │
│  Existing (line 856-878):                                           │
│  - Dynamic discovery via grep -rl                                   │
│  - Strict error (line 868) when file dispatches security-reviewer   │
│    AND lacks exclusion regex match                                  │
│  - Soft warning (line 874) when file does NOT dispatch              │
│    security-reviewer AND lacks "no security review at this phase"   │
│    indicator                                                        │
│                                                                     │
│  FR-2a change: line 874 log_warning → log_error                     │
│  FR-2b addition: allowlist+count assertion (exact 11 files)         │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### C1: Five Preamble Insertions

Five new `## Codex Reviewer Routing` sections inserted in:
- `plugins/pd/commands/secretary.md` (dispatches `pd:secretary-reviewer` at line 644)
- `plugins/pd/commands/taskify.md` (dispatches `pd:task-reviewer` at line 80)
- `plugins/pd/commands/review-ds-code.md` (dispatches `pd:ds-code-reviewer` at lines 44, 111, 179)
- `plugins/pd/commands/review-ds-analysis.md` (dispatches `pd:ds-analysis-reviewer` at lines 45, 115, 190)
- `plugins/pd/skills/decomposing/SKILL.md` (dispatches `pd:project-decomposition-reviewer` at line 82)

**Body content (byte-equivalent copy from `design.md` lines 10-14):**

The chosen template is the existing `design.md` block because (1) `design.md` is itself a "no security-reviewer dispatch" site, (2) its body wording covers both the reference glob and fallback semantics required by ACs, and (3) it has the "Security exclusion: This phase does NOT dispatch `pd:security-reviewer`..." clause matching validate.sh's regex.

For each new site, the placeholder substitutions are:
- `secretary.md`: "this command's reviewer dispatches (design-reviewer, phase-reviewer)" → "this command's reviewer dispatches (secretary-reviewer)". "This phase does NOT dispatch" → "This command does NOT dispatch" (for stylistic consistency). Per R-8, append a one-sentence note: "Note: Dynamic agent dispatch at Step 7 DELEGATE (line 726) is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site."
- `taskify.md`: substitute reviewer to `task-reviewer`. "This command does NOT dispatch."
- `review-ds-code.md`: substitute reviewer to `ds-code-reviewer`. "This command does NOT dispatch."
- `review-ds-analysis.md`: substitute reviewer to `ds-analysis-reviewer`. "This command does NOT dispatch."
- `skills/decomposing/SKILL.md`: substitute reviewer to `project-decomposition-reviewer`. "This skill does NOT dispatch."

**Insertion position:** Within the first 100 lines of each file, immediately after the file's existing top-level explanatory header and before the first procedural section. This mirrors the existing 6 sites' placement.

### C2: validate.sh Modification

Two changes to `validate.sh`:

**C2a — FR-2a:** Line 874 changes from `log_warning` to `log_error`. Pre-change verification: confirm the existing 4 no-dispatch sites already match the line-873 regex (per spec FR-2a, this is mechanical and pre-verified true via grep at design time — see V-1 below).

**C2b — FR-2b:** Block of code inserted immediately after the existing while-loop closes (after line 877, before line 878 `[ "$codex_routing_exclusion_violations" = "0" ] && log_info ...`). Block contents per spec FR-2b sketch (cwd assertion + allowlist diff). Variable name: `codex_routing_allowlist_violations` (separate counter from the existing `codex_routing_exclusion_violations` so the two checks emit distinct error messages).

### C3: tasks.md Manual-Checklist Documentation

Three task entries in `tasks.md` (created in plan phase, executed in implement phase):
- T-EXEC-AC-2.2: Document and run AC-2.2 negative-path procedure in temp clone, paste output evidence into a per-task evidence file.
- T-EXEC-AC-2.3: Document and run AC-2.3 allowlist-drift procedure (both directions).
- T-EXEC-AC-3.1: Capture the `pd:security-reviewer` baseline at task-start time per spec, then verify empty diff after all FR-1/FR-2 changes.

## Technical Decisions

### TD-1: Choose `design.md` as the byte-equivalent template

**Decision:** Copy from `commands/design.md` lines 10-14 (the `## Codex Reviewer Routing` block), not from any of the other 5 existing sites.

**Rationale:** `design.md` is the simplest of the 4 no-dispatch sites — it has the most concise body text, and its security-exclusion clause matches validate.sh:873's regex with the canonical phrasing. The other 3 no-dispatch sites (`create-plan.md`, `specify.md`, `brainstorming/SKILL.md`) all use slight phrasing variations. Standardizing on one template reduces drift.

**Alternative considered:** Use `specify.md` template (which adds "no code surface to review at spec stage" parenthetical). Rejected because the parenthetical doesn't generalize to all 5 new sites (e.g., `taskify.md` does have a code surface in the sense of task-list output).

**Validation:** AC-1.6, AC-1.7, NFR-1.1 all pass when `design.md`'s template is used verbatim with reviewer-name substitutions only.

### TD-2: Tighten else-branch (FR-2a) instead of restructuring exclusion check

**Decision:** Change validate.sh:874 from `log_warning` to `log_error` and `codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))` so the existing check counts these violations toward the same return-code logic.

**Rationale:** Minimum intrusion. The existing dispatching logic (line 865) is correct as-is. The bug is only in the severity of the else-branch — currently `log_warning` allows the regression to slip through. Tightening to `log_error` is a 2-line change.

**Alternative considered:** Restructure the entire check to use a unified strict regex regardless of dispatch mode. Rejected as out-of-scope (per spec "Out of Scope: Tightening any other validate.sh check").

**Validation:** Pre-change pass on the existing 4 no-dispatch files (design.md, create-plan.md, specify.md, brainstorming/SKILL.md) + 5 new files all match the line-873 regex. Post-change, `validate.sh` exits 0 on the green tree.

### TD-3: Use exact-allowlist diff (FR-2b) instead of count-only assertion

**Decision:** FR-2b uses `diff <(echo "$expected_sorted") <(echo "$actual_codex_files")` with `log_error` on mismatch.

**Rationale:** Catches drift in both directions (file added or removed) AND identifies which files differ. Pure count assertion (`wc -l != 11`) only catches additions/removals but not substitutions (e.g., one file removed + one new file added would net to count==11 and silently pass). The diff approach is verbose enough on failure (prints the actual diff) to make debugging easy.

**Alternative considered:** `wc -l == 11` count check. Rejected per spec-reviewer iter 1 warning #5 (substitution-pattern silent pass).

**Validation:** AC-2.3 simulates both drift directions and asserts validate.sh exits non-zero in both cases.

### TD-4: Manual-checklist for negative-path tests (AC-2.2, AC-2.3)

**Decision:** AC-2.2 and AC-2.3 negative-path procedures are documented in `tasks.md` and executed manually by the implementer at implement time. Output evidence is pasted into `.qa-gate-low-findings.md` or task-completion artifact.

**Rationale:** Encoding negative-path tests as automated test files would either:
- Mutate the source tree (rejected per spec-reviewer iter 1 warning #4)
- Require a separate stable fixture tree (out-of-scope hardening)

Manual checklist + output evidence achieves the user-direction filter ("primary feature + primary/secondary defense; NO edge-case hardening") with minimal infrastructure investment.

**Alternative considered:** Skip negative-path tests entirely. Rejected because FR-2a's regression guard is the entire purpose of the spec; a positive-only test (FR-1 + FR-2b allowlist) doesn't verify FR-2a fires when expected.

**Validation:** Implementer runs the procedures and pastes terminal output as evidence in the implementation log.

### TD-5: Skip Step 0 research

**Decision:** Per YOLO mode "domain expert" path, skip codebase-explorer and internet-researcher dispatches.

**Rationale:** Feature 103 is direct prior art, already canonicalized in `plugins/pd/references/codex-routing.md`. The 6 existing preamble sites are the byte-equivalent templates. There is no external industry pattern to research (codex routing is a pd-specific abstraction). Saves 2 agent dispatches with zero information gain.

**Alternative considered:** Run both research agents anyway for diligence. Rejected on token-budget grounds.

**Validation:** Design-reviewer can verify TD-5 is correctly invoked (research findings would have been a no-op anyway).

## Risks

### R-1: Drift in existing 6 preambles

**Risk:** Future edits to `commands/design.md` or other existing 6 sites could accidentally diverge from the template, breaking the "byte-equivalent" assumption for new copies.

**Mitigation:** FR-2b's allowlist+count assertion fires on file-set drift but does NOT detect content drift within an already-listed file. This is accepted out-of-scope for feature 105. Future feature could add a content-hash assertion. Not blocking.

**Severity:** Low. The 6 existing preambles are stable per the feature 103 retrospective; no edits in 1+ months.

### R-2: validate.sh:873 regex insufficiency

**Risk:** The line-873 regex (`does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced`) may not match a typo'd version of the spec-prescribed phrasing (e.g., "does not dispatch" lowercased "does", missing capitalization). FR-2a converts this to a hard error, so any typo at any of the 5 new sites breaks validate.sh.

**Mitigation:** TD-1 mandates byte-equivalent copy from `design.md`, eliminating typo risk. Implementer uses copy-paste with sed-substitution for reviewer name only.

**Severity:** Low if TD-1 is followed.

### R-3: Codex companion CLI changes

**Risk:** If `node codex-companion.mjs task --prompt-file` flag changes in a future codex plugin release, all 11 preambles propagate the bug at once. This is a scope-shared risk with feature 103, not new.

**Mitigation:** Out-of-scope per spec. Future feature could add a CI smoke test that runs `node codex-companion.mjs task --help` and asserts the flag.

**Severity:** Medium but not new (feature 103 inherits the same risk).

### R-4: cwd-sensitive validate.sh assertion

**Risk:** FR-2b's allowlist requires repo-root cwd. If validate.sh is ever run from a sub-directory or via a wrapper script that changes cwd, the assertion fires false-positive.

**Mitigation:** FR-2b includes explicit cwd-assertion (`[[ -f "./validate.sh" && -d "./plugins/pd" ]]`). On failure, `log_error` fires with a clear message.

**Severity:** Low.

### R-5: Manual-checklist negative-path tests not actually run

**Risk:** Implementer skips AC-2.2/2.3 manual procedures and marks tasks complete without evidence.

**Mitigation:** tasks.md requires output-evidence paste for each procedure. Implementation-reviewer at the implement phase verifies the evidence exists. Failure to paste evidence is an implementation-review blocker.

**Severity:** Medium. Mitigated by review-loop process gates.

### R-6: design.md template lines may shift

**Risk:** "Lines 10-14 of design.md" pinned in TD-1. If `design.md` is edited between design and implement phases, those line numbers may drift.

**Mitigation:** TD-1 says "byte-equivalent copy" which is content-anchored, not line-anchored. Implementer reads `design.md`, identifies the `## Codex Reviewer Routing` section by heading, and copies the section body. Line number is informational only.

**Severity:** Low.

### R-7: secretary.md positioning

**Risk:** `secretary.md` has a large Static Reference Tables block starting at line 10 and running to line 235 (verified at design-review iter 1). Inserting the preamble "after the tables but within line-100 budget" is impossible — the tables span past line 100.

**Mitigation:** Single prescriptive insertion position: immediately after secretary.md's H1 and brief description (line 6 area), and BEFORE the `## Static Reference Tables` H2 at line 10. Insertion point is between line 8 (end of brief description) and line 10 (start of tables). This is AC-1.1-compliant (heading lands at line ~10, well within first 100). Implementer has no choice to make.

**Severity:** Low.

### R-8: secretary.md dynamic-dispatch loophole

**Risk:** `secretary.md` line 726 dispatches `Task({ subagent_type: "{plugin}:{agent}", ... })` — a templated delegation that could route to any discovered agent at runtime, including a reviewer agent (e.g., `pd:security-reviewer` or any `pd:*-reviewer`). The new preamble's security-exclusion clause says "this command does NOT dispatch `pd:security-reviewer`," which is technically true for the literal grep at the static dispatch site (line 644 dispatches `pd:secretary-reviewer`, not security-reviewer), but ignores the runtime-templated case at line 726.

**Mitigation:** Out of scope for feature 105 per the user-direction filter. Acknowledge explicitly in the secretary.md preamble body via a one-sentence note: "Note: Dynamic agent dispatch at Step 7 DELEGATE (line 726) is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site." This makes the loophole explicit so future readers know it was intentionally not addressed. A future feature could add codex routing to the dynamic-dispatch path.

**Severity:** Medium for security-correctness (a user could ask secretary to delegate to security-reviewer, and that delegation would not currently route through codex — but the codex exclusion for security-reviewer means this is correct behavior, not a bug). Low for feature 105 scope (the feature does not introduce or worsen this; it merely doesn't fix it).

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/commands/secretary.md` | Insert preamble | `## Codex Reviewer Routing` section within first 100 lines |
| `plugins/pd/commands/taskify.md` | Insert preamble | Same structure as secretary.md, reviewer = `pd:task-reviewer` |
| `plugins/pd/commands/review-ds-code.md` | Insert preamble | Same structure, reviewer = `pd:ds-code-reviewer` |
| `plugins/pd/commands/review-ds-analysis.md` | Insert preamble | Same structure, reviewer = `pd:ds-analysis-reviewer` |
| `plugins/pd/skills/decomposing/SKILL.md` | Insert preamble | Same structure, reviewer = `pd:project-decomposition-reviewer` |
| `validate.sh` | Modify | Line 874 `log_warning` → `log_error` + `codex_routing_exclusion_violations` increment (FR-2a); insert allowlist+count block after line 877 (FR-2b) |
| `docs/features/105-codex-routing-coverage-extension/tasks.md` | Create | Task list including T-EXEC-AC-2.2/2.3/3.1 manual checklists (created in plan phase) |
| `CHANGELOG.md` | Append | Unreleased section: "Codex routing coverage extended to 5 additional dispatch sites" (created in finish-feature phase) |

## Test Strategy

| Layer | What to test | Where |
|-------|--------------|-------|
| Static contract | All 11 sites have `## Codex Reviewer Routing` heading + codex-routing.md reference + fallback semantic + security-exclusion clause matching validate.sh:873 regex | `validate.sh` (FR-2b allowlist + existing line 856-878 loop) |
| Static contract | No agent definition file modified | `git diff develop...HEAD --name-only -- plugins/pd/agents/` (AC-4.1) |
| Static contract | No existing 6 preamble bodies changed | `git diff develop...HEAD -- <existing-6>` (AC-4.2) |
| Static contract | No new pd:security-reviewer dispatch sites | `grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/` baseline-vs-post diff (AC-3.1) |
| Static contract | No `pd:security-reviewer` routed through codex anywhere | `grep -rn` negation per AC-3.2 |
| Negative-path | FR-2a fires on missing exclusion clause | Manual checklist in tasks.md (AC-2.2 procedure in temp clone) |
| Negative-path | FR-2b fires on file-set drift (both directions) | Manual checklist in tasks.md (AC-2.3 procedure in temp clone) |
| Regression | All existing hook tests pass | `bash plugins/pd/hooks/tests/test-hooks.sh` |
| Regression | Pattern-promotion pytest passes | `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/pattern_promotion/` |

## Verification Checks (V-1)

Pre-design verification confirming spec assumptions:
- All 5 reviewer dispatches at the 5 target files are confirmed via `grep -n "subagent_type:"` (already done at spec time, see spec.md Notes line 191-195).
- All 4 existing no-dispatch sites already match validate.sh:873's regex. Verified at spec time per spec FR-2a "Pre-change verification" clause.
- `commands/design.md` lines 10-14 contains the `## Codex Reviewer Routing` block. Verified at spec time.
- Codex companion is installed at `~/.claude/plugins/cache/openai-codex/codex/1.0.1/scripts/codex-companion.mjs`. Verified at design start time.

## Interfaces

### I-1: Preamble Section Format

Every new preamble section conforms to this structure (byte-equivalent from `commands/design.md` lines 10-14):

```markdown
## Codex Reviewer Routing

Before any reviewer dispatch in this {command|skill} ({reviewer-list-comma-separated}), follow the codex-routing reference (primary: `~/.claude/plugins/cache/*/pd*/*/references/codex-routing.md`; fallback for dev workspace: `plugins/pd/references/codex-routing.md`). If codex is installed (per the path-integrity-checked detection helper in the reference doc), route via Codex `task --prompt-file` (foreground). Reuse the reviewer's prompt body verbatim via temp-file delivery (single-quoted heredoc — never argv interpolation). Translate the response per the field-mapping table in the reference doc. Falls back to pd reviewer Task on detection failure or malformed codex output.

**Security exclusion:** This {command|skill|phase} does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature).
```

Substitutions:
- `{command|skill}`: "command" for the 4 commands, "skill" for `decomposing/SKILL.md`.
- `{reviewer-list-comma-separated}`: per Notes inventory.
- `{command|skill|phase}`: "command" for the 4 commands, "skill" for `decomposing/SKILL.md`, "phase" reserved for existing sites where this term is correct.

### I-2: validate.sh FR-2a Patch

Lines 871-876 change FROM:
```bash
    else
        # Does not dispatch security-reviewer → MUST contain "no security review at this phase" indicator.
        if ! grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" "$f"; then
            log_warning "$f: references codex-routing.md but lacks 'no security review at this phase' indicator (informational only)"
        fi
    fi
```

TO:
```bash
    else
        # Does not dispatch security-reviewer → MUST contain "no security review at this phase" indicator.
        if ! grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" "$f"; then
            log_error "$f: references codex-routing.md but lacks 'no security review at this phase' indicator"
            codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))
        fi
    fi
```

Diff: comment "(informational only)" removed; `log_warning` → `log_error`; counter increment added.

### I-3: validate.sh FR-2b Patch (insertion after line 877)

Inserted between the existing while-loop end (line 877) and the existing summary line (line 878):

```bash
# FR-2b (feature 105): allowlist+count assertion for codex-routing references.
# Catches drift where a preamble is removed from one of the 11 expected sites,
# or a 12th non-target file accidentally references codex-routing.md.
codex_routing_allowlist_violations=0
if [[ -f "./validate.sh" && -d "./plugins/pd" ]]; then
    expected_codex_files="plugins/pd/commands/specify.md
plugins/pd/commands/design.md
plugins/pd/commands/create-plan.md
plugins/pd/commands/implement.md
plugins/pd/commands/finish-feature.md
plugins/pd/skills/brainstorming/SKILL.md
plugins/pd/commands/secretary.md
plugins/pd/commands/taskify.md
plugins/pd/commands/review-ds-code.md
plugins/pd/commands/review-ds-analysis.md
plugins/pd/skills/decomposing/SKILL.md"
    # Note: alternation is intentionally redundant (mirrors validate.sh:877 verbatim per spec FR-2b).
    # Scope (commands+skills, NOT references) excludes codex-routing.md itself from the discovery set.
    actual_codex_files=$(grep -rl "plugins/pd/references/codex-routing.md\|codex-routing\.md" plugins/pd/commands plugins/pd/skills 2>/dev/null | sort)
    expected_sorted=$(echo "$expected_codex_files" | sort)
    if [ "$actual_codex_files" != "$expected_sorted" ]; then
        log_error "Codex routing coverage drift: actual file set differs from allowlist (feature 105 FR-2b)"
        diff <(echo "$expected_sorted") <(echo "$actual_codex_files") | head -20 | while IFS= read -r line; do log_error "  $line"; done || true
        codex_routing_allowlist_violations=$((codex_routing_allowlist_violations + 1))
    fi
else
    log_error "FR-2b allowlist check requires repo-root cwd (validate.sh and plugins/pd not found in cwd)"
    codex_routing_allowlist_violations=$((codex_routing_allowlist_violations + 1))
fi
[ "$codex_routing_allowlist_violations" = "0" ] && log_info "Codex routing coverage allowlist validated (11 expected files)"
```

### I-4: AC-3.1 Baseline Capture

Captured by the implementer at task start:

```bash
grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort > /tmp/pd-105-sec-baseline.txt
```

Verified post-implementation:

```bash
grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort | diff - /tmp/pd-105-sec-baseline.txt
```

Acceptance: empty diff (exit 0).

### I-5: Manual Checklist Procedure (AC-2.2, AC-2.3)

Both procedures share this scaffold:

```bash
TEMP_TEST_DIR=$(mktemp -d -t pd-105-test.XXXXXX)
trap 'rm -rf "$TEMP_TEST_DIR"' EXIT
cp -R . "$TEMP_TEST_DIR/repo"
cd "$TEMP_TEST_DIR/repo"
# ... per-AC mutation ...
# Sanity check: confirm mutation took effect (defends against BSD/GNU sed regex differences).
# For AC-2.2: ! grep -q 'does NOT dispatch.*pd:security-reviewer' plugins/pd/commands/secretary.md \
#   || { echo "FAIL: AC-2.2 sed mutation did not take effect"; exit 1; }
./validate.sh; rc=$?
[ "$rc" -ne 0 ] || { echo "FAIL"; exit 1; }
echo "PASS"
```

The implementer pastes the terminal output (stdout + stderr) into a per-task evidence file under `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.{2,3}.txt`. The `agent_sandbox/` directory is already git-tracked-ignore per CLAUDE.md ("Put all agent generated non-workflow related content in `agent_sandbox/[YYYY-MM-DD]/[Meaningful Directory Name]/`"). Evidence files are referenced in tasks.md task-completion DoD but NOT committed.

## Open Questions

None. All ambiguities resolved during 3 spec-review + 2 phase-review iterations.

## Out of Scope

Per spec "Out of Scope" section, plus:
- Content-hash assertions on existing 6 preamble bodies (R-1 mitigation deferred).
- CI smoke test for codex companion CLI flag stability (R-3 mitigation deferred).
- Refactoring routing into a `workflow-transitions::dispatchReviewer` helper (deferred per `codex-routing.md` Future Considerations).
