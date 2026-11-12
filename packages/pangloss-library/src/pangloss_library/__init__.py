"""Ready-made models for Pangloss (an app: `INSTALLED_APPS += ["pangloss_library"]`, for its migrations)"""

lazy from pangloss_library.identity import IdentityClaim
lazy from pangloss_library.models import (
    Identification,
    IdentificationByToolchain,
    Likelihood,
    SameEntity,
    WeightedAlternative,
)

__all__ = [
    "Identification",
    "IdentityClaim",
    "IdentificationByToolchain",
    "Likelihood",
    "SameEntity",
    "WeightedAlternative",
]
