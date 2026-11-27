"""The lookup of step 6.3 as built (`pangloss_compare.pairs.pairs_of`: the statement read, its pairs by rule found
and read) and the verdict on each pair, timed on the world for comparison at size.

    uv run python notes/similarity-evaluation/compare_pairs_built.py memgraph bolt://localhost:7716
    uv run python notes/similarity-evaluation/compare_pairs_built.py neo4j bolt://localhost:7717
"""

import asyncio
import collections
import random
import statistics
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASSES = ("Activity", "Transfer", "Attendance", "Birth", "Making", "MakingOfPicture", "Order")  # fmt: skip


def planted_script():
    source = (HERE / "planted.py").read_text(encoding="utf-8").replace("\nmain()\n", "\n")  # fmt: skip
    module = types.ModuleType("planted_script")
    exec(compile(source, "planted.py", "exec"), module.__dict__)
    module.COMPARED = module.DATED = True
    return module


async def main(backend: str, url: str) -> None:
    script = planted_script()
    storage = await script.connected(backend, url, ["pangloss_derived", "pangloss_library", "pangloss_criteria", "pangloss_compare"])  # fmt: skip
    from pangloss_compare import maths, pairs, rules
    from pangloss_core import backend as current_backend

    database = current_backend.current().database()

    @database.read_transaction
    async def ids_of(tx, kind):
        result = await tx.run(f"MATCH (s:{kind}) RETURN s.id AS id LIMIT 3000")
        return [str(r["id"]) async for r in result]

    known = rules.rules()
    for kind in CLASSES:
        ids = await ids_of(kind)
        random.Random(1).shuffle(ids)
        times, counts, relations = [], [], collections.Counter()
        for id in ids[:60]:
            began = time.perf_counter()
            statement, others, found = await pairs.pairs_of(id, False)
            if statement is not None:
                for pair in found.found:
                    relations[maths.verdict(statement, others[pair.id], known).relation] += 1  # fmt: skip
            times.append((time.perf_counter() - began) * 1000)
            counts.append(len(found.found))
        ordered = sorted(times)
        print(
            f"{backend} {kind:16} pairs median {statistics.median(counts):.0f} most {max(counts)}; "
            f"ms median {statistics.median(times):.1f} 90% {ordered[53]:.1f} most {ordered[-1]:.1f}; "
            + ", ".join(f"{name} {count}" for name, count in relations.most_common(6))
        )
    await storage.setup.disconnect()


asyncio.run(main(sys.argv[1], sys.argv[2]))
