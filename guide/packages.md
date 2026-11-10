# The packages, and where each is explained

Pangloss is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) of packages under `packages/`.
Some are always needed; the rest are **optional apps**: you add their name to `INSTALLED_APPS` and they add models,
routes, commands or interface pages. Python 3.15 is required throughout.

## Always

| Package | What it is for | Guide |
|---|---|---|
| `pangloss-core` | Settings and logging shared by everything | [Settings](../implementation_docs/settings.md), [Logging](../implementation_docs/logging.md) |
| `pangloss-models` | The base classes (`Document`, `Entity`, …), the generated models, export, type stubs, the migration planner | [Getting started](getting-started/README.md), [Checking data and methods](validation/README.md), [Migrations](migrations/README.md) |
| `pangloss-memgraph` **or** `pangloss-neo4j` | The database | [Choosing and running a database](backends/README.md) |
| `pangloss-cypher` | What the two database packages share. Installed with either; nothing to set | [The database abstraction](../implementation_docs/database-abstraction.md) |
| `pangloss-users` and `pangloss-api` | Users, logins, tokens and the REST API | [Users, logins and the API](accounts/README.md) |
| `pangloss-cli` | The `pangloss` command | [The command line](cli.md): every command, by package |

## Optional apps

| Package | `INSTALLED_APPS` | What it adds | Guide |
|---|---|---|---|
| `pangloss-sdk-server` | `pangloss_sdk_server` | Builds and serves a package of your models for scripts | [The SDK](sdk/README.md) |
| `pangloss-history` | `pangloss_history` | Every version, diffs, restore | [History](history/README.md) |
| `pangloss-review` | `pangloss_review` | Documents are checked before they are published; comments | [Review](review/README.md) |
| `pangloss-dates` | (import its types) | Uncertain dates, ranges, periods, recurrence; Julian and Gregorian | [Dates](dates/README.md) |
| `pangloss-calendar` | `pangloss_calendar` | What is on a day, a month, a year; feasts and Easter | [Calendar](calendar/README.md) |
| `pangloss-typology` | `pangloss_typology` | Vocabularies of types in a hierarchy | [Typology](typology/README.md) |
| `pangloss-derived` | `pangloss_derived` | Rules that derive relations (person-to-person networks) from documents, kept up to date in the background | [Derived relations](derived/README.md) |
| `pangloss-zotero` | `pangloss_zotero` | A Zotero library kept as sources and subjects | [Zotero](zotero/README.md) |
| `pangloss-rdf` | `pangloss_rdf` | Every item as RDF, an ontology made from the models, mixins for CIDOC-CRM | [Exporting as RDF](rdf/README.md) |
| `pangloss-library` | `pangloss_library` | Ready-made models: `WeightedAlternative`, `Likelihood` (alternatives whose shares add up to 100) | [Shares](../implementation_docs/shares-plan.md) (reference) |
| `pangloss-interface` | `pangloss_interface` | The web interface | [The interface](interface/README.md) |
| `pangloss-admin` | `pangloss_admin` | The page `/admin`, for admins: users, and long-running jobs such as an RDF dump | [The admin page](../implementation_docs/admin.md) (reference) |

## Used from outside a project

| Package | What it is for | Guide |
|---|---|---|
| `pangloss-sdk` | The client: your models' functions as requests to a server. Needs no database driver and no web framework | [The SDK](sdk/README.md) |

## In your editor

| Package | What it is for | Guide |
|---|---|---|
| `pangloss-lsp` | The language server: a mistake in a model shown at its line, quick fixes, completion of the `Meta` options, hover. Extensions for Zed and VS Code | [Language server](../implementation_docs/language-server.md) (reference) |

## For people building packages

| Package | |
|---|---|
| `pangloss-testing` | Fixtures for an add-on's tests that need a live database, on Memgraph or Neo4j. [Backends](backends/README.md#tests-of-add-on-packages) |
| `pydantic-meta-kit` | A separate repository, cloned here for reference and excluded from the workspace. `pangloss_models.meta_kit` is the copy Pangloss uses |

## Across packages

[Searching](search/README.md) (lists, autocomplete, structured search) is built into the models and the API, and works the
same over the SDK.

The dependency picture is in [Packages](../implementation_docs/packages.md).
