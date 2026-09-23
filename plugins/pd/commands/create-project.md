---
description: Create a project from a PRD and decompose it into features
argument-hint: "--prd=<path>"
---

# /pd:create-project

**Purpose:** turn a PRD into a project entity plus its planned feature entities.

**Inputs:** `--prd=<path>`, from `/pd:brainstorm` or standalone. Missing → ask for it.

**Output:** `project:{NNN}-{slug}` entity, `{pd_artifacts_root}/projects/{NNN}-{slug}/prd.md`, and the planned feature entities the decomposing skill registers.

**Steps:**
1. PRD must exist and exceed 100 bytes. Otherwise stop.
2. Slug from the PRD's first heading — lowercase, non-alphanumerics to hyphens, 30 chars, no trailing hyphen.
3. **Allocate atomically:** `allocate_entity_id(entity_type="project", name="{slug}")`. **Use the returned `entity_id` verbatim** for the directory, and the returned `seq` and `slug` to register. Do not build an id from `seq` — one function composes display ids (`render_display_id`) and a second composition is how the allocator and the registrar came to disagree. Projects carry no `P` prefix; they render `{NNN}-{slug}` like every other sequence-numbered kind. The `sequences` table is the only source of the next number: **never scan the filesystem for `{NNN}-*` directories**, on any path.
4. **Two hard stops, both creating nothing:** an allocation error envelope, or a `seq` at or below an existing project directory number — counting both the current `{NNN}-*` shape and the legacy `P{NNN}-*` directories still on disk, which are NOT renamed. Sequence drift is detected by no doctor check: stop, report it, and correct the workspace's `sequences` counter before anything is minted.
5. **Entity rows before artifact files (feature 132).** Register the brainstorm with `display_id` set to its file stem. When the PRD carries a `*Source: Backlog #…*` marker, `set_parent` the brainstorm under that backlog entity if it exists; a backlog entity is never registered here (a legacy `#NNNNN` id has no seq/slug form), so when it is absent, skip the link and say so. Then `register_entity(entity_type="project", seq={the allocated seq}, slug="{the allocated slug}", name="{slug}", status="active", parent_uuid="{brainstorm uuid}")`. A registration error stops the run here, before any directory exists.
6. Create `{pd_artifacts_root}/projects/{NNN}-{slug}/`, then `init_project_state(project_dir=..., project_id="{NNN}", slug="{slug}", features='[]', milestones='[]', brainstorm_source="{prd path}")` for the state and its `.meta.json` projection. `init_project_state` composes `{project_id}-{slug}`, so pass the bare number, not the full id.
7. Copy the PRD to `prd.md` there and verify it is non-empty. Failure → stop and name what exists, so a partial project is visible rather than silent.
8. Continue inline into the decomposing skill with the project directory and PRD text. It owns feature allocation, ordering, registration, and `roadmap.md`.

**Constraints:** no `.meta.json` writes outside MCP tools; the entities are the record and `roadmap.md` is their projection.
