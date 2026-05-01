"""Pure confidence-tier computation (Feature 101 FR-4).

Extracted into its own module to break the upward dependency that would
otherwise have ``database.py`` importing from ``maintenance.py`` (a
storage-layer module reaching into a business-logic module — code-quality
reviewer iter 1, blocker B2).

Both ``database.merge_duplicate`` and ``maintenance.upgrade_confidence``
import ``_recompute_confidence`` from here without violating the layer
ordering.

The function is pure (no DB access, no config read); thresholds are
passed via the entry dict's ``_K_OBS``/``_K_USE`` keys (defaults 3, 5).
Caller resolves config keys before calling.
"""
from __future__ import annotations


def _recompute_confidence(entry: dict) -> str | None:
    """Return new confidence tier if upgrade applies, else ``None``.

    Feature 101 FR-4 OR-semantics over two gates with outcome-validation
    floor on the use gate:

    - **Observation gate:** ``observation_count >= K_OBS`` (default 3,
      passed via ``entry['_K_OBS']``).
    - **Use gate:** ``influence_count >= 1 AND influence_count + recall_count >= K_USE``
      (default 5, passed via ``entry['_K_USE']``). The ``>= 1`` floor
      prevents pure-retrieval-popularity promotion.

    Either gate triggers ``low → medium``. Both gates' values doubled
    (auto-derived: ``K_OBS_HIGH = K_OBS * 2``, ``K_USE_HIGH = K_USE * 2``)
    trigger ``medium → high``. ``high`` is idempotent (returns ``None``).
    """
    cur = entry.get("confidence", "low")
    if cur not in ("low", "medium"):
        return None
    obs = int(entry.get("observation_count", 0) or 0)
    inf = int(entry.get("influence_count", 0) or 0)
    rec = int(entry.get("recall_count", 0) or 0)

    K_OBS = entry.get("_K_OBS", 3)
    K_USE = entry.get("_K_USE", 5)
    K_OBS_HIGH = K_OBS * 2
    K_USE_HIGH = K_USE * 2

    obs_gate_med = obs >= K_OBS
    use_gate_med = inf >= 1 and (inf + rec) >= K_USE
    obs_gate_high = obs >= K_OBS_HIGH
    use_gate_high = inf >= 1 and (inf + rec) >= K_USE_HIGH

    if cur == "low" and (obs_gate_med or use_gate_med):
        if obs_gate_high or use_gate_high:
            return "high"
        return "medium"
    if cur == "medium" and (obs_gate_high or use_gate_high):
        return "high"
    return None
