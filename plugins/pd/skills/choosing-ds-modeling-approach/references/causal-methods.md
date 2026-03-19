# Causal Methods

Detailed reference for quasi-experimental and experimental methods in causal inference.

## Randomized Controlled Trial (RCT / A/B Test)

**What it is:** Randomly assign subjects to treatment or control groups. Random assignment ensures that, on average, groups are identical except for the treatment.

**Key assumption:** Random assignment is truly random and maintained (no differential attrition, no contamination).

**When to use:** When you can randomize. This is always preferred if feasible.

**Limitations:**
- Ethical constraints (can't randomly withhold treatment when lives are at stake)
- Compliance issues (subjects don't always follow their assignment)
- External validity: results may not generalize beyond the experimental context
- Sample size requirements for detecting small effects

**Implementation checklist:**
- [ ] Randomization mechanism is truly random (not alternating, not by time of day)
- [ ] Sample size is powered for expected effect size
- [ ] Pre-registered primary metric and analysis plan
- [ ] Intent-to-treat analysis (analyze by assignment, not by compliance)
- [ ] Check for balance on key covariates after randomization

## Difference-in-Differences (DiD)

**What it is:** Compare the change in outcome over time between a treated group and a control group. The treatment effect is the difference in differences.

**Key assumption:** **Parallel trends** — absent treatment, treated and control groups would have followed the same trend.

**When to use:** A policy, feature, or intervention was applied to one group but not another, and you have before/after data for both groups.

**Limitations:**
- Parallel trends assumption is untestable (can only check pre-treatment trends)
- Sensitive to group composition changes over time
- Doesn't handle staggered adoption well (use recent "staggered DiD" methods)

**Red flags in practice:**
- Pre-treatment trends are not parallel → DiD is inappropriate
- Treatment timing varies across units → need staggered DiD
- Only one pre-treatment period → cannot verify parallel trends

## Instrumental Variables (IV)

**What it is:** Use a variable (instrument) that affects the treatment but has no direct effect on the outcome, to isolate the causal effect of treatment.

**Key assumption:** **Exclusion restriction** — the instrument affects the outcome ONLY through the treatment. Plus relevance (instrument must actually affect treatment).

**When to use:** When there are unmeasured confounders and you can find a valid instrument.

**Classic instruments:**
- Distance to hospital (for studying hospital effects)
- Quarter of birth (for studying education effects)
- Rainfall (for studying agricultural productivity)
- Random assignment encouragement (for studying program effects with non-compliance)

**Limitations:**
- Valid instruments are rare and hard to justify
- Estimates are local (LATE — applies only to "compliers")
- Weak instruments bias results toward OLS estimates
- Exclusion restriction is untestable

## Regression Discontinuity Design (RDD)

**What it is:** Exploit a threshold/cutoff in a running variable that determines treatment. Compare outcomes just above and just below the threshold.

**Key assumption:** **Continuity** — subjects just above and just below the cutoff are essentially identical except for treatment.

**When to use:** Treatment is determined by a score crossing a threshold (credit scores, test scores, age cutoffs, policy thresholds).

**Limitations:**
- Only estimates the effect at the cutoff (local estimate)
- Manipulation of the running variable invalidates the design (check for bunching at cutoff)
- Requires sufficient observations near the cutoff
- Bandwidth selection affects results (run sensitivity analysis)

**Validity checks:**
- McCrary density test (no bunching at cutoff)
- Balance on covariates at cutoff
- Robustness to bandwidth choice

## Propensity Score Matching (PSM)

**What it is:** Match treated subjects with control subjects who have similar propensity to be treated (based on observed covariates). Compare outcomes within matched pairs.

**Key assumption:** **Conditional independence / unconfoundedness** — after matching on observed covariates, treatment assignment is as good as random.

**When to use:** Rich covariate data available; you believe all important confounders are observed.

**Limitations:**
- Cannot address unmeasured confounders (the fundamental limitation)
- Requires overlap (common support) — some treated units may have no good matches
- Sensitive to model specification for propensity scores
- Can discard many observations if overlap is poor

**Best practices:**
- Check covariate balance after matching (standardized mean differences < 0.1)
- Report the number of unmatched units
- Use sensitivity analysis (Rosenbaum bounds) to assess how much unmeasured confounding would overturn results
- Consider inverse probability weighting (IPW) as an alternative

## Synthetic Control

**What it is:** Construct a "synthetic" version of the treated unit by weighting control units to match pre-treatment outcomes. Compare the treated unit's post-treatment outcomes to the synthetic control.

**Key assumption:** The synthetic control, constructed from a weighted combination of donor units, would have continued to track the treated unit absent treatment.

**When to use:** Few treated units (often just one), many potential control units, and a long pre-treatment period.

**Limitations:**
- Works best with one treated unit (extensions for multiple exist but are newer)
- Requires good pre-treatment fit
- Sensitive to donor pool selection
- Inference is complex (use placebo tests)

**Example:** Did California's tobacco control program reduce smoking? Construct a "synthetic California" from a weighted average of other states that matches California's pre-program smoking trajectory.
