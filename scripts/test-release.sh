#!/usr/bin/env bash
# Tests release-pr.sh, publish-release.sh, check-changelog.sh, check-version.sh and the protect-release-refs hook
# against throwaway repos: a local bare repo as origin and a stub gh.
# Usage: bash scripts/test-release.sh
set -uo pipefail

SCRIPTS=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
mkdir -p "$T/bin"
# The stub logs every call and answers `run list` (CI's conclusion on main) from $T/ci, default success.
printf '#!/bin/sh\necho "gh $*" >> "%s/gh.log"\n[ "$1 $2" = "run list" ] && { cat "%s/ci" 2>/dev/null || echo success; }\nexit 0\n' "$T" "$T" > "$T/bin/gh"
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"

pass=0 failed=0
check() {
    local name=$1 want=$2 got=0
    shift 2
    "$@" > "$T/out.new" 2>&1 || got=1
    mv "$T/out.new" "$T/out"  # a later check can read this one's output
    if [[ "$got" == "$want" ]]; then pass=$((pass + 1)); else
        failed=$((failed + 1)); echo "FAIL: $name"; sed 's/^/    /' "$T/out"; fi
}
ok() { local name=$1; shift; check "$name" 0 "$@"; }
fails() { local name=$1; shift; check "$name" 1 "$@"; }
in_work() { (cd "$W" && "$@"); }
g() { git -C "$W" "$@"; }
manifest_version() { jq -r .version "$W/plugins/pd/.claude-plugin/plugin.json"; }
set_version() { perl -pi -e "s/\"version\": \"[^\"]*\"/\"version\": \"$1\"/" "$W/plugins/pd/.claude-plugin/plugin.json"; }
# Lands a commit on main the way a merged PR does: a merge commit, pushed.
merge_pr() { g checkout -q main && g merge -q --no-ff -m "Merge $1" "$1" && g push -q origin main; }
add_entry() {  # add_entry <text>: a feature PR adding a line under [Unreleased], merged
    g checkout -q -b "feature/$1" main
    perl -pi -e "s/^## \\[Unreleased\\]\$/## [Unreleased]\n\n- $1/" "$W/CHANGELOG.md"
    g commit -qam "feature $1" && g push -q origin "feature/$1" && merge_pr "feature/$1"
}
remote_ref() { git -C "$T/origin.git" rev-parse -q --verify "$1^{commit}" || true; }

# A repository released at 1.0.0: main, stable and v1.0.0 on one commit.
fresh() {
    rm -rf "$T/origin.git" "$T/work" "$T/gh.log"
    git init -q --bare -b main "$T/origin.git"
    git init -q -b main "$T/work"
    W=$T/work
    mkdir -p "$W/plugins/pd/.claude-plugin" "$W/.claude-plugin"
    printf '{\n  "name": "pd",\n  "version": "1.0.0",\n  "description": "d"\n}\n' > "$W/plugins/pd/.claude-plugin/plugin.json"
    printf '{\n  "name": "m",\n  "plugins": [\n    { "name": "pd", "source": "./plugins/pd" }\n  ]\n}\n' > "$W/.claude-plugin/marketplace.json"
    printf '# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n\n- first\n' > "$W/CHANGELOG.md"
    g add -A && g commit -qm init && g tag v1.0.0
    g remote add origin "$T/origin.git"
    g push -q origin main main:stable v1.0.0
    g fetch -q origin
}

# --- check-version.sh ---
fresh
ok "check-version: equal to the last release" in_work bash "$SCRIPTS/check-version.sh"
set_version 0.9.0
perl -pi -e 's/^## \[1\.0\.0\]/## [0.9.0] - 2026-01-02\n\n- older\n\n## [1.0.0]/' "$W/CHANGELOG.md"  # so only the ordering can fail it
fails "check-version: below the last release" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && set_version 1.0.1
fails "check-version: a new version without its CHANGELOG section" in_work bash "$SCRIPTS/check-version.sh"
perl -pi -e 's/^## \[1\.0\.0\]/## [1.0.1] - 2026-01-02\n\n- next\n\n## [1.0.0]/' "$W/CHANGELOG.md"
ok "check-version: a new version with its CHANGELOG section" in_work bash "$SCRIPTS/check-version.sh"
set_version 1.0.1-dev
fails "check-version: a -dev suffix" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && set_version 1.01.0
perl -pi -e 's/^## \[1\.0\.0\]/## [1.01.0] - 2026-01-02\n\n- next\n\n## [1.0.0]/' "$W/CHANGELOG.md"  # so only the format can fail it
fails "check-version: a leading zero" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && set_version 1.0.1
perl -pi -e 's/^## \[Unreleased\]$/## [Unreleased]\n\n- see ## [1.0.1] below/' "$W/CHANGELOG.md"
fails "check-version: a mention of the version that isn't a heading" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && g tag v1.01.0
ok "check-version: a tag with a leading zero isn't a release" in_work bash "$SCRIPTS/check-version.sh"
g tag -d v1.01.0 > /dev/null
g checkout -q -- .
g tag v1.0.9 && set_version 1.0.10
perl -pi -e 's/^## \[1\.0\.0\]/## [1.0.10] - 2026-01-02\n\n- next\n\n## [1.0.0]/' "$W/CHANGELOG.md"
ok "check-version: 1.0.10 sorts above 1.0.9" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && g tag -d v1.0.9 > /dev/null
perl -pi -e 's/"source": "\.\/plugins\/pd"/"source": ".\/plugins\/pd", "version": "1.0.0"/' "$W/.claude-plugin/marketplace.json"
fails "check-version: a version in marketplace.json" in_work bash "$SCRIPTS/check-version.sh"
g checkout -q -- . && g tag -d v1.0.0 > /dev/null
fails "check-version: no tags" in_work bash "$SCRIPTS/check-version.sh"
g tag v1.0.0

# --- release-pr.sh: refusals ---
fails "release-pr: nothing under [Unreleased]" in_work bash "$SCRIPTS/release-pr.sh" patch
add_entry alpha
fails "release-pr: a bad argument" in_work bash "$SCRIPTS/release-pr.sh" huge
fails "release-pr: no bump given" in_work bash "$SCRIPTS/release-pr.sh"
ok "release-pr: no bump says usage" grep -q "usage: .*patch|minor|major" "$T/out"
echo x >> "$W/CHANGELOG.md"
fails "release-pr: a dirty tree" in_work bash "$SCRIPTS/release-pr.sh" patch
g checkout -q -- . && g checkout -q -b elsewhere
fails "release-pr: not on main" in_work bash "$SCRIPTS/release-pr.sh" patch
g checkout -q main && g reset -q --hard HEAD~1
fails "release-pr: main behind origin/main" in_work bash "$SCRIPTS/release-pr.sh" patch
g reset -q --hard origin/main

echo "" > "$T/ci"
fails "release-pr: CI on main still running" in_work bash "$SCRIPTS/release-pr.sh" patch
echo failure > "$T/ci"
fails "release-pr: CI on main failed" in_work bash "$SCRIPTS/release-pr.sh" patch
echo none > "$T/ci"
fails "release-pr: no CI run on main" in_work bash "$SCRIPTS/release-pr.sh" patch
ok "release-pr: asks about this main commit's push run" grep -q "gh run list --workflow ci.yml --commit $(g rev-parse HEAD) --event push" "$T/gh.log"
rm "$T/ci"
g branch release/v1.0.1  # a leftover from an earlier attempt
fails "release-pr: a leftover local release branch" in_work bash "$SCRIPTS/release-pr.sh" patch
ok "release-pr: refused before editing (local leftover)" test -z "$(g status --porcelain)"
g branch -D release/v1.0.1 > /dev/null && g push -q origin main:refs/heads/release/v1.0.1
fails "release-pr: a leftover release branch on origin" in_work bash "$SCRIPTS/release-pr.sh" patch
ok "release-pr: refused before editing (origin leftover)" test -z "$(g status --porcelain)"
g push -q origin :refs/heads/release/v1.0.1

# --- release-pr.sh: the PR ---
ok "release-pr: patch" in_work bash "$SCRIPTS/release-pr.sh" patch
ok "release-pr: back on main" test "$(g branch --show-current)" = main
ok "release-pr: the branch is pushed" test -n "$(remote_ref refs/heads/release/v1.0.1)"
ok "release-pr: plugin.json bumped" test "$(g show release/v1.0.1:plugins/pd/.claude-plugin/plugin.json | jq -r .version)" = 1.0.1
ok "release-pr: [Unreleased] promoted" test "$(g show release/v1.0.1:CHANGELOG.md | grep -A4 '^## \[Unreleased\]' | grep -c -e '^## \[1\.0\.1\] - ' -e '^- alpha')" = 2
ok "release-pr: the PR is opened into main" grep -q 'gh pr create --base main --head release/v1.0.1' "$T/gh.log"
ok "release-pr: main untouched" test "$(manifest_version)" = 1.0.0

# --- publish-release.sh ---
ok "publish: between releases, nothing to do" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: stable unmoved" test "$(remote_ref refs/heads/stable)" = "$(g rev-parse v1.0.0)"
merge_pr release/v1.0.1
add_entry beta
fails "release-pr: refuses while v1.0.1 isn't published" in_work bash "$SCRIPTS/release-pr.sh" patch
release1=$(g rev-parse main~1)  # the release merge; main is now the beta merge on top
# CI gates each push's publish run, so only the release commit's own run may publish it.
fails "publish: a later push doesn't publish an unpublished release" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: says to re-run the release commit's CI" grep -q "re-run CI on $release1" "$T/out"
ok "publish: no tag from a later push" test -z "$(remote_ref refs/tags/v1.0.1)"
ok "publish: stable unmoved by a later push" test "$(remote_ref refs/heads/stable)" = "$(g rev-parse v1.0.0)"
ok "publish: the release commit's own run publishes it" in_work bash "$SCRIPTS/publish-release.sh" "$release1"
ok "publish: v1.0.1 at the release merge" test "$(remote_ref refs/tags/v1.0.1)" = "$release1"
ok "publish: stable at the release merge" test "$(remote_ref refs/heads/stable)" = "$release1"
ok "publish: a re-run is a no-op" in_work bash "$SCRIPTS/publish-release.sh" "$release1"
ok "publish: re-run says so" grep -q 'is published' "$T/out"
ok "publish: a later push after it is a no-op" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: later push says so" grep -q 'is published' "$T/out"

g fetch -q --tags origin
ok "release-pr: minor" in_work bash "$SCRIPTS/release-pr.sh" minor
ok "release-pr: minor is 1.1.0" test -n "$(remote_ref refs/heads/release/v1.1.0)"
merge_pr release/v1.1.0
g push -q origin "$(g rev-parse main~2):refs/tags/v1.1.0"  # a stray tag at another commit
fails "publish: a tag at another commit" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: stable unmoved after a failure" test "$(remote_ref refs/heads/stable)" = "$release1"
g push -q origin :refs/tags/v1.1.0 && g tag -d v1.1.0 > /dev/null
g fetch -q origin && g checkout -q -b stray origin/stable && g commit -q --allow-empty -m stray && g push -q -f origin stray:stable && g checkout -q main
fails "publish: stable can't fast-forward" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: no tag after a failure" test -z "$(remote_ref refs/tags/v1.1.0)"
g push -q -f origin "$release1:refs/heads/stable"
printf '#!/bin/sh\n[ "$1" != refs/heads/stable ]\n' > "$T/origin.git/hooks/update" && chmod +x "$T/origin.git/hooks/update"
fails "publish: the server refuses the stable update" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: atomic, so no tag either" test -z "$(remote_ref refs/tags/v1.1.0)"
rm "$T/origin.git/hooks/update"
ok "publish: a re-run recovers, v1.1.0" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: stable at v1.1.0" test "$(remote_ref refs/heads/stable)" = "$(remote_ref refs/tags/v1.1.0)"

g checkout -q -b bump main && set_version 1.1.1 && g commit -qam "a bump with no CHANGELOG section" && merge_pr bump
fails "publish: no CHANGELOG section for the version" in_work bash "$SCRIPTS/publish-release.sh"
ok "publish: nothing pushed without it" test -z "$(remote_ref refs/tags/v1.1.1)"

# --- check-changelog.sh ---
fresh
add_entry gamma
base=$(g rev-parse main)
perl -pi -e 's/^## \[Unreleased\]$/## [Unreleased]\n\n- delta/' "$W/CHANGELOG.md"
ok "check-changelog: an [Unreleased] entry" in_work bash "$SCRIPTS/check-changelog.sh" "$base"
g checkout -q -- . && perl -pi -e 's/^- first$/- first, reworded/' "$W/CHANGELOG.md"
fails "check-changelog: a released section edited" in_work bash "$SCRIPTS/check-changelog.sh" "$base"
g checkout -q -- . && perl -pi -e 's/^## \[Unreleased\]$/## [Unreleased]\n\n## [1.0.1] - 2026-01-02/' "$W/CHANGELOG.md"
ok "check-changelog: a release prepends a section" in_work bash "$SCRIPTS/check-changelog.sh" "$base"
g checkout -q -- .
# A late feature PR merged after a release: git files its entry under the released section, no conflict.
g checkout -q -b feature/late main
perl -pi -e 's/^- gamma$/- gamma\n- late/' "$W/CHANGELOG.md" && g commit -qam late
g checkout -q main && perl -pi -e 's/^## \[Unreleased\]$/## [Unreleased]\n\n## [1.0.1] - 2026-01-02/' "$W/CHANGELOG.md"
g commit -qam "release 1.0.1"
released=$(g rev-parse main)
if g merge -q --no-ff --no-edit feature/late > /dev/null 2>&1; then
    fails "check-changelog: a late entry merged into a released section" in_work bash "$SCRIPTS/check-changelog.sh" "$released"
else
    g merge --abort; echo "note: this git conflicted on the late-entry merge; that case is covered by the conflict itself"
fi

# --- .claude/hooks/protect-release-refs.py: only CI's publish job pushes stable or a v* tag ---
HOOK="$SCRIPTS/../.claude/hooks/protect-release-refs.py"
hook() { jq -n --arg c "$1" '{tool_name: "Bash", tool_input: {command: $c}}' | python3 "$HOOK"; }
check_exit() { local name=$1 want=$2 got; shift 2; "$@" > "$T/out" 2>&1; got=$?
    if [[ "$got" == "$want" ]]; then pass=$((pass + 1)); else failed=$((failed + 1)); echo "FAIL: $name (exit $got)"; sed 's/^/    /' "$T/out"; fi; }
blocks() { check_exit "hook blocks: $1" 2 hook "$1"; }
allows() { check_exit "hook allows: $1" 0 hook "$1"; }
blocks "git push origin HEAD:stable"
blocks "git push origin stable"
blocks "git push origin +abc123:refs/heads/stable"
blocks "git push origin v8.2.0"
blocks "git push origin abc123:refs/tags/v9.0.0"
blocks "git push --tags"
blocks "git push --follow-tags origin main"
blocks "git -C /tmp/x push origin main:stable"
blocks "/usr/bin/git push origin stable"
blocks "git status && git push origin main:stable"
blocks "git fetch -q
git push origin stable"
blocks "bash -c 'git push origin HEAD:stable'"
allows "git push origin main"
allows "git push -u origin chore/stable-docs"
allows "git push origin vendor-fix"
allows "git push origin v2-redesign"
allows "git commit -m 'push to stable' && git push origin chore/x"
allows "git log --grep push stable"
allows "ls stable"
allows "echo 'unbalanced"
allows "git commit -m 'the hook refuses a git push to stable'"
allows "git commit -F - <<'MSG'
the hook refuses a git push to stable
MSG
git log -1"
blocks "git commit -F - <<'MSG'
a message
MSG
git push origin stable"
blocks "eval 'git push origin v9.0.0'"
blocks "# publish
git push origin HEAD:stable"
blocks "bash -lc 'git push origin HEAD:stable'"
blocks "bash <<'EOF'
git push origin HEAD:stable
EOF"
blocks "git -c remote.origin.push=HEAD:stable push origin"
allows "git push origin main # not stable"
allows "git push --dry-run origin HEAD:stable"
allows "git push -n origin v8.2.0"
allows "git -c user.name=stable-bot push origin main"
ok "hook: the block says why" sh -c "hook_out=\$(jq -n '{tool_input: {command: \"git push origin stable\"}}' | python3 '$HOOK' 2>&1); echo \"\$hook_out\" | grep -q 'publish-release.sh'"
ok "hook: registered for Bash in .claude/settings.json" jq -e '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[].command | contains("protect-release-refs.py")' "$SCRIPTS/../.claude/settings.json"

echo "test-release: $pass passed, $failed failed"
[[ "$failed" == 0 ]]
