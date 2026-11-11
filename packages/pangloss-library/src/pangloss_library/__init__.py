"""Ready-made models for Pangloss (an app: `INSTALLED_APPS += ["pangloss_library"]`, for its migrations)"""

lazy from pangloss_library.models import (
    Identification,
    IdentificationByToolchain,
    Likelihood,
    WeightedAlternative,
)

__all__ = [
    "Identification",
    "IdentificationByToolchain",
    "Likelihood",
    "WeightedAlternative",
]
