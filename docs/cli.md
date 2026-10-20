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
| `pangloss setup-database` | Imports the `models` module of each installed app, runs `initialise()`, then asks the database backend to set up what it needs (for Memgraph: indexes, uniqueness constraints, the text index and enums). Safe to repeat |
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

## What a database backend supplies

The core commands do not know about any database. The backend named by `DATABASE_MODULE` has a `setup` module with:

| Function | |
|----------|--|
| `create_database(settings)` | Makes the default database object (not async; does not connect). Called when the project is loaded, as `exposed_functions` needs it |
| `async connect()`, `async disconnect()` | Open and close the connection inside the event loop that runs a command |
| `async setup_database() -> list[str]` | Does the work of `pangloss setup-database`, and returns lines to show |

For Memgraph this is `pangloss_memgraph.databases.memgraph.setup`; the SDK has a stub.
