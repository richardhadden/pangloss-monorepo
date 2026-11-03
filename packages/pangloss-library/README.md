# pangloss-library

Ready-made models for Pangloss, built from its primitives.

- `WeightedAlternative[T]` (a `Conjunction`): one of several things, not known which, each with how likely it
  is the one meant. `alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]`.
- `Likelihood` (an `EdgeModel`): `percent`, 1 to 100, edited with a slider.

The percentages add up to 100: the server refuses what does not, and the interface keeps them to it (dragging
one, the others give way in proportion; one added is given an even share; one taken away, the others share
the whole).

```python
INSTALLED_APPS = [..., "pangloss_library"]
```

```python
from pangloss_library.models import WeightedAlternative

class Statement(Document):
    suspect: WeightedAlternative[Person]
```

The same can be declared in a project with the primitives (another name, another edge model):

```python
from pangloss_interface import Slider
from pangloss_models.validators import SumsTo

class Probability(EdgeModel):
    percent: Annotated[int, Ge(1), Le(100), Slider()]

class Alternative[T](Conjunction):
    alternatives: Annotated[list[ViaEdge[T, Probability]], SumsTo("percent")]
```

See docs/shares-plan.md.
