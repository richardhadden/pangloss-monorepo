from uuid import uuid7

import pytest
from history_support import record
from pangloss_history.store import SqliteStore


@pytest.fixture
def store(tmp_path):
    return SqliteStore(tmp_path / "sub" / "history.sqlite3")


def test_records_come_back_in_order_with_a_sequence_and_without_content(store):
    id = uuid7()
    store.append([record(id), record(id, 2, "update"), record(id, 2, "delete")])
    store.append([record(id, 2, "undelete")])

    found = store.versions(id)
    assert [(r.seq, r.version, r.op) for r in found] == [
        (1, 1, "create"),
        (2, 2, "update"),
        (3, 2, "delete"),
        (4, 2, "undelete"),
    ]
    assert all(r.content is None for r in found)
    assert found[0].schema_position == {"letters": "0001_initial"}
    assert found[0].who == "john" and found[0].at.year == 2026


def test_get_gives_the_content_of_the_latest_record_of_that_version(store):
    id = uuid7()
    store.append(
        [
            record(id, 1, content={"text": "one"}),
            record(id, 2, "update", content={"text": "two"}),
            record(id, 2, "delete"),
            record(id, 3, "restore", content={"text": "one"}, restored_from=1),
        ]
    )
    assert store.get(id, 2).data() == {"text": "two"}  # (not the delete of version 2)
    restored = store.get(id, 3)
    assert restored.data() == {"text": "one"} and restored.restored_from == 1
    assert store.get(id, 9) is None
    assert store.get(uuid7(), 1) is None


def test_the_same_content_is_kept_once(store):
    a, b = uuid7(), uuid7()
    store.append([record(a, content={"x": 1}), record(b, content={"x": 1})])
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM blobs").fetchone() == (1,)
    assert store.get(a, 1).data() == store.get(b, 1).data() == {"x": 1}


def test_a_failed_append_adds_nothing(store):
    id = uuid7()
    bad = record(id, 2, "update")
    object.__setattr__(bad, "schema_position", {"a": object()})  # (cannot be made JSON)
    with pytest.raises(TypeError):
        store.append([record(id), bad])
    assert store.versions(id) == []


def test_latest_version(store):
    id = uuid7()
    assert store.latest_version(id) is None
    store.append([record(id), record(id, 2, "update")])
    assert store.latest_version(id) == 2


def test_it_opens_an_existing_file(tmp_path):
    path = tmp_path / "h.sqlite3"
    id = uuid7()
    SqliteStore(path).append([record(id)])
    assert SqliteStore(path).get(id, 1).data() == {"text": "version 1"}
