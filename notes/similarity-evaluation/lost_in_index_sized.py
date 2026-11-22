"""Memgraph's vector index among many identical vectors, at a size (the second trial of `lost_in_index.py`).

    uv run python notes/similarity-evaluation/lost_in_index_sized.py bolt://localhost:7702 test test N SHARE once|twice

N nodes: SHARE of them (0 to 1) have one vector they all share (as items joined to nothing have, whose profile vector
is of the class part alone); the rest are families of three, each family with a vector of its own that has the shared
one as a part (cosine 0.30 to the shared one, about 0.1 +- 0.1 between families). `once`: each written once, with its
vector, as a rebuild writes them. `twice`: each written first with the shared vector and the families' then written
again in place, as the worker does when a new item is later joined to something. Then 300 members of families are
each asked for the 21 nearest their own vector: how many are found themselves, and how many have both others of
their family; and the same by an exact scan with `vector_search.cosine_similarity`, with its time.
"""

import random
import sys
import time

import neo4j

DIM, LABEL, INDEX = 181, "LostSized", "lost_sized"


def main() -> None:
    uri, user, password, n, share, way = sys.argv[1:7]
    n, share = int(n), float(share)
    # (with a seventh argument: each node's stored vector moved by a little of its own, of this size beside a
    # vector of length 1, so that no two are the same)
    jitter = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    rng = random.Random(1)

    def run(text: str, **parameters):
        with driver.session() as session:
            return [r.data() for r in session.run(text, **parameters)]

    def clear() -> None:
        try:
            run(f"DROP VECTOR INDEX {INDEX}")
        except Exception:  # noqa: BLE001
            pass
        while run(
            f"MATCH (n:{LABEL}) WITH n LIMIT 20000 DETACH DELETE n RETURN count(*) AS c"
        )[0]["c"]:
            pass

    clear()
    try:
        run(f"CREATE INDEX ON :{LABEL}(of)")
    except Exception:  # noqa: BLE001
        pass
    run(
        f"CREATE VECTOR INDEX {INDEX} ON :{LABEL}(vector) "
        f'WITH CONFIG {{"dimension": {DIM}, "capacity": {max(2048, 2 * n)}, "metric": "cos"}}'
    )
    shared = [0.0] * 128 + [rng.gauss(0, 1) * 0.3 for _ in range(DIM - 128)]
    size = sum(x * x for x in shared) ** 0.5
    shared = [x / size * 0.3162 for x in shared]

    def family_vector() -> list[float]:
        graph = [rng.gauss(0, 1) for _ in range(128)]
        size = sum(x * x for x in graph) ** 0.5
        return [x / size for x in graph] + shared[128:]

    alone = int(n * share)
    families = (n - alone) // 3
    final = {f"a{i}": shared for i in range(alone)}
    members = []
    for f in range(families):
        vector = family_vector()
        for m in range(3):
            final[f"f{f}-{m}"] = vector
            members.append(f"f{f}-{m}")
    ofs = list(final)
    rng.shuffle(ofs)
    asked_by = dict(final)
    if jitter:
        for of, vector in list(final.items()):
            own = random.Random(of)
            final[of] = [x + own.gauss(0, 1) * jitter / DIM**0.5 for x in vector]
    stored_shared = shared
    write = f"UNWIND $rows AS row MERGE (n:{LABEL} {{of: row.of}}) SET n.vector = row.vector"
    started = time.monotonic()
    for start in range(0, len(ofs), 500):
        page = ofs[start : start + 500]
        run(
            write,
            rows=[
                {
                    "of": of,
                    "vector": (
                        final[of]
                        if not of.startswith("f")
                        else [
                            x
                            + random.Random(of + "first").gauss(0, 1)
                            * jitter
                            / DIM**0.5
                            for x in stored_shared
                        ]
                    )
                    if way == "twice"
                    else final[of],
                }
                for of in page
            ],
        )
    if way == "twice":
        again = [of for of in ofs if of.startswith("f")]
        for start in range(0, len(again), 500):
            run(
                write,
                rows=[
                    {"of": of, "vector": final[of]} for of in again[start : start + 500]
                ],
            )
    written = time.monotonic() - started
    asked = rng.sample(members, min(300, len(members)))
    itself = both = exact_both = 0
    index_time = scan_time = 0.0
    for of in asked:
        family = {f"{of.rsplit('-', 1)[0]}-{m}" for m in range(3)}
        t = time.monotonic()
        hits = run(
            f"CALL vector_search.search('{INDEX}', 21, $v) YIELD node, distance "
            "WITH id(node) AS i, distance MATCH (n) WHERE id(n) = i RETURN n.of AS of",
            v=asked_by[of],
        )
        index_time += time.monotonic() - t
        found = {h["of"] for h in hits}
        itself += of in found
        both += family <= found
        t = time.monotonic()
        scan = run(
            f"MATCH (n:{LABEL}) WITH n, vector_search.cosine_similarity(n.vector, $v) AS c "
            "ORDER BY c DESC, n.of LIMIT 21 RETURN n.of AS of",
            v=asked_by[of],
        )
        scan_time += time.monotonic() - t
        exact_both += family <= {h["of"] for h in scan}
    count = len(asked)
    print(
        f"jitter {jitter}: {n} nodes, {alone} with the shared vector, {families} families, written {way} ({written:.0f} s): "
        f"of {count} asked, the index gives the node itself {itself}, its whole family {both} "
        f"({index_time / count * 1000:.1f} ms a search); the exact scan its whole family {exact_both} "
        f"({scan_time / count * 1000:.1f} ms a search)"
    )
    clear()
    driver.close()


if __name__ == "__main__":
    main()
