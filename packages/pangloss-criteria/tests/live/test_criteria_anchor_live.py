"""`evaluate_many`: several descriptions evaluated at once, from an anchor (the ids one head away from an entity the
criteria name, `hops` times, each then tested as any search tests it), root first, or among ids given (seeded).
Whichever way, the result is what `evaluate` gives, root first, of the same criteria (implementation_docs/
matches-criteria.md, "As built", step 7). `Counts` says which way each went."""

import importlib
from typing import Annotated, ClassVar, no_type_check

import pangloss_criteria.models
import pytest
from pangloss_core import storage_of
from pangloss_criteria.evaluate import Counts, Job, evaluate, evaluate_many
from pangloss_criteria.pattern import SearchPattern
from pangloss_cypher import fragments
from pangloss_models import (
    Cites,
    Computed,
    ComputedTarget,
    Document,
    EdgeModel,
    Entity,
    PanglossSearchError,
    ReifiedRelation,
    ViaEdge,
    hooks,
    initialise,
)
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the module: `pangloss_criteria.evaluate` is also the name of a function the package exports)
evaluating = importlib.import_module("pangloss_criteria.evaluate")


@pytest.fixture(autouse=True)
def placeholder_stands_in():
    """A document a relation to a person takes in the person's place (as `Unreconciled` does)"""
    stand_in = hooks.StandIn(
        document="Placeholder",
        stands_for=lambda model: getattr(model, "replaceable", False),
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


def models():
    # (the registry was reset, and a module is only run once: its class is declared again)
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Certainty(EdgeModel):
        percent: int

    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        name: str

    class Person(Entity):
        replaceable: ClassVar[bool] = True
        title: str | None = None
        knows: list[Person]
        born_in: Place | None = None
        near: Annotated[list[Place], Computed()] = []

    class Place(Entity):
        pass

    class Office(Entity):
        pass

    class Source(Document):
        title: str | None = None

    class InRole[T](ReifiedRelation[T]):
        role: str | None = None

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person
        witness: list[InRole[Person]]
        surely: list[ViaEdge[Person, Certainty]]
        evidence: list[Cites[Source]]
        year: int | None = None

    class Factoid(Document):
        statements: list[HoldsOffice]

    initialise()
    return Person, Place, Office, Source, HoldsOffice, Factoid


def ref(item) -> dict:
    return {"type": type(item)._owner.__name__, "id": item.id}


class Court:
    """Maximilian's court and Sigismund's"""

    @no_type_check
    async def make(self):
        (
            self.Person,
            self.Place,
            self.Office,
            self.Source,
            self.HoldsOffice,
            self.Factoid,
        ) = models()
        self.people = {}
        self.wien = await self.Place.Create(label="Wien").save()
        self.secretary = await self.Office.Create(label="Secretary").save()
        self.courier = await self.Office.Create(label="Courier").save()
        self.letters = await self.Source.Create(label="Letters", title="Letters").save()
        await self.person("Maximilian", born_in=ref(self.wien))
        await self.person("Sigismund")
        await self.person("Eck", title="Dr", born_in=ref(self.wien))
        await self.person("Waldauf", knows=[ref(self.people["Maximilian"])])
        self.waldauf = await self.holds(
            "Waldauf",
            witness=[
                {"type": "InRole", "role": "seal", "target": [ref(self.people["Eck"])]}
            ],
            surely=[
                {
                    "type": "Person",
                    "id": (await self.person("Lang")).id,
                    "edge_properties": {"percent": 80},
                }
            ],
            evidence=[{"type": "Source", "id": self.letters.id}],
            year=1500,
        )
        self.serntein = await self.holds(
            "Serntein",
            surely=[
                {
                    "type": "Person",
                    "id": (await self.person("Kurz")).id,
                    "edge_properties": {"percent": 40},
                }
            ],
            year=1505,
        )
        await storage_of().operations.set_published_in_db(
            self.HoldsOffice, self.serntein.id, False
        )
        await self.holds("Lang", employer="Sigismund", office=self.courier)
        self.factoid = await self.Factoid.Create(
            label="A factoid",
            statements=[await self.holding("Kurz", year=1510)],
        ).save()
        self.unknown = await self.HoldsOffice.Create(
            **{
                **(await self.holding("Fugger")),
                "employer": {
                    "type": "Placeholder",
                    "label": "a king",
                    "name": "a king",
                },
            }
        ).save(detail=True)
        return self

    async def person(self, label, **more):
        if label not in self.people:
            self.people[label] = await self.Person.Create(
                label=label, **{"knows": [], **more}
            ).save()
        return self.people[label]

    def id(self, label) -> str:
        return str(self.people[label].id)

    async def holding(self, holder, employer="Maximilian", office=None, **more) -> dict:
        office = office or self.secretary
        return {
            "type": "HoldsOffice",
            "label": f"{holder} holds {office.label} under {employer}",
            "holder": [ref(await self.person(holder))],
            "office": ref(office),
            "employer": ref(await self.person(employer)),
            **{"witness": [], "surely": [], "evidence": [], **more},
        }

    async def holds(self, holder, employer="Maximilian", office=None, **more):
        payload = await self.holding(holder, employer, office, **more)
        payload.pop("type")
        return await self.HoldsOffice.Create(**payload).save()


async def a_court() -> Court:
    return await Court().make()


def holders_of(where: dict, field: str = "holder", **more) -> dict:
    return {
        "type": "Person",
        "where": {
            "$incoming": [
                {"type": "HoldsOffice", "field": field, "where": where, **more}
            ]
        },
    }


def secretary_of(court, employer="Maximilian") -> dict:
    return holders_of(
        {
            "office": {"is": str(court.secretary.id)},
            "employer": {"is": court.id(employer)},
        }
    )


async def the_same(criteria: dict, without=(), limit=None, among=None) -> tuple:
    """`evaluate_many` of one job, which must be what `evaluate` gives (seeded: of the ids given): what it found, and
    the counts of how it went"""
    pattern = SearchPattern(criteria)
    counts = Counts()
    many = await evaluate_many(
        [Job("one", pattern, set(without), among)], limit=limit, counts=counts
    )
    alone = await evaluate(pattern, without, limit)
    if among is not None:
        # (seeded: the full result, of those ids)
        kept = [c for c in alone.candidates if c["id"] in among]
        assert many["one"].candidates == kept
        assert many["one"].count == len(kept)
    else:
        assert many["one"] == alone
    return many["one"], counts


def labels(found) -> list[tuple[str, str]]:
    return [(c["label"], c["seen_by"]) for c in found.candidates]


def way(counts: Counts) -> tuple[int, int, int]:
    return counts.seeded, counts.anchored, counts.root_first


ANCHORED, ROOT_FIRST, SEEDED = (0, 1, 0), (0, 0, 1), (1, 0, 0)


# --- each kind of pattern ---------------------------------------------------------------------------------------------


@no_type_check
async def test_the_secretaries_from_the_anchor(clear_database):
    court = await a_court()

    found, counts = await the_same(secretary_of(court))

    # (Kurz's is a statement of a factoid; Serntein's is not published; Fugger's employer is a stand-in)
    assert labels(found) == [
        ("Kurz", "everyone"),
        ("Serntein", "logged_in"),
        ("Waldauf", "everyone"),
    ]
    assert (found.count, found.count_everyone) == (3, 2)
    assert way(counts) == ANCHORED


@no_type_check
async def test_through_a_wrapper_by_any_way_and_by_through(clear_database):
    court = await a_court()
    max_ = {"employer": {"is": court.id("Maximilian")}}

    seal, counts = await the_same(holders_of(max_, field="witness"))
    named, named_counts = await the_same(
        holders_of(max_, field="witness", through=["InRole"])
    )

    assert labels(seal) == labels(named) == [("Eck", "everyone")]
    assert way(counts) == way(named_counts) == ANCHORED


@no_type_check
async def test_with_a_condition_on_the_edge(clear_database):
    court = await a_court()

    def surely(percent):
        return holders_of(
            {
                "surely": {
                    "is_any": [court.id("Lang"), court.id("Kurz")],
                    "edge": {
                        "type": "Certainty",
                        "where": {"percent": {"gte": percent}},
                    },
                }
            }
        )

    sure, counts = await the_same(surely(60))
    less, _ = await the_same(surely(30))

    assert labels(sure) == [("Waldauf", "everyone")]
    assert labels(less) == [("Serntein", "logged_in"), ("Waldauf", "everyone")]
    assert way(counts) == ANCHORED


@no_type_check
async def test_is_any(clear_database):
    court = await a_court()

    found, counts = await the_same(
        holders_of(
            {"employer": {"is_any": [court.id("Maximilian"), court.id("Sigismund")]}}
        )
    )

    assert [c["label"] for c in found.candidates] == [
        "Kurz",
        "Lang",
        "Serntein",
        "Waldauf",
    ]
    assert way(counts) == ANCHORED


@no_type_check
async def test_far_two_heads_from_the_anchor(clear_database):
    court = await a_court()

    found, counts = await the_same(
        holders_of(
            {
                "employer": {
                    "type": "Person",
                    "where": {"born_in": {"is": str(court.wien.id)}},
                }
            }
        )
    )

    assert [c["label"] for c in found.candidates] == ["Kurz", "Serntein", "Waldauf"]
    assert way(counts) == ANCHORED


@no_type_check
async def test_far_through_what_refers_to_a_second_entity(clear_database):
    """Secretaries of someone who was a courier: the anchor (the office of courier) is two heads from the root"""
    court = await a_court()
    await court.holds("Hans", employer="Lang")

    found, counts = await the_same(
        holders_of(
            {
                "employer": {
                    "type": "Person",
                    "where": {
                        "$incoming": [
                            {
                                "type": "HoldsOffice",
                                "field": "holder",
                                "where": {"office": {"is": str(court.courier.id)}},
                            }
                        ]
                    },
                }
            }
        )
    )

    assert labels(found) == [("Hans", "everyone")]
    assert way(counts) == ANCHORED


@no_type_check
async def test_an_anchor_that_is_a_stand_in(clear_database, db_driver):
    court = await a_court()
    (row,) = run(
        db_driver, "MATCH (p:Placeholder) RETURN p.id AS id, p.head_node_id AS head"
    )
    # (a stand-in is part of the document that holds it)
    assert row["head"] == str(court.unknown.id)

    found, counts = await the_same(holders_of({"employer": {"is": row["id"]}}))

    assert labels(found) == [("Fugger", "everyone")]
    assert way(counts) == ANCHORED


@no_type_check
async def test_an_anchor_that_is_cited(clear_database):
    court = await a_court()

    # (a relation to a citation is to the citation's node: the id of what is cited is no target of it. Found by
    # neither way)
    cited, counts = await the_same(
        holders_of({"evidence": {"is": str(court.letters.id)}})
    )
    assert cited.count == 0
    assert way(counts) == ANCHORED
    # (what is cited, asked of the citation: far, from the other anchor)
    by_target, counts = await the_same(
        holders_of(
            {
                "employer": {"is": court.id("Maximilian")},
                "evidence": {
                    "type": "PGCitation",
                    "where": {"target_id": {"eq": str(court.letters.id)}},
                },
            }
        )
    )
    assert labels(by_target) == [("Waldauf", "everyone")]
    assert way(counts) == ANCHORED


@no_type_check
async def test_the_roots_own_relation(clear_database):
    court = await a_court()

    found, counts = await the_same(
        {"type": "Person", "where": {"knows": {"is": court.id("Maximilian")}}}
    )

    assert labels(found) == [("Waldauf", "everyone")]
    assert way(counts) == ANCHORED


@no_type_check
async def test_an_anchor_merged_into_another(clear_database):
    court = await a_court()
    await court.holds("Fugger", employer="Maximilian I")
    named = secretary_of(court, "Maximilian I")
    before, _ = await the_same(named)
    assert [c["label"] for c in before.candidates] == ["Fugger"]

    await court.Person.merge(
        absorb=court.id("Maximilian I"), into=court.id("Maximilian")
    )

    # (the criteria name the absorbed one: its id leads to the survivor)
    found, counts = await the_same(named)
    assert [c["label"] for c in found.candidates] == [
        "Fugger",
        "Kurz",
        "Serntein",
        "Waldauf",
    ]
    assert way(counts) == ANCHORED


@no_type_check
async def test_without_and_the_cap(clear_database):
    court = await a_court()

    left_out, counts = await the_same(
        secretary_of(court), without=[court.id("Waldauf"), court.id("Kurz")]
    )
    capped, capped_counts = await the_same(secretary_of(court), limit=1)

    assert labels(left_out) == [("Serntein", "logged_in")]
    assert (left_out.count, left_out.count_everyone) == (1, 0)
    assert labels(capped) == [("Kurz", "everyone")]
    assert (capped.count, capped.count_everyone) == (3, 2)
    assert way(counts) == way(capped_counts) == ANCHORED


@no_type_check
async def test_with_no_anchor_root_first(clear_database):
    court = await a_court()

    doctors, counts = await the_same(
        {"type": "Person", "where": {"title": {"eq": "Dr"}}}
    )
    # (an id inside `$not` is no anchor)
    not_of_max, not_counts = await the_same(
        holders_of({"$not": {"employer": {"is": court.id("Maximilian")}}})
    )

    assert labels(doctors) == [("Eck", "everyone")]
    assert [c["label"] for c in not_of_max.candidates] == ["Fugger", "Lang"]
    assert way(counts) == way(not_counts) == ROOT_FIRST


@no_type_check
async def test_too_much_around_the_anchor_is_root_first(clear_database, monkeypatch):
    court = await a_court()

    monkeypatch.setattr(evaluating, "MAX_AMONG", 2)
    among, among_counts = await the_same(secretary_of(court))
    far, far_counts = await the_same(
        holders_of(
            {
                "employer": {
                    "type": "Person",
                    "where": {"born_in": {"is": str(court.wien.id)}},
                }
            }
        )
    )
    monkeypatch.setattr(evaluating, "MAX_AMONG", 5000)
    monkeypatch.setattr(evaluating, "MAX_HEADS", 1)
    heads, heads_counts = await the_same(secretary_of(court))

    assert among == heads and among.count == 3 and far.count == 3
    assert way(among_counts) == way(far_counts) == way(heads_counts) == ROOT_FIRST


@no_type_check
async def test_criteria_that_no_longer_fit_are_the_value_of_their_key(clear_database):
    court = await a_court()
    counts = Counts()

    found = await evaluate_many(
        [
            Job(
                "broken",
                SearchPattern({"type": "Person", "where": {"shoe_size": {"gt": 40}}}),
                set(),
            ),
            Job("gone", SearchPattern({"type": "Nobody", "where": {}}), set()),
            Job("secretaries", SearchPattern(secretary_of(court)), set()),
            Job(
                "doctors",
                SearchPattern({"type": "Person", "where": {"title": {"eq": "Dr"}}}),
                set(),
            ),
        ],
        counts=counts,
    )

    assert isinstance(found["broken"], PanglossSearchError)
    assert "shoe_size" in str(found["broken"])
    assert isinstance(found["gone"], (PanglossSearchError, ValueError))
    assert found["secretaries"] == await evaluate(SearchPattern(secretary_of(court)))
    assert [c["label"] for c in found["doctors"].candidates] == ["Eck"]
    assert way(counts) == (0, 1, 1)


@no_type_check
async def test_many_of_one_shape_with_other_anchors_in_one_call(clear_database):
    court = await a_court()
    for n in range(4):
        await court.holds(f"Clerk {n}", employer=f"Lord {n}")
    patterns = {
        **{f"lord {n}": secretary_of(court, f"Lord {n}") for n in range(4)},
        "max": secretary_of(court),
        "sig": secretary_of(court, "Sigismund"),
        "courier of sig": holders_of(
            {
                "office": {"is": str(court.courier.id)},
                "employer": {"is": court.id("Sigismund")},
            }
        ),
        "doctors": {"type": "Person", "where": {"title": {"eq": "Dr"}}},
    }
    counts = Counts()

    found = await evaluate_many(
        [Job(key, SearchPattern(p), set()) for key, p in patterns.items()],
        counts=counts,
    )

    for key, criteria in patterns.items():
        assert found[key] == await evaluate(SearchPattern(criteria)), key
    assert [c["label"] for c in found["lord 2"].candidates] == ["Clerk 2"]
    assert found["sig"].count == 0
    assert [c["label"] for c in found["courier of sig"].candidates] == ["Lang"]
    assert way(counts) == (0, 7, 1)


@no_type_check
async def test_seeded_is_the_full_result_of_the_ids_given(clear_database):
    court = await a_court()
    among = {
        court.id("Waldauf"),
        court.id("Serntein"),
        court.id("Eck"),
        str(court.factoid.id),
    }

    found, counts = await the_same(secretary_of(court), among=among)
    doctors, _ = await the_same(
        {"type": "Person", "where": {"title": {"eq": "Dr"}}}, among=among
    )
    nothing, _ = await the_same(secretary_of(court), among=set())

    assert labels(found) == [("Serntein", "logged_in"), ("Waldauf", "everyone")]
    assert labels(doctors) == [("Eck", "everyone")]
    assert nothing.count == 0
    assert way(counts) == SEEDED


# --- what is beside the edges of the models ---------------------------------------------------------------------------


def add_shortcut(db_driver, a, b, type: str):
    """An edge between two entities of no field, as `pangloss-derived` writes for `Meta(shortcut=True)`"""
    made = run(
        db_driver,
        f"""
        MATCH (a:PGIndexableNode {{id: $a}}), (b:PGIndexableNode {{id: $b}})
        CREATE (a)-[e:{type} {{key: 'k', {fragments.DERIVED_EDGE}: true}}]->(b)
        RETURN count(e) AS made
        """,
        a=str(a.id),
        b=str(b.id),
    )
    assert made == [{"made": 1}]


@no_type_check
async def test_with_shortcut_edges_the_result_is_the_same(clear_database, db_driver):
    court = await a_court()
    maximilian = court.people["Maximilian"]
    for name in ("Lang", "Eck", "Sigismund"):
        add_shortcut(db_driver, court.people[name], maximilian, "KnowsOf")
    add_shortcut(db_driver, maximilian, court.people["Lang"], "KnowsOf")

    known, counts = await the_same(
        {"type": "Person", "where": {"knows": {"is": court.id("Maximilian")}}}
    )
    secretaries, secretary_counts = await the_same(secretary_of(court))

    assert labels(known) == [("Waldauf", "everyone")]
    assert secretaries.count == 3
    assert way(counts) == way(secretary_counts) == ANCHORED


@no_type_check
async def test_a_computed_relation_of_the_root(clear_database):
    """A relation the server computes (`Computed()`) is followed by a search as any relation is: a person whose
    computed relation is to the anchor is found from the anchor as root first finds them"""
    court = await a_court()
    await storage_of().operations.set_computed(
        court.people["Sigismund"].id, {"near": [ComputedTarget(court.wien.id)]}
    )

    found, counts = await the_same(
        {"type": "Person", "where": {"near": {"is": str(court.wien.id)}}}
    )

    assert labels(found) == [("Sigismund", "everyone")]
    # (criteria that follow a relation the server computes have no anchor: root first)
    assert way(counts) == ROOT_FIRST
