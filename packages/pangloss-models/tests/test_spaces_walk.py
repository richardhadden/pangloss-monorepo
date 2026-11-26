"""The walk (`pangloss_models.spaces`; implementation_docs/semantic-spaces.md): what a node's path says of it.

The cases are written here by hand, each with what the walk must give, and kept as data in `space_cases.json`, which
the interface's port of the walk passes too: `PANGLOSS_WRITE_SPACE_CASES=1` writes the file again."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, no_type_check
from uuid import uuid7

import pytest
from pydantic.alias_generators import to_camel
from pangloss_models import (
    Degree,
    DegreeStep,
    Document,
    Entity,
    Ground,
    Modal,
    SemanticSpace,
    initialise,
)
from pangloss_models.spaces import (
    GroundedBy,
    Signature,
    UnknownHeadError,
    UnknownSpaceError,
    normalise,
    registered_grounds,
    registered_spaces,
    signature,
)

CASES = Path(__file__).parent / "space_cases.json"


@no_type_check
def declare() -> dict[str, Any]:
    class Person(Entity):
        pass

    class Reported[T](SemanticSpace[T]):
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class Believed[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(degree="possible")

    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    # (a denial that is no operator of logic: nothing is rewritten around it)
    class Doubted[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=-1, unary=True)

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Might[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))

    # (this project's "must have been" commits the source)
    class Must[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "epistemic"), veridical=1)

    class Deontic[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(abstract=True, fit="prescribes")

    class Obligatory[T](Deontic[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "deontic"))

    class Permitted[T](Deontic[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "deontic"))

    class Forbidden[T](Deontic[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "deontic", of_not=True))

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), fit="prescribes", degree="expected"
        )
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    # (what cannot be: a necessity of not that commits the source)
    class Impossible[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "alethic", of_not=True), veridical=-1
        )

    class Possible[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "alethic"))

    # (a possibility whose flavour has no necessity declared)
    class Feasible[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "practical"))

    class Purchase(Document):
        buyer: Person

    class Service(Document):
        parts: list[Purchase]

    class Order(Document):
        ordered_by: Person
        content: Ordered[Purchase | Not[Purchase]]

    class Factoid(Document):
        statements: list[Purchase | Not[Purchase | Service] | Order]

    # --- heads with a ground of their own (`Factoid` says nothing: asserted, a claim, no one's)
    class Source(Entity):
        pass

    class Charter(Document):
        _meta = Document.Meta(ground=Ground(by="issued_by"))
        issued_by: Source
        statements: list[Purchase | Not[Purchase] | Reported[Purchase] | Order]

    class Rumour(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))
        statements: list[Purchase | Not[Purchase] | Reported[Purchase]]

    # (neither asserted nor denied, and no degree)
    class Hearsay(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, by="heard_from"))
        heard_from: Person
        statements: list[Purchase]

    # (a document whose every statement is how things are to be)
    class Rule(Document):
        _meta = Document.Meta(ground=Ground(veridical=0, fit="prescribes"))
        statements: list[Purchase | Not[Purchase] | Order]

    class Register(Document):
        _meta = Document.Meta(ground=Ground(standing="record"))
        statements: list[Purchase]

    class Place(Entity):
        within: Place | None = None

    class Legend(Entity):
        _meta = Entity.Meta(ground=Ground(standing="claim", by="told_by"))
        told_by: Person

    initialise()
    return locals()


@pytest.fixture
def models():
    return declare()


ENTITIES = {"Person", "Source", "Place", "Legend"}


def path_of(written: list[str], spaces, head: str = "Factoid") -> list[dict]:
    """A path from its short form: each node by its class, a space with `=degree` where one was entered on it and
    `.field` where it holds the next by a field that is not its contents. The
    head, a `Factoid` unless another is named, is put first; ids are the class in small letters and the place in
    the path"""
    path = []
    for place, name in enumerate([head, *written]):
        name, _, degree = name.partition("=")
        name, _, field = name.partition(".")
        is_space = name in spaces
        entry = {
            "kind": "space"
            if is_space
            else "entity"
            if name in ENTITIES
            else "document",
            "type": name,
            "id": f"{name.lower()}-{place}",
            "field": field or ("contents" if is_space else "parts"),
        }
        if degree:
            entry["degree"] = degree
        path.append(entry)
    return path


def said(
    veridical,
    lean=None,
    degree=None,
    fit="describes",
    by=None,
    force=None,
    flavour=None,
    standing="claim",
    grounded=None,
):
    """What the walk gives, as JSON. `grounded`: `(head id, field)` where the ground names whose it is"""
    return {
        "veridical": veridical,
        "lean": lean,
        "degree": degree,
        "fit": fit,
        "prescribedBy": by,
        "force": force,
        "flavour": flavour,
        "standing": standing,
        "groundedBy": {
            "head": grounded[0],
            "field": grounded[1],
            "key": to_camel(grounded[1]),
        }
        if grounded
        else None,
    }


EPISTEMIC = {"flavour": "epistemic"}
DEONTIC = {"fit": "prescribes", "flavour": "deontic"}
COMMAND = {"fit": "prescribes", "flavour": "command", "force": "necessity"}

# (name, the path of p below the head, what the walk gives of p)
WRITTEN: list[tuple[str, list[str], dict]] = [
    # --- no space
    ("the head itself", [], said(1)),
    ("a statement nested with no space is asserted", ["Service"], said(1)),
    # --- the walk's table
    ("Not[p]", ["Not"], said(-1)),
    ("Not[Not[p]]", ["Not", "Not"], said(1)),
    ("Not[Not[Not[p]]]", ["Not", "Not", "Not"], said(-1)),
    ("Reported[p]", ["Reported"], said(0, "for")),
    ("Reported[Not[p]]", ["Reported", "Not"], said(0, "against")),
    (
        "Not[Known[p]]: it is not known that p",
        ["Not", "Known"],
        said(0, "neither"),
    ),
    ("Known[p]", ["Known"], said(1)),
    ("Known[Not[p]]", ["Known", "Not"], said(-1)),
    ("Known[Service(parts=[p])]", ["Known", "Service"], said(1)),
    (
        "Not[Service(parts=[p])]: there was no such service, which says nothing of p",
        ["Not", "Service"],
        said(0, "neither"),
    ),
    (
        "Reported[Service(parts=[p])]",
        ["Reported", "Service"],
        said(0, "for"),
    ),
    (
        "Reported[Not[Service(parts=[p])]]: a statement met while leaning against",
        ["Reported", "Not", "Service"],
        said(0, "neither"),
    ),
    (
        "Reported[Not[Believed[p]]]: a space met while leaning against",
        ["Reported", "Not", "Believed"],
        said(0, "neither"),
    ),
    (
        "nothing further in brings a lean back",
        ["Not", "Service", "Reported", "Not"],
        said(0, "neither"),
    ),
    (
        "Order(content=Ordered[p])",
        ["Order", "Ordered"],
        said(0, "for", "expected", by="order-1", **COMMAND),
    ),
    (
        "Order(content=Ordered[Not[p]])",
        ["Order", "Ordered", "Not"],
        said(0, "against", "expected", by="order-1", **COMMAND),
    ),
    # --- a denial that is no operator of logic
    ("Doubted[p]", ["Doubted"], said(-1)),
    (
        "Doubted[Doubted[p]]: two denials cancel only where both are a 'not'",
        ["Doubted", "Doubted"],
        said(0, "neither"),
    ),
    ("Doubted[Not[p]]", ["Doubted", "Not"], said(0, "neither")),
    ("Reported[Doubted[p]]", ["Reported", "Doubted"], said(0, "against")),
    # --- modalities as written
    ("Might[p]", ["Might"], said(0, "for", force="possibility", **EPISTEMIC)),
    ("Must[p], which commits", ["Must"], said(1, force="necessity", **EPISTEMIC)),
    (
        "Must[Not[p]]",
        ["Must", "Not"],
        said(-1, force="necessity", **EPISTEMIC),
    ),
    (
        "Obligatory[p]: a deontic necessity commits to nothing",
        ["Obligatory"],
        said(0, "for", by="factoid-0", force="necessity", **DEONTIC),
    ),
    (
        "Permitted[p]",
        ["Permitted"],
        said(0, "for", by="factoid-0", force="possibility", **DEONTIC),
    ),
    # --- the normalising table
    (
        "Not[Might[p]], read as Must[Not[p]]: denied, this project's Must committing",
        ["Not", "Might"],
        said(-1, force="necessity", **EPISTEMIC),
    ),
    (
        "Not[Must[p]], read as Might[Not[p]]",
        ["Not", "Must"],
        said(0, "against", force="possibility", **EPISTEMIC),
    ),
    (
        "Not[Obligatory[p]], read as Permitted[Not[p]]",
        ["Not", "Obligatory"],
        said(0, "against", by="factoid-0", force="possibility", **DEONTIC),
    ),
    (
        "Not[Permitted[p]], read as Obligatory[Not[p]]",
        ["Not", "Permitted"],
        said(0, "against", by="factoid-0", force="necessity", **DEONTIC),
    ),
    (
        "Forbidden[p], read as Obligatory[Not[p]]",
        ["Forbidden"],
        said(0, "against", by="factoid-0", force="necessity", **DEONTIC),
    ),
    (
        "Forbidden[Not[p]], read as Obligatory[p]",
        ["Forbidden", "Not"],
        said(0, "for", by="factoid-0", force="necessity", **DEONTIC),
    ),
    (
        "Not[Forbidden[p]], read as Permitted[p]",
        ["Not", "Forbidden"],
        said(0, "for", by="factoid-0", force="possibility", **DEONTIC),
    ),
    (
        "Impossible[p]: a necessity of not that commits",
        ["Impossible"],
        said(-1, force="necessity", flavour="alethic"),
    ),
    (
        "Not[Possible[p]], read as Impossible[p]",
        ["Not", "Possible"],
        said(-1, force="necessity", flavour="alethic"),
    ),
    (
        "Not[Impossible[p]], read as Possible[p]",
        ["Not", "Impossible"],
        said(0, "for", force="possibility", flavour="alethic"),
    ),
    (
        "a 'not' passes two modalities, each turned within its own flavour (must not be permitted = must be forbidden)",
        ["Not", "Might", "Permitted"],
        said(0, "against", by="factoid-0", force="necessity", **DEONTIC),
    ),
    (
        "Might[Not[Might[p]]]",
        ["Might", "Not", "Might"],
        said(0, "against", force="necessity", **EPISTEMIC),
    ),
    # --- the two limits
    (
        "a flavour with no necessity declared: no other flavour's stands in for it",
        ["Not", "Feasible"],
        said(0, "against", force="necessity", flavour="practical"),
    ),
    (
        "Not[Order(content=Permitted[p])]: the statement between stops the 'not'",
        ["Not", "Order", "Permitted"],
        said(0, "neither", by="order-2", force="possibility", **DEONTIC),
    ),
    (
        "Not[Known[Might[p]]]: a space that is no modality stops it too",
        ["Not", "Known", "Might"],
        said(0, "neither", force="possibility", **EPISTEMIC),
    ),
    (
        "Not[Service(parts=[Not[p]])]: two that are not next to each other do not cancel",
        ["Not", "Service", "Not"],
        said(0, "neither"),
    ),
    # --- what a space holds in a field of its own is not its contents
    (
        "Not(witness=d): the space says nothing of what is not its contents",
        ["Not.witness"],
        said(1),
    ),
    (
        "Reported[Ordered(issued=d)]: in the report, not in the order",
        ["Reported", "Ordered.issued"],
        said(0, "for"),
    ),
    (
        "Not(witness=Not[d]): between two 'not's as a statement is",
        ["Not", "Not.witness", "Not"],
        said(0, "neither"),
    ),
    # --- the degree
    ("the class's default", ["Believed"], said(0, "for", "possible")),
    (
        "entered on the space",
        ["Reported=likely"],
        said(0, "for", "likely"),
    ),
    (
        "entered, over the class's default",
        ["Order", "Ordered=unlikely"],
        said(0, "for", "unlikely", by="order-1", **COMMAND),
    ),
    (
        "of the innermost space that leaves its contents neither",
        ["Reported=likely", "Believed"],
        said(0, "for", "possible"),
    ),
    (
        "the innermost has none: an outer one's is not taken",
        ["Believed", "Reported"],
        said(0, "for"),
    ),
    (
        "kept through a statement and a 'not'",
        ["Believed", "Service", "Not"],
        said(0, "against", "possible"),
    ),
    (
        "none where it leans neither way",
        ["Believed", "Not", "Service"],
        said(0, "neither"),
    ),
    (
        "none of what is asserted, whatever was reported outside it",
        ["Known", "Service"],
        said(1),
    ),
    # --- prescribed, and by what
    (
        "the innermost space that prescribes, and the statement that holds it",
        ["Order", "Ordered", "Service", "Order", "Permitted"],
        said(
            0,
            "for",
            by="order-4",
            fit="prescribes",
            force="possibility",
            flavour="deontic",
        ),
    ),
    (
        "prescribed whatever else the path says",
        ["Not", "Order", "Ordered", "Service"],
        said(0, "neither", by="order-2", **COMMAND),
    ),
    (
        "a space held by a space: prescribed by the nearest statement outside both",
        ["Order", "Reported", "Ordered"],
        said(0, "for", "expected", by="order-1", **COMMAND),
    ),
]


BY_CHARTER = {"grounded": ("charter-0", "issued_by")}
BY_HEARSAY = {"grounded": ("hearsay-0", "heard_from")}

# The ground: (name, the head's class, the path of p below the head or None for the head itself, what the walk gives)
GROUNDED: list[tuple[str, str, list[str] | None, dict]] = [
    # --- a claim that names whose it is
    (
        "a claim: a statement of a charter is its issuer's",
        "Charter",
        [],
        said(1, **BY_CHARTER),
    ),
    (
        "a claim: nested further, still the head's",
        "Charter",
        ["Service"],
        said(1, **BY_CHARTER),
    ),
    ("a claim: denied in it", "Charter", ["Not"], said(-1, **BY_CHARTER)),
    ("a claim: reported in it", "Charter", ["Reported"], said(0, "for", **BY_CHARTER)),
    (
        "a claim: an order in it is prescribed by the order, not the head",
        "Charter",
        ["Order", "Ordered"],
        said(0, "for", "expected", by="order-1", **COMMAND, **BY_CHARTER),
    ),
    (
        "a nested document has its head's ground, whatever its own class says",
        "Charter",
        ["Rumour"],
        said(1, **BY_CHARTER),
    ),
    # --- the record
    ("a document that is the record", "Register", [], said(1, standing="record")),
    ("an entity's own relation: the record", "Place", [], said(1, standing="record")),
    (
        "an entity that is a claim, someone's",
        "Legend",
        [],
        said(1, grounded=("legend-0", "told_by")),
    ),
    # --- a ground that neither asserts nor denies
    (
        "a ground of 0: what it holds leans for, at its degree",
        "Rumour",
        [],
        said(0, "for", "possible"),
    ),
    (
        "a ground of 0: nested further the same",
        "Rumour",
        ["Service"],
        said(0, "for", "possible"),
    ),
    ("a ground of 0 with no degree", "Hearsay", [], said(0, "for", **BY_HEARSAY)),
    (
        "a ground of 0, a denial inside: leans against, at the ground's degree",
        "Rumour",
        ["Not"],
        said(0, "against", "possible"),
    ),
    (
        "a ground of 0, two denials inside",
        "Rumour",
        ["Not", "Not"],
        said(0, "for", "possible"),
    ),
    (
        "a ground of 0, a statement denied and what it holds: nothing said",
        "Rumour",
        ["Not", "Service"],
        said(0, "neither"),
    ),
    (
        "a ground of 0, a space inside that has no degree: the ground's is not taken in its place",
        "Rumour",
        ["Reported"],
        said(0, "for"),
    ),
    (
        "a ground of 0, a space inside with a degree entered",
        "Rumour",
        ["Reported=likely"],
        said(0, "for", "likely"),
    ),
    (
        "a ground of 0, a space inside that asserts keeps the ground's",
        "Rumour",
        ["Known"],
        said(0, "for", "possible"),
    ),
    (
        "a ground of 0, a 'not' round a possibility inside: it must not be, which leans against",
        "Rumour",
        ["Not", "Might"],
        said(0, "against", "possible", force="necessity", **EPISTEMIC),
    ),
    (
        "a ground of 0, a 'not' round a space inside: nothing said",
        "Rumour",
        ["Not", "Reported"],
        said(0, "neither"),
    ),
    (
        "a ground of 0, a space inside round a 'not': against, at the space's degree, which is none",
        "Rumour",
        ["Reported", "Not"],
        said(0, "against"),
    ),
    # --- a ground that prescribes
    (
        "a ground that prescribes, a denial inside: prescribed not, by the head",
        "Rule",
        ["Not"],
        said(0, "against", fit="prescribes", by="rule-0"),
    ),
    (
        "a ground that prescribes: by the head",
        "Rule",
        [],
        said(0, "for", fit="prescribes", by="rule-0"),
    ),
    (
        "a ground that prescribes, an order inside: by the order",
        "Rule",
        ["Order", "Ordered"],
        said(0, "for", "expected", by="order-1", **COMMAND),
    ),
    # --- the head itself (an empty path), its class named by the caller
    (
        "the head itself, a claim",
        "Charter",
        None,
        said(1, grounded=(None, "issued_by")),
    ),
    ("the head itself, an entity", "Place", None, said(1, standing="record")),
    ("the head itself, a rumour", "Rumour", None, said(0, "for", "possible")),
    (
        "the head itself, prescribing: by no node",
        "Rule",
        None,
        said(0, "for", fit="prescribes"),
    ),
]


def build_cases() -> dict:
    spaces = registered_spaces()
    return {
        "spaces": spaces,
        "grounds": registered_grounds(),
        "cases": [
            {"name": name, "path": path_of(written, spaces), "expected": expected}
            for name, written, expected in WRITTEN
        ]
        + [
            {
                "name": name,
                "path": [] if written is None else path_of(written, spaces, head),
                **({"head": head} if written is None else {}),
                "expected": expected,
            }
            for name, head, written, expected in GROUNDED
        ],
    }


@pytest.mark.parametrize(
    "name, head, written, expected", GROUNDED, ids=[w[0] for w in GROUNDED]
)
def test_the_walk_from_the_ground(models, name, head, written, expected):
    spaces, grounds = registered_spaces(), registered_grounds()
    if written is None:
        given = signature([], spaces, grounds, head=head)
    else:
        given = signature(path_of(written, spaces, head), spaces, grounds)
    assert given.as_json() == expected


def test_what_the_models_say_of_each_ground(models):
    grounds = registered_grounds()
    assert grounds["Charter"] == {
        "veridical": 1,
        "fit": "describes",
        "degree": None,
        "by": {"name": "issued_by", "key": "issuedBy"},
        "standing": "claim",
    }
    assert (
        grounds["Factoid"]["standing"] == "claim" and grounds["Factoid"]["by"] is None
    )
    assert grounds["Person"]["standing"] == "record"
    assert (
        grounds["Rumour"]["veridical"] == 0
        and grounds["Rumour"]["degree"] == "possible"
    )
    assert "Not" not in grounds


def test_the_grounds_are_read_from_the_models_where_none_are_given(models):
    path = path_of(["Not"], registered_spaces(), "Charter")
    assert signature(path) == Signature(
        veridical=-1,
        lean=None,
        degree=None,
        fit="describes",
        prescribed_by=None,
        force=None,
        flavour=None,
        standing="claim",
        grounded_by=GroundedBy("charter-0", "issued_by", "issuedBy"),
    )


def test_a_head_class_the_grounds_do_not_have_reads_as_its_kind(models):
    """A table of grounds may leave out the head of a path that says nothing: a document is then a claim, an
    entity the record"""
    spaces = registered_spaces()
    assert signature(path_of(["Not"], spaces, "Charter"), spaces, {}).as_json() == said(
        -1
    )
    assert signature(path_of([], spaces, "Place"), spaces, {}).as_json() == said(
        1, standing="record"
    )


def test_a_path_that_does_not_begin_with_a_head_has_no_ground(models):
    """A part of a path, made by hand: asserted, of no standing"""
    spaces = registered_spaces()
    path = [{"kind": "space", "type": "Reported", "id": "r", "field": "contents"}]
    assert signature(path, spaces).as_json() == said(0, "for", standing=None)
    assert signature([], spaces).as_json() == said(1, standing=None)
    for kind in ("reified", "embedded", "conjunction"):
        held = [{"kind": kind, "type": "Wrapper", "id": "w", "field": "target"}]
        assert signature(held, spaces).as_json() == said(1, standing=None)
    # (an entry with no id, as a form's has for a new node)
    new = [{"kind": "document", "type": "Charter", "field": "statements"}]
    assert signature(new).grounded_by == GroundedBy(None, "issued_by", "issuedBy")


def test_a_head_named_that_is_no_head_class_is_refused(models):
    with pytest.raises(UnknownHeadError, match="'Not' has no ground"):
        signature([], head="Not")
    # (a head the caller names has to be in the table given, which may leave out only the heads of paths)
    with pytest.raises(UnknownHeadError, match="leave it out"):
        signature([], registered_spaces(), {}, head="Place")


@pytest.mark.parametrize(
    "name, written, expected", WRITTEN, ids=[w[0] for w in WRITTEN]
)
def test_the_walk(models, name, written, expected):
    spaces = registered_spaces()
    assert signature(path_of(written, spaces), spaces).as_json() == expected


def test_the_shared_cases_are_up_to_date(models):
    text = json.dumps(build_cases(), indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("PANGLOSS_WRITE_SPACE_CASES"):
        CASES.write_text(text)
    assert CASES.read_text() == text, (
        "space_cases.json is out of date: run with PANGLOSS_WRITE_SPACE_CASES=1"
    )


def test_the_shared_cases_need_only_what_the_file_has():
    """As the interface runs them: no model declared, the spaces from the file"""
    built = json.loads(CASES.read_text())
    for case in built["cases"]:
        given = signature(
            case["path"], built["spaces"], built["grounds"], case.get("head")
        ).as_json()
        assert given == case["expected"], case["name"]


def test_the_spaces_are_read_from_the_models_where_none_are_given(models):
    path = path_of(["Order", "Ordered", "Not"], registered_spaces())
    assert signature(path) == Signature(
        veridical=0,
        lean="against",
        degree="expected",
        fit="prescribes",
        prescribed_by="order-1",
        force="necessity",
        flavour="command",
        standing="claim",
    )


def test_what_the_models_say_of_each_space(models):
    spaces = registered_spaces()
    assert spaces["Forbidden"] == {
        "veridical": 0,
        "fit": "prescribes",
        "logical": {"force": "necessity", "flavour": "deontic", "ofNot": True},
        "unary": True,
        "degree": None,
        "abstract": False,
    }
    assert spaces["Deontic"]["abstract"] is True
    assert "Purchase" not in spaces and "Person" not in spaces


def test_a_necessity_that_does_not_commit_makes_its_dual_uncommitted():
    spaces = {
        "Not": {
            "veridical": -1,
            "fit": "describes",
            "logical": {"not": True},
            "degree": None,
        },
        "Might": {
            "veridical": 0,
            "fit": "describes",
            "logical": {"force": "possibility", "flavour": "epistemic", "ofNot": False},
            "degree": "possible",
        },
        "Must": {
            "veridical": 0,
            "fit": "describes",
            "logical": {"force": "necessity", "flavour": "epistemic", "ofNot": False},
            "degree": None,
        },
    }
    given = signature(path_of(["Not", "Might"], spaces), spaces)
    # (the degree is the written space's own: the dual is of no class)
    assert (given.veridical, given.lean, given.degree) == (0, "against", "possible")
    assert (given.force, given.flavour) == ("necessity", "epistemic")


@no_type_check
def test_an_abstract_modality_with_classes_below_it_is_not_counted():
    # (found by the second reading of 7.3: `Epistemic[T]`, which declaring `Must[T](Epistemic[T])` makes, has the
    # logic of `Epistemic` and not its `abstract`; counted, it was a necessity that commits to nothing)
    class Epistemic[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            abstract=True, logical=Modal("necessity", "epistemic")
        )

    class Must[T](Epistemic[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Might[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class P(Document):
        pass

    class Factoid(Document):
        statements: list[P | Must[P] | Not[Might[P]]]

    initialise()
    spaces = registered_spaces()
    assert sorted(spaces) == ["Epistemic", "Might", "Must", "Not"]
    # (it cannot have been: the one necessity of the flavour commits, so it is denied)
    given = signature(path_of(["Not", "Might"], spaces), spaces)
    assert (given.veridical, given.force) == (-1, "necessity")


def test_two_necessities_of_one_flavour_that_disagree_do_not_commit():
    spaces = {
        "Not": {
            "veridical": -1,
            "fit": "describes",
            "logical": {"not": True},
            "degree": None,
        },
        "Might": {
            "veridical": 0,
            "fit": "describes",
            "logical": {"force": "possibility", "flavour": "epistemic", "ofNot": False},
            "degree": None,
        },
        "Must": {
            "veridical": 1,
            "fit": "describes",
            "logical": {"force": "necessity", "flavour": "epistemic", "ofNot": False},
            "degree": None,
        },
        "Surely": {
            "veridical": 0,
            "fit": "describes",
            "logical": {"force": "necessity", "flavour": "epistemic", "ofNot": False},
            "degree": None,
        },
    }
    assert signature(path_of(["Not", "Might"], spaces), spaces).veridical == 0
    del spaces["Surely"]
    assert signature(path_of(["Not", "Might"], spaces), spaces).veridical == -1
    # (an abstract class is no modality of the project's: it is never written)
    spaces["Surely"] = {
        "veridical": 0,
        "fit": "describes",
        "logical": {"force": "necessity", "flavour": "epistemic", "ofNot": False},
        "degree": None,
        "abstract": True,
    }
    assert signature(path_of(["Not", "Might"], spaces), spaces).veridical == -1


def test_the_normalised_steps(models):
    spaces = registered_spaces()
    steps = normalise(
        path_of(["Not", "Might", "Service", "Forbidden"], spaces)[1:], spaces
    )
    assert [(s.kind, s.force, s.veridical, s.type) for s in steps] == [
        ("modal", "necessity", 1, None),
        ("not", None, -1, None),
        ("statement", None, 1, "Service"),
        ("modal", "necessity", 0, "Forbidden"),
        ("not", None, -1, None),
    ]


def test_a_space_that_is_not_among_the_models_is_refused(models):
    path = [{"kind": "space", "type": "Rumoured", "id": "x", "field": "contents"}]
    with pytest.raises(UnknownSpaceError, match="'Rumoured'"):
        signature(path)


def test_the_path_the_models_give_an_instance(models):
    """The paths as the models work them out for what they write, not written by hand"""
    m = models
    person = {"type": "Person", "id": uuid7()}

    def purchase():
        return {"type": "Purchase", "label": "A purchase", "buyer": person}

    factoid = m["Factoid"].Create(
        label="A factoid",
        statements=[
            {"type": "Not", "contents": [purchase()]},
            {
                "type": "Not",
                "contents": [
                    {"type": "Service", "label": "A service", "parts": [purchase()]}
                ],
            },
            {
                "type": "Order",
                "label": "An order",
                "ordered_by": person,
                "content": {
                    "type": "Ordered",
                    "how_likely": "likely",
                    "contents": [{"type": "Not", "contents": [purchase()]}],
                },
            },
        ],
    )
    db = factoid._to_db_model()
    denied, no_service, order = db.statements
    assert signature(denied.contents[0].context_path).veridical == -1
    part = no_service.contents[0].parts[0]
    assert part.semantic_spaces == ["Not"]
    assert signature(part.context_path).as_json() == said(0, "neither")
    bought = order.content.contents[0].contents[0]
    assert signature(bought.context_path).as_json() == said(
        0, "against", "likely", by=str(order.id), **COMMAND
    )
