"""Derived facts in a search: `$derived` on the pattern of an entity, the entity has a derived fact of a class, fitting
a filter (`pangloss_models.search.Extension`).

    Person.search(Person.Where(derived_=SameGroup.Where(group=medici, plain=True)))
    {"type": "Person", "where": {"$derived": {"type": "SameGroup", "where": {"group": "<id>", "plain": true}}}}

What is seen is as everywhere: a fact one of whose justifications rests on documents the reader sees
(`fragments.derived_visible`; the search gives `$see_unpublished`).
"""

from typing import TYPE_CHECKING, Any

from pangloss_models.exceptions import PanglossSearchError
from pangloss_models.search import Checked, Extension, register_extension
from pangloss_models.search_where import WhereExtension, where_extensions

from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.views import DerivedWhere

if TYPE_CHECKING:
    from pangloss_derived.declare import Derived

FACT = "PGDerived"

KEY = "$derived"


def fact_conditions(model: "type[Derived]", where: Any, d: str, param) -> list[str]:
    """The conditions of a `DerivedWhere` on the fact `d` (shared with `read.filters`)"""
    from pangloss_derived.read import filters

    return filters(model, where, param, d)


def check_derived(model: type, value: Any, top: bool, path: str) -> Checked:
    field = f"{path}{KEY}"
    if isinstance(value, DerivedWhere):
        value = value.to_json()
    if not isinstance(value, dict) or "type" not in value:
        raise PanglossSearchError(
            f"{field}: needs the derived class ('type') and, if wanted, a filter ('where'), or a `SomeDerived.Where(...)`"
        )
    derived = DerivedRegistry.concrete_classes().get(value["type"])
    if derived is None:
        known = ", ".join(sorted(DerivedRegistry.concrete_classes())) or "(none)"
        raise PanglossSearchError(
            f"{field}: there is no derived class called {value['type']!r} (there are {known})"
        )
    reaching = [
        f.name
        for f in derived._fields.values()
        if f.kind == "relation"
        and isinstance(f.model, type)
        and (issubclass(model, f.model) or issubclass(f.model, model))
    ]
    if not reaching:
        raise PanglossSearchError(
            f"{field}: no field of {derived.__name__} is a {model.__name__}"
        )
    where = value.get("where") or {}
    where = {k: v for k, v in where.items() if k != "type"}
    try:
        checked_where = derived.Where(**where)
    except ValueError as error:
        raise PanglossSearchError(f"{field}: {error}") from None

    def cypher(compiler: Any, var: str) -> str:
        # (imported here: a client of the SDK has this package with the models, and no database)
        from pangloss_cypher import fragments

        label = fragments.label(derived.__name__)
        edges = "|".join(fragments.field_edge(f) for f in reaching)
        d = compiler.name("d")
        conditions = [
            fragments.derived_visible(d),
            *fact_conditions(derived, checked_where, d, compiler.param),
        ]
        return (
            f"EXISTS {{ MATCH ({var})<-[:{edges}]-({d}:{FACT}:{label}) "
            f"WHERE {' AND '.join(conditions)} }}"
        )

    return Checked(cypher, f"a {derived.__name__}")


def install() -> None:
    """(At import of the package) the key, and the `derived_` field of every entity's `Where`"""
    register_extension(Extension(KEY, check_derived, kinds=("entity",)))
    if not any(e.name == "derived_" for e in where_extensions):
        where_extensions.append(
            WhereExtension("derived_", KEY, DerivedWhere | dict | None, ("Entity",))
        )
