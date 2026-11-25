# Modelling with Pangloss

How to declare models, what is generated from them, the shape of payloads, searching, and changing models that have
data. The full reference is `implementation_docs/models.md`, `implementation_docs/relations.md` and `implementation_docs/generated-models.md`; the best worked
example is `pangloss-demo/demo_app/models.py` (a factoid model that uses nearly every feature, with a table at its top
saying where), and `guide/tutorial/` builds an application step by step.

## Contents

- The kinds of model
- Fields
- Relations: what `Create` expects
- What is not supported
- Options: `_meta` and the slots of other packages
- The generated models and their methods
- Reading an entity: reverse relations
- Searching
- Changing models: migrations
- Modelling habits of this project

## The kinds of model

All are in `pangloss_models.model_bases.<module>`. Subclassing registers the class; `initialise()` generates.

| Kind | Is | Notes |
|---|---|---|
| `Document` | A unit of research data: a factoid, a statement, an order | Has a `label` (required unless `require_label=False`). Nests other documents. A head node when it is the top one |
| `Entity` | A real-world thing documents refer to: a person, a place, a source | Always a head node. Can be found by a URL as well as its id |
| `Embedded` | Structured data with no identity of its own: a date | A node, written and read with what holds it. One per field (no list, no optional) |
| `Trait`, `NonHeritableTrait` | A mixin, so a relation can say "any of these": `Agent` is a `Person` or a `Group` | Can carry fields and `after` validators. A heritable trait's name becomes a node label |
| `SemanticTrait`, `SemanticNonHeritableTrait` | A trait that means something as a class (`Agent`: "a person or a group"), not only a mixin (`Dateable`) | Stored exactly as `Trait`/`NonHeritableTrait` (same labels: changing one to the other is no migration). `model_is_semantic_trait`; a trait below one is semantic; the export lists them in `semanticTraits` beside `traits`. The core gives them no meaning; `pangloss-vectors`' class part makes each a class above those that have it |
| `EdgeModel` | Properties of a relation itself: certainty | Literal fields only. Used through `ViaEdge[Target, EdgeModel]` |
| `AnnotatedValue[T]` | A literal with extra literals bound to it: a name with its certainty | Stored as a map property, not a node. One per field |
| `ReifiedRelation[T]` | A relation that has fields: a person *in a role*, a source *at a page* | Generic over its `target`. No label. Written with what holds it. A field that names one takes the generic classes below it too (a generic `Finer` declared below `InRole`, in a field of `InRole[Person]`), as do a space and a conjunction |
| `ReifiedRelationDocument[T]` | The same with the life of a document (label, views, can be a head) | 🚧 |
| `SemanticSpace[T]` | A context that changes how its contents are read: `Negative`, `Hypothetical` | Payload `{"type": "Negative", "contents": [...]}`, never empty (`MinLen(1)` on every space's `contents`). Everything inside records the spaces it is in (`meta.semantic_spaces`), made from its path (`meta.path`: every node it is nested in). `SemanticSpace.Meta(veridical=, fit=, logical=, unary=, degree=)` says what it says of its contents (below) |
| `Conjunction` | A join of several things in named slots: `Causes[TCause, TResult]` | Generic |

Subclassing a declared class works: a relation to `Statement` accepts `Activity(Statement)`, and parent names are
node labels, so a list or search of the parent finds the subclasses. A read by a class gives an item as its own
subclass (`Statement.get(id)` of an `Activity` is an `Activity.HeadView`). Generic parameters are resolved at
initialisation and each use gets its own generated models. Docstrings of classes and fields become descriptions.

## Fields

`initialise()` puts every annotated field into one of these (`Model._meta.fields`):

| Annotation | Kind | Stored as |
|---|---|---|
| `str`, `int`, `float`, `bool`, `date`, `datetime`, `time`, `timedelta`, `Decimal`, `UUID`, the URL, email, IP and path types, `re.Pattern`, `Fraction`, an `Enum`, a `Literal[...]`, a `TypedDict`; `list`/`set`/`tuple` of these; any as `X \| None` | literal | A property of the node. `Decimal`, `UUID`, a URL and the like are strings (the export says the format). An enum is the member's *value* (so renaming a member changes nothing; changing its value is a migration). `None` is not written; falsy values (`0`, `""`, `[]`) are. The list of types is `pangloss_models.literals`; a package may add a codec |
| Another declared class, a union, a `list[...]` of them, a trait, a generic wrapper | relation | Nodes and edge pairs (below) |
| An `Embedded` class, or a union of them | embedded | A node, joined like a relation |
| An `AnnotatedValue[...]` | annotated value | A map property |
| `Annotated[T, DBField]` | database-side field | In `CreateDB`, not in `Create`: filled by a validator or `to_db`, not by the user |
| `Annotated[T, Computed()] = ...` | computed field (a literal, a list of them, or a relation to entities) | Read with the model (`View`, `HeadView`), in no `Create`, `Update` or database model: written by the backend's `set_computed` alone, with no new version. Must be able to be empty (a default, a list, or `X \| None`). A computed relation is no reference |

Everything in `Annotated` that pydantic acts on (`Ge(1)`, `MinLen`, `Predicate`, `StringConstraints`, `Strict`,
`Field(pattern=...)`, `AfterValidator`; so `PositiveInt`, `constr(...)` too) is carried to the generated models, the
export and so the interface's forms; anything else that is not Pangloss's own is an error. An optional one is written
either way: `Annotated[int, Ge(1)] | None` or `Annotated[int | None, Ge(1)]`. `pangloss_models.validators.SumsTo`
checks that an edge property adds up over a list. A default the class declares (`year: int = 0`) is carried: the
field may be left out.

Validators and methods (`implementation_docs/generated-models.md`, "Validators, write checks and methods"): pydantic's
`@model_validator`s and `@field_validator`s run once, on `Create`/`Update` (a `before` one gets snake_case keys);
`@create_validator` / `@update_validator` run on `CreateDB` / `UpdateDB` (server side: fill in `DBField`s there, as
`pangloss_dates` does); `async` `@before_create` / `@before_update(self, previous)` run on the server before a write, on
each node of the class in it (nested too), and may raise `PanglossWriteRefused(message, field=...)` (a 422). Each is given its own node; `whole_write()` is the head being written and `nodes_of(whole_write())` every part of it, for a check of several parts together. Methods and properties are copied to
every generated model but the references. A `@computed_field` or a `model_config` is a `PanglossModelWarning`.

## Relations: what `Create` expects

| The field's type | `Create` takes | Stored |
|---|---|---|
| An `Entity` | `{"type": "Person", "id": <uuid or URL>}` (`Person.ReferenceSet`) | An edge to the existing node |
| A `Document` | Its own `Create`, nested | A new node, belonging to the head |
| A `Trait` | Any concrete class that has it, told apart by `type` | As that class |
| `A \| B` | Either, told apart by `type` | |
| `list[...]` | A list | An edge per item |
| `ViaEdge[Person, Certainty]` | The reference plus `"edge_properties": {...}` | Properties on both edges |
| A reified relation, semantic space or conjunction | Its generated model (`target`, `contents`, or its slots) | A node of its own |

Each relation is two edges: `(a)-[:field]->(b)` and `(a)<-[:field_reverse {reverse: true}]-(b)`. The reverse name can
be set: `Annotated[Person, RelationConfig(reverse_name="is_subject_of")]`. A relation marked `KeepOnMerge()` (or the
library's `IdentityClaim()`) is left where it is when the entity it names is merged into another (`Person.merge`).
`Attribution(by="ordered_by", to="ordered_to")` on the field that holds a semantic space
(`Annotated[Ordered[Statement], Attribution(...)]`) names the fields that say whose attitude or act it is and whom it
is addressed to: each another relation of the class that reaches an entity, checked at `initialise()`, exported as
the field's `attribution`, not data; nothing reads it yet.
The library's `SameEntity[Person]` is a ready-made statement that two entities are one (its `target` is an
`IdentityClaim()`); an entity's page lists what it is said to be the same as. A relation's markers are exported to
the interface (`markers`), which asks what a marker says (`identityClaim`), not its name. Nothing reads through
these claims unless asked: `await pangloss_library.clusters.cluster(a)` is the entities joined to A by claims in
no semantic space (read from the graph each time, not stored or derived), and a search asks for any of them with
`Person.Where(same_as_=a)` (`$same_as`).

**A citation** is the one relation to a document that does not contain it: `evidence: list[Cites[Statement]]`
(`Cites[Note] | None`, `Cites[Note | Factoid]`). The payload is a reference, `{"type": "Birth", "id": "…"}`; what is
read is a `PGCitation` (`target_id`, `target_label`, `target_head_id`, `target_spaces`, `target_state`,
`changed_since_cited`), to be sent back as it is. The target must exist and be of an allowed class (422). A write
that changes a cited part raises `PanglossCitedError` (409) unless it says `acknowledge_citations` (`save(...)`, the
query parameter, or `with pangloss_models.citations.acknowledging("changes")`); one that removes it, or deletes its
document, is refused unless an admin says `"removals"`. `Document.Meta(cited_with=["source"])` names fields of the
head that count as part of each cited part. `Model.cited_by(id)` and `GET /api/NAME/{id}/cited` say who cites it.
A subclass with `bases = False` (`CitesShared[T]` of `pangloss-criteria`) never takes a cited basis, so its field is the same in every project.
A subclass of `Cites` with `protect = False` (`DerivedFrom[T]` of `pangloss-derived`) is a citation that protects
nothing and is never marked: its nodes are `PGUnprotectedCitation`s, listed with `/cited?unprotected=true`.
A document class with the trait `DerivedDocument` and one `list[DerivedFrom[...]]` is a **derived document class**
(`pangloss-derived`): a rule writes its documents (`DerivedFactoid.Derive(statements=[Sibling.Template(people=[a, b])])`,
`Template` being a `Create` that takes variables), nobody else can, and `initialise()` checks the rule. The worker
writes one document for each justification, as the user `derived`: deleted when the rule no longer matches,
undeleted when it does again, updated in place when only a value changed, published when all its sources are, and
not written when nothing changed. A citation of one is saved as citations of what it rests on (`PGCitedBasis`)
(`implementation_docs/derived.md`, "Derived documents").

`RelationConfig` also has `subclasses_parent_fields` (this relation stands for a field of a parent or fulfilled
class), `bind_to_child_field` (copy a value of the parent into nested children, so it is entered once; the child keeps
its own copy; its allowed and excluded types include the types below them, and its child fields reach the fields that
stand for them in narrower classes), `validators`, `description`, and `default_reified_type` (for the interface's form). `Fulfils[Other]`
lets one payload make a node that is also an `Other`, with its labels. See `implementation_docs/relations.md`.

## What is not supported

Each of these raises at `initialise()`:

- an optional list of relations (`list[Person] | None`): `list[Person]` may already be empty (a single relation or
  embedded object may be optional: `Person | None`, `Date | None`);
- a list of embedded objects (a list of annotated values, `list[WithCertainty[str]]`, is allowed: a list of maps; to
  give one certainty to a whole list, `WithCertainty[list[str]]`);
- a plain `dict` (use a `TypedDict`), `bytes`, `complex`, a pydantic model or dataclass (use an `Embedded` or a
  `TypedDict`), a `Flag` enum, a union of literal types, `list[X | None]`;
- a model called `users`, `docs`, `redoc`, `openapi.json` or `sdk`, in any case (the API uses those paths).

Check `implementation_docs/status.md` ("Not implemented") before telling a user that something cannot be done: this list shrinks.

## Options: `_meta` and the slots of other packages

`_meta = Document.Meta(...)` or `Entity.Meta(...)`. Most options are inherited; `abstract` and `indexes` are not;
`view_extra_fields` and `reference_view_extra_fields` accumulate.

| Option | Effect |
|---|---|
| `abstract=True` | Not a concrete type: read routes only, never created |
| `merge=MergeRules(label_into="aliases")` (entities) | Where the label of an entity merged into this one goes by default |
| `create_with_id=True` | The client may supply the `id` (with `create_new`) |
| `accept_url_as_id` | An http URL as the id (entities: on by default; the entity still gets a UUID, and the URL is kept as a unique node) |
| `create_inline=True` (entities; needs `create_with_id`) | A document's payload may name an entity that does not exist yet, to be made as its own head node. For batch uploads. Not "inline entities" |
| `create_directly=False` (documents) | Only ever part of another document: no `POST` route, `save()` refuses, no "New" button |
| `global_search=False` | Left out of "search everything" (the homepage's box); not inherited, not data |
| `require_label=False` | No label needed |
| `companions=[Companion(...)]` (entities) | Documents offered with a new one in the interface (a factoid of its naming), written with it in one transaction if filled in; `save_with_companions`, `POST /api/NAME/with-companions`; inherited; not data ([companion documents](../../../../implementation_docs/companion-documents.md)) |
| `label_template="Will of {testator}"` | The label worked out from what it holds, on the client and on every write, unless written by hand (`label_auto`); any kind, inherited; not data ([label templates](../../../../implementation_docs/label-templates.md)) |
| `indexes=["field"]` | A database index of the field, for searching by value. A change is a migration |
| `use_in_semantic_space_label=False` (documents) | Display only: the interface leaves a nested document of this class out of the trail of spaces and documents it shows round what is inside it. Storage does not read it: `meta.path` has every node a node is nested in ([semantic spaces](../../../../implementation_docs/semantic-spaces.md)) |

**A semantic space's options** (`SemanticSpace.Meta(...)`, `implementation_docs/semantic-spaces.md`, "What a space
says of its contents"), each inherited and settable anew, none data (no migration), exported on the model:
`veridical` (`1` asserted, `0` neither, `-1` denied; left out: `-1` for `"not"`, else `0`), `fit` (`"describes"` or
`"prescribes"`: an order, a wish), `logical` (`"not"`, or `Modal("necessity", "command", of_not=False)` /
`Modal("possibility", "epistemic")`: force, the project's own flavour word, compared as written), `unary` (left out:
true for `"not"` and a modal `of_not`; a unary space's `contents` takes one item, a second refused), `degree` (the
class's default degree of its contents, `"impossible"` to `"expected"`, only where `veridical` is `0`). Code reads
`_meta.veridicality` and `_meta.is_unary` (what holds), not the raw fields. `initialise()` refuses contradictions
(`logical="not"` with `veridical=1`; three quick fixes) and warns of flavours differing only in case. Several items
in a space that is not unary are read each by itself, never together (`Hypothetical` of A and B: A may be, B may
be); where that matters, one space per item. A degree entered on one space is a field of the class marked `Degree()`
(`how_likely: Annotated[DegreeStep | None, Degree()] = None`; one per class, only where `veridicality` is `0`),
written also into that space's entry of the path (`degree`; never the class's default). **The walk** reads them:
`pangloss_models.spaces.signature(node.meta.path)` gives a `Signature` (`veridical` 1/0/-1 of the node itself; where
0, its `lean` for/against/neither and a `degree`, the one entered on the innermost uncommitted space else its class's
default; `fit` and `prescribed_by`, the id of the node holding the innermost prescribing space; `force`, `flavour`),
after normalising each run of adjacent spaces (a double "not"; a "not" through a modality into its dual of the same
flavour; `of_not`). Pure, never stored; a statement between two spaces stops a "not" (`Not[Service(parts=[p])]` says
nothing of p, which `semantic_spaces` alone cannot tell). For many nodes pass `spaces.registered_spaces()` as the
second argument. Its cases are data, `pangloss-models/tests/space_cases.json`. No package follows the walk yet, and
the interface has no port of it (later phases of `implementation_docs/spaces-and-comparison-plan.md`).

Other packages keep their own settings on the class in **meta slots**, attributes named `_<name>_meta`:

| Slot | Package | For |
|---|---|---|
| `_interface_meta = InterfaceMeta(...)` | `pangloss_interface` | colour, navigation section, components that take over a page or card, `collapse`, `headless` |
| `_review_meta = ReviewMeta(reviewable=True)` | `pangloss_review` | Written unpublished until checked. On an entity, `ReviewMeta(allow_unreconciled=True)`: a relation to it also takes an `Unreconciled` (a mention not yet identified, part of the document; `NoUnreconciled()` on a field opts out) |
| `_criteria_meta = CriteriaMeta(allowed=True)` | `pangloss_criteria` | On an entity: a relation to it also takes a `MatchesCriteria` of it (someone described and not named: a stored search, its candidates computed), as if the annotation said `Person \| MatchesCriteria[Person]`; `NoCriteria()` on a field opts out. A migration of every field that takes the class |
| `_protect_meta = Protection(read_only=(...), delete_only_if=..., delete_refused=...)` | `pangloss_models.protection` | Fields the API will not let a person change; a package's own rule for deleting (a function giving the reason: 409, nothing marked; typology types use it) |
| `_usage_meta = Usage(include_only_when_referenced=True \| False \| function)` | `pangloss_models.usage` | Entities of interest only if something refers to them: a neutral fact that the interface's lists and the RDF dump follow |
| `_typology_meta = TypologyMeta(name=...)` | `pangloss_typology` | The name of a typology's generated entity |
| `_derived_meta = DerivedMeta(...)` | `pangloss_derived` | What a space or wrapper does to a derived relation, winning over the walk (`block`; `transparent`; `qualify`: read as a plain space). A space that says nothing is read by the walk: each justification gets a status (asserted, reported, prescribed, denied, reported_not, prescribed_not, nothing), a rule takes asserted, reported and prescribed unless `.when(..., status=[...])` says otherwise (a virtual class: `status=["denied"]`), and a fact's `status` is summed up (asserted, contested, reported, prescribed, denied, nothing: `status.summed`, the same in `store.SUMMARY_QUERY`); a reified relation or conjunction is read through (`implementation_docs/derived.md`, "Through semantic spaces") |
| `_derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to")]` | `pangloss_derived` | On a document class: a derived edge between the entities of two of its fields, with no class or rule written (the one slot not called `_x_meta`; only the class that declares it gets the rule, a subclass is matched by it) |
| `_zotero_meta` | `pangloss_zotero` | Which class a Zotero item becomes |
| `_rdf_meta = RDFMeta(class_name=..., class_uri=..., exclude=...)` | `pangloss_rdf` | A class in the RDF export. A name is not inherited |
| `_vectors_meta = VectorsMeta(searchable=True \| include=False)` | `pangloss_vectors` | A group "Similar" can be narrowed to, with a vector index for each profile (a migration); or no vectors at all |
| `_fastrp_meta = FastRPMeta(weight=, weights=, stop=, own=, include=)` | `pangloss_fastrp` | How a class counts in the joined graph of the graph part: weights, a wrapper that ends a chain (`Negative`), a class left out (`implementation_docs/fastrp.md`) |
| `_names_meta = NamesMeta(fields=["label"], include=True)` | `pangloss_names` | Which fields of a class are its names (`label`, text fields, `list[str]`): entities have their label by default, documents none (`implementation_docs/names.md`) |

A slot is inherited; a subclass's value replaces its parent's. A value of the wrong type is an error at the class.

## The generated models and their methods

| On the class | Is |
|---|---|
| `Create` | What a client sends to make one. `Statement(...)` is `Statement.Create(...)` |
| `Update` | A full replacement, with `id`; nested items are an `Update` (kept) or a `Create` (new) |
| `CreateDB`, `UpdateDB` | The same after ids, labels, spaces and database fields are filled in: what a backend takes |
| `View` | A nested item in a read |
| `HeadView` | A top-level read: fields, `meta`, and for an entity its reverse relations |
| `EditView` (entities) | A `HeadView` without reverse relations: what is sent back as an `Update` |
| `ReferenceSet` (entities) | `{type, id}`: how a payload points at one |
| `ReferenceView` | `{type, id, label, …}`: a summary, in lists and nested reads |
| `Where` | A typed search pattern |

After `initialise()`, on a `Document` or `Entity`, all async: `Create(...).save(detail=False)`,
`Update(id=..., ...).save()`, `get(id)` (`None` if there is none or it is deleted), `get_for_edit(id)`,
`list(search_terms=, page_number=, page_size=, deep_search=)`, `search(...)`, `autocomplete(...)` (entities),
`delete(id)`, `undelete(id)`. `save()` returns a `ReferenceView`, or the `HeadView` with `detail=True`.

A node's class is set when it is made. The one way to change it is an update of an **entity**, or of a head
**document**, as the new class (a document: everything in it is written again, what cites it must be acknowledged, and
a citing field that cannot hold the new class refuses it):
`Book.Update(id=..., ...).save(expected_version=v, changing_class_from=Plain)`. The node keeps its id, URLs and what
refers to it; the update is refused (`PanglossClassChangeError`) if it is not a `Plain`, or if a relation that refers
to it cannot hold a `Book`. Not over the API: a package's own route uses it (`pangloss-zotero`'s `base-on`).

A method that needs the database or anything a client lacks is marked `@server_only` (from `pangloss_models`), or
better kept in a module the models do not import, so that the models can be shipped in the SDK.

## Reading an entity: reverse relations

`Person.get(id)` has a field for each relation *to* the person, named `<field>_reverse` (or the `reverse_name`),
listing the documents that refer to it. Through a wrapper (a reified relation, space or conjunction) the document
comes with only the field that holds the chain of wrappers. A relation that a subclass narrows is listed only under
the narrower name. The table of cases is in `implementation_docs/models.md`, "Reading an entity".

## Searching

- `Model.list(search_terms=...)` / `GET /api/NAME?q=`: words in labels, through the text index; `deep` also finds
  what refers to what matches.
- `GET /api/autocomplete`: entities by label over a set of types.
- Structured search, `POST /api/search` and `Model.search(...)`: a JSON pattern of fields and conditions, nested
  through relations, with `$all`, `$any_of`, `$not`, `$any`, `$somewhere`, `$mentions`, `$spaces`, `$incoming` and
  `order_by`. `Model.Where` is the typed form of the same pattern. See `guide/search/README.md` and
  `implementation_docs/structured-search.md`.
- The way of a relation: `Rel(through=[Negative])` names wrappers it must pass through (in no order);
  `Through(WeightedAlternative, edge=Likelihood.Where(percent=Compare(gte=60)), where=...)` asks more of one (its own
  values, its own relations by id: `InRole.Where(role=baker)`, and the edge that leaves it);
  `Rel(edge=Certainty.Where(...))` is of the edge that reaches the target. `Rel(via=[Certainty.Where(...),
  InRole.Where(...)])` asks of the places of the way **in order**, whether stored on an edge or a node (also on
  `AnyRel` and `IncomingFrom`; `implementation_docs/structured-search.md`, "The way in order"). An edge says which edge
  model it is of (`pg_edge_model`), so a condition by `Certainty` is of `Certainty` edges alone; a wrapper named is
  that class or one below it. In a rule of
  `pangloss-derived` a field of a step or an edge can be a variable (`Likelihood.Where(percent=p)`), which a
  `PerJustification()` field of the edge can keep; `via` and a wrapper's own relation are refused there.

All of it works the same over the SDK.

## Changing models: migrations

Once there is data, a change to the models is applied with migrations, much as in Django:

```sh
pangloss makemigrations        # writes <app>/migrations/NNNN_name.py; asks what the models cannot say
pangloss migrate --dry-run     # what each change would do, in a transaction that is rolled back
pangloss migrate               # applies them, records them, then reads the affected data back
```

- A rename is **asked, not guessed**; the answers are kept in the migration file.
- Changes can be written by hand (`makemigrations --empty`, `RunCypher`, `RunPython`), undone
  (`migrate <app> <target>`), batched (`--batch-size`) and squashed.
- Indexes and constraints are migrations too, the library's own included.
- The API refuses to start with migrations pending or models changed since (`MIGRATION_CHECK`).
- A migration that has been applied anywhere is not edited: write another.

How to use them: `guide/migrations/README.md`. The design and what is built: `implementation_docs/migrations.md`.

## Modelling habits of this project

Drawn from the demo and `notes/modelling.md`; the user's own domain is prosopography (factoids about people in
historical sources).

- **A claim is a document; what it is about is an entity.** A `Factoid` is what a `Source` says, and holds
  `Statement`s; people, groups and places are entities the statements refer to. Uncertainty, negation and hearsay are
  data about the claim (edge properties, annotated values, semantic spaces), never changes to the entity.
- **Make the kinds of statement subclasses of an abstract base** (`Statement` → `Activity`, `Transfer`, `Order`), with
  `create_directly=False` if they only exist inside a factoid, and narrow the base's relations in the subclasses
  (`subclasses_parent_fields`) so a person's page lists each under its most exact name.
- **Use a trait where a relation should take several unrelated classes** (`Agent`), not a common base class.
- **Use a reified relation when a relation needs fields and a target** (`InRole[Agent]`, `AtPage[Source]`), an
  `EdgeModel` when it only needs a value or two (`ViaEdge[Agent, Certainty]`).
- **Controlled vocabularies that grow or have a hierarchy are a typology** (`pangloss-typology`), not an `Enum`. An
  enum is for a short fixed list.
- **Dates in sources are uncertain**: use `pangloss_dates` types (and the `Dateable` trait for something that happens
  at a time), not `datetime.date`, unless the date really is exact.
- Roles (a specific office, one of several holders, a generic role) are an open design question: read
  `notes/modelling.md` before proposing a model for them.
