"""How a justification holds (`pangloss_derived.status`): the status of a part from what the walk says of it, the
parts put together, what of the spaces a rule's hash has, a rule's own statuses (`.when(..., status=[...])`) and a
fact's status summed up from its justifications'. The whole of it on a database: `live/test_derived_status_live.py`."""

import typing
from typing import Annotated, no_type_check

import pytest
from pangloss_derived import DerivedEdge, DerivedMeta, Object, Subject, Var, rule
from pangloss_derived.registry import DerivedRegistry, PanglossDerivedError
from pangloss_derived.status import (
    DERIVES,
    STATUSES,
    SUMMED,
    holds,
    ordered,
    standing,
    status_of,
    status_of_row,
    summed,
    summed_standing,
    together,
    under_grounds,
    walked_nodes,
)
from pangloss_derived.views import Status, Summed
from pangloss_models import (
    Document,
    Entity,
    Ground,
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
def declare(
    *,
    logical: bool = True,
    allow: bool = False,
    document_free: bool = True,
    status: typing.Any = None,
    ground: typing.Any = None,
):
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
        if ground is not None:
            _meta = Document.Meta(ground=ground)
        statements: list[
            Purchase | Reported[Purchase] | Not[Purchase] | Ordered[Purchase]
        ]

    class BoughtFrom(DerivedEdge):
        buyer: Annotated[Person, Subject()]
        seller: Annotated[Person, Object()]

    @rule
    def bought_from(a: Var[Person], b: Var[Person]):
        return BoughtFrom.Derive(buyer=a, seller=b).when(
            Purchase.Where(buyer=a, seller=b),
            **({"allow": [Not]} if allow else {}),
            **({"status": status} if status is not None else {}),
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
    return {"walks": [["p", path, "Purchase"]], "ways": ways}


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


@pytest.mark.parametrize(
    "statuses, fact",
    [
        (["asserted"], "asserted"),
        (["asserted", "asserted", "reported"], "asserted"),
        (["asserted", "nothing"], "asserted"),
        (["asserted", "denied"], "contested"),
        (["reported", "asserted", "reported_not"], "contested"),
        (["prescribed_not", "asserted"], "contested"),
        (["reported", "prescribed"], "reported"),
        (["reported", "denied"], "reported"),
        (["prescribed", "prescribed_not"], "prescribed"),
        (["denied"], "denied"),
        (["reported_not", "prescribed_not", "denied"], "denied"),
        (["denied", "nothing"], "nothing"),
        (["nothing"], "nothing"),
        ([], "nothing"),
    ],
)
def test_a_fact_is_summed_up_from_its_justifications(statuses, fact):
    assert summed(statuses) == fact
    assert fact in SUMMED


def test_the_statuses_of_a_fact_are_each_once_in_the_order_of_the_names():
    assert ordered(["nothing", "asserted", "denied", "asserted"]) == [
        "asserted",
        "denied",
        "nothing",
    ]


def test_the_views_name_the_same_statuses():
    assert typing.get_args(Status) == STATUSES
    assert typing.get_args(Summed) == SUMMED


def test_a_rule_takes_the_statuses_it_names():
    checked = declare(status=["denied"])
    assert checked.statuses == {"denied"}
    ModelRegistry._reset()
    assert declare(status=["prescribed_not", "denied"]).statuses == {
        "prescribed_not",
        "denied",
    }
    ModelRegistry._reset()
    plain = declare()
    assert plain.statuses == DERIVES
    # (what it takes is in its hash: its facts are due again when it changes)
    assert plain.hash != checked.hash


@pytest.mark.parametrize(
    "status, says",
    [
        (
            ["deneid"],
            "Rule bought_from: status=['deneid']: 'deneid' is not a status of a justification (they are: asserted, "
            "reported, prescribed, denied, reported_not, prescribed_not, nothing). Did you mean 'denied'?",
        ),
        (
            ["contested"],
            "'contested' is not a status of a justification",
        ),
        ([], "status=[] takes no justification at all"),
        ("denied", "status='denied': status takes a list"),
    ],
)
def test_a_status_that_is_none_is_refused(status, says):
    with pytest.raises(PanglossDerivedError) as error:
        declare(status=status)
    assert says in str(error.value)


def test_a_document_rule_that_names_its_statuses_takes_them_through_any_space():
    from types import SimpleNamespace as ns

    from pangloss_derived.status import DERIVES, derives

    in_not = {
        "walks": [["p", [FACTOID, entry("space", "Not", "n")], "Purchase"]],
        "ways": [],
    }
    facts = {
        "Not": {
            "veridical": -1,
            "fit": "describes",
            "logical": {"not": True},
            "degree": None,
        }
    }
    node = ns(kind="document")

    def a_rule(statuses, forced=frozenset()):
        return ns(
            document=True,
            statuses=frozenset(statuses),
            forced=forced,
            transparent=frozenset(),
            spaces=facts,
            grounds={},
            nodes={"p": node},
            patterns=["p"],
            edges=[],
        )

    # (by default: not through a space it does not allow, whatever the status)
    assert not derives(a_rule(DERIVES), in_not, "reported")
    assert derives(a_rule(DERIVES, forced=frozenset({"Not"})), in_not, "reported")
    assert derives(a_rule(DERIVES), in_not, "asserted")
    # (it asked for what is denied: taken, and nothing else)
    assert derives(a_rule({"denied"}), in_not, "denied")
    assert not derives(a_rule({"denied"}), in_not, "asserted")


# --- what the second reading of step 4.1 found -------------------------------------------------------------------


def a_rule(nodes: dict, edges: list, spaces: dict, patterns: list[str]):
    """A rule as `parts_of` reads it, by hand: its nodes by kind, its relations, what the spaces say"""
    from types import SimpleNamespace as ns

    return ns(
        nodes={
            name: ns(
                kind=kind, model=type(name.title(), (), {"__metatype__": "Document"})
            )
            for name, kind in nodes.items()
        },
        edges=[ns(source=s, target=t, field=f) for s, f, t in edges],
        patterns=patterns,
        spaces=spaces,
        grounds={},
        transparent=frozenset(),
        forced=frozenset(),
        statuses=DERIVES,
        document=False,
    )


PLAIN = {"veridical": 0, "fit": "describes", "logical": None, "degree": None}
NOT = {"veridical": -1, "fit": "describes", "logical": {"not": True}, "degree": None}
KNOWN = {"veridical": 1, "fit": "describes", "logical": None, "degree": None}
SAID = {"Uncertain": PLAIN, "Not": NOT, "Known": KNOWN}


@pytest.mark.parametrize(
    "space, status",
    [("Uncertain", "reported"), ("Not", "denied"), ("Known", "asserted")],
)
def test_a_nested_pattern_is_a_part_by_its_own_path(space, status):
    """`Order.Where(content=Gift.Where(giver=a, receiver=b))`: the gift is no pattern of the body, and its path has
    the space it is ordered in"""
    checked = a_rule(
        {"order": "document", "gift": "document", "a": "entity", "b": "entity"},
        [
            ("order", "content", "gift"),
            ("gift", "giver", "a"),
            ("gift", "receiver", "b"),
        ],
        SAID,
        patterns=["order"],
    )
    held = entry("document", "Order", "o", "content")
    found = {
        "walks": [
            ["o", [FACTOID], "Order"],
            ["g", [FACTOID, held, entry("space", space, "s")], "Gift"],
        ],
        "ways": [[[space, "s"]], [], []],
    }
    assert status_of_row(checked, found) == status


@pytest.mark.parametrize(
    "space, status",
    [("Uncertain", "reported"), ("Not", "denied"), ("Known", "asserted")],
)
def test_a_relation_that_starts_at_an_entity_is_its_wrappers_alone(space, status):
    """`Friend(Entity).knows: Person | Not[Person]`: an entity has no path"""
    checked = a_rule(
        {"a": "entity", "b": "entity"}, [("a", "knows", "b")], SAID, patterns=["a"]
    )
    assert status_of_row(checked, {"walks": [], "ways": [[[space, "s"]]]}) == status


def test_a_wrapper_that_is_no_space_counts_as_a_statement_on_a_relation():
    checked = a_rule(
        {"p": "document", "a": "entity"}, [("p", "buyer", "a")], SAID, patterns=["p"]
    )

    def through(*wrappers):
        return {
            "walks": [["p", [FACTOID], "P"]],
            "ways": [[[kind, f"w{i}"] for i, kind in enumerate(wrappers)]],
        }

    assert status_of_row(checked, through("InRole")) == "asserted"
    assert status_of_row(checked, through("InRole", "Not")) == "denied"
    # (it is not that he was the one in that role: nothing is said of him)
    assert status_of_row(checked, through("Not", "InRole")) == "nothing"
    # (two that are not next to each other do not cancel)
    assert status_of_row(checked, through("Not", "InRole", "Not")) == "nothing"
    assert status_of_row(checked, through("Not", "Not")) == "asserted"


def test_a_relation_whose_wrappers_assert_leaves_its_statement_s_status_as_it_is():
    """`Not[Purchase(buyer=Known[x])]` is denied as `Not[Purchase(buyer=x)]` is"""
    checked = a_rule(
        {"p": "document", "a": "entity"}, [("p", "buyer", "a")], SAID, patterns=["p"]
    )
    denied = [FACTOID, entry("space", "Not", "n")]
    for wrappers in (
        [],
        [["Known", "k"]],
        [["InRole", "r"]],
        [["InRole", "r"], ["Known", "k"]],
    ):
        found = {"walks": [["p", denied, "P"]], "ways": [wrappers]}
        assert status_of_row(checked, found) == "denied", wrappers


# --- the ground and the standing (step 4.5) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "parts, said",
    [
        (["record", "record"], "record"),
        (["record", "claim", "record"], "claim"),
        (["claim"], "claim"),
        # (a relation from an entity whose wrappers are a part of their own: no ground, and the entity's record)
        ([None, "record"], "record"),
        ([None, None], "claim"),
        ([], "claim"),
    ],
)
def test_the_standing_of_a_justification_is_the_record_only_where_no_part_is_a_claim(
    parts, said
):
    assert standing(parts) == said


@pytest.mark.parametrize(
    "standings, said",
    [
        (["record"], "record"),
        (["record", "record"], "record"),
        (["record", "claim"], "claim"),
        (["claim"], "claim"),
        ([], "claim"),
    ],
)
def test_a_fact_is_of_the_record_only_where_every_justification_is(standings, said):
    assert summed_standing(standings) == said


def test_a_change_of_a_ground_is_in_the_hash_of_a_rule():
    plain = declare()
    assert plain.grounds["Factoid"]["standing"] == "claim"
    ModelRegistry._reset()
    assert declare().hash == plain.hash
    ModelRegistry._reset()
    by_rumour = declare(ground=Ground(veridical=0, degree="possible"))
    assert by_rumour.grounds["Factoid"]["veridical"] == 0
    assert by_rumour.hash != plain.hash
    ModelRegistry._reset()
    # (the ground as it holds is what counts: a ground written that is the default changes nothing)
    assert declare(ground=Ground()).hash == plain.hash


def test_a_part_is_walked_from_the_ground_of_its_head():
    rumour = declare(ground=Ground(veridical=0, degree="possible"))
    assert status_of_row(rumour, row(rumour, [FACTOID])) == "reported"
    in_not = [FACTOID, entry("space", "Not", "n")]
    assert status_of_row(rumour, row(rumour, in_not)) == "reported_not"
    ModelRegistry._reset()
    # (an order: what it holds is neither asserted nor denied, and prescribed. One that asserts what it prescribes
    # is asserted, as a space that does is)
    ordering = declare(ground=Ground(veridical=0, fit="prescribes"))
    assert status_of_row(ordering, row(ordering, [FACTOID])) == "prescribed"
    ModelRegistry._reset()
    asserting = declare(ground=Ground(fit="prescribes"))
    assert status_of_row(asserting, row(asserting, [FACTOID])) == "asserted"
    ModelRegistry._reset()
    plain = declare()
    assert status_of_row(plain, row(plain, [FACTOID])) == "asserted"


def test_a_justification_has_the_standing_of_its_parts_and_of_the_entities_it_starts_at():
    checked = declare()
    found = {**row(checked, [FACTOID]), "starts": [None for _ in checked.edges]}
    assert holds(checked, found) == ("asserted", "claim")
    ModelRegistry._reset()
    record = declare(ground=Ground(standing="record"))
    found = {**row(record, [FACTOID]), "starts": [None for _ in record.edges]}
    assert holds(record, found) == ("asserted", "record")


def test_a_head_that_is_matched_itself_is_walked_from_the_ground_of_its_class_as_stored():
    """A rule over a head document (its path is empty): the class the node is stored as, which may be a subclass with
    a ground of its own, not the pattern's"""
    checked = a_rule(
        {"p": "document", "a": "entity"}, [("p", "buyer", "a")], SAID, ["p"]
    )
    checked.grounds = {
        "Charter": {
            "veridical": 1,
            "fit": "describes",
            "degree": None,
            "by": None,
            "standing": "claim",
        },
        "Rumour": {
            "veridical": 0,
            "fit": "describes",
            "degree": None,
            "by": None,
            "standing": "claim",
        },
    }

    def found(kind):
        return {"walks": [["p", [], kind]], "ways": [[]], "starts": [None]}

    assert holds(checked, found("Charter")) == ("asserted", "claim")
    assert holds(checked, found("Rumour")) == ("reported", "claim")


def _ground(veridical=1, fit="describes", standing="claim"):
    return {
        "veridical": veridical,
        "fit": fit,
        "degree": None,
        "by": None,
        "standing": standing,
    }


def test_what_rests_on_a_ground_that_does_not_assert_is_qualified_by_its_head_class():
    """A statement directly in a rumour passes through no space: the rumour's class is what qualifies it, and a rule
    that derives a document makes none of it (no rule can allow a ground)"""
    from pangloss_derived.status import derives

    checked = a_rule(
        {"p": "document", "a": "entity"}, [("p", "buyer", "a")], SAID, ["p"]
    )
    checked.grounds = {
        "Charter": _ground(),
        "Rumour": _ground(veridical=0),
        "RuleBook": _ground(fit="prescribes"),
    }

    def held_in(head):
        path = [{"kind": "document", "type": head, "id": "h", "field": "statements"}]
        return {"walks": [["p", path, "P"]], "ways": [[]], "starts": [None]}

    assert under_grounds(checked, held_in("Charter")) == []
    assert under_grounds(checked, held_in("Rumour")) == ["Rumour"]
    assert under_grounds(checked, held_in("RuleBook")) == ["RuleBook"]
    # (a head matched itself, by its class as stored)
    itself = {"walks": [["p", [], "Rumour"]], "ways": [[]], "starts": [None]}
    assert under_grounds(checked, itself) == ["Rumour"]

    assert holds(checked, held_in("Rumour")) == ("reported", "claim")
    assert derives(checked, held_in("Rumour"), "reported")
    checked.document = True
    assert not derives(checked, held_in("Rumour"), "reported")
    assert derives(checked, held_in("Charter"), "asserted")
    # (a rule that names its statuses has said what its documents are made from)
    checked.statuses = frozenset({"reported"})
    assert derives(checked, held_in("Rumour"), "reported")


def test_a_rule_over_entities_alone_with_no_relation_has_the_standing_of_their_classes():
    """Two people born in one year: nothing is walked and no relation followed. It rests on what the entities hold
    themselves"""
    checked = a_rule({"person": "entity", "legend": "entity"}, [], SAID, ["person"])
    checked.grounds = {"Person": _ground(standing="record")}
    nothing = {"walks": [], "ways": [], "starts": []}
    assert holds(checked, nothing) == ("asserted", "record")
    checked.grounds["Legend"] = _ground()
    assert holds(checked, nothing) == ("asserted", "claim")


def test_a_relation_that_starts_at_an_entity_has_the_standing_of_the_entity_s_class():
    """`Place.within`, an entity's own relation: of the record, whether or not its wrappers are a part of their own"""
    checked = a_rule(
        {"a": "entity", "b": "entity", "c": "entity"},
        [("a", "within", "b"), ("b", "within", "c")],
        SAID,
        patterns=["a"],
    )
    record = {
        "veridical": 1,
        "fit": "describes",
        "degree": None,
        "by": None,
        "standing": "record",
    }
    checked.grounds = {"Place": record, "Legend": {**record, "standing": "claim"}}
    plain = {"walks": [], "ways": [[], []], "starts": ["Place", "Place"]}
    assert holds(checked, plain) == ("asserted", "record")
    reported = {**plain, "ways": [[["Uncertain", "u"]], []]}
    assert holds(checked, reported) == ("reported", "record")
    # (an entity of a class whose ground is a claim)
    assert holds(checked, {**plain, "starts": ["Place", "Legend"]}) == (
        "asserted",
        "claim",
    )
