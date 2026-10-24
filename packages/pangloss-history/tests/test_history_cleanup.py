from types import SimpleNamespace
from uuid import uuid7

from history_support import record
from pangloss_history.cleanup import versions_inside, warnings_for
from pangloss_history.store import SqliteStore
from pangloss_models.meta_kit.migrations.files import Migration


def squash():
    return Migration(
        app="letters",
        name="0001_squashed_0003",
        changes=(),
        replaces=(
            ("letters", "0001_initial"),
            ("letters", "0002_a"),
            ("letters", "0003_b"),
        ),
    )


def test_versions_part_way_through_a_squashed_range_are_counted_and_the_end_of_it_is_not(
    tmp_path,
):
    store = SqliteStore(tmp_path / "h.sqlite3")
    import dataclasses

    def written_at(position):
        return dataclasses.replace(
            record(uuid7()), schema_position={"letters": position}
        )

    store.append(
        [
            written_at("0001_initial"),
            written_at("0002_a"),
            written_at("0002_a"),
            written_at("0003_b"),  # (the end: the squash stands for it)
            written_at("0004_later"),
        ]
    )
    assert store.position_counts() and sum(n for _, n in store.position_counts()) == 5
    assert [(m.name, n) for m, n in versions_inside(store, [squash()])] == [
        ("0001_squashed_0003", 3)
    ]


def test_the_warning_is_in_words_and_there_is_none_without_a_store_or_versions(
    tmp_path,
):
    settings = SimpleNamespace(HISTORY_DB_PATH=str(tmp_path / "none.sqlite3"))
    assert warnings_for(settings, [squash()]) == []

    store = SqliteStore(tmp_path / "h.sqlite3")
    settings = SimpleNamespace(HISTORY_DB_PATH=str(tmp_path / "h.sqlite3"))
    assert warnings_for(settings, [squash()]) == []  # (empty)

    import dataclasses

    store.append(
        [
            dataclasses.replace(
                record(uuid7()), schema_position={"letters": "0001_initial"}
            )
        ]
    )
    (warning,) = warnings_for(settings, [squash()])
    assert (
        "1 recorded version was written part way through" in warning
        and "0001_squashed_0003" in warning
    )
