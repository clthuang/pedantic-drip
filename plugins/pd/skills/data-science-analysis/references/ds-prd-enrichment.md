# DS PRD Enrichment

Guidance for enriching brainstorm PRDs with data science analysis. Use this reference to assess methodology, data needs, pitfalls, and modeling approach.

## Methodology Assessment Guide

### Problem Type Classification

| Type | Question Answered | Methods |
|------|------------------|---------|
| **Descriptive** | "What happened?" | Summary statistics, EDA, segmentation, dashboards |
| **Predictive** | "What will happen?" | ML classifiers/regressors, time series forecasting |
| **Causal** | "What should we do?" | RCT, DiD, IV, RDD, PSM, synthetic control |
| **Prescriptive** | "What's optimal?" | Optimization, simulation, reinforcement learning |

### Decision Criteria

- If the goal is **understanding patterns** → Descriptive
- If the goal is **forecasting/scoring** → Predictive
- If the goal is **measuring an intervention's effect** → Causal
- If the goal is **finding the best action** → Prescriptive
- If unclear → Start descriptive, then decide what question matters most

### Experimental Design Checklist

- Can you randomize treatment? → RCT is first choice
- Is there a natural threshold/cutoff? → Consider RDD
- Is there a before/after + treated/untreated structure? → Consider DiD
- Can you match treated to similar untreated? → Consider PSM
- One treated unit, many controls? → Consider Synthetic Control

## Data Requirements Assessment

### Volume Heuristics

| Task | Minimum Data Guidance |
|------|-----------------------|
| EDA/descriptive | 100+ rows per segment of interest |
| Simple classification | 10x features per class, minimum |
| Complex ML (deep learning) | 10,000+ samples typical |
| Causal inference | Depends on effect size; power analysis required |
| Time series | 2+ full seasonal cycles minimum |

### Quality Dimensions

- **Completeness:** What percentage of values are missing? Is missingness random (MCAR), dependent on observed data (MAR), or dependent on unobserved data (MNAR)?
- **Accuracy:** Are values correct? Measurement error magnitude?
- **Consistency:** Are definitions stable over time and across sources?
- **Timeliness:** How fresh is the data? Is lag acceptable?
- **Representativeness:** Does the data represent the target population?

### Collection Pitfall Checklist

- [ ] Is the data collection mechanism biased toward certain populations?
- [ ] Are there survivorship effects (only "successful" entities in the data)?
- [ ] Is there selection on the outcome (data only exists for one outcome)?
- [ ] Are there temporal effects (data from different time periods mixed)?
- [ ] Is there label noise (ground truth unreliable)?

## Pitfall Risk Assessment

### High-Risk Indicators

Map concept characteristics to likely pitfalls:

| Concept Characteristic | High-Risk Pitfalls |
|-----------------------|-------------------|
| Uses observational data | Selection Bias, Confounding, Simpson's Paradox |
| Involves time series | Look-ahead Bias, Data Leakage, Immortal Time Bias |
| Tests multiple hypotheses | Multiple Comparisons |
| Uses model feature importance for decisions | Correlation vs Causation |
| Studies "top performers" | Survivorship Bias, Regression to the Mean |
| Aggregates across groups | Simpson's Paradox, Ecological Fallacy |
| Rare event prediction | Base Rate Fallacy |
| Before/after comparison without control | Regression to the Mean |

### Mitigation Strategies

For each identified pitfall:
1. State why this concept is at risk
2. Propose a specific prevention step
3. Describe how to detect it if it occurs

## Modeling Approach Selection

### Evaluation Strategy by Problem Type

| Problem Type | Primary Metrics | Validation Approach |
|-------------|----------------|-------------------|
| Classification | Precision, Recall, F1, AUC-ROC | Stratified k-fold CV |
| Regression | RMSE, MAE, R-squared | k-fold CV, residual analysis |
| Causal | ATE, ATT with CI | Placebo tests, sensitivity analysis |
| Time series | MAPE, RMSE, coverage | Time-series CV (expanding window) |
| Ranking | NDCG, MAP, MRR | Leave-one-out or temporal split |

### Production Readiness Checklist

- [ ] Baseline model defined (what to beat)
- [ ] Evaluation metric agreed upon with stakeholders
- [ ] Monitoring plan for model drift
- [ ] Retraining cadence defined
- [ ] Fallback plan if model underperforms
