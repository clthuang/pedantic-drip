"""Feature 115 FR-E.2-115.1 / IF-115-4: shared interactive triage helpers.

Used by `_fix_triage_cross_workspace_link` to iterate over per-link decisions
via AskUserQuestion. Designed to be reusable by future per-item interactive
fix actions (e.g., B-H4 dry-run interactive mode if added).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def _interactive_triage_loop(
    items: list[T],
    build_question_fn: Callable[[T], dict],
    apply_fn: Callable[[T, str], None],
    ask_user_fn: Callable[[dict], str] | None = None,
) -> int:
    """Iterate over items, prompt user per item via AskUserQuestion, apply mutation.

    Parameters
    ----------
    items:
        List of per-item triage records (opaque to this helper).
    build_question_fn:
        Callable that takes an item and returns an AskUserQuestion payload dict
        (with ``question``, ``header``, ``options``, ``multiSelect`` keys).
    apply_fn:
        Callable taking ``(item, user_choice)`` that performs the per-item mutation.
    ask_user_fn:
        Callable taking the AskUserQuestion payload and returning the user's
        choice string. If None, the function returns 0 (no-op — used in tests
        and non-interactive contexts where the caller will inject the dispatch).

    Returns the count of items processed.
    """
    if ask_user_fn is None:
        return 0  # non-interactive: caller must supply ask_user_fn

    count = 0
    for item in items:
        question = build_question_fn(item)
        choice = ask_user_fn(question)
        apply_fn(item, choice)
        count += 1
    return count
