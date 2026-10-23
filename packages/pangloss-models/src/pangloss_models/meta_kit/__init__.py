"""Meta objects on Pydantic classes, inherited by rules (`WithMeta`, `BaseMeta`, ...).

Vendored from pydantic-meta-kit (https://github.com/richardhadden/pydantic-meta-kit, commit
6f8ea9c), so that `pangloss-models` has no dependency that cannot be published. Changes are
made here now.
"""

from pangloss_models.meta_kit.meta import BaseMeta, InheritValue, MetaRules, WithMeta

__all__ = ("BaseMeta", "MetaRules", "InheritValue", "WithMeta")
