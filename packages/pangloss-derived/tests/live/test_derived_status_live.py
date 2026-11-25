"""How a justification holds, on the backend under test (`pangloss_derived.status`;
implementation_docs/spaces-and-comparison-plan.md, step 4.1): a rule over a purchase that the source asserts, reports,
orders, denies or says nothing of, by the walk over what is stored of it; and a wrapper's own `DerivedMeta` winning."""

import json
from typing import Annotated, no_type_check

import pytest
from pangloss_derived import DerivedEdge, DerivedMeta, Object, Subject, Var, read, rule
from pangloss_derived.worker import run_pending_derivations
from pangloss_models import Document, Entity, Modal, SemanticSpace, initialise
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models(allow_doubted: bool = False):
    class Reported[T](SemanticSpace[T]):
        pass

    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), fit="prescribes"
        )

    # (it denies what it holds, and its own `DerivedMeta` says to derive from it all the same)
    class Disputed[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=-1, unary=True)
        _derived_meta = DerivedMeta(derivation="qualify")

    # (it asserts what it holds, and its own `DerivedMeta` blocks it)
    class Sealed[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)
        _derived_meta = DerivedMeta(derivation="block")

    class Person(Entity):
        pass

    class Purchase(Document):
        buyer: Person | Not[Person]
        seller: Person

    class Service(Document):
        parts: list[Purchase]

    class Factoid(Document):
        statements: list[
            Purchase
            | Service
            | Reported[Purchase | Not[Purchase]]
            | Known[Purchase | Service]
            | Not[Purchase | Service | Not[Purchase] | Known[Purchase]]
            | Ordered[Purchase | Not[Purchase]]
            | Disputed[Purchase]
            | Sealed[Purchase]
        ]

    class BoughtFrom(DerivedEdge):
        """Who bought from whom"""

        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    @rule
    def bought_from(a: Var[Person], b: Var[Person]):
        return BoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b),
            **({"allow": [Disputed]} if allow_doubted else {}),
        )

    initialise()
    return Person, Factoid, BoughtFrom


def inside(space, *contents):
    return {"type": space, "contents": list(contents)}


@no_type_check
async def world(clear_database, **options):
    Person, Factoid, BoughtFrom = models(**options)
    seller = await Person.Create(label="Seller").save()
    people = {}

    async def purchase(name: str, *, not_the_buyer: bool = False):
        people[name] = await Person.Create(label=name).save()
        buyer = {"type": "Person", "id": people[name].id}
        return {
            "type": "Purchase",
            "label": f"purchase by {name}",
            "buyer": inside("Not", buyer) if not_the_buyer else buyer,
            "seller": {"type": "Person", "id": seller.id},
        }

    return Factoid, BoughtFrom, purchase


async def facts(BoughtFrom) -> dict[str, tuple]:
    """Each fact by its buyer: its context labels and whether it is qualified only"""
    page = await read.list_facts(BoughtFrom, page_size=100)
    return {
        v.buyer.label: (tuple(v.context_labels), v.qualified_only)
        for v in page["results"]
    }


def statuses(db_driver) -> list[str]:
    rows = run(db_driver, "MATCH (j:PGJustification) RETURN j.context AS context")
    return sorted(json.loads(row["context"])["status"] for row in rows)


@no_type_check
async def test_what_is_asserted_is_plain_whatever_spaces_say_so(
    db_driver, clear_database
):
    Factoid, BoughtFrom, purchase = await world(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            await purchase("bare"),
            inside("Known", await purchase("known")),
            inside("Not", inside("Not", await purchase("not not"))),
            inside(
                "Known",
                {
                    "type": "Service",
                    "label": "a service",
                    "parts": [await purchase("part of a known service")],
                },
            ),
        ],
    ).save()
    await run_pending_derivations()
    assert await facts(BoughtFrom) == {
        "bare": ((), False),
        "known": ((), False),
        "not not": ((), False),
        "part of a known service": ((), False),
    }
    assert statuses(db_driver) == ["asserted"] * 4


@no_type_check
async def test_what_is_reported_or_ordered_is_qualified_and_says_which(
    db_driver, clear_database
):
    Factoid, BoughtFrom, purchase = await world(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            inside("Reported", await purchase("reported")),
            inside("Ordered", await purchase("ordered")),
        ],
    ).save()
    await run_pending_derivations()
    assert await facts(BoughtFrom) == {
        "reported": (("Reported",), True),
        "ordered": (("Ordered",), True),
    }
    assert statuses(db_driver) == ["prescribed", "reported"]


@no_type_check
async def test_what_is_denied_or_said_nothing_of_derives_nothing(
    db_driver, clear_database
):
    Factoid, BoughtFrom, purchase = await world(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            inside("Not", await purchase("denied")),
            inside("Reported", inside("Not", await purchase("reported not"))),
            inside("Ordered", inside("Not", await purchase("forbidden"))),
            inside("Not", inside("Known", await purchase("not known"))),
            # (there was no such service, which says nothing of its part: its spaces alone, ["Not"], would say more)
            inside(
                "Not",
                {
                    "type": "Service",
                    "label": "no service",
                    "parts": [await purchase("part of no service")],
                },
            ),
        ],
    ).save()
    await run_pending_derivations()
    assert await facts(BoughtFrom) == {}
    assert statuses(db_driver) == []


@no_type_check
async def test_a_space_on_the_relation_itself_is_walked_from_its_statement(
    db_driver, clear_database
):
    Factoid, BoughtFrom, purchase = await world(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            # (it was not this one who bought: denied)
            await purchase("not the buyer", not_the_buyer=True),
            # (reported that it was not this one: leaning against)
            inside("Reported", await purchase("reported not him", not_the_buyer=True)),
            # (two that are not next to each other do not cancel)
            inside("Not", await purchase("denied twice apart", not_the_buyer=True)),
            await purchase("bare"),
        ],
    ).save()
    await run_pending_derivations()
    assert await facts(BoughtFrom) == {"bare": ((), False)}


@no_type_check
async def test_a_wrapper_s_own_derived_meta_wins_over_the_walk(
    db_driver, clear_database
):
    Factoid, BoughtFrom, purchase = await world(clear_database)
    await Factoid.Create(
        label="F",
        statements=[
            # (it denies, and says `qualify`: derived, qualified, as a plain space is)
            inside("Disputed", await purchase("disputed")),
            # (it asserts, and says `block`)
            inside("Sealed", await purchase("sealed")),
        ],
    ).save()
    await run_pending_derivations()
    assert await facts(BoughtFrom) == {"disputed": (("Disputed",), True)}
    assert statuses(db_driver) == ["reported"]


# --- a pattern nested in another, and a relation that starts at an entity (found by the second reading) ----------


@no_type_check
def nested_models():
    # (no option set: a plain space, as every space was before the walk)
    class Uncertain[T](SemanticSpace[T]):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Person(Entity):
        knows: list[Person | Uncertain[Person] | Not[Person]]

    class Gift(Document):
        giver: Person
        receiver: Person

    class Order(Document):
        content: Gift | Uncertain[Gift] | Not[Gift]

    class GaveTo(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]

    class Knows(DerivedEdge):
        who: Annotated[Person, Subject()]
        whom: Annotated[Person, Object()]

    @rule
    def gave_to(a: Var[Person], b: Var[Person]):
        return GaveTo.Derive(giver=a, receiver=b).when(
            Order.Where(content=Gift.Where(giver=a, receiver=b))
        )

    @rule
    def knows(a: Var[Person], b: Var[Person]):
        return Knows.Derive(who=a, whom=b).when(Person.Where(is_=a, knows=b))

    initialise()
    return Person, Order, GaveTo, Knows


@no_type_check
async def test_a_pattern_nested_in_another_is_read_by_its_own_path(
    db_driver, clear_database
):
    Person, Order, GaveTo, Knows = nested_models()
    receiver = await Person.Create(label="Receiver", knows=[]).save()

    async def order(name: str, space: str | None):
        giver = await Person.Create(label=name, knows=[]).save()
        gift = {
            "type": "Gift",
            "label": f"gift by {name}",
            "giver": {"type": "Person", "id": giver.id},
            "receiver": {"type": "Person", "id": receiver.id},
        }
        content = inside(space, gift) if space else gift
        await Order.Create(label=f"order to {name}", content=content).save()

    await order("bare", None)
    await order("uncertain", "Uncertain")
    await order("denied", "Not")
    await run_pending_derivations()
    page = await read.list_facts(GaveTo, page_size=100)
    assert {
        v.giver.label: (tuple(v.context_labels), v.qualified_only, v.status)
        for v in page["results"]
    } == {
        "bare": ((), False, "asserted"),
        # (as before the walk: derived, and qualified by the space)
        "uncertain": (("Uncertain",), True, "reported"),
    }


@no_type_check
async def test_a_relation_that_starts_at_an_entity_is_read_by_its_spaces(
    db_driver, clear_database
):
    Person, Order, GaveTo, Knows = nested_models()
    known = {
        name: await Person.Create(label=name, knows=[]).save()
        for name in ("plainly", "perhaps", "not")
    }

    def ref(name):
        return {"type": "Person", "id": known[name].id}

    await Person.Create(
        label="Who",
        knows=[
            ref("plainly"),
            inside("Uncertain", ref("perhaps")),
            inside("Not", ref("not")),
        ],
    ).save()
    await run_pending_derivations()
    page = await read.list_facts(Knows, page_size=100)
    assert {
        v.whom.label: (tuple(v.context_labels), v.qualified_only, v.status)
        for v in page["results"]
    } == {
        "plainly": ((), False, "asserted"),
        "perhaps": (("Uncertain",), True, "reported"),
    }
