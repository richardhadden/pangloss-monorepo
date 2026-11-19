"""`Computed()`: a field the server keeps up to date, and nobody writes. It is in what is read and not in what is
written (implementation_docs/matches-criteria.md, "`Computed()`"). How it is stored and written is a backend's, and
tested by the conformance suite (`test_computed.py`)."""

import datetime
from typing import Annotated, ClassVar

import pytest
from annotated_types import Ge
from pangloss_models import (
    AnnotatedValue,
    Computed,
    ComputedTarget,
    ComputedWrite,
    DBField,
    Document,
    Embedded,
    Entity,
    ModelRegistry,
    PanglossModelError,
    ReifiedRelation,
    SemanticSpace,
    export_models,
    hooks,
    initialise,
)
from pangloss_models.computed import (
    computed_fields,
    has_computed,
    has_computed_fields,
    has_computed_relations,
)
from pangloss_models.field_definitions import RelationToDocument
from pangloss_models.markers import FieldMarker, is_computed
from pangloss_models.migrations.snapshot import build_snapshot, snapshot_hash
from pangloss_models.typestubs import generated_classes
from pydantic import ValidationError

ID = "01a1c564-7def-70f0-bd21-410a35c82ab1"
OTHER = "01a1c564-7def-70f0-bd21-410a35c82ab2"


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        """Someone the source does not name"""

        wording: str | None = None
        target: Annotated[list[T], Computed()] = []
        count: Annotated[int, Computed(), Ge(0)] = 0
        worked_out: Annotated[datetime.datetime | None, Computed()] = None
        tags: Annotated[list[str], Computed()] = []

    class Act(Document):
        by: list[Person | Guess[Person]]
        score: Annotated[int, Computed()] = 0
        near: Annotated[list[Place], Computed()] = []
        nearest: Annotated[Place | None, Computed()] = None

    initialise()
    return Person, Place, Guess, Act


def guess_model(Act, kind: str):
    """The model made for `Guess[Person]` in `Act.by`, of a kind (`Create`, `View`, ...)"""
    import typing

    annotation = getattr(Act, kind).model_fields["by"].annotation
    item = typing.get_args(annotation)[0]
    members = typing.get_args(typing.get_args(item)[0])
    return next(member for member in members if "Guess" in member.__name__)


# --- which models have it --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["Create", "Update", "CreateDB", "UpdateDB"])
def test_the_models_that_are_written_do_not_have_a_computed_field(kind):
    Person, Place, Guess, Act = models()

    assert {"score", "near", "nearest"} & set(getattr(Act, kind).model_fields) == set()
    assert "by" in getattr(Act, kind).model_fields
    nested = guess_model(Act, kind)
    assert {"target", "count", "worked_out", "tags"} & set(nested.model_fields) == set()
    assert "wording" in nested.model_fields


@pytest.mark.parametrize("kind", ["View", "HeadView"])
def test_the_models_that_are_read_have_it(kind):
    Person, Place, Guess, Act = models()

    assert {"score", "near", "nearest", "by"} <= set(getattr(Act, kind).model_fields)
    if kind == "View":
        nested = guess_model(Act, "View")
        assert {"target", "count", "worked_out", "tags", "wording"} <= set(
            nested.model_fields
        )


def test_a_read_with_nothing_computed_has_the_defaults_the_class_declares():
    Person, Place, Guess, Act = models()

    view = Act.View(id=ID, type="Act", label="A", by=[{"type": "Guess", "id": OTHER}])

    assert view.score == 0 and view.near == [] and view.nearest is None
    guess = view.by[0]
    assert guess.target == [] and guess.count == 0
    assert guess.worked_out is None and guess.tags == []


def test_the_view_of_an_entity_as_it_is_edited_has_it_too():
    class Place(Entity):
        pass

    class Person(Entity):
        mentions: Annotated[int, Computed()] = 0
        near: Annotated[list[Place], Computed()] = []

    initialise()

    assert {"mentions", "near"} <= set(Person.EditView.model_fields)
    assert {"mentions", "near"} & set(Person.Update.model_fields) == set()


def test_a_read_has_what_was_computed():
    Person, Place, Guess, Act = models()

    view = Act.View(
        id=ID,
        type="Act",
        label="A",
        score=3,
        near=[{"type": "Place", "id": OTHER, "label": "Vienna"}],
        by=[
            {
                "type": "Guess",
                "id": OTHER,
                "count": 1,
                "target": [{"type": "Person", "id": ID, "label": "Ann"}],
            }
        ],
    )

    assert view.score == 3 and view.near[0].label == "Vienna"
    assert view.by[0].target[0].label == "Ann" and view.by[0].count == 1
    dumped = view.model_dump(by_alias=True, mode="json")
    assert dumped["by"][0]["workedOut"] is None and dumped["by"][0]["count"] == 1


def test_a_computed_field_may_be_in_the_reference_view():
    class Person(Entity):
        pass

    class Tally(Document):
        _meta = Document.Meta(reference_view_extra_fields=["mentions"])
        about: list[Person]
        mentions: Annotated[int | None, Computed()] = None

    initialise()

    assert "mentions" in Tally.ReferenceView.model_fields
    assert "mentions" not in Tally.Create.model_fields
    assert Tally.ReferenceView(id=ID, type="Tally", label="T").mentions is None


# --- what a client sends ---------------------------------------------------------------------------------------------


def test_a_computed_value_sent_back_from_a_read_is_taken_out_before_the_check():
    Person, Place, Guess, Act = models()

    made = Act.Create(
        label="A",
        score=99,
        near=[{"type": "Place", "id": OTHER}],
        nearest=None,
        by=[
            {
                "type": "Guess",
                "wording": "N. N.",
                "count": 4,
                "workedOut": "2026-11-19T10:00:00Z",
                "worked_out": None,
                "tags": ["x"],
                "target": [{"type": "Person", "id": ID, "label": "Ann"}],
            }
        ],
    )

    assert not hasattr(made, "score") and not hasattr(made, "near")
    assert made.by[0].wording == "N. N." and not hasattr(made.by[0], "target")
    # (and so is not written)
    written = made._to_db_model()
    assert "score" not in written.model_dump()
    assert set(written.by[0].model_dump()) & {"target", "count", "tags"} == set()

    updated = Act.Update(
        id=ID,
        label="A",
        score=1,
        by=[{"type": "Guess", "id": OTHER, "wording": "N. N.", "target": []}],
    )
    assert not hasattr(updated, "score") and not hasattr(updated.by[0], "target")


def test_a_key_that_is_no_field_is_still_refused():
    Person, Place, Guess, Act = models()

    with pytest.raises(ValidationError):
        Act.Create(label="A", by=[], scores=1)
    with pytest.raises(ValidationError):
        Act.Create(label="A", by=[{"type": "Guess", "targets": []}])


def test_a_document_is_made_without_saying_anything_of_what_is_computed():
    Person, Place, Guess, Act = models()

    made = Act.Create(label="A", by=[{"type": "Guess"}, {"type": "Person", "id": ID}])

    assert [item.type for item in made.by] == ["Guess", "Person"]


# --- the definitions --------------------------------------------------------------------------------------------------


def test_the_definition_says_which_fields_are_computed():
    Person, Place, Guess, Act = models()

    assert is_computed(Act._meta.fields["score"])
    assert is_computed(Guess._meta.fields["target"])
    assert not is_computed(Act._meta.fields["by"])
    assert not is_computed(Guess._meta.fields["wording"])

    fields = computed_fields(Act)
    assert sorted(fields.relations) == ["near", "nearest"]
    assert sorted(fields.values) == ["score"]
    of_guess = computed_fields(Guess)
    assert sorted(of_guess.relations) == ["target"]
    assert sorted(of_guess.values) == ["count", "tags", "worked_out"]
    assert not computed_fields(Person) and not has_computed_fields(Person)
    assert has_computed_fields(Act) and has_computed_fields(Guess)


def test_a_use_of_a_generic_wrapper_has_the_computed_fields_of_the_wrapper():
    Person, Place, Guess, Act = models()

    assert sorted(computed_fields(Guess[Person]).relations) == ["target"]


def test_whether_any_model_computes_anything_is_asked_of_the_models_of_now():
    class Person(Entity):
        pass

    class Plain(Document):
        about: list[Person]

    initialise()
    assert not has_computed() and not has_computed_relations()

    ModelRegistry._reset()

    class Other(Entity):
        pass

    class Counted(Document):
        about: list[Other]
        mentions: Annotated[int, Computed()] = 0

    initialise()
    # (a value, and no relation: nothing that looks like a reference and is none)
    assert has_computed() and not has_computed_relations()

    ModelRegistry._reset()
    models()
    assert has_computed() and has_computed_relations()


def test_a_subclass_of_the_marker_is_computed_too():
    class Worked(Computed):
        pass

    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        mentions: Annotated[int, Worked()] = 0

    initialise()

    assert is_computed(Tally._meta.fields["mentions"])
    assert "mentions" not in Tally.Create.model_fields


def test_other_markers_and_constraints_are_kept_beside_it():
    class Shown(FieldMarker):
        pass

    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        mentions: Annotated[int, Computed(), Shown(), Ge(0)] = 0

    initialise()

    definition = Tally._meta.fields["mentions"]
    assert [type(m).__name__ for m in definition.markers] == ["Computed", "Shown"]
    # (the constraint is the field's: what is read is checked against it)
    with pytest.raises(ValidationError):
        Tally.View(id=ID, type="Tally", label="T", mentions=-1)


# --- what it may be ---------------------------------------------------------------------------------------------------


def test_a_computed_value_needs_a_default_or_to_be_optional():
    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        mentions: Annotated[int, Computed()]

    with pytest.raises(PanglossModelError, match="Tally.mentions.*needs a default"):
        initialise()


def test_a_computed_relation_is_a_list_or_optional():
    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        first: Annotated[Person, Computed()]

    with pytest.raises(PanglossModelError, match="Tally.first.*a list, or optional"):
        initialise()


def test_an_embedded_object_cannot_be_computed():
    class Span(Embedded):
        length: int

    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        span: Annotated[Span | None, Computed()] = None

    with pytest.raises(PanglossModelError, match="Tally.span.*Computed"):
        initialise()


def test_an_annotated_value_cannot_be_computed():
    class Sure[T](AnnotatedValue[T]):
        certainty: int

    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        name: Annotated[Sure[str], Computed()]

    with pytest.raises(PanglossModelError, match="Tally.name.*Computed"):
        initialise()


def test_a_field_can_be_computed_and_of_the_database_only():
    class Person(Entity):
        pass

    class Tally(Document):
        about: list[Person]
        key: Annotated[str | None, Computed(), DBField] = None

    initialise()

    assert "key" not in Tally.Create.model_fields
    # (a `DBField` is not in what a client reads; the server's own models are not asked to write it)
    assert "key" not in Tally.View.model_fields
    assert "key" not in Tally.CreateDB.model_fields


# --- stand-ins --------------------------------------------------------------------------------------------------------


@pytest.fixture
def placeholder_stands_in():
    stand_in = hooks.StandIn(
        document="Placeholder",
        stands_for=lambda model: getattr(model, "replaceable", False),
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


def test_a_computed_relation_takes_no_stand_in(placeholder_stands_in):
    class Placeholder(Document):
        _meta = Document.Meta(create_directly=False)
        said: str

    class Person(Entity):
        replaceable: ClassVar[bool] = True

    class Act(Document):
        by: list[Person]
        like: Annotated[list[Person], Computed()] = []

    initialise()

    def stand_ins(name):
        return [
            option
            for option in Act._meta.fields[name].type_options
            if isinstance(option, RelationToDocument) and option.stands_in_for
        ]

    assert len(stand_ins("by")) == 1
    assert stand_ins("like") == []
    exported = export_models()["models"]["Act"]["fields"]
    by, like = (next(f for f in exported if f["name"] == n) for n in ("by", "like"))
    assert any(t.get("standsInFor") for t in by["options"])
    assert not any(t.get("standsInFor") for t in like["options"])
    assert like["required"] is False


# --- the export, the stubs, the migration snapshot ---------------------------------------------------------------------


def test_the_export_says_which_fields_are_computed():
    Person, Place, Guess, Act = models()

    exported = export_models()["models"]
    act = {field["name"]: field for field in exported["Act"]["fields"]}
    guess = {field["name"]: field for field in exported["Guess"]["fields"]}

    assert act["score"]["computed"] is True and act["near"]["computed"] is True
    assert act["by"]["computed"] is False
    assert guess["target"]["computed"] is True and guess["count"]["computed"] is True
    assert guess["wording"]["computed"] is False
    # (and what it is, as any field: a form shows it)
    assert act["score"]["kind"] == "literal" and act["near"]["kind"] == "relation"
    assert {"name": "Computed", "computed": True} in act["score"]["markers"]


def test_the_stubs_have_it_where_it_is_read_and_not_where_it_is_written():
    Person, Place, Guess, Act = models()

    classes = generated_classes(Act)

    assert "score" in classes["HeadView"].model_fields
    assert "score" in classes["View"].model_fields
    assert "score" not in classes["Create"].model_fields
    assert "near" not in classes["Update"].model_fields


def test_marking_a_field_computed_is_no_migration():
    def declared(marked: bool):
        ModelRegistry._reset()

        class Person(Entity):
            pass

        class Tally(Document):
            about: list[Person]
            mentions: Annotated[int, *([Computed()] if marked else [Ge(0)])] = 0
            like: Annotated[list[Person], *([Computed()] if marked else [])] = []

        initialise()
        return snapshot_hash(build_snapshot())

    assert declared(True) == declared(False)


# --- search -----------------------------------------------------------------------------------------------------------


def test_a_computed_value_is_in_the_where_of_its_class():
    Person, Place, Guess, Act = models()

    assert "score" in Act.Where.model_fields
    where = Act.Where(score={"gte": 2})
    assert where.model_dump(exclude_none=True, by_alias=True)["score"] == {"gte": 2}


def test_a_computed_value_of_a_wrapper_can_be_asked_of_the_way_of_a_relation():
    from pangloss_models import Match
    from pangloss_models.search import check_match

    Person, Place, Guess, Act = models()

    checked = check_match(
        Act,
        Match(
            where={
                "by": {
                    "exists": True,
                    "through": [{"type": "Guess", "where": {"count": {"lte": 3}}}],
                }
            }
        ),
    )

    assert checked is not None


# --- what set_computed is given ---------------------------------------------------------------------------------------


def test_what_a_backend_is_given_to_write():
    target = ComputedTarget(ID, seen_by="logged_in")
    write = ComputedWrite(OTHER, {"target": [target], "count": 1}, based_on_version=3)

    assert target.id == ID and target.seen_by == "logged_in"
    assert ComputedTarget(ID).seen_by is None
    assert write.node_id == OTHER and write.based_on_version == 3
    assert ComputedWrite(OTHER, {}).based_on_version is None


def test_a_semantic_space_has_no_computed_field_of_its_own_by_default():
    class Person(Entity):
        pass

    class Doubtful[T](SemanticSpace[T]):
        pass

    class Act(Document):
        by: list[Person | Doubtful[Person]]

    initialise()

    assert not computed_fields(Doubtful) and not has_computed()
