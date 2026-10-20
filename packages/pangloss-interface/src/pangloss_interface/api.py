"""Endpoints that the interface needs, beyond the REST API of the models.

`pangloss-api` includes the `router` of the `api` module of each installed app. These are
under `/api/interface`, so that the interface need only pass `/api` on to the API.

Nothing is done here yet. What is planned (see docs/interface.md, "Sessions"): the
interface does not keep the JWT of a user in the browser. It asks here for a session,
which is an opaque token in an HTTP-only cookie that the API can look up (and revoke), and
the interface's server uses it to act for the user.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/interface", tags=["interface"])


def not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/health")
async def health() -> dict[str, str]:
    """That the API has the interface's endpoints"""
    return {"status": "ok"}


@router.post("/session")
async def start_session() -> None:
    """Log in: an opaque session token, in a cookie"""
    raise not_implemented()


@router.get("/session")
async def get_session() -> None:
    """Who the session is for"""
    raise not_implemented()


@router.delete("/session")
async def end_session() -> None:
    """Log out: the session is ended, here as well as in the browser"""
    raise not_implemented()
