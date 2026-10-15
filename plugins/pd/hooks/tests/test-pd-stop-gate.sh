#!/usr/bin/env bash
# test-pd-stop-gate.sh — the Stop gate fed hook JSON (build-tasks T4.6): when it blocks, when it
# yields to background work, the stuck question, and the token count per feature and repository.
# Each case asserts the exit code AND the reason only its own path prints.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GATE="$HERE/../pd-stop-gate.sh"
PD_NEW="$HERE/../../scripts/pd-new"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
mkdir -p "$HOME"
PASSED=0
FAILED=0

# run <json>: feed the gate; sets CODE and ERR (its stderr).
run() { ERR=$(printf '%s' "$1" | bash "$GATE" 2>&1 >/dev/null); CODE=$?; }
# expect <label> <code> [needle] [absent needle]: the last run's exit, and its stderr has needle (or is empty).
expect() {
  local good=1
  [ "$CODE" = "$2" ] || good=0
  if [ -n "${3:-}" ]; then grep -qF -- "$3" <<<"$ERR" || good=0; else [ -z "$ERR" ] || good=0; fi
  if [ -n "${4:-}" ] && grep -qF -- "$4" <<<"$ERR"; then good=0; fi
  if [ "$good" = 1 ]; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: $1 (exit $CODE)"; echo "$ERR" | sed 's/^/    /'; fi
}
# hook <repo> <session> [stop_hook_active] [background_tasks JSON]
hook() {
  local bg=""
  [ -n "${4:-}" ] && bg=",\"background_tasks\":$4"
  printf '{"session_id":"%s","cwd":"%s","transcript_path":"%s","stop_hook_active":%s%s}' \
    "$2" "$1" "$TMP/t-$2.jsonl" "${3:-false}" "$bg"
}
# mkrepo <dir> [config lines]: an adopted repo, one pd-new feature, its branch checked out.
mkrepo() {
  mkdir -p "$1/.claude"
  ( cd "$1" && git init -q -b main && git config user.email t@t && git config user.name t &&
    git config commit.gpgsign false &&
    printf -- '---\nartifacts_root: docs/dev_artifacts\nsop: 1\n%s---\n' "${2:-}" > .claude/pd.local.md &&
    "$PD_NEW" feature "Parse the input" >/dev/null && git add -A && git commit -qm base &&
    git checkout -qb "feature/$(ls docs/dev_artifacts/features)" )
}
# now <repo> <text>: the README's ## Now body.
now() {
  python3 - "$1"/docs/dev_artifacts/features/*/README.md "$2" <<'PY'
import re, sys
p, text = sys.argv[1], sys.argv[2]
s = open(p).read()
open(p, "w").write(re.sub(r"(## Now\n\n)(.*?)(\n\n## Links)", lambda m: m.group(1) + text + m.group(3), s, flags=re.S))
PY
}
usage() { printf '{"message":{"usage":{"input_tokens":%s,"output_tokens":%s,"cache_creation_input_tokens":%s,"cache_read_input_tokens":100000}}}\n' "$1" "$2" "$3"; }
tokens() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]))' "$1" "$2" 2>/dev/null; }

A="$TMP/a"; mkrepo "$A"
FID=$(ls "$A/docs/dev_artifacts/features")
FD="$A/docs/dev_artifacts/features/$FID"
cp "$FD/log.md" "$TMP/log.orig"; cp "$FD/README.md" "$TMP/readme.orig"

# --- when it blocks -------------------------------------------------------------------
run "$(hook "$A" S1)"; expect "no goal: line: the stop goes through" 0
now "$A" "goal: $FID target finish session S2"
run "$(hook "$A" S1)"; expect "another session's goal: the stop goes through" 0
now "$A" "goal: $FID target finish session S1"
run "$(hook "$A" S1)"; expect "its own goal short of target blocks" 2 "target finish not reached"
printf '## 2026-10-15 10:00+08:00 review\n- R1 blocker src/a.py:3 — wrong value\n' >> "$FD/log.md"
run "$(hook "$A" S1)"; expect "an open blocker blocks" 2 "open blocker review@2026-10-15 10:00+08:00#R1"
cp "$TMP/log.orig" "$FD/log.md"
sed -i '' 's/^status: active$/status: bogus/' "$FD/README.md"
run "$(hook "$A" S1)"; expect "a pd-lint failure blocks" 2 "pd-lint fails"
sed -i '' 's/^status: bogus$/status: active/' "$FD/README.md"

# --- background work --------------------------------------------------------------------
run "$(hook "$A" S1 false '[{"type":"workflow","status":"running"}]')"; expect "a running workflow yields" 0
run "$(hook "$A" S1 false '[{"type":"subagent","status":"running"}]')"; expect "a running subagent yields" 0
run "$(hook "$A" S1 false '[{"type":"shell","status":"running"}]')"; expect "a running shell doesn't yield" 2 "not reached"
now "$A" "goal: $FID target finish session S1
run in flight: implement-tasks session S1"
run "$(hook "$A" S1)"; expect "no array: this session's run in flight: yields" 0
run "$(hook "$A" S1 false '[]')"; expect "an empty array: the run in flight: line is not read" 2 "not reached"
now "$A" "goal: $FID target finish session S1
run in flight: implement-tasks session S9"
run "$(hook "$A" S1)"; expect "no array: another session's run in flight: doesn't yield" 2 "not reached"
now "$A" "goal: $FID target finish session S1"

# --- stop_hook_active with no progress -------------------------------------------------------
run "$(hook "$A" S1)"; expect "a first check records the state" 2 "not reached"
run "$(hook "$A" S1 true)"; expect "stop_hook_active, nothing moved: ask continue or stop" 2 "no progress since the last check: continue or stop?"
git -C "$A" commit -q --allow-empty -m progress
run "$(hook "$A" S1 true)"; expect "stop_hook_active after a commit: not stuck" 2 "not reached" "no progress"

# --- tokens -------------------------------------------------------------------------------------
STATE_A=$(ls -d "$HOME"/.claude/pd/gate/*/ 2>/dev/null)
{ usage 100 50 10; echo '{"usage":{"input_tokens":7000}}'; } > "$TMP/t-S1.jsonl"
mkdir -p "$TMP/t-S1/subagents/workflows/run1"
usage 5 5 0 > "$TMP/t-S1/subagents/workflows/run1/agent-a1.jsonl"
usage 900 0 0 > "$TMP/t-S1/subagents/workflows/run1/journal.jsonl"
run "$(hook "$A" S1)"
STATE_A=$(ls "$HOME"/.claude/pd/gate/*/"$FID.json")
[ "$(tokens "$STATE_A" tokens)" = 170 ] && [ -z "$(tokens "$STATE_A" budget | grep -v None)" ] \
  && PASSED=$((PASSED + 1)) || { FAILED=$((FAILED + 1)); echo "FAIL: message.usage summed over main + subagents/**/agent-*.jsonl, cache reads excluded: $(cat "$STATE_A")"; }
usage 30 0 0 >> "$TMP/t-S1.jsonl"
run "$(hook "$A" S1)"
[ "$(tokens "$STATE_A" tokens)" = 200 ] && PASSED=$((PASSED + 1)) || { FAILED=$((FAILED + 1)); echo "FAIL: only new usage is charged: $(cat "$STATE_A")"; }
python3 -c 'import json, sys; p = sys.argv[1]; d = json.load(open(p)); d["calvin_ledger"] = "x.md"; json.dump(d, open(p, "w"))' "$HOME/.claude/pd/gate/S1.json"
run "$(hook "$A" S1)"
grep -q '"calvin_ledger": "x.md"' "$HOME/.claude/pd/gate/S1.json" && PASSED=$((PASSED + 1)) || { FAILED=$((FAILED + 1)); echo "FAIL: the session state keeps keys it doesn't own"; }

# Two repositories with the same feature id keep separate totals and budgets.
B="$TMP/b"; mkrepo "$B" $'feature_token_budget: 100\n'
FB="$B/docs/dev_artifacts/features/$FID"
now "$B" "goal: $FID target finish session S3"
usage 100 50 20 > "$TMP/t-S3.jsonl"
run "$(hook "$B" S3)"; expect "past feature_token_budget: ask continue or stop" 2 "budget spent: continue or stop?"
grep -qF 'feature_token_budget=200' <<<"$ERR" && PASSED=$((PASSED + 1)) || { FAILED=$((FAILED + 1)); echo "FAIL: the raise defaults to feature_token_budget"; }
STATES=$(ls "$HOME"/.claude/pd/gate/*/"$FID.json" | wc -l | tr -d ' ')
STATE_B=$(ls "$HOME"/.claude/pd/gate/*/"$FID.json" | grep -v "^$STATE_A$")
[ "$STATES" = 2 ] && [ "$(tokens "$STATE_A" tokens)" = 200 ] && [ "$(tokens "$STATE_B" tokens)" = 170 ] && [ "$(tokens "$STATE_B" budget)" = 100 ] \
  && PASSED=$((PASSED + 1)) || { FAILED=$((FAILED + 1)); echo "FAIL: per-repository state ($STATES files)"; }
run "$(hook "$A" S1)"; expect "the other repository's budget doesn't apply" 2 "not reached" "budget spent"
printf '## 2026-10-15 11:00+08:00 decision\nQ: budget spent: continue or stop?\nA (user, verbatim): "continue"\nBudget: feature_token_budget=1000\n' >> "$FB/log.md"
run "$(hook "$B" S3)"; expect "a decision's raise lifts the cap" 2 "not reached" "budget spent"

# --- the target --------------------------------------------------------------------------------
cp "$TMP/readme.orig" "$FD/README.md"
sed -i '' 's/^phase: specify$/phase: design/' "$FD/README.md"
now "$A" "goal: $FID target specify session S1"
printf '## Requirements\n\nB1: an empty input -> EmptyInput is raised\n' > "$FD/shape.md"
run "$(hook "$A" S1)"; expect "past the target, its exit check failing: not reached" 2 "target specify not reached"
printf '## 2026-10-15 09:00+08:00 decision\nQ: criteria signed off?\nA (user, verbatim): "Yes."\n' >> "$FD/log.md"
run "$(hook "$A" S1)"; expect "target reached, no blockers: clear the goal: line" 2 "reached specify with no open blockers" "not met"
now "$A" "Done."
run "$(hook "$A" S1)"; expect "the goal: line gone: the run ends" 0

echo "test-pd-stop-gate: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
