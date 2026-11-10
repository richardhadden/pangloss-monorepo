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
from pangloss_derived import Derived, RuleType, Var, rule

from demo_app.models import Group, MemberOf, Person

family = RuleType("family", "Ties of family and of membership")


class SameGroup(Derived):
    """Members of the same group"""

    _meta = Derived.Meta(symmetric=True)

    first: Person
    second: Person
    group: Group


@rule(types=[family])
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    """Two people said (perhaps by different sources) to be members of one group"""
    return SameGroup.Derive(first=a, second=b, group=group).when(
        MemberOf.Where(member=a, group=group),
        MemberOf.Where(member=b, group=group),
    )
```

- **A `Derived` class** is what can be derived: relations to entities (or a trait of them) and literals. Its `Meta`:
  `symmetric` (two fields whose order does not matter: stored once, in order of id, never a thing with itself), `ends`
  (the two fields that are the edge in a graph; by default the symmetric two, or the first two relations),
  `max_per_seed` (10,000: the most justifications one written document may give; past it none of them is written, and
  it is counted), `abstract`, `reverse_names`. The two symmetric fields need names (`first`, `second`), but they mean
  nothing to a reader: give them one name for the interface with `SymmetricLabel`, on either field
  (`first: Annotated[Person, SymmetricLabel("member")]`). It is translated as a field's name is.
- **Translations:** each concrete derived class goes in its app's `translations/models.jsonc` as a model does (`pangloss
  interface translations generate`): its name, its description (the docstring), its fields (the two symmetric ones as
  the one `SymmetricLabel`), and its `reverse_names` as incoming names.
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

## What a space or a wrapper does: `DerivedMeta`

Rules see through semantic spaces, conjunctions and reified relations, and record what they passed through (the
**context** of a justification). What a space means is the project's to say, on its class:

```python
class Hypothetical[T](SemanticSpace[T]):
    _derived_meta = DerivedMeta(derivation="block")        # derives nothing from inside it

class InRole[T](ReifiedRelation[T]):
    _derived_meta = DerivedMeta(derivation="transparent")  # as if it were not there

class Alternative[T](Conjunction):
    _derived_meta = DerivedMeta(exclusive=True)            # "one of these": a justification takes one member
```

`qualify` (the default) derives and keeps the wrapper's name in the context. A rule can override: `.when(...,
block=[Negative], allow=[Hypothetical])`. **`exclusive`** is for an "or": without it, "Smith, who is B or C, was of
family G" would make B and C of one family. The library's `WeightedAlternative`, which the demo uses, is exclusive.

A fact's `contextLabels` are the names over all its justifications, and `qualifiedOnly` is true when none of them is
plain ("only from a negated statement"). Nothing is filtered by default.

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
| `await SameGroup.list(entity=smith)` | a page of the facts the reader sees, about an entity |
| `await SameGroup.list(SameGroup.Where(group=g, plain=True))` | by a field, `plain`, `context_label`, `rule_type` |
| `await SameGroup.list(evidence=factoid)` | the facts a head document is evidence of |
| `Person.search(Person.Where(derived_=SameGroup.Where(group=g)))` | the entities with such a fact (`$derived` in the JSON of a search; a filter, as above) |
| `await SameGroup.get(id)` | one, with its justifications: the rule, the evidence documents, the context |
| `await pangloss_derived.graph("family")` | the facts of the rules of a type, as edges between their two ends |
| `GET /api/derived` | the classes, the rules (as Datalog) and the types |
| `GET /api/derived/{Class}?entity=…&page=2` | a page (or `evidence=` a document; any field as a parameter, and `plain`, `context_label`, `rule_type`) |
| `GET /api/derived/{Class}/{id}` | one, with "why" |
| `GET /api/derived/graph/{type}?plain=true` | the graph of a type |
| `GET /api/derived/status` | what is pending, the state of each rule, what the worker did |
| `GET /api/Person/{id}` | has `_derived`: for each class, a count and a first page (the other end and the field it is in, `otherField`; the other fields). Not with `?extras=false` |
| `GET /api/derived/about/{Type}/{id}` | the same `_derived` on its own, for a reader that read the view without it (`{Type}`: the item's own class); `{}` when nothing is derived about it |
| `GET /api/Factoid/{id}` | has `_derived` only of facts with a field that points at the document, not what it is evidence of (that is what it says itself; `list(evidence=...)` gives it) |

The same functions work through the SDK (they ask the API; blocking with `connect(sync=True)`, as the models' own
are). The interface shows what is derived under an item's contents, a page at a time, with "why" on demand: the "Derived" section is
the interface module of `pangloss_derived` (`itemSections.Derived`), so a project can leave it out, or put its own in its place, with
`InterfaceConfig(disabled=["pangloss_derived:Derived"])` ([interface-features.md#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived](interface-features.md#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived)). The section shows
the item's `_derived` if the item came with it, and otherwise reads `/api/derived/about/{Type}/{id}` itself, in the section's own
boundary (the item's page reads the item with `?extras=false`, so that it is on show before what is derived about it has been found;
the section appears after what refers to the item, never before it).

## Commands

`pangloss derive explain [rule] [--queries]` (the rule as Datalog, what triggers it, the join order from each place),
`dry-run [rule]` (how many facts, the seeds that give most, nothing written), `rebuild [rule]`, `status`,
`graph TYPE [--plain-only] [--csv]`, `worker`.

## Storage

`(:PGDerived:SameGroup {key, ...})-[:first]->(person)` and so on, and `(:PGJustification {key, rule, types, nodes, context,
context_labels})-[:justifies]->(fact)` with `-[:evidence]->` to the head node of each document used. Nothing is written
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
