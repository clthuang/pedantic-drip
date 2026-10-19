---
name: data-science-analysis
description: "Assesses a data science idea or planned analysis: problem type, data requirements, pitfall risks and modeling approach. Use when the user asks for a data science assessment of a concept; inside a brainstorm, the data-science advisor reads the same reference."
---

# Data Science Analysis

Apply the frameworks in the reference file to the concept the user names and return the analysis below. Inside a brainstorm, brainstorming's `data-science` advisor reads the same file; this skill is the standalone path.

## Input

From the request: the concept, its users, its success criteria and its constraints. Ask for any that is missing.

## Process

### 1. Read Reference Files

Read each reference file via Read tool. Each file is optional — warn and continue if missing.

- [ds-prd-enrichment.md](references/ds-prd-enrichment.md) — PRD analysis guidance for methodology, data requirements, pitfalls, and modeling

See Graceful Degradation for missing-file behavior.

### 2. Apply Frameworks to Concept

Using loaded reference content, analyze the concept across four dimensions:
1. **Methodology Assessment** — Predictive vs causal, experimental design considerations, validated methods
2. **Data Requirements** — Sources, volume, quality needs, collection challenges, privacy/ethical considerations
3. **Key Pitfall Risks** — Which of the 15 common pitfalls (from spotting-ds-analysis-pitfalls skill) apply to this concept
4. **Modeling Approach Recommendation** — Specific methods and frameworks suited to the problem

### 3. Produce Output

Generate the Data Science Analysis section per the Output section below.

## Output

Return a `## Data Science Analysis` section with 4 subsections:

```markdown
## Data Science Analysis

### Methodology Assessment
- **Problem Type:** {predictive / causal / descriptive / prescriptive}
- **Experimental Design:** {RCT feasible? Quasi-experimental alternatives? Observational only?}
- **Statistical Framework:** {frequentist / Bayesian / both, with justification}
- **Key Assumptions:** {distributional, independence, stationarity — which apply and which are risky}

### Data Requirements
- **Data Sources:** {what data is needed, where it comes from}
- **Volume Estimate:** {approximate rows/features needed for reliable results}
- **Quality Concerns:** {missing data patterns, measurement error, label quality}
- **Collection Pitfalls:** {sampling bias risks, selection effects in data collection}
- **Privacy/Ethics:** {PII handling, consent requirements, fairness considerations}

### Key Pitfall Risks
- **High Risk:** {pitfalls most likely to affect this concept, with brief explanation}
- **Medium Risk:** {pitfalls that could apply under certain conditions}
- **Mitigations:** {specific steps to prevent the identified pitfalls}

### Modeling Approach Recommendation
- **Recommended Method:** {specific method(s) with justification}
- **Alternatives:** {backup approaches if primary method isn't feasible}
- **Evaluation Strategy:** {metrics, validation approach, baseline comparison}
- **Production Considerations:** {monitoring, drift detection, retraining cadence}
```

In a brainstorm PRD, the section goes under Strategic Analysis, as the `data-science` advisor's subsection.

## Graceful Degradation

If reference files are partially available:
1. Produce analysis from loaded files only — omit fields whose source file is missing
2. Warn about each missing file: "Reference {filename} not found, skipping {affected fields}"
3. The analysis section will be partial but still useful

If ALL reference files are missing:
1. Warn: "No reference files found, skipping domain enrichment"
2. STOP — do not produce a Data Science Analysis section
