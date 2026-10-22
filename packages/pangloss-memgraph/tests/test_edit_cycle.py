"""Write, read, edit and save again, through the database, for every kind of model.

Every model of the kitchen sink of `pangloss-models` (its tests' `kitchen_sink.py`) is given samples made
from its field definitions (`sample_data.py`; four of them, which reach different members of each union).
For each, what is written must be what is read; and what is read, edited by changing nothing and sent back
as an update, must change nothing: the same is read again. That is the loop the interface makes
(`GET /api/<Model>/{id}/edit`, then `PUT`), which depends on the models made for writing, the writes, the
reads and the models made for reading all agreeing.
"""

import pathlib
import sys

import pytest
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry

sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "pangloss-models/tests/test_model_setup"))

import kitchen_sink  # noqa: E402
import sample_data  # noqa: E402

pytestmark = pytest.mark.asyncio(loop_scope="session")


def with_real_ids(value, ids: dict):
    """The sample with the ids of the entities it refers to replaced by those of entities that were made"""
    if isinstance(value, dict):
        return {
            k: (ids.get(v, v) if k == "id" and not isinstance(v, (dict, list)) else with_real_ids(v, ids))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [with_real_ids(v, ids) for v in value]
    return value


def without(value, keys=("meta",), suffixes=("_reverse",)):
    """A dump of what was read, without what is only for reading (`meta`, the fields of incoming relations)"""
    if isinstance(value, dict):
        return {
            k: without(v, keys, suffixes)
            for k, v in value.items()
            if k not in keys and not k.endswith(suffixes)
        }
    if isinstance(value, list):
        return [without(v, keys, suffixes) for v in value]
    return value


def lost(given, kept, path="") -> list[str]:
    """What was given and is not in what was kept: keys that are missing, and lists that are shorter, at any depth"""
    missing: list[str] = []
    if isinstance(given, dict):
        if not isinstance(kept, dict):
            return [f"{path}: kept as {type(kept).__name__}"]
        for key, value in given.items():
            if key not in kept:
                missing.append(f"{path}.{key}")
            else:
                missing.extend(lost(value, kept[key], f"{path}.{key}"))
    elif isinstance(given, list):
        if not isinstance(kept, list) or len(kept) < len(given):
            return [f"{path}: list of {len(given)} kept as a shorter one"]
        for index, (g, k) in enumerate(zip(given, kept)):
            missing.extend(lost(g, k, f"{path}[{index}]"))
    return missing


def differences(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            out.extend(differences(a.get(key, "<absent>"), b.get(key, "<absent>"), f"{path}.{key}"))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {str(a)[:40]} -> {str(b)[:40]}"]


async def test_every_kind_of_model_is_written_read_edited_and_saved_again(clear_database):
    kitchen_sink.declare()
    initialise()
    heads = {
        m.__name__: m
        for m in ModelRegistry._models
        if getattr(m, "__metatype__", None) in ("Document", "Entity")
    }
    samplable = [m for m in heads.values() if not getattr(m._meta, "abstract", False)]
    failures: list[str] = []

    async def read(model, identifier):
        edit = model.__metatype__ == "Entity"  # (the edit route gives an entity's EditView, a document's HeadView)
        return await (model.get_for_edit(identifier) if edit else model.get(identifier))

    for model in samplable:
        for choice in sample_data.CHOICES:
            label = f"{model.__name__} (choice {choice})"
            step = "sampling"
            try:
                sampler = sample_data.Sampler(choice)
                payload = sampler.head(model)
                payload.pop("type")
                ids = {}
                for entity_name, fake in sampler.references:  # (the entities it refers to must exist)
                    entity = heads[entity_name]
                    made = await entity.Create(**sample_data.sample_payload(entity)).save()
                    ids[fake] = made.id
                payload = with_real_ids(payload, ids)

                step = "writing"
                saved = await model.Create(**payload).save()

                step = "reading"
                first = await read(model, saved.id)
                dumped = without(first.model_dump())
                gone = lost(payload, dumped)
                assert not gone, f"lost on the way out and back: {gone[:4]}"

                step = "editing (update from what was read)"
                update = model.Update(**without(first.model_dump()))

                step = "saving the edit"
                await update.save()

                step = "reading again"
                second = without((await read(model, saved.id)).model_dump())
                changed = differences(dumped, second)
                assert not changed, f"changed by saving what was read, unchanged: {changed[:4]}"
            except Exception as error:
                failures.append(f"{label} while {step}: {type(error).__name__}: {str(error).replace(chr(10), ' ')[:260]}")

    assert not failures, "\n" + "\n".join(failures)
