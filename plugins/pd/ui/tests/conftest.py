"""Path resolution for UI tests.

Adds plugins/pd/ and plugins/pd/hooks/lib/ to sys.path so that
imports like ``from ui.routes.board import router`` and
``from entity_registry.database import EntityDatabase`` work without
requiring PYTHONPATH to be set externally.
"""
import sys
from pathlib import Path

_plugin_dir = str(Path(__file__).resolve().parent.parent.parent)
_hooks_lib_dir = str(Path(__file__).resolve().parent.parent.parent / "hooks" / "lib")

if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)
if _hooks_lib_dir not in sys.path:
    sys.path.insert(0, _hooks_lib_dir)
