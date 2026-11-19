"""The worker is exact in the end (implementation_docs/matches-criteria.md, "Why it is exact", "The test"): with the
worker running, several writers create, update, delete and undelete offices held and activities with descriptions,
change people's fields, merge people and undo merges, and publish and unpublish, all at once. When the queue is empty,
every description has what a full evaluation gives (`out_of_date() == []`)."""

import asyncio
import collections
import importlib
import logging
import random
import time
from typing import no_type_check

import pangloss_criteria.models
import pytest
from criteria_court_support import ref, secretary_of
from pangloss_core import storage_of
from pangloss_criteria.worker import Settings, Worker, out_of_date, pending_status
from pangloss_models import (
    Document,
    Entity,
    PanglossEntityInUseError,
    PanglossMergedError,
    PanglossMergeError,
    PanglossNotDeletedError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
    hooks,
    initialise,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

logger = logging.getLogger("pangloss.criteria.churn")

WRITERS = 4
ROUNDS = 30
SEED = 20261119

# What concurrent writers legitimately meet: a document another writer updated since it was read, or deleted; a
# person another merged away, or that something refers to; a merge or an undo that another write made impossible
TOLERATED = (
    PanglossVersionConflictError,
    PanglossNotFoundError,
    PanglossNotDeletedError,
    PanglossMergedError,
    PanglossMergeError,
    PanglossEntityInUseError,
)


def models():
    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    class Factoid(Document):
        """Offices held, as its statements: an update may take them out"""

        statements: list[HoldsOffice]

    initialise()
    return Person, Office, HoldsOffice, Activity, Factoid


class World:
    """What the writers know of: ids only, read again before each change"""

    def __init__(self, Person, Office, HoldsOffice, Activity, Factoid):
        self.Person, self.Office, self.HoldsOffice, self.Activity = (
            Person,
            Office,
            HoldsOffice,
            Activity,
        )
        self.Factoid = Factoid
        self.factoids: list = []
        self.employers: list = []
        self.offices: list = []
        self.people: list = []
        self.holds: list = []
        self.activities: list = []
        self.merges: list = []
        self.deleted: list = []
        """(class, id) of what was deleted, and may have been brought back since"""
        self.criteria: list[dict] = []
        self.tolerated: collections.Counter = collections.Counter()
        self.done: collections.Counter = collections.Counter()

    async def set_up(self):
        for name in ("Maximilian", "Sigismund"):
            self.employers.append(await self.Person.Create(label=name).save())
        for name in ("Secretary", "Courier"):
            self.offices.append(await self.Office.Create(label=name).save())
        for n in range(12):
            self.people.append(
                await self.Person.Create(
                    label=f"P{n:02}", title="Dr" if n % 3 == 0 else None
                ).save()
            )
        (maximilian, sigismund), (secretary, courier) = self.employers, self.offices
        self.criteria = [
            secretary_of(secretary, maximilian),
            secretary_of(secretary, sigismund),
            secretary_of(courier, maximilian),
            # (no anchor: everyone who carried out an activity)
            {
                "type": "Person",
                "where": {
                    "$incoming": [{"type": "Activity", "field": "carried_out_by"}]
                },
            },
            # (on a field of the person)
            {"type": "Person", "where": {"title": {"eq": "Dr"}}},
        ]

    # -- the writes --

    def someone(self, rng):
        return rng.choice(self.people + self.employers)

    async def create_holds(self, rng):
        holder = rng.choice(self.people)
        self.holds.append(
            await self.HoldsOffice.Create(
                label=f"{holder.label} holds an office",
                holder=[ref(holder)],
                office=ref(rng.choice(self.offices)),
                employer=ref(rng.choice(self.employers + self.people[:2])),
            ).save()
        )

    def statements(self, rng) -> list[dict]:
        return [
            {
                "type": "HoldsOffice",
                "label": "A statement",
                "holder": [ref(rng.choice(self.people))],
                "office": ref(rng.choice(self.offices)),
                "employer": ref(rng.choice(self.employers)),
            }
            for _ in range(rng.randint(0, 2))
        ]

    async def create_factoid(self, rng):
        self.factoids.append(
            await self.Factoid.Create(
                label="A factoid", statements=self.statements(rng)
            ).save()
        )

    async def update_factoid(self, rng):
        """Its statements replaced by others, or none"""
        factoid = rng.choice(self.factoids)
        read = await self.Factoid.get(factoid.id)
        if read is None:
            raise PanglossNotFoundError("deleted meanwhile")
        await self.Factoid.Update(
            id=read.id, label=read.label, statements=self.statements(rng)
        ).save(expected_version=read.meta.version)

    async def update_holds(self, rng):
        held = rng.choice(self.holds)
        read = await self.HoldsOffice.get(held.id)
        if read is None:
            raise PanglossNotFoundError("deleted meanwhile")
        change = rng.choice(["holder", "employer", "office", "label"])
        await self.HoldsOffice.Update(
            id=read.id,
            label=f"{read.label}." if change == "label" else read.label,
            holder=[ref(rng.choice(self.people))]
            if change == "holder"
            else [ref(p) for p in read.holder],
            office=ref(rng.choice(self.offices))
            if change == "office"
            else ref(read.office),
            employer=ref(rng.choice(self.employers))
            if change == "employer"
            else ref(read.employer),
        ).save(expected_version=read.meta.version)

    async def create_activity(self, rng):
        named = rng.sample(self.people, rng.randint(0, 2))
        self.activities.append(
            await self.Activity.Create(
                label="An activity",
                carried_out_by=[
                    *[ref(p) for p in named],
                    {"type": "MatchesCriteria", "criteria": rng.choice(self.criteria)},
                ],
                witnessed_by=[ref(rng.choice(self.people))]
                if rng.random() < 0.3
                else [],
            ).save()
        )

    async def update_activity(self, rng):
        activity = rng.choice(self.activities)
        read = await self.Activity.get(activity.id)
        if read is None:
            raise PanglossNotFoundError("deleted meanwhile")
        kept = [
            {"type": "MatchesCriteria", "id": item.id, "criteria": item.criteria}
            if item.type == "MatchesCriteria"
            else ref(item)
            for item in read.carried_out_by
        ]
        change = rng.choice(["named", "criteria", "label"])
        if change == "named":
            kept = [item for item in kept if item["type"] == "MatchesCriteria"] + [
                ref(p) for p in rng.sample(self.people, rng.randint(0, 2))
            ]
        elif change == "criteria":
            kept = [
                {**item, "criteria": rng.choice(self.criteria)}
                if item["type"] == "MatchesCriteria"
                else item
                for item in kept
            ]
        await self.Activity.Update(
            id=read.id,
            label=f"{read.label}." if change == "label" else read.label,
            carried_out_by=kept,
            witnessed_by=[ref(p) for p in read.witnessed_by],
        ).save(expected_version=read.meta.version)

    async def delete(self, rng):
        cls, items = rng.choice(
            [(self.HoldsOffice, self.holds), (self.Activity, self.activities)]
        )
        item = rng.choice(items)
        await cls.delete(item.id)
        self.deleted.append((cls, item.id))

    async def undelete(self, rng):
        cls, id = self.deleted.pop(rng.randrange(len(self.deleted)))
        await cls.undelete(id)

    async def publish(self, rng):
        await storage_of().operations.set_published_in_db(
            self.HoldsOffice, rng.choice(self.holds).id, rng.random() < 0.5
        )

    async def title(self, rng):
        person = rng.choice(self.people)
        await self.Person.Update(
            id=person.id, label=person.label, title=rng.choice(["Dr", None])
        ).save()

    async def merge(self, rng):
        absorbed, survivor = rng.sample(self.people, 2)
        result = await self.Person.merge(absorb=absorbed.id, into=survivor.id)
        self.merges.append(result.merge.id)

    async def unmerge(self, rng):
        await self.Person.unmerge(self.merges.pop(rng.randrange(len(self.merges))))

    async def write(self, rng):
        """One write, chosen at random among those that can be made"""
        choices = [(self.create_holds, 4), (self.create_activity, 3), (self.title, 2)]
        if self.holds:
            choices += [(self.update_holds, 5), (self.publish, 2)]
        if self.activities:
            choices += [(self.update_activity, 3)]
        choices += [(self.create_factoid, 1)]
        if self.factoids:
            choices += [(self.update_factoid, 2)]
        if self.holds and self.activities:
            choices += [(self.delete, 2)]
        if self.deleted:
            choices += [(self.undelete, 2)]
        choices += [(self.merge, 1)]
        if self.merges:
            choices += [(self.unmerge, 1)]
        functions, weights = zip(*choices, strict=True)
        (function,) = rng.choices(functions, weights)
        try:
            await function(rng)
            self.done[function.__name__] += 1
        except TOLERATED as error:
            self.tolerated[f"{function.__name__}: {type(error).__name__}"] += 1

    async def writer(self, seed):
        rng = random.Random(seed)
        for _ in range(ROUNDS):
            await self.write(rng)
            await asyncio.sleep(rng.random() * 0.01)


@no_type_check
async def test_with_the_worker_running_through_concurrent_writes_every_description_is_exact_in_the_end(
    clear_database,
):
    world = World(*models())
    await world.set_up()
    running = Worker(Settings(batch=20, idle=0.5))
    task = asyncio.create_task(running.run())
    hooks.after_write.append(running.listen)
    hooks.work_marked.append(running.marked)
    began = time.monotonic()
    try:
        await asyncio.gather(*(world.writer(SEED + n) for n in range(WRITERS)))
        written = time.monotonic()
        deadline = written + 30
        while (await pending_status())["pending"] > 0:
            assert time.monotonic() < deadline, "the worker did not empty the queue"
            assert not task.done(), task
            await asyncio.sleep(0.05)
        caught_up = time.monotonic()
    finally:
        hooks.after_write.remove(running.listen)
        hooks.work_marked.remove(running.marked)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    stale = await out_of_date()
    logger.warning(
        "Churn: %.1f s writing, %.1f s to catch up; done %s; tolerated %s; worker %s",
        written - began,
        caught_up - written,
        dict(world.done),
        dict(world.tolerated),
        running.stats,
    )
    assert stale == []
    assert running.stats.failures == 0
    assert running.stats.batches > 0 and running.stats.chosen > 0
    # (the churn did what it is for)
    assert sum(world.done.values()) > WRITERS * ROUNDS // 2
    assert world.done["merge"] > 0 and world.done["update_holds"] > 0
    assert world.done["undelete"] > 0 and world.done["update_factoid"] > 0


# --- with `pangloss-derived` (step 6): both workers running ------------------------------------------------------------


def models_with_derived():
    """The same models, and what `pangloss-derived` reads and writes: an edge between each two who carried out an
    activity (through its descriptions), a derived document for each who carried one out (through them as well:
    `allow=`), and a description whose criteria read those documents"""
    from pangloss_derived import (
        DerivedDocument,
        DerivedFrom,
        DerivesEdge,
        Var,
        rule,
    )

    importlib.reload(pangloss_criteria.models)
    MatchesCriteria = pangloss_criteria.models.MatchesCriteria

    class Person(Entity):
        title: str | None = None

    class Office(Entity):
        pass

    class HoldsOffice(Document):
        holder: list[Person | MatchesCriteria[Person]]
        office: Office
        employer: Person

    class Activity(Document):
        _derives = [
            DerivesEdge(
                "CoParticipants",
                subject="carried_out_by",
                object="carried_out_by",
                symmetric=True,
                label="participant",
            )
        ]
        carried_out_by: list[Person | MatchesCriteria[Person]]
        witnessed_by: list[Person]

    class Factoid(Document):
        statements: list[HoldsOffice]

    class Acted(Document):
        """Someone carried out an activity (only ever in a derived document)"""

        _meta = Document.Meta(create_directly=False)
        person: Person

    class DerivedFactoid(Document, DerivedDocument):
        sources: list[DerivedFrom[Activity]]
        statements: list[Acted]

    @rule
    def acted(a: Var[Person]):
        return DerivedFactoid.Derive(
            label="Acted", statements=[Acted.Template(label="Acted", person=a)]
        ).when(Activity.Where(carried_out_by=a), allow=[MatchesCriteria])

    initialise()
    return Person, Office, HoldsOffice, Activity, Factoid


# Whoever is said, by a derived document, to have carried out an activity
ACTED = {
    "type": "Person",
    "where": {"$incoming": [{"type": "Acted", "field": "person"}]},
}


async def marks_left() -> list[dict]:
    from pangloss_cypher import pending
    from pangloss_derived.worker import database

    @database().read_transaction
    async def read(tx):
        result = await tx.run(
            f"MATCH (p:{pending.LABEL}) OPTIONAL MATCH (h:HeadNode {{id: p.head_id}}) "
            "RETURN p.kind AS kind, h.type AS type, count(*) AS marks ORDER BY kind, type"
        )
        return [dict(r) async for r in result]

    return await read()


async def derived_state() -> tuple[list[dict], dict[str, int]]:
    """Every justification, and how many updates each head document has had"""
    from pangloss_derived.worker import database

    @database().read_transaction
    async def read(tx):
        justifications = [
            dict(r)
            async for r in await tx.run(
                "MATCH (j:PGJustification) RETURN j.key AS key, j.values AS values, "
                "j.context_labels AS labels, j.document_id AS document ORDER BY key"
            )
        ]
        updates = {
            r["id"]: r["updates"]
            async for r in await tx.run(
                "MATCH (h:HeadNode) WHERE NOT h:Entity OPTIONAL MATCH (h)<-[:is_update_of]-(u) "
                "RETURN h.id AS id, count(u) AS updates"
            )
        }
        return justifications, updates

    return await read()


@no_type_check
async def test_with_both_workers_running_through_concurrent_writes_both_come_to_rest(
    clear_database,
):
    import dataclasses

    from pangloss_criteria import idle
    from pangloss_derived.registry import DerivedRegistry
    from pangloss_derived.worker import Settings as DerivedSettings
    from pangloss_derived.worker import Worker as DerivedWorker
    from pangloss_derived.worker import worker as derived_worker

    world = World(*models_with_derived())
    await world.set_up()
    world.criteria.append(ACTED)
    criteria = Worker(Settings(batch=20, idle=0.5))
    derived = DerivedWorker(DerivedSettings(batch=20, idle=0.5))
    workers = [criteria, derived]
    tasks = [asyncio.create_task(w.run()) for w in workers]
    for w in workers:
        hooks.after_write.append(w.listen)
        hooks.work_marked.append(w.marked)
    began = time.monotonic()
    try:
        # (one description reads the derived documents from the start)
        world.activities.append(
            await world.Activity.Create(
                label="Whoever acted",
                carried_out_by=[{"type": "MatchesCriteria", "criteria": ACTED}],
                witnessed_by=[],
            ).save()
        )
        await asyncio.gather(*(world.writer(SEED + n) for n in range(WRITERS)))
        written = time.monotonic()
        try:
            await idle(timeout=30)
        except TimeoutError:
            raise AssertionError(
                f"the workers did not come to rest: {await marks_left()}"
            ) from None
        caught_up = time.monotonic()
        for task in tasks:
            assert not task.done(), task
    finally:
        for w in workers:
            hooks.after_write.remove(w.listen)
            hooks.work_marked.remove(w.marked)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    logger.warning(
        "Churn with derived: %.1f s writing, %.1f s to catch up; done %s; tolerated %s; criteria %s; derived %s",
        written - began,
        caught_up - written,
        dict(world.done),
        dict(world.tolerated),
        criteria.stats,
        derived.stats,
    )
    assert await out_of_date() == []
    assert criteria.stats.failures == 0 and derived.stats.failures == 0
    assert criteria.stats.batches > 0 and derived.stats.batches > 0
    assert derived.stats.documents.made > 0

    # every rule built again, in order: nothing changes, nothing is written
    justifications, updates = await derived_state()
    before = dataclasses.replace(derived_worker.stats.documents)
    for name in DerivedRegistry.order:
        await derived_worker.rebuild(DerivedRegistry.all_checked()[name])
        await derived_worker.drain()
    now = derived_worker.stats.documents
    changed = {
        f.name: getattr(now, f.name) - getattr(before, f.name)
        for f in dataclasses.fields(now)
        if getattr(now, f.name) != getattr(before, f.name)
    }
    assert set(changed) <= {"same"}, changed
    assert await derived_state() == (justifications, updates)
    assert await out_of_date() == []
    assert sum(world.done.values()) > WRITERS * ROUNDS // 2
