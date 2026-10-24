"""The SDK as a git repository: a bare repository of one branch, `main`, with a commit for each
build that changed the content, so `git log -p` is the history of the models as the server saw
them.

Only the files of the package are in it (never the project). A commit says the version, the
fingerprint and the schema position; each is tagged `v<version>`, and the first at a schema is
tagged `schema-<hash>` too, so a client can ask for the SDK of a given schema.
"""

import logging
import time
from pathlib import Path
from typing import Any

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo
from pangloss_sdk.schemas import schema_hash

logger = logging.getLogger("pangloss.sdk")

REPOSITORY = "sdk.git"
BRANCH = b"refs/heads/main"


def repository_path(output: Path) -> Path:
    return output / REPOSITORY


def open_repository(path: Path) -> Repo:
    if (path / "HEAD").exists():
        return Repo(str(path))
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init_bare(str(path))
    repo.refs.set_symbolic_ref(b"HEAD", BRANCH)
    return repo


def tree_of(repo: Repo, files: dict[str, bytes]) -> Tree:
    """The tree of nested directories for the files (path -> content)"""
    nested: dict[str, Any] = {}
    for path, content in files.items():
        *directories, name = path.split("/")
        level = nested
        for directory in directories:
            level = level.setdefault(directory, {})
        level[name] = content

    def build(level: dict[str, Any]) -> Tree:
        tree = Tree()
        for name, item in sorted(level.items()):
            if isinstance(item, dict):
                child = build(item)
                tree.add(name.encode(), 0o040000, child.id)
            else:
                blob = Blob.from_string(item)
                repo.object_store.add_object(blob)
                tree.add(name.encode(), 0o100644, blob.id)
        repo.object_store.add_object(tree)
        return tree

    return build(nested)


def commit_package(
    output: Path, files: dict[str, bytes], manifest: dict[str, Any]
) -> bytes | None:
    """Commit the package if it is not what the last commit has. Returns the commit, or None
    if nothing changed"""
    repo = open_repository(repository_path(output))
    try:
        tree = tree_of(repo, files)
        head = repo.refs.read_ref(BRANCH)
        if head is not None and repo[head].tree == tree.id:  # type: ignore[attr-defined]
            return None

        project = manifest["project"]
        now = int(time.time())
        commit = Commit()
        commit.tree = tree.id
        commit.parents = [head] if head else []
        commit.author = commit.committer = f"Pangloss <sdk@{project}>".encode()
        commit.author_time = commit.commit_time = now
        commit.author_timezone = commit.commit_timezone = 0
        commit.encoding = b"UTF-8"
        position = manifest["schema_position"]
        commit.message = (
            f"{manifest['distribution']} {manifest['version']}\n\n"
            f"fingerprint: {manifest['fingerprint']}\n"
            f"schema: {schema_hash(position)} {position}\n"
        ).encode()
        repo.object_store.add_object(commit)

        repo.refs[BRANCH] = commit.id
        repo.refs[f"refs/tags/v{manifest['version']}".encode()] = commit.id
        schema_tag = f"refs/tags/schema-{schema_hash(position)}".encode()
        if schema_tag not in repo.refs:
            repo.refs[schema_tag] = commit.id
        return commit.id
    finally:
        repo.close()


def commit_safely(
    output: Path, files: dict[str, bytes], manifest: dict[str, Any]
) -> None:
    """(a failure here is logged: the build itself stands)"""
    try:
        commit_package(output, files, manifest)
    except Exception:
        logger.exception("The SDK could not be committed to its git repository")
