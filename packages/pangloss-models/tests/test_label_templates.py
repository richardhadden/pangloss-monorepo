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


# --- the interpreter on its own (a schema from JSON, as the interface has it) ------------------------------------


def literal(name: str) -> dict:
    return {"name": name, "key": name, "kind": "literal"}


SMALL = LabelSchema.from_json(
    {
        "Book": {
            "kind": "Document",
            "requireLabel": True,
            "labelTemplate": None,
            "fields": [
                literal("title"),
                {"name": "authors", "key": "authors", "kind": "relation"},
                literal("pages"),
                literal("weight"),
                literal("signed"),
                {"name": "date", "key": "date", "kind": "embedded"},
            ],
        },
        "Maybe": {
            "kind": "ReifiedRelation",
            "requireLabel": False,
            "labelTemplate": None,
            "fields": [{"name": "target", "key": "target", "kind": "relation"}],
        },
        "When": {
            "kind": "Embedded",
            "requireLabel": False,
            "labelTemplate": {"formatter": "test:when"},
            "fields": [literal("year")],
        },
    },
    formatters=lambda name: (
        (lambda value: f"in {value['year']}" if value.get("year") else "")
        if name == "test:when"
        else None
    ),
)


def say(template: str, value: dict, schema: LabelSchema = SMALL) -> str | None:
    return render(LabelTemplate(template), {"type": "Book", **value}, schema)


AUTHORS = {
    "authors": [
        {"type": "Person", "label": "ann"},
        {"type": "Person", "label": "bob"},
        {"type": "Person", "label": "cy"},
    ]
}


@pytest.mark.parametrize(
    "template, said",
    [
        ("{authors|first}", "ann"),
        ("{authors|last}", "cy"),
        ("{authors|join}", "ann, bob, cy"),
        ('{authors|join(" / ")}', "ann / bob / cy"),
        ('{authors|join(", ", " & ")}', "ann, bob & cy"),
        ("{authors|count}", "3"),
        ("{authors|first|capitalise}", "Ann"),
        ('{authors|join(" ")|capitalise}', "Ann bob cy"),
        ("{title|lower}", "a title"),
        ("{title|capitalise}", "A Title"),
        ('{missing|default("none")}', "none"),
        ('{title|default("none")}', "A Title"),
    ],
)
def test_each_filter(template, said):
    assert say(template, {"title": "A Title", **AUTHORS}) == said


def test_a_filter_on_nothing_gives_nothing_and_so_no_label():
    for template in [
        "{authors|count}",
        "{authors|join}",
        "{authors|lower}",
        "{authors|capitalise}",
        "{authors|last}",
    ]:
        assert say(template, {"authors": []}) is None, template
    assert (
        say(
            '{authors|join(" and ")}', {"authors": [{"type": "Person", "label": "ann"}]}
        )
        == "ann"
    )


def test_values_as_text():
    assert say("{pages}", {"pages": 2.0}) == "2"
    assert say("{weight}", {"weight": 2.5}) == "2.5"
    assert say("{pages}", {"pages": 7}) == "7"
    assert say("{signed}", {"signed": True}) == "true"
    assert say("{signed}", {"signed": False}) == "false"
    assert say("{title}", {"title": ""}) is None
    # an annotated value (`{value, certainty}`) by its value, and a path into it
    assert say("{title}", {"title": {"value": "Kept", "certainty": 1}}) == "Kept"
    assert say("{title.certainty}", {"title": {"value": "Kept", "certainty": 1}}) == "1"
    assert say("{title}", {"title": {"certainty": 1}}) is None
    # a label written is what a thing is called, before what it holds (and an empty one is none)
    named = {"type": "Book", "label": "by hand", "title": "t"}
    assert say("{authors}", {"authors": [named]}) == "by hand"
    assert say("{authors}", {"authors": [{**named, "label": ""}]}) is None


def test_a_reified_relation_without_a_template_reads_as_what_it_holds():
    maybe = {
        "type": "Maybe",
        "target": [
            {"type": "Person", "label": "ann"},
            {"type": "Person", "label": "bob"},
        ],
    }
    assert say("{authors}", {"authors": [maybe]}) == "ann, bob"
    assert say("{authors|count}", {"authors": [maybe]}) == "2"
    assert say("{authors.target}", {"authors": [maybe]}) == "ann, bob"


def test_an_embedded_object_with_a_formatter_reads_as_the_formatter_says():
    assert say("{date}", {"date": {"type": "When", "year": 1500}}) == "in 1500"
    # (the formatter giving "" is nothing, and so is a formatter that is not registered)
    assert say("{date}", {"date": {"type": "When", "year": None}}) is None
    unregistered = LabelSchema(SMALL.models, formatters=lambda name: None)
    assert say("{date}", {"date": {"type": "When", "year": 1500}}, unregistered) is None


@pytest.mark.parametrize(
    "source, text",
    [
        (r"a \[b\] \{c\} d\\e", r"a [b] {c} d\e"),
        (r'{x|default("say \"hi\"")}', 'say "hi"'),
        (r'{x|default("back\\slash")}', "back\\slash"),
        # (other escapes in the text of a filter are kept, for the template of `each`)
        (r'{x|default("\{x\}")}', r"\{x\}"),
    ],
)
def test_escapes(source, text):
    parts = parse(source)
    if len(parts) == 1 and type(parts[0]).__name__ == "Text":
        assert parts[0].text == text  # ty: ignore[unresolved-attribute]
    else:
        assert parts[0].filters[0].args == (text,)  # ty: ignore[unresolved-attribute]


def test_the_text_of_each_is_a_template_with_its_own_escapes():
    assert (
        say(
            r'{authors|each("\{{authors}\}")|join}',
            {
                "authors": [
                    {"type": "Book", "authors": [{"type": "Person", "label": "ann"}]}
                ]
            },
        )
        == "{ann}"
    )


@pytest.mark.parametrize(
    "source, problem",
    [
        ("ends with \\", "a \\ at the end (at 10)"),
        ("{x|default(y)}", 'a text in "" expected'),
        ('{x|default("a" "b")}', "a , or a ) expected"),
        ("{x|default}", "'default' takes 1 text(s), not 0"),
        ('{x|each("a", "b")}', "'each' takes 1 text(s), not 2"),
        ('{x|join("a", "b", "c")}', "'join' takes 0 to 2 text(s), not 3"),
    ],
)
def test_more_templates_that_cannot_be_read(source, problem):
    with pytest.raises(PanglossMetaError) as raised:
        parse(source)
    assert problem in str(raised.value)
    assert raised.value.at_string is not None


def test_a_label_template_and_a_formatter_are_checked_when_they_are_made():
    from pangloss_models import Formatter

    with pytest.raises(PanglossMetaError, match="one template or more"):
        LabelTemplate()
    with pytest.raises(PanglossMetaError, match="one template or more"):
        LabelTemplate("{a}", 3)  # ty: ignore[invalid-argument-type]
    for bad in ["nocolon", "a:b:c", 3]:
        with pytest.raises(PanglossMetaError, match="the name is 'app:name'"):
            Formatter(bad)  # ty: ignore[invalid-argument-type]
    assert Formatter("app:name").name == "app:name"
    assert LabelTemplate("{a}") != "{a}"
    assert Formatter("app:name") != "app:name"


def test_a_root_is_worked_out_even_if_it_looks_like_a_reference():
    declare_case_models()
    root = {"type": "Person", "id": "x"}
    derived = derive_labels(root, models_schema())
    assert root == {"type": "Person", "id": "x", "label": "", "labelAuto": True}
    assert derived.labels == {"x": ("", True)}
    assert derived.empty == [((), "Person")]


def test_the_schema_is_made_again_for_other_models_and_kept_for_the_same():
    from pangloss_models import ModelRegistry

    declare_case_models()
    first = models_schema()
    assert models_schema() is first
    ModelRegistry._reset()

    class Letter(Document):
        text: str
        _meta = Document.Meta(label_template="{text}")

    initialise(bind_database=False)
    second = models_schema()
    assert "Letter" in second.models and "Will" not in second.models
    assert models_schema() is second


def test_a_nested_label_its_template_gives_nothing_for_is_refused_at_its_path():
    models = declare_case_models()

    async def read_labels(ids):
        return {}

    will = (
        models["Will"]
        .Create(
            testator={"type": "Person", "id": uuid.uuid4()},
            made_at=None,
            bequests=[
                {
                    "type": "Bequest",
                    "item": "a cup",
                    "recipient": {
                        "type": "Identification",
                        "target": [{"type": "Person", "id": uuid.uuid4()}],
                    },
                }
            ],
        )
        ._to_db_model()
    )
    with pytest.raises(
        PanglossWriteRefused, match="Bequest: its label_template gives no label"
    ) as refused:
        asyncio.run(fill_labels(will, read_labels))
    assert refused.value.path == ("bequests", 0, "label")
