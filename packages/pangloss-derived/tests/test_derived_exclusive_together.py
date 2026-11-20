"""`DerivedMeta(exclusive="field")`, with no database: wrappers of one document with the same value of a field are one
alternative together (several places of one unknown person). What the checked rule says of them, its hash, the
refusal of a field that is not a literal, and what the rule's query gives `store.one_of_each` for them"""

import types
from typing import Annotated, no_type_check

import pytest
from pangloss_models import Document, Entity, ReifiedRelation, Var, initialise

from pangloss_derived import (
    DerivedEdge,
    DerivedMeta,
    Object,
    PanglossDerivedError,
    Subject,
    rule,
)
from pangloss_derived import check as check_module
from pangloss_derived.check import rule_hash
from pangloss_derived.compile import compile_rule
from pangloss_derived.declare import exclusive_with, is_exclusive
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.store import one_of_each


@no_type_check
def declared(exclusive):
    """An activity whose participants are people or `Unknown`s; the `Unknown` is exclusive as given; a rule relating
    each two participants"""

    class Person(Entity):
        pass

    class Unknown[T](ReifiedRelation[T]):
        _derived_meta = DerivedMeta(exclusive=exclusive)
        mark: str | None = None
        by: Person | None = None

    class Activity(Document):
        carried_out_by: list[Person | Unknown[Person]]

    class Together(DerivedEdge):
        first: Annotated[Person, Subject()]
        second: Annotated[Person, Object()]

    @rule
    def together(a: Var[Person], b: Var[Person]):
        return Together.Derive(first=a, second=b).when(
            Activity.Where(carried_out_by=a), Activity.Where(carried_out_by=b)
        )

    return Unknown


@no_type_check
def test_a_wrapper_exclusive_by_a_field_is_exclusive_and_named_with_its_field():
    Unknown = declared("mark")
    initialise(bind_database=False)

    assert is_exclusive(Unknown) and exclusive_with(Unknown) == "mark"
    checked = DerivedRegistry.checked["together"]
    assert checked.exclusive == {"Unknown"}
    assert checked.exclusive_with == (("Unknown", "mark"),)


@no_type_check
def test_exclusive_alone_names_no_field_and_the_hash_is_as_it_was(monkeypatch):
    Unknown = declared(True)
    initialise(bind_database=False)

    assert is_exclusive(Unknown) and exclusive_with(Unknown) is None
    checked = DerivedRegistry.checked["together"]
    assert checked.exclusive_with == ()
    hashed = []

    def dumps(value, **options):
        hashed.append(value)
        import json

        return json.dumps(value, **options)

    monkeypatch.setattr(check_module, "json", types.SimpleNamespace(dumps=dumps))
    assert rule_hash(checked) == checked.hash
    (made,) = hashed
    # (the hash of every rule of a project with no such wrapper is what it was before)
    assert "exclusive_with" not in made and made["exclusive"] == ["Unknown"]


@no_type_check
def test_the_field_changes_the_hash_of_the_rule():
    declared(True)
    initialise(bind_database=False)
    alone = DerivedRegistry.checked["together"].hash

    from pangloss_models import ModelRegistry

    ModelRegistry._reset()
    declared("mark")
    initialise(bind_database=False)
    assert DerivedRegistry.checked["together"].hash != alone


@no_type_check
@pytest.mark.parametrize(
    "field, why", [("nothing", "no such field"), ("by", "a relation")]
)
def test_a_field_that_is_not_a_literal_of_the_class_is_refused(field, why):
    declared(field)
    with pytest.raises(
        PanglossDerivedError,
        match=rf"^Unknown: DerivedMeta\(exclusive='{field}'\) names a field by which its wrappers are exclusive"
        rf" together, and Unknown has no literal field `{field}`$",
    ):
        initialise(bind_database=False)


@no_type_check
def test_the_query_gives_the_document_and_the_value_in_the_place_of_such_a_wrapper(
    monkeypatch,
):
    import pangloss_cypher.search_query
    import pangloss_derived.compile
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect

    # (the query is made with a backend's dialect: Memgraph's, with no database behind it)
    dialect = MemgraphDialect()
    monkeypatch.setattr(pangloss_derived.compile, "dialect", lambda: dialect)
    monkeypatch.setattr(pangloss_cypher.search_query, "dialect", lambda: dialect)
    declared("mark")
    initialise(bind_database=False)
    checked = DerivedRegistry.checked["together"]

    text, params = compile_rule(checked, checked.seeds[0].node)
    assert "THEN x.head_node_id + ':' + toString(x.`mark`) ELSE x.id END" in text
    assert "Unknown" in params.values()

    # (`one_of_each` is unchanged: two places of one mark are one wrapper, with one member at most)
    def row(first, second):
        return {
            "through": [["Unknown"], ["Unknown"]],
            "paths": [first, second],
        }

    assert not one_of_each(checked, row(["h:m", "waldauf"], ["h:m", "serntein"]))
    assert one_of_each(checked, row(["h:m", "waldauf"], ["h:m", "waldauf"]))
    assert one_of_each(checked, row(["w1", "waldauf"], ["w2", "serntein"]))
