# Inference Errors

Detailed guidance for Correlation vs Causation, Confirmation Bias, and Publication Bias.

## Correlation vs Causation

**What it is:** Assuming that because two variables are correlated, one causes the other. Correlation can arise from confounders, colliders, mediators, or pure coincidence.

**Red flag:** "Feature X is the most important predictor, so X causes Y." Model feature importance is NOT causal evidence.

**Example:** Ice cream sales and drowning deaths are correlated. Neither causes the other — both are caused by hot weather (a confounder).

### Key Concepts

**Confounder:** A variable that causes both X and Y, creating a spurious association.
```
Temperature (confounder)
    ↓           ↓
Ice cream → ? ← Drowning
```

**Collider:** A variable caused by both X and Y. Conditioning on a collider creates a spurious association (see Berkson's Paradox).
```
Talent → Hollywood success ← Attractiveness
```

**Mediator:** A variable on the causal path from X to Y. Controlling for a mediator removes the causal effect you're trying to measure.
```
Education → Income → Health
(controlling for income hides education's effect)
```

**Prevention:**
- Never claim causation from observational data without causal methodology
- Draw a causal DAG before analysis — identify confounders, colliders, mediators
- Use causal methods when causal claims are needed (see choosing-ds-modeling-approach skill)
- Report associations as "associated with" not "causes" or "leads to"
- Check for reverse causation: maybe Y causes X, not the other way around

**Detection:**
- Does the analysis claim causation? If so, what causal method was used?
- Are confounders identified and controlled for?
- Is feature importance being interpreted as causal effect?
- Has reverse causation been considered?
- Are there known third variables that could explain the association?

## Confirmation Bias

**What it is:** The tendency to search for, interpret, and remember information in a way that confirms pre-existing beliefs, while giving less attention to contradictory evidence.

**Red flag:** Only reporting analyses that match expectations. Discarding or not investigating unexpected results. "We found what we expected."

**Example:** A team believes their new recommendation algorithm is better. They run an A/B test and find: overall conversion is higher for the new algorithm (confirms belief), but return rates are also higher (disconfirms belief). They report only the conversion result.

**Prevention:**
- **Pre-register hypotheses:** Write down what you expect to find before analyzing data
- **Actively seek disconfirming evidence:** For every positive finding, explicitly look for counter-evidence
- **Report all results:** Include null results, negative results, and unexpected findings
- **Blinded analysis:** When possible, analyze data without knowing group labels
- **Red team your own analysis:** Assign someone to argue against the conclusions

**Detection:**
- Were hypotheses stated before or after data analysis?
- Are null/negative results reported?
- Were any analyses run but not reported?
- Does the narrative only include supporting evidence?
- Were alternative explanations seriously considered?

## Publication Bias

**What it is:** Positive/significant results are more likely to be published, shared, or acted upon, while negative/null results are suppressed. This creates a distorted view of evidence.

**Red flag:** "All studies show X works" — suspiciously uniform positive results. "Every A/B test we've run shows improvement."

**Example:** A company runs 20 A/B tests per quarter. Only the 5 "successful" ones are presented to leadership. Over time, leadership believes the team has a 100% success rate, when the actual rate is 25%.

**Prevention:**
- **Report all experiments:** Maintain a registry of all tests run, not just successful ones
- **Pre-register experiments:** Document hypotheses and analysis plans before running tests
- **Track the denominator:** Always report "X of Y tests showed significance"
- **Funnel plot analysis:** For meta-analyses, check for asymmetry indicating missing studies
- **Publish negative results:** Negative results are informative — they prevent others from wasting resources

**Detection:**
- Is the base rate of positive results suspiciously high? (e.g., >80% of experiments "succeed")
- Are there registries or logs of all experiments, not just reported ones?
- Do published effect sizes seem too consistent? (Real effects vary.)
- Funnel plot asymmetry: are small studies with null results missing?
- Ask: "How many experiments did you run to get this one result?"
