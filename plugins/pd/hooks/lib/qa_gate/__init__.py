"""qa_gate package: canonical .qa-gate.json schema + emitter (FR-1).

Status enum is module-level so it's importable from validators or future
schema-generators without instantiating the emitter.
"""
from __future__ import annotations

__version__ = "0.1.0"

# FR-1.1 canonical per-AC status enum. Modeled on
# semantic_memory.__init__.VALID_CATEGORIES (frozenset, O(1) membership).
STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})
