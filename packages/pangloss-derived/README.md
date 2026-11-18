# pangloss-derived

Derived relations: rules that make edges between entities from what documents say ("X and Y are members of the same
family", from two factoids that each speak of one person), each edge with two ends and the qualifiers that define it, each with its justifications ("why"), and
kept up to date by a worker in the background, so that saves stay fast and the derivations are eventually consistent.

```python
from pangloss_derived import DerivedEdge, RuleType, SymmetricLabel, Var, rule

family = RuleType("family", "Ties of family")


class SameFamily(DerivedEdge):
    """Members of the same family"""

    _meta = DerivedEdge.Meta(symmetric=True)
    first: Annotated[Person, SymmetricLabel("member")]
    second: Annotated[Person, SymmetricLabel("member")]
    family: Group


@rule(types=[family])
def same_family(a: Var[Person], b: Var[Person], family: Var[Group]):
    return SameFamily.Derive(first=a, second=b, family=family).when(
        MemberOf.Where(member=a, group=family),
        MemberOf.Where(member=b, group=family),
    )
```

See [implementation_docs/derived.md](../../implementation_docs/derived.md).
