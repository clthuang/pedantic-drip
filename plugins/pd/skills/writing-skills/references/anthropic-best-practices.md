# Anthropic Skill Authoring Best Practices

Adapted from Anthropic's official documentation for skill development.

## Core Principles

### Concise Is Key

The context window is a shared resource. Your skill competes with:
- System prompt
- Conversation history
- Other skills' metadata
- The user's actual request

**Default assumption:** Claude is already very smart. Only add context Claude doesn't already have.

Challenge each piece of information:
- "Does Claude really need this explanation?"
- "Can I assume Claude knows this?"
- "Does this paragraph justify its token cost?"

**Good (50 tokens):**
```markdown
## Extract PDF text

Use pdfplumber:
```python
import pdfplumber
with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```
```

**Bad (150 tokens):**
```markdown
PDF (Portable Document Format) files are a common file format...
```

### Set Appropriate Degrees of Freedom

Match specificity to task fragility:

| Freedom Level | Use When | Example |
|---------------|----------|---------|
| **High** (text instructions) | Multiple approaches valid, context-dependent | Code review guidelines |
| **Medium** (pseudocode + params) | Preferred pattern exists, some variation OK | Report generation |
| **Low** (exact scripts) | Operations fragile, consistency critical | Database migrations |

**Analogy:**
- **Narrow bridge with cliffs:** One safe path. Give exact instructions.
- **Open field:** Many paths work. Give general direction.

## Skill Structure

### Naming Conventions

Use **gerund form** (verb + -ing):
- Good: "Processing PDFs", "Testing code", "Writing documentation"
- Avoid: "Helper", "Utils", "Tools", "Documents"

### Writing Effective Descriptions

**Always write in third person.** The description is injected into the system prompt.

- Good: "Processes Excel files and generates reports"
- Bad: "I can help you process Excel files"
- Bad: "You can use this to process Excel files"

**Include both what AND when:**
```yaml
description: Extract text and tables from PDF files. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

### Progressive Disclosure

SKILL.md serves as an overview pointing to detailed materials as needed.

**Keep SKILL.md under 500 lines.** Split content into separate files when approaching this limit.

**Directory structure:**
```
skill-name/
├── SKILL.md              # Main instructions (loaded when triggered)
├── references/           # Detailed guides (loaded as needed)
│   ├── advanced.md
│   └── api-reference.md
├── scripts/              # Utility scripts (executed, not loaded)
│   └── validate.py
└── examples/             # Usage examples (loaded as needed)
```

**Pattern: High-level guide with references:**
```markdown
## Quick start
[Basic usage here]

## Advanced features
- **Form filling**: See [references/forms.md](references/forms.md)
- **API reference**: See [references/api.md](references/api.md)
```

**Avoid deeply nested references.** Keep references one level deep from SKILL.md.

## Workflows and Feedback Loops

### Use Workflows for Complex Tasks

Break complex operations into clear, sequential steps. Provide a checklist:

```markdown
## Research synthesis workflow

Copy this checklist and track progress:

```
- [ ] Step 1: Read all source documents
- [ ] Step 2: Identify key themes
- [ ] Step 3: Cross-reference claims
- [ ] Step 4: Create structured summary
- [ ] Step 5: Verify citations
```
```

### Implement Feedback Loops

**Pattern:** Run validator -> fix errors -> repeat

```markdown
## Document editing process

1. Make edits to `document.xml`
2. **Validate immediately**: `python scripts/validate.py`
3. If validation fails:
   - Review error message
   - Fix issues
   - Run validation again
4. **Only proceed when validation passes**
```

## Content Guidelines

### Avoid Time-Sensitive Information

**Bad:**
```markdown
If you're doing this before August 2025, use the old API.
```

**Good:**
```markdown
## Current method
Use the v2 API endpoint.

## Old patterns
<details>
<summary>Legacy v1 API (deprecated)</summary>
[Historical context]
</details>
```

### Use Consistent Terminology

Choose one term and use it throughout:
- Always "API endpoint" (not "URL", "route", "path")
- Always "field" (not "box", "element", "control")

## Common Patterns

### Template Pattern

Provide templates for output format:

```markdown
## Report structure

ALWAYS use this exact template:

```markdown
# [Analysis Title]

## Executive summary
[One-paragraph overview]

## Key findings
- Finding 1 with data
- Finding 2 with data

## Recommendations
1. Actionable recommendation
```
```

### Examples Pattern

Provide input/output pairs:

```markdown
## Commit message format

**Example 1:**
Input: Added user authentication with JWT tokens
Output:
```
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware
```
```

### Conditional Workflow Pattern

Guide through decision points:

```markdown
## Document modification

1. Determine modification type:
   **Creating new?** -> Follow "Creation workflow"
   **Editing existing?** -> Follow "Editing workflow"
```

## Evaluation and Iteration

### Build Evaluations First

Create evaluations BEFORE writing documentation. This ensures your skill solves real problems.

**Evaluation-driven development:**
1. **Identify gaps**: Run Claude on tasks without skill. Document failures.
2. **Create evaluations**: Build 3+ scenarios testing these gaps.
3. **Establish baseline**: Measure performance without skill.
4. **Write minimal instructions**: Just enough to pass evaluations.
5. **Iterate**: Execute evaluations, compare, refine.

### Develop Skills Iteratively with Claude

Work with Claude A (expert) to create skills used by Claude B (agent):

1. **Complete task without skill** - notice what context you provide
2. **Identify reusable pattern** - what would help future tasks?
3. **Ask Claude A to create skill** - it understands the format natively
4. **Review for conciseness** - remove unnecessary explanations
5. **Test with Claude B** - observe real behavior
6. **Iterate based on observation** - fix gaps found in testing

## Checklist for Effective Skills

### Core Quality
- [ ] Description is specific with key terms
- [ ] Description includes what AND when
- [ ] SKILL.md under 500 lines
- [ ] Additional details in separate files
- [ ] No time-sensitive information
- [ ] Consistent terminology
- [ ] Concrete examples (not abstract)
- [ ] File references one level deep
- [ ] Workflows have clear steps

### Code and Scripts
- [ ] Scripts solve problems (don't punt to Claude)
- [ ] Error handling is explicit
- [ ] No magic constants
- [ ] Required packages listed
- [ ] Validation steps for critical operations
- [ ] Feedback loops for quality-critical tasks

### Testing
- [ ] At least 3 evaluations created
- [ ] Tested with pressure scenarios
- [ ] Team feedback incorporated
