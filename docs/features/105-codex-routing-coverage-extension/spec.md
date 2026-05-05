# Spec: Codex Routing Coverage Extension

## Problem

Feature 103 introduced codex reviewer routing for 5 commands (`specify`, `design`, `create-plan`, `implement`, `finish-feature`) and 1 skill (`brainstorming/SKILL.md`), with a centralized reference doc (`plugins/pd/references/codex-routing.md`) and a `validate.sh` exclusion guard. Five additional dispatch sites still bypass codex routing because they were missed in the original rollout: `commands/secretary.md` (dispatches `pd:secretary-reviewer`), `commands/taskify.md` (dispatches `pd:task-reviewer`), `commands/review-ds-code.md` (dispatches `pd:ds-code-reviewer` at 3 call sites), `commands/review-ds-analysis.md` (dispatches `pd:ds-analysis-reviewer` at 3 call sites), and `skills/decomposing/SKILL.md` (dispatches `pd:project-decomposition-reviewer`). When users have the `openai-codex/codex` plugin installed, these sites still route reviewers through Anthropic models even though the routing decision was already made for the rest of the system. None of the 5 sites dispatch `pd:security-reviewer` — they are all forward-compat additions to the security-exclusion family used by `design.md`, `create-plan.md`, `specify.md`, and `brainstorming/SKILL.md`.

## Success Criteria

1. All 5 listed dispatch sites contain a `## Codex Reviewer Routing` preamble that mirrors the format used by the existing 5 sites (primary path glob, dev-workspace fallback, dispatch-via-`task --prompt-file`, JSON field translation reference, fall back to pd reviewer Task on detection failure or malformed output).
2. Every preamble names `pd:security-reviewer` in a "no security review at this phase" exclusion clause that satisfies validate.sh's regression-guard regex (`does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced`).
3. `validate.sh`'s codex-routing exclusion check is tightened so the existing else-branch (file references codex-routing.md but does NOT dispatch security-reviewer) emits `log_error` instead of `log_warning`, making the regression guard load-bearing for these 5 new files.
4. `validate.sh` adds a count-allowlist assertion: the dynamic-discovery `grep -rl` finds exactly 11 files (existing 6 + new 5), each in a known-good allowlist. Drift in either direction (file added or removed) errors.
5. No dispatch of `pd:security-reviewer` is routed through codex anywhere in the codebase. The pre-change baseline of `pd:security-reviewer` dispatch sites is preserved.
6. `validate.sh` passes overall; existing hook tests in `plugins/pd/hooks/tests/` pass; pattern_promotion pytest passes.

## Functional Requirements

### FR-1: Preamble Authoring

The 5 listed files each receive a `## Codex Reviewer Routing` section that appears within the first 100 lines of the file (after any frontmatter). Body wording matches the pattern established by the existing 4 "no-dispatch" sites (`design.md`, `create-plan.md`, `specify.md`, `brainstorming/SKILL.md`). The exclusion clause MUST use the exact phrasing pattern: "This {command|skill|phase} does NOT dispatch `pd:security-reviewer` ..." (so it satisfies validate.sh:873's regex `does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced`).

If a target file dispatches more than one reviewer type, the preamble enumerates all dispatched reviewer types. (Per the verified inventory in Notes, secretary.md dispatches only `pd:secretary-reviewer`; all 5 sites are effectively single-reviewer.)

**AC-1.1:** `commands/secretary.md` contains a `## Codex Reviewer Routing` section within the first 100 lines. The section names `pd:security-reviewer` in an exclusion clause whose phrasing matches validate.sh:873's regex. Verifiable via:
```bash
section=$(awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' plugins/pd/commands/secretary.md)
[[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
echo "$section" | head -n 100 | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion clause missing"; exit 1; }
heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/commands/secretary.md | head -1 | cut -d: -f1)
[[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
```

**AC-1.2:** `commands/taskify.md` contains a `## Codex Reviewer Routing` section. Same verification pattern as AC-1.1, substituting the file path. The dispatched reviewer mentioned in the body is `pd:task-reviewer`.

**AC-1.3:** `commands/review-ds-code.md` contains a `## Codex Reviewer Routing` section. Same verification as AC-1.1. The dispatched reviewer is `pd:ds-code-reviewer` (3 call sites at lines 44, 111, 179).

**AC-1.4:** `commands/review-ds-analysis.md` contains a `## Codex Reviewer Routing` section. Same verification as AC-1.1. The dispatched reviewer is `pd:ds-analysis-reviewer` (3 call sites at lines 45, 115, 190).

**AC-1.5:** `skills/decomposing/SKILL.md` contains a `## Codex Reviewer Routing` section. Same verification as AC-1.1. The dispatched reviewer is `pd:project-decomposition-reviewer` (line 82). Note: this skill also dispatches `pd:project-decomposer` (an executor, not a reviewer) — only the reviewer is routed via codex.

**AC-1.6:** Every new preamble references the codex-routing reference path. Verifiable via the awk-extracted section content from AC-1.1's pattern grep'd for `codex-routing\.md`. Required: ≥1 match per file's section.

**AC-1.7:** Every new preamble includes fallback semantic text within the section (not just anywhere in the file). Verifiable via the awk-extracted section content grep'd for `fall.?back|falls back` (case-insensitive). Required: ≥1 match per file's section.

### FR-2: Validate Coverage Assertion

Two changes to `validate.sh`:

**FR-2a:** Tighten `validate.sh`'s line-874 from `log_warning` to `log_error`. The else-branch (file references codex-routing.md but does NOT dispatch `pd:security-reviewer`) currently only warns when the "no security review at this phase" indicator is missing. Changing this to error makes the regression guard load-bearing for files like the 5 new ones (and the existing 4 no-dispatch sites). Pre-change verification: confirm the existing 4 no-dispatch files (`design.md`, `create-plan.md`, `specify.md`, `brainstorming/SKILL.md`) all already match `does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced` so they continue to pass.

**FR-2b:** Add an allowlist+count assertion to `validate.sh`'s codex-routing section. After the existing while-loop, capture the discovery list and assert it matches a known-good set of exactly 11 files. The allowlist is defined inline in `validate.sh`. Implementation sketch:
```bash
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
actual_codex_files=$(grep -rl "codex-routing\.md" plugins/pd/commands plugins/pd/skills 2>/dev/null | sort)
expected_sorted=$(echo "$expected_codex_files" | sort)
if [ "$actual_codex_files" != "$expected_sorted" ]; then
  log_error "Codex routing coverage drift: actual file set differs from allowlist"
  log_error "Diff (expected vs actual):"
  diff <(echo "$expected_sorted") <(echo "$actual_codex_files") || true
fi
```

**AC-2.1:** Running `./validate.sh` after the FR-1 + FR-2a + FR-2b changes succeeds with exit 0 AND the codex-routing exclusion check logs success for all 11 files.

**AC-2.2:** FR-2a's regression guard is verified by removing the exclusion clause from one of the 5 new files in a temp working tree (NOT in the source tree), running `validate.sh` against the temp tree, and asserting non-zero exit. Implementation: copy the 5 new files plus `validate.sh` into `/tmp/pd-105-test-$$/`, mutate one copy via `sed -i.bak '/does NOT dispatch.*pd:security-reviewer/d' /tmp/pd-105-test-$$/<file>`, re-run `validate.sh` from the temp dir scope (or via a test wrapper that overrides `plugins/pd/`), and assert non-zero exit. Cleanup: `rm -rf /tmp/pd-105-test-$$/`. This is encoded as a manual implementer-checklist step in `tasks.md`, NOT automated in test files (acceptance: tasks.md task documenting the procedure exists and was performed).

**AC-2.3:** FR-2b's allowlist drift is verified by simulating drift in two directions: (a) add a 12th file that references codex-routing.md (e.g. via temp-tree copy of `commands/secretary.md` to `/tmp/pd-105-test-$$/extra-file.md` and pointing the test wrapper at it) → expect non-zero exit; (b) delete one of the 11 expected files from the temp tree → expect non-zero exit. Same temp-tree pattern as AC-2.2; same manual-checklist documentation requirement.

**AC-2.4:** `validate.sh` passes overall after the FR-1 and FR-2 changes (`./validate.sh` exits 0). No regressions in unrelated checks.

### FR-3: Security-Reviewer Exclusion Preservation

No dispatch of `pd:security-reviewer` anywhere in the codebase is routed through codex. The exclusion clause in every preamble (existing 6 + new 5 = 11 total) is preserved.

**AC-3.1:** Before any FR-1 changes, capture baseline:
```bash
grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort > /tmp/pd-105-sec-baseline.txt
```
After all FR-1/FR-2 changes, re-run the same grep and assert empty diff:
```bash
grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort | diff - /tmp/pd-105-sec-baseline.txt
```
Acceptance: exit 0 (empty diff). The baseline file path is documented in `tasks.md` so the implementer captures it at task-start time. The baseline file is NOT committed (it lives in /tmp).

**AC-3.2:** No file under `plugins/pd/` contains a literal that routes `pd:security-reviewer` through codex. Verifiable via:
```bash
! grep -rn "codex.*pd:security-reviewer\|pd:security-reviewer.*codex" plugins/pd/ \
  | grep -vE "except.*pd:security-reviewer|NOT.*pd:security-reviewer|excludes.*pd:security-reviewer|does NOT dispatch.*pd:security-reviewer|always.*Task.*pd:security-reviewer|security-reviewer.*always.*standard|security.*always.*Anthropic"
```
Acceptance: the negated grep returns zero matches (the only allowed mentions are exclusion-clause text).

### FR-4: Out-of-Scope Boundaries

This feature does NOT modify:
- Agent definition files under `plugins/pd/agents/` (agents are dispatch targets, not dispatchers).
- The model selection for `pd:security-reviewer` (stays opus/Anthropic).
- Existing 6 preambles (already verified by feature 103 regression guard; no edits except the FR-2a `log_warning → log_error` change in `validate.sh`).
- Reviewer prompt bodies anywhere.
- The `decomposing/SKILL.md` `pd:project-decomposer` dispatch (executor, not a reviewer; not part of the reviewer routing scope).

**AC-4.1:** `git diff main...HEAD --name-only -- plugins/pd/agents/` returns no files. Verifiable via the diff listing being empty.

**AC-4.2:** `git diff main...HEAD -- plugins/pd/commands/specify.md plugins/pd/commands/design.md plugins/pd/commands/create-plan.md plugins/pd/commands/implement.md plugins/pd/commands/finish-feature.md plugins/pd/skills/brainstorming/SKILL.md` shows ZERO substantive changes (verifiable: existing `## Codex Reviewer Routing` sections are byte-identical to main).

## Non-Functional Requirements

### NFR-1: Plugin Portability

All preambles use the two-location glob pattern from CLAUDE.md ("never use hardcoded `plugins/pd/` paths in agent, skill, or command files"): primary `~/.claude/plugins/cache/*/pd*/*/...`, fallback `plugins/*/...` (dev workspace) marked with "Fallback" or "dev workspace".

**AC-NFR-1.1:** Each new preamble references both the primary `~/.claude/plugins/cache/*/pd*/*/references/codex-routing.md` glob and the dev-workspace fallback. Verifiable via the awk-extracted section content (per AC-1.1 pattern) showing both path forms.

## Out of Scope

- Refactoring routing into a `workflow-transitions::dispatchReviewer(name, prompt)` helper (deferred per `codex-routing.md` "Future Considerations", requires 3+ features of dogfooding before promotion).
- Changing the model selection or dispatch semantics for any reviewer.
- Adding new reviewer types or codex-only reviewers.
- Modifying agent definition files (agents are dispatch targets).
- Updating `commands/brainstorm.md` or other commands that do not dispatch reviewers.
- Adding telemetry or A/B testing for codex-vs-Anthropic outcomes.
- Tightening any other validate.sh check (only the FR-2a + FR-2b changes are in scope).

## Notes

- Feature 103 ID and merge commit (1e5b06a) are the precedent template — copy the preamble wording from `design.md`, `create-plan.md`, `specify.md`, or `brainstorming/SKILL.md` (the four no-dispatch sites) verbatim, adjusting only the file-list of reviewer types dispatched at that site.
- Verified reviewer dispatches per site (via `grep -n "subagent_type:" <file>` at spec time):
  - `commands/secretary.md` → `pd:secretary-reviewer` (line 644)
  - `commands/taskify.md` → `pd:task-reviewer` (line 80)
  - `commands/review-ds-code.md` → `pd:ds-code-reviewer` (lines 44, 111, 179)
  - `commands/review-ds-analysis.md` → `pd:ds-analysis-reviewer` (lines 45, 115, 190)
  - `skills/decomposing/SKILL.md` → `pd:project-decomposition-reviewer` (line 82); also dispatches `pd:project-decomposer` at lines 26, 123 (executor; not a reviewer; not in scope)
- The exclusion clause MUST use phrasing matching validate.sh:873's regex (`does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced`). The recommended verbatim phrasing is: "**Security exclusion:** This {command|skill} does NOT dispatch `pd:security-reviewer`, so the codex-routing exclusion does not need to be enforced here. The exclusion is enforced wherever `pd:security-reviewer` IS dispatched (implement, finish-feature)." — copied byte-equivalent from `design.md` / `create-plan.md` (with `{command}` placeholder replaced).
- The validate.sh dynamic-discovery `grep -rl` already auto-picks-up new files. The reason for the FR-2b allowlist is to catch DRIFT (regression where someone removes a preamble from one of the 11, OR adds a 12th non-target file that references codex-routing.md). FR-2a tightens the same loop's else-branch to error (load-bearing for these 5 new files which don't dispatch security-reviewer).
- AC-2.2 and AC-2.3 negative-path tests are documented as MANUAL implementer-checklist steps in tasks.md (with explicit cleanup ordering: `trap 'rm -rf /tmp/pd-105-test-$$' EXIT`), NOT encoded as automated tests. Rationale: the negative test mutates files in a tree that validate.sh would scan; encoding it as a permanent test would either require a stable separate-tree fixture (out of scope) or risk leaving the source tree mutated on failure (per spec-reviewer iter 1 warning #4).
