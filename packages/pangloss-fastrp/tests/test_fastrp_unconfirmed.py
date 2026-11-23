"""A guess no person has confirmed is no evidence (step 10.5c of implementation_docs/similarity-build-plan.md, the
user's answer to row 16): a class `hooks.unconfirmed` names (with `pangloss-library`, every class of suggestion) is
an `END` in the maps, whatever its `FastRPMeta` says, so the graph part's signature differs with it; with the hook
empty nothing differs. No database."""

from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    ReifiedRelation,
    hooks,
    initialise,
)

from pangloss_fastrp import FastRPMeta, graph_maps, maps
from pangloss_fastrp.maths import Edge, Node, joins
from pangloss_fastrp.memory import MemoryReader


@pytest.fixture
def no_unconfirmed(monkeypatch):
    """The hook emptied for the test (the library registers its function when it is imported), and the maps
    forgotten before and after"""
    monkeypatch.setattr(hooks, "unconfirmed", [])
    maps.forget()
    yield
    maps.forget()


@pytest.fixture
def unconfirmed(no_unconfirmed):
    """`said("Guess")`: the hook names these classes from now on (the maps forgotten)"""

    def said(*names: str) -> None:
        hooks.unconfirmed.append(lambda: names)
        maps.forget()

    return said


@no_type_check
def declare(guess: FastRPMeta | None = None):
    """A person through `Sure`, or through `Guess` (with this `FastRPMeta`, and `Hunch` below it)"""

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class Sure[T](ReifiedRelation[T]):
        pass

    class Guess[T](ReifiedRelation[T]):
        if guess is not None:
            _fastrp_meta = guess
        at: Place | None = None

    class Hunch[T](Guess[T]):
        pass

    class Note(Document):
        about: list[Person | Sure[Person] | Guess[Person] | Hunch[Person]]

    initialise()


def test_a_class_the_hook_names_is_an_end_whatever_its_fastrp_meta_says(unconfirmed):
    declare(FastRPMeta(weight=2.0, own=False))
    found = graph_maps()
    assert found.kinds["Guess"] == "through"
    assert found.class_weight["Guess"] == 2.0 and found.own["Guess"] is False

    unconfirmed("Guess")
    found = graph_maps()
    assert found.kinds["Guess"] == "end"
    # (a chain ends there: nothing of its own is kept, as for `FastRPMeta(stop=True)`)
    assert "Guess" not in found.class_weight and "Guess" not in found.own
    # (a class below it is named itself: the hook names it, or it stays as it is)
    assert found.kinds["Hunch"] == "through"
    assert found.kinds["Sure"] == "through"


def test_a_name_the_hook_gives_of_no_wrapper_or_of_no_class_changes_nothing(
    unconfirmed,
):
    declare()
    before = graph_maps().plain()
    unconfirmed("Note", "Person", "NoSuchClass")
    assert graph_maps().plain() == before


def test_the_signature_differs_with_a_class_the_hook_names_and_not_with_the_hook_empty(
    unconfirmed,
):
    declare()
    plain = maps.signature()
    # (with the hook empty, as before the hook: the same each time)
    maps.forget()
    assert maps.signature() == plain
    unconfirmed("Guess")
    guessed = maps.signature()
    assert guessed != plain
    unconfirmed("Hunch")
    assert maps.signature() not in (plain, guessed)


def test_with_the_library_every_class_of_suggestion_is_an_end_and_an_identification_is_passed_through():
    from pangloss_testing.similar_models import declare as similar

    maps.forget()
    similar()
    kinds = graph_maps().kinds
    assert kinds["IdentificationByToolchain"] == "end"
    assert kinds["IdentificationByToolchainFromText"] == "end"
    assert kinds["Identification"] == "through"
    assert kinds["IdentificationFromText"] == "through"
    assert hooks.unconfirmed_classes() == [
        "IdentificationByToolchain",
        "IdentificationByToolchainFromText",
    ]


def test_with_the_hook_empty_the_library_s_suggestions_are_passed_through_as_before(
    no_unconfirmed,
):
    from pangloss_testing.similar_models import declare as similar

    similar()
    # (declaring them runs the library's models again, which register their function again)
    hooks.unconfirmed.clear()
    maps.forget()
    kinds = graph_maps().kinds
    assert kinds["IdentificationByToolchain"] == "through"
    assert kinds["IdentificationByToolchainFromText"] == "through"


def _graph(held: str) -> MemoryReader:
    """A note about Ada, and through `held` about Ben"""
    graph = MemoryReader()
    for id, type in [("ada", "Person"), ("ben", "Person"), ("note", "Note")]:
        graph.add(Node(id, type))
    graph.add(Node("w", held))
    graph.link(Edge("note", "ada", "about"))
    graph.link(Edge("note", "w", "about"))
    graph.link(Edge("w", "ben", "target"))
    return graph


@pytest.mark.parametrize("held", ["Guess", "Hunch"])
def test_what_is_below_an_unconfirmed_node_is_joined_to_nothing_and_once_confirmed_it_is(
    unconfirmed, held
):
    declare()
    unconfirmed("Guess", "Hunch")
    found = graph_maps()
    assert joins(_graph(held), found) == {("ada", "note"): 1.0}
    assert joins(_graph("Sure"), found) == {("ada", "note"): 1.0, ("ben", "note"): 1.0}
