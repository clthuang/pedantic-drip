"""Tests for the conductor prose (shape.md ## Design, ConductorProse and LogEntries; plan Task 11, cases C1 to C23)."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins/pd"
sys.path.insert(0, str(PLUGIN / "scripts"))
import pd_common as pc  # noqa: E402

SECRETARY = PLUGIN / "commands/secretary.md"
INIT = PLUGIN / "commands/init.md"
CREATE_WORKITEM = PLUGIN / "commands/create-workitem.md"
TRANSITIONS = PLUGIN / "skills/workflow-transitions/SKILL.md"
SPECIFYING = PLUGIN / "skills/specifying/SKILL.md"
PLANNING = PLUGIN / "skills/planning/SKILL.md"
VERIFYING = PLUGIN / "skills/verifying/SKILL.md"
FINISHING = PLUGIN / "skills/finishing-branch/SKILL.md"
REVIEW_CALL = PLUGIN / "references/review-call.md"
LOG_ENTRIES = PLUGIN / "references/log-entries.md"
SESSION = "${CLAUDE_SESSION_ID}"


def flat(path):
    """The file's text with every run of whitespace collapsed, so a wrapped line still matches."""
    return re.sub(r"\s+", " ", path.read_text())


def section(path, heading):
    """The text from `## <heading>` to the next `## ` heading, whitespace collapsed."""
    text = path.read_text()
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return re.sub(r"\s+", " ", text[start:end if end != -1 else len(text)])


def has_all(text, *needles):
    for needle in needles:
        assert needle in text, needle


def in_order(text, *needles):
    position = -1
    for needle in needles:
        found = text.find(needle, position + 1)
        assert found != -1, f"{needle!r} missing or out of order"
        position = found


def hint(path):
    return next(l for l in path.read_text().splitlines() if l.startswith("argument-hint:"))


def yolo():
    return section(TRANSITIONS, "YOLO")


def test_c1_secretary_offers_a_goal_run_without_yolo():
    text = flat(SECRETARY)
    has_all(text, "once the work item exists", "without YOLO", "one AskUserQuestion", "goal run to finish",
            "workflow-transitions", "Goal runs", "goal: <id> target finish session <id>", "committed before Criteria starts",
            "on no, no goal line is written")
    assert SESSION not in text  # D3: the session variable lives in workflow-transitions' "Goal runs"


def test_c22_secretary_starts_the_goal_run_under_yolo_and_replaces_the_old_session_line():
    text = flat(SECRETARY)
    has_all(text, "with YOLO on, the goal run starts per workflow-transitions without the question",
            "committed before Criteria starts", "`/pd:secretary --yolo` on an existing item",
            "in place of the old session's")


def test_c2_secretary_stage_mvp_depth():
    text = flat(SECRETARY)
    has_all(text, "At stage mvp, from the config or `--stage`", "`risk: security`", "`risk: migration`",
            "the only standard-depth triggers", "`stage: mvp`")


def test_c3_stage_argument_reaches_create_workitem():
    assert "[--yolo]" in hint(SECRETARY)
    assert "[--stage mvp|production]" in hint(SECRETARY)
    assert "[--stage mvp|production]" in hint(CREATE_WORKITEM)
    has_all(flat(SECRETARY), "passes `--stage` to `/pd:create-workitem`")
    assert "pd-new workitem $ARGUMENTS" in flat(CREATE_WORKITEM)


def test_c4_yolo_step_and_confirmation_commands():
    secretary = flat(SECRETARY)
    in_order(secretary, "`--yolo`", "workflow-transitions", "YOLO section", "before triage")
    text = yolo()
    in_order(text, "Hard stop: turn YOLO on for this session?", f"pd-yolo on --session {SESSION}",
             f"pd-yolo status --session {SESSION}", "must print `on`", "on no, carry on without YOLO")


def test_c5_confirmation_entry_comes_first_and_has_its_shape():
    in_order(yolo(), "Before the session's first entry in any item's log", "YOLO confirmation entry",
             "then the decisions made before that item existed")
    shape = flat(LOG_ENTRIES)
    in_order(shape, "YOLO confirmation", "Q: Hard stop: turn YOLO on for this session?",
             'A (user, verbatim): "Yes', "Session: <session id>")


def labels_in_order(text):
    in_order(text, *pc.DECISION_RECORD)


def test_c6_decision_record_labels_in_four_places(tmp_path):
    log = flat(LOG_ENTRIES)
    labels_in_order(log[log.index("Decision record"):])
    labels_in_order(yolo())
    print_line = next(l for l in TRANSITIONS.read_text().splitlines() if l.startswith("- **Print mode"))
    labels_in_order(print_line)
    home = tmp_path / "home"
    (home / ".claude/pd/gate").mkdir(parents=True)
    (home / ".claude/pd/gate/s1.yolo").write_text("2026-11-26T10:00:00+08:00\n")
    payload = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "cwd": "/",
               "tool_input": {"questions": [{"question": "Which name?"}]}}
    env = {**os.environ, "HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(PLUGIN)}
    r = subprocess.run(["bash", str(PLUGIN / "hooks/pd-yolo-guard.sh")], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2
    labels_in_order(r.stderr)


def test_c7_owner_turns_yolo_off():
    in_order(yolo(), "turn YOLO off", f"pd-yolo off --session {SESSION}")


def test_c8_promotion_moves_the_goal_line():
    has_all(yolo(), "Promotion moves this session's goal line from the brainstorm or rca to the new work item")


def test_c9_stage_change_rule():
    text = section(TRANSITIONS, "Stage changes")
    has_all(text, "a decision entry and the README's `stage:` edited, committed first", "mvp to production",
            "past specify", "moves back to specify with `Invalidates:`", "production to mvp moves nothing back",
            "pd-review-prompt verifying <dir>", "before the finish gate", "a done item is refused",
            "new production work item", "harden-later backlog line")


def test_c10_refused_command_goes_to_the_owner():
    has_all(yolo(), "a command the guard refused goes into a `Hard stop:` question showing it",
            "the owner runs it as `! <command>`", "the conductor never runs it itself",
            "an agent's reported refusal becomes such a question")


def test_c11_review_prompt_stage_and_harden_later():
    review_call = flat(REVIEW_CALL)
    has_all(review_call, "`pd-review-prompt <skill> <work item dir>`", "copies the reply's stage into a `Stage:` line")
    log = flat(LOG_ENTRIES)
    has_all(log, "Stage: <stage>", "harden-later")
    verifying = flat(VERIFYING)
    has_all(verifying, "`stage`", "`pd-review-prompt verifying <work item dir>`")


def test_c12_specifying_mvp_and_planning_green_only():
    specifying = flat(SPECIFYING)
    has_all(specifying, "At stage mvp", "closing `Deferred:` line", "judged at the sign-off",
            "by the conductor under YOLO", "Under YOLO the sign-off is answered on the owner's behalf",
            "decision record")
    has_all(flat(PLANNING), "`proof: green-only (mvp)` at stage mvp")


def test_c13_yolo_opens_the_pull_request():
    text = flat(FINISHING)
    in_order(text, "Under YOLO", "git push -u origin workitem/<id>", "gh pr create")


def test_c14_yolo_waits_with_pd_pr_checks():
    text = flat(FINISHING)
    has_all(text, "`pd-pr-checks <pr>`", "Bash timeout of 600000 ms", "repeated while it exits 8", "at most 7 times per wait",
            "exits 0 and 3 end the wait", "1 starts a fix cycle", "2 asks `Hard stop: gh failed`",
            "at most 3 fix cycles", "each fix with a decision record", "pushes, then waits again")


def test_c23_yolo_reads_review_comments_after_each_wait():
    text = flat(FINISHING)
    has_all(text, "after each wait", "`gh pr view <pr> --comments`", "`gh api repos/{owner}/{repo}/pulls/<pr>/comments`",
            "actionable", "even when the checks passed")


def test_c15_yolo_hard_stops_at_the_end_of_the_pull_request():
    text = flat(FINISHING)
    has_all(text, "`Hard stop: checks still failing`", "after the third fix cycle", "follows the owner's answer",
            "`Hard stop: ready to merge?`", "no failure and no open comment")
    in_order(text, "`Hard stop: ready to merge?`", f"pd-yolo off --session {SESSION}", "gh pr merge")
    has_all(text, "on no, clear the goal line and run the same `pd-yolo off`")


def test_c16_yolo_without_remote_or_gh():
    has_all(flat(FINISHING), "no remote or no `gh`", "`Hard stop: branch ready; no remote to open a pull request on`")


def test_c17_harden_later_line_precedes_the_finish_gate():
    text = flat(FINISHING)
    has_all(text, "harden-later", "(from: workitems/<id>)")
    assert text.index("(from: workitems/<id>)") < text.index("phase-gate.sh finish")


def test_c18_init_asks_the_stage():
    text = flat(INIT)
    has_all(text, "AskUserQuestion", "mvp or production", "sets the config's `stage` key to the answer")


def test_c19_probe_ruling_shape():
    has_all(flat(LOG_ENTRIES), "Ruling: B<n>", "Next: none (Met only) | phase <from> -> <to> (back) | backlog <id>")


def test_c20_hard_stop_prefix_and_dispatch():
    text = flat(TRANSITIONS)
    has_all(text, "requires the `Hard stop:` prefix")
    dispatch = section(TRANSITIONS, "Dispatch")
    has_all(dispatch, "codebase-explorer", "internet-researcher", "investigation-agent", "skill-searcher", "at any stage")


def run(*command):
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def test_c21_suites_pass_and_finishing_names_pd_pr_checks():
    assert "pd-pr-checks" in FINISHING.read_text()  # true only after the change
    for command in (("bash", "plugins/pd/hooks/tests/test-hooks.sh"), ("./validate.sh",)):
        r = run(*command)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


def test_p2_probe_ruling_is_a_hard_stop_asked_at_finish():
    has_all(flat(LOG_ENTRIES), "Q: Hard stop: <the probe's question>")
    has_all(flat(TRANSITIONS), "a probe ruling")
    has_all(flat(FINISHING), "Probe ruling", "`Hard stop:` AskUserQuestion", "Met", "Missed")
