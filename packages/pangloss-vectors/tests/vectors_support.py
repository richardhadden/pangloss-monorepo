"""What the tests of `pangloss-vectors` share: a part that computes nothing, of a dimension a test can change"""

import typing

from pangloss_vectors import Changed, Refreshed, signature_of


class SizedPart:
    """A part that computes nothing: a dimension and a setting of its signature that a test can change"""

    def __init__(self, name: str, dimension: int = 3, weight: float = 1.0):
        self.name = name
        self.local = True
        self.requires = frozenset({"cypher"})
        self.weight = weight
        self.size = dimension
        self.setting: typing.Any = None

    def __repr__(self) -> str:
        return f"SizedPart({self.name!r}, {self.size})"

    def dimension(self) -> int:
        return self.size

    def signature(self) -> str:
        return signature_of(self.size, self.setting)

    async def rebuild(self, write) -> int:
        return 0

    async def refresh(self, changed: Changed, write) -> Refreshed:
        return Refreshed()

    async def overlay(self, plan) -> dict:
        return {}
