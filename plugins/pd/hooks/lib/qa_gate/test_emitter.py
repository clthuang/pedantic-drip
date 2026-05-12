"""Unit tests for qa_gate.emitter (FR-1)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Make the package importable when pytest is run with PYTHONPATH=plugins/pd/hooks/lib
_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from qa_gate.emitter import emit_qa_gate  # noqa: E402


def _valid_kwargs(feature_dir: str, *, ac_results=None):
    """Build a minimally valid emit_qa_gate kwargs dict."""
    return dict(
        feature="113-feature-112-qa-followups",
        feature_dir=feature_dir,
        ac_results=ac_results
        if ac_results is not None
        else [
            {
                "id": "AC-1",
                "status": "passed",
                "evidence": "test path: plugins/pd/hooks/lib/qa_gate/test_emitter.py",
            }
        ],
        decision="approved",
        reviewers=["pd:adversarial-reviewer"],
        head_sha="deadbeef" * 5,  # 40-char hex stand-in
    )


def test_emit_qa_gate_rejects_invalid_status(tmp_path):
    """FR-1.1: status outside STATUS_ENUM raises ValueError."""
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[{"id": "AC-1", "status": "invalid", "evidence": "x"}],
    )
    with pytest.raises(ValueError, match="status|STATUS_ENUM"):
        emit_qa_gate(**kwargs)


def test_emit_qa_gate_requires_id_status_evidence(tmp_path):
    """FR-1.2: missing required per-entry key raises ValueError."""
    # missing 'evidence'
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[{"id": "AC-1", "status": "passed"}],
    )
    with pytest.raises(ValueError):
        emit_qa_gate(**kwargs)

    # missing 'status'
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[{"id": "AC-2", "evidence": "x"}],
    )
    with pytest.raises(ValueError):
        emit_qa_gate(**kwargs)

    # missing 'id'
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[{"status": "passed", "evidence": "x"}],
    )
    with pytest.raises(ValueError):
        emit_qa_gate(**kwargs)


def test_emit_qa_gate_rejects_evidence_over_500_chars(tmp_path):
    """FR-1.2: evidence > 500 chars raises ValueError."""
    long_evidence = "x" * 501
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[{"id": "AC-1", "status": "passed", "evidence": long_evidence}],
    )
    with pytest.raises(ValueError, match="evidence"):
        emit_qa_gate(**kwargs)


def test_emit_qa_gate_rejects_conditional_skipped_with_empty_condition(tmp_path):
    """FR-1.2: status='conditional_skipped' + condition='' raises ValueError."""
    kwargs = _valid_kwargs(
        str(tmp_path),
        ac_results=[
            {
                "id": "AC-1",
                "status": "conditional_skipped",
                "evidence": "skipped pending #00xyz",
                "condition": "",
            }
        ],
    )
    with pytest.raises(ValueError, match="condition|conditional_skipped"):
        emit_qa_gate(**kwargs)


def test_emit_qa_gate_head_sha_idempotent(tmp_path):
    """FR-1.3: re-emit with same head_sha is a no-op (returns same path, doesn't rewrite)."""
    kwargs = _valid_kwargs(str(tmp_path))
    path1 = emit_qa_gate(**kwargs)
    assert os.path.exists(path1)

    # Capture mtime + content
    mtime1 = os.path.getmtime(path1)
    content1 = Path(path1).read_text()

    # Re-emit with same head_sha
    path2 = emit_qa_gate(**kwargs)
    assert path2 == path1
    mtime2 = os.path.getmtime(path2)
    content2 = Path(path2).read_text()

    # Idempotent: no rewrite (mtime unchanged) and content identical.
    assert mtime2 == mtime1
    assert content2 == content1
