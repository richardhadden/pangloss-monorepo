"""Does Memgraph's vector index lose a node whose vector is written again in place?

Found 2026-11-22 from `e2e/test_similar.py`, which failed now and then: three people whose profile vectors had been
written twice (first of the class part alone, then with the graph part) carried the label of the group's index
(`PGV_default_181_Person`) and their vectors, the index said it held 16 entries, and a search of it for 40 gave 13:
not those three. The index of the other label of the same nodes gave them. This asks it of Memgraph alone.

    uv run python notes/similarity-evaluation/lost_in_index.py bolt://localhost:7702 test test [rounds] [searchers] \\
        [in_place|again] [same|distinct] [keep]

Each round: 8 nodes with two labels, each label with a vector index on `vector`, written one at a time with one
shared vector (`same`: as items whose profile vector is of the class part alone) or with a random one each
(`distinct`); six of them written again by the statement `pangloss_vectors.store` uses (MERGE ... SET labels, vector)
in one transaction (`in_place`), or deleted and made again (`again`), as two families of three with a vector each;
`searchers` threads search the second index meanwhile. Then each of the six is asked, in each index, for the 21
nearest its own vector, and those not among them are counted. `keep`: the rounds' nodes stay (the index grows).

What it gave on Memgraph 3.14 (2026-11-22), 120 rounds kept: `same`, 684 of 720 not found, in place or made again,
with a searcher or none; `distinct`, 22 of 720. `lost_in_index_sized.py` is the same at a size, with an exact scan
beside it.
"""

import random
import sys
import threading

import neo4j

DIM = 181
A, B = "LostTrialAll", "LostTrialGroup"


def vector(rng: random.Random) -> list[float]:
    return [rng.gauss(0, 1) for _ in range(DIM)]


def main() -> None:
    uri, user, password = sys.argv[1:4]
    rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    searchers = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    way = sys.argv[6] if len(sys.argv) > 6 else "in_place"
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    rng = random.Random(1)

    def run(text: str, **parameters):
        with driver.session() as session:
            return [r.data() for r in session.run(text, **parameters)]

    for name, label in (("lost_trial_all", A), ("lost_trial_group", B)):
        try:
            run(f"DROP VECTOR INDEX {name}")
        except Exception:  # noqa: BLE001
            pass
    run(f"MATCH (n:{A}) DETACH DELETE n")
    for name, label in (("lost_trial_all", A), ("lost_trial_group", B)):
        run(
            f"CREATE VECTOR INDEX {name} ON :{label}(vector) "
            f'WITH CONFIG {{"dimension": {DIM}, "capacity": 2048, "metric": "cos"}}'
        )
    stop = threading.Event()

    def search() -> None:
        own = random.Random(2)
        while not stop.is_set():
            try:
                run(
                    "CALL vector_search.search('lost_trial_group', 21, $v) YIELD node, distance "
                    "WITH id(node) AS i MATCH (n) WHERE id(n) = i RETURN n.of AS of",
                    v=vector(own),
                )
            except Exception:  # noqa: BLE001
                pass

    threads = [threading.Thread(target=search, daemon=True) for _ in range(searchers)]
    for thread in threads:
        thread.start()
    write = (
        f"UNWIND $rows AS row MERGE (n:PGLostTrial {{of: row.of, generation: 1}}) "
        f"SET n:{A}:{B}, n.type = 'Person', n.vector = row.vector"
    )
    lost = {A: 0, B: 0}
    lost_rounds = 0
    distinct = len(sys.argv) > 7 and sys.argv[7] == "distinct"
    keep = len(sys.argv) > 8 and sys.argv[8] == "keep"
    class_part = [0.0] * 128 + [x * 0.3 for x in vector(rng)[: DIM - 128]]

    def unit(values: list[float]) -> list[float]:
        size = sum(x * x for x in values) ** 0.5
        return [x / size for x in values]

    def with_graph() -> list[float]:
        return unit(vector(rng)[:128]) + class_part[128:]

    for round_ in range(rounds):
        ofs = [f"{round_}-{n}" for n in range(8)]
        for of in ofs:  # (as the worker does after each person is made: one at a time, the class part alone)
            run(
                write,
                rows=[{"of": of, "vector": vector(rng) if distinct else class_part}],
            )
        if distinct:
            again = [{"of": of, "vector": vector(rng)} for of in ofs[:6]]
        else:  # (two families of three, each with one graph part)
            first, second = with_graph(), with_graph()
            again = [
                {"of": of, "vector": first if n < 3 else second}
                for n, of in enumerate(ofs[:6])
            ]
        if way == "in_place":
            run(write, rows=again)
        else:  # delete and make again, in one transaction
            with driver.session() as session:
                with session.begin_transaction() as tx:
                    tx.run(
                        "UNWIND $ofs AS of MATCH (n:PGLostTrial {of: of}) DETACH DELETE n",
                        ofs=ofs[:6],
                    ).consume()
                    tx.run(
                        f"UNWIND $rows AS row CREATE (n:PGLostTrial:{A}:{B} {{of: row.of, generation: 1, "
                        "type: 'Person', vector: row.vector})",
                        rows=again,
                    ).consume()
                    tx.commit()
        missing_here = False
        for name, label in (("lost_trial_all", A), ("lost_trial_group", B)):
            found = set()
            # (the six written twice: each must be among the 21 nearest its own vector, which is its family's, or
            # its own alone; the two written once share their vector with every other such node, and are not asked)
            for of in ofs[:6]:
                own = run(
                    "MATCH (n:PGLostTrial {of: $of}) RETURN n.vector AS v", of=of
                )[0]["v"]
                hits = run(
                    f"CALL vector_search.search('{name}', 21, $v) YIELD node, distance "
                    "WITH id(node) AS i, distance MATCH (n) WHERE id(n) = i RETURN n.of AS of, distance",
                    v=own,
                )
                if any(h["of"] == of and h["distance"] < 1e-4 for h in hits):
                    found.add(of)
            missing = set(ofs[:6]) - found
            if missing:
                missing_here = True
                lost[label] += len(missing)
                print(
                    f"round {round_}: {name} does not give {sorted(missing)} at their own vectors"
                )
        lost_rounds += missing_here
        if not keep:
            run(
                "MATCH (n:PGLostTrial) WHERE n.of STARTS WITH $p DETACH DELETE n",
                p=f"{round_}-",
            )
    stop.set()
    print(
        f"{way}, {rounds} rounds, {searchers} searchers: rounds with a loss {lost_rounds}; lost {lost}"
    )
    for name in ("lost_trial_all", "lost_trial_group"):
        run(f"DROP VECTOR INDEX {name}")
    run("MATCH (n:PGLostTrial) DETACH DELETE n")
    driver.close()


if __name__ == "__main__":
    main()
