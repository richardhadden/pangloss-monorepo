"""`git clone` of the SDK, at `/api/sdk/git`: read-only smart HTTP (upload-pack only: there is no
`receive-pack`, so nothing can be pushed), by dulwich, with the same access as the rest of the SDK.

Git asks for a username and a password when the answer is 401 with `WWW-Authenticate: Basic`,
and a credential helper then keeps them: the password can be a personal access token."""

from typing import Any

from a2wsgi import WSGIMiddleware
from dulwich.repo import Repo
from dulwich.server import DictBackend, UploadPackHandler
from dulwich.web import HTTPGitApplication
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pangloss_core import settings as core_settings
from starlette.requests import Request
from starlette.types import Receive, Scope, Send

from pangloss_sdk_server import config, current, gitrepo, publish
from pangloss_sdk_server.access import authorise


def wsgi_app_for(path: str) -> Any:
    backend = DictBackend({"/": Repo(path)})
    git = HTTPGitApplication(backend, handlers={b"git-upload-pack": UploadPackHandler})
    # (the handlers given are added to the defaults, which have `receive-pack`: take it out)
    git.handlers = {b"git-upload-pack": UploadPackHandler}
    return WSGIMiddleware(git)


def is_push(request: Request) -> bool:
    return (
        request.url.path.rstrip("/").endswith("git-receive-pack")
        or request.query_params.get("service") == "git-receive-pack"
    )


class GitEndpoint:
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        request = Request(scope, receive)
        try:
            await authorise(request)
        except HTTPException as error:
            await JSONResponse(
                {"detail": error.detail},
                status_code=error.status_code,
                headers=error.headers,
            )(scope, receive, send)
            return

        if is_push(request):
            await JSONResponse(
                {"detail": "This repository is read-only: nothing can be pushed"},
                status_code=403,
            )(scope, receive, send)
            return

        settings = core_settings.__dict__.get("SETTINGS")
        output = config.output_directory(current.find_root(settings), settings)
        repository = gitrepository(output)
        if repository is None:
            await JSONResponse(
                {"detail": "The SDK is not built (pangloss sdk build)"}, status_code=503
            )(scope, receive, send)
            return
        await wsgi_app_for(repository)(scope, receive, send)


def gitrepository(output: Any) -> str | None:
    path = gitrepo.repository_path(output)
    return (
        str(path) if (path / "HEAD").exists() and publish.read_state(output) else None
    )
