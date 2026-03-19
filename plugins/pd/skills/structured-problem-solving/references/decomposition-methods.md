# Decomposition Methods

Five methods for breaking down the SCQA Question into structured sub-problems. Each method produces a tree that becomes the basis for the mind map.

**Constraints (all methods):**
- Depth: 2-3 levels maximum
- Breadth: 2-5 items per layer
- Each layer should be MECE within its parent (mutually exclusive, collectively exhaustive)

## MECE Decomposition

**Used by:** product/feature, financial/business

Break the solution space into categories that are:
- **Mutually Exclusive:** No overlap between categories
- **Collectively Exhaustive:** No gaps in coverage

**Tree format:**
```
Question (from SCQA)
├── Category A
│   ├── Sub-item A1
│   └── Sub-item A2
├── Category B
│   ├── Sub-item B1
│   └── Sub-item B2
└── Category C
    ├── Sub-item C1
    └── Sub-item C2
```

**Common MECE patterns:**
- **Dichotomous:** Internal vs External, Supply vs Demand
- **Process-based:** Input → Process → Output
- **Elemental:** Who / What / When / Where / How
- **Segmentation:** By user type, geography, time period

## Issue Tree

**Used by:** technical/architecture

Diagnostic tree mapping "why" questions from root cause to symptoms:

**Tree format:**
```
Why is X a problem?
├── Factor 1: {testable hypothesis}
│   ├── Evidence for
│   └── Evidence against
├── Factor 2: {testable hypothesis}
│   ├── Sub-factor 2a
│   └── Sub-factor 2b
└── Factor 3: {testable hypothesis}
    └── Investigation needed
```

**Key rule:** Each branch should be independently verifiable. Leaf nodes are specific enough to investigate or test.

## Hypothesis Tree

**Used by:** research/scientific

Tree of testable claims where leaf nodes are falsifiable predictions:

**Tree format:**
```
Primary Research Question
├── Hypothesis H1: {claim}
│   ├── Prediction P1a: {if H1, then...}
│   └── Prediction P1b: {if H1, then...}
├── Hypothesis H2: {claim}
│   ├── Prediction P2a: {if H2, then...}
│   └── Prediction P2b: {if H2, then...}
└── Null Hypothesis H0: {nothing changes}
    └── Prediction P0: {expected baseline}
```

**Key rule:** Every leaf prediction must be falsifiable — there must be observable evidence that could disprove it.

## Design Space Exploration

**Used by:** creative/design

Map divergent creative options, then converge on evaluation:

**Tree format:**
```
Design Question
├── Option A: {creative direction}
│   ├── Strength: {what it does well}
│   └── Risk: {what could go wrong}
├── Option B: {creative direction}
│   ├── Strength: {what it does well}
│   └── Risk: {what could go wrong}
└── Evaluation Criteria
    ├── Aesthetic fit
    ├── Functional fit
    └── Emotional resonance
```

**Key rule:** Generate at least 2 distinct options before evaluating. Avoid premature convergence.

## Generic Issue Tree

**Used by:** "Other" types (custom problem descriptions)

A universal decomposition when no specific method applies:

**Tree format:**
```
Core Question
├── Dimension 1: {aspect of the problem}
│   ├── Sub-issue 1a
│   └── Sub-issue 1b
├── Dimension 2: {aspect of the problem}
│   ├── Sub-issue 2a
│   └── Sub-issue 2b
└── Dimension 3: {aspect of the problem}
    ├── Sub-issue 3a
    └── Sub-issue 3b
```

**Key rule:** Identify 2-4 independent dimensions of the problem. Each dimension should cover a distinct aspect without overlapping.
