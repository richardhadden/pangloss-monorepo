# pangloss-library

Ready-made models for Pangloss, built from its primitives.

- `WeightedAlternative[T]` (a `Conjunction`): one of several things, not known which, each with how likely it
  is the one meant, and exclusive for derived relations (one at a time). `alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]`.
- `Likelihood` (an `EdgeModel`): `percent`, 1 to 100, edited with a slider.

On an item's page a `WeightedAlternative` has its own card (its interface module, `pangloss_library:WeightedAlternativeCard`):
no head, each alternative with its likelihood at the end of its chip ("19%"), and the name of the field only when
there are several. The library has the translations of its models (`translations/models.jsonc`: "% likelihood"); a
project changes them in its own overrides.

The percentages add up to 100: the server refuses what does not, and the interface keeps them to it (dragging
one, the others give way in proportion; one added is given an even share; one taken away, the others share
the whole).

```python
INSTALLED_APPS = [..., "pangloss_library"]
```

```python
from pangloss_library import WeightedAlternative


class Statement(Document):
    suspect: WeightedAlternative[Person]
```

The same can be declared in a project with the primitives (another name, another edge model):

```python
from pangloss_interface import Slider
from pangloss_models import SumsTo


class Probability(EdgeModel):
    percent: Annotated[int, Ge(1), Le(100), Slider()]


class Alternative[T](Conjunction):
    alternatives: Annotated[list[ViaEdge[T, Probability]], SumsTo("percent")]
```

See implementation_docs/shares-plan.md.
