"""The database module of the backend under test (`PANGLOSS_TEST_BACKEND`), as a package of its own name, so that a test
written once imports what it needs of the backend it runs on:

    from pangloss_testing.under_test.database import current
    from pangloss_testing.under_test import migration_backend

is `pangloss_memgraph.databases.memgraph.database` on Memgraph and `pangloss_neo4j.databases.neo4j.database` on Neo4j. The
modules are the backend's own (the same objects: patching one patches the backend's)."""

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType

from pangloss_testing.backends import under_test

_backend = under_test()

# (a package: its submodules are found by `_Aliases`)
__path__: list[str] = []


class _Existing(importlib.abc.Loader):
    def __init__(self, module: ModuleType) -> None:
        self.module = module

    def create_module(self, spec):
        return self.module

    def exec_module(self, module) -> None:
        pass


class _Aliases(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        prefix = __name__ + "."
        if not name.startswith(prefix):
            return None
        real = importlib.import_module(
            f"{_backend.database_module}.{name.removeprefix(prefix)}"
        )
        # (typeshed's `LoaderProtocol` still asks for `load_module`, which `importlib.abc.Loader` no longer has)
        return importlib.util.spec_from_loader(
            name,
            _Existing(real),  # ty: ignore[invalid-argument-type]
            is_package=hasattr(real, "__path__"),
        )


if not any(isinstance(finder, _Aliases) for finder in sys.meta_path):
    sys.meta_path.insert(0, _Aliases())
