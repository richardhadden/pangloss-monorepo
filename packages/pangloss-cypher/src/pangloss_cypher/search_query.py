"""The query for a structured search (see implementation_docs/structured-search.md): the checked conditions of a pattern,
made into one Cypher query. Only names the models have (the class and its fields, which are checked first)
are put in the text; every value is a parameter.

The backend's dialect gives the paths through wrappers and the `meta` of a node, and may give a subclass of `Compiler` that
finds some of what is tested in another way, for its planner (`Dialect.search_compiler`)."""

from typing import LiteralString, cast

from pangloss_models import AnyOf, Document, Entity, Not
from pangloss_models.search import (
    WRAPPER_LABELS,
    CheckedCondition,
    CheckedIncoming,
    CheckedOrder,
    CheckedPattern,
    Expr,
    SearchKey,
)

from pangloss_cypher import fragments
from pangloss_cypher.transactions import dialect
from pangloss_cypher.values import convert_type_for_writing
from pangloss_cypher.visibility import unpublished_visible

COMPARISONS = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class Compiler:
    """Makes the expressions of a pattern into one Cypher test of a node (a variable). Each value is a
    parameter; each relation is an `EXISTS` subquery, so that it can be negated and or-ed."""

    # How the creation record of a node of the page is found
    CREATION = "(n)<-[:is_creation_of]-(creation:PGCreation)"

    def __init__(self, params: dict):
        self.params = params
        self.targets = 0
        self.preludes: list[tuple[str, str]] = []
        """Subqueries that go before the `MATCH` of the pattern, each as (its text, the name of the one list it gives for the
        tests to look in): what is found once for the whole search, not again for each node it is tested of. (None, here:
        a subclass may make them)"""

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
        if c.kind == "extension":
            # (a key an optional package added: it compiles its own condition; see `pangloss_models.search.Extension`)
            return c.value.cypher(self, var)
        if c.kind == "spaces":
            # (the spaces a node is inside are kept in its `meta`)
            return f"all(s IN {self.param(c.value)} WHERE s IN coalesce({dialect().meta_property(var, 'semantic_spaces')}, []))"
        # (what is left tests a property of the node; `ne` includes what has no value: "not draft" is what it means)
        prop = f"{var}.{fragments.property_name(c.field)}"
        if c.field == "published":  # (a document with no property is published)
            prop = f"coalesce({prop}, true)"
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

    def in_document(self, head: str, node: str, label: str = "") -> str:
        """A pattern for the nodes of a document (not its head node), found by their `head_node_id`. Memgraph 3.14
        uses the index on `PGIndexableNode(head_node_id)` for this inside an `EXISTS`, if the pattern has the
        label (3.13 scanned every node for each document: it is why this once went down from the head node)."""
        return (
            f"({node}:PGIndexableNode{':' + fragments.label(label) if label else ''} "
            f"{{head_node_id: {head}.id}})"
        )

    def relation(self, c: CheckedCondition, var: str) -> str:
        """Whether the node has a relation that is as the condition says. A relation to wrappers (a semantic
        space, a conjunction, a reified relation) is also to what is inside them, however deep; and one that
        has to pass through some is only that. `$mentions` is of the node or of any node of its document."""
        if c.field == SearchKey.MENTIONS:
            node = self.name("m")
            return (
                f"({self.relation_of(c, var)} OR "
                f"EXISTS {{ MATCH {self.in_document(var, node)} "
                f"WHERE {self.relation_of(c, node)} }})"
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
        if c.field in (SearchKey.ANY, SearchKey.MENTIONS):
            edge = f"({var})-[{e}]->({w})"
            where.append(f"NOT coalesce({e}.reverse, false) AND {w}:PGIndexableNode")
        else:
            edge = f"({var})-[{e}:{fragments.field_edge(c.field)}]->({w})"
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
        x, r, t, p = (self.name(n) for n in ("x", "r", "t", "p"))
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
            f"MATCH {p} = {edge}{dialect().through_wrappers(self.name('q'))}({x})-[{r}]->({t}) "
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
        types = "|".join(fragments.field_edge(name) for name in incoming.fields)

        def source_tests(s: str) -> str:
            tests = [fragments.not_deleted(s), self.all_of(pattern.items, s)]
            if not issubclass(pattern.model, Entity):
                # (nor does a document inside a deleted head document)
                tests.append(self.not_in_hidden_document(s))
            return " AND ".join(tests)

        s, e = self.name("s"), self.name("e")
        label = pattern.model.__name__
        direct = (
            f"EXISTS {{ MATCH ({var})<-[{e}:{types}]-({s}:{fragments.label(label)}) "
            f"WHERE {source_tests(s)} }}"
        )
        if not c.wrapped:
            return direct
        s, e = self.name("s"), self.name("e")
        w, x, r, p, q = (self.name(n) for n in ("w", "x", "r", "p", "q"))
        where = [wrapper(w), wrapper(x), f"NOT coalesce({r}.reverse, false)"]
        if c.through:
            where.append(
                f"all(n IN {self.param(list(c.through))} WHERE any(nd IN nodes({p}) WHERE n IN labels(nd)))"
            )
        where.append(source_tests(s))
        via = (
            f"EXISTS {{ MATCH {p} = ({var})<-[{r}]-({x}){dialect().through_wrappers(q, backwards=True)}({w})"
            f"<-[{e}:{types}]-({s}:{fragments.label(label)}) WHERE {' AND '.join(where)} }}"
        )
        return via if c.through else f"({direct} OR {via})"

    def not_in_hidden_document(self, s: str) -> str:
        """Whether the node is not in a head document that is hidden: going up to it, along the reverse edges"""
        h, q = self.name("h"), self.name("q")
        return (
            f"NOT EXISTS {{ MATCH ({s}){dialect().up_reverse(q, minimum=0)}({h}:HeadNode) "
            f"WHERE {fragments.hidden(h)} }}"
        )

    def target(self, c: CheckedCondition, t: str) -> str:
        """The test of what a relation points at"""
        if c.operator == "match":
            pattern: CheckedPattern = c.value
            tests = self.all_of(pattern.items, t)
            if issubclass(pattern.model, Entity):  # (a deleted entity is not found)
                tests = f"{fragments.not_deleted(t)} AND {tests}"
            return f"{t}:{fragments.label(pattern.model.__name__)} AND {tests}"
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
            finding.append(
                f"OPTIONAL MATCH ({var})-[:{fragments.field_edge(step)}]->({nxt})"
            )
            var = nxt
        value = f"{var}.{fragments.property_name(key.field)}"
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
    used_only: bool = False,
) -> tuple[LiteralString, dict]:
    params: dict = {
        "page": page_number,
        "page_size": page_size,
        "see_unpublished": unpublished_visible(),
    }
    compiler: Compiler = dialect().search_compiler(params)
    tests = compiler.all_of(conditions, "n")
    finding, keys, sorting = ordering(compiler, order or [])

    kind = "HeadNode" if issubclass(model, Document) else "Entity"
    where = f"{fragments.visible('n')} AND {tests}"
    prelude = "\n    ".join(text for text, _ in compiler.preludes)
    query = f"""
    {prelude}
    MATCH (n:{fragments.label(model.__name__)}:{kind})
    WHERE {where}
    {fragments.only_used("n") if used_only else ""}
    {finding}
    WITH n{keys}
    ORDER BY {sorting}toLower(n.label), {dialect().tie_break("n")}
    WITH collect(n) AS allNodes
    WITH allNodes, size(allNodes) AS total,
         toInteger(ceil(toFloat(size(allNodes)) / $page_size)) AS totalPages
    WITH allNodes[($page - 1) * $page_size .. $page * $page_size] AS pageNodes,
         total, totalPages
    CALL {{
        WITH pageNodes
        UNWIND pageNodes AS n
        OPTIONAL MATCH {compiler.CREATION}
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


def build_field_types_query(
    model: type[Document | Entity],
    field: str,
    conditions: list[Expr],
    head: bool,
) -> tuple[LiteralString, dict]:
    """What the relation `field` of the nodes of `model` that fit the conditions points at: each concrete type found,
    through wrappers (what is in a `Negative`, not the `Negative`), and how many of the nodes point at one. `head`: the
    nodes are head documents or entities (as a search finds); otherwise parts of documents, of any document the reader
    sees. (For the search form, to offer only the types there are.)"""
    params: dict = {"see_unpublished": unpublished_visible()}
    compiler: Compiler = dialect().search_compiler(params)
    tests = compiler.all_of(conditions, "n")
    if head:
        kind = ":HeadNode" if issubclass(model, Document) else ":Entity"
        seen = fragments.visible("n")
    else:
        kind = ""
        seen = (
            f"{fragments.not_deleted('n')} AND {compiler.not_in_hidden_document('n')}"
        )
    prelude = "\n    ".join(text for text, _ in compiler.preludes)
    query = f"""
    {prelude}
    MATCH (n:{fragments.label(model.__name__)}{kind})
    WHERE {seen} AND {tests}
    MATCH (n)-[:{fragments.field_edge(field)}]->(first){dialect().from_wrappers("fw")}(t)
    WHERE NOT {wrapper("t")} AND {fragments.not_deleted("t")}
    WITH t.type AS type, count(DISTINCT n) AS count
    RETURN type, count
    ORDER BY type
    """
    return cast(LiteralString, query), params
