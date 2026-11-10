---
name: pangloss
description: How Pangloss is designed and how to work on it. Pangloss is the framework in this repository that turns research data models declared as Python classes (Document, Entity, Embedded, Trait, ReifiedRelation, SemanticSpace, Conjunction) into generated Pydantic models, graph storage (Memgraph or Neo4j), a REST API, migrations, an SDK and a Solid 2.0 web interface. Read this before any non-trivial work in the pangloss-monorepo or in a project built with Pangloss - declaring or changing models, the model layer and initialise(), backends and Cypher, the API, migrations, the add-on packages (history, review, dates, calendar, typology, derived, zotero), the interface and its modules, tests, e2e, docs - and before reviewing Pangloss code or answering how or why Pangloss does something, even if the user does not name the skill.
---

# Pangloss

Pangloss (v3; *Prosopography and Network Graph Labyrinth Orientation System*) is a framework for research databases
about people, sources, statements, events and places: data that fits a graph better than a table. The model is declared
once, as Python classes, and everything else is made from it.

It is in active development and not published, so its APIs still move. **Where this skill and the code or `implementation_docs/`
disagree, the code is right**: follow it, and then correct the skill (see the last section).

## The idea

```python
from pangloss_models import Document, Entity, initialise   # public names come from a package's root


class Person(Entity):
    pass


class Statement(Document):
    text: str
    was_carried_out_by: Person      # a relation to an entity


initialise()                        # after every class is declared

saved = await Statement.Create(
    label="A statement", text="…", was_carried_out_by={"type": "Person", "id": some_uuid}
).save()
loaded = await Statement.get(saved.id)      # a Statement.HeadView
```

From the classes Pangloss makes: a family of Pydantic models for each (`Create`, `Update`, `View`, `HeadView`,
`ReferenceView`, `Where`, …); storage in a graph database through a backend named in the settings; CRUD routes, login
and search in a FastAPI application; migrations when the classes change; an installable SDK that runs the same code
over HTTP; type stubs; and a web interface built from an export of the models.

## What is true everywhere

These are the facts that most mistakes come from not knowing.

1. **Declared classes and generated classes.** You write `Statement`; `initialise()` makes `Statement.Create` and the
   rest. Nothing is generated, and no database function is bound, until `initialise()` has run, and it needs a settings
   object to exist first (it reads `STORAGE`). A type checker cannot see the generated classes: that is what
   `pangloss make-stubs` is for, and why `pyproject.toml` relaxes `ty` for tests and model-making code.
2. **Documents contain; entities are referred to.** A `Document` is a unit of research data and nests other documents,
   which are written with it and belong to it. An `Entity` is a real-world thing that documents point at by
   `{"type", "id"}`. An entity is **never part of a document**. There are no "inline entities": `create_inline` only
   lets a payload name an entity by a UUID or URL so that batches can be uploaded; the entity is still its own head
   node with its own history. Do not write "inline", "embedded" or "nested" of an entity.
3. **Everything that is not a literal is a node.** Documents, entities, embedded objects, reified relations, semantic
   spaces and conjunctions are nodes; literals are properties. Every relation is two edges: `field_name` forward and a
   reverse edge with `reverse: true`. The top-level document or entity is the *head node*; what is nested in it
   carries `head_node_id`.
4. **An update replaces the whole document.** There is no patch. Everything below the head is deleted and written
   again (entities are never touched), after all checks have passed. So each head has a `meta.version`, and the API
   refuses an update that does not say which version it is based on (`If-Match`; 412 if stale, 428 if absent).
5. **Nothing is deleted for good.** Delete sets a flag and records who and when; reads leave flagged nodes out. An
   entity that something refers to is marked, not deleted. Unpublished documents (`pangloss-review`) are hidden in the
   same way from readers who are not logged in. Any query you write over model data has to apply these rules (there
   are helpers: see the architecture reference).
6. **What the models cannot do is an error, not a guess.** An annotation `initialise()` does not understand raises
   `PanglossModelError` naming the model, field and the alternative. A single relation or embedded
   object may be optional (`Person | None`, `Date | None`: no edge or node when there is none). Not supported:
   lists of embedded objects (a list of annotated values, `list[WithCertainty[str]]`, is allowed: a list of maps),
   `list[Person] | None` (a list may already be empty), plain
   `dict` (use a `TypedDict`). What a literal is, and how it is stored, is said once in `pangloss_models.literals`
   (pydantic's standard types included: a `UUID` or a URL is text with a format); anything in `Annotated` that is
   neither pydantic's nor Pangloss's is an error, and a `model_config` or `@computed_field` on a declared class a
   `PanglossModelWarning`. A class's methods are on its generated models; its pydantic validators run once, on
   `Create`/`Update`; `@create_validator`/`@update_validator` on the DB models, `@before_create`/`@before_update`
   (async, may refuse) before a write. Writes that cannot succeed raise typed `PanglossWriteError`s.
7. **Python is `snake_case`, JSON is `camelCase`.** The API and the interface see `bornIn`; requests accept either.
   Every generated model has a `type` field, the discriminator of unions.
8. **`Create` wants everything that has no default.** `X | None` and a field with a default (`count: int = 0`,
   `tags: list[str] = []`) may be left out, as in pydantic; every other list and every relation has to be given
   (`[]` will do). A key a `Create`, `Update` or `ReferenceSet` has no field for is **refused** (a 422 over the
   API), except what a read itself gives (`meta`, incoming relations, `DBField`s), which may be sent back as it is.
9. **A project is settings plus apps.** One `BaseSettings` subclass; `STORAGE` names the backend
   (`"pangloss_memgraph:storage"`, `"pangloss_neo4j:storage"`, or the SDK's `"pangloss_sdk.storage:api"`);
   `INSTALLED_APPS` lists the packages whose models, routes, commands, migrations and interface modules are used.
10. **A changed model with data behind it is a migration** (`pangloss makemigrations`, then `pangloss migrate`). The
    API will not start with migrations pending. What is not data (field bindings, markers, interface settings) is not
    seen by migrations.

## Design principles

When a design question comes up, these are how it has been answered so far. Follow them, or say that you are departing
from one and why.

- **Declare once, generate the rest.** If two things have to be kept in step by hand (a model and its form, a model and
  its TypeScript type), the answer is to generate one from the other. The interface is driven by `export_models()`;
  the SDK is the same model code with HTTP behind it.
- **The model layer knows no database.** `pangloss-models` describes data; a backend stores it. Abstract at the level
  of *operations* ("create this head document"), not queries. There is deliberately **no Cypher query builder or AST**:
  the two Cypher backends share one implementation (`pangloss-cypher`) that asks a `Dialect` at the few named points
  where they differ. Query text is chosen for each planner and measured, so it must stay visible.
- **Behaviour is defined by a test suite, once.** The conformance suite (`pangloss_testing/conformance/`) is what a
  backend must pass; a fix to storage behaviour gets a test there, not in one backend's tests.
- **The core knows nothing of the optional packages.** History, review, dates, calendar, typology, derived and Zotero
  are apps that attach through general hooks: meta slots on a model class, write events, routes and background tasks
  from an app's `api.py`, commands from its `cli.py`, an interface module with a manifest. If a package needs
  something of the core, add a general hook and let the package use it; do not put the package's name, fields or UI
  in the core. (The timeline belongs to `pangloss-dates`, not to `interface-core`.)
- **Add-ons run on any backend.** They go through the models, or through `pangloss_core.backend.current()`, never
  `import pangloss_memgraph`. One that runs its own Cypher says `requires = {"cypher"}`.
- **Fail early and loudly.** Mistakes in models are found at `initialise()`, in interface modules by
  `pangloss interface check`, in a deployment at server start (pending migrations, requirements not met). A silent
  fallback is a bug.
- **Nothing is lost quietly.** Flags instead of deletion, a version on every head, every version kept by
  `pangloss-history`, updates checked before anything is removed.
- **Measure before deciding.** Performance claims in the docs come with numbers on a database of about 640,000 nodes
  (`implementation_docs/large-data.md`, `implementation_docs/backend-profiling.md`, `implementation_docs/backend-comparison.md`). A test on an empty database says
  nothing about a query plan.
- **Say what is built and what is not.** Every doc marks features ✅ built, 🚧 partial, ⏳ planned. A plan stays as
  written and gets "As built" sections where the code differs. Do not describe a plan as if it existed.

## The repository

A uv workspace; Python 3.15 (the models use `lazy import`). Each directory of `packages/` is a package of its own.

| Where | What |
|---|---|
| `packages/pangloss-core` | Settings, logging, the `Storage` object, the backend loader for add-ons |
| `packages/pangloss-models` | The base classes, `initialise()`, generated models, export, type stubs, search patterns, the migration planner, hooks and meta slots. The main package |
| `packages/pangloss-cypher` | The one implementation of storage for Cypher databases: write plan, reads, search, delete, users, review, migrations, the `Dialect` |
| `packages/pangloss-memgraph`, `packages/pangloss-neo4j` | The backends: dialect, connection, DDL, bulk load, their own CLI |
| `packages/pangloss-users`, `packages/pangloss-api`, `packages/pangloss-cli` | Users and passwords; the FastAPI application; the `pangloss` command |
| `packages/pangloss-sdk`, `packages/pangloss-sdk-server` | The client (models over HTTP); building and serving a project's SDK |
| `packages/pangloss-history`, `packages/pangloss-review` | Every version, diffs, restore; documents checked before they are published |
| `packages/pangloss-dates`, `packages/pangloss-calendar` | Uncertain dates in the Julian and Gregorian calendars; days, feasts, Easter |
| `packages/pangloss-typology`, `packages/pangloss-derived`, `packages/pangloss-zotero` | Vocabularies in a hierarchy; rules that derive relations from documents; a Zotero library as sources |
| `packages/pangloss-rdf` | RDF export of every item, a generated ontology, mixins for CIDOC-CRM and the like (`implementation_docs/rdf.md`) |
| `packages/pangloss-admin` | The admin-only page `/admin` and long-running jobs in their own process; apps add jobs in `admin.py` and parts of the page through the manifest's `slots` (`implementation_docs/admin.md`) |
| `packages/pangloss-library` | Ready-made models (`WeightedAlternative`, `Likelihood`) |
| `packages/pangloss-lsp` | The language server (diagnostics, quick fixes, completion, hover, hints, references, pending migrations), on `pangloss check`; its Zed and VS Code extensions (`implementation_docs/language-server.md`). A new refusal should name its `fix=` |
| `packages/pangloss-interface` | The web interface: a Python package holding a JavaScript workspace (`interface-core`, `interface-app`) |
| `packages/pangloss-testing` | Live-database fixtures for either backend, and the conformance suite |
| `packages/pydantic-meta-kit` | A clone of another repository, outside the workspace and **not used**: the copy in use is `pangloss_models.meta_kit` |
| `pangloss-demo/`, `sdk-demo/` | A finished project (a factoid model that uses nearly every feature); a script that uses its SDK |
| `e2e/` | Playwright tests of the built interface against a real API and database |
| `implementation_docs/` | The reference: design, status, measurements. Start at `implementation_docs/README.md` |
| `guide/` | Tutorials and how-tos for people using Pangloss. Start at `guide/README.md` |
| `TODO.md`, `implementation_docs/status.md` | What is outstanding; what works |

## Read the reference for the work in hand

Each is short and points on into `implementation_docs/`. Read the one that fits before you start; they hold the detail this page
leaves out.

| You are about to… | Read |
|---|---|
| Declare or change models, write payloads, search, write a migration, or use Pangloss in a project | [references/modelling.md](references/modelling.md) |
| Touch the model layer, a backend, Cypher, the API, the SDK, or write or change an add-on package | [references/architecture.md](references/architecture.md) |
| Touch anything under `packages/pangloss-interface`, an app's `interface/` module, or `e2e/` | [references/interface.md](references/interface.md) |
| Run anything: tests, servers, databases, uv, linters; or write docs or commits | [references/development.md](references/development.md) |

For the interface, the `solidjs-v2` skills in `.claude/skills/` hold the Solid 2.0 API; the interface reference here
holds what is particular to Pangloss.

## Rules that prevent the usual accidents

- **The tests empty the database on port 7687.** Never point a project you care about at it. The demo's data is on
  7688: do not run tests or experiments against it. For scratch work start a container on another port
  (`implementation_docs/large-data.md` shows how).
- **`uv sync --all-packages --all-groups --all-extras`**, always with all three: plain `uv sync` removes the other
  workspace members from `.venv`.
- **Stop a server by the process on its port** (`lsof -tiTCP:<port>`), never by a broad `pkill`: the user may have
  their own servers running.
- **Run `ruff format` on `packages/` only.** Formatting `pangloss-demo/` moves the `# type: ignore` of its generated
  stubs and rewrites its migrations.
- **Solid 2.0 only, Tailwind only** in the interface: no Solid 1.x or React idioms, no hand-written CSS.
- **An item shown as a reference in the interface is a `ReferenceChip`**, everywhere, unless the user says otherwise.
- **Do not edit `.pangloss/interface/` in a project**: every command writes over it. The source is in the package.

## Before a change is finished

- `./run_tests.sh` passes (ruff, `ty`, the packages on Memgraph, Neo4j, e2e), or the part you ran and the part you
  did not are both stated. `--no-neo4j` and `--no-e2e` skip those runs; other arguments go to pytest.
- A change to how storage behaves has a conformance test, and works on both backends.
- The docs say what is now true: the page of the feature (with its marker), `implementation_docs/status.md`, the guide if what a user
  types changed, `TODO.md` if an item is done.
- An interface change has its row in `e2e/COVERAGE.md`, its fixed text as `t()` slots with translations, and has been
  loaded in the dev build (`e2e/test_dev_mode.py`), which stops on errors the production build lets through.
- A change to the demo's models has a migration, and its stubs made again (`../.venv/bin/pangloss make-stubs`, from
  `pangloss-demo/`).
- **This skill still tells the truth** (next section).

## Keeping this skill current

This skill is part of the repository (`.claude/skills/pangloss/`) and is kept as the code is: a change that makes it
wrong is not finished until the skill is corrected, in the same commit.

Update it when a change is one a newcomer would need to be told about:

- a package is added, removed, renamed or changes its job;
- a new kind of model, field, `Meta` option or hook, or one of the "not supported" things becomes supported;
- a design decision is made or reversed (how backends are abstracted, what the core may know, how apps attach);
- a convention changes (commands, ports, test layout, the docs' markers, the interface's stack or rules);
- something here turned out to be wrong, or a trap cost real time and will catch the next agent too.

Do not add: the status of work in progress, the history of how something came to be, or detail that a page of `implementation_docs/`
already holds (link to the page instead). The skill should stay short enough to read before starting work: prefer
replacing a sentence to adding one, and put detail in a reference file, not in this page.

After editing it, and whenever packages or docs are added, moved or renamed, run the check, which finds paths that no
longer exist and packages the skill does not mention (`./run_tests.sh` runs it too):

```sh
python3 .claude/skills/pangloss/scripts/check_skill.py
```
