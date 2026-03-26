"""Reconciliation Orchestrator CLI — entrypoint for `python -m reconciliation_orchestrator`.

Runs all session-start reconciliation tasks in sequence:
  1. entity_status.sync_entity_statuses   — .meta.json → entity DB status sync
  2. brainstorm_registry.sync_brainstorm_entities — brainstorm file registration
  3. kb_import.sync_knowledge_bank         — MarkdownImporter KB sync
  4. workflow_engine.reconciliation        — .meta.json → DB workflow state sync

Design principles:
  - Fail-open: any task error is captured in `errors` list; exit code is always 0.
  - Per-task isolation: one task raising does not prevent others from running.
  - DB connections closed in finally block (even on task errors).

Output (stdout): single JSON line with keys:
  entity_sync, brainstorm_sync, kb_import, workflow_reconcile, dependency_cleanup, elapsed_ms, errors
"""
import argparse
import json
import os
import sys
import time

from entity_registry.database import EntityDatabase
from entity_registry.project_identity import detect_project_id
from semantic_memory.database import MemoryDatabase

from reconciliation_orchestrator import brainstorm_registry, entity_status, kb_import


def parse_args(argv=None):
    """Parse CLI arguments. Exposed for direct testing."""
    parser = argparse.ArgumentParser(
        prog="reconciliation_orchestrator",
        description="Run all session-start reconciliation tasks.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Absolute path to the project/repo root.",
    )
    parser.add_argument(
        "--artifacts-root",
        required=True,
        help="Relative sub-path for artifacts (e.g., 'docs').",
    )
    parser.add_argument(
        "--entity-db",
        required=True,
        help="Path to the entity registry SQLite DB file.",
    )
    parser.add_argument(
        "--memory-db",
        required=True,
        help="Path to the semantic memory SQLite DB file.",
    )
    return parser.parse_args(argv)


def run(args):
    """Execute all reconciliation tasks and write JSON summary to stdout.

    Args:
        args: Parsed argparse.Namespace with project_root, artifacts_root,
              entity_db, memory_db, verbose fields.

    Side effects:
        - Writes a single JSON line to sys.stdout.
        - Calls sys.exit(0).
    """
    start = time.monotonic()
    entity_db = None
    memory_db = None

    results = {
        "entity_sync": None,
        "brainstorm_sync": None,
        "kb_import": None,
        "workflow_reconcile": None,
        "dependency_cleanup": None,
        "elapsed_ms": 0,
        "errors": [],
    }

    try:
        entity_db = EntityDatabase(args.entity_db)
        memory_db = MemoryDatabase(args.memory_db)

        full_artifacts_path = os.path.join(args.project_root, args.artifacts_root)
        global_store_path = os.path.dirname(args.memory_db)
        project_id = detect_project_id(args.project_root)

        # Task 1: entity status sync
        try:
            results["entity_sync"] = entity_status.sync_entity_statuses(
                entity_db, full_artifacts_path, project_id=project_id
            )
        except Exception as exc:
            results["errors"].append(f"entity_status: {exc}")

        # Task 2: brainstorm registry sync
        try:
            results["brainstorm_sync"] = brainstorm_registry.sync_brainstorm_entities(
                entity_db, full_artifacts_path, args.artifacts_root,
                project_id=project_id,
            )
        except Exception as exc:
            results["errors"].append(f"brainstorm_registry: {exc}")

        # Task 3: KB import
        try:
            results["kb_import"] = kb_import.sync_knowledge_bank(
                memory_db, args.project_root, args.artifacts_root, global_store_path
            )
        except Exception as exc:
            results["errors"].append(f"kb_import: {exc}")

        # Task 4: workflow state reconciliation (.meta.json → DB)
        # Runs after entity_status sync (Task 1) so entity DB statuses are current.
        try:
            from workflow_engine.engine import WorkflowStateEngine
            from workflow_engine.reconciliation import apply_workflow_reconciliation

            engine = WorkflowStateEngine(entity_db, full_artifacts_path)
            recon_result = apply_workflow_reconciliation(
                engine=engine,
                db=entity_db,
                artifacts_root=full_artifacts_path,
            )
            results["workflow_reconcile"] = recon_result.summary
        except ImportError as exc:
            results["errors"].append(f"workflow_reconcile: import skipped: {exc}")
        except Exception as exc:
            results["errors"].append(f"workflow_reconcile: {exc}")

        # Task 5: dependency freshness cleanup
        try:
            from reconciliation_orchestrator import dependency_freshness
            result = dependency_freshness.cleanup_stale_dependencies(entity_db)
            results["dependency_cleanup"] = result
        except Exception as exc:
            results["errors"].append(f"dependency_freshness: {exc}")
            results["dependency_cleanup"] = 0

    except Exception as exc:
        # DB connection failure or other setup error
        results["errors"].append(f"setup: {exc}")

    finally:
        if entity_db is not None:
            entity_db.close()
        if memory_db is not None:
            memory_db.close()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    results["elapsed_ms"] = elapsed_ms

    sys.stdout.write(json.dumps(results))
    sys.exit(0)


if __name__ == "__main__":
    run(parse_args())
