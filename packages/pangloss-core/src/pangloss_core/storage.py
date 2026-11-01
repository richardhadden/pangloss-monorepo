"""The storage backend of a project: the object that the setting `STORAGE` names.

```python
STORAGE = "pangloss_memgraph:storage"
```

A backend package gives one `Storage`. It says what the backend can do (`capabilities`), and where its parts are:

- `operations`: the functions the models are bound to (`get`, `save`, `list`, ...; the module `exposed_functions`);
- `setup`: what the command line and the server need (`create_database`, `connect`, `disconnect`, `setup_database`);
- `migration_backend`: what the migrations need, if the backend has migrations;
- `cypher`: for an add-on that runs its own Cypher (typology, calendar), if the backend speaks Cypher (see
  `pangloss_core.backend`).

The parts are imported when they are first asked for, so naming a backend imports nothing of it.

`DATABASE_MODULE`, the module path that came before `STORAGE`, is still read, with a warning: it is taken as a backend
whose parts are in that module (`storage_of` finds the backend's own `Storage` if it has one).
"""

import dataclasses
import importlib
import warnings
from types import ModuleType
from typing import Any


@dataclasses.dataclass(frozen=True)
class Capabilities:
    """What a backend can do, of what not every backend can"""

    snapshots: bool = False
    """`pangloss migrate --backup`, `pangloss backups` and `pangloss restore`"""

    fast_bulk_load: bool = False
    """A bulk load into an empty database in a mode of its own (`pangloss <backend> bulk-load`)"""

    accent_folding: bool = False
    """A search for `zurich` finds "Zürich\""""

    deep_search: bool = False
    """A list searched with `deep` finds what refers to what matches"""

    cypher: bool = False
    """An add-on that runs its own Cypher (typology, calendar) can be installed: `Storage.cypher` is there"""


class PanglossStorageError(Exception):
    """The backend named by the settings cannot be found, or cannot do what is asked of it"""


@dataclasses.dataclass(frozen=True)
class Storage:
    """A storage backend: its name, what it can do, and the module that holds its parts"""

    name: str
    package: str
    """The module whose submodules are the parts: `pangloss_memgraph.databases.memgraph`"""
    capabilities: Capabilities = Capabilities()

    def part(self, name: str) -> ModuleType:
        return importlib.import_module(f"{self.package}.{name}")

    @property
    def operations(self) -> ModuleType:
        """The functions the models are bound to (`exposed_functions`)"""
        return self.part("exposed_functions")

    @property
    def setup(self) -> ModuleType:
        return self.part("setup")

    @property
    def migration_backend(self) -> ModuleType | None:
        """What the migrations need, or `None` if the backend has no migrations"""
        try:
            return self.part("migration_backend")
        except ModuleNotFoundError as error:
            if error.name == f"{self.package}.migration_backend":
                return None
            raise

    @property
    def cypher(self) -> Any:
        """The backend's module for add-ons that run their own Cypher: a `pangloss_core.backend.Backend`"""
        if not self.capabilities.cypher:
            raise PanglossStorageError(
                f"The storage backend {self.name!r} does not run Cypher, which this needs"
            )
        return self.part("backend")


def load(reference: str) -> Storage:
    """The `Storage` named `module:attribute` (`pangloss_memgraph:storage`). The attribute may also be a class or a
    function that makes one, called with nothing."""
    module_name, _, attribute = reference.partition(":")
    if not attribute:
        raise PanglossStorageError(
            f"STORAGE = {reference!r} should be 'module:attribute', like 'pangloss_memgraph:storage'"
        )
    try:
        found = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as error:
        raise PanglossStorageError(
            f"Cannot find the storage backend {reference!r}: {error}"
        ) from error
    if not isinstance(found, Storage) and callable(found):
        found = found()
    if not isinstance(found, Storage):
        raise PanglossStorageError(
            f"{reference!r} is not a storage backend (a `pangloss_core.storage.Storage`)"
        )
    return found


def from_module(database_module: str) -> Storage:
    """The backend whose parts are in `database_module` (what `DATABASE_MODULE` named): the `storage` of its top-level
    package if that is the one, or else one with no capabilities"""
    try:
        own = getattr(
            importlib.import_module(database_module.partition(".")[0]), "storage", None
        )
    except ImportError:
        own = None
    if isinstance(own, Storage) and own.package == database_module:
        return own
    return Storage(name=database_module, package=database_module)


_loaded: dict[str, Storage] = {}


def storage_of(settings: Any = None) -> Storage:
    """The backend of the settings (by default, those of the project: `pangloss_core.settings.SETTINGS`)"""
    if settings is None:
        from pangloss_core.settings import get_settings

        settings = get_settings()
    reference = getattr(settings, "STORAGE", None)
    if reference:
        if reference not in _loaded:
            _loaded[reference] = load(reference)
        return _loaded[reference]
    database_module = getattr(settings, "DATABASE_MODULE", None)
    if database_module:
        key = f"DATABASE_MODULE={database_module}"
        if key not in _loaded:
            _loaded[key] = from_module(database_module)
        return _loaded[key]
    raise PanglossStorageError(
        "The settings name no storage backend: give STORAGE, like 'pangloss_memgraph:storage'"
    )


def check_requirements(settings: Any = None) -> None:
    """Whether the backend can do what the installed apps need. An app says what in its package, by the names of the
    `Capabilities` (`requires = {"cypher"}`); an app that says nothing needs nothing"""
    if settings is None:
        from pangloss_core.settings import get_settings

        settings = get_settings()
    storage = storage_of(settings)
    names = {field.name for field in dataclasses.fields(Capabilities)}
    problems = []
    for app in getattr(settings, "INSTALLED_APPS", []):
        try:
            module = importlib.import_module(app)
        except ModuleNotFoundError as error:
            if error.name == app:
                continue  # (not this check's to report)
            raise
        required = set(getattr(module, "requires", ()))
        unknown = sorted(required - names)
        if unknown:
            problems.append(
                f"{app} requires {', '.join(unknown)}, which is not a capability of a storage backend "
                f"(those are {', '.join(sorted(names))})"
            )
        missing = sorted(
            name for name in required & names if not getattr(storage.capabilities, name)
        )
        if missing:
            problems.append(
                f"{app} needs a storage backend with {', '.join(missing)}, which {storage.name!r} does not have"
            )
    if problems:
        raise PanglossStorageError(
            "The storage backend cannot run the installed apps: " + "; ".join(problems)
        )


def warn_database_module(database_module: str) -> None:
    warnings.warn(
        f"DATABASE_MODULE is replaced by STORAGE: instead of DATABASE_MODULE = {database_module!r}, give STORAGE "
        "= '<package>:storage' (for Memgraph, 'pangloss_memgraph:storage'; for Neo4j, 'pangloss_neo4j:storage')",
        DeprecationWarning,
        stacklevel=4,
    )
