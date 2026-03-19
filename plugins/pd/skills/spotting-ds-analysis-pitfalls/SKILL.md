---
name: spotting-ds-analysis-pitfalls
description: "Use when reviewing analysis results, interpreting statistical findings, designing experiments, validating conclusions, or when the user asks to check for bias or pitfalls."
---

# Spotting Analysis Pitfalls

A routing table of 15 common statistical and analytical pitfalls. Use the diagnostic decision tree to identify which pitfalls are relevant, then consult the detailed reference files for prevention and detection guidance.

## Diagnostic Decision Tree

```
Is the problem about DATA COLLECTION?
├── YES → Is the sample representative?
│   ├── NO → Selection Bias, Sampling Bias, Survivorship Bias
│   └── Depends on conditioning → Berkson's Paradox
│
├── Is the problem about STATISTICAL REASONING?
│   ├── Is an aggregate hiding subgroup patterns? → Simpson's Paradox
│   ├── Are you running multiple tests? → Multiple Comparisons (p-hacking)
│   ├── Are you generalizing from groups to individuals? → Ecological Fallacy
│   ├── Are prior probabilities being ignored? → Base Rate Fallacy
│   └── Are extreme values returning to normal? → Regression to the Mean
│
├── Is the problem about TIME or DATA LEAKAGE?
│   ├── Does the model use future information? → Look-ahead Bias
│   ├── Is there an immortal period in the study? → Immortal Time Bias
│   └── Did preprocessing leak test data? → Overfitting & Data Leakage
│
└── Is the problem about DRAWING CONCLUSIONS?
    ├── Inferring causation from correlation? → Correlation vs Causation
    ├── Seeing only confirming evidence? → Confirmation Bias
    └── Are negative results missing? → Publication Bias
```

## Pitfall Quick Reference

### Sampling & Selection Issues

| # | Pitfall | One-Line Definition | Red Flag | One-Line Fix | Reference |
|---|---------|-------------------|----------|-------------|-----------|
| 1 | Selection Bias | Non-random sample inclusion distorts results | "We only analyzed users who completed onboarding" | Define population first, then sample randomly | [sampling-and-selection.md](references/sampling-and-selection.md) |
| 2 | Sampling Bias | Sample doesn't represent the target population | "Our survey was online-only" | Stratified sampling; weight underrepresented groups | [sampling-and-selection.md](references/sampling-and-selection.md) |
| 3 | Survivorship Bias | Analyzing only successes, ignoring failures | "Top-performing companies all do X" | Include failures in analysis; ask "where are the missing?" | [sampling-and-selection.md](references/sampling-and-selection.md) |
| 4 | Berkson's Paradox | Conditioning on a collider creates spurious associations | Negative correlation appears only in hospital data | Check if your sample was conditioned on an outcome | [sampling-and-selection.md](references/sampling-and-selection.md) |

### Statistical Traps

| # | Pitfall | One-Line Definition | Red Flag | One-Line Fix | Reference |
|---|---------|-------------------|----------|-------------|-----------|
| 5 | Simpson's Paradox | Trend reverses when data is aggregated/disaggregated | Overall trend contradicts every subgroup | Always check subgroups before reporting aggregates | [statistical-traps.md](references/statistical-traps.md) |
| 6 | Multiple Comparisons | Running many tests inflates false positive rate | "We tested 50 features and found 3 significant ones" | Bonferroni correction or FDR (Benjamini-Hochberg) | [statistical-traps.md](references/statistical-traps.md) |
| 7 | Ecological Fallacy | Inferring individual behavior from group-level data | "Countries with more X have more Y, so X causes Y in individuals" | Use individual-level data; don't generalize across levels | [statistical-traps.md](references/statistical-traps.md) |
| 8 | Base Rate Fallacy | Ignoring prevalence when interpreting test results | "The test is 99% accurate, so a positive result means 99% chance" | Apply Bayes' theorem with actual base rates | [statistical-traps.md](references/statistical-traps.md) |
| 9 | Regression to the Mean | Extreme values naturally return toward average | "The intervention worked — extreme cases improved" | Use control groups; measure from population mean, not extremes | [statistical-traps.md](references/statistical-traps.md) |

### Temporal & Leakage Issues

| # | Pitfall | One-Line Definition | Red Flag | One-Line Fix | Reference |
|---|---------|-------------------|----------|-------------|-----------|
| 10 | Overfitting & Data Leakage | Model learns noise or uses information it shouldn't have | Excellent training metrics, poor production performance | Strict train/test split before any preprocessing | [temporal-and-leakage.md](references/temporal-and-leakage.md) |
| 11 | Look-ahead Bias | Using future data to make past predictions | Features include data from after the prediction date | Time-ordered splits; features use only past data | [temporal-and-leakage.md](references/temporal-and-leakage.md) |
| 12 | Immortal Time Bias | Period where outcome cannot occur is counted as follow-up | "Users who upgraded within 30 days had better retention" | Align time zero with treatment start; use time-varying analysis | [temporal-and-leakage.md](references/temporal-and-leakage.md) |

### Inference Errors

| # | Pitfall | One-Line Definition | Red Flag | One-Line Fix | Reference |
|---|---------|-------------------|----------|-------------|-----------|
| 13 | Correlation vs Causation | Assuming association implies causation | "Feature X is most important in the model, so X causes Y" | Identify confounders/colliders/mediators; use causal methods | [inference-errors.md](references/inference-errors.md) |
| 14 | Confirmation Bias | Seeking/favoring evidence that confirms existing beliefs | Only reporting analyses that match expectations | Pre-register hypotheses; actively seek disconfirming evidence | [inference-errors.md](references/inference-errors.md) |
| 15 | Publication Bias | Positive results are published, negatives are hidden | "All studies show X works" | Report all results including nulls; check for funnel plot asymmetry | [inference-errors.md](references/inference-errors.md) |

## Before You Publish Checklist

Run through this before sharing any analysis or model:

### Data Quality
- [ ] Is the sample representative of the target population?
- [ ] Are there survivorship or selection effects in the data?
- [ ] Have missing values been handled transparently (not silently dropped)?
- [ ] Is the sample size large enough to support the stated claims?

### Statistical Validity
- [ ] Have you checked for Simpson's Paradox (subgroup vs aggregate)?
- [ ] If running multiple tests, have you applied multiple comparison correction?
- [ ] Are confidence intervals reported alongside point estimates?
- [ ] Is statistical significance confused with practical significance?

### Temporal Integrity
- [ ] Is the train/test split time-ordered for temporal data?
- [ ] Do features only use information available at prediction time?
- [ ] Is there any preprocessing leakage (fit on full data before split)?
- [ ] Are there immortal time periods in survival/retention analyses?

### Causal Claims
- [ ] Are causal claims supported by causal methods (not just correlation)?
- [ ] Have confounders been identified and addressed?
- [ ] Is feature importance being misinterpreted as causal effect?
- [ ] Have you considered reverse causation?

### Reporting
- [ ] Are negative/null results reported alongside positive ones?
- [ ] Are limitations explicitly stated?
- [ ] Are assumptions documented (distributional, independence, etc.)?
- [ ] Is the analysis reproducible from the code provided?

## How to Use This Skill

When reviewing analysis:
1. Walk through the **Diagnostic Decision Tree** to identify which category of pitfalls applies
2. Check each relevant pitfall in the **Quick Reference** tables
3. For any flagged pitfalls, read the detailed reference file for prevention and detection steps
4. Use the **Before You Publish Checklist** as a final sweep

When reviewing code:
- Pair this skill with the `writing-ds-python` skill for code-level anti-patterns
- Focus this skill on analytical/statistical correctness, not code style
