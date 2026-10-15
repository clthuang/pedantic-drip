#!/usr/bin/env bash
# test-pd-commit-lint.sh — the commit hook fed hook JSON on stdin (build-tasks T3.10):
# a bad staged artifact blocks with exit 2 and the lint message on stderr; a clean commit
# passes; a non-commit Bash call exits 0 within 100 ms.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../pd-commit-lint.sh"
PD_NEW="$HERE/../../scripts/pd-new"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASSED=0
FAILED=0
ok() { PASSED=$((PASSED + 1)); }
bad() { FAILED=$((FAILED + 1)); echo "FAIL: $1"; }
hook_json() { printf '{"tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$1" "$2"; }

# An adopted fixture repo with one feature made by pd-new, committed.
R="$TMP/repo"
mkdir -p "$R/.claude"
( cd "$R" && git init -q -b main && git config user.email t@t && git config user.name t &&
  git config commit.gpgsign false &&
  printf -- '---\nartifacts_root: docs/dev_artifacts\nsop: 1\n---\n' > .claude/pd.local.md &&
  "$PD_NEW" feature "Parse the input" >/dev/null && git add -A && git commit -qm base )
README=$(ls "$R"/docs/dev_artifacts/features/*/README.md)

# 1. A bad staged artifact: a status outside the closed list.
sed -i '' 's/^status: active$/status: finished/' "$README"
git -C "$R" add -A
err=$(hook_json "git commit -m x" "$R" | bash "$HOOK" 2>&1 >/dev/null); code=$?
[ "$code" = 2 ] && echo "$err" | grep -q 'finished' && ok || bad "bad staged artifact: exit $code, stderr: $err"

# The same through `cd <repo> && git commit` from elsewhere.
code=0; hook_json "cd $R && git commit -m x" "$TMP" | bash "$HOOK" >/dev/null 2>&1 || code=$?
[ "$code" = 2 ] && ok || bad "cd <repo> && git commit: exit $code"

# 2. A clean commit.
sed -i '' 's/^status: finished$/status: active/' "$README"
git -C "$R" add -A
code=0; out=$(hook_json "git commit -m x" "$R" | bash "$HOOK" 2>&1) || code=$?
[ "$code" = 0 ] && ok || bad "clean commit: exit $code, output: $out"

# 3. A non-commit Bash call: exit 0, within 100 ms.
TIMEFORMAT=%R
t=$( { time (hook_json "ls -la" "$R" | bash "$HOOK" >/dev/null 2>&1); } 2>&1 ); code=$?
[ "$code" = 0 ] && awk -v t="$t" 'BEGIN { exit !(t < 0.100) }' && ok || bad "non-commit call: exit $code, ${t}s"

# A command that only mentions "commit" isn't a commit.
code=0; hook_json "echo commit" "$R" | bash "$HOOK" >/dev/null 2>&1 || code=$?
sed -i '' 's/^status: active$/status: finished/' "$README"; git -C "$R" add -A
code2=0; hook_json "grep commit notes.txt" "$R" | bash "$HOOK" >/dev/null 2>&1 || code2=$?
[ "$code" = 0 ] && [ "$code2" = 0 ] && ok || bad "a non-git mention of commit: exits $code, $code2"

echo "test-pd-commit-lint: $PASSED passed, $FAILED failed"
[ "$FAILED" -eq 0 ]
