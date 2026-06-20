"""Reconciliation Orchestrator CLI — entrypoint for `python -m reconciliation_orchestrator`.

Runs all session-start reconciliation tasks in sequence:
  1. entity_status.sync_entity_statuses   — .meta.json → entity DB status sync
  2. workflow_engine.reconciliation        — .meta.json → DB workflow state sync

Design principles:
  - Fail-open: any task error is captured in `errors` list; exit code is always 0.
  - Per-task isolation: one task raising does not prevent others from running.
  - DB connections closed in finally block (even on task errors).

Output (stdout): single JSON line with keys:
  entity_sync, workflow_reconcile, dependency_cleanup, elapsed_ms, errors
"""
import argparse
import json
import os
import sys
import time

from entity_registry.database import EntityDatabase
from entity_registry.project_identity import _compute_legacy_project_id, resolve_workspace_uuid

from reconciliation_orchestrator import entity_status


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
        "--workspace-uuid",
        default=None,
        help=(
            "Optional workspace UUID (feature 108 / Decision 6 / Decision 11). "
            "If unset, resolved via resolve_workspace_uuid(project_root)."
        ),
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
    return parser.parse_args(argv)


def _resolve_workspace_uuid_with_precedence(args) -> str:
    """Resolve workspace UUID using FR-3 / Decision 11 precedence.

    Order: ENTITY_WORKSPACE_UUID env > --workspace-uuid CLI flag >
           resolve_workspace_uuid(project_root) (which itself walks
           workspace.json → DB → fresh-write).
    """
    env_uuid = os.environ.get("ENTITY_WORKSPACE_UUID")
    if env_uuid:
        return env_uuid
    flag_uuid = getattr(args, "workspace_uuid", None)
    if flag_uuid:
        return flag_uuid
    return resolve_workspace_uuid(args.project_root)


def run(args):
    """Execute all reconciliation tasks and write JSON summary to stdout.

    Args:
        args: Parsed argparse.Namespace with project_root, artifacts_root,
              entity_db, verbose fields.

    Side effects:
        - Writes a single JSON line to sys.stdout.
        - Calls sys.exit(0).
    """
    start = time.monotonic()
    entity_db = None

    results = {
        "entity_sync": None,
        "workflow_reconcile": None,
        "dependency_cleanup": None,
        "elapsed_ms": 0,
        "errors": [],
    }

    try:
        entity_db = EntityDatabase(args.entity_db)

        full_artifacts_path = os.path.join(args.project_root, args.artifacts_root)
        project_id = _compute_legacy_project_id(args.project_root)
        # Feature 108 FR-12 / AC-30: resolve workspace UUID with the
        # documented precedence chain. Best-effort: if resolution fails we
        # fall back to legacy project_id semantics (entity_status / etc.
        # still accept project_id) and emit nothing — the orchestrator must
        # never block session-start.
        try:
            workspace_uuid = _resolve_workspace_uuid_with_precedence(args)
        except Exception as exc:
            results["errors"].append(f"workspace_uuid: {exc}")
            workspace_uuid = ""

        # Task 1: entity status sync
        try:
            results["entity_sync"] = entity_status.sync_entity_statuses(
                entity_db, full_artifacts_path, project_id=project_id,
                artifacts_root=args.artifacts_root, project_root=args.project_root,
                workspace_uuid=workspace_uuid,
            )
        except Exception as exc:
            results["errors"].append(f"entity_status: {exc}")

        # Task 2: workflow state reconciliation (.meta.json → DB)
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

        # Task 3: dependency freshness cleanup
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

    elapsed_ms = int((time.monotonic() - start) * 1000)
    results["elapsed_ms"] = elapsed_ms

    sys.stdout.write(json.dumps(results))
    sys.exit(0)


if __name__ == "__main__":
    run(parse_args())
