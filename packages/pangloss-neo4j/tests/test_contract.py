"""What the rest of Pangloss calls on a backend is there, with the signatures that Memgraph's has.

The two backends are meant to be interchangeable: `pangloss_users`, `pangloss_review`, `pangloss_api`, `pangloss_cli` and
`pangloss_models` call functions of the module that `DATABASE_MODULE` names, found by name. This compares the *source* of
the two (by `ast`: Memgraph's `exposed_functions` cannot be imported without a Memgraph `Database` of its own), so that it
fails when Memgraph gains a function that Neo4j has not, or one is changed on one side only."""

import ast
import importlib.util
from pathlib import Path

import pytest

MODULES = ["exposed_functions", "setup", "migration_backend", "users", "review"]

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
