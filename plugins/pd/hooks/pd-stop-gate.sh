#!/usr/bin/env bash
# Stop hook: the script gate under /goal (plan §A5, cap 3; ported from yolo-stop.sh).
# On every stop it charges the session's new token usage to the checked-out feature. It blocks
# (exit 2, the reason on stderr) only while a feature's `## Now` has a `goal: <id> target <phase>
# session <this session>` line and the goal isn't met: target not reached, open blockers, or a
# pd-lint failure. It yields to running background workflows and subagents, and at the token cap
# or on a stuck loop it tells the conductor to ask the user, so nothing repeats a dead block.
# State: ~/.claude/pd/gate/<session id>.json (the progress snapshot; other keys, such as
# calvin_ledger, are kept) and ~/.claude/pd/gate/<repo key>/<feature id>.json (the running
# token total and the original budget).
set -uo pipefail
trap '' PIPE
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

read -r -d '' GATE_PY <<'PY' || true
import fcntl, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
scripts = Path(sys.argv[1]).parent / "scripts"
sys.path.insert(0, str(scripts))
import pd_common as pc

GOAL_RE = re.compile(r"^goal: (\S+) target (\S+) session (\S+)$")
RUN_RE = re.compile(r"^run in flight: (\S+) session (\S+)")
BUDGET_RE = re.compile(r"^Budget: feature_token_budget=(\d+)$")
inp = json.loads(sys.stdin.read() or "{}")
sid, gate = str(inp.get("session_id") or ""), Path.home() / ".claude" / "pd" / "gate"
root = pc.git(["rev-parse", "--show-toplevel"], inp.get("cwd") or ".", check=False)
if not root or not re.fullmatch(r"[\w.-]+", sid):
    sys.exit(0)
root = Path(root)


def load(p):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=p.name + ".")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(data, indent=1))
    os.replace(tmp, p)


def usage(transcript):
    """input + output + cache-creation tokens from each entry's message.usage (cache reads excluded),
    over the main transcript and every agent transcript under <session>/subagents/."""
    if not transcript:
        return 0
    main = Path(transcript)
    sub = main.with_suffix("") / "subagents"
    total = 0
    for f in [main] + (sorted(sub.rglob("agent-*.jsonl")) if sub.is_dir() else []):
        try:
            lines = f.read_text(errors="replace").split("\n")
        except OSError:
            continue
        for line in lines:
            try:
                u = json.loads(line)["message"]["usage"]
                total += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return total


def number(value):
    return int(value) if str(value).strip().isdigit() else None


cfg = pc.load_config(root)
features = []
for type_, fid, ctl in pc.find_items(pc.artifacts_dir(root, cfg)):
    try:
        fm, body, _ = pc.split_frontmatter(ctl.read_text()) if type_ == "feature" else (None, "", 0)
    except (OSError, ValueError):
        continue
    if type_ == "feature":
        now = [l.strip() for l in pc.blank_fences(pc.sections(body).get("Now", "")).split("\n") if l.strip()]
        features.append({"id": fid, "fm": fm or {}, "readme": ctl, "now": now})
origin = pc.git(["remote", "get-url", "origin"], root, check=False)
repo_key = hashlib.sha256((origin or str(root.resolve())).encode()).hexdigest()[:16]
state = lambda f: gate / repo_key / f"{f['id']}.json"

# 1. Count, on every stop: the usage since the previous count goes to the checked-out feature.
sess_path = gate / f"{sid}.json"
sess = load(sess_path)
total, counted = usage(inp.get("transcript_path")), int(sess.get("counted") or 0)
delta = total - counted if total > counted else 0
sess["counted"] = max(total, counted)
branch = pc.git(["rev-parse", "--abbrev-ref", "HEAD"], root, check=False) or ""
here = next((f for f in features if branch in (f["fm"].get("branch"), f"feature/{f['id']}")), None)
if here and delta:
    p = state(here)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_name(p.name + ".lock"), "w") as lock:  # sessions on one feature charge it in turn
        fcntl.flock(lock, fcntl.LOCK_EX)
        fs = load(p)
        fs["tokens"] = int(fs.get("tokens") or 0) + delta
        fs.setdefault("budget", number(cfg.get("feature_token_budget")))  # the original budget
        save(p, fs)


def finish(code, reason=None):
    save(sess_path, sess)
    if reason:
        print(reason, file=sys.stderr)
    sys.exit(code)


# 2. Only this session's goal line arms the gate.
goal = next(((f, m) for f in features for l in f["now"] for m in [GOAL_RE.match(l)] if m and m.group(3) == sid), None)
if not goal:
    finish(0)
f, m = goal
fid, target = f["id"], m.group(2)

# 3. Yield to background work that will wake the session; a shell or monitor doesn't count.
tasks = inp.get("background_tasks")
if isinstance(tasks, list):
    # Observed 2026-10-18 (bake-off): entries are {type: workflow|subagent|shell, status: running}; a finished task leaves the list.
    busy = any(isinstance(t, dict) and t.get("type") in ("workflow", "subagent")
               and t.get("status") == "running" for t in tasks)
else:
    busy = any(r and r.group(2) == sid for r in map(RUN_RE.match, f["now"]))
if busy:
    finish(0)

# 4. The token cap: the latest decision entry's `Budget: feature_token_budget=<n>` raise, else the config.
entries = pc.parse_log(*pc.log_text("feature", f["readme"]))
raises = [int(b.group(1)) for e in entries if e["kind"] == "decision"
          for b in map(BUDGET_RE.match, (l.strip() for l in e["body"])) if b]
budget = raises[-1] if raises else number(cfg.get("feature_token_budget"))
tokens = int(load(state(f)).get("tokens") or 0)
increment = number(cfg.get("budget_increment")) or number(cfg.get("feature_token_budget")) or budget
if budget is not None and tokens >= budget:
    finish(2, f"pd gate: feature {fid} has used {tokens} tokens of its feature_token_budget {budget}. Ask the user "
              "through AskUserQuestion: \"budget spent: continue or stop?\". On continue, write a decision entry with "
              f"`Budget: feature_token_budget={budget + increment}`; on stop, clear "
              "the goal: line from ## Now and commit.")

# 5. Stuck: blocked last time and nothing moved (a commit on the feature branch, log.md or the README).
ref = f["fm"].get("branch") or f"feature/{fid}"
head = pc.git(["rev-parse", "-q", "--verify", ref], root, check=False) or pc.git(["rev-parse", "HEAD"], root, check=False)
log = f["readme"].parent / "log.md"
snap = "|".join([head or ""] + [hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "" for p in (log, f["readme"])])
moved, sess["last_check"] = sess.get("last_check") != snap, snap
if inp.get("stop_hook_active") and not moved:
    finish(2, f"pd gate: no progress on {fid} since the last check. Ask the user through AskUserQuestion: "
              "\"no progress since the last check: continue or stop?\". On stop, clear the goal: line from ## Now and commit.")

# 6. The goal's conditions: open blockers, pd-lint on the feature's files, the target phase.
reasons = [f"open blocker {b['ref']} {b['file']}:{b['line']} — {b['claim']}" for b in pc.open_blockers(entries)]
lint = subprocess.run([str(scripts / "pd-lint"), str(f["readme"].parent)], cwd=root, capture_output=True, text=True)
if lint.returncode == 1:
    reasons += ["pd-lint fails:"] + [l for l in lint.stdout.splitlines() if " ERROR " in l][:10]
status, phase = f["fm"].get("status"), f["fm"].get("phase")
if target == "finish":
    reached = status == "done"
else:
    reached = phase in pc.PHASES and target in pc.PHASES and pc.PHASES.index(phase) > pc.PHASES.index(target) and \
        subprocess.run(["bash", str(scripts / "phase-gate.sh"), target, str(f["readme"].parent)], capture_output=True).returncode == 0
if not reached:
    reasons.append(f"target {target} not reached (status {status}, phase {phase}): keep working toward it")
if reasons:
    finish(2, f"pd gate: the goal on {fid} is not met.\n" + "\n".join(reasons))
finish(2, f"pd gate: {fid} reached {target} with no open blockers: clear the goal: line from ## Now, commit, then stop.")
PY

python3 -c "$GATE_PY" "$HERE"
code=$?
[ "$code" -eq 0 ] || [ "$code" -eq 2 ] && exit "$code"
echo "pd-stop-gate: the gate failed to run (exit $code); the stop goes through" >&2
exit 1
