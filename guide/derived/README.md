# Derived relations: a network from what the documents say

Your factoids say one thing about one person at a time: "Einhard was a member of the court school", "Alcuin was a
member of the court school". `pangloss-derived` makes the relations that follow from them ("Einhard and Alcuin were of
the same group"), keeps them up to date as documents are written, and says, for each, *why*. The reference is
[docs/derived.md](../../docs/derived.md).

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
from pangloss_derived import Derived, Var, rule

from my_app.models import Group, MemberOf, Person


class SameGroup(Derived):
    """Members of the same group"""

    _meta = Derived.Meta(symmetric=True)   # (A with B is B with A: one fact)

    first: Person
    second: Person
    group: Group
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

## 4. Try it before switching it on

`pangloss derive dry-run same_group` says how many facts the rule would make from the data you have, and the
documents that give most. A pair rule is quadratic in the members of a group: a group of 400 is 79,800 pairs. If that
is not what you mean, narrow the rule (a condition on the group's type, a year) before you build it.

## 5. Build it, and let it run

Start the server: the worker builds a new rule from the data there is, and then keeps up with writes (a write is
derived from within about half a second). `GET /api/derived/status` (or `pangloss derive status`) says what is
pending. After a bulk load, `pangloss derive rebuild`.

## 6. Read it

`GET /api/Person/{id}` has `_derived.SameGroup`: the other people, with how many justifications each has. "Why" is
`GET /api/derived/SameGroup/{id}`: the rule, the factoids, and anything the evidence passed through (a negation, an
uncertain identification). In Python: `await SameGroup.list(entity=einhard)`, `await SameGroup.get(id)`.

## 7. Contexts

A statement inside `Negative[...]` still derives, but the fact says so (`contextLabels: ["Negative"]`, and
`qualifiedOnly` if that is all it rests on). Decide what your spaces mean, on their classes:
`_derived_meta = DerivedMeta(derivation="block")` to derive nothing from one, `"transparent"` to count it as nothing,
and `DerivedMeta(exclusive=True)` on an "or" (an `Alternative`), so that "Smith, who is A or B" does not make A and B
of one group.

## 8. Dates, and lists

A variable can be a date (`d: Var[Date]`, with `pangloss-dates`), and `overlaps(d1, d2)`, `before(d1, d2)`,
`within(d1, d2, days=365)` compare two of them: "held office at the same time", "within a year of each other". It can
also be one item of a list field (`Person.Where(is_=a, aliases=name)`): two people with an alias in common.

## 9. A network

Give rules a type, `@rule(types=[family])` with `family = RuleType("family")`, and `pangloss derive graph family --csv`
is an edge list of everything the rules of that type derive, for Gephi or networkx.
