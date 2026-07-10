"""Time-ordered UUID (RFC 9562 uuid7) minting helper.

Wraps stdlib ``uuid.uuid7()`` (Python 3.14+). The import-time floor check
below fails fast with the required version named, rather than surfacing a
lazy ``AttributeError`` deep in a write path on an older interpreter.
"""
from __future__ import annotations

import sys
import uuid


def _require_uuid7(mod=uuid) -> None:
    """Raise RuntimeError if *mod* lacks ``uuid7``.

    Accepts *mod* so tests can inject a fake module lacking ``uuid7``
    directly, without monkeypatching the real ``uuid`` module.
    """
    if not hasattr(mod, "uuid7"):
        raise RuntimeError(
            "pd requires Python >= 3.14 for uuid.uuid7 (stdlib); "
            f"running {sys.version.split()[0]}"
        )


_require_uuid7()


def generate_uuid7() -> str:
    """Return a newly minted, time-ordered uuid7 string."""
    return str(uuid.uuid7())
