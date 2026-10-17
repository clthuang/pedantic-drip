# Workflow results and the review's issue schema

The structured output of pd's workflows and of the review call (plan §A4). Each workflow script pins its `schema`; this file restates it in one place. The conductor writes `log.md` entries from these results (`references/log-entries.md`).

## Every workflow result

```json
{
  "stopped": null,
  "agents_used": 6,
  "tokens": 412000
}
```

- **`stopped`:** `null`, or `"budget"` when `workflow_output_cap` ended the run early. A stopped run's other fields are partial.
- **`agents_used`:** the agents the run launched.
- **`tokens`:** output tokens the run spent, from `budget.spent()`.

## `implement-tasks`

```json
{
  "tasks": [
    {
      "id": 1,
      "branch": "pd/2026-10-14-x/task-1",
      "head": "6ccfa3a5",
      "case_map": {"C1": "tests/test_parse.py::test_empty_input"},
      "proof": {"first": "fail", "head": "pass", "greens": [], "skipped": []},
      "cycles": 0,
      "flakes": [],
      "status": "merged"
    }
  ]
}
```

- **`case_map`:** each plan test case id mapped to the test that encodes it.
- **`proof`:** `pd-proof`'s verdict at the first commit and at HEAD. `greens` and `skipped` name tests already green, or skipped, at the first commit, for the Verify reviewer.
- **`cycles`:** fix cycles spent; the first run is not a cycle.
- **`flakes`:** tests whose runs disagreed, each `{test, runs}`; the conductor writes one `note` per flake.
- **`status`:** `merged`, `failed` or `wrong-test` (a wrong test case sends the task back to Plan).

## `verify-change`

```json
{
  "review": {"approved": false, "issues": [], "summary": ""},
  "reviewed_by": "codex (fallback: no)",
  "qa": {"commit": "6ccfa3a5", "ran": [{"command": "", "result": "pass"}], "gaps": [], "issues": []},
  "fixes": [{"issue": "R1", "commit": "9f2c1a7e", "test": "tests/test_parse.py::test_empty_input"}],
  "rejections": [{"issue": "R2", "evidence": "src/pd/io.py:12"}],
  "cycles": 1,
  "flakes": []
}
```

- **`reviewed_by`:** who made the review call, as the `review` entry's heading names it: `codex (fallback: no)`, `<Claude reviewer> (fallback: yes)` or `<Claude reviewer> (codex off)`; `null` when no usable review came back.
- **No usable review** (every reviewer failed, not a cap stop): `review.issues` holds one blocker, `{"id": "R0", "severity": "blocker", "category": "review", "file": <args.shape>, "line": 1, "claim": "no usable review: Codex and the Claude reviewer both failed", "evidence": ""}`. The fix cycles skip it; only a re-run review or the user's `decision` closes it.
- **`qa`:** `ran` holds the `qa_battery` lines only. Failures come back in `qa.issues` at `shape.md:1`: a battery command with a `fail` line is a blocker, `QB<n>` (n its place in the battery); QA's other failing checks are warnings, `QX<n>`.
- **A removal fix** (unneeded code deleted: see verifying's blocker bar) has an empty `test`: QA checks its commit deletes the code at the finding's file:line (plan §A2).
- **A budget stop's unstarted tasks** aren't listed: the conductor derives them from `plan.md` and the `pd/<id>/task-*` branches.

## `research-fanout` and `rca-fanout`

```json
{
  "findings": [
    {"claim": "", "evidence": "", "source": "", "verdict": "survived"}
  ]
}
```

- **`verdict`:** `rca-fanout` only: `survived` or `refuted`, from the refuter.

## The review call

```json
{
  "approved": false,
  "issues": [
    {"id": "R1", "severity": "blocker", "category": "correctness", "file": "src/pd/parse.py", "line": 41, "claim": "", "evidence": ""}
  ],
  "summary": ""
}
```

- **Issue fields:** `id severity category file line claim evidence`. `severity` is `blocker`, `warning` or `note`. `approved` is true only with no blocker.
- **A scoped re-review** returns `{"findings": [{"id", "status": "resolved | open | regressed", "evidence"}], "new_in_diff": [<issues>]}`. The conductor drops any new finding whose file and line fall outside the diff's hunks.
