"""The models of the library: `WeightedAlternative[Person]` is one of several people, not known which, each with
how likely it is the one meant, in per cent (the percentages add up to 100, and the interface keeps them to it)"""

from typing import Annotated

from annotated_types import Ge, Le, MinLen
from pangloss_derived import DerivedMeta
from pangloss_interface import InterfaceMeta, Slider
from pangloss_models import Conjunction, EdgeModel, SumsTo, ViaEdge


class Likelihood(EdgeModel):
    """How likely it is that this is the one meant, out of the alternatives (1 to 100, in per cent)"""

    percent: Annotated[int, Ge(1), Le(100), Slider(unit="%")]


class WeightedAlternative[T](Conjunction):
    """One of several things, not known which, each with how likely it is the one meant: the percentages add up
    to 100"""

    # (one of them, not known which: a derived relation takes one alternative at a time, never two together)
    _derived_meta = DerivedMeta(exclusive=True)
    # (on the item page, its own card: no head, each with its likelihood at the end of its chip, the name of the
    # field only for several; in the form, the sliders)
    _interface_meta = InterfaceMeta(
        collapse=True, view_card="pangloss_library:WeightedAlternativeCard"
    )

    alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]
