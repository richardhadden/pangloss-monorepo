"""The maps of the joined graph, worked out of the models (implementation_docs/similarity-build-plan.md, step 3.1):
one test for each rule, on `pangloss_testing.similar_models` and on small models written here. No database."""

import json
from types import SimpleNamespace
from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Document,
    EdgeModel,
    Embedded,
    Entity,
    PanglossMetaError,
    ReifiedRelation,
    SemanticSpace,
    Trait,
    ViaEdge,
    initialise,
)
from pangloss_models.exceptions import PanglossInitialisationError

from pangloss_fastrp import FastRPMeta, graph_maps
from pangloss_fastrp.maps import signature
from pangloss_fastrp.maths import GraphMaps


def similar():
    from pangloss_testing.similar_models import declare

    return declare()


@no_type_check
def wrappers(in_role: FastRPMeta | None = None, negative: FastRPMeta | None = None):
    """A person through `InRole` (and `Sworn` below it), inside a `Negative` (and `Denied` below it)"""

    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        if in_role is not None:
            _fastrp_meta = in_role
        at: Place | None = None

    class Sworn[T](InRole[T]):
        oath: str = ""

    class Negative[T](SemanticSpace[T]):
        if negative is not None:
            _fastrp_meta = negative

    class Denied[T](Negative[T]):
        pass

    class Meeting(Document):
        people: list[InRole[Person] | Sworn[Person]]

    class Report(Document):
        statements: list[Meeting | Negative[Meeting] | Denied[Meeting]]

    initialise()


# -- what the models are ---------------------------------------------------------------------------------------------


def test_documents_and_entities_are_stops_the_five_wrappers_through_and_a_use_of_a_generic_goes_by_the_generic():
    similar()
    kinds = graph_maps().kinds
    # (nested documents too; abstract classes have no nodes and no entry)
    for name in ("Factoid", "Activity", "Transfer", "Inference", "Person", "Group"):
        assert kinds[name] == "stop", name
    assert "Statement" not in kinds and "Event" not in kinds
    # (a reified relation, a reified relation that is a document, a conjunction, a semantic space)
    for name in (
        "InRole",
        "Identification",
        "SameEntity",
        "WeightedAlternative",
        "Negative",
    ):
        assert kinds[name] == "through", name
    # (a node of `InRole[Agent]` has the type `InRole`: no key is a use of a generic)
    assert not [name for name in kinds if "[" in name]
    assert not [name for maps in (graph_maps().held,) for name in maps if "[" in name]


@no_type_check
def test_an_embedded_object_is_passed_through_and_its_relations_are_its_own():
    class Person(Entity):
        pass

    class Signature(Embedded):
        witness: Person

    class Charter(Document):
        signature: Signature

    initialise()
    maps = graph_maps()
    assert maps.kinds["Signature"] == "through"
    assert "Signature" not in maps.held


@no_type_check
def test_a_class_below_in_role_gets_what_in_role_declares():
    wrappers(in_role=FastRPMeta(weight=0.5, weights={"at": 0.3}, own=False))
    maps = graph_maps()
    for name in ("InRole", "Sworn"):
        assert maps.kinds[name] == "through", name
        assert maps.held[name] == ["target"], name
        assert maps.class_weight[name] == 0.5, name
        assert maps.own[name] is False, name
        assert maps.field_weight[f"{name}.at"] == 0.3, name


def test_sworn_of_the_similar_models_is_named_itself_with_in_role_s_held_field():
    similar()
    maps = graph_maps()
    assert maps.kinds["Sworn"] == "through"
    assert maps.held["Sworn"] == maps.held["InRole"] == ["target"]


def test_stop_on_negative_reaches_a_class_below_it():
    wrappers(negative=FastRPMeta(stop=True))
    maps = graph_maps()
    assert maps.kinds["Negative"] == maps.kinds["Denied"] == "end"
    assert maps.held["Denied"] == ["contents"]
    assert maps.kinds["InRole"] == "through"


def test_weighted_alternative_alternatives_is_a_share_of_percent_out_of_100():
    similar()
    maps = graph_maps()
    assert maps.shares == {"WeightedAlternative.alternatives": ["percent", 100]}
    assert maps.held["WeightedAlternative"] == ["alternatives"]


@no_type_check
def test_a_share_of_a_total_other_than_100_is_given_with_its_total():
    from pangloss_models import SumsTo

    class Person(Entity):
        pass

    class Vote(EdgeModel):
        votes: int

    class Ballot(Document):
        for_: Annotated[list[ViaEdge[Person, Vote]], SumsTo("votes", total=12)]

    initialise()
    assert graph_maps().shares == {"Ballot.for_": ["votes", 12]}


def test_a_matches_criteria_is_through_and_its_target_is_held():
    similar()
    maps = graph_maps()
    assert maps.kinds["MatchesCriteria"] == "through"
    assert maps.held["MatchesCriteria"] == ["target"]


def test_pg_citation_and_its_variants_are_citations_with_no_kind():
    similar()
    maps = graph_maps()
    assert maps.citations == {"PGCitation": True, "PGUnprotectedCitation": True}
    assert "PGCitation" not in maps.kinds and "PGUnprotectedCitation" not in maps.kinds


def test_a_cited_basis_is_passed_through_to_the_citations_it_holds():
    similar()
    maps = graph_maps()
    assert maps.kinds["PGCitedBasis"] == "through"
    assert maps.held["PGCitedBasis"] == ["basis"]


def test_a_derived_document_is_out():
    similar()
    maps = graph_maps()
    assert maps.kinds["DerivedFactoid"] == "out"
    assert maps.kinds["Factoid"] == "stop"


@no_type_check
def test_a_weight_on_a_wrapper_class_and_on_a_field_and_only_what_is_not_the_default():
    class Person(Entity):
        pass

    class Place(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        _fastrp_meta = FastRPMeta(weight=0.3, weights={"at": 0.5})
        at: Place | None = None

    class Mention(Document):
        _fastrp_meta = FastRPMeta(weight=0.2, weights={"people": 2, "place": 1})
        people: list[InRole[Person]]
        place: Place

    class Birth(Mention):
        pass

    initialise()
    maps = graph_maps()
    assert maps.class_weight == {"InRole": 0.3, "Mention": 0.2, "Birth": 0.2}
    assert maps.field_weight == {
        "InRole.at": 0.5,
        "Mention.people": 2.0,
        "Birth.people": 2.0,
    }
    assert maps.own == {}


@no_type_check
def test_a_trait_s_setting_counts_for_the_classes_that_have_it():
    class Noisy(Trait):
        _fastrp_meta = FastRPMeta(weight=0.1)

    class Mention(Document, Noisy):
        pass

    class Birth(Document):
        pass

    initialise()
    assert graph_maps().class_weight == {"Mention": 0.1}


@no_type_check
def test_include_false_leaves_a_class_and_those_below_it_out():
    class Note(Document):
        _fastrp_meta = FastRPMeta(include=False, weight=3)

    class Margin(Note):
        pass

    class Letter(Document):
        pass

    initialise()
    maps = graph_maps()
    assert maps.kinds["Note"] == maps.kinds["Margin"] == "out"
    assert maps.kinds["Letter"] == "stop"
    # (what is out has no weight to give)
    assert maps.class_weight == {}


def test_the_maps_survive_json_and_graph_maps_of():
    similar()
    maps = graph_maps()
    text = json.dumps(maps.plain())
    again = GraphMaps.of(json.loads(text))
    assert again.plain() == maps.plain()
    assert again.kinds["Sworn"] == "through"


def test_the_maps_are_forgotten_when_the_models_are():
    from pangloss_models import ModelRegistry

    similar()
    assert "Factoid" in graph_maps().kinds
    ModelRegistry._reset()
    wrappers()
    assert "Factoid" not in graph_maps().kinds and "Meeting" in graph_maps().kinds


# -- refusals --------------------------------------------------------------------------------------------------------


@no_type_check
def test_a_weight_for_a_field_the_class_has_not_is_refused_by_the_field_s_name():
    class Person(Entity):
        pass

    class Mention(Document):
        _fastrp_meta = FastRPMeta(weights={"peple": 0.5})
        people: list[Person]

    with pytest.raises(PanglossMetaError, match="Mention: .*'peple'.*Mention"):
        initialise()


@no_type_check
def test_a_weight_for_a_literal_field_is_refused():
    class Mention(Document):
        _fastrp_meta = FastRPMeta(weights={"text": 0.5})
        text: str

    with pytest.raises(PanglossMetaError, match="'text', which is not a relation"):
        initialise()


@no_type_check
def test_a_weight_for_a_field_a_subclass_has_is_refused_on_the_class_that_says_it():
    class Person(Entity):
        pass

    class Statement(Document):
        _fastrp_meta = FastRPMeta(weights={"child": 0.5})

    class Birth(Statement):
        child: Person

    with pytest.raises(
        PanglossMetaError, match="Statement: .*'child'.*field of Statement"
    ):
        initialise()


@no_type_check
def test_stop_on_a_class_of_documents_is_refused():
    class Note(Document):
        _fastrp_meta = FastRPMeta(stop=True)

    with pytest.raises(
        PanglossMetaError, match=r"Note: FastRPMeta\(stop=True\) is for a wrapper"
    ):
        initialise()


@no_type_check
def test_own_false_on_a_class_of_entities_is_refused_by_the_trait_that_says_it():
    class Quiet(Trait):
        _fastrp_meta = FastRPMeta(own=False)

    class Person(Entity, Quiet):
        pass

    with pytest.raises(
        PanglossMetaError, match=r"Quiet: FastRPMeta\(own=False\).*Person"
    ):
        initialise()


@no_type_check
def test_a_weight_below_0_is_refused():
    class Note(Document):
        _fastrp_meta = FastRPMeta(weight=-1)

    with pytest.raises(PanglossMetaError, match=r"Note: FastRPMeta\(weight=-1\)"):
        initialise()


@no_type_check
def test_a_field_weight_below_0_is_refused():
    class Person(Entity):
        pass

    class Note(Document):
        _fastrp_meta = FastRPMeta(weights={"about": -0.5})
        about: Person

    with pytest.raises(
        PanglossMetaError, match=r"Note: FastRPMeta\(weights=\{'about': -0.5\}\)"
    ):
        initialise()


@no_type_check
def test_include_false_on_a_wrapper_is_refused():
    class Person(Entity):
        pass

    class InRole[T](ReifiedRelation[T]):
        _fastrp_meta = FastRPMeta(include=False)

    class Note(Document):
        people: list[InRole[Person]]

    with pytest.raises(PanglossMetaError, match=r"InRole: FastRPMeta\(include=False\)"):
        initialise()


@no_type_check
def test_the_setting_on_an_edge_model_is_refused():
    class Person(Entity):
        pass

    class Certainty(EdgeModel):
        _fastrp_meta = FastRPMeta(weight=0.5)
        level: int

    class Note(Document):
        about: list[ViaEdge[Person, Certainty]]

    with pytest.raises(PanglossMetaError, match="Certainty: .*an edge model"):
        initialise()


# -- the settings and the signature ----------------------------------------------------------------------------------


def test_the_settings_are_in_the_maps(project_settings):
    similar()
    maps = graph_maps()
    assert (list(maps.steps), maps.dimension, maps.sees) == (
        [0.0, 1.0, 1.0],
        128,
        "everyone",
    )
    project_settings(
        FASTRP_STEPS=[1, 0.5], FASTRP_DIMENSION=64, VECTORS_GRAPH_SEES="logged_in"
    )
    maps = graph_maps()
    assert (list(maps.steps), maps.dimension, maps.sees) == (
        [1.0, 0.5],
        64,
        "logged_in",
    )


@pytest.mark.parametrize(
    "value", [[], [0, 0], [1] * 9, [1, -1], [1, True], "011", 3, None]
)
def test_steps_that_are_not_1_to_8_numbers_of_0_or_more_not_all_0_are_refused(value):
    with pytest.raises(
        PanglossInitialisationError, match="FASTRP_STEPS is a list of 1 to 8"
    ):
        graph_maps(SimpleNamespace(FASTRP_STEPS=value))


@pytest.mark.parametrize("value", [7, 2049, 64.0, True, "128", None])
def test_a_dimension_that_is_not_a_whole_number_from_8_to_2048_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match="FASTRP_DIMENSION is a whole number from 8 to 2048",
    ):
        graph_maps(SimpleNamespace(FASTRP_DIMENSION=value))


def test_the_signature_changes_with_the_settings_and_not_otherwise():
    similar()
    plain = signature()
    assert signature() == plain
    assert signature(SimpleNamespace()) == plain
    # (the defaults written out are the defaults)
    assert (
        signature(
            SimpleNamespace(
                FASTRP_STEPS=[0, 1, 1],
                FASTRP_DIMENSION=128,
                VECTORS_GRAPH_SEES="everyone",
            )
        )
        == plain
    )
    changed = {
        signature(SimpleNamespace(FASTRP_STEPS=[0, 1, 1, 1])),
        signature(SimpleNamespace(FASTRP_DIMENSION=64)),
        signature(SimpleNamespace(VECTORS_GRAPH_SEES="logged_in")),
    }
    assert len(changed) == 3 and plain not in changed
    # (the models declared again, the same)
    similar()
    assert signature() == plain


@no_type_check
def test_the_signature_changes_with_a_weight():
    def declare(weight: float):
        class Person(Entity):
            pass

        class Note(Document):
            _fastrp_meta = FastRPMeta(weight=weight)
            about: Person

        initialise()
        return signature()

    plain = declare(1.0)
    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    assert declare(1.0) == plain
    ModelRegistry._reset()
    assert declare(0.5) != plain


def test_the_stops_that_are_documents_are_named_so_that_a_nested_one_takes_its_own_weight():
    similar()
    documents = graph_maps().documents
    assert documents.get("Transfer") and documents.get("Factoid")
    assert (
        "Person" not in documents
        and "InRole" not in documents
        and "DerivedFactoid" not in documents
    )
