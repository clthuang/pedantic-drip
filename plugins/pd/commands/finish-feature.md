---
description: Run QA, retro, merge, and close out a feature
argument-hint: "[--feature=<id-slug>]"
---

# /pd:finish-feature

Contract command. Shared mechanics (entry, exit, YOLO, review gate, dispatch hygiene): workflow-transitions skill.

**Purpose:** prove the branch is releasable, capture what the feature taught, then merge and clean up.

**Inputs:** the feature's artifacts and its diff against `{pd_base_branch}`; engine phase state.

**Output:** `retro.md`; docs in sync; the branch merged to `{pd_base_branch}`; the feature entity terminal.

**Steps:**
1. Engine entry (workflow-transitions) with `target_phase="finish"`. Commit any stray working-tree changes before anything else runs.
2. QA battery — every check the project defines, each exiting zero:

```bash
./validate.sh
bash plugins/pd/hooks/tests/test-hooks.sh                                        # dev workspace
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/ -q                        # dev workspace
```

   Fix every failure on the branch and re-run the battery, including failures this feature did not introduce. Three failed rounds escalate to the user.
3. Docs sync: `updating-docs` skill.
4. Security surface touched (auth, secrets, input parsing, permissions, data deletion, dependency bumps): dispatch `pd:security-reviewer` — always a standard Anthropic-model Task. Its findings block the merge until fixed or waived by the user in writing.
5. Retro before cleanup: the `retrospecting` skill writes `retro.md` while the branch context still exists.
6. Mechanical gate: `bash scripts/phase-gate.sh finish {feature-dir}`.
7. Merge to `{pd_base_branch}` and push. A merge conflict is a hard stop in every mode.
8. Engine exit (workflow-transitions) with artifacts `[retro.md]` — that call is what marks the entity terminal. `.meta.json` is never hand-edited.
9. Cleanup: delete the feature branch and any `.pd-worktrees/` leftovers.

**Constraints:** retro runs before cleanup, never after — the context it reads disappears with the branch. Steps 2 through 6 all pass before step 7 starts. No state writes outside MCP tools; no phase-sequence or status-vocabulary restatement.
