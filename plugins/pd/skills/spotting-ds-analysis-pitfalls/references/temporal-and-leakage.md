# Temporal & Leakage Pitfalls

Detailed guidance for Look-ahead Bias, Immortal Time Bias, Overfitting, and Data Leakage.

## Overfitting & Data Leakage

**What it is:** The model learns patterns specific to the training data (noise) rather than generalizable patterns, or the model has access to information it shouldn't have during training.

**Red flag:** Excellent training/validation metrics but poor production performance. Model accuracy drops significantly on new data.

**Example — Target Leakage:** Predicting customer churn, and a feature is "cancellation_reason." This field is only populated after the customer churns — it's a consequence of the target, not a predictor.

**Example — Preprocessing Leakage:** Fitting a StandardScaler on the entire dataset before train/test split. The test set's statistics influence the training data transformation, giving an optimistic estimate of performance.

**Prevention:**
- **Strict temporal split:** For time-series data, always split by time. Never shuffle temporal data.
- **Pipeline approach:** Use sklearn Pipelines to ensure preprocessing is fit only on training data.
- **Feature audit:** For every feature, ask: "Would this be available at prediction time?"
- **Cross-validation:** Use time-series cross-validation (expanding window) for temporal data.

```python
# BAD: Leaks test data statistics
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)  # fit on ALL data
X_train, X_test = train_test_split(X_scaled)

# GOOD: Fit only on training data
X_train, X_test = train_test_split(X)
scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_test = scaler.transform(X_test)  # transform only
```

**Detection:**
- Compare training accuracy to test accuracy — large gap suggests overfitting
- Check: are any features derived from or correlated with the target in a way that wouldn't exist at prediction time?
- Use feature importance: if a single feature dominates, investigate whether it's leaking the target
- Test on truly held-out data from a different time period

### Common Leakage Sources

| Leakage Type | Example | Fix |
|-------------|---------|-----|
| Target leakage | Using "cancellation_reason" to predict churn | Remove features that are consequences of the target |
| Temporal leakage | Using next month's sales to predict this month | Enforce time-ordered features |
| Preprocessing leakage | Imputing missing values with full-dataset mean | Fit imputer on training set only |
| Feature engineering leakage | Aggregates computed over train+test | Compute aggregates on training set only |
| ID leakage | User ID correlates with target through grouping | Remove or encode IDs properly |

## Look-ahead Bias

**What it is:** Using information from the future to make predictions about the past or present. Common in financial modeling and time-series analysis.

**Red flag:** Features include data from after the prediction date. "We used the average price over the next 30 days."

**Example:** Building a stock prediction model using features that include future price movements or volume data. The model looks great in backtesting but fails in live trading because future data isn't available at prediction time.

**Prevention:**
- For every feature, verify: "Was this data available at the time the prediction would be made?"
- Use point-in-time correctness: features should only use data from before the prediction timestamp
- In backtesting, simulate the information state at each prediction point
- Use expanding-window cross-validation, never shuffle temporal data

**Detection:**
- Check feature generation timestamps against prediction timestamps
- If backtesting performance is suspiciously good (e.g., >90% accuracy on stock prices), suspect look-ahead bias
- Trace each feature back to its source data and verify temporal ordering
- Test: does performance degrade when you add a lag to features?

## Immortal Time Bias

**What it is:** A period during which the outcome cannot occur is counted as follow-up time, biasing results in favor of the treatment group.

**Red flag:** Cohort definition requires something that takes time (e.g., "users who upgraded within 30 days"), creating a survival advantage for the treated group.

**Example:** Studying whether premium subscribers have better retention. You define "premium users" as those who upgrade within the first 30 days. By definition, these users survived 30 days without churning — giving them a built-in survival advantage over the comparison group, which includes users who churned in the first 30 days.

**Prevention:**
- Align time zero with the treatment start, not with study enrollment
- Use time-varying covariates: a user is "control" until they upgrade, then "treatment"
- Landmark analysis: only include users who survived to a fixed time point, then compare
- Intent-to-treat: analyze based on initial group assignment, not eventual behavior

**Detection:**
- Check: is there a period between study entry and treatment where the treated group "must have survived"?
- Compare the time-to-event distributions — if the treated group has a gap at the beginning, suspect immortal time bias
- Ask: "Could a subject in the control group have experienced the outcome during the immortal period?"
- Verify that time zero is the same for treatment and control groups
