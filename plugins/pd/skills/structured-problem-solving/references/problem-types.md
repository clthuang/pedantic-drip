# Problem Type Taxonomy

Five problem types, each with framing approach, decomposition method, domain-specific PRD sections, and review criteria.

## product/feature

### Framing Approach
SCQA with user-centric focus:
- **Situation:** Current user experience and workflow
- **Complication:** What's broken, missing, or slow for users
- **Question:** How should we change the product to solve this?
- **Answer:** Proposed feature/change with rationale

### Decomposition Method
MECE decomposition of the solution space:
- User segments (who is affected)
- User journeys (what flows change)
- Technical capabilities (how it's built)
- Success metrics (how we measure)

See [decomposition-methods.md](decomposition-methods.md) for tree format and constraints.

### PRD Sections
When this type is selected, the Structured Analysis should include:
- **Target Users** — personas or segments with needs
- **User Journey** — before/after flow comparison
- **UX Considerations** — interaction patterns, accessibility, edge cases

### Review Criteria
1. Target users defined
2. User journey described
3. UX considerations noted

---

## technical/architecture

### Framing Approach
SCQA with system-centric focus:
- **Situation:** Current system architecture and constraints
- **Complication:** Technical debt, scaling limits, or integration gaps
- **Question:** How should we restructure to resolve this?
- **Answer:** Proposed architecture change with migration path

### Decomposition Method
Issue tree mapping "why" questions:
- Root: Why is this a problem?
- Branches: Contributing factors (performance, coupling, complexity)
- Leaves: Specific, testable hypotheses

See [decomposition-methods.md](decomposition-methods.md) for tree format and constraints.

### PRD Sections
When this type is selected, the Structured Analysis should include:
- **Technical Constraints** — hard limits, dependencies, compatibility requirements
- **Component Boundaries** — what changes, what stays, interfaces between
- **Migration/Compatibility** — backward compatibility, rollback plan, phased rollout

### Review Criteria
1. Technical constraints identified
2. Component boundaries clear
3. Migration/compatibility noted

---

## financial/business

### Framing Approach
SCQA with business-centric focus:
- **Situation:** Current business model, revenue, or cost structure
- **Complication:** Market shift, cost pressure, or opportunity gap
- **Question:** What business change maximizes value?
- **Answer:** Proposed business model/pricing/investment with projected impact

### Decomposition Method
MECE decomposition of the business space:
- Revenue drivers (sources, growth levers)
- Cost structure (fixed, variable, scaling costs)
- Risk factors (market, execution, regulatory)
- Assumptions to validate (quantified where possible)

See [decomposition-methods.md](decomposition-methods.md) for tree format and constraints.

### PRD Sections
When this type is selected, the Structured Analysis should include:
- **Key Assumptions** — quantified assumptions with validation approach
- **Risk Factors** — enumerated risks with likelihood and impact
- **Financial Metrics** — success measured in financial terms (ROI, margin, payback)

### Review Criteria
1. Key assumptions quantified
2. Risk factors enumerated
3. Success metrics are financial

---

## research/scientific

### Framing Approach
SCQA with knowledge-centric focus:
- **Situation:** Current state of knowledge in the domain
- **Complication:** What's unknown, contradictory, or unverified
- **Question:** What hypothesis should we test?
- **Answer:** Proposed research approach with expected outcomes

### Decomposition Method
Hypothesis tree with falsifiable leaf nodes:
- Root: Primary research question
- Branches: Sub-hypotheses (each independently testable)
- Leaves: Specific, falsifiable predictions with evidence requirements

See [decomposition-methods.md](decomposition-methods.md) for tree format and constraints.

### PRD Sections
When this type is selected, the Structured Analysis should include:
- **Hypothesis** — stated clearly and testably
- **Methodology** — research approach, data collection, analysis plan
- **Falsifiability** — what evidence would disprove the hypothesis

### Review Criteria
1. Hypothesis stated and testable
2. Methodology outlined
3. Falsifiability criteria defined

---

## creative/design

### Framing Approach
SCQA with experience-centric focus:
- **Situation:** Current design landscape and user expectations
- **Complication:** Design gap, aesthetic mismatch, or unexplored creative space
- **Question:** What design direction best serves the experience goals?
- **Answer:** Proposed creative direction with inspiration references

### Decomposition Method
Design space exploration:
- Divergent options (2+ distinct creative directions)
- Evaluation criteria (aesthetic, functional, emotional)
- Convergent selection (chosen direction with rationale)
- Inspiration mapping (references, mood boards, precedents)

See [decomposition-methods.md](decomposition-methods.md) for tree format and constraints.

### PRD Sections
When this type is selected, the Structured Analysis should include:
- **Design Space** — multiple options explored (minimum 2)
- **Aesthetic/Experiential Goals** — what the design should feel like
- **Inspiration/References** — precedents, mood boards, reference designs

### Review Criteria
1. Design space explored (>1 option)
2. Aesthetic/experiential goals stated
3. Inspiration/references cited
