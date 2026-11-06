"""One person with a ridiculous number of statements about them: 3,000 factoids over the REST API, in which about half
of every person slot is them (so every kind of statement, in every role, in spaces and conjunctions).

    ../.venv/bin/python smoke_scripts/ingest_superperson.py [N]       # from pangloss-smoketest/
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).parent))
import statements  # noqa: E402
from fake import R  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "out"
API = "http://localhost:8010/api"
TOKEN = dict(line.split("=", 1) for line in (HERE / ".secrets").read_text().split())["PANGLOSS_TOKEN"]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
SUPER_URL = "https://example.org/smoke/person/bartolomeo-ubiquitous"


class SuperPool(statements.Pool):
    def __init__(self, entities, sources, super_id):
        super().__init__(entities, sources)
        self.super = {"type": "Person", "id": super_id}

    def person(self) -> dict:
        return dict(self.super) if R.random() < 0.5 else super().person()


async def main() -> None:
    entities = json.loads((OUT / "entities.json").read_text())
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {TOKEN}"}, timeout=300) as c:
        r = await c.get(f"{API}/Person/{SUPER_URL}")
        if r.status_code == 404:
            r = await c.post(f"{API}/Person", json={
                "id": SUPER_URL, "createNew": True, "label": "Bartolomeo Ubiquitous",
                "knownAs": {"value": "Bartolomeo detto l'Onnipresente", "certainty": 3}, "gender": "male",
                "born": {"type": "EDTFDate", "edtf": "1470~"}, "aliases": ["Bartolomeo", "il Ubiquo", "Bart. Ubiq."],
                "hasType": [{"type": "OccupationType", "id": i} for i in entities["OccupationType"][:5]]})
            r.raise_for_status()
        super_id = r.json()["id"]
        print("super person", super_id, flush=True)
        r = await c.get(f"{API}/ZoteroObject", params={"page_size": 100})
        sources = [{"type": "ZoteroObject", "id": i["id"]} for i in r.json()["results"]]
        pool = SuperPool(entities, sources, super_id)
        payloads = [statements.factoid(pool, 100000 + i) for i in range(N)]
        for p in payloads:
            p["label"] = p["label"].replace("Factoid", "Ubiquitous factoid")
        sem = asyncio.Semaphore(8)
        times, ids, errs = [], [], []

        async def one(p):
            async with sem:
                t = time.perf_counter()
                r = await c.post(f"{API}/Factoid", json=p)
                times.append(time.perf_counter() - t)
                (ids.append(r.json()["id"]) if r.status_code == 201 else errs.append(r.text[:500]))

        t0 = time.perf_counter()
        await asyncio.gather(*(one(p) for p in payloads))
        took = time.perf_counter() - t0
    s = sorted(times)
    summary = {"super_id": super_id, "made": len(ids), "errors": len(errs), "seconds": round(took),
               "p50_ms": round(s[len(s) // 2] * 1000), "p95_ms": round(s[int(len(s) * .95)] * 1000), "first_errors": errs[:5]}
    print(json.dumps(summary), flush=True)
    (OUT / "superperson.json").write_text(json.dumps({**summary, "factoids": ids}))


if __name__ == "__main__":
    asyncio.run(main())
