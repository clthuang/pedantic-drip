# Causal Frameworks

Detailed reference for the Rubin (potential outcomes) and Pearl (structural causal models) frameworks.

## Rubin Framework: Potential Outcomes

### Core Concept

For each unit i, there are two potential outcomes:
- **Y_i(1)** — the outcome if unit i receives treatment
- **Y_i(0)** — the outcome if unit i does not receive treatment

The **individual treatment effect** is: Y_i(1) - Y_i(0)

The **fundamental problem of causal inference:** We can never observe both potential outcomes for the same unit. We see Y_i(1) OR Y_i(0), never both.

### Key Estimands

| Estimand | Definition | Meaning |
|----------|-----------|---------|
| **ATE** | E[Y(1) - Y(0)] | Average effect across the entire population |
| **ATT** | E[Y(1) - Y(0) \| T=1] | Average effect on those who were treated |
| **LATE** | Effect on "compliers" | Average effect on those whose treatment status was changed by the instrument (IV) |
| **CATE** | E[Y(1) - Y(0) \| X=x] | Conditional average effect for subgroup with covariates X=x |

### Assumptions for Identification

1. **SUTVA (Stable Unit Treatment Value Assumption):**
   - No interference: one unit's treatment doesn't affect another's outcome
   - No hidden variations of treatment: treatment is well-defined

2. **Ignorability / Unconfoundedness:**
   - Conditional on observed covariates X: Y(0), Y(1) ⊥ T | X
   - Treatment assignment is "as good as random" after conditioning on X

3. **Overlap / Positivity:**
   - 0 < P(T=1|X) < 1 for all X
   - Every unit has some probability of being in either group

### Common Methods in Rubin Framework

- Matching (PSM, coarsened exact matching)
- Inverse probability weighting (IPW)
- Doubly robust estimation (AIPW)
- Instrumental variables (for LATE)
- Difference-in-differences

## Pearl Framework: Structural Causal Models

### Core Concept

Represent causal relationships as a **Directed Acyclic Graph (DAG)** where:
- Nodes are variables
- Edges represent direct causal effects
- Missing edges encode causal assumptions (no direct effect)

### The do-operator

Pearl's key innovation — distinguishing **seeing** from **doing**:

- **P(Y | X=x)**: Probability of Y given we OBSERVE X=x (may include confounding)
- **P(Y | do(X=x))**: Probability of Y if we INTERVENE to set X=x (removes confounding)

Observation conditions on X. Intervention removes all arrows INTO X and sets its value.

### DAG Construction

**Step 1:** List all relevant variables
**Step 2:** For each pair, decide: does A directly cause B?
**Step 3:** Draw directed edges
**Step 4:** Verify: is the graph acyclic (no loops)?
**Step 5:** Check for missing variables (unmeasured confounders shown as dashed nodes)

### Key Structural Patterns

**Chain (Mediator):** X → M → Y
- M mediates the effect of X on Y
- Controlling for M blocks the causal path (don't control if you want total effect)

**Fork (Confounder):** X ← Z → Y
- Z confounds the X-Y relationship
- MUST control for Z to get the causal effect of X on Y

**Collider:** X → Z ← Y
- Z is caused by both X and Y
- Do NOT control for Z — it opens a spurious path (Berkson's paradox)

### Backdoor Criterion

A set of variables Z satisfies the backdoor criterion relative to (X, Y) if:
1. No node in Z is a descendant of X
2. Z blocks every path between X and Y that contains an arrow into X

If Z satisfies the backdoor criterion: P(Y | do(X)) = Σ_z P(Y | X, Z=z) P(Z=z)

This converts the interventional query into an observational (estimable) quantity.

### Frontdoor Criterion

When the backdoor criterion fails (unmeasured confounders), the frontdoor criterion may still identify the effect:
1. M intercepts all directed paths from X to Y
2. There is no unblocked backdoor path from X to M
3. All backdoor paths from M to Y are blocked by X

## Practical: When to Use Which Framework

| Situation | Recommended Framework |
|-----------|----------------------|
| Designing an experiment | Rubin (clear potential outcomes, power analysis) |
| Reasoning about what to control for | Pearl (DAGs make it visual) |
| Estimating treatment effects | Rubin (mature estimation methods) |
| Understanding mechanisms/mediation | Pearl (path analysis, direct/indirect effects) |
| Communicating to stakeholders | Pearl (DAGs are intuitive visuals) |
| High-dimensional confounders | Rubin + ML (Double ML, causal forests) |

**In practice:** Draw a DAG (Pearl) to understand the structure, then use Rubin's framework to estimate effects.
