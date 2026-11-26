"""The ground of a head class (`Ground`; implementation_docs/semantic-spaces.md, "The ground"): its defaults by kind,
how it is inherited, every refusal at `initialise()` by its message, the export, and that it is not data."""

import ast
from pathlib import Path
from typing import no_type_check

import pytest
from pangloss_models import (
    Document,
    Entity,
    Ground,
    ReifiedRelation,
    SemanticSpace,
    initialise,
)
from pangloss_models.diagnostics import FIXES
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.export import export_models
from pangloss_models.migrations.snapshot import build_snapshot, snapshot_hash
from pangloss_models.model_bases.ground import ground_of
from pydantic import ValidationError


@no_type_check
def test_a_class_that_says_nothing_is_asserted_with_the_standing_of_its_kind():
    class Person(Entity):
        pass

    class Factoid(Document):
        about: Person

    initialise()
    assert Factoid._meta.ground is None and Person._meta.ground is None
    assert ground_of(Factoid) == Ground(standing="claim")
    assert ground_of(Person) == Ground(standing="record")
    assert ground_of(Factoid).veridical == 1 and ground_of(Factoid).fit == "describes"


@no_type_check
def test_a_ground_is_inherited_and_a_subclass_may_set_its_own():
    class Source(Entity):
        pass

    class Factoid(Document):
        _meta = Document.Meta(abstract=True, ground=Ground(by="source"))
        source: Source

    class Charter(Factoid):
        pass

    class Rumour(Factoid):
        _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))

    class Whisper(Rumour):
        pass

    initialise()
    assert ground_of(Charter) == Ground(by="source", standing="claim")
    assert ground_of(Rumour) == Ground(veridical=0, degree="possible", standing="claim")
    assert ground_of(Whisper) == ground_of(Rumour)


@no_type_check
def test_an_entity_may_be_a_claim_and_a_document_the_record():
    class Person(Entity):
        pass

    class Legend(Entity):
        _meta = Entity.Meta(ground=Ground(standing="claim", by="told_by"))
        told_by: Person

    class Register(Document):
        _meta = Document.Meta(ground=Ground(standing="record"))

    initialise()
    assert ground_of(Legend).standing == "claim" and ground_of(Legend).by == "told_by"
    assert ground_of(Register).standing == "record"


def test_a_ground_is_frozen_and_its_values_are_checked_where_it_is_written():
    ground = Ground(by="source")
    with pytest.raises(Exception, match="frozen|cannot assign"):
        ground.by = "other"  # ty: ignore[invalid-assignment]
    with pytest.raises(ValidationError):
        Ground(veridical=2)  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValidationError):
        Ground(degree="certain")  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValidationError):
        Ground(standing="fact")  # ty: ignore[invalid-argument-type]
    with pytest.raises(ValidationError):
        Ground(0)  # ty: ignore[too-many-positional-arguments]


# --- the refusals ---------------------------------------------------------------------------------------------


@no_type_check
def test_a_ground_that_denies_is_refused():
    class Hoax(Document):
        _meta = Document.Meta(ground=Ground(veridical=-1))

    with pytest.raises(
        PanglossModelError,
        match=r"Hoax: Ground\(veridical=-1\): a ground does not deny what its class holds\. Give veridical=0",
    ):
        initialise()


def _fixed(model: type) -> str:
    """The class's `_meta` statement in this file as it would be after the fix of its refusal (as `ast` writes it)"""
    with pytest.raises(PanglossModelError) as raised:
        initialise()
    assert raised.value.fix == "ground_degree"
    fix = FIXES["ground_degree"](model, "_meta")
    assert fix is not None and fix.title == "Leave out `degree`"
    (edit,) = fix.edits
    assert edit.file == __file__
    lines = Path(__file__).read_text().splitlines(keepends=True)
    start = sum(len(line) for line in lines[: edit.line - 1]) + edit.column
    end = sum(len(line) for line in lines[: edit.end_line - 1]) + edit.end_column
    text = "".join(lines)
    assert text[start:end] == edit.old_text
    tree = ast.parse(text[:start] + edit.new_text + text[end:])
    (node,) = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == model.__name__
    ]
    return ast.unparse(node.body[0])


@no_type_check
def test_a_degree_of_what_is_asserted_is_refused_with_its_fix():
    class LikelyFactoid(Document):
        _meta = Document.Meta(ground=Ground(degree="likely"))

    with pytest.raises(
        PanglossModelError,
        match=r"LikelyFactoid: Ground\(degree='likely'\), but what the class holds is asserted \(veridical=1\)",
    ):
        initialise()
    assert _fixed(LikelyFactoid) == "_meta = Document.Meta(ground=Ground())"


@no_type_check
def test_the_fix_leaves_the_rest_of_the_ground_as_written():
    class Source(Entity):
        pass

    class LikelySourced(Document):
        _meta = Document.Meta(
            abstract=True, ground=Ground(by="source", degree="likely", fit="prescribes")
        )
        source: Source

    assert (
        _fixed(LikelySourced)
        == "_meta = Document.Meta(abstract=True, ground=Ground(by='source', fit='prescribes'))"
    )


@no_type_check
def test_a_record_with_by_is_refused():
    class Person(Entity):
        pass

    class Register(Document):
        _meta = Document.Meta(ground=Ground(standing="record", by="kept_by"))
        kept_by: Person

    with pytest.raises(
        PanglossModelError,
        match=r"Register: Ground\(by='kept_by'\) on a record \(standing='record'\).*Leave by out, or give "
        r"standing='claim'",
    ):
        initialise()


@no_type_check
def test_an_entity_with_by_and_no_standing_is_a_record_and_refused():
    class Person(Entity):
        pass

    class Legend(Entity):
        _meta = Entity.Meta(ground=Ground(by="told_by"))
        told_by: Person

    with pytest.raises(
        PanglossModelError,
        match=r"Legend: Ground\(by='told_by'\) on a record \(Legend is an entity, whose ground is the record "
        r"unless it says standing='claim'\)",
    ):
        initialise()


@no_type_check
def test_by_that_is_no_field_is_refused_with_the_nearest_name():
    class Source(Entity):
        pass

    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="sorce"))
        source: Source

    with pytest.raises(
        PanglossModelError,
        match=r"Factoid: Ground\(by='sorce'\): Factoid has no field 'sorce'\. Did you mean 'source'\?",
    ) as raised:
        initialise()
    assert raised.value.at_string.candidates == ("source",)


@no_type_check
def test_by_that_is_not_a_relation_is_refused():
    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="source"))
        source: str

    with pytest.raises(
        PanglossModelError,
        match=r"Factoid: Ground\(by='source'\): Factoid\.source is not a relation\. It must be a relation that "
        r"reaches an entity",
    ):
        initialise()


@no_type_check
def test_by_that_reaches_only_documents_is_refused():
    class Note(Document):
        pass

    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="note"))
        note: Note

    with pytest.raises(
        PanglossModelError,
        match=r"Factoid\.note is a relation that reaches only documents",
    ):
        initialise()


@no_type_check
def test_by_may_reach_an_entity_through_a_wrapper_or_be_optional():
    class Source(Entity):
        pass

    class Cited[T](ReifiedRelation[T]):
        page: str = ""

    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="source"))
        source: Cited[Source]

    class Aside(Document):
        _meta = Document.Meta(ground=Ground(by="source"))
        source: Source | None = None

    initialise()
    assert ground_of(Factoid).by == "source" and ground_of(Aside).by == "source"


@no_type_check
def test_an_abstract_class_may_name_a_field_its_subclasses_declare_and_each_is_checked():
    class Source(Entity):
        pass

    class Factoid(Document):
        _meta = Document.Meta(abstract=True, ground=Ground(by="source"))

    class Charter(Factoid):
        source: Source

    class Stray(Factoid):
        pass

    with pytest.raises(
        PanglossModelError,
        match=r"Stray: Ground\(by='source'\): Stray has no field 'source'",
    ):
        initialise()


@no_type_check
def test_a_fault_inherited_whole_is_reported_of_the_parent_only():
    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(degree="likely"))

    class Charter(Factoid):
        pass

    with pytest.raises(PanglossModelError, match=r"^Factoid: Ground"):
        initialise()


# --- the export, and that it is not data ----------------------------------------------------------------------


@no_type_check
def test_the_export_has_the_ground_as_it_holds_of_heads_only():
    class Source(Entity):
        pass

    class Not[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical="not")

    class Statement(Document):
        pass

    class Factoid(Document):
        _meta = Document.Meta(ground=Ground(by="cited_source"))
        cited_source: Source
        statements: list[Statement | Not[Statement]]

    class Rumour(Document):
        _meta = Document.Meta(
            ground=Ground(veridical=0, degree="possible", fit="prescribes")
        )

    initialise()
    models = export_models()["models"]
    assert models["Factoid"]["ground"] == {
        "veridical": 1,
        "fit": "describes",
        "degree": None,
        "by": {"name": "cited_source", "key": "citedSource"},
        "standing": "claim",
    }
    assert models["Rumour"]["ground"] == {
        "veridical": 0,
        "fit": "prescribes",
        "degree": "possible",
        "by": None,
        "standing": "claim",
    }
    # (a class that says nothing: never null)
    assert models["Statement"]["ground"] == {
        "veridical": 1,
        "fit": "describes",
        "degree": None,
        "by": None,
        "standing": "claim",
    }
    assert models["Source"]["ground"]["standing"] == "record"
    assert "ground" not in models["Not"]


@no_type_check
def _declared(ground):
    from pangloss_models.model_registry import ModelRegistry

    ModelRegistry._reset()

    class Source(Entity):
        pass

    class Factoid(Document):
        _meta = Document.Meta(ground=ground)
        source: Source

    initialise()
    return build_snapshot()


def test_a_change_of_a_ground_is_no_change_of_the_data():
    plain = _declared(None)
    grounded = _declared(Ground(by="source"))
    uncommitted = _declared(Ground(veridical=0, degree="unlikely", standing="record"))
    assert (
        plain["models"]["Factoid"]["ground"] != grounded["models"]["Factoid"]["ground"]
    )
    assert snapshot_hash(plain) == snapshot_hash(grounded) == snapshot_hash(uncommitted)
