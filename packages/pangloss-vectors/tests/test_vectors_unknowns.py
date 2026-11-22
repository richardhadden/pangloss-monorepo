"""The unknowns of a write plan (`unknowns.unknowns_of`) and what the parts say of them (`parts.unknown_vectors`):
implementation_docs/similarity-build-plan.md, phase 10, "Read again (2026-11-22)", rows a and c. No database."""

from typing import no_type_check

import pytest
from pangloss_cypher.write_functions import to_db_model
from pangloss_cypher.write_plan import plan_create
from pangloss_models import Document, Entity, ReifiedRelation, hooks, initialise
from pangloss_vectors import VectorsMeta
from pangloss_vectors.parts import Unknown, unknown_vectors
from pangloss_vectors.unknowns import unknowns_of

from vectors_support import SizedPart

PERSON = "01a1c564-7def-70f0-bd21-410a35c82ab1"


@pytest.fixture(autouse=True)
def stand_ins():
    """Two stand-ins of the test's own: `Mention`, which names the class it stands for (`named_type`), and `Blank`,
    which does not"""
    made = [
        hooks.StandIn(
            document="Mention",
            stands_for=lambda model: model.__name__ in ("Person", "Saint"),
            named_type="stands_for",
        ),
        hooks.StandIn(
            document="Blank", stands_for=lambda model: model.__name__ == "Person"
        ),
    ]
    hooks.stand_ins.extend(made)
    yield
    for stand_in in made:
        hooks.stand_ins.remove(stand_in)


@no_type_check
def declare():
    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class Saint(Person):
        pass

    class Note(Document):
        pass

    class Mention(Document):
        _meta = Document.Meta(create_directly=False)
        stands_for: str

    class Blank(Document):
        _meta = Document.Meta(create_directly=False)

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Letter(Document):
        sender: Person
        recipients: list[Person]
        witnesses: list[InRole[Person]]
        notes: list[Note]

    class Report(Document):
        letters: list[Letter]
        about: list[Person]

    initialise()
    return Letter, Report


def mention(label: str, stands_for: str = "Person") -> dict:
    return {"type": "Mention", "label": label, "stands_for": stands_for}


@no_type_check
def test_a_stand_in_that_names_its_class_is_an_unknown_at_any_depth_in_the_order_of_the_plan():
    Letter, Report = declare()
    instance = to_db_model(
        Report.Create(
            label="a report",
            about=[mention("Ann")],
            letters=[
                {
                    "type": "Letter",
                    "label": "a letter",
                    "sender": mention("Bob", "Saint"),
                    "recipients": [{"type": "Person", "id": PERSON}, mention("Cat")],
                    "witnesses": [
                        {"type": "InRole", "role": "r", "target": [mention("Dan")]}
                    ],
                    "notes": [],
                }
            ],
        )
    )
    letter = instance.letters[0]
    found = unknowns_of(plan_create(instance))
    # (the order of the plan: of the fields as declared, `letters` before `about`)
    assert found == [
        Unknown(str(letter.sender.id), "Saint", "Bob"),
        Unknown(str(letter.recipients[1].id), "Person", "Cat"),
        Unknown(str(letter.witnesses[0].target[0].id), "Person", "Dan"),
        Unknown(str(instance.about[0].id), "Person", "Ann"),
    ]


@no_type_check
def test_a_stand_in_that_names_no_class_or_no_label_or_no_class_of_entities_is_none():
    Letter, _ = declare()
    instance = to_db_model(
        Letter.Create(
            label="a letter",
            sender={"type": "Blank", "label": "someone"},
            recipients=[
                mention(""),
                mention("   "),
                mention("Eve", "Note"),
                mention("Fay", "NoSuchClass"),
                mention("Gil"),
            ],
            witnesses=[],
            notes=[{"type": "Note", "label": "a note"}],
        )
    )
    assert unknowns_of(plan_create(instance)) == [
        Unknown(str(instance.recipients[4].id), "Person", "Gil")
    ]


@no_type_check
def test_with_no_stand_in_that_names_its_class_there_is_none():
    Letter, _ = declare()
    instance = to_db_model(
        Letter.Create(
            label="a letter",
            sender=mention("Bob"),
            recipients=[],
            witnesses=[],
            notes=[],
        )
    )
    plan = plan_create(instance)
    assert len(unknowns_of(plan)) == 1
    named = [s for s in hooks.stand_ins if s.named_type is not None]
    for stand_in in named:
        hooks.stand_ins.remove(stand_in)
    try:
        assert unknowns_of(plan) == []
    finally:
        hooks.stand_ins.extend(named)


# --- what the parts say -------------------------------------------------------------------------------------------


class Saying(SizedPart):
    """A part that says, of each unknown whose label it knows, a vector"""

    def __init__(self, name: str, says: dict[str, list[float]]):
        super().__init__(name)
        self.says = says
        self.asked: list = []

    async def unknown(self, plan, unknowns):
        self.asked.append(list(unknowns))
        return {u.id: self.says[u.label] for u in unknowns if u.label in self.says}


class Failing(SizedPart):
    async def unknown(self, plan, unknowns):
        raise RuntimeError("the part could not")


@pytest.fixture
def parts_registered(parts_of_the_test):
    return parts_of_the_test


ANN = Unknown("a", "Person", "Ann")
BOB = Unknown("b", "Person", "Bob")


@pytest.mark.asyncio
async def test_each_part_with_the_method_is_asked_by_unknown_then_part_and_one_without_is_passed_over(
    parts_registered,
):
    first = Saying("first", {"Ann": [1.0, 0.0, 0.0]})
    second = Saying("second", {"Ann": [0.0, 1.0, 0.0], "Bob": [0.0, 0.0, 1.0]})
    for made in (first, second, SizedPart("without")):
        parts_registered(made)

    found = await unknown_vectors(plan=None, unknowns=[ANN, BOB])

    assert found == {
        "a": {"first": [1.0, 0.0, 0.0], "second": [0.0, 1.0, 0.0]},
        "b": {"second": [0.0, 0.0, 1.0]},
    }
    assert first.asked == [[ANN, BOB]] and second.asked == [[ANN, BOB]]


@pytest.mark.asyncio
async def test_what_a_part_raises_is_not_swallowed(parts_registered):
    parts_registered(Saying("first", {"Ann": [1.0, 0.0, 0.0]}))
    parts_registered(Failing("second"))
    with pytest.raises(RuntimeError, match="the part could not"):
        await unknown_vectors(plan=None, unknowns=[ANN])


@pytest.mark.asyncio
@no_type_check
async def test_an_unknown_of_a_class_without_vectors_is_asked_of_no_part(
    parts_registered,
):
    class Person(Entity):
        pass

    class Ghost(Entity):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    saying = Saying("first", {"Ann": [1.0, 0.0, 0.0], "Gil": [0.0, 1.0, 0.0]})
    parts_registered(saying)
    gil = Unknown("g", "Ghost", "Gil")

    assert await unknown_vectors(plan=None, unknowns=[ANN, gil]) == {
        "a": {"first": [1.0, 0.0, 0.0]}
    }
    assert saying.asked == [[ANN]]
    assert await unknown_vectors(plan=None, unknowns=[gil]) == {}
    assert saying.asked == [[ANN]]
