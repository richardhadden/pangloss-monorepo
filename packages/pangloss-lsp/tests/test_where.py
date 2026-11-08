from pangloss_lsp.completion import complete, hover_on_parameter
from pangloss_lsp.positions import offset_of

SCHEMA = {
    "models": {
        "Person": {
            "kind": "Entity",
            "abstract": False,
            "fields": {},
            "where": [
                {"name": "all_", "type": "list[PersonWhere] | None"},
                {"name": "label", "type": "Text | None"},
                {"name": "born_in", "type": "Rel | PlaceWhere | None"},
                {"name": "not_", "type": "PersonWhere | None"},
            ],
        },
        "Place": {
            "kind": "Entity",
            "abstract": False,
            "fields": {},
            "where": [{"name": "label", "type": "Text | None"}],
        },
    },
}


def offered(source: str) -> list[str]:
    offset = source.index("|")
    text = source.replace("|", "", 1)
    return [item.label for item in complete(SCHEMA, text, offset)]


def test_the_fields_of_the_model_come_before_the_dollar_keys():
    assert offered("Person.Where(|") == ["label", "born_in", "all_", "not_"]


def test_a_keyword_already_given_is_not_offered_again():
    assert offered('Person.Where(label=Text(contains="x"), |') == [
        "born_in",
        "all_",
        "not_",
    ]


def test_the_where_inside_a_relation_is_of_the_model_it_names():
    assert offered("Person.Where(born_in=Place.Where(|") == ["label"]


def test_a_partly_typed_keyword_is_replaced_and_given_its_equals_sign():
    source = "Person.Where(bo|"
    offset = source.index("|")
    text = source.replace("|", "")
    (item,) = [i for i in complete(SCHEMA, text, offset) if i.label == "born_in"]
    assert item.text_edit is not None
    assert item.text_edit.new_text == "born_in="
    assert offset_of(text, item.text_edit.range.start) == len("Person.Where(")


def test_nothing_is_offered_where_a_value_goes_or_for_an_unknown_model():
    assert offered("Person.Where(label=|") == []
    assert offered("Nobody.Where(|") == []
    assert offered("Where(|") == []


def test_a_where_has_no_option_hover_of_a_meta():
    text = "Person.Where(label=1)"
    assert hover_on_parameter(SCHEMA, text, text.index("label")) is None
