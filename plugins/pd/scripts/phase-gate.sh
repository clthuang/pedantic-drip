#!/usr/bin/env bash
# phase-gate.sh — a phase's exit check: what the phase must hand down (plan Part B §5, §9;
# §A2 rows 2–7). Zero dispatch: artifacts, sections, the design's diagram and test strategy,
# duplicate contract blocks (#074 restatement class), and the log.md entries the phase owes
# (plugins/pd/references/log-entries.md). The skill runs it before moving `phase:` past a
# phase; pd-lint re-runs it at commit time, with changes staged, for every earlier phase.
#
# Usage: phase-gate.sh <phase> <workitem-dir> [--express]
#   phase ∈ specify|design|create-plan|implement|verify|finish|express
#   express: the mini-spec check (one task block in shape.md ## Requirements), which
#   replaces specify, design and create-plan for a `mode: express` work item. implement on
#   an express work item (the flag, or `mode: express` in README.md) takes its one task
#   from that block instead of plan.md.
# Exit 0 = gate passes; 1 prints each failure on its own line; 2 = usage.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PHASE="${1:-}"
DIR="${2:-}"
EXPRESS=0
[ "${3:-}" = "--express" ] && EXPRESS=1
FAIL=0
say() { echo "GATE FAIL [$PHASE]: $1"; FAIL=1; }

[ -n "$PHASE" ] && [ -n "$DIR" ] || { echo "usage: phase-gate.sh <phase> <workitem-dir> [--express]"; exit 2; }
[ -d "$DIR" ] || { say "work item dir missing: $DIR"; exit 1; }
grep -qE '^mode:[[:space:]]*["'"'"']?express["'"'"']?([[:space:]]|$)' "$DIR/README.md" 2>/dev/null && EXPRESS=1

need_file() { [ -f "$DIR/$1" ] || say "missing artifact: $1"; }
need_section() { [ -f "$DIR/$1" ] && grep -q "^## $2" "$DIR/$1" || say "$1 missing section: ## $2"; }
# A `### <name>` subsection inside shape.md's ## Design.
need_design_sub() {
  [ -f "$DIR/shape.md" ] && awk -v want="### $1" '/^## /{d=($0 ~ /^## Design/)} d && index($0, want) == 1 {f=1} END{exit !f}' "$DIR/shape.md" ||
    say "shape.md ## Design missing ### $1"
}

# Duplicate fenced code blocks across the artifact set = restated contract (#074).
# Blocks under 3 lines are ignored (single-line snippets legitimately repeat).
dupe_contract_blocks() {
  # Pure awk (BSD-portable: macOS uniq lacks -z). Prints DUPE on first repeat.
  find "$DIR" -maxdepth 1 -name '*.md' -print0 | xargs -0 cat 2>/dev/null |
    awk '
      /^```/ {
        if (inblk) { if (n > 3 && ++seen[blk] == 2) { print "DUPE"; exit } inblk = 0 }
        else { inblk = 1; blk = ""; n = 0 }
        next
      }
      inblk { blk = blk "\n" $0; n++ }
    '
}

# The checks that read log.md, the expectations and the task blocks (pd_common.py parses them).
log_checks() {
  python3 - "$HERE" "$PHASE" "$DIR" "$EXPRESS" <<'PY'
import re, subprocess, sys
from pathlib import Path
here, phase, d, express = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4] == "1"
sys.path.insert(0, here)
import pd_common as pc

def read(name):
    p = d / name
    return p.read_text() if p.is_file() else ""

entries = pc.parse_log(read("log.md"))
reqs = pc.sections(read("shape.md")).get("Requirements", "")
fail = lambda msg: print(msg)

def expectations():
    ids = []
    for line in pc.blank_fences(reqs).split("\n"):
        if re.match(r"^B\d+\b", line):
            m = pc.EXPECTATION_RE.match(line)
            if m:
                ids.append(m.group(1))
            else:
                fail(f"expectation not `B<n>: <input or action> -> <observable outcome>`: {line.strip()}")
    if not ids:
        fail("shape.md ## Requirements has no expectation (B1: <input or action> -> <observable outcome>)")
    dups = sorted({i for i in ids if ids.count(i) > 1}, key=int)
    if dups:
        fail("duplicate expectation ids: " + ", ".join("B" + i for i in dups))

def session_of(e):
    return next((l[len("Session:"):].strip() for l in e["body"] if l.startswith("Session:")), None)

def signed_off():
    confirmed = set()  # sessions that turned YOLO on, in the log's order: a sign-off before its confirmation doesn't count
    for e in entries:
        if e["kind"] != "decision":
            continue
        answered_by_user = any(l.startswith("A (user, verbatim):") for l in e["body"])
        if answered_by_user and any(l.strip().lower() == "q: hard stop: turn yolo on for this session?" for l in e["body"]):
            confirmed.add(session_of(e))
        if any(l.strip().lower() == "q: criteria signed off?" for l in e["body"]) and (
                answered_by_user or (any(l.startswith("A (conductor, on the user's behalf):") for l in e["body"])
                                     and session_of(e) in confirmed)):
            return
    fail("log.md has no sign-off: a decision entry with `Q: criteria signed off?` and `A (user, verbatim): …`")

def mini_spec():
    tasks = pc.parse_tasks(reqs)
    if len(tasks) != 1:
        fail(f"express mini-spec: shape.md ## Requirements needs one task block, found {len(tasks)}")
        return tasks
    fields = tasks[0]["fields"]
    for key in ("files", "uses", "command", "junit"):
        if not fields.get(key):
            fail(f"express mini-spec task has no `- {key}:`")
    if not tasks[0]["cases"]:
        fail("express mini-spec task has no test cases")
    expectations()
    return tasks

def tasks_merged(tasks):
    merged = {int(m.group(1)) for e in entries if e["kind"] == "run"
              for l in e["body"] for m in [pc.RUN_TASK_RE.match(l)] if m}
    if not tasks:
        fail("no tasks found (#### Task <n>: …)")
    missing = [str(t["n"]) for t in tasks if t["n"] not in merged]
    if missing:
        fail("no run entry records these tasks merged with their proof passing: " + ", ".join(missing))

def item_fm():
    return pc.split_frontmatter(read("README.md"))[0] or {}

def stage_matches_review():
    """The latest review entry with a `Stage:` line decides; entries without one are skipped. Only the exit being taken
    checks it (pd-lint's re-runs of passed gates skip it), so a stage change after Contracts commits."""
    fm = item_fm()
    if fm.get("phase") != phase:
        return
    applied = [l[len("Stage:"):].strip() for e in entries if e["kind"] == "review" for l in e["body"] if l.startswith("Stage:")]
    if applied and applied[-1] != pc.item_stage(fm):
        fail(f"the review applied stage {applied[-1]}; the work item is {pc.item_stage(fm)}")

def risk_declared():
    root = pc.repo_root(d)
    cfg = pc.load_config(root)
    base = pc.git(["merge-base", pc.base_branch(root, cfg), "HEAD"], root, check=False)
    if not base:
        return
    declared = set(pc.as_list(item_fm().get("risk"))) | pc.risk_waivers(entries)
    for tag, path, line in pc.risk_signals(root, f"{base}..HEAD"):
        if tag not in declared:
            fail(f"{tag} signal {path}:{line}: add risk: {tag} or a Risk: none ({tag}) decision")

def harden_later_on_backlog():
    if pc.item_stage(item_fm()) != "mvp":
        return
    refs = [f"{e['ref']}#{m['id']}" for e in entries if e["kind"] == "review" for l in e["body"]
            for m in [pc.ISSUE_RE.match(l)] if m and m["cat"]]
    if not refs:
        return
    root = pc.repo_root(d)
    backlog = pc.artifacts_dir(root, pc.load_config(root)) / "backlog.md"
    ending = f"(from: workitems/{d.name})"
    lines = [l for l in (backlog.read_text().split("\n") if backlog.is_file() else []) if l.rstrip().endswith(ending)]
    named = lambda line, ref: re.search(re.escape(ref) + r"(?!\w)", line)
    best = max(lines, key=lambda l: sum(bool(named(l, r)) for r in refs), default="")
    missing = [r for r in refs if not named(best, r)]
    if missing:
        fail(f"harden-later issues missing from the one backlog.md line ending {ending}: " + ", ".join(missing))

def probe_rulings():
    for n in re.findall(r"^B(\d+): Probe:", pc.blank_fences(reqs), re.M):
        for e in entries:
            body = e["body"]
            if e["kind"] != "decision" or f"Ruling: B{n}" not in body:
                continue
            verdict = next((m.group(1) for l in body for m in [re.match(r'^A \(user, verbatim\): "(Met|Missed)\b', l)] if m), None)
            nxt = next((l[len("Next:"):].strip() for l in body if l.startswith("Next:")), "")
            if verdict == "Met" and nxt or verdict == "Missed" and re.match(r"(phase \S+ -> \S+ \(back\)|backlog \S+)$", nxt):
                break
        else:
            fail(f"the owner's ruling on B{n} is missing or names no next step")

def verify():
    root = pc.repo_root(d)
    cfg = pc.load_config(root)
    battery = pc.as_list(cfg.get("qa_battery"))
    if not battery:
        fail("set qa_battery in .claude/pd.local.md")
    qas = [e for e in entries if e["kind"] == "qa"]
    if not qas:
        fail("log.md has no qa entry")
    elif battery:
        last = qas[-1]
        ran = dict(re.findall(r"^Ran: `(.+)` -> (pass|fail)\s*$", "\n".join(last["body"]), re.M))
        for cmd in battery:
            if ran.get(cmd) != "pass":
                fail(f"the latest qa entry ({last['ref']}) has no passing `Ran:` line for `{cmd}`")
        commit = next((m.group(1) for l in last["body"] for m in [re.search(r"\bCommit: ([0-9a-f]{7,40})\b", l)] if m), None)
        if not commit:
            fail(f"the latest qa entry ({last['ref']}) has no `Commit: <hash>`")
        elif pc.git(["cat-file", "-e", commit + "^{commit}"], root, check=False) is None:
            fail(f"qa commit {commit} is not in this repository")
        else:
            paths = [pc.dir_prefix(p) for k in ("source_paths", "test_paths", "fixture_paths") for p in pc.as_list(cfg.get(k))]
            paths = paths or [p for p in ("src/", "tests/") if (root / p).is_dir()]
            art = pc.dir_prefix(cfg.get("artifacts_root"))
            # The index, the working tree and untracked files: whatever differs from the QA'd commit.
            changed = "\n".join(pc.git(a, root) or "" for a in (["diff", "--cached", "--name-only", commit, "--"],
                                                                ["diff", "--name-only", commit, "--"],
                                                                ["ls-files", "--others", "--exclude-standard"])).split("\n")
            code = [p for p in changed if p and (any(p.startswith(x) for x in paths) if paths else not p.startswith(art))]
            if code:
                fail(f"source, test or fixture files changed since the qa commit {commit}; run QA again: " + ", ".join(code[:5]))
    for b in pc.open_blockers(entries):
        fail(f"open blocker {b['ref']} {b['file']}:{b['line']} — {b['claim']}")
    risk_declared()

if phase in ("design", "create-plan", "verify", "finish"):
    stage_matches_review()

if phase == "specify":
    expectations()
    signed_off()
elif phase == "express":
    mini_spec()
elif phase == "implement":
    tasks_merged(mini_spec() if express else pc.parse_tasks(read("plan.md")))
elif phase == "verify":
    verify()
elif phase == "finish":
    probe_rulings()
    harden_later_on_backlog()
    triggers = pc.retro_triggers(entries)
    if triggers and not (d / "retro.md").is_file():
        fail("retro.md missing: log.md records a retro trigger (" + ", ".join(triggers) + ")")
print("LOG_CHECKS_DONE")
PY
}

case "$PHASE" in
  specify)
    need_file shape.md
    need_section shape.md Requirements
    ;;
  design)
    need_file shape.md
    need_section shape.md Requirements
    need_section shape.md Design
    # The design draws its architecture: a mermaid block inside ## Design.
    [ -f "$DIR/shape.md" ] && ! awk '/^## /{d=($0 ~ /^## Design/)} d && /^```mermaid/{f=1} END{exit !f}' "$DIR/shape.md" &&
      say "shape.md ## Design missing its architecture diagram (a \`\`\`mermaid block)"
    need_design_sub "Test strategy"
    [ -n "$(dupe_contract_blocks)" ] && say "duplicate contract block in artifact set (pin each contract once)"
    ;;
  create-plan)
    need_file shape.md
    need_file plan.md
    need_section plan.md Plan
    [ -n "$(dupe_contract_blocks)" ] && say "duplicate contract block in artifact set (pin each contract once)"
    ;;
  express)
    need_file shape.md
    ;;
  implement)
    need_file shape.md
    [ "$EXPRESS" -eq 1 ] || need_file plan.md
    ;;
  verify|finish) ;;
  *)
    echo "usage: phase-gate.sh <phase> <workitem-dir> [--express] (unknown phase: $PHASE)"; exit 2
    ;;
esac

case "$PHASE" in
  specify|design|create-plan|express|implement|verify|finish)
    # A checker that crashes, or never ran, fails the gate: only its closing line proves it finished.
    out=$(log_checks); rc=$?
    while IFS= read -r line; do [ -n "$line" ] && [ "$line" != LOG_CHECKS_DONE ] && say "$line"; done <<< "$out"
    [ "$rc" -eq 0 ] && [ "${out##*$'\n'}" = LOG_CHECKS_DONE ] || say "the log.md checks did not complete (exit $rc)"
    ;;
esac

if [ "$FAIL" -ne 0 ]; then exit 1; fi
echo "GATE PASS [$PHASE] $DIR"
