# Specification: Comprehensive Prompt Refactoring

## Problem Statement
The iflow plugin's 85 prompt files (28 commands, 29 skills, 28 agents) contain prompt anti-patterns — subjective adjectives, God Prompts, LLM-performed math, missing JSON schemas, inconsistent terminology, and suboptimal caching structure — that reduce prompt effectiveness and waste cache tokens.

## Success Criteria
- [ ] SC-1: All 85 prompt files score >= 80 on promptimize's 10-dimension rubric (9 existing + cache-friendliness; denominator 30). Measured against the updated rubric (see AC-1); SC-1 verification requires AC-1 completion first
- [ ] SC-2: Zero subjective adjectives in instruction text (defined boundary: SKILL.md core content, agent .md files, command .md files — excludes reference files, domain-specific technical terms, description frontmatter trigger phrases, code examples)
- [ ] SC-3: One documented terminology convention for Stage/Step/Phase with all files conforming
- [ ] SC-4: All reviewer dispatch prompts include explicit typed JSON return schema blocks
- [ ] SC-5: Zero non-trivial math delegated to LLM (non-trivial = division, multiplication, rounding, or aggregation over >5 items; additive integer counting with <=5 signals is permitted inline). Note: this refines PRD SC-5's blanket "zero math" to exclude trivial additive counting — rationale: 5-signal addition is deterministic for LLMs and extracting it to code adds complexity without reliability gain. The PRD is the input document; spec refinements like this are expected and the PRD is not updated retroactively
- [ ] SC-6: Zero God Prompt patterns (no single dispatch doing 4+ orthogonal tasks)
- [ ] SC-7: All command files structured for prompt caching (static templates top, dynamic injection bottom)
- [ ] SC-8: Enforcement gate exists (promptimize reminder on component edits)
- [ ] SC-9: validate.sh extended with at least one content-level check (subjective adjective grep)
- [ ] SC-10: All 28 agent files retain static-content-first ordering after adjective and terminology modifications (verified by diffing all 28 agent files pre/post-modification and confirming no static content moved below dynamic injection points)

## Scope

### In Scope
- Update scoring-rubric.md: add cache-friendliness as 10th dimension
- Update prompt-guidelines.md: fill 3 gaps (tool use prompting, system vs human turn placement, negative framing guidance)
- Update promptimize skill/command: support 10 dimensions, denominator 30
- Create batch-promptimize shell script for all 85 files with aggregate reporting
- Restructure 6 commands for prompt caching (specify, design, create-plan, create-tasks, implement, secretary)
- Restructure 3 skills for prompt caching (brainstorming, implementing, retrospecting)
- Note: these 9 files were selected because they interleave static content (reviewer templates, routing tables, schemas, rules) with dynamic content (user input, feature context); all other files already follow static-first ordering
- Add typed JSON return schemas to 2 reviewer dispatches (review-ds-code.md, review-ds-analysis.md)
- Fix 2 math-in-LLM violations (promptimize score calculation, secretary complexity scoring)
- Split 2 God Prompt commands into chained dispatches (review-ds-code, review-ds-analysis)
- Remove subjective adjectives from instruction text (~73 raw instances across 38 files; exact in-scope count after exclusion filtering TBD by batch audit)
- Fix passive voice instances (~12)
- Normalize Stage/Step/Phase terminology across all files
- Add promptimize reminder to component-authoring.md
- Add content-level check to validate.sh
- Document terminology convention in component-authoring.md

### Out of Scope
- Automated CI gate for promptimize scores
- Behavioral regression test harness for prompts
- Score history tracking over time
- Rewriting prompt logic or workflows (this is quality/clarity, not functionality)
- Hook shell scripts (bash, not prompt text)
- Multimodal prompting guidance (plugin doesn't use image inputs)
- Batch-promptimize git diff integration (auto-detect changed files)

## Acceptance Criteria

### AC-1: Scoring Rubric Update
- Given the scoring-rubric.md file
- When a developer opens it
- Then it contains 10 dimensions including "cache-friendliness" with these behavioral anchors:
  - Pass (3): All static content precedes all dynamic content with zero interleaving
  - Partial (2): Mostly separated but 1-2 static blocks appear after dynamic injection points
  - Fail (1): Static and dynamic content freely interleaved or no clear separation
- And both the promptimize skill (SKILL.md dimension list) and command (promptimize.md Step 4c validator + Step 5 score formula) are updated to support 10 dimensions with denominator 30

### AC-2: Prompt Guidelines Update
- Given the prompt-guidelines.md file
- When a developer reads it for authoring guidance
- Then it contains sections on tool use prompting, system vs human turn placement, and negative framing
- And each section has source citations from Anthropic documentation

### AC-3: Batch Promptimize Script
- Given the batch-promptimize shell script
- When invoked with no arguments
- Then it iterates all 85 component files (28 commands, 29 skills, 28 agents)
- And produces per-file scores and an aggregate summary report
- And flags files scoring below 80
- And completes without timeout errors when run with max 5 concurrent processes
- Non-functional note: target runtime <60 minutes on Claude Opus 4.6 via standard API; escalate if exceeded but not acceptance-gating due to external API latency variance

### AC-4: Prompt Caching Restructure
- Given 6 command files and 3 skill files identified for restructuring
- When each file is inspected
- Then all static content (reviewer templates, routing tables, schemas, rules) precedes all dynamic content (user input, feature context, iteration state)
- And file behavior is functionally identical: for the 5 pilot files, use the full AC-13 behavioral equivalence procedure; for remaining files not in the pilot set, verify via automated diff that (a) no lines were deleted or added (only moved), (b) all dynamic injection markers remain after all static content blocks, and (c) all named static sections (reviewer templates, routing tables, schemas, rules) are fully contained before the first dynamic injection marker

### AC-5: JSON Schema Addition
- Given review-ds-code.md and review-ds-analysis.md (command dispatch prompts, not agent files)
- When a reviewer dispatch prompt is sent
- Then the command dispatch prompt includes an explicit typed JSON return schema block (field names with types, not just field name lists)
- And the schema is consistent with (or references) any return format defined in the corresponding agent files (ds-code-reviewer.md, ds-analysis-reviewer.md)

### AC-6: Math-in-LLM Fix
- Given promptimize score calculation
- When scores are computed
- Then sum/divide/round operations execute in orchestrating code, not LLM generation
- Given secretary complexity scoring (5-signal additive integer counting)
- When complexity is assessed
- Then the LLM performs the additive counting inline (permitted under SC-5's trivial-math exception: <=5 signals, addition only, no division/rounding)
- And a code comment documents this exception with rationale

### AC-7: God Prompt Splits
Definition: An "orthogonal task" is a review axis that requires a distinct evaluation framework and whose findings do not depend on other axes.

- Given review-ds-code.md (5 review axes) and review-ds-analysis.md (4-5 review axes)
- When a review is invoked
- Then each command dispatches via chained calls instead of a single monolithic prompt
- And each chained call handles <= 3 orthogonal tasks
- Planned split for review-ds-code.md: Chain 1 [anti-patterns, pipeline quality, code standards], Chain 2 [notebook quality, API correctness], Chain 3 [synthesis of findings]
- Planned split for review-ds-analysis.md: Chain 1 [methodology, statistical validity, data quality], Chain 2 [conclusion validity, reproducibility], Chain 3 [synthesis of findings]
- Agent file approach: the existing agent files (ds-code-reviewer.md, ds-analysis-reviewer.md) are called multiple times with narrower scope per chain. No new agent files are created. The command file orchestrates the chaining; the agent file's system prompt is unchanged but each invocation receives a subset of review axes
- Subset scope override: each chain's dispatch prompt must include an explicit instruction ("Evaluate ONLY the following axes. Ignore all other review sections in your system prompt.") to prevent the agent's full system prompt from causing evaluation of out-of-scope axes
- Synthesis chain input contract: Chain 3 receives the structured JSON outputs from Chains 1 and 2 concatenated as context and synthesizes them into a single consolidated review object with the same schema as the current single-dispatch output. Chain 3 does not re-read the original files

### AC-8: Subjective Adjective Removal
- Given all 85 prompt files
- When grep searches for "appropriate|sufficient|robust|thorough|proper|adequate|reasonable" in instruction text
- Then zero matches are found (excluding reference files, domain-specific terms, code examples, description frontmatter)
- And each removed adjective is replaced with a measurable criterion
- Exclusion boundary for "domain-specific terms": statistical terminology used in data science review checklists where the adjective describes a domain concept (e.g., "sufficient sample size", "appropriate statistical test") rather than a vague quality instruction. Apply grep then manual filter using this boundary.
- Note: adjective replacements in agent files must preserve static-content-first ordering per SC-10. If a replacement introduces dynamic content, flag for manual review

### AC-9: Terminology Normalization
- Given the terminology convention: "Stage" for top-level divisions in skills, "Step" for sequential sections in commands and sub-items within stages, "Phase" exclusively for workflow-state phase names (brainstorm, specify, design, plan, tasks, implement, finish)
- When grep searches all 85 files plus READMEs
- Then all instances conform to the convention
- And hook scripts referencing phase names by string are verified unbroken

### AC-10: Passive Voice Fix
- Given all prompt files
- When batch-promptimize identifies passive voice instances
- Then all flagged instances are fixed to imperative mood ("Return JSON" not "JSON should be returned")
- Verification: promptimize's technique_currency dimension (which includes imperative mood as a sub-criterion) serves as the verifier; all files score Pass (3) on technique_currency after fixes

### AC-11: Enforcement Gate
- Given component-authoring.md
- When a developer follows the authoring checklist
- Then promptimize is listed as a required quality gate
- And a hookify rule file (`.claude/hookify.promptimize-reminder.local.md`) is created using the existing hookify plugin (`hookify:hookify` command) to emit an advisory reminder when component files are edited. Note: `.local.md` naming is intentional — this is a local-only advisory reminder (not committed to version control), consistent with the project convention where `.local.md` files are per-developer session configuration

### AC-12: Validate.sh Extension
- Given validate.sh
- When run
- Then it includes at least one content-level check (grep for subjective adjectives in component files)
- And fails with descriptive output if violations found

### AC-13: Five-File Pilot with Behavioral Verification
- Given 5 pilot files: design-reviewer.md, secretary.md, brainstorming/SKILL.md, review-ds-code.md, review-ds-analysis.md
- When refactored before the full batch
- Then before/after promptimize scores are recorded for each file
- And secretary.md routing is verified with 5+ representative prompts (confirm same agent selection)
- And behavioral equivalence is verified per this procedure:
  1. For each pilot file, identify 2-3 representative inputs (e.g., for review-ds-code: a clean notebook, a notebook with anti-patterns, a mixed-quality notebook)
  2. Run the pre-restructure version and capture outputs (approval status, issue count, issue categories)
  3. Run the post-restructure version with identical inputs
  4. Compare: same JSON structure, same approval decision, issue count within +/- 1, no new issue categories introduced, severity distribution must not shift more than 1 level for any individual issue (a blocker becoming a non-blocker or vice versa requires investigation)
  5. If any pilot file fails comparison, halt batch and investigate before proceeding

## Feasibility Assessment

### Assessment Approach
1. **First Principles** — Prompt text refactoring is well-understood; all changes are to markdown files with known structure
2. **Codebase Evidence** — Feature 032 (promptimize redesign) completed today with 2-phase grading/rewriting, providing the primary execution tool. All 85 target files exist and are accessible. validate.sh exists and is extensible.
3. **External Evidence** — Anthropic's Claude 4 best practices document the specific patterns to enforce. Source: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices

### Assessment
**Overall:** Confirmed
**Reasoning:** All target files exist (85 verified), the promptimize tool is operational (feature 032 completed), the scoring rubric and guidelines files exist and are editable, and validate.sh is extensible. The changes are text-level modifications to markdown files — no new infrastructure, APIs, or external dependencies. God Prompt splits and caching restructure require manual judgment but are technically straightforward.
**Key Assumptions:**
- Feature 032 promptimize redesign is complete and functional — Status: Verified at `docs/dev_artifacts/workitems/032-promptimize-skill-redesign/.meta.json` (status: completed)
- scoring-rubric.md is extensible with new dimensions — Status: Verified at `plugins/iflow/skills/promptimize/references/scoring-rubric.md` (exists)
- validate.sh supports adding new checks — Status: Verified at `validate.sh` (exists, extensible bash script)
- Batch-promptimize parallelization is feasible — Status: Verified (shell scripts can run background processes with `&` and `wait`)
**Open Risks:** God Prompt splits change dispatch contracts, which could break agent expectations if not manually verified. Secretary.md routing is text-pattern-dependent and could silently break from description changes.

## Dependencies
- Feature 032 (promptimize-skill-redesign): Must be complete — Status: COMPLETED
- Anthropic Claude 4 best practices documentation: Reference standard — Status: Available
- prompt-guidelines.md: Must exist — Status: EXISTS
- scoring-rubric.md: Must exist — Status: EXISTS

## Resolved Decisions
- **Terminology convention:** "Stage" for top-level skill divisions, "Step" for sequential sections in commands and sub-items within stages, "Phase" exclusively for workflow-state phase names. Reflected in AC-9.
- **Secretary complexity scoring:** Keep as LLM inline. 5-signal additive integer counting qualifies under the trivial-math exception (<=5 signals, addition only). Documented code comment required. Reflected in AC-6.
- **Batch-promptimize format:** Shell script. Native parallelism via `&` and `wait`, YOLO mode passed as argument, avoids recursive command-scoring-command issue. Reflected in AC-3.
