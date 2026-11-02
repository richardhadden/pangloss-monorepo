# Derived relations: rules that make new facts from documents ⏳

A plan (2026-11-02). Nothing here is built. It is a design for declaring **rules** of the form "if documents say
*this* and *that*, then there is a derived relation between these things", and for keeping what the rules derive up to
date as documents are written, in the background. The questions were answered on 2026-11-02, in two rounds (see
[Decisions](#decisions-answered-2026-11-02)), and the plan below follows the answers. No question is open.

## What it is for

**Relational networks from factoids that speak of one person each.** Most factoids say something about one person: "X
is a member of family A", "Y held office O". As data is added, rules derive the **person-to-person relations** that
follow ("X and Y are members of the same family"), so that a network grows out of data that never states a relation
between two people. The pairs are the point, and they are stored.

The simplest example: "X is a member of family A" and "Y is a member of family A" (two factoids, perhaps from two
sources) give "X and Y are members of the same family". A longer one: "A held office X", "office X is part of
organisation Z", "B held office Y", "Y is part of Z" give "A and B worked for the same organisation". Nobody wrote
either, but they follow, and a researcher wants to see them on a person's page, search by them, and export the network.
When one is shown, it must say **why**: which rule, which documents (factoids) it came from, and in what context
(negated, hypothetical, an uncertain identification).

The pattern that links the two people has to be **arbitrary**: any number of documents, any relations, conditions on
fields, and on whether two things are the same or different.

Three principles from [the discussion of descriptions](../notes/descriptions-and-assertions.md) apply, and shape
everything below:

- **Only documents assert.** A derived relation is not a claim anybody made: it is computed, and always recomputable.
  It is never written by a user, never has a history, and is not part of any document.
- **It carries its evidence.** A derived relation exists while at least one *justification* holds: a rule, and the
  documents it matched. Delete or change a document, and what depended on it goes.
- **Asserted documents are data; derived facts are a cache.** They can be dropped and rebuilt at any time (after a
  migration, a change of a rule, a bulk load).

## Recommendation in short

- **A `derived.py` next to `models.py`**, imported by the server after the models, with two things in it:
  **`Derived` classes** (what can be derived: a relation with typed ends and, perhaps, values) and **rules** (how).
- **Rules are Datalog with a Python surface.** A rule is a *head* (a `Derived` class, with variables for its fields)
  and a *body*: a list of patterns, each the existing typed `Model.Where` of a model, in which a **variable** can stand
  where an entity, a document or a value would be. A variable used in two patterns joins them. This is the
  "variables across branches" that [structured search](structured-search.md#what-this-does-not-do-on-purpose-for-now)
  left for later; the body of a rule is a structured search with variables, so it is checked by `check_match` and
  compiled by the same compiler.
- **Variables are typed** (`Var[Person]`), declared as the parameters of the rule's function, so that a type checker
  and an editor know them, and the generated `Where` stubs say where each kind of variable may go
  (`person=a` is accepted only if `a` is a variable of a class the field allows).
- **Stored as one node connecting entities:** a `PGDerived` node per derived fact (`SameFamily` between X and Y, in
  family A), with edges *out* to the entities it relates, and one `PGJustification` node per way it was derived, with
  edges to the **head documents** it came from. No edge is written from an entity, and nothing points into a
  document's tree. A graph of plain edges, when one is wanted, is a collapse of these nodes (a query, or an export).
- **Rules see through everything** (semantic spaces, identifications, alternatives, reified relations), and record
  **what they passed through** on the justification and, summed up, on the fact (as `context_labels` does for a node
  in a semantic space now): "X and Y in the same family, *only from a negated statement*" is a fact with its context,
  not a fact left out.
- **Kept up to date incrementally, in the background.** At `initialise()`, each rule is analysed for which models can
  trigger it. A write of a head document marks it as *pending* (in the same transaction, so it cannot be lost) only if
  its class can contain a node that a rule's body matches. A background task takes pending heads in batches and, for
  each rule and each pattern of its body that the written document can match, runs the rule **seeded from the
  document's nodes** (the "delta" query of incremental Datalog): one indexed lookup, then joins outward. What the
  document no longer justifies is deleted; what is new is written; what is unchanged is not touched.
- **In the API and on the page, apart:** an entity's view has its derived facts under `_derived`, so that nothing
  derived is mistaken for something a document says.
- **Read with a visibility rule:** a derived fact is seen if one of its justifications is made only of documents the
  reader can see. So a deleted or unpublished document hides what it justifies at once, before the background task has
  caught up, and a *lens* (authors, sources) can later be the same test with more conditions.
- **Tools for a large model:** `pangloss derive explain` (the compiled query, the triggers, the join order),
  `dry-run` (how many facts a rule would make, and the worst seeds, before it is switched on), `rebuild`, `status`.

## Ways of writing a rule

Five were considered. The examples assume these models. The family one goes into the demo, where a family is already
a `Group` ("a family, an order, an army..."); the office one only into the test models, as the case of a longer chain:

```python
class MemberOf(Statement):       # "X is a member of family A" (nested in a Factoid)
    member: Person
    group: Group

class Office(Entity): ...
class Organisation(Entity): ...

class HoldsOffice(Statement):    # "A held office X" (nested in a Factoid)
    person: Person
    office: Office

class OfficeIn(Statement):       # "office X is part of organisation Z"
    office: Office
    organisation: Organisation
```

### A. Typed variables in the generated `Where` classes (recommended)

```python
# demo_app/derived.py
from pangloss_derived import Derived, Var, rule

from demo_app.models import Group, HoldsOffice, MemberOf, OfficeIn, Office, Organisation, Person


class SameFamily(Derived):
    """Members of the same family"""

    _meta = Derived.Meta(symmetric=True)

    first: Person
    second: Person
    family: Group


@rule
def same_family(a: Var[Person], b: Var[Person], family: Var[Group]):
    """Two people said (perhaps by different sources) to be members of one family"""
    return SameFamily.Derive(first=a, second=b, family=family).when(
        MemberOf.Where(member=a, group=family),
        MemberOf.Where(member=b, group=family),
    )


class SameOrganisation(Derived):
    """Held offices in the same organisation"""

    _meta = Derived.Meta(symmetric=True)

    first: Person
    second: Person
    organisation: Organisation


@rule
def same_organisation(
    a: Var[Person], b: Var[Person],
    office_a: Var[Office], office_b: Var[Office],
    org: Var[Organisation],
):
    """Two people who held offices of one organisation (perhaps not the same office)"""
    return SameOrganisation.Derive(first=a, second=b, organisation=org).when(
        HoldsOffice.Where(person=a, office=office_a),
        HoldsOffice.Where(person=b, office=office_b),
        OfficeIn.Where(office=office_a, organisation=org),
        OfficeIn.Where(office=office_b, organisation=org),
    )
```

- It is what a developer already writes for a search (`HoldsOffice.Where(...)`), with variables where the values were.
  Every condition a search has is there with no new syntax: `HoldsOffice.Where(person=a, year=Compare(lt=1500))`,
  `Rel(is_=a, through=[InRole])`, nested patterns, `any_of_`, `|`.
- **The type checker sees everything that can be seen**: the fields of each model (from the stubs that exist), the
  operators, and whether a variable fits a field. `HoldsOffice.Where(person=office_a)` is an error, because `person`
  takes a `Var[Person]`.
- **The parameters are the variables.** Their names are the names in error messages and in `explain`; their
  annotations are their types; the decorator makes them. A function also puts off building the body until the models
  are initialised (the `Where` classes do not exist when `derived.py` is imported: see below).
- The body is data, not code that runs: it has a JSON form (the search pattern's, with `{"$var": "a"}` where a variable
  is), so a rule can be hashed (to know when it changed), exported to the interface, and one day stored and written
  there (the descriptions of the notes: "the bishops Maximilian appointed" is a rule body with one free variable).

### B. A Cypher-like path builder

```python
match(a).from_(HoldsOffice.f.person).to(HoldsOffice.f.office, office_a).from_(OfficeIn.f.office)...
```

Reads like Cypher, but needs a typed descriptor for every field (another generated class per model), and a pattern
that is a star rather than a path (four statements around two people and one organisation) has to be broken into
several paths with shared variables anyway, which is A with more punctuation. Not recommended.

### C. A Prolog/Datalog text

```prolog
same_organisation(A, B, Org) :-
    holds_office(S1), person(S1, A), office(S1, O1),
    holds_office(S2), person(S2, B), office(S2, O2),
    office_in(S3), office(S3, O1), organisation(S3, Org),
    office_in(S4), office(S4, O2), organisation(S4, Org).
```

The semantics are exactly right (this *is* what A means), and it is short. But it is a second language with its own
parser, no editor completion or type checking without writing a language server, and every field becomes a predicate
whose name can clash between models (`office` of `HoldsOffice` and of `OfficeIn`). Recommended only as **a way of
showing** a rule (`explain` prints it like this), not of writing one.

### D. Cypher, with the triggers declared by hand

```python
CypherRule(SameOrganisation, triggers=[HoldsOffice, OfficeIn], cypher="MATCH ... RETURN a, b, org, [s1, s2, s3, s4]")
```

Anything Cypher can say, at once. But nothing is checked (a renamed field breaks it silently), the triggers are only as
right as the developer's list, the engine cannot seed the query from a written document (it would have to rerun it
whole, or the developer writes one query per trigger), it is not backend-neutral beyond Cypher, and it misses the
visibility and space rules unless written in by hand. Possible later as an **escape hatch** for what A cannot say
(aggregates, paths of unknown length), clearly marked as unchecked. Not in the first version.

### E. Python functions over loaded documents

`@rule(trigger=HoldsOffice) def f(statement: HoldsOffice.HeadView) -> list[SameOrganisation]`, which loads what it
needs with `get` and `search`. Flexible and easy to understand, but every join is a round of queries from Python, the
engine cannot tell what a rule reads (so cannot know which writes make it stale, only which trigger it), and
retraction is the developer's problem. Not recommended, except perhaps later as a `filter=` on the bindings of an A
rule (a Python test of values that Cypher cannot express), run on what the query found.

## The declaration in full

### Where it lives, and when it is loaded

- `<app>/derived.py`, for each of `INSTALLED_APPS` (as `models.py`, `api.py` and `cli.py` are). The server and the CLI
  import it **after** `models.py` and **before** `initialise()`, because `Derived` classes are models: they are
  registered as they are defined, and `initialise()` makes their classes (below).
- A rule's function is **not called on import**. `@rule` records it; `initialise()` calls it once, after every
  `Where` exists, with the variables, and checks what it returns. An error in a rule is an error of `initialise()`,
  naming the rule, the pattern and the field (`same_organisation: pattern 3, OfficeIn.office: a Var[Person] cannot
  be an Office`), as `check_match` names the path of a search.
- The SDK: `derived.py` is shipped with the models (its `Derived` classes are needed to read derived facts: their
  views). The rules are harmless there (they are only declarations; nothing runs them), or the builder can leave the
  function bodies out as it does for `@server_only`.

### `Derived` classes: what can be derived

A new kind of model, in `pangloss_derived` (registered with the models through a small hook; see
[Where the work is done](#where-the-work-is-done)):

```python
class SameFamily(Derived):
    _meta = Derived.Meta(symmetric=True)
    first: Person
    second: Person
    family: Group
```

- **Fields** are relations to entities, and literals. A derived fact is **one node connecting entities** (decided):
  no documents, embedded objects, wrappers or lists among its fields. It is a tuple of entities and values.
- **`Meta`:** `symmetric` (two fields of the same type whose order does not matter: the fact is stored once, with the
  two in order of id, and `first == second` is never derived; which two fields, if there are more than two of the
  type, is given by `symmetric=("first", "second")`), `abstract`, `reverse_names` (the name of the field on the entity's
  view, as `RelationConfig(reverse_name=...)` does).
- **Generated classes:** `SameOrganisation.Derive` (the head of a rule: each field typed as a variable of its type,
  `first: Var[Person]`, or a literal value), `View` and `ReferenceView` (with `justifications`), `Where` (so derived
  facts can be searched, and used in the body of another rule later). No `Create` or `Update`: nobody writes one.
- **On the entity's view:** under `_derived` (decided), apart from its own fields and its reverse relations. See
  [Reading](#reading).
- **Several rules may derive the same class** (two ways of being colleagues). Each justification says which.

### Variables

```python
class Var[T]:          # covariant in T
    name: str
    model: type[T]
```

- **A variable of an entity or document class** (`Var[Person]`) stands for one node of that class or a subclass.
  `Var` is covariant, so a `Var[Person]` is accepted where a `Var[Agent]` is (a field of the demo typed `Agent` takes it),
  and a `Var[Place]` is not.
- **A variable of a literal type** (`Var[int]`, `Var[datetime.date]`, `Var[ActivityType]`) stands for a value, joined
  by equality where it is used twice, and compared with the constraints below.
- **A variable of an embedded class** (`Var[Date]`) stands for the embedded node, so that an add-on's constraint can
  compare two of them (`overlaps(date_a, date_b)` from `pangloss-dates`).
- Variables are made by `@rule` from the parameters; `Var("a", Person)` makes one by hand (for a rule built by a loop,
  over many classes, as a generated rule could be).
- **Every variable of the head must appear in the body**, and every variable in the body must be in at least one
  pattern (not only in a constraint): the "safety" of Datalog, checked by `initialise()`. A variable used only once is
  allowed but warned of (it is probably a typo: an unused variable joins nothing).

### Patterns: the body

A pattern is any `Model.Where`, with these additions:

| Where | Takes | Meaning |
|---|---|---|
| a relation field (`person=`) | `Var[T]` for a `T` the field allows | the field points at the node the variable stands for (as `Rel(is_=...)`: for a list field, one of them) |
| `Rel(is_=...)` | a `Var` too | the same, with `through`, `exists` and the rest |
| a literal field (`year=`) | `Var[int]` | the field's value is the variable's (bound here if it is not bound yet) |
| `is_=` (new, on every `Where`) | `Var[ThisModel]` | the node matched is the variable's: lets two patterns be about the same document, and a document variable be used in a constraint |

So "two statements in the same factoid" is either `same_document(s1, s2)` (a constraint, below) or, in full,
`Factoid.Where(is_=f, statements=s1)` and `Factoid.Where(is_=f, statements=s2)`.

**What a pattern matches**, which differs from a search on purpose:

- **Any node of the class**, nested or a head (a statement is nested in a factoid); a search's root is always a head.
- **Inside semantic spaces too**, and **relations see through every wrapper**: semantic spaces, conjunctions
  (`Alternative`), identifications and other reified relations, as a search's relations do (decided). What was passed
  through is not lost: it is the *context* of the derivation, recorded (below). A project can make a space or wrapper
  block derivations, or count as nothing, by its `DerivedMeta` (below). A pattern can still narrow it with what a
  search has: `spaces_=[Negative]` (only inside one), `Rel(is_=a, through=[InRole])` (only through one).
- **Deleted documents and entities are never matched.** Unpublished documents are (their facts are hidden when
  read; see Reading).

### Context: what a derivation passed through

As a node inside a semantic space carries `meta.semantic_spaces` and `context_labels` now, a derivation carries what
its evidence was inside, and what its relations went through. For each pattern of a justification:

- **`spaces`**: the semantic spaces the matched node is in (read from its `semantic_spaces`, so free);
- **`through`**: for each relation that bound a variable, the wrappers on the path, outermost first
  (`["Identification", "Alternative"]` for `member` reached through `Identification[Alternative[ViaEdge[Person,
  Probability]]]`), and the properties of the edge to the entity, if it has any (`{"percent": 40}`), so that a network
  can weigh an edge by how likely the identification is.

Stored:

- on the **justification**: `context`, the whole of it, as JSON text (Neo4j cannot keep a map as a property, and nothing
  queries inside it), and `context_labels`, the names in it as a flat list (`["Negative", "Identification",
  "Alternative"]`), which a query can test;
- on the **fact**: `context_labels`, the names over all its justifications, and **`qualified_only`**: true if every
  justification has some context. "Members of the same family, *plainly*" is `qualified_only = false`; a fact that rests
  only on a negated statement or an uncertain identification is true, and is shown so.

The context does not make another fact (decided): X and Y in family A is one fact, however many justifications, plain
or not, it has. `Derived.list` and `Derived.Where` take `plain=True` (only facts with a plain justification) and
`context_labels` like a list field (`Items(contains="Negative")`). Nothing is filtered by default: what a context
means is the project's to say (below), and the reader's to choose.

### What a semantic space (or other wrapper) does to a derivation: the project says

Pangloss does not know what a semantic space means: a project makes its own, and they can mean anything. The general
point of one is to record a connection between entities that is not necessarily actual but suggests a connection all the
same ("don't go about with that dodgy group" suggests that one might have). So whether a space stops a derivation, or
only qualifies it, is said **on the space's class**, in a meta slot of the package (as `_interface_meta` is for the
interface; see [meta slots](meta-slots.md)):

```python
from pangloss_derived import DerivedMeta

class Negative[T](SemanticSpace[T]):
    """It is *not* the case that..."""
    _derived_meta = DerivedMeta(derivation="qualify")      # the default: derive, and record it in the context

class Hypothetical[T](SemanticSpace[T]):
    _derived_meta = DerivedMeta(derivation="block")        # nothing is derived from inside it

class Reported[T](SemanticSpace[T]):
    _derived_meta = DerivedMeta(derivation="transparent")  # derive as if it were not there (not in the context)
```

| `derivation` | A pattern matched inside it (or a relation through it) |
|---|---|
| `"qualify"` (default) | derives; the space's name is in the justification's context, so the fact is not plain on that account |
| `"block"` | does not derive: the compiled query leaves out nodes in it (`semantic_spaces`) and paths through it |
| `"transparent"` | derives, and is left out of the context: the project counts it as plain |

- The same slot is taken by **reified relations and conjunctions** (`Identification`, `Alternative`, `InRole`), with
  the same three values and the same default. A project that does not want uncertain identifications to derive
  anything says `block` on `Alternative`; `InRole` is a natural `transparent`.
- It is inherited, as meta slots are, so a family of spaces can share one setting.
- **A rule can override it** for itself: `.when(..., block=[Negative], allow=[Hypothetical])` (`allow` lets a blocked
  wrapper through, as `qualify`). For a rule that means something only in a negative, a pattern says
  `spaces_=[Negative]`, as in a search.
- **It is part of each rule's hash**: changing a space's setting rebuilds the rules that can pass through it (those whose
  patterns' classes can be inside it, or whose relations' types include it).
- `pangloss derive explain` lists, for each rule, the wrappers it can pass through and what each does.

How it is found: a relation whose type has wrappers is matched, as in a search, either directly or through a path of
wrappers of any length (`dialect().through_wrappers`), and the query collects the labels of the path's inner nodes. A
relation whose type has no wrapper (`MemberOf.member: Person`) is one edge, and costs nothing more. On a large model the
paths through wrappers are what to watch when measuring (step 7).

### Constraints

Functions that return a `Constraint`, given after the patterns in `.when(...)`:

| | |
|---|---|
| `distinct(a, b, ...)` | none of these is the same node (or value). Automatic for the two fields of a symmetric class |
| `same(a, b)` | the same (rarely needed: use one variable) |
| `same_document(s1, s2)` | the two nodes are in one head document (`head_node_id`, so cheap) |
| `lt(y1, y2)`, `lte`, `gt`, `gte`, `between(y, lo, hi)` | for literal variables; also as `y1 < y2` on `Var` (but not `==`, which would make a `Var` unusable in a set or dict) |
| add-ons' constraints | `pangloss_dates.overlaps(d1, d2)`, `before(d1, d2)`: a `Constraint` subclass that the add-on compiles to Cypher (`pangloss-dates` already knows the bounds of its dates) |

**No negation across documents** (decided: not wanted). "A held an office, and *no* document says A left it" would make
the rules non-monotonic (writing a document could remove facts that it is not evidence of), which would change how they
are kept up to date. `not_` *inside* one pattern, on that node's own fields, is allowed (it is a condition on one node).
`check_rule` refuses a `not_` that reaches another document or an entity's relations.

### Literal values in the head

```python
class HeldOfficeInYear(Derived):
    person: Person
    organisation: Organisation
    year: int

@rule
def held_office_in_year(a: Var[Person], o: Var[Office], org: Var[Organisation], y: Var[int]):
    return HeldOfficeInYear.Derive(person=a, organisation=org, year=y).when(
        HoldsOffice.Where(person=a, office=o, year=y),
        OfficeIn.Where(office=o, organisation=org),
    )
```

A literal field of the head is filled from a variable of the body (or a constant). Aggregates (`min(certainty)` over
the patterns, a count) are not in the first version.

### Two rules from the demo as it is

A single pattern, flattening a reified structure into a direct relation that is easy to traverse:

```python
class GaveTo(Derived):
    giver: Agent
    receiver: Agent

@rule
def gave_to(a: Var[Agent], b: Var[Agent]):
    return GaveTo.Derive(giver=a, receiver=b).when(Transfer.Where(given_by=a, given_to=b))
```

(`given_by` may be an `Identification[Alternative[...]]`: it is seen through, so each person who may be the giver is
a `giver`, in a justification whose context says `Identification`, `Alternative` and the probability.)

Two agents in one activity (one factoid's evidence):

```python
class CoParticipants(Derived):
    _meta = Derived.Meta(symmetric=True)
    first: Agent
    second: Agent

@rule
def co_participants(a: Var[Agent], b: Var[Agent], act: Var[Activity]):
    return CoParticipants.Derive(first=a, second=b).when(
        Activity.Where(is_=act, participants=a),
        Activity.Where(is_=act, participants=b),
    )
```

## Storage

```
(:PGDerived:SameFamily {key, derived_at, context_labels, qualified_only, ...literal fields})
    -[:first]->(x:Person)  -[:second]->(y:Person)  -[:family]->(a:Group)
(:PGJustification {key, rule: "same_family", rule_hash, nodes: [s1.id, s2.id], context, context_labels, derived_at})
    -[:justifies]->(fact)
    -[:evidence]->(factoid_1:HeadNode)   -[:evidence]->(factoid_2:HeadNode)   ...
```

- **A fact** is one node per derived class and values of its fields. Its `key` is a hash of the class and the ids and
  values of its fields (the two ends of a symmetric one in order), with a uniqueness constraint, so writing it is a
  `MERGE` and two workers cannot make two.
- **A justification** is one way the fact was derived: the rule, and the nodes each pattern matched, in order (`nodes`:
  the precise proof, for "why"), with an `evidence` edge to the **head node** of each (one edge per distinct head:
  four statements in two factoids are two edges). Its `key` is a hash of the rule and `nodes`.
- **Why edges go to head nodes, and ids of nested nodes are a property:** an update replaces a document's tree, deleting
  every node below the head node with its edges (`build_replace_head_query`), so an edge to a nested statement would
  vanish on every update. The head node stays.
- **Why the fact points outward, and nothing points from an entity:** an update of an entity deletes the edges it owns
  (its outgoing forward edges), so a `(Person)-[:SameOrganisation]->(Person)` edge would be deleted by any edit of the
  person. Edges *into* a head node that are not marked `reverse` are not touched by an update of it (checked in
  `build_replace_head_query`). No reverse edge pairs are written: the derived nodes are not part of anything's tree.
- **What the core must learn to ignore:** the check that an entity is in use before deleting it (an entity related only
  by derived facts is not in use: the facts go with it), `$any`/`$mentions` and the incoming relations of an entity's
  view (which list documents), and the text index (derived nodes have no `PGIndexableNode` label). One label,
  `PGDerived` / `PGJustification`, is excluded where those queries walk edges. To check, query by query, in step 2.
- **No direct edge** between the entities (decided: a derived fact is one node connecting entities). A network of
  plain person-to-person edges is a **collapse** of the nodes, made when it is wanted: `pangloss derive export
  SameFamily` (with `--plain-only` if wanted; an edge list, with the counts and contexts of the justifications as weights), or a query
  `MATCH (x)<-[:first]-(d:SameFamily)-[:second]->(y)` for a graph algorithm. Nothing has to be kept in step with it.
- **Not in history**, not in the snapshots of migrations, not exported as data. A migration of the models drops all
  derived facts of the rules that it affects and they are rebuilt.

## Reading

- `await SameFamily.list(first=smith.id)` and `SameFamily.search(SameFamily.Where(...))`: pages of
  `SameFamily.View`, each with its ends as reference views, `context_labels`, `qualified_only`, and its
  justifications (the rule's name and docstring, each evidence document as a reference view, and the context: "why").
- **An entity's head view has `_derived`** (decided), apart from its fields and reverse relations, so that the API and
  the page never mix what is derived with what a document says:

  ```json
  "_derived": {
    "SameFamily": {
      "count": 14,
      "items": [{"id": "…", "type": "SameFamily", "other": {"type": "Person", "id": "…", "label": "Y"},
                 "fields": {"family": {"type": "Group", "id": "…", "label": "A"}},
                 "context_labels": [], "qualified_only": false, "justifications": 2}]
    }
  }
  ```

  One key per derived class that can point at the entity (by the class's name, or a `reverse_name` of its `Meta`).
  Each holds a **first page** (25, by order of the other end's label) and the count: a person can have hundreds of
  derived relations where they have a few documents. The rest by `GET /api/derived/SameFamily?entity=…&page=2`. For a
  symmetric class the entity's own end is left out and the other is `other`. The field is `derived` in Python, with
  the alias `_derived` (pydantic does not allow a field whose name begins with `_`), and the interface shows it as its
  own section, marked derived, each with its "why" on demand (`GET /api/derived/SameFamily/<id>`).
- **A head document's view has `_derived` too** (decided): what it is evidence of, found by the `evidence` edges into
  it. The same shape (per derived class, a count and a first page), each item with the statements of the document that
  the justification used (from its `nodes`), so that the page can say "this statement, with that one in another
  factoid, gives: X and Y of the same family". For a nested document the field is not given (the evidence edge is to
  the head); the head's view says which of its statements was used.
- In a search: a derived class's `Where` can be used where a relation pattern is (`Person.Where(derived_=
  SameOrganisation.Where(organisation=z))`), later.
- **What is seen:** a fact is visible if one of its justifications has all its evidence visible to the reader (by
  `fragments.visible`: not deleted, published or the reader may see what is not). In Cypher, an `EXISTS` over the
  justifications, then over their evidence, so the test is in one place (`fragments.derived_visible`). A fact
  justified only by unpublished factoids is seen by a reviewer and not by the public, without anything being
  recomputed when a factoid is published. This is also where a **lens** goes later: "only justifications whose
  evidence is by these authors, from these sources".

## Keeping it up to date

### What can trigger a rule (worked out once, at `initialise()`)

For each rule, the **classes of its patterns** (with their subclasses: a pattern on `Statement` is matched by an
`Activity`). From the model's metadata, the **head classes whose tree can contain** a node of each (`Factoid` can
contain a `MemberOf` through `statements`, and through `Negative[...]` and the other spaces). The result is a table:

```
head class  ->  [(rule, pattern index, pattern class), ...]
Factoid     ->  [(same_family, 0, MemberOf), (same_family, 1, MemberOf), (co_participants, 0, Activity), ...]
Person      ->  []          # (no pattern is about a person's own fields: a variable is not a trigger)
```

An entity class is a trigger only if a pattern is *of* it, with conditions on its own fields or relations
(`Person.Where(is_=a, has_type=...)`); being the value of a variable is not, because a variable is joined by the edge,
which belongs to the document. A write of a class with an empty list costs nothing more than now.

`pangloss derive explain` prints this table, so a developer can see that a rule triggers on what they expect.

### Marking what is pending (in the write's own transaction)

`hooks.new_head_properties` and `updated_head_properties` already put properties on a head node in the transaction
of the write (as `pangloss-review` does). The add-on puts `pg_derive_pending: true` on a head whose class is in the
table. So a committed write is always known to be pending, even if the server stops at once. A delete (and undelete)
does not call those hooks now: the delete query has to put the marker too (a small change in the core, step 4). An
index on `HeadNode(pg_derive_pending)` finds the work.

This is the **pending-derivation mechanism** that [dates.md](dates.md#what-the-core-needs) and the calendar asked the
core for: a marker, an index, a worker with a lease, a compare-and-set. It is built once, generically, and derived
rules are its first user (decided: built in core).

`after_write` (already there) **wakes** the worker, so that the work starts at once rather than at its next poll; it
does not carry the work.

### The worker

A `BackgroundTask` (`pangloss_api.background`), and `pangloss derive worker` for running it on its own. In a loop:

1. **Claim** a batch of pending heads (say 200): `SET h.pg_derive_claimed_until = now + lease` where it is unclaimed or
   its lease has run out, and read each one's `version` and which classes its tree has (`labels` of the nodes with its
   `head_node_id`: one indexed query).
2. **Choose the queries:** for each (rule, pattern) of the table whose pattern class is among the classes found, one
   **seeded query** with all the batch's matching node ids. Nothing for a head whose tree has none.
3. **Run each seeded query**, which returns the justifications (`key`, fact key, fields, `nodes`, evidence heads) that
   include one of the seeds at that pattern's place.
4. **In one write transaction:** `MERGE` each fact and justification found (a no-op for those already there); delete
   the justifications with evidence in the batch's heads **whose keys were not found**; delete facts left with no
   justification; clear `pg_derive_pending` on each head **only if its `version` is still the one read** in step 1. A
   head written again meanwhile keeps its marker, and is done again in the next batch.

**Why this is exact** (for rules without negation or recursion): every justification that involves a document has at
least one pattern matched by a node of that document; seeding each pattern of each rule with the document's nodes
therefore finds **every** justification the document now takes part in, and nothing else needs re-checking. What it
took part in before and does not now is exactly what was not found again. Other documents' justifications are not
touched. This is the "delta rule" of semi-naive Datalog evaluation, applied one document at a time; the deletion is
"delete and re-derive" restricted to the document.

**Writes only what changed.** An edit of a factoid's label re-runs its seeded queries, finds the same keys, and writes
nothing but the cleared marker.

**A deleted document** is seeded like any other, its nodes are not matched (deleted), so nothing is found and all its
justifications go. Meanwhile, the visibility rule has hidden them since the delete committed.

### The seeded query

For `same_family`, seeded at pattern 0, with the demo's `MemberOf.member` typed as `given_by` is (`Person |
Identification[Alternative[ViaEdge[Person, Probability]]]`), so that it has wrappers to see through:

```cypher
UNWIND $seeds AS seed
MATCH (s0:MemberOf {id: seed})-[:group]->(family:Group)        // `group: Group`: no wrappers, one edge
WHERE <s0's head not deleted> AND <family not deleted>
MATCH p0 = (s0)-[:member]->/* wrappers, none or more */(a:Person)
MATCH (family)<-[:group]-(s1:MemberOf)
MATCH p1 = (s1)-[:member]->/* wrappers, none or more */(b:Person)
WHERE a <> b AND <s1's head not deleted> AND <a, b not deleted>
RETURN a.id, b.id, family.id,
       [s0.id, s1.id], [s0.head_node_id, s1.head_node_id],          // the proof, and the evidence
       [s0.semantic_spaces, s1.semantic_spaces],                     // the context: spaces
       <the wrapper labels of p0 and p1, and the properties of their last edges>   // the context: through
```

- **The join order** is chosen by the compiler, not left to the planner: start from the seeded pattern, then each
  pattern that shares a bound variable with what is bound, preferring those joined by a relation from a bound document
  (one edge) over those reached backwards from an entity (all its incoming edges). `explain` prints the order.
- One query per (rule, pattern position) for the batch: two for `same_family`, four for `same_organisation` (fewer
  when the batch has no `OfficeIn`: those positions are skipped).
- **Symmetry is used:** for a symmetric rule whose patterns pair up under swapping the two ends (patterns 0 and 1 of
  `same_family`), only one of each pair needs seeding, and the query returns each pair both ways. Found at `initialise()` by comparing the patterns with the
  variables swapped; an optimisation, step 7.
- It goes through the backend's dialect (`pangloss-cypher`), so Memgraph and Neo4j both get it, and the conformance
  suite (`pangloss-testing`) runs the rules' tests on both.

### When a rule changes, or is new

Each rule has a hash of its compiled body (and of the `Derived` class). A `PGDeriveRule {name, hash, state}` node per
rule records what the stored facts were made with. On start:

- **New rule, or changed hash:** the worker **rebuilds** it: the full query (not seeded), in pages of the first pattern's
  nodes in order of id, `MERGE`ing facts and justifications with the new hash; then deletes justifications of that rule
  with another hash. While it runs, the old facts stay (they are what is known), and `status` says the rule is being
  rebuilt. Writes during the rebuild are handled as usual (seeded queries use the new rule).
- **Rule removed:** its justifications are deleted, then facts with none.
- `pangloss derive rebuild [rule]` does the same on demand; after a **bulk load** (which does not go through the
  hooks: `pangloss memgraph bulk-load`) it is the way to derive everything, and it is far faster than marking 600,000
  documents pending.

### Cost, and limits

- **A write that triggers nothing** costs a dictionary lookup.
- **A write that triggers** costs a property on its head node (in its transaction; the index on it), then, later, a
  few indexed queries in a batch. The writes of the worker are batched into one transaction, which matters on Memgraph,
  where each commit costs some milliseconds whatever it holds.
- **Fan-out is the cost of the pairs**, which are what is wanted (decided: person-to-person networks, stored). A pair
  rule through a shared node is quadratic in the members: a family of 50 is 1,225 facts; one `OfficeIn` that adds an
  office to an organisation with 1,000 office-holders is up to 500,000 `SameOrganisation` facts from one write. Most
  writes add one member, which is linear (one new member of a family of 50 is 50 facts). The safeguards, so that a
  mistake in a rule or in the data does not fill the database: a limit per seed (`Derived.Meta(max_per_seed=...)`;
  10,000 justifications from one written document by default, decided, to be revisited after measuring), past which that seed's results are not written, `status` flags
  it and the log says so; and `dry-run`, which shows the count and the worst seeds before a rule is switched on.
- **To measure** on the 642,000-node demo data, on both backends: the time of a seeded query per rule, a batch of 200,
  a rebuild of each demo rule, and the cost added to a write by the marker.

## What the first version does not do

- **Negation across documents** (decided: not wanted), **recursion** (a rule whose body uses a derived class: transitive
  closure, "colleague of a colleague", ancestors; needs the rules ordered in strata, a fixpoint, and full "delete and
  re-derive"), **aggregates** (counts, `min` of certainties into the head), **paths of unknown length**.
- **Computing from qualifications** into the fact's fields (a `min` of certainties): the context records them (the
  properties of the last edge, such as a `Probability`), and a constraint can test them, but the head cannot compute
  from them yet.
- **Freezing** a derived fact into an asserted document ("a researcher confirms this"): it is an ordinary document,
  written by hand; a button in the interface later.
- **Rules written in the interface or stored in the database.** The JSON form makes it possible; nothing more.
- **The interface:** derived facts on an entity's page, with their "why". After the API.

## Where the work is done

| Layer | Module | Role |
|---|---|---|
| Package | `pangloss-derived` (decided: all of it there, as far as it can be) | `Derived`, its `Meta`, and the generation of `Derive`, `View`, `ReferenceView`, `Where`; `Rule`, `@rule`, `Constraint`, `check_rule`, the trigger table; loading `derived.py`; the queries (through the kit's dialect); the worker (`BackgroundTask`); the CLI (`pangloss derive explain / dry-run / rebuild / status / export / worker`); the routes (`/api/derived/...`); the `_derived` of entity views |
| Models (small) | `search.py`, `search_where.py` | `Var[T]` and `{"$var": ...}`: variables are a part of search patterns ("variables across branches"), so `check_match` and the generated `Where` fields know them; `is_=` on every `Where` |
| Models (hooks) | `hooks.py`, `model_registry.py`, `typestubs.py` | What the package needs to be a package: a way to add a kind of model that `initialise()` generates classes for (or a hook after it, in which the package makes them), stubs for a project's `derived.py` (by `pangloss make-stubs` and the SDK builder), and an extra section of an entity's head view (`derived`, alias `_derived`) that a backend function fills |
| Core | `hooks`, the delete query, `pangloss_cypher` | The pending-derivation mechanism (marker, index, lease, compare-and-set; generic, a handler per kind), the marker on delete, `PGDerived` / `PGJustification` left out of the queries that must not see them |
| Kit | `pangloss_cypher/fragments.py` | `derived_visible`, so that the one rule of what is seen stays in one place |
| Testing | `pangloss-testing` | `await run_pending_derivations()` for tests (no waiting for the background); conformance tests on both backends |
| Add-ons | `pangloss-dates` | `overlaps`, `before`: constraints on `Var[Date]` |

## Plan, in steps that each work alone

0. **Example models.** `MemberOf` in the demo (with `member` typed like `given_by`, so that it has identifications)
   and in the kitchen-sink test models, with `Office`, `Organisation`, `HoldsOffice` and `OfficeIn` in the test models
   only. Hand-written cases: two members of one family from two factoids, a third in a `Negative`, one through an
   `Identification` with two alternatives, a deleted factoid, an unpublished one.
1. **Variables and rules, no database.** `Var`, `@rule`, `Derived` and its generated `Derive`; `Var` accepted by the
   `Where` fields and `is_=`; the JSON form; `check_rule` (fields, types of variables, safety, unused variables,
   constraints); the trigger table. Tests: each check's error message; the trigger table for the kitchen sink; the
   stubs, with a usage file that `ty` must accept and one it must refuse (a `Var[Group]` given to `member`). The hooks
   the package needs from the models (a kind of model, its stubs).
2. **The full query, and storage.** Compile a rule to one Cypher query (no seeds), with the context of each
   justification; write facts and justifications (and `context_labels`, `qualified_only`); `pangloss derive rebuild`,
   `dry-run` and `export`. `DerivedMeta` (`qualify`, `block`, `transparent`) and the rule's `block` and `allow`, in the
   query and in the rule's hash. Exclude `PGDerived` where the core must not see it (checked query by query).
   Tests on both backends: the cases of step 0.
3. **Reading.** `Derived.list`, `get`, `search` (with `plain=`), the views with their justifications and context,
   `derived_visible`; the routes; the SDK.
4. **The pending mechanism, in core.** Marker, index, lease, compare-and-set, the marker on delete; generic (a handler
   per kind), with derived rules its first handler.
5. **Seeded queries and the worker.** The delta queries, the join order, the diff and write of step 4 of the worker,
   the wake-up from `after_write`. Tests: write, update (a change that removes a justification, one that changes
   nothing), delete, undelete, publish; two writes of one head during one batch; a crash between claim and write.
6. **Rule changes.** `PGDeriveRule`, the rebuild of a changed rule, the removal of a removed one; `status`.
7. **Measure** on the 642,000 nodes (both backends); the limits (`max_per_seed`); the symmetric optimisation if it is
   needed.
8. **Views, and docs.** `_derived` on entity and head document views (and the interface's sections for them, with
   "why"); `DerivedMeta` on the demo's spaces; `docs/derived.md`, a guide chapter with a rule built up
   step by step, the safeguards on fan-out, and how to collapse the facts into a network.

Later, each its own plan: recursion, aggregates, a lens, rules written in the interface.

## Decisions (answered 2026-11-02)

1. **Example models:** the office chain was only an example. The simpler one, "X is a member of family A" and "Y is a
   member of family A" give "X and Y are of the same family", is the main example, and goes into the demo (a family is
   a `Group`).
2. **The surface:** as recommended (A: typed parameters as variables, `Derive(...).when(...)`, `is_=` on `Where`).
3. **Pairs, stored:** the point is to derive person-to-person networks from factoids that each speak of one person, as
   data is added. Fan-out is guarded, not designed away.
4. **Rules see through all semantic spaces and identifications** (and every other wrapper), and what was passed
   through is recorded on the justification and summed up on the fact, as `context_labels` is for nodes in a space.
5. **A derived fact is one node connecting entities.** A graph of plain edges is a collapse of them, made when wanted.
6. **In the API and on the page, as derived:** under `_derived` on an entity's view.
7. **No negation across documents.**
8. **The pending-derivation mechanism is built in core.**
9. **Unpublished evidence:** derive from everything not deleted, hide on reading what rests only on what the reader
   cannot see.
10. **All in the package**, no strong view. The plan keeps in the models only `Var` (it is a part of search patterns)
    and the hooks the package needs to add a kind of model.

### Second round

11. **The context does not make another fact.** One fact per tuple, with its justifications, plain and qualified.
12. **What a semantic space does to a derivation is the project's to say**, since spaces are made by projects and mean
    what they want: `DerivedMeta(derivation="qualify" | "block" | "transparent")` on the space's class (and on reified
    relations and conjunctions), `qualify` by default; a rule can override it. Nothing is filtered on reading by
    default.
13. **`max_per_seed`: 10,000** by default, revisited after measuring.
14. **Head documents have `_derived` too**: what they are evidence of.
