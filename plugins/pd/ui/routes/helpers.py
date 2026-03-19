"""Shared helpers for UI route handlers."""

# Generic message for DB errors shown to users. Detailed error goes to stderr.
DB_ERROR_USER_MESSAGE = (
    "An error occurred while querying the database. "
    "Check server logs for details."
)


def missing_db_response(templates, request, db_path):
    """Return error.html response for missing database."""
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "error_title": "Database Not Found",
            "error_message": (
                "The entity database was not found. "
                "Run the entity registry MCP server to initialize it, "
                "or set ENTITY_DB_PATH to point to an existing database."
            ),
            "db_path": db_path,
        },
    )
