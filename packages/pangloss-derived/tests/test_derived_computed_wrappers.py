"""What a computed relation (`Computed()`: the candidates of a description, implementation_docs/matches-criteria.md,
step 6) does to the queries, with no database: a rule follows a path through wrappers only along edges everyone may see,
and a search that leaves wrappers out reads nothing inside a document derived through one of them. Neither is in a
query where the models have nothing for it"""

from typing import Annotated, no_type_check

import pytest
from pangloss_models import (
    Computed,
    Document,
    Entity,
    Match,
    ReifiedRelation,
    initialise,
)
from pangloss_models.search import check_excluded, check_match

from pangloss_derived import (
    DerivedDocument,
    DerivedEdge,
    DerivedFrom,
    DerivedMeta,
    Object,
    Subject,
    Var,
    rule,
)
from pangloss_derived.compile import compile_rule
from pangloss_derived.registry import DerivedRegistry

SEEN = "coalesce(x.seen_by, 'everyone') = 'everyone'"
CONTEXT = ".derived_context, [])"


class Names(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture(autouse=True)
def a_dialect(monkeypatch):
    """The queries are made with a backend's dialect: Memgraph's, with no database behind it"""
    import pangloss_cypher.search_query
    import pangloss_derived.compile
    from pangloss_memgraph.databases.memgraph.dialect import MemgraphDialect

    dialect = MemgraphDialect()
    monkeypatch.setattr(pangloss_derived.compile, "dialect", lambda: dialect)
    monkeypatch.setattr(pangloss_cypher.search_query, "dialect", lambda: dialect)


@no_type_check
def models(*, computed: bool, derived_documents: bool):
    """A gift to someone, or to a description of someone whose candidates the server computes (`computed`); who
    received what, said in a document of someone's own, and in a derived document (`derived_documents`)"""

    class Person(Entity):
        pass

    if computed:

        class Described[T](ReifiedRelation[T]):
            _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)
            target: Annotated[list[T], Computed()] = []

    else:

        class Described[T](ReifiedRelation[T]):
            _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)

    class Other[T](ReifiedRelation[T]):
        pass

    class Transfer(Document):
        given_by: Person
        given_to: list[Person | Described[Person] | Other[Person]]

    class GaveTo(DerivedEdge):
        giver: Annotated[Person, Subject()]
        receiver: Annotated[Person, Object()]

    @rule
    def gave_to(a: Var[Person], b: Var[Person]):
        return GaveTo.Derive(giver=a, receiver=b).when(
            Transfer.Where(given_by=a, given_to=b)
        )

    class Received(Document):
        _meta = Document.Meta(create_directly=False)
        person: Person

    class Own(Document):
        statements: list[Received]

    if derived_documents:

        class DerivedFactoid(Document, DerivedDocument):
            sources: list[DerivedFrom[Transfer]]
            statements: list[Received]

    initialise(bind_database=False)
    return Names(locals())


def rule_query() -> str:
    checked = DerivedRegistry.checked["gave_to"]
    text, _ = compile_rule(checked, checked.seeds[0].node)
    return text


def search_query(model, **match) -> str:
    """People who received something, said by a document (a derived one, where the models have it)"""
    from pangloss_cypher.search_query import build_search_ids_query

    found = Match(
        where={"$incoming": [{"type": "Received", "field": "person"}]}, **match
    )
    text, _ = build_search_ids_query(
        model, check_match(model, found), 10, False, check_excluded(found)
    )
    return text


# --- a rule follows only the computed edges everyone sees --------------------------------------------------------------


@no_type_check
def test_a_rule_through_wrappers_follows_only_edges_everyone_sees_where_some_relation_is_computed():
    models(computed=True, derived_documents=False)
    text = rule_query()
    assert SEEN in text
    # (on the path through the wrappers: the one that reaches the receiver, not the one to the giver)
    (line,) = [line for line in text.splitlines() if SEEN in line]
    assert "relationships(rp_" in line


@no_type_check
def test_with_no_computed_relation_the_rule_is_as_it_was():
    models(computed=False, derived_documents=False)
    assert "seen_by" not in rule_query()


# --- a search that leaves wrappers out reads nothing derived through one ------------------------------------------------


@no_type_check
def test_a_search_that_leaves_wrappers_out_tests_the_context_of_the_head():
    m = models(computed=True, derived_documents=True)
    text = search_query(m.Person, exclude_wrappers=["Described"])
    assert CONTEXT in text
    # (another wrapper left out: the same test, of the names it is given)
    assert CONTEXT in search_query(m.Person, exclude_wrappers=["Other"])


@no_type_check
def test_an_ordinary_search_does_not():
    m = models(computed=True, derived_documents=True)
    assert "derived_context" not in search_query(m.Person)


@no_type_check
def test_with_no_derived_document_class_a_search_that_leaves_wrappers_out_does_not():
    m = models(computed=True, derived_documents=False)
    assert "derived_context" not in search_query(
        m.Person, exclude_wrappers=["Described"]
    )
