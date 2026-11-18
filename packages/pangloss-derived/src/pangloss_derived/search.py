"""Derived edges in a search: `$derived` on the pattern of an entity, the entity has a derived edge of a class, fitting
a filter (`pangloss_models.search.Extension`).

    Person.search(Person.Where(derived_=SameGroup.Where(group=medici, plain=True)))
    {"type": "Person", "where": {"$derived": {"type": "SameGroup", "where": {"group": "<id>", "plain": true}}}}

What is seen is as everywhere: a fact one of whose justifications rests on documents the reader sees
(`fragments.derived_visible`; the search gives `$see_unpublished`).

An end that the filter gives is the *other* end: `Person.Where(derived_=GaveTo.Where(receiver=b))` are those who gave
to b, not b; of a symmetric class, `SameGroup.Where(first=b)` are those in a group with b (at either end), not b.
"""

from typing import TYPE_CHECKING, Any

from pangloss_models import PanglossSearchError
from pangloss_models.search import Checked, Extension, register_extension
from pangloss_models.search_where import WhereExtension, where_extensions

from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.views import DerivedWhere

if TYPE_CHECKING:
    from pangloss_derived.declare import DerivedEdge

FACT = "PGDerived"

KEY = "$derived"


def fact_conditions(model: "type[DerivedEdge]", where: Any, d: str, param) -> list[str]:
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
        and f.role != "per_justification"
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

        from pangloss_derived.views import ids

        label = fragments.label(derived.__name__)
        d = compiler.name("d")
        conditions = [
            fragments.derived_visible(d),
            *fact_conditions(derived, checked_where, d, compiler.param),
        ]
        # (an end the filter gives is not the entity looked for: it is the one at the other end)
        given = [
            f for f in derived._ends if getattr(checked_where, f, None) is not None
        ]
        at = reaching
        if derived._meta.symmetric:
            conditions += [
                f"{var}.id <> {compiler.param(ids(getattr(checked_where, f)))}"
                for f in given
            ]
        else:
            at = [f for f in reaching if f not in given] or reaching
        edges = "|".join(fragments.field_edge(f) for f in at)
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
