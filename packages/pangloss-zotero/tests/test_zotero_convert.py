"""A Zotero item as the fields of a model"""

import json

from pangloss_zotero.convert import convert, creators_text, item_url, plain
from zotero_support import LIBRARY, make_item


def test_the_fields_of_an_item():
    item = make_item(
        "ABCD1234",
        "letter",
        "Letter to Anne",
        creators=[
            {"creatorType": "author", "firstName": "Joan", "lastName": "Hall"},
            {"creatorType": "recipient", "name": "The Chapter"},
        ],
        language="en",
        abstractNote="About the roof",
        shortTitle="Roof",
        DOI="10.1/x",
    )
    item["version"] = 7

    fields = convert(item, LIBRARY)

    assert fields["zotero_url"] == "https://www.zotero.org/groups/1/items/ABCD1234"
    assert (
        fields["zotero_library"],
        fields["zotero_key"],
        fields["zotero_version"],
    ) == ("groups/1", "ABCD1234", 7)
    assert fields["item_type"] == "letter"
    assert fields["title"] == "Letter to Anne"
    assert fields["short_title"] == "Roof"
    assert fields["creators"] == "Hall, Joan; The Chapter"
    assert fields["date"] == "1742"
    assert fields["language"] == "en"
    assert fields["abstract"] == "About the roof"
    assert fields["label"] == "(Smith, ABCD1234)"
    assert fields["bibliography"] == "Smith, Anne. ABCD1234. 1742."
    # (everything else is kept as Zotero gave it)
    assert json.loads(fields["zotero_data"])["DOI"] == "10.1/x"
    assert json.loads(fields["csl_json"])["id"] == "ABCD1234"
    assert fields["removed_from_zotero"] is None


def test_the_label_is_the_title_if_there_is_no_citation_and_the_key_if_there_is_no_title():
    item = make_item("KKKK")
    del item["citation"]
    assert convert(item, LIBRARY)["label"] == "Title of KKKK"
    item["data"]["title"] = ""
    assert convert(item, LIBRARY)["label"] == "KKKK"


def test_an_item_in_the_trash_is_flagged():
    item = make_item("KKKK", deleted=1)
    assert convert(item, LIBRARY)["removed_from_zotero"] is True


def test_html_becomes_text():
    assert plain("<span>(Smith 1999, <i>p.</i> 3)</span>") == "(Smith 1999, p. 3)"
    assert (
        plain('<div class="x"><div>One &amp; two</div><div>Three</div></div>')
        == "One & two\nThree"
    )
    assert plain("") is None and plain(None) is None


def test_creators_are_last_first_and_a_single_field_name_is_kept():
    assert (
        creators_text(
            [
                {"firstName": "A", "lastName": "B"},
                {"name": "The Guild"},
                {"lastName": "Solo"},
                {},
            ]
        )
        == "B, A; The Guild; Solo"
    )
    assert creators_text([]) is None


def test_the_url_is_the_same_for_the_same_item():
    assert item_url("users/5", "XY") == "https://www.zotero.org/users/5/items/XY"
