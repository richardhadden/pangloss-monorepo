"""What each kind of change does to a stored version (no database): conversions of values,
nullability, enum members, relation targets and cardinality, and the problems each reports"""

import pytest
from pangloss_history.upgrade import Unconvertible, apply_migrations, convert_value
from pangloss_models.meta_kit.migrations import changes as c
from pangloss_models.meta_kit.migrations.files import Migration


def literal(name, type="str", nullable=False, **more):
    return {
        "name": name,
        "kind": "literal",
        "type": {"type": type, **more},
        "nullable": nullable,
        "required": True,
    }


def enum_field(name, enum="Colour"):
    return {
        "name": name,
        "kind": "literal",
        "type": {"type": "enum", "enum": enum},
        "nullable": False,
        "required": True,
    }


def list_field(name, item):
    return {
        "name": name,
        "kind": "list",
        "item": item,
        "nullable": False,
        "required": True,
    }


def relation(name, many=False):
    return {
        "name": name,
        "kind": "relation",
        "many": many,
        "nullable": False,
        "required": True,
        "options": [],
    }


COLOUR = {
    "name": "Colour",
    "members": [{"name": "RED", "value": "red"}, {"name": "BLUE", "value": "blue"}],
}


def state(*fields, enums=None):
    return {
        "version": 1,
        "models": {
            "Note": {
                "name": "Note",
                "kind": "Document",
                "labels": ["Note", "Document"],
                "fields": list(fields),
            },
            "Person": {
                "name": "Person",
                "kind": "Entity",
                "labels": ["Person", "Entity"],
                "fields": [],
            },
            "Place": {
                "name": "Place",
                "kind": "Entity",
                "labels": ["Place", "Entity"],
                "fields": [],
            },
        },
        "enums": enums or {"Colour": COLOUR},
    }


def upgrade(data, fields, *changes, enums=None):
    note = {"type": "Note", "id": "1", "label": "n", **data}
    migration = Migration(app="letters", name="0002", changes=tuple(changes))
    return apply_migrations(note, state(*fields, enums=enums), [migration])


def kinds(result):
    return [(p.kind, p.path, p.blocking) for p in result.problems]


# --- converting values ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "old, new, value, expected",
    [
        ("str", "int", " 42 ", 42),
        ("str", "float", "1.5", 1.5),
        ("str", "bool", "True", True),
        ("str", "bool", "false", False),
        ("str", "decimal", "2.50", "2.50"),
        ("str", "date", "0800-12-25", "0800-12-25"),
        ("int", "float", 3, 3.0),
        ("int", "str", 3, "3"),
        ("float", "str", 1.5, "1.5"),
        ("int", "decimal", 3, "3"),
        ("int", "bool", 0, False),
        ("float", "int", 2.9, 2),
        ("decimal", "int", "2.9", 2),
        ("bool", "str", True, "true"),
        ("bool", "int", False, 0),
        ("decimal", "str", "1.10", "1.10"),
        ("date", "str", "0800-12-25", "0800-12-25"),
        ("decimal", "float", "1.25", 1.25),
        ("str", "str", "same", "same"),
    ],
)
def test_a_value_is_converted_as_the_cypher_of_the_migration_does(
    old, new, value, expected
):
    assert convert_value({"type": old}, {"type": new}, value, {}) == expected


@pytest.mark.parametrize(
    "old, new, value",
    [
        ("str", "int", "four"),
        ("str", "bool", "yes"),
        ("str", "decimal", "x"),
        ("str", "date", "Christmas"),
        ("date", "int", "0800-12-25"),
        ("bool", "date", True),
    ],
)
def test_a_value_that_cannot_be_converted_says_so(old, new, value):
    with pytest.raises(Unconvertible):
        convert_value({"type": old}, {"type": new}, value, {})


def test_values_become_members_of_an_enum_by_value_or_by_a_mapping():
    enums = {
        "Colour": COLOUR,
        "Hue": {
            "name": "Hue",
            "members": [{"name": "RED", "value": 1}, {"name": "GREEN", "value": 2}],
        },
    }
    to_colour = {"type": "enum", "enum": "Colour"}
    assert convert_value({"type": "str"}, to_colour, "blue", enums) == "blue"
    assert (
        convert_value({"type": "str"}, to_colour, "crimson", enums, {"crimson": "RED"})
        == "red"
    )
    with pytest.raises(Unconvertible, match="not a value of Colour"):
        convert_value({"type": "str"}, to_colour, "green", enums)

    # (from one enum to another: by the names of the members, and a mapping of names)
    to_hue = {"type": "enum", "enum": "Hue"}
    assert convert_value(to_colour, to_hue, "red", enums) == 1
    assert convert_value(to_colour, to_hue, "blue", enums, {"BLUE": "GREEN"}) == 2
    assert convert_value(to_colour, {"type": "str"}, "red", enums) == "red"
    with pytest.raises(Unconvertible, match="enum to int"):
        convert_value(to_colour, {"type": "int"}, "red", enums)


def test_a_change_of_type_converts_and_reports_what_it_cannot():
    change = c.AlterLiteralType(
        model="Note", name="pages", old={"type": "str"}, new={"type": "int"}
    )
    assert upgrade({"pages": "12"}, [literal("pages")], change).data["pages"] == 12

    result = upgrade({"pages": "twelve"}, [literal("pages")], change)
    assert result.data["pages"] == "twelve"
    assert kinds(result) == [("type-changed", "pages", True)]
    assert result.problems[0].old_value == "twelve"

    # (an empty value stays empty)
    assert (
        upgrade({"pages": None}, [literal("pages", nullable=True)], change).problems
        == []
    )


@pytest.mark.parametrize("on_failure, expected", [("null", None), ("default", 0)])
def test_what_cannot_be_converted_can_be_emptied_or_given_the_default(
    on_failure, expected
):
    change = c.AlterLiteralType(
        model="Note",
        name="pages",
        old={"type": "str"},
        new={"type": "int"},
        on_failure=on_failure,
        default=0,
    )
    result = upgrade({"pages": "twelve"}, [literal("pages")], change)
    assert result.data["pages"] == expected and result.problems == []


def test_the_items_of_a_list_are_converted_one_by_one():
    change = c.AlterListItemType(
        model="Note", name="years", old={"type": "str"}, new={"type": "int"}
    )
    result = upgrade(
        {"years": ["800", "x", "801"]}, [list_field("years", {"type": "str"})], change
    )
    assert result.data["years"] == [800, "x", 801]
    assert kinds(result) == [("type-changed", "years", True)]


# --- nullability, fields -----------------------------------------------------------------------


def test_a_field_that_may_no_longer_be_empty_takes_the_default_or_is_a_problem():
    with_default = c.AlterNullability(
        model="Note", name="title", nullable=False, default="untitled"
    )
    assert (
        upgrade({"title": None}, [literal("title", nullable=True)], with_default).data[
            "title"
        ]
        == "untitled"
    )

    without = c.AlterNullability(model="Note", name="title", nullable=False)
    assert kinds(
        upgrade({"title": None}, [literal("title", nullable=True)], without)
    ) == [("missing-required", "title", True)]
    # (becoming nullable changes nothing)
    became = c.AlterNullability(model="Note", name="title", nullable=True)
    assert upgrade({"title": None}, [literal("title")], became).problems == []


def test_an_added_field_is_given_its_default_an_empty_list_or_none_or_is_a_problem():
    def added(name, field_kind, definition, needs_value=False):
        return c.AddField(
            model="Note",
            name=name,
            field_kind=field_kind,
            definition=definition,
            needs_value=needs_value,
        )

    result = upgrade(
        {},
        [],
        added("tags", "list", list_field("tags", {"type": "str"})),
        added("people", "relation", relation("people", many=True)),
        added("subtitle", "literal", literal("subtitle", nullable=True)),
        added("pages", "literal", literal("pages", "int"), needs_value=True),
    )
    assert (
        result.data["tags"] == []
        and result.data["people"] == []
        and result.data["subtitle"] is None
    )
    assert "pages" not in result.data
    assert kinds(result) == [("missing-required", "pages", True)]


def test_a_removed_field_is_reported_but_does_not_block_and_an_absorbed_one_is_left():
    removed = upgrade(
        {"old": "x"},
        [literal("old")],
        c.RemoveField(model="Note", name="old", field_kind="literal"),
    )
    assert "old" not in removed.data and kinds(removed) == [
        ("removed-field", "old", False)
    ]

    absorbed = c.RemoveField(
        model="Note", name="old", field_kind="literal", absorbed=True
    )
    assert upgrade({"old": "x"}, [literal("old")], absorbed).problems == []


# --- enums -----------------------------------------------------------------------------------------


def test_the_value_of_a_member_changes_in_fields_and_lists():
    change = c.AlterEnumMemberValue(enum="Colour", member="RED", old="red", new="rouge")
    result = upgrade(
        {"colour": "red", "colours": ["blue", "red"]},
        [
            enum_field("colour"),
            list_field("colours", {"type": "enum", "enum": "Colour"}),
        ],
        change,
    )
    assert result.data["colour"] == "rouge" and result.data["colours"] == [
        "blue",
        "rouge",
    ]


def test_a_removed_member_is_replaced_or_reported():
    replaced = upgrade(
        {"colour": "red"},
        [enum_field("colour")],
        c.RemoveEnumMember(enum="Colour", member="RED", replacement="BLUE"),
    )
    assert replaced.data["colour"] == "blue" and replaced.problems == []

    gone = upgrade(
        {"colour": "red"},
        [enum_field("colour")],
        c.RemoveEnumMember(enum="Colour", member="RED"),
    )
    assert gone.data["colour"] == "red"
    assert kinds(gone) == [("type-changed", "colour", True)]

    # (a value that is not the member is left alone)
    other = upgrade(
        {"colour": "blue"},
        [enum_field("colour")],
        c.RemoveEnumMember(enum="Colour", member="RED"),
    )
    assert other.problems == []


# --- relations ---------------------------------------------------------------------------------------


PERSON = {"type": "Person", "id": "p", "label": "Ann"}
PLACE = {"type": "Place", "id": "q", "label": "Rome"}


def test_a_target_no_longer_allowed_is_removed_or_reported():
    fields = [relation("about", many=True)]
    removed = upgrade(
        {"about": [PERSON, PLACE]},
        fields,
        c.AlterRelationTarget(
            model="Note", name="about", removed=["Place"], on_narrowing="remove"
        ),
    )
    assert removed.data["about"] == [PERSON]
    assert kinds(removed) == [("removed-field", "about", False)]

    refused = upgrade(
        {"about": [PERSON, PLACE]},
        fields,
        c.AlterRelationTarget(model="Note", name="about", removed=["Place"]),
    )
    assert refused.data["about"] == [PERSON, PLACE]
    assert kinds(refused) == [("reference-not-allowed", "about", True)]

    # (one, not a list: removed, it is empty)
    single = upgrade(
        {"about": PLACE},
        [relation("about")],
        c.AlterRelationTarget(
            model="Note", name="about", removed=["Place"], on_narrowing="remove"
        ),
    )
    assert single.data["about"] is None

    # (only adding targets changes nothing)
    added = c.AlterRelationTarget(model="Note", name="about", added=["Place"])
    assert upgrade({"about": [PERSON]}, fields, added).problems == []


def test_one_becomes_many_and_many_becomes_one():
    to_many = c.AlterCardinality(model="Note", name="about", many=True)
    assert upgrade({"about": PERSON}, [relation("about")], to_many).data["about"] == [
        PERSON
    ]
    assert upgrade({"about": None}, [relation("about")], to_many).data["about"] == []

    to_one = c.AlterCardinality(model="Note", name="about", many=False)
    assert (
        upgrade({"about": [PERSON]}, [relation("about", True)], to_one).data["about"]
        == PERSON
    )
    assert (
        upgrade({"about": []}, [relation("about", True)], to_one).data["about"] is None
    )

    several = upgrade({"about": [PERSON, PLACE]}, [relation("about", True)], to_one)
    assert kinds(several) == [("cardinality-changed", "about", True)]
    keep_first = c.AlterCardinality(
        model="Note", name="about", many=False, keep="first"
    )
    assert (
        upgrade({"about": [PERSON, PLACE]}, [relation("about", True)], keep_first).data[
            "about"
        ]
        == PERSON
    )


def test_problems_say_which_migration_and_can_be_written_as_json():
    result = upgrade(
        {"title": None},
        [literal("title", nullable=True)],
        c.AlterNullability(model="Note", name="title", nullable=False),
    )
    assert result.problems[0].to_dict() == {
        "kind": "missing-required",
        "message": "Note.title may no longer be empty, and this version has no value",
        "blocking": True,
        "path": "title",
        "migration": "letters.0002",
    }
