"""Workflow templates registry.

Maps ``(entity_type, weight)`` pairs to ordered phase sequences.
The canonical 7-phase feature sequence is referenced from
``transition_gate.constants.PHASE_SEQUENCE``.
"""
from __future__ import annotations

# Canonical 7-phase feature sequence (string values, not Phase enums)
FEATURE_7_PHASE: list[str] = [
    "brainstorm", "specify", "design", "create-plan",
    "implement", "finish",
]

# 5D lifecycle phases (Level 1/2/4 entities)
FIVE_D_FULL: list[str] = ["discover", "define", "design", "deliver", "debrief"]

WEIGHT_TEMPLATES: dict[tuple[str, str], list[str]] = {
    # --- Initiatives (L1) ---
    ("initiative", "full"):     FIVE_D_FULL[:],
    ("initiative", "standard"): FIVE_D_FULL[:],

    # --- Objectives (L1.5 / OKR) ---
    ("objective", "standard"):  ["define", "design", "deliver", "debrief"],

    # --- Key Results (L1.5 / OKR) ---
    ("key_result", "standard"): ["define", "deliver", "debrief"],

    # --- Projects (L2) ---
    ("project", "full"):        FIVE_D_FULL[:],
    ("project", "standard"):    FIVE_D_FULL[:],
    ("project", "light"):       ["define", "design", "deliver", "debrief"],

    # --- Features (L3) ---
    ("feature", "full"):        FEATURE_7_PHASE[:],
    ("feature", "standard"):    FEATURE_7_PHASE[:],
    ("feature", "light"):       ["specify", "implement", "finish"],

    # --- Tasks (L4) ---
    ("task", "standard"):       ["define", "deliver", "debrief"],
    ("task", "light"):          ["deliver"],
}


def get_template(entity_type: str, weight: str) -> list[str]:
    """Look up the phase sequence for an ``(entity_type, weight)`` pair.

    Parameters
    ----------
    entity_type:
        Entity type string (e.g. ``"feature"``, ``"task"``).
    weight:
        Ceremony weight (``"full"``, ``"standard"``, or ``"light"``).

    Returns
    -------
    list[str]
        Ordered list of phase names for the lifecycle.

    Raises
    ------
    KeyError
        If no template is defined for the given ``(entity_type, weight)`` pair.
    """
    key = (entity_type, weight)
    if key not in WEIGHT_TEMPLATES:
        raise KeyError(
            f"No workflow template for ({entity_type!r}, {weight!r}). "
            f"Defined pairs: {sorted(WEIGHT_TEMPLATES.keys())}"
        )
    # Return a copy to prevent mutation of the registry
    return WEIGHT_TEMPLATES[key][:]
