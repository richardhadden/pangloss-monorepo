"""The names and the parameters of a query"""

import typing

from pangloss_cypher.values import convert_type_for_writing


class Identifier(str):
    """A name in a query, for a variable or a parameter. Made by `QueryParams.new_identifier`."""


class QueryParams(dict[Identifier, dict[str, typing.Any] | typing.Any]):
    """The parameters of a query, by name, and the names of a query.

    The names are `x1`, `x2`... in the order they are made in, so a query of the same shape has the
    same text each time and Memgraph, which keeps the plan of a query by its text, plans it once
    (names that were made at random were planned afresh every time)."""

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        super().__init__(*args, **kwargs)
        self._made = 0

    def new_identifier(self) -> Identifier:
        self._made += 1
        return Identifier(f"x{self._made}")

    def add(self, item: dict[str, typing.Any] | typing.Any) -> Identifier:
        identifier = self.new_identifier()
        self.__setitem__(identifier, convert_type_for_writing(item))
        return identifier
