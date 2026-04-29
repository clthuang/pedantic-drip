---
name: designing
description: Creates design.md with architecture and contracts. Use when the user says 'design the architecture', 'create technical design', 'define interfaces', or 'plan the structure'.
---

# Design Phase

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Design the technical architecture.

## Prerequisites

- If `spec.md` exists: Read for requirements
- If not: Gather requirements from the user's request context. Design can run independently — the research stage (Stage 0) gathers context when earlier phases were skipped.

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Standard: Full process with optional verification
   - Full: Full process with required verification

## Stage Parameter

The design command may invoke this skill with a `stage` parameter to produce specific sections:

| Stage | Sections Produced | Use Case |
|-------|-------------------|----------|
| `architecture` | Architecture Overview, Components, Technical Decisions, Risks | First pass - structure and decisions |
| `interface` | Interfaces (detailed contracts) | Second pass - precise contracts |
| (none/default) | All sections | Backward compatibility |

When `stage=architecture`:
- Focus on high-level structure and component boundaries
- Define what each component does, not the precise API
- Identify technical decisions and risks early

When `stage=interface`:
- Read existing design.md for component definitions
- Add detailed interface contracts with exact formats
- Define error cases and edge cases precisely

When no stage specified:
- Produce complete design in one pass (existing behavior)

## Process

### 1. Architecture Overview

High-level design:
- Components involved
- How they interact
- Data flow

Keep it simple (KISS). One diagram if helpful.

### 2. Interface Definitions

For each component boundary:
- Input format
- Output format
- Error cases

Define contracts before implementation.

### 3. Technical Decisions

For significant choices:
- Decision
- Options considered
- Rationale

### 4. Risk Assessment

- What could go wrong?
- How do we mitigate?

### 5. Cross-File Invariants (when design spans 2+ files)

If the design moves or splits a single logical unit across multiple files (e.g. relocating a symbol, extracting a shared helper, threading a new parameter), explicitly enumerate the cross-file invariants up front. Common patterns:

| Invariant | Verification Pattern |
|-----------|---------------------|
| Atomic-commit (all N files must land in one commit) | AC asserting per-file `git log {base}..HEAD --format=%H -- {file}` returns same single non-empty hash across all files. Hash-equality is O(file-size), zero infrastructure, binary pass/fail. |
| Source-pin transparency (existing tests must continue passing post-relocation) | Determine whether existing source-pin tests use `inspect.getsource(method)` (insulated from module-level relocation — safe) vs `inspect.getsource(module)` (would break — requires coordinated test update). Enumerate which flavor is in use BEFORE the design lands. |
| Single source of truth (relocated symbol must remain identity-equal across imports) | Optional identity-pin test: `assert consumer_module._SYMBOL is producer_module._SYMBOL`. Guards against future local re-shadowing. |
| Circular-import ban (e.g. producer module must not import from consumer) | Grep AC: `grep -cE '^from {consumer_module}' {producer_module}` returns 0. |

Naming these invariants in the design phase reduces design-reviewer iteration churn for structural refactors. (Promoted from feature 096 retro Tune #1.)

## Output: design.md

Write to `{pd_artifacts_root}/features/{id}-{slug}/design.md`:

```markdown
# Design: {Feature Name}

## Prior Art Research

### Research Conducted
| Question | Source | Finding |
|----------|--------|---------|
| Similar pattern in codebase? | Grep/Read | {Yes at {location} / No} |
| Library support? | Context7 | {Yes: {method} / No} |
| Industry standard? | WebSearch | {Yes: {reference} / No} |

### Existing Solutions Evaluated
| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| {pattern} | {location} | {Adopted/Rejected because...} |

### Novel Work Justified
{Why existing doesn't fit, what we're reusing}

## Architecture Overview

{High-level description}

```
[Simple diagram if helpful]
```

## Components

### {Component 1}
- Purpose: {what it does}
- Inputs: {what it receives}
- Outputs: {what it produces}

### {Component 2}
...

## Interfaces

### {Interface 1}
```
Input:  {format}
Output: {format}
Errors: {error cases}
```

### {Interface 2}
...

## Technical Decisions

### {Decision 1}
- **Choice:** {what we decided}
- **Alternatives Considered:**
  1. {Alt A} — Rejected: {reason}
  2. {Alt B} — Rejected: {reason}
- **Trade-offs:** Pros: {benefits} | Cons: {accepted drawbacks}
- **Rationale:** {why, based on trade-off analysis}
- **Engineering Principle:** {KISS | YAGNI | DRY | Single Responsibility | etc.}
- **Evidence:** {Codebase: file:line | Documentation: URL | First Principles: reasoning}

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| {Risk 1} | {Impact} | {Mitigation} |

## Dependencies

- {Technical dependency}
```

## Self-Check

- [ ] KISS: Is this the simplest design that works?
- [ ] Interfaces defined before implementation?
- [ ] No over-engineering?
- [ ] Prior Art Research section completed?
- [ ] Each Technical Decision has evidence citation?

## Completion

"Design complete. Saved to design.md."
"Run /pd:show-status to check, or /pd:create-plan to continue."
