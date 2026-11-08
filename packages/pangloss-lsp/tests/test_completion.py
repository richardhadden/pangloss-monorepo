from lsprotocol import types
from pangloss_lsp.completion import (
    complete,
    hover_on_parameter,
    import_edit,
    offset_of,
    resolve_call,
)

SCHEMA = {
    "calls": {
        "DocumentMeta": {
            "doc": None,
            "parameters": [
                {
                    "name": "abstract",
                    "type": "bool",
                    "default": "False",
                    "doc": None,
                    "choices": [["True", False], ["False", False]],
                },
                {
                    "name": "indexes",
                    "type": "list[str]",
                    "default": "[]",
                    "doc": "Fields of this class to keep an index of",
                    "choices": [],
                },
                {
                    "name": "view_extra_fields",
                    "type": "list[str]",
                    "default": "[]",
                    "doc": None,
                    "choices": [],
                },
            ],
        },
        "InterfaceMeta": {
            "doc": "How the interface shows a model",
            "parameters": [
                {
                    "name": "colour",
                    "type": "Colour | None",
                    "default": "None",
                    "doc": None,
                    "choices": [["red", True], ["blue", True]],
                },
                {
                    "name": "view_card",
                    "type": "str | None",
                    "default": "None",
                    "doc": None,
                    "choices": [["pangloss_dates:DateCard", True]],
                },
                {
                    "name": "list_page",
                    "type": "str | Literal[False] | None",
                    "default": "None",
                    "doc": None,
                    "choices": [["False", False], ["app:ListPage", True]],
                },
            ],
        },
        "RelationConfig": {
            "doc": None,
            "parameters": [
                {
                    "name": "reverse_name",
                    "type": "str | None",
                    "default": "None",
                    "doc": None,
                    "choices": [],
                },
                {
                    "name": "default_reified_type",
                    "type": "type | None",
                    "default": "None",
                    "doc": None,
                    "choices": [],
                },
            ],
        },
        "FieldBinding": {
            "doc": None,
            "parameters": [
                {
                    "name": "bound_field",
                    "type": "str",
                    "default": None,
                    "doc": None,
                    "choices": [],
                },
                {
                    "name": "allowed_type_names",
                    "type": "list[str]",
                    "default": "[]",
                    "doc": None,
                    "choices": [],
                },
            ],
        },
    },
    "aliases": {
        "Document.Meta": "DocumentMeta",
        "Entity.Meta": "DocumentMeta",
        "Person.Meta": "DocumentMeta",
    },
    "slots": [
        {
            "name": "_interface_meta",
            "class": "InterfaceMeta",
            "module": "pangloss_interface",
            "doc": "How the interface shows a model",
        },
    ],
    "models": {
        "Person": {
            "kind": "Entity",
            "abstract": False,
            "fields": {
                "name": "literal",
                "tags": "list",
                "born_in": "relation",
                "born": "embedded",
            },
        },
        "Place": {"kind": "Entity", "abstract": False, "fields": {}},
        "InRole": {"kind": "ReifiedRelation", "abstract": False, "fields": {}},
    },
}

HEADER = "from pangloss_models import Entity\n\n\nclass Person(Entity):\n    name: str\n    nickname: str\n"


def labels(source: str) -> list[str]:
    offset = source.index("|")
    text = source.replace("|", "", 1)
    return [item.label for item in complete(SCHEMA, text, offset)]


def edited(source: str, label: str) -> str:
    """The text with the completion of that label applied"""
    offset = source.index("|")
    text = source.replace("|", "", 1)
    (item,) = [i for i in complete(SCHEMA, text, offset) if i.label == label]
    edit = item.text_edit
    assert isinstance(edit, types.TextEdit)
    start = offset_of(text, edit.range.start)
    end = offset_of(text, edit.range.end)
    return text[:start] + edit.new_text + text[end:]


def test_the_options_of_a_meta_are_offered_by_name():
    assert labels(HEADER + "    _meta = Document.Meta(|") == [
        "abstract",
        "indexes",
        "view_extra_fields",
    ]


def test_the_meta_of_a_model_is_the_meta_of_its_kind():
    assert "indexes" in labels(HEADER + "    _meta = Person.Meta(|")


def test_an_option_already_given_is_not_offered_again():
    assert labels(HEADER + "    _meta = Document.Meta(abstract=True, |") == [
        "indexes",
        "view_extra_fields",
    ]


def test_choosing_an_option_replaces_what_was_typed_and_adds_the_equals_sign():
    assert edited(HEADER + "    _meta = Document.Meta(ind|", "indexes").endswith(
        "Document.Meta(indexes="
    )


def test_a_call_that_is_not_known_offers_nothing():
    assert labels(HEADER + "    x = print(|") == []


def test_indexes_offers_the_fields_that_hold_a_value():
    # (not the relation or the embedded object; the field typed since the last run; and the label)
    assert labels(HEADER + "    _meta = Document.Meta(indexes=[|") == [
        "name",
        "tags",
        "nickname",
        "label",
    ]


def test_a_value_is_quoted_unless_the_string_is_already_begun():
    assert edited(HEADER + "    _meta = Document.Meta(indexes=[na|", "name").endswith(
        'indexes=["name"'
    )
    assert edited(HEADER + '    _meta = Document.Meta(indexes=["na|', "name").endswith(
        'indexes=["name'
    )


def test_every_field_is_offered_for_the_options_that_name_one():
    assert labels(HEADER + "    _meta = Document.Meta(view_extra_fields=[|") == [
        "name",
        "tags",
        "born_in",
        "born",
        "nickname",
    ]


def test_the_choices_of_an_option_come_from_the_schema():
    source = HEADER + "    _interface_meta = InterfaceMeta(colour=|"
    assert labels(source) == ["red", "blue"]
    assert edited(source, "red").endswith('colour="red"')


def test_a_value_that_is_not_a_string_is_not_offered_inside_one():
    assert labels(HEADER + '    _interface_meta = InterfaceMeta(list_page="|') == [
        "app:ListPage"
    ]
    assert labels(HEADER + "    _interface_meta = InterfaceMeta(list_page=|") == [
        "False",
        "app:ListPage",
    ]


def test_booleans_are_offered_bare():
    assert edited(HEADER + "    _meta = Document.Meta(abstract=|", "True").endswith(
        "abstract=True"
    )


def test_the_reverse_name_suggested_is_the_one_the_field_would_get():
    source = "class P(Entity):\n    born_in: Annotated[list[Place], RelationConfig(reverse_name=|"
    assert labels(source) == ["born_in_reverse"]
    assert edited(source, "born_in_reverse").endswith('reverse_name="born_in_reverse"')


def test_a_reified_type_is_named_by_its_class_not_as_a_string():
    source = "class P(Entity):\n    f: Annotated[list[X], RelationConfig(default_reified_type=|"
    assert labels(source) == ["InRole"]
    assert edited(source, "InRole").endswith("default_reified_type=InRole")


def test_the_type_names_of_a_binding_are_the_models():
    source = "class P(Entity):\n    f: Annotated[X, RelationConfig(bind_to_child_field=[FieldBinding(allowed_type_names=[|"
    assert labels(source) == ["InRole", "Person", "Place"]


def test_a_slot_is_offered_at_the_start_of_a_line_of_a_class_and_imports_its_class():
    source = HEADER + "    _inter|"
    # (the editor narrows the list by what is typed)
    (item,) = [
        item
        for item in complete(SCHEMA, source.replace("|", "", 1), source.index("|"))
        if item.label == "_interface_meta"
    ]
    edit = item.text_edit
    assert isinstance(edit, types.TextEdit)
    assert edit.new_text == "_interface_meta = InterfaceMeta($0)"
    assert item.insert_text_format == types.InsertTextFormat.Snippet
    assert item.additional_text_edits is not None
    assert (
        item.additional_text_edits[0].new_text
        == "from pangloss_interface import InterfaceMeta\n"
    )
    assert item.additional_text_edits[0].range.start.line == 1


def test_the_meta_of_the_base_class_is_offered_as_meta():
    source = HEADER + "    _|"
    assert labels(source) == ["_meta", "_interface_meta"]
    assert edited(source, "_meta").endswith("    _meta = Entity.Meta($0)")


def test_the_import_is_not_added_if_it_is_there():
    text = (
        "from pangloss_interface import InterfaceMeta\n\n\nclass A(Entity):\n    pass\n"
    )
    assert import_edit(text, "pangloss_interface", "InterfaceMeta") is None
    edit = import_edit("import x\n", "pangloss_interface", "InterfaceMeta")
    assert edit is not None and edit.range.start.line == 1
    assert import_edit("class A(\n", "m", "N") is None


def test_the_import_goes_below_a_docstring_and_the_last_import():
    edit = import_edit(
        '"""Models"""\n\nimport a\nfrom b import (\n    c,\n)\n\nX = 1\n', "m", "N"
    )
    assert edit is not None and edit.range.start.line == 6


def test_the_call_is_found_by_its_alias_its_last_two_names_or_its_last():
    call = resolve_call(SCHEMA, "Document.Meta")
    assert call is not None
    assert call["parameters"][0]["name"] == "abstract"
    assert resolve_call(SCHEMA, "pangloss_models.Document.Meta") is not None
    assert resolve_call(SCHEMA, "pangloss_interface.InterfaceMeta") is not None
    assert resolve_call(SCHEMA, "Other.Meta") is None


def hover(source: str) -> str | None:
    offset = source.index("|")
    return hover_on_parameter(SCHEMA, source.replace("|", "", 1), offset)


def test_hovering_an_option_gives_its_type_default_and_documentation():
    text = hover(HEADER + "    _meta = Document.Meta(ind|exes=['name'])")
    assert text is not None
    assert text.startswith("`indexes: list[str] = []`")
    assert "Fields of this class" in text


def test_hovering_anything_else_gives_nothing():
    assert hover(HEADER + "    _meta = Document.Meta(indexes=['na|me'])") is None
    assert hover(HEADER + "    x = unknown(ab|c=1)") is None
    assert hover(HEADER + "    nam|e: str") is None
