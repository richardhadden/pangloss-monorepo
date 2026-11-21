"""Before phase 4 is built: is reading the graph from inside a Memgraph query module faster than `load_all` through
Cypher (12 s on `:7690`), and what does a refresh of one document cost the Python engine there?

    cd /tmp/similar-demo && /path/to/.venv/bin/python /path/to/notes/similarity-evaluation/module_scan_trial.py

It installs a module `pg_scan_trial` on the database of the project's settings (a scratch one) and removes it.
"""

import asyncio
import random
import statistics
import time

import neo4j
from pangloss_cli import load_project
from pangloss_models import initialise

MODULE = '''
import time
import mgp

@mgp.read_proc
def scan(ctx: mgp.ProcCtx) -> mgp.Record(nodes=int, edges=int, seconds=float, bare=float):
    began = time.perf_counter()
    count = 0
    for vertex in ctx.graph.vertices:
        count += 1
    bare = time.perf_counter() - began
    began = time.perf_counter()
    nodes, edges = [], []
    for vertex in ctx.graph.vertices:
        properties = vertex.properties
        i = properties.get("id")
        if i is None or properties.get("label_folded") is None and properties.get("type") is None:
            continue
        nodes.append((i, properties.get("type"), properties.get("head_node_id"), properties.get("deleted"),
                      properties.get("merged_into"), properties.get("published"), properties.get("target_id")))
        for edge in vertex.out_edges:
            p = edge.properties
            if p.get("reverse") or p.get("derived"):
                continue
            edges.append((i, edge.to_vertex.properties.get("id"), edge.type.name, p.get("computed"), p.get("percent")))
    return mgp.Record(nodes=len(nodes), edges=len(edges), seconds=time.perf_counter() - began, bare=bare)
'''
PATH = "/var/lib/memgraph/internal_modules/pg_scan_trial.py"


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    from pangloss_core import settings as core_settings
    from pangloss_fastrp import maths
    from pangloss_fastrp.cypher_reader import load_all, reading
    from pangloss_fastrp.maps import graph_maps

    database = core_settings.get_settings().DATABASE
    driver = neo4j.GraphDatabase.driver(database.DB_URL, auth=(database.DB_USERNAME, database.DB_PASSWORD))

    def run(q, **p):
        with driver.session() as s:
            return [r.data() for r in s.run(q, **p)]

    try:
        run("CALL mg.delete_module_file($path)", path=PATH)
    except Exception:  # noqa: BLE001
        pass
    run("CALL mg.create_module_file('pg_scan_trial.py', $text) YIELD path RETURN path", text=MODULE)
    for _ in range(2):
        began = time.perf_counter()
        found = run("CALL pg_scan_trial.scan() YIELD nodes, edges, seconds, bare RETURN nodes, edges, seconds, bare")[0]
        print(f"in the module: {found['nodes']:,} nodes and {found['edges']:,} forward edges read in "
              f"{found['seconds']:.1f} s (a bare pass over every vertex: {found['bare']:.1f} s); the call "
              f"{time.perf_counter() - began:.1f} s")
    run("CALL mg.delete_module_file($path)", path=PATH)

    maps = graph_maps()
    began = time.perf_counter()
    graph = await load_all(maps)
    print(f"load_all through Cypher: {time.perf_counter() - began:.1f} s ({len(graph.node):,} nodes)")
    documents = [n.id for n in graph.node.values() if maps.is_in(n) and maps.documents.get(n.type) and graph.out.get(n.id)]
    sample = random.Random(2).sample(documents, 30)
    took, read, capped = [], [], 0
    for i in sample:
        began = time.perf_counter()
        try:
            made = await reading(maps, lambda reader, i=i: maths.refresh(reader, maps, [i], cap=50_000))
            took.append(time.perf_counter() - began)
            read.append(made.read)
        except maths.TooLarge:
            capped += 1
    took.sort()
    print(f"a refresh of one document by the Python engine through Cypher, {len(sample)} documents: "
          f"{capped} past the cap; of the rest, median {1000 * statistics.median(took):.0f} ms, "
          f"slowest {1000 * took[-1]:.0f} ms; nodes read: median {statistics.median(read):,.0f}, most {max(read):,}")
    quick = [t for t, r in zip(took, sorted(read), strict=True)]
    _ = quick


asyncio.run(main())
