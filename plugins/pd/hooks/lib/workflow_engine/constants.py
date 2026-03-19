"""Constants for the workflow engine package."""

FEATURE_PHASE_TO_KANBAN: dict[str, str] = {
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "create-tasks": "prioritised",
    "implement": "wip",
    "finish": "documenting",
}
