"""Stored statements read as the verdict's plain data (`maths.Told`; implementation_docs/spaces-and-comparison-plan.md,
step 6.3):

    await read(tx, ids, see_unpublished=...) -> dict[str, maths.Told]

For each id that is a document of a compared class (a head, or nested in one), in an open read transaction:

- `classes`: its class and the compared classes above it, nearest first;
- `fields`: the ids of the entities in each relation field of the class that reaches an entity, identifying or not.
  What is behind wrappers is in the field it is held from, followed through the fields in which wrappers hold what
  they are made for only (`held_fields`: `target`, `contents`, an identification's alternatives), so a wrapper's own
  relation (`InRole.at`) is not on the way. A field is named as it counts for comparison: an identifying field by
  the name `meta.identifying_fields` gives it, any other by the name of the field of the most general compared class
  above it that it narrows (`picture_made` as `made`); a field that narrows none keeps its own name;
- **real entities only** (`entities_query`): no stand-in (a stand-in document is no entity, and no wrapper that is
  a stand-in, `MatchesCriteria`, is on the way), no relation the server computes, nothing below a guess no person has
  confirmed (`hooks.unconfirmed_classes()`, the rule of `pangloss_reconcile.reasons.unconfirmed`), no deleted
  entity; an entity merged into another counts as the one kept (`merged_into` followed to the end:
  `pangloss_cypher.validate_write.survivors_of`);
- `dates`: each field of the class that holds a date of `pangloss_dates` itself, as the date's widest stored bounds
  (`maths.Span`); a date only unknown, or with a bound not stored, gives none;
- `signature`: the walk over its stored path (`pangloss_models.spaces.signature`, with the models' grounds; a head by
  its class);
- `head`: its head's id (its own, where it is a head); `source`: where the head's ground names whose commitment it is
  (`Signature.grounded_by`), the entity in that field of the head (of several, the first by id), and `sources`, every
  entity in it (for showing);
- `prescribed`, where the walk says it is prescribed: of the node holding the innermost space that prescribes, the
  entities of the fields its `Attribution` names (`by`, `to`), its date where it has exactly one date field, and the
  space's `CompareMeta.orientation`. Where only the head's ground prescribes (no space on the path does) there is no
  `Attribution`: `by` is then what the ground's `by` field of the head names, if it names one, `to` none, `at` the
  head's date as above, `orientation` `"after"`. The head itself, under its own ground, has `Prescribed()`.

Not returned: an id that is not there, not a document, not of a compared class, one the reader may not see
(`see_unpublished`: by its head, `fragments.visible`), and one any space of whose path has `CompareMeta(compared=False)`.

At most four statements, whatever the number of ids: the nodes (`NODES_QUERY`), the nodes that hold a space that
prescribes (the same, only when there are some), the entities of every field wanted of every node in one
(`entities_query`), and the chain of merges, only when an entity found is merged into another."""

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pangloss_compare import maths, meta

# (the label of every date of `pangloss_dates`, and the precision of one only unknown)
DATE = "Date"
UNKNOWN = "unknown"


def stored_path(value: Any) -> list[Any]:
    """A node's path as a query returns it: a list, or (on a database that cannot hold one, Neo4j) its JSON text; none
    is empty. (The same as `pangloss_derived.status.stored_path` and three others: none of them can be imported
    without an optional package)"""
    import json

    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


# --- what the models say ----------------------------------------------------------------------------------


def held_fields() -> list[str]:
    """The names of the fields in which a wrapper (a semantic space, a conjunction, a reified relation) holds what it
    is made for, of every wrapper class of the models (`pangloss_models.search.held_field_names`)"""
    from pangloss_models import ModelRegistry
    from pangloss_models.search import WRAPPER_LABELS, held_field_names

    names: set[str] = set()
    for model in ModelRegistry.all_models().values():
        if (
            isinstance(model, type)
            and getattr(model, "__metatype__", None) in WRAPPER_LABELS
        ):
            names |= held_field_names(model)
    return sorted(names)


def stand_in_classes() -> list[str]:
    """The names of the classes given in the place of an entity (`hooks.stand_ins`): never an entity, nor on the way
    to one"""
    from pangloss_models import hooks

    return sorted({stand_in.document for stand_in in hooks.stand_ins})


@dataclasses.dataclass(frozen=True)
class Shape:
    """What is read of a stored node of a class"""

    classes: tuple[str, ...]
    """Its class and the compared classes above it, nearest first"""
    fields: Mapping[str, str]
    """Of each relation field that reaches an entity (the type of its edge): the name it counts as"""
    dates: tuple[str, ...]
    """The fields that hold a date itself"""


def _model(name: str) -> type | None:
    from pangloss_models import ModelRegistry

    found = ModelRegistry._model_dict.get(name)
    return found if isinstance(found, type) else None


def _date_fields(model: type) -> tuple[str, ...]:
    date = _model(DATE)
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    if date is None or fields is None:
        return ()
    return tuple(
        name
        for name, definition in fields.embedded_fields.items()
        if isinstance(definition.annotated_type, type)
        and issubclass(definition.annotated_type, date)
    )


def _entity_fields(model: type, top: type) -> dict[str, str]:
    from pangloss_models.initialise_models.check_attributions import (
        reaches_an_entity,
    )

    fields = getattr(getattr(model, "_meta", None), "fields", None)
    if fields is None:
        return {}
    identifying = {
        holder: name
        for name, holders in meta.identifying_fields(model).items()
        for holder in holders
    }
    above = meta._fields_of(top)
    named: dict[str, str] = {}
    for field, definition in fields.relation_fields.items():
        if not reaches_an_entity(definition):
            continue
        if field in identifying:
            named[field] = identifying[field]
        elif field in above:
            named[field] = field
        else:
            narrowed = sorted(meta._narrowed_by(definition) & set(above))
            named[field] = narrowed[0] if narrowed else field
    return named


class Known:
    """What the models say, worked out once for a read: the shapes of classes as they are asked for, the spaces and
    grounds of the walk, the compared classes"""

    def __init__(self) -> None:
        from pangloss_models import spaces

        self.compared = meta.compared_classes()
        self.spaces = spaces.registered_spaces()
        self.grounds = spaces.registered_grounds()
        self._shapes: dict[str, Shape] = {}

    def shape(self, name: str) -> Shape:
        """The shape of a class by its name (of one that is not compared, `classes` is empty)"""
        if name not in self._shapes:
            model = _model(name)
            if model is None:
                self._shapes[name] = Shape((), {}, ())
            else:
                classes = tuple(
                    dict.fromkeys(
                        cls.__name__
                        for cls in model.__mro__
                        if cls.__name__ in self.compared
                    )
                )
                if classes and classes[0] != name:
                    classes = ()
                top = _model(classes[-1]) if classes else model
                self._shapes[name] = Shape(
                    classes,
                    _entity_fields(model, top or model),
                    _date_fields(model),
                )
        return self._shapes[name]

    def compared_path(self, path: Sequence[Mapping[str, Any]]) -> bool:
        """Whether no space of the path leaves what is inside it out (`CompareMeta(compared=False)`)"""
        from pangloss_models.context import SPACE

        return all(
            meta.space_compared(entry["type"])
            for entry in path
            if entry.get("kind") == SPACE and _model(entry["type"]) is not None
        )


# --- the queries -------------------------------------------------------------------------------------------


def is_wrapper(node: str) -> str:
    """A condition: the node is a wrapper. (Not an `OR` of labels, which after an `UNWIND` loses rows on Memgraph:
    `implementation_docs/memgraph.md`)"""
    from pangloss_models.search import WRAPPER_LABELS

    labels = ", ".join(f"'{label}'" for label in WRAPPER_LABELS)
    return f"any(label IN labels({node}) WHERE label IN [{labels}])"


def not_stand_in(node: str) -> str:
    """A condition: the node is of no class of `$stand_ins` (`stand_in_classes`)"""
    return f"NOT any(label IN labels({node}) WHERE label IN $stand_ins)"


def unconfirmed(node: str, names: Sequence[str], dialect: Any) -> str:
    """A condition (with its `AND`, or nothing with no `names`): the node `node`, which has the edge to an entity, is
    not of a class of `names` (`hooks.unconfirmed_classes()`), nor below one through the wrappers that hold it. A head
    is below nothing. The rule of `pangloss_reconcile.reasons.unconfirmed`, written again here: that package is not
    one this depends on"""
    from pangloss_cypher import fragments

    if not names:
        return ""
    held = f"{node}_held"
    for name in names:
        fragments.label(name)  # (refused if it cannot be the name of a class)
    labels = ", ".join(f"'{name}'" for name in names)
    return (
        f" AND ({node}.head_node_id IS NULL OR NOT EXISTS {{ MATCH ({node})"
        f"{dialect.through_wrappers(f'{node}_up', backwards=True)}({held}) "
        f"WHERE any(label IN labels({held}) WHERE label IN [{labels}]) }})"
    )


def nodes_query(fragments: Any, dialect: Any) -> str:
    """The documents of the ids `$ids` the reader may see: id, class, head, stored path, and each date it holds itself
    (`[field, earliest, latest, precision]`)"""
    head = fragments.head_of("n", "n_head")
    return f"""
        UNWIND $ids AS nid
        MATCH (n:PGIndexableNode {{id: nid}})
        WHERE n:Document
        {head.match}
        WITH n, {head.name}
        WHERE {fragments.visible("n", head)}
        RETURN n.id AS id, n.type AS type, n.head_node_id AS head,
            {dialect.meta_property("n", "path")} AS path,
            [(n)-[e]->(d:{DATE}) WHERE NOT coalesce(e.reverse, false) |
                [type(e), d.earliest_fuzzy, d.latest_fuzzy, d.precision]] AS dates
    """


# (of a walk through wrappers named `held`: every hop is by a field a wrapper holds its contents in, so a wrapper's
# own relation is not on the way where it too leads to a wrapper)
HELD_ALL_THE_WAY = "all(hop IN relationships(held) WHERE type(hop) IN $held)"


def entities_query(fragments: Any, dialect: Any, names: Sequence[str]) -> str:
    """The entities in fields of nodes: for each row of `$rows` (`{id, edges}`), the entity at the end of each of
    its edges of those names, directly or through wrappers by the fields of `$held`, each `{id, edge, entity, into}`
    (`into`: the entity it is merged into, or null). Real entities only (the module's docstring). `names`: the
    classes of a guess not confirmed (`unconfirmed`)"""
    return f"""
        UNWIND $rows AS r
        WITH r, r.id AS sid
        MATCH (s:PGIndexableNode {{id: sid}})
        MATCH (s)-[e]->(v)
        WHERE type(e) IN r.edges AND {fragments.forward("e")}{fragments.reference("e")}
        WITH sid, s, e, v
        WHERE v:Entity AND {fragments.not_deleted("v")}{unconfirmed("s", names, dialect)}
        RETURN sid AS id, type(e) AS edge, v.id AS entity, v.merged_into AS into
        UNION
        UNWIND $rows AS r
        WITH r, r.id AS sid
        MATCH (s:PGIndexableNode {{id: sid}})
        MATCH (s)-[e]->(x)
        WHERE type(e) IN r.edges AND {fragments.forward("e")}
        WITH sid, s, e, x
        WHERE {is_wrapper("x")} AND {not_stand_in("x")}
        MATCH held = (x){dialect.through_wrappers("w")}(y)
        WHERE {HELD_ALL_THE_WAY}
        MATCH (y)-[e3]->(v)
        WHERE type(e3) IN $held AND {fragments.forward("e3")}{fragments.reference("e3")}
        WITH sid, e, y, v
        WHERE v:Entity AND {fragments.not_deleted("v")} AND {not_stand_in("y")}{unconfirmed("y", names, dialect)}
        RETURN sid AS id, type(e) AS edge, v.id AS entity, v.merged_into AS into
    """


async def survivors(tx: Any, found: Iterable[tuple[str, str | None]]) -> dict[str, str]:
    """Of entities found (`(id, merged_into)`), the one each counts as: itself, or the survivor at the end of its
    chain of merges"""
    from pangloss_cypher.validate_write import survivors_of

    found = list(found)
    merged = sorted({id for id, into in found if into is not None})
    kept = await survivors_of(tx, merged) if merged else {}
    return {id: kept.get(id, id) for id, _ in found}


async def entities_of(
    tx: Any, rows: Mapping[str, Iterable[str]], query: str, **params: Any
) -> dict[str, dict[str, set[str]]]:
    """For each node id of `rows` (its edges to follow), the entities (as the ones kept) by edge"""
    asked = [{"id": id, "edges": sorted(set(edges))} for id, edges in rows.items()]
    asked = [row for row in asked if row["edges"]]
    if not asked:
        return {}
    result = await tx.run(query, rows=asked, **params)
    found = [
        (str(r["id"]), str(r["edge"]), str(r["entity"]), r["into"])
        async for r in result
    ]
    kept = await survivors(tx, [(entity, into) for _, _, entity, into in found])
    by_node: dict[str, dict[str, set[str]]] = {}
    for node, edge, entity, _ in found:
        by_node.setdefault(node, {}).setdefault(edge, set()).add(kept[entity])
    return by_node


# --- the read ----------------------------------------------------------------------------------------------


@dataclasses.dataclass
class _Node:
    id: str
    type: str
    head: str | None
    path: list[Any]
    dates: dict[str, maths.Span]


def _span(earliest: Any, latest: Any, precision: Any) -> maths.Span | None:
    if precision == UNKNOWN or earliest is None or latest is None:
        return None
    return maths.Span(int(earliest), int(latest))


async def _nodes(
    tx: Any, ids: Iterable[str], query: str, see_unpublished: bool
) -> dict[str, _Node]:
    ids = sorted(set(ids))
    if not ids:
        return {}
    result = await tx.run(query, ids=ids, see_unpublished=see_unpublished)
    found: dict[str, _Node] = {}
    async for r in result:
        dates: dict[str, maths.Span] = {}
        for field, earliest, latest, precision in r["dates"]:
            if (span := _span(earliest, latest, precision)) is not None:
                dates[str(field)] = span
        found[str(r["id"])] = _Node(
            str(r["id"]),
            str(r["type"]),
            None if r["head"] is None else str(r["head"]),
            stored_path(r["path"]),
            dates,
        )
    return found


@dataclasses.dataclass(frozen=True)
class _Prescriber:
    """The node whose field holds the innermost space that prescribes a statement, and what to read of it"""

    id: str
    type: str
    by: str | None
    to: str | None
    orientation: str


def _prescriber(node: _Node, signature: Any, known: Known) -> _Prescriber | None:
    """Of a statement that is prescribed: the node that prescribes it and which of its fields say by whom and to
    whom (`Attribution`), or, where only the head's ground prescribes, the head and the ground's field. None for a
    head under its own ground"""
    from pangloss_models.markers import attributions
    from pangloss_models.spaces import PRESCRIBES, holds_as_space

    holder: Mapping[str, Any] | None = None
    found: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None
    for entry in node.path:
        if not holds_as_space(entry):
            holder = entry
        elif (
            known.spaces.get(entry["type"], {}).get("fit") == PRESCRIBES
            and holder is not None
        ):
            found = (holder, entry)
    if found is not None:
        holder, space = found
        model = _model(holder["type"])
        attribution = attributions(model).get(holder["field"]) if model else None
        return _Prescriber(
            str(holder["id"]),
            str(holder["type"]),
            attribution.by if attribution else None,
            attribution.to if attribution else None,
            meta.orientation_of(space["type"]),
        )
    if not node.path or signature.prescribed_by is None:
        return None
    head = node.path[0]
    ground = known.grounds.get(head["type"]) or {}
    by = (ground.get("by") or {}).get("name")
    return _Prescriber(str(head["id"]), str(head["type"]), by, None, "after")


async def read(
    tx: Any, ids: Iterable[Any], *, see_unpublished: bool
) -> dict[str, maths.Told]:
    """The stored statements of these ids as plain data, by id (the module's docstring). `see_unpublished`: whether
    the reader may see what is not published (the statements and nothing else are judged by it)"""
    from pangloss_core import backend
    from pangloss_models import hooks, spaces

    current = backend.current()
    fragments, dialect = current.fragments, current.dialect
    known = Known()
    if not known.compared:
        return {}
    node_query = nodes_query(fragments, dialect)
    nodes = await _nodes(tx, (str(id) for id in ids), node_query, see_unpublished)

    statements: dict[str, tuple[_Node, Shape, Any]] = {}
    for node in nodes.values():
        shape = known.shape(node.type)
        if not shape.classes or not known.compared_path(node.path):
            continue
        signature = spaces.signature(
            node.path,
            known.spaces,
            known.grounds,
            head=node.type if not node.path else None,
        )
        statements[node.id] = (node, shape, signature)

    prescribers = {
        id: _prescriber(node, signature, known)
        for id, (node, _, signature) in statements.items()
        if signature.fit == spaces.PRESCRIBES
    }
    # (the dates of those that prescribe: read as any other node, whoever may see them)
    holders = await _nodes(
        tx,
        {p.id for p in prescribers.values() if p is not None} - set(nodes),
        node_query,
        True,
    )
    holders.update(nodes)

    wanted: dict[str, set[str]] = {}
    for id, (_, shape, signature) in statements.items():
        wanted.setdefault(id, set()).update(shape.fields)
        if signature.grounded_by is not None:
            head = signature.grounded_by.head or id
            wanted.setdefault(head, set()).add(signature.grounded_by.field)
    for prescriber in prescribers.values():
        if prescriber is not None:
            wanted.setdefault(prescriber.id, set()).update(
                field for field in (prescriber.by, prescriber.to) if field
            )
    names = hooks.unconfirmed_classes()
    entities = await entities_of(
        tx,
        wanted,
        entities_query(fragments, dialect, names),
        held=held_fields(),
        stand_ins=stand_in_classes(),
    )

    told: dict[str, maths.Told] = {}
    for id, (node, shape, signature) in statements.items():
        mine = entities.get(id, {})
        fields: dict[str, set[str]] = {}
        for edge, name in shape.fields.items():
            if mine.get(edge):
                fields.setdefault(name, set()).update(mine[edge])
        source = None
        named: set[str] = set()
        if signature.grounded_by is not None:
            head = signature.grounded_by.head or id
            named = entities.get(head, {}).get(signature.grounded_by.field, set())
            source = min(named) if named else None
        prescribed = None
        if signature.fit == spaces.PRESCRIBES:
            prescribed = _prescribed(prescribers.get(id), holders, entities, known)
        told[id] = maths.Told(
            id=id,
            classes=shape.classes,
            signature=signature,
            fields={name: frozenset(values) for name, values in fields.items()},
            dates={
                field: node.dates[field] for field in shape.dates if field in node.dates
            },
            head=node.head or id,
            source=source,
            sources=frozenset(named),
            prescribed=prescribed,
        )
    return told


def _prescribed(
    prescriber: _Prescriber | None,
    holders: Mapping[str, _Node],
    entities: Mapping[str, Mapping[str, set[str]]],
    known: Known,
) -> maths.Prescribed:
    if prescriber is None:
        return maths.Prescribed()
    named = entities.get(prescriber.id, {})
    holder = holders.get(prescriber.id)
    date_fields = known.shape(prescriber.type).dates
    at = None
    if holder is not None and len(date_fields) == 1:
        at = holder.dates.get(date_fields[0])
    return maths.Prescribed(
        by=frozenset(named.get(prescriber.by, ())) if prescriber.by else frozenset(),
        to=frozenset(named.get(prescriber.to, ())) if prescriber.to else frozenset(),
        at=at,
        orientation=prescriber.orientation,
    )
