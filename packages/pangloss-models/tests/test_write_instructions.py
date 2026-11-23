"""The instructions of one write, as an app declares them and a write says them (`hooks.declare_write_instruction`,
`hooks.checked_instructions`), and the argument in the stubs of `save`"""

import pytest
from pangloss_models import PanglossInstructionError, PanglossModelError, hooks

SUGGEST = hooks.WriteInstruction("suggest", ("true", "false"), "Suggest after it")


@pytest.fixture(autouse=True)
def declared(monkeypatch):
    monkeypatch.setattr(hooks, "write_instructions", {})


def test_the_same_declaration_twice_is_one():
    assert hooks.declare_write_instruction(SUGGEST) is SUGGEST
    hooks.declare_write_instruction(
        hooks.WriteInstruction("suggest", ("true", "false"), "Suggest after it")
    )
    assert hooks.write_instructions == {"suggest": SUGGEST}


def test_a_second_declaration_that_differs_is_refused():
    hooks.declare_write_instruction(SUGGEST)
    with pytest.raises(PanglossModelError, match="'suggest' is declared twice"):
        hooks.declare_write_instruction(
            hooks.WriteInstruction("suggest", ("yes", "no"))
        )
    assert hooks.write_instructions == {"suggest": SUGGEST}


@pytest.mark.parametrize("name", sorted(hooks.WRITE_PARAMETERS))
def test_a_parameter_the_write_routes_have_cannot_be_an_instruction(name):
    with pytest.raises(PanglossModelError, match="already have a parameter"):
        hooks.declare_write_instruction(hooks.WriteInstruction(name, ("x",)))
    assert hooks.write_instructions == {}


@pytest.mark.parametrize("name", ["Suggest", "suggestNow", "suggest-now", "", "_x"])
def test_a_name_not_in_snake_case_is_refused(name):
    with pytest.raises(PanglossModelError, match="snake_case"):
        hooks.declare_write_instruction(hooks.WriteInstruction(name, ("x",)))


def test_an_instruction_with_no_values_is_refused():
    with pytest.raises(PanglossModelError, match="needs the values"):
        hooks.declare_write_instruction(hooks.WriteInstruction("suggest", ()))


def test_nothing_said_is_nothing():
    assert hooks.checked_instructions(None) == {}
    assert hooks.checked_instructions({}) == {}


def test_a_bool_is_its_text_and_text_is_kept():
    hooks.declare_write_instruction(SUGGEST)
    assert hooks.checked_instructions({"suggest": True}) == {"suggest": "true"}
    assert hooks.checked_instructions({"suggest": False}) == {"suggest": "false"}
    assert hooks.checked_instructions({"suggest": "false"}) == {"suggest": "false"}


def test_an_undeclared_name_is_refused_with_what_is_declared():
    with pytest.raises(
        PanglossInstructionError,
        match=r"^'suggest' is no instruction of a write \(the instructions are: none is declared\)$",
    ):
        hooks.checked_instructions({"suggest": True})
    hooks.declare_write_instruction(SUGGEST)
    with pytest.raises(
        PanglossInstructionError,
        match=r"^'sugest' is no instruction of a write \(the instructions are: suggest\)$",
    ):
        hooks.checked_instructions({"sugest": True})


@pytest.mark.parametrize("value", ["maybe", "True", 1, None])
def test_a_value_not_declared_is_refused_with_the_values_there_are(value):
    hooks.declare_write_instruction(SUGGEST)
    with pytest.raises(
        PanglossInstructionError,
        match=rf"^The instruction 'suggest' of a write is one of true, false, not {value!r}$",
    ):
        hooks.checked_instructions({"suggest": value})


def test_the_refusal_is_a_refused_write():
    from pangloss_models import PanglossWriteError

    assert issubclass(PanglossInstructionError, PanglossWriteError)


def test_instructed_kinds_asks_each_function_and_the_later_answer_wins(monkeypatch):
    monkeypatch.setattr(
        hooks,
        "instructed_work",
        [
            lambda model, said: {"a": True, "b": True},
            lambda model, said: {"b": said.get("suggest") == "true"},
        ],
    )
    assert hooks.instructed_kinds(int, {}) == {"a": True, "b": False}
    assert hooks.instructed_kinds(int, {"suggest": "true"}) == {"a": True, "b": True}


@pytest.mark.parametrize(
    "name, is_document", [("Create", True), ("Update", True), ("Create", False)]
)
def test_save_in_the_stubs_takes_instructions(name, is_document):
    from pangloss_models.typestubs import save_methods

    stub = "\n".join(save_methods("Letter", name, "async", is_document=is_document))
    assert (
        stub.count(
            "instructions: _pg_typing.Mapping[str, str | bool] | None = None) ->"
        )
        == 2
    )
