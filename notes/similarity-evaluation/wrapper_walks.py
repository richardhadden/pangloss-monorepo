"""Wrapper chains in the graph part: hopped over, walked, or weighted (2026-11-20).

Planted data in the shapes Pangloss stores, numpy and scipy only, no database. The findings are in
implementation_docs/graph-embeddings.md, "Chains of wrappers". Run:

    uv venv /tmp/embed-venv2 && uv pip install --python /tmp/embed-venv2/bin/python numpy scipy
    /tmp/embed-venv2/bin/python notes/similarity-evaluation/wrapper_walks.py
"""

import sys
from collections import defaultdict

import numpy as np
import scipy.sparse as sp

DIM = 128
STOPS = {"Document", "Entity"}


class Graph:
    """Forward edges only, as the walk reads them. An edge is (source, target, field, holds, likelihood)."""

    def __init__(self):
        self.kind: list[str] = []
        self.cls: list[str] = []
        self.out: dict[int, list[tuple[int, str, bool, float | None]]] = defaultdict(list)

    def node(self, kind: str, cls: str) -> int:
        self.kind.append(kind)
        self.cls.append(cls)
        return len(self.kind) - 1

    def edge(self, source: int, target: int, field: str, holds: bool = True, likelihood: float | None = None):
        # holds: the edge to what a wrapper holds (`target`), against a relation of the wrapper's own (`role`)
        self.out[source].append((target, field, holds, likelihood))


def join(g: Graph, stops=STOPS, weight="flat", own="ignore", own_weight=1.0, field_weights=None, typed=None):
    """The joined graph: (stop, stop, weight, type key) for every way from a stop through wrappers to a stop.

    weight: "flat" (every stop reached counts 1), "split" (what a wrapper holds shares the weight that came
        into it, as a walker's probability would), "likelihood" (an edge's likelihood where it has one, else flat),
        "likelihood+split" (likelihood where there is one, else split).
    own: what is done with a wrapper's own relations: "ignore", "bubble" (joined to the document the way started
        from), "attach" (joined to what the wrapper holds), "both".
    typed: None, "field" or "role": what the type key of a join is.
    """
    field_weights = field_weights or {}
    rows = []

    def descend(start, node, w, key):
        """Returns the stops reached below `node`."""
        if g.kind[node] in stops:
            rows.append((start, node, w, key))
            return [node]
        edges = g.out[node]
        held = [e for e in edges if e[2]]
        owned = [e for e in edges if not e[2]]
        if typed == "role" and owned:
            key = f"role:{owned[0][0]}"
        reached = []
        for target, _field, _holds, likelihood in held:
            if "likelihood" in weight and likelihood is not None:
                factor = likelihood
            elif "split" in weight:
                factor = 1.0 / len(held)
            else:
                factor = 1.0
            reached += descend(start, target, w * factor, key)
        for target, _field, _holds, _likelihood in owned:
            if own in ("bubble", "both"):
                rows.append((start, target, w * own_weight, "own"))
            if own in ("attach", "both"):
                for stop in reached:
                    rows.append((stop, target, own_weight, "own"))
        return reached

    for start in range(len(g.kind)):
        if g.kind[start] not in stops:
            continue
        for target, field, _holds, _likelihood in g.out[start]:
            key = f"field:{field}" if typed else ""
            descend(start, target, field_weights.get(field, 1.0), key)
    return rows


def fastrp(n, rows, steps=(0.0, 1.0, 1.0), seed=0, typed_share=0.0):
    """FastRP over undirected joins. With typed_share, that share of what a neighbour gives is its vector with
    the signs of its type key's own random diagonal, so the same neighbour by another relation gives another vector."""
    rng = np.random.default_rng(seed)
    start = rng.choice([-1.0, 0.0, 1.0], size=(n, DIM), p=[1 / 6, 2 / 3, 1 / 6]).astype(np.float32)
    by_key = defaultdict(lambda: ([], [], []))
    for a, b, w, key in rows:
        if a == b or w <= 0:
            continue
        i, j, v = by_key[key if typed_share else ""]
        i += [a, b]
        j += [b, a]
        v += [w, w]
    mats = {k: sp.csr_matrix((v, (i, j)), shape=(n, n), dtype=np.float32) for k, (i, j, v) in by_key.items()}
    total = sum(mats.values())
    degree = np.asarray(total.sum(axis=1)).ravel()
    inverse = sp.diags(np.where(degree > 0, 1.0 / np.maximum(degree, 1e-12), 0.0).astype(np.float32))
    signs = {k: np.random.default_rng(abs(hash(k)) % 2**32).choice([-1.0, 1.0], size=DIM).astype(np.float32) for k in mats}

    def step(x):
        if not typed_share:
            y = inverse @ (total @ x)
        else:
            y = (1 - typed_share) * (inverse @ (total @ x))
            for k, m in mats.items():
                y += typed_share * (inverse @ (m @ x)) * signs[k]
        norm = np.linalg.norm(y, axis=1, keepdims=True)
        return y / np.maximum(norm, 1e-12)

    x, result = start, np.zeros((n, DIM), dtype=np.float32)
    for w in steps:
        x = step(x)
        result += w * x
    return result


def nearest(vectors, ids, k=10):
    v = vectors[ids]
    v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    sims = v @ v.T
    np.fill_diagonal(sims, -2)
    return np.argsort(-sims, axis=1)[:, :k]


def share(vectors, ids, truth, k=10):
    """How many of each item's k nearest (among ids) have its truth value."""
    near = nearest(vectors, ids, k)
    truth = np.asarray(truth)
    return float((truth[near] == truth[:, None]).mean()) * 100


# --------------------------------------------------------------------------------------------------------------
# The world

N_PEOPLE, FAMILY, N_PROFESSIONS, N_PLACES = 2000, 20, 8, 50


class World:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.g = Graph()
        g = self.g
        self.people = [g.node("Entity", "Person") for _ in range(N_PEOPLE)]
        self.family = [i // FAMILY for i in range(N_PEOPLE)]
        self.profession = list(self.rng.integers(0, N_PROFESSIONS, N_PEOPLE))
        self.places = [g.node("Entity", "Place") for _ in range(N_PLACES)]
        self.roles = [g.node("Entity", "RoleType") for _ in range(N_PROFESSIONS)]
        self.kin_role = g.node("Entity", "RoleType")
        self.statements: list[int] = []

    def statement(self, cls, place=None):
        s = self.g.node("Document", cls)
        self.statements.append(s)
        if place is not None:
            self.g.edge(s, self.places[place], "place")
        return s

    def relate(self, s, field, person, depth=0, role=None):
        """A person in a field, through `depth` wrappers: InRole, Identification, Alternative."""
        g, source, f = self.g, s, field
        chain = [("ReifiedRelation", "InRole"), ("ReifiedRelation", "Identification"), ("Conjunction", "Alternative")]
        for kind, cls in chain[:depth]:
            wrapper = g.node(kind, cls)
            g.edge(source, wrapper, f)
            if cls == "InRole" and role is not None:
                g.edge(wrapper, role, "role", holds=False)
            source, f = wrapper, "target"
        g.edge(source, self.people[person], f)

    def kin_pair(self):
        family = int(self.rng.integers(0, N_PEOPLE // FAMILY))
        a, b = self.rng.choice(FAMILY, 2, replace=False)
        return family, family * FAMILY + int(a), family * FAMILY + int(b)


def mean(runs):
    return " ".join(f"{np.mean(c):6.1f}" for c in zip(*runs))


def table(title, columns, results):
    print(f"\n{title}\n  {'':58s}" + " ".join(f"{c:>6s}" for c in columns))
    for name, runs in results.items():
        print(f"  {name:58s}{mean(runs)}")


SEEDS = (1, 2, 3)

# --------------------------------------------------------------------------------------------------------------
# A. How deep the chain is: walked (every node a node of the graph) against hopped over


def experiment_depth():
    results = defaultdict(list)
    for seed in SEEDS:
        for depth in (0, 1, 2, 3, "mixed"):
            w = World(seed)
            for _ in range(6000):
                family, a, b = w.kin_pair()
                s = w.statement("Kinship", family % N_PLACES)
                for p in (a, b):
                    w.relate(s, "person", p, int(w.rng.integers(0, 4)) if depth == "mixed" else depth)
            for _ in range(12000):
                s = w.statement("Mention", int(w.rng.integers(0, N_PLACES)))
                for p in w.rng.choice(N_PEOPLE, 3, replace=False):
                    w.relate(s, "person", int(p), int(w.rng.integers(0, 4)) if depth == "mixed" else depth)
            n = len(w.g.kind)
            everything = {"Document", "Entity", "ReifiedRelation", "Conjunction"}
            raw = join(w.g, stops=everything)
            hopped = join(w.g)
            row = [
                share(fastrp(n, raw, seed=seed), w.people, w.family),
                share(fastrp(n, raw, steps=(0, 1, 1, 1, 1, 1, 1, 1), seed=seed), w.people, w.family),
                share(fastrp(n, raw, steps=(0, 0, 0, 1, 0, 1, 0, 1), seed=seed), w.people, w.family),
                share(fastrp(n, hopped, seed=seed), w.people, w.family),
                share(fastrp(n, hopped, steps=(0, 1, 1, 1, 1, 1, 1, 1), seed=seed), w.people, w.family),
                n / 1000,
                len(raw) / 1000,
                len(hopped) / 1000,
            ]
            results[f"wrappers between statement and person: {depth}"].append(row)
    table(
        "A. Same family among a person's 10 nearest people (chance 1.0%), by the depth of the chain",
        ["walk3", "walk8", "walk8e", "hopped", "hop8", "nodes k", "raw k", "joins k"],
        results,
    )


# --------------------------------------------------------------------------------------------------------------
# B. What a wrapper's targets weigh: uncertain identifications and long lists


def experiment_weights():
    results = defaultdict(list)
    for seed in SEEDS:
        w = World(seed)
        g = w.g
        for _ in range(6000):
            family, a, b = w.kin_pair()
            s = w.statement("Kinship", family % N_PLACES)
            w.relate(s, "person", a)
            if w.rng.random() < 0.5:  # the second person is one of three candidates, with likelihoods
                ident = g.node("ReifiedRelation", "Identification")
                alt = g.node("Conjunction", "Alternative")
                g.edge(s, ident, "person")
                g.edge(ident, alt, "target")
                likes = [0.6, 0.25, 0.15] if w.rng.random() < 0.7 else [0.25, 0.6, 0.15]
                others = [int(p) for p in w.rng.choice(N_PEOPLE, 2, replace=False)]
                for person, like in zip([b, *others], likes):
                    g.edge(alt, w.people[person], "target", likelihood=like)
            else:
                w.relate(s, "person", b)
            witnesses = g.node("Conjunction", "Group")  # a list of bystanders, held as one
            g.edge(s, witnesses, "witnesses")
            for p in w.rng.choice(N_PEOPLE, 6, replace=False):
                g.edge(witnesses, w.people[int(p)], "target")
        for _ in range(6000):
            s = w.statement("Mention", int(w.rng.integers(0, N_PLACES)))
            for p in w.rng.choice(N_PEOPLE, 3, replace=False):
                w.relate(s, "person", int(p))
        n = len(g.kind)
        variants = {
            "flat: every person reached counts 1 (as designed 2026-11-11)": dict(weight="flat"),
            "split: what a wrapper holds shares what came into it": dict(weight="split"),
            "likelihood on the edge, the rest flat": dict(weight="likelihood"),
            "likelihood on the edge, the rest split": dict(weight="likelihood+split"),
            "flat, the witnesses field at 0.2 (a per-field weight)": dict(weight="flat", field_weights={"witnesses": 0.2}),
            "likelihood, the witnesses field at 0.2": dict(weight="likelihood", field_weights={"witnesses": 0.2}),
            "likelihood, the witnesses field left out": dict(weight="likelihood", field_weights={"witnesses": 0.0}),
        }
        for name, options in variants.items():
            results[name].append([share(fastrp(n, join(g, **options), seed=seed), w.people, w.family)])
    table("B. Same family among a person's 10 nearest people (chance 1.0%)", ["family"], results)


# --------------------------------------------------------------------------------------------------------------
# B2. The converse: the wrapper holds what matters (a family named together), the plain fields hold bystanders


def experiment_groups():
    results = defaultdict(list)
    for seed in SEEDS:
        w = World(seed)
        g = w.g
        for _ in range(6000):
            family = int(w.rng.integers(0, N_PEOPLE // FAMILY))
            s = w.statement("Kinship", family % N_PLACES)
            group = g.node("Conjunction", "Group")
            g.edge(s, group, "family")
            for p in w.rng.choice(FAMILY, 4, replace=False):
                g.edge(group, w.people[family * FAMILY + int(p)], "target")
            for p in w.rng.choice(N_PEOPLE, 2, replace=False):
                w.relate(s, "witness", int(p))
        for _ in range(6000):
            s = w.statement("Mention", int(w.rng.integers(0, N_PLACES)))
            for p in w.rng.choice(N_PEOPLE, 3, replace=False):
                w.relate(s, "person", int(p))
        n = len(g.kind)
        for name, options in {"flat": dict(weight="flat"), "split": dict(weight="split")}.items():
            results[name].append([share(fastrp(n, join(g, **options), seed=seed), w.people, w.family)])
    table("B2. The converse: four of a family held by one wrapper, two bystanders in a plain field", ["family"], results)


# --------------------------------------------------------------------------------------------------------------
# C. A wrapper's own relation: InRole.role -> RoleType


def experiment_roles():
    results = defaultdict(list)
    for seed in SEEDS:
        w = World(seed)
        g = w.g
        for _ in range(6000):
            family, a, b = w.kin_pair()
            s = w.statement("Kinship", family % N_PLACES)
            for p in (a, b):
                w.relate(s, "person", p, 1, role=w.kin_role)
        for _ in range(12000):  # acts: strangers, each in the role of their profession most of the time
            s = w.statement("Act", int(w.rng.integers(0, N_PLACES)))
            for p in w.rng.choice(N_PEOPLE, 3, replace=False):
                p = int(p)
                role = w.profession[p] if w.rng.random() < 0.7 else int(w.rng.integers(0, N_PROFESSIONS))
                w.relate(s, "person", p, 1, role=w.roles[role])
        n = len(g.kind)
        with_wrappers = STOPS | {"ReifiedRelation"}
        variants = {
            "own relations ignored": (dict(own="ignore"), {}),
            "joined to the statement (everything reachable is joined)": (dict(own="bubble"), {}),
            "joined to the person held, weight 1": (dict(own="attach"), {}),
            "joined to the person held, weight 0.25": (dict(own="attach", own_weight=0.25), {}),
            "joined to the person held, weight 0.05": (dict(own="attach", own_weight=0.05), {}),
            "joined to both": (dict(own="both"), {}),
            "the wrapper kept as a node, 3 steps": (dict(stops=with_wrappers), {}),
            "the wrapper kept as a node, 6 steps": (dict(stops=with_wrappers), dict(steps=(0, 1, 1, 1, 1, 1))),
        }
        for name, (options, run) in variants.items():
            v = fastrp(n, join(g, **options), seed=seed, **run)
            results[name].append([share(v, w.people, w.family), share(v, w.people, w.profession)])

        # A part of its own: people by the roles they are held in, beside the graph part, weighed in the query
        graph = fastrp(n, join(g, own="ignore"), seed=seed)[w.people]
        profile = np.zeros((N_PEOPLE, N_PROFESSIONS + 1), dtype=np.float32)
        index = {node: i for i, node in enumerate(w.people)}
        role_index = {node: i for i, node in enumerate([*w.roles, w.kin_role])}
        for a, b, _w, _k in join(g, own="attach"):
            if b in role_index and a in index:
                profile[index[a], role_index[b]] += 1
        profile[:, N_PROFESSIONS] = 0  # the role everyone has says nothing
        unit = lambda m: m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)  # noqa: E731
        ids = list(range(N_PEOPLE))
        for weight in (0.0, 0.3, 1.0, 3.0):
            both = np.hstack([unit(graph), weight * unit(profile)])
            if weight == 3.0:
                both = unit(profile)
                name = "a role part of its own, alone"
            else:
                name = f"a role part of its own beside the graph part, weight {weight}"
            results[name].append([share(both, ids, w.family), share(both, ids, w.profession)])
    table(
        "C. Among a person's 10 nearest people: same family (chance 1.0%), same profession (chance 12.5%)",
        ["family", "prof."],
        results,
    )


# --------------------------------------------------------------------------------------------------------------
# D. The same people the other way round: does the kind of join need to be in the vector?


def experiment_typed():
    results = defaultdict(list)
    for seed in SEEDS:
        for shape in ("fields", "roles"):
            w = World(seed)
            g = w.g
            buyer, seller = w.roles[0], w.roles[1]
            for _ in range(6000):
                family, a, b = w.kin_pair()
                s = w.statement("Kinship", family % N_PLACES)
                for p in (a, b):
                    w.relate(s, "person", p)
            event_of, has_reverse = {}, {}
            for event in range(3000):
                a, b = (int(p) for p in w.rng.choice(N_PEOPLE, 2, replace=False))
                place = int(w.rng.integers(0, N_PLACES))
                reverse = w.rng.random() < 0.5
                for which, (x, y) in enumerate([(a, b), (b, a)] if reverse else [(a, b)]):
                    for _report in range(2):
                        s = w.statement("Sale", place)
                        event_of[s], has_reverse[s] = (event, which), reverse
                        if shape == "fields":
                            w.relate(s, "buyer", x)
                            w.relate(s, "seller", y)
                        else:
                            w.relate(s, "party", x, 1, role=buyer)
                            w.relate(s, "party", y, 1, role=seller)
            n = len(g.kind)
            sales = [s for s in w.statements if s in event_of]
            asked = [i for i, s in enumerate(sales) if has_reverse[s]]
            for typed_share in (0.0, 0.1, 0.25, 0.5, 1.0):
                rows = join(g, typed="field" if shape == "fields" else "role")
                v = fastrp(n, rows, seed=seed, typed_share=typed_share)
                first = nearest(v, sales, 1)[:, 0]
                right = np.mean([event_of[sales[first[i]]] == event_of[sales[i]] for i in asked]) * 100
                results[f"{shape}: typed share {typed_share}"].append([right, share(v, w.people, w.family)])
    table(
        "D. A sale reported twice, and the same two people the other way round, reported twice.\n"
        "   Nearest other sale is the other report of the same sale (chance 33.3%); people's same family",
        ["same", "family"],
        results,
    )


if __name__ == "__main__":
    chosen = sys.argv[1:] or ["A", "B", "B2", "C", "D"]
    for name, run in (("A", experiment_depth), ("B", experiment_weights), ("B2", experiment_groups), ("C", experiment_roles), ("D", experiment_typed)):
        if name in chosen:
            run()
