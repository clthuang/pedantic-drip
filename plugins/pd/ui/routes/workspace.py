"""Workspace-select route — sets the workspace-scope cookie (feature 130)."""

from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ui.routes.helpers import COOKIE_NAME, _is_uuid_shaped

router = APIRouter()


def _safe_referer_path(referer: str | None) -> str:
    """Return a same-origin ``path[?query]`` to redirect back to.

    The ``if not referer`` guard MUST run first: ``urlsplit(None)``
    silently returns a bytes ``SplitResult`` (verified empirically) rather
    than raising, and the concat/startswith logic below would then
    TypeError on that bytes value -- this is a mandatory guard, not
    defensive cleanup.

    Only accepts a destination that starts with a single ``/`` (rejects
    absolute URLs stripped to their path/query, and protocol-relative
    ``//host/...`` referers that a bare ``startswith("/")`` would let
    through) and contains no backslash (browsers normalize ``/\host`` to
    ``//host`` -- today Starlette percent-encodes ``\`` in Location, but
    this guard's contract must not lean on that); anything else falls
    back to ``"/"``.
    """
    if not referer:
        return "/"
    parts = urlsplit(referer)
    dest = parts.path + ("?" + parts.query if parts.query else "")
    if dest.startswith("/") and not dest.startswith("//") and "\\" not in dest:
        return dest
    return "/"


@router.get("/workspace/select")
def select_workspace(request: Request, uuid: str = "") -> RedirectResponse:
    """Set the workspace-scope cookie and redirect back to the referer.

    Malformed `uuid` values (anything other than the literal ``"*"`` or a
    canonical 36-char uuid) leave the cookie untouched -- fail quiet, since
    this is a GET that only ever mutates a cookie -- but the redirect still
    happens either way.
    """
    dest = _safe_referer_path(request.headers.get("referer"))
    response = RedirectResponse(dest, status_code=303)
    if uuid == "*" or _is_uuid_shaped(uuid):
        response.set_cookie(
            COOKIE_NAME,
            uuid,
            max_age=2592000,
            httponly=True,
            samesite="lax",
            path="/",
        )
    return response
