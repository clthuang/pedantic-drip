---
name: choosing-ds-modeling-approach
description: "Use when choosing between predictive and causal modeling, designing experiments, evaluating causal claims, or selecting methods like DiD, IV, RDD, PSM, or uplift modeling."
---

# Choosing a Modeling Approach

Guide for selecting between predictive and causal modeling approaches. The core question is: **"What will happen?" (prediction) vs "What should we do?" (causal inference).**

## The Core Question

Before choosing a method, answer this:

| Question | Approach | Example |
|----------|----------|---------|
| "What will happen?" | **Predictive** | What's the probability this customer will churn? |
| "What should we do?" | **Causal** | Will sending a discount email reduce churn? |
| "What would have happened?" | **Counterfactual** | Would this customer have churned without the email? |

**The critical mistake:** Using predictive model feature importance to answer causal questions. A random forest may show "discount_received" as the top predictor of retention, but that doesn't mean discounts cause retention. Discounts may be sent to at-risk users (confounding).

## Decision Flowchart

```
What question are you trying to answer?
│
├── "What will happen?" (Prediction)
│   └── Use predictive modeling
│       ├── Structured data → Gradient boosted trees (XGBoost, LightGBM)
│       ├── Text/image → Deep learning
│       ├── Time series → ARIMA, Prophet, or temporal models
│       └── Evaluate: accuracy, precision, recall, AUC, calibration
│
└── "What should we do?" / "What caused this?" (Causal)
    │
    ├── Can you randomize treatment?
    │   ├── YES → Randomized Controlled Trial (RCT / A/B test)
    │   │         Gold standard. Random assignment eliminates confounders.
    │   └── NO → Need quasi-experimental method
    │
    └── Is there a natural experiment?
        ├── Policy change / threshold → Regression Discontinuity (RDD)
        ├── Before/after + treated/untreated → Difference-in-Differences (DiD)
        ├── External shock affects treatment → Instrumental Variables (IV)
        ├── Can match treated to similar untreated → Propensity Score Matching (PSM)
        └── Few treated units, many controls → Synthetic Control
```

## Predictive vs Causal: Comparison

| Dimension | Predictive | Causal |
|-----------|-----------|--------|
| **Goal** | Minimize prediction error | Estimate treatment effect |
| **Key metric** | Accuracy, AUC, RMSE | ATE, ATT, CATE |
| **Model selection** | Cross-validation | Domain knowledge + assumptions |
| **Feature selection** | Whatever improves prediction | Only pre-treatment variables |
| **Interpretability** | "Feature importance" (not causal) | Effect size with confidence interval |
| **Confounders** | Don't matter (prediction is fine with confounders) | Must be addressed (bias the estimate) |
| **Colliders** | Can include (improves prediction) | Must NOT control for (introduces bias) |
| **Overfitting risk** | High (use regularization, CV) | Low (but specification error is high) |
| **External validity** | Depends on training data distribution | Depends on assumptions holding |
| **Common methods** | XGBoost, neural nets, random forest | DiD, IV, RDD, PSM, RCT |

## Common Mistake: Feature Importance as Causal Evidence

```
                 Confounding Variable (Z)
                ╱                        ╲
               ↓                          ↓
    Treatment (X)  ──────?──────>  Outcome (Y)
```

**What feature importance tells you:** X is correlated with Y in the training data.
**What it does NOT tell you:** Changing X will change Y.

**Example:** A churn model shows "number_of_support_tickets" as the top predictor. Does closing support tickets reduce churn? No — both high tickets and churn are caused by product problems (the confounder).

**Rule:** Never use predictive model feature importance to recommend interventions. Use causal methods instead.

## Hybrid Approaches

When you need both prediction and causal insight:

| Approach | What It Does | When to Use |
|----------|-------------|-------------|
| **Uplift modeling** | Predicts individual treatment effect (CATE) | Targeting: who benefits most from treatment? |
| **Causal forests** | Non-parametric heterogeneous treatment effects | When effect varies by subgroup, many covariates |
| **Meta-learners** (S, T, X) | Combine any ML model with causal framing | Flexible CATE estimation with existing models |
| **Double ML** | ML for nuisance parameters, causal for target | High-dimensional confounders |

See [hybrid-approaches.md](references/hybrid-approaches.md) for details.

## Framework Comparison: Rubin vs Pearl

Two dominant frameworks for causal inference:

| Aspect | Rubin (Potential Outcomes) | Pearl (Structural Causal Models) |
|--------|---------------------------|----------------------------------|
| **Core concept** | What would have happened under alternative treatment? | What happens when we intervene (do-operator)? |
| **Language** | Potential outcomes Y(0), Y(1) | DAGs, do-calculus, SCMs |
| **Strengths** | Rigorous estimation, connects to experiments | Visual reasoning, handles complex causal chains |
| **Weaknesses** | Hard to reason about complex structures | Requires correct DAG specification |
| **Common methods** | PSM, IPW, DiD, IV | Backdoor/frontdoor criteria, mediation analysis |
| **Best for** | Estimating treatment effects | Understanding causal mechanisms |

In practice, use both: Pearl's DAGs to reason about structure, Rubin's framework to estimate effects.

See [causal-frameworks.md](references/causal-frameworks.md) for details.

## Method Selection Quick Reference

| Method | Key Assumption | Data Requirement | Strength |
|--------|---------------|-----------------|----------|
| **RCT** | Random assignment | Randomized experiment | Gold standard; eliminates all confounders |
| **DiD** | Parallel trends | Before/after, treated/untreated | Works with observational data; intuitive |
| **RDD** | Continuity at cutoff | Running variable with threshold | Strong internal validity near cutoff |
| **IV** | Exclusion restriction | Instrument affecting treatment only | Handles unmeasured confounders |
| **PSM** | No unmeasured confounders | Rich covariates | Intuitive matching; flexible |
| **Synthetic Control** | Pre-treatment fit | Multiple control units over time | Few treated units; transparent weights |

See [causal-methods.md](references/causal-methods.md) for detailed assumptions, limitations, and examples.

## When to Recommend What

| Scenario | Recommendation |
|----------|---------------|
| "Should we launch this feature?" | RCT (A/B test) if possible |
| "Did the policy change work?" | DiD or Synthetic Control |
| "Who should we target for the offer?" | Uplift modeling (CATE estimation) |
| "What drives customer satisfaction?" | Causal DAG + matched method, NOT regression coefficients |
| "Will this customer churn?" | Predictive model (no causal claims needed) |
| "Does the new checkout flow increase conversion?" | RCT; if not possible, RDD at rollout boundary |
