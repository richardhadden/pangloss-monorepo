"""Mixed read (and optionally write) load on the API: N clients for S seconds; prints throughput and latency per kind

    ../.venv/bin/python smoke_scripts/load_test.py [readers] [seconds] [writers]     # from pangloss-smoketest/
"""

import asyncio
import json
import random
import sys
import time
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).parent))
import statements  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
API = "http://localhost:8010/api"
READERS = int(sys.argv[1]) if len(sys.argv) > 1 else 32
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
WRITERS = int(sys.argv[3]) if len(sys.argv) > 3 else 0
R = random.Random(5)
entities = json.loads((OUT / "entities.json").read_text())
factoids = json.loads((OUT / "factoids.json").read_text())
TOKEN = dict(line.split("=", 1) for line in (HERE / ".secrets").read_text().split())["PANGLOSS_TOKEN"]
WORDS = ["Medici", "Giovanni", "Florence", "Fugger", "Anna", "Codex", "Guild", "Lorenzo", "Venice", "Maria"]


def read_request():
    k = R.random()
    if k < 0.3:
        return "get person", "GET", f"/Person/{R.choice(entities['Person'])}", None
    if k < 0.5:
        return "get factoid", "GET", f"/Factoid/{R.choice(factoids)}", None
    if k < 0.65:
        return "list search", "GET", f"/Person?q={R.choice(WORDS)}&page_size=25", None
    if k < 0.8:
        return "autocomplete", "GET", f"/autocomplete?q={R.choice(WORDS)[:4]}&type=Person&type=Group", None
    if k < 0.9:
        return "structured search", "POST", "/search", {"type": "Factoid", "where": {"statements": {"type": R.choice(
            ["Marriage", "Sale", "Letter", "Death", "Meeting"]), "where": {}}}}
    return "list page", "GET", f"/Settlement?page={R.randint(1, 80)}&page_size=50", None


async def main():
    stats: dict[str, list[float]] = {}
    codes: dict[str, int] = {}
    stop = time.perf_counter() + SECONDS
    pool = statements.Pool(entities, [{"type": "Book", "id": b} for b in entities["Book"][:200]])

    async def reader(c):
        while time.perf_counter() < stop:
            name, method, path, body = read_request()
            t = time.perf_counter()
            r = await c.request(method, API + path, json=body)
            stats.setdefault(name, []).append(time.perf_counter() - t)
            codes[str(r.status_code)] = codes.get(str(r.status_code), 0) + 1

    async def writer(c):
        i = 0
        while time.perf_counter() < stop:
            t = time.perf_counter()
            r = await c.post(API + "/Factoid", json=statements.factoid(pool, 900000 + i))
            stats.setdefault("write factoid", []).append(time.perf_counter() - t)
            codes[str(r.status_code)] = codes.get(str(r.status_code), 0) + 1
            i += 1

    async with httpx.AsyncClient(timeout=120, limits=httpx.Limits(max_connections=READERS + WRITERS + 4)) as c, \
            httpx.AsyncClient(timeout=120, headers={"Authorization": f"Bearer {TOKEN}"}) as w:
        await asyncio.gather(*[reader(c) for _ in range(READERS)], *[writer(w) for _ in range(WRITERS)])
    total = sum(len(v) for v in stats.values())
    print(f"{READERS} readers, {WRITERS} writers, {SECONDS} s: {total} requests, {total / SECONDS:.0f}/s; status {codes}")
    summary = {}
    for k, v in sorted(stats.items()):
        s = sorted(v)
        summary[k] = {"n": len(s), "p50_ms": round(s[len(s) // 2] * 1000), "p95_ms": round(s[int(len(s) * .95)] * 1000),
                      "p99_ms": round(s[int(len(s) * .99)] * 1000), "max_ms": round(s[-1] * 1000)}
        print(f"  {k:18} n={len(s):5}  p50 {summary[k]['p50_ms']:5} ms  p95 {summary[k]['p95_ms']:5} ms  p99 {summary[k]['p99_ms']:5} ms  max {summary[k]['max_ms']:5} ms")
    with (OUT / "load_test.jsonl").open("a") as f:
        f.write(json.dumps({"readers": READERS, "writers": WRITERS, "seconds": SECONDS, "total": total, "codes": codes, "kinds": summary}) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
