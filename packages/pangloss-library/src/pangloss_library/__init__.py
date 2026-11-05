"""Ready-made models for Pangloss (an app: `INSTALLED_APPS += ["pangloss_library"]`, for its migrations)"""

lazy from pangloss_library.models import Likelihood, WeightedAlternative

__all__ = ["Likelihood", "WeightedAlternative"]
