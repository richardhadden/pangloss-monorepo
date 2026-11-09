"""The export on a real database (either backend): what a read becomes, the routes, the dump, and the promise of the
ontology: generated data conforms to the generated shapes, and uses nothing the ontology does not have"""

import gzip
import json
from types import SimpleNamespace
from typing import Annotated, TypedDict
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pangloss_models import (
    AnnotatedValue,
    Conjunction,
    Document,
    EdgeModel,
    Embedded,
    Entity,
    ReifiedRelation,
    RelationConfig,
    SemanticSpace,
    Trait,
    Usage,
    ViaEdge,
    initialise,
)
from pangloss_rdf import (
    IRI,
    RDFField,
    RDFMeta,
    class_uri,
    convert,
    item_uri,
    property_uri,
)
from pangloss_rdf.dump import dump
from pangloss_rdf.export import item_quads
from pangloss_rdf.ontologies.crm import (
    E7_Activity,
    E21_Person,
    E39_Actor,
    P14_carried_out_by,
)
from pangloss_rdf.ontology import jsonld_context, ontology_quads
from pangloss_rdf.serialise import serialise
from pangloss_rdf.shacl import shape_quads
from pangloss_rdf.uris import ontology_url
from pangloss_users import see_unpublished
from pangloss_rdf.vocabulary import (
    RDF_OBJECT,
    RDF_SUBJECT,
    RDF_TYPE,
    RDF_VALUE,
    RDFS_LABEL,
    dcterms,
    pgo,
)
from rdflib import Dataset, Graph

pytestmark = pytest.mark.asyncio(loop_scope="session")

CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def declare():
    class Coords(TypedDict):
        lat: float

    class Sure(EdgeModel):
        level: int

    class WC[T](AnnotatedValue[T]):
        certainty: int

    class Span(Embedded):
        year: int

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Neg[T](SemanticSpace[T]):
        pass

    class Causes[A, B](Conjunction):
        cause: A
        result: B

    class Agent(Trait, E39_Actor):
        pass

    class Person(Entity, Agent, E21_Person):
        _meta = Entity.Meta(create_with_id=True, accept_url_as_id=True)

        known: WC[str]
        aliases: list[WC[str]]
        coords: Coords | None = None
        when: Span
        tags: Annotated[list[str], RDFField(ordered=True)]

    class Group(Entity, Agent):
        pass

    class Stmt(Document, E7_Activity):
        _meta = Document.Meta(create_directly=False)

        text: str
        by: Annotated[
            ViaEdge[Agent, Sure],
            RelationConfig(reverse_name="did"),
            RDFField(parent=P14_carried_out_by),
        ]
        who: Annotated[list[InRole[Agent]], RDFField(parent=P14_carried_out_by)]

    class Fact(Document):
        items: list[Stmt | Neg[Stmt] | Causes[Stmt, Stmt]]

    class Sealed(Fact):
        pass

    initialise()
    return SimpleNamespace(**locals())


def statement(person_id):
    return {
        "type": "Stmt",
        "label": "s",
        "text": "t",
        "by": {"type": "Person", "id": str(person_id), "edge_properties": {"level": 3}},
        "who": [
            {
                "type": "InRole",
                "role": "r",
                "target": [{"type": "Person", "id": str(person_id)}],
            }
        ],
    }


async def fill(m):
    url = f"https://viaf.org/{uuid4()}"
    person = await m.Person(
        id=url,
        create_new=True,
        label="Max",
        known={"value": "M", "certainty": 1},
        aliases=[{"value": "X", "certainty": 2}],
        coords={"lat": 1.0},
        when={"type": "Span", "year": 3},
        tags=["b", "a"],
    ).save()
    fact = await m.Fact(
        label="F",
        items=[
            statement(person.id),
            {"type": "Neg", "contents": [statement(person.id)]},
            {
                "type": "Causes",
                "cause": statement(person.id),
                "result": statement(person.id),
            },
        ],
    ).save()
    return SimpleNamespace(person=person, fact=fact, url=url)


@pytest_asyncio.fixture(loop_scope="session")
async def world(clear_database):
    m = declare()
    return m, await fill(m)


def triples(quads, s=None, p=None, o=None):
    return [
        q
        for q in quads
        if (s is None or q.subject == s)
        and (p is None or q.predicate == p)
        and (o is None or q.object == o)
    ]


async def person_quads(m, data):
    found = await item_quads(m.Person, data.person.id)
    assert found is not None
    return found[1]


async def fact_quads(m, data):
    return list(convert(await m.Fact.get(data.fact.id)))


async def test_a_head_is_a_graph_with_its_provenance_outside(world):
    m, data = world
    quads = await fact_quads(m, data)
    head = item_uri(m.Fact, data.fact.id)
    outside = [q for q in quads if q.graph is None]
    assert outside and all(q.subject == head for q in outside)
    assert triples(outside, head, dcterms("created"))
    assert triples(outside, head, pgo("version"))[0].object.lexical == "1"
    assert {q.graph for q in quads} == {None, head}


async def test_a_relation_is_a_direct_triple_and_an_edge_node(world):
    m, data = world
    quads = await fact_quads(m, data)
    item = (await m.Fact.get(data.fact.id)).items[0]
    subject = item_uri(m.Stmt, item.id)
    person = item_uri(m.Person, data.person.id)
    predicate = property_uri(m.Stmt, "by")
    assert triples(quads, subject, predicate, person)
    edges = triples(quads, subject, pgo("edge"))
    edge = next(e.object for e in edges if "Stmt.by" in e.object.value)
    assert triples(quads, edge, RDF_TYPE, pgo("Edge"))
    assert triples(quads, edge, RDF_SUBJECT, subject)
    assert triples(quads, edge, RDF_OBJECT, person)
    assert triples(quads, edge, pgo("position"))[0].object.lexical == "0"
    assert triples(quads, edge, property_uri(m.Sure, "level"))[0].object.lexical == "3"


async def test_an_entity_referred_to_is_only_what_a_chip_shows(world):
    m, data = world
    quads = await fact_quads(m, data)
    person = item_uri(m.Person, data.person.id)
    said = {q.predicate for q in triples(quads, person)}
    assert said == {RDF_TYPE, RDFS_LABEL}


async def test_outside_classes_and_properties_outside_a_space(world):
    m, data = world
    quads = await fact_quads(m, data)
    item = (await m.Fact.get(data.fact.id)).items[0]
    subject = item_uri(m.Stmt, item.id)
    person = item_uri(m.Person, data.person.id)
    assert triples(quads, subject, RDF_TYPE, IRI(f"{CRM}E7_Activity"))
    aligned = triples(quads, subject, IRI(P14_carried_out_by.uri))
    # (the direct relation, and through the role to the person, not the role)
    assert {q.object for q in aligned} == {person}


async def test_inside_a_space_nothing_is_asserted(world):
    m, data = world
    quads = await fact_quads(m, data)
    space = (await m.Fact.get(data.fact.id)).items[1]
    inner = item_uri(m.Stmt, space.contents[0].id)
    space_uri = item_uri(m.Neg, space.id)
    assert triples(quads, inner, pgo("inSpace"), space_uri)
    assert triples(quads, inner, RDF_TYPE, class_uri(m.Stmt))
    assert not triples(quads, inner, RDF_TYPE, IRI(f"{CRM}E7_Activity"))
    assert not triples(quads, inner, IRI(P14_carried_out_by.uri))
    assert not triples(quads, inner, property_uri(m.Stmt, "by"))
    # (the edge node is there: not asserted, but not lost)
    assert triples(quads, inner, pgo("edge"))
    assert triples(quads, inner, property_uri(m.Stmt, "text"))


async def test_an_aligned_property_does_not_pass_through_a_conjunction(world):
    m, data = world
    quads = await fact_quads(m, data)
    fact = await m.Fact.get(data.fact.id)
    causes = item_uri(m.Causes, fact.items[2].id)
    assert triples(quads, causes, property_uri(m.Causes, "cause"))
    assert not triples(quads, causes, IRI(P14_carried_out_by.uri))


async def test_an_entitys_own_data(world):
    m, data = world
    quads = await person_quads(m, data)
    subject = item_uri(m.Person, data.person.id)
    assert triples(quads, subject, RDF_TYPE, class_uri(m.Agent))
    assert triples(quads, subject, RDF_TYPE, IRI(f"{CRM}E21_Person"))
    # (the nearest outside class only)
    assert not triples(quads, subject, RDF_TYPE, IRI(f"{CRM}E39_Actor"))
    assert triples(
        quads, subject, IRI("http://www.w3.org/2002/07/owl#sameAs"), IRI(data.url)
    )
    known = triples(quads, subject, property_uri(m.Person, "known"))[0].object
    assert triples(quads, known, RDF_VALUE)[0].object.lexical == "M"
    assert (
        triples(quads, known, property_uri(m.WC, "certainty"))[0].object.lexical == "1"
    )
    aliases = triples(quads, subject, property_uri(m.Person, "aliases"))[0].object
    assert aliases.value.endswith("/Person.aliases/0")
    coords = triples(quads, subject, property_uri(m.Person, "coords"))[0].object
    assert triples(quads, coords, IRI(f"{property_uri(m.Person, 'coords')}.lat"))
    span = triples(quads, subject, property_uri(m.Person, "when"))[0].object
    assert triples(quads, span, RDF_TYPE, class_uri(m.Span))


async def test_an_ordered_list_keeps_its_order(world):
    m, data = world
    quads = await person_quads(m, data)
    graph = Graph()
    graph.parse(data=serialise(quads, "ttl"), format="turtle")
    from rdflib import URIRef
    from rdflib.collection import Collection

    subject, predicate = (
        URIRef(item_uri(m.Person, data.person.id).value),
        URIRef(property_uri(m.Person, "tags").value),
    )
    first = next(graph.objects(subject, predicate))
    assert [str(v) for v in Collection(graph, first)] == ["b", "a"]


async def test_an_entity_says_what_refers_to_it_not_what_they_say(world):
    m, data = world
    quads = await person_quads(m, data)
    subject = item_uri(m.Person, data.person.id)
    assert len(triples(quads, subject, pgo("referencedBy"))) == 4
    assert triples(quads, subject, pgo("referenceCount"))[0].object.lexical == "8"
    assert not triples(quads, None, property_uri(m.Stmt, "by"))


async def test_every_format_is_readable(world):
    m, data = world
    quads = await fact_quads(m, data)
    for name, parser in (("ttl", "turtle"), ("nt", "nt")):
        assert len(Graph().parse(data=serialise(quads, name), format=parser)) > 10
    for name, parser in (("trig", "trig"), ("nq", "nquads"), ("jsonld", "json-ld")):
        read = Dataset(default_union=True)
        read.parse(data=serialise(quads, name), format=parser)
        assert len(read) > 10


async def test_generated_data_conforms_to_generated_shapes(world):
    import pyshacl

    m, data = world
    quads = [
        *await fact_quads(m, data),
        *await person_quads(m, data),
    ]
    target = Graph().parse(data=serialise(quads, "ttl"), format="turtle")
    shapes = Graph().parse(data=serialise(shape_quads(), "ttl"), format="turtle")
    conforms, _, report = pyshacl.validate(target, shacl_graph=shapes)
    assert conforms, report


async def test_shapes_refuse_a_wrong_value(world):
    import pyshacl

    m, data = world
    quads = list(convert(await m.Fact.get(data.fact.id)))
    target = Graph().parse(data=serialise(quads, "ttl"), format="turtle")
    from rdflib import URIRef

    item = (await m.Fact.get(data.fact.id)).items[0]
    target.remove(
        (
            URIRef(item_uri(m.Stmt, item.id).value),
            URIRef(property_uri(m.Stmt, "text").value),
            None,
        )
    )
    shapes = Graph().parse(data=serialise(shape_quads(), "ttl"), format="turtle")
    conforms, _, _ = pyshacl.validate(target, shacl_graph=shapes)
    assert not conforms


async def test_everything_used_is_in_the_ontology(world):
    m, data = world
    quads = [
        *await fact_quads(m, data),
        *await person_quads(m, data),
    ]
    ontology = list(ontology_quads())
    defined = {q.subject for q in ontology}
    project = ontology_url()
    for q in quads:
        if q.predicate.value.startswith(project):
            assert q.predicate in defined, q.predicate
        if q.predicate == RDF_TYPE and q.object.value.startswith(project):
            assert q.object in defined, q.object


async def test_the_context_compacts(world):
    m, data = world
    quads = await fact_quads(m, data)
    text = serialise(quads, "jsonld", context=jsonld_context())
    assert "Stmt.text" in text
    json.loads(text)


@pytest_asyncio.fixture(loop_scope="session")
async def client(world):
    from pangloss_api import create_app
    from pangloss_rdf import api

    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


async def test_the_route_chooses_a_format(client, world):
    m, data = world
    path = f"/api/rdf/Fact/{data.fact.id}"
    assert (await client.get(path)).headers["content-type"].startswith("text/turtle")
    trig = await client.get(path, headers={"Accept": "application/trig"})
    assert trig.headers["content-type"].startswith("application/trig")
    assert (
        (await client.get(f"{path}?format=nt"))
        .headers["content-type"]
        .startswith("application/n-triples")
    )
    assert (await client.get(f"{path}?format=nope")).status_code == 422


async def test_view_is_plain_text_for_a_tab(client, world):
    m, data = world
    response = await client.get(f"/api/rdf/Fact/{data.fact.id}?view=true")
    assert response.headers["content-type"].startswith("text/plain")


async def test_a_document_read_at_a_parent_goes_to_its_own_address(client, world):
    m, _ = world
    sealed = await m.Sealed(label="x", items=[]).save()
    response = await client.get(f"/api/rdf/Fact/{sealed.id}?format=nt")
    assert response.status_code == 301
    assert response.headers["location"] == f"/api/rdf/Sealed/{sealed.id}?format=nt"


async def test_an_entity_at_a_class_it_no_longer_is_redirects(client, world):
    m, data = world
    response = await client.get(f"/api/rdf/Group/{data.person.id}")
    assert response.status_code == 301
    assert response.headers["location"] == f"/api/rdf/Person/{data.person.id}"
    gone = await client.get(f"/api/rdf/RemovedClass/{data.person.id}")
    assert gone.status_code == 301


async def test_what_is_not_there_is_a_404(client):
    assert (await client.get(f"/api/rdf/Fact/{uuid4()}")).status_code == 404


async def test_the_ontology_shapes_context_and_dataset_routes(client):
    assert "owl:Class" in (await client.get("/api/rdf/ontology")).text
    assert "sh:NodeShape" in (await client.get("/api/rdf/ontology?part=shapes")).text
    assert "@context" in (await client.get("/api/rdf/ontology?part=context")).json()
    assert "void:Dataset" in (await client.get("/api/rdf")).text


async def test_the_dump_has_each_head_once(world, tmp_path):
    m, data = world
    path = tmp_path / "data.nq.gz"
    result = await dump(path)
    assert result.items == 2
    with gzip.open(path, "rt", encoding="utf-8") as read:
        text = read.read()
    fact = item_uri(m.Fact, data.fact.id).value
    graph = Dataset(default_union=True).parse(data=text, format="nquads")
    assert len(graph) > 10
    assert f"<{fact}> ." in text
    person = item_uri(m.Person, data.person.id).value
    assert f"<{person}> ." in text
    assert "referencedBy" not in text


def harvested_models():
    class Harvested(Entity):
        _usage_meta = Usage(include_only_when_referenced=True)

    class Everything(Harvested):
        _rdf_meta = RDFMeta(dump="all")

    class Note(Document):
        cites: list[Harvested]

    initialise()
    return Harvested, Everything, Note


async def make_harvested():
    Harvested, Everything, Note = harvested_models()
    cited = await Harvested(label="cited").save()
    unused = await Harvested(label="unused").save()
    kept = await Everything(label="kept").save()
    note = await Note(
        label="note", cites=[{"type": "Harvested", "id": str(cited.id)}]
    ).save()
    return SimpleNamespace(
        Harvested=Harvested,
        Everything=Everything,
        Note=Note,
        cited=cited,
        unused=unused,
        kept=kept,
        note=note,
    )


async def dumped(path, **options):
    await dump(path, **options)
    return path.read_text()


async def test_a_class_that_include_only_when_referenced_is_dumped_where_it_is_used(
    clear_database, tmp_path
):
    h = await make_harvested()
    text = await dumped(tmp_path / "data.nq")
    assert f"<{item_uri(h.Harvested, h.cited.id).value}> ." in text
    assert item_uri(h.Harvested, h.unused.id).value not in text
    # (the project has the last word)
    assert f"<{item_uri(h.Everything, h.kept.id).value}> ." in text


async def test_the_dump_can_be_told_to_have_what_is_unused(clear_database, tmp_path):
    h = await make_harvested()
    text = await dumped(tmp_path / "data.nq", include_unused=True)
    assert f"<{item_uri(h.Harvested, h.unused.id).value}> ." in text


async def test_an_item_left_out_of_the_dump_still_has_its_export(clear_database):
    h = await make_harvested()
    assert await item_quads(h.Harvested, h.unused.id) is not None


async def test_what_only_an_unpublished_document_cites_is_only_in_a_dump_of_those(
    clear_database, db_driver, backend_under_test, tmp_path
):
    h = await make_harvested()
    db_driver.execute_query(
        "MATCH (n {id: $id}) SET n.published = false",
        id=str(h.note.id),
        database_=backend_under_test.database,
    )
    cited = item_uri(h.Harvested, h.cited.id).value
    assert cited not in await dumped(tmp_path / "public.nq")
    assert cited in await dumped(tmp_path / "all.nq", include_unpublished=True)
    see_unpublished.set(True)


async def test_excluding_a_class(clear_database):
    class Secret(Entity):
        _rdf_meta = RDFMeta(exclude=True)

    class Public(Entity):
        pass

    class Note(Document):
        secret: Secret
        public: Public

    initialise()
    secret = await Secret(label="s").save()
    public = await Public(label="p").save()
    note = await Note(
        label="n",
        secret={"type": "Secret", "id": str(secret.id)},
        public={"type": "Public", "id": str(public.id)},
    ).save()
    quads = list(convert(await Note.get(note.id)))
    assert not triples(quads, None, property_uri(Note, "secret"))
    assert triples(quads, None, property_uri(Note, "public"))


async def test_what_is_not_published_is_only_for_those_who_may_see_it(
    world, client, db_driver, backend_under_test, tmp_path
):
    m, data = world
    db_driver.execute_query(
        "MATCH (n {id: $id}) SET n.published = false",
        id=str(data.fact.id),
        database_=backend_under_test.database,
    )
    assert (await client.get(f"/api/rdf/Fact/{data.fact.id}")).status_code == 404
    fact = item_uri(m.Fact, data.fact.id).value

    path = tmp_path / "public.nq"
    await dump(path)
    assert f"<{fact}> ." not in path.read_text()

    path = tmp_path / "all.nq"
    await dump(path, include_unpublished=True)
    assert f"<{fact}> ." in path.read_text()
    see_unpublished.set(True)


async def test_a_uri_leads_to_the_item(client, world):
    m, data = world
    uri = item_uri(m.Fact, data.fact.id).value
    response = await client.get(
        uri.removeprefix("http://test.com"),
        headers={"Accept": "application/n-triples"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/n-triples")
    assert f"<{uri}>" in response.text
