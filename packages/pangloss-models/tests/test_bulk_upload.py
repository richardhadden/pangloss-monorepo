"""Reading, checking and writing the records of a bulk upload (`pangloss_models.bulk_upload`).

What is written is `Model.Create(...).save()`, which these tests replace by one that notes what it
was called with, so that no database is needed (`pangloss-memgraph` has the tests of a real load)."""

import asyncio
import json
from pathlib import Path

import pytest
from pangloss_models import initialise
from pangloss_models.bulk_upload import creator, read_records, upload, validate
from pangloss_models.exceptions import PanglossBulkRecordError
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


def models():
    class Person(Entity):
        pass

    class Note(Document):
        text: str

    initialise()
    return Person, Note


def write_lines(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n")
    return path


def test_the_records_of_a_file_are_read_with_their_line_numbers(tmp_path: Path):
    path = write_lines(
        tmp_path / "in.jsonl", '{"type": "A"}', "", "   ", '{"type": "B", "x": 1}'
    )

    assert list(read_records(path)) == [(1, {"type": "A"}), (4, {"type": "B", "x": 1})]


def test_a_line_that_is_not_a_record_is_reported_by_its_number(tmp_path: Path):
    path = write_lines(tmp_path / "in.jsonl", '{"type": "A"}', "{nope")
    with pytest.raises(PanglossBulkRecordError, match="line 2: not JSON") as caught:
        list(read_records(path))
    assert caught.value.line == 2

    path = write_lines(tmp_path / "list.jsonl", "[1, 2]")
    with pytest.raises(PanglossBulkRecordError, match="line 1: a record must be"):
        list(read_records(path))


def test_a_record_must_name_a_model_that_can_be_written():
    models()

    with pytest.raises(
        PanglossBulkRecordError, match='line 3: a record needs a "type"'
    ):
        creator(3, {"label": "x"})
    with pytest.raises(PanglossBulkRecordError, match="'Nothing' is not a model"):
        creator(4, {"type": "Nothing"})

    type_name, create = creator(5, {"type": "Note", "label": "n", "text": "t"})
    assert type_name == "Note" and create.text == "t"


def test_an_invalid_record_says_which_field(tmp_path: Path):
    models()

    with pytest.raises(PanglossBulkRecordError, match="line 7: Note: text: ") as caught:
        creator(7, {"type": "Note", "label": "n"})  # (no text)
    assert caught.value.line == 7


def test_validate_checks_everything_and_counts_the_types():
    models()
    records = [
        (1, {"type": "Person", "label": "a"}),
        (2, {"type": "Note", "label": "n", "text": "t"}),
        (3, {"type": "Person", "label": "b"}),
    ]

    assert validate(records) == {"Person": 2, "Note": 1}

    with pytest.raises(PanglossBulkRecordError, match="line 4"):
        validate([*records, (4, {"type": "Note", "label": "n"})])


class Writes:
    """A `save` that notes when each record began and ended, and how many were going at once"""

    def __init__(self, monkeypatch, *classes, fail_on: str | None = None):
        self.log: list[tuple[str, str]] = []
        self.running = 0
        self.most = 0
        self.fail_on = fail_on

        async def save(this):
            label = this.label
            self.log.append(("start", label))
            self.running += 1
            self.most = max(self.most, self.running)
            await asyncio.sleep(0.01)
            self.running -= 1
            if label == self.fail_on:
                raise RuntimeError("the database said no")
            self.log.append(("end", label))

        for cls in classes:
            monkeypatch.setattr(cls.Create, "save", save)


def people_then_notes(people: int, notes: int):
    return [
        *[(i + 1, {"type": "Person", "label": f"p{i}"}) for i in range(people)],
        *[
            (people + i + 1, {"type": "Note", "label": f"n{i}", "text": "t"})
            for i in range(notes)
        ],
    ]


@pytest.mark.asyncio
async def test_records_of_one_type_are_written_together_and_the_next_type_waits(
    monkeypatch,
):
    Person, Note = models()
    writes = Writes(monkeypatch, Person, Note)
    seen: list[int] = []

    written = await upload(people_then_notes(6, 4), concurrency=3, progress=seen.append)

    assert written == {"Person": 6, "Note": 4}
    assert seen == list(range(1, 11))
    assert writes.most == 3
    # (no note begins until every person has ended)
    first_note = next(i for i, (_, label) in enumerate(writes.log) if label[0] == "n")
    assert all(("end", f"p{i}") in writes.log[:first_note] for i in range(6)), (
        writes.log
    )


@pytest.mark.asyncio
async def test_one_writer_writes_in_the_order_of_the_file(monkeypatch):
    Person, Note = models()
    writes = Writes(monkeypatch, Person, Note)

    await upload(people_then_notes(3, 2), concurrency=1)

    assert writes.most == 1
    assert [label for kind, label in writes.log if kind == "start"] == [
        "p0",
        "p1",
        "p2",
        "n0",
        "n1",
    ]


@pytest.mark.asyncio
async def test_the_first_failure_stops_the_rest_and_says_which_line(monkeypatch):
    Person, Note = models()
    writes = Writes(monkeypatch, Person, Note, fail_on="p2")

    with pytest.raises(
        PanglossBulkRecordError, match="line 3: RuntimeError: the database said no"
    ) as caught:
        await upload(people_then_notes(4, 3), concurrency=1)

    assert caught.value.line == 3
    # (p3 and the notes were never begun)
    assert [label for kind, label in writes.log if kind == "start"] == [
        "p0",
        "p1",
        "p2",
    ]


@pytest.mark.asyncio
async def test_a_file_of_a_thousand_records_is_written(monkeypatch, tmp_path: Path):
    Person, Note = models()
    writes = Writes(monkeypatch, Person, Note)
    path = tmp_path / "big.jsonl"
    path.write_text(
        "\n".join(json.dumps(record) for _, record in people_then_notes(600, 400))
    )

    written = await upload(read_records(path), concurrency=8)

    assert written == {"Person": 600, "Note": 400}
    assert writes.most == 8
