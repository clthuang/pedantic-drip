#!/usr/bin/env bash
# Opens the release PR: bumps plugin.json's version and promotes CHANGELOG.md's [Unreleased] section.
# You merge it once CI passes; .github/workflows/publish.yml then tags it and moves stable.
# Usage: scripts/release-pr.sh [patch|minor|major]   (default patch)
set -euo pipefail

MANIFEST=plugins/pd/.claude-plugin/plugin.json
die() { echo "release-pr: $*" >&2; exit 1; }

part=${1:-patch}
case "$part" in patch|minor|major) ;; *) die "usage: $0 [patch|minor|major]" ;; esac
command -v gh >/dev/null || die "gh (GitHub CLI) is required to open the PR"
[[ "$(git branch --show-current)" == main ]] || die "run it on main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || die "commit or stash your changes first"
git fetch -q --tags origin main stable
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || die "main isn't origin/main: pull first"

current=$(jq -r '.version' "$MANIFEST")
{ git rev-parse -q --verify "refs/tags/v$current" >/dev/null && git merge-base --is-ancestor "v$current" origin/stable; } \
    || die "v$current isn't published yet (its tag and stable): wait for the Publish workflow"
IFS=. read -r major minor patch <<<"$current"
case "$part" in
    major) next="$((major + 1)).0.0" ;;
    minor) next="$major.$((minor + 1)).0" ;;
    patch) next="$major.$minor.$((patch + 1))" ;;
esac
! git rev-parse -q --verify "refs/tags/v$next" >/dev/null || die "v$next already exists"
awk '/^## \[Unreleased\]/ { f = 1; next } /^## \[/ { f = 0 } f && NF { n++ } END { exit !n }' CHANGELOG.md \
    || die "CHANGELOG.md has nothing under [Unreleased]"

OLD=$current NEW=$next perl -pi -e 's/("version":\s*")\Q$ENV{OLD}\E"/$1$ENV{NEW}"/' "$MANIFEST"
[[ "$(jq -r '.version' "$MANIFEST")" == "$next" ]] || die "couldn't set the version in $MANIFEST"
awk -v h="## [$next] - $(date +%Y-%m-%d)" '!done && /^## \[Unreleased\]/ { print; print ""; print h; done = 1; next } 1' \
    CHANGELOG.md > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md
notes=$(awk -v h="## [$next]" 'index($0, h) == 1 { f = 1; next } /^## \[/ { f = 0 } f' CHANGELOG.md)

branch="release/v$next"
git checkout -q -b "$branch"
git commit -q -m "release: v$next" -- "$MANIFEST" CHANGELOG.md
git push -q -u origin "$branch"
gh pr create --base main --head "$branch" --title "Release v$next" --body "$notes"
git checkout -q main
echo "release-pr: opened the v$next PR; merge it once CI passes"
