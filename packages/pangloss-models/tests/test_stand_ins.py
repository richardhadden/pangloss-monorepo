"""Stand-ins (`hooks.stand_ins`): a document that a relation takes in the place of an entity, because a package says
so of the entity's class"""

import dataclasses
from typing import Annotated, ClassVar

import pytest
from pangloss_models import (
    Computed,
    Document,
    EdgeModel,
    Entity,
    PanglossModelError,
    ReifiedRelation,
    Trait,
    ViaEdge,
    export_models,
    hooks,
    initialise,
)
from pangloss_models.field_definitions import RelationToDocument, RelationToEntity
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


def test_a_stand_in_names_no_property_of_its_type_unless_it_says_and_stays_frozen():
    plain = hooks.StandIn(document="Placeholder", stands_for=lambda model: True)
    assert plain.named_type is None
    named = hooks.StandIn(
        document="Placeholder", stands_for=lambda model: True, named_type="stands_for"
    )
    assert named.named_type == "stands_for"
    with pytest.raises(dataclasses.FrozenInstanceError):
        named.named_type = "other"  # ty: ignore[invalid-assignment]


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


# --- a stand-in that is a generic wrapper -----------------------------------------------------------------------------


class NotDescribed(FieldMarker):
    pass


@pytest.fixture
def described_stands_in():
    stand_in = hooks.StandIn(
        document="Described",
        stands_for=lambda model: getattr(model, "describable", False),
        refused_by=NotDescribed,
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


def described_models(computed: bool = False):
    if computed:

        class Described[T](ReifiedRelation[T]):
            said: str | None = None
            target: Annotated[list[T], Computed()] = []

    else:

        class Described[T](ReifiedRelation[T]):
            said: str | None = None

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        describable: ClassVar[bool] = True
        # (the document stand-in of the tests above, too)
        replaceable: ClassVar[bool] = True

    class Monk(Person):
        pass

    class Group(Entity, Agent):
        describable: ClassVar[bool] = True

    class Place(Entity):
        pass

    class Certainty(EdgeModel):
        certainty: int

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Statement(Document):
        person: Person
        agents: list[Agent]
        place: Place | None = None
        strict: Annotated[Person, NotDescribed()] | None = None
        certain: ViaEdge[Person, Certainty] | None = None
        in_role: list[InRole[Agent]]
        written_out: Group | Described[Group] | None = None
        mixed: list[Agent | Described[Person]]

    initialise()
    return Statement, Described


def uses_of(model, field: str, wrapper: str = "Described") -> list:
    """The uses of a generic among the options of a relation: what its parameter stands for (the names of the
    classes), and the edge model"""
    return sorted(
        (
            sorted(
                o.annotated_type.__name__
                for o in option.parameter_type_options["T"].type_options
            ),
            option.edge_model.__name__ if option.edge_model else None,
        )
        for option in model._meta.fields[field].type_options
        if getattr(getattr(option, "base_type", None), "__name__", None) == wrapper
    )


def test_a_generic_stand_in_is_a_use_of_it_with_the_entity_classes_of_the_relation(
    described_stands_in,
):
    Statement, _ = described_models()
    # (for the class, and the classes below it: one use, of all of them)
    assert uses_of(Statement, "person") == [(["Monk", "Person"], None)]
    # (through a trait: of every class that allows it)
    assert uses_of(Statement, "agents") == [(["Group", "Monk", "Person"], None)]
    # (not for a class that does not; and a field refuses it with the marker)
    assert uses_of(Statement, "place") == []
    assert uses_of(Statement, "strict") == []
    # (with the properties of the relation)
    assert uses_of(Statement, "certain") == [(["Monk", "Person"], "Certainty")]
    # (the entities are still taken as themselves)
    assert {
        o.annotated_type.__name__
        for o in Statement._meta.fields["agents"].type_options
        if isinstance(o, RelationToEntity)
    } == {"Person", "Monk", "Group"}


def test_a_use_the_annotation_writes_out_is_the_only_one(described_stands_in):
    Statement, _ = described_models()
    assert uses_of(Statement, "written_out") == [(["Group"], None)]
    # (the union says who may be described here, though more of its classes allow it)
    assert uses_of(Statement, "mixed") == [(["Monk", "Person"], None)]


def test_what_a_wrapper_holds_takes_the_generic_stand_in_too(described_stands_in):
    Statement, _ = described_models()
    (in_role,) = Statement._meta.fields["in_role"].type_options
    held = in_role.parameter_type_options["T"].type_options
    (described,) = [o for o in held if getattr(o, "base_type", None) is not None]
    assert described.base_type.__name__ == "Described"
    assert sorted(
        o.annotated_type.__name__
        for o in described.parameter_type_options["T"].type_options
    ) == ["Group", "Monk", "Person"]


def test_the_same_classes_make_the_same_use_wherever_they_are_met(
    described_stands_in,
):
    class Described[T](ReifiedRelation[T]):
        pass

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        describable: ClassVar[bool] = True

    class Group(Entity, Agent):
        describable: ClassVar[bool] = True

    class First(Document):
        agents: list[Agent]

    class Second(Document):
        either: Group | Person

    initialise()

    def use(model, field):
        return next(
            o.annotated_type
            for o in model._meta.fields[field].type_options
            if getattr(o, "base_type", None) is Described
        )

    assert use(First, "agents") is use(Second, "either")
    assert use(First, "agents").__pydantic_generic_metadata__["args"] == (
        Group | Person,
    )


def test_a_generic_stand_in_is_written_and_read_where_the_entity_goes(
    described_stands_in,
):
    Statement, Described = described_models()
    made = Statement.Create(
        label="S",
        person={"type": "Described", "said": "N. N.", "target": []},
        agents=[
            {"type": "Group", "id": ID},
            {"type": "Described", "target": [{"type": "Group", "id": ID}]},
        ],
        certain={
            "type": "Described",
            "target": [{"type": "Monk", "id": ID}],
            "edge_properties": {"certainty": 60},
        },
        in_role=[
            {
                "type": "InRole",
                "role": "scribe",
                "target": [{"type": "Described", "said": "a scribe", "target": []}],
            }
        ],
        mixed=[],
    )
    assert made.person.type == "Described" and made.person.said == "N. N."
    assert [item.type for item in made.agents] == ["Group", "Described"]
    assert made.certain.edge_properties.certainty == 60
    assert made.in_role[0].target[0].said == "a scribe"
    # (its parameter is the classes of the relation: a place is no person)
    with pytest.raises(ValidationError):
        Statement.Create(
            label="S",
            person={"type": "Described", "target": [{"type": "Place", "id": ID}]},
            agents=[],
            in_role=[],
            mixed=[],
        )
    # (and it is not taken where no class allows it, or the field refuses it)
    for field in ("place", "strict"):
        with pytest.raises(ValidationError):
            Statement.Create(
                label="S",
                person={"type": "Person", "id": ID},
                agents=[],
                in_role=[],
                mixed=[],
                **{field: {"type": "Described", "target": []}},
            )
    update = Statement.Update(
        id=ID,
        label="S",
        person={"type": "Described", "said": "N. N.", "target": []},
        agents=[],
        in_role=[],
        mixed=[],
    )
    assert update.person.said == "N. N."
    view = Statement.View(
        type="Statement",
        id=ID,
        label="S",
        person={"type": "Described", "id": ID, "said": "N. N.", "target": []},
        agents=[],
        in_role=[],
        mixed=[],
    )
    assert view.person.said == "N. N."


def test_the_use_made_for_a_stand_in_is_a_model_as_one_written_out_is(
    described_stands_in,
):
    from pangloss_models import ModelRegistry

    Statement, Described = described_models()
    uses = [
        model
        for model in ModelRegistry._models
        if model.__pydantic_generic_metadata__["origin"] is Described
    ]
    # (of a group, written out; of a person, written out in one field and made for others; and of both, made for
    # `agents` and what `in_role` holds)
    assert len(uses) == 3
    # (each has the models and the field definitions the others have)
    assert all("Create" in vars(model) and "View" in vars(model) for model in uses)
    assert len({len(model._meta.fields) for model in uses}) == 1


def test_the_export_gives_a_generic_stand_in_as_the_wrapper_it_is(
    described_stands_in,
):
    described_models()
    fields = {
        field["name"]: field
        for field in export_models()["models"]["Statement"]["fields"]
    }
    (described,) = [
        o for o in fields["agents"]["options"] if o.get("type") == "Described"
    ]
    (written,) = [
        o for o in fields["written_out"]["options"] if o.get("type") == "Described"
    ]
    assert described["kind"] == written["kind"]
    assert sorted(o["type"] for o in described["params"]["T"]["options"]) == [
        "Group",
        "Monk",
        "Person",
    ]
    assert "Described" not in [o.get("type") for o in fields["place"]["options"]]


def test_nothing_stands_in_among_what_only_computed_relations_hold(
    described_stands_in,
):
    """`Described[Person].target` is computed: neither a `Described[Person]` nor a document stand-in is offered
    among its own candidates (and the first would never end)"""

    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        stands_for: str

    Statement, Described = described_models(computed=True)
    for field in ("person", "written_out"):
        (use,) = [
            o
            for o in Statement._meta.fields[field].type_options
            if getattr(o, "base_type", None) is Described
        ]
        held = use.parameter_type_options["T"].type_options
        assert all(isinstance(o, RelationToEntity) for o in held)
    # (the relation itself takes both)
    assert stand_ins_of(Statement, "person") == [
        ("Placeholder", ["Monk", "Person"], None)
    ]
    assert uses_of(Statement, "person") == [(["Monk", "Person"], None)]
    # (a wrapper that people fill takes them for what it holds)
    (in_role,) = Statement._meta.fields["in_role"].type_options
    held = in_role.parameter_type_options["T"].type_options
    assert {type(o).__name__ for o in held} == {
        "RelationToEntity",
        "RelationToDocument",
        "RelationToReifiedRelation",
    }
    # (nobody writes the candidates)
    made = Statement.Create(
        label="S",
        person={"type": "Described", "said": "N. N."},
        agents=[],
        in_role=[],
        mixed=[],
    )
    assert "target" not in type(made.person).model_fields


def test_a_generic_stand_in_has_one_type_variable(described_stands_in):
    class Described[T, U](ReifiedRelation[T]):
        other: list[U]

    class Person(Entity):
        describable: ClassVar[bool] = True

    class Statement(Document):
        person: Person

    with pytest.raises(PanglossModelError, match="a generic\\s+stand-in has one"):
        initialise()


def test_without_the_generic_declared_nothing_is_added(described_stands_in):
    class Person(Entity):
        describable: ClassVar[bool] = True

    class Statement(Document):
        person: Person

    initialise()
    assert [
        type(o).__name__ for o in Statement._meta.fields["person"].type_options
    ] == ["RelationToEntity"]


def test_a_stub_names_what_is_read_back_through_a_use_of_a_generic_without_brackets(
    described_stands_in,
):
    """A stand-in inside a reified relation document (`Same[Person]`) is read back through it, in a class named after
    its source: the name a stub gives it is a name"""
    from pangloss_models import ReifiedRelationDocument
    from pangloss_models.typestubs import incoming_classes

    class Described[T](ReifiedRelation[T]):
        said: str | None = None

    class Person(Entity):
        describable: ClassVar[bool] = True

    class Same[T](ReifiedRelationDocument[T]):
        pass

    class Statement(Document):
        same: Same[Person]

    initialise()
    names = list(incoming_classes(Person).values())
    assert names and all(name.isidentifier() for name in names)
    assert any(name.startswith("_Same_") for name in names)
