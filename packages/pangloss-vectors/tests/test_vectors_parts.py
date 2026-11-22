"""Parts, profiles and the settings of `pangloss-vectors` (implementation_docs/similarity-build-plan.md, step 2.1):
no database."""

import typing
from types import SimpleNamespace

import pytest
from pangloss_core import BaseSettings, DatabaseSettings
from pangloss_core.settings import configure
from pangloss_models import Document, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_models.migrations.state import replay
from pangloss_vectors import (
    DEFAULT_PROFILE,
    Changed,
    Refreshed,
    part,
    profile,
    profiles,
    register_part,
    signature_of,
    structure,
    unregister_part,
)
from pangloss_vectors.parts import parts
from pangloss_vectors.settings import exact_up_to, graph_sees, overfetch


class FakePart:
    """A part that computes nothing: what the protocol asks for, and a signature of a setting"""

    def __init__(self, name: str, weight: float = 1.0, settings: typing.Any = None):
        self.name = name
        self.local = True
        self.requires = frozenset({"cypher"})
        self.weight = weight
        self.settings = settings

    def __repr__(self) -> str:
        return f"FakePart({self.name!r}, id={id(self)})"

    def dimension(self) -> int:
        return 3

    def signature(self) -> str:
        return signature_of(getattr(self.settings, "FAKE_DECAY", None))

    async def rebuild(self, write) -> int:
        return 0

    async def refresh(self, changed: Changed, write) -> Refreshed:
        return Refreshed()

    async def overlay(self, plan) -> dict:
        return {}


class NoOverlay:
    """Everything of a part but `overlay`"""

    name = "no_overlay"
    local = False
    requires = frozenset()
    weight = 1.0

    def dimension(self) -> int:
        return 1

    def signature(self) -> str:
        return ""

    async def rebuild(self, write) -> int:
        return 0

    async def refresh(self, changed, write):
        return Refreshed()


@pytest.fixture(autouse=True)
def registered():
    """The parts a test registers are forgotten after it; the parts other packages registered are put aside for it
    (so that the default profile is of the test's parts alone) and given back after"""
    before = parts()
    for name in before:
        unregister_part(name)
    yield
    for name in parts():
        unregister_part(name)
    for made in before.values():
        register_part(made)


@pytest.fixture
def project_settings(settings):
    """Makes settings of the project (as importing a project's settings module does), and gives back the module's
    after the test"""

    def make(installed: list[str], profiles: dict | None = None):
        class Settings(BaseSettings):
            PROJECT_NAME: str = "Test"
            BACKEND_CORS_ORIGINS: list[typing.Any] = []
            INSTALLED_APPS: list[str] = installed
            STORAGE: str | None = "pangloss_sdk.storage:api"
            DATABASE: DatabaseSettings = DatabaseSettings()
            AUTHJWT_SECRET_KEY: str = "asdf"
            ENTITY_BASE_URL: typing.Any = "http://test.com/"
            VECTORS_PROFILES: dict[str, typing.Any] | None = profiles

        return Settings()

    yield make
    configure(settings)


# --- registering --------------------------------------------------------------------------------------------------


def test_a_registered_part_is_found_by_name():
    made = FakePart("fake")
    register_part(made)
    assert parts() == {"fake": made}
    assert part("fake") is made


def test_the_same_part_registered_again_is_nothing():
    made = FakePart("fake")
    register_part(made)
    register_part(made)
    assert parts() == {"fake": made}


def test_parts_are_given_in_the_order_of_their_names():
    register_part(FakePart("zeta"))
    register_part(FakePart("alpha"))
    assert list(parts()) == ["alpha", "zeta"]


def test_another_part_of_the_same_name_is_refused_naming_both():
    first, second = FakePart("fake"), FakePart("fake")
    register_part(first)
    with pytest.raises(PanglossInitialisationError) as refused:
        register_part(second)
    assert repr(first) in str(refused.value)
    assert repr(second) in str(refused.value)
    assert part("fake") is first


def test_an_object_without_a_method_of_a_part_is_refused():
    with pytest.raises(PanglossInitialisationError, match="is not a part"):
        register_part(NoOverlay())  # ty: ignore[invalid-argument-type]
    assert parts() == {}


def test_a_part_whose_name_is_not_a_word_is_refused():
    with pytest.raises(PanglossInitialisationError, match="'two words'"):
        register_part(FakePart("two words"))
    assert parts() == {}


def test_a_part_that_is_not_registered_names_those_that_are():
    register_part(FakePart("fake"))
    register_part(FakePart("other"))
    with pytest.raises(PanglossInitialisationError, match="'nope'.*fake, other"):
        part("nope")


# --- profiles -----------------------------------------------------------------------------------------------------


def test_without_the_setting_the_default_is_every_part_at_its_weight():
    register_part(FakePart("fake", weight=1))
    register_part(FakePart("other", weight=0.25))
    register_part(FakePart("unweighted", weight=0))
    found = profiles(SimpleNamespace())
    assert found == {DEFAULT_PROFILE: {"fake": 1.0, "other": 0.25}}
    assert profile(settings=SimpleNamespace()) == {"fake": 1.0, "other": 0.25}


def test_profiles_of_the_settings_are_kept_and_the_default_added():
    register_part(FakePart("fake", weight=1))
    register_part(FakePart("other", weight=0.5))
    settings = SimpleNamespace(
        VECTORS_PROFILES={"mostly_other": {"fake": 0, "other": 2}}
    )
    assert profiles(settings) == {
        "mostly_other": {"other": 2.0},
        DEFAULT_PROFILE: {"fake": 1.0, "other": 0.5},
    }


def test_a_profile_that_is_not_there_names_those_that_are():
    register_part(FakePart("fake"))
    with pytest.raises(KeyError, match="'nope'.*default"):
        profile("nope", SimpleNamespace())


@pytest.mark.parametrize(
    "weights, named",
    [
        ({"fake": -1}, r"\['fake'\].*-1"),
        ({"fake": "a lot"}, r"\['fake'\].*'a lot'"),
        ({"fake": True}, r"\['fake'\].*True"),
        ({"fake": 0, "other": 0}, "no part a weight above zero"),
        ([1, 2], r"\['bad'\] is a weight for each part"),
    ],
)
def test_a_bad_weight_is_refused_by_name(weights, named):
    register_part(FakePart("fake"))
    register_part(FakePart("other"))
    with pytest.raises(
        PanglossInitialisationError, match=r"VECTORS_PROFILES\['bad'\]"
    ) as refused:
        profiles(SimpleNamespace(VECTORS_PROFILES={"bad": weights}))
    assert refused.match(named)


def test_a_profile_naming_a_part_that_is_not_registered_is_refused_at_initialise(
    project_settings,
):
    register_part(FakePart("fake"))
    project_settings(["pangloss_vectors"], {"default": {"fake": 1, "graph": 1}})

    class Factoid(Document):
        pass

    with pytest.raises(
        PanglossInitialisationError,
        match=r"VECTORS_PROFILES\['default'\] names 'graph'.*fake",
    ):
        initialise()


def test_the_profiles_are_not_checked_without_the_app_installed(project_settings):
    register_part(FakePart("fake"))
    project_settings([], {"default": {"fake": 1, "graph": 1}})

    class Factoid(Document):
        pass

    initialise()


def test_good_profiles_pass_initialise(project_settings):
    register_part(FakePart("fake"))
    project_settings(
        ["pangloss_vectors", "not_a_package_at_all"], {"default": {"fake": 1}}
    )

    class Factoid(Document):
        pass

    # (an app that cannot be imported is not this check's to report)
    initialise()


@pytest.mark.parametrize("name", ["two words", "with-dash", "1st"])
def test_a_profile_whose_name_is_not_a_word_is_refused_by_name(name):
    register_part(FakePart("fake"))
    with pytest.raises(PanglossInitialisationError, match=f"not {name!r}"):
        profiles(SimpleNamespace(VECTORS_PROFILES={name: {"fake": 1}}))


# --- signatures ---------------------------------------------------------------------------------------------------


def test_a_signature_is_the_same_for_equal_values():
    assert signature_of({"a": 1, "b": [1, 2]}, "x") == signature_of(
        {"b": [1, 2], "a": 1}, "x"
    )
    assert signature_of({"c", "a", "b"}) == signature_of({"b", "c", "a"})
    assert signature_of(frozenset({3, 1, 2}), (1, 2)) == signature_of({1, 2, 3}, [1, 2])


def test_a_signature_differs_when_a_value_does():
    assert signature_of({"a": 1}) != signature_of({"a": 2})
    assert signature_of([1, 2]) != signature_of([2, 1])
    assert signature_of("x", "y") != signature_of("y", "x")


def test_the_signature_of_a_part_changes_when_its_setting_does():
    settings = SimpleNamespace(FAKE_DECAY=0.5)
    made = FakePart("fake", settings=settings)
    before = made.signature()
    assert made.signature() == before
    settings.FAKE_DECAY = 0.25
    assert made.signature() != before


# --- settings -----------------------------------------------------------------------------------------------------


def test_a_profile_is_read_whole_up_to_twenty_thousand_vectors_unless_the_settings_say():
    assert exact_up_to(SimpleNamespace()) == 20_000
    assert exact_up_to(SimpleNamespace(VECTORS_EXACT_UP_TO=0)) == 0
    for value in (-1, 1.5, "100", True, None):
        with pytest.raises(PanglossInitialisationError, match="VECTORS_EXACT_UP_TO"):
            exact_up_to(SimpleNamespace(VECTORS_EXACT_UP_TO=value))


def test_overfetch_is_four_unless_the_settings_say():
    assert overfetch(SimpleNamespace()) == 4
    assert overfetch(SimpleNamespace(VECTORS_OVERFETCH=10)) == 10


@pytest.mark.parametrize("value", [0, -2, 2.5, "4", True])
def test_a_bad_overfetch_is_refused_by_name(value):
    with pytest.raises(PanglossInitialisationError, match="VECTORS_OVERFETCH"):
        overfetch(SimpleNamespace(VECTORS_OVERFETCH=value))


def test_the_graph_sees_what_everyone_does_unless_the_settings_say():
    assert graph_sees(SimpleNamespace()) == "everyone"
    assert graph_sees(SimpleNamespace(VECTORS_GRAPH_SEES="logged_in")) == "logged_in"


@pytest.mark.parametrize("value", ["admin", "", None, "Everyone"])
def test_a_bad_graph_sees_is_refused_by_name(value):
    with pytest.raises(
        PanglossInitialisationError,
        match="VECTORS_GRAPH_SEES.*'everyone' or 'logged_in'",
    ):
        graph_sees(SimpleNamespace(VECTORS_GRAPH_SEES=value))


def test_the_settings_are_read_from_the_project_when_none_are_given(project_settings):
    made = project_settings([])
    assert overfetch() == 4
    assert graph_sees() == "everyone"
    assert profiles() == {DEFAULT_PROFILE: {}}
    assert made is not None


# --- structure ----------------------------------------------------------------------------------------------------


def test_the_package_s_migrations_make_the_structure_it_asks_for():
    """So that a project with the app installed has no migration pending once they are applied (0002: the index on
    the class of a profile vector, step 7a.4; 0003: the index of what a part kept, step 8.3)"""
    made = EMPTY_SNAPSHOT
    for name in ("0001_initial", "0002_profile_vector_type", "0003_vector_kept"):
        made = replay(made, load("pangloss_vectors", name).changes)
    # (in any order: a snapshot keeps its own)
    assert sorted(made["indexes"], key=repr) == sorted(structure.INDEXES, key=repr)
    assert made["constraints"] == structure.CONSTRAINTS
