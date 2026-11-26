"""Reading derived edges (the stored "facts"): a page of those of a class (of an entity, or fitting a `Where`), one
with its justifications, the graph of a type of rule, and the `_derived` of a head node's view.

What a reader sees is one rule, `fragments.derived_visible`: a fact one of whose justifications rests only on head nodes
the reader sees, and none of whose entities is deleted. Nothing is recomputed for it: a document deleted or unpublished
hides at once what only it justifies, before the worker has caught up.
"""

import json
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pangloss_derived.declare import DerivedEdge

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments
from pangloss_cypher.values import native_datetime

from pangloss_derived.check import ends_of
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.status import summed, summed_standing
from pangloss_derived.store import FACT, JUSTIFICATION
from pangloss_derived.views import JustificationView, ids

MAX_PAGE_SIZE = 100
FIRST_PAGE = 25


def derived_class(name: str) -> type[DerivedEdge]:
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
    model: type[DerivedEdge],
    fact: dict[str, Any],
    justifications: list[Any] | None = None,
) -> Any:
    refs: dict[str, Any] = {}
    for end in fact.get("ends", []):
        refs[end["field"]] = {
            "id": end["id"],
            "type": end["type"],
            "label": end["label"],
        }
    subject, object_ = model._ends
    qualifiers: dict[str, Any] = {}
    for field in model.qualifiers():
        qualifiers[field.name] = (
            refs.get(field.name) if field.kind == "relation" else fact.get(field.name)
        )
    qualified_only = bool(fact.get("qualified_only"))
    return model.View(
        id=fact["key"],
        type=model.__name__,
        ends=[subject, object_],
        symmetric=bool(model._meta.symmetric),
        plain=not qualified_only,
        context_labels=fact.get("context_labels") or [],
        qualified_only=qualified_only,
        status=fact["status"],
        statuses=fact.get("statuses") or [],
        standing=fact["standing"],
        types=fact.get("types") or [],
        justification_count=fact.get("justifications") or 0,
        justifications=justifications,
        qualifiers=qualifiers,
        **{subject: refs[subject], object_: refs[object_]},
    )


def filters(
    model: type[DerivedEdge], where: Any, param: Callable[[Any], str], d: str = "d"
) -> list[str]:
    """The conditions of a `Where` on the fact `d` (`param(value)` gives a value as a parameter, by its name)"""
    conditions: list[str] = []
    if where is None:
        return conditions
    # (of a symmetric class, which end an entity is at is only the order of two ids: a value for either matches both)
    either = (
        "|".join(fragments.field_edge(f) for f in model._ends)
        if model._meta.symmetric
        else None
    )
    for field in model._fields.values():
        if field.role == "per_justification":
            continue
        value = getattr(where, field.name, None)
        if value is None:
            continue
        if field.kind == "relation":
            edge = (
                either
                if either and field.name in model._ends
                else fragments.field_edge(field.name)
            )
            conditions.append(
                f"({d})-[:{edge}]->(:PGIndexableNode {{id: {param(ids(value))}}})"
            )
        else:
            conditions.append(
                f"{d}.{fragments.field_edge(field.name)} = {param(getattr(value, 'value', value))}"
            )
    if where.plain is True:
        conditions.append(f"NOT coalesce({d}.qualified_only, false)")
    elif where.plain is False:
        conditions.append(f"coalesce({d}.qualified_only, false)")
    if where.status is not None:
        conditions.append(f"{d}.status = {param(where.status)}")
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
    model: type[DerivedEdge],
    entity: Any,
    evidence: Any,
    params: dict[str, Any],
    at: Sequence[str] | None = None,
) -> str:
    """The `MATCH` that finds the facts of the class: all of them, those about an entity (at any field, or at one of
    the fields `at`), or those a head document is evidence of"""
    label = fragments.label(model.__name__)
    if entity is not None:
        params["entity"] = ids(entity)
        edges = ""
        if at:
            unknown = [f for f in at if f not in model._fields]
            if unknown:
                raise PanglossDerivedError(
                    f"{model.__name__} has no field {unknown[0]!r} (it has: {', '.join(model._fields)})"
                )
            edges = ":" + "|".join(fragments.field_edge(f) for f in at)
        return f"MATCH (:PGIndexableNode {{id: $entity}})<-[{edges}]-(d:{FACT}:{label})"
    if evidence is not None:
        params["evidence"] = ids(evidence)
        return f"MATCH (:HeadNode {{id: $evidence}})<-[:evidence]-(:{JUSTIFICATION})-[:justifies]->(d:{FACT}:{label})"
    return f"MATCH (d:{FACT}:{label})"


async def list_facts(
    model: type[DerivedEdge],
    where: Any = None,
    entity: Any = None,
    page: int = 1,
    page_size: int = FIRST_PAGE,
    evidence: Any = None,
    at: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A page of the edges of the class the reader sees (of an entity, at any of its fields, or only at the fields
    `at`; or those a head document is `evidence` of; fitting `where`), in order of the label of their first end"""
    page_size = min(page_size, MAX_PAGE_SIZE)
    params: dict[str, Any] = {
        "see_unpublished": see_unpublished(),
        "skip": (page - 1) * page_size,
        "limit": page_size,
    }
    first = fragments.field_edge(ends_of(model)[0])
    start = start_of(model, entity, evidence, params, at)
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
        total = await count_facts(model, where, entity, evidence, at)
    return {
        "results": [view_of(model, f) for f in facts],
        "count": total,
        "page": page,
        "page_size": page_size,
        "next_page": page + 1 if page * page_size < total else None,
        "previous_page": page - 1 if page > 1 else None,
    }


async def count_facts(
    model: type[DerivedEdge],
    where: Any = None,
    entity: Any = None,
    evidence: Any = None,
    at: Sequence[str] | None = None,
) -> int:
    params: dict[str, Any] = {"see_unpublished": see_unpublished()}
    start = start_of(model, entity, evidence, params, at)
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


async def get_fact(model: type[DerivedEdge], key: str) -> Any | None:
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
                values=json.loads(j["values"]) if j.get("values") else {},
                evidence=row["evidence"],
                context=json.loads(context)
                if isinstance(context, str)
                else context or {},
                context_labels=j.get("context_labels") or [],
                status=j["status"],
                standing=j["standing"],
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
    """The edges derived by the rules of a type: the two ends of each (`source`, its subject; `target`, its object), its
    class, its qualifiers (`attributes`), how many justifications of the type it has that the reader sees
    (`justifications`, and `weight`: the same number, under the name graph tools look for), whether one of them is
    plain, the context labels of those, their status summed up (`status`, `status.summed`) and their standing
    (`standing`, `status.summed_standing`). Each is one edge,
    however many justifications it has"""
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
                   reduce(acc = [], j IN js | acc + [l IN j.context_labels WHERE NOT l IN acc]) AS context_labels,
                   [j IN js | j.status] AS statuses,
                   [j IN js | j.standing] AS standings
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
            for field in (f.name for f in model.qualifiers())
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
                "weight": row["justifications"],
                "plain": row["plain"],
                "context_labels": row["context_labels"],
                "status": summed(row["statuses"]),
                "standing": summed_standing(row["standings"]),
            }
        )
    edges.sort(
        key=lambda e: (e["class"], str(e["source"]["label"]), str(e["target"]["label"]))
    )
    return edges


# ---------------------------------------------------------------------------
# Every edge of a class, with what it rests on (for an export)
# ---------------------------------------------------------------------------

EXPORT_PAGE = 500


async def edges_with_evidence(
    model: type[DerivedEdge], page_size: int = EXPORT_PAGE
) -> Any:
    """A page at a time, every edge of the class that the reader sees (in order of key), each a dict: the edge's view
    (`view`), and of the justifications the reader sees: the head documents they rest on (`evidence`, each once, as
    `{id, type}`), how many they are (`justifications`), whether one is plain (`plain`), their context labels
    (`context_labels`), their status summed up (`status`, `status.summed`) and their standing (`standing`,
    `status.summed_standing`). So what an export says of an edge is
    what its reader may know, not what is stored of it"""
    label = fragments.label(model.__name__)
    query = f"""
    MATCH (d:{FACT}:{label})
    WHERE {fragments.derived_visible("d")}
    WITH d ORDER BY d.key SKIP $skip LIMIT $limit
    MATCH (d)<-[:justifies]-(j:{JUSTIFICATION})
    WITH d, j, [(j)-[:evidence]->(h) | h] AS heads
    WHERE all(v IN heads WHERE {fragments.visible("v")})
    UNWIND heads AS e
    WITH d, j, collect(DISTINCT {{id: e.id, type: e.type}}) AS evidence
    WITH d, collect({{labels: coalesce(j.context_labels, []), status: j.status, standing: j.standing,
                      evidence: evidence}}) AS js
    WITH d, js ORDER BY d.key
    RETURN js, {FACT_FIELDS}
    """
    db = database()
    skip = 0
    while True:
        params = {
            "see_unpublished": see_unpublished(),
            "skip": skip,
            "limit": page_size,
        }

        @db.read_transaction
        async def read(tx: Transaction, params=params) -> list[dict[str, Any]]:
            result = await tx.run(query, params)
            return [dict(r) async for r in result]

        rows = await read()
        found = []
        for row in rows:
            evidence: dict[str, dict[str, Any]] = {}
            labels: list[str] = []
            for justification in row["js"]:
                for head in justification["evidence"]:
                    evidence.setdefault(str(head["id"]), head)
                labels += [
                    name for name in justification["labels"] if name not in labels
                ]
            found.append(
                {
                    "view": view_of(model, row["fact"]),
                    "evidence": list(evidence.values()),
                    "justifications": len(row["js"]),
                    "plain": any(not j["labels"] for j in row["js"]),
                    "context_labels": sorted(labels),
                    "status": summed(j["status"] for j in row["js"]),
                    "standing": summed_standing(j["standing"] for j in row["js"]),
                }
            )
        if found:
            yield found
        # (every edge the reader sees has a justification they see, so a row: a short page is the last)
        if len(rows) < page_size:
            return
        skip += page_size


# ---------------------------------------------------------------------------
# `_derived` of a head node's view
# ---------------------------------------------------------------------------


def can_hold(field: Any, owner: type) -> bool:
    return isinstance(field.model, type) and (
        issubclass(owner, field.model) or issubclass(field.model, owner)
    )


def symmetric_label_of(model: type[DerivedEdge]) -> dict[str, Any] | None:
    """The `SymmetricLabel` of a class, with the two fields it names"""
    if not model._symmetric_label or not model._meta.symmetric:
        return None
    return {"name": model._symmetric_label, "fields": list(model._ends)}


def sections_of(
    model: type[DerivedEdge], owner: type
) -> list[tuple[str, str, list[str]]]:
    """The ways an entity of the class can be in an edge of the derived class, each a section of `_derived`: its key,
    what the entity is of the edge (`role`) and the fields it is at.

    - at an end: one section, by the class's name; but two for an asymmetric class whose object has a `reverse_name`
      (`GaveTo`, read from the giver, and `received_from`, from the receiver);
    - as a qualifier (a group, of the `SameGroup` edges between its members): one section for each such field,
      `SameGroup:group`."""
    subject, object_ = model._ends
    fields = model._fields
    at_subject, at_object = (
        can_hold(fields[subject], owner),
        can_hold(fields[object_], owner),
    )
    found: list[tuple[str, str, list[str]]] = []
    if model._reverse_name and not model._meta.symmetric:
        if at_subject:
            found.append((model.__name__, "subject", [subject]))
        if at_object:
            found.append((model._reverse_name, "object", [object_]))
    elif at_subject or at_object:
        ends = [f for f, held in ((subject, at_subject), (object_, at_object)) if held]
        found.append((model.__name__, "ends", ends))
    for field in model.qualifiers():
        if field.kind == "relation" and can_hold(field, owner):
            found.append((f"{model.__name__}:{field.name}", "qualifier", [field.name]))
    return found


async def derived_of_entity(owner: type, id: Any) -> dict[str, Any]:
    """What is derived about an entity. For each way it can be in an edge of a derived class (`sections_of`): the
    class (`type`), what the entity is of the edge (`role`, and the fields: `as`), the class's `ends`, `symmetricLabel`
    and `reverseName`, the count of its edges, and a first page. Each row has the other end (`other`, `otherField`)
    and the qualifiers (`fields`); read from a qualifier, which is at neither end, both ends (`ends`)"""
    section: dict[str, Any] = {}
    for model in DerivedRegistry.concrete_classes().values():
        subject, object_ = model._ends
        for key, role, fields in sections_of(model, owner):
            page = await list_facts(model, entity=id, page_size=FIRST_PAGE, at=fields)
            if not page["count"]:
                continue
            items = []
            for view in page["results"]:
                data = view.model_dump(
                    by_alias=True, mode="json", exclude={"justifications"}
                )
                item: dict[str, Any] = {
                    "id": data["id"],
                    "type": model.__name__,
                    "as": fields,
                    "other": None,
                    "otherField": None,
                    "fields": {
                        k: v for k, v in data["qualifiers"].items() if k not in fields
                    },
                    "contextLabels": data["contextLabels"],
                    "qualifiedOnly": data["qualifiedOnly"],
                    "plain": data["plain"],
                    "status": data["status"],
                    "statuses": data["statuses"],
                    "standing": data["standing"],
                    "types": data["types"],
                    "justifications": data["justificationCount"],
                }
                if role == "qualifier":
                    item["ends"] = {subject: data[subject], object_: data[object_]}
                else:
                    own = [
                        f for f in (subject, object_) if str(data[f]["id"]) == str(id)
                    ]
                    item["as"] = own
                    other = next((f for f in (subject, object_) if f not in own), None)
                    if other is not None:
                        item["other"], item["otherField"] = data[other], other
                items.append(item)
            section[key] = {
                "type": model.__name__,
                "role": role,
                "as": fields,
                "ends": [subject, object_],
                "symmetric": bool(model._meta.symmetric),
                "symmetricLabel": symmetric_label_of(model),
                "reverseName": model._reverse_name,
                "count": page["count"],
                "items": items,
            }
    return section


async def derived_section(owner: type, view: Any) -> dict[str, Any]:
    """(`hooks.head_view_extras`) `_derived` of the view of a head node: what the rules derive about it, an entity or a
    head document (the facts with a field that points at it). Not what a document is evidence of: that is what it says
    itself. Not given when there is nothing"""
    from pangloss_models import Document, Entity

    if not DerivedRegistry.checked or not issubclass(owner, (Entity, Document)):
        return {}
    section = await derived_of_entity(owner, view.id)
    return {"_derived": section} if section else {}
