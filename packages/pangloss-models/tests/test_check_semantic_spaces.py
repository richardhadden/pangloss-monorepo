"""The checks at `initialise()` of what a semantic space class says of its contents (`check_semantic_spaces`): each
refusal by its message and its fix (the edit of the class's `_meta`, read from this file), what is allowed, and the
warning of flavours that differ only in case. (Each refused class has a name of its own: a fix finds its class in the
source by name)"""

import ast
import warnings
from pathlib import Path

import pytest
from pangloss_models import (
    Modal,
    PanglossModelError,
    PanglossModelWarning,
    SemanticSpace,
    initialise,
)
from pangloss_models.diagnostics import FIXES, Fix


def refused(model: type) -> tuple[str, Fix]:
    with pytest.raises(PanglossModelError) as raised:
        initialise(bind_database=False)
    assert raised.value.fix is not None
    fix = FIXES[raised.value.fix](model, "_meta")  # ty: ignore[invalid-argument-type]
    assert fix is not None
    return str(raised.value), fix


def applied(fix: Fix, model: type) -> str:
    """The class's `_meta` statement in this file as it would be after the fix (as `ast` writes it)"""
    (edit,) = fix.edits
    assert edit.file == __file__
    lines = Path(__file__).read_text().splitlines(keepends=True)
    start = sum(len(line) for line in lines[: edit.line - 1]) + edit.column
    end = sum(len(line) for line in lines[: edit.end_line - 1]) + edit.end_column
    text = "".join(lines)
    assert text[start:end] == edit.old_text
    tree = ast.parse(text[:start] + edit.new_text + text[end:])
    (node,) = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == model.__name__
    ]
    (statement,) = [
        s
        for s in node.body
        if isinstance(s, ast.Assign) and getattr(s.targets[0], "id", None) == "_meta"
    ]
    return ast.unparse(statement)


def passes() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", PanglossModelWarning)
        initialise(bind_database=False)


# --- the refusals -------------------------------------------------------------------------------------------


def test_a_not_with_veridical_other_than_minus_one_is_refused():
    class NotButSo[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not", veridical=0)

    message, fix = refused(NotButSo)
    assert message.startswith("NotButSo: logical='not' with veridical=0")
    assert "what is under a 'not' is denied" in message
    assert fix.title == "Leave out `veridical`"
    assert applied(fix, NotButSo) == "_meta = SemanticSpace.Meta(logical='not')"


def test_a_possibility_with_veridical_other_than_zero_is_refused():
    class MightBeSo[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("possibility", "epistemic"), veridical=1
        )

    message, fix = refused(MightBeSo)
    assert message.startswith(
        'MightBeSo: logical=Modal("possibility", "epistemic") with veridical=1'
    )
    assert "neither asserted nor denied" in message
    assert fix.title == "Leave out `veridical`"
    assert (
        applied(fix, MightBeSo)
        == "_meta = SemanticSpace.Meta(logical=Modal('possibility', 'epistemic'))"
    )


def test_a_possibility_of_not_with_veridical_minus_one_is_refused_as_a_possibility():
    class MightNotBe[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            veridical=-1, logical=Modal("possibility", "deontic", of_not=True)
        )

    message, fix = refused(MightNotBe)
    assert message.startswith(
        'MightNotBe: logical=Modal("possibility", "deontic", of_not=True) with veridical=-1: what may be so'
    )
    assert "only what is necessarily not" not in message
    assert fix.title == "Leave out `veridical`"
    assert (
        applied(fix, MightNotBe)
        == "_meta = SemanticSpace.Meta(logical=Modal('possibility', 'deontic', of_not=True))"
    )


def test_minus_one_on_a_necessity_that_is_not_of_not_is_refused():
    class OrderedDenied[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command"), veridical=-1)

    message, fix = refused(OrderedDenied)
    assert message.startswith(
        'OrderedDenied: logical=Modal("necessity", "command") with veridical=-1'
    )
    assert "only what is necessarily not" in message
    assert fix.title == "Leave out `veridical`"
    assert (
        applied(fix, OrderedDenied)
        == "_meta = SemanticSpace.Meta(logical=Modal('necessity', 'command'))"
    )


def test_one_on_a_necessity_of_not_is_refused():
    class ForbiddenButDone[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command", of_not=True), veridical=1
        )

    message, fix = refused(ForbiddenButDone)
    assert message.startswith(
        'ForbiddenButDone: logical=Modal("necessity", "command", of_not=True) with veridical=1'
    )
    assert "necessarily not is not asserted" in message
    assert fix.title == "Leave out `veridical`"
    assert (
        applied(fix, ForbiddenButDone)
        == "_meta = SemanticSpace.Meta(logical=Modal('necessity', 'command', of_not=True))"
    )


def test_unary_false_on_a_not_is_refused():
    class NotOfMany[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(unary=False, logical="not")

    message, fix = refused(NotOfMany)
    assert message.startswith("NotOfMany: logical='not' with unary=False")
    assert "neither is denied by itself" in message
    assert fix.title == "Leave out `unary`"
    assert applied(fix, NotOfMany) == "_meta = SemanticSpace.Meta(logical='not')"


def test_unary_false_on_a_modal_of_not_is_refused():
    class ForbiddenOfMany[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command", of_not=True), unary=False
        )

    message, fix = refused(ForbiddenOfMany)
    assert message.startswith(
        'ForbiddenOfMany: logical=Modal("necessity", "command", of_not=True) with unary=False'
    )
    assert fix.title == "Leave out `unary`"
    assert (
        applied(fix, ForbiddenOfMany)
        == "_meta = SemanticSpace.Meta(logical=Modal('necessity', 'command', of_not=True))"
    )


def test_a_degree_of_what_is_asserted_is_refused():
    class SurelyLikely[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1, degree="likely")

    message, fix = refused(SurelyLikely)
    assert message.startswith(
        "SurelyLikely: degree='likely', but its contents are asserted (veridical=1)"
    )
    assert "a degree is only of contents neither asserted nor denied" in message
    assert fix.title == "Leave out `degree`"
    assert applied(fix, SurelyLikely) == "_meta = SemanticSpace.Meta(veridical=1)"


def test_a_degree_of_what_a_not_denies_is_refused():
    class NotLikely[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(degree="unlikely", logical="not")

    message, fix = refused(NotLikely)
    assert message.startswith(
        "NotLikely: degree='unlikely', but its contents are denied (logical='not')"
    )
    assert fix.title == "Leave out `degree`"
    assert applied(fix, NotLikely) == "_meta = SemanticSpace.Meta(logical='not')"


def test_a_meta_of_one_refused_value_is_left_empty():
    class OnlyAsserted[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class OnlyAssertedChild[T](OnlyAsserted[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    message, fix = refused(OnlyAssertedChild)
    assert message.startswith("OnlyAssertedChild: logical='not' with veridical=1")
    assert applied(fix, OnlyAssertedChild) == "_meta = SemanticSpace.Meta()"


def test_a_value_left_out_of_a_meta_written_over_lines_takes_its_comma_with_it():
    class NotOverLines[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            veridical=1,
            logical="not",
        )

    _, fix = refused(NotOverLines)
    assert fix.edits[0].old_text.strip() == "veridical=1,"
    assert applied(fix, NotOverLines) == "_meta = SemanticSpace.Meta(logical='not')"


def test_the_only_value_of_a_meta_written_over_lines_is_left_out_whole():
    class NotAlone[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class NotAloneChild[T](NotAlone[T]):
        _meta = SemanticSpace.Meta(
            unary=False,
        )

    _, fix = refused(NotAloneChild)
    assert fix.edits[0].new_text == ""
    assert applied(fix, NotAloneChild) == "_meta = SemanticSpace.Meta()"


# --- what a subclass inherits -------------------------------------------------------------------------------


def test_a_subclass_contradicting_a_value_it_inherits_is_refused_by_its_own_name():
    class Asserted[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class AssertedNot[T](Asserted[T]):
        _meta = SemanticSpace.Meta(logical="not")

    message, fix = refused(AssertedNot)
    assert message.startswith("AssertedNot: logical='not' with veridical=1")
    assert "Asserted:" not in message
    # (left out, it would still be inherited: it is written in)
    assert fix.title == "Add `veridical=-1`"
    assert (
        applied(fix, AssertedNot)
        == "_meta = SemanticSpace.Meta(logical='not', veridical=-1)"
    )


def test_a_value_that_would_still_be_wrong_if_inherited_is_changed_not_left_out():
    class AssertedAgain[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)

    class AssertedAgainNot[T](AssertedAgain[T]):
        _meta = SemanticSpace.Meta(logical="not", veridical=0)

    message, fix = refused(AssertedAgainNot)
    assert message.startswith("AssertedAgainNot: logical='not' with veridical=0")
    assert fix.title == "Change to `veridical=-1`"
    assert (
        applied(fix, AssertedAgainNot)
        == "_meta = SemanticSpace.Meta(logical='not', veridical=-1)"
    )


def test_a_fault_a_subclass_inherits_whole_is_reported_of_the_parent():
    class WrongNot[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not", veridical=1)

    class WrongNotPrescribed[T](WrongNot[T]):
        _meta = SemanticSpace.Meta(fit="prescribes")

    message, _ = refused(WrongNot)
    assert message.startswith("WrongNot: ")
    # (the subclass, checked by itself, would not be refused for it)
    from pangloss_models.initialise_models.check_semantic_spaces import (
        check_semantic_space,
    )

    check_semantic_space(WrongNotPrescribed, WrongNot)
    with pytest.raises(PanglossModelError, match="WrongNotPrescribed: "):
        check_semantic_space(WrongNotPrescribed, None)


def test_an_inherited_space_with_an_unary_of_its_own_is_refused():
    class ForbiddenFamily[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command", of_not=True))

    class ForbiddenPair[T](ForbiddenFamily[T]):
        _meta = SemanticSpace.Meta(unary=False)

    message, fix = refused(ForbiddenPair)
    assert message.startswith("ForbiddenPair: ")
    assert applied(fix, ForbiddenPair) == "_meta = SemanticSpace.Meta()"


# --- what is allowed ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("veridical", [1, 0, -1, None])
@pytest.mark.parametrize("unary", [True, False, None])
def test_a_space_with_no_logic_takes_any_veridical_and_unary(veridical, unary):
    class Free[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=veridical, unary=unary)

    passes()


@pytest.mark.parametrize("veridical", [1, 0, None])
def test_a_necessity_may_be_asserted_or_not(veridical):
    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), veridical=veridical
        )

    passes()


@pytest.mark.parametrize("veridical", [-1, 0, None])
def test_a_necessity_of_not_may_be_denied_or_not(veridical):
    class Forbidden[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command", of_not=True), veridical=veridical
        )

    passes()


@pytest.mark.parametrize(
    "logical",
    [
        None,
        "not",
        Modal("necessity", "command"),
        Modal("necessity", "command", of_not=True),
        Modal("possibility", "epistemic"),
        Modal("possibility", "epistemic", of_not=True),
    ],
)
def test_unary_true_is_allowed_anywhere(logical):
    class One[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=logical, unary=True)

    passes()


@pytest.mark.parametrize(
    "logical", [Modal("necessity", "command"), Modal("possibility", "epistemic")]
)
def test_unary_false_is_allowed_on_a_modal_that_is_not_of_not(logical):
    class Many[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=logical, unary=False)

    passes()


@pytest.mark.parametrize(
    "values",
    [
        {"logical": Modal("possibility", "epistemic")},
        {"logical": Modal("possibility", "epistemic"), "veridical": 0},
        {"veridical": 0},
        {},
    ],
)
def test_a_degree_is_allowed_of_what_is_neither_asserted_nor_denied(values):
    class Weighed[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(degree="likely", **values)

    passes()


def test_a_family_whose_subclasses_change_one_value_each_passes():
    class Commanded[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            fit="prescribes", logical=Modal("necessity", "command"), degree="likely"
        )

    class Requested[T](Commanded[T]):
        _meta = SemanticSpace.Meta(degree="possible")

    class Prohibited[T](Commanded[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command", of_not=True))

    passes()


# --- flavours that differ only in case ----------------------------------------------------------------------


def test_flavours_that_differ_only_in_case_are_warned_of_once_with_their_classes():
    class Royal[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "Command"))

    class RoyalForbidden[T](Royal[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "Command", of_not=True))

    class Papal[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command"))

    class PapalRequest[T](Papal[T]):
        _meta = SemanticSpace.Meta(degree="possible")

    class Episcopal[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "COMMAND"))

    class Wished[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "wish"))

    with pytest.warns(PanglossModelWarning) as caught:
        initialise(bind_database=False)

    (warning,) = [w for w in caught if "differ only in case" in str(w.message)]
    message = str(warning.message)
    assert "'COMMAND' and 'Command' and 'command'" in message
    assert "'COMMAND' by Episcopal" in message
    # (a subclass of the same flavour is not named apart from the class that set it)
    assert "'Command' by Royal;" in message
    assert "'command' by Papal)" in message
    assert "Wished" not in message
    assert warning.message.model is Episcopal  # ty: ignore[unresolved-attribute]
    assert warning.message.member == "_meta"  # ty: ignore[unresolved-attribute]


def test_flavours_that_are_the_same_give_no_warning():
    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command"))

    class AlsoOrdered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "command"))

    class OrderedChild[T](Ordered[T]):
        _meta = SemanticSpace.Meta(degree="likely")

    passes()
