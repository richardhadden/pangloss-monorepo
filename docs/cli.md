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

## Core commands

| Command | |
|---------|--|
| `pangloss new-project <name>`, `pangloss new-app <name>` | See above |
| `pangloss run [--host H] [--port P]` | Starts the API server (`127.0.0.1:8000` by default) |
| `pangloss dev [--host H] [--port P]` | The same, restarting when files change |
| `pangloss setup-database` | Imports the `models` module of each installed app, runs `initialise()`, then asks the database backend to set up what it needs (for Memgraph: indexes, uniqueness constraints, the text index and enums). Safe to repeat |
| `pangloss make-stubs [--force]` | Writes a type stub (`.pyi`) beside each module of the project that declares models, so that an editor can complete the classes made for each model (`Person.Create(...)`, `Person.HeadView`, `Person.EditView`, and so on) with their fields. Needs no database. Run it again when the models change. It does not overwrite a `.pyi` it did not write, unless `--force` is given. See [Type stubs](#type-stubs) |
| `pangloss makemigrations [--dry-run] [--check] [--noinput] [--name N]`, `makemigrations --empty <app>` | Writes migrations (`<app>/migrations/NNNN_name.py`) for what has changed in the models since the last, asking what the models cannot say: whether something was renamed, and a value for the nodes that exist where one is needed. See [Database migrations](migrations.md) |
| `pangloss squashmigrations <app> <first> <last> [--name N] [--no-optimize] [--dry-run]` | Writes one migration that does what a run of the app's do and `replaces` them (the originals are kept; a database that has had all of them or none uses it, one part way goes on with them). See [Database migrations](migrations.md) |
| `pangloss migrate [app [target]] [--plan] [--dry-run] [--check] [--fake] [--yes] [--backup|--no-backup] [--unlock] [--no-check] [--check-all] [--batch-size N]` | Applies the migrations the database has not had, and records them; then reads the data of the models they could have made unreadable. `--batch-size` makes them in batches that can be gone on from if they stop. `--dry-run` tries them in a transaction that is rolled back and says what each would do (and which would fail). `migrate <app> <target>` goes to that migration, backwards (undoing what follows, in every app) if it is applied (`zero`: all of them). `--backup` takes a Memgraph snapshot first (needed, or `--no-backup`, for changes that lose data). `--fake` records them without running them (for a database that already is as they say, such as one made before there were migrations) |
| `pangloss check-data [--type T] [--limit N]` | Reads all the data with the models as they are, and reports what cannot be read |
| `pangloss showmigrations` | The migrations of each app, and which the database has had |
| `pangloss users create` | Asks for (or takes `--username`, `--email`, `--password`, `--full-name`, `--admin/--no-admin`) the details of a new user |
| `pangloss users list` | |
| `pangloss users set-password <username>` | |
| `pangloss users make-admin <username>`, `remove-admin` | |
| `pangloss users disable <username>`, `enable` | A disabled user cannot log in or write |

See [Users](users.md). Errors about a user are shown as a message, with exit status 1.

## Commands from installed apps

Each name in `INSTALLED_APPS` is the name of a package. If it has a module `cli.py` with a `typer.Typer` object named `cli`, that is added to the command line, named after the Typer object (`typer.Typer(name="memgraph")`) or, if it has no name, after the app without a `pangloss_` prefix. `pangloss_memgraph` adds `pangloss memgraph <command>`:

| Command | |
|---------|--|
| `pangloss memgraph info` | Shows the indexes, constraints and enums in the database |

An app with no `cli.py` adds nothing. An app whose `cli.py` cannot be imported, has no `cli` Typer, or has a name that is already a command, gives a warning, and the rest of the command line works.

```python
# my_app/cli.py
import typer

cli = typer.Typer(name="my-app")

@cli.command()
def hello():
    typer.echo("hello")      # pangloss my-app hello
```

An app's `models.py` (if it has one) is imported by `setup-database`, so that its models are registered.

## Running the server

`pangloss run` and `pangloss dev` start the API (see [REST API](api.md)) with uvicorn, as the factory `pangloss_api.app:create_app`. They need `pangloss-api` installed.

The server is run from the project's directory (where `pyproject.toml` is), wherever the command is typed, so `.env` and the project's imports are found. The settings module is passed to the server in the environment variable `PANGLOSS_SETTINGS`. The server imports the `models` of the installed apps and initialises them when it is built, and connects to the database when it starts; a mistake in them is shown, and the server does not start.

`pangloss dev` restarts the server when a `.py` file or `.env` changes in the project, or in an installed app that is not installed as a package (for example a Pangloss package being worked on). Environment directories (`.venv`, `venv`) are ignored. After an error such as a syntax error in a model, the server stays down, showing the traceback, and starts again when the file is fixed.

Settings are always loaded with the project's directory as the current directory, so the `.env` of the project is read whichever directory a command is run from.

## What a database backend supplies

The core commands do not know about any database. The backend named by `DATABASE_MODULE` has a `setup` module with:

| Function | |
|----------|--|
| `create_database(settings)` | Makes the default database object (not async; does not connect). Called when the project is loaded, as `exposed_functions` needs it |
| `async connect()`, `async disconnect()` | Open and close the connection inside the event loop that runs a command |
| `async setup_database() -> list[str]` | Does the work of `pangloss setup-database`, and returns lines to show |

For Memgraph this is `pangloss_memgraph.databases.memgraph.setup`; the SDK has a stub.

## Type stubs

`Person.Create`, `Person.Update`, `Person.HeadView` and the other classes of a model are made when the models are initialised, so an editor or type checker cannot see them. `pangloss make-stubs` imports the models of the installed apps, initialises them, and writes a `.pyi` file beside each module in the project that declares models (`myapp/models.pyi` next to `myapp/models.py`). In it each model has those classes as nested classes, with their fields typed (a relation is the `ReferenceSet` or `ReferenceView` of its target, an enum is the enum).

- A stub **replaces its module for a type checker**, so it has everything the module declares (classes, functions and signatures, enums, type variables), without function bodies. If the module changes, make the stubs again.
- Models in other modules of the project (imported by a `models.py`) get stubs of their own. Modules in `site-packages` or a virtual environment do not.
- The first line says the file was generated. Commit the stubs of your apps, so that everyone who clones the project (and any CI type check) has them: do not add `*.pyi` to `.gitignore`. Make them again, and commit the change, when the models change.
- The nested classes are marked `# type: ignore` where they replace the class variable of the same name in `Entity` or `Document`.
