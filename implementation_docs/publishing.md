# Publishing the packages

Not done yet: this is how, and what is checked. Nothing here uploads by itself.

## What a client needs

A client of a project's API (the generated SDK, `pangloss-sdk`) needs three packages, and nothing else of Pangloss: **`pangloss-core`, `pangloss-models`, `pangloss-sdk`** (with `pydantic`, `frozendict`, `httpx2`, `pydantic-settings` and what they need; `pangloss-sdk[keyring]` adds `keyring`). They have to be on an index for `pip install <project>-sdk` to work, as the generated package depends on `pangloss-sdk==<the version the server has>`. The server side (`pangloss-api`, `-cli`, `-memgraph`, `-users`, `-history`, `-interface`, `-sdk-server`) is built the same way; the SDK does not need it.

Until they are, install the three from this repository (a path or `git+https://github.com/richardhadden/pangloss-monorepo#subdirectory=packages/pangloss-sdk`, and the same for the other two), or set `SDK_REQUIREMENT` in the project's settings to the requirement the generated package should have.

## Build and check

```bash
uv build --all-packages --out-dir dist       # a wheel and an sdist for each (uv_build or hatchling)

# the client in a new environment, from what was built (the dependencies come from the index)
uv venv --python 3.15 /tmp/check && uv pip install --python /tmp/check/bin/python --find-links dist pangloss-sdk
```

Tried on 2026-10-23: `pangloss-sdk` installs from the built wheels with `pangloss-core` and `pangloss-models` (and no `neo4j`, no FastAPI), the demo's generated SDK installs on top of it, `connect_offline()` makes the models, and `pangloss-sdk sync-stubs` and `update` run.

## Before an upload

- **A licence.** There is no `LICENSE` file and no `license` in any `pyproject.toml`: that is yours to choose, and an index will show "no licence". Add the file and `license = "..."` (and `license-files`) to each package.
- **Names.** `pangloss-*` on PyPI are permanent once taken: check they are free, or use a private index.
- **Versions.** All are `0.1.0`. The generated SDK pins `pangloss-sdk==<version>`, so a server and its clients must be on versions that exist on the index; a change to the SDK client needs a new version of `pangloss-sdk` for the servers that use it.
- **Dependencies between packages** are unversioned (`pangloss-core`, `pangloss-models`): once published, say `pangloss-models>=0.1` so that an old `pangloss-core` is not paired with a new one.
- **READMEs** of `pangloss-core`, `-models`, `-memgraph`, `-users` and `-sdk` are one line: they are the page of the package on the index.
- **`pydantic-meta-kit`** is vendored as `pangloss_models.meta_kit` (its own repository is excluded from the workspace); check its licence allows it (see [TODO](../TODO.md)).

## Upload

```bash
uv publish --token <token> dist/pangloss_core-* dist/pangloss_models-* dist/pangloss_sdk-*   # then the rest
# a private index: uv publish --publish-url https://... --token ...
```

Upload in dependency order (`pangloss-core`, `pangloss-models`, `pangloss-users`, `pangloss-memgraph`, `pangloss-sdk`, `pangloss-api`, then the others). An upload cannot be replaced: a mistake is a new version.
