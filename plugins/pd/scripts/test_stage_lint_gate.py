"""Tests for stage, decision records, risk and probe rulings in pd-lint and phase-gate.sh (plan Task 9, cases C1 to C14)."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[2]
LINT = str(SCRIPTS / "pd-lint")
GATE = str(SCRIPTS / "phase-gate.sh")

REQS = "## Requirements\n\nB1: an empty input -> the parser raises EmptyInput\n"
DESIGN = """## Design

### Architecture

```mermaid
flowchart LR
    A[cli] -->|ParseRequest| B[parser]
```

### Test strategy

- Runner: pytest --junitxml=PATH.
"""
STAGE_MESSAGE = "the review applied stage"


def item(repo):
    return repo.root / "docs" / "dev_artifacts" / "workitems" / repo.id


def set_fm(repo, **keys):
    """Set (or add) frontmatter keys of the work item's README."""
    path = item(repo) / "README.md"
    head, sep, rest = path.read_text().partition("\n---\n")
    lines = [l for l in head.split("\n") if l.split(":")[0] not in keys]
    lines += [f"{k}: {v}" for k, v in keys.items()]
    path.write_text("\n".join(lines) + sep + rest)


def append(repo, name, text):
    path = item(repo) / name
    path.write_text((path.read_text() if path.exists() else "") + text)


def entry(minute, kind, *lines):
    return f"\n## 2026-11-26 10:{minute:02d}+08:00 {kind}\n" + "\n".join(lines) + "\n"


def run(args, repo):
    return subprocess.run(args, cwd=repo.root, capture_output=True, text=True)


def lint(repo):
    r = run([sys.executable, LINT, str(item(repo))], repo)
    return r.returncode, r.stdout


def gate(repo, phase):
    r = run(["bash", GATE, phase, str(item(repo))], repo)
    return r.returncode, r.stdout


def errors(out):
    return [l for l in out.split("\n") if l.startswith("pd-lint: ERROR")]


def warnings(out):
    return [l for l in out.split("\n") if l.startswith("pd-lint: WARN")]


def valid_design(repo):
    (item(repo) / "shape.md").write_text(f"# Shape\n\n{REQS}\n{DESIGN}")


def review(minute, stage=None, *issues, suffix=""):
    body = ([f"Stage: {stage}"] if stage else []) + list(issues)
    return entry(minute, "review" + suffix, *body)


def test_c1_stage_vocabulary(pd_repo):
    set_fm(pd_repo, stage="beta")
    code, out = lint(pd_repo)
    bad = [l for l in errors(out) if "stage" in l and "beta" in l]
    assert code == 1 and len(bad) == 1
    assert re.match(r"pd-lint: ERROR \S*README\.md:\d+:", bad[0])
    set_fm(pd_repo, stage="mvp")
    code, out = lint(pd_repo)
    assert not [l for l in errors(out) if "stage" in l]


def test_c2_no_stage_key_and_brainstorm(pd_repo):
    code, out = lint(pd_repo)
    assert not [l for l in errors(out) if "stage" in l]
    made = run([sys.executable, str(SCRIPTS / "pd-new"), "brainstorm", "an idea"], pd_repo).stdout.strip()
    path = pd_repo.root / made
    path.write_text(path.read_text().replace("\n---\n", "\nstage: mvp\n---\n", 1))
    r = run([sys.executable, LINT, str(path)], pd_repo)
    bad = [l for l in errors(r.stdout) if "stage" in l and path.name in l]
    assert r.returncode == 1 and bad


RECORD = ["Session: s1", "Stage: mvp", "Pros/cons: a, b", "Trade-off: c", "Implications: d", "Premortem: e"]


def decision(*record):
    return entry(0, "decision", "Q: pick one?", "A (conductor, on the user's behalf): the first", *record)


def test_c3_decision_record(pd_repo):
    append(pd_repo, "log.md", decision(*RECORD))
    _, out = lint(pd_repo)
    assert not [l for l in errors(out) if "Premortem:" in l or "Session:" in l]
    for dropped in RECORD:
        label = dropped.split(" ")[0]
        (item(pd_repo) / "log.md").write_text("")
        append(pd_repo, "log.md", decision(*[l for l in RECORD if l != dropped]))
        code, out = lint(pd_repo)
        bad = [l for l in errors(out) if label in l]
        others = [x.split(" ")[0] for x in RECORD if x != dropped]
        assert code == 1 and len(bad) == 1, label
        assert not any(o in bad[0] for o in others), bad[0]
    (item(pd_repo) / "log.md").write_text("")
    append(pd_repo, "log.md", decision(RECORD[0], RECORD[1]))
    _, out = lint(pd_repo)
    named = [l for l in errors(out) if "Pros/cons:" in l]
    assert len(named) == 1 and all(x in named[0] for x in ("Trade-off:", "Implications:", "Premortem:"))
    set_fm(pd_repo, status="done")
    _, out = lint(pd_repo)
    assert [l for l in errors(out) if "Pros/cons:" in l]


def test_c4_deferred_line_warns_at_mvp(pd_repo):
    set_fm(pd_repo, stage="mvp")
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}")
    code, out = lint(pd_repo)
    assert [l for l in warnings(out) if "Deferred:" in l]
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}\nDeferred: none\n")
    code, out = lint(pd_repo)
    assert not [l for l in warnings(out) if "Deferred:" in l]
    set_fm(pd_repo, stage="production")
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}")
    code, out = lint(pd_repo)
    assert not [l for l in warnings(out) if "Deferred:" in l]


def plan_with(proof):
    return (f"---\nfrom_shape: x\n---\n# Plan\n\n## Plan\n\n### Wave 1\n\n#### Task 1: t [parallel-safe]\n"
            f"- files: a.py\n- uses: none\n- command: `pytest a --junitxml=j.xml`\n- junit: j.xml\n- proof: {proof}\n"
            "- test cases:\n  - C1 [B1] (fixture: none): a case.\n")


def test_c5_green_only_mvp_reason(pd_repo):
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}")
    (item(pd_repo) / "plan.md").write_text(plan_with("green-only (mvp)"))
    set_fm(pd_repo, stage="mvp")
    _, out = lint(pd_repo)
    assert not [l for l in errors(out) if "green-only" in l]
    set_fm(pd_repo, stage="production")
    _, out = lint(pd_repo)
    assert [l for l in errors(out) if "proof: green-only needs a reason" in l]


def test_c6_review_stage_must_match_the_item(pd_repo):
    for phase in ("verify", "design", "create-plan", "finish"):
        set_fm(pd_repo, stage="mvp", phase=phase)
        (item(pd_repo) / "log.md").write_text(review(1, "production"))
        code, out = gate(pd_repo, phase)
        want = f"GATE FAIL [{phase}]: the review applied stage production; the work item is mvp"
        assert code == 1 and want in out, (phase, out)
        (item(pd_repo) / "log.md").write_text(review(1, "mvp"))
        code, out = gate(pd_repo, phase)
        assert STAGE_MESSAGE not in out, (phase, out)


def test_c7_latest_stage_bearing_entry_decides(pd_repo):
    set_fm(pd_repo, stage="mvp", phase="design")
    valid_design(pd_repo)
    log = item(pd_repo) / "log.md"
    log.write_text(entry(1, "review", "Summary: a calvin cycle") + entry(2, "review", "- R1 note a.py:1 — old"))
    code, out = gate(pd_repo, "design")
    assert code == 0 and STAGE_MESSAGE not in out, out
    log.write_text(review(1, "production") + review(2, "mvp"))
    code, out = gate(pd_repo, "design")
    assert code == 0 and STAGE_MESSAGE not in out, out
    log.write_text(review(1, "production") + entry(2, "review", "Summary: no stage line"))
    code, out = gate(pd_repo, "design")
    assert code == 1 and STAGE_MESSAGE in out, out


def test_c8_stage_change_after_contracts_passes_the_replay(pd_repo):
    set_fm(pd_repo, stage="mvp", phase="implement")
    valid_design(pd_repo)
    (item(pd_repo) / "log.md").write_text(review(1, "production"))
    _, out = lint(pd_repo)
    assert STAGE_MESSAGE not in out, out
    set_fm(pd_repo, phase="design")
    code, out = gate(pd_repo, "design")
    assert code == 1 and STAGE_MESSAGE in out


def branch_with_api(repo):
    repo.git("checkout", "-q", f"workitem/{repo.id}")
    api = repo.root / "src" / "pkg" / "api.py"
    api.parent.mkdir(parents=True)
    api.write_text("@app.get('/x')\ndef x():\n    return 1\n")
    repo.git("add", "-A")
    repo.git("commit", "-q", "-m", "api")


@pytest.mark.parametrize("mode", ["standard", "express"])
def test_c9_security_signal_fails_verify(pd_repo, mode):
    branch_with_api(pd_repo)
    set_fm(pd_repo, mode=mode)
    code, out = gate(pd_repo, "verify")
    want = ("GATE FAIL [verify]: security signal src/pkg/api.py:1: "
            "add risk: security or a Risk: none (security) decision")
    assert code == 1 and want in out, out


def test_c10_risk_tag_or_waiver_passes(pd_repo):
    branch_with_api(pd_repo)
    set_fm(pd_repo, risk="[security]")
    _, out = gate(pd_repo, "verify")
    assert "security signal" not in out
    set_fm(pd_repo, risk="")
    (item(pd_repo) / "log.md").write_text(
        entry(1, "decision", "Q: security?", "A (user, verbatim): \"Fine\"",
              "Risk: none (security) — the match is message text"))
    _, out = gate(pd_repo, "verify")
    assert "security signal" not in out
    set_fm(pd_repo, risk="")
    (item(pd_repo) / "log.md").write_text("")
    _, out = gate(pd_repo, "verify")
    assert "security signal" in out


CONFIRM = ["Q: Hard stop: turn YOLO on for this session?", 'A (user, verbatim): "Yes, on"']
SIGNOFF = ["Q: criteria signed off?", "A (conductor, on the user's behalf): Yes."]


def test_c11_conductor_sign_off_needs_a_yolo_confirmation(pd_repo):
    set_fm(pd_repo, phase="specify")
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}")
    log = item(pd_repo) / "log.md"

    def run_with(confirm_session, sign_session, order=("confirm", "sign")):
        parts = {"confirm": entry(1, "decision", *CONFIRM, f"Session: {confirm_session}") if confirm_session else "",
                 "sign": entry(2, "decision", *SIGNOFF, f"Session: {sign_session}")}
        log.write_text("".join(parts[k] for k in order))
        return gate(pd_repo, "specify")

    code, out = run_with("s1", "s1")
    assert code == 0, out
    for args in (("s2", "s1"), (None, "s1"), ("s1", "s1", ("sign", "confirm"))):
        code, out = run_with(*args)
        assert code == 1 and "GATE FAIL [specify]" in out, args


def test_c11b_a_refusal_to_turn_yolo_on_is_not_a_confirmation(pd_repo):
    set_fm(pd_repo, phase="specify")
    (item(pd_repo) / "shape.md").write_text(f"# Shape\n\n{REQS}")
    refusal = [CONFIRM[0], 'A (user, verbatim): "No, keep YOLO off"']
    (item(pd_repo) / "log.md").write_text(entry(1, "decision", *refusal, "Session: s1") + entry(2, "decision", *SIGNOFF, "Session: s1"))
    code, out = gate(pd_repo, "specify")
    assert code == 1 and "GATE FAIL [specify]" in out, out


def test_c12_harden_later_lines_need_a_backlog_line(pd_repo):
    set_fm(pd_repo, stage="mvp", phase="finish")
    ts = "2026-11-26 10:01+08:00"
    issue = "- R{n} warning harden-later src/a.py:{n} — claim"
    (item(pd_repo) / "log.md").write_text(
        entry(1, "review", "Stage: mvp", issue.format(n=3), issue.format(n=5))
        + entry(1, "review-2", "Stage: mvp", issue.format(n=3)))
    refs = [f"review@{ts}#R3", f"review@{ts}#R5", f"review-2@{ts}#R3"]
    backlog = pd_repo.root / "docs" / "dev_artifacts" / "backlog.md"
    suffix = f"(from: workitems/{pd_repo.id})"
    code, out = gate(pd_repo, "finish")
    assert code == 1, out
    backlog.write_text(f"- [ ] 2026-11-26-x — harden {refs[0]} {refs[1]} {refs[2]} {suffix}\n")
    code, out = gate(pd_repo, "finish")
    assert code == 0, out
    backlog.write_text(f"- [ ] 2026-11-26-x — harden {refs[0]} {refs[1]} {suffix}\n")
    code, out = gate(pd_repo, "finish")
    assert code == 1 and refs[2] in out, out


def ruling(minute, verdict, nxt, probe="B43"):
    return entry(minute, "decision", "Q: did it hold?", f'A (user, verbatim): "{verdict} — notes"',
                 f"Ruling: {probe}", f"Next: {nxt}")


def test_c13_probe_rulings(pd_repo):
    set_fm(pd_repo, phase="finish")
    (item(pd_repo) / "shape.md").write_text(
        "# Shape\n\n## Requirements\n\nB43: Probe: run it live -> it holds\nB44: Probe: run it twice -> it holds\n")
    log = item(pd_repo) / "log.md"
    missing = "the owner's ruling on B{n} is missing or names no next step"
    log.write_text("")
    code, out = gate(pd_repo, "finish")
    assert code == 1 and missing.format(n=43) in out and missing.format(n=44) in out
    log.write_text(ruling(1, "Met", "none", "B43") + ruling(2, "Met", "none", "B44"))
    code, out = gate(pd_repo, "finish")
    assert code == 0, out
    log.write_text(ruling(1, "Missed", "none", "B43") + ruling(2, "Met", "none", "B44"))
    code, out = gate(pd_repo, "finish")
    assert code == 1 and missing.format(n=43) in out and missing.format(n=44) not in out
    for nxt in ("phase finish -> design (back)", "backlog 2026-11-26-x"):
        log.write_text(ruling(1, "Missed", nxt, "B43") + ruling(2, "Met", "none", "B44"))
        code, out = gate(pd_repo, "finish")
        assert code == 0, (nxt, out)


@pytest.mark.parametrize("command", [
    [sys.executable, str(SCRIPTS / "pd-lint"), "--self-test"],
    ["bash", str(SCRIPTS / "test-phase-gate.sh")],
    ["bash", str(ROOT / "plugins/pd/hooks/tests/test-pd-stop-gate.sh")],
    ["bash", str(ROOT / "plugins/pd/hooks/tests/test-hooks.sh")],
    ["node", str(ROOT / "plugins/pd/workflows/tests/test-workflows.mjs")],
], ids=["pd-lint", "test-phase-gate", "test-pd-stop-gate", "test-hooks", "test-workflows"])
def test_c14_existing_suites(command):
    r = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
