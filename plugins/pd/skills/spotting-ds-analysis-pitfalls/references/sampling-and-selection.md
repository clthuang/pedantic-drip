# Sampling & Selection Pitfalls

Detailed guidance for Selection Bias, Sampling Bias, Survivorship Bias, and Berkson's Paradox.

## Selection Bias

**What it is:** Non-random inclusion/exclusion of subjects distorts the sample, making results unrepresentative of the target population.

**Red flag:** Analysis is performed on a subset that was filtered by an outcome-related criterion. "We only analyzed customers who stayed for 6+ months."

**Example:** Studying churn predictors using only users who completed onboarding. Users who churned during onboarding are excluded, biasing the remaining sample toward more engaged users.

**Prevention:**
- Define the target population before selecting the sample
- Document all inclusion/exclusion criteria and justify each one
- Use intention-to-treat analysis where possible (include everyone who started)
- Check: "Who is missing from my dataset, and why?"

**Detection:**
- Compare your sample demographics against known population statistics
- Check if any filtering criteria are correlated with the outcome
- Look for unusually narrow distributions (sign of over-filtered data)

## Sampling Bias

**What it is:** The mechanism of collecting data systematically over- or under-represents certain groups.

**Red flag:** Data collection method inherently excludes populations. "We surveyed users via our mobile app."

**Example:** An online-only survey about technology adoption. People without internet access are excluded — the exact population most relevant to understanding non-adoption.

**Prevention:**
- Use stratified sampling to ensure representation across key demographics
- Weight underrepresented groups in analysis
- Use multiple data collection channels to reduce single-channel bias
- Document the sampling frame and any known gaps

**Detection:**
- Compare sample distribution to known population demographics
- Check response rates across subgroups
- Look for impossible or implausible distributions (e.g., 0% of a demographic group)

## Survivorship Bias

**What it is:** Analyzing only the entities that passed a selection process, ignoring those that didn't survive.

**Red flag:** Analysis only includes "successful" cases. "Companies that IPO'd all had trait X."

**Example:** Studying successful startups to find common traits. Conclusion: "All successful startups pivoted early." But you didn't check — maybe most startups that pivoted early also failed. You only see the survivors.

**Prevention:**
- Always ask: "Where are the missing? Who didn't make it into this dataset?"
- Include failures/dropouts in analysis when possible
- If studying outcomes, include the full cohort from the starting point
- Be suspicious of datasets that only contain positive outcomes

**Detection:**
- Check if your dataset has been pre-filtered by outcome
- Look for missing historical data (companies that went bankrupt, products discontinued)
- Compare early vs late cohorts — if early cohorts look "better," survivorship bias may be at play

## Berkson's Paradox

**What it is:** Conditioning on a collider variable creates a spurious negative association between two independent (or positively correlated) causes.

**Red flag:** A negative correlation appears in your sample that contradicts domain knowledge. Two traits are negatively correlated in hospital data but not in the general population.

**Example:** In a hospital dataset, diabetes and heart disease appear negatively correlated. Why? Hospitalization is a collider — people are hospitalized if they have diabetes OR heart disease. Among hospitalized patients, knowing someone has diabetes makes heart disease less likely (it "explains" their presence). In the general population, the correlation is positive or zero.

**Prevention:**
- Identify whether your sample was selected based on an outcome variable
- Draw a causal DAG — check for collider structures
- Don't condition on variables that are effects of the variables you're studying
- When possible, analyze the full population, not a conditioned subset

**Detection:**
- If you find a surprising negative correlation, check if your sample was conditioned on a variable
- Test: does the association change when you expand to a broader population?
- Draw the selection mechanism as a DAG and look for collider paths
