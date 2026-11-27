# Commands Reference

Every check CI runs (`.github/workflows/ci.yml`), in the form to run it locally.

## Tests and checks

Run them in a throwaway shell, so no test touches your real `~/.claude`:

- **Fresh `HOME`:** `export HOME=$(mktemp -d)` gives every test an empty home directory.
- **No `ENTITY_DB_PATH`:** `unset ENTITY_DB_PATH`. `pd-adopt` reads it as the path of the old entity registry, so unsetting it keeps the tests away from a live registry.

```bash
export HOME=$(mktemp -d); unset ENTITY_DB_PATH

# The whole battery, as CI and Verify's QA run it (scripts/test-all.sh lists each suite):
# validate.sh, the hook suites, the release tests, every pd-* self-test, the workflow tests, pytest over plugins/pd
bash scripts/test-all.sh

# One piece alone, for example:
./validate.sh                    # components, the version and doc drift (0 errors, 0 warnings expected)
bash scripts/test-release.sh     # release scripts and the protect-release-refs hook (throwaway repos, stub gh)
uv run --project plugins/pd pytest -q plugins/pd/scripts/test_pd_yolo.py

# On a pull request: released CHANGELOG sections are unchanged (new entries go under [Unreleased])
bash scripts/check-changelog.sh origin/main
```

## Release

Run it in your normal shell: `release-pr.sh` needs your `gh` login.

```bash
# Bumps plugin.json, promotes [Unreleased], opens a PR from release/vX.Y.Z into main (needs gh)
# Run on a clean main equal to origin/main, once CI on that commit has passed; name the bump by semver (no default)
scripts/release-pr.sh minor   # or patch, or major
# Merge the PR once CI passes; CI's publish job then tags vX.Y.Z and fast-forwards stable
```

`release-pr.sh` also refuses while the last version isn't published yet, and while `CHANGELOG.md` has nothing under `[Unreleased]`. The full flow is in [README_FOR_DEV.md "Release Process"](../../README_FOR_DEV.md#release-process).
