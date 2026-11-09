# Exporting as RDF

`pangloss-rdf` publishes your data as linked data. Every document and entity can be read as RDF, the whole database can
be written to one file, and an ontology describing your project is made from its models. You can also say what your
classes mean in another ontology, such as CIDOC-CRM.

It only reads. Your database stays as it is, and installing the package needs no migration.

- [Getting started](#getting-started)
- [What the data looks like](#what-the-data-looks-like)
- [Addresses](#addresses)
- [Getting the data](#getting-the-data)
- [The ontology, shapes and context](#the-ontology-shapes-and-context)
- [Renaming and leaving things out](#renaming-and-leaving-things-out)
- [Saying what a class means in CIDOC-CRM](#saying-what-a-class-means-in-cidoc-crm)
- [Making the URIs resolve](#making-the-uris-resolve)
- [Querying the data](#querying-the-data)
- [RDF for a package's own models](#rdf-for-a-packages-own-models)
- [Before you publish](#before-you-publish)
- [All the settings](#all-the-settings)
- [What is not there yet](#what-is-not-there-yet)

## Getting started

Add the app, and rebuild the interface so that its menu appears:

```python
INSTALLED_APPS: list[str] = [
    # ...
    "pangloss_rdf",
]
ENTITY_BASE_URL: AnyHttpUrl = AnyHttpUrl("https://example.com/entity/")
RDF_PREFIX: str = "demo"
```

`ENTITY_BASE_URL` is what your URIs start with. **Choose it with care: URIs are meant to be permanent once anyone has
used them.** `RDF_PREFIX` is the short name of your terms in the output; without it, one is made from `PROJECT_NAME`.

Then check that everything has a good name:

```sh
pangloss rdf check
```

The console of every item page now has a menu with the RDF formats and **API JSON**, the item as the API gives it. (It
takes the place of the View as JSON button.)

## What the data looks like

Take these models:

```python
class Certainty(EdgeModel):
    level: int


class Person(Entity):
    pass


class Meeting(Document):
    place_name: str
    led_by: ViaEdge[Person, Certainty]


class Negative[T](SemanticSpace[T]):
    pass


class Report(Document):
    says: list[Meeting | Negative[Meeting]]
```

A `Report` says one meeting happened, and another did not. This is part of what it becomes (the ids are shortened):

```turtle
<https://example.com/entity/Report/0190> {

    <https://example.com/entity/Report/0190> a demo:Report, core:Document ;
        rdfs:label "A report" ;
        demo:Report.says <https://example.com/entity/Meeting/0191>,
                         <https://example.com/entity/Negative/0192> ;
        core:edge <https://example.com/entity/Report/0190/edge/Report.says/0>,
                  <https://example.com/entity/Report/0190/edge/Report.says/1> .

    # The meeting that happened
    <https://example.com/entity/Meeting/0191> a demo:Meeting, core:Document ;
        rdfs:label "It happened" ;
        demo:Meeting.placeName "Innsbruck" ;
        demo:Meeting.ledBy <https://example.com/entity/Person/0188> ;
        core:edge <https://example.com/entity/Meeting/0191/edge/Meeting.ledBy/0> ;
        core:partOf <https://example.com/entity/Report/0190> .

    # The same relation again, as a thing that can have properties
    <https://example.com/entity/Meeting/0191/edge/Meeting.ledBy/0> a core:Edge ;
        rdf:subject   <https://example.com/entity/Meeting/0191> ;
        rdf:predicate demo:Meeting.ledBy ;
        rdf:object    <https://example.com/entity/Person/0188> ;
        core:position 0 ;
        demo:Certainty.level 3 .

    # The meeting that did not happen: no direct demo:Meeting.ledBy
    <https://example.com/entity/Meeting/0193> a demo:Meeting, core:Document ;
        rdfs:label "It did not" ;
        demo:Meeting.placeName "Innsbruck" ;
        core:inSpace <https://example.com/entity/Negative/0192> ;
        core:edge <https://example.com/entity/Meeting/0193/edge/Meeting.ledBy/0> ;
        core:partOf <https://example.com/entity/Report/0190> .

    # An entity it mentions: only what a chip shows
    <https://example.com/entity/Person/0188> a demo:Person ;
        rdfs:label "Maximilian" .
}
```

The rules behind that:

**A head document or entity is a named graph.** Everything in it is what that document says. Who made it and when
(`dcterms:creator`, `dcterms:created`, `dcterms:contributor`, `dcterms:modified`, `core:version`) is said *about* the
graph, outside it. Turtle has no graphs, so a Turtle export puts it all together; use TriG or N-Quads to keep them apart.

**Every relation appears twice.** Once as a plain triple, so that simple queries are simple, and once as an **edge
node**, which holds what a triple cannot: the place in the list (`core:position`) and the fields of an `EdgeModel`.
`edge` links a subject to its edge nodes. Lists of relations keep their order this way.

**Inside a semantic space, nothing is asserted.** A node in `Negative`, `Hypothetical` or any other space keeps its
classes, its literal values and its edge nodes, and says `core:inSpace` for every space around it. The direct triples
are left out, as are outside classes and properties such as CIDOC-CRM's. Someone who reads the data naively does not
learn that a meeting took place when the source says it did not.

**An entity is only described in its own export.** A document that mentions a person gives only its class and label.
The person's own export has its fields, and what refers to it:

```turtle
<https://example.com/entity/Person/0188> a demo:Person, core:Entity ;
    rdfs:label "Maximilian" ;
    core:referenceCount 2 ;
    core:referencedBy <https://example.com/entity/Meeting/0191>,
                      <https://example.com/entity/Meeting/0193> .
```

`core:referencedBy` names the document holding the reference, which may be nested in another. It says nothing of what
that document claims.

How the other kinds of thing are written:

| In your model | In RDF |
|---|---|
| A field of text, a number, a date | One triple, with its XSD datatype (`xsd:integer`, `xsd:date`, `xsd:decimal`, a URL as `xsd:anyURI`...) |
| An enum or `Literal[...]` | Its value, as a literal |
| A list of literals | One triple for each: the order is lost (see `ordered=True` below) |
| An `Embedded` object | A node of its own, `{parent}/{Class.field}`, joined like a relation |
| An `AnnotatedValue` (`WithCertainty[str]`) | A node with `rdf:value` and its other fields |
| A `TypedDict` | A node of type `core:Map` |
| A `ReifiedRelation`, `SemanticSpace` or `Conjunction` | A node of its own, with its fields as relations |
| A generic (`InRole[Person]`, `InRole[Group]`) | One class, `demo:InRole` |
| An entity's URL id | `owl:sameAs` that URL |

Not exported: reverse relations (the ontology has `owl:inverseOf` instead), `DBField`s, what `pangloss-derived` derives,
past versions, and anything deleted.

A node has the classes its database node has: `demo:Meeting`, its parents and its traits.

## Addresses

| Thing | URI |
|---|---|
| A document, entity, reified relation or space | `{ENTITY_BASE_URL}/{Class}/{uuid}` |
| An embedded object, annotated value, `TypedDict` | `{parent}/{Class.field}`, and `/{n}` in a list |
| An edge node | `{subject}/edge/{Class.field}/{position}` |
| A class | `{RDF_ONTOLOGY_URL}{Class}` |
| A property | `{RDF_ONTOLOGY_URL}{Class.field}`, in camelCase |
| A structural term (`Edge`, `inSpace`...) | `{RDF_CORE_URL}{name}` |

A property belongs to the top-most class that has the field, so a subclass uses its parent's: `Activity` inherits
`demo:Statement.text`.

**What to cite.** The URI of a head document or entity lasts. If an entity changes class, its old address redirects to
the new one. The URI of an edge changes if its list is reordered, and a nested document may get a new id if an update
makes it anew, so cite the head.

## Getting the data

For one item:

```
GET /api/rdf/Person/{id}?format=ttl
```

| `format` | `Accept` | |
|---|---|---|
| `ttl` (the default) | `text/turtle` | Turtle: easy to read, no graphs |
| `trig` | `application/trig` | Turtle with graphs |
| `jsonld` | `application/ld+json` | JSON-LD |
| `nt` | `application/n-triples` | One triple to a line, no graphs |
| `nq` | `application/n-quads` | One quad to a line |

`?view=true` sends it as plain text, for a browser tab. A reader sees just what they would see at `GET /api/Person/{id}`:
something unpublished is a 404 to someone not logged in. Asked for at a parent class, an item redirects to its own.

For everything:

```sh
pangloss rdf dump -o data.nq.gz                     # N-Quads, compressed because of the name
pangloss rdf dump -o data.trig --format trig
pangloss rdf dump -o people.nq --types Person,Group
pangloss rdf dump -o all.nq --include-unpublished   # what a reader who is not logged in cannot see, too
pangloss rdf dump -o all.nq --include-unused        # also the items of a class dumped only where they are used
```

By default a dump has only what a reader who is not logged in can see. Each head is read once. An entity has no
`core:referencedBy` in a dump, since the documents are all in the file.

Some entities are brought in by the thousand and matter only where something refers to them: a Zotero library is the
example. Such a class says `_usage_meta = Usage(include_only_when_referenced=True)`, and a dump has only the items that
something refers to. The address of an item left out still works.

## The ontology, shapes and context

All three are made from your models, with no database:

```sh
pangloss rdf ontology -o ontology.ttl
pangloss rdf ontology --shapes -o shapes.ttl
pangloss rdf ontology --context -o context.jsonld
```

or at `GET /api/rdf/ontology`, with `?format=`, `?part=shapes` or `?part=context`.

- **The ontology** has every class with its parents and docstring, and every property with what it applies to and what
  it can hold. A narrowed field (`subclasses_parent_fields`) is an `rdfs:subPropertyOf`; a reverse name is an
  `owl:inverseOf`. `owl:versionInfo` is a hash of your models, so a reader can tell that they have changed.
- **Domains and ranges are `schema:domainIncludes` and `schema:rangeIncludes`**, because a relation to `Person | Group`
  has several ranges, and several `rdfs:range`s would mean something that is *both*.
- **The SHACL shapes** say what valid data looks like. Nothing in Pangloss needs them at run time: they are for whoever
  receives your data and wants to check it. Relations have no minimum count, as a direct triple is left out in a space.
- **The JSON-LD context** maps short names to URIs, for those who want to compact the JSON-LD. The API's JSON-LD uses
  only prefixes (`demo:Meeting.placeName`).

## Renaming and leaving things out

Names are made for you, and can be changed:

```python
from pangloss_rdf import RDFField, RDFMeta


class Person(Entity):
    _rdf_meta = RDFMeta(class_name="HistoricalPerson")

    known_as: Annotated[str, RDFField(name="appellation")]
    notes: Annotated[str, RDFField(exclude=True)]
    epithets: Annotated[list[str], RDFField(ordered=True, language="la")]
```

`RDFMeta` takes:

| | |
|---|---|
| `class_name` | The name in the class's URI and its items' URIs. **Not inherited**, or a subclass would have its parent's URI |
| `class_uri` | A whole URI, to use an outside class as this class itself |
| `exclude=True` | The class is not exported, nor any relation to it. Inherited |
| `dump="all"` or `"used"` | For an Entity: a dump has every item, or only those something refers to, whatever the class's `Usage` says. Inherited |

`RDFField` takes:

| | |
|---|---|
| `name` | The field's name in its URI |
| `uri` | A whole URI instead |
| `exclude=True` | Not exported |
| `language` | A language tag for text |
| `ordered=True` | A list of literals as an `rdf:List`, which keeps its order. Harder to query, so only where order means something |
| `parent` | A property of another ontology: see below |

Neither is data, so neither needs a migration. **But renaming changes published URIs**, so do it before you publish.

Two things with one URI are refused as the server starts, as is a class called `ontology`.

## Saying what a class means in CIDOC-CRM

Mix in the CRM class, and give a field its CRM property:

```python
from pangloss_rdf import RDFField
from pangloss_rdf.ontologies.crm import (
    E5_Event,
    E7_Activity,
    E21_Person,
    E39_Actor,
    E74_Group,
    P4_has_time_span,
    P14_carried_out_by,
)


class Agent(Trait, E39_Actor): ...


class Person(Entity, Agent, E21_Person): ...
class Group(Entity, Agent, E74_Group): ...


class Statement(Document, E5_Event):
    _meta = Document.Meta(abstract=True)

    when: Annotated[Date, RDFField(parent=P4_has_time_span)]


class Activity(Statement, E7_Activity):
    carried_out_by: Annotated[Agent, RDFField(parent=P14_carried_out_by)]
```

**The CRM classes are plain Python classes**, not traits or models. They add no label to the database and no model to
the interface, and adding or removing one needs no migration.

A relation cannot point at one of them, since Pangloss only knows its own kinds of model. For a relation to "any actor",
declare a trait and mix the CRM class into it, as `Agent` is above.

**Put the trait first, then the narrower class.** `class Person(Entity, E39_Actor, Agent)` is refused by Python itself
as the class is declared ("Cannot create a consistent method resolution order"; `ty` says so without running it),
because `E39_Actor` is named before something that has it.

What this gives:

- In the ontology: `demo:Person rdfs:subClassOf crm:E21_Person`, and `demo:Activity.carriedOutBy rdfs:subPropertyOf
  crm:P14_carried_out_by`.
- In the data, outside a semantic space: `a crm:E21_Person`, and a `crm:P14_carried_out_by` triple beside your own, so
  CRM queries work without a reasoner. The nearest CRM class is written, and the CRM's own file knows its parents.
- An aligned property reaches **through a reified relation** to what it is about: with `InRole[Agent]`, `P14` goes to the
  person and not to the role. Through a semantic space or a conjunction it writes nothing, as the value is not simply so.
- A date is an `E52_Time-Span` with `P82a` and `P82b`, so `P4_has_time_span` on a date field is all it needs.

`pangloss rdf check` warns of a class outside a property's domain or range. A warning is not an error: Pangloss models
often do not match the CRM exactly.

**One thing a reasoner will do.** The ontology says `demo:Activity rdfs:subClassOf crm:E7_Activity`, and a node in
a `Negative` is still `a demo:Activity`. A reasoner given both will infer that it is an `E7_Activity`. It gets no `P14`.

### Another ontology

Make a module from its RDFS or OWL file, and keep it with your code:

```sh
pangloss rdf generate-ontology frbroo.rdfs --prefix frbroo --title "FRBRoo" --out myapp/frbroo.py
```

`--prefix` is what it is called in the output (`frbroo:`). Classes keep the ontology's hierarchy, and a name that is not valid in Python is changed (`P4_has_time-span` becomes
`P4_has_time_span`). Its URI stays as it was. Deprecated terms are left out. Generating needs `rdflib`; using the module
does not, so your models still load in the SDK.

## Making the URIs resolve

A URI can also be an address. Ask for `https://example.com/entity/Person/0188` and you get a `303` redirect:

| Who is asking | Where to |
|---|---|
| A browser | The item's page at `RDF_HTML_URL`; the data as text if that is not set |
| Anything else (`curl`, a triple store) | `/api/rdf/Person/0188`, with the format it asked for |
| For an edge, or an embedded object | The item it is in |
| For anything under the ontology's address | The ontology |
| For `{ENTITY_BASE_URL}/dataset` | A description of the dataset |

"A browser" means an `Accept` header naming HTML above any RDF type.

These requests must reach the API, so:

1. Give `ENTITY_BASE_URL` a path of its own, such as `/entity/`. The root of a site belongs to the interface.
2. Set `RDF_HTML_URL` to where the interface is.
3. Run the interface with `pangloss interface serve --api-path /entity`, or send that path to the API in your reverse
   proxy. The development server reads `PANGLOSS_API_PATHS=/entity`.

```sh
curl -L -H 'Accept: text/turtle' https://example.com/entity/Person/0188
```

## Querying the data

Load a dump into any triple store. A direct triple answers the simple questions:

```sparql
PREFIX demo: <https://example.com/entity/ontology/>

# Who says that this person led a meeting?
SELECT ?source ?meeting WHERE {
  GRAPH ?source { ?meeting demo:Meeting.ledBy <https://example.com/entity/Person/0188> }
}
```

Go through the edge node for what is on the relation, and for what is inside a space:

```sparql
PREFIX demo: <https://example.com/entity/ontology/>
PREFIX core: <https://example.com/entity/ontology/core#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

# How sure each source is, leaving out what is negated or hypothetical
SELECT ?meeting ?level WHERE {
  GRAPH ?source {
    ?edge rdf:subject ?meeting ;
          rdf:predicate demo:Meeting.ledBy ;
          rdf:object <https://example.com/entity/Person/0188> ;
          demo:Certainty.level ?level .
    FILTER NOT EXISTS { ?meeting core:inSpace ?space }
  }
}
```

## RDF for a package's own models

An app can add to what is written for a class, in a module called `rdf.py`, which is found by name:

```python
# myapp/rdf.py
from pangloss_rdf import register_rdf_converter, to_literal
from pangloss_rdf.vocabulary import skos

from myapp.models import Office


def convert_office(value, uri, context):
    yield context.quad(uri, skos("prefLabel"), to_literal(value.label))


register_rdf_converter(Office, convert_office)
```

It is given the item as read, its URI and a `Context`. It applies to subclasses too. With `replace=True` it is written
instead of the class's fields. A view has no `DBField`s. **If `context.asserted` is false the node is in a semantic
space: leave out what would claim something.**

Dates, typologies and Zotero items do this already:

- A date has `core:earliest`, `core:earliestStrict`, `core:latestStrict` and `core:latest`, as `xsd:date` in the
  proleptic Gregorian calendar, whatever calendar it was entered in (its fields say that). A date with no known end has
  no end bounds.
- A type of a typology is a `skos:Concept`, with `skos:broader` to its supertype.
- A Zotero item has `dcterms` terms for its title, date, language, abstract and citation.

## Before you publish

- [ ] `ENTITY_BASE_URL` is the address you mean to keep, with a path of its own.
- [ ] Classes and fields have the names you want: a rename changes URIs.
- [ ] `pangloss rdf check` is clean, or you have read its warnings.
- [ ] `RDF_LICENSE` says what others may do with the data.
- [ ] `RDF_EXPOSE_USERS` is what you want: usernames are in the provenance by default.
- [ ] The URIs resolve (`curl -L` one).

## All the settings

All are optional but `ENTITY_BASE_URL`, which every project has.

| Setting | Default | |
|---|---|---|
| `ENTITY_BASE_URL` | | What item URIs start with |
| `RDF_PREFIX` | made from `PROJECT_NAME` | The short name of your terms in the output |
| `RDF_ONTOLOGY_URL` | `{ENTITY_BASE_URL}/ontology/` | Where your classes and properties are |
| `RDF_CORE_URL` | `{RDF_ONTOLOGY_URL}/core#` | The structural terms (`Edge`, `inSpace`...). By default your project's own; projects that want to be queried alike can share an address, where the terms must then be published |
| `RDF_CORE_PREFIX` | `core` | Their short name |
| `RDF_HTML_URL` | none | Where the interface is, for browsers following a URI |
| `RDF_EXPOSE_USERS` | `True` | Whether usernames are in the provenance |
| `RDF_REFERENCED_BY_LIMIT` | 1000 | `core:referencedBy` of an entity, per incoming field (no more than 500 are read of each) |
| `RDF_LICENSE`, `RDF_DUMP_URL` | none | In the description of the dataset |

## What is not there yet

- A class a node fulfils through `Fulfils` is not among its classes.
- The ontology's labels are not translated.
- `pangloss check` and the language server know of `RDFField` and `_rdf_meta` only what `initialise()` refuses.
- The dump reads one head at a time, and has not been measured on a very large database.

The design, and why it is as it is: [the plan](../../docs/rdf-export-plan.md). The reference: [RDF export](../../docs/rdf.md).
