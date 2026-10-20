# Candid Feedback Report: The Design of `promptimize`

This report provides a critical and constructive analysis of the `promptimize` command and its underlying skill (`plugins/iflow/skills/promptimize/SKILL.md`), evaluated strictly against Anthropic's official [Claude Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).

Overall, the *intent* of `promptimize`—to enforce prompt engineering standards automatically using progressive disclosure—is excellent. However, its *execution design* violates several core Anthropic recommendations, particularly regarding prompt chaining, parser formatting, and tool orchestration.

---

## 1. The "God Prompt" Anti-Pattern (Violation of Prompt Chaining)

**Current Design:** 
Step 4 (Evaluate 9 dimensions), Step 5 (Calculate score), Step 6 (Generate improved version), and Step 7 (Generate report) are all executed in a single, massive LLM pass. The model is asked to read references, evaluate 9 complex rubrics, calculate a mathematical score, rewrite the entire file injecting HTML comments, and format a markdown report all at once.

**Anthropic Best Practice Violated:** [Chain complex prompts](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#chain-complex-prompts) & [Overthinking and excessive thoroughness](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#overthinking-and-excessive-thoroughness)

**Candid Feedback:**
This is a classic "God Prompt." Asking an LLM (even Opus 4.6) to perform deeply analytical grading *and* complex conditional text generation (rewriting a file while injecting markers) in one sequential generation invites severe hallucination and context degradation. The model will likely start cutting corners on the rewrite because it spent its token budget thinking about the 9-dimension rubric.

**Constructive Refactoring Proposal:**
Break this into two explicit, chained API calls (or Agent delegations):
1.  **The Grader Call:** Evaluate the 9 dimensions and output *only* the JSON report with scores, findings, and suggestions.
2.  **The Rewriter Call:** Take the Grader's JSON output as a `<context>` input and execute the rewrite.

---

## 2. Using HTML Comments instead of XML Tags

**Current Design (Step 6):**
The skill explicitly instructs the model to use HTML comments to demarcate changed regions:
```markdown
<!-- CHANGE: {dimension} - {rationale} -->
{modified content}
<!-- END CHANGE -->
```

**Anthropic Best Practice Violated:** [Structure prompts with XML tags](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#structure-prompts-with-xml-tags)

**Candid Feedback:**
Anthropic models are explicitly fine-tuned to parse and generate `<xml>` tags flawlessly. While HTML comments `<!-- -->` technically work, they are not the native language of the model's structural attention mechanisms. Furthermore, Step 8 relies on a complex text-parsing "Merge algorithm" to rip these HTML comments out, which is brittle.

**Constructive Refactoring Proposal:**
Use XML tags. Not only is this native to Claude, but it allows for robust, native parsing in the orchestration layer (the `xml.etree.ElementTree` equivalent in whatever runner parses the response).
```xml
<change dimension="token_economy" rationale="Remove redundant preamble">
You are a code reviewer focused on quality.
</change>
```

---

## 3. Mathematical Operations in LLM

**Current Design (Step 5):**
The skill asks the LLM to calculate the score: `Overall score = (sum of all 9 dimension scores) / 27 x 100, rounded to nearest integer.`

**Anthropic Best Practice Violated:** *Use tools for deterministic tasks* (Implicit in the Tool Use guidelines).

**Candid Feedback:**
LLMs are notoriously unreliable at deterministic mathematics. Asking the model to sum 9 numbers, divide by 27, multiply by 100, and round is dangerous. Even if it gets it right 90% of the time, the 10% failure rate will break the UX.

**Constructive Refactoring Proposal:**
The LLM should only output the raw scores for the 9 dimensions in a structured JSON schema. The orchestrating script/command should execute the high-school math `(sum / 27 * 100)` to render the final report to the user.

---

## 4. The "Accept Some" Merge Algorithm is Brittle

**Current Design (Step 8):**
The "Accept some" logic asks the system to take an AI-generated rewritten file, find `<!-- CHANGE -->` markers, and surgically swap unselected blocks back to the original text using string replacement.

**Anthropic Best Practice Violated:** [Minimize hallucinations in agentic coding](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#minimizing-hallucinations-in-agentic-coding) & *General system robustness*.

**Candid Feedback:**
This is highly risky. If the LLM misses a closing `<!-- END CHANGE -->` marker, or if an overlapping line change misaligns the string-replace index against the `original_content`, the entire file will be corrupted. Text-replacement algorithms relying on LLM-generated boundary markers are historically brittle.

**Constructive Refactoring Proposal:**
If partial acceptance is a strict requirement, the model should not generate a fully merged file. It should generate standard diffs or patches (using a standard diff format) for each dimension. The system can then apply the selected patches sequentially using standard `patch` utilities, which are designed to handle context line matching and rejection gracefully.

---

## Executive Summary

To align `promptimize` with Anthropic's standard of excellence:
1.  **Decompose the God Prompt** into a "Grader" and a "Rewriter".
2.  **Switch from HTML to XML** for structural markers (`<change>`).
3.  **Remove math** from the LLM's responsibilities.
4.  **Use standard diffs** instead of custom string-replacement logic for partial file updates.
