"""Indexes and constraints, the Neo4j way (what Neo4j does with `CREATE INDEX ON :L(p)` and `... ASSERT ...`).

What was found out about Neo4j (see `docs/neo4j-implementation.md`), and is relied on here:

- indexes and constraints are *named*, and dropped by name, so the names are made from the label and the properties and are
  the same every time. What is already there is recognised by label and properties, not by name, so a database made by hand
  is not made again;
- a uniqueness constraint makes its own index. An index made first makes the constraint fail, and one made after is not
  made (so constraints are made first, and an index that a constraint gives is not asked for);
- nodes have a lookup index by label by default: a label index (`kind: "label"`) needs nothing;
- the text search is a full-text index (Lucene), which finds words (`search_pattern`);
- DDL cannot be in a transaction with data: each statement is run on a session of its own (`run_statement`).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import neo4j

TEXT_INDEX_NAME = "label_text"

# Lower-cases and folds accents: "cafe" finds "Café". (Neo4j's text index folds nothing; it is a better default for a
# name search to find "Zürich" from "zurich", and to be a little looser than Neo4j's.)
FULLTEXT_ANALYZER = "standard-folding"

# How long a new index may take to be ready, in seconds
AWAIT_INDEXES_SECONDS = 300


def ident(name: str) -> str:
    """A name for a statement, quoted"""
    return "`" + name.replace("`", "``") + "`"


def name_part(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def index_name(label: str, properties: list[str] | tuple[str, ...]) -> str:
    return f"pg_idx_{name_part(label)}_{'_'.join(name_part(p) for p in properties)}"


def unique_name(label: str, properties: list[str] | tuple[str, ...]) -> str:
    return f"pg_unique_{name_part(label)}_{'_'.join(name_part(p) for p in properties)}"


@dataclass(frozen=True)
class ExistingIndex:
    name: str
    kind: str
    """`label+property`, `fulltext`, `text`, ... (the type of the index, lower case, `range` as `label+property`)"""
    label: str
    properties: tuple[str, ...]
    owned: bool
    """Made by a constraint (it goes when the constraint does)"""


@dataclass(frozen=True)
class ExistingConstraint:
    name: str
    kind: str
    label: str
    properties: tuple[str, ...]


async def run_statement(
    driver: neo4j.AsyncDriver, database_name: str, statement: str
) -> list[dict[str, Any]]:
    """Run a statement on its own: a change to indexes or constraints cannot be in a transaction with data"""
    async with driver.session(database=database_name) as session:
        result = await session.run(statement)  # type: ignore
        rows = await result.data()
        await result.consume()
        return rows


async def list_indexes(
    driver: neo4j.AsyncDriver, database_name: str
) -> list[ExistingIndex]:
    """The indexes of nodes that are not the lookup indexes every database has"""
    rows = await run_statement(
        driver,
        database_name,
        "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, owningConstraint "
        "WHERE type <> 'LOOKUP' AND entityType = 'NODE' RETURN *",
    )
    found = []
    for row in rows:
        kind = row["type"].lower()
        found.append(
            ExistingIndex(
                name=row["name"],
                kind="label+property" if kind == "range" else kind,
                label=(row["labelsOrTypes"] or [""])[0],
                properties=tuple(row["properties"] or ()),
                owned=row["owningConstraint"] is not None,
            )
        )
    return found


async def list_constraints(
    driver: neo4j.AsyncDriver, database_name: str
) -> list[ExistingConstraint]:
    rows = await run_statement(
        driver,
        database_name,
        "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
        "WHERE entityType = 'NODE' RETURN *",
    )
    return [
        ExistingConstraint(
            name=row["name"],
            kind="unique" if "UNIQUENESS" in row["type"] else row["type"].lower(),
            label=(row["labelsOrTypes"] or [""])[0],
            properties=tuple(row["properties"] or ()),
        )
        for row in rows
    ]


def properties_clause(variable: str, properties: list[str]) -> str:
    return ", ".join(f"{variable}.{ident(p)}" for p in properties)


def create_index_statement(entry: dict[str, Any]) -> str | None:
    """The statement that makes an index of the snapshot (`{"kind": "label+property", "label": "L", "properties": [..]}`),
    or None if there is nothing to make (a label index: every database has one)"""
    label, properties = entry["label"], list(entry["properties"])
    if entry["kind"] == "label" or not properties:
        return None
    if entry["kind"] == "text":
        name = entry.get("name") or TEXT_INDEX_NAME
        return (
            f"CREATE FULLTEXT INDEX {ident(name)} IF NOT EXISTS FOR (n:{ident(label)}) "
            f"ON EACH [{properties_clause('n', properties)}] "
            f"OPTIONS {{indexConfig: {{`fulltext.analyzer`: '{FULLTEXT_ANALYZER}'}}}}"
        )
    return (
        f"CREATE INDEX {ident(index_name(label, properties))} IF NOT EXISTS "
        f"FOR (n:{ident(label)}) ON ({properties_clause('n', properties)})"
    )


def create_constraint_statement(entry: dict[str, Any]) -> str:
    """The statement that makes a uniqueness constraint of the snapshot"""
    label, properties = entry["label"], list(entry["properties"])
    subject = (
        properties_clause("n", properties)
        if len(properties) == 1
        else f"({properties_clause('n', properties)})"
    )
    return (
        f"CREATE CONSTRAINT {ident(unique_name(label, properties))} IF NOT EXISTS "
        f"FOR (n:{ident(label)}) REQUIRE {subject} IS UNIQUE"
    )


async def await_indexes(driver: neo4j.AsyncDriver, database_name: str) -> None:
    """Wait for the indexes just made to be ready (making one is asynchronous: a query before that fails or is slow)"""
    await run_statement(
        driver, database_name, f"CALL db.awaitIndexes({AWAIT_INDEXES_SECONDS})"
    )


def has_index(
    existing: list[ExistingIndex], entry: dict[str, Any]
) -> ExistingIndex | None:
    """The index that is the entry, if there is one: by kind, label and properties, whatever it is called"""
    if entry["kind"] == "text":
        return next(
            (i for i in existing if i.kind == "fulltext" and i.label == entry["label"]),
            None,
        )
    return next(
        (
            i
            for i in existing
            if i.kind == "label+property"
            and i.label == entry["label"]
            and i.properties == tuple(entry["properties"])
        ),
        None,
    )


def has_constraint(
    existing: list[ExistingConstraint], entry: dict[str, Any]
) -> ExistingConstraint | None:
    return next(
        (
            c
            for c in existing
            if c.kind == "unique"
            and c.label == entry["label"]
            and c.properties == tuple(entry["properties"])
        ),
        None,
    )


# --- searching the full-text index ------------------------------------------------------------------------------------

# What does not decompose into a letter and an accent: the analyzer folds these (ASCII folding), the query must too
FOLDED = str.maketrans(
    {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ð": "d", "đ": "d", "ł": "l", "þ": "th"}
)


def fold(text: str) -> str:
    """The text as the index holds it: lower case, accents folded (wildcard terms are not analysed by the query parser, so
    the words of a search are brought to the form of the index here)"""
    lowered = text.lower().translate(FOLDED)
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_patterns(search_terms: str | None) -> list[str]:
    """A pattern for each word of a search: `*word*`, folded. The text is cut where the index cuts a label into words (at
    anything that is not a letter, a digit or an underscore), so what Lucene reads as syntax (`( ) - * ? :` ...) never
    reaches the query, and `max-planck` is the words `max` and `planck`. Nothing to search for gives no pattern."""
    words = re.split(r"[^\w]+", fold(search_terms or ""))
    return [f"*{word}*" for word in words if word]
