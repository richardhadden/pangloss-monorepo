# pangloss-derived

Derived relations: rules that make new facts from what documents say ("X and Y are members of the same family", from two
factoids that each speak of one person), stored as nodes connecting entities, each with its justifications ("why"), and
kept up to date by a worker in the background, so that saves stay fast and the derivations are eventually consistent.

```python
from pangloss_derived import Derived, RuleType, Var, rule

family = RuleType("family", "Ties of family")


class SameFamily(Derived):
    """Members of the same family"""

    _meta = Derived.Meta(symmetric=True)
    first: Person
    second: Person
    family: Group


@rule(types=[family])
def same_family(a: Var[Person], b: Var[Person], family: Var[Group]):
    return SameFamily.Derive(first=a, second=b, family=family).when(
        MemberOf.Where(member=a, group=family),
        MemberOf.Where(member=b, group=family),
    )
```

See [docs/derived.md](../../docs/derived.md) and the plan, [docs/derived-implementation.md](../../docs/derived-implementation.md).
