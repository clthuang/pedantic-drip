---
description: Create a project from a PRD and decompose it into features
argument-hint: "--prd=<path>"
---

# /pd:create-project

**Purpose:** turn a PRD into a project entity plus its planned feature entities.

**Inputs:** `--prd=<path>`, from `/pd:brainstorm` or standalone. Missing → ask for it.

**Output:** `project:P{NNN}` entity, `{pd_artifacts_root}/projects/P{NNN}-{slug}/prd.md`, and the planned feature entities the decomposing skill registers.

**Steps:**
1. PRD must exist and exceed 100 bytes. Otherwise stop.
2. Slug from the PRD's first heading — lowercase, non-alphanumerics to hyphens, 30 chars, no trailing hyphen.
3. **Allocate atomically:** `allocate_entity_id(entity_type="project", name="{slug}")`. Build `P{NNN}` from the returned `seq` zero-padded to 3 digits and discard the response's `entity_id` field — projects use the `P{NNN}` shape. The `sequences` table is the only source of the next number: **never scan the filesystem for `P{NNN}-*` directories**, on any path.
4. **Two hard stops, both creating nothing:** an allocation error envelope, or a `seq` at or below an existing `P{NNN}-*` directory number — sequence drift, which no doctor check detects: stop, report it, and correct the workspace's `sequences` counter before anything is minted.
5. **Entity rows before artifact files (feature 132).** Register the brainstorm — plus the backlog entity when the PRD carries a `*Source: Backlog #NNNNN*` marker — and `set_parent` to chain backlog → brainstorm. Then `register_entity(entity_type="project", entity_id="P{NNN}", name="{slug}", status="active", parent_uuid="{brainstorm uuid}")`. A registration error stops the run here, before any directory exists.
6. Create `{pd_artifacts_root}/projects/P{NNN}-{slug}/`, then `init_project_state(project_dir=..., project_id="P{NNN}", slug="{slug}", features='[]', milestones='[]', brainstorm_source="{prd path}")` for the state and its `.meta.json` projection.
7. Copy the PRD to `prd.md` there and verify it is non-empty. Failure → stop and name what exists, so a partial project is visible rather than silent.
8. Continue inline into the decomposing skill with the project directory and PRD text. It owns feature allocation, ordering, registration, and `roadmap.md`.

**Constraints:** no `.meta.json` writes outside MCP tools; the entities are the record and `roadmap.md` is their projection.
