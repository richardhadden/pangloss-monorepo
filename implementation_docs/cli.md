# Command line

The `pangloss` command is provided by the `pangloss-cli` package. Core commands are built in; an installed app can add its own.

```
pangloss --help
pangloss setup-database
pangloss users create
pangloss memgraph info
```

## Making a project and its apps

```
mkdir my-site && cd my-site
pangloss new-project my_site
pangloss new-app blog
```

`pangloss new-project <name>`, run in a directory, makes the project there. The name must be a valid Python name that is not already a module (`my_site`, not `my-site`).

| Made | |
|------|--|
| `<name>/settings.py` | The project's `Settings` (for Memgraph), with `INSTALLED_APPS = ["pangloss_memgraph"]` |
| `<name>/__init__.py` | |
| `pyproject.toml` | With `[tool.pangloss] settings = "<name>.settings"` (see below). If there is one already, the section is added to it; if it already has that section, the command refuses |
| `.env` | `AUTHJWT_SECRET_KEY` with a new random value (added to an existing `.env` that lacks it). It is not in `settings.py`, which is read for it |
| `.gitignore` | Keeps `.env` out of version control (created, or `.env` added to it) |

Nothing is overwritten: if anything cannot be made, nothing is written. Add the Pangloss packages you use to the dependencies in `pyproject.toml`.

`pangloss new-app <name>`, run anywhere in the project, makes an app for your own models next to the settings' project: `<name>/__init__.py` and `<name>/models.py`, and adds `"<name>"` to `INSTALLED_APPS` in the settings. The settings file is edited only if `INSTALLED_APPS` is a plain list of strings; otherwise the app is still made, and the command says to add it yourself. Declare the models in `<name>/models.py`: it is imported by `pangloss setup-database` and when the API starts.

## Finding the project

The settings are found, in this order, from:

1. `--settings <module>` on the command line
2. the environment variable `PANGLOSS_SETTINGS`
3. `settings` under `[tool.pangloss]` in the `pyproject.toml` of the current directory, or of the nearest directory above it that has one:

```toml
[tool.pangloss]
settings = "my_project.settings"
```

The module is imported, and so constructs the project's `BaseSettings` subclass (see [Settings](settings.md)). Without a project, `pangloss --help` and the like still work; a command that needs one says that no settings were found (or why they could not be loaded).

## The commands

**Every command, grouped by the package it comes from, is listed in [the guide](../guide/cli.md)**; `--help` on any
command gives its options. This page is how the command line works.

Errors a person can fix (no such user, a mistake in the models, no settings) are shown as a message, with exit
status 1, not as a traceback.

## Commands from installed apps

Each name in `INSTALLED_APPS` is the name of a package. If it has a module `cli.py` with a `typer.Typer` object named `cli`, that is added to the command line, named after the Typer object (`typer.Typer(name="memgraph")`) or, if it has no name, after the app without a `pangloss_` prefix. `pangloss_memgraph` adds `pangloss memgraph <command>`.

An app with no `cli.py` adds nothing. An app whose `cli.py` cannot be imported, has no `cli` Typer, or has a name that is already a command, gives a warning, and the rest of the command line works.

```python
# my_app/cli.py
import typer

cli = typer.Typer(name="my-app")


@cli.command()
def hello():
    typer.echo("hello")  # pangloss my-app hello
```

An app's `models.py` (if it has one) is imported by `setup-database`, so that its models are registered.

## Running the server

`pangloss run` and `pangloss dev` start the API (see [REST API](api.md)) with uvicorn, as the factory `pangloss_api.app:create_app`. They need `pangloss-api` installed.

The server is run from the project's directory (where `pyproject.toml` is), wherever the command is typed, so `.env` and the project's imports are found. The settings module is passed to the server in the environment variable `PANGLOSS_SETTINGS`. The server imports the `models` of the installed apps and initialises them when it is built, and connects to the database when it starts; a mistake in them is shown, and the server does not start.

`pangloss dev` restarts the server when a `.py` file or `.env` changes in the project, or in an installed app that is not installed as a package (for example a Pangloss package being worked on). Environment directories (`.venv`, `venv`) are ignored. After an error such as a syntax error in a model, the server stays down, showing the traceback, and starts again when the file is fixed.

Settings are always loaded with the project's directory as the current directory, so the `.env` of the project is read whichever directory a command is run from.

## What a database backend supplies

The core commands do not know about any database. The storage backend named by `STORAGE` has a `setup` module with:

| Function | |
|----------|--|
| `create_database(settings)` | Makes the default database object (not async; does not connect). Called when the project is loaded, as `exposed_functions` needs it |
| `async connect()`, `async disconnect()` | Open and close the connection inside the event loop that runs a command |
| `async setup_database() -> list[str]` | Does the work of `pangloss setup-database`, and returns lines to show |

For Memgraph this is `pangloss_memgraph.databases.memgraph.setup`; the SDK has a stub.

## SDK commands

With `pangloss_sdk_server` in `INSTALLED_APPS` (see [the SDK](sdk.md)): `pangloss sdk build [--force]` builds the SDK of the project into `.pangloss/sdk/package` (only if the models changed, and after trying it on a clean client), `pangloss sdk status` says what is built and whether the models have changed since (exit 2 if so), and `pangloss sdk show [--diff]` lists the files, or the change since the last build.

`pangloss sdk build` also type-checks the stubs it makes (see `SDK_TYPECHECK` in [settings](settings.md)); a failure stops the build and leaves the last one.

`pangloss users tokens create|list|revoke USERNAME` makes (and shows once), lists (with when each was last used) and deletes a user's personal access tokens. The client has its own command, `pangloss-sdk login|logout|status|update|sync-stubs` (in the `pangloss-sdk` package, which does not have `pangloss`).

## Type stubs

`Person.Create`, `Person.Update`, `Person.HeadView` and the other classes of a model are made when the models are initialised, so an editor or type checker cannot see them. `pangloss make-stubs` imports the models of the installed apps, initialises them, and writes a `.pyi` file beside each module in the project that declares models (`myapp/models.pyi` next to `myapp/models.py`). In it each model has those classes as nested classes, with their fields typed (a relation is the `ReferenceSet` or `ReferenceView` of its target, an enum is the enum).

- A stub **replaces its module for a type checker**, so it has everything the module declares (classes, functions and signatures, enums, type variables), without function bodies. If the module changes, make the stubs again.
- Models in other modules of the project (imported by a `models.py`) get stubs of their own. Modules in `site-packages` or a virtual environment do not.
- The first line says the file was generated. Commit the stubs of your apps, so that everyone who clones the project (and any CI type check) has them: do not add `*.pyi` to `.gitignore`. Make them again, and commit the change, when the models change.
- The nested classes are marked `# type: ignore` where they replace the class variable of the same name in `Entity` or `Document`.
- A class that a package makes at run time and puts in your module (the entity of a typology: `RoleType` for `RoleTypology`) is in the stub, so `from myapp.models import RoleType` type-checks.
- The models of the Pangloss packages (dates, calendar, library, Zotero) have stubs of their own, shipped with the packages, so a field that holds a date is typed. (They are written by `uv run python -m pangloss_testing.framework_stubs`, in this repository.)
