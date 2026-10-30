# The SDK: your project's models, in your own scripts

A Pangloss project is a server: its models, its database, its API. Most work with the data is not done *inside* that
project. It is a script that imports a spreadsheet, a notebook that counts things, a data fix, a report. The SDK is how
those scripts use the project.

The server **builds a package from your models** and serves it. You install it in the environment of the script, and
write what you would write on the server:

```python
import pangloss_demo_sdk as sdk

sdk.connect("https://pangloss.example.org")

from demo_app.models import Person          # the project's own module, under its own name

person = await Person.get(some_id)           # a request to the API
saved = await Person.Create(label="Ada", ...).save()
```

The classes are the project's own: `Person.Create` validates as it does on the server, `isinstance` works, and the type
checker knows every field. What differs is where the work is done. `get`, `list`, `search`, `save`, `delete` and the
rest are requests to the server's REST API. **The script needs no database driver, no database password, and no copy of
the project**: only a login.

| | |
|---|---|
| [1. On the server](01-server.md) | Turn the SDK on, build it, decide who may download it |
| [2. Installing it](02-install.md) | `git clone`, `pip install` from the server, a package index; a clean environment |
| [3. In your scripts](03-scripts.md) | `connect`, logging in, reading, writing, searching, errors, unattended jobs, notebooks |
| [4. Staying current](04-current.md) | When the models change; `pangloss-sdk update`; type checking; things that do not belong in the SDK |

A script using all of this, run against the demo project, is [`sdk-demo/`](../../sdk-demo/README.md). The design and
the history of how it was built are in [the SDK reference](../../docs/sdk.md).

## What is, and is not, in the SDK

In it: the declared model classes of your apps (and the modules of your project they import), with `.pyi` type stubs;
`connect`; a manifest that says which build this is.

Not in it: settings, `.env`, migrations, your populate scripts, anything outside the models' imports. A model module
that imports something only the server has (the database driver, FastAPI, a helper that connects at import time) stops
the build, and the message names the module: see [Server-only code](04-current.md#code-that-belongs-on-the-server).

## Two things to know first

- **Python 3.15** on the client as well: the models use `lazy from ... import`.
- The SDK ships `demo_app.models`, not a renamed copy, so **the SDK and the project itself cannot be installed in one
  environment**. A script on a machine that already has the project's source should simply use the project.
