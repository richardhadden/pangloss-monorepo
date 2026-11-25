"""The path of the nodes of a document (`pangloss_models.context`; implementation_docs/semantic-spaces.md): the
nodes a node is nested in, from the head down, and the semantic spaces made from it. First the algorithm on plain
objects, then on the instances the models write, in the shapes the lists that came before the path got wrong
(implementation_docs/spaces-and-comparison-plan.md, phase 1)."""

from typing import no_type_check
from uuid import uuid7

from pangloss_models import (
    Conjunction,
    Document,
    Embedded,
    Entity,
    ReifiedRelation,
    SemanticSpace,
    initialise,
)
from pangloss_models.context import propagate_context, spaces_of

# --- the algorithm, on plain objects ------------------------------------------------------------------------------


class Plain:
    def __init__(self, type: str, kind: str = "document", **held):
        self.type, self.kind, self.held = type, kind, held
        self.path: list = []


class PlainView:
    def is_entity(self, node):
        return node.kind == "entity"

    def kind_of(self, node):
        return node.kind

    def type_of(self, node):
        return node.type

    def id_of(self, node):
        return node.type.lower()

    def children(self, node):
        for field, value in node.held.items():
            for item in value if isinstance(value, list) else [value]:
                yield field, item

    def assign(self, node, path):
        node.path = path


def trail(node) -> list[str]:
    return [f"{entry['type']}.{entry['field']}" for entry in node.path]


def test_a_child_s_path_is_its_parent_s_path_and_the_parent():
    leaf = Plain("Leaf")
    space = Plain("Not", "space", contents=[leaf])
    head = Plain("Head", statements=[space])
    propagate_context(head, PlainView())
    assert head.path == []
    assert space.path == [
        {"kind": "document", "type": "Head", "id": "head", "field": "statements"}
    ]
    assert leaf.path == [
        {"kind": "document", "type": "Head", "id": "head", "field": "statements"},
        {"kind": "space", "type": "Not", "id": "not", "field": "contents"},
    ]


def test_the_order_of_the_fields_does_not_matter():
    def build(first: str):
        a, b = Plain("A"), Plain("B")
        in_space = {"cause": Plain("If", "space", contents=[a])}
        bare = {"result": b}
        held = in_space | bare if first == "space" else bare | in_space
        propagate_context(Plain("Causes", "conjunction", **held), PlainView())
        return trail(a), trail(b)

    assert build("space") == build("bare")
    assert build("space") == (["Causes.cause", "If.contents"], ["Causes.result"])


def test_no_node_shares_its_path_with_another():
    a, b = Plain("A"), Plain("B")
    head = Plain("Head", one=a, two=b, many=[Plain("C"), Plain("D")])
    propagate_context(head, PlainView())
    a.path.append("mine")
    a.path[0]["field"] = "changed"
    assert trail(b) == ["Head.two"]
    assert [trail(node) for node in head.held["many"]] == [["Head.many"]] * 2


def test_an_entity_met_in_a_document_starts_a_path_of_its_own():
    role = Plain("Role", "reified")
    person = Plain("Person", "entity", roles=[role])
    propagate_context(Plain("Head", about=person), PlainView())
    assert person.path == []
    assert trail(role) == ["Person.roles"]


def test_the_semantic_spaces_are_the_spaces_of_the_path_outermost_first():
    path = [
        {"kind": "document", "type": "Factoid", "id": "f", "field": "statements"},
        {"kind": "space", "type": "Doubt", "id": "d", "field": "contents"},
        {"kind": "conjunction", "type": "Causes", "id": "c", "field": "result"},
        {"kind": "space", "type": "Not", "id": "n", "field": "contents"},
    ]
    assert spaces_of(path) == ["Doubt", "Not"]
    assert spaces_of([]) == []


# --- on the instances the models write ----------------------------------------------------------------------------


def nodes_of(instance, found=None) -> dict[str, list]:
    """Every node of a `CreateDB` instance, by its label (or, with none, its type)"""
    found = {} if found is None else found
    found.setdefault(getattr(instance, "label", None) or instance.type, []).append(
        instance
    )
    fields = instance._meta.fields
    for name in (*fields.relation_fields, *fields.embedded_fields):
        value = getattr(instance, name, None)
        for item in value if isinstance(value, list) else [value]:
            if hasattr(item, "context_path"):
                nodes_of(item, found)
    return found


def one(nodes: dict[str, list], name: str):
    (node,) = nodes[name]
    return node


def assert_spaces_follow_paths(nodes: dict[str, list]) -> None:
    for group in nodes.values():
        for node in group:
            assert node.semantic_spaces == spaces_of(node.context_path)
            assert all(entry["id"] != str(node.id) for entry in node.context_path)


def doc(type: str, label: str | None = None, **fields) -> dict:
    return {"type": type, "label": label or type, **fields}


def space(type: str, *contents) -> dict:
    return {"type": type, "contents": list(contents)}


@no_type_check
def declare():
    class P(Document):
        pass

    class W(Document):
        pass

    class Service(Document):
        parts: list[P]

    class QuietService(Document):
        _meta = Document.Meta(use_in_semantic_space_label=False)
        parts: list[P]

    class Not[T](SemanticSpace[T]):
        pass

    class Ordered[T](SemanticSpace[T]):
        pass

    class If[T](SemanticSpace[T]):
        pass

    class Committed[T](SemanticSpace[T]):
        pass

    class Order(Document):
        thing: Ordered[P]
        witnesses: list[W]

    class Causes(Conjunction):
        cause: P | Not[P] | Order
        result: P

    class Cond(Conjunction):
        cause: If[P]
        consequence: Committed[P]

    class Factoid(Document):
        statements: list[
            P | Not[P | Service | QuietService | Not[P]] | Order | Cond | Causes
        ]

    initialise()
    return Factoid


def written(*statements) -> dict[str, list]:
    factoid = declare()
    db = factoid.Create(label="Factoid", statements=list(statements))._to_db_model()
    nodes = nodes_of(db)
    assert_spaces_follow_paths(nodes)
    return nodes


def kinds_and_fields(node) -> list[tuple[str, str, str]]:
    return [(e["kind"], e["type"], e["field"]) for e in node.context_path]


def test_two_single_slots_each_in_a_space_are_each_in_their_own():
    nodes = written(
        {
            "type": "Cond",
            "cause": space("If", doc("P", "cause")),
            "consequence": space("Committed", doc("P", "consequence")),
        }
    )
    assert one(nodes, "cause").semantic_spaces == ["If"]
    assert one(nodes, "consequence").semantic_spaces == ["Committed"]
    assert kinds_and_fields(one(nodes, "consequence")) == [
        ("document", "Factoid", "statements"),
        ("conjunction", "Cond", "consequence"),
        ("space", "Committed", "contents"),
    ]


def test_a_list_after_a_single_relation_that_holds_a_space_is_not_in_the_space():
    nodes = written(
        doc(
            "Order",
            thing=space("Ordered", doc("P", "ordered")),
            witnesses=[doc("W", "witness")],
        )
    )
    assert one(nodes, "ordered").semantic_spaces == ["Ordered"]
    assert one(nodes, "witness").semantic_spaces == []
    assert kinds_and_fields(one(nodes, "witness")) == [
        ("document", "Factoid", "statements"),
        ("document", "Order", "witnesses"),
    ]


def test_a_bare_result_after_a_negated_cause_is_not_negated():
    nodes = written(
        {
            "type": "Causes",
            "cause": space("Not", doc("P", "cause")),
            "result": doc("P", "result"),
        }
    )
    assert one(nodes, "cause").semantic_spaces == ["Not"]
    assert one(nodes, "result").semantic_spaces == []
    # (and the cause is no part of the result's context: a sibling does not hold it)
    assert kinds_and_fields(one(nodes, "result")) == [
        ("document", "Factoid", "statements"),
        ("conjunction", "Causes", "result"),
    ]
    # (nor is the older record of a node's place written: the path is the only one)
    assert "context_labels" not in type(one(nodes, "result")).model_fields


def test_the_space_of_an_order_that_is_a_cause_does_not_reach_the_result():
    nodes = written(
        {
            "type": "Causes",
            "cause": doc(
                "Order", thing=space("Ordered", doc("P", "ordered")), witnesses=[]
            ),
            "result": doc("P", "result"),
        }
    )
    assert one(nodes, "ordered").semantic_spaces == ["Ordered"]
    assert kinds_and_fields(one(nodes, "ordered")) == [
        ("document", "Factoid", "statements"),
        ("conjunction", "Causes", "cause"),
        ("document", "Order", "thing"),
        ("space", "Ordered", "contents"),
    ]
    assert one(nodes, "result").semantic_spaces == []


def test_a_statement_between_a_space_and_a_node_is_on_its_path_whatever_its_label_flag():
    bare = one(written(space("Not", doc("P", "part"))), "part")
    in_service = one(
        written(space("Not", doc("Service", parts=[doc("P", "part")]))), "part"
    )
    in_quiet = one(
        written(space("Not", doc("QuietService", parts=[doc("P", "part")]))), "part"
    )
    assert kinds_and_fields(bare) == [
        ("document", "Factoid", "statements"),
        ("space", "Not", "contents"),
    ]
    assert kinds_and_fields(in_service) == [
        *kinds_and_fields(bare),
        ("document", "Service", "parts"),
    ]
    # (the flag is a matter of what a trail shows: the path says the truth)
    assert kinds_and_fields(in_quiet) == [
        *kinds_and_fields(bare),
        ("document", "QuietService", "parts"),
    ]
    assert bare.semantic_spaces == in_service.semantic_spaces == ["Not"]
    assert in_quiet.semantic_spaces == ["Not"]


def test_a_space_has_a_path_of_its_own_and_is_in_the_spaces_above_it():
    nodes = written(space("Not", space("Not", doc("P", "twice"))))
    outer, inner = sorted(nodes["Not"], key=lambda node: len(node.context_path))
    assert outer.semantic_spaces == []
    assert kinds_and_fields(outer) == [("document", "Factoid", "statements")]
    assert inner.semantic_spaces == ["Not"]
    assert inner.context_path[-1] == {
        "kind": "space",
        "type": "Not",
        "id": str(outer.id),
        "field": "contents",
    }
    assert one(nodes, "twice").semantic_spaces == ["Not", "Not"]


def test_the_head_has_no_path():
    nodes = written(doc("P", "plain"))
    assert one(nodes, "Factoid").context_path == []
    assert one(nodes, "Factoid").semantic_spaces == []


@no_type_check
def test_reified_relations_and_embedded_objects_are_on_the_path_and_have_one():
    class Person(Entity):
        pass

    class When(Embedded):
        year: int

    class InRole[T](ReifiedRelation[T]):
        when: When

    class Meeting(Document):
        people: list[InRole[Person]]
        when: When

    initialise()
    db = Meeting.Create(
        label="Meeting",
        when={"type": "When", "year": 800},
        people=[
            {
                "type": "InRole",
                "target": [{"type": "Person", "id": uuid7()}],
                "when": {"type": "When", "year": 799},
            }
        ],
    )._to_db_model()
    role = db.people[0]
    assert kinds_and_fields(db.when) == [("document", "Meeting", "when")]
    assert kinds_and_fields(role) == [("document", "Meeting", "people")]
    assert kinds_and_fields(role.when) == [
        ("document", "Meeting", "people"),
        ("reified", "InRole", "when"),
    ]


@no_type_check
def test_an_entity_made_with_a_document_has_an_empty_path_and_holds_from_itself():
    class Place(Entity):
        pass

    class At[T](ReifiedRelation[T]):
        pass

    class Person(Entity):
        _meta = Entity.Meta(create_inline=True, create_with_id=True)
        born: At[Place]

    class Not[T](SemanticSpace[T]):
        pass

    class Statement(Document):
        about: Person

    class Factoid(Document):
        statements: list[Not[Statement]]

    initialise()
    person_id = uuid7()
    db = Factoid.Create(
        label="Factoid",
        statements=[
            {
                "type": "Not",
                "contents": [
                    {
                        "type": "Statement",
                        "label": "Statement",
                        "about": {
                            "type": "Person",
                            "id": person_id,
                            "label": "Ada",
                            "create_new": True,
                            "born": {
                                "type": "At",
                                "target": [{"type": "Place", "id": uuid7()}],
                            },
                        },
                    }
                ],
            }
        ],
    )._to_db_model()
    statement = db.statements[0].contents[0]
    person = statement.about
    assert statement.semantic_spaces == ["Not"]
    # (the entity is no part of the document: it is not in the space, and what it holds starts from it)
    assert person.context_path == []
    assert person.semantic_spaces == []
    assert person.born.context_path == [
        {"kind": "entity", "type": "Person", "id": str(person_id), "field": "born"}
    ]
    assert person.born.semantic_spaces == []
