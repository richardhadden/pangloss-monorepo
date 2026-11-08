from pangloss_lsp.hints import hints_in

HINTS = {
    "Person.born_in": {"label": "⇄ born_in_reverse", "tooltip": "the edge back"},
    "Person.friends": {"label": "⇄ friends_reverse"},
}

SOURCE = """\
class Person(Entity):
    name: str
    born_in: Place
    friends: Annotated[
        list[Person],
        RelationConfig(description="x: y"),
    ]
    _meta = Entity.Meta()

    def method(self):
        born_in: int = 1


class Other(Entity):
    born_in: Place
"""


def test_a_relation_field_has_the_name_of_its_edge_back_after_its_line():
    found = hints_in(HINTS, SOURCE, 0, 20)

    assert [(h.line, h.character, h.label) for h in found] == [
        (2, len("    born_in: Place"), "⇄ born_in_reverse"),
        # (the statement goes over several lines: after the last)
        (6, len("    ]"), "⇄ friends_reverse"),
    ]
    assert found[0].tooltip == "the edge back"
    assert found[1].tooltip is None


def test_only_the_fields_of_the_class_that_has_the_hint_are_hinted():
    # (`Other.born_in` has no hint; `born_in` in the method is not a field)
    assert [h.line for h in hints_in(HINTS, SOURCE, 0, 20)] == [2, 6]


def test_only_the_lines_asked_for_are_hinted():
    assert [h.line for h in hints_in(HINTS, SOURCE, 0, 2)] == [2]
    assert hints_in(HINTS, SOURCE, 0, 1) == []


def test_a_line_in_the_brackets_of_a_statement_is_not_a_field():
    text = (
        "class Person(Entity):\n    born_in: Annotated[\n        friends: 1,\n    ]\n"
    )
    assert [h.line for h in hints_in(HINTS, text, 0, 5)] == [3]


def test_no_hints_known_gives_none():
    assert hints_in({}, SOURCE, 0, 20) == []
