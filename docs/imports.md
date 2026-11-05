# Importing from the packages

Status: ✅ built (2026-11-06, branch `fix-imports`).

Every package exports what a project, a script or an add-on uses from its root:

```python
from pangloss_models import Document, Entity, ReifiedRelation, RelationConfig, ViaEdge, initialise
from pangloss_dates import Date, Dateable, SortBy, SortDefault
from pangloss_calendar import DateCharacterisation
from pangloss_core import BaseSettings
from pangloss_memgraph import MemgraphDatabaseSettings
```

and not from the file the class happens to be in (`pangloss_models.model_bases.document`). The files are where the code
is kept; they can move without anyone's imports changing.

## The plan

1. **Decide what is public, per package**, and list it in the root `__init__.py` with `__all__`. Public means what a
   project's models, settings, scripts and migrations use, and what an add-on's author uses (hooks, meta slots,
   `ModelRegistry`, exceptions, the Cypher transactions). Internals (the generated-model builder, field-definition
   classes, write plans, query builders, a backend's DDL) stay in their modules: code that needs them is working on the
   package, not with it.
2. **Use `lazy from … import …` in the root** (Python 3.15). Nothing is imported until a name is used, so
   - `import pangloss_dates` (an app is imported by name at start-up) does not declare the date models as a side
     effect, and `from pangloss_dates import Calendar` imports only the calendar arithmetic;
   - no import cycles: a module of `pangloss_models` that is being imported can import a sibling's root without the
     whole package having to be ready.
   `ty` follows lazy re-exports, so editors and the stubs see the real types.
3. **No root name may be the name of a submodule** (`pangloss_dates.easter` is a module, so the function `easter` is not
   exported; the same for `pangloss_zotero.convert`, `pangloss_history.restore` and `.diff`): a function bound over a
   module breaks `pangloss_dates.easter.<name>` and `mock.patch`.
4. **Rewrite every import from outside a package** (other packages, tests, the demo, the docs and guides, the
   `new-app` template, the migration file header) so that a public name comes from the root; a line that also imports
   internals keeps those in their module. Inside a package its own modules keep importing from each other's files (a
   package's root imports them, not the other way round).
5. **Migrations** are a subsystem of their own: `pangloss_models.migrations` exports what a migration file uses
   (`changes_from_data`, `RunPython`, `RunCypher`, `StateOnly` and the other changes), and `makemigrations` writes
   `from pangloss_models.migrations import changes_from_data`. Existing migration files are rewritten too (a migration's
   checksum is of its changes, not of its text).
6. Stubs of the demo made again; the docs, the guide and the skill say how to import.

### As built

- The rewrite was done by a script that moves a name to the root only where the root's name **is** the same object;
  an import that also takes internals is split in two. Imports with `as` are kept on lines of their own.
- **A lazy name must not be the name of a submodule, even one exported before.** `pangloss_models.migrations` had
  exported the function `diff` (from the module `diff`) eagerly; made lazy, importing the module
  `pangloss_models.migrations.diff` first put the module in its place (`'module' object is not callable`). The names
  that package exported before stay eager; only the new ones are lazy.
- **A test that reloads a module to declare its models again must reload the roots that re-export from it.** The
  calendar's live tests reload `pangloss_dates.models`; `pangloss_calendar.models` now imports `Date` from the
  `pangloss_dates` root, which had kept the class from before the reload. They reload `pangloss_dates` too.

### Not done: a `pangloss` namespace

A PEP 420 namespace (`from pangloss.models import Document`) is possible, but a package's module name is also its app
name: `"pangloss_dates"` is what `INSTALLED_APPS` lists, what a migration's `dependencies` name, what the migration
records in a database are kept under, and what translation files and SDK builds use. Renaming would mean changing all
of those in every database and project (or a mapping between two names kept for ever), and a thin `pangloss.<name>`
re-export would leave two spellings of everything. Decided (2026-11-06): root exports only.

## What each root exports

See each package's `__init__.py` (`__all__`); in short:

| Package | Exports |
|---|---|
| `pangloss_models` | `initialise`, `ModelRegistry`; the model kinds (`Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `ReifiedRelation`, `ReifiedRelationDocument`, `SemanticSpace`, `Conjunction`, `AnnotatedValue`, `EdgeModel`, `ContextLabel`); `RelationConfig`, `ViaEdge`, `Fulfils`, `DBField`, `Description`, `FieldBinding`, `FieldSubclassing`, `SumsTo`, `FieldMarker`; search (`Match`, `OrderBy`, `Var`, `AnyOf`, `Not`, `Where`, `Rel`, `AnyRel`, `Text`, `Compare`, `Choice`, `Items`, `IncomingFrom`); for add-ons `hooks`, `WriteEvent`, `register_meta_slot`, `Protection`, `protection_of`, `server_only`, `export_models`, `fold`; every `Pangloss…Error` |
| `pangloss_models.migrations` | `changes_from_data`, every change class (`RunPython`, `RunCypher`, `StateOnly`, `AddField`, …), and the planner's tools (`diff`, `replay`, `build_snapshot`, …) |
| `pangloss_core` | `BaseSettings`, `ClientSettings`, `DatabaseSettings`, `get_settings`, `Storage`, `Capabilities`, `PanglossStorageError`, `storage_of`, `check_requirements`, `Backend`, `Transaction` (the modules `settings`, `storage`, `backend`, `logs` as before) |
| `pangloss_cypher` | `read_transaction`, `write_transaction`, `Database`, `Transaction`, `Dialect`, `MigrationDialect` |
| `pangloss_memgraph`, `pangloss_neo4j` | `storage`, and their `…DatabaseSettings` |
| `pangloss_users` | `current_request_username`, `see_unpublished`, `service` (a module), `User`, `UserCreate`, `UserUpdate`, `UserInDB`, the user exceptions |
| `pangloss_api` | `create_app`, `BackgroundTask`, `get_current_user`, `CurrentUser`, `CurrentAdmin` |
| `pangloss_cli` | `load_project`, `Project` |
| `pangloss_dates` | the date models and their Julian and Gregorian families, `Dateable`, `SingleDateable`, `PeriodDateable`, `SortBy`, `Precision`, `Calendar`, `Weekday`, the day arithmetic (`to_jdn`, `from_jdn`, …), recurrence rules, the derived-rule constraints (`overlaps`, …), `on_day` |
| `pangloss_calendar` | `DateCharacterisation`, `NoRule` |
| `pangloss_library` | `WeightedAlternative`, `Likelihood` |
| `pangloss_review` | `ReviewMeta`, `ReviewStatus` and the other status models, `is_reviewable`, the review exceptions |
| `pangloss_history` | `HistoryStore`, `SqliteStore`, `HistoryRecord`, `PanglossRestoreError` |
| `pangloss_typology`, `pangloss_zotero`, `pangloss_derived`, `pangloss_interface`, `pangloss_sdk` | as before, and `InterfaceConfig`, `NavLink`, `NavModel` in `pangloss_interface`; `ZoteroClient`, `ZoteroError` in `pangloss_zotero` |
