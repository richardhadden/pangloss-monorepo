"""How a justification holds (`pangloss_derived.status`): the status of a part from what the walk says of it, the
parts put together, and what of the spaces a rule's hash has. The whole of it on a database:
`live/test_derived_status_live.py`."""

from typing import Annotated, no_type_check

import pytest
from pangloss_derived import DerivedEdge, DerivedMeta, Object, Subject, Var, rule
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.status import (
    DERIVES,
    STATUSES,
    status_of,
    status_of_row,
    together,
    walked_nodes,
)
from pangloss_models import (
    Document,
    Entity,
    Modal,
    ModelRegistry,
    SemanticSpace,
    initialise,
)
from pangloss_models.spaces import Signature


def said(veridical, lean=None, fit="describes") -> Signature:
    return Signature(veridical, lean, None, fit, None, None, None)


@pytest.mark.parametrize(
    "signature, status",
    [
        (said(1), "asserted"),
        (said(1, fit="prescribes"), "asserted"),
        (said(-1), "denied"),
        (said(0, "for"), "reported"),
        (said(0, "against"), "reported_not"),
        (said(0, "for", "prescribes"), "prescribed"),
        (said(0, "against", "prescribes"), "prescribed_not"),
        (said(0, "neither"), "nothing"),
        (said(0, "neither", "prescribes"), "nothing"),
    ],
)
def test_the_status_of_a_part(signature, status):
    assert status_of(signature) == status
    assert status in STATUSES


@pytest.mark.parametrize(
    "parts, status",
    [
        ([], "asserted"),
        (["asserted", "asserted"], "asserted"),
        (["asserted", "denied"], "denied"),
        (["reported", "asserted"], "reported"),
        (["asserted", "prescribed_not"], "prescribed_not"),
        (["reported", "reported"], "reported"),
        (["reported", "prescribed"], "prescribed"),
        (["denied", "denied"], "nothing"),
        (["reported", "denied"], "nothing"),
        (["reported", "reported_not"], "nothing"),
        (["asserted", "nothing"], "nothing"),
    ],
)
def test_the_parts_put_together(parts, status):
    assert together(parts) == status


def test_a_rule_derives_from_what_is_asserted_reported_or_prescribed():
    assert DERIVES == {"asserted", "reported", "prescribed"}


@no_type_check
def declare(*, logical: bool = True, allow: bool = False, document_free: bool = True):
    class Reported[T](SemanticSpace[T]):
        pass

    class Not[T](SemanticSpace[T]):
        if logical:
            _meta = SemanticSpace.Meta(logical="not")

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), fit="prescribes"
        )

    class Disputed[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=-1, unary=True)
        _derived_meta = DerivedMeta(derivation="qualify")

    class Aside[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")
        _derived_meta = DerivedMeta(derivation="transparent")

    class Person(Entity):
        pass

    class Purchase(Document):
        buyer: Person | Not[Person]
        seller: Person

    class Factoid(Document):
        statements: list[
            Purchase | Reported[Purchase] | Not[Purchase] | Ordered[Purchase]
        ]

    class BoughtFrom(DerivedEdge):
        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    @rule
    def bought_from(a: Var[Person], b: Var[Person]):
        return BoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b), **({"allow": [Not]} if allow else {})
        )

    initialise()
    return DerivedRegistry.checked["bought_from"]


@pytest.fixture(autouse=True)
def fresh():
    ModelRegistry._reset()
    yield
    ModelRegistry._reset()


def entry(kind: str, type: str, id: str, field: str = "contents") -> dict:
    return {"kind": kind, "type": type, "id": id, "field": field}


FACTOID = entry("document", "Factoid", "f", "statements")


def row(checked, path, *, buyer_through=()):
    """A row of the rule's query: the one purchase at `path`, its buyer reached through the wrappers given"""
    assert len(walked_nodes(checked)) == 1
    ways = [
        [list(w) for w in buyer_through] if e.field == "buyer" else []
        for e in checked.edges
    ]
    return {"walks": [["p", path]], "ways": ways}


def test_the_status_of_a_row_is_the_walk_over_the_stored_path():
    checked = declare()
    assert status_of_row(checked, row(checked, [FACTOID])) == "asserted"
    in_not = [FACTOID, entry("space", "Not", "n")]
    assert status_of_row(checked, row(checked, in_not)) == "denied"
    ordered = [FACTOID, entry("space", "Ordered", "o")]
    assert status_of_row(checked, row(checked, ordered)) == "prescribed"
    assert (
        status_of_row(checked, row(checked, [*ordered, entry("space", "Not", "n")]))
        == "prescribed_not"
    )


def test_a_path_stored_as_json_text_is_read_as_the_list():
    import json

    checked = declare()
    path = json.dumps([FACTOID, entry("space", "Not", "n")])
    assert status_of_row(checked, row(checked, path)) == "denied"
    assert status_of_row(checked, row(checked, None)) == "asserted"


def test_a_space_on_a_relation_is_walked_from_the_statement_it_starts_at():
    checked = declare()
    through = [("Not", "n2")]
    assert (
        status_of_row(checked, row(checked, [FACTOID], buyer_through=through))
        == "denied"
    )
    reported = [FACTOID, entry("space", "Reported", "r")]
    assert (
        status_of_row(checked, row(checked, reported, buyer_through=through))
        == "reported_not"
    )
    # (the statement is between the two: they do not cancel)
    denied = [FACTOID, entry("space", "Not", "n")]
    assert (
        status_of_row(checked, row(checked, denied, buyer_through=through)) == "nothing"
    )


def test_what_a_wrapper_s_derived_meta_says_wins_over_the_walk():
    checked = declare()
    assert checked.forced == {"Disputed"}
    assert "Aside" in checked.transparent
    disputed = [FACTOID, entry("space", "Disputed", "d")]
    assert status_of_row(checked, row(checked, disputed)) == "reported"
    # (a transparent space is left out of the path: this "not" is not read)
    aside = [FACTOID, entry("space", "Aside", "a")]
    assert status_of_row(checked, row(checked, aside)) == "asserted"


def test_a_space_the_rule_allows_is_read_as_a_plain_one():
    checked = declare(allow=True)
    assert checked.forced == {"Disputed", "Not"}
    in_not = [FACTOID, entry("space", "Not", "n")]
    assert status_of_row(checked, row(checked, in_not)) == "reported"


def test_what_a_space_says_of_its_contents_is_in_the_hash_of_a_rule():
    with_not = declare()
    assert with_not.spaces["Not"]["logical"] == {"not": True}
    ModelRegistry._reset()
    without = declare(logical=False)
    assert without.spaces["Not"]["logical"] is None
    assert without.hash != with_not.hash
    ModelRegistry._reset()
    assert declare().hash == with_not.hash
