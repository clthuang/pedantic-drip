---
name: promptimize
description: Reviews prompts against best practices guidelines and returns scored assessment with improved version. Use when user says 'review this prompt', 'improve this skill', 'optimize this agent', 'optimize this prompt', 'promptimize', or 'check prompt quality'.
---

# Promptimize

Review and improve prompts using structured scoring and best practices. Supports plugin components (skills, agents, commands), general prompt files, and inline prompt text.

## Process

### Step 1: Detect component type

Identify the component type from the input path using **suffix-based matching** (the path CONTAINS the pattern, not an exact glob match -- this handles both absolute dev-workspace paths and cache paths):

| Path suffix pattern | Component type |
|---------------------|----------------|
| `skills/<name>/SKILL.md` | skill |
| `agents/<name>.md` | agent |
| `commands/<name>.md` | command |
| *(no match)* | general |

Match rules:
1. Check if path contains `skills/` followed by a directory name and `/SKILL.md` --> type = **skill**
2. Check if path contains `agents/` followed by a filename ending in `.md` --> type = **agent**
3. Check if path contains `commands/` followed by a filename ending in `.md` --> type = **command**
4. No match --> type = **general**. Additionally, if the path contains `plugins/` or keywords `skills`, `agents`, `commands` but didn't match the exact suffix patterns above, set `near_miss_warning = true` and `near_miss_message` to: "Path contains plugin-like segments but did not match any component pattern. Classified as general prompt."

### Step 2: Load references

Load three files using two-location Glob (try primary cache path first, fall back to dev workspace).

**2a. Scoring rubric**

- Primary: `~/.claude/plugins/cache/*/pd*/*/skills/promptimize/references/scoring-rubric.md`
- Fallback (dev workspace): `plugins/*/skills/promptimize/references/scoring-rubric.md`

**2b. Prompt guidelines**

- Primary: `~/.claude/plugins/cache/*/pd*/*/skills/promptimize/references/prompt-guidelines.md`
- Fallback (dev workspace): `plugins/*/skills/promptimize/references/prompt-guidelines.md`

**2c. Target file**

Read the file at the input path directly (absolute path provided by caller). Retain the full content in memory as `target_content` -- needed by Stage 2 as rewrite context.

**Error handling:** If any reference file is not found after both Glob locations --> display error: "Required reference file not found: {filename}. Verify plugin installation." --> **STOP**

### Step 3: Check staleness

1. Parse the `## Last Updated: YYYY-MM-DD` heading from the prompt guidelines file
2. If the heading is missing or the date fails to parse, set `staleness_warning = true` with displayed date "unknown"
3. Compare the parsed date against today's date
4. If the date is **more than 30 days old**, set `staleness_warning = true`
5. This flag is included in the Stage 1 JSON output for the command to use in the report

### Stage 1: Grade

Evaluate all 10 dimensions against `references/scoring-rubric.md` (loaded in Step 2). For each dimension, apply the behavioral anchors to the target file and assign a score: **pass (3) / partial (2) / fail (1)**.

**Auto-pass exceptions:** Score 3 for any dimension marked "Auto-pass" in the Component Type Applicability table in `references/scoring-rubric.md`. For auto-passed dimensions, set `auto_passed = true`, `finding` to a brief note (e.g., "Auto-pass for {component_type}"), and `suggestion = null`.

For `general` component type, refer to the General Prompt Behavioral Anchors section in the scoring rubric for adapted criteria on structure compliance, token economy, description quality, and context engineering, plus a contextual note on example quality.

**Dimensions** (evaluate in this order):

1. **Structure compliance** -- matches macro-structure for component type
2. **Token economy** -- under budget with no redundant content
3. **Description quality** -- trigger phrases, activation conditions, specificity
4. **Persuasion strength** -- uses persuasion principles effectively
5. **Technique currency** -- current best practices, no outdated patterns
6. **Prohibition clarity** -- specific, unambiguous constraints
7. **Example quality** -- concrete, minimal, representative examples
8. **Progressive disclosure** -- overview in main file, details in references
9. **Context engineering** -- required tool restrictions, clean boundaries
10. **Cache friendliness** -- static content precedes dynamic content, no interleaving

For each evaluated dimension, record:
- **score**: integer 1, 2, or 3
- **finding**: one-line observation of what was assessed
- **suggestion**: what to improve (required when score < 3; null when score = 3)

Do NOT compute an overall score. Output only the raw dimension scores.

**Canonical dimension name mapping** -- use these exact JSON `name` values in the output:

| Rubric Name | JSON `name` Value |
|---|---|
| Structure compliance | `structure_compliance` |
| Token economy | `token_economy` |
| Description quality | `description_quality` |
| Persuasion strength | `persuasion_strength` |
| Technique currency | `technique_currency` |
| Prohibition clarity | `prohibition_clarity` |
| Example quality | `example_quality` |
| Progressive disclosure | `progressive_disclosure` |
| Context engineering | `context_engineering` |
| Cache friendliness | `cache_friendliness` |

**Output:** Wrap the JSON result in `<phase1_output>` tags:

```
<phase1_output>
{
  "file": "path/to/target.md",
  "component_type": "skill",
  "guidelines_date": "2026-02-24",
  "staleness_warning": false,
  "dimensions": [
    {
      "name": "structure_compliance",
      "score": 3,
      "finding": "Matches macro-structure exactly",
      "suggestion": null,
      "auto_passed": false
    }
  ]
}
</phase1_output>
```

Valid `component_type` values: `"skill"`, `"agent"`, `"command"`, `"general"`.

Optional fields: `near_miss_warning` (boolean, defaults to false when omitted) and `near_miss_message` (string, only present when `near_miss_warning` is true). Step 4c validation does not check these.

Populate `guidelines_date` and `staleness_warning` from Step 3. The `dimensions` array must contain exactly 10 entries, one per dimension in the order listed above.

### Stage 2: Rewrite

Using the Stage 1 grading result as context, rewrite the full target file incorporating improvements for every dimension scoring **partial or fail**.

**Step 1:** Wrap the Stage 1 JSON output from above in a `<grading_result>` block as context for the rewrite:

```
<grading_result>
{Stage 1 JSON output}
</grading_result>
```

**Step 2:** Generate the complete rewritten file. The output is a full copy of the target file with modified regions wrapped in `<change>` XML tags.

**Change tag format:**

```xml
<change dimension="token_economy" rationale="Remove redundant preamble">
modified content here
</change>
```

Attribute order is fixed: `dimension`, then `rationale`. Do not reorder.

**Tag rules:**

- **Pass dimensions (score=3):** Do NOT add `<change>` tags. Their content remains unchanged from the original.
- **Multi-region changes** for one dimension: each region gets its own `<change>` tag with the same `dimension` attribute.
- **Overlapping dimensions** (two dimensions modify the same text): use comma-separated dimension names: `<change dimension="token_economy,structure_compliance" rationale="Combined fix">`.
- **Preservation:** All text outside `<change>` tags must be identical to the original file (`target_content` from Step 2c). Do not modify whitespace, formatting, or content outside change blocks.

**Example** (two change blocks with an unchanged pass-dimension region between):

```
<change dimension="token_economy" rationale="Remove redundant preamble">
You are a code reviewer focused on quality.
</change>

## Process

<change dimension="structure_compliance" rationale="Add numbered steps with bold semantic labels">
1. **Read** -- Load the target file
2. **Analyze** -- Check against criteria
</change>
```

**Output:** Wrap the complete rewritten file in `<phase2_output>` tags:

```
<phase2_output>
{complete rewritten file with <change> tags}
</phase2_output>
```

## PROHIBITED

- NEVER score a dimension without referencing the behavioral anchors from `references/scoring-rubric.md`. Do not invent scoring criteria.

