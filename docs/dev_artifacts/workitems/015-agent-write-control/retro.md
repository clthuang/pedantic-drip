# Retrospective: Agent Write Control

## What Went Well

- **Comprehensive review process** caught design inconsistencies before implementation
- **TDD approach** resulted in 50 tests with full coverage
- **Internet research** validated design patterns against industry standards (gitignore-style exclusions, fail-open behavior, ephemeral sandboxes)
- **Clean separation of concerns** in final implementation (346 lines, well-documented)
- Feature completed in ~4 hours with Full mode workflow
- **Implementation review feedback** was specific and actionable, all issues fixed in iteration 2
- **Fail-open design philosophy** applied consistently throughout
- **Defensive fallback patterns** prevented brittleness

## What Could Improve

- **Dependency decisions** (jq vs python3) should be made earlier to avoid spec/design inconsistency
- Initial plan violated TDD by scheduling tests after implementation - plan template should enforce test-first
- Design review took 3 iterations - earlier industry research might have reduced iteration count
- Task review took 5 iterations - task template could include more explicit dependency validation
- Timeout testing was skipped due to complexity - could benefit from helper function for timeout simulation

## Learnings Captured

### Patterns Worth Documenting

| Pattern | Description |
|---------|-------------|
| **Placeholder for glob-to-regex** | Use `__DOUBLESTAR__` placeholder when converting `**` before `*` to prevent ordering issues in regex conversion |
| **Single Python call with markers** | Parse multiple JSON arrays in one call using `__PROTECTED__`, `__WARNED__`, `__SAFE__` markers instead of multiple subprocess calls |
| **--source-only flag** | Enable unit testing of bash script functions by guarding `main` with `[[ "${1:-}" != "--source-only" ]]` |
| **TEST_CONFIG_DIR with trap** | Isolate test fixtures in temp directory with cleanup on exit |
| **Defensive fallbacks** | Provide inline fallback for dependencies (like escape_json) that might be missing |
| **OUTSIDE_PROJECT marker** | Return sentinel value for security boundary violations instead of empty string |
| **Fail-open design** | All errors result in silent allow to avoid blocking legitimate work |

### Anti-Patterns to Avoid

| Anti-Pattern | Why It's Bad |
|--------------|--------------|
| Tests after implementation in plan | Violates TDD; caught by plan-reviewer |
| Multiple JSON parsing calls | Performance waste; consolidate into single call |
| Silent `2>/dev/null` on errors | Masks error information; allow stderr logging |
| Hardcoded dates in test paths | Not portable; use generic names like "session" |
| Spec/design dependency mismatch | Causes confusion; decide dependencies upfront |

### Heuristics Discovered

- **Skeptic persona** in design review catches blockers that permissive review misses
- **3 design review iterations** is typical for features with bash hooks
- **5 task review iterations** before task breakdown is stable
- **2-pass implementation review** is optimal: find issues then verify fixes
- **Internet research early** in specify phase validates approach and prevents rework
- **27 tasks across 8 phases** is manageable granularity for hook features
- **Test count > 2x function count** for adequate coverage (50 tests for ~15 functions)

## Knowledge Bank Updates

None required - patterns documented above are feature-specific and captured in this retro.
