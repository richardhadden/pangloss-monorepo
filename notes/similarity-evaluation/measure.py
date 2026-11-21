"""Step 3.5 of implementation_docs/similarity-build-plan.md: the graph part measured on a database of size.

Run from the directory of a project whose settings point at a **scratch** database and have `pangloss_vectors`
and `pangloss_fastrp` among the installed apps (a copy of the demo: notes/similarity-evaluation/README.md):

    cd /tmp/similar-demo && /path/to/.venv/bin/python /path/to/notes/similarity-evaluation/measure.py [heads]

It reads only. It prints: the rebuild by stage (reading, the joins, FastRP), what the joined graph is, and, for a
sample of heads, how many stops a refresh of each would read, by the number of steps.
"""

import asyncio
import random
import statistics
import sys
import time
from collections import Counter, defaultdict

from pangloss_cli import load_project
from pangloss_models import initialise

HEADS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
STOP_AT = 200_000


def clock(said, began):
    took = time.perf_counter() - began
    print(f"  {said}: {took:.1f} s")
    return took


def rings(neighbours, start, most):
    """How many stops are within 1, 2, ... `most` joins of `start` (stopping past STOP_AT)"""
    seen, ring, sizes = {start}, {start}, []
    for _ in range(most):
        following = set()
        for i in ring:
            following |= neighbours.get(i, set())
        following -= seen
        seen |= following
        sizes.append(len(seen))
        ring = following
        if len(seen) > STOP_AT or not ring:
            break
    return sizes + [sizes[-1] if sizes else 1] * (most - len(sizes))


def spread(values):
    values = sorted(values)
    at = lambda q: values[min(len(values) - 1, int(q * len(values)))]  # noqa: E731
    return f"median {at(0.5):,}, 90% {at(0.9):,}, 99% {at(0.99):,}, most {values[-1]:,}"


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    import numpy as np
    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import load_all
    from pangloss_fastrp.maps import graph_maps

    maps = graph_maps()
    print(f"backend {type(backend).__module__.split('.')[0]}; steps {list(maps.steps)}, dimension {maps.dimension}, "
          f"sees {maps.sees}")
    print("the rebuild, by stage")
    began = time.perf_counter()
    graph = await load_all(maps)
    read = clock("read every node and forward edge", began)
    nodes = len(graph.node)
    edges = sum(len(found) for found in graph.out.values())
    stops = [n for n in graph.node.values() if maps.is_in(n)]
    kinds = Counter(
        "deleted" if n.deleted else "merged" if n.merged_into else "unpublished" if not n.published else "in"
        for n in graph.node.values()
        if maps.kinds.get(n.type) == "stop"
    )
    print("    documents and entities:", ", ".join(f"{k} {c:,}" for k, c in kinds.most_common()))
    print(f"    {nodes:,} nodes, {edges:,} forward edges, {len(stops):,} stops in the graph")
    print("    by type:", ", ".join(f"{t} {c:,}" for t, c in Counter(n.type for n in stops).most_common(12)))
    began = time.perf_counter()
    joins = await asyncio.to_thread(maths.joins, graph, maps)
    joined = clock("the joins", began)
    ids = sorted({i for key in joins for i in key})
    began = time.perf_counter()
    vectors = await asyncio.to_thread(maths.embed, ids, joins, maps)
    embedded = clock("FastRP", began)
    print(f"    {len(joins):,} joins among {len(ids):,} stops; vectors {vectors.shape}, "
          f"{vectors.nbytes / 1e6:.0f} MB as float64")
    print(f"  in all, without writing: {read + joined + embedded:.1f} s")

    neighbours = defaultdict(set)
    for a, b in joins:
        neighbours[a].add(b)
        neighbours[b].add(a)
    degree = sorted(((len(found), i) for i, found in neighbours.items()), reverse=True)
    print("\nthe joined graph")
    print("  joins of a stop:", spread([d for d, _ in degree]))
    print("  the most joined:", ", ".join(f"{graph.node[i].type} {d:,}" for d, i in degree[:8]))
    by_type = defaultdict(list)
    for d, i in degree:
        by_type[graph.node[i].type].append(d)
    print("  by type (median, most):", ", ".join(
        f"{t} {statistics.median(v):.0f}/{max(v):,}" for t, v in sorted(by_type.items(), key=lambda x: -max(x[1]))[:12]))

    chooser = random.Random(1)
    heads = [n.id for n in stops if n.id in neighbours]
    documents = [i for i in heads if maps.documents.get(graph.node[i].type)]
    sample = chooser.sample(documents, min(HEADS, len(documents)))
    print(f"\nwhat a refresh of one document reads ({len(sample)} documents at random; a refresh with k steps reads "
          f"the stops within 2k - 1 joins; counting stops past {STOP_AT:,})")
    found = [rings(neighbours, i, 7) for i in sample]
    for k in (2, 3, 4):
        sizes = [f[2 * k - 2] for f in found]
        past = sum(1 for s in sizes if s > 50_000)
        print(f"  k = {k} ({2 * k - 1} joins out): {spread(sizes)}; past 50,000: {100 * past / len(sizes):.0f}%")
    print("  within 1 join:", spread([f[0] for f in found]), "| within 2:", spread([f[1] for f in found]))

    # (the same with the most joined kinds of entity left out of the walk, as a class with include=False would be)
    hubs = {i for d, i in degree[: max(1, len(degree) // 1000)]}
    trimmed = {i: found - hubs for i, found in neighbours.items() if i not in hubs}
    again = [rings(trimmed, i, 5) for i in sample if i not in hubs]
    sizes = [f[4] for f in again]
    past = sum(1 for s in sizes if s > 50_000)
    print(f"  k = 3 with the most joined 0.1% of stops ({len(hubs):,}) left out: {spread(sizes)}; "
          f"past 50,000: {100 * past / len(sizes):.0f}%")

    began = time.perf_counter()
    done = 0
    for i in sample[:20]:
        try:
            made = maths.refresh(graph, maps, [i], cap=50_000)
            done += 1
        except maths.TooLarge:
            pass
    print(f"\n  a refresh in memory of 20 of them, capped at 50,000: {done} within the cap, "
          f"{(time.perf_counter() - began) / 20 * 1000:.0f} ms each on average")
    _ = np


asyncio.run(main())
