"""How Neo4j finds some of what a structured search tests (`pangloss_cypher.search_query`): what is related to given ids,
or to what fits a pattern, is found once, before the `MATCH`, from the ids back along the edges; tested from each node,
Neo4j's planner looked the targets up again for each node. The rest is the kit's."""

from pangloss_models.search import (
    CheckedCondition,
    CheckedPattern,
    SearchKey,
)

from pangloss_cypher import fragments
from pangloss_cypher.search_query import Compiler, wrapper
from pangloss_neo4j.databases.neo4j.traversal import hops


def through(name: str, backwards: bool = False) -> str:
    """Any number of wrappers (a semantic space, a conjunction, a reified relation), the path continuing only through them"""
    return hops(name, wrapper(f"{name}_to"), minimum=0, backwards=backwards)


class Neo4jCompiler(Compiler):
    CREATION = "(creation:PGCreation)-[:is_creation_of]->(n)"

    def relation(self, c: CheckedCondition, var: str) -> str:
        if c.field == SearchKey.MENTIONS and c.operator in ("is", "is_any"):
            return self.mentioned_in_document(c, var)
        return super().relation(c, var)

    def mentioned_in_document(self, c: CheckedCondition, var: str) -> str:
        """Whether the head node or a node of its document has a relation to one of the ids. The documents that have one
        are found once, from the ids (which an index finds) back along the edges to the nodes of the documents, in a subquery
        before the `MATCH`, and the test is whether the document's id is among them. (Tested from each document, the same
        edges of the ids were read again for each: 1.2 million hits for 6,000 factoids.)"""
        wanted = self.param(c.value if c.operator == "is_any" else [c.value])
        m, t, e = self.name("m"), self.name("t"), self.name("e")
        where = [f"{t}.id IN {wanted}", f"NOT coalesce({e}.reverse, false)"]
        branches: list[str] = []
        if not c.through:
            direct = list(where)
            if c.wrapped:
                direct.append(f"NOT {wrapper(t)}")
            branches.append(
                f"MATCH ({t}:PGIndexableNode)<-[{e}]-({m}:PGIndexableNode) WHERE {' AND '.join(direct)} "
                f"RETURN coalesce({m}.head_node_id, {m}.id) AS head_id"
            )
        if c.wrapped or c.through:
            w, x, r, p, q = (self.name(n) for n in ("w", "x", "r", "p", "q"))
            via = [
                *where,
                wrapper(w),
                wrapper(x),
                f"NOT coalesce({r}.reverse, false)",
            ]
            if c.through:
                via.append(
                    f"all(s IN {self.param(list(c.through))} WHERE any(nd IN nodes({p}) WHERE s IN labels(nd)))"
                )
            branches.append(
                f"MATCH {p} = ({t}:PGIndexableNode)<-[{r}]-({x}) {through(q, backwards=True)} ({w})<-[{e}]-({m}:PGIndexableNode) "
                f"WHERE {' AND '.join(via)} RETURN coalesce({m}.head_node_id, {m}.id) AS head_id"
            )
        heads = self.name("heads")
        self.preludes.append(
            (
                f"CALL {{ CALL {{ {' UNION '.join(branches)} }} RETURN collect(DISTINCT head_id) AS {heads} }}",
                heads,
            )
        )
        return f"{var}.id IN {heads}"

    def related_to_targets(
        self, c: CheckedCondition, var: str, through_wrappers: bool
    ) -> str:
        """Whether the node has the relation `c.field` to what the condition says: one of the ids (`is`, `is_any`), or a node
        that fits a pattern (`match`). The nodes that have it are found once, from the targets (an index finds the ids; a
        pattern is a scan of its class, once) back along the edges, in a subquery before the `MATCH`, and the test is whether
        the node's id is among them. (Tested from each node, the target was looked up again for each: 6,000 times for 6,000
        factoids.)"""
        e, t, y = self.name("e"), self.name("t"), self.name("y")
        field = f"`{c.field}`"
        before = len(self.preludes)
        if c.operator == "match":
            pattern: CheckedPattern = c.value
            # (with `PGIndexableNode`, so that a test of the id, if the pattern has one, is an index seek)
            label = f"PGIndexableNode:`{pattern.model.__name__}`"
            found = self.target(c, t)
        else:
            label = "PGIndexableNode"
            wanted = self.param(c.value if c.operator == "is_any" else [c.value])
            found = f"{t}.id IN {wanted}"
        # (what the pattern's own tests need is made first, inside this subquery: they are not seen from outside it)
        needed = self.preludes[before:]
        del self.preludes[before:]
        if not through_wrappers:
            where = [found]
            if (
                c.wrapped
            ):  # (a wrapper is not what the relation is to: what is in it is)
                where.append(f"NOT {wrapper(t)}")
            body = (
                f"MATCH ({t}:{label})<-[{e}:{field}]-({y}) WHERE {' AND '.join(where)}"
            )
        else:
            # (a path of wrappers from the first, and then one edge to what is in the last: walked from the end)
            w, x, r, p, q = (self.name(n) for n in ("w", "x", "r", "p", "q"))
            where = [found, wrapper(w), wrapper(x), f"NOT coalesce({r}.reverse, false)"]
            if c.through:
                where.append(
                    f"all(s IN {self.param(list(c.through))} WHERE any(nd IN nodes({p}) WHERE s IN labels(nd)))"
                )
            body = (
                f"MATCH {p} = ({t}:{label})<-[{r}]-({x}) {through(q, backwards=True)} ({w})<-[{e}:{field}]-({y}) "
                f"WHERE {' AND '.join(where)}"
            )
        related = self.name("related")
        self.preludes.append(
            (
                f"CALL {{ {' '.join(text for text, _ in needed)} {body} RETURN collect(DISTINCT {y}.id) AS {related} }}",
                related,
            )
        )
        return f"{var}.id IN {related}"

    def reaching(self, c: CheckedCondition, var: str, through_wrappers: bool) -> str:
        if c.operator in ("is", "is_any", "match") and c.field not in (
            SearchKey.ANY,
            SearchKey.MENTIONS,
        ):
            return self.related_to_targets(c, var, through_wrappers)
        return super().reaching(c, var, through_wrappers)

    def not_in_hidden_document(self, s: str) -> str:
        """Its head node is looked up by the id it records. (Going up to it along the reverse edges read 222,000 hits for
        6,500 activities)"""
        h = self.name("h")
        return (
            f"NOT EXISTS {{ MATCH ({h}:HeadNode {{id: coalesce({s}.head_node_id, {s}.id)}}) "
            f"WHERE {fragments.hidden(h)} }}"
        )
