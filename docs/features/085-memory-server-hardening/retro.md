# Retro — feature 085-memory-server-hardening (2026-04-19)

## Summary

Bundled 8 QA follow-ups from feature 080 (#00067–#00074) into one coherent PR. 9-step implementation covering 3 security items (entry_name sanitization, log permission bits, log rotation), 3 code-quality items (shared `config_utils.py` extraction, drop redundant `recorded` field, eliminate double threshold resolution), and 2 testability items (regex-aware test stubs, validate.sh docs-sync guards). 135 new/migrated tests; all green. validate.sh green. Delivered across 8 commits on `feature/085-memory-server-hardening`.

## AORTA Analysis

### Agreements (what worked)
- **Phase-gate reviewer discipline caught real issues at every stage.** Spec: 3 iterations catching self-attestation, wrong patch target, sre_parse deprecation. Design: 3 iterations catching str→tuple shape mismatch, silent clamp change, int→list schema flip, nonexistent classifier function, duplicate test-file paths. Plan: 3 iterations catching TDD ordering violations, broken-suite intermediate states, stub-guard ambiguity.
- **Archetype override from default `exploring-an-idea` to `improving-existing-work`** was appropriate for maintenance scope and shifted advisory emphasis productively (pre-mortem + feasibility instead of vision-horizon + opportunity-cost).
- **Atomic Task 2.3 merge** (tuple-return + wrapper unpack + test-site unpack) prevented broken-suite intermediate state. Iter-2 plan-reviewer caught this before implementation.
- **Single-implementer batch dispatch** (one agent executing all 9 steps sequentially rather than per-task parallel worktree dispatch) was pragmatic for a session already deep in review cycles. Implementer's self-review documented 3 cosmetic deviations without blockers.

### Observations (facts from data)
- **Spec-review found 4 blockers in iter 1**, 3 in iter 2, 0 in iter 3 — monotonically decreasing, suggesting review cycles converge with adequate budget. Same pattern in design (2→3→0) and plan (6→3→0).
- **Self-attestation anti-pattern recurred across all 3 phases.** Spec AC-E1 cited `_sanitize_description` without verification. Design claimed `classify_entries` function existence. Plan claimed independent commit revertability. Each caught by the next review layer, not by the original author.
- **File-path drift between artifacts** caused rework: spec said `hooks/tests/fixtures/` for snapshots; design initially picked `hooks/lib/semantic_memory/fixtures/`; plan.md said `_capture.py`; tasks.md said `generate_feature_085_snapshots.py`. All eventually reconciled to spec's location.
- **Codebase-explorer Stage 2 research was critical** — discovered the 8 backlog items had WRONG file paths (claimed `hooks/lib/semantic_memory/memory_server.py`; actually `mcp/memory_server.py`). Without the Stage 2 correction, the entire feature would have targeted non-existent files.

### Reservations (concerns for next time)
- **6 memory learnings captured** (patch-target-bound-import, sre_parse deprecation, shared-helper test enumeration, verify function signatures, clamp invariants, inline-test convention). Two of these (return-shape verification, clamp invariants) are generalizations of refactor anti-patterns that may recur.
- **Plan-reviewer didn't have tasks.md in its first context** — only plan.md. Missed task-level TDD ordering that was already in tasks.md. The 3-reviewer combined loop is structured correctly (plan-reviewer → task-reviewer → phase-reviewer) but the plan-reviewer's feedback on TDD was predicated on missing context.
- **SC-9(a) literal grep is cosmetically broken** (returns 0 instead of 1 because the call spans multiple lines post-migration). SC-9(b) runtime spy is authoritative. Cosmetic SC metric didn't align with multiline code reality — consider stripping newlines in future grep-based SCs.

### Tunes (actionable adjustments)
- **High confidence**: Add `grep -P -z` or pre-flatten multiline matches to future source-grep SCs that assert function call counts. Single-line `wc -l` grep is fragile against multiline Python calls.
- **Medium confidence**: When a plan change introduces a new function-signature change affecting N callers, plan-reviewer should receive the caller enumeration alongside plan.md. Consider adding a "migration scope" field to plan sections that changes signatures.
- **Medium confidence**: The archetype selection default (`exploring-an-idea` when ARCHETYPE not specified in args) underserves maintenance/refactor features. Consider making `brainstorming` skill infer archetype from keyword signals when none is provided by the caller.

### Actions (concrete follow-ups)
- No net-new follow-ups triggered by this feature's retro (the 6 memory learnings are the main artifact).
- Backlog items #00067–#00074 annotated with `(fixed in feature:085-memory-server-hardening)`.

## Metrics

| Phase | Iterations | Real blockers found |
|-------|-----------|---------------------|
| Brainstorm (prd-reviewer + brainstorm-reviewer) | 1 + 1 (warn → PASS) | 0 blockers / several warnings addressed |
| Specify (spec-reviewer + phase-reviewer) | 3 + 1 | 10 blockers (4 iter1, 3 iter2, 3 iter3→0), 2 suggestions applied |
| Design (design-reviewer + phase-reviewer) | 3 + 1 | 5 blockers (2+3), 1 warning |
| Create-plan (plan-reviewer + task-reviewer + phase-reviewer) | 3+1+1 combined iter | 9 blockers (6+3), 6 task-reviewer suggestions |
| Implement | 1 (single-agent batch) | 0 blockers, 3 documented deviations |

**Total review iterations:** 15 across all phases. **Total blockers caught pre-implementation:** 24.

## Commits (feature branch)

Core feature (8):
- 5d6c75c snapshot baseline
- 34b8a71 config_utils extraction
- a24dafe FR-5+6+2 batched memory_server
- cb0efd2 FR-3 rotation
- 6e0823b FR-1 + FR-7 generators
- 360bd45 FR-8 validate.sh guards
- 661ee39 backlog annotations
- 35f05e6 plugin.json bump

Plus review iteration commits for the PRD/spec/design/plan artifacts.
