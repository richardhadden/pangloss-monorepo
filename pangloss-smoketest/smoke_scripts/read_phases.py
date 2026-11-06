"""Where the time of reading an entity with many reverse relations goes: the query for what refers to it (all of it,
or some of each field), the whole read, and writing JSON.

    ../.venv/bin/python smoke_scripts/read_phases.py 01a1ae21-0af5-74ce-be8a-4f28ff7098e0
"""
import asyncio, sys, time, uuid

sys.path[:0] = ["smoke_scripts", "."]
from pangloss_cli import load_project  # noqa: E402
from pangloss_core import get_settings, storage_of  # noqa: E402
from pangloss_models import initialise  # noqa: E402

project = load_project()
backend = project.require_database()
project.import_models()
initialise()
import smoke.models as m  # noqa: E402

import neo4j  # noqa: E402
from pangloss_cypher.read_incoming import shown_relations  # noqa: E402
from pangloss_cypher.read_query import build_fetch_incoming_query  # noqa: E402
from pangloss_users import see_unpublished  # noqa: E402
from pydantic import TypeAdapter  # noqa: E402

db = get_settings().DATABASE
ID = uuid.UUID(sys.argv[1])


async def main() -> None:
    see_unpublished.set(True)
    await backend.connect()
    operations = storage_of().operations
    driver = neo4j.AsyncGraphDatabase.driver(db.DB_URL, auth=(db.DB_USERNAME, db.DB_PASSWORD))
    allowed = shown_relations(m.Person)
    async with driver.session() as session:
        for limit in (None, 25, 10):
            times = []
            for _ in range(3):
                t = time.perf_counter()
                query, params = build_fetch_incoming_query(m.Person, ID, allowed, limit=limit)
                records = await (await session.run(query, **params)).data()
                times.append(1000 * (time.perf_counter() - t))
            print(f"incoming query, limit {limit}: {min(times):.0f} ms ({len(records)} rows, "
                  f"{len({r['name'] for r in records})} fields, {sum({r['name']: r['total'] for r in records}.values())} in all)")
    for _ in range(2):
        t = time.perf_counter()
        found = await m.Person.get(ID)
        whole = 1000 * (time.perf_counter() - t)
        t = time.perf_counter()
        text = TypeAdapter(type(found)).dump_json(found, by_alias=True)
        dumped = 1000 * (time.perf_counter() - t)
        print(f"Person.get: {whole:.0f} ms; JSON {dumped:.0f} ms ({len(text) / 1024:.0f} KB)")
    for limit in (25, 10):
        t = time.perf_counter()
        found, counts = await operations.get_entity_with_some(m.Person, ID, limit)
        some = 1000 * (time.perf_counter() - t)
        text = TypeAdapter(type(found)).dump_json(found, by_alias=True)
        print(f"get_entity_with_some({limit}): {some:.0f} ms ({len(text) / 1024:.0f} KB; {len(counts)} fields, {sum(counts.values())} in all)")
    name = max(counts, key=lambda k: counts[k])
    for skip in (0, 50, 100, 150):
        t = time.perf_counter()
        page = await operations.get_incoming(m.Person, ID, name, skip=skip, limit=50)
        print(f"get_incoming({name}, skip {skip}): {1000 * (time.perf_counter() - t):.0f} ms, {len(page.items)} of {page.count}")
    await driver.close()
    await backend.disconnect()


asyncio.run(main())
