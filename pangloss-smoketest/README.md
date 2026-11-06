# pangloss-smoketest

A Pangloss project made with `pangloss new-project` / `new-app`, using every Pangloss package, filled with invented
early modern data and driven through the API, the CLI and the interface to find bugs and slow spots (2026-11-06).
**`REPORT.md` is the report; `PROBLEMS.md` the running log it was written from.**

| | |
|---|---|
| `smoketest_site/settings.py` | Every app; Memgraph on :7697; Zotero from `.env` (copied from `pangloss-demo/.env`, not committed) |
| `smoketest_site/settings_neo4j.py` | The same project on Neo4j :7699 (`PANGLOSS_SETTINGS=smoketest_site.settings_neo4j`) |
| `smoke/models.py` | 26 entity classes, 2 typologies, 68 concrete statement kinds under an abstract `Statement` (dated, single-dated, period, undated), spaces, a conjunction, the Zotero-sourced `Factoid` |
| `smoke/derived.py` | Three derived rules (SameGroup, MetWith, GaveTo) |
| `smoke/migrations/` | 0001 initial; 0002 a rename, an index, a new field (applied, rolled back, applied again) |
| `smoke_scripts/` | The data generator and every check (below); `out/` holds logs, timings, screenshots (not committed) |

## Running it again

```sh
docker start pangloss-memgraph-smoketest            # (or: docker run -d --name pangloss-memgraph-smoketest -p 7697:7687 \
                                                    #   -e MEMGRAPH_USER=test -e MEMGRAPH_PASSWORD=test memgraph/memgraph-mage:3.14.0 \
                                                    #   --experimental-enabled=commit-lock-narrowing)
cd pangloss-smoketest
../.venv/bin/pangloss migrate
../.venv/bin/pangloss users create --username importer --email importer@smoke-example.org --password smoke-importer-pw-2026 --no-admin < /dev/null
#   (and admin, editor, reviewer, reader the same way: passwords are smoke-<name>-pw-2026)
../.venv/bin/pangloss users tokens create importer --name ingest --scope write --expires-days 30
#   put the token in smoke_scripts/.secrets as PANGLOSS_TOKEN=pgl_...
../.venv/bin/pangloss run --port 8010 &
../.venv/bin/python smoke_scripts/ingest_entities.py          # ~50,000 entities (SMOKE_SCALE=0.1 for a tenth)
../.venv/bin/python smoke_scripts/ingest_factoids.py 5000 8   # factoids over REST
../.venv/bin/python smoke_scripts/ingest_superperson.py 3000  # one person in 3,000 factoids
../.venv/bin/pangloss interface dev --api-url http://localhost:8010 --port 3010 &
```

Then any of: `api_checks.py`, `search_checks.py`, `review_history_checks.py`, `edge_checks.py`, `typology_checks.py`,
`session_checks.py`, `zotero_checks.py`, `derived_delete.py`, `deep_orders.py 3,12,30`, `scaling.py 10,20,40,80 Death`,
`load_test.py 32 30 8`, `gzip_sizes.py [interface url]`, `ui_checks.py`, `ui_form.py`, `ui_features.py`,
`ui_history.py`, `ui_probe.py /path [login]`, `cypher.py "<read-only query>"`.

The checks change the data a little (they create, update, delete, review and restore), so their counts drift on a
second run.
