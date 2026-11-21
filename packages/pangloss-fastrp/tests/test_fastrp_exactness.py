"""The exactness the graph part rests on: after any edit, `refresh` of what changed gives the vectors a whole
rebuild gives; an overlay gives the vectors the same nodes written would have; the order of reading does not
matter. A failure prints the seed and the edit."""

import numpy as np
import pytest

from pangloss_fastrp import maths
from pangloss_fastrp.maths import Edge, Node
from pangloss_fastrp.testing import WORLD_MAPS, MemoryReader, World, oracle

CLOSE = 1e-5


def changed_between(before: dict, after: dict) -> set[str]:
    """Both ends of every join made, lost or reweighted"""
    return {
        i
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
        for i in key
    }


def assert_same(found: dict, wanted: dict, said: str) -> None:
    assert set(found) == set(wanted), f"{said}: {sorted(set(found) ^ set(wanted))[:5]}"
    for id, vector in wanted.items():
        gap = float(np.abs(found[id] - vector).max())
        assert gap < CLOSE, f"{said}: {id} differs by {gap}"


@pytest.mark.parametrize("sees", ["everyone", "logged_in"])
@pytest.mark.parametrize("seed", range(4))
def test_a_refresh_after_any_edit_equals_a_rebuild(seed, sees):
    import dataclasses

    maps = dataclasses.replace(WORLD_MAPS, sees=sees)
    world = World(seed)
    vectors = oracle(world.graph, maps)
    joins = maths.joins(world.graph, maps)
    for round in range(25):
        edit = world.edit()
        after = maths.joins(world.graph, maps)
        changed = changed_between(joins, after)
        made = maths.refresh(world.graph, maps, changed)
        for id in made.gone:
            vectors.pop(id, None)
        vectors.update(made.vectors)
        assert not made.gone & set(made.vectors)
        assert_same(
            vectors,
            oracle(world.graph, maps),
            f"seed {seed}, {sees}, round {round}, {edit}",
        )
        joins = after


@pytest.mark.parametrize("seed", range(10))
def test_the_joins_that_touch_some_stops_are_those_of_the_whole_graph(seed):
    world = World(seed, people=120, documents=120)
    whole = maths.joins(world.graph, WORLD_MAPS)
    some = set(world.random.sample(sorted(world.graph.node), 30))
    wanted = {key: w for key, w in whole.items() if key[0] in some or key[1] in some}
    assert maths.joins(world.graph, WORLD_MAPS, some) == wanted


@pytest.mark.parametrize("seed", range(10))
def test_an_overlay_equals_the_same_nodes_written(seed):
    world = World(seed, people=150, documents=150)
    before = world.graph.copy()
    known = set(before.node)
    for _ in range(5):
        # (a new document, which may name people the database has not got: two unknowns)
        unknown = [world.stop("Person") for _ in range(2)]
        world.people += unknown
        document = world.document(published=True)
        nodes = [n for i, n in world.graph.node.items() if i not in known]
        edges = [e for n in nodes for e in world.graph.out.get(n.id, [])]
        found = maths.overlay(before, WORLD_MAPS, nodes, edges)
        wanted = oracle(world.graph, WORLD_MAPS)
        stops = [n.id for n in nodes if WORLD_MAPS.is_in(n)]
        assert document in stops
        assert_same(
            found,
            {i: wanted[i] for i in stops if i in wanted},
            f"seed {seed}, overlay of {document}",
        )
        before, known = world.graph.copy(), set(world.graph.node)


def test_an_overlay_of_an_update_replaces_what_was_below_the_head():
    world = World(3, people=100, documents=100)
    before = world.graph.copy()
    document = world.documents[5]
    old = world.tree(document)[1:]
    for id in old:
        world.graph.remove(id)
    world.edge(document, world.statement(document, True), "statements")
    nodes = [world.graph.node[i] for i in world.tree(document)]
    edges = [e for n in nodes for e in world.graph.out.get(n.id, [])]
    found = maths.overlay(before, WORLD_MAPS, nodes, edges, removed=old)
    wanted = oracle(world.graph, WORLD_MAPS)
    stops = [n.id for n in nodes if WORLD_MAPS.is_in(n)]
    assert_same(found, {i: wanted[i] for i in stops if i in wanted}, "an update")


def test_a_vector_does_not_depend_on_the_order_things_are_read_in():
    world = World(5, people=100, documents=100)
    nodes = list(world.graph.node.values())
    edges = [e for found in world.graph.out.values() for e in found]
    world.random.shuffle(nodes)
    world.random.shuffle(edges)
    assert_same(
        oracle(MemoryReader(nodes, edges), WORLD_MAPS),
        oracle(world.graph, WORLD_MAPS),
        "shuffled",
    )


def test_the_seed_of_an_id_is_its_own():
    one = maths.seeds(["a", "b", "c"], 64)
    assert np.array_equal(one[1], maths.seeds(["b"], 64)[0])
    assert set(np.unique(one)) <= {-1.0, 0.0, 1.0}
    many = maths.seeds([f"id-{n}" for n in range(2000)], 64)
    assert 0.30 < float((many != 0).mean()) < 0.37
    assert abs(float(many.mean())) < 0.01


def test_past_the_cap_a_refresh_says_so():
    world = World(1)
    with pytest.raises(maths.TooLarge):
        maths.refresh(
            world.graph,
            WORLD_MAPS,
            [min(maths.joins(world.graph, WORLD_MAPS))[0]],
            cap=5,
        )


def test_the_maps_survive_json():
    import json

    assert (
        maths.GraphMaps.of(json.loads(json.dumps(WORLD_MAPS.plain()))).plain()
        == WORLD_MAPS.plain()
    )


def test_rules_by_hand():
    """One document through each shape, the joins written out"""
    graph = MemoryReader(
        [
            Node("d", "Event"),
            Node("g", "Gift"),
            Node("ann", "Person"),
            Node("bob", "Person"),
            Node("cy", "Person"),
            Node("gone", "Person", deleted=True),
            Node("old", "Person", merged_into="ann"),
            Node("york", "Place"),
            Node("role", "InRole"),
            Node("ident", "Identification"),
            Node("alt", "Alternative"),
            Node("sworn", "Sworn"),
            Node("no", "Negative"),
            Node("quiet", "Quiet"),
            Node("match", "Matches"),
            Node("cite", "PGCitation", cites="d"),
            Node("hidden", "Factoid", published=False),
        ],
        [
            # (three wrappers and a share before a person)
            Edge("d", "role", "by"),
            Edge("role", "york", "at"),
            Edge("role", "ident", "target"),
            Edge("ident", "alt", "target"),
            Edge("alt", "ann", "alternatives", {"percent": 70}),
            Edge("alt", "bob", "alternatives", {"percent": 30}),
            # (the same person by two fields, and by a lighter wrapper: one join, the largest)
            Edge("d", "sworn", "to"),
            Edge("sworn", "bob", "target"),
            Edge("d", "york", "place"),
            # (not joined: deleted, merged, behind a stop, a reverse edge, a shortcut)
            Edge("d", "gone", "by"),
            Edge("d", "old", "by"),
            Edge("d", "no", "statements"),
            Edge("no", "cy", "contents"),
            Edge("cy", "d", "by", {"reverse": True}),
            Edge("ann", "cy", "SameGroup", {"derived": True}),
            # (a class weight; own relations not joined; candidates at a share; a citation; an unpublished document)
            Edge("g", "quiet", "to"),
            Edge("quiet", "ann", "target"),
            Edge("quiet", "york", "at"),
            Edge("g", "match", "by"),
            Edge("match", "bob", "target", {"computed": True}),
            Edge("match", "cy", "target", {"computed": True}),
            Edge("match", "ann", "target", {"computed": True, "seen_by": "logged_in"}),
            Edge("g", "cite", "evidence"),
            Edge("hidden", "cy", "by"),
        ],
    )
    assert maths.joins(graph, WORLD_MAPS) == {
        ("ann", "d"): pytest.approx(0.7),
        ("bob", "d"): pytest.approx(0.5),
        ("d", "york"): pytest.approx(0.7),
        ("ann", "g"): pytest.approx(2.0),
        ("bob", "g"): pytest.approx(1.0),
        ("cy", "g"): pytest.approx(1.0),
        ("d", "g"): pytest.approx(2.0),
    }
    import dataclasses

    logged_in = maths.joins(graph, dataclasses.replace(WORLD_MAPS, sees="logged_in"))
    assert logged_in[("cy", "hidden")] == pytest.approx(1.0)
    assert logged_in[("ann", "g")] == pytest.approx(2.0)
    assert logged_in[("bob", "g")] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# A batch refreshed in groups (`part.refresh_ids`, step 7a.1)
# ---------------------------------------------------------------------------


class WithBelow:
    """The world's graph as `part.changed_stops` reads it, with `below`: what is nested in a head"""

    def __init__(self, world: World):
        self.world = world

    def nodes(self, ids=None):
        return self.world.graph.nodes(ids)

    def out_edges(self, ids):
        return self.world.graph.out_edges(ids)

    def in_edges(self, ids):
        return self.world.graph.in_edges(ids)

    def citing(self, ids):
        return self.world.graph.citing(ids)

    def below(self, heads):
        return sorted(
            {
                i
                for h in heads
                if h in self.world.graph.node
                for i in self.world.tree(h)[1:]
            }
        )


def heads_as_they_stand(world: World) -> dict[str, tuple[frozenset, ...]]:
    """Each head (a document, a person) by its tree: the ids, the nodes, and their edges"""
    found = {}
    for head in [*world.documents, *world.people]:
        if head not in world.graph.node:
            continue
        tree = world.tree(head)
        found[head] = (
            frozenset(tree),
            frozenset(repr(world.graph.node[i]) for i in tree),
            frozenset(
                (e.source, e.target, e.field, tuple(sorted(e.properties.items())))
                for i in tree
                for e in world.graph.out.get(i, [])
            ),
        )
    return found


def units_of_a_batch(world: World, was: dict, joins_was: dict) -> list:
    """What the worker would give a batch of edits as units: the heads written (new or changed), the heads removed,
    and, as `before`, what the trees of the heads changed or removed were and were joined to before"""
    from pangloss_fastrp.part import BEFORE, REMOVED, WRITTEN, Unit

    now = heads_as_they_stand(world)
    written = {h for h in now if was.get(h) != now[h]}
    removed = set(was) - set(now)
    before: set[str] = set()
    for head in (written | removed) & set(was):
        tree = was[head][0]
        before |= tree | {
            i for key in joins_was if key[0] in tree or key[1] in tree for i in key
        }
    return sorted(
        [Unit(h, WRITTEN) for h in written]
        + [Unit(h, REMOVED) for h in removed]
        + [Unit(i, BEFORE) for i in before]
    )


def divided(units: list, groups: int, arrangement: str, r) -> list[list]:
    """The units in `groups` groups: shuffled; or the heads removed and the `before` ids all in the first group, or
    all in the last, the heads written shuffled among the others"""
    from pangloss_fastrp.part import WRITTEN

    if arrangement == "shuffled":
        mixed = list(units)
        r.shuffle(mixed)
        return [mixed[n::groups] for n in range(groups)]
    written = [u for u in units if u.kind == WRITTEN]
    rest = [u for u in units if u.kind != WRITTEN]
    r.shuffle(written)
    others = [written[n :: groups - 1] for n in range(groups - 1)]
    return [rest, *others] if arrangement == "first" else [*others, rest]


@pytest.mark.parametrize("arrangement", ["shuffled", "first", "last"])
@pytest.mark.parametrize("groups", [2, 3, 7])
@pytest.mark.parametrize("seed", range(2))
def test_a_batch_refreshed_in_groups_equals_a_rebuild(seed, groups, arrangement):
    """Batches of random edits; the batch's units (`part.Unit`) divided into groups, each group's centre
    (`part.changed_stops`) refreshed by itself: the union of the answers is a rebuild's"""
    from pangloss_fastrp.part import BEFORE, changed_stops

    world = World(seed + 10 * groups)
    reader = WithBelow(world)
    vectors = oracle(world.graph, WORLD_MAPS)
    joins = maths.joins(world.graph, WORLD_MAPS)
    for round in range(10):
        was = heads_as_they_stand(world)
        edits = [world.edit() for _ in range(world.random.randint(1, 4))]
        after = maths.joins(world.graph, WORLD_MAPS)
        units = units_of_a_batch(world, was, joins)
        parts = divided(units, groups, arrangement, world.random)
        centres = [
            changed_stops(
                reader,
                WORLD_MAPS,
                [u.id for u in group if u.kind != BEFORE],
                [u.id for u in group if u.kind == BEFORE],
            )
            for group in parts
            if group
        ]
        said = f"seed {seed}, {groups} groups, {arrangement}, round {round}, {edits}"
        # (the groups' centres together hold everything whose joins changed)
        assert changed_between(joins, after) <= set().union(*centres), said
        for centre in centres:
            made = maths.refresh(world.graph, WORLD_MAPS, centre)
            for id in made.gone:
                vectors.pop(id, None)
            vectors.update(made.vectors)
        assert_same(vectors, oracle(world.graph, WORLD_MAPS), said)
        joins = after
