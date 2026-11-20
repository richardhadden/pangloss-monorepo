"""Descriptions with `pangloss-derived` (implementation_docs/matches-criteria.md, "With derived edges and documents",
step 6): rules of edges read through a description, with "MatchesCriteria" in the context, one candidate at a time
(`exclusive`), and only the candidates everyone may see; rules of documents only if they allow it; the criteria read
derived documents, but not one derived through a description; and the two workers come to rest after a save."""

import asyncio
import importlib
import uuid
from typing import Any, no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import Court, ref, secretary_of
from pangloss_core import storage_of
from pangloss_criteria import idle, run_pending
from pangloss_criteria.worker import out_of_date
from pangloss_criteria.worker import worker as criteria_worker
from pangloss_cypher import pending
from pangloss_derived import (
    DerivedDocument,
    DerivedDocumentMeta,
    DerivedEdge,
    DerivedFrom,
    DerivesEdge,
    Var,
    read,
    rule,
)
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.store import one_of_each
from pangloss_derived.worker import run_pending_derivations
from pangloss_derived.worker import worker as derived_worker
from pangloss_models import Document, Entity, Match, ReifiedRelation, initialise
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "MatchesCriteria"


class Names(dict):
    __getattr__ = dict.__getitem__


@no_type_check
def models(*, allow=True, narrow: int | None = None):
    """Maximilian's court (as the other tests of the worker), with what rules read:

    - `Activity`: `CoParticipants` between each two of those who carried it out (as the demo's, on `participants`);
    - `Transfer`: `GaveTo` from the giver to each receiver (as the demo's), and two rules of documents that say who
      received something from whom: `received`, which does not read through a description, and `received_maybe`,
      which does (`allow=[MatchesCriteria]`) if `allow`;
    - `narrow`: a rule of edges `NarrowlyGaveTo` that passes only through descriptions of at most so many candidates
      everyone sees (`Through(MatchesCriteria, where=...)`)"""
    from pangloss_models import Compare, Rel, Through

    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class Perhaps[T](ReifiedRelation[T]):
        """Another wrapper, which no rule and no criteria leave out"""

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        _derives = [
            DerivesEdge(
                "CoParticipants",
                subject="carried_out_by",
                object="carried_out_by",
                symmetric=True,
                label="participant",
            )
        ]
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person | Perhaps[Person]]

    class Transfer(Document):
        _derives = [
            DerivesEdge(
                "GaveTo",
                subject="given_by",
                object="given_to",
                ends=("giver", "receiver"),
                reverse_name="received_from",
            )
        ]
        given_by: Person
        given_to: list[Person | MatchesCriteria[Person]]

    class Received(Document):
        """Someone received something from someone (only ever in a document)"""

        _meta = Document.Meta(create_directly=False)
        person: Person
        giver: Person

    class Own(Document):
        """What a derived document is made when someone takes it over"""

        statements: list[Received]

    class DerivedFactoid(Document, DerivedDocument):
        _derived_document_meta = DerivedDocumentMeta(converts_to=Own)
        sources: list[DerivedFrom[Transfer]]
        statements: list[Received]

    @rule
    def received(a: Var[Person], b: Var[Person]):
        """Who received from whom, said plainly: never through a description"""
        return DerivedFactoid.Derive(
            label="Received",
            statements=[Received.Template(label="Received", person=b, giver=a)],
        ).when(Transfer.Where(given_by=a, given_to=b))

    if allow:

        @rule
        def received_maybe(a: Var[Person], b: Var[Person]):
            """The same, and through a description: one document for each candidate"""
            return DerivedFactoid.Derive(
                label="Received, perhaps",
                statements=[
                    Received.Template(label="Received, perhaps", person=b, giver=a)
                ],
            ).when(Transfer.Where(given_by=a, given_to=b), allow=[MatchesCriteria])

    if narrow is not None:

        class NarrowlyGaveTo(DerivedEdge):
            from typing import Annotated

            from pangloss_derived import Object, Subject

            giver: Annotated[Person, Subject()]
            receiver: Annotated[Person, Object()]

        @rule
        def narrowly_gave_to(a: Var[Person], b: Var[Person]):
            return NarrowlyGaveTo.Derive(giver=a, receiver=b).when(
                Transfer.Where(
                    given_by=a,
                    given_to=Rel(
                        is_=b,
                        through=[
                            Through(
                                MatchesCriteria,
                                where=MatchesCriteria.Where(
                                    candidate_count_everyone=Compare[int](lte=narrow)
                                ),
                            )
                        ],
                    ),
                )
            )

    initialise()
    return Names(locals())


# --- helpers ---------------------------------------------------------------------------------------------------------


async def settle(most: int = 20) -> int:
    """Both workers, one after the other, until neither has anything to do. Gives how many alternations it took"""
    for alternation in range(1, most + 1):
        derived = await run_pending_derivations()
        criteria = await run_pending()
        if not derived["heads"] and not criteria:
            left = await marks()
            if not left:
                return alternation
    raise AssertionError(f"the two workers did not come to rest: {await marks()}")


async def marks() -> list[dict]:
    """What is still pending: kind, and the class of the head"""
    return await query(
        f"MATCH (p:{pending.LABEL}) OPTIONAL MATCH (h:HeadNode {{id: p.head_id}}) "
        "RETURN p.kind AS kind, h.type AS type ORDER BY kind, type"
    )


async def query(cypher, **params) -> list[dict]:
    from pangloss_derived.worker import database

    db = database()

    @db.read_transaction
    async def read_rows(tx):
        result = await tx.run(cypher, **params)
        return [dict(r) async for r in result]

    return await read_rows()


async def facts(m, name) -> list[tuple]:
    """The edges of a derived class: `(end, end, plain)`, the ends of a symmetric one in order of label"""
    model = DerivedEdge.named(name) if name not in m else m[name]
    page = await read.list_facts(model, page_size=500)
    found = []
    for view in page["results"]:
        ends = [getattr(view, end).label for end in model._ends]
        if model._symmetric_label:
            ends = sorted(ends)
        found.append((*ends, view.plain))
    return sorted(found)


async def contexts(m, name) -> dict[tuple, list[list[str]]]:
    """The `context_labels` of each justification of each edge of a class, by its ends"""
    model = DerivedEdge.named(name) if name not in m else m[name]
    found = {}
    for view in (await read.list_facts(model, page_size=500))["results"]:
        ends = [getattr(view, end).label for end in model._ends]
        if model._symmetric_label:
            ends = sorted(ends)
        detail = await read.get_fact(model, view.id)
        found[tuple(ends)] = sorted(
            sorted(j.context_labels) for j in detail.justifications
        )
    return found


async def documents(m, by=None) -> dict[tuple, Any]:
    """The derived factoids there are (of the rule `by`), by `(giver, person)` of their statement, with their
    `derived_context`"""
    found = {}
    for item in (await m.DerivedFactoid.list(page_size=500)).results:
        if by is not None and item.derived_by != by:
            continue
        full = await m.DerivedFactoid.get(item.id)
        (statement,) = full.statements
        found[(statement.giver.label, statement.person.label)] = sorted(
            item.derived_context or []
        )
    return found


def description(label="N. N.", criteria=None):
    return {"type": NAME, "wording": label, "criteria": criteria}


class World(Court):
    """The court, with gifts"""

    def __init__(self, m):
        super().__init__(m.Person, m.Office, m.HoldsOffice, m.Activity)
        self.m = m

    async def secretaries(self, *names, employer="Maximilian"):
        for name in names:
            await self.holds(name, employer=employer)

    async def secretary(self, employer="Maximilian", office="Secretary"):
        return secretary_of(await self.office(office), await self.person(employer))

    async def transfer(self, giver, *receivers, label="A gift"):
        """`receivers`: names, or descriptions"""
        return await self.m.Transfer.Create(
            label=label,
            given_by=ref(await self.person(giver)),
            given_to=[
                r if isinstance(r, dict) else ref(await self.person(r))
                for r in receivers
            ],
        ).save()

    async def activity(self, *who, label="An activity"):
        """`who`: names, or descriptions"""
        return await self.m.Activity.Create(
            label=label,
            carried_out_by=[
                w if isinstance(w, dict) else ref(await self.person(w)) for w in who
            ],
            witnessed_by=[],
        ).save()


async def a_world(**options) -> World:
    world = World(models(**options))
    await world.person("Maximilian")
    await world.office("Secretary")
    return world


# --- a rule of edges reads through a description (Q5) -----------------------------------------------------------------


@no_type_check
async def test_an_edge_rule_reads_through_a_description_and_the_fact_is_not_plain(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein")
    await world.transfer(
        "Maximilian", "Lang", description(criteria=await world.secretary())
    )
    await settle()

    assert await facts(world.m, "GaveTo") == [
        ("Maximilian", "Lang", True),
        ("Maximilian", "Serntein", False),
        ("Maximilian", "Waldauf", False),
    ]
    found = await contexts(world.m, "GaveTo")
    assert found[("Maximilian", "Serntein")] == [[NAME]]
    assert found[("Maximilian", "Waldauf")] == [[NAME]]
    assert found[("Maximilian", "Lang")] == [[]]


# --- candidates are alternatives (`exclusive`) ------------------------------------------------------------------------


async def rule_rows(name, seed) -> list[dict]:
    """What the rule's query gives when seeded at a node: the rows `store.one_of_each` is given"""
    from pangloss_derived.compile import compile_rule

    checked = DerivedRegistry.checked[name]
    text, params = compile_rule(checked, checked.seeds[0].node)
    return await query(text, seeds=[str(seed)], **params)


@no_type_check
async def test_candidates_of_one_description_are_never_related_to_each_other(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein", "Lang")
    activity = await world.activity(
        "Kurtz", description(criteria=await world.secretary())
    )
    await settle()

    assert await facts(world.m, "CoParticipants") == [
        ("Kurtz", "Lang", False),
        ("Kurtz", "Serntein", False),
        ("Kurtz", "Waldauf", False),
    ]
    # (the rule's query does find each two candidates of the description: what leaves them out is that one row
    # takes two members of one exclusive wrapper, `store.one_of_each`)
    rule_name = "Activity__CoParticipants"
    rows = await rule_rows(rule_name, activity.id)
    (wrapper,) = await query(
        f"MATCH (w:{NAME}) RETURN w.id AS id",
    )
    two = [
        row
        for row in rows
        if [path[0] for path in row["paths"]] == [wrapper["id"], wrapper["id"]]
    ]
    assert len(rows) == 6 and len(two) == 3
    assert all(r["through"] == [[NAME], [NAME]] for r in two)
    kept = [r for r in rows if one_of_each(DerivedRegistry.checked[rule_name], r)]
    assert len(kept) == 3 and not any(r in two for r in kept)


@no_type_check
async def test_candidates_of_two_descriptions_may_be_related_to_each_other(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein")
    await world.secretaries("Fugger", employer="Sigismund")
    await world.activity(
        "Kurtz",
        description("N. N.", await world.secretary()),
        description("M. M.", await world.secretary("Sigismund")),
    )
    await settle()

    assert await facts(world.m, "CoParticipants") == [
        ("Fugger", "Kurtz", False),
        ("Fugger", "Serntein", False),
        ("Fugger", "Waldauf", False),
        ("Kurtz", "Serntein", False),
        ("Kurtz", "Waldauf", False),
    ]


@no_type_check
async def test_the_places_of_one_description_are_one_alternative_together(
    clear_database,
):
    """N. N. in two places of one activity (one mark, `same_one`): one justification takes one candidate for both,
    so no two candidates are related, and each is related to the other participant once"""
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein", "Lang")
    mark = str(uuid.uuid4())
    activity = await world.activity(
        "Kurtz",
        {**description(criteria=await world.secretary()), "same_one": mark},
        {**description("the same"), "same_one": mark},
    )
    await settle()

    assert await facts(world.m, "CoParticipants") == [
        ("Kurtz", "Lang", False),
        ("Kurtz", "Serntein", False),
        ("Kurtz", "Waldauf", False),
    ]
    # (one justification each: through either place, the proof is the same activity)
    assert await contexts(world.m, "CoParticipants") == {
        ("Kurtz", "Lang"): [[NAME]],
        ("Kurtz", "Serntein"): [[NAME]],
        ("Kurtz", "Waldauf"): [[NAME]],
    }
    # (the query finds each candidate through each place, and pairs of them across the places: the two places
    # are given as one in the paths, so a row that takes two candidates of the mark is left out)
    rule_name = "Activity__CoParticipants"
    checked = DerivedRegistry.checked[rule_name]
    rows = await rule_rows(rule_name, activity.id)
    one = f"{activity.id}:{mark}"
    across = [r for r in rows if [path[0] for path in r["paths"]] == [one, one]]
    assert across and all(r["through"] == [[NAME], [NAME]] for r in across)
    assert not any(
        one_of_each(checked, r) and r["paths"][0][1] != r["paths"][1][1] for r in across
    )
    assert await out_of_date() == []


@no_type_check
async def test_two_descriptions_with_equal_criteria_and_no_mark_are_two(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein")
    await world.activity(
        "Kurtz",
        description("N. N.", await world.secretary()),
        description("N. N. too", await world.secretary()),
    )
    await settle()

    # (two of Maximilian's secretaries took part: any two of them may be those)
    assert await facts(world.m, "CoParticipants") == [
        ("Kurtz", "Serntein", False),
        ("Kurtz", "Waldauf", False),
        ("Serntein", "Waldauf", False),
    ]


# --- only the candidates everyone may see (Q26) -----------------------------------------------------------------------


@no_type_check
async def test_a_candidate_that_rests_on_an_unpublished_document_gives_no_fact_until_it_is_published(
    clear_database, db_driver
):
    world = await a_world()
    await world.secretaries("Waldauf")
    hidden = await world.holds("Serntein")
    await storage_of().operations.set_published_in_db(
        world.m.HoldsOffice, hidden.id, False
    )
    await world.transfer("Maximilian", description(criteria=await world.secretary()))
    await settle()
    # (Serntein is a candidate, for those logged in)
    assert run(
        db_driver,
        f"MATCH (:{NAME})-[e:target]->(p) RETURN p.label AS label, e.seen_by AS seen_by ORDER BY label",
    ) == [
        {"label": "Serntein", "seen_by": "logged_in"},
        {"label": "Waldauf", "seen_by": None},
    ]
    assert await facts(world.m, "GaveTo") == [("Maximilian", "Waldauf", False)]
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Waldauf"): [NAME]
    }

    await storage_of().operations.set_published_in_db(
        world.m.HoldsOffice, hidden.id, True
    )
    await settle()
    assert await facts(world.m, "GaveTo") == [
        ("Maximilian", "Serntein", False),
        ("Maximilian", "Waldauf", False),
    ]
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Serntein"): [NAME],
        ("Maximilian", "Waldauf"): [NAME],
    }

    # (and back)
    await storage_of().operations.set_published_in_db(
        world.m.HoldsOffice, hidden.id, False
    )
    await settle()
    assert await facts(world.m, "GaveTo") == [("Maximilian", "Waldauf", False)]
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Waldauf"): [NAME]
    }


# --- candidates change, and the facts follow --------------------------------------------------------------------------


async def head_state(id) -> dict:
    (row,) = await query(
        "MATCH (h:HeadNode {id: $id}) "
        "OPTIONAL MATCH (h)<-[:is_update_of]-(u) WITH h, count(u) AS updates "
        f"OPTIONAL MATCH (h)-[*1..2]->(d:{NAME}) "
        "RETURN updates, collect(d.evaluated_when) AS evaluated",
        id=str(id),
    )
    return row


@no_type_check
async def test_a_new_candidate_gives_a_new_fact_and_one_that_goes_takes_it_away(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf")
    transfer = await world.transfer(
        "Maximilian", description(criteria=await world.secretary())
    )
    await settle()
    assert await facts(world.m, "GaveTo") == [("Maximilian", "Waldauf", False)]

    held = await world.holds("Serntein")
    assert await run_pending() > 0
    # (the worker's write of the candidates leaves work for the rules, and none for itself)
    left = await marks()
    assert {"kind": "derive", "type": "Transfer"} in left
    assert not [m for m in left if m["kind"] == "criteria"]
    before = await head_state(transfer.id)
    version = (await world.m.Transfer.get(transfer.id)).meta.version

    await run_pending_derivations()
    assert await facts(world.m, "GaveTo") == [
        ("Maximilian", "Serntein", False),
        ("Maximilian", "Waldauf", False),
    ]
    # (what the rules wrote is no work for the criteria but for the derived documents they read, of a rule that
    # allows descriptions: looked at, and no description is written again)
    left = await marks()
    assert left == [{"kind": "criteria", "type": "DerivedFactoid"}]
    written = criteria_worker.stats.written
    assert await run_pending() == 1
    assert criteria_worker.stats.written == written
    assert await head_state(transfer.id) == before
    assert (await world.m.Transfer.get(transfer.id)).meta.version == version
    assert await settle() == 1

    await world.m.HoldsOffice.delete(held.id)
    await settle()
    assert await facts(world.m, "GaveTo") == [("Maximilian", "Waldauf", False)]
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Waldauf"): [NAME]
    }


# --- a rule of documents ----------------------------------------------------------------------------------------------


@no_type_check
async def test_a_document_rule_reads_through_a_description_only_if_it_allows_it(
    clear_database,
):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein")
    await world.transfer(
        "Maximilian", "Lang", description(criteria=await world.secretary())
    )
    await settle()

    # (without `allow=`: the one named in the same field, and no candidate)
    assert await documents(world.m, "received") == {("Maximilian", "Lang"): []}
    # (with it: a document for each candidate, which says what it was derived through)
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Lang"): [],
        ("Maximilian", "Serntein"): [NAME],
        ("Maximilian", "Waldauf"): [NAME],
    }
    rows = await query(
        "MATCH (j:PGJustification {rule: 'received_maybe'}) RETURN j.context_labels AS labels"
    )
    assert sorted(sorted(r["labels"]) for r in rows) == [[], [NAME], [NAME]]


# --- the criteria read derived documents, but not one derived through a description (D10) ------------------------------


def received_something() -> dict:
    return {
        "type": "Person",
        "where": {"$incoming": [{"type": "Received", "field": "person"}]},
    }


async def candidates_of(world, activity) -> list[str]:
    read_back = await world.m.Activity.get(activity.id)
    (described,) = [i for i in read_back.carried_out_by if i.type == NAME]
    return sorted(p.label for p in described.target)


async def found(model, **match) -> list[str]:
    page = await model.search(Match(where=received_something()["where"], **match))
    return sorted(item.label for item in page.results)


@no_type_check
async def test_criteria_read_a_derived_document_but_not_one_derived_through_a_description(
    clear_database,
):
    from pangloss_derived import convert

    world = await a_world()
    await world.secretaries("Waldauf")
    await world.transfer(
        "Maximilian", "Lang", description(criteria=await world.secretary())
    )
    activity = await world.activity(
        "Kurtz", description("whoever received something", received_something())
    )
    await settle()
    assert await documents(world.m, "received_maybe") == {
        ("Maximilian", "Lang"): [],
        ("Maximilian", "Waldauf"): [NAME],
    }

    # (Lang, by a derived document with nothing in its context; not Waldauf, by one derived through a description)
    assert await candidates_of(world, activity) == ["Lang"]
    assert await out_of_date() == []
    # (an ordinary search finds both; one that leaves out another wrapper is not affected by the context)
    assert await found(world.m.Person) == ["Lang", "Waldauf"]
    assert await found(world.m.Person, exclude_wrappers=["Perhaps"]) == [
        "Lang",
        "Waldauf",
    ]
    assert await found(world.m.Person, exclude_wrappers=[NAME]) == ["Lang"]
    # (and where the documents themselves are what is searched for: the same holds of each one found)
    every = await world.m.DerivedFactoid.search(Match(where={}))
    kept = await world.m.DerivedFactoid.search(Match(where={}, exclude_wrappers=[NAME]))
    through = [d for d in every.results if d.derived_context == [NAME]]
    assert through and len(kept.results) == len(every.results) - len(through)
    assert all(d.derived_context != [NAME] for d in kept.results)

    # a person makes it their own: it keeps its context, and is still not read
    ((maybe_id, _),) = [
        (item.id, item)
        for item in (await world.m.DerivedFactoid.list(page_size=50)).results
        if item.derived_by == "received_maybe" and item.derived_context == [NAME]
    ]
    form = await convert.prefill("DerivedFactoid", maybe_id, "Own")
    await convert.convert(
        "DerivedFactoid", maybe_id, "Own", form["initial"], form["version"]
    )
    await settle()
    assert await candidates_of(world, activity) == ["Lang"]
    assert await found(world.m.Person, exclude_wrappers=[NAME]) == ["Lang"]

    # until they clear it, which marks it: then the worker makes the person a candidate
    assert await convert.clear_context("Own", maybe_id) is True
    await settle()
    assert await candidates_of(world, activity) == ["Lang", "Waldauf"]
    assert await found(world.m.Person, exclude_wrappers=[NAME]) == ["Lang", "Waldauf"]
    assert await out_of_date() == []


# --- it ends (the order of things) ------------------------------------------------------------------------------------


async def stored_justifications() -> list[dict]:
    return await query(
        "MATCH (j:PGJustification) "
        "RETURN j.key AS key, j.values AS values, j.context_labels AS labels, j.document_id AS document "
        "ORDER BY key"
    )


async def versions() -> dict[str, int]:
    """Each head document by id: how many updates it has had"""
    rows = await query(
        "MATCH (h:HeadNode) WHERE NOT h:Entity "
        "OPTIONAL MATCH (h)<-[:is_update_of]-(u) "
        "RETURN h.id AS id, count(u) AS updates"
    )
    return {r["id"]: r["updates"] for r in rows}


async def rebuild_finds_nothing() -> None:
    """Every rule built again, in order, and what is pending done: nothing changes, nothing is written"""
    import dataclasses

    before_documents = dataclasses.replace(derived_worker.stats.documents)
    justifications, updates = await stored_justifications(), await versions()
    for name in DerivedRegistry.order:
        await derived_worker.rebuild(DerivedRegistry.all_checked()[name])
        await derived_worker.drain()
    await settle()
    assert await stored_justifications() == justifications
    assert await versions() == updates
    now = derived_worker.stats.documents
    changed = {
        f.name: getattr(now, f.name) - getattr(before_documents, f.name)
        for f in dataclasses.fields(now)
        if getattr(now, f.name) != getattr(before_documents, f.name)
    }
    assert set(changed) <= {"same"}, changed


@no_type_check
async def test_after_a_save_the_two_workers_come_to_rest(clear_database, caplog):
    world = await a_world()
    await world.secretaries("Waldauf", "Serntein")
    activity = await world.activity(
        "Kurtz", description("whoever received something", received_something())
    )
    await settle()
    assert await candidates_of(world, activity) == []

    # one save: a gift to someone named and to someone described
    transfer = await world.transfer(
        "Maximilian", "Lang", description(criteria=await world.secretary())
    )
    alternations = await settle()
    print(f"come to rest after {alternations} alternations")
    assert alternations <= 4

    assert await candidates_of(world, activity) == ["Lang"]
    assert await facts(world.m, "GaveTo") == [
        ("Maximilian", "Lang", True),
        ("Maximilian", "Serntein", False),
        ("Maximilian", "Waldauf", False),
    ]
    assert await facts(world.m, "CoParticipants") == [("Kurtz", "Lang", False)]
    assert await out_of_date() == []
    # (the heads people wrote were not saved again; no derived document was written twice)
    updates = await versions()
    assert updates[str(transfer.id)] == 0 and updates[str(activity.id)] == 0
    assert set(updates.values()) == {0}
    await rebuild_finds_nothing()
    assert await out_of_date() == []


# --- asking something of the description -------------------------------------------------------------------------------


@no_type_check
async def test_a_rule_and_a_search_pass_only_through_narrow_descriptions(
    clear_database,
):
    world = await a_world(narrow=2)
    await world.secretaries("Waldauf", "Serntein")
    await world.transfer("Maximilian", description(criteria=await world.secretary()))
    await settle()
    assert await facts(world.m, "NarrowlyGaveTo") == [
        ("Maximilian", "Serntein", False),
        ("Maximilian", "Waldauf", False),
    ]
    narrow = {
        "given_to": {
            "exists": True,
            "through": [
                {"type": NAME, "where": {"candidate_count_everyone": {"lte": 2}}}
            ],
        }
    }
    page = await world.m.Transfer.search(Match(where=narrow))
    assert len(page.results) == 1

    # (a third candidate: the count changes, which is a `set_computed`, which marks the rules' work)
    await world.secretaries("Lang")
    await settle()
    assert await facts(world.m, "NarrowlyGaveTo") == []
    assert len(await facts(world.m, "GaveTo")) == 3
    assert (await world.m.Transfer.search(Match(where=narrow))).results == []


# --- `idle()` ---------------------------------------------------------------------------------------------------------


@no_type_check
async def test_idle_returns_at_once_with_nothing_pending(clear_database):
    models()
    loop = asyncio.get_running_loop()
    began = loop.time()
    await idle(timeout=5)
    assert loop.time() - began < 1


@no_type_check
async def test_idle_waits_for_work_of_another_kind_and_says_how_much_is_left(
    clear_database,
):
    import uuid

    from pangloss_derived.worker import database

    models()
    db = database()
    head = str(uuid.uuid4())

    @db.write_transaction
    async def mark(tx):
        await pending.mark(tx, "something-else", [head])

    @db.write_transaction
    async def complete(tx):
        claimed = await pending.claim(tx, "something-else", 10, 30.0)
        await pending.complete(tx, "something-else", claimed)

    await mark()
    with pytest.raises(TimeoutError, match="1 heads still have work pending"):
        await idle(timeout=0.2)

    async def later():
        await asyncio.sleep(0.3)
        await complete()

    task = asyncio.create_task(later())
    await idle(timeout=5)
    await task
    assert await marks() == []


# --- the demo's rules, against a description ---------------------------------------------------------------------------
#
# (the demo's models are not tested against a database anywhere: these are its rules and the classes they read,
# copied in shape from `pangloss-demo/demo_app/models.py` and `derived.py`, with a description offered by the class,
# as the demo's `Person` says `CriteriaMeta(allowed=True)`)


@no_type_check
def demo_models():
    from pangloss_criteria import CriteriaMeta
    from pangloss_derived import unordered
    from pangloss_models import Trait

    importlib.reload(pangloss_criteria.models)

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class Group(Entity, Agent):
        _criteria_meta = CriteriaMeta(allowed=True)

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

    class MemberOf(Statement):
        member: Person
        group: Group

    class Activity(Statement):
        _derives = [
            DerivesEdge(
                "CoParticipants",
                subject="participants",
                object="participants",
                symmetric=True,
                label="participant",
            )
        ]
        participants: list[InRole[Agent]]

    class Transfer(Statement):
        _derives = [
            DerivesEdge(
                "GaveTo",
                subject="given_by",
                object="given_to",
                ends=("giver", "receiver"),
                reverse_name="received_from",
            )
        ]
        given_by: Agent
        given_to: Agent

    class ChildOf(Statement):
        child: Person
        parent: Person

    class Sibling(Statement):
        people: list[Person]

    class AbstractFactoid(Document):
        _meta = Document.Meta(abstract=True)

    class Factoid(AbstractFactoid):
        statements: list[Statement]

    class DerivedFactoid(AbstractFactoid, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]
        statements: list[Statement]

    @rule
    def siblings(a: Var[Person], b: Var[Person], parent: Var[Person]):
        """Two children of one parent are siblings"""
        return DerivedFactoid.Derive(
            label="Siblings",
            statements=[Sibling.Template(label="Siblings", people=[a, b])],
        ).when(
            ChildOf.Where(child=a, parent=parent),
            ChildOf.Where(child=b, parent=parent),
            unordered(a, b),
            block=[DerivedFactoid],
        )

    initialise()
    return Names(locals())


class Medici:
    """Cosimo, Lorenzo and Giuliano, members of the Medici; Piero, a parent"""

    def __init__(self, m):
        self.m = m
        self.people: dict[str, Any] = {}

    async def set_up(self):
        medici = await self.m.Group.Create(label="Medici").save()
        self.medici = medici
        for name in ("Cosimo", "Lorenzo", "Giuliano", "Piero"):
            self.people[name] = await self.m.Person.Create(label=name).save()
        for name in ("Cosimo", "Lorenzo", "Giuliano"):
            await self.factoid(
                {
                    "type": "MemberOf",
                    "label": f"{name} of the Medici",
                    "member": ref(self.people[name]),
                    "group": ref(medici),
                }
            )

    def a_medici(self) -> dict:
        return {
            "type": NAME,
            "wording": "one of the Medici",
            "criteria": {
                "type": "Person",
                "where": {
                    "$incoming": [
                        {
                            "type": "MemberOf",
                            "field": "member",
                            "where": {"group": {"is": str(self.medici.id)}},
                        }
                    ]
                },
            },
        }

    def ref(self, name):
        return ref(self.people[name])

    async def factoid(self, *statements, label="A factoid"):
        return await self.m.Factoid.Create(
            label=label, statements=list(statements)
        ).save()


async def a_medici_world() -> Medici:
    world = Medici(demo_models())
    await world.set_up()
    await settle()
    return world


@no_type_check
async def test_the_demo_s_gave_to_reaches_each_candidate_of_a_described_receiver(
    clear_database,
):
    world = await a_medici_world()
    await world.factoid(
        {
            "type": "Transfer",
            "label": "A gift",
            "given_by": world.ref("Piero"),
            "given_to": world.a_medici(),
        }
    )
    await settle()
    assert await facts(world.m, "GaveTo") == [
        ("Piero", "Cosimo", False),
        ("Piero", "Giuliano", False),
        ("Piero", "Lorenzo", False),
    ]
    assert await contexts(world.m, "GaveTo") == {
        ("Piero", name): [[NAME]] for name in ("Cosimo", "Giuliano", "Lorenzo")
    }


@no_type_check
async def test_the_demo_s_siblings_does_not_read_a_described_child(clear_database):
    world = await a_medici_world()
    child_of = {"type": "ChildOf", "label": "A child", "parent": world.ref("Piero")}
    await world.factoid({**child_of, "child": world.a_medici()}, label="N. N.")
    await world.factoid({**child_of, "child": world.ref("Lorenzo")}, label="Lorenzo")
    await world.factoid({**child_of, "child": world.ref("Giuliano")}, label="Giuliano")
    await settle()
    found = {}
    for item in (await world.m.DerivedFactoid.list(page_size=50)).results:
        full = await world.m.DerivedFactoid.get(item.id)
        found[tuple(sorted(p.label for p in full.statements[0].people))] = (
            item.derived_context
        )
    # (a rule of documents with no `allow=`: what is said of the two named children only, plainly; nothing of the
    # candidates of the description, Cosimo among them)
    assert found == {("Giuliano", "Lorenzo"): []}


@no_type_check
async def test_the_demo_s_co_participants_relates_the_named_to_each_candidate_and_no_two_candidates(
    clear_database,
):
    world = await a_medici_world()
    await world.factoid(
        {
            "type": "Activity",
            "label": "A meeting",
            "participants": [
                {"type": "InRole", "role": "host", "target": [world.ref("Piero")]},
                {"type": "InRole", "role": "guest", "target": [world.a_medici()]},
            ],
        }
    )
    await settle()
    assert await facts(world.m, "CoParticipants") == [
        ("Cosimo", "Piero", False),
        ("Giuliano", "Piero", False),
        ("Lorenzo", "Piero", False),
    ]
