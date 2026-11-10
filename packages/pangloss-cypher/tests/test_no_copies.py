"""What is in the kit is not also in a backend: a module of the kit is not copied back into one (by its name, or by its
text with the backend's name taken out). A backend that needs to differ changes the kit, or takes the module's name out
of the kit."""

import re
from pathlib import Path

import pytest

PACKAGES = Path(__file__).parents[2]
KIT = PACKAGES / "pangloss-cypher/src/pangloss_cypher"
BACKENDS = {
    "memgraph": PACKAGES / "pangloss-memgraph/src/pangloss_memgraph/databases/memgraph",
    "neo4j": PACKAGES / "pangloss-neo4j/src/pangloss_neo4j/databases/neo4j",
}


def normalised(path: Path, name: str) -> str:
    text = re.sub(
        rf"pangloss_{name}\.databases\.{name}|pangloss_cypher", "KIT", path.read_text()
    )
    text = re.sub(name, "BACKEND", text, flags=re.I)
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


# (what the kit declares and each backend gives its own of)
PER_BACKEND = {"__init__.py", "dialect.py"}


def kit_modules() -> list[Path]:
    return sorted(p for p in KIT.glob("*.py") if p.name not in PER_BACKEND)


@pytest.mark.parametrize("backend", BACKENDS)
def test_no_module_of_the_kit_is_in_a_backend_by_its_name(backend):
    copied = [p.name for p in kit_modules() if (BACKENDS[backend] / p.name).exists()]
    assert not copied, f"{backend} has modules of pangloss-cypher: {copied}"


@pytest.mark.parametrize("backend", BACKENDS)
def test_no_module_of_a_backend_is_the_text_of_one_of_the_kit(backend):
    kit = {normalised(p, "cypher"): p.name for p in kit_modules()}
    copied = [
        (p.name, kit[text])
        for p in BACKENDS[backend].rglob("*.py")
        if (text := normalised(p, backend)) in kit
    ]
    assert not copied, f"{backend} has copies of pangloss-cypher's modules: {copied}"


def top_level_functions(path: Path) -> set[str]:
    import ast

    return {
        node.name
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


@pytest.mark.parametrize("backend", BACKENDS)
def test_a_backend_does_not_write_again_what_the_kit_s_record_of_migrations_has(
    backend,
):
    """(Until 2026-11-10 each backend's `migration_backend` had its own copy of the record, the lock, `apply` and
    `unapply`: 300 lines, the same but for the logger's name)"""
    kit = top_level_functions(KIT / "migrations/record.py")
    assert {"apply", "unapply", "lock", "unlock", "applied"} <= kit
    own = top_level_functions(BACKENDS[backend] / "migration_backend.py")
    assert not (own & kit), f"{backend} defines again: {sorted(own & kit)}"
