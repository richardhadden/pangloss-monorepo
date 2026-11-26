"""Where a conversion is: given to a package's converter"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property

from pangloss_models.context import PathEntry
from pangloss_models.spaces import SpaceFacts, signature

from pangloss_rdf.terms import IRI, Lit, Quad


@dataclass(frozen=True)
class Context:
    graph: IRI
    spaces: tuple[IRI, ...] = ()
    """The semantic spaces around this node, outermost first"""
    path: tuple[PathEntry, ...] = ()
    """The node's path as the converter has walked it (`PathEntry`s, outermost first, as `meta.path` is stored)"""
    known: Mapping[str, SpaceFacts] | None = None
    """What each space class says of its contents (`pangloss_models.spaces.registered_spaces()`, made once a
    conversion)"""

    def quad(self, subject: IRI, predicate: IRI, object: IRI | Lit) -> Quad:
        return Quad(subject, predicate, object, self.graph)

    @cached_property
    def asserted(self) -> bool:
        """Whether the node is asserted, and so has its direct triples: in no space, or where the walk over its path
        says so (`pangloss_models.spaces.signature`: `Known[...]`, `Not[Not[...]]`). A context made with spaces and
        no path (by hand, as a converter's test may) is not asserted"""
        if not self.spaces:
            return True
        if not self.path:
            return False
        return signature(self.path, self.known).veridical == 1
