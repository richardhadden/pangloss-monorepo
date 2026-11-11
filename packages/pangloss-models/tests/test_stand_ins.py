"""Stand-ins (`hooks.stand_ins`): a document that a relation takes in the place of an entity, because a package says
so of the entity's class"""

from typing import Annotated, ClassVar

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Entity,
    ReifiedRelation,
    Trait,
    ViaEdge,
    export_models,
    hooks,
    initialise,
)
from pangloss_models.field_definitions import RelationToDocument
from pangloss_models.markers import FieldMarker
from pydantic import ValidationError

ID = "01a1c564-7def-70f0-bd21-410a35c82ab1"


class NotHere(FieldMarker):
    pass


def check(value, names: frozenset[str]) -> None:
    if value.stands_for not in names:
        raise ValueError(
            f"a Placeholder here is {sorted(names)}, not {value.stands_for}"
        )


@pytest.fixture(autouse=True)
def placeholder_stands_in():
    stand_in = hooks.StandIn(
        document="Placeholder",
        stands_for=lambda model: getattr(model, "replaceable", False),
        check=check,
        refused_by=NotHere,
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


def models():
    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        stands_for: str

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        replaceable: ClassVar[bool] = True

    class Monk(Person):
        pass

    class Group(Entity, Agent):
        pass

    class Certainty(EdgeModel):
        certainty: int

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Note(Document):
        text: str

    class Statement(Document):
        person: Person
        agents: list[Agent]
        group: Group | None = None
        either: Group | Note | None = None
        strict: Annotated[Person, NotHere()] | None = None
        certain: ViaEdge[Person, Certainty] | None = None
        in_role: InRole[Agent] | None = None

    initialise()
    return Statement, Placeholder


def stand_ins_of(model, field: str) -> list[tuple[str, list[str], str | None]]:
    return [
        (
            option.annotated_type.__name__,
            sorted(option.stands_in_for),
            option.edge_model.__name__ if option.edge_model else None,
        )
        for option in model._meta.fields[field].type_options
        if isinstance(option, RelationToDocument) and option.stands_in_for
    ]


def test_a_relation_to_an_entity_that_allows_it_takes_the_stand_in_too():
    Statement, _ = models()
    # (for the class, and the classes below it; one option whatever the number of them)
    assert stand_ins_of(Statement, "person") == [
        ("Placeholder", ["Monk", "Person"], None)
    ]
    # (through a trait: only for the classes that allow it)
    assert stand_ins_of(Statement, "agents") == [
        ("Placeholder", ["Monk", "Person"], None)
    ]
    # (not for a class that does not, nor beside a document the relation is declared to take)
    assert stand_ins_of(Statement, "group") == []
    assert stand_ins_of(Statement, "either") == []
    # (a field refuses it with the marker)
    assert stand_ins_of(Statement, "strict") == []
    # (with the properties of the relation)
    assert stand_ins_of(Statement, "certain") == [
        ("Placeholder", ["Monk", "Person"], "Certainty")
    ]


def placeholder(stands_for: str = "Person", **more) -> dict:
    return {"type": "Placeholder", "label": "Someone", "stands_for": stands_for, **more}


def test_the_stand_in_is_given_where_the_entity_goes_and_checked_against_the_field():
    Statement, Placeholder = models()
    made = Statement.Create(
        label="S",
        person=placeholder(),
        agents=[placeholder("Monk"), {"type": "Group", "id": ID}],
        certain={**placeholder(), "edge_properties": {"certainty": 2}},
        in_role={"type": "InRole", "role": "r", "target": [placeholder()]},
    )
    assert isinstance(made.person, Placeholder.Create)
    assert made.agents[0].stands_for == "Monk"
    assert made.certain.edge_properties.certainty == 2
    assert made.in_role.target[0].type == "Placeholder"
    # (and it is written as any nested document is)
    assert made._to_db_model().person.id is not None

    with pytest.raises(
        ValidationError, match=r"person: a Placeholder here is .* not Group"
    ):
        Statement.Create(label="S", person=placeholder("Group"), agents=[])
    with pytest.raises(ValidationError, match="agents: a Placeholder here"):
        Statement.Create(
            label="S",
            person={"type": "Person", "id": ID},
            agents=[placeholder("Group")],
        )
    # (inside a wrapper, where a type variable stands for the entity)
    with pytest.raises(ValidationError, match="target: a Placeholder here"):
        Statement.Create(
            label="S",
            person={"type": "Person", "id": ID},
            agents=[],
            in_role={"type": "InRole", "role": "r", "target": [placeholder("Group")]},
        )
    # (where it is not taken, it is not one of the types)
    with pytest.raises(ValidationError):
        Statement.Create(
            label="S",
            person={"type": "Person", "id": ID},
            agents=[],
            group=placeholder(),
        )
    with pytest.raises(ValidationError):
        Statement.Create(
            label="S",
            person={"type": "Person", "id": ID},
            agents=[],
            strict=placeholder(),
        )


def test_an_update_checks_it_too_and_a_read_gives_it_back():
    Statement, Placeholder = models()
    with pytest.raises(ValidationError, match="person: a Placeholder here"):
        Statement.Update(
            id=ID, label="S", person=placeholder("Group", id=ID), agents=[]
        )
    view = Statement.HeadView(
        id=ID,
        label="S",
        person={
            "type": "Placeholder",
            "id": ID,
            "label": "Someone",
            "stands_for": "Person",
        },
        agents=[],
        meta={
            "created_by": "a",
            "created_when": "2026-01-01T00:00:00Z",
            "updated_by": None,
            "updated_when": None,
        },
    )
    assert isinstance(view.person, Placeholder.View)


def test_the_export_says_what_a_stand_in_stands_for():
    models()
    exported = export_models()
    statement = exported["models"]["Statement"]
    fields = {field["name"]: field for field in statement["fields"]}

    def option(field: str) -> dict:
        return next(o for o in fields[field]["options"] if o["type"] == "Placeholder")

    assert option("person") == {
        "kind": "document",
        "type": "Placeholder",
        "edgeModel": None,
        "standsInFor": ["Monk", "Person"],
    }
    assert "Placeholder" not in [o["type"] for o in fields["group"]["options"]]
    in_role = fields["in_role"]["options"][0]["params"]["T"]["options"]
    assert {
        "kind": "document",
        "type": "Placeholder",
        "edgeModel": None,
        "standsInFor": ["Monk", "Person"],
    } in in_role


def test_without_the_document_declared_nothing_is_added():
    class Person(Entity):
        replaceable: ClassVar[bool] = True

    class Statement(Document):
        person: Person

    initialise()
    assert stand_ins_of(Statement, "person") == []
