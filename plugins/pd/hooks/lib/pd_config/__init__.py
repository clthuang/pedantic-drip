"""Standalone pd configuration reader (memory-independent).

Extracted from the former ``semantic_memory.config`` so that the entity
registry, workflow engine, and doctor can resolve project configuration
without depending on the (now removed) knowledge-bank / semantic-memory
subsystem.
"""
from __future__ import annotations

from pd_config.config import read_config

__all__ = ["read_config"]
