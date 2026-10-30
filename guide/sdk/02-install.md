# 2. Installing it

You need an environment with **Python 3.15**, and a login that the server allows to download the SDK
([`SDK_ACCESS`](01-server.md#who-may-download-it)): by default an administrator's, or a personal access token made for
you.

## The client library first

The SDK requires `pangloss-sdk`, which requires `pangloss-core` and `pangloss-models`. They are not published yet
([how Pangloss is installed](../../TODO.md)), so for now install them from a checkout of the repository. This is the
whole client side: no `neo4j`, no FastAPI, no Memgraph package.

```bash
uv venv --python 3.15 .venv && source .venv/bin/activate
uv pip install /path/to/pangloss-monorepo/packages/pangloss-core \
               /path/to/pangloss-monorepo/packages/pangloss-models \
               /path/to/pangloss-monorepo/packages/pangloss-sdk
```

Add `pangloss-sdk[keyring]` if you want [a kept login](03-scripts.md#keeping-a-login) in the operating system's keyring.

## The project's SDK: three ways

All three install the same package (here `pangloss-demo-sdk`, which provides `pangloss_demo_sdk` and the project's own
`demo_app`). Replace `HOST` with the server, and use a personal access token as the password.

### `git clone` (recommended)

```bash
git clone http://HOST/api/sdk/git demo-sdk        # git asks for a username and password, once
uv pip install ./demo-sdk
```

`git pull` brings the next version, and `git log -p` shows how the models changed. The repository is read-only. To give
credentials without typing them (in a script), see how [`sdk-demo/run.sh`](../../sdk-demo/run.sh) uses `GIT_ASKPASS`,
which keeps them out of the URL and the process list.

You can also install straight from the repository:

```bash
uv pip install "git+http://USER:TOKEN@HOST/api/sdk/git"
```

### The wheel

```bash
uv pip install "http://USER:TOKEN@HOST/api/sdk/download/pangloss_demo_sdk-0.4-py3-none-any.whl"
```

The exact file name is in the manifest (`GET /api/sdk`, with a login).

### The package index

```bash
uv pip install --extra-index-url http://USER:TOKEN@HOST/api/sdk/simple/ pangloss-demo-sdk
```

Credentials in a URL are not kept in the installed package's metadata. In a `requirements.txt` or `pyproject.toml`,
prefer the index form with the credentials supplied by your tool (`UV_INDEX_…` or a `.netrc`) rather than written in a
file that is committed.

## Check that it works

```bash
python - <<'PY'
import pangloss_demo_sdk as sdk
sdk.connect("http://HOST")
import asyncio
print(asyncio.run(sdk.check()))
PY
```

`check()` asks `GET /api/sdk/version` and returns a dictionary saying whether this SDK is the server's current one. It
raises `PanglossSdkMismatch` if the server has no SDK or this is the SDK of another project.

`pangloss-sdk status http://HOST` tells you, from the command line, which login is kept and what SDK the server has.

## One environment per project

Every SDK ships the project's model modules under their real names (`demo_app.models`). Two projects with an app of the
same name cannot share an environment, and neither can the SDK and the project itself. Use one virtual environment for
each project you script against.
