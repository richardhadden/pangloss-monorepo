# Part 1: A project

In this part you install Pangloss, start a database, and make the skeleton of the application: a **project** with one
**app** in it. By the end, a server is running that knows about your (so far empty) set of models.

## What you need

- **Python 3.15 or newer**, and [uv](https://docs.astral.sh/uv/), which installs Pangloss and its dependencies.
- **Docker**, to run the database. (You can install Memgraph another way if you prefer; Docker is the quickest.)
- **Node 22.12 or newer**, for the web interface in [part 3](03-interface.md). You can leave this until then.

## Installing Pangloss

Pangloss is not published as packages yet, so you use it from a checkout of its repository. In the root of the checkout:

```console
$ uv sync --all-packages
$ source .venv/bin/activate
```

The second line puts the `pangloss` command on your path; do it in each new terminal you use for this tutorial. Check it:

```console
$ pangloss --help
```

Outside a project it lists only a few commands (`new-project`, `new-app`, `users` and so on). Inside one it lists many
more: each app you install can add its own.

## The database

Pangloss stores data in a graph database. It supports two, Memgraph and Neo4j; this tutorial uses **Memgraph**, which is
the default. Start one in Docker:

```console
$ docker run -d --name chronicles-memgraph -p 7690:7687 memgraph/memgraph-mage:3.14.0
```

This runs Memgraph in the background and makes it reachable at `bolt://localhost:7690`. The `-p 7690:7687` part maps
port 7690 on your machine to Memgraph's usual port inside the container.

> **Why not the usual port, 7687?** You can use it, but if you ever run Pangloss's own test suite, its tests use a
> Memgraph on port 7687, and they **empty it** before each test. A port of your own keeps your tutorial data safe.

`docker ps` shows whether it is running. `docker stop chronicles-memgraph` stops it and `docker start chronicles-memgraph`
starts it again later, with your data still there.

## Making a project

A Pangloss **project** is a directory holding the settings for one installation: which database to use, which apps are
installed, secrets. Make a directory for the tutorial (anywhere outside the Pangloss checkout) and make the project in it:

```console
$ mkdir chronicles
$ cd chronicles
$ pangloss new-project chronicles_site
Created project 'chronicles_site'
  created pyproject.toml
  created chronicles_site/__init__.py
  created chronicles_site/settings.py
  created .env
  created .gitignore

Next: check the database settings in chronicles_site/settings.py, add the Pangloss packages to the dependencies in pyproject.toml, and make an app with
  pangloss new-app <name>
```

(A Python package name cannot contain a hyphen, so the directory can be `chronicles` but the project is `chronicles_site`.)

Now make an **app**, the package that will hold your models:

```console
$ pangloss new-app chronicle
Created app 'chronicle'
  created chronicle/__init__.py
  created chronicle/models.py
  added "chronicle" to INSTALLED_APPS in chronicles_site/settings.py

Now declare your models in chronicle/models.py
```

> **Projects and apps.** What is the difference? An *app* is a Python package that does one thing: here, it holds the
> models of chronicles and what they say. A *project* is a particular installation: these settings, this database, these
> apps. A project can have several apps, and an app can be used in several projects. The optional parts of Pangloss
> (dates, typologies, the web interface) are apps too: you install them into a project the same way you installed
> `chronicle`.

You now have:

```
chronicles/
├── pyproject.toml          says where the settings are
├── .env                    secrets; kept out of version control
├── .gitignore
├── chronicles_site/
│   ├── __init__.py
│   └── settings.py         the project's settings
└── chronicle/
    ├── __init__.py
    └── models.py           your models go here
```

- **`pyproject.toml`** has a section `[tool.pangloss]` with `settings = "chronicles_site.settings"`. That is how the
  `pangloss` command finds the project: it looks for this file in the directory you are in and the ones above it. So you
  can run `pangloss` anywhere inside `chronicles/`.
- **`.env`** holds `AUTHJWT_SECRET_KEY`, a random secret that signs login tokens. It was made for you, and `.gitignore`
  keeps it out of git. Values here, or in environment variables, override the settings file.
- **`chronicles_site/settings.py`** is where everything about this installation is configured.
- **`chronicle/models.py`** is empty but for a comment. You fill it in [part 2](02-models.md).

## The settings

Open `chronicles_site/settings.py`. It is a class, and every setting is an attribute with a type, so a mistake (a port
given as `"seventy"`, say) is reported when the project loads, not later. The parts that matter now:

```python
    INSTALLED_APPS: list[str] = [
        "pangloss_memgraph",
        "chronicle",
    ]

    STORAGE: str | None = "pangloss_memgraph:storage"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        DB_URL="bolt://localhost:7687",
        DB_USERNAME="memgraph",
        DB_PASSWORD="memgraph",
        DATABASE_NAME="memgraph",
    )
```

- **`INSTALLED_APPS`** lists the apps of the project. `pangloss_memgraph` is the database backend (it brings its own
  commands, such as `pangloss memgraph info`); `chronicle` is yours, added by `new-app`.
- **`STORAGE`** names the backend that stores the data, and **`DATABASE`** says how to reach it.

Change `DB_URL` to the port you gave Docker:

```python
        DB_URL="bolt://localhost:7690",
```

The user name and password can stay as they are: the Memgraph image has no password unless you give it one, and accepts
any. Now check that Pangloss can reach the database:

```console
$ pangloss memgraph info
Indexes
Unique constraints
```

Two empty lists: a new, empty database. If instead it says it cannot connect, check `docker ps` and the port.

## The first migration

Try starting the server:

```console
$ pangloss run
...
ERROR pangloss.api.app The database and the models do not agree with the migrations:
  6 migrations have not been applied (pangloss_memgraph.0001_initial, pangloss_memgraph.0002_addindex_addindex_addconstraint, ...): run `pangloss migrate`
...
```

It refuses, and says why. Pangloss keeps a record, in the database itself, of how the database has been set up: its
indexes and constraints, and later the shape of your data. Each step is a **migration**, a small Python file. The
database package comes with migrations of its own, for what Pangloss itself needs (an index to find a user by name, a
constraint that no two objects share an id), and none of them has been applied to your new database. The server checks
this as it starts so that it never runs against a database in the wrong shape.

See what there is:

```console
$ pangloss showmigrations
pangloss_memgraph
 [ ] 0001_initial
 [ ] 0002_addindex_addindex_addconstraint
 [ ] 0003_addindex
 [ ] 0004_addindex_addconstraint
 [ ] 0005_addindex_addindex_addindex
 [ ] 0006_removeindex_runpython_addindex
```

and apply them:

```console
$ pangloss migrate
To apply:
  pangloss_memgraph.0001_initial
    - Create the index :HeadNode(id)
    - Create the index :PGCreation(id)
    ...
  pangloss_memgraph.0006_removeindex_runpython_addindex
    - Drop the text index label_text on :PGIndexableNode(label)
    - Run pangloss_memgraph.databases.memgraph.folding:refold_in_migration: the folded label of every node that has a label
    - Create the text index label_text on :PGIndexableNode(label_folded)
  pangloss_memgraph.0001_initial: applying
  pangloss_memgraph.0001_initial: applied
  ...
  pangloss_memgraph.0006_removeindex_runpython_addindex: applied
Done
Nothing that exists is affected by these migrations: no data to read
```

`migrate` first says what it is going to do, then does it. `pangloss showmigrations` now shows `[X]` against each one.
You will write migrations of your own in the next part; the rhythm is always the same.

## The server

```console
$ pangloss run
INFO:     Started server process [38758]
INFO:     Waiting for application startup.
... INFO pangloss.api.app Starting chronicles_site: memgraph, 0 models, apps pangloss_memgraph, chronicle
... INFO pangloss.memgraph.setup Connected to Memgraph at localhost:7690 (database 'memgraph')
... INFO pangloss.api.app Migrations: the database and the models agree with them
... INFO pangloss.api.app chronicles_site is ready
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

This is the **REST API** of your project. Open <http://127.0.0.1:8000/docs> in a browser: it is the interactive
documentation of every endpoint the server has. For now those are only the ones for users and logging in
(`/api/users/...`) and the searches (`/api/search`, `/api/autocomplete`), because there are no models yet. In the next
part you add some, and endpoints for each appear here without your writing any code for them.

Stop the server with Ctrl-C.

> **`run` and `dev`.** `pangloss dev` does the same as `pangloss run`, but restarts the server when you change a file.
> Use it while you work; use `run` when you want a server that stays as it is.

## What you have done

You have a project with one app, a database it can reach, the migrations that set the database up, and a server. Next,
in [part 2](02-models.md), you describe your data.
