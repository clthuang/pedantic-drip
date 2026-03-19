# Documentation Schema Reference

Canonical file listings and metadata formats for each documentation tier. Used by the doc-writer agent and documentation skills to generate consistent project documentation.

## user-guide

- overview.md — Project name, description, key features
- installation.md — Prerequisites, install steps, verification
- usage.md — Quick start, common workflows, configuration

## dev-guide

- getting-started.md — Prerequisites, setup commands, running tests
- contributing.md — Branching, PR process, CI expectations
- architecture-overview.md — High-level component map for orientation

## technical

- architecture.md — Component map, data flow, module interfaces
- decisions/ — ADR directory (ADR-{NNN}-{slug}.md files)
- api-reference.md — Internal/external API contracts if applicable
- workflow-artifacts.md — Index linking to feature artifacts

## Project-Type Additions

Additional files added to the relevant tier based on detected project type:

- **Plugin:** plugin-api.md (added to technical tier)
- **CLI:** command-reference.md (added to user-guide tier)
- **API:** endpoint-reference.md (added to technical tier)
- **General:** none

## Tier-to-Source Monitoring

Source paths monitored per tier for drift detection. Changes in these paths signal that the corresponding documentation tier may need updating.

**user-guide:**
- `README.md`
- `package.json`
- `setup.py`
- `pyproject.toml`
- `bin/`

**dev-guide:**
- `src/`
- `test/`
- `Makefile`
- `.github/workflows/`
- `CONTRIBUTING.md`
- `docker-compose.yml`

**technical:**
- `src/`
- config files (`*.config.*`, `*.schema.*`)
- `docs/technical/`

## YAML Frontmatter Template

Every generated documentation file should include YAML frontmatter tracking its origin and freshness:

```yaml
---
last-updated: '2024-01-15T10:30:00Z'  # ISO 8601 with UTC Z suffix
source-feature: '{feature-id}-{slug}'
---
```

## Section Marker Template

Auto-generated sections within documentation files are delimited with HTML comments to enable safe regeneration without overwriting manual edits:

```
<!-- AUTO-GENERATED: START - source: {feature-id} -->
{auto-generated content}
<!-- AUTO-GENERATED: END -->
```

## Workflow Artifacts Index Format

The workflow-artifacts.md file uses a table format linking feature artifacts. References use the `{pd_artifacts_root}` config variable for project-aware path resolution:

```
| Feature | Status | Artifacts |
|---------|--------|-----------|
| {id}-{slug} | {status} | [{pd_artifacts_root}/features/{id}-{slug}/](link) |
```
