"""A wrapper's own relations asked in a `where` (implementation_docs/relation-steps-plan.md, step 2), checked with no
database: `check_values_only` lets through a relation of a wrapper that is not one of its held fields (`InRole.role`,
not `target`), by `is`, `is_any` and `exists` only; the typed `WrapperWhere` has a field for each, and its JSON is
what the check takes"""

from typing import no_type_check
from uuid import UUID

import pytest
from pangloss_models import (
    Compare,
    Conjunction,
    Document,
    EdgeModel,
    Entity,
    Match,
    ModelRegistry,
    PanglossSearchError,
    ReifiedRelation,
    Rel,
    SemanticSpace,
    Text,
    Through,
    ViaEdge,
    initialise,
)
from pangloss_models.search import (
    CheckedCondition,
    CheckedStep,
    check_match,
    conditions_of,
    held_field_names,
)
from pangloss_models.typestubs import TypeRenderer, stub_annotation
from pydantic import BaseModel, ValidationError

BAKER = "0194a1b2-0000-7000-8000-000000000001"
MILLER = "0194a1b2-0000-7000-8000-000000000002"
JOHN = "0194a1b2-0000-7000-8000-000000000003"

OWN = "a relation of a wrapper .* is tested here by 'is', 'is_any' and 'exists' only"
HELD = "only the values of a wrapper .* can be tested here, not what it points at"
# (on a generic wrapper the field of its type variable cannot be searched at all, and `check_where` says so first)
HELD_GENERIC = f"(this relation cannot be searched yet|{HELD})"


class Names(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture
@no_type_check
def m():
    ModelRegistry._reset()

    class Certainty(EdgeModel):
        value: int

    class RoleType(Entity):
        pass

    class Person(Entity):
        pass

    class Negative[T](SemanticSpace[T]):
        about: RoleType | None = None

    class InRole[T](ReifiedRelation[T]):
        role: RoleType | None = None
        rated: list[ViaEdge[RoleType, Certainty]] = []
        n: int = 0

    # (a class below a wrapper that gives its type variable: `target` is still what it holds)
    class JohnRole(InRole[Person]):
        pass

    class Pair[T](Conjunction):
        left: list[T]
        right: list[T]
        by: RoleType | None = None

    class Doc(Document):
        role: list[InRole[Person]]
        john: list[JohnRole]
        pair: list[Pair[InRole[Person]]]
        neg: list[Negative[Person]]
        plain: list[ViaEdge[Person, Certainty]]

    initialise(bind_database=False)
    yield Names(locals())
    ModelRegistry._reset()


def checked(m, where) -> list:
    return check_match(m.Doc, Match(where=where))


def refused(m, where, saying):
    with pytest.raises(PanglossSearchError, match=saying):
        checked(m, where)


def step(field, wrapper, **where):
    """A relation of the document that passes through `wrapper`, which fits `where`"""
    return {field: {"through": [{"type": wrapper, "where": where}]}}


def items_of_step(checked_where) -> list:
    [condition] = checked_where
    [found] = condition.steps
    assert isinstance(found, CheckedStep)
    return found.items


# ---------------------------------------------------------------------------
# What is held, and what is a wrapper's own
# ---------------------------------------------------------------------------


def test_the_held_fields_of_a_wrapper_are_those_of_its_type_variable(m):
    assert held_field_names(m.InRole) == {"target"}
    assert held_field_names(m.JohnRole) == {"target"}
    assert held_field_names(m.Pair) == {"left", "right"}
    assert held_field_names(m.Negative) == {"contents"}


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def test_an_own_relation_is_asked_by_is_is_any_and_exists(m):
    [is_] = items_of_step(checked(m, step("role", "InRole", role={"is": BAKER})))
    assert isinstance(is_, CheckedCondition)
    assert (is_.field, is_.kind, is_.operator, str(is_.value)) == (
        "role",
        "relation",
        "is",
        BAKER,
    )
    [any_] = items_of_step(
        checked(m, step("role", "InRole", role={"is_any": [BAKER, MILLER]}))
    )
    assert (any_.operator, [str(v) for v in any_.value]) == ("is_any", [BAKER, MILLER])
    [exists] = items_of_step(checked(m, step("role", "InRole", role={"exists": False})))
    assert (exists.operator, exists.value) == ("exists", False)
    # (beside the wrapper's values; a list relation of its own; with `is` of the relation the step is on)
    assert (
        len(
            items_of_step(
                checked(m, step("role", "InRole", role={"is": BAKER}, n={"eq": 1}))
            )
        )
        == 2
    )
    checked(m, step("role", "InRole", rated={"is": BAKER}))
    checked(
        m,
        {
            "role": {
                "is": JOHN,
                "through": [{"type": "InRole", "where": {"role": {"is": BAKER}}}],
            }
        },
    )
    # (of a conjunction and a semantic space, their own)
    checked(m, step("pair", "Pair", by={"is": BAKER}))
    checked(m, step("neg", "Negative", about={"exists": True}))


def test_an_own_relation_is_asked_on_a_class_below_a_wrapper_that_gives_the_type(m):
    """(`john: list[JohnRole]`, `class JohnRole(InRole[Person])`: by `$any`, which passes through any wrapper, and by
    the field itself, which is the use of the wrapper the class is below)"""

    def by_any(where):
        return {"$any": {"is": JOHN, "through": [{"type": "JohnRole", "where": where}]}}

    [condition] = checked(m, by_any({"role": {"is": BAKER}}))
    [is_] = condition.steps[0].items
    assert (is_.field, is_.operator) == ("role", "is")
    refused(
        m, by_any({"target": {"is": JOHN}}), "\\$any.through.JohnRole.target: " + HELD
    )
    refused(
        m,
        by_any({"role": {"type": "RoleType"}}),
        f"\\$any.through.JohnRole.role: {OWN}",
    )
    [condition] = checked(m, {"john": {"is": JOHN}})
    assert (condition.field, condition.operator, condition.wrapped) == (
        "john",
        "is",
        True,
    )
    step = {"type": "JohnRole", "where": {"role": {"is": BAKER}}}
    [condition] = checked(m, {"john": {"through": [step]}})
    assert condition.steps[0].model.__name__ == "JohnRole"
    refused(
        m,
        {
            "john": {
                "through": [{"type": "JohnRole", "where": {"target": {"is": JOHN}}}]
            }
        },
        "john.through.JohnRole.target: " + HELD,
    )


def test_an_own_relation_is_not_asked_by_a_pattern_or_its_way(m):
    for role, field in (
        ({"type": "RoleType"}, "role"),
        ({"type": "RoleType", "where": {"label": {"eq": "baker"}}}, "role"),
        (
            {
                "is": BAKER,
                "edge": {"type": "Certainty", "where": {"value": {"gte": 8}}},
            },
            "rated",
        ),
        (
            {
                "is": BAKER,
                "via": [{"type": "Certainty", "where": {"value": {"gte": 8}}}],
            },
            "rated",
        ),
    ):
        refused(
            m,
            step("role", "InRole", **{field: role}),
            f"role.through.InRole.{field}: {OWN}",
        )
    # (`through` on a relation of its own that passes through no wrapper is refused as it is anywhere: a wrapper's own
    # relation through a wrapper, `office: list[Doubt[RoleType]]` on a generic reified relation, is refused by
    # `initialise()` today, "Cannot take a Union of no types")
    refused(
        m,
        step("role", "InRole", role={"is": BAKER, "through": ["Negative"]}),
        "role.through.InRole.role.through: this relation does not pass through",
    )


def test_what_a_wrapper_holds_is_never_asked_of_it(m):
    refused(
        m,
        step("role", "InRole", target={"is": JOHN}),
        "role.through.InRole.target: " + HELD_GENERIC,
    )
    refused(
        m,
        step("role", "InRole", target={"exists": True}),
        "role.through.InRole.target: " + HELD_GENERIC,
    )
    refused(
        m,
        step("pair", "Pair", left={"is": JOHN}),
        "pair.through.Pair.left: " + HELD_GENERIC,
    )
    refused(
        m,
        step("pair", "Pair", right={"exists": True}),
        "pair.through.Pair.right: " + HELD_GENERIC,
    )
    refused(
        m,
        step("neg", "Negative", contents={"is": JOHN}),
        "neg.through.Negative.contents: " + HELD_GENERIC,
    )


def test_an_own_relation_inside_any_of_and_not(m):
    [either] = items_of_step(
        checked(
            m,
            step(
                "role",
                "InRole",
                **{"$any_of": [{"role": {"is": BAKER}}, {"n": {"eq": 3}}]},
            ),
        )
    )
    assert [c.field for c in conditions_of(either)] == ["role", "n"]
    [not_] = items_of_step(
        checked(m, step("role", "InRole", **{"$not": {"role": {"is": BAKER}}}))
    )
    assert [c.field for c in conditions_of(not_)] == ["role"]
    refused(
        m,
        step(
            "role",
            "InRole",
            **{"$any_of": [{"role": {"type": "RoleType"}}, {"n": {"eq": 3}}]},
        ),
        f"role.through.InRole.role: {OWN}",
    )
    refused(
        m,
        step("role", "InRole", **{"$not": {"target": {"is": JOHN}}}),
        "role.through.InRole.target: " + HELD_GENERIC,
    )


def test_in_a_via_item_too(m):
    found = checked(
        m, {"role": {"via": [{"type": "InRole", "where": {"role": {"is": BAKER}}}]}}
    )
    assert [(c.field, c.operator) for c in conditions_of(found)] == [
        ("role", "exists"),
        ("role", "is"),
    ]
    refused(
        m,
        {
            "role": {
                "via": [{"type": "InRole", "where": {"role": {"type": "RoleType"}}}]
            }
        },
        f"role.via.0.InRole.role: {OWN}",
    )


def test_an_edge_model_still_takes_only_its_values(m):
    checked(
        m, {"plain": {"edge": {"type": "Certainty", "where": {"value": {"gte": 8}}}}}
    )
    refused(
        m,
        {"plain": {"edge": {"type": "Certainty", "where": {"role": {"is": BAKER}}}}},
        "Certainty has no field 'role'",
    )
    assert set(m.Certainty.Where.model_fields) == {
        "is_",
        "all_",
        "any_of_",
        "not_",
        "any_",
        "value",
    }


def test_conditions_of_yields_the_relation_condition_of_a_step(m):
    found = checked(
        m,
        {
            "label": {"eq": "x"},
            "role": {
                "is": JOHN,
                "through": [{"type": "InRole", "where": {"role": {"is_any": [BAKER]}}}],
            },
        },
    )
    assert [(c.field, c.operator) for c in conditions_of(found)] == [
        ("label", "eq"),
        ("role", "is"),
        ("role", "is_any"),
    ]


# ---------------------------------------------------------------------------
# The typed forms
# ---------------------------------------------------------------------------


def test_the_where_of_a_wrapper_has_its_own_relations_and_not_what_it_holds(m):
    assert {"role", "rated", "n"} <= set(m.InRole.Where.model_fields)
    assert {"role", "rated", "n"} <= set(m.JohnRole.Where.model_fields)
    assert "by" in m.Pair.Where.model_fields
    assert "about" in m.Negative.Where.model_fields
    for wrapper, held in (
        (m.InRole, "target"),
        (m.JohnRole, "target"),
        (m.Pair, "left"),
        (m.Pair, "right"),
        (m.Negative, "contents"),
    ):
        assert held not in wrapper.Where.model_fields


@no_type_check
def test_an_own_relation_is_written_as_an_id_what_has_one_or_rel(m):
    baker = m.RoleType.ReferenceView(type="RoleType", id=UUID(BAKER), label="baker")
    # (an id, or anything with one: `is`)
    assert m.InRole.Where(role=baker).to_json() == {"role": {"is": UUID(BAKER)}}
    assert m.InRole.Where(role=UUID(BAKER)).to_json() == {"role": {"is": UUID(BAKER)}}
    assert m.InRole.Where(role=BAKER).to_json() == {"role": {"is": UUID(BAKER)}}
    assert m.InRole.Where(role=Rel(is_=baker)).to_json() == {
        "role": {"is": UUID(BAKER)}
    }
    assert m.InRole.Where(role=Rel(is_any=[baker, MILLER])).to_json() == {
        "role": {"is_any": [UUID(BAKER), UUID(MILLER)]}
    }
    assert m.InRole.Where(role=Rel(exists=False)).to_json() == {
        "role": {"exists": False}
    }
    assert m.InRole.Where(rated=baker, n=Compare[int](eq=1)).to_json() == {
        "rated": {"is": UUID(BAKER)},
        "n": {"eq": 1},
    }
    # (in a `Through`, and from there into the relation's condition, which the check takes)
    through = m.Doc.Where(
        role=Rel(
            is_=JOHN, through=[Through(m.InRole, where=m.InRole.Where(role=baker))]
        )
    )
    assert through.to_json() == {
        "role": {
            "is": UUID(JOHN),
            "through": [{"type": "InRole", "where": {"role": {"is": UUID(BAKER)}}}],
        }
    }
    [condition] = check_match(m.Doc, Match(where=through))
    [own] = condition.steps[0].items
    assert (own.field, own.operator, own.value) == ("role", "is", UUID(BAKER))
    # (combined, as any `Where`)
    either = m.InRole.Where(role=baker) | m.InRole.Where(n=Compare[int](eq=3))
    assert either.to_json() == {
        "$any_of": [{"role": {"is": UUID(BAKER)}}, {"n": {"eq": 3}}]
    }
    check_match(
        m.Doc,
        Match(where=m.Doc.Where(role=Rel(through=[Through(m.InRole, where=~either)]))),
    )


@no_type_check
def test_a_pattern_or_a_held_field_is_refused_by_the_typed_where(m):
    with pytest.raises(ValidationError, match="not by a pattern"):
        m.InRole.Where(role=m.RoleType.Where(label=Text(eq="baker")))
    with pytest.raises(ValidationError):
        m.InRole.Where(target=JOHN)
    with pytest.raises(ValidationError):
        m.Pair.Where(left=JOHN)
    # (what `Rel` has besides is checked when the pattern is: refused there)
    with pytest.raises(PanglossSearchError, match=OWN):
        check_match(
            m.Doc,
            Match(
                where=m.Doc.Where(
                    role=Rel(
                        through=[
                            Through(
                                m.InRole,
                                where=m.InRole.Where(
                                    role=Rel(match=m.RoleType.Where())
                                ),
                            )
                        ]
                    )
                )
            ),
        )


def test_the_stub_of_an_own_relation_says_rel_or_an_id_or_what_has_one(m):
    field = m.InRole.Where.model_fields["role"]
    assert stub_annotation(field) == Rel | UUID | BaseModel | None
    written = TypeRenderer("here", {}).render(stub_annotation(field))
    assert "Rel" in written and "UUID" in written and "BaseModel" in written
