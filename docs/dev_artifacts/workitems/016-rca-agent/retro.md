# Retrospective: Root Cause Analysis Agent

## What Went Well

- **Multi-iteration review process caught blockers early** — Design (3), Plan (3), Task (2) iterations resolved all blockers before implementation, resulting in single-pass implementation approval
- **Comprehensive PRD research validated design** — 9 external citations including OpenRCA benchmark, Meta RCA approach, and industry best practices informed design decisions
- **Design explicitly addressed LLM RCA limitations** — Added "Design Rationale" section explaining how 5 structured mitigations counter 11.34% OpenRCA benchmark failure rate
- **Trigger phrase differentiation** — Explicitly differentiated root-cause-analysis from systematic-debugging by triggers and output type, preventing confusion
- **Reference file evolution improved design** — causal-dag.md (89 lines with DAG patterns) replaced fishbone-categories.md as better fit for software debugging
- **Security concern resolved via architecture decision** — Write path restrictions documented as accepted design trade-off per prior decision removing write-control hooks

## What Could Improve

- **Agent frontmatter format evolved during review** — Design used `<example>` XML blocks; implementation used YAML `examples:` field. Format divergence may confuse future authors.
- **Reference file naming changed from spec** — Design specified fishbone-categories.md but implementation created causal-dag.md. Both serve similar purpose but naming/content diverged.
- **3 design iterations due to ambiguous directory creation** — agent_sandbox/ creation responsibility not specified initially
- **Plan reviewer found missing 'name' field** — validate.sh requirement not reflected in initial plan; should verify validator requirements early
- **Task review had to merge 12 tasks into 8** — Initial breakdown too granular; file-level tasks should be merged
- **Token/word/line budget inconsistency** — Plan initially said '<5000 words' but authoring guide specifies '<500 lines, <5000 tokens'

## Patterns Worth Documenting

| Pattern | Description |
|---------|-------------|
| **6-phase structured process** | CLARIFY → REPRODUCE → INVESTIGATE → EXPERIMENT → ANALYZE → REPORT provides clear checkpoints |
| **Minimum hypothesis requirement** | Require 3+ hypotheses but allow documenting 'considered but discarded' options |
| **Structured YAML examples** | Use `examples:` field with context/user/assistant/commentary keys |
| **Info-only handoff** | Pass description string and display path rather than modifying receiving command |
| **Date-based sandbox subdirs** | Use agent_sandbox/{YYYYMMDD}/rca-{slug}/ for visual organization (cleanup uses mtime) |
| **Causal DAG over Fishbone** | DAGs better capture interaction effects and multiple causes |
| **Trigger phrase differentiation table** | Explicitly document which triggers map to which skill |

## Anti-Patterns to Avoid

| Anti-Pattern | Consequence |
|--------------|-------------|
| Assuming validate.sh requirements without checking | Plan omitted required 'name:' field |
| Over-granular task breakdown | 12 tasks merged to 8 in review |
| Ambiguous directory creation responsibility | Design iterations |
| Referencing design.md line numbers | Fragile references; use section names |
| Mixing words/tokens/lines for size limits | Confusion; standardize on lines + tokens |

## Heuristics

- 3 design review iterations is typical for agent/skill/command triads
- 3 plan review iterations for features with structured multi-phase processes
- 2 task review iterations when initial breakdown is too granular
- 1 implementation iteration when design and plan are thoroughly reviewed
- RCA/investigation agents need Write/Edit tools unlike read-only investigation agents
- Skill reference files can evolve during implementation
- Security concerns that are architecture decisions should be documented, not fixed
- Total implementation time ~3 hours for agent+skill+command with thorough review

## Metrics

| Metric | Value |
|--------|-------|
| Total phases | 5 |
| Design iterations | 3 |
| Plan iterations | 3 |
| Task iterations | 2 |
| Implementation iterations | 1 |
| Files created | 14 |
| Total lines added | 2,739 |
| Components | 1 agent, 1 skill, 1 command, 3 reference files |

## Notable Decisions

1. **Info-only handoff to /create-feature** — Avoids cross-component coupling; user references RCA report manually
2. **Write path restrictions via instructions not hooks** — Per architecture decision, CLAUDE.md provides centralized guidelines
3. **Causal DAG over Fishbone** — Better captures software debugging scenarios with interaction effects

## Open Questions for Future

- Should causal-dag.md pattern be added to systematic-debugging references?
- Should architecture decisions about write control be added to central ADR document?

---
*Generated during feature 016-rca-agent finish phase*
