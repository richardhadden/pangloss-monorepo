"""`Degree()` (`pangloss_models.markers`), the degree entered on a semantic space: the checks at `initialise()`
(`check_degree_fields`, each refusal by its message), the marker kept on the literal field's definition and exported,
and the degree written into the space's entry of the path of what the space holds, and nowhere else.
(Each refused class has a name of its own)"""

from typing import Annotated, Literal, no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    DEGREE_STEPS,
    Degree,
    DegreeStep,
    Document,
    Embedded,
    Modal,
    PanglossModelError,
    SemanticSpace,
    export_models,
    initialise,
)
from pangloss_models.context import spaces_of
from pangloss_models.diagnostics import check_models
from pangloss_models.markers import degree_field


def refused() -> str:
    with pytest.raises(PanglossModelError) as raised:
        initialise(bind_database=False)
    return str(raised.value)


# --- the checks ---------------------------------------------------------------------------------------------------


def test_the_marker_is_kept_on_the_literal_field_s_definition_required_or_optional():
    class MaybeSo[T](SemanticSpace[T]):
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class SurelyGiven[T](SemanticSpace[T]):
        how: Annotated[DegreeStep, Degree()]

    class Inherits[T](MaybeSo[T]):
        pass

    initialise(bind_database=False)
    assert MaybeSo._meta.fields["how_likely"].markers == (Degree(),)
    assert degree_field(MaybeSo._meta.fields) == "how_likely"
    assert degree_field(SurelyGiven._meta.fields) == "how"
    assert degree_field(Inherits._meta.fields) == "how_likely"
    assert degree_field({}) is None


def test_degree_on_a_class_that_is_not_a_space_is_refused():
    class Rumour(Document):
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    assert refused() == (
        "Rumour.how_likely: Degree() is for a field of a semantic space class (the degree of what the space "
        "holds), and Rumour is not one"
    )


def test_degree_on_an_embedded_class_is_refused():
    class Likeliness(Embedded):
        step: Annotated[DegreeStep, Degree()]

    assert refused().startswith(
        "Likeliness.step: Degree() is for a field of a semantic space class"
    )


def test_two_marked_fields_on_one_space_are_refused():
    class TwiceLikely[T](SemanticSpace[T]):
        how_likely: Annotated[DegreeStep | None, Degree()] = None
        how_sure: Annotated[DegreeStep | None, Degree()] = None

    assert refused() == (
        "TwiceLikely: 2 fields are marked Degree() (how_likely, how_sure): a space has one degree, so one field "
        "at most is marked"
    )


def test_a_second_marked_field_in_a_subclass_is_refused_by_the_subclass_s_name_at_its_field():
    class OnceLikely[T](SemanticSpace[T]):
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class AgainLikely[T](OnceLikely[T]):
        how_sure: Annotated[DegreeStep | None, Degree()] = None

    assert refused().startswith(
        "AgainLikely: 2 fields are marked Degree() (how_likely, how_sure)"
    )
    (diagnostic,) = check_models()
    assert diagnostic.message.startswith("AgainLikely: 2 fields")
    assert diagnostic.file == __file__
    line = open(__file__).read().splitlines()[diagnostic.line - 1]
    assert line.strip().startswith("how_sure:")


@pytest.mark.parametrize(
    "annotation, shown",
    [
        (Literal["low", "high"], "Literal['low', 'high']"),
        (
            Literal["impossible", "unlikely", "possible", "likely"],
            "Literal['impossible', 'unlikely', 'possible', 'likely']",
        ),
        (str, "str"),
        (float, "float"),
        (list[DegreeStep], "list[Literal["),
        (DegreeStep | int, "Literal["),
    ],
)
def test_a_marked_field_of_another_type_is_refused_saying_what_to_write(
    annotation, shown
):
    class WrongDegree[T](SemanticSpace[T]):
        how_likely: Annotated[annotation, Degree()]  # ty: ignore[invalid-type-form]

    message = refused()
    assert message.startswith(
        f"WrongDegree.how_likely: Degree() is on a field of the type {shown}"
    )
    assert (
        "a degree is one of the five steps 'impossible', 'unlikely', 'possible', 'likely', 'expected'. Write "
        "`how_likely: Annotated[DegreeStep | None, Degree()] = None` (`DegreeStep` from pangloss_models), or "
        "`DegreeStep` alone for a degree always given"
    ) in message


def test_the_five_steps_in_another_order_are_taken():
    class Reordered[T](SemanticSpace[T]):
        how_likely: Annotated[
            Literal["expected", "likely", "possible", "unlikely", "impossible"] | None,
            Degree(),
        ] = None

    initialise(bind_database=False)
    assert degree_field(Reordered._meta.fields) == "how_likely"


def test_degree_on_an_asserted_space_is_refused():
    class Reported[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(veridical=1)
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    assert refused() == (
        "Reported.how_likely: Degree() on a space whose contents are asserted (veridical=1): a degree is only of "
        "contents neither asserted nor denied. Take Degree() off the field, or the field out"
    )


def test_degree_on_a_not_is_refused():
    class Denied[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    assert refused().startswith(
        "Denied.how_likely: Degree() on a space whose contents are denied (logical='not')"
    )


def test_a_subclass_that_becomes_a_not_with_the_field_inherited_is_refused_by_its_own_name():
    class Possibly[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class NotPossibly[T](Possibly[T]):
        _meta = SemanticSpace.Meta(logical="not")

    assert refused().startswith(
        "NotPossibly.how_likely: Degree() on a space whose contents are denied (logical='not')"
    )
    # (said at what the subclass changed, its `_meta`, since it does not declare the field)
    (diagnostic,) = check_models()
    assert diagnostic.message.startswith("NotPossibly.how_likely")
    line = open(__file__).read().splitlines()[diagnostic.line - 1]
    assert line.strip().startswith('_meta = SemanticSpace.Meta(logical="not")')


def test_a_fault_inherited_whole_is_the_parent_s_alone():
    class Rumoured(Document):
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class RumouredAgain(Rumoured):
        pass

    messages = [d.message for d in check_models()]
    assert len(messages) == 1
    assert messages[0].startswith("Rumoured.how_likely")


def test_a_space_with_a_degree_field_and_a_class_default_passes():
    class Hypothetical[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("possibility", "epistemic"), degree="possible"
        )
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    initialise(bind_database=False)
    assert Hypothetical._meta.degree == "possible"


# --- the export ---------------------------------------------------------------------------------------------------


def test_the_marked_field_is_exported_as_a_literal_with_its_marker():
    class Hypothetical[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class P(Document):
        pass

    class F(Document):
        statements: list[Hypothetical[P]]

    initialise(bind_database=False)
    (field,) = [
        f
        for f in export_models()["models"]["Hypothetical"]["fields"]
        if f["name"] == "how_likely"
    ]
    assert field["kind"] == "literal"
    assert field["key"] == "howLikely"
    # (in any order: `typing` caches a `Literal` by its values as a set, so another test's `Literal` of the same steps
    # in another order may be the one this field has)
    assert field["type"]["type"] == "literal"
    assert sorted(field["type"]["values"]) == sorted(DEGREE_STEPS)
    assert field["markers"] == [{"name": "Degree"}]
    assert field["nullable"] is True and field["required"] is False


# --- the path of an instance about to be written ------------------------------------------------------------------


@no_type_check
def declare():
    class P(Document):
        pass

    class Service(Document):
        parts: list[P]

    class Hypothetical[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("possibility", "epistemic"), degree="possible"
        )
        how_likely: Annotated[DegreeStep | None, Degree()] = None

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(
            logical=Modal("necessity", "command"), degree="likely"
        )

    class Factoid(Document):
        statements: list[
            P | Service | Hypothetical[P | Service | Hypothetical[P]] | Ordered[P]
        ]

    initialise(bind_database=False)
    return Factoid


def hypothetical(degree: str | None, *contents) -> dict:
    space = {"type": "Hypothetical", "contents": list(contents)}
    if degree is not None:
        space["how_likely"] = degree
    return space


def p(label: str) -> dict:
    return {"type": "P", "label": label}


def statement_db(*statements, update: bool = False):
    factoid = declare()
    payload = {"label": "Factoid", "statements": list(statements)}
    if update:
        return factoid.Update(id=uuid7(), **payload)._to_db_model()
    return factoid.Create(**payload)._to_db_model()


def degrees(node) -> list[tuple[str, str | None]]:
    return [(entry["type"], entry.get("degree")) for entry in node.context_path]


@pytest.mark.parametrize("update", [False, True])
def test_a_statement_in_a_space_with_a_degree_has_it_in_that_space_s_entry_only(
    update,
):
    db = statement_db(
        hypothetical("likely", {"type": "Service", "label": "s", "parts": [p("part")]}),
        update=update,
    )
    space = db.statements[0]
    service = space.contents[0]
    part = service.parts[0]
    assert space.how_likely == "likely"
    assert db.context_path == []
    assert degrees(space) == [("Factoid", None)]
    assert degrees(service) == [("Factoid", None), ("Hypothetical", "likely")]
    assert service.context_path[-1] == {
        "kind": "space",
        "type": "Hypothetical",
        "id": str(space.id),
        "field": "contents",
        "degree": "likely",
    }
    assert degrees(part) == [
        ("Factoid", None),
        ("Hypothetical", "likely"),
        ("Service", None),
    ]
    assert "degree" not in part.context_path[-1]
    assert part.semantic_spaces == spaces_of(part.context_path) == ["Hypothetical"]


def test_a_space_in_a_space_each_has_its_own_degree():
    db = statement_db(hypothetical("unlikely", hypothetical("expected", p("inner"))))
    outer = db.statements[0]
    inner = outer.contents[0]
    leaf = inner.contents[0]
    assert degrees(inner) == [("Factoid", None), ("Hypothetical", "unlikely")]
    assert degrees(leaf) == [
        ("Factoid", None),
        ("Hypothetical", "unlikely"),
        ("Hypothetical", "expected"),
    ]
    assert leaf.semantic_spaces == ["Hypothetical", "Hypothetical"]


def test_no_degree_entered_gives_no_key_and_the_class_default_is_not_written():
    db = statement_db(hypothetical(None, p("bare")))
    space = db.statements[0]
    assert space.how_likely is None
    (_, entry) = space.contents[0].context_path
    assert entry == {
        "kind": "space",
        "type": "Hypothetical",
        "id": str(space.id),
        "field": "contents",
    }


def test_a_space_without_the_field_gives_no_key_whatever_its_default():
    db = statement_db({"type": "Ordered", "contents": [p("ordered")]})
    (_, entry) = db.statements[0].contents[0].context_path
    assert entry["type"] == "Ordered"
    assert "degree" not in entry
    assert db.statements[0].contents[0].semantic_spaces == ["Ordered"]


def test_a_value_not_a_step_is_refused_as_any_literal_is():
    factoid = declare()
    with pytest.raises(ValueError, match="how_likely"):
        factoid.Create(label="Factoid", statements=[hypothetical("probable", p("x"))])


def test_a_path_read_back_with_or_without_a_degree_is_taken_as_it_is():
    """A path stored before the marker was put on has no `degree` until its document is written again (D18): it is
    read as it is, and one with a degree keeps it"""
    from pangloss_models import PathEntry
    from pydantic import TypeAdapter

    entries = TypeAdapter(list[PathEntry])
    old = [{"kind": "space", "type": "Hypothetical", "id": "s", "field": "contents"}]
    new = [{**old[0], "degree": "likely"}]
    assert entries.validate_python(old) == old
    assert entries.validate_python(new) == new
    assert spaces_of(old) == spaces_of(new) == ["Hypothetical"]
