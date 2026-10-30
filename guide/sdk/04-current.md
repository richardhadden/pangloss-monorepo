# 4. Staying current

The SDK is a snapshot of the server's models. When someone changes the models and migrates the database, an SDK built
before is out of date. The server knows, and tells the client.

## What the server does about it

Every request from a client that was connected with the generated `connect()` carries two headers: the fingerprint of its
SDK and a hash of the migrations it was built at. The answer says one of:

| Status | Means | What happens |
|---|---|---|
| `current` | This is the server's SDK | Nothing |
| `stale` | Another build, but the same schema (a change that needed no migration) | The client warns once (`PanglossSdkOutOfDateWarning`); everything works |
| `schema-changed` | The database has changed since | The client warns once. A **write** is refused with `409` (`PanglossSdkOutOfDate`) **before it reaches any route**, so an old client cannot write data the new models would not accept. A read is allowed |

`SDK_STALE_WRITES = "warn"` on the server lets those writes through instead, if you would rather. Reads, logging in and
the SDK's own routes are never refused. A client that sends no headers (a plain HTTP client) is not touched.

`await sdk.check()` asks directly (`sdk.check_sync()` in the blocking flavour). Put it at the top of a script that will
write.

## Updating

```bash
pangloss-sdk update --dry-run        # says what it would run
pangloss-sdk update                  # installs what the server has now
```

`update` finds the installed SDK and repeats the way it was installed:

| Installed from | `update` does |
|---|---|
| The server's wheel | Asks `/api/sdk/version`; if the version is new, gets the wheel and installs it |
| `git` | Installs again from the repository (a pinned revision stays pinned, and it says so) |
| The index | An upgrade by name |
| A directory (`git clone` then `pip install ./sdk`) | Nothing: it says to update the directory (`git pull`, then install again) |

It uses `uv pip` if `uv` is there, else `pip`. It uses your kept login, or asks. The real command carries the
credentials in a URL while it runs, so make sure the login is a personal access token or a short-lived one. What it
prints hides the password.

If you installed from a clone: `git pull && uv pip install ./demo-sdk`.

## Type checking

The package ships `.pyi` stubs for every module that declares models, so an editor completes `Person.Create(...)` and a
checker knows `await Person.get(id)` is `Person.HeadView | None`, `list` returns a page of reference views, and each
`save` form has its own return type. The stubs describe the **async** flavour. If you connect with `sync=True`:

```bash
pangloss-sdk sync-stubs          # writes ./typings/ with the blocking stubs
pangloss-sdk sync-stubs --remove
```

and tell your checker to look in `typings/` first: pyright does by default; mypy with `MYPYPATH=typings`; ty with

```toml
[tool.ty.environment]
extra-paths = ["typings"]
```

The server type-checks both kinds when it builds (if `ty` is installed), so a generated stub that is wrong stops the
build instead of reaching you.

## Code that belongs on the server

A model class can define validators, derived labels or helper methods. They run when models are validated, on the
client as well as on the server. That is harmless when they only compute from the data: the server never trusts the
client and validates again.

What cannot go in a module the SDK ships is anything that needs the server: a database driver, FastAPI, a helper that
connects when imported. The build refuses and names the module. Where the code has to stay in the model, mark it:

```python
from pangloss_models import server_only


class Person(Entity):
    @server_only
    def nearest_places(self):
        import neo4j                    # not followed by the build
        ...
```

In the SDK the body is replaced by `raise PanglossServerOnly("nearest_places is only available on the server")`. The
decorated function must have a body on its own line(s), not on the line of the `def`.

An app's `__init__.py` ships only if it is empty or holds docstrings, imports of its own code and `__all__`; one that
does anything else stops the build and is named.

## When it does not work

| Symptom | Cause |
|---|---|
| `PanglossNotConnected` | The model was used before `connect()`, or was imported before it |
| `ModuleNotFoundError: demo_app` | The SDK is not installed in this environment, or it is another environment |
| `ImportError` on `lazy from` | Python older than 3.15 |
| `PanglossAuthenticationRequired` in a job | No credentials in the environment (`PANGLOSS_TOKEN`), and no terminal to ask at |
| 401 from `pip` / `git` | Wrong username or password, or the user is not an admin and `SDK_ACCESS` is `"admin"`; repeated failures give 429 |
| 403 on a write | The token is `read` only |
| `PanglossSdkOutOfDate` (409) | The models have changed: `pangloss-sdk update` |
| `/api/sdk/version` is 503 | No SDK is built, or the last build failed: `pangloss sdk build` on the server shows why |
| `Cannot build the SDK: …` | A model module imports something server-only; the message names it |
| Two projects clash | One environment per project |
| `PanglossRequestError` (422) | The request is not valid for the server's models: update the SDK |

The server's log shows the build, and every login failure and write is an audit line ([Logging](../../docs/logging.md)).
