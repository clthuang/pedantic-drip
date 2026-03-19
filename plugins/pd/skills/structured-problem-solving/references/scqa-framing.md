# SCQA Framing Template

SCQA (Situation-Complication-Question-Answer) is a universal problem framing tool from Barbara Minto's Pyramid Principle. It bridges into structured decomposition by producing a clear Question that becomes the root of the decomposition tree.

## Template

- **Situation:** The established context everyone agrees on — current state, known facts, shared understanding
- **Complication:** What changed, what's broken, or why action is needed now — the tension that creates urgency
- **Question:** The specific question this analysis must answer — derived from the complication
- **Answer:** The proposed direction or hypothesis — what we believe should be done

**Usage:** Fill in S, then C, then Q (which flows naturally from C), then A. The Question becomes the root node for type-specific decomposition.

## Guidance by Problem Type

### product/feature
- **S:** Current user experience and workflow
- **C:** What's broken, missing, or slow for users
- **Q:** How should we change the product to solve this?
- **A:** Proposed feature/change with rationale

### technical/architecture
- **S:** Current system architecture and constraints
- **C:** Technical debt, scaling limits, or integration gaps
- **Q:** How should we restructure to resolve this?
- **A:** Proposed architecture change with migration path

### financial/business
- **S:** Current business model, revenue, or cost structure
- **C:** Market shift, cost pressure, or opportunity gap
- **Q:** What business change maximizes value?
- **A:** Proposed business model/pricing with projected impact

### research/scientific
- **S:** Current state of knowledge in the domain
- **C:** What's unknown, contradictory, or unverified
- **Q:** What hypothesis should we test?
- **A:** Proposed research approach with expected outcomes

### creative/design
- **S:** Current design landscape and user expectations
- **C:** Design gap, aesthetic mismatch, or unexplored creative space
- **Q:** What design direction best serves the experience goals?
- **A:** Proposed creative direction with inspiration references

## Hardcoded Fallback

If reference files are unavailable, use this minimal SCQA template:

- **Situation:** {Describe the current state}
- **Complication:** {What changed or what's wrong}
- **Question:** {The key question to answer}
- **Answer:** {The proposed direction}

This fallback applies SCQA framing without type-specific guidance.
