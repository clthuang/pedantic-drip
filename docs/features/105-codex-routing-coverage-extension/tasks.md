# Tasks: Codex Routing Coverage Extension

## Phase 1: Baseline Capture

### T1: Capture pre-change baselines

- [ ] Run baseline capture for pd:security-reviewer dispatches:
  ```bash
  grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort > /tmp/pd-105-sec-baseline.txt
  ```
- [ ] Verify baseline non-empty: `wc -l /tmp/pd-105-sec-baseline.txt` returns ≥ 1.
- [ ] Run baseline capture for codex-routing references:
  ```bash
  grep -rl "plugins/pd/references/codex-routing.md\|codex-routing\.md" plugins/pd/commands plugins/pd/skills 2>/dev/null | sort > /tmp/pd-105-codex-baseline.txt
  ```
- [ ] Verify pre-baseline matches existing 6 files exactly:
  ```bash
  expected_pre="plugins/pd/commands/create-plan.md
  plugins/pd/commands/design.md
  plugins/pd/commands/finish-feature.md
  plugins/pd/commands/implement.md
  plugins/pd/commands/specify.md
  plugins/pd/skills/brainstorming/SKILL.md"
  diff <(echo "$expected_pre" | sort) /tmp/pd-105-codex-baseline.txt
  ```
- [ ] DoD: both /tmp baseline files exist and pre-baseline diff is empty.

## Phase 2: Preamble Insertion (parallelizable group A)

### T2: Insert codex-routing preamble in commands/secretary.md

- [ ] Read `plugins/pd/commands/design.md` lines 10-14 to capture the byte-equivalent template (copy buffer for T2-T6).
- [ ] Identify exact insertion seam in `plugins/pd/commands/secretary.md`: AFTER the existing `Route requests to the best-matching specialist agent.` line (line 8 at HEAD) and BEFORE the `## Static Reference Tables` H2 (line 10 at HEAD). Insert with a blank line separator on each side. Per design R-7.
- [ ] Insert the preamble as a new `## Codex Reviewer Routing` section. Body adapted from design.md lines 10-14 with substitutions:
  - "this command's reviewer dispatches (design-reviewer, phase-reviewer)" → "this command's reviewer dispatches (secretary-reviewer)"
  - "This phase does NOT dispatch" → "This command does NOT dispatch"
  - Append one-sentence R-8 note: "Note: Dynamic agent dispatch at Step 7 DELEGATE (line 726) is a runtime-templated routing, not a static reviewer dispatch; codex routing is not applied at that delegation site."
- [ ] Verify AC-1.1:
  ```bash
  extract_codex_section() { awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' "$1"; }
  section=$(extract_codex_section plugins/pd/commands/secretary.md)
  [[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
  echo "$section" | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion clause missing"; exit 1; }
  heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/commands/secretary.md | head -1 | cut -d: -f1)
  [[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
  echo "$section" | grep -qE "codex-routing\.md" || { echo "FAIL: missing codex-routing.md reference"; exit 1; }
  echo "$section" | grep -qiE "fall.?back|falls back" || { echo "FAIL: missing fallback semantic"; exit 1; }
  echo "$section" | grep -q "Dynamic agent dispatch at Step 7 DELEGATE" || { echo "FAIL: missing R-8 note"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: AC-1.1 verification snippet prints PASS.

### T3: Insert codex-routing preamble in commands/taskify.md

- [ ] Identify exact insertion seam in `plugins/pd/commands/taskify.md`: AFTER the line `Break down any plan file into atomic, actionable tasks. This is a standalone command that works on ANY plan from ANY project -- no .meta.json, no entity registry, no MCP calls.` (line 6 at HEAD) and BEFORE `## Step 1: Parse Arguments` (line 8 at HEAD). Insert with blank-line separators on each side.
- [ ] Insert preamble using same template as T2, with substitutions:
  - Reviewer name: `pd:task-reviewer`
  - "{command|skill|phase}" → "command"
- [ ] Verify AC-1.2 (self-contained snippet — function defined inline):
  ```bash
  extract_codex_section() { awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' "$1"; }
  section=$(extract_codex_section plugins/pd/commands/taskify.md)
  [[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
  echo "$section" | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion missing"; exit 1; }
  heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/commands/taskify.md | head -1 | cut -d: -f1)
  [[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
  echo "$section" | grep -qE "codex-routing\.md" || { echo "FAIL: missing reference"; exit 1; }
  echo "$section" | grep -qiE "fall.?back|falls back" || { echo "FAIL: missing fallback"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: AC-1.2 verification prints PASS.

### T4: Insert codex-routing preamble in commands/review-ds-code.md

- [ ] Identify exact insertion seam in `plugins/pd/commands/review-ds-code.md`: AFTER the line `Dispatch the ds-code-reviewer agent to check DS Python code quality.` (line 8 at HEAD) and BEFORE `## Get Target File` (line 10 at HEAD). Insert with blank-line separators on each side.
- [ ] Insert preamble with substitutions: reviewer = `pd:ds-code-reviewer`, "{command|skill|phase}" → "command".
- [ ] Verify AC-1.3 (self-contained snippet):
  ```bash
  extract_codex_section() { awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' "$1"; }
  section=$(extract_codex_section plugins/pd/commands/review-ds-code.md)
  [[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
  echo "$section" | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion missing"; exit 1; }
  heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/commands/review-ds-code.md | head -1 | cut -d: -f1)
  [[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
  echo "$section" | grep -qE "codex-routing\.md" || { echo "FAIL: missing reference"; exit 1; }
  echo "$section" | grep -qiE "fall.?back|falls back" || { echo "FAIL: missing fallback"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: AC-1.3 verification prints PASS.

### T5: Insert codex-routing preamble in commands/review-ds-analysis.md

- [ ] Identify exact insertion seam in `plugins/pd/commands/review-ds-analysis.md`: AFTER the line `Dispatch the ds-analysis-reviewer agent via 3 chained calls to review analysis for statistical pitfalls, methodology issues, and conclusion validity.` (line 8 at HEAD) and BEFORE `## Get Target File` (line 10 at HEAD). Insert with blank-line separators on each side.
- [ ] Insert preamble with substitutions: reviewer = `pd:ds-analysis-reviewer`, "{command|skill|phase}" → "command".
- [ ] Verify AC-1.4 (self-contained snippet):
  ```bash
  extract_codex_section() { awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' "$1"; }
  section=$(extract_codex_section plugins/pd/commands/review-ds-analysis.md)
  [[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
  echo "$section" | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion missing"; exit 1; }
  heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/commands/review-ds-analysis.md | head -1 | cut -d: -f1)
  [[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
  echo "$section" | grep -qE "codex-routing\.md" || { echo "FAIL: missing reference"; exit 1; }
  echo "$section" | grep -qiE "fall.?back|falls back" || { echo "FAIL: missing fallback"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: AC-1.4 verification prints PASS.

### T6: Insert codex-routing preamble in skills/decomposing/SKILL.md

- [ ] Identify exact insertion seam in `plugins/pd/skills/decomposing/SKILL.md`: AFTER the line `Decomposes a project PRD into modules and features through an AI decomposer/reviewer cycle.` (line 12 at HEAD) and BEFORE `## Prerequisites` (line 14 at HEAD). Insert with blank-line separators on each side.
- [ ] Insert preamble with substitutions: reviewer = `pd:project-decomposition-reviewer`, "{command|skill|phase}" → "skill".
- [ ] Verify AC-1.5 (self-contained snippet):
  ```bash
  extract_codex_section() { awk '/^## Codex Reviewer Routing/{f=1} f{print; if (/^## /&&!/Codex Reviewer Routing/){exit}}' "$1"; }
  section=$(extract_codex_section plugins/pd/skills/decomposing/SKILL.md)
  [[ -n "$section" ]] || { echo "FAIL: section not found"; exit 1; }
  echo "$section" | grep -qE "does NOT dispatch.*pd:security-reviewer|no security review|exclusion does not need to be enforced" || { echo "FAIL: exclusion missing"; exit 1; }
  heading_line=$(grep -n "^## Codex Reviewer Routing" plugins/pd/skills/decomposing/SKILL.md | head -1 | cut -d: -f1)
  [[ "$heading_line" -le 100 ]] || { echo "FAIL: heading too far down"; exit 1; }
  echo "$section" | grep -qE "codex-routing\.md" || { echo "FAIL: missing reference"; exit 1; }
  echo "$section" | grep -qiE "fall.?back|falls back" || { echo "FAIL: missing fallback"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: AC-1.5 verification prints PASS.

## Phase 3: validate.sh Patches (sequential)

### T7: Apply FR-2a patch to validate.sh:871-876

- [ ] Read `validate.sh` lines 870-880 to confirm the existing else-branch block.
- [ ] Apply edit per design I-2:
  - Change `log_warning "$f: references codex-routing.md but lacks 'no security review at this phase' indicator (informational only)"` to `log_error "$f: references codex-routing.md but lacks 'no security review at this phase' indicator"`
  - Add immediately after: `codex_routing_exclusion_violations=$((codex_routing_exclusion_violations + 1))`
- [ ] Verify (using double-quote outer to avoid nested single-quote issues):
  ```bash
  grep -n "log_warning" validate.sh | grep -i "no security review"
  # Expect: zero matches (the log_warning line is gone)
  grep -n "log_error" validate.sh | grep -i "no security review"
  # Expect: 1 match showing the patched block
  # Direct anchor-based check for counter increment immediately after log_error:
  grep -A 1 "lacks 'no security review at this phase' indicator" validate.sh | grep -q "codex_routing_exclusion_violations" || { echo "FAIL: counter increment not adjacent to log_error"; exit 1; }
  echo "PASS"
  ```
- [ ] DoD: log_warning gone; log_error + counter increment present (PASS printed).

### T8: Insert FR-2b allowlist+count block in validate.sh after line 877

- [ ] Identify insertion line: directly after the existing `done < <(grep -rl ...)` line (currently line 877) and before the `[ "$codex_routing_exclusion_violations" = "0" ] && log_info ...` line (currently line 878). Note: line numbers may shift slightly after T7's edit; use anchor `grep -n "^done < <(grep -rl"` to locate.
- [ ] Insert the FR-2b block verbatim per design I-3 (cwd assertion + expected_codex_files heredoc list of 11 files + grep -rl with the two-alternation pattern + diff + log_error + log_info success).
- [ ] Include the alternation-redundancy comment line per design fix.
- [ ] Verify:
  ```bash
  grep -c "Codex routing coverage drift" validate.sh
  # Expect: 1
  grep -c "FR-2b" validate.sh
  # Expect: ≥ 1 (the FR-2b comment marker is present)
  grep -c "expected_codex_files" validate.sh
  # Expect: ≥ 1 (the allowlist heredoc starts with this var)
  grep -c "actual_codex_files" validate.sh
  # Expect: ≥ 1 (the discovery grep stores in this var)
  ```
- [ ] DoD: FR-2b block inserted with exact 11-file allowlist (all 4 grep -c above return ≥ 1).

## Phase 4: Validation

### T9: Run validate.sh + AC-3.x + AC-4.x

- [ ] Run `./validate.sh` from repo root. Expect exit 0.
- [ ] AC-3.1 verification: `grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort | diff - /tmp/pd-105-sec-baseline.txt` → expect empty diff. **Note:** the regex is anchored to `subagent_type:` prefix, so prose mentions of `pd:security-reviewer` in exclusion clauses (added by T2-T6) do NOT count toward the dispatch baseline. Only literal Task-tool `subagent_type:` lines are compared.
- [ ] AC-3.2 verification: `! grep -rn "codex.*pd:security-reviewer\|pd:security-reviewer.*codex" plugins/pd/ | grep -vE "except.*pd:security-reviewer|NOT.*pd:security-reviewer|excludes.*pd:security-reviewer|does NOT dispatch.*pd:security-reviewer|always.*Task.*pd:security-reviewer|security-reviewer.*always.*standard|security.*always.*Anthropic"` → expect zero "routing" matches.
- [ ] AC-4.1 verification: `git diff develop...HEAD --name-only -- plugins/pd/agents/` → expect empty.
- [ ] AC-4.2 verification: `git diff develop...HEAD -- plugins/pd/commands/specify.md plugins/pd/commands/design.md plugins/pd/commands/create-plan.md plugins/pd/commands/implement.md plugins/pd/commands/finish-feature.md plugins/pd/skills/brainstorming/SKILL.md` → expect zero substantive changes (or minor whitespace OK; preamble bodies unchanged).
- [ ] DoD: all 5 verifications pass.

## Phase 5: Manual Checklist Procedures (parallelizable group B)

### T10 (T-EXEC-AC-2.2): Run AC-2.2 negative-path procedure

- [ ] Create temp clone (capture original cwd FIRST so we can return to it):
  ```bash
  ORIGINAL_DIR=$(pwd)
  TEMP_TEST_DIR=$(mktemp -d -t pd-105-fr2a-test.XXXXXX)
  trap 'rm -rf "$TEMP_TEST_DIR"' EXIT
  cp -R . "$TEMP_TEST_DIR/repo"
  cd "$TEMP_TEST_DIR/repo"
  ```
- [ ] Mutate + sanity check + run validate.sh:
  ```bash
  # Note: sed -i.bak is portable across BSD (macOS) and GNU (Linux) — both accept the suffix arg.
  sed -i.bak '/does NOT dispatch.*pd:security-reviewer/d' plugins/pd/commands/secretary.md
  rm -f plugins/pd/commands/secretary.md.bak
  # BSD/GNU sed sanity check — if the file still contains the line, sed regex parsing failed
  ! grep -q 'does NOT dispatch.*pd:security-reviewer' plugins/pd/commands/secretary.md || { echo "FAIL: AC-2.2 sed mutation did not take effect (BSD/GNU dialect issue?)"; exit 1; }
  ./validate.sh; rc=$?
  [ "$rc" -ne 0 ] || { echo "FAIL: validate.sh did not error on missing exclusion clause"; exit 1; }
  echo "PASS: FR-2a regression guard fires on missing exclusion clause"
  ```
- [ ] cd back to source repo: `cd "$ORIGINAL_DIR"`
- [ ] Paste full terminal output (stdout + stderr from the procedure) to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.2.txt`. Create the directory if needed.
- [ ] DoD: evidence file committed at `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.2.txt` containing terminal output showing non-zero exit.

### T11 (T-EXEC-AC-2.3): Run AC-2.3 allowlist-drift procedure

- [ ] Create temp clone (same scaffold as T10, including `ORIGINAL_DIR=$(pwd)` capture):
  ```bash
  ORIGINAL_DIR=$(pwd)
  TEMP_TEST_DIR=$(mktemp -d -t pd-105-fr2b-test.XXXXXX)
  trap 'rm -rf "$TEMP_TEST_DIR"' EXIT
  cp -R . "$TEMP_TEST_DIR/repo"
  cd "$TEMP_TEST_DIR/repo"
  ```
- [ ] Direction (a) — drift +1:
  ```bash
  echo "See codex-routing.md" > plugins/pd/commands/extra-file.md
  ./validate.sh; rc_a=$?
  [ "$rc_a" -ne 0 ] || { echo "FAIL: drift+1 not detected"; exit 1; }
  rm plugins/pd/commands/extra-file.md
  echo "PASS direction (a)"
  ```
- [ ] Direction (b) — drift -1:
  ```bash
  mv plugins/pd/commands/taskify.md plugins/pd/commands/taskify.md.disabled
  # Sanity check: confirm grep discovery now finds the .disabled path (drift detected via path mismatch)
  grep -rl "codex-routing" plugins/pd/commands plugins/pd/skills | grep -q "taskify.md.disabled" || { echo "FAIL: rename did not change grep discovery output"; exit 1; }
  ./validate.sh; rc_b=$?
  [ "$rc_b" -ne 0 ] || { echo "FAIL: drift-1 not detected (allowlist diff did not trigger)"; exit 1; }
  mv plugins/pd/commands/taskify.md.disabled plugins/pd/commands/taskify.md
  echo "PASS direction (b)"
  ```
  Expected diff output: validate.sh's `log_error "Codex routing coverage drift..."` shows `taskify.md.disabled` in the actual list and `taskify.md` in the expected list — path mismatch, count stays 11.
- [ ] cd back to source repo.
- [ ] Paste full terminal output (both directions) to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.3.txt`.
- [ ] DoD: evidence file committed at the documented path showing both directions produce non-zero exit.

### T12 (T-EXEC-AC-3.1): Document AC-3.1 baseline match

- [ ] Re-run AC-3.1 diff to capture evidence: `grep -rn "subagent_type:.*pd:security-reviewer" plugins/pd/ | sort | diff - /tmp/pd-105-sec-baseline.txt > /dev/null && echo "PASS: empty diff" || echo "FAIL: diff non-empty"`
- [ ] Paste output (single line) to `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-3.1.txt`.
- [ ] DoD: evidence file committed at the documented path containing "PASS: empty diff".

## Phase 6: Final Commit + Phase Complete

After all 12 tasks pass: commit any uncommitted evidence files via standard commit pattern, push, and let the create-plan skill flow into the relevance gate + auto-chain to /pd:implement (per skill Step 4b).
