#!/usr/bin/env bash
# test-pd-session-start.sh — the SessionStart summary and /pd:init detection (build-tasks T4.7).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../pd-session-start.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASSED=0
FAILED=0
H="$TMP/home"
mkdir -p "$H/.claude/pd"

ctx() {  # ctx <cwd> <source> — the hook's additionalContext, or "<none>" when it prints nothing
  local out
  out=$(printf '{"session_id":"s1","source":"%s","cwd":"%s"}' "$2" "$1" | HOME="$H" bash "$HOOK" 2>/dev/null)
  [ -z "$out" ] && { echo "<none>"; return; }
  printf '%s' "$out" | jq -er 'select(.hookSpecificOutput.hookEventName == "SessionStart") | .hookSpecificOutput.additionalContext'
}
check() {  # check <label> <condition command…>
  local label="$1"; shift
  if "$@"; then PASSED=$((PASSED + 1)); else FAILED=$((FAILED + 1)); echo "FAIL: $label"; fi
}
has() { printf '%s' "$1" | grep -qF -- "$2"; }
lacks() { ! has "$1" "$2"; }
repo() { mkdir -p "$1" && git -C "$1" init -q && echo "$1"; }
workitem() {  # workitem <art> <id> <status> <now> [log]
  mkdir -p "$1/workitems/$2"
  printf -- '---\nid: %s\ntype: workitem\ntitle: %s\nstatus: %s\nphase: design\nmode: standard\n---\n# %s\n\n## Now\n\n%s\n\n## Links\n' \
    "$2" "$2" "$3" "$2" "$4" > "$1/workitems/$2/README.md"
  printf '%s' "${5:-}" > "$1/workitems/$2/log.md"
}

# An adopted repo: active and blocked items, the next ready item, the retros owed; not the rest.
A=$(repo "$TMP/adopted"); ART="$A/docs/dev_artifacts"
mkdir -p "$A/.claude" "$ART/plans" "$A/docs/features"  # sop: 1 wins over a stray docs/features/
printf -- '---\nartifacts_root: docs/dev_artifacts\nsop: 1\n---\n' > "$A/.claude/pd.local.md"
workitem "$ART" 2026-10-14-alpha active "next: task 2"
workitem "$ART" 2026-10-14-beta blocked "waiting on the API owner"
workitem "$ART" 2026-10-14-gamma done "Done." $'## 2026-10-14 13:00+08:00 defect\nFixed by: abc1234.\n'
workitem "$ART" 2026-10-14-delta abandoned "Dropped by the user."
printf -- '---\nid: 2026-10-14-road\ntype: plan\ntitle: road\nstatus: active\nroadmap:\n  - workitem: workitems/2026-10-14-gamma\n  - planned: emit\n    after: [gamma]\n---\n# road\n\n## Now\n\n## Links\n\n## Log\n' \
  > "$ART/plans/2026-10-14-road.md"
printf -- '---\nid: 2026-10-14-fin\ntype: plan\ntitle: fin\nstatus: active\nroadmap:\n  - workitem: workitems/2026-10-14-gamma\n---\n# fin\n\n## Now\n\n## Links\n\n## Log\n' \
  > "$ART/plans/2026-10-14-fin.md"
for src in startup compact; do
  out=$(ctx "$A" "$src")
  check "adopted ($src): active item and its ## Now" has "$out" "next: task 2"
  check "adopted ($src): blocked item and its ## Now" has "$out" "waiting on the API owner"
  check "adopted ($src): the next ready item" has "$out" "next ready: emit"
  check "adopted ($src): the retro owed" has "$out" "workitems/2026-10-14-gamma: defect"
  check "adopted ($src): done and abandoned rows left out" lacks "$out" "Dropped by the user."
  check "adopted ($src): a finished plan left out, its row and its roadmap line" lacks "$out" "2026-10-14-fin"
  check "adopted ($src): no /pd:init offer" lacks "$out" "/pd:init"
  check "adopted ($src): the {pd_*} values" eval 'has "$out" "pd_artifacts_root: docs/dev_artifacts" && has "$out" "pd_base_branch: main"'
done

# Only finished plans: no Plans heading left on its own.
F=$(repo "$TMP/finished"); mkdir -p "$F/.claude" "$F/docs/dev_artifacts/plans"
printf -- '---\nsop: 1\n---\n' > "$F/.claude/pd.local.md"
workitem "$F/docs/dev_artifacts" 2026-10-14-gamma done "Done."
cp "$ART/plans/2026-10-14-fin.md" "$F/docs/dev_artifacts/plans/"
out=$(ctx "$F" compact)
check "only finished plans: no Plans heading" eval 'lacks "$out" "Plans" && lacks "$out" "plan done"'

# A configured repo with no items still gets the values; base_branch auto follows origin's HEAD;
# release_script keeps its spaces.
C=$(repo "$TMP/configured"); mkdir -p "$C/.claude"
printf -- '---\nartifacts_root: docs/agent\nbase_branch: auto\nrelease_script: scripts/release.sh --ci\nsop: 1\n---\n' > "$C/.claude/pd.local.md"
git -C "$C" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop
out=$(ctx "$C" compact)
check "configured, no items: the values, no summary" eval 'has "$out" "pd_artifacts_root: docs/agent" && lacks "$out" "active and blocked"'
check "base_branch auto: origin's HEAD" has "$out" "pd_base_branch: develop"
check "release_script keeps its spaces" has "$out" "pd_release_script: scripts/release.sh --ci"

# The guard: an adopted repo left on the pd 7 names gets the Migrate section, items or not.
mkdir -p "$C/docs/agent/features"
printf -- '---\nartifacts_root: docs/agent\nfeature_token_budget:\nsop: 1\n---\n' > "$C/.claude/pd.local.md"
out=$(ctx "$C" compact)
check "pd 7 names: the Migrate section names the folder and the key" eval 'has "$out" "Migrate" && has "$out" "docs/agent/features/" && has "$out" "rename feature_token_budget:"'

# A git repo with no pd.local.md: one /pd:init line, on startup and resume only.
N=$(repo "$TMP/new")
for src in startup resume; do
  out=$(ctx "$N" "$src")
  check "no config ($src): one /pd:init line" [ "$(printf '%s\n' "$out" | grep -c '/pd:init')" = 1 ]
  check "no config ($src): the default values" has "$out" "pd_artifacts_root: docs/dev_artifacts"
done
for src in clear compact; do check "no config ($src): nothing" [ "$(ctx "$N" "$src")" = "<none>" ]; done

# docs/features/ with no sop: 1: run /pd:adopt, on every matcher, config or not.
O=$(repo "$TMP/old"); mkdir -p "$O/docs/features/001-x" "$O/.claude"
printf -- '---\nartifacts_root: docs\n---\n' > "$O/.claude/pd.local.md"
check "old layout (compact): run /pd:adopt" has "$(ctx "$O" compact)" "run /pd:adopt"
rm "$O/.claude/pd.local.md"
out=$(ctx "$O" startup)
check "old layout, no config: run /pd:adopt, not /pd:init" eval 'has "$out" "run /pd:adopt" && lacks "$out" "/pd:init"'

# A repo listed in init-declined (by path; by origin URL when it has one): no prompt.
D=$(repo "$TMP/declined")
printf '%s\n' "$(git -C "$D" rev-parse --show-toplevel)" > "$H/.claude/pd/init-declined"
check "declined by path: nothing" [ "$(ctx "$D" startup)" = "<none>" ]
U=$(repo "$TMP/withorigin"); git -C "$U" remote add origin https://example.test/u.git
check "an origin URL keys the offer" has "$(ctx "$U" startup)" "https://example.test/u.git"
echo "https://example.test/u.git" >> "$H/.claude/pd/init-declined"
check "declined by origin URL: nothing" [ "$(ctx "$U" startup)" = "<none>" ]

# Outside git: nothing.
mkdir -p "$TMP/plain"
check "outside git: nothing" [ "$(ctx "$TMP/plain" startup)" = "<none>" ]

echo "test-pd-session-start: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
