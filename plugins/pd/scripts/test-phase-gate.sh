#!/usr/bin/env bash
# test-phase-gate.sh — a pass and a fail fixture for each of phase-gate.sh's exit checks
# (build-tasks T3.6). Each fail fixture breaks one rule only, so removing the rule fails this test.
set -uo pipefail
GATE="$(cd "$(dirname "$0")" && pwd)/phase-gate.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASSED=0
FAILED=0

# expect <0|1> <label> <phase> <dir> [flag] — 0 means the gate must pass, 1 that it must fail.
expect() {
  local want="$1" label="$2"; shift 2
  local out code
  out=$(bash "$GATE" "$@" 2>&1); code=$?
  if { [ "$want" = 0 ] && [ "$code" = 0 ]; } || { [ "$want" = 1 ] && [ "$code" = 1 ]; }; then
    PASSED=$((PASSED + 1))
  else
    FAILED=$((FAILED + 1)); echo "FAIL: $label (exit $code)"; echo "$out" | sed 's/^/    /'
  fi
}

# --- fixtures -------------------------------------------------------------------
REQS='## Requirements

B1: an empty input -> the parser raises EmptyInput
B2: a valid file -> one record per line'
DESIGN='## Design

### Architecture

```mermaid
flowchart LR
    A[cli] -->|ParseRequest| B[parser]
```

### Test strategy

- Runner: pytest --junitxml=PATH.'
SIGNOFF='## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."'
TASKS='#### Task 1: parser [parallel-safe]
- files: src/p.py, tests/test_p.py
- uses: none
- command: `pytest tests/test_p.py --junitxml=j/1.xml`
- junit: j/1.xml
- test cases:
  - C1 [B1] (fixture: none): empty input raises.'
RUN='## 2026-10-14 14:00+08:00 run implement-tasks — finished
- task 1: merged, proof pass, cycles 0, branch pd/x/task-1
- task 2: merged, proof pass, cycles 1, branch pd/x/task-2'

feature() {  # feature <name> <shape body> [log body] — a feature dir with README, shape.md, log.md
  local d="$TMP/$1"; mkdir -p "$d"
  printf -- '---\nid: %s\ntype: feature\nstatus: active\nmode: standard\n---\n# x\n' "$1" > "$d/README.md"
  printf '%s\n' "$2" > "$d/shape.md"
  printf '%s\n' "${3:-}" > "$d/log.md"
  echo "$d"
}

# --- specify: the sign-off decision entry, and the expectation format ----------------
expect 0 "specify passes" specify "$(feature s-ok "$REQS" "$SIGNOFF")"
expect 1 "specify fails without the sign-off" specify "$(feature s-nosign "$REQS")"
expect 1 "specify fails when the sign-off is the conductor's" specify \
  "$(feature s-cond "$REQS" "${SIGNOFF/A (user, verbatim): \"Yes.\"/A (conductor): yes}")"
expect 1 "specify fails on a malformed expectation" specify "$(feature s-bad "$REQS
B3: no arrow here" "$SIGNOFF")"
expect 1 "specify fails with no expectation" specify "$(feature s-none "## Requirements

Goals only." "$SIGNOFF")"
expect 1 "specify fails on a duplicate expectation id" specify "$(feature s-dup "$REQS
B2: again -> twice" "$SIGNOFF")"

# --- design: the diagram and ### Test strategy ---------------------------------------
expect 0 "design passes" design "$(feature d-ok "$REQS

$DESIGN")"
expect 1 "design fails without the diagram" design "$(feature d-nomer "$REQS

${DESIGN/mermaid/text}")"
expect 1 "design fails without ### Test strategy" design "$(feature d-nots "$REQS

${DESIGN/Test strategy/Notes}")"
expect 1 "design fails without ## Design" design "$(feature d-none "$REQS")"

# --- create-plan ----------------------------------------------------------------------
d=$(feature p-ok "$REQS"); printf -- '---\nfrom_shape: x\n---\n## Plan\n\n### Wave 1\n\n%s\n' "$TASKS" > "$d/plan.md"
expect 0 "create-plan passes" create-plan "$d"
expect 1 "create-plan fails without plan.md" create-plan "$(feature p-none "$REQS")"
d=$(feature p-nosec "$REQS"); printf '# Plan\n' > "$d/plan.md"
expect 1 "create-plan fails without ## Plan" create-plan "$d"

# --- implement: a run entry recording every plan task merged with its proof passing ------
TWO="## Plan

### Wave 1

$TASKS

#### Task 2: io
- files: src/io.py"
d=$(feature i-ok "$REQS" "$RUN"); printf '%s\n' "$TWO" > "$d/plan.md"
# A staged log.md or README change passes: the old entry-time dirty-tree check is gone (codex C6).
( cd "$d" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm x &&
  echo "## Now" >> README.md && echo "" >> log.md && git add README.md log.md )
expect 0 "implement passes, with log.md and README changes staged" implement "$d"
d=$(feature i-miss "$REQS" "${RUN%$'\n'- task 2*}"); printf '%s\n' "$TWO" > "$d/plan.md"
expect 1 "implement fails when a task has no merged run line" implement "$d"
d=$(feature i-fail "$REQS" "${RUN/task 2: merged, proof pass/task 2: failed}"); printf '%s\n' "$TWO" > "$d/plan.md"
expect 1 "implement fails when a task's proof didn't pass" implement "$d"

# --- verify: a qa entry, every qa_battery command passing at its commit, nothing changed since,
# no open blockers ----------------------------------------------------------------------
repo() {  # repo <name> <qa_battery yaml lines> — a git repo with src/, tests/ and one feature
  local r="$TMP/$1"; mkdir -p "$r/.claude" "$r/src" "$r/tests" "$r/docs/dev_artifacts/features/f"
  printf -- '---\nartifacts_root: docs/dev_artifacts\nsource_paths: [src/]\ntest_paths: [tests/]\n%s---\n' "$2" > "$r/.claude/pd.local.md"
  echo 'x = 1' > "$r/src/a.py"; echo 'def test(): pass' > "$r/tests/test_a.py"
  printf -- '---\nid: f\ntype: feature\nstatus: active\n---\n' > "$r/docs/dev_artifacts/features/f/README.md"
  : > "$r/docs/dev_artifacts/features/f/log.md"
  ( cd "$r" && git init -q && git add -A && git -c user.email=t@t -c user.name=t commit -qm base )
  echo "$r"
}
qa() {  # qa <repo> <result> [extra body] — append a qa entry citing HEAD
  local c; c=$(git -C "$1" rev-parse --short HEAD)
  printf '## 2026-10-14 12:30+08:00 qa\nCommit: %s\nRan: `pytest -q` -> %s\n%s\n' "$c" "$2" "${3:-}" >> "$1/docs/dev_artifacts/features/f/log.md"
}
commit_all() { ( cd "$1" && git add -A && git -c user.email=t@t -c user.name=t commit -qm "$2" ); }
BAT=$'qa_battery:\n  - pytest -q\n'
F=docs/dev_artifacts/features/f

r=$(repo v-ok "$BAT"); qa "$r" pass
expect 0 "verify passes" verify "$r/$F"
echo "# retro" > "$r/$F/retro.md"; commit_all "$r" retro-only
expect 0 "verify passes after a later retro.md-only commit (codex C4)" verify "$r/$F"
echo 'x = 2' > "$r/src/a.py"; commit_all "$r" src-change
expect 1 "verify fails after a later source change (codex C4)" verify "$r/$F"
r=$(repo v-tests "$BAT"); qa "$r" pass; echo 'def test(): 1' > "$r/tests/test_a.py"; ( cd "$r" && git add -A )
expect 1 "verify fails on a staged test change since the qa commit" verify "$r/$F"
r=$(repo v-wt "$BAT"); qa "$r" pass; echo 'x = 3' > "$r/src/a.py"
expect 1 "verify fails on an unstaged source change since the qa commit" verify "$r/$F"
r=$(repo v-new "$BAT"); qa "$r" pass; echo 'y = 1' > "$r/src/b.py"
expect 1 "verify fails on an untracked source file since the qa commit" verify "$r/$F"
r=$(repo v-nobat ""); qa "$r" pass
out=$(bash "$GATE" verify "$r/$F" 2>&1)
if echo "$out" | grep -q 'set qa_battery in .claude/pd.local.md'; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: a missing qa_battery says to set it"; fi
r=$(repo v-red "$BAT"); qa "$r" fail
expect 1 "verify fails when a battery command failed" verify "$r/$F"
r=$(repo v-noqa "$BAT")
expect 1 "verify fails with no qa entry" verify "$r/$F"
r=$(repo v-block "$BAT"); qa "$r" pass "- Q1 blocker src/a.py:1 — wrong value"
expect 1 "verify fails on an open blocker" verify "$r/$F"
printf '## 2026-10-14 12:40+08:00 decision\nA (user, verbatim): "accept"\nCloses: qa@2026-10-14 12:30+08:00#Q1\n' >> "$r/$F/log.md"
expect 0 "verify passes once the blocker is closed" verify "$r/$F"

# --- finish: retro.md only when a trigger is recorded ------------------------------------
CAPPED='## 2026-10-14 16:00+08:00 capped verify
Deferred: none
Follow-ups: none
Decisions: none
Assumptions: none'
expect 0 "finish passes with no trigger and no retro.md" finish "$(feature f-none "$REQS" "$SIGNOFF")"
expect 1 "finish fails on a trigger without retro.md" finish "$(feature f-trig "$REQS" "$CAPPED")"
d=$(feature f-retro "$REQS" "$CAPPED"); echo "# retro" > "$d/retro.md"
expect 0 "finish passes on a trigger with retro.md" finish "$d"

# --- express: the mini-spec task block ----------------------------------------------------
MINI="$REQS

$TASKS"
expect 0 "express passes" express "$(feature e-ok "$MINI")"
expect 1 "express fails with no task block" express "$(feature e-none "$REQS")"
expect 1 "express fails with no expectation" express "$(feature e-nob "## Requirements

$TASKS")"
expect 1 "express fails when the task has no command" express "$(feature e-nocmd "${MINI/- command:*xml\`/}")"
d=$(feature e-impl "$MINI" "${RUN%$'\n'- task 2*}"); sed -i '' 's/mode: standard/mode: express/' "$d/README.md"
expect 0 "implement on mode: express takes its task from shape.md" implement "$d"
d=$(feature e-quote "$MINI" "${RUN%$'\n'- task 2*}"); sed -i '' 's/mode: standard/mode: "express"/' "$d/README.md"
expect 0 "implement on a quoted mode: \"express\" takes its task from shape.md" implement "$d"
# A log checker that exits 0 without finishing (a broken import, an empty heredoc) fails the gate.
mkdir -p "$TMP/broken" && cp "$GATE" "$TMP/broken/" && echo 'import sys; sys.exit(0)' > "$TMP/broken/pd_common.py"
d=$(feature e-crash "$MINI" "${RUN%$'\n'- task 2*}"); sed -i '' 's/mode: standard/mode: express/' "$d/README.md"
GATE="$TMP/broken/phase-gate.sh" expect 1 "a log checker that never finishes fails the gate" implement "$d"
expect 1 "implement on an express feature still needs the run line" implement "$(feature e-impl2 "$MINI")" --express

echo "test-phase-gate: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
