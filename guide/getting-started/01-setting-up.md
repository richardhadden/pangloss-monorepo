# 1. Setting up

## What you need

- **Python 3.14 or newer.**
- **Memgraph**, the graph database Pangloss stores data in. The easiest way is Docker:

  ```bash
  docker run -d --name pangloss-memgraph -p 7687:7687 memgraph/memgraph-mage
  ```

  It listens on `bolt://localhost:7687`. (This image has no password by default. To see that it is up: `docker ps`.)
- **The Pangloss packages.** Pangloss is used from a checkout of its repository for now. In the root of the checkout:

  ```bash
  uv sync --all-packages
  source .venv/bin/activate      # puts the `pangloss` command on your path
  ```

  Check it:

  ```bash
  pangloss --help
  ```

  It lists the commands you will use in this tutorial: `new-project`, `new-app`, `makemigrations`, `migrate`, `users`, `run`...

## A project and an app

A Pangloss **project** is a directory with settings. An **app** is a Python package in it that holds a set of related models. A project can have several; this one has one.

Make a directory for the tutorial, outside the repository, and make the project in it:

```console
$ mkdir letters-tutorial && cd letters-tutorial
$ pangloss new-project letters_site
Created project 'letters_site'
  created pyproject.toml
  created letters_site/__init__.py
  created letters_site/settings.py
  created .env
  created .gitignore
```

(Python names cannot have hyphens, so the directory is `letters-tutorial` but the project is `letters_site`.)

Then make the app:

```console
$ pangloss new-app letters
Created app 'letters'
  created letters/models.py
  added "letters" to INSTALLED_APPS in letters_site/settings.py
```

You now have:

```
letters-tutorial/
  pyproject.toml            says where the settings are: [tool.pangloss] settings = "letters_site.settings"
  .env                      secrets (a random AUTHJWT_SECRET_KEY); kept out of git
  letters_site/
    settings.py             the project's settings
  letters/
    models.py               your models go here
```

`pangloss` finds the project by looking for that `pyproject.toml` from the directory you are in, so run its commands anywhere inside `letters-tutorial`.

## Point it at the database

Open `letters_site/settings.py`. The part to look at is the database:

```python
DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
    DB_URL="bolt://localhost:7687",
    DB_USERNAME="memgraph",
    DB_PASSWORD="memgraph",
    DATABASE_NAME="memgraph",
)
```

These are the defaults for the Docker container above, so for this tutorial nothing needs to change. (If your Memgraph has other credentials, set them here.) Notice also:

```python
INSTALLED_APPS: list[str] = [
    "pangloss_memgraph",
    "letters",
]
```

`INSTALLED_APPS` is the list of packages whose models and commands are used. `pangloss_memgraph` is the database; `letters` is your app, added by `new-app`.

Check that Pangloss can reach the database:

```console
$ pangloss memgraph info
```

It lists the indexes and constraints the database has (none yet, in a new one). If it says it cannot connect, check that the container is running.

Next: [your first models](02-models.md).
