"""Neo4j's answers where the backends differ in a migration (`pangloss_cypher.dialect.MigrationDialect`).

Neo4j cannot keep a map as a property: a `meta`, an annotated value and a `TypedDict` are kept flat, a property for each
part (`` n.`meta.created_by` ``, `` n.`date.value` ``), and a list of maps as JSON text (`properties`). A migration
changes those properties. It walks with quantified path patterns (`traversal`), derives nothing from a `label` (its
full-text index folds accents itself), and makes its indexes and constraints with its own statements (`schema`)."""

from typing import Any

import neo4j
from pangloss_cypher import Transaction
from pangloss_models import PanglossMigrationError, PanglossMigrationNotSupported
from pangloss_models.migrations import changes as c

from pangloss_neo4j.databases.neo4j.properties import flat_meta
from pangloss_neo4j.databases.neo4j.schema import (
    await_indexes,
    create_constraint_statement,
    create_index_statement,
    has_constraint,
    has_index,
    list_constraints,
    list_indexes,
    run_statement,
)
from pangloss_neo4j.databases.neo4j.schema import ident as ident_name
from pangloss_neo4j.databases.neo4j.traversal import hops

INSERTED_NODE_META = """
    OPTIONAL MATCH (s)<-[:is_creation_of]-(creation:PGCreation)-[:created_by]->(creator:PGUser)
    WITH *, s.`meta.created_by` IS NOT NULL AS has_meta
    WITH *, CASE WHEN has_meta THEN coalesce(s.`meta.context_labels#json`, '[]') ELSE '[]' END AS base_labels
    WITH *, {
        created_by: coalesce(s.`meta.created_by`, creator.username),
        created_when: coalesce(s.`meta.created_when`, creation.created_when),
        updated_by: coalesce(s.`meta.updated_by`, creator.username),
        updated_when: coalesce(s.`meta.updated_when`, creation.created_when),
        semantic_spaces: coalesce(s.`meta.semantic_spaces`, []),
        context_labels: CASE
            WHEN NOT has_meta THEN '[]'
            WHEN base_labels <> '[]' THEN base_labels
            WHEN coalesce($labels_in_context[s.type], true)
                THEN '[{"type":"#rootcontext","contents":[{"type":"' + s.type + '","id":"' + s.id + '"}]}]'
            ELSE '[]' END,
        context_label_types: CASE
            WHEN NOT has_meta THEN []
            WHEN base_labels <> '[]' THEN coalesce(s.`meta.context_label_types`, [])
            WHEN coalesce($labels_in_context[s.type], true) THEN ['#rootcontext']
            ELSE [] END} AS new_meta
"""

# (the `meta` of the new node, as the flat properties it is stored in: the list of context labels is JSON text)
META_FROM_NEW = (
    "`meta.created_by`: new_meta.created_by, `meta.created_when`: new_meta.created_when, "
    "`meta.updated_by`: new_meta.updated_by, `meta.updated_when`: new_meta.updated_when, "
    "`meta.semantic_spaces`: new_meta.semantic_spaces, `meta.context_labels#json`: new_meta.context_labels, "
    "`meta.context_label_types`: new_meta.context_label_types"
)

# (what a node made for a wrapper's contents has: who and when, and no spaces and no context)
META_WITHOUT_CONTEXT = (
    "`meta.created_by`: new_meta.created_by, `meta.created_when`: new_meta.created_when, "
    "`meta.updated_by`: new_meta.updated_by, `meta.updated_when`: new_meta.updated_when, "
    "`meta.semantic_spaces`: []"
)


def holds_enum(
    var: str, path: str, descriptor: dict, enum: str, keys: str, depth: int = 0
) -> str | None:
    """A Cypher condition that is true when the property `path` of `var` (of the type `descriptor`) has in it a value of
    `enum` that is one of the `$keys` (their text); None if the type has no such enum. A `TypedDict` is stored flat, a
    property for each of its fields (`size.shade`): the conditions are of those properties."""
    ref = f"{var}.{ident_name(path)}"
    kind = descriptor.get("type")
    if kind == "enum":
        return f"toString({ref}) IN ${keys}" if descriptor["enum"] == enum else None
    if kind == "list":
        item = descriptor["item"]
        if item.get("type") == "typedDict":
            refuse_enum_in_json(item, enum, path)
            return None
        inner = holds_enum(f"x{depth}", "", item, enum, keys, depth + 1)
        if inner is None:
            return None
        return (
            f"any(x{depth} IN {ref} WHERE {inner.replace(f'x{depth}.``', f'x{depth}')})"
        )
    if kind == "typedDict":
        parts = [
            holds_enum(var, f"{path}.{name}", field, enum, keys, depth + 1)
            for name, field in descriptor["fields"].items()
        ]
        parts = [p for p in parts if p]
        return "(" + " OR ".join(parts) + ")" if parts else None
    return None


def refuse_enum_in_json(descriptor: dict, enum: str, path: str) -> None:
    """A list of `TypedDict`s is stored as JSON text, which Cypher cannot change a part of"""
    if any(
        holds_enum("v", "f", field, enum, "k") is not None
        for field in descriptor["fields"].values()
    ):
        raise PanglossMigrationNotSupported(
            f"{path} is a list of TypedDicts with a value of {enum} in them, which Neo4j keeps as JSON text: "
            "changing the values of an enum inside it is not supported by this backend"
        )


def rewrite_enum(
    var: str, path: str, descriptor: dict, enum: str, values: str, depth: int = 0
) -> list[tuple[str, str]] | None:
    """The properties to set, for the property `path` of `var` with the values of `enum` that are keys of the map `$values`
    (by their text) changed to what it says: pairs of the name of a flat property and the expression for its new value;
    None if the type has no such enum. (`SET p = null` of what is not there is no change.)"""
    ref = f"{var}.{ident_name(path)}"
    kind = descriptor.get("type")
    if kind == "enum":
        if descriptor["enum"] != enum:
            return None
        return [(path, f"coalesce(${values}[toString({ref})], {ref})")]
    if kind == "list":
        item = descriptor["item"]
        if item.get("type") == "typedDict":
            refuse_enum_in_json(item, enum, path)
            return None
        if item.get("type") == "enum" and item["enum"] == enum:
            x = f"x{depth}"
            return [(path, f"[{x} IN {ref} | coalesce(${values}[toString({x})], {x})]")]
        return None
    if kind == "typedDict":
        changed: list[tuple[str, str]] = []
        for name, field in descriptor["fields"].items():
            found = rewrite_enum(var, f"{path}.{name}", field, enum, values, depth + 1)
            if found:
                changed += found
        return changed or None
    return None


async def ddl(database: Any, statement: str) -> None:
    await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, statement
    )


async def indexes_and_constraints(database: Any):
    name = database.settings.DATABASE.DATABASE_NAME
    return (
        await list_indexes(database.driver, name),
        await list_constraints(database.driver, name),
    )


class Neo4jMigrations:
    # --- walks and `meta` -----------------------------------------------------------------------------------------

    def owned(self, name: str) -> str:
        return f" {hops(name, f'NOT {name}_to:Entity AND NOT coalesce({name}_edge.reverse, false)')} "

    def meta_mentions(self, node: str, model: str) -> str:
        return f"""{node}.`meta.created_by` IS NOT NULL AND (
            {model} IN coalesce({node}.`meta.semantic_spaces`, [])
            OR {model} IN coalesce({node}.`meta.context_label_types`, [])
            OR coalesce({node}.`meta.context_labels#json`, '') CONTAINS ('"type":"' + {model} + '"'))"""

    inserted_node_meta = INSERTED_NODE_META

    def new_meta_properties(self, *, context: bool) -> str:
        return META_FROM_NEW if context else META_WITHOUT_CONTEXT

    def meta_properties(self, meta: dict[str, Any]) -> dict[str, Any]:
        # (what is no longer there is set to null, which removes the property)
        return flat_meta(meta)

    # --- maps: kept flat --------------------------------------------------------------------------------------------

    def set_map(self, node: str, name: str, entries: dict[str, str]) -> str:
        parts = ", ".join(
            f"{node}.{ident_name(name + '.' + key)} = {value}"
            for key, value in entries.items()
        )
        return f"SET {parts} REMOVE {node}.{ident_name(name)}"

    def map_value(self, node: str, name: str, key: str) -> str:
        return f"{node}.{ident_name(name + '.' + key)}"

    def unwrap_map(self, node: str, name: str, key: str, keys: list[str]) -> str:
        parts = [self.map_value(node, name, k) for k in keys]
        return f"SET {node}.{ident_name(name)} = {self.map_value(node, name, key)} REMOVE {', '.join(parts)}"

    def enum_test(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, keys: str
    ) -> str:
        test = holds_enum(node, name, descriptor, enum, keys)
        assert test is not None, f"{name} has no value of {enum}"
        return test

    def enum_rewrite(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, values: str
    ) -> list[tuple[str, str]]:
        return [
            (f"{node}.{ident_name(path)}", expression)
            for path, expression in rewrite_enum(node, name, descriptor, enum, values)
            or []
        ]

    # --- nothing is derived from a label ------------------------------------------------------------------------------

    async def rederive(self, tx: Transaction, labels: list[str] | None) -> None:
        pass

    # --- indexes and constraints ------------------------------------------------------------------------------------

    async def add_index(self, database: Any, change: c.AddIndex, state: dict) -> None:
        """Make an index. (There is none to make for a label, which every database has an index of, nor for what a
        uniqueness constraint has made its own index of already.)"""
        entry = change.index
        existing, _ = await indexes_and_constraints(database)
        if has_index(existing, entry) is not None:
            return
        statement = create_index_statement(entry)
        if statement is not None:
            await ddl(database, statement)
            await await_indexes(
                database.driver, database.settings.DATABASE.DATABASE_NAME
            )

    async def remove_index(
        self, database: Any, change: c.RemoveIndex, state: dict
    ) -> None:
        """Drop an index. (One that a constraint made goes with the constraint, and cannot be dropped alone.)"""
        existing, _ = await indexes_and_constraints(database)
        found = has_index(existing, change.index)
        if found is not None and not found.owned:
            await ddl(database, f"DROP INDEX {ident_name(found.name)} IF EXISTS")

    async def add_constraint(
        self, database: Any, change: c.AddConstraint, state: dict
    ) -> None:
        """Make a uniqueness constraint. (It makes an index of its own: an index of the same properties made before it,
        as the migrations do, is dropped first, or Neo4j refuses the constraint.)"""
        existing_indexes, existing = await indexes_and_constraints(database)
        if has_constraint(existing, change.constraint) is not None:
            return
        same = has_index(
            existing_indexes, {**change.constraint, "kind": "label+property"}
        )
        try:
            if same is not None and not same.owned:
                await ddl(database, f"DROP INDEX {ident_name(same.name)} IF EXISTS")
            await ddl(database, create_constraint_statement(change.constraint))
        except neo4j.exceptions.Neo4jError as error:
            raise PanglossMigrationError(
                f"Cannot make {change.describe()}: {error.message} (the data may break it already)"
            ) from error

    async def remove_constraint(
        self, database: Any, change: c.RemoveConstraint, state: dict
    ) -> None:
        _, existing = await indexes_and_constraints(database)
        found = has_constraint(existing, change.constraint)
        if found is not None:
            await ddl(database, f"DROP CONSTRAINT {ident_name(found.name)} IF EXISTS")
