# Data Science Analysis - Statistical Methodology Review

## Study Design: Feature Impact Analysis

The analysis evaluates the impact of various features on a customer churn prediction model using a dataset of 10,000 customer records.

## Pitfall 1: P-Hacking Without Multiple Comparison Correction

The analysis tested 20 different feature combinations as potential predictors of churn. The analysis team reported only the feature combination that achieved p < 0.05 statistical significance (specifically, p = 0.047). This represents selective reporting without adjusting for multiple hypothesis testing.

Pitfall: Without Bonferroni correction (α_corrected = 0.05/20 = 0.0025) or controlling False Discovery Rate, the reported p-value is misleading. With 20 tests, we expect ~1 false positive by random chance alone at p < 0.05 threshold.

## Pitfall 2: Missing Confidence Interval and Variance Estimate

The final report states: "The model achieves 87% accuracy on the test set."

Pitfall: Without a confidence interval or standard error, we cannot assess whether 87% is stable, precise, or subject to high variance. Does accuracy range from 82-92% across different samples? Is 87% significantly different from a 85% baseline? These questions remain unanswered.

## Correct Methodology 1: Cross-Validation with Stratified K-Fold

```
Model Performance: 85.2% ± 2.1% (mean ± std across 5 folds)
Fold 1: 84.8%
Fold 2: 86.1%
Fold 3: 84.5%
Fold 4: 85.9%
Fold 5: 85.4%
```

Correct: Stratified k-fold cross-validation (k=5) with reported mean and standard deviation provides both point estimate and uncertainty quantification. Stratification ensures each fold maintains the original class distribution.

## Correct Methodology 2: Hypothesis Pre-Registration and Adjusted Testing

Before data analysis, the team specified three primary hypotheses:
1. Recency of last transaction predicts churn (α = 0.05)
2. Customer tenure predicts churn (α = 0.05)
3. Account balance predicts churn (α = 0.05)

Results after Bonferroni correction:
- Hypothesis 1: p = 0.012 (< 0.0167 threshold) ✓ Significant
- Hypothesis 2: p = 0.008 (< 0.0167 threshold) ✓ Significant
- Hypothesis 3: p = 0.231 (> 0.0167 threshold) ✗ Not significant

Correct: Pre-registered hypotheses with adjusted significance threshold (0.05/3 ≈ 0.0167) prevent post-hoc p-hacking.
