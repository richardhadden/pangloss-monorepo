"""Make the entities of the smoke test (about 50,000) with the models' own API, as `importer`.

    ../.venv/bin/python smoke_scripts/ingest_entities.py      # from pangloss-smoketest/

Writes smoke_scripts/out/entities.json: the ids made, by type, for the factoids to refer to.
"""

import asyncio
import os
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fake  # noqa: E402
from fake import R  # noqa: E402
from pangloss_cli import load_project  # noqa: E402
from pangloss_models import initialise  # noqa: E402
from pangloss_users import current_request_username  # noqa: E402

OUT = Path(__file__).parent / os.environ.get("SMOKE_OUT", "out")
CONCURRENCY = 16
SCALE = float(os.environ.get("SMOKE_SCALE", "1"))

COUNTS = {
    "Person": 28000,
    "Family": 1500, "Guild": 400, "ReligiousOrder": 60, "Army": 200, "TradingCompany": 150,
    "University": 80, "Monastery": 600, "Court": 120,
    "Place": 200, "Settlement": 4000, "Region": 300, "Building": 2500,
    "PhysicalObject": 300, "Ship": 1200, "Manuscript": 2500, "Artwork": 200, "Painting": 2000, "Sculpture": 800,
    "Book": 1500, "Commodity": 0, "Currency": 0, "Language": 0, "Office": 3000, "Feast": 120,
}
COUNTS = {k: max(1, int(v * SCALE)) if v else 0 for k, v in COUNTS.items()}
timings: dict[str, list[float]] = {}
errors: list[str] = []


async def run_all(name: str, payloads, model) -> list[str]:
    sem = asyncio.Semaphore(CONCURRENCY)
    ids: list[str] = []
    times: list[float] = []

    async def one(p):
        async with sem:
            t = time.perf_counter()
            try:
                saved = await model.Create(**p).save()
                ids.append(str(saved.id))
            except Exception as e:  # (counted and reported, not fatal)
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:300]}")
            times.append(time.perf_counter() - t)

    start = time.perf_counter()
    await asyncio.gather(*(one(p) for p in payloads))
    took = time.perf_counter() - start
    timings[name] = times
    print(f"{name:16} {len(ids):6} in {took:7.1f} s  ({len(ids) / took if took else 0:6.0f}/s)", flush=True)
    return ids


async def main() -> None:
    project = load_project()
    if project.settings is None:
        sys.exit(project.settings_error)
    backend = project.require_database()
    project.import_models()
    t = time.perf_counter()
    initialise()
    print(f"initialise() {time.perf_counter() - t:.1f} s", flush=True)
    from smoke import models as m

    current_request_username.set("importer")
    await backend.connect()
    made: dict[str, list[str]] = {}
    started = time.perf_counter()
    try:
        # --- typologies, through their own API (a hierarchy)
        occ: dict[str, str] = {}
        for top, subs in fake.OCCUPATIONS.items():
            parent = await m.OccupationTypology.create(top)
            occ[top] = str(parent.id)
            for s in subs:
                occ[s] = str((await m.OccupationTypology.create(s, supertype=parent.id)).id)
        titles: dict[str, str] = {}
        for top, subs in fake.TITLES.items():
            parent = await m.TitleTypology.create(top)
            titles[top] = str(parent.id)
            for s in subs:
                titles[s] = str((await m.TitleTypology.create(s, supertype=parent.id)).id)
        made["OccupationType"] = list(occ.values())
        made["TitleType"] = list(titles.values())
        occ_ids = list(occ.values())
        title_ids = list(titles.values())

        # --- small vocabularies
        made["Commodity"] = await run_all("Commodity", [{"label": c} for c in fake.COMMODITIES], m.Commodity)
        made["Currency"] = await run_all("Currency", [{"label": c} for c in fake.CURRENCIES], m.Currency)
        made["Language"] = await run_all(
            "Language", [{"label": n, "iso_code": c} for n, c in fake.LANGUAGES], m.Language
        )

        # --- people
        def person(i: int) -> dict:
            first, last, gender = fake.person_name()
            p = {
                "label": f"{first} {last}",
                "known_as": {"value": f"{first} {last}", "certainty": R.randint(1, 5)},
                "gender": gender,
                "born": fake.birth_date(),
                "aliases": R.sample([f"{first} de' {last}", f"{first[0]}. {last}", f"{last}, {first}"], R.randint(0, 2)),
                "has_type": [{"type": "OccupationType", "id": t} for t in R.sample(occ_ids, R.randint(0, 2))],
            }
            if i % 10 == 0:
                # (some have a URL id from another database)
                p["id"] = f"https://example.org/smoke/person/{i}"
                p["create_new"] = True
            return p

        made["Person"] = await run_all("Person", [person(i) for i in range(COUNTS["Person"])], m.Person)

        # --- groups
        def group(kind: str, i: int) -> dict:
            base = {
                "Family": lambda: f"House of {R.choice(fake.SURNAMES)}",
                "Guild": lambda: f"Guild of {R.choice(fake.CRAFTS)} of {R.choice(fake.TOWNS)}",
                "ReligiousOrder": lambda: f"Order of St {R.choice(fake.SAINTS)} ({i})",
                "Army": lambda: f"Army of {R.choice(fake.SURNAMES)} ({year_txt()})",
                "TradingCompany": lambda: f"{R.choice(fake.SURNAMES)} & {R.choice(fake.SURNAMES)} company",
                "University": lambda: f"University of {R.choice(fake.TOWNS)}",
                "Monastery": lambda: f"Monastery of St {R.choice(fake.SAINTS)}, {R.choice(fake.TOWNS)}",
                "Court": lambda: f"Court of {R.choice(fake.REGIONS)}",
            }[kind]()
            p = {"label": base, "name": base}
            if kind == "Guild":
                p["craft"] = R.choice(fake.CRAFTS)
            if kind == "University":
                p["founded_year"] = fake.year(1200, 1600)
            return p

        def year_txt() -> str:
            return str(fake.year())

        for kind in ("Family", "Guild", "ReligiousOrder", "Army", "TradingCompany", "University", "Monastery", "Court"):
            made[kind] = await run_all(kind, [group(kind, i) for i in range(COUNTS[kind])], getattr(m, kind))

        # --- places
        def coords() -> dict:
            return {"latitude": round(R.uniform(36, 56), 4), "longitude": round(R.uniform(-9, 20), 4)}

        made["Region"] = await run_all(
            "Region", [{"label": f"{R.choice(fake.REGIONS)} {i}", "coordinates": coords()} for i in range(COUNTS["Region"])],
            m.Region,
        )
        made["Settlement"] = await run_all(
            "Settlement",
            [
                {"label": f"{R.choice(fake.TOWNS)}{R.choice(fake.SUFFIX)}", "coordinates": coords(),
                 "population_estimate": R.randint(200, 150000)}
                for _ in range(COUNTS["Settlement"])
            ],
            m.Settlement,
        )
        made["Building"] = await run_all(
            "Building",
            [{"label": f"{R.choice(fake.BUILDING_KINDS)} {R.choice(fake.SAINTS)}, {R.choice(fake.TOWNS)}"}
             for _ in range(COUNTS["Building"])],
            m.Building,
        )
        made["Place"] = await run_all("Place", [{"label": f"Field near {R.choice(fake.TOWNS)}"} for _ in range(200)], m.Place)

        # --- objects
        made["Ship"] = await run_all(
            "Ship", [{"label": f"The {R.choice(fake.SAINTS)} ({i})", "tonnage": R.randint(40, 1200)} for i in range(COUNTS["Ship"])],
            m.Ship,
        )
        made["Manuscript"] = await run_all(
            "Manuscript",
            [{"label": f"Codex {R.choice(fake.TOWNS)} {i}", "shelfmark": f"MS {R.randint(1, 999)}.{R.randint(1, 99)}"}
             for i in range(COUNTS["Manuscript"])],
            m.Manuscript,
        )
        for kind, word in (("Painting", "Portrait of"), ("Sculpture", "Bust of"), ("Artwork", "Tapestry of"),
                           ("PhysicalObject", "Chest of")):
            made[kind] = await run_all(
                kind, [{"label": f"{word} {R.choice(fake.FIRST_M + fake.FIRST_F)} {R.choice(fake.SURNAMES)}"}
                       for _ in range(COUNTS[kind])],
                getattr(m, kind),
            )
        made["Book"] = await run_all(
            "Book",
            [
                {"id": f"https://example.org/smoke/book/{i}", "create_new": True,
                 "label": f"De {R.choice(['re', 'arte', 'natura', 'vita', 'mercatura'])} {R.choice(fake.SURNAMES).lower()} ({i})",
                 "item_type": "book", "title": f"Book {i}", "creators": R.choice(fake.SURNAMES), "date": str(fake.year())}
                for i in range(COUNTS["Book"])
            ],
            m.Book,
        )

        # --- offices and feasts
        made["Office"] = await run_all(
            "Office",
            [{"label": f"{R.choice(fake.OFFICE_KINDS)} {R.choice(fake.TOWNS)}",
              "has_type": [{"type": "TitleType", "id": t} for t in R.sample(title_ids, R.randint(0, 1))]}
             for _ in range(COUNTS["Office"])],
            m.Office,
        )

        def feast(i: int) -> dict:
            when = {"type": "Recurrence", "frequency": "yearly", "weekdays": [], "excluded_days": [],
                    "start": {"type": "ExactDate", "year": 1450}, "end": {"type": "ExactDate", "year": 1650, "month": 12, "day": 31}}
            if i % 6 == 0:
                when["easter_offset"] = R.choice([-46, -7, -2, 0, 1, 39, 49, 60])
            else:
                when["month"], when["month_day"] = R.randint(1, 12), R.randint(1, 28)
            return {"label": f"Feast of St {R.choice(fake.SAINTS)} ({i})", "when": when,
                    "rank": R.choice(["double", "semidouble", "simple"]), "use": R.choice(["Roman", "Sarum", None])}

        made["Feast"] = await run_all("Feast", [feast(i) for i in range(COUNTS["Feast"])], m.Feast)
    finally:
        await backend.disconnect()

    total = sum(len(v) for v in made.values())
    took = time.perf_counter() - started
    print(f"TOTAL {total} entities in {took:.0f} s ({total / took:.0f}/s); {len(errors)} errors", flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / "entities.json").write_text(json.dumps(made))
    stats = {}
    for k, v in timings.items():
        if v:
            s = sorted(v)
            stats[k] = {"n": len(s), "p50_ms": round(s[len(s) // 2] * 1000, 1), "p95_ms": round(s[int(len(s) * 0.95)] * 1000, 1),
                        "max_ms": round(s[-1] * 1000, 1)}
    (OUT / "entity_timings.json").write_text(json.dumps({"stats": stats, "errors": errors[:200], "seconds": took}, indent=1))
    for e in errors[:15]:
        print("ERR", e)


if __name__ == "__main__":
    asyncio.run(main())
