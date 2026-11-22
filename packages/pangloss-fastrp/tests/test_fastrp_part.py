"""The graph part without a database (implementation_docs/similarity-build-plan.md, step 3.3): what it is, its cap,
what a write plan is laid out as for an overlay, and that numpy waits until it is wanted"""

import subprocess
import sys
import uuid
from collections import Counter
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_cypher.write_functions import to_db_model
from pangloss_cypher.write_plan import plan_create
from pangloss_fastrp.cypher_reader import RememberingReader
from pangloss_fastrp.maps import graph_maps
from pangloss_fastrp.maths import Edge, Node
from pangloss_fastrp.memory import MemoryReader
from pangloss_fastrp.part import PART, _AsIfIn, in_groups, laid_out, stop_class
from pangloss_fastrp.settings import refresh_cap
from pangloss_fastrp.testing import WORLD_MAPS
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_testing.similar_models import declare
from pangloss_vectors.parts import part


def test_the_part_is_registered_as_graph_and_refreshes_after_a_write():
    assert part("graph") is PART
    assert (PART.name, PART.local, PART.requires, PART.weight) == (
        "graph",
        True,
        frozenset(),
        1.0,
    )


def test_its_dimension_and_signature_are_those_of_the_settings_and_the_maps():
    declare()
    assert PART.dimension() == 128
    from pangloss_fastrp.maps import signature

    assert PART.signature() == signature()


def test_the_cap_of_a_refresh_is_50_000_nodes_unless_the_settings_say():
    assert refresh_cap(SimpleNamespace()) == 50_000
    assert refresh_cap(SimpleNamespace(FASTRP_REFRESH_CAP=10)) == 10


@pytest.mark.parametrize("value", [0, -1, 2.5, True, "100"])
def test_a_cap_that_is_not_a_whole_number_of_1_or_more_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError, match="FASTRP_REFRESH_CAP is a whole number"
    ):
        refresh_cap(SimpleNamespace(FASTRP_REFRESH_CAP=value))


def test_numpy_is_not_imported_with_the_package():
    found = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, pangloss_fastrp, pangloss_fastrp.part; print('numpy' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert found.stdout.strip() == "False"


def test_a_reader_as_if_in_gives_its_nodes_in_and_the_others_as_they_are():
    base = MemoryReader(
        [
            Node("a", "Factoid", deleted=True, published=False),
            Node("b", "Person", merged_into="c"),
            Node("c", "Person", deleted=True),
        ],
        [Edge("a", "b", "of")],
    )
    found = {n.id: n for n in _AsIfIn(base, ["a", "b"]).nodes(["a", "b", "c"])}
    assert found["a"] == Node("a", "Factoid")
    assert found["b"] == Node("b", "Person")
    assert found["c"] == Node("c", "Person", deleted=True)
    assert list(_AsIfIn(base, ["a"]).out_edges(["a"])) == [Edge("a", "b", "of")]


@no_type_check
def test_a_plan_is_laid_out_as_its_nodes_and_the_forward_edges_of_each_name_of_a_relation():
    m = declare()
    ada, dee, york, cited = (str(uuid.uuid4()) for _ in range(4))
    instance = to_db_model(
        m.Factoid.Create(
            label="a meeting",
            statements=[
                {
                    "type": "Activity",
                    "label": "Ada met Dee",
                    "carried_out_by": {"type": "Person", "id": ada},
                    "participants": [
                        {
                            "type": "InRole",
                            "role": "guest",
                            "at": {"type": "Place", "id": york},
                            "target": [{"type": "Person", "id": dee}],
                        }
                    ],
                },
                {
                    "type": "Inference",
                    "label": "so",
                    "evidence": [{"type": "Transfer", "id": cited}],
                },
                {
                    "type": "Transfer",
                    "label": "someone gave to Ada",
                    "given_by": {
                        "type": "MatchesCriteria",
                        "criteria": {"type": "Person", "where": {}},
                    },
                    "given_to": {"type": "Person", "id": ada},
                },
            ],
        )
    )
    graph = graph_maps()
    nodes, edges = laid_out(plan_create(instance), {}, {}, False, graph.citations)
    by_type = {}
    for node in nodes:
        by_type.setdefault(node.type, []).append(node)
    activity, inference, transfer = (str(s.id) for s in instance.statements)
    [role] = by_type["InRole"]
    [citation] = by_type["PGCitation"]
    [described] = by_type["MatchesCriteria"]
    # (every node of the document takes the head's `published`)
    assert {n.published for n in nodes} == {False}
    assert citation.cites == cited
    found = {(e.source, e.target, e.field) for e in edges}
    assert {
        (str(instance.id), activity, "statements"),
        (activity, ada, "carried_out_by"),
        # (the parent field it subclasses: an edge of each name)
        (activity, ada, "involves"),
        (activity, role.id, "participants"),
        (role.id, dee, "target"),
        (role.id, york, "at"),
        (inference, citation.id, "evidence"),
        (transfer, described.id, "given_by"),
        (transfer, ada, "given_to"),
    } <= found
    # (a description has no candidates until its worker has run)
    assert not [e for e in edges if e.source == described.id]


# ---------------------------------------------------------------------------
# An unknown laid out as an entity (step 10.2b)
# ---------------------------------------------------------------------------


@pytest.fixture
def mention_stands_in():
    """`Mention`, a stand-in of the test's own for a person, that names its class"""
    from pangloss_models import hooks

    stand_in = hooks.StandIn(
        document="Mention",
        stands_for=lambda model: model.__name__ == "Person",
        named_type="stands_for",
    )
    hooks.stand_ins.append(stand_in)
    yield
    hooks.stand_ins.remove(stand_in)


@no_type_check
def declare_mentions():
    """A letter to people, of whom one may be a mention; a mention has a place it was seen at and notes of its own"""
    from pangloss_models import Document, Entity, initialise

    class Agent(Entity):
        _meta = Entity.Meta(abstract=True)

    class Person(Agent):
        pass

    class Group(Agent):
        pass

    class Place(Entity):
        pass

    class Note(Document):
        pass

    class Mention(Document):
        _meta = Document.Meta(create_directly=False)
        stands_for: str
        seen_at: Place | None = None
        notes: list[Note] = []

    class Letter(Document):
        recipients: list[Person]

    initialise()
    return Letter


@no_type_check
def test_an_unknown_is_laid_out_as_a_published_entity_reached_as_in_the_plan_and_nothing_of_it_below(
    mention_stands_in,
):
    Letter = declare_mentions()
    ada, york = str(uuid.uuid4()), str(uuid.uuid4())
    instance = to_db_model(
        Letter.Create(
            label="a letter",
            recipients=[
                {"type": "Person", "id": ada},
                {
                    "type": "Mention",
                    "label": "Ivo",
                    "stands_for": "Person",
                    "seen_at": {"type": "Place", "id": york},
                    "notes": [{"type": "Note", "label": "a note"}],
                },
            ],
        )
    )
    mention = instance.recipients[1]
    graph = graph_maps()
    nodes, edges = laid_out(
        plan_create(instance),
        {},
        {},
        False,
        graph.citations,
        {str(mention.id): "Person"},
    )
    head = str(instance.id)
    assert {n.id: n for n in nodes} == {
        head: Node(head, "Letter", published=False),
        str(mention.id): Node(str(mention.id), "Person", published=True),
    }
    assert {(e.source, e.target, e.field) for e in edges} == {
        (head, ada, "recipients"),
        (head, str(mention.id), "recipients"),
    }
    # (without it, the mention is the document it is, with what it holds)
    nodes, edges = laid_out(plan_create(instance), {}, {}, False, graph.citations)
    assert {n.type for n in nodes} == {"Letter", "Mention", "Note"}
    assert (str(mention.id), york, "seen_at") in {
        (e.source, e.target, e.field) for e in edges
    }


@no_type_check
def test_an_unknown_is_laid_out_as_its_class_or_for_an_abstract_class_the_first_concrete_one_below_it(
    mention_stands_in,
):
    declare_mentions()
    graph = graph_maps()
    assert stop_class("Person", graph) == "Person"
    # (`Agent` is abstract: of `Group` and `Person`, the first by name)
    assert "Agent" not in graph.kinds
    assert stop_class("Agent", graph) == "Group"
    assert stop_class("NoSuchClass", graph) is None


@no_type_check
def test_an_unknown_of_a_class_out_of_the_graph_is_laid_out_as_nothing():
    from pangloss_fastrp import FastRPMeta
    from pangloss_models import Entity, initialise

    class Person(Entity):
        _fastrp_meta = FastRPMeta(include=False)

    initialise()
    assert stop_class("Person", graph_maps()) is None


# ---------------------------------------------------------------------------
# A batch in groups (step 7a.1)
# ---------------------------------------------------------------------------


def test_a_batch_too_large_is_tried_in_halves_in_order_down_to_one():
    """Too large above three units: 10 → 5, 5 → 2, 3 → 1, 2 …; the unit `"f"` is too large even alone"""
    tried: list[str] = []

    def attempt(group):
        tried.append("".join(group))
        if len(group) > 3 or "f" in group:
            return None
        return "".join(group)

    made, alone = in_groups(list("abcdefghij"), attempt)
    assert tried == [
        "abcdefghij",
        "abcde",
        "ab",
        "cde",
        "fghij",
        "fg",
        "f",
        "g",
        "hij",
    ]
    assert made == ["ab", "cde", "g", "hij"]
    assert alone == ["f"]


def test_a_batch_that_fits_is_one_attempt_and_no_units_none():
    tried = []

    def attempt(group):
        tried.append(list(group))
        return len(group)

    assert in_groups(list("abcdefg"), attempt) == ([7], [])
    assert tried == [list("abcdefg")]
    assert in_groups([], attempt) == ([], [])
    assert len(tried) == 1


def test_every_unit_too_large_alone_is_returned_as_failed_in_order():
    made, alone = in_groups(list("abc"), lambda group: None)
    assert (made, alone) == ([], list("abc"))


class CountingReader(RememberingReader):
    """A `RememberingReader` whose database is a `MemoryReader`: each query answered from it, every id asked
    counted by the query"""

    def __init__(self, graph: MemoryReader, heads: dict[str, str], most: int):
        super().__init__(None, None, WORLD_MAPS, most)
        self.graph, self.heads = graph, heads
        self.asked: Counter = Counter()

    def _run(self, query, **parameters):
        from pangloss_fastrp import cypher_reader as q

        ids = parameters["ids"]
        name = {
            q.NODES_QUERY: "nodes",
            q.OUT_QUERY: "out",
            q.IN_QUERY: "in",
            q.CITING_QUERIES[0]: "citing",
            q.CITING_QUERIES[1]: "citing (unprotected)",
            q.BELOW_QUERY: "below",
        }[query]
        self.asked.update((name, i) for i in ids)
        g = self.graph
        if name == "nodes":
            return [
                {
                    "id": n.id,
                    "type": n.type,
                    "head": None,
                    "deleted": n.deleted,
                    "merged_into": n.merged_into,
                    "published": n.published,
                    "cites": n.cites,
                    "head_type": None,
                    "head_deleted": None,
                    "head_published": None,
                }
                for n in g.nodes(ids)
            ]
        if name in ("out", "in"):
            edges = g.out_edges(ids) if name == "out" else g.in_edges(ids)
            return [
                {
                    "source": e.source,
                    "target": e.target,
                    "field": e.field,
                    "properties": e.properties,
                }
                for e in edges
            ]
        if name == "citing":
            return [{"id": c, "of": n} for n in ids for c in g.citing([n])]
        if name == "below":
            return [
                {"id": i, "of": h}
                for h in ids
                for i, of in self.heads.items()
                if of == h
            ]
        return []


def small_graph() -> tuple[MemoryReader, dict[str, str]]:
    graph = MemoryReader(
        [
            Node("f", "Factoid"),
            Node("s", "Event"),
            Node("ann", "Person"),
            Node("bob", "Person"),
            Node("c", "PGCitation", cites="s"),
            Node("g", "Factoid"),
        ],
        [
            Edge("f", "s", "statements"),
            Edge("s", "ann", "by"),
            Edge("s", "bob", "to"),
            Edge("g", "c", "evidence"),
        ],
    )
    return graph, {"s": "f", "c": "g"}


def every_read(reader, ids):
    return (
        sorted(n.id for n in reader.nodes(ids)),
        sorted((e.source, e.target) for e in reader.out_edges(ids)),
        sorted((e.source, e.target) for e in reader.in_edges(ids)),
        list(reader.citing(ids)),
        list(reader.below(ids)),
    )


def test_a_remembering_reader_asks_the_database_for_an_id_once_for_each_of_its_five_reads():
    graph, heads = small_graph()
    reader = CountingReader(graph, heads, most=100)
    first = every_read(reader, ["f", "s", "ann"])
    again = every_read(reader, ["s", "f", "bob", "nobody"])
    assert first == (
        ["ann", "f", "s"],
        [("f", "s"), ("s", "ann"), ("s", "bob")],
        [("f", "s"), ("s", "ann")],
        ["c"],
        ["s"],
    )
    assert again == (
        ["bob", "f", "s"],
        [("f", "s"), ("s", "ann"), ("s", "bob")],
        [("f", "s"), ("s", "bob")],
        ["c"],
        ["s"],
    )
    reads = ("nodes", "out", "in", "citing", "citing (unprotected)", "below")
    # (each id once for each read, whether it was found or not)
    assert reader.asked == Counter(
        (read, i) for read in reads for i in ("f", "s", "ann", "bob", "nobody")
    )
    # (`seen` has every node given)
    assert set(reader.seen) == {"f", "s", "ann", "bob"}
    assert reader.forgotten == 0


def test_past_its_bound_a_remembering_reader_forgets_and_still_answers_rightly():
    graph, heads = small_graph()
    reader = CountingReader(graph, heads, most=2)
    wanted = every_read(MemoryAsReader(graph, heads), ["f", "s", "ann"])
    assert every_read(reader, ["f", "s", "ann"]) == wanted
    # (three nodes held, more than two: the next read forgets them and asks again)
    assert every_read(reader, ["f", "s", "ann"]) == wanted
    assert reader.forgotten >= 1
    assert reader.asked[("nodes", "f")] == 2
    assert set(reader.seen) == {"f", "s", "ann"}


class MemoryAsReader:
    """A `MemoryReader` with `below`, for what the answers should be"""

    def __init__(self, graph: MemoryReader, heads: dict[str, str]):
        self.graph, self.heads = graph, heads

    def nodes(self, ids):
        return self.graph.nodes(ids)

    def out_edges(self, ids):
        return self.graph.out_edges(ids)

    def in_edges(self, ids):
        return self.graph.in_edges(ids)

    def citing(self, ids):
        return sorted(self.graph.citing(ids))

    def below(self, ids):
        return sorted(i for i, head in self.heads.items() if head in set(ids))


def test_every_unit_past_the_cap_alone_is_counted_stale_even_with_no_approximate_row():
    """A head written, past the cap alone, whose own stops another group answered exactly, has no approximate row:
    its neighbourhood is still not right, and is counted (found by the second reading of step 7a.1)"""
    from pangloss_fastrp.part import stale_of

    assert stale_of(0, 1) == 1
    assert stale_of(2, 1) == 2
    assert stale_of(3, 5) == 5
    assert stale_of(0, 0) == 0
