"""Step 7a.4's measurement (implementation_docs/similarity-build-plan.md): the similar of several types at once.

Two ways to search for the nearest items of some types:

A. each type is in a group of its own index: ask each group's index and merge by score;
B. ask the profile's whole index with `node.type IN $types`, and ask again for more while short.

The truth is the exact ten nearest of those types, by brute force over the stored vectors of the parts, combined as
`store.Layout.combine` does. Measured: for types that are about 50%, 5%, 0.5% and less of the items, how many of the
ten way B finds before it stops (at `MOST_FETCHED`, and at larger limits), and what it costs; and that way A equals
the truth. **It reads only.** Run from a scratch project (notes/similarity-evaluation/README.md):

    cd /tmp/similar-demo && /path/to/.venv/bin/python /path/to/notes/similarity-evaluation/field_types_recall.py
"""

import asyncio
import random
import statistics
import time
from collections import Counter

import numpy as np
from pangloss_cli import load_project
from pangloss_models import initialise

QUERIES = 30
K = 10
LIMITS = (4096, 16384, 65536)


async def main():
    project = load_project()
    backend = project.require_database()
    project.import_models()
    initialise()
    await backend.connect()
    from pangloss_core import backend as core_backend
    from pangloss_vectors import meta, store
    from pangloss_vectors.search import FETCH_GROWTH, search_query
    from pangloss_vectors.settings import overfetch

    assert "7690" in str(project.settings.DATABASE.DB_URL), "a scratch database only"
    database = core_backend.current().database()
    lay = store.layout("default")
    states = await store.states()
    profile = states.profiles["default"]
    print(f"profile default: {profile.count:,} vectors, dimension {lay.dimension}, weights {dict(lay.weights)}")

    # The vectors of the parts in use, combined as the store combines them
    @database.read_transaction
    async def read_part(tx, part, generation):
        result = await tx.run(
            f"MATCH (v:{store.VECTOR}) WHERE v.part = $part AND v.generation = $generation "
            "RETURN v.of AS of, v.type AS type, v.vector AS vector",
            part=part, generation=generation,
        )
        return [(r["of"], r["type"], r["vector"]) async for r in result]

    began = time.perf_counter()
    types: dict[str, str] = {}
    parts: dict[str, dict[str, list[float]]] = {}
    for name in lay.weights:
        rows = await read_part(name, states.parts[name].generation)
        parts[name] = {of: vector for of, _, vector in rows}
        types.update({of: type_name for of, type_name, _ in rows})
    ids = sorted(types)
    index = {of: n for n, of in enumerate(ids)}
    blocks = []
    for name, weight in lay.weights.items():
        block = np.zeros((len(ids), int(lay.dimensions[name])))
        for of, vector in parts[name].items():
            block[index[of]] = vector
        length = np.linalg.norm(block, axis=1, keepdims=True)
        blocks.append(np.where(length > 0, block / np.maximum(length, 1e-300), 0.0) * np.sqrt(weight))
    matrix = np.hstack(blocks)
    length = np.linalg.norm(matrix, axis=1, keepdims=True)
    unit = np.where(length > 0, matrix / np.maximum(length, 1e-300), 0.0)
    has = (length > 0).ravel()
    type_of = np.array([types[of] for of in ids])
    counts = Counter(type_of[has])
    total = int(has.sum())
    print(f"{total:,} items with a vector, of {len(counts)} classes; read and combined in "
          f"{time.perf_counter() - began:.1f} s")

    def nearest_share(share):
        return min(counts, key=lambda name: abs(counts[name] / total - share))

    chosen = []
    for share in (0.5, 0.05, 0.005, 0.0005):
        name = nearest_share(share)
        if name not in chosen:
            chosen.append(name)
    chooser = random.Random(7)
    queries = chooser.sample([of for of in ids if has[index[of]]], QUERIES)

    def truth(of, wanted):
        scores = unit @ unit[index[of]]
        mask = np.isin(type_of, list(wanted)) & has
        mask[index[of]] = False
        candidates = np.flatnonzero(mask)
        best = candidates[np.argsort(-scores[candidates], kind="stable")[:K]]
        return [ids[n] for n in best], [float(scores[n]) for n in best]

    filtered = search_query(lay.index_name).replace(
        "AND node.of <> $of ", "AND node.of <> $of AND node.type IN $types "
    )
    assert "$types" in filtered

    async def ask(tx, query, **parameters):
        result = await tx.run(query, **parameters)
        return [(str(r["id"]), float(r["score"])) async for r in result]

    async def way_b(of, wanted, limit):
        """As `search.nearest` asks: more while short, to `limit`"""

        @database.read_transaction
        async def search(tx):
            vector = [float(x) for x in matrix[index[of]]]
            fetch = K * overfetch() + 1
            enough = min(2 * (profile.count + profile.removed) + 1, limit)
            asked = 0
            while True:
                hits = await ask(tx, filtered, profile="default", fetch=fetch, vector=vector, of=of, k=K,
                                 see_unpublished=True, types=sorted(wanted))
                asked += 1
                if len(hits) >= K or fetch >= enough:
                    return hits, asked, fetch
                fetch = min(fetch * FETCH_GROWTH, enough)

        began = time.perf_counter()
        hits, asked, fetch = await search()
        return hits, asked, fetch, time.perf_counter() - began

    print(f"\nB. the whole index with `type IN`, {QUERIES} items asked about, the ten nearest of a class")
    print(f"   (overfetch {overfetch()}, growth {FETCH_GROWTH}; 'right' is of the true ten, by brute force)")
    for name in chosen:
        share = counts[name] / total
        for limit in LIMITS:
            right, got, times, fetches, rounds = [], [], [], [], []
            for of in queries:
                true_ids, _ = truth(of, {name})
                hits, asked, fetch, took = await way_b(of, {name}, limit)
                right.append(len(set(true_ids) & {i for i, _ in hits}) / max(len(true_ids), 1))
                got.append(len(hits))
                times.append(took)
                fetches.append(fetch)
                rounds.append(asked)
            print(f"  {name:<22} {counts[name]:>8,} ({share:7.3%})  limit {limit:>6,}: right {statistics.mean(right):6.1%}, "
                  f"given {statistics.mean(got):4.1f} of {K}; asked {statistics.mean(rounds):.1f} times, last for "
                  f"{statistics.median(fetches):,.0f}; {1000 * statistics.median(times):7.1f} ms median, "
                  f"{1000 * max(times):7.1f} ms most")
            if statistics.mean(got) >= K and statistics.mean(rounds) == 1:
                break

    print("\nA. each group's index, merged by score, against the truth over the classes of those groups")
    groups = meta.groups()
    in_groups = {name for name in counts if meta.groups_of(name)}
    print(f"   groups {groups}: {sum(counts[n] for n in in_groups):,} items of {len(in_groups)} classes")
    if len(groups) >= 2:
        right, times, same_order = [], [], 0
        for of in queries:
            true_ids, _ = truth(of, in_groups)
            vector = [float(x) for x in matrix[index[of]]]
            began = time.perf_counter()
            merged = []
            for group in groups:

                @database.read_transaction
                async def search(tx, group=group):
                    return await ask(tx, search_query(lay.group_index_name(group)), profile="default",
                                     fetch=K * overfetch() + 1, vector=vector, of=of, k=K, see_unpublished=True)

                merged += await search()
            merged = sorted(set(merged), key=lambda hit: (-hit[1], hit[0]))[:K]
            times.append(time.perf_counter() - began)
            right.append(len(set(true_ids) & {i for i, _ in merged}) / max(len(true_ids), 1))
            same_order += [i for i, _ in merged] == true_ids
        print(f"  right {statistics.mean(right):6.1%}; the same ten in the same order for {same_order} of {QUERIES}; "
              f"{1000 * statistics.median(times):.1f} ms median, {1000 * max(times):.1f} ms most")

    print("\nC. an exact scan of a class's vectors in the database (what a rare class could get instead)")
    for name in chosen[1:]:
        label = lay.label

        @database.read_transaction
        async def scan(tx, name=name):
            result = await tx.run(
                f"MATCH (v:{store.VECTOR}) WHERE v.type = $type RETURN count(v) AS n", type=name
            )
            return (await result.single())["n"]

        began = time.perf_counter()
        try:
            found = await scan()
            print(f"  {name:<22} counting its part vectors by type: {found:,} in "
                  f"{1000 * (time.perf_counter() - began):.0f} ms (label {label})")
        except Exception as error:  # noqa: BLE001
            print(f"  {name}: {type(error).__name__}: {error}")
    close = getattr(backend, "close", None)
    if close is not None:
        await close()


asyncio.run(main())
