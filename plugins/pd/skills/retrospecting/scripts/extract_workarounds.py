#!/usr/bin/env python3
"""FR-3 workaround extraction for feature 102.

Standalone deterministic function invoked at retrospecting skill runtime
(per design.md I-4). Scans implementation-log.md for decision/deviation
entries followed within 10 lines by ≥2 failed-attempt entries.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_DECISION_RE = re.compile(r"\*\*Decision:?\*\*|^##\s+.*decision|^##\s+.*deviation", re.IGNORECASE | re.MULTILINE)
_FAILURE_RE = re.compile(r"\b(failed|error|reverted|tried again)\b", re.IGNORECASE)
_TASK_HEADER_RE = re.compile(r"^##\s+", re.MULTILINE)


def extract_workarounds(log_text: str, phase_iterations: dict) -> list[dict]:
    """Extract workaround candidates from implementation-log content.

    Returns [] if log is empty, no phase has iterations >= 3, or no
    matching blocks found.
    """
    if not log_text:
        return []
    if not any(v >= 3 for v in (phase_iterations or {}).values() if isinstance(v, int)):
        return []

    candidates: list[dict] = []
    lines = log_text.split("\n")
    decision_indices = [i for i, line in enumerate(lines) if _DECISION_RE.search(line)]

    for d_idx in decision_indices:
        # Look for ≥2 failure markers within next 10 lines
        window = lines[d_idx + 1 : d_idx + 11]
        failure_count = sum(1 for line in window if _FAILURE_RE.search(line))
        if failure_count >= 2:
            decision_line = lines[d_idx].strip()
            decision_text = re.sub(r"[*#]+", "", decision_line).strip()
            decision_text = re.sub(r"^Decision:?\s*", "", decision_text, flags=re.IGNORECASE).strip()
            name = decision_text[:60].rstrip().rstrip(".,!?;:")
            candidates.append({
                "name": name,
                "description": f"Workaround: {decision_text} after {failure_count} failed attempts",
                "category": "heuristics",
                "confidence": "low",
                "reasoning": f"Detected via decision-followed-by-{failure_count}-failures heuristic",
            })

    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract workaround candidates from implementation log")
    parser.add_argument("--log-path", required=True, help="Path to implementation-log.md")
    parser.add_argument("--meta-json-path", required=True, help="Path to .meta.json")
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)
    meta_path = Path(args.meta_json_path)

    log_text = log_path.read_text() if log_path.exists() else ""

    phase_iterations: dict[str, int] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            phases = meta.get("phases", {})
            for phase_name, phase_data in phases.items():
                if isinstance(phase_data, dict) and "iterations" in phase_data:
                    phase_iterations[phase_name] = phase_data["iterations"]
        except (json.JSONDecodeError, OSError):
            pass

    print(json.dumps(extract_workarounds(log_text, phase_iterations)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
