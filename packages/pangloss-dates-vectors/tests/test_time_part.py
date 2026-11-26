"""The time part without a database (implementation_docs/similarity-build-plan.md, step 9.3): what it is, its
settings and their refusals, what its signature depends on and what not, that it is in no profile by itself, whose
vector a date is (a row as a query gives it, and the dates of a plan), and that numpy waits until it is wanted"""

import subprocess
import sys
from types import SimpleNamespace
from typing import no_type_check

import numpy as np
import pytest
from pangloss_core.settings import configure
from pangloss_dates_vectors import maths, settings
from pangloss_dates_vectors.part import PART, Dates, counts_for
from pangloss_models import Document, Entity, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_vectors.parts import part, profile, register_part


@no_type_check
def letters() -> None:
    class Person(Entity):
        pass

    class Letter(Document):
        pass

    initialise()


def test_the_part_is_registered_as_time_and_refreshes_after_a_write():
    assert part("time") is PART
    assert (PART.name, PART.local, PART.requires, PART.weight) == (
        "time",
        True,
        frozenset(),
        0.0,
    )
    # (the same object again is nothing)
    register_part(PART)


def test_its_weight_is_0_so_the_default_profile_has_no_time():
    letters()
    assert "time" not in profile()


def test_a_profile_may_weigh_it(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=[
                "pangloss_dates",
                "pangloss_vectors",
                "pangloss_dates_vectors",
            ],
            VECTORS_PROFILES={"when": {"time": 1, "class": 0.1}},
        )
    )
    letters()
    assert profile("when") == {"time": 1.0, "class": 0.1}


# -- the settings ----------------------------------------------------------------------------------------------------


def test_the_dimension_is_128_and_the_width_2_unless_the_settings_say():
    assert settings.dimension(SimpleNamespace()) == 128
    assert settings.width(SimpleNamespace()) == 2.0
    assert settings.dimension(SimpleNamespace(DATES_VECTOR_DIMENSION=64)) == 64
    assert settings.width(SimpleNamespace(DATES_VECTOR_WIDTH=1)) == 1.0
    assert settings.width(SimpleNamespace(DATES_VECTOR_WIDTH=2.5)) == 2.5
    assert settings.ring(SimpleNamespace()) == maths.Ring(128, 2.0)
    assert settings.ring(
        SimpleNamespace(DATES_VECTOR_DIMENSION=32, DATES_VECTOR_WIDTH=100)
    ) == maths.Ring(32, 100.0)
    letters()
    assert PART.dimension() == 128
    assert PART.ring() == maths.Ring(128, 2.0)


@pytest.mark.parametrize("value", [4, 7, 2049, 4096, 128.0, True, "128", None])
def test_a_dimension_that_is_not_a_whole_number_from_8_to_2048_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match="DATES_VECTOR_DIMENSION is a whole number from 8 to 2048",
    ):
        settings.dimension(SimpleNamespace(DATES_VECTOR_DIMENSION=value))


@pytest.mark.parametrize(
    "value", [0, -1, 0.0, 0.001, 100.5, 1000, float("nan"), True, "2", None]
)
def test_a_width_that_is_not_a_number_from_a_hundredth_to_100_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match="DATES_VECTOR_WIDTH is a number of years from 0.01 to 100",
    ):
        settings.width(SimpleNamespace(DATES_VECTOR_WIDTH=value))


@pytest.mark.parametrize(
    "setting, value",
    [("DATES_VECTOR_DIMENSION", 4), ("DATES_VECTOR_WIDTH", 0)],
)
def test_a_project_with_the_app_installed_has_its_settings_refused_at_initialise(
    project_settings, setting, value
):
    configure(
        project_settings(
            INSTALLED_APPS=[
                "pangloss_dates",
                "pangloss_vectors",
                "pangloss_dates_vectors",
            ],
            **{setting: value},
        )
    )
    with pytest.raises(PanglossInitialisationError, match=setting):
        letters()


def test_a_project_without_the_app_is_not_asked_for_its_settings(project_settings):
    configure(project_settings(DATES_VECTOR_DIMENSION=4))
    letters()


# -- the signature ---------------------------------------------------------------------------------------------------


def test_the_signature_changes_with_the_dimension(project_settings):
    letters()
    before = PART.signature()
    configure(project_settings(DATES_VECTOR_DIMENSION=64))
    assert PART.signature() != before


def test_the_signature_changes_with_the_width(project_settings):
    letters()
    before = PART.signature()
    configure(project_settings(DATES_VECTOR_WIDTH=1))
    assert PART.signature() != before
    # (the same width as a whole number or not is the same)
    configure(project_settings(DATES_VECTOR_WIDTH=2.0))
    assert PART.signature() == before


@no_type_check
def test_the_signature_does_not_change_with_the_classes_and_the_stored_one_with_a_class_left_out(
    project_settings,
):
    """(a date's vector is of its bounds whatever classes there are: a new class makes no rebuild due. A class
    newly left out does, by the signature the store compares, which adds the classes that have no vectors)"""
    from pangloss_vectors import store

    letters()
    before, stored = PART.signature(), store.part_signature(PART)
    configure(project_settings(VECTORS_EXCLUDE=["Letter"]))
    assert PART.signature() == before
    assert store.part_signature(PART) != stored

    from pangloss_models import ModelRegistry

    configure(project_settings())
    ModelRegistry._reset()

    class Person(Entity):
        pass

    class Letter(Document):
        pass

    class Note(Document):
        pass

    initialise()
    assert PART.signature() == before
    assert store.part_signature(PART) == stored


@no_type_check
def test_the_signature_does_not_change_with_another_setting_nor_a_field(
    project_settings,
):
    letters()
    before = PART.signature()
    configure(
        project_settings(
            NAMES_DIMENSION=64, FASTRP_DIMENSION=64, VECTORS_CLASS_DECAY=0.25
        )
    )
    assert PART.signature() == before

    from pangloss_models import ModelRegistry

    ModelRegistry._reset()

    class Person(Entity):
        nickname: str | None = None

    class Letter(Document):
        text: str = ""

    initialise()
    assert PART.signature() == before


# -- whose vector a date is ------------------------------------------------------------------------------------------

BOUNDS = (2268924, 2268924, 2269288, 2269288)


def row(
    holder: str = "s",
    holder_type: str = "Statement",
    held_by_date: bool = False,
    holder_is_item: bool = True,
    precision: str = "year",
    head: str = "f",
    head_type: str = "Factoid",
    kept: bool = True,
    bounds: tuple = BOUNDS,
    path: list | str | None = None,
) -> list:
    """A row as the queries give it (`part._row`)"""
    return [
        "d",
        *bounds,
        precision,
        holder,
        holder_type,
        held_by_date,
        holder_is_item,
        head,
        head_type,
        kept,
        path,
    ]


def test_a_date_of_a_nested_document_counts_for_it_and_for_its_head():
    assert counts_for(row(), {}) == [("f", "Factoid"), ("s", "Statement")]


def test_a_date_a_head_holds_itself_counts_for_it_once():
    assert counts_for(
        row(holder="p", holder_type="Person", head="p", head_type="Person"), {}
    ) == [("p", "Person")]


def test_a_date_held_by_a_wrapper_counts_for_the_head_only():
    assert counts_for(
        row(holder="w", holder_type="InRole", holder_is_item=False), {}
    ) == [("f", "Factoid")]


@pytest.mark.parametrize(
    "given",
    [
        {"held_by_date": True, "holder_is_item": False},
        {"precision": "unknown"},
        {"kept": False},
        {"head": None},
        {"bounds": (None, None, None, None)},
    ],
    ids=[
        "held by a date",
        "only unknown",
        "under a head not kept",
        "with no head",
        "with no bounds",
    ],
)
def test_a_date_counts_for_nothing(given):
    assert counts_for(row(**given), {}) is None


def test_an_item_with_several_dates_has_their_vector_and_an_item_twice_is_one_row():
    dates = Dates({})
    later = tuple(b + 3652 for b in BOUNDS)
    dates.add(row())
    dates.add(row(holder="t", bounds=later))
    [rows] = list(dates.vectors(maths.Ring()))
    found = {r.of: np.asarray(r.vector) for r in rows}
    assert sorted(found) == ["f", "s", "t"]
    ring = maths.Ring()
    assert np.allclose(found["f"], maths.vector([BOUNDS, later], ring))
    assert np.allclose(found["s"], maths.vector([BOUNDS], ring))
    assert np.allclose(found["t"], maths.vector([later], ring))


def test_the_items_are_made_in_batches_with_the_same_vectors(monkeypatch):
    dates = Dates({})
    for n in range(7):
        dates.add(
            row(
                holder=f"s{n}",
                head=f"f{n // 3}",
                bounds=tuple(b + 365 * n for b in BOUNDS),
            )
        )
    whole = {r.of: r.vector for rows in dates.vectors(maths.Ring()) for r in rows}
    batches = list(dates.vectors(maths.Ring(), batch=2))
    assert [len(rows) for rows in batches] == [2, 2, 2, 2, 2]
    assert {r.of: r.vector for rows in batches for r in rows} == whole


@no_type_check
def test_a_class_that_has_no_vectors_is_given_none(project_settings):
    configure(project_settings(VECTORS_EXCLUDE=["Letter"]))
    letters()
    dates = Dates()
    dates.add(row(holder="l", holder_type="Letter", head="p", head_type="Person"))
    dates.add(row(holder="l2", holder_type="Letter", head="l2", head_type="Letter"))
    assert [r.of for rows in dates.vectors(maths.Ring()) for r in rows] == ["p"]


def test_numpy_is_not_imported_with_the_package():
    found = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pangloss_dates_vectors, pangloss_dates_vectors.part, pangloss_dates_vectors.settings; "
            "print('numpy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert found.stdout.strip() == "False"


# -- a date that its path says is denied -----------------------------------------------------------------------------


@no_type_check
def spaces_declared(must: bool = True, **metas) -> dict:
    """Spaces of each kind the walk knows (a "not", a possibility, one that asserts, one that neither asserts nor
    denies, and, with `must`, an epistemic necessity that commits, so that "it cannot have been" is denied), and what
    the walk reads of them. `metas`: a class's `Meta` given otherwise"""
    from pangloss_models import Modal, SemanticSpace
    from pangloss_models.spaces import registered_spaces

    class Negative[T](SemanticSpace[T]):
        _meta = metas.get("Negative", SemanticSpace.Meta(logical="not"))

    class Hypothetical[T](SemanticSpace[T]):
        _meta = metas.get(
            "Hypothetical",
            SemanticSpace.Meta(logical=Modal("possibility", "epistemic")),
        )

    if must:

        class Must[T](SemanticSpace[T]):
            _meta = SemanticSpace.Meta(
                logical=Modal("necessity", "epistemic"), veridical=1
            )

    class Known[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class Reported[T](SemanticSpace[T]):
        _meta = metas.get("Reported", SemanticSpace.Meta(veridical=0, degree="likely"))

    letters()
    return registered_spaces()


def entry(type_name: str, field: str, kind: str = "document") -> dict:
    return {"kind": kind, "type": type_name, "id": type_name.lower(), "field": field}


def space(type_name: str, field: str = "contents") -> dict:
    return entry(type_name, field, kind="space")


FACTOID = entry("Factoid", "statements")
ACTIVITY = entry("Statement", "when")


@pytest.mark.parametrize(
    "path, counts",
    [
        ([], True),
        ([FACTOID, ACTIVITY], True),
        ([FACTOID, space("Known"), ACTIVITY], True),
        ([FACTOID, space("Negative"), ACTIVITY], False),
        ([FACTOID, space("Negative"), space("Negative"), ACTIVITY], True),
        ([FACTOID, space("Reported"), ACTIVITY], True),
        ([FACTOID, space("Reported"), space("Negative"), ACTIVITY], True),
        ([FACTOID, space("Hypothetical"), ACTIVITY], True),
        ([FACTOID, space("Negative"), space("Hypothetical"), ACTIVITY], False),
        (
            [FACTOID, space("Negative"), entry("Service", "parts"), ACTIVITY],
            True,
        ),
        ([FACTOID, space("Negative"), space("Reported", "reported_at")], False),
        ([FACTOID, space("Reported", "reported_at")], True),
        (
            [
                FACTOID,
                space("Negative"),
                entry("Activity", "participants"),
                entry("InRole", "during", kind="reified"),
            ],
            False,
        ),
        (
            [
                FACTOID,
                space("Negative"),
                entry("Service", "parts"),
                entry("Activity", "participants"),
                entry("InRole", "during", kind="reified"),
            ],
            True,
        ),
    ],
    ids=[
        "a head's own date",
        "asserted",
        "in what asserts",
        "denied",
        "not not",
        "reported",
        "reported not",
        "possible",
        "it cannot have been",
        "a part of a service there was not",
        "held by a space in a field of its own, inside a not",
        "held by a space in a field of its own",
        "of a role in an activity there was not",
        "of a role in an activity that is a part of a service there was not",
    ],
)
def test_a_date_its_own_path_says_is_denied_counts_for_nothing_and_any_other_in_full(
    path, counts
):
    spaces = spaces_declared()
    found = counts_for(row(path=path), spaces)
    assert found == ([("f", "Factoid"), ("s", "Statement")] if counts else None)


def test_it_cannot_have_been_is_not_denied_where_no_necessity_commits():
    spaces = spaces_declared(must=False)
    path = [FACTOID, space("Negative"), space("Hypothetical"), ACTIVITY]
    assert counts_for(row(path=path), spaces) is not None


def test_a_path_as_json_text_is_read_as_the_list():
    import json

    spaces = spaces_declared()
    path = [FACTOID, space("Negative"), ACTIVITY]
    assert counts_for(row(path=json.dumps(path)), spaces) is None
    assert counts_for(row(path=json.dumps([FACTOID, ACTIVITY])), spaces) is not None


def test_a_path_that_names_a_space_the_models_do_not_have_fails():
    from pangloss_models.spaces import UnknownSpaceError

    spaces = spaces_declared()
    with pytest.raises(UnknownSpaceError, match="Gone"):
        counts_for(row(path=[FACTOID, space("Gone"), ACTIVITY]), spaces)


def test_a_denied_date_is_not_among_the_dates_of_its_head():
    spaces = spaces_declared()
    dates = Dates(spaces)
    later = tuple(b + 3652 for b in BOUNDS)
    dates.add(row(path=[FACTOID, ACTIVITY]))
    dates.add(
        row(holder="t", bounds=later, path=[FACTOID, space("Negative"), ACTIVITY])
    )
    [rows] = list(dates.vectors(maths.Ring()))
    found = {r.of: np.asarray(r.vector) for r in rows}
    assert sorted(found) == ["f", "s"]
    assert np.allclose(found["f"], maths.vector([BOUNDS], maths.Ring()))


@no_type_check
def test_the_signature_is_as_before_with_no_space_and_changes_with_what_the_walk_reads_of_a_space(
    project_settings,
):
    from pangloss_models import ModelRegistry, Modal, SemanticSpace
    from pangloss_vectors.parts import signature_of

    letters()
    plain = PART.signature()
    # (a project with no space: the signature it had before dates were walked)
    assert plain == signature_of(PART.dimension(), settings.width())

    def again(**metas) -> str:
        ModelRegistry._reset()
        spaces_declared(**metas)
        return PART.signature()

    spaced = again()
    assert spaced != plain
    assert again() == spaced
    # (what decides which paths are denied: a space's `veridical` or `logical`)
    assert again(Reported=SemanticSpace.Meta(veridical=-1)) != spaced
    assert again(Negative=SemanticSpace.Meta(veridical=0)) != spaced
    assert (
        again(Hypothetical=SemanticSpace.Meta(logical=Modal("necessity", "epistemic")))
        != spaced
    )
    # (and not what it does not: a degree, a fit)
    assert again(Reported=SemanticSpace.Meta(veridical=0, degree="possible")) == spaced
    assert (
        again(
            Reported=SemanticSpace.Meta(veridical=0, degree="likely", fit="prescribes")
        )
        == spaced
    )
