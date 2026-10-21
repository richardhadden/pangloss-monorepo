"""Going backwards against a database: migrate forwards, undo, and read with the old models"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.migrations import apply_changes
from pangloss_models.migrations import PossibleRename, data_view
from pangloss_models.migrations.reverse import reverse_changes
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from .helpers import run
from .migration_support import declare, migrate, with_answers
from .test_migrations_relations import person_models, person_payload, signature

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def go_back(old: dict, new: dict, forward: list):
    """Undo the changes that took the models from `old` to `new`, on the database"""
    reversal = reverse_changes(forward, data_view(old))
    await apply_changes(Database.default, new, reversal.changes)
    return reversal


@no_type_check
async def test_a_renamed_relation_is_renamed_back_with_its_reverse(db_driver, clear_database):
    def v1():
        class Place(Entity):
            pass

        class Statement(Document):
            home: Place

        return ns(Place=Place, Statement=Statement)

    def v2():
        class Place(Entity):
            pass

        class Statement(Document):
            residence: Place

        return ns(Place=Place, Statement=Statement)

    old_models, old = declare(v1)
    place = await old_models.Place.Create(label="Paris").save()
    statement = await old_models.Statement.Create(
        label="S", home={"type": "Place", "id": place.id}
    ).save()
    before = signature(db_driver, statement.id)

    _, new = declare(v2)
    rename = PossibleRename(what="field", scope="Statement", old="home", new="residence")
    forward = await migrate(old, new, confirmed=[rename])
    reversal = await go_back(old, new, forward)
    assert not reversal.lossy

    old_models, _ = declare(v1)
    assert (await old_models.Statement.get(id=statement.id)).home.id == place.id
    assert [s.id for s in (await old_models.Place.get(id=place.id)).home_reverse] == [statement.id]
    assert signature(db_driver, statement.id) == before


@no_type_check
async def test_a_wrapped_relation_is_unwrapped_to_what_it_was(db_driver, clear_database):
    old_models, old = declare(person_models(wrapped=False))
    person = await old_models.Person.Create(label="Ann").save()
    plain = await old_models.Statement.Create(label="Plain", person=person_payload(person, False)).save()
    factoid = await old_models.Factoid.Create(
        label="F",
        statements=[
            {"type": "Statement", "label": "Nested", "person": person_payload(person, False)},
            {
                "type": "Action",
                "label": "Narrowed",
                "person": person_payload(person, False),
                "carried_out_by": person_payload(person, False),
            },
        ],
    ).save()
    before = (signature(db_driver, plain.id), signature(db_driver, factoid.id))

    _, new = declare(person_models(wrapped=True))
    forward = await migrate(old, new, answer=with_answers(WrapRelation={"defaults": {"certainty": 5}}))
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS c") == [{"c": 3}]

    reversal = await go_back(old, new, forward)
    assert reversal.lossy  # (the certainties are gone)
    assert run(db_driver, "MATCH (r:IdentifiedAs) RETURN count(r) AS c") == [{"c": 0}]
    assert (signature(db_driver, plain.id), signature(db_driver, factoid.id)) == before

    old_models, _ = declare(person_models(wrapped=False))
    assert (await old_models.Statement.get(id=plain.id)).person.id == person.id
    read = await old_models.Factoid.get(id=factoid.id)
    by_label = {s.label: s for s in read.statements}
    assert by_label["Nested"].person.id == person.id
    assert by_label["Narrowed"].carried_out_by.id == person.id


@no_type_check
async def test_a_converted_type_is_converted_back_and_an_added_field_removed(db_driver, clear_database):
    def v1():
        class Item(Entity):
            count: int

        return ns(Item=Item)

    def v2():
        class Item(Entity):
            count: str
            note: str | None

        return ns(Item=Item)

    old_models, old = declare(v1)
    saved = await old_models.Item.Create(label="I", count=7).save()

    new_models, new = declare(v2)
    forward = await migrate(old, new)
    assert (await new_models.Item.get(id=saved.id)).count == "7"
    await new_models.Item.Update(id=saved.id, label="I", count="12", note="x").save()

    reversal = await go_back(old, new, forward)
    assert reversal.lossy

    old_models, _ = declare(v1)
    read = await old_models.Item.get(id=saved.id)
    assert read.count == 12  # (what was written since is converted too)
    assert run(db_driver, "MATCH (n:Item) RETURN n.note AS note") == [{"note": None}]


@no_type_check
async def test_a_value_that_cannot_go_back_fails_and_changes_nothing(db_driver, clear_database):
    def v1():
        class Item(Entity):
            count: int

        return ns(Item=Item)

    def v2():
        class Item(Entity):
            count: str

        return ns(Item=Item)

    old_models, old = declare(v1)
    saved = await old_models.Item.Create(label="I", count=7).save()
    new_models, new = declare(v2)
    forward = await migrate(old, new)
    await new_models.Item.Update(id=saved.id, label="I", count="seven").save()

    with pytest.raises(Exception, match="seven|convert"):
        await go_back(old, new, forward)
    assert run(db_driver, "MATCH (n:Item) RETURN n.count AS c") == [{"c": "seven"}]


@no_type_check
async def test_undoing_in_batches_and_again_after_a_stop(db_driver, clear_database, monkeypatch):
    from dataclasses import replace

    from pangloss_memgraph.databases.memgraph import migration_backend as backend
    from pangloss_memgraph.databases.memgraph.migrations import runner
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT, Migration

    def v1():
        class Item(Entity):
            name: str

        return ns(Item=Item)

    def v2():
        class Item(Entity):
            name: str
            count: int

        return ns(Item=Item)

    old_models, old = declare(v1)
    for n in range(5):
        await old_models.Item.Create(label=f"I{n}", name=f"n{n}").save()
    new_models, new = declare(v2)
    forward = await migrate(old, new, answer=with_answers(AddField={"default": 3}))
    assert run(db_driver, "MATCH (i:Item) WHERE i.count = 3 RETURN count(i) AS n") == [{"n": 5}]

    await backend.ensure_ready()
    reversal = reverse_changes(forward, data_view(old))
    migration = Migration(app="back", name="0001_x", changes=tuple(reversal.changes))
    run(db_driver, "CREATE (:PGMigration {app: 'back', name: '0001_x', status: 'applied'})")

    # the second batch fails
    calls = []
    original = runner.apply_window

    async def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("stopped part way")
        return await original(*args, **kwargs)

    monkeypatch.setattr(runner, "apply_window", failing)
    with pytest.raises(RuntimeError, match="stopped part way"):
        await backend.unapply([migration], data_view(new), batch_size=2)
    assert [r["key"] for r in run(db_driver, "MATCH (m:PGMigration) RETURN m.name AS key")] == ["0001_x"]  # (still recorded)
    assert run(db_driver, "MATCH (i:Item) WHERE i.count IS NOT NULL RETURN count(i) AS n") == [{"n": 3}]  # (2 done)

    # ... and run again from the start: the rest is done, and what was done is not found again
    monkeypatch.setattr(runner, "apply_window", original)
    state = await backend.unapply([migration], data_view(new), batch_size=2)
    assert run(db_driver, "MATCH (i:Item) WHERE i.count IS NOT NULL RETURN count(i) AS n") == [{"n": 0}]
    assert run(db_driver, "MATCH (m:PGMigration {app: 'back'}) RETURN count(m) AS n") == [{"n": 0}]
    assert state == data_view(old)
