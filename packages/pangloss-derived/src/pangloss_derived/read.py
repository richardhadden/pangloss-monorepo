"""Reading derived facts: a page of those of a class (of an entity, or fitting a `Where`), one with its justifications,
the graph of a type of rule, and the `_derived` of a head node's view.

What a reader sees is one rule, `fragments.derived_visible`: a fact one of whose justifications rests only on head nodes
the reader sees, and none of whose entities is deleted. Nothing is recomputed for it: a document deleted or unpublished
hides at once what only it justifies, before the worker has caught up.
"""

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pangloss_derived.declare import Derived

from pangloss_core import backend
from pangloss_cypher import fragments
from pangloss_core.backend import Transaction
from pangloss_cypher.values import native_datetime

from pangloss_derived.check import ends_of
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.store import FACT, JUSTIFICATION
from pangloss_derived.views import JustificationView, ids

MAX_PAGE_SIZE = 100
FIRST_PAGE = 25


def derived_class(name: str) -> type[Derived]:
    model = DerivedRegistry.concrete_classes().get(name)
    if model is None:
        raise PanglossDerivedError(f"There is no derived class called {name!r}")
    return model


def see_unpublished() -> bool:
    return backend.current().unpublished_visible()


def database() -> Any:
    return backend.current().database()


# (the ends of a fact, and its literal values, as the view has them)
FACT_FIELDS = """
d {.*, ends: [(d)-[r]->(x:PGIndexableNode) | {field: type(r), id: x.id, type: x.type, label: x.label}]} AS fact
"""


def view_of(
    model: type[Derived], fact: dict[str, Any], justifications: list[Any] | None = None
) -> Any:
    values: dict[str, Any] = {}
    for end in fact.get("ends", []):
        values[end["field"]] = {
            "id": end["id"],
            "type": end["type"],
            "label": end["label"],
        }
    for field in model._fields.values():
        if field.kind == "literal":
            values[field.name] = fact.get(field.name)
    return model.View(
        id=fact["key"],
        type=model.__name__,
        context_labels=fact.get("context_labels") or [],
        qualified_only=bool(fact.get("qualified_only")),
        types=fact.get("types") or [],
        justification_count=fact.get("justifications") or 0,
        justifications=justifications,
        **values,
    )


def filters(
    model: type[Derived], where: Any, param: Callable[[Any], str], d: str = "d"
) -> list[str]:
    """The conditions of a `Where` on the fact `d` (`param(value)` gives a value as a parameter, by its name)"""
    conditions: list[str] = []
    if where is None:
        return conditions
    for field in model._fields.values():
        value = getattr(where, field.name, None)
        if value is None:
            continue
        if field.kind == "relation":
            conditions.append(
                f"({d})-[:{fragments.field_edge(field.name)}]->(:PGIndexableNode {{id: {param(ids(value))}}})"
            )
        else:
            conditions.append(
                f"{d}.{fragments.field_edge(field.name)} = {param(getattr(value, 'value', value))}"
            )
    if where.plain is True:
        conditions.append(f"NOT coalesce({d}.qualified_only, false)")
    elif where.plain is False:
        conditions.append(f"coalesce({d}.qualified_only, false)")
    if where.context_label is not None:
        conditions.append(
            f"{param(where.context_label)} IN coalesce({d}.context_labels, [])"
        )
    if where.rule_type is not None:
        conditions.append(f"{param(where.rule_type)} IN coalesce({d}.types, [])")
    return conditions


def parameter(params: dict[str, Any]) -> Callable[[Any], str]:
    """A way of giving values as parameters of a query, into `params`"""

    def param(value: Any) -> str:
        name = f"f{len(params)}"
        params[name] = value
        return f"${name}"

    return param


def start_of(
    model: type[Derived], entity: Any, evidence: Any, params: dict[str, Any]
) -> str:
    """The `MATCH` that finds the facts of the class: all of them, those about an entity (at any field), or those a
    head document is evidence of"""
    label = fragments.label(model.__name__)
    if entity is not None:
        params["entity"] = ids(entity)
        return f"MATCH (:PGIndexableNode {{id: $entity}})<-[]-(d:{FACT}:{label})"
    if evidence is not None:
        params["evidence"] = ids(evidence)
        return f"MATCH (:HeadNode {{id: $evidence}})<-[:evidence]-(:{JUSTIFICATION})-[:justifies]->(d:{FACT}:{label})"
    return f"MATCH (d:{FACT}:{label})"


async def list_facts(
    model: type[Derived],
    where: Any = None,
    entity: Any = None,
    page: int = 1,
    page_size: int = FIRST_PAGE,
    evidence: Any = None,
) -> dict[str, Any]:
    """A page of the facts of the class the reader sees (of an entity, at any of its fields; or those a head document is
    `evidence` of; fitting `where`), in order of the label of their first end"""
    page_size = min(page_size, MAX_PAGE_SIZE)
    params: dict[str, Any] = {
        "see_unpublished": see_unpublished(),
        "skip": (page - 1) * page_size,
        "limit": page_size,
    }
    first = fragments.field_edge(ends_of(model)[0])
    start = start_of(model, entity, evidence, params)
    conditions = [
        fragments.derived_visible("d"),
        *filters(model, where, parameter(params)),
    ]
    query = f"""
    {start}
    WHERE {" AND ".join(conditions)}
    WITH DISTINCT d
    OPTIONAL MATCH (d)-[:{first}]->(f)
    WITH d, toLower(coalesce(f.label, '')) AS sort
    ORDER BY sort, d.key
    WITH collect(d) AS facts
    WITH facts, size(facts) AS total
    UNWIND facts[$skip..$skip + $limit] AS d
    RETURN total, {FACT_FIELDS}
    """
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> tuple[int, list[dict[str, Any]]]:
        result = await tx.run(query, params)
        rows = [dict(r) async for r in result]
        if not rows:
            # (the count, when the page is past the end)
            return 0, []
        return rows[0]["total"], [r["fact"] for r in rows]

    total, facts = await read()
    if total == 0 and page > 1:
        total = await count_facts(model, where, entity, evidence)
    return {
        "results": [view_of(model, f) for f in facts],
        "count": total,
        "page": page,
        "page_size": page_size,
        "next_page": page + 1 if page * page_size < total else None,
        "previous_page": page - 1 if page > 1 else None,
    }


async def count_facts(
    model: type[Derived], where: Any = None, entity: Any = None, evidence: Any = None
) -> int:
    params: dict[str, Any] = {"see_unpublished": see_unpublished()}
    start = start_of(model, entity, evidence, params)
    conditions = [
        fragments.derived_visible("d"),
        *filters(model, where, parameter(params)),
    ]
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> int:
        result = await tx.run(
            f"{start} WHERE {' AND '.join(conditions)} RETURN count(DISTINCT d) AS n",
            params,
        )
        record = await result.single()
        return record["n"] if record else 0

    return await read()


JUSTIFICATIONS_QUERY = f"""
MATCH (d:{FACT} {{key: $key}})<-[:justifies]-(j:{JUSTIFICATION})
WITH j, [(j)-[:evidence]->(h) | h] AS heads
WHERE all(v IN heads WHERE {fragments.visible("v")})
UNWIND heads AS e
WITH j, collect({{id: e.id, type: e.type, label: e.label, published: {fragments.published("e")}}}) AS evidence
RETURN j {{.*}} AS justification, evidence
ORDER BY j.rule, j.key
"""


async def get_fact(model: type[Derived], key: str) -> Any | None:
    """A fact, with the justifications the reader can see ("why"); None if the reader sees none"""
    params = {"key": key, "see_unpublished": see_unpublished()}
    label = fragments.label(model.__name__)
    db = database()

    @db.read_transaction
    async def read(
        tx: Transaction,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        result = await tx.run(
            f"MATCH (d:{FACT}:{label} {{key: $key}}) WHERE {fragments.derived_visible('d')} RETURN {FACT_FIELDS}",
            params,
        )
        record = await result.single()
        if record is None:
            return None, []
        result = await tx.run(JUSTIFICATIONS_QUERY, params)
        return record["fact"], [dict(r) async for r in result]

    fact, rows = await read()
    if fact is None:
        return None
    justifications = []
    for row in rows:
        j = row["justification"]
        declared = DerivedRegistry.rules.get(j["rule"])
        context = j.get("context")
        justifications.append(
            JustificationView(
                key=j["key"],
                rule=j["rule"],
                description=declared.description if declared else "",
                types=j.get("types") or [],
                nodes=j.get("nodes") or [],
                evidence=row["evidence"],
                context=json.loads(context)
                if isinstance(context, str)
                else context or {},
                context_labels=j.get("context_labels") or [],
                derived_at=native_datetime(j.get("derived_at")),
            )
        )
    return view_of(model, fact, justifications)


# ---------------------------------------------------------------------------
# A graph of a type of rule
# ---------------------------------------------------------------------------


def rules_of_type(name: str) -> list[str]:
    if name not in DerivedRegistry.types:
        raise PanglossDerivedError(f"There is no type of rule called {name!r}")
    return [
        rule.name
        for rule in DerivedRegistry.checked.values()
        if name in rule.type_names
    ]


async def graph(type_name: str, plain_only: bool = False) -> list[dict[str, Any]]:
    """The facts derived by the rules of a type, as edges: the two ends of each (its class's `ends`), its class, its other
    fields, how many justifications of the type it has that the reader sees, whether one of them is plain, and the
    context labels of those. Each fact is one edge, however many justifications it has"""
    rules = rules_of_type(type_name)
    edges: list[dict[str, Any]] = []
    if not rules:
        return edges
    params = {"rules": rules, "see_unpublished": see_unpublished()}
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            MATCH (j:{JUSTIFICATION})-[:justifies]->(d:{FACT})
            WHERE j.rule IN $rules
              AND all(h IN [(j)-[:evidence]->(h) | h] WHERE {fragments.visible("h")})
              AND all(e IN [(d)-[]->(e:Entity) | e] WHERE {fragments.not_deleted("e")})
            WITH d, collect(j) AS js
            RETURN {FACT_FIELDS},
                   size(js) AS justifications,
                   any(j IN js WHERE size(j.context_labels) = 0) AS plain,
                   reduce(acc = [], j IN js | acc + [l IN j.context_labels WHERE NOT l IN acc]) AS context_labels
            """,
            params,
        )
        return [dict(r) async for r in result]

    for row in await read():
        if plain_only and not row["plain"]:
            continue
        fact = row["fact"]
        model = DerivedRegistry.classes.get(fact.get("type"))
        if model is None:
            continue
        source_field, target_field = ends_of(model)
        ends = {e["field"]: e for e in fact.get("ends", [])}
        if source_field not in ends or target_field not in ends:
            continue
        attributes = {
            field: (
                {
                    "id": ends[field]["id"],
                    "type": ends[field]["type"],
                    "label": ends[field]["label"],
                }
                if field in ends
                else fact.get(field)
            )
            for field in model._fields
            if field not in (source_field, target_field)
        }
        edges.append(
            {
                "id": fact["key"],
                "class": model.__name__,
                "source": ends[source_field],
                "target": ends[target_field],
                "symmetric": bool(model._meta.symmetric),
                "attributes": attributes,
                "justifications": row["justifications"],
                "plain": row["plain"],
                "context_labels": row["context_labels"],
            }
        )
    edges.sort(
        key=lambda e: (e["class"], str(e["source"]["label"]), str(e["target"]["label"]))
    )
    return edges


# ---------------------------------------------------------------------------
# `_derived` of a head node's view
# ---------------------------------------------------------------------------


def classes_pointing_at(owner: type) -> list[tuple[type[Derived], list[str]]]:
    """The concrete derived classes with a relation field that can point at an entity of the class, and those fields"""
    found = []
    for model in DerivedRegistry.concrete_classes().values():
        fields = [
            f.name
            for f in model._fields.values()
            if f.kind == "relation"
            and isinstance(f.model, type)
            and (issubclass(owner, f.model) or issubclass(f.model, owner))
        ]
        if fields:
            found.append((model, fields))
    return found


def key_of(model: type[Derived], fields: list[str]) -> str:
    names = model._meta.reverse_names
    for field in fields:
        if field in names:
            return names[field]
    return model.__name__


async def derived_of_entity(owner: type, id: Any) -> dict[str, Any]:
    """For each derived class that can point at the entity: the count of its facts about it, and a first page, each with
    the other end (`other`, for a symmetric class or one of two ends) and the other fields"""
    section: dict[str, Any] = {}
    for model, fields in classes_pointing_at(owner):
        page = await list_facts(model, entity=id, page_size=FIRST_PAGE)
        if not page["count"]:
            continue
        items = []
        for view in page["results"]:
            data = view.model_dump(
                by_alias=True, mode="json", exclude={"justifications"}
            )
            own = [f for f in fields if str(data.get(f, {}).get("id")) == str(id)]
            ends = ends_of(model)
            other_field = (
                next((f for f in ends if f not in own), None)
                if any(f in ends for f in own)
                else None
            )
            item = {
                "id": data["id"],
                "type": model.__name__,
                "as": own,
                "other": data.get(other_field) if other_field else None,
                "otherField": other_field,
                "fields": {
                    k: data[k]
                    for k in model._fields
                    if k not in own and k != other_field
                },
                "contextLabels": data["contextLabels"],
                "qualifiedOnly": data["qualifiedOnly"],
                "types": data["types"],
                "justifications": data["justificationCount"],
            }
            items.append(item)
        section[key_of(model, fields)] = {"count": page["count"], "items": items}
    return section


async def derived_of_document(owner: type, id: Any) -> dict[str, Any]:
    """For each derived class: the facts that this head document is evidence of (a count, and a first page), each with
    the nodes of the document that the justification used"""
    params = {"id": str(id), "see_unpublished": see_unpublished(), "limit": FIRST_PAGE}
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            MATCH (:HeadNode {{id: $id}})<-[:evidence]-(j:{JUSTIFICATION})-[:justifies]->(d:{FACT})
            WHERE {fragments.derived_visible("d")}
            WITH d, collect(j.rule) AS rules, collect(j.nodes) AS nodes
            WITH d, rules, nodes, {FACT_FIELDS}
            ORDER BY d.key
            WITH d.type AS type, collect({{fact: fact, rules: rules, nodes: nodes}}) AS found
            RETURN type, size(found) AS count, found[..$limit] AS items
            """,
            params,
        )
        return [dict(r) async for r in result]

    section: dict[str, Any] = {}
    for row in await read():
        model = DerivedRegistry.classes.get(row["type"])
        if model is None:
            continue
        items = []
        for item in row["items"]:
            view = view_of(model, item["fact"])
            data = view.model_dump(
                by_alias=True, mode="json", exclude={"justifications"}
            )
            data["rules"] = sorted(set(item["rules"]))
            data["nodes"] = sorted({n for nodes in item["nodes"] for n in nodes})
            items.append(data)
        section[model.__name__] = {"count": row["count"], "items": items}
    return section


async def derived_section(owner: type, view: Any) -> dict[str, Any]:
    """(`hooks.head_view_extras`) `_derived` of the view of a head node: what the rules derive about an entity, or what
    a head document is evidence of. Not given when there is nothing"""
    from pangloss_models.model_bases.document import Document
    from pangloss_models.model_bases.entity import Entity

    if not DerivedRegistry.checked:
        return {}
    if issubclass(owner, Entity):
        section = await derived_of_entity(owner, view.id)
    elif issubclass(owner, Document):
        section = await derived_of_document(owner, view.id)
    else:
        return {}
    return {"_derived": section} if section else {}
