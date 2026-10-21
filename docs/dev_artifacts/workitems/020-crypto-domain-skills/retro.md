# Retrospective: Crypto Domain Skill (020-crypto-domain-skills)

## What Went Well

- **Spec-phase scope correction was the highest-value review action.** The spec reviewer's line budget analysis (484/500) caught that hardcoding a second domain was infeasible, forcing a beneficial refactor to generic dispatch. This prevented a Phase 3 dead end.
- **Generic dispatch refactor delivered net -20 lines** (485 to 465), creating 35 lines headroom. Future domains cost ~1 line each instead of ~40+.
- **Spec iteration count improved** from 5 (feature 019) to 3 (feature 020) while still catching 2 blockers early — front-loading pattern from 019's retro applied successfully.
- **Domain skill self-containment pattern worked well.** Each domain SKILL.md owns its Stage 2 Research Context, co-locating domain knowledge with domain implementation.
- **Source-of-truth hierarchy** explicitly declared in plan for 3 spec-vs-design discrepancies — new practice that prevented implementer confusion.
- **Cross-file consistency review** caught section ordering, orphaned files, and stale references that spec/design reviews could not detect.
- **All 14 verification checklist items passed cleanly** — checklist-as-final-gate validated for second consecutive feature.
- **Tasks passed in 1 iteration** — well-structured plan translated to unambiguous task definitions.

## What Could Improve

- **Off-by-one line count propagation recurred** (484 vs 485) despite being flagged as anti-pattern in 019 retro. "Single authoritative count" mitigation was not enforced.
- **Plan took 3 iterations** instead of expected 1 — generic dispatch refactor introduced planning complexity absent from greenfield features.
- **Two false-positive review events wasted cycles:** PRD reviewer flagged 3 existing sections; plan reviewer confused plan artifacts with implementation.
- **Review history at 367 lines** (up from 019's 353) — no summarization practice adopted despite being flagged.
- **Cross-skill Read mechanism still untested at runtime** for third consecutive feature. 019 retro suggested smoke test after third occurrence — still not done.
- **16 review events** is substantial overhead for a feature that is primarily content creation plus a mechanical refactor.

## Learnings Captured

### Patterns

1. **Generic-Before-Add:** When adding a second instance of a pattern, refactor to generic dispatch before adding rather than duplicating hardcoded blocks. Proactively choose this at 2 instances, not 3+.
2. **Source-of-Truth Declaration:** When plan references both spec and design for the same topic and they differ, explicitly declare which document wins.
3. **Domain Skill Self-Containment:** Each domain SKILL.md owns its Stage 2 Research Context, review criteria output, and output template. The orchestrator just dispatches generically.
4. **Cross-File Consistency Review:** Implementation quality reviews that examine multiple files together catch issues invisible to single-file analysis.
5. **Behavioral Constraint Cascade:** Financial advice prohibition defined in PRD, reinforced in spec, verified in design, enforced at reference file level. Each stage checks independently.

### Anti-Patterns

1. **Stale Line Count Propagation (recurrence):** Carrying forward line counts without re-verification. Occurred in 019 and 020. Needs enforcement mechanism, not just awareness.
2. **False-Positive Review Category Errors:** Reviewers flagging plan artifacts as implementation, or flagging present content as missing. Root cause: not calibrating to artifact type.
3. **Unbounded Review History Growth:** 367 lines of review history for ~1100 lines of deliverables. No summarization practice.
4. **Premature Out-of-Scope Classification:** PRD declared generic dispatch as out-of-scope without checking line budget feasibility. Feasibility analysis should precede scope classification.

### Heuristics

1. When a file is within 5% of its line budget limit, evaluate refactor-to-generic as a prerequisite, not a future optimization.
2. Features including a refactor should expect 3 spec iterations and 2-3 plan iterations.
3. Domain cost formula: ~1 line brainstorming + ~110 lines SKILL.md + ~500-900 lines references + ~7 lines reviewer = ~620-1020 total.
4. After 3 features use an untested runtime mechanism, add a smoke test. Do not punt.
5. Reference file sweet spot: 60-100 lines per file. The 160-line maximum has never been close to binding.

## Knowledge Bank Updates

- Generic-Before-Add pattern added to knowledge bank
- Domain cost formula documented for capacity planning
- Source-of-truth declaration practice documented
