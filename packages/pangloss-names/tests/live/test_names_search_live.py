"""A search by a name on the backend under test (implementation_docs/similarity-build-plan.md, step 8.6):
`pangloss_names.vector_of` and `pangloss_names.search`, through `nearest(vector=...)` by the profile `who` of the
conftest (`{"name": 1, "graph": 0.25}`), and `pangloss names search`.

(The people here are named in no document, so none has a graph vector beside its name vector, and a hit's score is the
cosine of the names: `by_name`'s docstring says what it is otherwise)"""

from typing import no_type_check

import pytest
from pangloss_names import NotBuilt, meta, search, vector_of
from pangloss_names.by_name import profile_for
from pangloss_names.cli import cli
from pangloss_testing.live import run_command, run_connected
from pangloss_testing.parts import drop_vector_indexes, one_turn

# (each async test is marked by itself: the command's test is not async)
on_the_loop = pytest.mark.asyncio(loop_scope="session")

PEOPLE = {
    "john": "John Smith",
    "namesake": "John Smith",
    "variant": "John Smyth",
    "other": "Mary Brown",
    "nearly": "Joan Smithers",
}


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


async def make_vector_indexes() -> None:
    """The vector index of each profile of today's settings (as the project's migrations would make them: a search
    that is not narrowed to a class asks it)"""
    from pangloss_cypher.migrations import apply_changes
    from pangloss_models.migrations import changes as c
    from pangloss_models.migrations.files import EMPTY_SNAPSHOT
    from pangloss_testing.under_test.database import current
    from pangloss_vectors import store, structure
    from pangloss_vectors.parts import profiles

    changes = []
    for name, weights in profiles().items():
        if weights:
            lay = store.layout(name, weights)
            entry = structure.vector_entry(
                lay.index_name, lay.label, lay.dimension, "test"
            )
            changes.append(
                c.AddIndex(index={k: v for k, v in entry.items() if k != "app"})
            )
    await apply_changes(current(), EMPTY_SNAPSHOT, changes)


@pytest.fixture
def factoids_with_names(monkeypatch):
    """(no class of documents of `similar_models` has names: here `Factoid` is given its label, as
    `NamesMeta(include=True)` would)"""
    plain = meta.named
    monkeypatch.setattr(meta, "named", lambda: {**plain(), "Factoid": ["label"]})


@no_type_check
async def saved_people(m) -> dict[str, str]:
    return {
        key: str((await m.Person.Create(label=label).save()).id)
        for key, label in PEOPLE.items()
    }


@no_type_check
async def built(database, reviewed: bool = False):
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare(reviewed=reviewed)
    ids = await saved_people(m)
    group = await m.Group.Create(label="The Smith guild").save()
    ids["group"] = str(group.id)
    await make_vector_indexes()
    await rebuild()
    await one_turn(database)
    return m, ids


def ids_of(found) -> list[str]:
    assert found.status == "ok", found
    return [hit.id for hit in found.hits]


@on_the_loop
@no_type_check
async def test_the_same_name_first_then_the_variant_spelling_and_another_name_last(
    database,
):
    _, ids = await built(database)
    found = await search("John Smith", types=["Person"])
    order = ids_of(found)
    assert set(order[:2]) == {ids["john"], ids["namesake"]}
    assert order[2] == ids["variant"]
    # (another name: not among them, or last)
    assert ids["other"] not in order or order[-1] == ids["other"]
    # (the same name: the cosine of the names is 1, and nothing of the graph is there to share the score)
    assert [round(hit.score, 6) for hit in found.hits[:2]] == [1.0, 1.0]
    assert 0 < found.hits[2].score < 1
    assert {hit.type for hit in found.hits} == {"Person"}


@on_the_loop
@no_type_check
async def test_narrowed_by_type(database):
    _, ids = await built(database)
    everything = ids_of(await search("Smith"))
    assert ids["group"] in everything
    people = ids_of(await search("Smith", types=["Person"]))
    assert ids["group"] not in people and ids["john"] in people
    groups = ids_of(await search("Smith", types=["Group"]))
    assert groups == [ids["group"]]
    assert ids_of(await search("Smith", types=["Person"], k=2)) == people[:2]


@on_the_loop
@no_type_check
async def test_several_names_of_one_item_make_one_vector(database):
    await built(database)
    one = await vector_of(["John", "Smith"])
    assert one == await vector_of("John Smith")
    assert await vector_of("--- !") is None


@on_the_loop
@no_type_check
async def test_an_unpublished_item_is_not_shown_to_a_reader_who_is_not_logged_in(
    database, factoids_with_names
):
    m, _ = await built(database, reviewed=True)
    letter = await m.Factoid.Create(label="John Smith's letter", statements=[]).save()
    await one_turn(database)
    assert ids_of(await search("John Smith's letter", types=["Factoid"])) == []
    assert ids_of(
        await search("John Smith's letter", types=["Factoid"], see_unpublished=True)
    ) == [str(letter.id)]


@on_the_loop
@no_type_check
async def test_a_merged_entity_is_not_a_hit_and_its_survivor_is(database):
    m, ids = await built(database)
    absorbed = await m.Person.Create(label="Peter Quill").save()
    kept = await m.Person.Create(label="Peter Quil").save()
    await one_turn(database)
    assert ids_of(await search("Peter Quill", types=["Person"], k=2)) == [
        str(absorbed.id),
        str(kept.id),
    ]
    await m.Person.merge(absorbed.id, into=kept.id)
    await one_turn(database)
    found = ids_of(await search("Peter Quill", types=["Person"]))
    assert str(absorbed.id) not in found
    assert found[0] == str(kept.id)


@on_the_loop
@no_type_check
async def test_before_any_rebuild_a_search_says_to_run_one(database):
    from pangloss_testing.similar_models import declare

    m = declare()
    await m.Person.Create(label="John Smith").save()
    with pytest.raises(NotBuilt, match="pangloss vectors rebuild"):
        await vector_of("John Smith")
    with pytest.raises(NotBuilt, match="pangloss vectors rebuild"):
        await search("John Smith")


@on_the_loop
@no_type_check
async def test_the_profile_is_the_first_that_weighs_the_name_part_or_a_clear_error(
    database, monkeypatch
):
    import pangloss_core.settings as core_settings

    await built(database)
    assert profile_for() == "who"
    with pytest.raises(ValueError, match="does not weigh the name part"):
        await search("John Smith", profile="default")
    with pytest.raises(ValueError, match="no profile named 'nope'"):
        await search("John Smith", profile="nope")
    with pytest.raises(ValueError, match="no letter or digit"):
        await search("--")
    monkeypatch.setattr(
        core_settings.SETTINGS,
        "VECTORS_PROFILES",
        {"b": {"name": 1}, "a": {"class": 1}, "c": {"name": 1}},
    )
    assert profile_for() == "b"
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_PROFILES", {"a": {"class": 1}})
    with pytest.raises(
        ValueError, match=r"a profile must weigh the name part \(VECTORS_PROFILES = "
    ):
        profile_for()


# -- the command -----------------------------------------------------------------------------------------------------


@no_type_check
def test_the_command_prints_the_hits(database, command_backend, factoids_with_names):
    """(a command runs its own event loop: not async. Unpublished documents are shown: the command line is the
    project's owner)"""
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare(reviewed=True)

    async def made():
        ids = await saved_people(m)
        letter = await m.Factoid.Create(label="John Smith", statements=[]).save()
        ids["letter"] = str(letter.id)
        await make_vector_indexes()
        await rebuild()
        return ids

    ids = run_connected(command_backend, made)
    told = run_command(cli, command_backend, "search", "John Smith", "--type", "Person")
    assert told.exit_code == 0, told.output
    lines = told.output.splitlines()
    assert len(lines) == len(PEOPLE)
    first = lines[0].split("  ")
    assert first[0] == "1.0000" and first[1] == "Person" and first[2] == "John Smith"
    assert {line.split("  ")[-1] for line in lines[:2]} == {
        ids["john"],
        ids["namesake"],
    }
    # (the order after them is the first test's: the letter's name changes the table of rarity here)
    assert {tuple(line.split("  ")[1:]) for line in lines} == {
        ("Person", PEOPLE[key], ids[key]) for key in PEOPLE
    }

    two = run_command(cli, command_backend, "search", "John Smith", "-k", "2")
    assert two.exit_code == 0, two.output
    assert len(two.output.splitlines()) == 2

    unpublished = run_command(
        cli, command_backend, "search", "John Smith", "--type", "Factoid"
    )
    assert unpublished.exit_code == 0, unpublished.output
    assert unpublished.output.splitlines() == [
        f"1.0000  Factoid  John Smith  {ids['letter']}"
    ]

    wrong = run_command(
        cli, command_backend, "search", "John Smith", "--profile", "default"
    )
    assert wrong.exit_code == 2
    assert "does not weigh the name part" in wrong.output
    unknown = run_command(cli, command_backend, "search", "John", "--type", "Nope")
    assert unknown.exit_code == 2
    assert "'Nope' is not a class" in unknown.output
