"""The order of the members of a union does not decide which member is chosen.

A relation to an entity that can be named in a document (`create_inline`) offers two members: a reference to
an entity that exists and the entity itself, to be made. They are put in different orders in different
models (the database models put the entity first so that a new entity is not taken for a reference; the
client models put the reference first). That is only safe if pydantic's smart union gives the same answer
in either order, which is checked here for every such pair in the kitchen sink, with and without an edge
model, for what a client sends (`Create`, `Update`) and what is written (`CreateDB`, `UpdateDB`)."""

import types
import typing
from uuid import uuid7

import kitchen_sink
import pytest
import sample_data
from pangloss_models import initialise
from pangloss_models.model_registry import ModelRegistry
from pydantic import BaseModel, TypeAdapter

EDGE_SAMPLES = {"Certainty": {"level": 1}, "Weight": {"weight": 1.5}}


def members(annotation) -> list[type]:
    """The pydantic models in an annotation, through unions, lists, `Annotated` and the wrappers"""
    found = []
    stack = [annotation]
    while stack:
        item = stack.pop()
        if isinstance(item, type) and issubclass(item, BaseModel):
            found.append(item)
        args = typing.get_args(item)
        if args and (
            typing.get_origin(item) in (typing.Union, types.UnionType, typing.Annotated)
            or True
        ):
            stack.extend(args)
    return found


@pytest.fixture
def pairs():
    """(entity, kind, reference member, entity member) for every union that offers both"""
    kitchen_sink.declare()
    initialise()
    entities = [
        m
        for m in ModelRegistry._models
        if getattr(m, "__metatype__", None) == "Entity" and m._meta.create_inline
    ]
    assert {m.__name__ for m in entities} >= {"Person", "Source"}
    found = {}
    for model in ModelRegistry._models:
        for kind in ("Create", "Update", "CreateDB", "UpdateDB"):
            made = getattr(model, kind, None)
            if made is None:
                continue
            for field in made.model_fields.values():
                offered = members(field.annotation)
                for entity in entities:
                    inline_kind = "CreateDB" if kind.endswith("DB") else "Create"
                    refs = [m for m in offered if issubclass(m, entity.ReferenceSet)]
                    inlines = [
                        m
                        for m in offered
                        if issubclass(m, getattr(entity, inline_kind))
                    ]
                    for ref in refs:
                        for inline in inlines:
                            # (the same edge model on both)
                            if ref.model_fields.get(
                                "edge_properties"
                            ) == inline.model_fields.get("edge_properties") or str(
                                ref.model_fields["edge_properties"].annotation
                            ) == str(inline.model_fields["edge_properties"].annotation):
                                found[(entity, kind, ref, inline)] = True
    assert found, "no union with both a reference and an entity was found"
    return list(found)


def edge_sample(member) -> dict:
    field = member.model_fields.get("edge_properties")
    if field is None or field.annotation is None:
        return {}
    name = getattr(field.annotation, "__name__", "")
    return {"edgeProperties": EDGE_SAMPLES[name]} if name in EDGE_SAMPLES else {}


def payloads(entity, kind, ref, inline):
    reference = {"type": entity.__name__, "id": str(uuid7()), **edge_sample(ref)}
    sample = sample_data.sample_payload(entity)
    created = entity.Create(**sample, id=uuid7(), create_new=True)
    if kind.endswith("DB"):
        created = created._to_db_model()
    new = created.model_dump(by_alias=True, mode="json", exclude_none=True)
    new.update({"type": entity.__name__, **edge_sample(inline)})
    return reference, new


def test_the_order_of_a_union_does_not_change_what_is_chosen(pairs):
    failures = []
    for entity, kind, ref, inline in pairs:
        reference, new = payloads(entity, kind, ref, inline)
        for order in ((ref, inline), (inline, ref)):
            adapter = TypeAdapter(typing.Union[order])
            for name, payload, expected in (
                ("reference", reference, ref),
                ("new", new, inline),
            ):
                try:
                    chosen = type(adapter.validate_python(payload))
                except Exception as error:
                    chosen = f"{type(error).__name__}: {str(error)[:100]}"
                if chosen is not expected:
                    failures.append(
                        f"{entity.__name__} {kind}, a {name} payload, order "
                        f"{[m.__name__ for m in order]}: chose {getattr(chosen, '__name__', chosen)}, "
                        f"not {expected.__name__}"
                    )
    assert not failures, "\n" + "\n".join(failures)
