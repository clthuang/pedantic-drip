"""Tests for export_entities MCP tool in entity_server."""
from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock


# Make entity_registry importable from hooks/lib/.
_hooks_lib = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "hooks", "lib")
)
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

import entity_server  # noqa: E402

from entity_server import export_entities


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExportEntitiesTool:
    def test_db_not_initialized(self):
        """Returns error when _db is None."""
        entity_server._db = None
        result = _run(entity_server.export_entities())
        assert result == "Error: database not initialized (server not started)"

    def test_delegates_to_helper(self):
        """Delegates to _process_export_entities with correct arguments."""
        mock_db = unittest.mock.MagicMock()
        mock_artifacts_root = "/tmp/arts"
        entity_server._db = mock_db
        entity_server._artifacts_root = mock_artifacts_root
        with unittest.mock.patch(
            "entity_server._process_export_entities"
        ) as mock_helper:
            mock_helper.return_value = "{}"
            _run(
                entity_server.export_entities(
                    entity_type="feature",
                    status="active",
                    include_lineage=False,
                )
            )
            mock_helper.assert_called_once_with(
                mock_db, "feature", "active", None, False, mock_artifacts_root
            )

    def test_include_lineage_default_true(self):
        """Default include_lineage is True when no args passed."""
        mock_db = unittest.mock.MagicMock()
        mock_artifacts_root = "/tmp/arts"
        entity_server._db = mock_db
        entity_server._artifacts_root = mock_artifacts_root
        with unittest.mock.patch(
            "entity_server._process_export_entities"
        ) as mock_helper:
            mock_helper.return_value = "{}"
            _run(entity_server.export_entities())
            mock_helper.assert_called_once_with(
                mock_db, None, None, None, True, mock_artifacts_root
            )

    def test_returns_helper_result(self):
        """Returns the exact string from _process_export_entities."""
        expected = '{"schema_version": 1, "entities": []}'
        mock_db = unittest.mock.MagicMock()
        entity_server._db = mock_db
        entity_server._artifacts_root = "/tmp/arts"
        with unittest.mock.patch(
            "entity_server._process_export_entities"
        ) as mock_helper:
            mock_helper.return_value = expected
            result = _run(entity_server.export_entities())
            assert result == expected
