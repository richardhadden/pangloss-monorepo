"""Where a conversion is: given to a package's converter"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property

from pangloss_models.context import PathEntry
from pangloss_models.spaces import GroundFacts, SpaceFacts, ground_at, signature

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

    grounds: Mapping[str, GroundFacts] | None = None
    """The ground of each head class (`pangloss_models.spaces.registered_grounds()`, made once a conversion). None
    (a context made by hand): every head asserts what it holds"""
    head_type: str | None = None
    """The class of the head being converted, by name: the head itself has no path to say it"""

    def quad(self, subject: IRI, predicate: IRI, object: IRI | Lit) -> Quad:
        return Quad(subject, predicate, object, self.graph)

    @cached_property
    def asserted(self) -> bool:
        """Whether the node is asserted, and so has its outside classes and direct triples: where the walk over its
        path says so (`pangloss_models.spaces.signature`), from the ground of its head. So in no space under a head
        whose class asserts what it holds (as every class does that says nothing), and in `Known[...]` or
        `Not[Not[...]]` there; nowhere under a head whose ground leaves what it holds neither asserted nor denied
        (a rumour). The head itself is asserted whatever its ground: that there is a rumour is not rumoured (what
        it holds is another question: `holds`). A context made with spaces and no path (by hand, as a converter's
        test may) is not asserted"""
        if self.spaces and not self.path:
            return False
        grounds = self.grounds or {}
        if not self.spaces:
            ground = ground_at(list(self.path), grounds)
            if ground is None or ground["veridical"] == 1:
                return True
        return signature(self.path, self.known, grounds).veridical == 1

    def holds(self, field: str) -> bool:
        """Whether what the node holds itself in `field` is asserted, and so has its direct triple and outside
        properties. For a node below the head: where the node is (`asserted`). For the head: where its class's
        ground asserts what it holds, and always for the field the ground names as whose commitment it is
        (`Ground(by=...)`: that the rumour is this person's is not rumoured)"""
        ground = (self.grounds or {}).get(self.head_type or "")
        if self.path or self.spaces or ground is None:
            return self.asserted
        if ground["by"] is not None and ground["by"]["name"] == field:
            return True
        return ground["veridical"] == 1
