"""Several heads made in one transaction (`create_heads`, implementation_docs/companion-documents.md): each written in the
order given, so a later one may refer to an earlier one; none if any fails; the labels of the earlier ones known to
the templates of the later; each announced after the commit, in order"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    PanglossConflictError,
    PanglossReferenceError,
    PanglossWriteRefused,
    WriteEvent,
    before_create,
    create_heads,
    initialise,
)
from pangloss_models.hooks import after_write

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def events():
    heard: list[WriteEvent] = []
    after_write.append(heard.append)
    yield heard
    after_write.remove(heard.append)


@no_type_check
def declare():
    class Person(Entity):
        pass

    class Naming(Document):
        named: Person
        first_name: str
        _meta = Document.Meta(label_template="{named} named {first_name}")

        @before_create
        async def refuse_a_bad_name(self):
            if self.first_name == "refused":
                raise PanglossWriteRefused("not a name", field="first_name")

    class Factoid(Document):
        statements: list[Naming]
        _meta = Document.Meta(label_template='Factoid: {statements|join("; ")}')

    initialise()
    return Person, Naming, Factoid


def ids_in_database(db_driver) -> set[str]:
    return {r["id"] for r in run(db_driver, "MATCH (n:HeadNode) RETURN n.id AS id")}


@no_type_check
async def test_a_later_head_can_refer_to_an_earlier_one_by_its_id(
    db_driver, clear_database, events
):
    Person, Naming, Factoid = declare()
    person = Person.Create(label="John of Gaunt")._to_db_model()
    factoid = Factoid.Create(
        statements=[
            {
                "type": "Naming",
                "named": {"type": "Person", "id": person.id},
                "first_name": "John",
            }
        ]
    )

    made = await create_heads(person, factoid)

    assert [m.type for m in made] == ["Person", "Factoid"]
    assert made[0].id == person.id
    # (the label of the person, not yet in the database when the factoid's was worked out)
    assert made[1].label == "Factoid: John of Gaunt named John"
    read = await Factoid.get(made[1].id)
    assert read.statements[0].named.id == person.id
    assert read.statements[0].named.label == "John of Gaunt"
    assert (await Person.get(person.id)).named_reverse[
        0
    ].label == "John of Gaunt named John"
    assert [(e.op, e.model, e.id, e.version) for e in events] == [
        ("create", Person, person.id, 1),
        ("create", Factoid, made[1].id, 1),
    ]


@no_type_check
async def test_a_head_given_as_its_create_model_is_made_as_save_would(
    db_driver, clear_database
):
    Person, _, _ = declare()

    (made,) = await create_heads(Person.Create(label="Blanche"))

    assert (await Person.get(made.id)).label == "Blanche"


@no_type_check
async def test_when_a_later_head_is_refused_none_is_written(
    db_driver, clear_database, events
):
    Person, _, Factoid = declare()
    person = Person.Create(label="Katherine")._to_db_model()

    with pytest.raises(PanglossWriteRefused):
        await create_heads(
            person,
            Factoid.Create(
                statements=[
                    {
                        "type": "Naming",
                        "named": {"type": "Person", "id": person.id},
                        "first_name": "refused",
                    }
                ]
            ),
        )

    assert ids_in_database(db_driver) == set()
    assert events == []


@no_type_check
async def test_when_a_later_head_fails_in_the_database_the_earlier_is_rolled_back(
    db_driver, clear_database, events
):
    Person, _, Factoid = declare()
    taken = await Person.Create(label="Taken").save()
    person = Person.Create(label="Katherine")._to_db_model()
    clash = Factoid.Create(label="Clash", statements=[])._to_db_model()
    # (an id already in use: found by the checks inside the transaction, after the person is written)
    clash.id = taken.id

    with pytest.raises(PanglossConflictError):
        await create_heads(person, clash)

    assert ids_in_database(db_driver) == {str(taken.id)}
    assert [e.id for e in events] == [taken.id]


@no_type_check
async def test_a_head_cannot_refer_to_one_given_after_it(db_driver, clear_database):
    Person, _, Factoid = declare()
    person = Person.Create(label="Later")._to_db_model()

    with pytest.raises(PanglossReferenceError):
        await create_heads(
            Factoid.Create(
                statements=[
                    # (labelled by hand: the template could not name a person not written yet)
                    {
                        "type": "Naming",
                        "label": "By hand",
                        "named": {"type": "Person", "id": person.id},
                        "first_name": "J",
                    }
                ]
            ),
            person,
        )

    assert ids_in_database(db_driver) == set()


@no_type_check
async def test_with_detail_each_is_read_back_whole(db_driver, clear_database):
    Person, _, Factoid = declare()
    person = Person.Create(label="Philippa")._to_db_model()

    _, factoid = await create_heads(
        person,
        Factoid.Create(
            statements=[
                {
                    "type": "Naming",
                    "named": {"type": "Person", "id": person.id},
                    "first_name": "Philippa",
                }
            ]
        ),
        detail=True,
    )

    assert factoid.statements[0].first_name == "Philippa"
    assert factoid.meta.version == 1


@no_type_check
async def test_nothing_given_makes_nothing(db_driver, clear_database):
    declare()
    assert await create_heads() == []
