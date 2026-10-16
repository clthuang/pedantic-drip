# Commands Reference

Run every test with a throwaway `HOME`, so no test touches your real `~/.claude`. Prefix each command below with `env -u ENTITY_DB_PATH HOME=$(mktemp -d)`.

```bash
# Validate components (0 errors, 0 warnings expected)
./validate.sh

# Docs match the components (skill, command, agent and hook counts)
bash scripts/check-doc-drift.sh

# Script self-tests (stdlib Python)
for s in pd-lint pd-proof pd-adopt pd-new pd-status pd-init pd-review-filter; do python3 plugins/pd/scripts/$s --self-test; done
python3 plugins/pd/scripts/pd_common.py --self-test
uv run plugins/pd/scripts/pd-html.py --self-test

# Phase exit checks
bash plugins/pd/scripts/test-phase-gate.sh

# Hooks: each new hook's own test, then the integration suite
bash plugins/pd/hooks/tests/test-pd-commit-lint.sh
bash plugins/pd/hooks/tests/test-pd-stop-gate.sh
bash plugins/pd/hooks/tests/test-pd-session-start.sh
bash plugins/pd/hooks/tests/test-pd-agent-write-guard.sh
bash plugins/pd/hooks/tests/test-hooks.sh

# Workflow scripts: syntax, result shapes and stubbed runs
node plugins/pd/workflows/tests/test-workflows.mjs

# Python hook tests (project root, unicode guard)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks -q

# Release (bumps version, merges develop→main, tags)
# Uses --ci for non-interactive; BUMP_OVERRIDE=patch|minor|major to force bump type
bash scripts/release.sh --ci
# Preconditions: (1) clean working tree — git stash first, (2) CHANGELOG.md needs entries under [Unreleased]
```
