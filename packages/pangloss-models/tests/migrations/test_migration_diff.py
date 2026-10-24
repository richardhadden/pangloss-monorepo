"""What changed between two versions of the models, and what is asked about it"""

import datetime
from enum import Enum
from typing import Annotated, no_type_check

from annotated_types import Ge
from migration_support import changes, snapshot_of
from pangloss_models.field_definitions import FieldSubclassing
from pangloss_models.meta_kit.migrations import (
    PossibleRename,
    diff,
    snapshot_hash,
)
from pangloss_models.meta_kit.migrations.changes import (
    AddEnumMember,
    AddField,
    AlterAnnotatedValue,
    AlterCardinality,
    AlterEdgeModel,
    AlterEnumMemberValue,
    AlterLiteralType,
    AlterModelKind,
    AlterModelLabels,
    AlterModelOption,
    AlterNullability,
    AlterParentFields,
    AlterRelationTarget,
    AlterReverseName,
    AnnotatedValueToLiteral,
    ChangeFieldKind,
    CreateEnum,
    CreateModel,
    DeleteModel,
    LiteralToAnnotatedValue,
    RemoveEnumMember,
    RenameEnum,
    RenameEnumMember,
    RenameField,
    RenameModel,
    UnwrapRelation,
    WrapRelation,
)
from pangloss_models.model_bases.annotated_value import AnnotatedValue
from pangloss_models.model_bases.configs import RelationConfig
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.embedded import Embedded
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_models.model_bases.trait import Trait


def kinds(result) -> list[str]:
    return [c.kind for c in result.changes]


def one(result, cls):
    found = [c for c in result.changes if isinstance(c, cls)]
    assert len(found) == 1, (cls.__name__, result.changes)
    return found[0]


# ---------------------------------------------------------------------------
# The snapshot
# ---------------------------------------------------------------------------


@no_type_check
def test_the_snapshot_says_how_models_are_stored():
    def declare():
        class Agent(Trait):
            pass

        class Place(Entity):
            pass

        class Person(Entity, Agent):
            pass

        class Date(Embedded):
            when: datetime.date

        class Statement(Document):
            involves: list[Agent]
            places: list[Place]
            date: Date

        class Action(Statement):
            carried_out_by: Annotated[
                Person,
                RelationConfig(
                    reverse_name="carried_out",
                    subclasses_parent_fields=[
                        FieldSubclassing("involves", field_on_model=Statement)
                    ],
                ),
            ]

    snapshot = snapshot_of(declare)
    action = snapshot["models"]["Action"]

    # the labels of its nodes
    assert action["labels"] == ["Action", "Statement", "Document"]
    assert snapshot["models"]["Person"]["labels"] == ["Person", "Agent", "Entity"]

    fields = {f["name"]: f for f in action["fields"]}
    # a relation is an edge pair, and a pair more for each parent field it narrows
    assert fields["carried_out_by"]["storage"] == {
        "kind": "edge",
        "edges": [["carried_out_by", "carried_out"], ["involves", "involves_reverse"]],
    }
    assert fields["places"]["storage"] == {
        "kind": "edge",
        "edges": [["places", "places_reverse"]],
    }
    assert fields["date"]["storage"] == {
        "kind": "embedded_node",
        "edges": [["date", "date_reverse"]],
    }
    when = {f["name"]: f for f in snapshot["models"]["Date"]["fields"]}["when"]
    assert when["storage"] == {"kind": "property"}


@no_type_check
def test_a_snapshot_can_be_written_and_read_back():
    import json

    def declare():
        class Colour(Enum):
            RED = "red"

        class Person(Entity):
            colour: Colour

    snapshot = snapshot_of(declare)
    assert json.loads(json.dumps(snapshot)) == snapshot
    assert snapshot["version"] == 1
    # (what was read back compares as the same)
    assert diff(snapshot, json.loads(json.dumps(snapshot))).changes == []


@no_type_check
def test_the_hash_is_of_what_is_stored():
    def declare(description="", max_value=10, order=False):
        def declare_it():
            class Person(Entity):
                if description:
                    __doc__ = description
                age: Annotated[int, Ge(0)] if max_value == 10 else int
                name: str

        return declare_it

    base = snapshot_hash(snapshot_of(declare()))
    # the same declarations: the same hash
    assert snapshot_hash(snapshot_of(declare())) == base
    # a docstring and a validator are not stored
    assert snapshot_hash(snapshot_of(declare(description="A person"))) == base
    assert snapshot_hash(snapshot_of(declare(max_value=11))) == base

    # the order of the fields is not stored either
    def reordered():
        class Person(Entity):
            name: str
            age: Annotated[int, Ge(0)]

    assert snapshot_hash(snapshot_of(reordered)) == base

    # but a type is
    def retyped():
        class Person(Entity):
            age: float
            name: str

    assert snapshot_hash(snapshot_of(retyped)) != base


# ---------------------------------------------------------------------------
# No change, and the order of changes
# ---------------------------------------------------------------------------


@no_type_check
def test_the_same_models_have_no_changes():
    def declare():
        class Person(Entity):
            name: str

    result = changes(declare, declare)
    assert result.changes == []
    assert result.is_final


@no_type_check
def test_changes_come_in_the_order_they_can_be_applied():
    def before():
        class Person(Entity):
            old: str

    def after():
        class Colour(Enum):
            RED = "red"

        class Place(Entity):
            pass

        class Person(Entity):
            colour: Colour
            home: Place

    result = changes(before, after)
    order = kinds(result)
    # what others need is made first; what is gone, last
    assert order.index("CreateEnum") < order.index("AddField")
    assert order.index("CreateModel") < order.index("AddField")
    assert order.index("AddField") < order.index("RemoveField")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@no_type_check
def test_models_added_and_removed():
    def before():
        class Old(Entity):
            pass

    def after():
        class New(Entity):
            pass

    result = changes(before, after)
    assert one(result, CreateModel).model == "New"
    assert one(result, DeleteModel).model == "Old"
    assert one(result, DeleteModel).safety == "lossy"
    # (both were asked about: they might be one model renamed)
    assert [q.what for q in result.questions] == ["model"]


@no_type_check
def test_a_parent_class_or_trait_changes_the_labels():
    def before():
        class Agent(Trait):
            pass

        class Person(Entity):
            pass

    def after():
        class Agent(Trait):
            pass

        class Person(Entity, Agent):
            pass

    change = one(changes(before, after), AlterModelLabels)
    assert change.model == "Person"
    assert change.added == ["Agent"]
    assert change.removed == []


@no_type_check
def test_a_change_of_kind_is_left_to_a_person():
    def before():
        class Thing(Entity):
            pass

    def after():
        class Thing(Document):
            pass

    result = changes(before, after)
    change = one(result, AlterModelKind)
    assert (change.old, change.new) == ("Entity", "Document")
    assert change.safety == "manual"


@no_type_check
def test_model_options():
    def before():
        class Thing(Entity):
            pass

    def after():
        class Thing(Entity):
            _meta = Entity.Meta(create_with_id=True, abstract=True)

    options = {
        c.option: (c.old, c.new)
        for c in changes(before, after).changes
        if isinstance(c, AlterModelOption)
    }
    assert options == {"abstract": (False, True), "createWithId": (False, True)}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


@no_type_check
def test_enums_and_their_members():
    def before():
        class Colour(Enum):
            RED = "red"
            GREEN = "green"

        class Thing(Entity):
            colour: Colour

    def after():
        class Colour(Enum):
            RED = "red"
            BLUE = "blue"

        class Size(Enum):
            SMALL = "small"

        class Thing(Entity):
            colour: Colour
            size: Size

    result = changes(before, after)
    assert one(result, CreateEnum).enum == "Size"
    assert one(result, AddEnumMember).member == "BLUE"
    removed = one(result, RemoveEnumMember)
    assert (removed.enum, removed.member) == ("Colour", "GREEN")
    # (GREEN went and BLUE came: a member renamed, or not?)
    assert [(q.what, q.old, q.new) for q in result.questions] == [
        ("enum_member", "GREEN", "BLUE")
    ]


@no_type_check
def test_a_member_renamed_with_the_same_value_is_not_a_question():
    def before():
        class Colour(Enum):
            RED = "red"
            GREEN = "green"

        class Thing(Entity):
            colour: Colour

    def after():
        class Colour(Enum):
            RED = "red"
            LIME = "green"

        class Thing(Entity):
            colour: Colour

    # (an enum is stored as the values: the same value is the same member, whatever it is called)
    result = changes(before, after)
    assert result.is_final
    assert kinds(result) == ["RenameEnumMember"]
    renamed = one(result, RenameEnumMember)
    assert (renamed.enum, renamed.old, renamed.new) == ("Colour", "GREEN", "LIME")
    assert renamed.safety == "safe"


@no_type_check
def test_a_member_whose_value_changes_changes_the_data():
    def before():
        class Colour(Enum):
            RED = "red"
            GREEN = "green"

        class Thing(Entity):
            colour: Colour

    def after():
        class Colour(Enum):
            RED = "red"
            GREEN = "verde"

        class Thing(Entity):
            colour: Colour

    result = changes(before, after)
    assert kinds(result) == ["AlterEnumMemberValue"]
    altered = one(result, AlterEnumMemberValue)
    assert (altered.member, altered.old, altered.new) == ("GREEN", "green", "verde")
    assert altered.safety == "transforming"


@no_type_check
def test_a_member_renamed_and_given_another_value_is_asked_about_and_then_both():
    def before():
        class Colour(Enum):
            RED = "red"
            GREEN = "green"

        class Thing(Entity):
            colour: Colour

    def after():
        class Colour(Enum):
            RED = "red"
            LIME = "lime"

        class Thing(Entity):
            colour: Colour

    question = changes(before, after).questions[0]
    assert (question.what, question.old, question.new) == (
        "enum_member",
        "GREEN",
        "LIME",
    )
    result = changes(before, after, confirmed=[question])
    assert kinds(result) == ["RenameEnumMember", "AlterEnumMemberValue"]
    assert result.is_final

    # (declined: GREEN goes, and LIME comes)
    declined = changes(before, after, declined=[question])
    assert sorted(kinds(declined)) == ["AddEnumMember", "RemoveEnumMember"]


@no_type_check
def test_a_renamed_enum_is_only_the_name():
    def before():
        class Colour(Enum):
            RED = "red"

        class Thing(Entity):
            colour: Colour

    def after():
        class Hue(Enum):
            RED = "red"

        class Thing(Entity):
            colour: Hue

    question = changes(before, after).questions[0]
    result = changes(before, after, confirmed=[question])
    assert kinds(result) == ["RenameEnum"]
    assert one(result, RenameEnum).safety == "safe"


# ---------------------------------------------------------------------------
# Literal fields
# ---------------------------------------------------------------------------


@no_type_check
def test_adding_an_optional_and_a_required_field():
    def before():
        class Person(Entity):
            name: str

    def after():
        class Person(Entity):
            name: str
            nickname: str | None
            born: int

    added = {
        c.name: c for c in changes(before, after).changes if isinstance(c, AddField)
    }
    assert added["nickname"].needs_value is False
    assert added["nickname"].safety == "safe"
    assert added["born"].needs_value is True
    assert added["born"].safety == "additive"


@no_type_check
def test_type_and_nullability_of_a_literal():
    def before():
        class Person(Entity):
            age: str
            height: float | None

    def after():
        class Person(Entity):
            age: int
            height: float

    result = changes(before, after)
    retyped = one(result, AlterLiteralType)
    assert (retyped.name, retyped.old, retyped.new) == (
        "age",
        {"type": "str"},
        {"type": "int"},
    )
    nullability = one(result, AlterNullability)
    assert nullability.name == "height"
    assert nullability.nullable is False
    assert nullability.safety == "additive"


@no_type_check
def test_a_validator_or_a_docstring_is_not_a_change():
    def before():
        class Person(Entity):
            age: int

    def after():
        class Person(Entity):
            """A person"""

            age: Annotated[int, Ge(0)]

    assert changes(before, after).changes == []


@no_type_check
def test_a_literal_that_becomes_an_annotated_value_and_back():
    def plain():
        class Person(Entity):
            name: str

    def annotated():
        class WithCertainty[T](AnnotatedValue[T]):
            certainty: int

        class Person(Entity):
            name: WithCertainty[str]

    wrapped = changes(plain, annotated)
    assert one(wrapped, LiteralToAnnotatedValue).annotated_model == "WithCertainty"
    assert one(wrapped, LiteralToAnnotatedValue).name == "name"
    unwrapped = changes(annotated, plain)
    assert one(unwrapped, AnnotatedValueToLiteral).safety == "lossy"


@no_type_check
def test_a_field_that_changes_kind_is_left_to_a_person():
    def before():
        class Place(Entity):
            pass

        class Person(Entity):
            home: str

    def after():
        class Place(Entity):
            pass

        class Person(Entity):
            home: Place

    change = one(changes(before, after), ChangeFieldKind)
    assert (change.old, change.new) == ("literal", "relation")


@no_type_check
def test_the_type_of_an_annotated_value():
    def before():
        class WithCertainty[T](AnnotatedValue[T]):
            certainty: int

        class Person(Entity):
            name: WithCertainty[str]

    def after():
        class WithCertainty[T](AnnotatedValue[T]):
            certainty: int

        class Person(Entity):
            name: WithCertainty[int]

    change = one(changes(before, after), AlterAnnotatedValue)
    assert change.old_value_type == {"type": "str"}
    assert change.new_value_type == {"type": "int"}


# ---------------------------------------------------------------------------
# Renames are asked, never assumed
# ---------------------------------------------------------------------------


@no_type_check
def test_a_removed_and_an_added_field_is_a_question():
    def before():
        class Person(Entity):
            born: int

    def after():
        class Person(Entity):
            birth_year: int

    result = changes(before, after)
    # not assumed: it is a removal and an addition, and a question
    assert sorted(kinds(result)) == ["AddField", "RemoveField"]
    assert result.questions == [
        PossibleRename(what="field", scope="Person", old="born", new="birth_year")
    ]
    assert not result.is_final
    assert "Person" in result.questions[0].question()


@no_type_check
def test_a_field_of_another_type_is_not_asked_about():
    def before():
        class Person(Entity):
            born: int

    def after():
        class Person(Entity):
            nickname: str

    assert changes(before, after).questions == []


@no_type_check
def test_a_confirmed_rename_is_a_rename_and_not_a_removal():
    def before():
        class Person(Entity):
            born: int

    def after():
        class Person(Entity):
            birth_year: int

    question = changes(before, after).questions[0]
    result = changes(before, after, confirmed=[question])
    assert kinds(result) == ["RenameField"]
    renamed = one(result, RenameField)
    assert (renamed.model, renamed.old, renamed.new) == ("Person", "born", "birth_year")
    assert result.is_final


@no_type_check
def test_a_declined_rename_is_not_asked_again():
    def before():
        class Person(Entity):
            born: int

    def after():
        class Person(Entity):
            birth_year: int

    question = changes(before, after).questions[0]
    result = changes(before, after, declined=[question])
    assert sorted(kinds(result)) == ["AddField", "RemoveField"]
    assert result.is_final


@no_type_check
def test_a_renamed_field_that_also_changed_is_not_suggested_but_can_be_confirmed():
    def before():
        class Person(Entity):
            born: str

    def after():
        class Person(Entity):
            birth_year: int

    result = changes(before, after)
    # (a different type: not alike enough to ask)
    assert result.questions == []
    assert sorted(kinds(result)) == ["AddField", "RemoveField"]

    # ... but a person who says it is a rename (by name) gets the rename, and the retyping
    by_hand = PossibleRename(what="field", scope="Person", old="born", new="birth_year")
    result = changes(before, after, confirmed=[by_hand])
    assert sorted(kinds(result)) == ["AlterLiteralType", "RenameField"]
    retyped = one(result, AlterLiteralType)
    assert retyped.name == "birth_year"
    assert (retyped.old, retyped.new) == ({"type": "str"}, {"type": "int"})


@no_type_check
def test_a_renamed_relation_keeps_its_reverse_edge_name_in_step():
    def before():
        class Place(Entity):
            pass

        class Person(Entity):
            home: Place

    def after():
        class Place(Entity):
            pass

        class Person(Entity):
            residence: Place

    question = changes(before, after).questions[0]
    result = changes(before, after, confirmed=[question])
    # (`home_reverse` became `residence_reverse` with it: that is part of the rename)
    assert kinds(result) == ["RenameField"]


@no_type_check
def test_a_renamed_model():
    def before():
        class Human(Entity):
            name: str
            born: int

        class Statement(Document):
            about: Human

    def after():
        class Person(Entity):
            name: str
            born: int

        class Statement(Document):
            about: Person

    first = changes(before, after)
    assert [(q.what, q.old, q.new) for q in first.questions] == [
        ("model", "Human", "Person")
    ]

    result = changes(before, after, confirmed=first.questions)
    # the relation to it is the same relation, to the model under its new name
    assert kinds(result) == ["RenameModel"]
    renamed = one(result, RenameModel)
    assert (renamed.old, renamed.new) == ("Human", "Person")


@no_type_check
def test_models_that_are_not_alike_are_not_asked_about():
    def before():
        class Human(Entity):
            name: str

    def after():
        class Place(Entity):
            latitude: float

    assert changes(before, after).questions == []


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------


@no_type_check
def test_what_a_relation_can_be_to_widens_and_narrows():
    def before():
        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            about: Person

    def widened():
        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            about: Person | Group

    wide = one(changes(before, widened), AlterRelationTarget)
    assert wide.added == ["entity:Group"]
    assert wide.removed == []
    assert wide.safety == "safe"

    narrow = one(changes(widened, before), AlterRelationTarget)
    assert narrow.removed == ["entity:Group"]
    assert narrow.safety == "lossy"


@no_type_check
def test_cardinality_and_the_reverse_name():
    def before():
        class Person(Entity):
            pass

        class Statement(Document):
            about: Person

    def after():
        class Person(Entity):
            pass

        class Statement(Document):
            about: Annotated[list[Person], RelationConfig(reverse_name="is_subject_of")]

    result = changes(before, after)
    assert one(result, AlterCardinality).many is True
    assert one(result, AlterCardinality).safety == "safe"
    reverse = one(result, AlterReverseName)
    assert (reverse.old, reverse.new) == ("about_reverse", "is_subject_of")
    assert one(changes(after, before), AlterCardinality).safety == "lossy"


@no_type_check
def test_properties_on_an_edge():
    def before():
        class Person(Entity):
            pass

        class Statement(Document):
            about: Person

    def after():
        class Certainty(EdgeModel):
            level: int

        class Person(Entity):
            pass

        class Statement(Document):
            about: ViaEdge[Person, Certainty]

    result = changes(before, after)
    change = one(result, AlterEdgeModel)
    assert (change.old, change.new) == ([], ["Certainty"])
    assert change.safety == "additive"
    assert one(result, CreateModel).model == "Certainty"


@no_type_check
def test_narrowing_a_parent_field_is_a_change_of_the_edges_written():
    def before():
        class Person(Entity):
            pass

        class Statement(Document):
            involves: list[Person]

        class Action(Statement):
            carried_out_by: Person

    def after():
        class Person(Entity):
            pass

        class Statement(Document):
            involves: list[Person]

        class Action(Statement):
            carried_out_by: Annotated[
                Person,
                RelationConfig(
                    subclasses_parent_fields=[
                        FieldSubclassing("involves", field_on_model=Statement)
                    ]
                ),
            ]

    change = one(changes(before, after), AlterParentFields)
    assert (change.model, change.name) == ("Action", "carried_out_by")
    assert change.added == ["involves"]
    assert change.safety == "additive"


# ---------------------------------------------------------------------------
# Wrapping a relation in a node
# ---------------------------------------------------------------------------


@no_type_check
def test_a_relation_wrapped_in_a_reified_relation():
    """`person: Person` becomes `person: IdentifiedAs[Person]`: a node is inserted on each
    edge, and not the field removed and added"""

    def before():
        class Person(Entity):
            pass

        class Statement(Document):
            person: Person

    def after():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]

    result = changes(before, after)
    assert kinds(result) == ["CreateModel", "WrapRelation"]
    assert one(result, CreateModel).model == "IdentifiedAs"
    assert one(result, CreateModel).model_kind == "ReifiedRelation"
    wrap = one(result, WrapRelation)
    assert (wrap.model, wrap.name) == ("Statement", "person")
    assert (wrap.wrapper, wrap.wrapper_kind) == ("IdentifiedAs", "reifiedRelation")
    assert wrap.safety == "transforming"
    assert result.is_final

    # ... and back: the node (and what it holds) is lost
    unwrapped = changes(after, before)
    assert kinds(unwrapped) == ["UnwrapRelation", "DeleteModel"]
    assert one(unwrapped, UnwrapRelation).safety == "lossy"


@no_type_check
def test_a_wrapped_relation_in_a_subclass_and_a_union():
    def before():
        class Person(Entity):
            pass

        class Student(Person):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            person: Person | Group

    def after():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Student(Person):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person | Group]

    result = changes(before, after)
    assert kinds(result) == ["CreateModel", "WrapRelation"]


@no_type_check
def test_wrapping_that_also_widens():
    def before():
        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            person: Person

    def after():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Group(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person | Group]

    result = changes(before, after)
    assert "WrapRelation" in kinds(result)
    target = one(result, AlterRelationTarget)
    assert target.added == ["Group"]
    assert "RemoveField" not in kinds(result)


@no_type_check
def test_a_relation_wrapped_in_a_semantic_space():
    def before():
        class Action(Document):
            pass

        class Factoid(Document):
            has_statement: Action

    def after():
        class Negative[T](SemanticSpace[T]):
            pass

        class Action(Document):
            pass

        class Factoid(Document):
            has_statement: Negative[Action]

    wrap = one(changes(before, after), WrapRelation)
    assert (wrap.wrapper, wrap.wrapper_kind) == ("Negative", "semanticSpace")


@no_type_check
def test_adding_a_wrapped_alternative_is_only_a_new_option():
    """`Statement` becomes `Statement | Negative[Statement]`: the old edges are as they were"""

    def before():
        class Statement(Document):
            pass

        class Factoid(Document):
            has_statement: list[Statement]

    def after():
        class Negative[T](SemanticSpace[T]):
            pass

        class Statement(Document):
            pass

        class Factoid(Document):
            has_statement: list[Statement | Negative[Statement]]

    result = changes(before, after)
    assert "WrapRelation" not in kinds(result)
    target = one(result, AlterRelationTarget)
    assert target.added == ["semanticSpace:Negative[T=document:Statement]"]
    assert target.removed == []


# ---------------------------------------------------------------------------
# One wrapper for another, and literals that become an embedded object
# ---------------------------------------------------------------------------


@no_type_check
def test_a_relation_that_changes_its_wrapper():
    from pangloss_models.meta_kit.migrations.changes import ChangeWrapper

    def before():
        class IdentifiedAs[T](ReifiedRelation[T]):
            certainty: int

        class Person(Entity):
            pass

        class Statement(Document):
            person: IdentifiedAs[Person]

    def after():
        class ProxyFor[T](ReifiedRelation[T]):
            certainty: int
            note: str | None

        class Person(Entity):
            pass

        class Statement(Document):
            person: ProxyFor[Person]

    result = changes(before, after)
    change = one(result, ChangeWrapper)
    assert (change.old_wrapper, change.new_wrapper) == ("IdentifiedAs", "ProxyFor")
    assert change.wrapper_kind == "reifiedRelation"
    assert "RemoveField" not in kinds(result)


@no_type_check
def test_literals_that_become_an_embedded_object_and_back():
    from pangloss_models.meta_kit.migrations.changes import (
        EmbeddedToLiterals,
        LiteralsToEmbedded,
    )

    def literals():
        class Statement(Document):
            when: str
            precision: int
            text: str

    def embedded():
        class Date(Embedded):
            when: str
            precision: int

        class Statement(Document):
            date: Date
            text: str

    wrapped = changes(literals, embedded)
    change = one(wrapped, LiteralsToEmbedded)
    assert (change.model, change.name, change.embedded_model) == (
        "Statement",
        "date",
        "Date",
    )
    assert change.fields == ["precision", "when"]
    # (the data is moved: not removed, and written again)
    assert "RemoveField" not in kinds(wrapped) and "AddField" not in kinds(wrapped)

    back = changes(embedded, literals)
    unwrapped = one(back, EmbeddedToLiterals)
    assert unwrapped.fields == ["precision", "when"]
    assert unwrapped.safety == "lossy"
    assert "RemoveField" not in kinds(back)
