"""What refers to an entity, in its `HeadView`: a document whose field takes the entity directly or through a wrapper
is read as what it is, whichever it is (the members of the union are tried in order, those through a wrapper first)"""

from pangloss_models import Document, Entity, ReifiedRelation, initialise

PERSON = "01a1c564-7def-70f0-bd21-410a35c82ab1"
OTHER = "01a1c564-7def-70f0-bd21-410a35c82ab2"
SIGHTING = "01a1c564-7def-70f0-bd21-410a35c82ab3"
WRAPPER = "01a1c564-7def-70f0-bd21-410a35c82ab4"

META = {
    "is_head_node": True,
    "head_node_id": SIGHTING,
    "head_node_type": "Sighting",
    "semantic_spaces": [],
    "created_by": [{"username": "ann", "kind": "user"}],
    "created_when": "2026-11-19T10:00:00Z",
    "updated_by": None,
    "updated_when": None,
}


def models():
    class Person(Entity):
        pass

    class Described[T](ReifiedRelation[T]):
        wording: str | None = None

    class Sighting(Document):
        seen: list[Person | Described[Person]]

    initialise()
    return Person


def read(Person, *referring: dict):
    return Person.HeadView.model_validate(
        {
            "id": PERSON,
            "type": "Person",
            "label": "Marie",
            "meta": {**META, "is_head_node": True, "head_node_id": PERSON},
            "seen_reverse": list(referring),
        }
    ).seen_reverse


def test_a_document_that_refers_through_a_wrapper_keeps_the_wrapper_however_little_it_holds():
    Person = models()
    (through,) = read(
        Person,
        {
            "id": SIGHTING,
            "type": "Sighting",
            "label": "Seen",
            "meta": META,
            "seen": [
                {
                    "id": WRAPPER,
                    "type": "Described",
                    "target": [{"id": PERSON, "type": "Person", "label": "Marie"}],
                }
            ],
        },
    )
    # (not the plain reference, which would leave the wrapper out)
    assert type(through).__name__ == "SightingView.from.Person.seen_reverse"
    (wrapper,) = through.seen
    assert wrapper.type == "Described" and str(wrapper.target[0].id) == PERSON


def test_one_that_refers_directly_is_a_plain_reference():
    Person = models()
    (direct,) = read(
        Person, {"id": SIGHTING, "type": "Sighting", "label": "Seen", "meta": META}
    )
    assert type(direct).__name__ == "SightingReferenceView"
    assert direct.label == "Seen"
