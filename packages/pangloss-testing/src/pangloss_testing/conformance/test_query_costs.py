"""What the common operations cost the database, so that a change that makes one slower is seen when it is made, not
on a database of hundreds of thousands of nodes later. Two measures, both exact, so the tests do not depend on how
busy the machine is:

- **the transactions and statements** an operation runs (`Recorded`): an operation that starts running a statement
  for each item it reads, or that grows with the size of a document, is caught; and each has a budget, what it takes
  now, so that one more round trip is a decision, not an accident;
- **the work the database does** for each read (`PROFILE`: the rows each operator touches, Memgraph's "actual hits" and
  Neo4j's db hits), on a database with the item alone and again with hundreds of other items about: a read that has
  started to scan a label, or all the nodes, rather than to start from an index and walk, does more work as the
  database grows, and fails here.

The databases' query plans are their own (implementation_docs/backend-profiling.md): the budgets of work are
compared on one backend, never between them."""

import contextlib
import logging
import re
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_cypher.transactions import LoggedTransaction
from pangloss_models import Document, Entity, Match, initialise
from pangloss_testing.backends import under_test
from pangloss_testing.under_test.initialise_database import initialise_database

from .helpers import DATABASE_NAME

pytestmark = pytest.mark.asyncio(loop_scope="session")


@dataclass
class Recorded:
    """The transactions and the statements run while it was open"""

    transactions: int = 0
    statements: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def reads(self) -> list[tuple[str, dict[str, Any]]]:
        """The statements that write nothing (those that can be profiled again)"""
        return [
            (query, params)
            for query, params in self.statements
            if not WRITES.search(query)
        ]


# (the clauses that write, as the queries spell them: `n.deleted` is read by every query)
WRITES = re.compile(r"\b(CREATE|MERGE|SET|DELETE|REMOVE)\b")


class _Counter(logging.Handler):
    def __init__(self, recorded: Recorded) -> None:
        super().__init__(logging.DEBUG)
        self.recorded = recorded

    def emit(self, record: logging.LogRecord) -> None:
        if " transaction " in record.getMessage():
            self.recorded.transactions += 1


@contextlib.contextmanager
def recorded() -> Generator[Recorded]:
    """What the database was asked while the block ran. (The statements are those of `LoggedTransaction`, which
    every transaction is run through when its logger is at DEBUG)"""
    name = under_test().name
    found = Recorded()
    queries = logging.getLogger(f"pangloss.{name}.queries")
    transactions = logging.getLogger(f"pangloss.{name}.transactions")
    counter = _Counter(found)
    levels = queries.level, transactions.level
    original = LoggedTransaction.run

    async def run(self, query: Any, parameters: Any = None, **kwargs: Any) -> Any:
        found.statements.append((str(query), {**(parameters or {}), **kwargs}))
        return await original(self, query, parameters, **kwargs)

    queries.setLevel(logging.DEBUG)
    transactions.setLevel(logging.DEBUG)
    transactions.addHandler(counter)
    LoggedTransaction.run = run  # ty: ignore[invalid-assignment]
    try:
        yield found
    finally:
        LoggedTransaction.run = original  # ty: ignore[invalid-assignment]
        transactions.removeHandler(counter)
        queries.setLevel(levels[0])
        transactions.setLevel(levels[1])


def _neo4j_hits(plan: Any) -> int:
    return int(plan.get("dbHits", 0)) + sum(
        _neo4j_hits(child) for child in plan.get("children", [])
    )


def work(db_driver, statements: list[tuple[str, dict[str, Any]]]) -> int:
    """The rows the database touches to answer the statements again, profiled"""
    total = 0
    with db_driver.session(database=DATABASE_NAME) as session:
        for query, params in statements:
            result = session.run("PROFILE " + query, params)  # ty: ignore[no-matching-overload]
            if under_test().name == "neo4j":
                profile = result.consume().profile
                assert profile is not None
                total += _neo4j_hits(profile)
            else:
                total += sum(int(row["ACTUAL HITS"] or 0) for row in result.data())
    return total


# How many of each kind of other item there are (people, places, notes): a scan of one kind is that many rows more
CROWD = 200
# How much more work a read may do among the others: a plan made again differs by some rows (Neo4j: 128 and 129 for a
# search, 1,343 and 1,387 for the document of twenty nested documents), a scan of the fewest by `CROWD`
SLACK = 60


def replan(db_driver) -> None:
    """The database's statistics brought up to date, and its plans made again: the test's database is new, and the
    plans of its queries are kept by their text, made with what the statistics said then. (Neo4j makes them again
    itself when the data has changed enough, after a while; Memgraph only when it is told, or restarts)"""
    with db_driver.session(database=DATABASE_NAME) as session:
        if under_test().name == "neo4j":
            session.run("CALL db.prepareForReplanning()").consume()
        else:
            session.run("ANALYZE GRAPH").consume()


def forget_statistics(db_driver) -> None:
    """(the statistics of `ANALYZE GRAPH` would stay for the tests after this one)"""
    if under_test().name == "memgraph":
        with db_driver.session(database=DATABASE_NAME) as session:
            session.run("ANALYZE GRAPH DELETE STATISTICS").consume()


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Citation(Document):
        page: int

    class Statement(Document):
        text: str
        about: Person
        at: list[Place]
        citations: list[Citation]

    class Note(Document):
        text: str
        about: Person

    initialise()
    return Person, Place, Citation, Statement, Note


async def statement_of(Statement, person, places, citations: int):
    return await Statement.Create(
        label=f"Ada spoke at {len(places)} places",
        text="Ada spoke",
        about={"type": "Person", "id": person.id},
        at=[{"type": "Place", "id": p.id} for p in places],
        citations=[{"label": f"p. {n}", "page": n} for n in range(citations)],
    ).save()


async def crowd(Person, Place, Note, size: int) -> None:
    """Other people, places and notes about them: what a read of one item has nothing to do with"""
    for n in range(size):
        other = await Person.Create(label=f"Someone {n:03}").save()
        await Place.Create(label=f"Somewhere {n:03}").save()
        await Note.Create(
            label=f"Note {n:03}",
            text="unrelated",
            about={"type": "Person", "id": other.id},
        ).save()


async def made(Person, Place, Statement):
    """Ada, three places, a statement about her at one place with one citation, and one at all three with twenty"""
    ada = await Person.Create(label="Ada Lovelace").save()
    places = [await Place.Create(label=f"Place {n}").save() for n in range(3)]
    small = await statement_of(Statement, ada, places[:1], 1)
    big = await statement_of(Statement, ada, places, 20)
    return ada, places, small, big


def reads(Person, Statement, ada, small, big) -> dict[str, Any]:
    """The reads of the item page, the list page, search and the field that finds an entity"""
    operations = storage_of().operations
    return {
        "a document": lambda: Statement.get(small.id),
        "a document of twenty nested documents": lambda: Statement.get(big.id),
        "an entity, with what refers to it": lambda: Person.get(ada.id),
        "an entity alone": lambda: operations.get_entity_without_incoming(
            Person, ada.id
        ),
        "what refers to an entity, a few of each": lambda: (
            operations.get_incoming_fields(Person, ada.id, 5)
        ),
        "a page of a list": lambda: Statement.list(page_size=10),
        "a page of a list, with words": lambda: Statement.list(
            "ada spoke", page_size=10
        ),
        "a structured search": lambda: Statement.search(
            Match(where={"about": {"is_": str(ada.id)}})
        ),
        "the entities that start with what is typed": lambda: Entity.autocomplete(
            "ada", types=[Person]
        ),
    }


# What each read takes now: (transactions, statements). Fewer is welcome (lower the budget); more is a decision to
# make knowingly, with the budget raised in the same change and the reason in its message
READ_BUDGETS = {
    "a document": (1, 1),
    "a document of twenty nested documents": (1, 1),
    "an entity, with what refers to it": (1, 2),
    "an entity alone": (1, 1),
    "what refers to an entity, a few of each": (1, 2),
    "a page of a list": (1, 1),
    "a page of a list, with words": (1, 2),
    "a structured search": (1, 1),
    "the entities that start with what is typed": (1, 1),
}

# And each write: one transaction, and statements that do not grow with the document (`UNWIND` of rows): the
# checks before a write (the migration lock, the user, the references, the ids), then the writes
WRITE_BUDGETS = {
    "memgraph": {"create": (1, 7), "update": (1, 10), "delete": (1, 5)},
    "neo4j": {"create": (1, 7), "update": (1, 11), "delete": (1, 5)},
}


@no_type_check
async def test_each_read_is_one_transaction_of_the_statements_it_has_always_had(
    clear_database,
):
    Person, Place, Citation, Statement, Note = models()
    await initialise_database()
    ada, places, small, big = await made(Person, Place, Statement)

    took = {}
    for name, read in reads(Person, Statement, ada, small, big).items():
        with recorded() as r:
            await read()
        took[name] = (r.transactions, len(r.statements))

    over = {
        name: (took[name], budget)
        for name, budget in READ_BUDGETS.items()
        if took[name] > budget
    }
    assert not over, f"(taken, budget): {over}"
    # (and the size of a document makes no difference)
    assert took["a document"] == took["a document of twenty nested documents"]


@no_type_check
async def test_a_write_runs_as_many_statements_however_big_the_document(clear_database):
    Person, Place, Citation, Statement, Note = models()
    await initialise_database()
    ada, places, small, big = await made(Person, Place, Statement)

    with recorded() as one:
        await statement_of(Statement, ada, places[:1], 1)
    with recorded() as twenty:
        await statement_of(Statement, ada, places, 20)

    async def update_to(citations: int, version: int) -> Recorded:
        with recorded() as update:
            await Statement.Update(
                id=big.id,
                label="Ada spoke again",
                text="Ada spoke again",
                about={"type": "Person", "id": ada.id},
                at=[{"type": "Place", "id": p.id} for p in places],
                citations=[{"label": f"p. {n}", "page": n} for n in range(citations)],
            ).save(expected_version=version)
        return update

    update = await update_to(1, 1)
    bigger = await update_to(30, 2)
    with recorded() as delete:
        await Statement.delete(small.id)

    assert len(update.statements) == len(bigger.statements)
    assert (one.transactions, len(one.statements)) == (
        twenty.transactions,
        len(twenty.statements),
    )
    took = {
        "create": (twenty.transactions, len(twenty.statements)),
        "update": (update.transactions, len(update.statements)),
        "delete": (delete.transactions, len(delete.statements)),
    }
    over = {
        name: (took[name], budget)
        for name, budget in WRITE_BUDGETS[under_test().name].items()
        if took[name] > budget
    }
    assert not over, f"(taken, budget): {over}"


@no_type_check
async def test_heads_written_together_are_one_transaction_of_the_statements_of_each(
    clear_database,
):
    from pangloss_models import create_heads

    Person, Place, Citation, Statement, Note = models()
    await initialise_database()
    ada, places, _, _ = await made(Person, Place, Statement)

    with recorded() as alone:
        await statement_of(Statement, ada, places[:1], 1)
    person = Person.Create(label="Bo")._to_db_model()
    statement = Statement.Create(
        label="Bo spoke",
        text="Bo spoke",
        about={"type": "Person", "id": person.id},
        at=[{"type": "Place", "id": places[0].id}],
        citations=[{"label": "p. 1", "page": 1}],
    )
    with recorded() as person_alone:
        await Person.Create(label="Cy").save()
    with recorded() as together:
        await create_heads(person, statement)

    # (one transaction, not one each; and the statements of the two, less the checks of the user made once)
    assert together.transactions == 1
    assert len(together.statements) <= len(alone.statements) + len(
        person_alone.statements
    )


@no_type_check
async def test_a_read_does_no_more_work_when_the_database_has_more_in_it(
    clear_database, db_driver
):
    """The work of each read with nothing else in the database, and again with six hundred other items: people,
    places, and notes about the people. A read that starts from an index and walks from there does the same work; one
    that scans does more. Measured with fresh plans, and on Memgraph with the plans made before the others were
    there too, which it keeps"""
    Person, Place, Citation, Statement, Note = models()
    await initialise_database()
    ada, places, small, big = await made(Person, Place, Statement)
    measured = reads(Person, Statement, ada, small, big)

    async def work_of_each() -> dict[str, int]:
        done = {}
        for name, read in measured.items():
            with recorded() as r:
                await read()
            done[name] = work(db_driver, r.reads())
        return done

    replan(db_driver)
    alone = await work_of_each()
    await crowd(Person, Place, Note, CROWD)
    rounds = {}
    if under_test().name == "memgraph":
        # (Memgraph keeps a plan, by the text of the query, until it restarts: the plans made with the item alone)
        rounds["among the others, planned when it was alone"] = await work_of_each()
    replan(db_driver)
    rounds["among the others"] = await work_of_each()
    try:
        grew = {
            f"{name}, {round}": (alone[name], crowded[name])
            for round, crowded in rounds.items()
            for name in measured
            if crowded[name] > alone[name] + SLACK
        }
        assert not grew, f"(work alone, work then): {grew}"
    finally:
        forget_statistics(db_driver)
    assert all(alone.values()), alone
