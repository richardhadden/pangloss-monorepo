# Derived relations: a network from what the documents say

Your factoids say one thing about one person at a time: "Einhard was a member of the court school", "Alcuin was a
member of the court school". `pangloss-derived` makes the relations that follow from them ("Einhard and Alcuin were of
the same group"), keeps them up to date as documents are written, and says, for each, *why*. The reference is
[implementation_docs/derived.md](../../implementation_docs/derived.md).

## 1. Install it

```python
INSTALLED_APPS = [
    "pangloss_memgraph",
    ...
    "pangloss_derived",   # before your app
    "my_app",
]
```

then `pangloss migrate`.

## 2. Say what can be derived

In `my_app/derived.py`, next to `models.py`:

```python
from typing import Annotated

from pangloss_derived import DerivedEdge, Object, Subject, SymmetricLabel, Var, rule

from my_app.models import Agent, Group, MemberOf, Person, Transfer


class SameGroup(DerivedEdge):
    """Members of the same group"""

    _meta = DerivedEdge.Meta(symmetric=True)   # (A with B is B with A: one edge)

    first: Annotated[Person, SymmetricLabel("member")]    # the two ends: either is a "member"
    second: Annotated[Person, SymmetricLabel("member")]
    group: Group                                          # which group: part of what the edge is
```

What is derived is an **edge**: it has two ends, and anything else qualifies it. A and B in two groups are two
edges. When the order matters, mark the ends instead:

```python
class GaveTo(DerivedEdge):
    """Gave something to"""

    giver: Annotated[Agent, Subject()]
    receiver: Annotated[Agent, Object(reverse_name="received_from")]   # how it reads from the receiver
    year: int
```

## 3. Say how

A rule is a function. Its parameters are its *variables*; it gives the fact to derive, `.when(...)` the patterns hold:

```python
@rule
def same_group(a: Var[Person], b: Var[Person], group: Var[Group]):
    """Two people said to be members of one group"""
    return SameGroup.Derive(first=a, second=b, group=group).when(
        MemberOf.Where(member=a, group=group),
        MemberOf.Where(member=b, group=group),
    )
```

The patterns are the `Where` of your models, as in a search, with a variable where a value would be. `group` is in
both, so both statements must be about the same group. Run `pangloss make-stubs`, and your editor knows that `member=`
takes a `Var[Person]`.

`pangloss derive explain` shows the rule as Datalog, which writes trigger it, and how its query is joined.

### The short way, for one document

When both ends are in one document, there is no rule to write. Say it on the document class, in `models.py`:

```python
from pangloss_derived import DerivesEdge


class Transfer(Statement):
    _derives = [DerivesEdge("GaveTo", subject="given_by", object="given_to", reverse_name="received_from")]

    given_by: Agent
    given_to: Agent


class Activity(Statement):
    # everyone who took part, with everyone else
    _derives = [DerivesEdge("CoParticipants", subject="participants", object="participants", symmetric=True)]

    participants: list[Agent]
```

That makes the `GaveTo` and `CoParticipants` edges, and the rules, for you. Three factoids that say A gave to B are
one edge with three justifications. `qualifiers={"year": "year"}` puts a field of the document on the edge. If two
kinds of document should give the same edge (`Transfer` and `Sale`), give both the same name and
`ends=("giver", "receiver")`. Keep `derived.py` for rules that need two documents, like `same_group` above.

## 4. Try it before switching it on

`pangloss derive dry-run same_group` says how many facts the rule would make from the data you have, and the
documents that give most. A pair rule is quadratic in the members of a group: a group of 400 is 79,800 pairs. If that
is not what you mean, narrow the rule (a condition on the group's type, a year) before you build it.

## 5. Build it, and let it run

Start the server: the worker builds a new rule from the data there is, and then keeps up with writes (a write is
derived from within about half a second). `GET /api/derived/status` (or `pangloss derive status`) says what is
pending. After a bulk load, `pangloss derive rebuild`.

## 6. Read it

`GET /api/Person/{id}` has `_derived.SameGroup`: the other people, with how many justifications each has. Someone who
gave and received has `_derived.GaveTo` (what they gave) and `_derived.received_from`. A group has
`_derived["SameGroup:group"]`: the edges it qualifies, each with both its ends. "Why" is
`GET /api/derived/SameGroup/{id}`: the rule, the factoids, and anything the evidence passed through (a negation, a
weighted alternative). In Python: `await SameGroup.list(entity=einhard)`, `await SameGroup.get(id)`,
`await Person.search(Person.Where(derived_=GaveTo.Where(receiver=einhard)))` (who gave to Einhard).

## 7. Contexts

A statement inside `Negative[...]` still derives, but the edge says so (`contextLabels: ["Negative"]`, and
`plain: false` if that is all it rests on). A reified relation (an identification, a role) and a conjunction are
read through as if they were not there. Say otherwise on the class:
`_derived_meta = DerivedMeta(derivation="block")` to derive nothing from one, `"transparent"` to count a space as
nothing, `"qualify"` to have an identification put what is derived through it in doubt, and
`DerivedMeta(exclusive=True)` on an "or" (an `Alternative`), so that "Smith, who is A or B" does not make A and B of
one group. `pangloss-library`'s `WeightedAlternative` and `IdentificationByToolchain` qualify.

A value found on the way that should not make another edge (a probability, an amount) is a field marked
`PerJustification()`: it is kept with each justification, and shown under "why".

A rule can also ask something of the way, and read what it finds there. "Through an alternative only when it is at
least 60 per cent likely, and keep the percentage":

```python
class LikelyGaveTo(DerivedEdge):
    giver: Annotated[Agent, Subject()]
    receiver: Annotated[Agent, Object()]
    likelihood: Annotated[int, PerJustification()]

@rule
def likely_gave_to(a: Var[Agent], b: Var[Agent], p: Var[int]):
    return LikelyGaveTo.Derive(giver=a, receiver=b, likelihood=p).when(
        Transfer.Where(
            given_by=Rel(is_=a, through=[Through(WeightedAlternative, edge=Likelihood.Where(percent=p))]),
            given_to=b,
        ),
        p >= 60,
    )
```

`Through(Wrapper, where=..., edge=...)` asks for a wrapper on the way: `where` is of its own values
(`Identification.Where(identified_by=who)`), `edge` of the edge that leaves it, by its edge model. `Rel(is_=w,
edge=Certainty.Where(value=c))` is of the edge that reaches the entity. A field of either can be a variable (as `p`),
or a condition (`Compare[int](gte=60)`). `Rel`, `Through` and `Compare` come from `pangloss_models`. They work in
[a search](../search/README.md) too.

## 8. Dates, and lists

A variable can be a date (`d: Var[Date]`, with `pangloss-dates`), and `overlaps(d1, d2)`, `before(d1, d2)`,
`within(d1, d2, days=365)` compare two of them: "held office at the same time", "within a year of each other". It can
also be one item of a list field (`Person.Where(is_=a, aliases=name)`): two people with an alias in common.

## 9. A network

Give rules a type, `@rule(types=[family])` with `family = RuleType("family")`, and `pangloss derive graph family --csv`
is an edge list of everything the rules of that type derive, for Gephi or networkx. Its `weight` is how many
justifications an edge has. `--graphml` gives a GraphML file instead, which keeps the labels of the people and the
qualifiers of each edge (the group, the year). With `pangloss-rdf`, `pangloss rdf dump --include-derived` writes the
edges as RDF, each with the documents it rests on.

## 10. A document, not an edge

A rule can also derive a whole document: from "A was a child of P" and "B was a child of P", a factoid saying that A
and B were siblings, with the two factoids as its sources. Declare the class with the trait and one `DerivedFrom`
field, and write the rule with `Derive` and `Template`, which are shaped like `Create` but take variables:

```python
class DerivedFactoid(Document, DerivedDocument):
    sources: list[DerivedFrom[Factoid]]      # filled in for you
    statements: list[Statement]


@rule
def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
    return DerivedFactoid.Derive(
        label="Siblings",
        statements=[Sibling.Template(label="Siblings", people=[a, b])],
    ).when(
        ChildOf.Where(child=a, parent=p),
        ChildOf.Where(child=b, parent=p),
        unordered(a, b),          # each pair once, not (A, B) and (B, A)
    )
```

The rule is checked when the models are initialised. If `initialise()` refuses it, the message says what to change:
most often that a `ChildOf` could be a document of its own (say `create_directly=False` on your statement classes),
or that a rule reads what it writes (`block=[DerivedFactoid]`). `pangloss derive explain siblings` shows the rule and
`pangloss derive dry-run siblings` counts the documents it would make.

The worker writes the documents, in the background, as the user `derived`:

- **One document for each time the rule matches.** The same two siblings found through another parent, or in a
  third source, are another document. Its `sources` are the documents the match was found in.
- **It follows its sources.** A source changed so that the rule no longer matches: the document is deleted. Changed
  back: the same document returns, with its history. A value changed (a person merged into another): the document is
  updated in place and keeps its id.
- **It is published when every source is.** With `pangloss-review`, a derived document is hidden until the
  documents it rests on have been checked. It is never reviewed itself.
- **Nobody edits it.** A create, update or delete by hand is refused. Change the sources and it follows.
- **Rules can read it.** A rule whose pattern matches a `Sibling` also matches the derived ones, and what it
  derives rests on the derived document. A rule that should read only what people wrote says
  `block=[DerivedFactoid]`.
- **It can be cited.** A `Cites` field that names a derived document (or a statement inside one) saves citations of
  what it rests on, grouped under it. If the derivation later changes or stops holding, the citation is marked.
- **Nothing is written when nothing changed.** Saving a source as it was, or `pangloss derive rebuild`, adds no
  version to a derived document.

`pangloss derive status` says how many derived documents wait to be written or deleted and how many each rule has.
After a bulk load, `pangloss derive rebuild` builds the rules in order and writes their documents. Before switching
on a rule over a large family, look at `dry-run`: a pair rule over 50 children is 1,225 documents, and a document
that would give more than `max_per_seed` (2,000) gives none.

### In the web interface

- A derived document's page has no Edit or Delete. A section **Derived** says which rule made it and shows the
  documents it rests on.
- A source's page lists what follows from it under **Derived from this**.
- In the search form of a class that has both kinds (`AbstractFactoid`), **Add a filter → Derived** gives Yes or No.
  As a search: `{"$derived_document": true}`, or `AbstractFactoid.Where(derived_document_=True)`.

### Making one your own

A derived document cannot be edited, but someone logged in can take it over: **Make it my own: Factoid** on its page
opens the form of a `Factoid` with what the two classes share filled in. Nothing is written until it is saved. Then:

- It is the same document: same id, same address but for the class, same history.
- The rule no longer writes it and never makes another for the same match.
- If the target has a `Cites` field that takes them, the sources become its citations (and are protected, as
  anything cited is).
- Its page says **Made from a derivation**, and says so if the derivation later stops holding. The document itself is
  not touched.
- If the derivation passed through a denial or another context, the document still carries that ("Through:
  Negative") and rules still read it that way. **Clear** takes it off: you are saying that the document no longer
  rests on the derivation.
- With `pangloss-review`, it keeps the status it had and gets an open comment saying what it was made from.

Which classes it can become: those that share a parent class with it, or what you name:

```python
class DerivedFactoid(AbstractFactoid, DerivedDocument):
    _derived_document_meta = DerivedDocumentMeta(converts_to=Factoid)
```

Over the API: `GET /api/derived/convert/DerivedFactoid/{id}/Factoid` gives the form (`initial`, `version`), and
`POST /api/derived/convert` with `{model, id, to, version, data}` writes it.
