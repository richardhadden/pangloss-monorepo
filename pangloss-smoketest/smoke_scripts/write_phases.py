"""Where the time of writing one factoid of n statements goes: making the queries (Python) and running them (the
database), without keeping what is written (the transaction is rolled back). On Neo4j:
`PANGLOSS_SETTINGS=smoketest_site.settings_neo4j SMOKE_OUT=out-neo4j`.

    ../.venv/bin/python smoke_scripts/write_phases.py 10,20,40,80 Death
"""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path[:0] = ["smoke_scripts", "."]
import statements  # noqa: E402
from fake import R  # noqa: E402
from pangloss_cli import load_project  # noqa: E402
from pangloss_core import get_settings  # noqa: E402
from pangloss_models import initialise  # noqa: E402

project = load_project()
backend = project.require_database()
project.import_models()
initialise()
import smoke.models as m  # noqa: E402

import neo4j  # noqa: E402
from pangloss_cypher import render_write  # noqa: E402
from pangloss_cypher.write_plan import plan_create  # noqa: E402
from pangloss_users import current_request_username  # noqa: E402

e = json.loads(Path(f"smoke_scripts/{os.environ.get('SMOKE_OUT', 'out')}/entities.json").read_text())
pool = statements.Pool(e, [{"type": "Book", "id": e["Book"][4]}])
kinds = sys.argv[2].split(",") if len(sys.argv) > 2 else statements.KINDS
db = get_settings().DATABASE


async def main() -> None:
    current_request_username.set("importer")
    driver = neo4j.AsyncGraphDatabase.driver(db.DB_URL, auth=(db.DB_USERNAME, db.DB_PASSWORD))
    for n in [int(x) for x in sys.argv[1].split(",")]:
        payload = {"label": f"Phases {n}", "source": pool.source(), "statements": [statements.make(pool, R.choice(kinds)) for _ in range(n)]}
        t0 = time.perf_counter()
        instance = m.Factoid.Create(**payload)
        t1 = time.perf_counter()
        db_instance = instance._to_db_model() if hasattr(instance, "_to_db_model") else instance
        if asyncio.iscoroutine(db_instance):
            db_instance = await db_instance
        t2 = time.perf_counter()
        plan = plan_create(db_instance)
        made = render_write.render(plan)
        t3 = time.perf_counter()
        async with driver.session(database=db.DATABASE_NAME) as session:
            tx = await session.begin_transaction()
            for statement in made:
                result = await tx.run(statement.text, **statement.params)
                await result.consume()
            t4 = time.perf_counter()
            await tx.rollback()
        print(
            f"{n:4} statements: validate {1000 * (t1 - t0):6.0f} ms, to db model {1000 * (t2 - t1):6.0f} ms, plan+render "
            f"{1000 * (t3 - t2):6.0f} ms, database {1000 * (t4 - t3):8.0f} ms; {len(made)} queries, "
            f"{sum(statement.rows for statement in made)} rows",
            flush=True,
        )
    await driver.close()


asyncio.run(main())
