# The command line: every command, by package

Everything you can type, grouped by the package it comes from. A package's commands are there when its app is in
`INSTALLED_APPS` (the first column of each heading says which). Every command takes `--help`.

How the command finds your project, and how an app adds commands of its own, is in the
[reference](../implementation_docs/cli.md).

- [Before any command](#before-any-command)
- Always there: [`pangloss-cli`](#pangloss-cli-always-there) (projects, the server, models, migrations, users)
- The database: [`pangloss-memgraph`](#pangloss-memgraph), [`pangloss-neo4j`](#pangloss-neo4j)
- Optional apps: [`pangloss-interface`](#pangloss-interface), [`pangloss-sdk-server`](#pangloss-sdk-server),
  [`pangloss-history`](#pangloss-history), [`pangloss-review`](#pangloss-review),
  [`pangloss-calendar`](#pangloss-calendar), [`pangloss-typology`](#pangloss-typology),
  [`pangloss-derived`](#pangloss-derived), [`pangloss-zotero`](#pangloss-zotero), [`pangloss-rdf`](#pangloss-rdf),
  [`pangloss-admin`](#pangloss-admin)
- Commands of their own: [`pangloss-sdk`](#pangloss-sdk-the-client), [`pangloss-lsp`](#pangloss-lsp)
- [Packages with no commands](#packages-with-no-commands)
- [What to type when](#what-to-type-when)

## Before any command

```sh
pangloss --help                      # the commands this project has
pangloss <command> --help            # the arguments and options of one
pangloss --settings my_site.settings <command>
```

The project is found from, in this order: `--settings MODULE`; the environment variable `PANGLOSS_SETTINGS`;
`settings` under `[tool.pangloss]` in the nearest `pyproject.toml`. Commands can be run from any directory inside
the project. Without a project, only `--help`, `new-project` and the like work.

In the tables, `[x]` is optional and `A | B` is a choice.

## `pangloss-cli` (always there)

### Projects and the server

| Command | What it does |
|---|---|
| `pangloss new-project NAME` | Makes a project in the current directory: its settings, `pyproject.toml`, `.env` with a new secret, `.gitignore`. Writes over nothing |
| `pangloss new-app NAME` | Makes an app for your models (`NAME/models.py`) and adds it to `INSTALLED_APPS` |
| `pangloss run [--host H] [--port P]` | Starts the API server (`127.0.0.1:8000`). Will not start with migrations pending |
| `pangloss dev [--host H] [--port P]` | The same, starting again when the code or the settings change |
| `pangloss setup-database` | Makes what the database needs: indexes, constraints and so on. Safe to repeat |

### Models

| Command | What it does |
|---|---|
| `pangloss check [--json] [--write-stubs]` | Says what is wrong with the models, at the file and line, without a database; warns of changes not yet in a migration. Exits with 1 on an error. `--json` is for tools (the language server reads it); `--write-stubs` writes the stubs too if the models are sound |
| `pangloss make-stubs [--force]` | Writes a type stub (`.pyi`) beside each module that declares models, so that an editor can complete `Person.Create(...)`. Run it again when the models change. `--force` writes over a `.pyi` it did not make |

### Migrations

See the [migrations guide](migrations/README.md).

| Command | What it does |
|---|---|
| `pangloss makemigrations [APP] [--name N] [--dry-run] [--check] [--noinput]` | Writes the migrations for what has changed in the models, asking what it cannot know (was this renamed? what value for the nodes that exist?). `--check` writes nothing and fails if the models have changed; `--noinput` fails rather than ask |
| `pangloss makemigrations --empty APP [--name N]` | A migration with no changes, to put `RunCypher` or `RunPython` in |
| `pangloss showmigrations` | The migrations of each app, and which the database has had |
| `pangloss migrate [APP [TARGET]]` | Applies the migrations the database has not had, then reads the data they could have made unreadable. With `TARGET` (a name or number; `zero` for none) it goes to that migration, backwards if it is applied |
| … `--plan` | Shows what would be applied, and applies nothing |
| … `--dry-run` | Tries the changes in a transaction that is rolled back, and says what each would do |
| … `--check` | Applies nothing; fails if there are migrations to apply |
| … `--backup` / `--no-backup` | Takes a snapshot first, or not. A migration that loses data needs one of the two |
| … `--yes`, `-y` | Does not ask before changes that lose data |
| … `--batch-size N` | In batches of N nodes, each its own transaction; one that stops goes on from there the next time |
| … `--fake` | Records the migrations as applied without running them |
| … `--no-check`, `--check-all` | Does not read the data afterwards; reads all of it |
| … `--unlock` | Removes the lock of a `migrate` that was stopped |
| `pangloss squashmigrations APP [FIRST] LAST [--name N] [--no-optimize] [--dry-run]` | Writes one migration that replaces a run of them. The originals are kept until every database has had them |
| `pangloss cleanmigrations [APP] [--yes]` | Deletes the files of migrations that a squashed one replaces. Only this database is looked at |
| `pangloss check-data [--type T]… [--limit N] [--parallel N]` | Reads all the data with the models as they are, and reports what cannot be read. Also reports references that are on an entity that was merged into another, and merges that stopped part of the way |
| … `--move-merged --user U` | Moves the references found on merged entities to the entities they were merged into |
| `pangloss backups` | Lists the snapshots the database server has, newest first |
| `pangloss restore PATH [--yes]` | Puts the database back to a snapshot. **Everything in it now is replaced**; run `migrate` after |

### Merging entities

Two entities that are one (a duplicate made by mistake) are merged: what refers to the second refers to the first,
and the second is kept, marked as merged, so that the merge can be undone. See
[entity-identity.md](../implementation_docs/entity-identity.md).

| Command | What it does |
|---|---|
| `pangloss merge TYPE SURVIVOR ABSORBED --user U` | Merges the entity `ABSORBED` into `SURVIVOR` (their ids). The survivor keeps its own fields, takes the other's where it has none, and has both of every list |
| `pangloss merge TYPE --pairs FILE --user U` | Merges each pair of a file: a line each, the survivor's id and then the absorbed entity's. The first that cannot be merged stops the rest |
| … `--as CLASS` | The class the survivor takes, when the two differ (the narrower, if not given) |
| … `--large` | Makes a merge that writes more documents than `MERGE_LIMIT`, in batches; also goes on with one that stopped |
| … `--dry-run` | Says what each merge would do, and writes nothing |
| `pangloss unmerge MERGE_ID --user U [--dry-run] [--confirm-migrated]` | Undoes a merge. Lists what could not be put back, and what was written to the survivor since. After a migration it needs `--confirm-migrated` (look at `--dry-run` first) |
| `pangloss merges [--state S]… [--limit N]` | Lists the merges recorded, the latest first, with their ids |

### Users

See [users, logins and the API](accounts/README.md).

| Command | What it does |
|---|---|
| `pangloss users create [NAME \| --username NAME] [--email E] [--password P] [--full-name F] [--admin \| --no-admin]` | Adds a user, asking for what is not given. In a script give `--admin` or `--no-admin`, or it asks |
| `pangloss users create-toolchain NAME [--full-name F]` | Adds a toolchain: a user that cannot log in, named as a maker of the data it made (`save(toolchain=...)`) |
| `pangloss users list` | Lists the users |
| `pangloss users set-password USERNAME [--password P]` | Sets a password (and ends the user's sessions) |
| `pangloss users make-admin USERNAME`, `pangloss users remove-admin USERNAME` | Makes a user an admin, or an ordinary user again |
| `pangloss users disable USERNAME`, `pangloss users enable USERNAME` | Stops a user logging in or writing (what they wrote stays), or lets them again |
| `pangloss users tokens create USERNAME [--name N] [--scope read \| write] [--expires-days D]` | Makes a personal access token. It is shown once |
| `pangloss users tokens list USERNAME` | A user's tokens (not the tokens themselves), with when each was last used |
| `pangloss users tokens revoke USERNAME TOKEN_ID` | Deletes one |

## `pangloss-memgraph`

`"pangloss_memgraph"` in `INSTALLED_APPS`. See [choosing and running a database](backends/README.md) and
[large data](../implementation_docs/large-data.md).

| Command | What it does |
|---|---|
| `pangloss memgraph info` | Shows the indexes and constraints in the database |
| `pangloss memgraph bulk-load FILE --user NAME [--concurrency N] [--validate-only]` | Loads a JSON Lines file of records into an **empty** database, several times faster than writing them as usual (Memgraph's analytical mode). What a record refers to must be earlier in the file |
| `pangloss memgraph bulk-recover` | Puts the database back after a bulk load that stopped or left duplicates |
| `pangloss memgraph refold` | Deprecated: writes the folded label of every node again. Only needed after a query of your own, run outside the models and migrations |

## `pangloss-neo4j`

`"pangloss_neo4j"` in `INSTALLED_APPS`, instead of Memgraph's.

| Command | What it does |
|---|---|
| `pangloss neo4j info` | Shows the indexes and constraints in the database |
| `pangloss neo4j bulk-load FILE --user NAME [--concurrency N] [--validate-only]` | Loads a JSON Lines file into an **empty** database, in ordinary transactions with several writers. The database is read-only for everyone else meanwhile |
| `pangloss neo4j bulk-recover` | Releases the lock of a bulk load that was stopped |

## `pangloss-interface`

`"pangloss_interface"` in `INSTALLED_APPS`. See [the interface guide](interface/README.md). `--runtime node | bun`
(or `PANGLOSS_INTERFACE_RUNTIME`) is taken by `info`, `install`, `dev`, `build`, `serve`, `check` and `modules`.

| Command | What it does |
|---|---|
| `pangloss interface install` | Prepares the interface in the project (`.pangloss/interface`) and installs its packages |
| `pangloss interface dev [--port 3000] [--api-url URL] [--link]` | The development server; it passes `/api` on to the API. Start it again after changing models. `--link` runs from the source of the package, for working on the interface itself |
| `pangloss interface build` | Builds the interface for production |
| `pangloss interface serve [--host H] [--port 3000] [--api-url URL] [--no-api-proxy] [--api-path P]…` | Runs the built interface. `--no-api-proxy` where a reverse proxy in front passes `/api` on; `--api-path /entity` passes another path on to the API (the URIs of an RDF export) |
| `pangloss interface check` | Type-checks the interface with the project's models, and checks the layers |
| `pangloss interface info` | Where the interface is built, and what will run it |
| `pangloss interface export-models [--format ts \| json] [-o, --output FILE]` | The definitions of the models, as the interface reads them |
| `pangloss interface new-module APP [--force] [--no-example]` | Makes `APP/interface/`: a Solid library for the pages and cards of an app's models |
| `pangloss interface modules` | Lists the interface modules of the installed apps, what each provides, and their problems |
| `pangloss interface new-homepage [--force]` | Makes the project's own homepage, `pages/index.tsx`, from the default one |
| `pangloss interface new-page NAME [--force]` | Makes a blank page in `pages/`: `About` is at `/about`, and linked from the homepage |
| `pangloss interface translations generate [--app A] [--prune] [--dry-run] [--strict]` | Writes or brings up to date each app's `translations/models.jsonc`. What a person has written is kept |
| `pangloss interface translations gather [-o, --out FILE]` | Merges the apps' files, the project's and the interface's own into the one file the interface reads |
| `pangloss interface translations check [--lang L] [--strict]` | Lists what is missing in a language. Exits with 1 if anything is |

## `pangloss-sdk-server`

`"pangloss_sdk_server"` in `INSTALLED_APPS`. See [the SDK guide](sdk/README.md).

| Command | What it does |
|---|---|
| `pangloss sdk build [--force]` | Builds the SDK of the project (its models, with stubs, as a package), checked on a clean client before it replaces the last build. Does nothing if the models have not changed |
| `pangloss sdk status` | What is built, and whether the models have changed since (exits with 2 if so) |
| `pangloss sdk show [--diff]` | The files of the SDK as the models are now; with `--diff`, the change since the last build |

## `pangloss-history`

`"pangloss_history"` in `INSTALLED_APPS`. See [the history guide](history/README.md). `ID` is the id of a document
or entity.

| Command | What it does |
|---|---|
| `pangloss history list ID` | The versions recorded |
| `pangloss history show ID VERSION` | A version, as it was written |
| `pangloss history diff ID VERSION [--to N]` | What changed from one version to another (to the latest, without `--to`) |
| `pangloss history restore MODEL ID VERSION --user NAME [--expected-version N]` | Writes an earlier version again, as a new version |
| `pangloss history baseline [--model M]… [--dry-run]` | Records what each item is now, where history has no record of it (data from before the package was installed). Safe to repeat |

## `pangloss-review`

`"pangloss_review"` in `INSTALLED_APPS`. See [the review guide](review/README.md).

| Command | What it does |
|---|---|
| `pangloss review index-uris` | Make again the index of the URIs that unreconciled mentions and suggested identifications name (after a bulk load) |
| `pangloss review queue [--status unchecked \| errors_found \| published]… [--type T] [--page N]` | The documents to check, the oldest change first |
| `pangloss review show ID` | The state of a document, and its open comments |
| `pangloss review set ID STATUS [--user NAME] [--comment TEXT]` | Sets the status. `published` publishes the document (`checked`, its earlier name, is still taken) |

## `pangloss-calendar`

`"pangloss_calendar"` in `INSTALLED_APPS`. See [the calendar guide](calendar/README.md). Run `pangloss migrate`
first.

| Command | What it does |
|---|---|
| `pangloss calendar seed [--from YEAR] [--to YEAR] [--calendar C]` | Makes the days of the span (by default `CALENDAR_FIRST_YEAR` to `CALENDAR_LAST_YEAR`), with their months and years in both calendars, then links the characterisations that have a rule. Safe to repeat |
| `pangloss calendar link` | Makes again the links from days to the characterisations (feasts) whose rule falls on them, after one is made or changed. What was attached by hand is not touched |
| `pangloss calendar status` | How much of the calendar there is |

## `pangloss-typology`

`"pangloss_typology"` in `INSTALLED_APPS`. See [the typology guide](typology/README.md). `NAME` is the name of the
typology's entity, such as `RoleType`.

| Command | What it does |
|---|---|
| `pangloss typology load NAME FILE --user USER` | Makes the types of a nested JSON(C) file. One already there is left alone, so the file can be loaded again |
| `pangloss typology dump NAME [--to FILE]` | Writes the vocabulary in the form `load` reads |
| `pangloss typology tree NAME` | Shows the hierarchy |

## `pangloss-derived`

`"pangloss_derived"` in `INSTALLED_APPS`. See [the derived relations guide](derived/README.md). The group is
`derive`.

| Command | What it does |
|---|---|
| `pangloss derive explain [RULE] [--queries]` | Each rule as Datalog, what can trigger it, and the order of its joins; with `--queries`, the queries too |
| `pangloss derive dry-run [RULE] [--top N]` | What a rule would derive from the data as it is, and the seeds that give most. Writes nothing. Run it before switching a rule on |
| `pangloss derive rebuild [RULE]` | Derives everything again. The way to derive after a bulk load |
| `pangloss derive status` | What is pending, and the state of each rule |
| `pangloss derive graph TYPE [--plain-only] [--csv]` | The facts of a type of rule, as a graph of edges between their two ends |
| `pangloss derive worker [--batch N]` | Runs the worker until stopped. The server runs one itself; only one works at a time |

## `pangloss-zotero`

`"pangloss_zotero"` in `INSTALLED_APPS`. See [the Zotero guide](zotero/README.md).

| Command | What it does |
|---|---|
| `pangloss zotero check` | Looks for what is wrong with how Zotero is set up (settings, classes, fields the sync cannot give) |
| `pangloss zotero sync [--library L]… [--full] [--dry-run]` | Brings the libraries up to date, once |
| `pangloss zotero watch` | Syncs, then listens to Zotero and syncs when a library changes. The server does this itself unless `ZOTERO_WATCH` is `False`: use this when the server has several workers |
| `pangloss zotero status [--remote]` | For each library: how far it has been synced, when, and the last error |

## `pangloss-rdf`

`"pangloss_rdf"` in `INSTALLED_APPS`. See [exporting as RDF](rdf/README.md).

| Command | What it does |
|---|---|
| `pangloss rdf check` | Finds what is wrong with the names of the models in RDF, and what to settle before publishing |
| `pangloss rdf ontology [--format ttl \| trig \| jsonld \| nt \| nq] [--shapes] [--context] [-o, --output FILE]` | Writes the ontology made from the models; or the SHACL shapes; or the JSON-LD context |
| `pangloss rdf dump [-o, --output FILE] [--format nq \| trig \| ttl] [--types A,B] [--include-unpublished] [--include-unused]` | Writes every document and entity to a file. A name ending `.gz` is compressed |
| `pangloss rdf generate-ontology SOURCE [--prefix P] [--out FILE] [--title T]` | Makes a Python module of mixins from an ontology's RDFS or OWL file (as for CIDOC-CRM) |

## `pangloss-admin`

`"pangloss_admin"` in `INSTALLED_APPS`. It has nothing to type: its page is `/admin` in the interface, where jobs
(such as the RDF dump) are started. `pangloss admin run-job` is how the server starts a job's process, and is hidden.

## `pangloss-sdk` (the client)

A command of its own, installed with the client package, for the people who use a project's SDK from their own
scripts. It needs no project. See [the SDK guide](sdk/02-install.md).

| Command | What it does |
|---|---|
| `pangloss-sdk login [URL] [--username U] [--token]` | Logs in to a server and keeps the login; with `--token`, keeps a personal access token |
| `pangloss-sdk logout [URL]` | Revokes the kept login and forgets it |
| `pangloss-sdk status [URL]` | Where you are logged in, and the SDK there |
| `pangloss-sdk update [PACKAGE] [--dry-run]` | Installs the SDK the server has now |
| `pangloss-sdk sync-stubs [DIRECTORY] [--package P] [--remove]` | Type stubs for the blocking SDK (`connect(sync=True)`), into `typings/` by default |

## `pangloss-lsp`

`pangloss-lsp` is the language server, started by an editor (the Zed and VS Code extensions do it), not typed. What
it shows comes from `pangloss check --json`. See [the reference](../implementation_docs/language-server.md).

## Packages with no commands

`pangloss-core`, `pangloss-models`, `pangloss-cypher`, `pangloss-users` (its commands are `pangloss users`, in
`pangloss-cli`), `pangloss-api` (started by `pangloss run`), `pangloss-dates`, `pangloss-library`,
`pangloss-testing`.

## What to type when

| When | Type |
|---|---|
| Starting a project | `pangloss new-project`, `pangloss new-app`, then `pangloss setup-database` and `pangloss users create` |
| After changing a model | `pangloss check`, `pangloss makemigrations`, `pangloss migrate`, `pangloss make-stubs`; then start `pangloss interface dev` again, and `pangloss sdk build` if scripts use the SDK |
| Working | `pangloss dev` and, in another terminal, `pangloss interface dev` |
| Deploying | `pangloss migrate --check` (or `migrate --backup`), `pangloss interface build`, `pangloss run`, `pangloss interface serve` |
| After a bulk load | `pangloss derive rebuild` (a bulk load leaves nothing pending for the worker) |
| Something looks wrong with the data | `pangloss check-data`, `pangloss showmigrations`, `pangloss memgraph info` |
| Two entities are one | `pangloss merge TYPE SURVIVOR ABSORBED --user U --dry-run`, then without `--dry-run`; `pangloss unmerge` takes it back |
