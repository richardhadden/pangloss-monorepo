"""The walk (`pangloss_models.spaces`; implementation_docs/semantic-spaces.md): what a node's path says of it.

The cases are written here by hand, each with what the walk must give, and kept as data in `space_cases.json`, which
the interface's port of the walk passes too: `PANGLOSS_WRITE_SPACE_CASES=1` writes the file again."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    Degree,
    DegreeStep,
    Document,
    Entity,
    Modal,
    SemanticSpace,
    initialise,
)
from pangloss_models.spaces import (
    Signature,
    UnknownSpaceError,
    normalise,
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

    initialise()
    return locals()


@pytest.fixture
def models():
    return declare()


def path_of(written: list[str], spaces) -> list[dict]:
    """A path from its short form: each node by its class, a space with `=degree` where one was entered on it and
    `.field` where it holds the next by a field that is not its contents. The
    head, a `Factoid`, is put first; ids are the class in small letters and the place in the path"""
    path = []
    for place, name in enumerate(["Factoid", *written]):
        name, _, degree = name.partition("=")
        name, _, field = name.partition(".")
        is_space = name in spaces
        entry = {
            "kind": "space" if is_space else "document",
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
):
    return {
        "veridical": veridical,
        "lean": lean,
        "degree": degree,
        "fit": fit,
        "prescribedBy": by,
        "force": force,
        "flavour": flavour,
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


def build_cases() -> dict:
    spaces = registered_spaces()
    return {
        "spaces": spaces,
        "cases": [
            {"name": name, "path": path_of(written, spaces), "expected": expected}
            for name, written, expected in WRITTEN
        ],
    }


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
        given = signature(case["path"], built["spaces"]).as_json()
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
