"""A field removed from a base class, that a subclass declares itself: the subclass's nodes keep their data.

`RemoveField` on the base acts on every node with the base's label, which includes the nodes of its subclasses. A
subclass that does not declare the field again has a `RemoveField` of its own (its fields change); one that does has
none, and its data must be left as it is. (Found when `pangloss_calendar` took `use` and `rank` off the abstract
`DateCharacterisation`, and a project's `Feast` declares them.)"""

from types import SimpleNamespace as ns
from typing import no_type_check

import pytest
from pangloss_history.upgrade import apply_migrations
from pangloss_models.migrations.files import Migration
from pangloss_models.migrations.snapshot import data_view
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity

from .helpers import run
from .migration_support import declare, migrate

pytestmark = pytest.mark.asyncio(loop_scope="session")


def v1():
    class Note(Document):
        text: str

    class Saint(Entity):
        pass

    class Characterisation(Entity):
        _meta = Entity.Meta(abstract=True)

        use: str | None = None
        notes: list[Note]
        saints: list[Saint]

    class Feast(Characterisation):
        pass

    class Fair(Characterisation):
        pass

    return ns(Note=Note, Saint=Saint, Feast=Feast, Fair=Fair)


def v2():
    class Note(Document):
        text: str

    class Saint(Entity):
        pass

    class Characterisation(Entity):
        _meta = Entity.Meta(abstract=True)

    # (declares them itself: they are no longer the base's, and its data stays)
    class Feast(Characterisation):
        use: str | None = None
        notes: list[Note]
        saints: list[Saint]

    # (does not: it loses them)
    class Fair(Characterisation):
        pass

    return ns(Note=Note, Saint=Saint, Feast=Feast, Fair=Fair)


async def write(models):
    saint = await models.Saint.Create(label="Benedict").save()
    feast = await models.Feast.Create(
        label="Benedict's day",
        use="sarum",
        notes=[{"type": "Note", "label": "Feast note", "text": "kept"}],
        saints=[{"type": "Saint", "id": saint.id}],
    ).save()
    fair = await models.Fair.Create(
        label="Market",
        use="town",
        notes=[{"type": "Note", "label": "Fair note", "text": "gone"}],
        saints=[{"type": "Saint", "id": saint.id}],
    ).save()
    return feast, fair


@no_type_check
@pytest.mark.parametrize("batch_size", [None, 1])
async def test_a_subclass_that_declares_a_removed_field_itself_keeps_its_data(
    db_driver, clear_database, batch_size
):
    old_models, old = declare(v1)
    feast, fair = await write(old_models)
    new_models, new = declare(v2)
    changes = await migrate(old, new, batch_size=batch_size)
    removed = sorted(
        (ch.model, ch.name) for ch in changes if type(ch).__name__ == "RemoveField"
    )
    # (the base loses the three fields, and so does the subclass that does not declare them; the other has no change)
    assert removed == [
        ("Characterisation", "notes"),
        ("Characterisation", "saints"),
        ("Characterisation", "use"),
        ("Fair", "notes"),
        ("Fair", "saints"),
        ("Fair", "use"),
    ]

    kept = await new_models.Feast.get(id=feast.id)
    assert kept.use == "sarum"
    assert [n.label for n in kept.notes] == ["Feast note"]
    assert [s.label for s in kept.saints] == ["Benedict"]

    props = run(db_driver, "MATCH (n:Fair) RETURN properties(n) AS p")[0]["p"]
    assert props.get("use") is None
    assert (
        run(db_driver, "MATCH (:Fair)-[e]->(:Saint) RETURN count(e) AS n")[0]["n"] == 0
    )
    # (the fair's note went with its field; the feast's is still there, and so is the saint, an entity)
    notes = run(db_driver, "MATCH (n:Note) RETURN n.label AS label")
    assert [row["label"] for row in notes] == ["Feast note"]
    assert run(db_driver, "MATCH (n:Saint) RETURN count(n) AS n")[0]["n"] == 1
    read = await new_models.Fair.get(id=fair.id)
    assert read.label == "Market"


@no_type_check
async def test_the_base_alone_losing_a_field_leaves_every_subclass_that_keeps_it(
    db_driver, clear_database
):
    """The base's own migration may run before the project's, which removes the field from a subclass that does not
    declare it: until then, that subclass still has the field, and its nodes are left to its own removal"""
    from pangloss_models.migrations import changes as c

    old_models, old = declare(v1)
    feast, fair = await write(old_models)
    # (only the change to the base, as a package's migration would have it; the subclasses still have the field)
    base_only = [
        c.RemoveField(model="Characterisation", name="use", field_kind="literal")
    ]
    await migrate(old, old, answer=lambda _: base_only)
    uses = run(
        db_driver,
        "MATCH (n) WHERE n:Feast OR n:Fair RETURN n.label AS label, n.use AS use ORDER BY label",
    )
    assert [(row["label"], row["use"]) for row in uses] == [
        ("Benedict's day", "sarum"),
        ("Market", "town"),
    ]


@no_type_check
async def test_a_stored_version_of_a_subclass_that_keeps_the_field_keeps_it(
    clear_database,
):
    """`pangloss-history` upgrades a stored version as the database is migrated: the same rule"""
    from pangloss_models.migrations import changes as c

    old_models, old = declare(v1)
    state = data_view(old)
    version = {
        "type": "Feast",
        "label": "Benedict's day",
        "use": "sarum",
        "notes": [],
        "saints": [],
    }
    other = {
        "type": "Fair",
        "label": "Market",
        "use": "town",
        "notes": [],
        "saints": [],
    }
    base_only = [
        c.RemoveField(model="Characterisation", name="use", field_kind="literal")
    ]
    migration = [Migration(app="t", name="0002_change", changes=tuple(base_only))]
    assert apply_migrations(version, state, migration).data["use"] == "sarum"
    assert apply_migrations(other, state, migration).data["use"] == "town"
    with_fair = [
        *base_only,
        c.RemoveField(model="Fair", name="use", field_kind="literal"),
    ]
    upgraded = apply_migrations(
        other, state, [Migration(app="t", name="0002_change", changes=tuple(with_fair))]
    )
    assert "use" not in upgraded.data
