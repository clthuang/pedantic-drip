"""Tests for entity_registry.uuid7 module."""
from __future__ import annotations

import types

import pytest

from entity_registry.uuid7 import _require_uuid7, generate_uuid7


# ---------------------------------------------------------------------------
# generate_uuid7
# ---------------------------------------------------------------------------
class TestGenerateUuid7:
    def test_mints_are_version_7_and_time_ordered(self):
        """1000 mints: every uuid is version 7, and generation order is
        already sorted order (uuid7 is time-ordered — non-vacuous: this
        fails against a v4 mint, which has no temporal ordering)."""
        minted = [generate_uuid7() for _ in range(1000)]
        assert all(u[14] == "7" for u in minted)
        assert minted == sorted(minted)


# ---------------------------------------------------------------------------
# _require_uuid7
# ---------------------------------------------------------------------------
class TestRequireUuid7:
    def test_raises_when_uuid7_missing(self):
        """A module lacking uuid7 (pre-3.14 uuid) fails the floor check,
        naming the 3.14 floor rather than surfacing a bare AttributeError."""
        fake_uuid_module = types.SimpleNamespace()
        with pytest.raises(RuntimeError, match="3.14"):
            _require_uuid7(mod=fake_uuid_module)
