"""The graph of a typology: all the Cypher of the package.

    (:RoleType {id, label, label_de, description, is_concrete})-[:is_subtype_of]->(:RoleType)         at most one
    (:RoleType)-[:is_supertype_of {reverse: true}]->(:RoleType)                                        the other way
    (entity)-[:has_type]->(:RoleType)  and  (:RoleType)-[:type_of {reverse: true}]->(entity)

A relation is two edges (see `docs/relations.md`). Types are entities: they are made and changed through the entity,
except the hierarchy and the switch (`is_concrete`), which only this module writes.
"""

import base64
import json
from typing import Any

from pangloss_core import backend
from pangloss_core.backend import Transaction

from pangloss_typology.tree import Row, Rows

SUBTYPE = "is_subtype_of"
SUPERTYPE = "is_supertype_of"
HAS_TYPE = "has_type"
TYPE_OF = "type_of"

SEEN = """NOT coalesce({n}.deleted, false) AND (coalesce({n}.published, true) OR $see_unpublished)"""


def seen(name: str) -> str:
    return SEEN.format(n=name)


class Refused(ValueError):
    """The change would leave the vocabulary invalid: the message says why"""


def _database():
    return backend.current().Database.default


def unpublished_visible() -> bool:
    return backend.current().unpublished_visible()


def row_of(record: Any) -> Row:
    properties = dict(record["props"])
    return Row(
        id=str(properties["id"]),
        label=properties.get("label") or "",
        parent=record["parent"],
        properties=properties,
    )


async def types(label: str) -> Rows:
    """All the types a reader may see, by id.

    (The parent is chosen after the match, not by a pattern with a test on `p`: Memgraph keeps the plan of a query by its text,
    and with that pattern the plan made while the vocabulary was small scanned every type for each type, 360,600 rows for 600
    types, however many there were later.)"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> Rows:
        result = await tx.run(
            f"""
            MATCH (t:{label}) WHERE {seen("t")}
            OPTIONAL MATCH (t)-[:{SUBTYPE}]->(p)
            RETURN properties(t) AS props,
                   CASE WHEN p:{label} AND {seen("p")} THEN p.id END AS parent
            """,
            see_unpublished=unpublished_visible(),
        )
        rows = [row_of(record) async for record in result]
        return {row.id: row for row in rows}

    return await read()


# --- the entities that have a type -----------------------------------------------------------------------


def cursor_of(label: str, id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([label.casefold(), id]).encode()
    ).decode()


def after_cursor(cursor: str) -> tuple[str, str]:
    try:
        label, id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return str(label), str(id)
    except ValueError as error:
        raise Refused("That is not a place in the list ('after')") from error


def _typed_match(label: str, include_subtypes: bool, start: str = "$id") -> str:
    """Match `t`: the type (and, with `include_subtypes`, every type below it)"""
    if include_subtypes:
        return f"MATCH (:{label} {{id: {start}}})<-[:{SUBTYPE}*0..]-(t:{label})"
    return f"MATCH (t:{label} {{id: {start}}})"


async def entities_of(
    label: str,
    id: str,
    *,
    include_subtypes: bool,
    entity_type: str | None,
    limit: int,
    after: str | None,
) -> tuple[int, list[dict[str, Any]]]:
    """The entities that have the type (or a type below it): how many, and a page of them by label.
    Each is `{id, label, labels}`; one more than `limit` is read to tell whether there is a next page"""
    database = _database()
    anchor = _typed_match(label, include_subtypes)
    where = f"""{seen("e")} AND ($entity_type IS NULL OR $entity_type IN labels(e))"""
    after_label, after_id = after_cursor(after) if after else (None, None)

    @database.read_transaction
    async def read(tx: Transaction) -> tuple[int, list[dict[str, Any]]]:
        counted = await tx.run(
            f"""
            {anchor}
            MATCH (t)<-[:{HAS_TYPE}]-(e) WHERE {where}
            RETURN count(DISTINCT e) AS total
            """,
            id=id,
            entity_type=entity_type,
            see_unpublished=unpublished_visible(),
        )
        record = await counted.single()
        page = await tx.run(
            f"""
            {anchor}
            MATCH (t)<-[:{HAS_TYPE}]-(e) WHERE {where}
            WITH DISTINCT e, toLower(coalesce(e.label, '')) AS sort_label
            WHERE $after_label IS NULL OR sort_label > $after_label
                OR (sort_label = $after_label AND e.id > $after_id)
            RETURN e.id AS id, e.label AS label, labels(e) AS labels, sort_label
            ORDER BY sort_label, e.id
            LIMIT $limit
            """,
            id=id,
            entity_type=entity_type,
            after_label=after_label,
            after_id=after_id,
            limit=limit + 1,
            see_unpublished=unpublished_visible(),
        )
        return (record["total"] if record else 0), [dict(item) async for item in page]

    return await read()


async def entity_counts(
    label: str, ids: list[str], include_subtypes: bool
) -> dict[str, int]:
    """For each type: how many entities have it (or, with `include_subtypes`, it or a type below it), each once"""
    if not ids:
        return {}
    database = _database()
    anchor = _typed_match(label, include_subtypes, "sid")

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, int]:
        result = await tx.run(
            f"""
            UNWIND $ids AS sid
            {anchor}
            OPTIONAL MATCH (t)<-[:{HAS_TYPE}]-(e) WHERE {seen("e")}
            RETURN sid, count(DISTINCT e) AS total
            """,
            ids=ids,
            see_unpublished=unpublished_visible(),
        )
        return {record["sid"]: record["total"] async for record in result}

    return await read()


# --- changing the hierarchy ------------------------------------------------------------------------------


def lock_key(label: str) -> str:
    return f"typology:{label}"


async def lock_hierarchy(tx: Transaction, label: str) -> None:
    """Make this transaction conflict with any other that changes the same hierarchy, so that one waits for the other and its
    checks then see what the first did. Without it two moves that are each fine alone can together make a loop: edges added
    by different transactions do not conflict. (`pangloss_core.backend`'s `lock`; the lock is made before the transaction by
    `ensure_lock`)"""
    await backend.current().lock(tx, lock_key(label))


async def ensure_lock(label: str) -> None:
    await backend.current().ensure_lock(lock_key(label))


async def move(label: str, id: str, to: str | None) -> None:
    """Make `to` the supertype of `id` (a root, for `None`), in one transaction. Refused if `id` or `to` is not there, or
    `to` is the type or below it (a loop). The check is made again here, where it cannot be raced"""
    database = _database()

    await ensure_lock(label)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await lock_hierarchy(tx, label)
        found = await (
            await tx.run(
                f"MATCH (n:{label} {{id: $id}}) WHERE NOT coalesce(n.deleted, false) RETURN n.id AS id",
                id=id,
            )
        ).single()
        if not found:
            raise Refused(f"There is no such type: {id}")
        if to is not None:
            target = await (
                await tx.run(
                    f"MATCH (p:{label} {{id: $to}}) WHERE NOT coalesce(p.deleted, false) RETURN p.id AS id",
                    to=to,
                )
            ).single()
            if not target:
                raise Refused(f"There is no such type to move it to: {to}")
            looped = await (
                await tx.run(
                    f"""
                    MATCH (n:{label} {{id: $id}})<-[:{SUBTYPE}*0..]-(d:{label} {{id: $to}})
                    RETURN count(d) AS found
                    """,
                    id=id,
                    to=to,
                )
            ).single()
            if looped and looped["found"]:
                raise Refused(
                    "A type cannot be moved below itself or below one of its own subtypes"
                )
        await tx.run(
            f"""
            MATCH (n:{label} {{id: $id}})
            OPTIONAL MATCH (n)-[up:{SUBTYPE}]->(p:{label})
            OPTIONAL MATCH (p)-[down:{SUPERTYPE}]->(n)
            DELETE up, down
            """,
            id=id,
        )
        if to is not None:
            await tx.run(
                f"""
                MATCH (n:{label} {{id: $id}}), (p:{label} {{id: $to}})
                CREATE (n)-[:{SUBTYPE}]->(p)
                CREATE (n)<-[:{SUPERTYPE} {{reverse: true}}]-(p)
                """,
                id=id,
                to=to,
            )

    await write()


async def uses(label: str, id: str) -> list[dict[str, Any]]:
    """What refers to the type other than as a type or in the hierarchy: the entities that have it as a type (`has_type`),
    and anything that has it by another relation (it is also a `Role`, and a role is held). Each is
    `{relation, id, label}`; the hierarchy is not included"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            MATCH (n:{label} {{id: $id}})<-[r]-(m)
            WHERE NOT coalesce(r.reverse, false) AND type(r) <> '{SUBTYPE}' AND {seen("m")}
                AND ('Entity' IN labels(m) OR 'Document' IN labels(m))
            RETURN type(r) AS relation, m.id AS id, m.label AS label
            ORDER BY relation, label
            """,
            id=id,
            see_unpublished=True,
        )
        return [dict(record) async for record in result]

    return await read()


async def set_concrete(
    label: str, id: str, on: bool, concrete_labels: tuple[str, ...]
) -> None:
    """Switch a type on or off as the other class (`also`): its labels, and `is_concrete`. Off is refused while anything
    refers to the type by a relation that is not the type's (`uses` other than `has_type`)"""
    if not on:
        blocking = [u for u in await uses(label, id) if u["relation"] != HAS_TYPE]
        if blocking:
            names = ", ".join(f"{u['label']} ({u['relation']})" for u in blocking[:5])
            raise Refused(
                f"It is used as a {', '.join(concrete_labels[:1])} by {names}"
                + (" and more" if len(blocking) > 5 else "")
                + ": change those first"
            )
    database = _database()
    labels = "".join(f":{name}" for name in concrete_labels)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        verb = (
            f"SET n{labels}, n.is_concrete = true"
            if on
            else f"REMOVE n{labels}, n.is_concrete"
        )
        result = await tx.run(
            f"MATCH (n:{label} {{id: $id}}) WHERE NOT coalesce(n.deleted, false) {verb} RETURN n.id AS id",
            id=id,
        )
        if not await result.single():
            raise Refused(f"There is no such type: {id}")

    await write()


async def merge(label: str, source: str, into: str) -> None:
    """Everything that has `source` has `into`, `source`'s subtypes become `into`'s, and `source` is marked deleted.
    If `into` is below `source`, it first takes `source`'s place (so there is no loop)"""
    database = _database()

    await ensure_lock(label)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await lock_hierarchy(tx, label)
        both = await (
            await tx.run(
                f"""
                MATCH (a:{label} {{id: $a}}), (b:{label} {{id: $b}})
                WHERE NOT coalesce(a.deleted, false) AND NOT coalesce(b.deleted, false)
                OPTIONAL MATCH (a)-[:{SUBTYPE}]->(parent:{label})
                RETURN a.id AS a, parent.id AS parent
                """,
                a=source,
                b=into,
            )
        ).single()
        if not both:
            raise Refused("Both types must exist")
        below = await (
            await tx.run(
                f"""
                MATCH (a:{label} {{id: $a}})<-[:{SUBTYPE}*1..]-(b:{label} {{id: $b}})
                RETURN count(b) AS found
                """,
                a=source,
                b=into,
            )
        ).single()
        if below and below["found"]:
            await tx.run(
                f"""
                MATCH (b:{label} {{id: $b}})
                OPTIONAL MATCH (b)-[up:{SUBTYPE}]->(p:{label})
                OPTIONAL MATCH (p)-[down:{SUPERTYPE}]->(b)
                DELETE up, down
                """,
                b=into,
            )
            if both["parent"]:
                await tx.run(
                    f"""
                    MATCH (b:{label} {{id: $b}}), (p:{label} {{id: $p}})
                    CREATE (b)-[:{SUBTYPE}]->(p)
                    CREATE (b)<-[:{SUPERTYPE} {{reverse: true}}]-(p)
                    """,
                    b=into,
                    p=both["parent"],
                )
        # the subtypes of source (other than `into`) move to `into`
        await tx.run(
            f"""
            MATCH (a:{label} {{id: $a}})<-[up:{SUBTYPE}]-(c:{label}), (b:{label} {{id: $b}})
            WHERE c.id <> $b
            OPTIONAL MATCH (a)-[down:{SUPERTYPE}]->(c)
            DELETE up, down
            WITH c, b
            CREATE (c)-[:{SUBTYPE}]->(b)
            CREATE (c)<-[:{SUPERTYPE} {{reverse: true}}]-(b)
            """,
            a=source,
            b=into,
        )
        # what had `source` has `into`
        await tx.run(
            f"""
            MATCH (a:{label} {{id: $a}})<-[old:{HAS_TYPE}]-(e), (b:{label} {{id: $b}})
            OPTIONAL MATCH (a)-[oldr:{TYPE_OF}]->(e)
            DELETE old, oldr
            WITH e, b
            MERGE (e)-[:{HAS_TYPE}]->(b)
            MERGE (e)<-[:{TYPE_OF} {{reverse: true}}]-(b)
            """,
            a=source,
            b=into,
        )
        # (source's own supertype edges go with it)
        await tx.run(
            f"""
            MATCH (a:{label} {{id: $a}})
            OPTIONAL MATCH (a)-[up:{SUBTYPE}]->(p:{label})
            OPTIONAL MATCH (p)-[down:{SUPERTYPE}]->(a)
            DELETE up, down
            """,
            a=source,
        )

    await write()
