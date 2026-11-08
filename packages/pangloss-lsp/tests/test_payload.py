from lsprotocol import types
from pangloss_lsp.completion import complete
from pangloss_lsp.positions import offset_of

SCHEMA = {
    "models": {
        "Person": {
            "kind": "Entity",
            "abstract": False,
            "fields": {
                "name": "literal",
                "born_in": "relation",
                "known_as": "annotated",
            },
        },
        "Place": {"kind": "Entity", "abstract": False, "fields": {}},
        "Agent": {"kind": "Entity", "abstract": True, "fields": {}},
        "InRole[Person]": {"kind": "ReifiedRelation", "abstract": False, "fields": {}},
        "Date": {"kind": "Embedded", "abstract": False, "fields": {"year": "literal"}},
    },
}


def offered(source: str) -> list[str]:
    offset = source.index("|")
    text = source.replace("|", "", 1)
    return [item.label for item in complete(SCHEMA, text, offset)]


def applied(source: str, label: str) -> str:
    offset = source.index("|")
    text = source.replace("|", "", 1)
    (item,) = [i for i in complete(SCHEMA, text, offset) if i.label == label]
    edit = item.text_edit
    assert isinstance(edit, types.TextEdit)
    start, end = offset_of(text, edit.range.start), offset_of(text, edit.range.end)
    return text[:start] + edit.new_text + text[end:]


def test_the_keys_of_the_model_a_payload_names_are_offered_in_camel_case():
    assert offered('payload = {"type": "Person", |') == [
        "label",
        "id",
        "name",
        "bornIn",
        "knownAs",
    ]


def test_a_key_already_given_is_not_offered_again():
    assert "name" not in offered('payload = {"type": "Person", "name": "x", |')
    assert "label" not in offered('payload = {"label": "x", "type": "Person", |')


def test_the_type_may_come_after_the_key_being_typed():
    assert "bornIn" in offered('payload = {"type": "Person", "bo|')


def test_a_key_typed_without_quotes_is_quoted():
    assert applied('payload = {"type": "Person", bor|', "bornIn").endswith(
        '"type": "Person", "bornIn"'
    )


def test_a_key_inside_its_quotes_is_not_quoted_again():
    assert applied('payload = {"type": "Person", "bor|', "bornIn").endswith(
        '"type": "Person", "bornIn'
    )


def test_an_embedded_model_has_no_label_or_id():
    keys = offered('payload = {"type": "Date", |')
    assert "year" in keys and "label" not in keys and "id" not in keys


def test_a_dict_that_does_not_say_what_it_is_is_offered_the_type():
    assert offered("payload = {|") == ["type"]
    assert offered('payload = {"label": "x", |') == ["type"]


def test_the_value_of_a_type_is_the_name_of_a_model():
    # (not an abstract one, and not a generated parametrisation)
    assert offered('payload = {"type": "|') == ["Date", "Person", "Place"]
    assert applied('payload = {"type": Pe|', "Person").endswith('"type": "Person"')
    assert applied('payload = {"type": "Pe|', "Person").endswith('"type": "Person')


def test_the_dict_inside_another_is_its_own():
    source = 'payload = {"type": "Person", "bornIn": {"type": "Place", |}}'
    assert offered(source) == ["label", "id"]


def test_a_dict_in_a_call_is_a_payload_too():
    assert "bornIn" in offered('client.post("/api/Person", json={"type": "Person", |')


def test_what_is_not_a_dict_key_position_is_left_alone():
    # (after the colon of a key that is not `type`, a value is being written)
    assert offered('payload = {"type": "Person", "name": |') == []
    assert offered('payload = ["type", |') == []
    assert offered("payload = {  # |") == []
