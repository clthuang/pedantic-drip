# Scoring Rubric

## Behavioral Anchors

| Dimension | Pass (3) | Partial (2) | Fail (1) |
|-----------|----------|-------------|----------|
| Structure compliance | Matches macro-structure for component type exactly | Missing 1-2 optional sections | Missing required sections or wrong structure |
| Token economy | Under budget (<500 lines, <5000 tokens) with no redundant content | Under budget but contains redundant content | Over budget |
| Description quality | Has trigger phrases, activation conditions, third person, specific | Missing some trigger conditions | Vague, first person, or missing |
| Persuasion strength | Uses 3+ persuasion principles effectively | Uses 1-2 principles or uses them weakly | No persuasion techniques |
| Technique currency | Uses current best practices (XML tags, positive framing, appropriate emphasis) | Uses some current practices, has minor outdated patterns | Uses outdated patterns (emphasis overuse, anti-laziness language) |
| Prohibition clarity | All constraints are specific, unambiguous, use definitive language | Some constraints vague or use weak language ("should", "try to") | No explicit constraints or constraints are contradictory |
| Example quality | 2+ concrete, minimal, representative examples | 1 example or examples are too long/generic | No examples (when component type expects them) |
| Progressive disclosure | SKILL.md is overview, details in references/ | Some detail in SKILL.md that could move to references/ | All content crammed in one file, no progressive disclosure |
| Context engineering | Tool restrictions appropriate, minimal context passing, clean boundaries | Minor context bloat or loose tool restrictions | Unrestricted tools, excessive context, unclear boundaries |
| Cache-friendliness | All static content precedes all dynamic content with zero interleaving | Mostly separated but 1-2 static blocks appear after dynamic injection points | Static and dynamic content freely interleaved or no clear separation |

## Component Type Applicability

| Dimension | Skill | Agent | Command | General |
|-----------|-------|-------|---------|---------|
| Structure compliance | Evaluated | Evaluated | Evaluated | Evaluated |
| Token economy | Evaluated | Evaluated | Evaluated | Evaluated |
| Description quality | Evaluated | Evaluated | Evaluated | Evaluated |
| Persuasion strength | Evaluated | Evaluated | Auto-pass | Evaluated |
| Technique currency | Evaluated | Evaluated | Evaluated | Evaluated |
| Prohibition clarity | Evaluated | Evaluated | Auto-pass | Evaluated |
| Example quality | Evaluated | Evaluated | Auto-pass | Evaluated |
| Progressive disclosure | Evaluated | Auto-pass | Auto-pass | Auto-pass |
| Context engineering | Evaluated | Evaluated | Evaluated | Evaluated |
| Cache-friendliness | Evaluated | Evaluated | Evaluated | Auto-pass |

Dimensions marked "Auto-pass" score 3 automatically for that component type.

## General Prompt Behavioral Anchors

> When `component_type` is `general`, use the behavioral anchors in this section instead of the standard anchors above for the dimensions listed below. All other dimensions use the standard anchors.

| Dimension | Pass (3) | Partial (2) | Fail (1) |
|-----------|----------|-------------|----------|
| Structure compliance | Clear sections with headers, logical flow, no wall of text | Some organization but missing headers or inconsistent grouping | No structure, single unbroken block of instructions |
| Token economy | Concise and proportional to task complexity, no redundant content | Some redundant or verbose content that could be trimmed | Significant redundancy, content vastly disproportionate to task |
| Description quality | Clear purpose statement, target use case, expected behavior defined | Some purpose stated but vague or incomplete | No purpose statement, unclear what the prompt does or when to use it |
| Context engineering | Clear input/output boundaries, appropriate context scoping, no unnecessary information | Some boundary issues or minor context bloat | No clear boundaries, excessive irrelevant context, undefined inputs/outputs |

> For general prompts, the Example quality dimension is context-dependent. Examples are expected when the prompt involves structured output, classification, or pattern-following tasks. For open-ended generation prompts, zero examples is acceptable: score Pass(3) if no examples are needed, Partial(2) if examples would help but are absent, Fail(1) only if the task clearly requires examples and none are provided.
