# Statistical Traps

Detailed guidance for Simpson's Paradox, Multiple Comparisons, Ecological Fallacy, Base Rate Fallacy, and Regression to the Mean.

## Simpson's Paradox

**What it is:** A trend that appears in aggregated data reverses or disappears when the data is disaggregated into subgroups.

**Red flag:** An overall statistic tells a different story than every subgroup. "Treatment A is better overall, but Treatment B is better in every subgroup."

**Example:** A company finds that overall, employees who work from home have higher performance ratings. But when broken down by department, in-office workers score higher in every department. The paradox: departments with higher-performing employees also happen to have more remote workers.

**Prevention:**
- Always check results at the subgroup level before reporting aggregates
- Identify lurking/confounding variables that might differ across subgroups
- When aggregated and disaggregated results disagree, the disaggregated view is usually more informative
- Use stratified analysis or regression with confounders as covariates

**Detection:**
- Split data by key categorical variables and check if the trend holds
- If you have a surprising aggregate result, ask: "What variable is unevenly distributed across groups?"
- Plot the relationship within subgroups and compare to the overall plot

## Multiple Comparisons (p-hacking)

**What it is:** Running many statistical tests inflates the probability of finding at least one "significant" result by chance.

**Red flag:** "We tested 50 features and found 3 significant at p < 0.05." (Expected: 2.5 false positives by chance alone.)

**Example:** A/B testing 20 different button colors. At p < 0.05, you expect 1 false positive. Finding that "chartreuse converts 15% better" is likely noise.

**Prevention:**
- **Bonferroni correction:** Divide alpha by the number of tests. 50 tests at alpha=0.05 → use alpha=0.001 per test.
- **FDR (Benjamini-Hochberg):** Controls the expected proportion of false discoveries. Less conservative than Bonferroni.
- **Pre-register hypotheses:** Decide what you'll test before looking at data.
- **Limit exploratory tests:** Separate exploratory (hypothesis-generating) from confirmatory (hypothesis-testing) analysis.

**Detection:**
- Count the total number of statistical tests performed (including unreported ones)
- Check if corrections were applied
- Be suspicious of results that are "just barely significant" (p = 0.04) across many tests
- Ask: "How many things did you test to find this one result?"

## Ecological Fallacy

**What it is:** Inferring individual-level relationships from group-level (aggregated) data.

**Red flag:** Drawing individual conclusions from country/region/group averages. "States with higher ice cream sales have more drownings, so ice cream causes drowning."

**Example:** Countries with higher average income have higher rates of depression diagnoses. Conclusion: "Rich people are more depressed." Fallacy: The correlation at the country level doesn't hold at the individual level — richer countries simply have better mental health diagnosis infrastructure.

**Prevention:**
- Use individual-level data when making individual-level claims
- Don't generalize from one level of analysis to another
- State the level of analysis explicitly: "At the country level..." not "People who..."
- Use multilevel models if you have both group and individual data

**Detection:**
- Check: does the claim jump from group-level data to individual-level conclusions?
- Is the unit of analysis (country, company, group) different from the unit of inference (person, transaction)?
- Would the relationship hold if you had individual data?

## Base Rate Fallacy

**What it is:** Ignoring the prevalence (base rate) of a condition when interpreting test results or probabilities.

**Red flag:** "The test is 99% accurate" used to claim high confidence without considering how rare the condition is.

**Example:** A fraud detection model is 99% accurate. 0.1% of transactions are fraudulent. If the model flags a transaction, what's the probability it's actually fraud? Only ~9% (via Bayes' theorem). The 99.9% non-fraud base rate dominates.

**Prevention:**
- Always apply Bayes' theorem: P(condition|positive test) depends on P(condition) AND test accuracy
- Report positive predictive value (precision), not just sensitivity/specificity
- For rare events, even highly accurate classifiers produce many false positives
- Use confusion matrices with actual counts, not just percentages

**Detection:**
- Check: is the base rate of the condition being analyzed?
- If someone reports accuracy without base rates, ask: "What proportion of the population actually has this condition?"
- Calculate: false positive rate x (1 - base rate) vs true positive rate x base rate

## Regression to the Mean

**What it is:** Extreme observations tend to be followed by less extreme ones, purely due to natural variation.

**Red flag:** Attributing improvement to an intervention when subjects were selected for being extreme. "Students who scored worst improved most after tutoring."

**Example:** You identify the 10 worst-performing stores and implement a new training program. Next quarter, they improve. Was it the training? Probably not entirely — the worst performers were likely experiencing bad luck, and their natural variation would bring them closer to average regardless.

**Prevention:**
- Use control groups: compare treated extreme cases to untreated extreme cases
- Measure change from the population mean, not from the selected extreme
- If selecting subjects based on extreme values, expect regression and account for it
- Use pre-post designs with control groups, not just pre-post on extreme cases

**Detection:**
- Were subjects selected because they were extreme on the outcome variable?
- Is there a control group of equally extreme subjects who didn't receive the intervention?
- Would you expect improvement even without the intervention?
