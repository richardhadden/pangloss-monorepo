# The demo project

`pangloss-demo/` (in the root of the repository, not one of the packages) is a project made with the
installer, with one app, `demo_app`, which has a small model of **factoids**: what a source says,
at a page of it, as a list of statements about people, groups and places. `populate.py` puts some data in it
(a few factoids about the year 800).

This is every command a person runs to make it, in order. (Python names cannot have hyphens, so the
directory is `pangloss-demo`, the project `pangloss_demo`, and the app `demo_app`.)

## 0. Before: the environment and the database

```bash
# In the root of the repository: install every package of the workspace
uv sync --all-packages

# The Memgraph for the demo. It is a container of its own, `pangloss-memgraph-demo`, with the
# user `test` (password `test`) and the database `memgraph`, on bolt://localhost:7688.
docker ps --format '{{.Names}} {{.Ports}}'
```

> **Port 7688, not 7687.** `7687` is the container that the tests of the packages use
> (`pangloss-memgraph-test`), and the tests **empty it** after each test. The demo's Memgraph is
> the one published on host port `7688` (to `7687` in the container). Use `7687` for the demo only if
> there is nothing else on it.

## 1. Make the project and the app

```bash
mkdir pangloss-demo && cd pangloss-demo

# the `pangloss` command is in the repository's environment
source ../.venv/bin/activate

pangloss new-project pangloss_demo     # settings.py, pyproject.toml, .env, .gitignore
pangloss new-app demo_app              # demo_app/models.py; adds "demo_app" to INSTALLED_APPS
```

## 2. Point it at the database, and declare the models

These are edits, not commands:

- `pangloss_demo/settings.py`: `DATABASE` is `MemgraphDatabaseSettings(DB_URL="bolt://localhost:7688",
  DB_USERNAME="test", DB_PASSWORD="test", DATABASE_NAME="memgraph")`.
- `demo_app/models.py`: the models (a table at the top of the file says which feature each shows).

Then, optionally, type stubs, so that an editor can complete `Factoid.Create(...)` and the like:

```bash
pangloss make-stubs                    # writes demo_app/models.pyi (commit it)
```

## 3. Set up the database, and a user

```bash
pangloss setup-database                # indexes, constraints, the text index and the enums
pangloss users create --username demo --email demo@example.org \
    --password demo-password --full-name "Demo User" --admin
```

What the script writes is recorded as written by the user `demo`.

## 3b. Migrations (optional, and from now on)

The database was set up without migrations, so the first migration is recorded as already applied:

```bash
pangloss makemigrations                # writes demo_app/migrations/0001_initial.py
pangloss migrate --fake                # the database is as it says: record it (the library's migrations too), do not run it
pangloss showmigrations                # [X] 0001_initial (faked)
```

After that, when `demo_app/models.py` changes: `pangloss makemigrations` (it asks about renames and about values for what exists), then `pangloss migrate`. See [Database migrations](migrations.md).

## 4. Put data in it

```bash
python populate.py                     # run in pangloss-demo/; refuses to run twice
```

To start again, empty the database (for the demo's only; this is not undoable) and repeat step 3 if the
user went too:

```bash
python - <<'PY'
from neo4j import GraphDatabase
driver = GraphDatabase.driver("bolt://localhost:7688", auth=("test", "test"))
driver.execute_query("MATCH (n) WHERE NOT n:PGUser DETACH DELETE n")   # (the user is kept)
PY
python populate.py
```

## 5. Use it (optional)

```bash
pangloss dev                           # the REST API on http://127.0.0.1:8000, restarting on changes
curl http://127.0.0.1:8000/api/Factoid
curl http://127.0.0.1:8000/api/Person/https://example.org/demo/person/charlemagne   # an entity, by its URL
```

## 6. The web interface (optional)

`pangloss-interface` is installed by adding it to `INSTALLED_APPS` (an edit, in `pangloss_demo/settings.py`):

```python
INSTALLED_APPS: list[str] = [
    "pangloss_memgraph",
    "demo_app",
    "pangloss_interface",
]
```

It adds `pangloss interface …` and the endpoints under `/api/interface`. Then (Node 22.12 or later is needed;
see [The interface](interface.md)):

```bash
pangloss interface build               # copies the interface to .pangloss/interface, exports the
                                       # models of the demo as TypeScript, installs its packages, builds
pangloss interface serve               # the built, server-rendered interface on http://127.0.0.1:3000

# or, for development, in two terminals (the interface passes /api on to the API):
pangloss dev                           # the API, port 8000
pangloss interface dev                 # the interface, port 3000, restarting on changes
```

To work on the interface itself, with the demo's models and your edits to the package showing at once:

```bash
pangloss dev                           # the API, port 8000
pangloss interface dev --link          # runs from packages/pangloss-interface/.../js, not the copy
```

The home page lists the models of the demo (`Factoid`, `Person`, ...) from the exported definitions, and
`/Factoid` and the like list the fields of a model. `.pangloss/interface/` can be committed or ignored (its
own `.gitignore` leaves out `node_modules` and `dist`).

## What is in it

| | |
|---|---|
| Entities | `Person` and `Group` (both an `Agent`), `Place`, `Source`: with URLs as ids, and written inline in the factoid that needs them |
| Documents | `Factoid` contains `Statement`s (abstract), which are `Activity` or `Transfer` |
| Relations | `AtPage[Source]` and `InRole[Agent]` (reified: a relation with fields), `ViaEdge[Agent, Certainty]` (fields on the edge), a field narrowed by a subclass (`carried_out_by` narrows `involves`) |
| Wrappers | `Negative` and `Hypothetical` (semantic spaces), `Causes` (a conjunction) |
| Values | an embedded `Date`, an annotated `WithCertainty[str]`, enums, a `TypedDict`, `Decimal`, lists, validators |
| Binding | `Factoid.year` is given to the statements that have none |

## Found while making it

Making the demo showed two faults in `pangloss-models`, now fixed (with tests):

- an entity with `create_inline` could not be used by a model declared *before* it (an `AttributeError` for
  `Create` or `CreateDB` when initialising the models);
- a field binding (`bind_to_child_field`) failed on a relation to a `list[...]` of documents.

Not supported, and avoided in the demo: an entity cannot be written inline where the relation has
properties of its own (`ViaEdge`), so `carried_out_by` refers to entities that already exist.
