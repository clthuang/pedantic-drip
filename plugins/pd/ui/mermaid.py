"""Mermaid DAG builder for entity lineage visualization."""

import hashlib
import re

_ENTITY_TYPE_STYLES = {
    "feature": "fill:#1d4ed8,stroke:#3b82f6,color:#fff",
    "project": "fill:#059669,stroke:#10b981,color:#fff",
    "brainstorm": "fill:#0891b2,stroke:#22d3ee,color:#fff",
    "backlog": "fill:#4b5563,stroke:#6b7280,color:#fff",
}

_CURRENT_STYLE = "fill:#7c3aed,stroke:#a78bfa,color:#fff,stroke-width:3px"



def _sanitize_id(type_id: str) -> str:
    """Convert a type_id into a Mermaid-safe node identifier."""
    safe = re.sub(r"[^a-zA-Z0-9]", "_", type_id)
    if safe and safe[0] in "0123456789ox":
        safe = "n" + safe
    hash_suffix = hashlib.sha256(type_id.encode("utf-8")).hexdigest()[:4]
    return safe + "_" + hash_suffix


def _sanitize_label(text: str) -> str:
    """Escape characters that would break Mermaid node labels."""
    return (
        text.replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\\", "/")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_mermaid_dag(
    entity: dict, ancestors: list[dict], children: list[dict]
) -> str:
    """Generate a Mermaid flowchart TD definition string."""
    # Step 0: Build all_entities dict (entity last wins)
    all_entities: dict[str, dict] = {}
    for e in ancestors + children + [entity]:
        all_entities[e["type_id"]] = e

    lines: list[str] = ["flowchart TD"]

    # Step 1: Node definitions
    for tid, e in all_entities.items():
        safe_id = _sanitize_id(tid)
        label = e.get("name") or tid
        safe_label = _sanitize_label(label)
        lines.append(f'{safe_id}["{safe_label}"]')

    # Step 2: Edges
    for tid, e in all_entities.items():
        parent_tid = e.get("parent_type_id")
        if parent_tid and parent_tid in all_entities:
            lines.append(f"{_sanitize_id(parent_tid)} --> {_sanitize_id(tid)}")

    # Step 3: Click handlers (not for current entity)
    current_tid = entity["type_id"]
    for tid in all_entities:
        if tid != current_tid:
            safe_tid = tid.replace('"', '%22')
            lines.append(f'click {_sanitize_id(tid)} href "/entities/{safe_tid}"')

    # Step 4: classDef blocks
    for etype, style in _ENTITY_TYPE_STYLES.items():
        lines.append(f"classDef {etype} {style}")
    lines.append(f"classDef current {_CURRENT_STYLE}")

    # Step 5: Class assignments
    for tid, e in all_entities.items():
        safe_id = _sanitize_id(tid)
        if tid == current_tid:
            lines.append(f"class {safe_id} current")
        else:
            etype = e.get("entity_type", "feature")
            if etype not in _ENTITY_TYPE_STYLES:
                etype = "feature"
            lines.append(f"class {safe_id} {etype}")

    return "\n".join(lines)
