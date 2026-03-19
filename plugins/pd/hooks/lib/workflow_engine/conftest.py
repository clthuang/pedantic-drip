"""Pytest configuration for workflow_engine tests."""
from __future__ import annotations

import os
import sys

# Resolve transition_gate and entity_registry from parent lib directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
