# 1. On the server

The SDK is made by an optional app, `pangloss-sdk-server`. Add it to `INSTALLED_APPS`:

```python
class Settings(BaseSettings[MemgraphDatabaseSettings]):
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "demo_app",
        "pangloss_sdk_server",
    ]
```

(`pangloss-demo` already does.) Nothing else is needed: with the defaults the server builds the SDK as it starts and
serves it under `/api/sdk`.

## Building

```bash
pangloss sdk build            # the models of the installed apps, as a package
pangloss sdk status           # what is built; exit code 2 if the models have changed since
pangloss sdk show             # the files it would contain; --diff shows what differs from the last build
```

```
pangloss-demo-sdk 0.4 built (fingerprint 5c1f0a9e47b2)
  apps: demo_app
  modules: 1
  in /…/pangloss-demo/.pangloss/sdk
```

What the build does:

1. Finds what ships: the `models` module of each app, and every module *of your project* that those import (read with
   `ast`, never run). Framework packages (`pangloss_*`) are dependencies of the SDK, not copied.
2. Writes the package: your modules as written, a `.pyi` stub for each that declares models, the `<project>_sdk` entry
   module, a manifest, a `pyproject.toml` that requires `pangloss-sdk` at this server's version and whatever third-party
   packages your models import.
3. **Checks it on a clean client** in a subprocess that is forbidden to import anything server-only: it imports the
   package, initialises the models, and compares the JSON schema of every generated model with the server's.
4. Type-checks the stubs with `ty`, if `ty` is installed.
5. Only then replaces the last build. A build that fails leaves the previous one in place, and says why.

The version is `0.<n>`, where `n` counts the builds that *changed something*. The fingerprint is a hash of the shipped
content, so building again with no change does nothing (`--force` builds anyway), and a version is never spent for
nothing.

## When it is built

| `SDK_BUILD` | |
|---|---|
| `"start"` (default) | As the server starts, in a thread; it builds only if the content changed. The server comes up even if the build fails (`/api/sdk/version` then answers 503 with the reason) |
| `"off"` | Never by itself. Run `pangloss sdk build` (as part of a deployment) |

Without either, the first request that needs the SDK builds it. Build in your deployment if you want a failed build to
stop the release, not to be found by the first user.

## Who may download it

`SDK_ACCESS` sets the login the downloads need. What the SDK reveals is the *shape* of your data model, not data.

| `SDK_ACCESS` | |
|---|---|
| `"admin"` (default) | Only administrators |
| `"user"` | Any logged-in user |
| `"public"` | Anyone |

A login is a Bearer token, the session cookie, or HTTP Basic, which is what `pip` and `git` send: a username and
password, **or a personal access token as the password**. With nothing, the answer is `401` with
`WWW-Authenticate: Basic`, so `pip`, `git` and a browser ask. Wrong passwords count towards the login limit
([REST API](../../docs/api.md)).

`GET /api/sdk/version` is open to anyone, whatever `SDK_ACCESS` says: it shows only the project, version, fingerprint
and schema position, so that a client can tell whether it is out of date.

For scripts and for `git`, give people a **personal access token** rather than a password:

```bash
pangloss users tokens create ada --name "import scripts" --scope write --expires-days 90
pangloss users tokens list ada
pangloss users tokens revoke ada <token id>
```

The token (`pgl_…`) is printed once. Scope `read` can only read. People can make their own, too:
`POST /api/users/me/tokens`.

## What is served

| | |
|---|---|
| `GET /api/sdk` | The manifest, the build time, the download URLs (`SDK_ACCESS`) |
| `GET /api/sdk/download/<file>` | The wheel and the sdist, under their real file names |
| `/api/sdk/git` | A **read-only** git repository: `git clone`, `fetch`, `pull`. A push is refused with 403. Each build that changed something is a commit tagged `v<version>`, so `git log -p` is the history of your schema |
| `/api/sdk/simple/` | A PEP 503 package index with the one project, for `pip --extra-index-url` |

## Settings

All optional, on the project's settings class.

| Setting | Default | |
|---|---|---|
| `SDK_ACCESS` | `"admin"` | Above |
| `SDK_BUILD` | `"start"` | Above |
| `SDK_APPS` | every installed app that is not a framework package and declares models | Which apps ship |
| `SDK_EXCLUDE_APPS` | `[]` | Apps left out |
| `SDK_NAME` | `<project>-sdk` | The distribution name |
| `SDK_REQUIREMENT` | `pangloss-sdk==<this version>` | What the SDK requires of the client library. Change it if the client library comes from your own index |
| `SDK_EXTRA_REQUIREMENTS` | `[]` | More requirements |
| `SDK_OUTPUT` | `.pangloss/sdk` | Where it is built (the bare git repository is here too) |
| `SDK_TYPECHECK` | `"auto"` | Run `ty` over the stubs if found; `"required"` fails the build without it; `"off"` |
| `SDK_STALE_WRITES` | `"refuse"` | What to do with a write from a client whose models are older than the server's: refuse it (409), or `"warn"` and let it through ([chapter 4](04-current.md)) |
| `SDK_ROOT` | found from the working directory | The project directory |

Behind a reverse proxy, let `/api/sdk/git` through with `Authorization` headers intact, and do not cache `/api/sdk`.

## An existing database

The SDK uses personal access tokens and revoked sessions, which have indexes made by a library migration. If you
update an old project, run `pangloss migrate` before starting the server (the server says so if it is pending).
