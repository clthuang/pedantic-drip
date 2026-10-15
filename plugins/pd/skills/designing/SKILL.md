---
name: designing
description: The Contracts stage's playbook — shape.md ## Design with its Architecture diagram, one contract block per module and the Test strategy, reviewed by the review call. Use when a feature is in phase design, or when writing or reviewing `## Design`.
---

# Designing

The Contracts stage (`phase: design`) removes one unknown: what crosses each boundary? It hands down `shape.md` `## Design`: documents only, no code. Shared mechanics: the `workflow-transitions` skill.

## Steps

1. **Phase entry** per `workflow-transitions`.
2. **Ground it:** dispatch `codebase-explorer` for the modules, patterns and callers the change touches. Its report is claims; check the ones the design rests on at file:line.
3. **Write `## Design`** in `shape.md` under the existing `## Requirements`, using `${CLAUDE_PLUGIN_ROOT}/templates/shape.md`. The bar is the checklist below.
4. **Review:** the review call per `${CLAUDE_PLUGIN_ROOT}/references/review-call.md`, with this skill's `## Review checklist` inline, given `shape.md`, read access to the code, and the open assumptions from `pd-status <id>`. Up to three review-revise cycles:
   - **revise** for each blocker; a finding you can refute at file:line gets a `Rejects:` line instead, and only the user accepts it;
   - **re-review scoped** to the earlier findings and the edit that answered them (`pd-review-filter --range <reviewed commit>..HEAD` drops new findings outside the edit);
   - **the loop ends** at the first pass with no blocker, whatever its warnings say. Still open after the third: a `capped` entry, then ask the user.
5. **Exit check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh design <feature dir>` (`## Design`, its mermaid diagram, `### Test strategy`, no duplicate contract block). Then phase exit per `workflow-transitions` (`phase design -> create-plan`).

**Entries this stage writes:** `review` (one per review call, with every finding as an issue line), `decision` (each user ruling, each accepted rejection), `capped` (at the cap), `phase`.

**Small mode** (`mode: small`): write `## Design` and `plan.md` in one sitting, then make one joint review call carrying this checklist and the `planning` skill's, over both artifacts; its cycles count once. Both phases are still recorded: run this stage's exit check and append `phase design -> create-plan`, then finish with the `planning` skill's exit.

## Review checklist

- **Architecture:** `### Architecture` holds one `mermaid` block of the modules, the data flowing between them, and a contract name on each edge. Every edge carries a contract and every contract sits on an edge; an edge without one is an unpinned seam. The diagram never restates a signature. Even a one-module change draws its module and its callers.
- **Contracts pinned once:** under `### Contracts`, one code block per module: its `modules:` line first (the paths it owns), then its interface (signatures, payload shapes, event names, config keys, migration steps), its errors and its invariants. Every interface appears in exactly one code block across `shape.md` and `plan.md`; prose links to it.
- **The expectations are reachable:** each `B<n>` in `## Requirements` is produced by some module's contract, through the contract surface a test can call.
- **Decisions with rationale:** per choice, what was decided, the alternatives rejected and why, the principle it serves (KISS, YAGNI, DRY, single responsibility), and its evidence: file:line, a documentation URL, or first-principles reasoning. A choice with no rejected alternative is a description, not a decision.
- **Risks with mitigations:** a table of risk, blast radius and mitigation. A design spanning two or more files names its cross-file invariants (atomic commit, identity after a symbol moves, no new import cycle), each with the command that proves it.
- **Test strategy:** `### Test strategy` names the runner with its JUnit option (pytest `--junitxml=PATH`), where fixtures live, each fake and what it stands in for, and which real resources tests may touch (none unless named). A new code path beside an existing fallback needs a test asserting a fact true only on the new path; "no exception raised" holds on the fallback too.
- **No code:** the design is semantic and contract-level; nothing under the source paths changes in this stage.
- **Assumptions checked:** each open assumption handed in is confirmed or flagged, with file:line.
