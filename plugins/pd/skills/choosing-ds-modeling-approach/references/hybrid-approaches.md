# Hybrid Approaches

Methods that combine machine learning with causal inference for heterogeneous treatment effect estimation.

## Uplift Modeling

**What it is:** Predicts the individual-level treatment effect (CATE) — how much a specific individual's outcome would change due to treatment. Used for targeting: identify who benefits most from an intervention.

**The four quadrants:**

| Group | Treatment Effect | Action |
|-------|-----------------|--------|
| **Persuadables** | Positive CATE | Target these — treatment works |
| **Sure Things** | Positive outcome regardless | Don't waste treatment here |
| **Lost Causes** | Negative outcome regardless | Treatment won't help |
| **Sleeping Dogs** | Negative CATE | Treatment backfires — avoid |

**Methods:**

- **Two-Model (T-learner):** Train separate models on treatment and control. CATE = E[Y|X, T=1] - E[Y|X, T=0]. Simple but ignores shared structure.
- **Single-Model (S-learner):** Train one model with treatment as a feature. CATE = f(X, T=1) - f(X, T=0). Can underestimate effects if treatment variable is "drowned out."
- **Class Transformation:** Transform the problem into a single classification task (works for binary outcomes).

**When to use:** Marketing (who to send offers to), medicine (personalized treatment), product (who benefits from a feature).

**Pitfall:** Requires RCT data (or strong ignorability assumption) to train on. Observational data introduces confounding into CATE estimates.

## Causal Forests

**What it is:** Extension of random forests that estimates heterogeneous treatment effects. Each tree split is optimized to maximize treatment effect heterogeneity across subgroups.

**How it works:**
1. Split data into estimation and splitting samples (honesty)
2. For each tree, find splits that maximize the difference in treatment effects between the two child nodes
3. Estimate CATE by averaging honest estimates across trees

**Key properties:**
- Non-parametric: no assumptions about the functional form of CATE
- Honest estimation: splitting and estimation use different data (reduces overfitting)
- Asymptotically normal: enables confidence intervals for CATE
- Built-in variable importance for effect modification

**Implementation (econml/grf):**

```python
from econml.dml import CausalForestDML

model = CausalForestDML(
    model_y=LGBMRegressor(),
    model_t=LGBMClassifier(),
    n_estimators=1000,
    random_state=42,
)
model.fit(Y, T, X=X, W=W)

# Individual treatment effects
cate = model.effect(X_test)

# Confidence intervals
lb, ub = model.effect_interval(X_test, alpha=0.05)
```

**When to use:** Many covariates, non-linear effect modification, need confidence intervals. Requires experimental or strongly unconfounded data.

## Meta-Learners

### S-Learner (Single Model)

```
Train: f(X, T) → Y
CATE(x) = f(x, T=1) - f(x, T=0)
```

- Simplest approach
- Can use any ML model
- Risk: treatment variable may be "regularized away" if effect is small

### T-Learner (Two Models)

```
Train: f₁(X) → Y|T=1   and   f₀(X) → Y|T=0
CATE(x) = f₁(x) - f₀(x)
```

- Separate models for treated and control
- More flexible but doubles the number of models
- Risk: different models may learn different biases

### X-Learner (Cross-Learner)

```
Step 1: Train f₁(X) on treated, f₀(X) on control
Step 2: Impute treatment effects:
  - For treated: τ₁ = Y₁ - f₀(X₁)
  - For control: τ₀ = f₁(X₀) - Y₀
Step 3: Train models on imputed effects
Step 4: Weight using propensity scores
```

- Best when treatment and control group sizes differ significantly
- More efficient than T-learner for small treatment groups
- More complex implementation

### Comparison

| Meta-Learner | Best When | Weakness |
|-------------|-----------|----------|
| S-Learner | Effect is large, simple | Underestimates small effects |
| T-Learner | Balanced groups, different effect shapes | Needs sufficient data per group |
| X-Learner | Imbalanced groups | More complex, depends on propensity |

## Double Machine Learning (DML)

**What it is:** Use ML to model confounders (nuisance parameters), then use the residualized data for causal estimation. Separates "prediction" (handled by ML) from "causal estimation" (handled by econometrics).

**How it works:**
1. Predict Y from X using ML: Ŷ = g(X). Get residuals: Ỹ = Y - Ŷ
2. Predict T from X using ML: T̂ = m(X). Get residuals: T̃ = T - T̂
3. Regress Ỹ on T̃ to get the causal effect

**Key properties:**
- Handles high-dimensional confounders (ML does the heavy lifting)
- Debiased: cross-fitting removes overfitting bias
- Root-n consistent under mild conditions
- Can use any ML model for nuisance parameters

**When to use:** Many confounders, want a simple treatment effect estimate, have ML models that predict well.

## CATE Estimation Summary

| Method | Flexibility | Data Requirement | Inference | Complexity |
|--------|------------|-----------------|-----------|------------|
| S-Learner | Low | Any ML | Bootstrap | Low |
| T-Learner | Medium | Separate models | Bootstrap | Low |
| X-Learner | High | Propensity scores | Bootstrap | Medium |
| Causal Forest | High | RCT or unconfounded | Asymptotic | Medium |
| Double ML | Medium | Cross-fitting | Asymptotic | Medium |
