"""Reconciliation Orchestrator CLI — entrypoint for `python -m reconciliation_orchestrator`.

Runs all session-start reconciliation tasks in sequence:
  1. entity_status.sync_entity_statuses   — registers the checkout's new
     brainstorm ``.prd.md`` files
  2. workflow_engine.reconciliation._recover_pending_cascades — re-runs
     the missed completion cascades found in this session's workspace
  3. dependency_freshness.cleanup_stale_dependencies — flips this
     workspace's blocked entities whose blockers are all resolved

Nothing here reads a feature's or project's ``.meta.json`` back into the
registry: those files are projections of it (design W1).

Design principles:
  - Fail-open: any task error is captured in `errors` list; exit code is always 0.
  - Per-task isolation: one task raising does not prevent others from running.
  - Workspace-scoped scans: Tasks 2 and 3 list only this session's
    workspace, so an unresolved workspace skips them and records why under
    `errors`. Task 3 flips only this workspace's entities, but Task 2's
    writes follow edges: an unblock can flip a dependent in another
    workspace across a cross-workspace `blocks` edge, and an objective's
    rescore rewrites a changed key result wherever it is registered.
  - DB connections closed in finally block (even on task errors).

Output (stdout): single JSON line with keys:
  entity_sync, cascade_recovery, dependency_cleanup, elapsed_ms, errors
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
            "If unset, resolved via resolve_workspace_uuid(project_root, "
            "db_path=--entity-db)."
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
           resolve_workspace_uuid(project_root, db_path=args.entity_db)
           (which itself walks workspace.json → DB → fresh-write; db_path
           threaded so registration lands in the SAME DB the run targets,
           not the real ~/.claude default — 2026-09-17 leak fix).
    """
    env_uuid = os.environ.get("ENTITY_WORKSPACE_UUID")
    if env_uuid:
        return env_uuid
    flag_uuid = getattr(args, "workspace_uuid", None)
    if flag_uuid:
        return flag_uuid
    return resolve_workspace_uuid(args.project_root, db_path=args.entity_db)


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
        "cascade_recovery": None,
        "dependency_cleanup": None,
        "elapsed_ms": 0,
        "errors": [],
    }

    try:
        entity_db = EntityDatabase(args.entity_db)

        full_artifacts_path = os.path.join(args.project_root, args.artifacts_root)
        project_id = _compute_legacy_project_id(args.project_root)
        # Feature 108 FR-12 / AC-30: resolve workspace UUID with the
        # documented precedence chain. Best-effort: if resolution fails,
        # Task 1 falls back to the legacy project_id (brainstorm
        # registration still accepts one), Tasks 2 and 3 are skipped, and
        # the reason is recorded under `errors` — the orchestrator must
        # never block session-start.
        try:
            workspace_uuid = _resolve_workspace_uuid_with_precedence(args)
        except Exception as exc:
            results["errors"].append(f"workspace_uuid: {exc}")
            workspace_uuid = ""

        # Task 1: register the checkout's new brainstorms
        try:
            results["entity_sync"] = entity_status.sync_entity_statuses(
                entity_db, full_artifacts_path, project_id=project_id,
                artifacts_root=args.artifacts_root, project_root=args.project_root,
                workspace_uuid=workspace_uuid,
            )
        except Exception as exc:
            results["errors"].append(f"entity_status: {exc}")

        # Task 2: recover missed completion cascades (a completion whose
        # rollup or unblock never ran). It scans only this session's
        # workspace and writes by uuid; its unblocks and key-result rescores
        # follow edges into other workspaces. Unscoped, it would rewrite
        # every workspace's parents, so an unresolved workspace skips it.
        if workspace_uuid:
            try:
                from workflow_engine.reconciliation import _recover_pending_cascades

                results["cascade_recovery"] = _recover_pending_cascades(
                    entity_db, workspace_uuid,
                )
            except Exception as exc:
                results["errors"].append(f"cascade_recovery: {exc}")
        else:
            results["errors"].append(
                "cascade_recovery: skipped: workspace unresolved"
            )

        # Task 3: dependency freshness cleanup, scoped the same way.
        if workspace_uuid:
            try:
                from reconciliation_orchestrator import dependency_freshness
                results["dependency_cleanup"] = (
                    dependency_freshness.cleanup_stale_dependencies(
                        entity_db, workspace_uuid,
                    )
                )
            except Exception as exc:
                results["errors"].append(f"dependency_freshness: {exc}")
                results["dependency_cleanup"] = 0
        else:
            results["errors"].append(
                "dependency_freshness: skipped: workspace unresolved"
            )

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
