"""What the store works out without a database (implementation_docs/similarity-build-plan.md, step 2.2): the names of
labels and indexes, the combined vector of a profile, a profile's dimension and signature, and the vector indexes
the project's migrations are to make (`structure.indexes`)."""

import math
import random
from types import SimpleNamespace

import pytest
from pangloss_core import settings as core_settings
from pangloss_models import Document, Entity, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors import VectorsMeta, structure
from pangloss_vectors.store import (
    Layout,
    VectorLengthError,
    check_length,
    group_index_name,
    group_label,
    layout,
    profile_index_name,
    profile_label,
    profile_signature,
)
from vectors_support import SizedPart

# --- names --------------------------------------------------------------------------------------------------------


def test_the_label_and_index_of_a_profile_carry_its_name_and_dimension():
    assert profile_label("default", 191) == "PGV_default_191"
    assert profile_index_name("default", 191) == "pgv_default_191"
    assert group_label("default", 191, "Person") == "PGV_default_191_Person"
    assert group_index_name("default", 191, "Person") == "pgv_default_191_person"


def test_a_name_that_is_not_a_word_is_refused():
    with pytest.raises(ValueError, match="'two words'"):
        profile_label("two words", 3)
    with pytest.raises(ValueError, match="'Not-a-class'"):
        group_label("default", 3, "Not-a-class")


def test_a_layout_names_its_label_and_index_from_its_dimension():
    lay = Layout("mostly", {"graph": 1, "class": 0.1}, {"graph": 128, "class": 63})
    assert lay.dimension == 191
    assert lay.label == "PGV_mostly_191"
    assert lay.index_name == "pgv_mostly_191"
    assert lay.group_index_name("Statement") == "pgv_mostly_191_statement"


# --- the combined vector ------------------------------------------------------------------------------------------


def test_the_parts_are_at_length_one_scaled_by_the_root_of_their_weight_in_the_order_of_their_names():
    lay = Layout("p", {"b": 1, "a": 4}, {"a": 2, "b": 3})
    assert list(lay.weights) == ["a", "b"]
    combined = lay.combine({"a": [3, 4], "b": [0, 0, 5]})
    assert combined == pytest.approx([2 * 0.6, 2 * 0.8, 0, 0, 1])


def test_a_part_the_item_has_no_vector_of_is_zeros():
    lay = Layout("p", {"a": 4, "b": 1}, {"a": 2, "b": 3})
    assert lay.combine({"b": [1, 0, 0]}) == pytest.approx([0, 0, 1, 0, 0])
    assert lay.combine({"a": [0, 2]}) == pytest.approx([0, 2, 0, 0, 0])
    # (and one of length zero)
    assert lay.combine({"a": [0, 0], "b": [0, 1, 0]}) == pytest.approx([0, 0, 0, 1, 0])


def test_a_part_at_weight_zero_is_not_in_the_profile():
    lay = Layout("p", {"a": 1, "b": 0}, {"a": 2, "b": 3})
    assert list(lay.weights) == ["a"] and lay.dimension == 2
    assert lay.combine({"a": [1, 0], "b": [1, 1, 1]}) == [1.0, 0.0]


def test_a_vector_of_the_wrong_length_is_refused():
    lay = Layout("p", {"a": 1}, {"a": 2})
    with pytest.raises(VectorLengthError, match="has 3 numbers.*dimension is 2"):
        lay.combine({"a": [1, 2, 3]})
    with pytest.raises(VectorLengthError, match="The a vector of x1"):
        check_length("a", "x1", [1.0], 2)
    assert check_length("a", "x1", [1, 2], 2) == [1.0, 2.0]


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / (
        math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    )


def test_the_cosine_of_two_combined_vectors_is_the_weighted_mean_of_the_cosines_of_their_parts():
    found = random.Random(3)
    lay = Layout("p", {"graph": 1, "class": 0.25}, {"graph": 5, "class": 4})

    def some(n: int) -> list[float]:
        return [found.uniform(-1, 1) for _ in range(n)]

    one = {"graph": some(5), "class": some(4)}
    two = {"graph": some(5), "class": some(4)}
    expected = (
        1 * cosine(one["graph"], two["graph"])
        + 0.25 * cosine(one["class"], two["class"])
    ) / 1.25
    assert cosine(lay.combine(one), lay.combine(two)) == pytest.approx(expected)


# --- dimension and signature --------------------------------------------------------------------------------------


def test_the_dimension_and_signature_of_a_profile_change_with_its_weights_and_its_parts(
    parts_of_the_test,
):
    graph, kind = SizedPart("graph", 8), SizedPart("kind", 3)
    parts_of_the_test(graph)
    parts_of_the_test(kind)
    weights = {"graph": 1.0, "kind": 0.1}
    first = layout("p", weights)
    assert first.dimension == 11
    signature = profile_signature(weights)
    assert first.signature() == signature == profile_signature(dict(weights))

    assert profile_signature({"graph": 1.0, "kind": 0.2}) != signature
    assert profile_signature({"graph": 1.0}) != signature
    # (a part at weight zero is no part of it)
    assert profile_signature({"graph": 1.0, "kind": 0.1, "other": 0}) == signature

    kind.setting = "changed"
    assert profile_signature(weights) != signature
    kind.size = 4
    assert layout("p", weights).dimension == 12


# --- the vector indexes of a project ------------------------------------------------------------------------------

SOURCE = """
class Person(Entity):
    _vectors_meta = VectorsMeta(searchable=True)

class Saint(Person):
    pass

class Statement(Document):
    pass
"""

OTHER = """
class Place(Entity):
    _vectors_meta = VectorsMeta(searchable=True)
"""


def declare(source: str, module: str) -> None:
    namespace = {
        "__name__": module,
        "Document": Document,
        "Entity": Entity,
        "VectorsMeta": VectorsMeta,
    }
    exec(source, namespace)


@pytest.fixture
def project(monkeypatch, parts_of_the_test):
    """Declares the models of two apps of a project (a project's own, and a gazetteer with one searchable class),
    initialises them, and gives a function that installs settings for `structure.indexes`"""
    parts_of_the_test(SizedPart("graph", 8, weight=1))
    parts_of_the_test(SizedPart("kind", 3, weight=0.1))
    declare(SOURCE, "pgv_project.models")
    declare(OTHER, "pgv_gazetteer.models")
    initialise()

    def use(**settings) -> None:
        given = {
            "INSTALLED_APPS": ["pangloss_vectors", "pgv_gazetteer", "pgv_project"],
            **settings,
        }
        monkeypatch.setattr(core_settings, "SETTINGS", SimpleNamespace(**given))

    return use


def entry(name: str, label: str, dimension: int, app: str) -> dict:
    return {
        "kind": "vector",
        "name": name,
        "label": label,
        "properties": ["vector"],
        "dimension": dimension,
        "metric": "cos",
        "quantization": False,
        "app": app,
    }


def test_each_profile_has_an_index_and_one_for_each_group_each_in_the_migrations_of_its_app(
    project,
):
    project(VECTORS_PROFILES={"graph_only": {"graph": 1}})
    assert structure.indexes() == [
        entry("pgv_graph_only_8", "PGV_graph_only_8", 8, "pgv_project"),
        entry("pgv_graph_only_8_person", "PGV_graph_only_8_Person", 8, "pgv_project"),
        entry("pgv_graph_only_8_place", "PGV_graph_only_8_Place", 8, "pgv_gazetteer"),
        entry("pgv_default_11", "PGV_default_11", 11, "pgv_project"),
        entry("pgv_default_11_person", "PGV_default_11_Person", 11, "pgv_project"),
        entry("pgv_default_11_place", "PGV_default_11_Place", 11, "pgv_gazetteer"),
    ]


def test_the_project_s_app_is_the_one_with_the_most_models_unless_the_setting_names_one(
    project,
):
    project()
    assert structure.project_app() == "pgv_project"
    project(VECTORS_MIGRATIONS_APP="pgv_gazetteer")
    assert structure.project_app() == "pgv_gazetteer"
    assert {e["app"] for e in structure.indexes() if "person" not in e["name"]} == {
        "pgv_gazetteer"
    }
    project(VECTORS_MIGRATIONS_APP="pgv_elsewhere")
    with pytest.raises(PanglossInitialisationError, match="'pgv_elsewhere'"):
        structure.project_app()


def test_of_two_apps_with_as_many_models_the_later_is_the_project_s(
    monkeypatch, parts_of_the_test
):
    parts_of_the_test(SizedPart("graph", 8))
    declare(OTHER, "pgv_one.models")
    declare(OTHER.replace("Place", "Region"), "pgv_two.models")
    initialise()
    apps = ["pgv_one", "pgv_two"]
    monkeypatch.setattr(core_settings, "SETTINGS", SimpleNamespace(INSTALLED_APPS=apps))
    assert structure.project_app() == "pgv_two"
    monkeypatch.setattr(
        core_settings, "SETTINGS", SimpleNamespace(INSTALLED_APPS=apps[::-1])
    )
    assert structure.project_app() == "pgv_one"


def test_there_are_no_vector_indexes_without_a_part_or_without_an_app_of_the_project(
    project, parts_of_the_test, monkeypatch
):
    project()
    assert structure.indexes()
    # (the models of the framework's packages are not the project's)
    monkeypatch.setattr(
        core_settings,
        "SETTINGS",
        SimpleNamespace(INSTALLED_APPS=["pangloss_vectors", "pangloss_library"]),
    )
    assert structure.project_app() is None
    assert structure.indexes() == []

    from pangloss_vectors import unregister_part

    unregister_part("graph")
    unregister_part("kind")
    project()
    assert structure.indexes() == []


def test_a_profile_s_vector_indexes_follow_a_change_of_a_part_s_dimension(
    project, parts_of_the_test
):
    project(VECTORS_PROFILES={"default": {"graph": 1}})
    before = {e["name"] for e in structure.indexes()}
    from pangloss_vectors.parts import part

    graph = part("graph")
    assert isinstance(graph, SizedPart)
    graph.size = 9
    after = {e["name"] for e in structure.indexes()}
    assert before == {"pgv_default_8", "pgv_default_8_person", "pgv_default_8_place"}
    assert after == {"pgv_default_9", "pgv_default_9_person", "pgv_default_9_place"}
