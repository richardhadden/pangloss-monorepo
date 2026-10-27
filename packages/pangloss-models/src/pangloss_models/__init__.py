from pangloss_models.model_registry import ModelRegistry

initialise = ModelRegistry.finalise
from pangloss_models import protection as protection  # (registers the `_protect_meta` slot)
from pangloss_models.server_only import server_only as server_only
