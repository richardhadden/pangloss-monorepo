"""The worker that suggests, without a database (step 10.5d): its settings and their refusals, which classes of head
can be marked and how a write's instruction and the setting decide it (`marking.py`), the two shapes of a suggestion's
target, the digest of a stand-in tried, and what is cited (`suggesting.py`)"""

from types import SimpleNamespace
from typing import Any, no_type_check

import pytest
from pangloss_core.settings import configure
from pangloss_models import Document, Entity, ReifiedRelation, hooks, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_reconcile import marking, settings, suggesting
from pangloss_reconcile.suggest import Alternative
from pangloss_vectors import Refreshed, Unknown, parts

APPS = ["pangloss_vectors", "pangloss_reconcile"]
WHO = {"who": {"name": 1, "graph": 0.25}}


class Knowing:
    """A part that computes nothing, and can say what an unknown would be"""

    local = True
    requires = frozenset()

    def __init__(self, name: str, weight: float = 0.0) -> None:
        self.name = name
        self.weight = weight

    def dimension(self) -> int:
        return 3

    def signature(self) -> str:
        return self.name

    async def rebuild(self, write) -> int:
        return 0

    async def refresh(self, changed, write) -> Refreshed:
        return Refreshed()

    async def overlay(self, plan) -> dict:
        return {}

    async def unknown(self, plan, unknowns) -> dict:
        return {}


@pytest.fixture(autouse=True)
def registered(monkeypatch):
    monkeypatch.setattr(
        parts,
        "_PARTS",
        {"graph": Knowing("graph", 1.0), "name": Knowing("name")},
    )


@pytest.fixture
def mention():
    """`Mention`, a stand-in for a person that names what it stands for, while the test runs"""
    stand_in = hooks.StandIn(
        document="Mention",
        stands_for=lambda model: model.__name__ == "Person",
        named_type="mentioned_type",
    )
    hooks.stand_ins.append(stand_in)
    yield stand_in
    hooks.stand_ins.remove(stand_in)


def given(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


# -- the settings ------------------------------------------------------------------------------------------------


def test_the_settings_of_the_worker_have_their_defaults():
    assert settings.suggest_on_save(given()) is False
    assert settings.suggest_as(given()) == "IdentificationByToolchainFromText"
    assert settings.toolchain(given()) == "pangloss-reconcile"
    assert settings.worker_in_server(given()) is True


@pytest.mark.parametrize(
    ("name", "value", "said"),
    [
        (
            "RECONCILE_SUGGEST_ON_SAVE",
            "yes",
            r"RECONCILE_SUGGEST_ON_SAVE is True or False",
        ),
        (
            "RECONCILE_WORKER_IN_SERVER",
            1,
            r"RECONCILE_WORKER_IN_SERVER is True or False",
        ),
        ("RECONCILE_TOOLCHAIN", "the worker", r"RECONCILE_TOOLCHAIN is the username"),
        ("RECONCILE_TOOLCHAIN", 3, r"RECONCILE_TOOLCHAIN is the username"),
        (
            "RECONCILE_SUGGEST_AS",
            "not a name",
            r"RECONCILE_SUGGEST_AS is the name of the class",
        ),
    ],
)
def test_each_setting_of_the_worker_is_refused_with_what_it_is(name, value, said):
    read = {
        "RECONCILE_SUGGEST_ON_SAVE": settings.suggest_on_save,
        "RECONCILE_WORKER_IN_SERVER": settings.worker_in_server,
        "RECONCILE_TOOLCHAIN": settings.toolchain,
        "RECONCILE_SUGGEST_AS": settings.suggest_as,
    }[name]
    with pytest.raises(PanglossInitialisationError, match=said):
        read(given(**{name: value}))


@no_type_check
def people():
    class Person(Entity):
        pass

    initialise()


def test_a_class_to_suggest_as_that_is_no_model_is_refused_at_initialise_only_with_the_setting_on(
    project_settings,
):
    configure(
        project_settings(
            INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, RECONCILE_SUGGEST_AS="Nothing"
        )
    )
    people()
    configure(
        project_settings(
            INSTALLED_APPS=APPS,
            VECTORS_PROFILES=WHO,
            RECONCILE_SUGGEST_AS="Nothing",
            RECONCILE_SUGGEST_ON_SAVE=True,
        )
    )
    with pytest.raises(
        PanglossInitialisationError,
        match="RECONCILE_SUGGEST_AS names 'Nothing', which is not a model",
    ):
        people()


@no_type_check
def test_a_class_to_suggest_as_without_the_fields_the_worker_fills_is_refused(
    project_settings,
):
    configure(
        project_settings(
            INSTALLED_APPS=APPS,
            VECTORS_PROFILES=WHO,
            RECONCILE_SUGGEST_AS="Guess",
            RECONCILE_SUGGEST_ON_SAVE=True,
        )
    )

    class Person(Entity):
        pass

    class Guess[T](ReifiedRelation[T]):
        text: str

    with pytest.raises(
        PanglossInitialisationError,
        match="which has no uris, identified_by, toolchain_version: the worker fills",
    ):
        initialise()


@no_type_check
def test_the_library_s_class_is_one_to_suggest_as(project_settings):
    import importlib

    import pangloss_library.models

    configure(
        project_settings(
            INSTALLED_APPS=[*APPS, "pangloss_library"],
            VECTORS_PROFILES=WHO,
            RECONCILE_SUGGEST_ON_SAVE=True,
        )
    )
    importlib.reload(pangloss_library.models)
    people()
    assert settings.check_suggest_as().__name__ == "IdentificationByToolchainFromText"


# -- what can be marked --------------------------------------------------------------------------------------------


@no_type_check
def declared(project_settings, apps=APPS):
    """Heads of each kind: one that takes a stand-in in a nested document's wrapper, one in its own field, one that
    takes none, one people do not write, an abstract one"""
    configure(project_settings(INSTALLED_APPS=apps, VECTORS_PROFILES=WHO))

    class Person(Entity):
        pass

    class Mention(Document):
        _meta = Document.Meta(create_directly=False)
        mentioned_type: str

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Meeting(Document):
        _meta = Document.Meta(create_directly=False)
        met: list[InRole[Person]]

    class Factoid(Document):
        statements: list[Meeting]

    class Note(Document):
        about: Person

    class Place(Entity):
        pass

    class Listing(Document):
        places: list[Place]

    class Computed(Document):
        about: Person

    class Abstract(Document):
        _meta = Document.Meta(abstract=True)
        about: Person

    initialise()
    return SimpleNamespace(**{k: v for k, v in locals().items() if isinstance(v, type)})


def test_the_classes_that_can_be_marked_are_written_by_people_and_hold_a_stand_in_at_any_depth(
    project_settings, mention
):
    def found(model):
        return model.__name__ == "Computed"

    hooks.not_written_by_people.append(found)
    try:
        m = declared(project_settings)
    finally:
        hooks.not_written_by_people.remove(found)
    assert {"Factoid", "Note", "Meeting"} <= marking.suggestible_classes()
    for name in ["Listing", "Computed", "Abstract", "Person", "Place", "Mention"]:
        assert name not in marking.suggestible_classes(), name
    assert marking.holds_stand_ins(m.Factoid)
    assert not marking.holds_stand_ins(m.Listing)


def test_nothing_can_be_marked_when_the_app_is_not_installed(project_settings, mention):
    declared(project_settings, apps=["pangloss_vectors"])
    assert marking.suggestible_classes() == frozenset()


@pytest.mark.parametrize(
    ("on_save", "said", "answer"),
    [
        (False, {}, {}),
        (False, {"suggest": "true"}, {"reconcile": True}),
        (False, {"suggest": "false"}, {"reconcile": False}),
        (True, {}, {"reconcile": True}),
        (True, {"suggest": "true"}, {"reconcile": True}),
        (True, {"suggest": "false"}, {"reconcile": False}),
    ],
)
def test_the_instruction_says_it_either_way_and_the_setting_when_it_says_nothing(
    project_settings, mention, on_save, said, answer
):
    m = declared(project_settings)
    configure(
        project_settings(
            INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, RECONCILE_SUGGEST_ON_SAVE=on_save
        )
    )
    assert marking.instructed(m.Factoid, said) == answer
    # (a class that cannot be marked: nothing, whatever is said)
    assert marking.instructed(m.Listing, said) == {}


def test_the_instruction_is_declared_with_its_two_values():
    assert hooks.write_instructions["suggest"].values == ("true", "false")
    assert marking.instructed in hooks.instructed_work


# -- the two shapes, the digest, what is cited ---------------------------------------------------------------------


def test_the_two_shapes_of_a_target_are_the_alternatives_with_their_per_cent_or_the_first_alone():
    alternatives = [Alternative("a", "Person", 70), Alternative("b", "Person", 30)]
    assert suggesting.target_of("alternatives", alternatives) == [
        {
            "type": "WeightedAlternative",
            "alternatives": [
                {"type": "Person", "id": "a", "edge_properties": {"percent": 70}},
                {"type": "Person", "id": "b", "edge_properties": {"percent": 30}},
            ],
        }
    ]
    assert suggesting.target_of("one", alternatives) == [{"type": "Person", "id": "a"}]
    with pytest.raises(ValueError):
        suggesting.target_of("one", [])


def test_a_suggestion_keeps_the_text_the_uris_and_the_properties_of_the_relation():
    part = {
        "type": "Unreconciled",
        "id": "s",
        "label": "Jon Smyth",
        "uris": ["http://example.org/j"],
        "edge_properties": {"certain": True},
    }
    made = suggesting.suggestion(
        part,
        "one",
        [Alternative("a", "Person", 100)],
        id="new",
        suggest_as="IdentificationByToolchainFromText",
        toolchain="pangloss-reconcile",
        version="profile who",
    )
    assert made == {
        "type": "IdentificationByToolchainFromText",
        "id": "new",
        "text": "Jon Smyth",
        "uris": ["http://example.org/j"],
        "identified_by": "pangloss-reconcile",
        "toolchain_version": "profile who",
        "target": [{"type": "Person", "id": "a"}],
        "edge_properties": {"certain": True},
    }


TODAY = {
    "profile": "who",
    "signature": "s",
    "parts": "{}",
    "weights": "{}",
    "features": 1,
    "least": 0.15,
}


def test_the_digest_of_a_stand_in_changes_with_today_s_signatures_the_decision_and_the_stand_in_itself():
    jon = Unknown(id="1", type="Person", label="Jon Smyth")
    first = suggesting.digest(TODAY, "decided", jon, [])
    assert suggesting.digest(TODAY, "decided", jon, []) == first
    assert suggesting.digest({**TODAY, "signature": "t"}, "decided", jon, []) != first
    assert suggesting.digest(TODAY, "other", jon, []) != first
    assert (
        suggesting.digest(
            TODAY, "decided", Unknown(id="1", type="Person", label="Jon Smith"), []
        )
        != first
    )
    assert suggesting.digest(TODAY, "decided", jon, ["http://example.org/j"]) != first
    # (its id is not in it: it is what the record is found by)
    assert (
        suggesting.digest(
            TODAY, "decided", Unknown(id="2", type="Person", label="Jon Smyth"), []
        )
        == first
    )


def test_the_settings_of_the_decision_are_in_what_a_stand_in_is_tried_with(
    project_settings,
):
    configure(project_settings(INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO))
    one = suggesting.decided_by(None)
    configure(
        project_settings(
            INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, RECONCILE_SUGGEST_ABOVE=0.5
        )
    )
    assert suggesting.decided_by(None) != one
    assert suggesting.decided_by("a fit") != suggesting.decided_by(None)


def test_a_stand_in_is_cited_by_a_citation_of_it_of_what_is_above_it_or_of_the_head():
    from pangloss_cypher.write_plan import PlannedNode, Relation, WritePlan

    def node(id, *below):
        return PlannedNode(
            id=id,
            type="X",
            labels=(),
            properties={},
            relations=[
                Relation(
                    edges=((field, f"{field}_of"),), edge_properties=None, target=target
                )
                for field, target in below
            ],
        )

    # (head h: statements s1 (holding m1) and s2 (holding m2); a field `other` holding m3)
    plan = WritePlan(
        head=node(
            "h",
            ("statements", node("s1", ("met", node("m1")))),
            ("statements", node("s2", ("met", node("m2")))),
            ("other", node("m3")),
        )
    )
    model = SimpleNamespace(_meta=SimpleNamespace(cited_with=["other"]))
    plain = SimpleNamespace(_meta=SimpleNamespace(cited_with=[]))
    every = ["m1", "m2", "m3"]
    assert suggesting.cited_among("h", plain, plan, every, set()) == []
    assert suggesting.cited_among("h", plain, plan, every, {"s1"}) == ["m1"]
    assert suggesting.cited_among("h", plain, plan, every, {"m2"}) == ["m2"]
    assert suggesting.cited_among("h", plain, plan, every, {"h"}) == every
    # (a part cited, and the head cites its field `other` with every part)
    assert suggesting.cited_among("h", model, plan, every, {"s2"}) == ["m2", "m3"]
