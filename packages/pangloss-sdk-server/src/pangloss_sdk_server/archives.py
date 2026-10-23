"""The built SDK as the files a Python installer takes: a wheel and an sdist, made in memory
and the same bytes for the same content (no times, no ordering from the file system).

The wheel is written here rather than by a build backend, so installing it needs nothing but
its dependencies (a build backend would be downloaded for the sdist, and not for this)."""

import base64
import gzip
import hashlib
import io
import tarfile
import zipfile
from typing import Any

# Not part of an installed package
NOT_IN_WHEEL = {"pyproject.toml", "README.md"}


def wheel_name(manifest: dict[str, Any]) -> str:
    return f"{manifest['distribution'].replace('-', '_')}-{manifest['version']}-py3-none-any.whl"


def sdist_name(manifest: dict[str, Any]) -> str:
    return f"{manifest['distribution']}-{manifest['version']}.tar.gz"


def metadata(manifest: dict[str, Any], python: str, readme: str = "") -> str:
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {manifest['distribution']}",
        f"Version: {manifest['version']}",
        f"Summary: The SDK of {manifest['project']}",
        f"Requires-Python: >={python}",
        *(f"Requires-Dist: {requirement}" for requirement in manifest["requires"]),
    ]
    return "\n".join(lines) + "\n" + (f"\n{readme}" if readme else "")


def python_of(files: dict[str, bytes]) -> str:
    for line in files["pyproject.toml"].decode().splitlines():
        if line.startswith("requires-python"):
            return line.split(">=")[1].strip(' "')
    return "3.15"


def record_line(path: str, content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
    return f"{path},sha256={digest},{len(content)}"


def wheel_bytes(files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    dist_info = f"{manifest['distribution'].replace('-', '_')}-{manifest['version']}.dist-info"
    contents = {
        path: content for path, content in files.items() if path not in NOT_IN_WHEEL
    }
    contents[f"{dist_info}/METADATA"] = metadata(manifest, python_of(files)).encode()
    contents[f"{dist_info}/WHEEL"] = (
        "Wheel-Version: 1.0\nGenerator: pangloss-sdk-server\nRoot-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    ).encode()
    record = [record_line(path, content) for path, content in sorted(contents.items())]
    record.append(f"{dist_info}/RECORD,,")
    contents[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(contents.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def sdist_bytes(files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    top = f"{manifest['distribution']}-{manifest['version']}"
    contents = dict(files)
    contents["PKG-INFO"] = metadata(
        manifest, python_of(files), files.get("README.md", b"").decode()
    ).encode()

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path, content in sorted(contents.items()):
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(content)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(content))

    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as compressed:
        compressed.write(tar_buffer.getvalue())
    return out.getvalue()
