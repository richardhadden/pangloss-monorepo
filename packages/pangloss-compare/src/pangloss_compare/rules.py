"""Each compared class's `CompareMeta` as the verdict takes it (`maths.Rules`), worked out of the models"""

from pangloss_compare import maths
from pangloss_compare.meta import compared_classes


def rules() -> dict[str, maths.Rules]:
    """The rules of every compared class (`meta.compared_classes`), by name: what `maths.verdict` is given"""
    return {
        name: maths.Rules(
            tuple(dict.fromkeys(meta.identifying)), meta.once_per, meta.recurs
        )
        for name, meta in compared_classes().items()
    }
