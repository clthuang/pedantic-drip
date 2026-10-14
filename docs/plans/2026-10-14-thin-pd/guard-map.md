# Thin pd: the transition-gate guard map (T1.2, 2026-10-15)

Each of the 43 guards in `GUARD_METADATA` (`plugins/pd/hooks/lib/transition_gate/constants.py`) mapped to one of (plan §A9 row 1, §16 step 4):
- **`phase-gate`:** a phase's exit check in `phase-gate.sh <phase>` (§5). The skill runs it before moving `phase:` on, and `pd-lint` re-runs it at commit for every earlier phase.
- **`pd-lint`:** one of the checks in §9's "What `pd-lint` checks".
- **`dropped`:** nothing replaces it, for the reason given. §A9 accepts "any guard the mapping drops" as a loss.

**Sources:** what each guard checks today is read from `transition_gate/gate.py` (the function that emits it) and `PHASE_GUARD_MAP`/`SERVICE_GUARD_MAP` in `constants.py`. The names come from `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml`, whose iflow-era names predate feature 134 (one `shape.md` for specify and design; `create-tasks` folded into `create-plan`). Where the two disagree, the code wins.

T2.1 deletes `transition_gate/` only after this file is committed (build-tasks T1.2).

## The map

| Guard | Today (`gate.py` function) | Mapping | Reason |
|---|---|---|---|
| G-02 | `validate_artifact` level 1: the phase's artifact exists | phase-gate | `need_file` in every phase's exit check |
| G-03 | `validate_artifact` level 2: the artifact is at least 100 bytes | dropped | The section checks (G-04 to G-06) and `pd-lint`'s expectation and plan-task formats are stronger than a byte count |
| G-04 | `validate_artifact` level 3: the artifact has markdown headings | phase-gate | `need_section` requires the named `##` headings, which subsumes "has headings" |
| G-05 | `validate_artifact` level 4: `shape.md`'s required sections | phase-gate | `phase-gate.sh specify` and `design` require `## Requirements` and `## Design` |
| G-06 | `validate_artifact` level 4: `plan.md`'s required sections | phase-gate | `phase-gate.sh create-plan` requires `plan.md` and its section; `pd-lint` checks each task's fields (§9 Plans) |
| G-07 | `validate_prd`: a PRD exists before a project is created | dropped | A plan holds its PRD in its own body (§7.1); there is no separate `prd.md` to require |
| G-08 | `check_hard_prerequisites`: design needs `shape.md`, implement needs `shape.md` and `plan.md` | pd-lint | `pd-lint` re-runs `phase-gate.sh` for every phase before the feature's current one (§9 Phase artifacts), which is this table enforced at commit (§A9 row 1) |
| G-09 | `check_prd_exists`: soft redirect when specify starts without a PRD | dropped | The entry picks the depth (§A2): a direct request enters at Criteria with no PRD, by design |
| G-11 | `check_branch`: the checkout isn't the feature's branch | dropped | The frontmatter's `branch:` names it, and the playbooks check it out before launching a workflow (§A4); §9 has no branch check |
| G-13 | `fail_open_mcp` (brainstorm): warn when MCP registration fails | dropped | No MCP servers (§A6) |
| G-14 | `fail_open_mcp` (create-feature) | dropped | No MCP servers (§A6) |
| G-15 | `fail_open_mcp` (create-project) | dropped | No MCP servers (§A6) |
| G-16 | `fail_open_mcp` (retrospective): warn when the memory store write fails | dropped | Lessons land in checks, CLAUDE.md or skills, never a store (§A8.3 S4) |
| G-17 | `check_partial_phase`: a phase started but never completed | dropped | Resume reads `## Now`, its `run in flight:` line and `log.md` (§8); `pd-lint` checks only the key lines' format |
| G-18 | `check_backward_transition`: warns on a move to an earlier phase | pd-lint | Going back is normal (§A2): it must be a `phase` entry marked `(back)`, and a second one is a retro trigger `pd-lint` enforces when the feature is `done` (§9) |
| G-22 | `validate_transition`: the canonical phase sequence | pd-lint | `phase` is from the closed list (§9 Vocabularies), and the earlier phases' exit checks must pass (§9 Phase artifacts), so phases can't be skipped out of order |
| G-23 | `check_soft_prerequisites`: warns about skipped phases | pd-lint | A skip is legal only through `mode: express`, whose mini-spec check replaces the skipped exit checks (§9); any other skip fails the earlier phases' exit checks |
| G-25 | `get_next_phase` (secretary's workflow guardian): suggests the next phase | dropped | A suggestion, not a check: `pd-status` and the `SessionStart` summary show the next step (§9, §11) |
| G-27 | `pre_merge_validation` (finish-feature): checks pass before merge, with retries | phase-gate | `phase-gate.sh verify`: a `qa` entry with every `qa_battery` command passing at its recorded commit, no source, test or fixture change since, and no open blockers (§A2 row 6) |
| G-28 | `check_merge_conflict` (finish-feature): a failed merge stops | dropped | A merge conflict is a hard stop in the playbook (§A5), an AskUserQuestion, not a script check |
| G-29 | `pre_merge_validation` (wrap-up) | dropped | The duplicate of G-27 in wrap-up (guard-rules cluster 4); `/pd:wrap-up` doesn't merge |
| G-30 | `check_merge_conflict` (wrap-up, YOLO hard stop) | dropped | YOLO retires (§A5); a merge conflict is a hard stop (G-28) |
| G-31 | `brainstorm_readiness_gate`: the PRD readiness loop | dropped | A PRD gets no review; calvin covers it at Criteria (§A2 row 1, §A8.3 S2) |
| G-32 | `brainstorm_quality_gate`: the PRD quality review loop | dropped | `prd-reviewer` retires (§A8.3 S2) |
| G-33 | `brainstorm_readiness_gate`: blockers remain or the cap is reached | dropped | As G-31 |
| G-34 | `review_quality_gate` (create-plan): the plan review approved or capped | dropped | The test-case review is the conductor's bounded loop (§A2 row 4); an open blocker it leaves shows in `pd-status` and holds the `Stop` gate (§A5, §11). No script requires the `review` entry itself (D18: the user, "No, as planned") |
| G-35 | `phase_handoff_gate` (create-plan): the handoff review | dropped | As G-34: one review moment per stage, no separate handoff review (§A8.3 S2) |
| G-36 | `review_quality_gate` (create-tasks) | dropped | No emitter since feature 134 folded `create-tasks` into `create-plan` (absent from `PHASE_GUARD_MAP`); the test-case review covers it |
| G-37 | `phase_handoff_gate` (create-tasks) | dropped | As G-36 |
| G-38 | `review_quality_gate` (design): the design review approved or capped | dropped | As G-34, for the design review (§A2 row 3; D18) |
| G-39 | `phase_handoff_gate` (design) | dropped | As G-35 |
| G-40 | `review_quality_gate` (implement): the code review approved or capped | phase-gate | The code review moves to Verify, and `phase-gate.sh verify` requires no open blockers (§A2 row 6) |
| G-41 | `implement_circuit_breaker`: the review-iteration cap | pd-lint | The cap becomes control flow, a loop bounded at three in `verify-change` and `implement-tasks` (§A4); the `capped` entry it leaves must have its four lists and backlog lines (§9) |
| G-45 | `secretary_review_criteria`: skip the triage reviewer on a confident match | dropped | Triage is the model applying `/pd:secretary`'s rules, with no reviewer (§A9, the triage row) |
| G-46 | `review_quality_gate` (specify): the spec review approved or capped | phase-gate | `phase-gate.sh specify` requires the user's sign-off `decision` entry, which follows calvin's cycles (§A2 row 2) |
| G-47 | `phase_handoff_gate` (specify) | phase-gate | As G-46: the sign-off entry is Criteria's handoff |
| G-48 | `check_active_feature_conflict`: warns when another feature is active | dropped | Several active features are normal; `pd-status` lists them (§11) |
| G-49 | `check_active_feature`: specify starts with no feature | dropped | Triage's `pd-new feature` creates the feature before Criteria (§A2 row 0) |
| G-50 | `planned_to_active_transition`: a planned feature becomes active | pd-lint | A roadmap's `planned:` line becomes a `feature:` line through `pd-new --plan`, and a `planned:` slug that already exists as a feature fails `pd-lint` (§7.1, §9 Roadmaps) |
| G-51 | `check_terminal_status`: blocks changes to a completed or abandoned feature | dropped | A done item stays in place as history (§10), and a `defect` entry on a done feature is allowed (§6, §9); any reopening is a reviewed frontmatter diff in git |
| G-52 | `check_task_completion` (finish-feature): incomplete tasks | phase-gate | `phase-gate.sh implement`: a `run` entry recording every plan task merged with its proof passing (§16 step 5) |
| G-53 | `check_task_completion` (wrap-up) | dropped | The duplicate of G-52 in wrap-up (guard-rules cluster 6); `/pd:wrap-up` doesn't finish |
| G-60 | `check_orchestrate_prerequisite`: orchestrate needs YOLO | dropped | YOLO retires; `/goal` drives (§A5) |

## Totals

| Mapping | Guards |
|---|---|
| phase-gate | 9: G-02, G-04, G-05, G-06, G-27, G-40, G-46, G-47, G-52 |
| pd-lint | 6: G-08, G-18, G-22, G-23, G-41, G-50 |
| dropped | 28 |

## The user's ruling (D18, 2026-10-15)

**The design and test-case reviews aren't mechanically required** (G-34, G-35, G-38, G-39): "No, as planned". §A2's "Mechanical gate" column for Contracts and Plan names no review entry, and `phase-gate.sh verify` alone requires "no open blockers". An open blocker still shows in `pd-status` and holds a goal run's `Stop` gate.

## Proof

Run from the repository root:

```bash
# Every guard has exactly one row: both sets have 43 members and are equal (prints "43 43 True").
python3 - <<'EOF'
import ast, re
t = ast.parse(open('plugins/pd/hooks/lib/transition_gate/constants.py').read())
keys = next({k.value for k in n.value.keys} for n in ast.walk(t)
            if isinstance(n, (ast.Assign, ast.AnnAssign))
            and getattr(n.targets[0] if isinstance(n, ast.Assign) else n.target, 'id', '') == 'GUARD_METADATA')
rows = re.findall(r'^\| (G-\d+) \|', open('docs/plans/2026-10-14-thin-pd/guard-map.md').read(), re.M)
print(len(keys), len(rows), keys == set(rows) and len(rows) == len(set(rows)))
EOF
# Every row has a mapping (prints nothing).
grep -E '^\| G-[0-9]+ \|' docs/plans/2026-10-14-thin-pd/guard-map.md | awk -F' \\| ' '$3 !~ /^(phase-gate|pd-lint|dropped)$/'
```
