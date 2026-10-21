# Retrospective: Feature 009 - Harden Brainstorm Workflow

## Summary

Hardened the brainstorming skill to enforce verification and promotion gates, preventing the agent from skipping directly to implementation.

## What Went Well

- Clear problem statement from user experience (agent skipped phases)
- Incremental brainstorming with checkpoints
- Chain-reviewer caught design gaps (missing interface specs)
- Spec reviewer confirmed full compliance

## Learnings Captured

### Subagent Verification
Using subagents for review provides fresh perspective. The reviewing agent doesn't have context from creating the artifact, so it evaluates more objectively.

### AskUserQuestion Enforcement
Requiring specific tool usage (AskUserQuestion) creates a hard interaction point that cannot be skipped. Specifying exact tool syntax in skills makes compliance verifiable.

### PROHIBITED Sections
Explicit forbidden actions help guide LLM behavior. Listing what the agent MUST NOT do is as important as listing what it should do. Use strongest language (MUST NOT) for critical constraints.

## Metrics

- Phases completed: brainstorm → specify → design → plan → tasks → implement
- Review iterations: spec(1), design(2), tasks(2), implement(1)
- Files changed: 2 (skill + agent)

## Date

2026-01-31
