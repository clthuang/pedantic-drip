"""Constants for the workflow engine package.

FEATURE_PHASE_TO_KANBAN was removed in feature:052 (AC-4). Kanban
derivation was subsequently centralized in the (now-retired)
workflow_engine.kanban module. Feature 132 (D6.1-.3) deleted that shared
module: each live call site now carries its own private, byte-identical
phase-to-kanban mapping instead (backfill.py, engine.py,
feature_lifecycle.py, reconciliation.py, mcp/workflow_state_server.py —
kept in sync via test_constants.py's parity pin). No shared constant
lives here.
"""
