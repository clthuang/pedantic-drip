# Commands Reference

Every check CI runs (`.github/workflows/ci.yml`), in the form to run it locally.

## Tests and checks

Run them in a throwaway shell, so no test touches your real `~/.claude`:

- **Fresh `HOME`:** `export HOME=$(mktemp -d)` gives every test an empty home directory.
- **No `ENTITY_DB_PATH`:** `unset ENTITY_DB_PATH`. `pd-adopt` reads it as the path of the old entity registry, so unsetting it keeps the tests away from a live registry.

```bash
export HOME=$(mktemp -d); unset ENTITY_DB_PATH

# Validate components (0 errors, 0 warnings expected).
# It also runs check-doc-drift.sh, check-version.sh and test-hooks.sh.
./validate.sh

# Docs match the components (skill, command, agent and hook counts)
bash scripts/check-doc-drift.sh

# Script self-tests (stdlib Python)
for s in pd-lint pd-proof pd-adopt pd-new pd-status pd-init pd-review-filter; do python3 plugins/pd/scripts/$s --self-test; done
python3 plugins/pd/scripts/pd_common.py --self-test
uv run --script plugins/pd/scripts/pd-html.py --self-test

# Phase exit checks
bash plugins/pd/scripts/test-phase-gate.sh

# Hooks: each hook's own test, the promptimize content and git worktree suites, then the integration suite
bash plugins/pd/hooks/tests/test-pd-commit-lint.sh
bash plugins/pd/hooks/tests/test-pd-stop-gate.sh
bash plugins/pd/hooks/tests/test-pd-session-start.sh
bash plugins/pd/hooks/tests/test-pd-agent-write-guard.sh
bash plugins/pd/hooks/tests/test-promptimize-content.sh
bash plugins/pd/hooks/tests/test-worktree-dispatch.sh
bash plugins/pd/hooks/tests/test-hooks.sh

# Workflow scripts: syntax, result shapes and stubbed runs
node plugins/pd/workflows/tests/test-workflows.mjs

# Python hook tests (project root, unicode guard); uv creates the venv if it's missing
uv run --project plugins/pd pytest -q plugins/pd/hooks

# Release scripts' tests (throwaway repos, stub gh)
bash scripts/test-release.sh

# On a pull request: released CHANGELOG sections are unchanged (new entries go under [Unreleased])
bash scripts/check-changelog.sh origin/main
```

## Release

Run it in your normal shell: `release-pr.sh` needs your `gh` login.

```bash
# Bumps plugin.json, promotes [Unreleased], opens a PR from release/vX.Y.Z into main (needs gh)
# Run on a clean main equal to origin/main, once CI on that commit has passed; the bump is your choice, default patch
scripts/release-pr.sh [patch|minor|major]
# Merge the PR once CI passes; publish.yml then tags vX.Y.Z and fast-forwards stable
```

`release-pr.sh` also refuses while the last version isn't published yet, and while `CHANGELOG.md` has nothing under `[Unreleased]`. The full flow is in [README_FOR_DEV.md "Release Process"](../../README_FOR_DEV.md#release-process).
