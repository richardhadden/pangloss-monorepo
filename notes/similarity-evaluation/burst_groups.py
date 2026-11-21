"""Step 7a.1's trial (implementation_docs/similarity-build-plan.md): a burst refreshed in groups.

Today `part.refresh_ids` gives every head of a batch to one `maths.refresh`; 200 factoids are past the cap together
and all are approximated. The step halves the heads on `TooLarge`. The questions here:

1. can the halves run inside one `reading(...)`, on one reader that remembers what it read, so that what the failed
   attempts read is not read again;
2. what the attempts cost with and without that, and from what size of group it is cheapest to start;
3. how many single heads are past the cap alone (the only ones that should be approximated).

**It reads only.** The heads are factoids already in the database (the "measured N" factoids `measure_worker.py`
left), taken as if they had just been written. Run from a scratch project (notes/similarity-evaluation/README.md):

    cd /tmp/similar-demo && /path/to/.venv/bin/python /path/to/notes/similarity-evaluation/burst_groups.py [HEADS]
"""

import asyncio
import sys
import time

from pangloss_cli import load_project
from pangloss_models import initialise

HEADS = int(sys.argv[1]) if len(sys.argv) > 1 else 200


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    from pangloss_core import backend as core_backend
    from pangloss_fastrp import maps, maths
    from pangloss_fastrp.cypher_reader import CITING_QUERIES, CypherReader, reading
    from pangloss_fastrp.part import changed_stops
    from pangloss_fastrp.settings import refresh_cap

    database = core_backend.current().database()
    assert "7690" in str(project.settings.DATABASE.DB_URL), "a scratch database only"

    @database.read_transaction
    async def heads_of(tx):
        result = await tx.run(
            "MATCH (f:Factoid:HeadNode) WHERE f.label STARTS WITH 'measured' "
            "AND coalesce(f.deleted, false) = false RETURN f.id AS id ORDER BY f.id LIMIT $n",
            n=HEADS,
        )
        return [r["id"] async for r in result]

    heads = await heads_of()
    graph = maps.graph_maps()
    cap = refresh_cap()
    print(f"{len(heads)} heads, cap {cap:,}, steps {list(graph.steps)}")

    class Counting(CypherReader):
        """How many queries and ids go to the database"""

        def __init__(self, *args):
            super().__init__(*args)
            self.queries = self.asked = 0

        def _run(self, query, **parameters):
            self.queries += 1
            self.asked += len(parameters.get("ids", ()))
            return super()._run(query, **parameters)

    CITING_WITH_TARGET = tuple(q.replace("RETURN c.id AS id", "RETURN c.id AS id, c.target_id AS target")
                               for q in CITING_QUERIES)

    class Remembering(Counting):
        """A reader that asks the database for an id once in its life (one transaction: one snapshot on Memgraph)"""

        def __init__(self, *args):
            super().__init__(*args)
            self._node, self._out, self._in, self._citing, self._below = {}, {}, {}, {}, {}

        def nodes(self, ids=None):
            ids = sorted({str(i) for i in ids or ()})
            missing = [i for i in ids if i not in self._node]
            if missing:
                for i in missing:
                    self._node[i] = None
                for node in super().nodes(missing):
                    self._node[node.id] = node
            return [n for i in ids if (n := self._node[i]) is not None]

        def _grouped(self, cache, ids, fetch, key):
            ids = sorted({str(i) for i in ids})
            missing = [i for i in ids if i not in cache]
            if missing:
                for i in missing:
                    cache[i] = []
                for found in fetch(missing):
                    cache[key(found)].append(found)
            return [found for i in ids for found in cache[i]]

        def out_edges(self, ids):
            return self._grouped(self._out, ids, super().out_edges, lambda e: e.source)

        def in_edges(self, ids):
            return self._grouped(self._in, ids, super().in_edges, lambda e: e.target)

        def citing(self, ids):
            def fetch(missing):
                rows = []
                for query in CITING_WITH_TARGET:
                    rows += self._each(query, missing)
                return rows

            return sorted({str(r["id"]) for r in self._grouped(self._citing, ids, fetch, lambda r: str(r["target"]))})

        def below(self, heads):
            heads = sorted({str(h) for h in heads})
            missing = [h for h in heads if h not in self._below]
            if missing:
                for h in missing:
                    self._below[h] = []
                for row in self._each(
                    "UNWIND $ids AS id MATCH (n:PGIndexableNode {head_node_id: id}) RETURN n.id AS id, id AS head",
                    missing,
                ):
                    self._below[str(row["head"])].append(str(row["id"]))
            return sorted({i for h in heads for i in self._below[h]})

    def attempt(reader, group, log):
        """One refresh of a group of heads: its vectors, or None past the cap"""
        began = time.perf_counter()
        queries = reader.queries
        try:
            centre = changed_stops(reader, graph, group)
            made = maths.refresh(reader, graph, centre, cap)
            log.append((len(group), "ok", time.perf_counter() - began, reader.queries - queries, len(made.vectors)))
            return made.vectors
        except maths.TooLarge:
            log.append((len(group), "too large", time.perf_counter() - began, reader.queries - queries, 0))
            return None

    def halving(reader, group, log, vectors, alone):
        made = attempt(reader, group, log)
        if made is not None:
            vectors.update(made)
        elif len(group) == 1:
            alone.append(group[0])
        else:
            half = len(group) // 2
            halving(reader, group[:half], log, vectors, alone)
            halving(reader, group[half:], log, vectors, alone)

    def run(start, log, vectors, alone):
        def work(reader):
            for at in range(0, len(heads), start):
                halving(reader, heads[at : at + start], log, vectors, alone)
            return reader.queries, reader.asked

        return work

    async def one_reader(kind, start):
        """Every group within one `reading`, on one reader of this kind"""
        log, vectors, alone = [], {}, []
        began = time.perf_counter()

        @database.read_transaction
        async def go(tx):
            reader = kind(tx, asyncio.get_running_loop(), graph)
            return await asyncio.to_thread(run(start, log, vectors, alone), reader)

        queries, asked = await go()
        return time.perf_counter() - began, log, vectors, alone, queries, asked

    def said(name, took, log, vectors, alone, queries, asked):
        fitted = sorted({size for size, how, *_ in log if how == "ok"}, reverse=True)
        failed = [t for _, how, t, *_ in log if how != "ok"]
        print(f"  {name:<46} {took:6.2f} s; {len(log):3d} attempts ({len(failed)} too large, {sum(failed):.2f} s in "
              f"them); {queries:5d} queries, {asked:8,d} ids asked; {len(vectors):6,d} vectors; "
              f"{len(alone)} heads past the cap alone; sizes that fitted {fitted[:6]}")

    print("\n1. as today: every head to one refresh")
    took, log, vectors, alone, queries, asked = await one_reader(Counting, len(heads))
    # (today it stops at the first `TooLarge`: only the first attempt is today's)
    first = log[0]
    print(f"  the first attempt: {first[1]}, {first[2]:.2f} s, {first[3]} queries")
    print("\n2. halved from the whole batch")
    said("a reader that remembers nothing", took, log, vectors, alone, queries, asked)
    plain = vectors
    result = await one_reader(Remembering, len(heads))
    said("one reader that remembers, one transaction", *result)
    remembered = result[2]
    same = set(plain) == set(remembered) and all(
        float(abs(plain[i] - remembered[i]).max()) < 1e-9 for i in plain
    )
    print(f"  the two give the same vectors: {same}")

    print("\n3. one reader that remembers, starting from groups of a size")
    for start in (100, 50, 25, 10, 5, 1):
        result = await one_reader(Remembering, start)
        said(f"groups of {start}", *result)
        if set(result[2]) != set(remembered):
            print("    (other vectors than halving from the whole)")

    print("\n4. each head alone: how large is its neighbourhood")

    def sizes(reader):
        found = []
        for head in heads:
            began = time.perf_counter()
            try:
                made = maths.refresh(reader, graph, changed_stops(reader, graph, [head]), None)
                found.append((made.read, len(made.vectors), time.perf_counter() - began))
            except maths.TooLarge:
                found.append((None, 0, time.perf_counter() - began))
        return found

    if HEADS <= 60:
        found = await reading(graph, sizes)
        reads = sorted(r for r, _, _ in found)
        print(f"  nodes read around one head: median {reads[len(reads) // 2]:,}, most {reads[-1]:,}; "
              f"past the cap of {cap:,} alone: {sum(1 for r in reads if r > cap)}")
    else:
        print("  (skipped above 60 heads: without a cap a hub's neighbourhood is read whole)")
    close = getattr(backend, "close", None)
    if close is not None:
        await close()


asyncio.run(main())
