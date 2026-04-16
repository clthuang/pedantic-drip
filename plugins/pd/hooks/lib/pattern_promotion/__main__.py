"""CLI entrypoint for pattern_promotion.

Five subcommands (enumerate, classify, generate, apply, mark) per design I-8.
Each emits a single JSON status object on stdout's last line and writes bulky
artifacts to the --sandbox directory. Stderr carries diagnostics and stack
traces.

Subprocess Serialization Contract (design TD-3):

- Stdout: exactly one single-line JSON object (no pretty-printing) so callers
  can `json.loads(line)` without re-joining.
- Exit codes:
    0 — success (status="ok") OR need-input (status="need-input")
    1 — usage / argparse / user-correctable errors
    2 — schema validation failure (status="error", need-input path)
    3 — apply rollback (status="error", rolled back target files)
- Sandbox files: bulky artifacts (entries.json, classifications.json,
  diff_plan.json, apply_result.json) live in the caller-provided sandbox
  directory so stdout stays terse.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


CONFIG_DEFAULT_MIN_OBSERVATIONS = 3
CONFIG_FIELD = "memory_promote_min_observations"


# ---------------------------------------------------------------------------
# Stdout status helpers
# ---------------------------------------------------------------------------


def _emit_status(
    status: str,
    *,
    summary: str = "",
    data_path: str | None = None,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """Write a single JSON status object to stdout (Subprocess Contract).

    `data_path` and purpose-specific aliases (entries_path, classifications_path,
    diff_plan_path, result_path) are merged via `extra`. Output is a single line
    (no indent) so callers can parse the final stdout line directly.
    """
    payload = {"status": status, "summary": summary}
    if data_path is not None:
        payload["data_path"] = data_path
    if error is not None:
        payload["error"] = error
    if extra:
        payload.update(extra)
    print(json.dumps(payload))


# ---------------------------------------------------------------------------
# Shared sandbox / serialization helpers
# ---------------------------------------------------------------------------


def _write_sandbox_json(path: Path, payload) -> None:
    """Write `payload` as pretty JSON into the sandbox path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _load_entries(sandbox: Path, entries_path: Path | None = None) -> list[dict]:
    """Read entries.json from either an explicit path or the sandbox default."""
    path = entries_path if entries_path is not None else sandbox / "entries.json"
    if not path.is_file():
        raise FileNotFoundError(f"entries.json not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"entries.json must be a list, got {type(data).__name__}")
    return data


def _find_entry(entries: list[dict], entry_name: str) -> dict | None:
    """Return the first entry matching `entry_name` (case-sensitive)."""
    for e in entries:
        if e.get("name") == entry_name:
            return e
    return None


def _reconstitute_entry(entry_dict: dict):
    """Rehydrate a KBEntry from its JSON-serialized form."""
    from pattern_promotion.kb_parser import KBEntry

    line_range = entry_dict.get("line_range", [0, 0])
    if isinstance(line_range, list):
        line_range = tuple(line_range)  # JSON arrays -> tuple for the dataclass
    return KBEntry(
        name=entry_dict["name"],
        description=entry_dict.get("description", ""),
        confidence=entry_dict.get("confidence", "n/a"),
        effective_observation_count=int(
            entry_dict.get("effective_observation_count", 0)
        ),
        category=entry_dict.get("category", ""),
        file_path=Path(entry_dict.get("file_path", "")),
        line_range=line_range,
    )


def _serialize_file_edit(edit) -> dict:
    """Serialize a FileEdit to a JSON-friendly dict."""
    return {
        "path": str(edit.path),
        "action": edit.action,
        "before": edit.before,
        "after": edit.after,
        "write_order": edit.write_order,
    }


def _serialize_diff_plan(plan) -> dict:
    """Serialize a DiffPlan to a JSON-friendly dict."""
    return {
        "edits": [_serialize_file_edit(e) for e in plan.edits],
        "target_type": plan.target_type,
        "target_path": str(plan.target_path),
    }


def _deserialize_diff_plan(data: dict):
    """Rehydrate a DiffPlan + FileEdits from their JSON-serialized form."""
    from pattern_promotion.types import DiffPlan, FileEdit

    edits: list[FileEdit] = []
    for e in data.get("edits", []):
        edits.append(
            FileEdit(
                path=Path(e["path"]),
                action=e["action"],
                before=e.get("before"),
                after=e["after"],
                write_order=int(e["write_order"]),
            )
        )
    return DiffPlan(
        edits=edits,
        target_type=data["target_type"],
        target_path=Path(data["target_path"]),
    )


# ---------------------------------------------------------------------------
# Config resolution (Task 1.8)
# ---------------------------------------------------------------------------


def _read_min_observations_from_config(config_path: Path) -> int | None:
    """Minimal YAML parse: find `memory_promote_min_observations: N`.

    Returns None if the file is missing or the field is not present.
    Inline grep — no external YAML dependency per task spec.
    """
    if not config_path.is_file():
        return None
    pattern = re.compile(
        rf"^\s*{re.escape(CONFIG_FIELD)}\s*:\s*(\d+)\s*$", re.MULTILINE
    )
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _resolve_min_observations(
    cli_value: int | None, project_root: Path | None = None
) -> int:
    """Resolve --min-observations with config fallback.

    Priority: CLI flag > `.claude/pd.local.md` in project_root > default 3.
    """
    if cli_value is not None:
        return cli_value
    root = project_root if project_root is not None else Path.cwd()
    config_path = root / ".claude" / "pd.local.md"
    from_config = _read_min_observations_from_config(config_path)
    if from_config is not None:
        return from_config
    return CONFIG_DEFAULT_MIN_OBSERVATIONS


# ---------------------------------------------------------------------------
# Task 4a.1 — enumerate
# ---------------------------------------------------------------------------


def _cmd_enumerate(args: argparse.Namespace) -> int:
    sandbox = Path(args.sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)

    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    min_obs = _resolve_min_observations(args.min_observations, project_root)

    try:
        from pattern_promotion.kb_parser import enumerate_qualifying_entries
    except ImportError as exc:
        _emit_status("error", error=f"kb_parser unavailable: {exc}")
        return 1

    try:
        entries = enumerate_qualifying_entries(Path(args.kb_dir), min_obs)
    except Exception as exc:
        _emit_status("error", error=f"enumerate failed: {exc}")
        return 1

    data_path = sandbox / "entries.json"
    serialized = [
        {
            "name": e.name,
            "description": e.description,
            "confidence": e.confidence,
            "effective_observation_count": e.effective_observation_count,
            "category": e.category,
            "file_path": str(e.file_path),
            "line_range": list(e.line_range),
        }
        for e in entries
    ]
    data_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    _emit_status(
        "ok",
        summary=f"{len(entries)} qualifying entries (threshold={min_obs})",
        data_path=str(data_path),
        extra={
            "count": len(entries),
            "min_observations": min_obs,
            "entries_path": str(data_path),
            "sandbox": str(sandbox),
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Task 4a.2 — classify
# ---------------------------------------------------------------------------


def _cmd_classify(args: argparse.Namespace) -> int:
    """Classify every entry in entries.json and emit classifications.json.

    Per user spec: reads `--entries` (or sandbox/entries.json fallback),
    calls `classify_keywords` + `decide_target` per entry, writes a list of
    `{entry_name, scores, winner, tied}` records.
    """
    sandbox = Path(args.sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)

    entries_arg = getattr(args, "entries", None)
    entries_path = Path(entries_arg) if entries_arg else sandbox / "entries.json"
    try:
        entries = _load_entries(sandbox, entries_path)
    except (FileNotFoundError, ValueError) as exc:
        _emit_status("error", error=str(exc))
        return 1

    try:
        from pattern_promotion.classifier import classify_keywords, decide_target
    except ImportError as exc:
        _emit_status("error", error=f"classifier unavailable: {exc}")
        return 1

    classifications: list[dict] = []
    for entry_dict in entries:
        kb_entry = _reconstitute_entry(entry_dict)
        try:
            scores = classify_keywords(kb_entry)
        except Exception as exc:
            _emit_status("error", error=f"classify_keywords failed: {exc}")
            return 1
        winner = decide_target(scores)
        max_score = max(scores.values()) if scores else 0
        tied = (
            max_score > 0
            and sum(1 for s in scores.values() if s == max_score) >= 2
        )
        classifications.append(
            {
                "entry_name": kb_entry.name,
                "scores": scores,
                "winner": winner,
                "tied": tied,
            }
        )

    out_path = sandbox / "classifications.json"
    _write_sandbox_json(out_path, classifications)

    _emit_status(
        "ok",
        summary=f"classified {len(classifications)} entries",
        data_path=str(out_path),
        extra={
            "count": len(classifications),
            "classifications_path": str(out_path),
            "sandbox": str(sandbox),
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Task 4a.3 — generate
# ---------------------------------------------------------------------------


_GENERATOR_MODULES = {
    "hook": "pattern_promotion.generators.hook",
    "skill": "pattern_promotion.generators.skill",
    "agent": "pattern_promotion.generators.agent",
    "command": "pattern_promotion.generators.command",
}


def _import_generator(target_type: str):
    """Dynamically import the per-target generator module."""
    import importlib

    module_name = _GENERATOR_MODULES[target_type]
    return importlib.import_module(module_name)


def _validate_target_meta(target_type: str, generator, target_meta: dict):
    """Invoke the generator's validator and normalize the return tuple.

    Hook validates the nested `feasibility` dict; skill/agent/command validate
    `target_meta` directly.
    """
    if target_type == "hook":
        feasibility = target_meta.get("feasibility")
        if feasibility is None:
            return False, "target_meta missing required key: 'feasibility'"
        return generator.validate_feasibility(feasibility)
    return generator.validate_target_meta(target_meta)


def _cmd_generate(args: argparse.Namespace) -> int:
    """Route to the per-target generator; emit DiffPlan to sandbox."""
    sandbox = Path(args.sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)

    # Load entry from sandbox/entries.json by name.
    try:
        entries = _load_entries(sandbox)
    except (FileNotFoundError, ValueError) as exc:
        _emit_status("error", error=str(exc))
        return 1

    entry_dict = _find_entry(entries, args.entry_name)
    if entry_dict is None:
        _emit_status(
            "error",
            error=(
                f"entry {args.entry_name!r} not found in entries.json "
                f"(available: {[e.get('name') for e in entries]})"
            ),
        )
        return 1

    # Load target_meta from the provided JSON file.
    meta_path = Path(args.target_meta_json)
    if not meta_path.is_file():
        _emit_status("error", error=f"--target-meta-json not found: {meta_path}")
        return 1
    try:
        target_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit_status("error", error=f"--target-meta-json parse failed: {exc}")
        return 1
    if not isinstance(target_meta, dict):
        _emit_status(
            "error", error="--target-meta-json must be a JSON object"
        )
        return 1

    # Import the right generator and pre-validate.
    try:
        generator = _import_generator(args.target_type)
    except ImportError as exc:
        _emit_status("error", error=f"generator unavailable: {exc}")
        return 1

    ok, reason = _validate_target_meta(args.target_type, generator, target_meta)
    if not ok:
        # Schema failure — skill re-asks the LLM with this reason.
        _emit_status(
            "error",
            error=reason or "target_meta validation failed",
            extra={"reason": reason or "target_meta validation failed"},
        )
        return 2

    # Delegate to generate().
    kb_entry = _reconstitute_entry(entry_dict)
    try:
        plan = generator.generate(kb_entry, target_meta)
    except ValueError as exc:
        _emit_status(
            "error",
            error=str(exc),
            extra={"reason": str(exc)},
        )
        return 2
    except Exception as exc:
        _emit_status("error", error=f"generate failed: {exc}")
        return 1

    out_path = sandbox / "diff_plan.json"
    _write_sandbox_json(out_path, _serialize_diff_plan(plan))

    _emit_status(
        "ok",
        summary=(
            f"generated {len(plan.edits)} edit(s) for {args.target_type} "
            f"target {plan.target_path}"
        ),
        data_path=str(out_path),
        extra={
            "diff_plan_path": str(out_path),
            "edit_count": len(plan.edits),
            "target_type": plan.target_type,
            "target_path": str(plan.target_path),
            "sandbox": str(sandbox),
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Task 4a.4 — apply
# ---------------------------------------------------------------------------


def _cmd_apply(args: argparse.Namespace) -> int:
    """Invoke apply.apply() and serialize the Result to the sandbox."""
    sandbox = Path(args.sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)

    # Locate diff_plan.json: explicit flag wins, else sandbox default.
    dp_arg = getattr(args, "diff_plan", None)
    dp_path = Path(dp_arg) if dp_arg else sandbox / "diff_plan.json"
    if not dp_path.is_file():
        _emit_status("error", error=f"diff_plan.json not found at {dp_path}")
        return 1

    try:
        dp_data = json.loads(dp_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit_status("error", error=f"diff_plan.json parse failed: {exc}")
        return 1

    try:
        diff_plan = _deserialize_diff_plan(dp_data)
    except (KeyError, ValueError, TypeError) as exc:
        _emit_status("error", error=f"diff_plan.json malformed: {exc}")
        return 1

    # Resolve target_type: explicit flag wins, else from diff_plan body.
    target_type = getattr(args, "target_type", None) or diff_plan.target_type

    # Reconstitute KBEntry from sandbox/entries.json by name.
    try:
        entries = _load_entries(sandbox)
    except (FileNotFoundError, ValueError) as exc:
        # entries.json is optional for apply if we have enough context —
        # construct a minimal KBEntry from the --entry-name alone.
        entries = []

    entry_dict = _find_entry(entries, args.entry_name)
    if entry_dict is None:
        # Build a minimal KBEntry so Stage 1 TD-8 scan has entry.name.
        from pattern_promotion.kb_parser import KBEntry

        kb_entry = KBEntry(
            name=args.entry_name,
            description="",
            confidence="n/a",
            effective_observation_count=0,
            category="",
            file_path=Path(""),
            line_range=(0, 0),
        )
    else:
        kb_entry = _reconstitute_entry(entry_dict)

    try:
        from pattern_promotion.apply import apply as apply_fn
    except ImportError as exc:
        _emit_status("error", error=f"apply module unavailable: {exc}")
        return 1

    try:
        result = apply_fn(kb_entry, diff_plan, target_type=target_type)
    except Exception as exc:
        _emit_status("error", error=f"apply crashed: {exc}")
        return 1

    # Serialize Result to sandbox.
    result_payload = {
        "success": result.success,
        "target_path": str(result.target_path) if result.target_path else None,
        "reason": result.reason,
        "rolled_back": result.rolled_back,
        "stage_completed": result.stage_completed,
    }
    out_path = sandbox / "apply_result.json"
    _write_sandbox_json(out_path, result_payload)

    if result.success:
        _emit_status(
            "ok",
            summary=(
                f"apply succeeded at stage {result.stage_completed} "
                f"-> {result.target_path}"
            ),
            data_path=str(out_path),
            extra={
                "result_path": str(out_path),
                "stage_completed": result.stage_completed,
                "target_path": str(result.target_path)
                if result.target_path
                else None,
                "sandbox": str(sandbox),
            },
        )
        return 0

    # Rollback / error paths.
    _emit_status(
        "error",
        summary=(
            f"apply failed at stage {result.stage_completed}: {result.reason}"
        ),
        data_path=str(out_path),
        error=result.reason or "apply failed",
        extra={
            "result_path": str(out_path),
            "stage": str(result.stage_completed),
            "rolled_back": result.rolled_back,
            "reason": result.reason or "apply failed",
            "sandbox": str(sandbox),
        },
    )
    return 3


# ---------------------------------------------------------------------------
# mark (Task 3.6 — already implemented, retained)
# ---------------------------------------------------------------------------


def _cmd_mark(args: argparse.Namespace) -> int:
    """Wire the `mark` subcommand to kb_parser.mark_entry (Task 3.6).

    Delegates all insertion logic to kb_parser (Task 1.4). This subcommand
    exists solely to expose that helper over the Subprocess Serialization
    Contract so the skill orchestrator can invoke it after `apply` succeeds.
    """
    try:
        from pattern_promotion.kb_parser import mark_entry
    except ImportError as exc:
        _emit_status("error", error=f"kb_parser unavailable: {exc}")
        return 1

    kb_file = Path(args.kb_file)
    if not kb_file.is_file():
        _emit_status("error", error=f"KB file not found: {kb_file}")
        return 1

    try:
        mark_entry(
            kb_file,
            args.entry_name,
            args.target_type,
            args.target_path,
        )
    except ValueError as exc:
        # Entry-not-found is a user-correctable error, not a crash.
        _emit_status("error", error=str(exc))
        return 1
    except Exception as exc:
        _emit_status("error", error=f"mark failed: {exc}")
        return 1

    _emit_status(
        "ok",
        summary=(
            f"marked {args.entry_name!r} -> {args.target_type}:{args.target_path}"
        ),
        extra={
            "kb_file": str(kb_file),
            "entry_name": args.entry_name,
            "target_type": args.target_type,
            "target_path": args.target_path,
        },
    )
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pattern_promotion",
        description="Promote KB patterns to hooks/skills/agents/commands",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_enum = sub.add_parser(
        "enumerate", help="List KB entries meeting promotion criteria"
    )
    p_enum.add_argument("--sandbox", required=True, help="Sandbox directory")
    p_enum.add_argument("--kb-dir", required=True, help="Knowledge bank directory")
    p_enum.add_argument(
        "--min-observations",
        type=int,
        default=None,
        help="Override effective_observation_count threshold",
    )
    p_enum.add_argument(
        "--project-root",
        default=None,
        help="Project root for .claude/pd.local.md resolution (default: cwd)",
    )

    p_classify = sub.add_parser(
        "classify", help="Score KB entries against the keyword table"
    )
    p_classify.add_argument("--sandbox", required=True)
    p_classify.add_argument(
        "--entries",
        default=None,
        help="Path to entries.json (default: <sandbox>/entries.json)",
    )

    p_gen = sub.add_parser(
        "generate", help="Generate a DiffPlan for a target type"
    )
    p_gen.add_argument("--sandbox", required=True)
    p_gen.add_argument("--entry-name", required=True)
    p_gen.add_argument(
        "--target-type",
        required=True,
        choices=["hook", "skill", "agent", "command"],
    )
    p_gen.add_argument(
        "--target-meta-json",
        required=True,
        help="Path to JSON file with target_meta (feasibility for hook; "
        "{skill,agent,command}_name + section/step + insertion_mode for the "
        "markdown targets)",
    )

    p_apply = sub.add_parser("apply", help="Execute the 5-stage atomic write")
    p_apply.add_argument("--sandbox", required=True)
    p_apply.add_argument("--entry-name", required=True)
    p_apply.add_argument(
        "--diff-plan",
        default=None,
        help="Path to diff_plan.json (default: <sandbox>/diff_plan.json)",
    )
    p_apply.add_argument(
        "--target-type",
        default=None,
        choices=["hook", "skill", "agent", "command"],
        help="Override target_type (default: read from diff_plan)",
    )

    p_mark = sub.add_parser("mark", help="Append `- Promoted:` marker to KB entry")
    p_mark.add_argument("--kb-file", required=True)
    p_mark.add_argument("--entry-name", required=True)
    p_mark.add_argument(
        "--target-type", required=True, choices=["hook", "skill", "agent", "command"]
    )
    p_mark.add_argument("--target-path", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_package_on_path()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "enumerate":
        return _cmd_enumerate(args)
    if args.cmd == "classify":
        return _cmd_classify(args)
    if args.cmd == "generate":
        return _cmd_generate(args)
    if args.cmd == "apply":
        return _cmd_apply(args)
    if args.cmd == "mark":
        return _cmd_mark(args)
    parser.error(f"Unknown subcommand: {args.cmd}")
    return 2  # pragma: no cover


def _ensure_package_on_path() -> None:
    """Make sibling modules importable when run as `python -m pattern_promotion`."""
    lib_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)


if __name__ == "__main__":
    sys.exit(main())
