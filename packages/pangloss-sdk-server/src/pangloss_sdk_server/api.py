"""Routes of the SDK, under `/api/sdk`:

| | | |
|-|-|-|
| `GET` | `/api/sdk/version` | which SDK the server has built (anyone: a client checks itself) |
| `GET` | `/api/sdk` | the manifest, and where to download it (`SDK_ACCESS`) |
| `GET` | `/api/sdk/git/...` | the SDK as a read-only git repository (`git clone`; the same access) |
| `GET` | `/api/sdk/simple/`, `/api/sdk/simple/{project}/` | a package index (PEP 503), for `pip install --extra-index-url https://user:password@host/api/sdk/simple/ NAME` (`SDK_ACCESS`) |
| `GET` | `/api/sdk/download/{file}` | the wheel or the sdist (`SDK_ACCESS`; the names are in the manifest, as an installer wants a real file name) |
"""

import hashlib
import html
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from pangloss_sdk_server import archives, current
from pangloss_sdk_server.access import sdk_access
from pangloss_sdk_server.git_endpoint import GitEndpoint
from pangloss_sdk_server.version_check import SdkVersionMiddleware

router = APIRouter(prefix="/api/sdk", tags=["sdk"])


def unavailable() -> HTTPException:
    reason = current.last_error()
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The SDK is not built" + (f": {reason}" if reason else " (pangloss sdk build)"),
    )


async def served() -> current.Current:
    built = await current.serving()
    if built is None:
        raise unavailable()
    return built


Served = Annotated[current.Current, Depends(served)]


def summary(built: current.Current) -> dict[str, Any]:
    manifest = built.manifest
    return {
        "project": manifest["project"],
        "distribution": manifest["distribution"],
        "module": manifest["module"],
        "version": manifest["version"],
        "fingerprint": built.fingerprint,
        "schemaPosition": manifest["schema_position"],
        "schemaHash": built.schema_hash,
    }


@router.get("/version", operation_id="sdk_version")
async def version(built: Served) -> dict[str, Any]:
    return summary(built)


@router.get("", dependencies=[Depends(sdk_access)], operation_id="sdk")
async def sdk(built: Served, request: Request) -> dict[str, Any]:
    manifest = built.manifest
    base = str(request.base_url).rstrip("/") + router.prefix + "/download/"
    return {
        **summary(built),
        "apps": manifest["apps"],
        "modules": manifest["modules"],
        "requires": manifest["requires"],
        "builtAt": built.built_at,
        "downloads": {
            "wheel": base + archives.wheel_name(manifest),
            "sdist": base + archives.sdist_name(manifest),
        },
    }


@router.get("/download/{filename}", dependencies=[Depends(sdk_access)], operation_id="sdk_download")
async def download(filename: str, built: Served) -> Response:
    manifest = built.manifest
    if filename == archives.wheel_name(manifest):
        content = archives.wheel_bytes(built.files, manifest)
        media_type = "application/octet-stream"
    elif filename == archives.sdist_name(manifest):
        content = archives.sdist_bytes(built.files, manifest)
        media_type = "application/gzip"
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"There is no file '{filename}'")
    return Response(
        content,
        media_type=media_type,
        headers={"ETag": f'"{built.fingerprint}"', "Content-Disposition": f'attachment; filename="{filename}"'},
    )


def normalised(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def page(title: str, links: list[str]) -> HTMLResponse:
    body = "\n".join(links)
    return HTMLResponse(
        "<!DOCTYPE html>\n<html><head><meta name=\"pypi:repository-version\" content=\"1.0\">"
        f"<title>{html.escape(title)}</title></head><body>\n{body}\n</body></html>"
    )


@router.get("/simple/", dependencies=[Depends(sdk_access)], include_in_schema=False)
async def simple_index(built: Served) -> HTMLResponse:
    name = normalised(built.manifest["distribution"])
    return page("Links for the SDK", [f'<a href="{name}/">{name}</a>'])


@router.get("/simple/{project}/", dependencies=[Depends(sdk_access)], include_in_schema=False)
async def simple_project(project: str, built: Served) -> HTMLResponse:
    """The files of the SDK, as pip looks for them (the one version the server has)"""
    manifest = built.manifest
    name = normalised(manifest["distribution"])
    if normalised(project) != name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"There is no project '{project}'")

    python = built.files.get("pyproject.toml", b"").decode()
    requires = next(
        (line.split(">=")[1].strip(' "') for line in python.splitlines() if line.startswith("requires-python")),
        None,
    )
    attribute = f' data-requires-python="{html.escape(">=" + requires)}"' if requires else ""
    files = {
        archives.wheel_name(manifest): archives.wheel_bytes(built.files, manifest),
        archives.sdist_name(manifest): archives.sdist_bytes(built.files, manifest),
    }
    links = [
        f'<a href="../../download/{file}#sha256={hashlib.sha256(content).hexdigest()}"{attribute}>{file}</a><br>'
        for file, content in files.items()
    ]
    return page(f"Links for {name}", links)


def configure_app(app: FastAPI, settings: Any) -> None:
    """(called by `pangloss-api`): say whether a client's SDK is the server's, and build as
    the server starts"""
    app.add_middleware(SdkVersionMiddleware)
    app.mount("/api/sdk/git", GitEndpoint())

    async def build_as_it_starts() -> None:
        await current.on_start(settings)

    app.state.startup_hooks.append(build_as_it_starts)
