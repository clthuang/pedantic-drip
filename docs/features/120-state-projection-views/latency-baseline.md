# Session-Start Latency Baseline (feature 120, design D7)

Snapshot artifact — NOT a gate. Captured 2026-07-12 on branch `feature/120-state-projection-views` (HEAD `cf9a542f`, tasks 1-3 committed, tree clean).

## Scope statement

This measures the **empty-HOME fixed session-start overhead, median-only** (the bench isolates `HOME` to a temp dir, so no populated workspace state is read). It is **NOT** PRD NFR-3's populated p50/p95 read-latency baseline — that CAPTURE is assigned to feature 126 and its verification to feature 127, per `docs/projects/P004-entity-db-redesign/roadmap.md:42`. Feature 120's views ship dark (guard-enforced unimported), so both medians below estimate the same quantity on this branch; the value of this artifact is the recorded reference point and the reproduction recipe.

## Results

| Measurement | Median |
|---|---|
| merge-base (`641a57be`, detached worktree) | 227 ms |
| HEAD (tasks 1-3 committed) | 228 ms |
| delta | 1 ms (bench's own threshold: +50 ms) |

## Raw script output (verbatim)

```
Preparing worktree (detached HEAD 641a57be)
baseline median: 227 ms
patched  median: 228 ms
delta:           1 ms (threshold +50)
PASS: NFR2 within budget
```

Bench exit code: 0. Note the script's internal NFR2 gate (delta > 50 ms → exit 1) is not this feature's gate; medians are echoed before that check and are captured regardless of exit code. The script overwrites the tracked `plugins/pd/hooks/tests/bench-results.txt` (do-not-re-commit convention); it was `git restore`d after capturing stdout.

## Machine context

- macOS 26.5.1 (build 25F80)
- `uname -m`: arm64
- CPU: Apple M3 Ultra

## Reproduction

```bash
# from a clean committed tree at the project root (script exits 2 on dirty tree)
bash plugins/pd/hooks/tests/bench-session-start.sh
git restore plugins/pd/hooks/tests/bench-results.txt
```
