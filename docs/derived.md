# Derived relations ✅

`pangloss-derived` (built 2026-11-02): **rules** that make new facts from what documents say, kept up to date by a
worker in the background. Most factoids speak of one person at a time ("X was a member of family A"); a rule makes the
relations between people that follow ("X and Y are of the same family"), so that a network grows as data is added.
Nobody writes a derived fact: it is computed, it carries its evidence ("why"), and it can be dropped and rebuilt at any
time. The design, the decisions and the measurements are in [derived-implementation.md](derived-implementation.md); the
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
  it is counted), `abstract`, `reverse_names`.
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
family G" would make B and C of one family. The demo's `Alternative` is exclusive.

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
| `GET /api/Person/{id}` | has `_derived`: for each class, a count and a first page (the other end and the field it is in, `otherField`; the other fields) |
| `GET /api/Factoid/{id}` | has `_derived` too: what the document is evidence of |

The same functions work through the SDK (they ask the API; blocking with `connect(sync=True)`, as the models' own
are). The interface shows `_derived` under an item's contents, a page at a time, with "why" on demand.

## Commands

`pangloss derive explain [rule] [--queries]` (the rule as Datalog, what triggers it, the join order from each place),
`dry-run [rule]` (how many facts, the seeds that give most, nothing written), `rebuild [rule]`, `status`,
`graph TYPE [--plain-only] [--csv]`, `worker`.

## Storage

`(:PGDerived:SameGroup {key, ...})-[:first]->(person)` and so on, and `(:PGJustification {key, rule, types, nodes, context,
context_labels})-[:justifies]->(fact)` with `-[:evidence]->` to the head node of each document used. Nothing is written
from an entity or into a document's tree. About 2.6 KB of Memgraph's memory per fact (measured).
