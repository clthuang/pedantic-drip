"""qa_gate.emitter — canonical .qa-gate.json writer (FR-1).

Schema (per spec FR-1.2 / design TD-8):
    {
      "feature": "{id}-{slug}",
      "head_sha": "{git rev-parse HEAD}",
      "gate_run_at": "{ISO 8601 UTC}",
      "ac_results": [
        {
          "id": "AC-N",
          "status": "passed|deferred|n_a|conditional_skipped",
          "evidence": "<≤500 chars>",
          "condition": "<non-empty when status == conditional_skipped, else ''>",
          "backlog_ref": "<5-digit backlog ID> | null"
        },
        ...
      ],
      "decision": "approved|deferred",
      "reviewers": [<reviewer agent names>]
    }

Idempotency (FR-1.3): when re-emitted with the same head_sha as an
existing on-disk JSON, the write is skipped and the existing path is
returned without mutation.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow `from qa_gate import STATUS_ENUM` regardless of how the package was
# imported (PYTHONPATH=plugins/pd/hooks/lib OR direct path import).
try:
    from qa_gate import STATUS_ENUM
except ImportError:  # pragma: no cover — fallback when invoked outside the package
    _HERE = Path(__file__).resolve().parent
    if str(_HERE.parent) not in sys.path:
        sys.path.insert(0, str(_HERE.parent))
    from qa_gate import STATUS_ENUM


_EVIDENCE_MAX_CHARS = 500
_DECISION_ENUM = frozenset({"approved", "deferred"})
_REQUIRED_KEYS = ("id", "status", "evidence")


def _validate_ac_result(entry: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Validate one ac_results entry; return a normalized copy with defaults."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"ac_results[{index}]: expected dict, got {type(entry).__name__}"
        )

    for key in _REQUIRED_KEYS:
        if key not in entry:
            raise ValueError(
                f"ac_results[{index}]: missing required key {key!r} "
                f"(required: id, status, evidence)"
            )

    status = entry["status"]
    if status not in STATUS_ENUM:
        raise ValueError(
            f"ac_results[{index}]: status={status!r} not in STATUS_ENUM "
            f"({sorted(STATUS_ENUM)})"
        )

    evidence = entry["evidence"]
    if not isinstance(evidence, str):
        raise ValueError(
            f"ac_results[{index}]: evidence must be str, got {type(evidence).__name__}"
        )
    if len(evidence) > _EVIDENCE_MAX_CHARS:
        raise ValueError(
            f"ac_results[{index}]: evidence length {len(evidence)} exceeds "
            f"{_EVIDENCE_MAX_CHARS}-char limit"
        )

    condition = entry.get("condition", "")
    if status == "conditional_skipped" and not condition:
        raise ValueError(
            f"ac_results[{index}]: status='conditional_skipped' requires "
            f"non-empty condition (got {condition!r})"
        )

    backlog_ref = entry.get("backlog_ref", None)

    return {
        "id": entry["id"],
        "status": status,
        "evidence": evidence,
        "condition": condition,
        "backlog_ref": backlog_ref,
    }


def _git_head_sha() -> str:
    """Resolve HEAD SHA via git. Caller scope; not cached."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _iso_utc_now() -> str:
    """ISO 8601 UTC timestamp, second precision (no microseconds)."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_qa_gate(
    *,
    feature: str,
    feature_dir: str,
    ac_results: List[Dict[str, Any]],
    decision: str,
    reviewers: List[str],
    head_sha: Optional[str] = None,
) -> str:
    """Validate inputs and write `.qa-gate.json` to `{feature_dir}/.qa-gate.json`.

    Returns the absolute path of the written file. Idempotent on head_sha:
    if the file already exists with the same head_sha, returns the path
    without rewriting.

    Raises
    ------
    ValueError
        - any ac_results[i].status not in STATUS_ENUM
        - any ac_results[i] missing id/status/evidence
        - any ac_results[i].evidence > 500 chars
        - any ac_results[i].status == "conditional_skipped" with empty condition
        - decision not in {"approved", "deferred"}
    """
    if decision not in _DECISION_ENUM:
        raise ValueError(
            f"decision={decision!r} not in {sorted(_DECISION_ENUM)}"
        )
    if not isinstance(ac_results, list):
        raise ValueError(
            f"ac_results must be list, got {type(ac_results).__name__}"
        )
    if not isinstance(reviewers, list):
        raise ValueError(
            f"reviewers must be list, got {type(reviewers).__name__}"
        )

    validated = [_validate_ac_result(e, i) for i, e in enumerate(ac_results)]

    if head_sha is None:
        head_sha = _git_head_sha()

    feature_dir_path = Path(feature_dir)
    feature_dir_path.mkdir(parents=True, exist_ok=True)
    out_path = feature_dir_path / ".qa-gate.json"

    # FR-1.3 idempotency: same head_sha → no-op return.
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
            if existing.get("head_sha") == head_sha:
                return str(out_path.resolve())
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable — fall through and overwrite.
            pass

    payload = {
        "feature": feature,
        "head_sha": head_sha,
        "gate_run_at": _iso_utc_now(),
        "ac_results": validated,
        "decision": decision,
        "reviewers": list(reviewers),
    }

    tmp_path = out_path.with_suffix(".json.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        os.replace(tmp_path, out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return str(out_path.resolve())
