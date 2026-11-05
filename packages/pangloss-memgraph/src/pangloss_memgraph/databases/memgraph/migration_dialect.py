"""Memgraph's answers where the backends differ in a migration (`pangloss_cypher.dialect.MigrationDialect`).

Memgraph keeps a map as a property (`meta`, an annotated value, a `TypedDict`), so a part of one is `n.meta.created_by`;
it walks with `-[*BFS ...]->`; it keeps `label_folded` beside every `label` (`folding`), which a migration that changes
labels in Cypher writes again (`rederive`); and its indexes and constraints are made with its own statements, outside a
transaction."""

from typing import Any

import neo4j
from pangloss_cypher.migrations.operations import ident
from pangloss_cypher import Transaction
from pangloss_models import PanglossMigrationError, fold
from pangloss_models.migrations import changes as c

from pangloss_memgraph.databases.memgraph.dialect import FOLDED_LABEL

# What `rederive` reads and writes at a time
REDERIVE_BATCH = 10_000

INSERTED_NODE_META = """
    OPTIONAL MATCH (s)<-[:is_creation_of]-(creation:PGCreation)-[:created_by]->(creator:PGUser)
    WITH *, coalesce(s.meta, {
        created_by: creator.username, created_when: creation.created_when,
        updated_by: creator.username, updated_when: creation.created_when,
        semantic_spaces: [], context_labels: []}) AS base_meta
    WITH *, {
        created_by: base_meta.created_by, created_when: base_meta.created_when,
        updated_by: base_meta.updated_by, updated_when: base_meta.updated_when,
        semantic_spaces: coalesce(base_meta.semantic_spaces, []),
        context_labels: CASE
            WHEN s.meta IS NULL THEN []
            WHEN size(coalesce(base_meta.context_labels, [])) > 0 THEN base_meta.context_labels
            WHEN coalesce($labels_in_context[s.type], true)
                THEN [{type: '#rootcontext', contents: [{type: s.type, id: s.id}]}]
            ELSE [] END} AS new_meta
"""


async def run_statement(database: Any, statement: str) -> list[dict[str, Any]]:
    from pangloss_memgraph.databases.memgraph.initialise_database import (
        run_statement,
    )

    return await run_statement(
        database.driver, database.settings.DATABASE.DATABASE_NAME, statement
    )


def constraint_exists(rows: list[dict], entry: dict) -> bool:
    return any(
        row["constraint type"] == "unique"
        and row["label"] == entry["label"]
        and row["properties"] == entry["properties"]
        for row in rows
    )


def unique_statement(verb: str, entry: dict) -> str:
    label = ident(entry["label"])
    properties = ", ".join(f"n.{ident(p)}" for p in entry["properties"])
    return f"{verb} CONSTRAINT ON (n:{label}) ASSERT {properties} IS UNIQUE"


def holds_enum(
    ref: str, descriptor: dict, enum: str, keys: str, depth: int = 0
) -> str | None:
    """A Cypher condition that is true when the value `ref` (of the type `descriptor`) has in it a
    value of `enum` that is one of the `$keys` (their text); None if the type has no such enum"""
    kind = descriptor.get("type")
    if kind == "enum":
        return f"toString({ref}) IN ${keys}" if descriptor["enum"] == enum else None
    if kind == "list":
        inner = holds_enum(f"x{depth}", descriptor["item"], enum, keys, depth + 1)
        return f"any(x{depth} IN {ref} WHERE {inner})" if inner else None
    if kind == "typedDict":
        parts = [
            holds_enum(f"{ref}.{ident(name)}", field, enum, keys, depth + 1)
            for name, field in descriptor["fields"].items()
        ]
        parts = [p for p in parts if p]
        return "(" + " OR ".join(parts) + ")" if parts else None
    return None


def rewrite_enum(
    ref: str, descriptor: dict, enum: str, values: str, depth: int = 0
) -> str | None:
    """A Cypher expression for the value `ref` with the values of `enum` that are keys of the map
    `$values` (by their text) changed to what it says; None if the type has no such enum"""
    kind = descriptor.get("type")
    if kind == "enum":
        if descriptor["enum"] != enum:
            return None
        return f"coalesce(${values}[toString({ref})], {ref})"
    if kind == "list":
        inner = rewrite_enum(f"x{depth}", descriptor["item"], enum, values, depth + 1)
        return f"[x{depth} IN {ref} | {inner}]" if inner else None
    if kind == "typedDict":
        changed = {
            name: rewrite_enum(f"{ref}.{ident(name)}", field, enum, values, depth + 1)
            for name, field in descriptor["fields"].items()
        }
        changed = {
            name: expression for name, expression in changed.items() if expression
        }
        if not changed:
            return None
        # (a key that is not there is left not there)
        built = ref
        for name, expression in changed.items():
            built = (
                f"CASE WHEN {ref}.{ident(name)} IS NULL THEN {built} "
                f"ELSE map.set_key({built}, '{name}', {expression}) END"
            )
        return f"CASE WHEN {ref} IS NULL THEN null ELSE {built} END"
    return None


class MemgraphMigrations:
    # --- walks and `meta` -----------------------------------------------------------------------------------------

    def owned(self, name: str) -> str:
        edge, end = f"{name}_edge", f"{name}_to"
        return f"-[*BFS ({edge}, {end} | NOT {end}:Entity AND NOT coalesce({edge}.reverse, false))]->"

    def meta_mentions(self, node: str, model: str) -> str:
        return f"""{node}.meta IS NOT NULL AND (
            {model} IN coalesce({node}.meta.semantic_spaces, [])
            OR any(label IN coalesce({node}.meta.context_labels, []) WHERE label.type = {model}
                   OR any(entry IN coalesce(label.contents, []) WHERE entry.type = {model})))"""

    inserted_node_meta = INSERTED_NODE_META

    def new_meta_properties(self, *, context: bool) -> str:
        if context:
            return "meta: new_meta"
        return """meta: {created_by: new_meta.created_by, created_when: new_meta.created_when,
                    updated_by: new_meta.updated_by, updated_when: new_meta.updated_when,
                    semantic_spaces: [], context_labels: null}"""

    def meta_properties(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {"meta": meta}

    # --- maps -----------------------------------------------------------------------------------------------------

    def set_map(self, node: str, name: str, entries: dict[str, str]) -> str:
        fields = ", ".join(f"{ident(key)}: {value}" for key, value in entries.items())
        return f"SET {node}.{ident(name)} = {{{fields}}}"

    def map_value(self, node: str, name: str, key: str) -> str:
        return f"{node}.{ident(name)}.{key}"

    def unwrap_map(self, node: str, name: str, key: str, keys: list[str]) -> str:
        prop = f"{node}.{ident(name)}"
        return f"SET {prop} = {prop}.{key}"

    def enum_test(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, keys: str
    ) -> str:
        test = holds_enum(f"{node}.{ident(name)}", descriptor, enum, keys)
        assert test is not None, f"{name} has no value of {enum}"
        return test

    def enum_rewrite(
        self, node: str, name: str, descriptor: dict[str, Any], enum: str, values: str
    ) -> list[tuple[str, str]]:
        ref = f"{node}.{ident(name)}"
        new = rewrite_enum(ref, descriptor, enum, values)
        return [(ref, new)] if new else []

    # --- the folded labels ----------------------------------------------------------------------------------------

    async def rederive(self, tx: Transaction, labels: list[str] | None) -> None:
        """The folded labels that are not the label folded are written again, by the database's ids of their nodes, a
        batch at a time. (All are read, and only what differs is written: a write of a text-indexed property is what
        costs)"""
        matches = (
            ["MATCH (n)"]
            if labels is None
            else [f"MATCH (n:{ident(label)})" for label in labels]
        )
        changed: dict[int, str | None] = {}
        for match in matches:
            query = f"""
                {match} WHERE n.label IS NOT NULL OR n.{FOLDED_LABEL} IS NOT NULL
                RETURN id(n) AS node, n.label AS label, n.{FOLDED_LABEL} AS folded
                """
            result = await tx.run(query)  # ty: ignore[invalid-argument-type]
            async for row in result:
                label = row["label"]
                folded = fold(label) if isinstance(label, str) else None
                if folded != row["folded"]:
                    changed[row["node"]] = folded
        rows = [{"node": node, "folded": folded} for node, folded in changed.items()]
        for start in range(0, len(rows), REDERIVE_BATCH):
            await (
                await tx.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (n) WHERE id(n) = row.node
                    SET n.{FOLDED_LABEL} = row.folded
                    """,
                    rows=rows[start : start + REDERIVE_BATCH],
                )
            ).consume()

    # --- indexes and constraints ------------------------------------------------------------------------------------

    async def add_index(self, database: Any, change: c.AddIndex, state: dict) -> None:
        from pangloss_memgraph.databases.memgraph.initialise_database import (
            create_index_statement,
            index_exists,
        )

        entry = change.index
        label, properties = (
            ident(entry["label"]),
            ", ".join(ident(p) for p in entry["properties"]),
        )
        rows = await run_statement(database, "SHOW INDEX INFO")
        if entry.get("kind") == "text":
            name = ident(entry["name"]).strip("`")
            if not any(
                row["index type"] == f"label_text (name: {name})" for row in rows
            ):
                await run_statement(
                    database,
                    f"CREATE TEXT INDEX {ident(entry['name'])} ON :{label}({properties})",
                )
            return
        if not index_exists(rows, entry):
            await run_statement(database, create_index_statement(entry))

    async def remove_index(
        self, database: Any, change: c.RemoveIndex, state: dict
    ) -> None:
        from pangloss_memgraph.databases.memgraph.initialise_database import (
            create_index_statement,
            index_exists,
        )

        entry = change.index
        rows = await run_statement(database, "SHOW INDEX INFO")
        if entry.get("kind") == "text":
            name = ident(entry["name"]).strip("`")
            if any(row["index type"] == f"label_text (name: {name})" for row in rows):
                await run_statement(database, f"DROP TEXT INDEX {ident(entry['name'])}")
            return
        if index_exists(rows, entry):
            await run_statement(
                database, create_index_statement(entry).replace("CREATE", "DROP", 1)
            )

    async def add_constraint(
        self, database: Any, change: c.AddConstraint, state: dict
    ) -> None:
        rows = await run_statement(database, "SHOW CONSTRAINT INFO")
        if not constraint_exists(rows, change.constraint):
            try:
                await run_statement(
                    database, unique_statement("CREATE", change.constraint)
                )
            except neo4j.exceptions.Neo4jError as error:
                raise PanglossMigrationError(
                    f"Cannot make {change.describe()}: {error.message} (the data may break it already)"
                ) from error

    async def remove_constraint(
        self, database: Any, change: c.RemoveConstraint, state: dict
    ) -> None:
        rows = await run_statement(database, "SHOW CONSTRAINT INFO")
        if constraint_exists(rows, change.constraint):
            await run_statement(database, unique_statement("DROP", change.constraint))
