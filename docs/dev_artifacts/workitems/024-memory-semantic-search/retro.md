# Retrospective: 024-memory-semantic-search

## AORTA Analysis

### Achievements

**Delivered:**
- Semantic memory system with Gemini embeddings (768d, L2-normalized)
- Hybrid scoring: 0.5*vector + 0.2*bm25 + 0.3*prominence
- SQLite-backed storage with FTS5 keyword search and WAL mode
- Two-phase import (fast insert + retro embedding batches)
- MCP server integration
- Comprehensive test suite: 423 passing tests across 6 test files
- 33 commits, 44 files changed, 17,039 insertions

**Technical Highlights:**
- NormalizingWrapper for embedding L2 normalization
- JSON-stripping FTS5 REPLACE triggers for clean tokenization
- BEGIN IMMEDIATE for atomic upserts
- SkipKeywordGenerator as CI fallback
- sys.path manipulation for entry point isolation

**Process Resilience:**
- Absorbed mid-phase spec rework (FTS5-only → embeddings-first) without downstream breakage
- Implementation converged efficiently (4 iterations, 3 reviewers)
- Circuit breaker handoff pattern worked: design review cap → handoff resolved 7 notes in 4 iterations

---

### Obstacles

**Iteration Cap Hits (3 phases):**
1. **Design review:** 5 iterations, 7 unresolved notes → handoff review resolved in 4 iterations
2. **Plan review (stage 1):** 5 iterations, 2 notes carried forward, most feedback "no change needed"
3. **Task review (stage 1):** 5 iterations → stage 2 clean approval in 3 iterations

**Root Causes:**
- **Reviewer fatigue:** False positive rate increased in later iterations, re-flagging accepted items
- **Subjective feedback accumulation:** Most common categories (assumptions, completeness, testability) are inherently subjective
- **Warning-only iterations:** Plan review repeatedly found warnings but said "no change needed," inflating iteration count without artifact changes

**Spec Rework:**
- Mid-phase pivot from FTS5-only to embeddings-first required 7 total specify iterations (5+2)
- Fundamental requirement change absorbed gracefully, but iteration count suggests need for explicit "rework checkpoint"

---

### Reflections

**What Worked:**
1. **Handoff review as circuit-breaker recovery** — Fresh reviewer perspective resolved stalled design review quickly (7 notes in 4 iterations vs. original reviewer hitting cap)
2. **Multi-stage review pattern** — Task and plan reviews had stage 2 that allowed clean convergence after stage 1 caps
3. **Implementation review convergence** — 3-reviewer loop achieved consensus at iteration 4, suggesting clear acceptance criteria and well-scoped feedback

**What Didn't:**
1. **Iteration caps count advisory feedback** — "No change needed" warnings inflated iteration counts without improving artifacts
2. **Reviewer context loss** — Re-flagging accepted items in iterations 4-5 indicates reviewers lack visibility into decision history
3. **No mid-phase rework checkpoints** — Spec rework discovered organically; explicit "pivot or continue?" decision point at iteration 3 might reduce false iterations

**Surprising:**
- Handoff reviewers consistently found issues design reviewers missed, yet resolved their own findings faster
- Mid-phase spec rework didn't cascade failure to downstream phases
- Implementation review (4 iterations) more efficient than upstream reviews despite 3-reviewer complexity

---

### Takeaways

**High-Confidence Learnings:**
1. **Reviewer rotation at iteration 3-4** accelerates convergence for complex phases
2. **Warning-only iterations should not count toward cap** — distinguish blocking issues from advisory notes
3. **Decision history must be visible to reviewers** — re-flagging accepted items is a context problem
4. **Mid-phase requirement pivots are recoverable** — fundamental changes can be absorbed if upstream artifact is reworked cleanly

---

### Actions

**Immediate (High Confidence):**
1. **Tune reviewer instructions** to distinguish blocking issues (count toward cap) from advisory notes (do not count)
2. **Introduce reviewer rotation trigger** at iteration 3-4 for phases with >3 unresolved notes
3. **Add decision log to artifacts** to track accepted/rejected feedback and reduce re-flagging

**Exploratory (Medium Confidence):**
4. **Formalize "requirement pivot" checkpoint** at specify iteration 3
5. **Analyze implementation reviewer prompts** for convergence patterns transferable to upstream reviews

---

## Knowledge Bank Updates

### Patterns
1. **Handoff review as circuit-breaker recovery:** When review phase hits iteration cap with unresolved notes, handoff to fresh reviewer often resolves quickly
2. **Mid-phase requirement pivots are recoverable:** Fundamental spec changes don't cascade failure if upstream artifact is reworked cleanly

### Anti-Patterns
1. **Warning-only iterations against cap:** Reviewer feedback that says "warning but no change needed" should not count toward iteration cap
2. **Late-iteration re-flagging:** Reviewers re-raising previously accepted items signals reviewer fatigue, not spec regression

### Heuristics
1. **If iteration 3+ has mostly warnings with "no change needed," rotate reviewer or skip to next phase**

---

## Raw Data

**Feature:** 024-memory-semantic-search
**Mode:** Standard
**Branch:** feature/024-memory-semantic-search
**Total review iterations:** ~37 across all phases
**Circuit breaker hits:** 3 (design review, plan stage 1, task stage 1)
**Git stats:** 33 commits, 44 files changed, 17,039 insertions, 9 deletions
**Test coverage:** 423 passing tests, 5 MCP tests deselected
**Created:** 2026-02-20T10:00:00Z
