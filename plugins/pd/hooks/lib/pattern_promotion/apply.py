"""Apply orchestrator — 5-stage atomic write per FR-5.

Stages implemented here (1-4):

  Stage 1 — Pre-flight validation (no writes):
    * modify targets must exist; create targets must NOT exist.
    * `hooks.json` targets: the patched `after` must parse as JSON.
    * TD-8 collision scan: any existing `.sh` in the hook's directory or any
      sibling markdown file in the edited dirs that already carries a
      `Promoted ... {entry.name}` marker aborts the run.

  Stage 2 — Snapshot:
    * For every modify edit, read and record current bytes keyed by path.
    * Record the list of create-edits (rollback: unlink).

  Stage 3 — Write:
    * Apply each FileEdit in ascending `write_order`, breaking ties by path.
    * Any exception during write -> rollback every edit applied so far.

  Stage 4 — Post-write validation:
    * Every FileEdit's path must exist after write.
    * hooks.json targets must re-parse as JSON.
    * If target_type == "hook": execute the test script (write_order=1) with
      `subprocess.run(..., timeout=<env|30>, capture_output=True)`.
      Non-zero exit OR timeout -> rollback.

Stage 5 (KB marker) is delegated to the `mark` CLI subcommand; see design C-7.

Every stage emits a "[promote-pattern] Stage N: <label>" line to stderr so
the skill orchestrator can show progress via Bash stderr capture.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from pattern_promotion.kb_parser import KBEntry
from pattern_promotion.types import DiffPlan, FileEdit, Result


# ---------------------------------------------------------------------------
# Constants / environment
# ---------------------------------------------------------------------------

_TIMEOUT_ENV = "PATTERN_PROMOTION_HOOK_TEST_TIMEOUT"
_DEFAULT_TIMEOUT_SECS = 30

# Marker patterns per TD-8. Both the bash-comment form and the HTML-comment
# form contain the literal `Promoted` adjacent to the entry name.
_BASH_MARKER_RE = re.compile(r"^\s*#\s*Promoted\s+from\s+KB\s+entry\s*:\s*(.+?)\s*$")
_MD_MARKER_RE = re.compile(r"<!--\s*Promoted\s*:\s*(.+?)\s*-->")


# ---------------------------------------------------------------------------
# Stage logging
# ---------------------------------------------------------------------------


def _log_stage(n: int, label: str) -> None:
    """Emit a stage-boundary progress line to stderr."""
    print(f"[promote-pattern] Stage {n}: {label}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------


def _is_hooks_json(path: Path) -> bool:
    return path.name == "hooks.json"


def _stage1_preflight(
    entry: KBEntry,
    diff_plan: DiffPlan,
) -> tuple[bool, Optional[str]]:
    """Run all three pre-flight checks. Return (ok, reason)."""
    # 1. file existence vs action
    for edit in diff_plan.edits:
        if edit.action == "modify":
            if not edit.path.is_file():
                return False, f"modify target does not exist: {edit.path}"
        elif edit.action == "create":
            if edit.path.exists():
                return (
                    False,
                    f"create target already exists: {edit.path}",
                )
        else:
            return False, f"unknown action {edit.action!r} for {edit.path}"

    # 2. JSON validity for any hooks.json edit (check the `after` content).
    for edit in diff_plan.edits:
        if _is_hooks_json(edit.path):
            try:
                json.loads(edit.after)
            except (ValueError, TypeError) as exc:
                return (
                    False,
                    f"patched hooks.json is not valid JSON: {exc}",
                )

    # 3. TD-8 partial-run collision detection.
    #    Scan the directories that will be touched (plus the hook-target's
    #    hooks/ dir for bash markers) for existing files carrying the same
    #    entry-name marker. Any match -> abort.
    scan_dirs: set[Path] = set()
    for edit in diff_plan.edits:
        parent = edit.path.parent
        if parent.is_dir():
            scan_dirs.add(parent)
    for d in scan_dirs:
        # Only scan files at the top level of each touched directory;
        # avoid recursive walks on large trees.
        try:
            candidates = list(d.iterdir())
        except OSError:
            continue
        for cand in candidates:
            if not cand.is_file():
                continue
            # Ignore the files that this plan itself will create/modify — a
            # modify target legitimately pre-exists, and its pre-image content
            # is what we compare against the TD-8 marker.
            if cand in {e.path for e in diff_plan.edits}:
                # Allow modify targets: only a pre-existing marker for a
                # DIFFERENT action would indicate partial-run state.
                # But collision is really about OTHER files not in this plan,
                # so skip these.
                continue
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Fast-path pre-filter: skip anything without `Promoted` substring.
            if "Promoted" not in text:
                continue
            # Match either dialect against the entry name.
            for line in text.splitlines():
                m = _BASH_MARKER_RE.match(line)
                if m and m.group(1).strip() == entry.name.strip():
                    return (
                        False,
                        (
                            f"possible prior partial run: found TD-8 marker "
                            f"for {entry.name!r} in {cand}"
                        ),
                    )
            for m in _MD_MARKER_RE.finditer(text):
                if m.group(1).strip() == entry.name.strip():
                    return (
                        False,
                        (
                            f"possible prior partial run: found TD-8 marker "
                            f"for {entry.name!r} in {cand}"
                        ),
                    )

    return True, None


# ---------------------------------------------------------------------------
# Stage 2 / 3 — snapshot + write
# ---------------------------------------------------------------------------


def _stage2_snapshot(diff_plan: DiffPlan) -> dict[Path, Optional[str]]:
    """Record pre-image content for every edit.

    Maps path -> original content (modify) or None (create).
    """
    snapshot: dict[Path, Optional[str]] = {}
    for edit in diff_plan.edits:
        if edit.action == "modify":
            snapshot[edit.path] = edit.path.read_text(encoding="utf-8")
        else:
            snapshot[edit.path] = None
    return snapshot


def _stage3_write(
    diff_plan: DiffPlan,
) -> tuple[bool, Optional[str], list[FileEdit]]:
    """Write in ascending write_order (ties broken by path).

    Returns (ok, reason, applied_edits). `applied_edits` lists the edits that
    were successfully written up to (and not including) the failing one — used
    by rollback.
    """
    applied: list[FileEdit] = []
    ordered = sorted(diff_plan.edits, key=lambda e: (e.write_order, str(e.path)))
    for edit in ordered:
        try:
            edit.path.parent.mkdir(parents=True, exist_ok=True)
            edit.path.write_text(edit.after, encoding="utf-8")
            applied.append(edit)
        except Exception as exc:  # deliberate: any failure = abort
            return False, f"write failed for {edit.path}: {exc}", applied
    return True, None, applied


def _rollback(
    snapshot: dict[Path, Optional[str]],
    applied: list[FileEdit],
) -> None:
    """Reverse every applied edit using the snapshot.

    For modify: write back the original content.
    For create: unlink the created file (if it exists).
    Rollback must be best-effort — per-file failures are logged to stderr but
    do not re-raise (otherwise rollback errors would mask the original cause).
    """
    for edit in reversed(applied):
        try:
            original = snapshot.get(edit.path)
            if edit.action == "create":
                if edit.path.exists():
                    edit.path.unlink()
            else:  # modify
                if original is not None:
                    edit.path.write_text(original, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - rollback-of-rollback
            print(
                f"[promote-pattern] rollback warning for {edit.path}: {exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Stage 4 — post-write validation
# ---------------------------------------------------------------------------


def _hook_test_script_path(diff_plan: DiffPlan) -> Optional[Path]:
    """Return the test script path (write_order=1) for a hook DiffPlan."""
    for edit in diff_plan.edits:
        if edit.write_order == 1:
            return edit.path
    return None


def _run_hook_test_script(script: Path) -> tuple[bool, Optional[str]]:
    """Execute the generated test script with a bounded timeout.

    Returns (ok, reason). On timeout the reason mentions "timeout" so callers
    can surface it verbatim.
    """
    timeout_secs = _DEFAULT_TIMEOUT_SECS
    override = os.environ.get(_TIMEOUT_ENV)
    if override:
        try:
            timeout_secs = int(override)
        except ValueError:
            pass  # use default; bad env values are not fatal
    try:
        proc = subprocess.run(
            ["bash", str(script)],
            timeout=timeout_secs,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return (
            False,
            f"hook test script timeout after {timeout_secs}s: {script}",
        )
    except FileNotFoundError as exc:
        return False, f"hook test script not found: {exc}"
    except OSError as exc:
        return False, f"hook test script failed to execute: {exc}"
    if proc.returncode != 0:
        snippet = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
        tail = snippet[0] if snippet else ""
        return (
            False,
            f"hook test script exited {proc.returncode}: {tail}",
        )
    return True, None


def _stage4_validate(
    diff_plan: DiffPlan, target_type: str
) -> tuple[bool, Optional[str]]:
    """Post-write validation: existence + re-parse + (hook) test script."""
    # 1. Every edited path must exist.
    for edit in diff_plan.edits:
        if not edit.path.is_file():
            return False, f"post-write file missing: {edit.path}"

    # 2. hooks.json must re-parse as JSON.
    for edit in diff_plan.edits:
        if _is_hooks_json(edit.path):
            try:
                json.loads(edit.path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                return (
                    False,
                    f"post-write hooks.json parse failed: {exc}",
                )

    # 3. Hook target: run the TD-7 test script.
    if target_type == "hook":
        test_script = _hook_test_script_path(diff_plan)
        if test_script is None:
            return False, "hook target missing test script (write_order=1)"
        ok, reason = _run_hook_test_script(test_script)
        if not ok:
            return False, reason

    return True, None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def apply(
    entry: KBEntry,
    diff_plan: DiffPlan,
    target_type: str,
) -> Result:
    """Run Stages 1-4 atomically. Return Result with success + rollback flags.

    On Stage 1 failure: returns (success=False, rolled_back=False) because no
    writes were performed.
    On Stage 2/3/4 failure: rollback runs and returns rolled_back=True.
    """
    # ---- Stage 1
    _log_stage(1, "pre-flight validation")
    ok, reason = _stage1_preflight(entry, diff_plan)
    if not ok:
        return Result(
            success=False,
            target_path=None,
            reason=reason,
            rolled_back=False,
            stage_completed=1,
        )

    # ---- Stage 2
    _log_stage(2, "snapshot")
    try:
        snapshot = _stage2_snapshot(diff_plan)
    except Exception as exc:
        return Result(
            success=False,
            target_path=None,
            reason=f"snapshot failed: {exc}",
            rolled_back=False,
            stage_completed=2,
        )

    # ---- Stage 3
    _log_stage(3, "write")
    ok, reason, applied = _stage3_write(diff_plan)
    if not ok:
        print(
            f"[promote-pattern] rollback: {reason}",
            file=sys.stderr,
        )
        _rollback(snapshot, applied)
        return Result(
            success=False,
            target_path=None,
            reason=reason,
            rolled_back=True,
            stage_completed=3,
        )

    # ---- Stage 4
    _log_stage(4, "post-write validation")
    ok, reason = _stage4_validate(diff_plan, target_type)
    if not ok:
        print(
            f"[promote-pattern] rollback: {reason}",
            file=sys.stderr,
        )
        _rollback(snapshot, applied)
        return Result(
            success=False,
            target_path=None,
            reason=reason,
            rolled_back=True,
            stage_completed=4,
        )

    return Result(
        success=True,
        target_path=diff_plan.target_path,
        reason=None,
        rolled_back=False,
        stage_completed=4,
    )
