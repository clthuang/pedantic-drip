# Design: Unify Entity Reconciliation

## Prior Art Research

### Research Conducted
| Question | Source | Finding |
|----------|--------|---------|
| How does entity_status.py work? | entity_status.py:6-61 | Scans features/ and projects/ for .meta.json, compares status with DB, updates on drift |
| How does brainstorm_registry.py work? | brainstorm_registry.py:11-58 | Scans brainstorms/ for .prd.md, registers new ones. Never updates existing. |
| How does orchestrator call them? | __main__.py:92-107 | Task 1: entity_status, Task 2: brainstorm_registry — separate calls with different return dicts |
| What's in backlog.md? | docs/backlog.md | Markdown table with `\| ID \| timestamp \| description \|`. Status embedded in description: `(closed:`, `(promoted →`, `(fixed:` |
| What ENTITY_MACHINES statuses exist for backlog? | entity_lifecycle.py:38-57 | open, triaged, promoted, dropped |
| What junk exists in DB? | DB export | B2, B3, E1, #, ~~B1~~, ~~E2~~, etc. — OCM checklist items registered as pd backlogs |

### Existing Solutions Evaluated
| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| Keep separate modules | Current architecture | Rejected — unnecessary separation, backlog gap never gets addressed |
| Add third module for backlogs | — | Rejected — three modules for four entity types is worse than one |

### Novel Work Justified
The only new code is backlog parsing from `backlog.md` and junk cleanup. Everything else is merging existing code.

## Architecture Overview

```
sync_entity_statuses(db, full_artifacts_path, project_id, artifacts_root, project_root)
  │
  ├── _sync_meta_json_entities(db, full_artifacts_path, "features", "feature", project_id)
  │     └── existing logic from entity_status.py (unchanged)
  │
  ├── _sync_meta_json_entities(db, full_artifacts_path, "projects", "project", project_id)
  │     └── existing logic from entity_status.py (unchanged)
  │
  ├── _sync_brainstorm_entities(db, full_artifacts_path, artifacts_root, project_root, project_id)
  │     └── existing logic from brainstorm_registry.py + new missing-file detection
  │
  └── _sync_backlog_entities(db, full_artifacts_path, artifacts_root, project_id)
        └── NEW: parse backlog.md, detect status markers, sync to DB
```

Single function, four type-specific internal helpers. The existing feature/project logic is extracted into `_sync_meta_json_entities()` without behavioral changes.

## Components

### C1: Refactored sync_entity_statuses()
- **Purpose:** Single entry point for all entity reconciliation
- **Location:** `reconciliation_orchestrator/entity_status.py`
- **Change:** Add `artifacts_root` parameter, call 4 helpers, aggregate results
- **Returns:** `{"updated": N, "skipped": N, "archived": N, "registered": N, "deleted": N, "warnings": [...]}`

### C2: _sync_backlog_entities() helper
- **Purpose:** Parse backlog.md and sync backlog entity statuses to DB
- **Location:** Inside `entity_status.py` (private function)
- **Logic:** Read backlog.md → parse table rows → detect status markers → register/update/delete entities

### C3: Orchestrator update
- **Purpose:** Remove Task 2, pass artifacts_root to Task 1
- **Location:** `reconciliation_orchestrator/__main__.py`
- **Change:** Delete brainstorm_registry import and call; add artifacts_root to sync_entity_statuses call; remove `brainstorm_sync` key from results dict (entity_sync now includes registered/deleted counts). Tests asserting on `brainstorm_sync` key need updating.

### C4: brainstorm_registry.py deletion
- **Purpose:** Remove dead code
- **Change:** Delete file, update __init__.py if needed

## Interfaces

### I1: sync_entity_statuses() — updated signature

```python
def sync_entity_statuses(
    db: EntityDatabase,
    full_artifacts_path: str,
    project_id: str = "__unknown__",
    artifacts_root: str = "docs",  # NEW — relative path for artifact_path storage
    project_root: str = "",  # NEW — absolute path to project root for artifact_path resolution
) -> dict:
    """Scan all entity types and sync statuses to entity registry.
    
    Args:
        project_root: Absolute path to project root. If empty, derived from
                      full_artifacts_path by stripping artifacts_root suffix.
    
    Returns:
        {"updated": int, "skipped": int, "archived": int, 
         "registered": int, "deleted": int, "warnings": list[str]}
    """
```

### I2: _sync_backlog_entities() — new helper

```python
def _sync_backlog_entities(
    db: EntityDatabase,
    full_artifacts_path: str,
    artifacts_root: str,
    project_id: str,
) -> dict:
    """Parse backlog.md and sync backlog entities.
    
    Status mapping:
        (closed: *)             → "dropped"
        (already implemented *) → "dropped"
        (promoted → *)          → "promoted"  
        (fixed: *)              → "dropped"
        no marker               → "open"
    
    Also:
        - Deletes junk entities (non ^[0-9]{5}$ IDs)
        - Deduplicates same-project duplicates (keeps non-null status)
        - Registers new backlog items not in DB
    
    Returns:
        {"updated": int, "skipped": int, "registered": int, "deleted": int, "warnings": list[str]}
    """
```

**Parsing logic:**
```python
import re

BACKLOG_ROW_RE = re.compile(r'^\|\s*(\d{5})\s*\|[^|]*\|(.+)\|')
CLOSED_RE = re.compile(r'\((?:closed|already implemented)[:\s—]')
PROMOTED_RE = re.compile(r'\(promoted\s*(?:→|->)')
FIXED_RE = re.compile(r'\(fixed:')
JUNK_ID_RE = re.compile(r'^[0-9]{5}$')

for line in backlog_md_lines:
    match = BACKLOG_ROW_RE.match(line)
    if not match:
        continue
    entity_id = match.group(1)
    description = match.group(2).strip()
    
    # Detect status from description text
    # Aligned with doctor/checks.py:796 regex patterns (most comprehensive)
    if CLOSED_RE.search(description):
        status = "dropped"  # covers (closed: ...) and (already implemented ...)
    elif PROMOTED_RE.search(description):
        status = "promoted"
    elif FIXED_RE.search(description):
        status = "dropped"
    else:
        status = "open"
    
    # Strip status markers from name
    name = re.sub(r'\s*\((?:closed|promoted|fixed)[^)]*\)\s*', '', description).strip()
    
    # Register or update
    type_id = f"backlog:{entity_id}"
    existing = db.get_entity(type_id)
    if existing is None:
        db.register_entity(
            entity_type="backlog",
            entity_id=entity_id,
            name=name[:200],  # truncate long descriptions
            artifact_path=os.path.join(artifacts_root, "backlog.md"),
            status=status,
            project_id=project_id,
        )
        results["registered"] += 1
    elif existing.get("status") != status:
        db.update_entity(type_id, status=status, project_id=project_id)
        results["updated"] += 1
    else:
        results["skipped"] += 1
```

**Execution order within _sync_backlog_entities:**
1. Junk cleanup first (removes non-5-digit IDs from DB)
2. Dedup second (removes same-project duplicates among valid IDs)
3. Parse backlog.md and sync statuses last (operates on clean data)

**Missing file handling:** If `backlog.md` doesn't exist, return empty results dict immediately (matching brainstorm_registry.py pattern).

### I5: _sync_brainstorm_entities() — absorbed + new missing-file detection

```python
def _sync_brainstorm_entities(
    db: EntityDatabase,
    full_artifacts_path: str,
    artifacts_root: str,
    project_root: str,
    project_id: str,
) -> dict:
    """Scan brainstorms/ for .prd.md files; register new, detect missing.
    
    Logic from brainstorm_registry.py plus NEW missing-file detection:
    1. Scan brainstorms/ dir for .prd.md files → register any not in DB (existing logic)
    2. Scan DB for brainstorm entities → check if artifact_path file still exists
       If missing → update status to "archived" (NEW)
    
    Args:
        project_root: Absolute path to project root (e.g., /Users/terry/projects/pedantic-drip).
                      Used for resolving artifact_path to absolute path in missing-file detection.
    
    Returns: {"registered": int, "archived": int, "skipped": int}
    """
    results = {"registered": 0, "archived": 0, "skipped": 0}
    brainstorms_dir = os.path.join(full_artifacts_path, "brainstorms")
    
    if not os.path.isdir(brainstorms_dir):
        return results
    
    # Part 1: Register new brainstorms (existing brainstorm_registry.py logic)
    for filename in os.listdir(brainstorms_dir):
        if not filename.endswith(".prd.md") or filename == ".gitkeep":
            continue
        stem = filename[:-len(".prd.md")]
        type_id = f"brainstorm:{stem}"
        if db.get_entity(type_id) is not None:
            results["skipped"] += 1
            continue
        db.register_entity(
            entity_type="brainstorm", entity_id=stem, name=stem,
            artifact_path=os.path.join(artifacts_root, "brainstorms", filename),
            status="active", project_id=project_id,
        )
        results["registered"] += 1
    
    # Part 2: Detect missing files for existing brainstorm entities (NEW)
    for entity in db.list_entities(entity_type="brainstorm", project_id=project_id):
        if entity.get("status") in ("promoted", "abandoned", "archived"):
            continue  # already terminal
        artifact = entity.get("artifact_path", "")
        full_path = os.path.join(project_root, artifact) if artifact else ""
        if artifact and not os.path.isfile(full_path):
            db.update_entity(entity["type_id"], status="archived", project_id=project_id)
            results["archived"] += 1
    
    return results
```

### I3: Junk cleanup logic

```python
def _cleanup_junk_backlogs(db: EntityDatabase, project_id: str) -> tuple[int, list[str]]:
    """Delete backlog entities with non-5-digit IDs. Returns (count deleted, warnings)."""
    deleted = 0
    warnings = []
    all_backlogs = db.list_entities(entity_type="backlog", project_id=project_id)
    for entity in all_backlogs:
        entity_id = entity["type_id"].split(":", 1)[1] if ":" in entity["type_id"] else ""
        if not JUNK_ID_RE.match(entity_id):
            try:
                db.delete_entity(entity["type_id"])
                deleted += 1
            except ValueError as e:
                warnings.append(f"Cannot delete junk backlog {entity['type_id']}: {e}")
    return deleted, warnings
```

### I4: Deduplication logic

```python
def _dedup_backlogs(db: EntityDatabase, project_id: str) -> int:
    """Remove same-project duplicate backlog entities. Returns count deleted."""
    deleted = 0
    seen = {}  # entity_id -> entity with best status
    all_backlogs = db.list_entities(entity_type="backlog", project_id=project_id)
    
    for entity in all_backlogs:
        eid = entity.get("entity_id", "")
        proj = entity.get("project_id", "__unknown__")
        key = (eid, proj)
        
        if key in seen:
            # Duplicate — keep the one with non-null status
            existing = seen[key]
            if entity.get("status") and not existing.get("status"):
                db.delete_entity(existing["type_id"])
                seen[key] = entity
            else:
                db.delete_entity(entity["type_id"])
            deleted += 1
        else:
            seen[key] = entity
    
    return deleted
```

## Technical Decisions

### TD-1: Single file, private helpers
- **Choice:** All 4 sync functions in entity_status.py as private helpers, not separate modules
- **Rationale:** They share the same DB connection, project_id, and return dict pattern. Separation was artificial.
- **Engineering Principle:** Colocation — code that changes together lives together

### TD-2: Status markers parsed by regex, not by field
- **Choice:** Parse `(closed:`, `(promoted →`, `(fixed:` from description text via regex
- **Rationale:** backlog.md embeds status in the description column, not a separate status column. The format is well-established (36 rows use it consistently).
- **Engineering Principle:** Parse the data you have, don't reshape the source

### TD-3: Name strips status markers
- **Choice:** Entity name = description text with status markers removed
- **Rationale:** The marker is metadata, not the entity name. `"Security Scanning — static rule-based..."` is better than `"Security Scanning — static rule-based... (closed: pd:security-reviewer agent runs on every implement phase)"`.

### TD-4: Junk cleanup is active deletion, not passive ignore
- **Choice:** Delete junk entities from DB rather than just not re-registering them
- **Rationale:** 30+ junk entries pollute search_entities results and entity counts. Active cleanup ensures they don't reappear.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Regex misparses a backlog row | Wrong status set | Regex tested against all 36 rows in current backlog.md |
| Junk cleanup deletes legitimate entities | Data loss | Only deletes non-5-digit IDs; all legitimate backlogs use 5-digit format |
| Dedup deletes wrong duplicate | Loses status or metadata | Keeps entity with non-null status; tie-breaks by keeping first seen |
| brainstorm_registry deletion breaks import | Import error on session start | Verify no other modules import brainstorm_registry before deleting |

## Dependencies
- `entity_registry/database.py` — EntityDatabase (register_entity, update_entity, get_entity, delete_entity, search_entities)
- `reconciliation_orchestrator/__main__.py` — orchestrator
- `docs/backlog.md` — backlog source of truth
