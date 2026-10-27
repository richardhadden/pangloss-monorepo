"""The query for a structured search (see docs/structured-search.md): the checked conditions of a pattern,
made into one Cypher query. Only names the models have (the class and its fields, which are checked first)
are put in the text; every value is a parameter."""

from typing import LiteralString, cast

from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.search import (
    ANY_IN_DOCUMENT,
    ANY_RELATION,
    WRAPPER_LABELS,
    AnyOf,
    CheckedCondition,
    CheckedIncoming,
    CheckedOrder,
    CheckedPattern,
    Expr,
    Not,
)

from pangloss_memgraph.databases.memgraph.build_create_query import (
    convert_type_for_writing,
)
from pangloss_memgraph.databases.memgraph.visibility import unpublished_visible

COMPARISONS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class Compiler:
    """Makes the expressions of a pattern into one Cypher test of a node (a variable). Each value is a
    parameter; each relation is an `EXISTS` subquery, so that it can be negated and or-ed."""

    def __init__(self, params: dict):
        self.params = params
        self.targets = 0

    def param(self, value) -> str:
        name = f"p{len(self.params)}"
        self.params[name] = convert_type_for_writing(value)
        return f"${name}"

    def all_of(self, exprs: list[Expr], var: str) -> str:
        return " AND ".join(self.expr(e, var) for e in exprs) or "true"

    def expr(self, e: Expr, var: str) -> str:
        if isinstance(e, AnyOf):
            return (
                "(" + " OR ".join(f"({self.all_of(b, var)})" for b in e.branches) + ")"
            )
        if isinstance(e, Not):
            # (what has no value is not what was asked for: so it is not "not" it)
            return f"NOT coalesce(({self.all_of(e.items, var)}), false)"
        return self.condition(e, var)

    def condition(self, c: CheckedCondition, var: str) -> str:
        # (`ne` includes what has no value: "not draft" is what it means)
        prop = f"{var}.`{c.field}`"
        if c.kind == "relation":
            return self.relation(c, var)
        if c.kind == "somewhere":
            pattern: CheckedPattern = c.value
            node = self.name("m")
            return (
                f"EXISTS {{ MATCH {self.in_document(var, node, pattern.model.__name__)} "
                f"WHERE {self.all_of(pattern.items, node)} }}"
            )
        if c.kind == "incoming":
            return self.incoming(c, var)
        if c.kind == "spaces":
            # (the spaces a node is inside are kept in its `meta`)
            return f"all(s IN {self.param(c.value)} WHERE s IN coalesce({var}.meta.semantic_spaces, []))"
        if c.operator == "exists":
            return f"{prop} IS {'NOT ' if c.value else ''}NULL"
        if c.kind == "list":
            if c.operator == "contains":
                return f"{self.param(c.value)} IN {prop}"
            if c.operator == "contains_any":
                return f"any(x IN {self.param(c.value)} WHERE x IN {prop})"
            return f"all(x IN {self.param(c.value)} WHERE x IN {prop})"
        # (a Decimal is stored as a string: it is compared as a number, which is as exact as a float)
        left = f"toFloat({prop})" if c.kind == "decimal" else prop
        if c.kind == "text" and c.operator in ("contains", "starts_with"):
            word = "CONTAINS" if c.operator == "contains" else "STARTS WITH"
            return f"toLower({prop}) {word} {self.param(c.value)}"
        if c.operator == "in":
            return f"{left} IN {self.param(c.value)}"
        if c.operator == "between":
            low, high = c.value
            return f"({left} >= {self.param(low)} AND {left} <= {self.param(high)})"
        if c.operator == "ne":
            return f"({prop} IS NULL OR {left} <> {self.param(c.value)})"
        return f"{left} {COMPARISONS[c.operator]} {self.param(c.value)}"

    def name(self, base: str) -> str:
        """A variable of its own: those of the `EXISTS` inside one another must not be the same"""
        self.targets += 1
        return f"{base}{self.targets}"

    def in_document(
        self, head: str, node: str, label: str = "", zero: bool = False
    ) -> str:
        """A pattern for the nodes of a document, found by going down from its head node, along the edges
        of the document (the nodes with its id as their `head_node_id`, not along reverse edges). It is not a
        lookup of the nodes by `head_node_id`: inside an `EXISTS` Memgraph does not use the index for that,
        and scans every node for each document (8 seconds for 100 documents of 640,000 nodes; this is
        about 0.2 seconds for 30,000)."""
        r, v = self.name("r"), self.name("v")
        return (
            f"({head})-[*{'0' if zero else ''}.. ({r}, {v} | {v}.head_node_id = {head}.id "
            f"AND NOT coalesce({r}.reverse, false))]->({node}{':`' + label + '`' if label else ''})"
        )

    def relation(self, c: CheckedCondition, var: str) -> str:
        """Whether the node has a relation that is as the condition says. A relation to wrappers (a semantic
        space, a conjunction, a reified relation) is also to what is inside them, however deep; and one that
        has to pass through some is only that. `$mentions` is of the node or of any node of its document."""
        if c.field == ANY_IN_DOCUMENT:
            node = self.name("m")
            return (
                f"EXISTS {{ MATCH {self.in_document(var, node, zero=True)} "
                f"WHERE {self.relation_of(c, node)} }}"
            )
        return self.relation_of(c, var)

    def relation_of(self, c: CheckedCondition, var: str) -> str:
        direct = self.reaching(c, var, through_wrappers=False)
        if not c.wrapped or (c.operator == "exists" and not c.through):
            return direct
        via = self.reaching(c, var, through_wrappers=True)
        return via if c.through else f"({direct} OR {via})"

    def reaching(self, c: CheckedCondition, var: str, through_wrappers: bool) -> str:
        e, w = self.name("e"), self.name("w")
        where = ["true"]
        if c.field in (ANY_RELATION, ANY_IN_DOCUMENT):
            edge = f"({var})-[{e}]->({w})"
            where.append(f"NOT coalesce({e}.reverse, false) AND {w}:PGIndexableNode")
        else:
            edge = f"({var})-[{e}:`{c.field}`]->({w})"
        if not through_wrappers:
            if (
                c.wrapped and c.operator != "exists"
            ):  # (a wrapper is not what the relation is to: what is in it is)
                where.append(f"NOT {wrapper(w)}")
            if c.operator != "exists":
                where.append(self.target(c, w))
            elif not c.value:
                return f"NOT EXISTS {{ MATCH {edge} WHERE {' AND '.join(where)} }}"
            return f"EXISTS {{ MATCH {edge} WHERE {' AND '.join(where)} }}"
        # (through wrappers: a path of them from the first, and then one edge to what is in the last)
        x, r, v, t, p = (self.name(n) for n in ("x", "r", "v", "t", "p"))
        where += [
            wrapper(w),
            wrapper(x),
            f"NOT coalesce({r}.reverse, false)",
        ]
        if c.through:
            where.append(
                f"all(s IN {self.param(list(c.through))} WHERE any(nd IN nodes({p}) WHERE s IN labels(nd)))"
            )
        if c.operator != "exists":
            where.append(self.target(c, t))
        body = (
            f"MATCH {p} = {edge}-[* 0.. ({self.name('q')}, {v} | {wrapper(v)})]->({x})-[{r}]->({t}) "
            f"WHERE {' AND '.join(where)}"
        )
        if c.operator == "exists" and not c.value:
            return f"NOT EXISTS {{ {body} }}"
        return f"EXISTS {{ {body} }}"

    def incoming(self, c: CheckedCondition, var: str) -> str:
        """Whether a node of the pattern points at this one with one of the relations: directly, or through
        wrappers (which is what it does if its relation is to one, and what it must if `through` is given).
        The patterns start from this node and go back along its edges: written from the referring node,
        Memgraph scans every node of the class, for each node."""
        incoming: CheckedIncoming = c.value
        pattern = incoming.pattern
        types = "|".join(f"`{name}`" for name in incoming.fields)

        def source_tests(s: str) -> str:
            tests = [f"NOT coalesce({s}.deleted, false)", self.all_of(pattern.items, s)]
            if not issubclass(pattern.model, Entity):
                # (nor does a document inside a deleted head document: go up to it, along the reverse edges)
                h, q, v = self.name("h"), self.name("q"), self.name("v")
                tests.append(
                    f"NOT EXISTS {{ MATCH ({s})-[* 0.. ({q}, {v} | coalesce({q}.reverse, false))]->({h}:HeadNode) WHERE {h}.deleted OR NOT ($see_unpublished OR coalesce({h}.published, true)) }}"
                )
            return " AND ".join(tests)

        s, e = self.name("s"), self.name("e")
        label = pattern.model.__name__
        direct = (
            f"EXISTS {{ MATCH ({var})<-[{e}:{types}]-({s}:`{label}`) "
            f"WHERE {source_tests(s)} }}"
        )
        if not c.wrapped:
            return direct
        s, e = self.name("s"), self.name("e")
        w, x, r, v, p, q = (self.name(n) for n in ("w", "x", "r", "v", "p", "q"))
        where = [wrapper(w), wrapper(x), f"NOT coalesce({r}.reverse, false)"]
        if c.through:
            where.append(
                f"all(n IN {self.param(list(c.through))} WHERE any(nd IN nodes({p}) WHERE n IN labels(nd)))"
            )
        where.append(source_tests(s))
        via = (
            f"EXISTS {{ MATCH {p} = ({var})<-[{r}]-({x})<-[* 0.. ({q}, {v} | {wrapper(v)})]-({w})"
            f"<-[{e}:{types}]-({s}:`{label}`) WHERE {' AND '.join(where)} }}"
        )
        return via if c.through else f"({direct} OR {via})"

    def target(self, c: CheckedCondition, t: str) -> str:
        """The test of what a relation points at"""
        if c.operator == "match":
            pattern: CheckedPattern = c.value
            tests = self.all_of(pattern.items, t)
            if issubclass(pattern.model, Entity):  # (a deleted entity is not found)
                tests = f"NOT coalesce({t}.deleted, false) AND {tests}"
            return f"{t}:`{pattern.model.__name__}` AND {tests}"
        wanted = c.value if c.operator == "is_any" else [c.value]
        return f"{t}.id IN {self.param(wanted)}"


def wrapper(var: str) -> str:
    return "(" + " OR ".join(f"{var}:{label}" for label in WRAPPER_LABELS) + ")"


def ordering(compiler: Compiler, order: list[CheckedOrder]) -> tuple[str, str, str]:
    """What the results are ordered by: the `OPTIONAL MATCH` that finds the embedded objects the values are in
    (a node without one is not left out), the values, and the `ORDER BY` (nodes with no value last, whichever way)"""
    finding: list[str] = []
    keys: list[str] = []
    sorting: list[str] = []
    for index, key in enumerate(order):
        var = "n"
        for step in key.path:
            nxt = compiler.name("o")
            finding.append(f"OPTIONAL MATCH ({var})-[:`{step}`]->({nxt})")
            var = nxt
        value = f"{var}.`{key.field}`"
        if key.kind == "text":
            value = f"toLower({value})"
        keys.append(f"{value} AS order{index}")
        sorting.append(
            f"(order{index} IS NULL), order{index}{' DESC' if key.descending else ''}, "
        )
    return (
        "\n    ".join(finding),
        "".join(f", {k}" for k in keys),
        "".join(sorting),
    )


def build_search_query(
    model: type[Document | Entity],
    conditions: list[Expr],
    page_number: int,
    page_size: int,
    order: list[CheckedOrder] | None = None,
) -> tuple[LiteralString, dict]:
    params: dict = {
        "page": page_number,
        "page_size": page_size,
        "see_unpublished": unpublished_visible(),
    }
    compiler = Compiler(params)
    tests = compiler.all_of(conditions, "n")
    finding, keys, sorting = ordering(compiler, order or [])

    kind = "HeadNode" if issubclass(model, Document) else "Entity"
    where = f"NOT coalesce(n.deleted, false) AND ($see_unpublished OR coalesce(n.published, true)) AND {tests}"
    query = f"""
    MATCH (n:`{model.__name__}`:{kind})
    WHERE {where}
    {finding}
    WITH n{keys}
    ORDER BY {sorting}toLower(n.label), id(n)
    WITH collect(n) AS allNodes
    WITH allNodes, size(allNodes) AS total,
         toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
    WITH allNodes[($page - 1) * $page_size .. $page * $page_size] AS pageNodes,
         total, totalPages
    CALL {{
        WITH pageNodes
        UNWIND pageNodes AS n
        OPTIONAL MATCH (creation:PGCreation)-[:is_creation_of]->(n)
        OPTIONAL MATCH (creation)-[:created_by]->(user:PGUser)
        RETURN collect(n{{.*, meta: {{
            created_by: user.username,
            created_when: creation.created_when,
            updated_by: null,
            updated_when: null,
            semantic_spaces: n.semantic_spaces,
            context_labels: n.context_labels,
            published: coalesce(n.published, true),
            review_status: n.review_status
        }}}}) AS items
    }}
    RETURN {{
        results: items,
        count: total,
        page: $page,
        page_size: $page_size,
        page_count: totalPages,
        previous_page: CASE WHEN $page > 1 THEN $page - 1 ELSE null END,
        next_page: CASE WHEN $page < totalPages THEN $page + 1 ELSE null END
    }} AS response
    """
    return cast(LiteralString, query), params
