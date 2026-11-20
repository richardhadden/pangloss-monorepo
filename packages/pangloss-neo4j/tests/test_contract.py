"""What the rest of Pangloss calls on a backend is there, with the signatures that Memgraph's has.

The two backends are meant to be interchangeable: `pangloss_users`, `pangloss_review`, `pangloss_api`, `pangloss_cli` and
`pangloss_models` call functions of the parts of the backend that `STORAGE` names, found by name. This compares the
*source* of the two (by `ast`), so that it fails when Memgraph gains a function that Neo4j has not, or one is changed on
one side only."""

import ast
import importlib.util
import inspect
import typing
from pathlib import Path

import pytest
from pangloss_core import backend as core_backend

# (`users` and `review` are one module, in `pangloss-cypher`, shared by both)
MODULES = ["exposed_functions", "setup", "migration_backend"]

# Memgraph's, that Neo4j does not have, and why (each is optional in the contract, or specific to Memgraph)
NOT_IN_NEO4J = {
    "migration_backend": {
        "backup": "Neo4j Community has no online snapshot",
        "backups": "Neo4j Community has no online snapshot",
        "backup_notice": "Neo4j Community has no online snapshot",
        "restore": "Neo4j Community has no online snapshot",
        "rebuild_text_indexes": "a Memgraph snapshot does not bring the files of its text indexes",
    },
}


def source_of(package: str, module: str) -> Path:
    spec = importlib.util.find_spec(package)
    assert spec and spec.submodule_search_locations
    root = Path(next(iter(spec.submodule_search_locations)))
    return next(root.glob(f"databases/*/{module}.py"))


def public_functions(path: Path) -> dict[str, tuple]:
    """The public functions of a module: name -> (async?, argument names, how many have no default, keyword-only names)"""
    tree = ast.parse(path.read_text())
    found = {}
    for node in tree.body:
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and not node.name.startswith("_"):
            args = node.args
            positional = [a.arg for a in [*args.posonlyargs, *args.args]]
            found[node.name] = (
                isinstance(node, ast.AsyncFunctionDef),
                tuple(positional),
                len(positional) - len(args.defaults),
                tuple(a.arg for a in args.kwonlyargs),
            )
    return found


@pytest.mark.parametrize("module", MODULES)
def test_every_public_function_of_memgraphs_is_here_with_the_same_signature(module):
    memgraph = public_functions(source_of("pangloss_memgraph", module))
    neo4j = public_functions(source_of("pangloss_neo4j", module))
    skipped = NOT_IN_NEO4J.get(module, {})
    missing = sorted(set(memgraph) - set(neo4j) - set(skipped))
    assert not missing, f"{module}: not in Neo4j's: {missing}"
    different = {
        name: (memgraph[name], neo4j[name])
        for name in memgraph
        if name in neo4j and memgraph[name] != neo4j[name]
    }
    assert not different, f"{module}: signatures differ: {different}"


@pytest.mark.parametrize("module", MODULES)
def test_what_neo4j_leaves_out_is_said_and_is_really_not_there(module):
    neo4j = public_functions(source_of("pangloss_neo4j", module))
    for name in NOT_IN_NEO4J.get(module, {}):
        assert name not in neo4j, f"{module}.{name} is there: take it off the list"


# --- what the add-on packages take from a backend (pangloss_core.backend) ---------------------------------

BACKENDS = ("pangloss_memgraph:storage", "pangloss_neo4j:storage")
BACKEND_NAMES = typing.get_type_hints(core_backend.Backend).keys()


@pytest.mark.parametrize("module", BACKENDS)
def test_a_backend_gives_every_name_of_the_backend_interface(module):
    found = core_backend.current(module)
    missing = [
        name
        for name in BACKEND_NAMES
        if name not in core_backend.ONLY_WITH_CAPABILITY and not hasattr(found, name)
    ]
    assert not missing, f"the backend of {module} lacks {missing}"


@pytest.mark.parametrize("module", BACKENDS)
@pytest.mark.parametrize("name", sorted(core_backend.ONLY_WITH_CAPABILITY))
def test_a_name_of_a_capability_is_there_exactly_where_the_capability_is(module, name):
    from pangloss_core.storage import load

    capability = core_backend.ONLY_WITH_CAPABILITY[name]
    has = getattr(load(module).capabilities, capability)
    assert hasattr(core_backend.current(module), name) is has


def test_memgraph_installs_query_modules_and_neo4j_does_not():
    from pangloss_core.storage import load

    memgraph, neo4j = (load(module) for module in BACKENDS)
    # (the names of each, as `ONLY_WITH_CAPABILITY` has them)
    assert core_backend.ONLY_WITH_CAPABILITY["install_query_module"] == "query_modules"
    assert memgraph.capabilities.query_modules
    assert hasattr(core_backend.current(BACKENDS[0]), "install_query_module")
    assert not neo4j.capabilities.query_modules
    assert not hasattr(core_backend.current(BACKENDS[1]), "install_query_module")


def test_a_backend_gives_its_dialect():
    for module in BACKENDS:
        found = core_backend.current(module)
        assert found.dialect is found.Database.dialect


@pytest.mark.parametrize(
    "name",
    [
        n
        for n in BACKEND_NAMES
        if n not in ("Database", "Transaction", "database", "fragments", "dialect")
        and n not in core_backend.ONLY_WITH_CAPABILITY
    ],
)
def test_the_functions_of_the_backend_interface_have_the_same_signature_on_both(name):
    signatures = {
        module: str(inspect.signature(getattr(core_backend.current(module), name)))
        for module in BACKENDS
    }
    assert len(set(signatures.values())) == 1, signatures


def test_both_backends_give_the_one_set_of_fragments():
    """(the rule of what a reader sees is the kit's, on every Cypher backend)"""
    from pangloss_cypher import fragments

    assert all(
        core_backend.current(module).fragments is fragments for module in BACKENDS
    )


# --- the dialects (pangloss_cypher.dialect) -------------------------------------------------------------------------


def dialect_parts() -> list[str]:
    from pangloss_cypher import Dialect

    names = {name for name in vars(Dialect) if not name.startswith("_")}
    return sorted(names | set(Dialect.__annotations__))


@pytest.mark.parametrize("name", dialect_parts())
def test_both_dialects_have_every_part_of_the_dialect_with_its_signature(name):
    from pangloss_cypher import Dialect
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect
    from pangloss_neo4j.databases.neo4j.dialect import Neo4jDialect

    for dialect in (MemgraphDialect, Neo4jDialect):
        assert hasattr(dialect, name), f"{dialect.__name__} has no {name}"
        wanted = getattr(Dialect, name, None)
        if callable(wanted) and not isinstance(wanted, type):
            assert inspect.signature(getattr(dialect, name)) == inspect.signature(
                wanted
            ), f"{dialect.__name__}.{name}"


def test_the_search_compiler_of_a_dialect_is_the_kits_or_a_subclass_of_it():
    from pangloss_cypher.search_query import Compiler
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect
    from pangloss_neo4j.databases.neo4j.dialect import Neo4jDialect

    assert MemgraphDialect.search_compiler is Compiler
    assert issubclass(Neo4jDialect.search_compiler, Compiler)


def migration_dialect_parts() -> list[str]:
    from pangloss_cypher import MigrationDialect

    names = {name for name in vars(MigrationDialect) if not name.startswith("_")}
    return sorted(names | set(MigrationDialect.__annotations__))


@pytest.mark.parametrize("name", migration_dialect_parts())
def test_both_dialects_have_every_part_of_the_migration_dialect_with_its_signature(
    name,
):
    from pangloss_cypher import MigrationDialect
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect
    from pangloss_neo4j.databases.neo4j.dialect import Neo4jDialect

    for dialect in (MemgraphDialect(), Neo4jDialect()):
        part = dialect.migrations
        assert hasattr(part, name), f"{type(part).__name__} has no {name}"
        wanted = getattr(MigrationDialect, name, None)
        if callable(wanted) and not isinstance(wanted, type):
            assert inspect.signature(getattr(type(part), name)) == inspect.signature(
                wanted
            ), f"{type(part).__name__}.{name}"
