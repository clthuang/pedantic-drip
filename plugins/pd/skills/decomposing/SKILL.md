---
name: decomposing
description: Contract for decomposing a project PRD into modules and planned features. Use when creating a project from a PRD.
---

# Decomposing

**Input:** a project PRD, its project directory, and its `project_uuid` (returned by `init_project_state`, the project's one registrar).
**Output:** planned feature entities in the workflow engine, and `roadmap.md` beside the PRD.

1. **Decompose.** Dispatch `pd:project-decomposer`. Every PRD requirement maps to at least one feature; each feature is a vertical slice with end-to-end value; module boundaries follow functional domains; cross-feature dependencies are minimised.

2. **Review.** Dispatch `pd:project-decomposition-reviewer` in fresh context. One pass → at most one fix round → remaining issues go to the user.

3. **Allocate identity.** Per feature, in module order, call `allocate_entity_id(entity_type="feature", name=...)`. The returned `entity_id` IS `{id}-{slug}` — atomic and workspace-scoped — and the returned `seq` and `slug` are what registration takes. Never derive a slug locally or scan the filesystem for the next number: a local slug diverges on truncation and silently breaks the remap below. An error envelope stops the run; there is no fallback.

4. **Remap dependencies** from human-readable names to allocated ids, in the feature graph and every milestone list.

5. **Order.** Topologically sort by dependency — `tsort` reports cycles natively. A cycle goes to the user before anything is created.

6. **Approve.** Present feature count, module count, execution order, and any cycle. Cancelling creates nothing.

7. **Register.** Create each feature with `register_entity(entity_type="feature", seq=<allocated seq>, slug="<allocated slug>", name=..., status="planned", parent_uuid=<project_uuid>)` — never `auto_id`, which allocates a second number and breaks the remap — with dependencies recorded as entity relations — not as prose in a document. A registration error stops the run.

8. **Write `roadmap.md`:** dependency graph, execution order, milestones, cross-cutting concerns — a projection of those relations, not a second source of truth.
