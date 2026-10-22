"""Properties that the five models made for a declared model must have *together*.

`Create` and `Update` are what a client sends, `CreateDB` and `UpdateDB` what is written, `View` what is
read. They are made by one builder but are different models, so it is not enough that each is right:
what one accepts, the others must. These tests give every model of the kitchen sink samples made from its
field definitions (`sample_data.py`; four of them for each, which reach different members of each union),
and check what must hold between the models. The models are made once for all of them (this is the slow
part), and a failure names every model and sample that broke it.
"""

import pytest
from uuid import uuid7

import kitchen_sink
import sample_data
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry


@pytest.fixture
def heads():
    """The documents and entities of the kitchen sink that can be created, with a sample for each of
    four choices of the members of unions"""
    kitchen_sink.declare()
    initialise()
    models = [
        m
        for m in ModelRegistry._models
        if getattr(m, "__metatype__", None) in ("Document", "Entity")
        and not getattr(m._meta, "abstract", False)
    ]
    assert len(models) >= 10  # (the sink has twelve)
    return [(m, c, sample_data.sample_payload(m, c)) for m in models for c in sample_data.CHOICES]


def check(heads, work):
    """Run `work(model, payload)` for every model and sample; fail with all that failed"""
    failures = []
    for model, choice, payload in heads:
        try:
            work(model, payload)
        except Exception as error:
            failures.append(f"{model.__name__} (choice {choice}): {type(error).__name__}: {str(error)[:300]}")
    assert not failures, "\n" + "\n".join(failures)


def test_every_sample_is_accepted_by_create(heads):
    check(heads, lambda model, payload: model.Create(**payload))


def test_a_create_payload_with_an_id_is_accepted_by_update(heads):
    """What can be created can be given as an update of an existing thing, with its id"""
    check(heads, lambda model, payload: model.Update(id=uuid7(), **payload))


def test_what_is_made_for_writing_can_be_made_from_both(heads):
    def work(model, payload):
        created = model.Create(**payload)
        written = created._to_db_model()
        assert isinstance(written, model.CreateDB), type(written)
        updated = model.Update(id=uuid7(), **payload)._to_db_model()
        assert isinstance(updated, model.UpdateDB), type(updated)
        # the values that were given are the values to be written
        for name, definition in model._meta.fields.literal_fields.items():
            if definition.db_field:
                continue
            assert getattr(written, name) == getattr(created, name), name
        if "label" in model.Create.model_fields:  # (a model may have none)
            assert written.label == created.label

    check(heads, work)


def test_a_model_survives_a_round_trip_through_its_aliases(heads):
    """Dumped with the names a client uses (`camelCase`) and read again, it is the same"""

    def work(model, payload):
        created = model.Create(**payload)
        dumped = created.model_dump(by_alias=True, mode="json")
        again = model.Create(**dumped)
        assert again.model_dump(mode="json") == created.model_dump(mode="json")

        updated = model.Update(id=uuid7(), **payload)
        dumped = updated.model_dump(by_alias=True, mode="json")
        assert model.Update(**dumped).model_dump(mode="json") == updated.model_dump(mode="json")

    check(heads, work)


def test_the_models_have_the_same_fields_and_agree_on_which_are_required(heads):
    """Every field that is not only for the database is in `Create`, `Update` and `View`; the database
    models have them all; and `Create` and `Update` require the same fields"""

    def work(model, payload):
        fields = model._meta.fields
        for name, definition in fields.items():
            kinds = ("CreateDB", "UpdateDB") if definition.db_field else (
                "Create", "Update", "View", "CreateDB", "UpdateDB"
            )
            for kind in kinds:
                assert name in getattr(model, kind).model_fields, f"{kind} has no {name}"
            if definition.db_field:
                for kind in ("Create", "Update", "View"):
                    assert name not in getattr(model, kind).model_fields, f"{kind} has {name}"
                continue
            create = model.Create.model_fields[name].is_required()
            update = model.Update.model_fields[name].is_required()
            assert create == update, f"{name}: required in Create {create}, in Update {update}"

    check(heads, work)


def lost(given, kept, path="") -> list[str]:
    """What was given and is not in what was kept: keys that are missing, and lists that are shorter, at
    any depth (a field that is not one of the model's is ignored when a model is made, silently)"""
    missing = []
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
            return [f"{path}: list of {len(given)} kept as {kept!r}"[:120]]
        for index, (g, k) in enumerate(zip(given, kept)):
            missing.extend(lost(g, k, f"{path}[{index}]"))
    return missing


def test_nothing_that_is_given_is_lost(heads):
    """Every value given for a model is in the model made from it, in the one made for writing, and in the
    one made for an update, at every depth. (The variant of a document or wrapper with an edge model had
    only `type` and `edge_properties`: the rest was ignored, silently.)"""

    def work(model, payload):
        # (the payload uses the names of the fields; a nested `type` is the name of the model)
        for name, made in (
            ("Create", model.Create(**payload)),
            ("Update", model.Update(id=uuid7(), **payload)),
        ):
            gone = lost(payload, made.model_dump())
            assert not gone, f"{name} lost {gone[:5]}"
        written = model.Create(**payload)._to_db_model()
        gone = lost(payload, written.model_dump())
        assert not gone, f"CreateDB lost {gone[:5]}"

    check(heads, work)
