"""The models of the library: `WeightedAlternative[Person]` is one of several people, not known which, each with
how likely it is the one meant, in per cent (the percentages add up to 100, and the interface keeps them to it)"""

from typing import Annotated

from annotated_types import Ge, Le, MinLen
from pangloss_interface import Slider
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.validators import SumsTo


class Likelihood(EdgeModel):
    """How likely it is that this is the one meant, out of the alternatives (1 to 100, in per cent)"""

    percent: Annotated[int, Ge(1), Le(100), Slider()]


class WeightedAlternative[T](Conjunction):
    """One of several things, not known which, each with how likely it is the one meant: the percentages add up
    to 100"""

    alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]
