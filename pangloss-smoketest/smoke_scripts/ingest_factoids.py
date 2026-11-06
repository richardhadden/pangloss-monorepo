"""Write the factoids of the smoke test over the REST API, as `importer` (a personal access token).

    ../.venv/bin/python smoke_scripts/ingest_factoids.py [N] [CONCURRENCY]     # from pangloss-smoketest/

Needs smoke_scripts/out/entities.json (from ingest_entities.py) and the server on :8010.
"""

import asyncio
import os
import json
import sys
import time
from pathlib import Path

import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).parent))
import statements  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / os.environ.get("SMOKE_OUT", "out")
API = os.environ.get("SMOKE_API", "http://localhost:8010/api")
TOKEN = os.environ.get("SMOKE_TOKEN") or dict(line.split("=", 1) for line in (HERE / ".secrets").read_text().split())["PANGLOSS_TOKEN"]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
CONCURRENCY = int(sys.argv[2]) if len(sys.argv) > 2 else 8


async def zotero_sources(client: httpx.AsyncClient) -> list[dict]:
    found: list[dict] = []
    page = 1
    while True:
        r = await client.get(f"{API}/ZoteroObject", params={"page": page, "page_size": 100})
        r.raise_for_status()
        body = r.json()
        items = body.get("results") or body.get("items") or []
        found += [{"type": "ZoteroObject", "id": i["id"]} for i in items]
        if len(items) < 100 or page >= 60:
            return found
        page += 1


async def main() -> None:
    entities = json.loads((OUT / "entities.json").read_text())
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        zot = await zotero_sources(client) if not os.environ.get("SMOKE_NO_ZOTERO") else []
        books = [{"type": "Book", "id": b} for b in entities["Book"][:300]]
        print(f"{len(zot)} Zotero items and {len(books)} books as sources", flush=True)
        pool = statements.Pool(entities, zot + books)
        payloads = [statements.factoid(pool, i) for i in range(N)]
        (OUT / "factoid_sample.json").write_text(json.dumps(payloads[:20], indent=1))

        sem = asyncio.Semaphore(CONCURRENCY)
        times: list[float] = []
        ids: list[str] = []
        errors: list[dict] = []
        status: dict[int, int] = {}

        async def one(i: int, p: dict):
            async with sem:
                t = time.perf_counter()
                r = await client.post(f"{API}/Factoid", json=p)
                times.append(time.perf_counter() - t)
                status[r.status_code] = status.get(r.status_code, 0) + 1
                if r.status_code == 201:
                    ids.append(r.json()["id"])
                else:
                    errors.append({"i": i, "status": r.status_code, "body": r.text[:1500], "payload": p})
                if (i + 1) % 500 == 0:
                    print(f"  {i + 1} sent, {len(ids)} made, {len(errors)} errors", flush=True)

        start = time.perf_counter()
        await asyncio.gather(*(one(i, p) for i, p in enumerate(payloads)))
        took = time.perf_counter() - start
    s = sorted(times)
    summary = {
        "made": len(ids), "errors": len(errors), "status": status, "seconds": round(took, 1),
        "per_second": round(len(ids) / took, 1), "p50_ms": round(s[len(s) // 2] * 1000), "p95_ms": round(s[int(len(s) * 0.95)] * 1000),
        "max_ms": round(s[-1] * 1000), "concurrency": CONCURRENCY,
    }
    print(json.dumps(summary), flush=True)
    (OUT / "factoids.json").write_text(json.dumps(ids))
    (OUT / "factoid_errors.json").write_text(json.dumps(errors[:300], indent=1))
    (OUT / "factoid_timings.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
