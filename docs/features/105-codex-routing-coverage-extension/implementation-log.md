# Implementation Log — Feature 105

All 12 tasks executed via direct-orchestrator pattern (no per-task implementer dispatch). Heavy upstream review (specify 3 iters + design 4 iters + create-plan 3 iters) produced binary-checkable DoDs that enabled single-pass implementation.

## T1: Capture pre-change baselines — PASS

- `/tmp/pd-105-sec-baseline.txt`: 3 lines (3 existing pd:security-reviewer dispatch sites preserved).
- `/tmp/pd-105-codex-baseline.txt`: matches expected 6 existing files exactly.

## T2-T6: 5 preamble insertions — PASS

All 5 verifications passed via the AC-1.x extract_codex_section snippets:
- AC-1.1 secretary.md → PASS (including R-8 dynamic-dispatch note)
- AC-1.2 taskify.md → PASS
- AC-1.3 review-ds-code.md → PASS
- AC-1.4 review-ds-analysis.md → PASS
- AC-1.5 decomposing/SKILL.md → PASS

## T7: validate.sh FR-2a (log_warning → log_error + counter increment) — PASS

- log_warning gone, log_error in place with adjacent counter increment.

## T8: validate.sh FR-2b (allowlist+count assertion) — PASS

- Block inserted with cwd assertion + 11-file expected list + sorted-diff + log_error on mismatch.
- "Codex routing coverage drift" string appears exactly once.

## T9: Full validation — PASS

- `./validate.sh` exits 0; `Codex routing coverage allowlist validated (11 expected files)` logged.
- AC-3.1 baseline diff: empty (no pd:security-reviewer dispatch sites added or removed).
- AC-3.2 (with reference doc excluded per validate.sh:861 pattern): no routing matches.
- AC-4.1: no agents/ files modified.
- AC-4.2: no diff against the existing 6 preamble files (validate.sh excluded as authorized FR-2a touch).

## T10: AC-2.2 FR-2a regression guard — PASS

Procedure (temp clone, removed exclusion clause from secretary.md, ran validate.sh):
- validate.sh exit code: 1 (non-zero, expected)
- ERROR: "plugins/pd/commands/secretary.md: references codex-routing.md but lacks 'no security review at this phase' indicator"

Evidence file: `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.2.txt` (gitignored; local-only — see Implementation Note below).

## T11: AC-2.3 FR-2b allowlist drift (both directions) — PASS

Direction (a) drift +1 (added 12th file): validate.sh exit 1; "Codex routing coverage drift" logged.
Direction (b) drift -1 path substitution (rename taskify.md → taskify.md.disabled): validate.sh exit 1; sanity check confirms grep discovery picks up the renamed path; diff output shows `< taskify.md` and `> taskify.md.disabled`.

Evidence file: `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-2.3.txt` (gitignored; local-only).

## T12: AC-3.1 dispatch baseline preservation — PASS

Empty diff against baseline. Evidence file: `agent_sandbox/2026-05-06/feature-105-evidence/T-EXEC-AC-3.1.txt` (gitignored; local-only).

## Implementation Note

The design's commit-stance instruction in I-5 ("Evidence files ARE committed") was based on an incorrect assumption — `agent_sandbox/` is gitignored at the repo root. Per project precedent (feature 102's `.qa-gate-low-findings.md` is also gitignored), evidence files stay local and this implementation-log.md documents the procedure outcomes. This is a minor design-vs-reality inconsistency; the validation gates still passed correctly. To be tracked in retro for future feature reference.
