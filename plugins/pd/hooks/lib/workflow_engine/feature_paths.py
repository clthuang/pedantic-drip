"""Name a feature's directory without taking its type_id apart (C11).

A feature's artifacts live in ``{artifacts_root}/features/<name>``. Every
writer names that directory by the feature's entity_id: the phase commands,
the hooks and doctor.sh all use ``features/{id}-{slug}``. The readers here
take the name from the same place:

1. **Registry:** the feature row's stored ``entities.entity_id`` column
   (``EntityDatabase.feature_entity_id``).
2. **Listing:** with no row, or with no db (degraded mode), the entry of
   ``{artifacts_root}/features`` whose ``"feature:" + name`` equals the
   type_id. That is a whole-string, case-sensitive comparison: the type_id
   is composed from the listed name, never parsed.

Either way the name passes ``check_feature_dir_name``. Joining it under
``features/`` and checking where it resolves is ``contained_feature_dir``,
the one owner of that containment check (the engine's
``_contained_feature_dir_name`` calls it); ``feature_dir_path`` does both
steps.
"""
from __future__ import annotations

import os
import unicodedata

from entity_registry.database import EntityDatabase


def check_feature_dir_name(name: str) -> str:
    """Return *name* if it is one safe path component, else raise.

    Refused: empty, ``.``, ``..``, and any name holding ``/``, ``\\``, NUL
    or another control character (Unicode category Cc). Such a name can
    come only from a corrupt ``entity_id`` or a hostile listing entry.

    Raises ``ValueError("feature_not_found: <name!r> is not a single path
    component (path traversal blocked)")``.
    """
    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or "\0" in name
        or any(unicodedata.category(ch) == "Cc" for ch in name)
    ):
        raise ValueError(
            f"feature_not_found: {name!r} is not a single path component "
            "(path traversal blocked)"
        )
    return name


def _listed_feature_dir_name(artifacts_root: str, type_id: str) -> str | None:
    """The ``features/`` entry whose name composes to *type_id*, or None.

    Never raises: a missing ``features/`` directory, or any other OSError
    while listing it, is None.
    """
    try:
        with os.scandir(os.path.join(artifacts_root, "features")) as entries:
            for entry in entries:
                if "feature:" + entry.name == type_id:
                    return entry.name
    except OSError:
        return None
    return None


def feature_dir_name(
    db: EntityDatabase | None, artifacts_root: str, type_id: str
) -> str | None:
    """The name of the directory under ``{artifacts_root}/features`` that
    holds the feature *type_id*, or None when nothing names one.

    With *db*, the row's ``entity_id`` column; with no row, or ``db=None``,
    the listing match (see the module docstring). The name need not exist
    on disk: existence and containment are the caller's checks.

    Raises:
        ValueError: ``feature_not_found: ...`` when the name is not one
            safe path component (``check_feature_dir_name``), or when the
            type_id's rows hold two distinct entity_ids.
        sqlite3.Error: when the registry read fails. It is not answered
            from the listing here; each caller decides (design D3c).
    """
    name = db.feature_entity_id(type_id) if db is not None else None
    if name is None:
        name = _listed_feature_dir_name(artifacts_root, type_id)
    if name is None:
        return None
    return check_feature_dir_name(name)


def contained_feature_dir(artifacts_root: str, type_id: str, name: str) -> str:
    """``{artifacts_root}/features/<name>``, when it resolves inside
    ``artifacts_root``, symlinks included.

    Defense-in-depth against path traversal. *name* is the directory name
    of the feature *type_id*, which the refusal names. The directory need
    not exist.

    Raises ``ValueError("Invalid feature_type_id (path traversal):
    <type_id>")``.
    """
    path = os.path.join(artifacts_root, "features", name)
    root = os.path.realpath(artifacts_root)
    if not os.path.realpath(path).startswith(root + os.sep):
        raise ValueError(f"Invalid feature_type_id (path traversal): {type_id}")
    return path


def feature_dir_path(
    db: EntityDatabase | None, artifacts_root: str, type_id: str
) -> str | None:
    """``{artifacts_root}/features/<name>`` for the feature *type_id*, or
    None when nothing names a directory.

    The name is ``feature_dir_name``'s, and the path passes
    ``contained_feature_dir``, the containment check the engine makes. The
    directory need not exist; existence is the caller's check. Callers that
    must not follow a stored ``artifact_path`` into another checkout name
    the directory here instead (W2).

    Raises:
        ValueError: ``feature_dir_name``'s refusals (``feature_not_found:
            ...``), or ``Invalid feature_type_id (path traversal): ...``
            when the path resolves outside ``artifacts_root``.
        sqlite3.Error: when the registry read fails.
    """
    name = feature_dir_name(db, artifacts_root, type_id)
    if name is None:
        return None
    return contained_feature_dir(artifacts_root, type_id, name)
