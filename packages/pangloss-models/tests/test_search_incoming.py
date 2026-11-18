"""`$incoming` in a search pattern: an entity found by what refers to it, checked against the models"""

import pytest
from pangloss_models import (
    Document,
    Entity,
    Match,
    PanglossSearchError,
    ReifiedRelation,
    initialise,
)
from pangloss_models.search import (
    MAX_PATTERNS,
    CheckedCondition,
    CheckedIncoming,
    CheckedPattern,
    SearchKey,
    check_match,
)


def models():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Birth(Statement):
        person: Person
        place: Place | None = None

    class Naming(Statement):
        named: Identification[Person]

    class Letter(Document):
        title: str
        sender: Person
        recipient: Identification[Person]
        sent_from: Place | None = None

    initialise()
    return locals()


def check(model, incoming):
    return check_match(model, Match.model_validate({"where": {"$incoming": incoming}}))


def test_what_refers_to_an_entity_by_any_of_its_relations_that_can():
    m = models()
    assert check(m["Person"], {"type": "Letter"}) == [
        CheckedCondition(
            SearchKey.INCOMING,
            "incoming",
            "match",
            CheckedIncoming(CheckedPattern(m["Letter"], []), ("recipient", "sender")),
            True,  # (the recipient is reached through a reified relation)
        )
    ]
    # a place is pointed at only by sent_from, and not through a wrapper
    [place] = check(m["Place"], {"type": "Letter"})
    assert place.value.fields == ("sent_from",)
    assert place.wrapped is False


def test_by_one_relation_and_with_a_pattern_of_what_refers():
    m = models()
    [sender] = check(
        m["Person"],
        {"type": "Letter", "field": "sender", "where": {"title": {"eq": "x"}}},
    )
    assert sender.value == CheckedIncoming(
        CheckedPattern(m["Letter"], [CheckedCondition("title", "text", "eq", "x")]),
        ("sender",),
    )
    assert sender.wrapped is False
    [recipient] = check(m["Person"], {"type": "Letter", "field": "recipient"})
    assert recipient.wrapped is True


def test_an_abstract_class_refers_by_the_relations_of_its_kinds():
    m = models()
    [found] = check(m["Person"], {"type": "Statement"})
    assert found.value.fields == ("named", "person")
    assert found.value.pattern.model is m["Statement"]
    assert found.wrapped is True


def test_a_wrapper_on_the_way_may_be_named():
    m = models()
    [found] = check(
        m["Person"],
        {"type": "Letter", "field": "recipient", "through": ["Identification"]},
    )
    assert found.through == ("Identification",)
    with pytest.raises(PanglossSearchError, match="does not pass through"):
        check(
            m["Person"],
            {"type": "Letter", "field": "sender", "through": ["Identification"]},
        )


@pytest.mark.parametrize(
    "searched, incoming, message",
    [
        ("Letter", {"type": "Letter"}, r"^\$incoming: only an entity is referred to$"),
        ("Person", {"type": "Nothing"}, r"^\$incoming: "),
        (
            "Person",
            {"type": "Letter", "field": "sent_from"},
            r"^\$incoming: Letter has no relation 'sent_from' that can point at a Person "
            r"\(it has recipient, sender\)$",
        ),
        (
            "Person",
            {"type": "Letter", "field": "title"},
            r"^\$incoming: Letter has no relation 'title'",
        ),
        (
            "Place",
            {"type": "Naming"},
            r"^\$incoming: Naming has no relation that can point at a Place$",
        ),
        (
            "Person",
            {"type": "Letter", "where": {"nope": {"eq": 1}}},
            r"^\$incoming\.nope",
        ),
    ],
)
def test_what_is_refused(searched, incoming, message):
    m = models()
    with pytest.raises(PanglossSearchError, match=message):
        check(m[searched], incoming)


def test_patterns_for_what_refers_count_towards_the_limit():
    m = models()
    one = {"type": "Letter", "field": "sender"}
    assert len(check(m["Person"], [one] * MAX_PATTERNS)) == MAX_PATTERNS
    with pytest.raises(
        PanglossSearchError,
        match=f"More than {MAX_PATTERNS} patterns for what a relation points at",
    ):
        check(m["Person"], [one] * (MAX_PATTERNS + 1))
