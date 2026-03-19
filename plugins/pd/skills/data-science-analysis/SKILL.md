---
name: data-science-analysis
description: "Applies data science frameworks to enrich brainstorm PRDs with methodology assessment, pitfall analysis, and modeling approach recommendations. Use when brainstorming skill loads the data science domain in Stage 1 Step 10."
---

# Data Science Analysis

Apply data science frameworks from reference files to the concept, producing a structured analysis for PRD insertion. This skill is invoked by the brainstorming skill (Stage 1, Step 10) — not standalone.

## Input

From the brainstorming Stage 1 context:
- **problem_statement** — the data science concept from Step 1 item 1
- **target_user** — target audience from Step 1 item 2
- **success_criteria** — from Step 1 item 3
- **constraints** — known limitations from Step 1 item 4

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

Generate the Data Science Analysis section and domain review criteria list per the Output section below.

## Output

Return a `## Data Science Analysis` section with 4 subsections for PRD insertion:

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

Also return the domain review criteria list:

```
Domain Review Criteria:
- Methodology type identified and justified?
- Data requirements specified with quality concerns?
- Relevant pitfalls identified with mitigations?
- Modeling approach matched to problem type?
```

Insert the Data Science Analysis section in the PRD between `## Structured Analysis` and `## Review History`. If `## Structured Analysis` is absent, place after `## Research Summary` and before `## Review History`.

## Stage 2 Research Context

When this domain is active, append these lines to the internet-researcher dispatch:
- Research current best practices for the data science methodology relevant to this concept
- Evaluate data availability and quality for the problem domain
- Research common pitfalls and failure modes in similar analyses
- Find benchmark datasets or baseline results for comparison
- Include current library/tool recommendations for the chosen approach

## Graceful Degradation

If reference files are partially available:
1. Produce analysis from loaded files only — omit fields whose source file is missing
2. Warn about each missing file: "Reference {filename} not found, skipping {affected fields}"
3. The analysis section will be partial but still useful

If ALL reference files are missing:
1. Warn: "No reference files found, skipping domain enrichment"
2. STOP — do not produce a Data Science Analysis section
