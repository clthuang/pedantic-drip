"""KB Import wrapper — syncs markdown knowledge-bank entries to semantic memory DB."""

from semantic_memory.importer import MarkdownImporter


def sync_knowledge_bank(memory_db, project_root, artifacts_root, global_store_path):
    """Run MarkdownImporter to sync markdown KB entries to semantic memory DB.

    Args:
        memory_db: MemoryDatabase instance (connected to memory.db)
        project_root: absolute repo root (e.g., /Users/terry/projects/pedantic-drip)
        artifacts_root: relative sub-path (e.g., "docs")
        global_store_path: directory containing memory.db (e.g., ~/.claude/pd/memory)

    Returns:
        {"imported": int, "skipped": int}
    """
    importer = MarkdownImporter(db=memory_db, artifacts_root=artifacts_root)
    result = importer.import_all(
        project_root=project_root,
        global_store=global_store_path,
    )
    return {"imported": result.get("imported", 0), "skipped": result.get("skipped", 0)}
