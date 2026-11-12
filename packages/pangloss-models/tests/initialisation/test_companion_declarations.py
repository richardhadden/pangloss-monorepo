"""A companion document declared on an entity (implementation_docs/companion-documents.md): its names are checked at
`initialise()`, as a binding's are, since a misspelt one would never be offered"""

from typing import no_type_check

import pytest
from pangloss_models import (
    Companion,
    CompanionPart,
    CopyFromOuter,
    Document,
    Entity,
    PanglossModelError,
    ReifiedRelation,
    SemanticSpace,
    Standalone,
    Trait,
    Within,
    initialise,
)
from pangloss_models.companions import companion_named, companions_of


def naming_and_gender(**changes) -> Companion:
    given = dict(
        name="naming_and_gender",
        document="Factoid",
        field="statements",
        parts=[
            CompanionPart(type="Naming", entity_field="named"),
            CompanionPart(type="Gendering", entity_field="gendered"),
        ],
        copies=[CopyFromOuter(field="source")],
        offered=[Within(heads=["Factoid"]), Standalone()],
    )
    given.update(changes)
    return Companion(**given)


@no_type_check
def declare(*companions: Companion, person_meta: dict | None = None):
    """A factoid model: a person with the companions given; factoids of statements, with a source at a page"""

    class Agent(Trait):
        pass

    class Person(Entity, Agent):
        _meta = Entity.Meta(companions=list(companions), **(person_meta or {}))

    class Group(Entity, Agent):
        pass

    class Source(Entity):
        pass

    class AtPage[T](ReifiedRelation[T]):
        page: str

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)
        involves: list[Agent]

    class Naming(Statement):
        named: Person
        first_name: str | None = None

    class Gendering(Statement):
        gendered: Person
        gender: str | None = None

    class Membership(Statement):
        group: Group

    class Negative[T](SemanticSpace[T]):
        pass

    class Factoid(Document):
        source: AtPage[Source]
        statements: list[Statement | Negative[Statement]]
        about: Person | None = None

    class Letter(Document):
        source: AtPage[Source]
        sender: Person

    class Note(Document):
        source: str
        concerns: Person

    class Hidden(Document):
        _meta = Document.Meta(create_directly=False)
        concerns: Person

    return {
        cls.__name__: cls
        for cls in (
            Person,
            Group,
            Source,
            Statement,
            Naming,
            Gendering,
            Factoid,
            Letter,
            Note,
            Hidden,
        )
    }


def refusal(*companions: Companion) -> PanglossModelError:
    declare(*companions)
    with pytest.raises(PanglossModelError) as error:
        initialise(bind_database=False)
    return error.value


def test_a_companion_whose_names_all_exist_is_accepted_and_kept_on_the_entity():
    models = declare(naming_and_gender())
    initialise(bind_database=False)

    (companion,) = companions_of(models["Person"])
    assert companion.document == "Factoid"
    assert companion.parts[0] == CompanionPart(type="Naming", entity_field="named")
    assert companion.slots == (("Naming", "named"), ("Gendering", "gendered"))
    assert companion_named(models["Person"], "naming_and_gender") is companion
    assert companion_named(models["Person"], "other") is None


def test_lists_given_to_a_companion_are_kept_as_tuples_so_it_can_be_hashed():
    companion = naming_and_gender()
    assert isinstance(companion.parts, tuple)
    assert isinstance(Within(heads=["Factoid"]).heads, tuple)
    assert hash(companion) == hash(naming_and_gender())


def test_a_companion_without_a_field_is_its_own_part():
    models = declare(
        Companion(
            name="note",
            document="Note",
            entity_field="concerns",
            offered=[Standalone()],
        )
    )
    initialise(bind_database=False)

    assert companions_of(models["Person"])[0].slots == ((None, "concerns"),)


def test_a_subclass_inherits_the_companions_and_may_have_none():
    models = declare(naming_and_gender())

    @no_type_check
    class Woman(models["Person"]):
        pass

    @no_type_check
    class Anonymous(models["Person"]):
        _meta = Entity.Meta(companions=[])

    initialise(bind_database=False)
    assert companions_of(Woman)[0].name == "naming_and_gender"
    assert companions_of(Anonymous) == ()


def test_a_document_that_is_not_a_model_is_refused_with_a_suggestion():
    error = refusal(naming_and_gender(document="Factiod"))
    assert "Person" in str(error)
    assert "Did you mean 'Factoid'?" in str(error)
    assert error.at_string.option == "document"
    assert error.at_string.value == "Factiod"


@pytest.mark.parametrize("document", ["Person", "Statement", "Hidden"])
def test_a_document_that_cannot_be_made_on_its_own_is_refused(document):
    error = refusal(
        naming_and_gender(
            document=document, field=None, parts=[], entity_field="named", copies=[]
        )
    )
    assert document in str(error)
    assert "made on its own" in str(error) or "not a document" in str(error)


def test_a_field_that_is_not_a_list_relation_of_the_document_is_refused():
    error = refusal(naming_and_gender(field="statments"))
    assert "Did you mean 'statements'?" in str(error)
    assert error.at_string.option == "field"

    error = refusal(naming_and_gender(field="about"))
    assert "list" in str(error)


def test_a_part_the_field_cannot_hold_is_refused():
    error = refusal(
        naming_and_gender(parts=[CompanionPart(type="Namign", entity_field="named")])
    )
    assert "Did you mean 'Naming'?" in str(error)
    assert error.at_string.option == "type"

    error = refusal(
        naming_and_gender(parts=[CompanionPart(type="Letter", entity_field="sender")])
    )
    assert "Factoid.statements" in str(error)
    assert "cannot hold" in str(error)


def test_a_part_type_given_twice_is_refused():
    error = refusal(
        naming_and_gender(
            parts=[
                CompanionPart(type="Naming", entity_field="named"),
                CompanionPart(type="Naming", entity_field="named"),
            ]
        )
    )
    assert "twice" in str(error)


def test_a_companion_with_a_field_needs_parts_and_one_without_needs_an_entity_field():
    assert "parts" in str(refusal(naming_and_gender(parts=[])))
    assert "entity_field" in str(
        refusal(naming_and_gender(field=None, parts=[], document="Note", copies=[]))
    )
    assert "entity_field" in str(refusal(naming_and_gender(entity_field="named")))


def test_an_entity_field_that_does_not_take_the_entity_is_refused():
    error = refusal(
        naming_and_gender(parts=[CompanionPart(type="Naming", entity_field="nmed")])
    )
    assert "Did you mean 'named'?" in str(error)
    assert error.at_string.option == "entity_field"

    error = refusal(
        naming_and_gender(
            parts=[CompanionPart(type="Membership", entity_field="group")]
        )
    )
    assert "Membership.group" in str(error)
    assert "Person" in str(error)


def test_an_entity_field_may_take_the_entity_through_a_trait():
    declare(
        naming_and_gender(parts=[CompanionPart(type="Naming", entity_field="involves")])
    )
    initialise(bind_database=False)


def test_a_copy_to_a_field_the_companion_does_not_have_is_refused():
    error = refusal(
        naming_and_gender(copies=[CopyFromOuter(field="source", to="sorce")])
    )
    assert "Did you mean 'source'?" in str(error)
    assert error.at_string.option == "to"


def test_a_copy_from_a_field_a_head_it_is_offered_within_does_not_have_is_refused():
    error = refusal(naming_and_gender(copies=[CopyFromOuter(field="sorce")]))
    assert "Did you mean 'source'?" in str(error)
    assert error.at_string.option == "field"


def test_a_copy_between_fields_of_different_types_is_refused():
    error = refusal(
        naming_and_gender(
            offered=[Within(heads=["Note"])],
            copies=[CopyFromOuter(field="source")],
        )
    )
    assert "Note.source" in str(error)
    assert "Factoid.source" in str(error)


def test_a_copy_from_a_relation_to_one_that_holds_the_same_types_is_accepted():
    declare(naming_and_gender(offered=[Within(heads=["Factoid", "Letter"])]))
    initialise(bind_database=False)


@pytest.mark.parametrize(
    "within, option, misspelt",
    [
        (Within(heads=["Factiod"]), "heads", "Factiod"),
        (Within(holders=["Statment"]), "holders", "Statment"),
        (Within(fields=["Statement.involve"]), "fields", "Statement.involve"),
        (Within(fields=["Statment.involves"]), "fields", "Statment.involves"),
    ],
)
def test_a_name_offered_within_that_is_not_a_model_or_field_is_refused(
    within, option, misspelt
):
    error = refusal(naming_and_gender(offered=[within], copies=[]))
    assert "Did you mean" in str(error)
    assert error.at_string.option == option
    assert error.at_string.value == misspelt


def test_a_field_offered_within_must_be_written_class_dot_field():
    error = refusal(naming_and_gender(offered=[Within(fields=["involves"])], copies=[]))
    assert "Class.field" in str(error)


def test_two_companions_of_one_name_are_refused():
    error = refusal(naming_and_gender(), naming_and_gender())
    assert "naming_and_gender" in str(error)
    assert "twice" in str(error)
