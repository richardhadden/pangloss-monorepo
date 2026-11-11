"""Label templates (implementation_docs/label-templates.md): the language, the checks at `initialise()`, the models a label is
written by, and `fill_labels`. The cases in `label_cases.json` are run here and by the interface
(`interface-core/src/schema/labelTemplate.test.ts`): `PANGLOSS_WRITE_LABEL_CASES=1` writes the file again"""

import asyncio
import copy
import json
import os
import uuid
from pathlib import Path

import pytest
from pangloss_models import (
    Conjunction,
    Document,
    Embedded,
    Entity,
    LabelTemplate,
    PanglossMetaError,
    PanglossModelError,
    PanglossWriteRefused,
    ReifiedRelation,
    initialise,
)
from pangloss_models.label_templates import (
    LabelSchema,
    derive_labels,
    fill_labels,
    label_schema_json,
    models_schema,
    parse,
    render,
)

CASES = Path(__file__).parent / "label_cases.json"


# --- the language ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, problem",
    [
        ("Birth of {person", "a } expected"),
        ("Birth of person}", "a } with no {"),
        ("[at {place}", "a [ that is not closed"),
        ("at {place}]", "a ] with no ["),
        ("{people|jion}", "there is no filter 'jion'. Did you mean 'join'?"),
        ('{people|join(", ", "and", "x")}', "'join' takes 0 to 2"),
        ("{people|each}", "'each' takes 1"),
        ("{}", "the name of a field expected"),
        ('{a|default("x)}', "not closed"),
    ],
)
def test_a_template_that_cannot_be_read_is_refused_when_it_is_declared(source, problem):
    with pytest.raises(PanglossMetaError, match=None) as raised:
        parse(source)
    assert problem in str(raised.value)


def test_a_template_reads_escapes_groups_and_filters():
    parts = parse(r'\{x\} {a.b|join(" & ")|lower}[ ({c})]')
    assert [type(p).__name__ for p in parts] == ["Text", "Placeholder", "Group"]
    assert parts[0].text == "{x} "  # ty: ignore[unresolved-attribute]
    assert parts[1].path == ("a", "b")  # ty: ignore[unresolved-attribute]
    assert [f.name for f in parts[1].filters] == ["join", "lower"]  # ty: ignore[unresolved-attribute]


def test_meta_takes_a_string_a_label_template_or_nothing():
    class Statement(Document):
        text: str
        _meta = Document.Meta(label_template="{text}")

    assert Statement._meta.label_template == LabelTemplate("{text}")
    with pytest.raises(Exception, match="a string, a LabelTemplate"):
        Document.Meta(label_template=3)


# --- the models for the cases -----------------------------------------------------------------------------


def declare_case_models():
    class Person(Entity):
        forename: str | None = None
        surname: str | None = None
        _meta = Entity.Meta(
            label_template=LabelTemplate("{surname}[, {forename}]", "{forename}")
        )

    class Place(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int | None = None

    class Witnesses[T](Conjunction):
        witness: list[T]
        also: list[T]

    class Amount(Embedded):
        number: int
        unit: str
        _meta = Embedded.Meta(label_template="{number} {unit}")

    class Bequest(Document):
        item: str
        recipient: Identification[Person]
        amount: Amount | None = None
        _meta = Document.Meta(label_template="{item}[ ({amount})] to {recipient}")

    class Will(Document):
        testator: Person
        made_at: Place | None
        bequests: list[Bequest]
        witnesses: Witnesses[Person] | None = None
        _meta = Document.Meta(
            label_template=LabelTemplate(
                'Will of {testator}[ at {made_at}][: {bequests|count} bequests][, witnessed by {witnesses|join(", ", " and ")}]',
                "Will of {testator}",
            )
        )

    class Summary(Document):
        will: Will
        _meta = Document.Meta(
            label_template='[{will.bequests|each("{item} → {recipient}")|join("; ")}][ | first: {will.bequests|first}][ | {will.testator|default("?")}]'
        )

    class Witnessing(Document):
        witnesses: list[Identification[Person]]
        _meta = Document.Meta(
            label_template='{witnesses|each("{target} [({certainty})]")|join("; ")}[ — {witnesses|count} in all]'
        )

    class Plain(Document):
        """A document without a template"""

        text: str

    initialise(bind_database=False)
    return locals()


_ids = iter(range(1, 10_000))


def ref(type_: str, label: str | None = None, id_: str | None = None) -> dict:
    # (ids that are the same each time: the file of cases is compared)
    made = {"type": type_, "id": id_ or f"00000000-0000-0000-0000-{next(_ids):012d}"}
    if label is not None:
        made["label"] = label
    return made


def build_cases() -> dict:
    global _ids
    _ids = iter(range(1, 10_000))
    models = declare_case_models()
    schema = models_schema()
    names = {
        "Person",
        "Place",
        "Identification",
        "Witnesses",
        "Amount",
        "Bequest",
        "Will",
        "Summary",
        "Witnessing",
        "Plain",
    }
    exported = {
        name: model
        for name, model in label_schema_json(schema).items()
        if name in names
    }
    anne = ref("Person", "Hathaway, Anne")
    judith = ref("Person", "Quiney, Judith")
    stratford = ref("Place", "Stratford")

    def bequest(item, recipient, amount=None, label=None, auto=None):
        made = {
            "type": "Bequest",
            "item": item,
            "recipient": {"type": "Identification", "target": [recipient]},
            "amount": amount,
        }
        if label is not None:
            made["label"] = label
        if auto is not None:
            made["labelAuto"] = auto
        return made

    cases = [
        {
            "name": "an entity by its own fields, the first alternative",
            "data": {"type": "Person", "forename": "Anne", "surname": "Hathaway"},
        },
        {
            "name": "the second alternative, when the first has an empty placeholder",
            "data": {"type": "Person", "forename": "Anne", "surname": None},
        },
        {
            "name": "no alternative: an empty label",
            "data": {"type": "Person", "forename": None, "surname": None},
        },
        {
            "name": "nested documents first, a reified relation by its target, an embedded object by its template",
            "data": {
                "type": "Will",
                "testator": anne,
                "madeAt": stratford,
                "bequests": [
                    bequest(
                        "a silver cup",
                        judith,
                        {"type": "Amount", "number": 2, "unit": "lb"},
                    ),
                    bequest("the second-best bed", anne),
                ],
                "witnesses": None,
            },
        },
        {
            "name": "a group left out; a conjunction by what it holds, joined with 'and'",
            "data": {
                "type": "Will",
                "testator": anne,
                "madeAt": None,
                "bequests": [],
                "witnesses": {
                    "type": "Witnesses",
                    "witness": [
                        ref("Person", "Collins, Francis"),
                        ref("Person", "Shaw, Julyne"),
                    ],
                    "also": [ref("Person", "Sadler, Hamnet")],
                },
            },
        },
        {
            "name": "a label written by hand is kept, and used by what holds it",
            "data": {
                "type": "Will",
                "testator": anne,
                "madeAt": None,
                "bequests": [
                    bequest("plate", judith, label="All my plate, by hand", auto=False),
                    bequest("a ring", anne, label="old label", auto=True),
                    bequest("a sword", judith, label="no flag: kept"),
                ],
                "witnesses": None,
            },
        },
        {
            "name": "a path into nested documents, each, first, and default",
            "data": {
                "type": "Summary",
                "will": {
                    "type": "Will",
                    "testator": {"type": "Person", "id": "x"},
                    "madeAt": None,
                    "bequests": [bequest("a cup", judith), bequest("a bed", anne)],
                    "witnesses": None,
                },
            },
        },
        {
            "name": "each takes the reified relations themselves; count and the text take what they hold",
            "data": {
                "type": "Witnessing",
                "witnesses": [
                    {"type": "Identification", "certainty": 2, "target": [anne]},
                    {"type": "Identification", "certainty": None, "target": [judith]},
                ],
            },
        },
        {
            "name": "a reference with no label is not worked out (it is not part of the item)",
            "data": {
                "type": "Will",
                "testator": {"type": "Person", "id": "y"},
                "madeAt": None,
                "bequests": [],
                "witnesses": None,
            },
        },
    ]
    for case in cases:
        made = copy.deepcopy(case["data"])
        derive_labels(made, schema)
        case["expected"] = made
    del models
    return {"models": exported, "cases": cases}


def test_the_shared_cases_are_up_to_date():
    built = build_cases()
    text = json.dumps(built, indent=2, ensure_ascii=False) + "\n"
    if os.environ.get("PANGLOSS_WRITE_LABEL_CASES"):
        CASES.write_text(text)
    assert CASES.read_text() == text, (
        "label_cases.json is out of date: run with PANGLOSS_WRITE_LABEL_CASES=1"
    )


def test_the_shared_cases_give_these_labels():
    built = json.loads(CASES.read_text())
    labels = [case["expected"].get("label") for case in built["cases"]]
    assert labels == [
        "Hathaway, Anne",
        "Anne",
        "",
        "Will of Hathaway, Anne at Stratford: 2 bequests",
        "Will of Hathaway, Anne, witnessed by Collins, Francis, Shaw, Julyne and Sadler, Hamnet",
        "Will of Hathaway, Anne: 3 bequests",
        "a cup → Quiney, Judith; a bed → Hathaway, Anne | first: a cup to Quiney, Judith | ?",
        "Hathaway, Anne (2); Quiney, Judith — 2 in all",
        # (a reference without a label names nothing: no alternative gives a label)
        "",
    ]
    will = built["cases"][3]["expected"]
    assert [b["label"] for b in will["bequests"]] == [
        "a silver cup (2 lb) to Quiney, Judith",
        "the second-best bed to Hathaway, Anne",
    ]
    by_hand = built["cases"][5]["expected"]
    assert [(b["label"], b["labelAuto"]) for b in by_hand["bequests"]] == [
        ("All my plate, by hand", False),
        ("a ring to Hathaway, Anne", True),
        ("no flag: kept", False),
    ]


def test_the_cases_give_the_same_from_the_schema_in_the_file():
    built = json.loads(CASES.read_text())
    schema = LabelSchema.from_json(built["models"])
    for case in built["cases"]:
        made = copy.deepcopy(case["data"])
        derive_labels(made, schema)
        assert made == case["expected"], case["name"]


# --- initialise() ------------------------------------------------------------------------------------------


def test_a_path_to_a_field_that_is_not_there_is_refused():
    class Person(Entity):
        pass

    class Birth(Document):
        person: Person
        _meta = Document.Meta(label_template="Birth of {persn}")

    with pytest.raises(PanglossModelError, match="Did you mean 'person'"):
        initialise(bind_database=False)


def test_a_path_through_an_entity_is_refused():
    class Person(Entity):
        name: str

    class Birth(Document):
        person: Person
        _meta = Document.Meta(label_template="Birth of {person.name}")

    with pytest.raises(PanglossModelError, match="only use the label"):
        initialise(bind_database=False)


def test_a_yes_or_no_field_is_refused():
    class Event(Document):
        certain: bool
        _meta = Document.Meta(label_template="Event {certain}")

    with pytest.raises(PanglossModelError, match="yes-or-no"):
        initialise(bind_database=False)


def test_an_embedded_object_without_a_template_is_refused_but_its_fields_may_be_named():
    class Measure(Embedded):
        number: int

    class Thing(Document):
        size: Measure
        _meta = Document.Meta(label_template="Thing of {size}")

    with pytest.raises(PanglossModelError, match="no label_template of its own"):
        initialise(bind_database=False)


def test_an_embedded_objects_fields_and_a_reified_relations_target_may_be_named():
    class Person(Entity):
        pass

    class Identification[T](ReifiedRelation[T]):
        certainty: int | None = None

    class Measure(Embedded):
        number: int

    class Thing(Document):
        size: Measure
        owner: Identification[Person]
        _meta = Document.Meta(
            label_template="{size.number} [{owner.certainty}] {owner} {owner.target}"
        )

    initialise(bind_database=False)


def test_an_unknown_formatter_is_refused():
    from pangloss_models import Formatter

    class Measure(Embedded):
        number: int
        _meta = Embedded.Meta(label_template=Formatter("nowhere:measure"))

    with pytest.raises(PanglossModelError, match="no formatter of that name"):
        initialise(bind_database=False)


# --- the generated models, and fill_labels -----------------------------------------------------------------


def test_with_a_template_the_label_may_be_left_out_and_says_whether_it_is_worked_out():
    models = declare_case_models()
    Will, Plain, Bequest = models["Will"], models["Plain"], models["Bequest"]
    assert Will.Create.model_fields["label"].is_required() is False
    assert "label_auto" in Will.Create.model_fields
    assert "label_auto" in Will.Update.model_fields
    assert "label_auto" in Will.View.model_fields
    assert "label_auto" in Will.HeadView.model_fields
    assert Will.View.model_fields["label"].is_required()
    assert Plain.Create.model_fields["label"].is_required()
    assert "label_auto" not in Plain.Create.model_fields
    # (an embedded object or a reified relation has no label: its template is how it reads in another's)
    assert "label" not in models["Amount"].Create.model_fields
    assert Bequest.Create.model_fields["label"].is_required() is False


def test_fill_labels_reads_what_is_referred_to_once_and_works_the_labels_out():
    models = declare_case_models()
    Will = models["Will"]
    anne, judith = uuid.uuid4(), uuid.uuid4()
    will = Will.Create(
        testator={"type": "Person", "id": anne},
        made_at=None,
        bequests=[
            {
                "type": "Bequest",
                "item": "a cup",
                "recipient": {
                    "type": "Identification",
                    "target": [{"type": "Person", "id": judith}],
                },
            },
            {
                "type": "Bequest",
                "item": "a bed",
                "label": "My bed, by hand",
                "recipient": {
                    "type": "Identification",
                    "target": [{"type": "Person", "id": anne}],
                },
            },
        ],
    )._to_db_model()
    asked: list[list[str]] = []

    async def read_labels(ids):
        asked.append(ids)
        return {str(anne): "Hathaway, Anne", str(judith): "Quiney, Judith"}

    asyncio.run(fill_labels(will, read_labels))
    assert asked == [sorted([str(anne), str(judith)])]
    assert (will.label, will.label_auto) == ("Will of Hathaway, Anne: 2 bequests", True)
    assert [(b.label, b.label_auto) for b in will.bequests] == [
        ("a cup to Quiney, Judith", True),
        ("My bed, by hand", False),
    ]


def test_fill_labels_reads_nothing_for_an_item_without_a_template():
    models = declare_case_models()

    async def read_labels(ids):
        raise AssertionError("nothing to read")

    plain = models["Plain"].Create(label="x", text="t")._to_db_model()
    asyncio.run(fill_labels(plain, read_labels))
    assert plain.label == "x"


def test_a_label_its_template_gives_nothing_for_is_refused():
    models = declare_case_models()

    async def read_labels(ids):
        return {}

    person = models["Person"].Create()._to_db_model()
    with pytest.raises(PanglossWriteRefused, match="gives no label") as refused:
        asyncio.run(fill_labels(person, read_labels))
    assert refused.value.path == ("label",)


def test_render_takes_the_first_alternative_that_gives_a_label():
    declare_case_models()
    schema = models_schema()
    template = LabelTemplate("{surname}", "{forename}", "nobody")
    assert render(template, {"type": "Person", "forename": "A"}, schema) == "A"
    assert render(template, {"type": "Person"}, schema) == "nobody"
