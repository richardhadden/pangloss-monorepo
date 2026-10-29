# pangloss-typology

Typologies: a vocabulary of types arranged in a hierarchy (`secretary` is a subtype of `court official`), given to entities
with a `has_type` relation. See [docs/typology-implementation.md](../../docs/typology-implementation.md).

```python
from pangloss_typology import Typed, Typology, TypologyMeta


class Role(Entity):
    has_type: list[Typed[RoleTypology]]


class RoleTypology(Typology):
    _typology_meta = TypologyMeta(name="RoleType")
```
