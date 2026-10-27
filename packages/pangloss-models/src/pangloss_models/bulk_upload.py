"""Writing the records of a file with the models: what `pangloss memgraph bulk-load` does.

The file is JSON Lines: a record a line, each a JSON object with the `type` of the model it is a
`Create` of, and the fields of that:

```
{"type": "Person", "id": "https://example.org/person/1", "create_new": true, "label": "Ann", ...}
{"type": "Factoid", "label": "...", "source": {"type": "AtPage", "page": "1", "target": [{"type": "Source", "id": "..."}]}}
```

A record is written as `Model.Create(**fields).save()` is, so what it refers to must be written
**before** it: entities have to be given their ids (`create_with_id`, as a URL or a UUID), so that
the records that refer to them can say which they mean. The records are written in the order of the
file; those that follow each other with the same `type` are written by several writers at once
(`concurrency`), and the next type starts when they have all finished. So a file of entities, then
factoids, can be written four or more at a time; but a type whose records refer to each other
(a `Person` with a `Person` in a relation) has to be written by one writer, in order
(`concurrency=1`).

`validate` reads a whole file first and writes nothing, so a record that is not valid is found
before the database is touched. (It cannot know that something referred to exists.)
"""

import asyncio
import itertools
import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pangloss_models.exceptions import PanglossBulkRecordError
from pangloss_models.model_registry import ModelRegistry

Record = tuple[int, dict[str, Any]]


def read_records(path: Path | str) -> Iterator[Record]:
    """The records of a JSON Lines file, with their line numbers (blank lines are skipped)"""
    with open(path, encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise PanglossBulkRecordError(number, f"not JSON: {error}") from error
            if not isinstance(record, dict):
                raise PanglossBulkRecordError(number, "a record must be a JSON object")
            yield number, record


def creator(number: int, record: dict[str, Any]) -> tuple[str, Any]:
    """The `Create` object of a record, and its type. Raises `PanglossBulkRecordError`"""
    fields = dict(record)
    type_name = fields.pop("type", None)
    if not isinstance(type_name, str):
        raise PanglossBulkRecordError(number, 'a record needs a "type"')
    model = ModelRegistry.all_models().get(type_name)
    create = getattr(model, "Create", None)
    if model is None or create is None:
        raise PanglossBulkRecordError(
            number, f"{type_name!r} is not a model that can be written"
        )
    try:
        return type_name, create(**fields)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}"
            for e in error.errors()
        )
        raise PanglossBulkRecordError(number, f"{type_name}: {problems}") from error


def validate(records: Iterable[Record]) -> dict[str, int]:
    """Check every record as `Create` does, writing nothing; how many there are of each type"""
    counts: dict[str, int] = {}
    for number, record in records:
        type_name, _ = creator(number, record)
        counts[type_name] = counts.get(type_name, 0) + 1
    return counts


async def write_group(
    pending: Iterator[Record], concurrency: int, written: Callable[[], None]
) -> None:
    """Write records with `concurrency` writers that share the one iterator; `written()` is called
    after each. The first failure stops the others"""

    async def writer() -> None:
        for number, record in pending:
            _, create = creator(number, record)
            try:
                await create.save()
            except Exception as error:
                raise PanglossBulkRecordError(
                    number, f"{type(error).__name__}: {error}"
                ) from error
            written()

    try:
        async with asyncio.TaskGroup() as writers:
            for _ in range(max(1, concurrency)):
                writers.create_task(writer())
    except ExceptionGroup as failures:
        # (the first record, by line, of those that failed together; anything else as it is)
        records_failed = [
            e for e in failures.exceptions if isinstance(e, PanglossBulkRecordError)
        ]
        if not records_failed:
            raise
        raise min(records_failed, key=lambda e: e.line) from None


async def upload(
    records: Iterable[Record],
    concurrency: int = 4,
    progress: Callable[[int], None] | None = None,
) -> dict[str, int]:
    """Write the records, in order (see the module for what that means); how many of each type
    were written. The first record that cannot be written stops the rest, with
    `PanglossBulkRecordError`: what was written before it stays written."""
    written: dict[str, int] = {}
    done = 0

    for type_name, group in itertools.groupby(
        records, key=lambda record: str(record[1].get("type"))
    ):

        def count(type_name: str = type_name) -> None:
            nonlocal done
            written[type_name] = written.get(type_name, 0) + 1
            done += 1
            if progress:
                progress(done)

        await write_group(group, concurrency, count)
    return written
