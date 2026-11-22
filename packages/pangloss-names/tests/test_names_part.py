"""The name part without a database (implementation_docs/similarity-build-plan.md, step 8.3): what it is, its
dimension, what its signature depends on and what not, that it is in no profile by itself, how it reads a row of
names, and that numpy waits until it is wanted"""

import subprocess
import sys
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core.settings import configure
from pangloss_models import Document, Entity, initialise
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_names import NamesMeta, settings
from pangloss_names.part import PART, names_of, table_of, table_text
from pangloss_vectors.parts import part, profile, register_part


@no_type_check
def people():
    class Person(Entity):
        nickname: str | None = None

    class Letter(Document):
        pass

    initialise()


def test_the_part_is_registered_as_name_and_refreshes_after_a_write():
    assert part("name") is PART
    assert (PART.name, PART.local, PART.requires, PART.weight) == (
        "name",
        True,
        frozenset(),
        0.0,
    )
    # (the same object again is nothing)
    register_part(PART)


def test_its_weight_is_0_so_the_default_profile_has_no_name():
    people()
    assert "name" not in profile()


def test_a_profile_may_weigh_it(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=["pangloss_vectors", "pangloss_names"],
            VECTORS_PROFILES={"who": {"name": 1}},
        )
    )
    people()
    assert profile("who") == {"name": 1.0}


def test_its_dimension_is_256_unless_the_settings_say():
    assert settings.dimension(SimpleNamespace()) == 256
    assert settings.dimension(SimpleNamespace(NAMES_DIMENSION=64)) == 64
    people()
    assert PART.dimension() == 256


@pytest.mark.parametrize("value", [4, 4096, 2.5, True, "256", None])
def test_a_dimension_that_is_not_a_whole_number_from_8_to_2048_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError, match="NAMES_DIMENSION is a whole number"
    ):
        settings.dimension(SimpleNamespace(NAMES_DIMENSION=value))


def test_with_no_table_of_variants_the_table_is_empty():
    assert settings.variants() == {}
    assert PART.table() == {}


# -- the signature ---------------------------------------------------------------------------------------------------


@no_type_check
def test_the_signature_changes_with_the_name_fields():
    people()
    before = PART.signature()

    from pangloss_models import ModelRegistry

    ModelRegistry._reset()

    class Person(Entity):
        nickname: str | None = None
        _names_meta = NamesMeta(fields=["label", "nickname"])

    class Letter(Document):
        pass

    initialise()
    assert PART.signature() != before


def test_the_signature_changes_with_the_dimension(project_settings):
    people()
    before = PART.signature()
    configure(project_settings(NAMES_DIMENSION=128))
    assert PART.signature() != before


def test_the_signature_changes_with_the_table_of_variants(monkeypatch):
    people()
    before = PART.signature()
    monkeypatch.setattr(
        settings, "variants", lambda settings=None: {"Johannes": ["Hans"]}
    )
    assert PART.table() == {"hans": "johannes"}
    assert PART.signature() != before


@no_type_check
def test_the_signature_does_not_change_with_another_setting_nor_a_class_with_no_names(
    project_settings,
):
    people()
    before = PART.signature()
    configure(project_settings(FASTRP_DIMENSION=64, VECTORS_CLASS_DECAY=0.25))
    assert PART.signature() == before

    from pangloss_models import ModelRegistry

    ModelRegistry._reset()

    class Person(Entity):
        nickname: str | None = None

    class Letter(Document):
        pass

    class Note(Document):
        text: str = ""

    initialise()
    assert PART.signature() == before


# -- what it reads, what it keeps ------------------------------------------------------------------------------------


def test_a_row_s_names_are_those_of_its_class_s_own_fields_with_lists_flattened_and_nulls_left_out():
    named = {"Person": ["label", "aliases"], "Ship": ["label", "nickname"]}
    fields = ["aliases", "label", "nickname"]
    assert names_of("Person", [["Jo", None, "Joe"], "John", "Jack"], fields, named) == [
        "Jo",
        "Joe",
        "John",
    ]
    assert names_of("Ship", [None, "Mary Rose", None], fields, named) == ["Mary Rose"]
    assert names_of("Place", ["x", "y", "z"], fields, named) == []


@no_type_check
def test_a_label_is_a_name_of_a_concrete_class_that_names_it_and_of_an_abstract_one_if_of_any_class_below_it():
    from pangloss_names.meta import named
    from pangloss_names.part import label_is_a_name

    class Agent(Entity):
        _meta = Entity.Meta(abstract=True)

    class Person(Agent):
        pass

    class Ship(Entity):
        name: str = ""
        _names_meta = NamesMeta(fields=["name"])

    class Vessel(Entity):
        _meta = Entity.Meta(abstract=True)

    class Boat(Vessel):
        _names_meta = NamesMeta(include=False)

    class Letter(Document):
        pass

    initialise()
    found = named()
    assert label_is_a_name("Person", found)
    assert label_is_a_name("Agent", found)
    # (a class whose name fields leave out the label; one with no names; and above only those)
    assert not label_is_a_name("Ship", found)
    assert not label_is_a_name("Boat", found)
    assert not label_is_a_name("Vessel", found)
    assert not label_is_a_name("Letter", found)
    assert not label_is_a_name("NoSuchClass", found)


def test_the_table_of_rarity_is_kept_as_json_with_sorted_keys_and_read_back_the_same():
    from pangloss_names.maths import Rarity

    rarity = Rarity.of([["john", "smith"], ["john", "brown"], ["mary", "smith"]])
    text = table_text(rarity)
    assert text == '{"having":{"john":2,"smith":2},"names":3}'
    assert table_of(text) == rarity


def test_numpy_is_not_imported_with_the_package():
    found = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pangloss_names, pangloss_names.part, pangloss_names.meta; print('numpy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert found.stdout.strip() == "False"
