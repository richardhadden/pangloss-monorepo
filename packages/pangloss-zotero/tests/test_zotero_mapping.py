"""Which class a Zotero item type is written as: declared, never guessed"""

import pytest
from pangloss_models.exceptions import PanglossMetaError
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta, ZoteroObject
from pangloss_zotero.mapping import accepts, build_table

BOOK, LETTER = ZoteroItemType.BOOK, ZoteroItemType.LETTER


def test_with_no_declarations_everything_is_a_zotero_object():
    class TextObject(ZoteroBacked):
        pass

    table = build_table()
    assert table.by_type == {}
    assert table.class_for("book") is ZoteroObject


def test_a_class_stands_for_the_types_it_names():
    class TextObject(ZoteroBacked):
        pass

    class Atlas(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[BOOK, ZoteroItemType.BOOK_SECTION])

    class Letter(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[LETTER])

    table = build_table()
    assert table.describe() == {
        "book": "Atlas",
        "bookSection": "Atlas",
        "letter": "Letter",
    }
    assert table.class_for("manuscript") is ZoteroObject


def test_a_subclass_that_only_inherits_does_not_claim_the_types():
    class Atlas(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK])

    class AtlasOfCities(Atlas):
        pass

    assert build_table().by_type == {"book": Atlas}
    assert AtlasOfCities._zotero_meta == Atlas._zotero_meta


def test_two_classes_for_one_type_need_exactly_one_default():
    class Atlas(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK])

    class Chronicle(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK])

    with pytest.raises(
        PanglossMetaError,
        match="'book' is claimed by Atlas, Chronicle, and none says default",
    ):
        build_table()


def test_a_default_decides_between_two_classes():
    class Atlas(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK], default=True)

    class Chronicle(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK])

    assert build_table().by_type == {"book": Atlas}


def test_two_defaults_for_one_type_are_refused():
    class Atlas(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK], default=True)

    class Chronicle(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[BOOK], default=True)

    with pytest.raises(PanglossMetaError, match="2 of them say default"):
        build_table()


def test_the_fallback_takes_the_types_no_class_claims():
    class TextObject(ZoteroBacked):
        _zotero_meta = ZoteroMeta(fallback=True)

    class Letter(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[LETTER])

    table = build_table()
    assert table.class_for("letter") is Letter
    assert table.class_for("report") is TextObject


def test_two_fallbacks_are_refused():
    class One(ZoteroBacked):
        _zotero_meta = ZoteroMeta(fallback=True)

    class Two(ZoteroBacked):
        _zotero_meta = ZoteroMeta(fallback=True)

    with pytest.raises(
        PanglossMetaError, match="Only one class can be the Zotero fallback"
    ):
        build_table()


def test_a_declaration_that_says_nothing_is_refused():
    class Nothing(ZoteroBacked):
        _zotero_meta = ZoteroMeta()

    with pytest.raises(PanglossMetaError, match="says nothing"):
        build_table()


def test_an_abstract_class_cannot_stand_for_types():
    from pangloss_models.model_bases.entity import Entity

    class Base(ZoteroBacked):
        _meta = Entity.Meta(abstract=True)
        _zotero_meta = ZoteroMeta(item_types=[BOOK])

    with pytest.raises(PanglossMetaError, match="abstract"):
        build_table()


def test_a_class_accepts_the_types_it_stands_for_and_one_that_says_nothing_accepts_all():
    class TextObject(ZoteroBacked):
        pass

    class Atlas(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[BOOK, "someNewType"])

    class AtlasOfCities(Atlas):
        pass

    assert accepts(TextObject, "letter")
    assert accepts(Atlas, "book") and accepts(Atlas, "someNewType")
    assert not accepts(Atlas, "letter")
    assert accepts(AtlasOfCities, "book") and not accepts(AtlasOfCities, "letter")
