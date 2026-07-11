# Populated-State Read-Latency Baseline (feature 126, PRD NFR-3)

Captured 2026-07-12 on branch `feature/126-lossless-meta-json-projection` (tasks 1-3 committed at `86410074`, tree clean). This is the baseline PRD NFR-3 names; **feature 127 verifies DB-direct reads against it** (converting OQ-1 keep-vs-drop `.meta.json` into pass/fail).

## What was measured (component 5a)

The session-start hook's two per-session state reads, each extracted BETWEEN THE SENTINELS in `plugins/pd/hooks/session-start.sh` at run time (drift-proof; the bench self-guards with exit 3 if extraction fails):

- **walk** — `find_active_feature`'s python snippet (`BENCH-WALK-START/END`): `os.walk` over the features tree, `json.load` every `.meta.json`.
- **glob** — the projects workspace-lookup snippet (`BENCH-GLOB-START/END`), measured in the NO-MATCH full-scan posture (`feature_workspace_uuid` set to a non-matching sentinel so the first-match `break` never fires — worst case, matching the walk's always-full-scan behavior).

Each component runs as its own process (python startup ~28 ms is included in every sample — it is part of the real hook cost). Doctor and reconcile are excluded (their DB reads are not the path 127 replaces). Seeded tree: one `.meta.json` per feature dir, realistic payload sizes, `random.Random(0x126)`.

## Scaling parameter (RECORDED — 127 must reuse)

- **Recorded live feature-`.meta.json` count: N = 22** (`find docs/features -name .meta.json | wc -l` at capture time; the parse-cost driver — the repo has ~137 feature dirs but `.meta.json` is gitignored and mostly absent).
- Stress scale: 10× = 220.
- **127 MUST re-run this harness with `--features 22` (and 220), seed 0x126 — never re-derive N** (the repo will have grown).

## Results (N_ITERATIONS = 120 per component per scale)

| component | scale | p50 | p95 |
|---|---|---|---|
| walk | N=22 | 29 ms | 31 ms |
| glob (no-match) | N=22 | 29 ms | 32 ms |
| walk | N=220 | 40 ms | 42 ms |
| glob (no-match) | N=220 | 36 ms | 38 ms |

Full sorted distributions (verbatim bench output):

```
bench-populated-read.sh: seed=0x126 features_n=22 iterations=120 smoke=0
=== walk (find_active_feature) @ N=22 (n=120 iterations) ===
p50: 29 ms
p95: 31 ms
distribution (sorted ms): 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 30 30 30 30 31 31 31 31 31 31 31 31 32 32
=== glob (build_context workspace lookup, NO-MATCH) @ N=22 (n=120 iterations) ===
p50: 29 ms
p95: 32 ms
distribution (sorted ms): 28 28 28 28 28 28 28 28 28 28 28 28 28 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 29 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 30 31 31 31 31 31 31 31 31 31 32 32 32 32 32 32 33 35 36
=== walk (find_active_feature) @ N=220 (n=120 iterations) ===
p50: 40 ms
p95: 42 ms
distribution (sorted ms): 38 38 38 38 38 38 38 38 38 38 38 38 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 39 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 40 41 41 41 41 41 41 41 41 41 41 41 41 41 41 41 41 41 42 42 42 42 42 42 42 43 43 43 44 47
=== glob (build_context workspace lookup, NO-MATCH) @ N=220 (n=120 iterations) ===
p50: 36 ms
p95: 38 ms
distribution (sorted ms): 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 35 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 36 37 37 37 37 37 37 37 37 37 37 38 38 38 38 38 38 38 38 38 39 39 39 40
PASS: bench-populated-read.sh completed
```

Reading: python interpreter startup (~28 ms) dominates both components at live scale; the marginal parse cost is ~11 ms per 200 additional `.meta.json` (walk: 29→40 ms p50 across 22→220). Any DB-direct replacement that avoids one python spawn, or amortizes into an existing one, has ~28 ms of headroom before parse costs even enter.

## Component 5b — census DB substrate (seeded, NOT measured here)

`scripts/seed-census-db.py` full-scale run (into a scratch dir, then discarded): **533 entities, 5,644 events, 7 workspaces in 0.113 s wall-clock**. Deterministic at seed 0x126 with sequential type_ids — 127 re-runs the same script at the same seed to build the substrate its DB-direct reads are measured against, then compares to the 5a numbers above (harness-to-harness; never against ad-hoc measurements).

## Machine context

- macOS 26.5.1 (build 25F80); `uname -m`: arm64; CPU: Apple M3 Ultra

## Reproduction

```bash
# from the project root, clean committed tree
bash plugins/pd/hooks/tests/bench-populated-read.sh --features 22   # recorded N — do not re-derive
plugins/pd/.venv/bin/python scripts/seed-census-db.py --target "$(mktemp -d)"
```

Residual: synthetic payload sizes approximate the real distribution; real-world `.meta.json` payloads vary (reviewerNotes strings especially). The comparison discipline (same harness, same seeds, same N) keeps this residual common to both sides of 127's comparison.
