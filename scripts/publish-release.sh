#!/usr/bin/env bash
# Publishes the version on main: tags vX.Y.Z on the commit where plugin.json's version became X.Y.Z,
# and fast-forwards stable (the branch the marketplace follows) to it.
# Converges: a re-run, a superseded run or any later push to main reaches the same end state,
# and between releases it does nothing.
# Usage: scripts/publish-release.sh [commit]   (default HEAD; run by .github/workflows/publish.yml)
set -euo pipefail

MANIFEST=plugins/pd/.claude-plugin/plugin.json
die() { echo "publish: $*" >&2; exit 1; }
version_at() { git show "$1:$MANIFEST" 2>/dev/null | jq -r '.version // empty'; }

head=$(git rev-parse "${1:-HEAD}^{commit}")
version=$(version_at "$head")
[[ -n "$version" ]] || die "no version in $MANIFEST at $head"

# The release commit: the newest first-parent commit whose first parent had another version.
# Derived from history, not from the pushed commit, so every run picks the same one.
release=""
for c in $(git rev-list --first-parent "$head" -- "$MANIFEST"); do
    if [[ "$(version_at "$c^")" != "$version" ]]; then release=$c; break; fi
done
[[ -n "$release" ]] || die "can't find the commit where the version became $version"

git fetch -q --tags origin "+refs/heads/stable:refs/remotes/origin/stable" || die "can't fetch origin's stable branch"
stable=$(git rev-parse refs/remotes/origin/stable)
tag=$(git rev-parse -q --verify "refs/tags/v$version^{commit}" || true)
[[ -z "$tag" || "$tag" == "$release" ]] || die "v$version is at $tag, not at $release where the version became $version"

refs=""
[[ -n "$tag" ]] || refs="$release:refs/tags/v$version"
if ! git merge-base --is-ancestor "$release" "$stable"; then
    git merge-base --is-ancestor "$stable" "$release" || die "stable ($stable) can't fast-forward to $release"
    refs="$refs $release:refs/heads/stable"
fi
if [[ -z "$refs" ]]; then echo "publish: v$version is published"; exit 0; fi

git show "$release:CHANGELOG.md" | awk -v h="## [$version]" 'index($0, h) == 1 { found = 1 } END { exit !found }' \
    || die "CHANGELOG.md has no '## [$version]' section at $release"
# Atomic: the tag and stable move together or not at all.
git push --atomic origin $refs
echo "publish: v$version at $release"
