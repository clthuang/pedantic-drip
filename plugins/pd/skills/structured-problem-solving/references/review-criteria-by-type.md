# Review Criteria by Problem Type

Criteria for the brainstorm-reviewer to validate domain-relevant analysis exists in a PRD.

## Universal Criteria (always applied)

These 5 checks apply to every brainstorm regardless of problem type:

1. **Problem clearly stated** — What are we solving?
2. **Goals defined** — What does success look like?
3. **Options explored** — Were alternatives considered?
4. **Direction chosen** — Is there a clear decision?
5. **Rationale documented** — Why this approach?

## Type-Specific Criteria

When a known problem type is present, also check the matching row (3 additional criteria):

| Problem Type | Check 1 | Check 2 | Check 3 |
|---|---|---|---|
| product/feature | Target users defined | User journey described | UX considerations noted |
| technical/architecture | Technical constraints identified | Component boundaries clear | Migration/compatibility noted |
| financial/business | Key assumptions quantified | Risk factors enumerated | Success metrics are financial |
| research/scientific | Hypothesis stated and testable | Methodology outlined | Falsifiability criteria defined |
| creative/design | Design space explored (>1 option) | Aesthetic/experiential goals stated | Inspiration/references cited |

**When Problem Type is absent, "none", or a custom string (from "Other"):** Apply universal criteria only. No type-specific checks.

## Criteria Descriptions

**Existence check, not correctness.** Each criterion verifies whether the relevant analysis EXISTS in the PRD, not whether it is correct, complete, or optimal. The reviewer checks presence, not quality.

### Universal Criteria

- **Problem clearly stated:** The PRD contains a section or paragraph that describes what problem is being solved. It doesn't need to be perfect — it needs to exist.
- **Goals defined:** The PRD mentions what success looks like, in any form (metrics, outcomes, user states). Doesn't need to be SMART-formatted.
- **Options explored:** The PRD shows evidence that alternatives were considered — could be a comparison table, pros/cons, or even "we considered X but rejected it because Y."
- **Direction chosen:** The PRD indicates a decision or recommendation, not just a list of options.
- **Rationale documented:** The PRD explains WHY the chosen direction was selected, with some reasoning (evidence, logic, or user input).

### Type-Specific Criteria

- **Target users defined:** The PRD mentions who the users/audience are. A sentence is enough.
- **User journey described:** The PRD describes some kind of user flow, before/after, or interaction sequence.
- **UX considerations noted:** The PRD acknowledges user experience factors (accessibility, usability, interaction patterns).
- **Technical constraints identified:** The PRD lists hard technical limits, dependencies, or compatibility requirements.
- **Component boundaries clear:** The PRD describes what parts of the system change and what stays the same.
- **Migration/compatibility noted:** The PRD addresses backward compatibility, migration path, or rollback strategy.
- **Key assumptions quantified:** The PRD includes numbers — estimates, ranges, or orders of magnitude for business assumptions.
- **Risk factors enumerated:** The PRD lists specific risks (not just "there are risks").
- **Success metrics are financial:** The PRD measures success in financial terms (ROI, revenue, cost reduction, margin).
- **Hypothesis stated and testable:** The PRD contains a falsifiable hypothesis — a claim that could be proven wrong.
- **Methodology outlined:** The PRD describes how the research/investigation would be conducted.
- **Falsifiability criteria defined:** The PRD specifies what evidence would disprove the hypothesis.
- **Design space explored (>1 option):** The PRD presents at least 2 distinct creative directions.
- **Aesthetic/experiential goals stated:** The PRD describes what the design should feel like or achieve experientially.
- **Inspiration/references cited:** The PRD references existing designs, mood boards, or precedent work.
