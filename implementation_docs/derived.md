# Derived relations ✅

`pangloss-derived` (built 2026-11-02): **rules** that make new facts from what documents say, kept up to date by a
worker in the background. Most factoids speak of one person at a time ("X was a member of family A"); a rule makes the
relations between people that follow ("X and Y are of the same family"), so that a network grows as data is added.
Nobody writes a derived fact: it is computed, it carries its evidence ("why"), and it can be dropped and rebuilt at any
time. Why it is built as it is, what it does not do and what was measured are at the end of this page; the
guide is [guide/derived](../guide/derived/README.md).

## Installing

Add `"pangloss_derived"` to `INSTALLED_APPS`, before the apps whose rules it reads, and run `pangloss migrate` (the
package ships `migrations/0001_initial.py`: the keys of facts and justifications; the core ships the queue of pending
work, `pangloss_memgraph` 0007 / `pangloss_neo4j` 0005). It needs a backend that runs Cypher (`requires = {"cypher"}`).

## Declaring: `<app>/derived.py`

```python
from pangloss_derived import DerivedEdge, Object, RuleType, Subject, SymmetricLabel, Var, rule

from demo_app.models import Agent, Group, MemberOf, Person

family = RuleType("family", "Ties of family and of membership")


class SameGroup(DerivedEdge):
    """Members of the same group"""

    _meta = DerivedEdge.Meta(symmetric=True)

    first: Annotated[Person, SymmetricLabel("member")]     # the two ends, in either order
    second: Annotated[Person, SymmetricLabel("member")]
    group: Group                                          # a qualifier: part of what the edge is


class GaveTo(DerivedEdge):
    """Gave something to"""

    giver: Annotated[Agent, Subject()]
    receiver: Annotated[Agent, Object(reverse_name="received_from")]


@rule(types=[family])
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    """Two people said (perhaps by different sources) to be members of one group"""
    return SameGroup.Derive(first=a, second=b, group=group).when(
        MemberOf.Where(member=a, group=group),
        MemberOf.Where(member=b, group=group),
    )
```

- **A `DerivedEdge` class** is what can be derived: an edge between two entities, qualified by its other fields.
  (Until 2026-11-17 it was `Derived`, an n-ary fact of which `Meta(ends=...)` chose two fields for the graph. That is
  gone, with `reverse_names`: [derived-edges-and-documents.md](derived-edges-and-documents.md).)
  - **Exactly two ends**, each an entity class or a trait of entities. An asymmetric edge marks one field `Subject()`
    and one `Object()`; `Object(reverse_name="received_from")` names the edge as read from its object. A symmetric
    edge (`Meta(symmetric=True)`) marks its two ends with the same `SymmetricLabel("member")`: their own names
    (`first`, `second`) mean nothing to a reader, and the label is the one name the interface gives both. It is stored
    once, with its ends in order of id, and never relates a thing to itself. `initialise()` refuses a class without
    exactly two ends, and says what it found.
  - **Every other field is a qualifier**: a relation to an entity (`group: Group`) or a literal (`year: int`). No
    documents, embedded objects or lists. Qualifiers define the edge: two people in two groups have two `SameGroup`
    edges.
  - **`PerJustification()`** marks a literal that does not define the edge: it is a value of each justification (a
    probability found on the way), kept on the justification (`values`) and shown with it. One edge between A and B
    can have a justification at 80 and one at 60. There are no aggregates.
  - `Meta`: `symmetric`, `max_per_seed` (10,000: the most justifications one written document may give; past it none
    of them is written, and it is counted), `abstract` (a parent, which may leave the ends to its subclasses).
  - A field cannot have a name of the stored edge or of its view (`type`, `ends`, `qualifiers`, `plain`, anything
    starting `pg_`...). `subject` and `object` are free, since the stored names are `pg_subject` and `pg_object`.
  - `DerivedEdge.named("GaveTo")` gives a class by its name (for one no module declares).
- **Translations:** each concrete derived class goes in its app's `translations/models.jsonc` as a model does (`pangloss
  interface translations generate`): its name, its description (the docstring), its fields (the two ends of a symmetric
  class as the one `SymmetricLabel`), and the `reverse_name` of its object as an incoming name.
- **A rule** is a function whose parameters are its variables (`a: Var[Person]`), giving `Class.Derive(...)` (the head)
  `.when(...)` (the body). The body is patterns, each a model's `Where`, with a variable where a value or an entity would
  be: a variable used twice joins. Every `Where` has `is_` (the node itself), so two patterns can be about one node:
  `Activity.Where(is_=act, participants=a), Activity.Where(is_=act, participants=b)`. Anything a search can say is
  there too, as a condition (`HoldsOffice.Where(person=a, year=Compare(gt=1400))`).
- **Constraints** after the patterns: `distinct(a, b)`, `same(a, b)`, `same_document(s1, s2)`, `lt`, `lte`, `gt`, `gte`,
  `between`, and `y > 1400` on a literal variable. No negation across documents (decided), no recursion, no aggregates.
- **A variable of a list field** (`Person.Where(is_=a, aliases=name)` with `name: Var[str]`) is one of its items: two
  people with an alias in common.
- **Dates** (`pangloss_dates.rules`): a variable of a date (`d: Var[Date]`, or of a family, `Var[JulianDate]`) stands for
  the date of a field, and `overlaps(d1, d2)`, `before(d1, d2)`, `after`, `during(d1, d2)` and `within(d1, d2, days=365)`
  compare two by their bounds (day numbers, so the calendars may differ). They take the **fuzzy** bounds (allowing for
  doubt: "about 1500" reaches into 1499 and 1501) unless `strict=True`; so `overlaps` and `within` are generous by
  default (the dates might overlap) and `before` and `during` cautious (before even allowing for doubt). A variable that
  is not a date is refused at `initialise()`.
- **A symmetric class whose body is not symmetric** (`before(d1, d2)` between the two ends: who held office *first*)
  works as it reads: `initialise()` sees whether the body is the same with the two ends swapped; if it is, each pair is
  matched once; if not, both orders are matched and the fact is written with its ends in order of id.
- **Types of rule** (`RuleType`): a tag any number of rules can have, whatever their class. The facts of the rules of a
  type are one graph: `pangloss derive graph family`.
- `initialise()` imports `derived.py`, calls each rule once with its variables, and checks it: a variable of the wrong
  class, one in no pattern, one inside `any_of_`/`not_`, a constraint on an unbound variable, are errors that name the
  rule, the pattern and the field. A variable used only once is warned of.
- **Type stubs**: `pangloss make-stubs` writes `derived.pyi` too; a type checker then refuses `MemberOf.Where(member=g)`
  for a `Var[Group]`, and `SameGroup.Derive(group=p)` for a `Var[Place]` (`Var` is covariant: a `Var[Person]` is a
  `Var[Agent]`).

## An edge declared on a document class: `DerivesEdge`

Most of a network comes from one document at a time: "the giver of a transfer gave to its receiver", "everyone who
took part in an activity, with everyone else". Such an edge is declared on the document class, with no class or rule
written out:

```python
from pangloss_derived import DerivesEdge, RuleType

exchange = RuleType("exchange", "What passed between agents")   # in the models' module, or one it imports


class Transfer(Statement):
    _derives = [
        DerivesEdge("GaveTo", subject="given_by", object="given_to", reverse_name="received_from",
                    types=[exchange]),
    ]
    given_by: Agent
    given_to: Agent


class Activity(Statement):
    _derives = [DerivesEdge("CoParticipants", subject="participants", object="participants", symmetric=True)]
    participants: list[Agent | InRole[Agent]]
```

When the models are initialised each becomes **an ordinary `DerivedEdge` class and an ordinary rule**
(`pangloss_derived/derives.py`), so everything on this page holds of it. For `Transfer` it is the same as writing

```python
class GaveTo(DerivedEdge):
    given_by: Annotated[Agent, Subject()]
    given_to: Annotated[Agent, Object(reverse_name="received_from")]

@rule(types=[exchange])
def Transfer__GaveTo(a: Var[Agent], b: Var[Agent]):
    return GaveTo.Derive(given_by=a, given_to=b).when(Transfer.Where(given_by=a, given_to=b))
```

and the edge it stores is the same one (its key is of the class's name, its ends and its qualifiers).

- **`subject`, `object`**: fields of the document that are relations to entities. A field through a reified relation,
  a conjunction or a space is seen through as a rule sees through it; a list field gives each item, and two list
  fields every pair. A field that can also hold a document (an unreconciled mention) gives edges of its entities
  only. The class of an end is the nearest class or trait that everything the field can reach shares (`Person` and
  `Group` are `Agent`s; `Entity` if they share nothing of the project's).
- **The same field as both ends** needs `symmetric=True`: each two of its items, once, and never a thing with
  itself. Its ends are called `first` and `second`, and their one name in the interface is `label=` (by default the
  field's name). A symmetric edge of two different fields (`husband`, `wife`) matches both orders and is stored once.
- **`ends=("giver", "receiver")`** names the two ends on the edge; by default they have the fields' names. They have to
  be given when **several document classes give one edge** from fields of different names, the usual case for a
  network: `Transfer` (`given_by`, `given_to`) and `Sale` (`seller`, `buyer`) both declare `DerivesEdge("GaveTo", ...,
  ends=("giver", "receiver"))`. That is one class and a rule for each document class. The declarations of one name
  must agree on `ends`, `symmetric`, `reverse_name`, `label`, `max_per_seed` and the names of their qualifiers (their
  fields and `types` may differ); the class of each end is the nearest that the fields of all of them share.
- **`qualifiers={"year": "year", "at": "place"}`**: a name on the edge, and the field of the document it is read
  from (a literal, or a relation to an entity). They define the edge, as any qualifier. A document with no value for
  one gives no edge.
- **One edge for each pair** and set of qualifiers, whatever the number of documents: each document is a
  justification, and their count is the edge's `weight` in a graph.
- **`types=`**: the `RuleType`s of its rule. They are declared in the models' module or one it imports, not in
  `derived.py`, which imports the models.
- **Subclasses.** `_derives` is a meta slot (the one that is not called `_x_meta`: it is a declaration, not
  settings), so a subclass has its parent's list. But only the class that declares it gets a rule: the rule's pattern
  matches the subclasses already. A subclass may declare its own, more particular edges. An abstract class may
  declare for its subclasses.
- **The class** is `DerivedEdge.named("GaveTo")`. Once the models are initialised it is also an attribute of the
  module of its (first) document class, and `pangloss make-stubs` writes it in that module's stub, so `from
  my_app.models import GaveTo` type-checks and `GaveTo.list(...)` is known. The rule is called
  `<DocumentClass>__<Edge>` (`Transfer__GaveTo`).
- **With `derived.py`.** The declared edges are made before the apps' `derived.py` are read, so a rule written there
  can feed one (`DerivedEdge.named("GaveTo").Derive(...)`). `derived.py` stays for what joins several documents. A
  declared edge with the name of a class written there is refused.
- **Refused**, naming the class and the declaration (`Transfer._derives, GaveTo: ...`): a field there is not (with
  those there are), an end that is not a relation to entities, a declaration on an entity class, one name twice on
  one class, declarations that disagree. What a declaration cannot be whatever its class (one field as both ends
  without `symmetric`, a `reverse_name` on a symmetric edge, a qualifier called as an end) is refused where it is
  written. `pangloss check`, and so the language server, reports these at the class.

Not done: completion of the field names inside `DerivesEdge(...)` in the language server.

## `DerivedFrom[T]`

`sources: list[DerivedFrom[Factoid]]` is a citation that does not protect what it cites
(`class DerivedFrom[Target](Cites[Target]): protect = False`): the field a derived document keeps its sources in.
What the core does with such a citation is in [entity-identity.md](entity-identity.md#as-built-citations-that-do-not-protect-and-cited-bases-2026-11-17-).

## Derived documents ✅ (2026-11-17; conversion and the interface 2026-11-18)

A rule can derive a **document** in place of an edge: "A and B were children of P" in two factoids gives a factoid
that says "A and B were siblings", whose sources are those two. Steps 6 and 7 of
[derived-edges-and-documents.md](derived-edges-and-documents.md) are built: the class, the templates, every check
that `initialise()` makes, and [the worker writing the documents](#the-worker-writes-them-2026-11-17). Not built:
their page in the interface and converting one into a document of one's own (step 8).

```python
from pangloss_derived import DerivedDocument, DerivedDocumentMeta, DerivedFrom


class DerivedFactoid(Document, DerivedDocument):
    """What follows from what other factoids say"""

    sources: list[DerivedFrom[Factoid]]       # filled by the worker: the documents its justification rests on
    statements: list[Statement]
```

```python
@rule(types=[family])
def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
    """Two children of one parent are siblings"""
    return DerivedFactoid.Derive(
        label="Siblings",
        statements=[Sibling.Template(label="Siblings", people=[a, b])],
    ).when(
        ChildOf.Where(child=a, parent=p),
        ChildOf.Where(child=b, parent=p),
        unordered(a, b),
    )
```

**The class** (`pangloss_derived.documents`). A derived document class is a document class with the trait
`DerivedDocument` and one field `list[DerivedFrom[...]]`. One without the other is refused (a `DerivedFrom` on a
class people write; the trait with no field, with two, or with a single one), as is `create_directly=False`. An
abstract parent may leave the field to its subclasses.

- The trait carries two `DBField`s, `derived_by` (the rule) and `derived_context` (the labels of what the
  justification passed through). They are filled on `CreateDB`/`UpdateDB` from what the worker says it is writing
  for (`with writing_derived(rule, context, id=, published=, content=):`). They are in every `ReferenceView` (so in lists and search results)
  and in `Where` (`DerivedFactoid.Where(derived_by=Text(exists=True))` is "derived"). They are not in the `HeadView`.
- `_derived_document_meta = DerivedDocumentMeta(max_per_seed=2000, converts_to=Factoid)` is optional.
  `converts_to` is checked and kept; nothing converts yet (step 8).
- **Nobody writes one but the worker.** A create, update, delete or undelete outside `writing_derived` raises
  `PanglossDerivedDocumentError` (a `PanglossWriteError`: 400) in the transaction of the write, through
  `hooks.in_write`. A restore of a version (`pangloss-history`) is an update, so it is refused too. The class has no
  `POST` route, and the export says `createDirectly: false`, both through the new general hook
  `hooks.not_written_by_people` (`hooks.written_by_people(model)`).
- **Never reviewed.** A `ReviewMeta(reviewable=True)` that the class has from a parent (`AbstractFactoid`) is turned
  off for it; one it declares itself is refused. `pangloss-review` is not imported for this.

**Templates** (`pangloss_derived.templates`). `initialise()` gives a `Template` to every class a derived document
can hold (documents and their subclasses, embedded objects, wrappers by their class without parameters, edge models),
and a `Derive` to each derived document class: its template without the `DerivedFrom` field, with `.when(...)`. A
project with no derived document class gets none. A template has the fields of the class's `Create` but its
citations; one of a subclass is a subclass of its parent's.

| A field of | takes |
|---|---|
| a literal | a value, or a `Var` of its type; a list of them |
| a relation to an entity | a `Var` of an entity, a reference (`{"type", "id"}` or a `ReferenceSet`), or `Via(a, Certainty.Template(certainty=p))` where the edge has properties |
| a relation to a document | the `Template` of a concrete class it takes |
| a wrapper | its `Template` (`InRole.Template(target=[a], role="heir")`, `Negative.Template(contents=[...])`), checked as the class it is with its parameters where it is used |
| an embedded object | its `Template` |
| a citation | nothing: a list of them is written empty, and a class with one that must be given cannot be in a derived document |

When validated a field takes anything; the check is `TemplateCheck`, at `initialise()`, which names the rule and the
place (`Rule made: DerivedFactoid.statements[0].people[1]: takes Either, InRole, Person: the variable 'where' can be
a Place`). The stubs have the real types. What is refused: a variable of a class the relation does not take (every
concrete class the variable can be must be taken: declare `Var[Person]`, not `Var[Agent]`, for a field of `Person`,
or give the variable a pattern of its own), a value where an entity goes and the reverse, a value that does not
validate (as the `Create` field validates it), a class the field does not take, an abstract class, a relation whose
edge has properties that must be given and no `Via`, a variable of a matched document (it is part of the document it
was found in), a variable for a whole embedded object, a variable that is not the rule's, or that no pattern binds.
A rule of documents with no pattern of a document is refused: it would have no source.

The checked template is data (`TNode`, `TVar`, `TValue`, `TRef`, `TVia`): it is in the rule's hash, `explain` prints
it, and `templates.fill(node, bindings)` gives the payload of one document (what `Create` validates). The hash of a
rule of edges is unchanged by all this.

**The checks between rules** (`check.initialise_rules`).

- **No loop.** The graph has an edge from rule A to rule B when a pattern of B (the node of a top-level pattern that
  is not an entity) is of a class, or a parent of a class, of a node A's template writes. A cycle is refused, naming
  the rules and classes, with the way out. It is worked out from the template, not from the document's class, so
  `siblings` (reads `ChildOf`, writes `Sibling`) does not feed itself. It is by the class of the top-level pattern
  only: `AbstractFactoid.Where(statements=ChildOf.Where(...))` counts as reading any derived factoid.
  `DerivedRegistry.order` is every rule with readers after writers, and `DerivedRegistry.readers` says who reads
  each rule of documents; the worker uses both.
- **`block=` takes a document class**: `.when(..., block=[DerivedFactoid])` reads nothing inside a document of the
  class (`AND NOT hd:DerivedFactoid` on the head of each pattern's node), for a rule of edges as well. Such a rule
  is not a reader of the rules that write that class. `block` and `allow` now refuse what is neither a wrapper nor
  (for `block`) a document class.
- **Sources.** A rule is refused if a pattern of it can be found in a head document that the `DerivedFrom` field
  does not take. The heads a pattern can be in: the concrete classes people write, with `create_directly`, that can
  hold a node of its class; and the derived class of each rule that feeds it. So a statement class that can be a
  document of its own trips it: the refusal names the three ways out (widen the field, `block=[ChildOf]`,
  `create_directly=False` on the class). A rule that reads derived factoids needs
  `DerivedFrom[Factoid | DerivedFactoid]`, which a class can say of itself.
- **`unordered(a, b)`** matches each pair once (`a.id < b.id`), in any rule. It is refused where the body is not the
  same with the two swapped, and a rule of documents whose body is the same with two variables of its template
  swapped, and does not say it, is warned that it derives each document twice. (`distinct`, `same` and `unordered`
  now count as the same in either order when a body is compared with itself swapped, so a symmetric rule of edges
  with `distinct(a, b)` is matched once and not twice.)
- **What a document is derived through.** A wrapper that qualifies (a semantic space; `WeightedAlternative` and
  `IdentificationByToolchain` of the library) is blocked for a rule of documents unless the rule says
  `allow=[Negative]`; then it is in the justification's `context_labels`, to be written as `derived_context`.

**Where they are kept.** `DerivedRegistry.documents` (not `checked`, the rules of edges; `all_checked()` is both).
A rule of documents has `CheckedRule.template`, `head` (each variable of the template, by name), `tops`,
`max_per_seed`, `blocked_heads`, `unordered`. `store.Found.add` makes of each row one justification with no fact, in
`Found.documents`: its key is the rule, the nodes of its patterns and the values of its variables; `values` are the
bindings and `sources` the head documents of its patterns (not the entities). `GET /api/derived` lists these rules
with `"document": true`. `DerivedRegistry.triggers` has the places of both kinds of rule.

### The worker writes them (2026-11-17)

`pangloss_derived.written`. One document for each justification.

    (:PGJustification {key, rule, rule_hash, types, nodes, values, context, context_labels, generation,
                       document_id, document_type, sources})-[:evidence]->(head)

Such a justification justifies no fact (`document_id` is what tells the two kinds apart in every query). The work
is in two parts:

1. **Finding**, with the facts, in the same batch (`written.store_found`, after `store.write_found`): the new
   justifications are written, those with evidence in the batch that were not found are deleted, and the id of each
   document concerned is left pending (`pangloss_cypher.pending`, where the "head" is the document's id): kind
   `derive-retractions` for one whose justification is gone, `derive-documents` for one to make or to look at again
   (every justification found again: what it rests on may have been published, or its own context changed). The
   mark is in the transaction that wrote or deleted the justification.
2. **Reconciling** (`written.reconcile`, from `Worker.write_documents`): each pending document is made what its
   justification says. No justification: deleted. One, and no document: made. Deleted: undeleted. What would be
   written differs: updated. Only whether it is published differs: that alone is set. Otherwise nothing.
   `Worker.drain` does a batch of facts, then up to `Settings.documents` (25) documents, retractions first, and
   again until nothing is left: so a rule that gives a thousand documents holds no fact back, and what no longer
   holds goes before anything is made.

- **Through the ordinary writes** (`Create.save()`, `Update.save()`, `delete`, `undelete`), as the user `derived`
  (`DERIVED_USER`; made when first needed, as the Zotero sync's), inside `writing_derived`. So a label, history, the
  text index and pending marks follow as for any document.
- **Its id is made once and stored**: a UUID5 of the justification's key and the class (`written.document_id`), kept
  on the justification. **Taken over**: when, in one batch, one justification of a rule and a set of pattern nodes is
  gone and one is new (a value changed: an entity merged, a statement edited with its id kept), the new one has the
  document, which is updated in place. Not when several share their nodes. An id that another justification holds
  (it took it over) is not given twice: the key's second id is used.
- **The ids of its nodes are worked out** (`documents.node_id`: a UUID5 of the document's id and the path,
  `statements/0`, `statements/0/people/1`, `sources/0`), by the trait's `create_validator`/`update_validator`. So a
  document written again has the nodes it had, and a rule that read them keeps its justifications.
- **Written only when it differs.** The head keeps a hash of what was written (`pg_derived_content`: the rule, the
  payload, the context), put there in the write's transaction with `published` through
  `hooks.new_head_properties` / `updated_head_properties`. A rebuild, or a source saved as it was, writes nothing
  and adds no version. One exception: a merge of entities rewrites the relation itself (a version by whoever
  merged), and the worker then writes the document once more.
- **Published as what it rests on is**: every source published, or not. A change of only that is
  `set_published_in_db` (no version). A source checked with `pangloss-review` leaves `derive` work (the core marks
  the head on a change of status), so the document follows it.
- **Context is inherited**: `derived_context` is the justification's labels with those of each derived document it
  rests on.
- **Chains.** A document written is a write: it leaves `derive` work if a rule reads what its rule writes
  (`DerivedRegistry.readers`; otherwise nothing), and the reader is run in a later batch. Its sources are the
  derived documents it read. Retraction goes step by step.
- **A document that cannot be written**: something it rests on or names is gone (`left_out`: the write that removed
  it left the work that settles it); or its class refuses what the template gives (`failed`: logged, not tried
  again until its sources are written or the rule is built).
- **Rules are built in order** (`Worker.sync_rules`, `derive rebuild`): `DerivedRegistry.order`, and the documents
  of a rule are written before the next rule is built. A rule whose hash changed keeps the keys it finds again, so
  its documents are updated in place; one that derives another class gets new documents. A removed rule's documents
  are deleted. A renamed rule is another rule.
- `max_per_seed` (2,000) is the cap for one written document, as for facts.

**Citing one** (`pangloss_derived.citing`). A class with the trait asks for the core's cited basis
(`citations.enable_cited_basis()`, when the class is declared: a project with no derived document class is as it
was). A citation of a derived document, or of a node inside one, is saved as a `PGCitedBasis`
(`hooks.resolve_citation`): citations of the nodes its justification matched, a derived document among them
replaced by what it rests on, with `via` the derived **document** (also when a statement in it was chosen:
`ResolvedCitation.via`). A citation of one with no justification is refused. When the worker updates, deletes or
undeletes the document, its bases are marked `changed`, `lost`, or cleared, in that write's transaction
(`hooks.in_write` → `citations.mark_via`).

**An entity only derived documents name is not "referred to"** (`hooks.references_not_counted`): not in the count of
its uses, not in a list of what is used, and it can be deleted.

**In the core, for this** (general; conformance tests `test_published_without_review.py`, `test_citations_basis.py`):

| | |
|---|---|
| A change of review status marks the head | `review.set_review_status` → `pending.mark_written`, in its transaction; `hooks.work_marked` is told after (a worker wakes) |
| `set_published_in_db(cls, id, published)` | sets `published` alone, for a class that is not reviewed: no review status, so not in the queue; marks the head as above. (The plan called this `hooks.set_visibility`; it is an operation of the backend) |
| `hooks.references_not_counted` | classes whose references do not count: `fragments.counted`, in `uses_of` and the check before a delete |
| `hooks.work_marked` | told of a head marked by something that is not a write |
| `ResolvedCitation.via` | what a basis records as chosen, when it is not what the citation named |

**Seen.** `derive status` and `GET /api/derived/status` say how many documents wait (to write, to delete, the oldest)
and how many each rule has; `derive rebuild` writes a rule's documents before it ends and says what it did. The
migration `0002_documents` adds the index on `PGJustification.document_id`.

**Not built**: the page in the interface and conversion (step 8); a review task for a document that cites through a
lost derivation (`hooks.citation_marked` tells, nothing listens yet); an index on `derived_by` (a class says
`Document.Meta(indexes=["derived_by"])` if it searches by it much); RDF and similarity defaults; `Template` of a
copied embedded object (a date matched by a pattern cannot be put in a template as a variable). Not measured at
scale (step 10).

### Made a document of someone's own (2026-11-18)

"Make this a document of my own" (`pangloss_derived/convert.py`): the derived document itself changes class, in place
(`Target.Update(...).save(changing_class_from=DerivedFactoid)`, which the core now does for a head document as for an
entity). Same id, same history; the versions written by `derived`, then the person's.

- **Which classes**: `DerivedDocumentMeta(converts_to=...)`; with none, the concrete classes people write that share
  a parent class with it (`convert.targets_of`).
- **What carries over**: the fields of the same name in both classes (not the `DerivedFrom` field, not the trait's).
  `GET /api/derived/convert/{Type}/{id}/{To}` gives the target's form filled in (`initial`, `version`, the sources);
  `POST /api/derived/convert` `{model, id, to, version, data}` writes it. Nothing is written before that.
- **Adopted.** In the transaction of that write the justification is marked `adopted` (`adopted_by`, `adopted_at`).
  The worker never writes that id again (`reconcile_one` leaves a document whose class is not a derived one), makes
  no new document for the same match, does not count it in `written`, and never deletes the justification: through a
  rebuild, a changed rule, and the removal of the rule. One that takes it over (an entity merged) is adopted as it was.
- **`lost`.** When the rule no longer finds an adopted justification it is marked `lost`, and the citations made
  through the document are marked `lost` as for any other; found again, both are cleared. The document is not touched.
  `pending_status()` has `converted` (per rule: `converted`, `lost`) and `lost` (the documents, up to 100).
- **`derived_by` and `derived_context` stay on the head** (D19), through later updates: `hooks.kept_head_properties`.
- **Why.** `GET /api/derived/document/{Type}/{id}` (`why.py`): the rule, the sources the reader may see (and how many
  not), the context, `converted`, `holds`, `convertsTo`. 404 for a document no rule made.

In the interface (the package's module): a section on a document's page ("Derived", or "Made from a derivation" with
"the derivation it was made from no longer holds"), with the sources as chips and, for someone logged in, *Make it my
own: Factoid*, which opens `/derived/convert/:type/:id/:to`: the target's form, filled in, saved through the route
above (`ItemFormProps.sendBy`, new). A derived document has no Edit, Delete or New (`writtenByPeople: false` in the
export; `canEdit` in core), and `/Type/{id}/edit` says why.

Not built: the sources put into a `Cites` field of the target; the review task for a converted document; clearing
`derived_context` by the author; the restore of a version from before the conversion is refused by history as for any
class change ("was a DerivedFactoid"); the form's display of a `PGCitedBasis` and of `PGUnprotectedCitation` as chips;
"Derived from this" on a source's page; the search form's derived / not derived filter.

## Keeping it up to date

- A write (create, update, delete, undelete, and a merge of entities) of a head whose class can contain a node a rule's
  pattern matches leaves it **pending**, in the write's own transaction: a `(:PGPending {key, kind, head_id, token})`
  node. A write that triggers no rule writes nothing more. (Generic, in the core: `hooks.pending_work`.)
- The **worker** (a background task of the server; or `pangloss derive worker` with `DERIVED_WORKER_IN_SERVER = False`)
  claims a batch (200), finds every justification a node of those heads is in (one seeded query per place of each rule,
  for the whole batch), writes what is new and deletes what is not found again, in short transactions, then completes
  the claims whose token is unchanged. A head written again meanwhile is done again. One worker works at a time (a 30 s
  lease); a write wakes it.
- **Exact**: a churn of creates, updates, deletes and undeletes run with the worker, then every rule built again from
  scratch, found nothing missing and nothing stale (see the measurements).
- A **deleted or unpublished** document hides what only it justifies at once (the read rule `fragments.derived_visible`),
  before the worker has run.
- A **rule that changes** (its hash: the body, the class, the types, what the wrappers do) is built again when the worker
  starts; one removed has its facts deleted. After a **bulk load** (which marks nothing), `pangloss derive rebuild`.

## Reading

| | |
|-|-|
| `await SameGroup.list(entity=smith)` | a page of the edges the reader sees, about an entity (at an end or as a qualifier; `at=["giver"]`: only at these fields) |
| `await SameGroup.list(SameGroup.Where(group=g, plain=True))` | by an end or a qualifier, `plain`, `context_label`, `rule_type`. An end of a symmetric class matches either end: `SameGroup.Where(first=b)` is every edge b is in |
| `await SameGroup.list(evidence=factoid)` | the edges a head document is evidence of |
| `Person.search(Person.Where(derived_=GaveTo.Where(receiver=b)))` | the entities with such an edge (`$derived` in the JSON of a search; a filter, as above). An end the filter gives is the *other* end: those who gave to b, not b |
| `await SameGroup.get(id)` | one, with its justifications: the rule, the evidence documents, the context, and its `values` (the `PerJustification()` fields) |
| `await pangloss_derived.graph("family")` | the edges of the rules of a type: `source` (the subject), `target` (the object), `attributes` (the qualifiers), `justifications` and `weight` (how many justifications, under the name graph tools look for) |
| `GET /api/derived` | the classes (their `ends`, `reverseName`, `qualifiers`, `perJustification`, and the `role` of each field), the rules (as Datalog) and the types |
| `GET /api/derived/{Class}?entity=…&page=2` | a page (or `evidence=` a document; `at=giver` with `entity`; an end or a qualifier as a parameter, and `plain`, `context_label`, `rule_type`) |
| `GET /api/derived/{Class}/{id}` | one, with "why" |
| `GET /api/derived/graph/{type}?plain=true` | the graph of a type |
| `GET /api/derived/status` | what is pending, the state of each rule, what the worker did |
| `GET /api/Person/{id}` | has `_derived` (below). Not with `?extras=false` |
| `GET /api/derived/about/{Type}/{id}` | the same `_derived` on its own, for a reader that read the view without it (`{Type}`: the item's own class); `{}` when nothing is derived about it |
| `GET /api/Factoid/{id}` | has `_derived` only of facts with a field that points at the document, not what it is evidence of (that is what it says itself; `list(evidence=...)` gives it) |

**An edge's view** has its two ends as fields of their own names, and the rest under `qualifiers`:

```json
{"type": "GaveTo", "id": "…", "ends": ["giver", "receiver"], "symmetric": false,
 "giver": {"id": "…", "type": "Person", "label": "A"}, "receiver": {"id": "…", "type": "Person", "label": "B"},
 "qualifiers": {"year": 1500}, "plain": true, "qualifiedOnly": false, "contextLabels": [], "types": ["exchange"],
 "justificationCount": 2, "justifications": [{"rule": "gave_to", "values": {"amount": 80}, "evidence": […], …}]}
```

**`_derived` of an entity** has a section for each way it can be in the edges of a class (`read.sections_of`):

| Key | When | `role` |
|---|---|---|
| `GaveTo` | at an end. Of an asymmetric class whose object has a `reverse_name`: at the subject only | `ends`, or `subject` |
| `received_from` | at the object of a class with that `reverse_name` | `object` |
| `SameGroup:group` | as a qualifier (a group, of the edges between its members): one for each such field | `qualifier` |

Each has `type`, `role`, `as` (the fields the entity is at), `ends`, `symmetric`, `symmetricLabel`, `reverseName`,
`count`, and `items`: a first page of 25. A row has the other end (`other`, `otherField`) and the qualifiers
(`fields`); read from a qualifier, which is at neither end, it has both ends (`ends`) instead. The pages after the
first are `/api/derived/{Class}?entity=…&at=<the fields of "as">&page=2`.

The same functions work through the SDK (they ask the API; blocking with `connect(sync=True)`, as the models' own
are). The interface shows what is derived under an item's contents, a page at a time, with "why" on demand: the "Derived" section is
the interface module of `pangloss_derived` (`itemSections.Derived`), so a project can leave it out, or put its own in its place, with
`InterfaceConfig(disabled=["pangloss_derived:Derived"])` ([interface-features.md#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived](interface-features.md#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived)). The section shows
the item's `_derived` if the item came with it, and otherwise reads `/api/derived/about/{Type}/{id}` itself, in the section's own
boundary (the item's page reads the item with `?extras=false`, so that it is on show before what is derived about it has been found;
the section appears after what refers to the item, never before it).

## Commands

`pangloss derive explain [rule] [--queries]` (the rule as Datalog, what triggers it, the join order from each place),
`dry-run [rule]` (how many facts, or documents, the seeds that give most, nothing written), `rebuild [rule]` (rules
in order; the documents of a rule of documents are written before it ends), `status` (also the derived documents
that wait, and how many each rule has),
`graph TYPE [--plain-only] [--csv] [--graphml]` (the CSV's last column is `weight`), `worker`.

**Exports.** `graph TYPE --graphml`, and `GET /api/derived/graph/{type}?format=graphml`, give GraphML
(`pangloss_derived.export.graphml`), which Gephi, Cytoscape and networkx read: each entity at an end once as a node
(label, type), each edge from its subject to its object (undirected if its class is symmetric; a graph of both kinds
is directed, and its symmetric edges say `directed="false"`), with `class`, `weight`, `justifications`, `plain`,
`context` (labels joined by `|`) and each qualifier (a value; or an entity's label, with its id as `<name>_id`).
As RDF, with `pangloss-rdf`: `pangloss rdf dump --include-derived` ([rdf.md](rdf.md#a-packages-own-rdf-)).

## Storage

`(:PGDerived:SameGroup {key, type, pg_subject, pg_object, ...literal qualifiers})-[:first]->(person)` and so on (an
edge to each end and to each qualifier that is an entity, by the name of its field), and `(:PGJustification {key,
rule, types, nodes, values, context, context_labels})-[:justifies]->(fact)` with `-[:evidence]->` to the head node of
each document used. The node says which two fields are its ends (`pg_subject`, `pg_object`), so a reading needs no
class to know them. An edge is a node, not a relationship, because justifications point at it (who may see it is
worked out from them) and because a qualifier that is an entity stays a link (a merge moves it, its page lists the
edges it qualifies). Its key is a hash of its class, its ends and its qualifiers; a justification's, of its rule, its
edge, its nodes and its own `values`. Nothing is written
from an entity or into a document's tree. About 2.6 KB of Memgraph's memory per fact (measured).

## Why it is built this way

Condensed from the implementation plan (2026-11-02), which is in the history of the repository
(`docs/derived-implementation.md`, before 2026-11-10) with every worked example.

### Decisions (the user's, 2026-11-02)

1. **The point is person-to-person networks**, stored, derived from factoids that each speak of one person, as data
   is added. So pairs are stored, and fan-out is guarded, not designed away.
2. **A rule is Datalog written in Python**: typed parameters are the variables (`Var[Person]`), the body is a list of
   the generated `Where` patterns, and a variable used in two patterns joins them.
3. **Rules see through every semantic space, identification and wrapper**, and what was passed through is recorded
   on the justification and summed up on the fact. The context does not make another fact: one fact for each tuple,
   with its justifications, plain and qualified.
4. **What a space does to a derivation is the project's to say** (`DerivedMeta(derivation="qualify" | "block" |
   "transparent")`, `qualify` by default), since spaces mean what a project wants.
5. **A derived fact is one node connecting entities.** A graph of plain edges is a collapse of them, made when
   wanted (`pangloss derive graph`).
6. **Apart in the API and on the page**: under `_derived`, so that nothing derived is taken for what a document says.
   A head document has `_derived` only for facts with a field that points at it. (The plan had it show what it is
   evidence of; as built that is asked for, `list(evidence=...)`, since it is what the document itself says.)
7. **Unpublished evidence**: derive from everything not deleted, and hide on reading what rests only on what the
   reader cannot see. So a deleted or unpublished document hides what it justifies at once, before the worker has
   caught up.
8. **No negation across documents.**
9. `max_per_seed` is 10,000 by default.

### Other ways of writing a rule, and why not

| Way | Why not |
|---|---|
| A Cypher-like path builder (`match(a).from_(…).to(…)`) | Needs a typed descriptor for every field, and a pattern that is a star, not a path, has to be broken into paths with shared variables anyway |
| Prolog or Datalog text | The meaning is exactly right, but it is a second language: its own parser, no completion or type checking. Kept as a way of **showing** a rule (`explain`) |
| Cypher with the triggers listed by hand | Nothing is checked, the triggers are only as right as the list, the engine cannot seed the query from a written document, and visibility and spaces are missed unless written in. Possible later as an escape hatch |
| Python functions over loaded documents | Every join is a round of queries; the engine cannot tell what a rule reads, so not which writes make it stale; retraction is the developer's problem |

### How it differs from the first plan

- **What is pending is a queue of nodes, not a property of the head node.** An update replaces the properties of a
  head node, and a delete does not change its version, so neither could carry the mark. `(:PGPending {key, kind,
  head_id, token, claimed_until})` is `MERGE`d by the write in its own transaction with a new random token; the
  worker claims with a lease and deletes a node only if its token is the one it claimed, so a head written again
  while it was worked on is done again. It is general: `pangloss_models.hooks.pending_work`.
- **One worker at a time** (a lease, `PGWorkerLease`). With one, the work is exact: each head is processed after its
  last write, and that processing reads the data as it then is, so when the writes stop every justification has
  been found or removed by the last processing of one of its heads. With two, a justification read by one before a
  document changed could be written after the other had removed it.
- **`Derived` classes are not models of the registry** (`DerivedRegistry`): no `Create`, not migrated, exported or
  listed. `initialise()` calls the package once the models are made (`ModelRegistry.after_finalise`).
- **`Var` is in `pangloss_models.search`**; the JSON form is `{"$var": "a"}`. A search refuses a variable; a rule
  refuses one inside `any_of_` or `not_` (Datalog would need two rules).
- **`_derived` is filled by the API** (`hooks.head_view_extras`), not by the models: `Person.get` in Python does not
  carry it, and nothing is added to the generated classes or the TypeScript types.
- **A symmetric class whose body is not symmetric.** Matching each pair once with `a.id < b.id` is right only if the
  body is the same with the ends swapped; `before(d1, d2)` between them is not. `initialise()` compares the body
  with its ends swapped: if the same, `a.id < b.id`; if not, `a <> b`, the fact written with its ends in order of
  id, and the two rows that are one proof made one justification.

### What it does not do

- **Recursion**: a derived class in the body of another rule (transitive closure, "colleague of a colleague"). It
  needs the rules ordered in strata, a fixpoint, and "delete and derive again".
- **Aggregates** (counts, a `min` of certainties in the head) and **paths of unknown length**.
- **Freezing** a derived fact into a document that asserts it: write the document by hand.
- Rules written in the interface or stored in the database.
- `$derived` is not in the interface's search form (it is for the API and Python).

### Cost and its guards

A write that triggers nothing costs a dictionary lookup; one that triggers costs a `MERGE` in its transaction. The
cost is **the pairs**: a pair rule through a shared node is quadratic in its members (a family of 50 is 1,225 facts;
an office added to an organisation with 1,000 office-holders is up to 500,000). Most writes add one member, which is
linear. The guards: `max_per_seed` (past it that seed's rows are dropped, what the head justified before is kept,
and `status` and the log say so) and `pangloss derive dry-run` before a rule is switched on.

## Measured

2026-11-02, on the scratch Memgraph (3.14.0): 642,551 nodes (60,000 people, 15,000 groups, 30,000 factoids), from
Python through the models, one process, a laptop.

| What | Result |
|---|---|
| The pending mark on a save | 0.1 to 0.9 ms (median save 11.7 against 11.6 ms). A class no rule is about writes nothing |
| The worker draining 5,000 factoids | 902 heads/s in batches of 200; about 5,000 justifications/s when the groups are full |
| From a save to its derivations, four writers and the worker in one process | median 291 ms, p95 444 ms, max 963 ms; never more than 23 heads pending. Saves were slower with the worker running: median 40.7 against 36.2 ms |
| Exactness | After 3,000 creates, updates, deletes and undeletes by four writers into shared groups, a rebuild from scratch found nothing new and nothing to remove (twice) |
| Rebuilds | `gave_to` 23,605 facts in 3.2 s; `co_participants` 18,372 facts in 5.5 s; `same_group` over 37,651 memberships in 21 s; one that changes nothing, 2.5 s |
| Fan-out | A group of 400 built 20 at a time: 115 ms for the first 20, rising to 1,364 ms for the last (79,800 pairs). One more member: 108 ms |
| Memory, Python | Nothing grows: the worker's RSS rose 0.2 MB over 25 batches. The process is large for another reason: `initialise()` of the demo's models took 1.32 GB |
| Memory, database | 209,380 facts and 301,246 justifications: 0.53 GiB, about 2.6 KB a fact |
| Neo4j (2026.10.1, 118,173 nodes of the same kind) | mark +0.4 ms; 626 heads/s; lag median 308 ms, p95 1.0 s; everything right there too |

What measuring found and changed (traps for anyone writing such queries):

- Deleting stale justifications with `j.key IN $found` was planned from every justification for each head: 4.1 s a
  batch. Read the keys from the head, compare in Python, delete by key: 0.12 s.
- Memgraph planned a seeded query's `MATCH`es as one pattern and began with every `MemberOf` for each seed (354 ms).
  **`WITH *` between clauses keeps the order chosen**: 8 ms.
- A batch written as one transaction (15 s at worst) made saves of the same people wait, and was itself retried
  until the driver gave up. Writes of 500 justifications a transaction, and a worker that backs off and halves its
  batch, ended both.
- A lease of 120 s left by a stopped process held the next worker back that long: now 30 s, and given up on stopping.
- **`Var[X]` in the unions of every `Where` field cost 440 MB at `initialise()`.** A bare `Var` is validated;
  `Var[X]` is only in the stubs.
