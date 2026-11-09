"""Where a conversion is: given to a package's converter"""

from dataclasses import dataclass

from pangloss_rdf.terms import IRI, Lit, Quad


@dataclass(frozen=True)
class Context:
    graph: IRI
    spaces: tuple[IRI, ...] = ()
    """The semantic spaces around this node, outermost first: what is inside one is not asserted"""

    def quad(self, subject: IRI, predicate: IRI, object: IRI | Lit) -> Quad:
        return Quad(subject, predicate, object, self.graph)

    @property
    def asserted(self) -> bool:
        return not self.spaces
