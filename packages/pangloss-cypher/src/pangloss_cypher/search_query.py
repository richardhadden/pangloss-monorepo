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
    CheckedEdge,
    CheckedIncoming,
    CheckedOrder,
    CheckedPattern,
    CheckedStep,
    CheckedVia,
    Expr,
    SearchKey,
    head_conditions,
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
        self.excluded: tuple[str, ...] = ()
        """The wrappers no relation of the search passes through (`Match.exclude_wrappers`). An extension reads it
        too, for what it finds by ways of its own"""
        self._excluded_param: str | None = None
        self.local = False
        """Whether what is being compiled is asked of a node named inside another test (a wrapper of a path), so that
        nothing of it can be found before the `MATCH` (a prelude)"""
        self.holder = "$"
        """What a value is read from in the text: a parameter of the query (`$p3`), or, for one query that makes
        several searches of the same shape, a field of the row of each (`row.p3`: `build_search_ids_rows_query`)"""

    def excluded_labels(self) -> str:
        """The parameter of the excluded wrappers' names (one, however often it is tested)"""
        if self._excluded_param is None:
            self._excluded_param = self.param(list(self.excluded))
        return self._excluded_param

    def path_allowed(self, path: str) -> list[str]:
        """What `exclude_wrappers` asks of the path of a relation: none of its nodes is a wrapper that is left out"""
        if not self.excluded:
            return []
        return [
            f"none(nd IN nodes({path}) WHERE any(l IN labels(nd) WHERE l IN {self.excluded_labels()}))"
        ]

    def edge_seen(self, edge: str) -> list[str]:
        """What is asked of the edge that reaches what a relation is to, where it may be of a computed relation: the
        reader may see it (`fragments.edge_visible`; nothing, when no model computes a relation)"""
        from pangloss_models.computed import has_computed_relations

        return [fragments.edge_visible(edge)] if has_computed_relations() else []

    def node_allowed(self, node: str) -> list[str]:
        """What `exclude_wrappers` asks of a node of a document that is found by the document, not along a path
        (`$mentions`, `$somewhere`): it is not a wrapper that is left out, nor inside one"""
        if not self.excluded:
            return []
        a, q = self.name("a"), self.name("q")
        return [
            f"NOT EXISTS {{ MATCH ({node}){dialect().up_reverse(q, minimum=0)}({a}) "
            f"WHERE any(l IN labels({a}) WHERE l IN {self.excluded_labels()}) }}"
        ]

    def param(self, value) -> str:
        name = f"p{len(self.params)}"
        self.params[name] = convert_type_for_writing(value)
        return f"{self.holder}{name}"

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
            tests = [self.all_of(pattern.items, node), *self.node_allowed(node)]
            return (
                f"EXISTS {{ MATCH {self.in_document(var, node, pattern.model.__name__)} "
                f"WHERE {' AND '.join(tests)} }}"
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
            tests = [self.relation_of(c, node), *self.node_allowed(node)]
            return (
                f"({self.relation_of(c, var)} OR "
                f"EXISTS {{ MATCH {self.in_document(var, node)} "
                f"WHERE {' AND '.join(tests)} }})"
            )
        return self.relation_of(c, var)

    def relation_of(self, c: CheckedCondition, var: str) -> str:
        direct = self.reaching(c, var, through_wrappers=False)
        # (whether there is any: the first edge says, unless something is asked of the way, or of the last edge, or
        # some wrappers are left out: then an edge to one of those is not one)
        if not c.wrapped or (
            c.operator == "exists"
            and not c.through
            and c.edge is None
            and not c.via
            and not self.excluded
        ):
            return direct
        via = self.reaching(c, var, through_wrappers=True)
        if c.through:
            return via
        if c.operator == "exists" and not c.value:
            return f"({direct} AND {via})"  # (neither way is there one)
        return f"({direct} OR {via})"

    def path_tests(
        self, c: CheckedCondition, path: str, backwards: bool = False
    ) -> list[str]:
        """What `through` asks of the path of a relation: a node of each class named is on it, and for each of which
        more is asked, one that fits. `path`: from the node to what the relation is to, the wrappers between them (or,
        `backwards`, written from what it is to)"""
        tests = []
        if c.through:
            tests.append(
                f"all(s IN {self.param(list(c.through))} WHERE any(nd IN nodes({path}) WHERE s IN labels(nd)))"
            )
        for step in c.steps:
            if has_relation(step.items):
                tests.append(self.step_with_relations(step, path, backwards))
                continue
            i = self.name("i")
            tests.append(
                f"any({i} IN range(1, size(nodes({path})) - 2) WHERE {self.step_at(step, path, i, backwards)})"
            )
        if c.via:
            tests.append(self.way_test(c.via, path, backwards))
        return tests

    def way_test(
        self, via: tuple[CheckedVia, ...], path: str, backwards: bool = False
    ) -> str:
        """What `via` asks of the path of a relation: each item is met by a place of the way (an edge of it, or a
        wrapper), each by one after that of the item before. The way is `node -e0-> w1 -e1-> … wk -ek-> target`: edge
        `j` is `relationships(path)[j]` and wrapper `i` is `nodes(path)[i]` (counted from the other end, `backwards`),
        so an item after edge `j` starts at edge or wrapper `j + 1`, and one after wrapper `i` at edge `i` or wrapper
        `i + 1`.

        Where no item asks a relation of a wrapper, it is list predicates inside one another. Where one does, the
        places are named by `UNWIND` in a subquery, as `step_with_relations` names its wrapper (and for its reason)."""
        size = f"size(nodes({path}))"
        indexes = [self.name("i") for _ in via]
        names = [self.name("nd" if item.kind == "wrapper" else "ed") for item in via]

        def at(k: int) -> str:
            if via[k].kind == "wrapper":
                index = f"{size} - 1 - {indexes[k]}" if backwards else indexes[k]
                return f"nodes({path})[{index}]"
            index = f"{size} - 2 - {indexes[k]}" if backwards else indexes[k]
            return f"relationships({path})[{index}]"

        def places(k: int) -> str:
            if k == 0:
                low = "1" if via[k].kind == "wrapper" else "0"
            elif via[k - 1].kind == "wrapper" and via[k].kind == "edge":
                low = indexes[k - 1]
            else:
                low = f"{indexes[k - 1]} + 1"
            # (the last wrapper and the last edge have the same number)
            return f"range({low}, {size} - 2)"

        def asked(k: int, own: bool) -> list[str]:
            item = via[k]
            tests = []
            if item.kind == "wrapper":
                tests.append(f"{self.param(item.model.__name__)} IN labels({names[k]})")
            if item.items:
                compile_ = self.own_tests if own else self.all_of
                tests.append(compile_(item.items, names[k]))
            return tests

        if any(has_relation(item.items) for item in via):
            unwinds = " ".join(
                f"UNWIND {places(k)} AS {indexes[k]}" for k in range(len(via))
            )
            named = ", ".join(f"{at(k)} AS {names[k]}" for k in range(len(via)))
            tests = [test for k in range(len(via)) for test in asked(k, own=True)]
            return f"EXISTS {{ {unwinds} WITH {named} WHERE {' AND '.join(tests)} RETURN 1 AS found }}"
        text = ""
        for k in reversed(range(len(via))):
            here = " AND ".join(asked(k, own=False)) or "true"
            inner = f"any({names[k]} IN [{at(k)}] WHERE {here})"
            if text:
                inner += f" AND {text}"
            text = f"any({indexes[k]} IN {places(k)} WHERE {inner})"
        return text

    def never_direct(self, c: CheckedCondition) -> bool:
        """Whether what `via` asks cannot be met by a relation with no wrapper, which is one edge: it asks for a
        wrapper, or for more than one place"""
        return bool(c.via) and not (len(c.via) == 1 and c.via[0].kind == "edge")

    def way_of_one_edge(self, c: CheckedCondition, edge: str) -> list[str]:
        """What `via` asks of a relation with no wrapper, of its one edge (where it can be met by one: `never_direct`)"""
        return [self.all_of(item.items, edge) for item in c.via if item.items]

    def step_at(
        self, step: CheckedStep, path: str, index: str, backwards: bool = False
    ) -> str:
        """Whether the node at `index` of the path is the wrapper the step asks for, and its edge onwards as asked. (A
        node or an edge of a path is given a name by a list of it alone, so that it is tested as any other)"""
        nd = self.name("nd")
        tests = [f"{self.param(step.model.__name__)} IN labels({nd})"]
        if step.items:
            tests.append(self.all_of(step.items, nd))
        text = f"any({nd} IN [nodes({path})[{index}]] WHERE {' AND '.join(tests)})"
        if step.edge is not None and step.edge.items:
            ed = self.name("ed")
            at = f"{index} - 1" if backwards else index
            text += (
                f" AND any({ed} IN [relationships({path})[{at}]] "
                f"WHERE {self.all_of(step.edge.items, ed)})"
            )
        return text

    def step_with_relations(
        self, step: CheckedStep, path: str, backwards: bool = False
    ) -> str:
        """Whether a wrapper of the path is the one the step asks for, where the step asks for a relation of the
        wrapper's own (`InRole.role`): each wrapper is named by an `UNWIND` in a subquery, and its relation is a
        pattern from that name. (Named by a list predicate, as `step_at` names it, a pattern from the name is not
        tested of it on Memgraph 3.14: an `EXISTS` inside `any(nd IN [...])` held for a wrapper it did not hold of)"""
        i, nd, ed = self.name("i"), self.name("nd"), self.name("ed")
        tests = [f"{self.param(step.model.__name__)} IN labels({nd})"]
        tests.append(self.own_tests(step.items, nd))
        if step.edge is not None and step.edge.items:
            tests.append(self.all_of(step.edge.items, ed))
        at = f"{i} - 1" if backwards else i
        return (
            f"EXISTS {{ UNWIND range(1, size(nodes({path})) - 2) AS {i} "
            f"WITH nodes({path})[{i}] AS {nd}, relationships({path})[{at}] AS {ed} "
            f"WHERE {' AND '.join(tests)} RETURN 1 AS found }}"
        )

    def own_tests(self, items: list[Expr], var: str) -> str:
        """The tests of a wrapper named inside the test of a relation: its values, and its own relations each from the
        wrapper itself (`local`: not found beforehand for the whole search, which is of another node)"""
        was, self.local = self.local, True
        try:
            return self.all_of(items, var)
        finally:
            self.local = was

    def edge_tests(self, edge: CheckedEdge | None, var: str) -> list[str]:
        """What is asked of the edge `var` (the one that reaches what a relation is to)"""
        return [self.all_of(edge.items, var)] if edge is not None and edge.items else []

    def reaching(self, c: CheckedCondition, var: str, through_wrappers: bool) -> str:
        if not through_wrappers and self.never_direct(c):
            # (no relation without a wrapper is by such a way)
            return "true" if c.operator == "exists" and not c.value else "false"
        e, w = self.name("e"), self.name("w")
        where = ["true"]
        if c.field in (SearchKey.ANY, SearchKey.MENTIONS):
            edge = f"({var})-[{e}]->({w})"
            where.append(f"{fragments.forward(e)} AND {w}:PGIndexableNode")
        else:
            edge = f"({var})-[{e}:{fragments.field_edge(c.field)}]->({w})"
        if not through_wrappers:
            if c.wrapped and (
                c.operator != "exists" or c.edge is not None or c.via or self.excluded
            ):  # (a wrapper is not what the relation is to: what is in it is)
                where.append(f"NOT {wrapper(w)}")
            where += self.edge_tests(c.edge, e)
            where += self.way_of_one_edge(c, e)
            where += self.edge_seen(e)
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
        where += self.path_tests(c, p)
        where += self.path_allowed(p)
        where += self.edge_tests(c.edge, r)
        where += self.edge_seen(r)
        if c.operator != "exists":
            where.append(self.target(c, t))
        else:
            # (what is reached is what the relation is to: the edge into a wrapper inside the last is not its edge)
            where.append(f"NOT {wrapper(t)}")
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
            f"WHERE {' AND '.join([source_tests(s), *self.edge_seen(e)])} }}"
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
        where += self.path_allowed(p)
        where += self.edge_seen(r)
        where.append(source_tests(s))
        via = (
            f"EXISTS {{ MATCH {p} = ({var})<-[{r}]-({x}){dialect().through_wrappers(q, backwards=True)}({w})"
            f"<-[{e}:{types}]-({s}:{fragments.label(label)}) WHERE {' AND '.join(where)} }}"
        )
        return via if c.through else f"({direct} OR {via})"

    def hidden_head(self, h: str) -> str:
        """A condition: the search reads nothing inside the head node `h`. It is hidden from the reader; or, in a
        search that leaves wrappers out, an installed app says so (`pangloss_models.search.head_conditions`)"""
        # (each true or null, as `hidden` is, for the `NOT EXISTS` it is in)
        return " OR ".join([fragments.hidden(h), *self.head_tests(h)])

    def head_tests(self, h: str) -> list[str]:
        """What the installed apps say hides a head from a search that leaves wrappers out"""
        if not self.excluded:
            return []
        tests = [function(self, h) for function in head_conditions]
        return [f"({test})" for test in tests if test]

    def root_allowed(self, model: type, n: str) -> list[str]:
        """Conditions on what the search finds, where that is itself a head document: the same as for the head
        of a document the pattern passes"""
        if not issubclass(model, Document):
            return []
        return [f"NOT coalesce({test}, false)" for test in self.head_tests(n)]

    def not_in_hidden_document(self, s: str) -> str:
        """Whether the node is not in a head document that is hidden: going up to it, along the reverse edges"""
        h, q = self.name("h"), self.name("q")
        return (
            f"NOT EXISTS {{ MATCH ({s}){dialect().up_reverse(q, minimum=0)}({h}:HeadNode) "
            f"WHERE {self.hidden_head(h)} }}"
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


def has_relation(exprs: list[Expr]) -> bool:
    """Whether any of the conditions, at any depth of `$any_of` and `$not`, is of a relation"""
    for e in exprs:
        if isinstance(e, AnyOf):
            if any(has_relation(branch) for branch in e.branches):
                return True
        elif isinstance(e, Not):
            if has_relation(e.items):
                return True
        elif e.kind == "relation":
            return True
    return False


ROWS_HOLDER = "row."


def build_search_ids_rows_query(
    model: type[Document | Entity],
    conditions: list[Expr],
    exclude_wrappers: tuple[str, ...] = (),
) -> tuple[LiteralString, dict] | None:
    """`build_search_ids_query` for several searches of one shape at once (patterns that differ only in their ids
    and values compile to the same text): the query, and the values of this search, to be given with it as a row.

        text, values = build_search_ids_rows_query(Person, conditions)
        tx.run(text, rows=[{"key": ..., "among": [...], "without": [...], **values}, ...], limit=, see_unpublished=)

    Each row is a search among the ids it gives (`among`: found by their index), less `without`. A row for each
    search that finds something: its `key`, the count, and the ids, types and labels of the first `$limit` by
    label. None where this backend's compiler makes subqueries that go before the `MATCH` (they cannot read a row):
    such a search is made alone, with `build_search_ids_query`."""
    values: dict = {}
    compiler: Compiler = dialect().search_compiler(values)
    compiler.holder = ROWS_HOLDER
    compiler.excluded = tuple(exclude_wrappers)
    tests = compiler.all_of(conditions, "n")
    if compiler.preludes:
        return None
    kind = "HeadNode" if issubclass(model, Document) else "Entity"
    where = [
        f"n:{fragments.label(model.__name__)} AND n:{kind}",
        fragments.listed("n"),
        tests,
        *compiler.root_allowed(model, "n"),
        "NOT n.id IN row.without",
    ]
    query = f"""
    UNWIND $rows AS row
    UNWIND row.among AS among_id
    MATCH (n:PGIndexableNode {{id: among_id}})
    WHERE {" AND ".join(where)}
    WITH DISTINCT row.key AS key, n
    ORDER BY key, toLower(n.label), {dialect().tie_break("n")}
    WITH key, collect(n.id) AS ids, collect(n.type) AS types, collect(n.label) AS labels
    RETURN key, size(ids) AS count, ids[0..$limit] AS ids, types[0..$limit] AS types,
           labels[0..$limit] AS labels
    """
    return cast(LiteralString, query), values


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
    exclude_wrappers: tuple[str, ...] = (),
) -> tuple[LiteralString, dict]:
    """`exclude_wrappers`: the wrappers no relation of the search passes through (`Match.exclude_wrappers`, checked)"""
    params: dict = {
        "page": page_number,
        "page_size": page_size,
        "see_unpublished": unpublished_visible(),
    }
    compiler: Compiler = dialect().search_compiler(params)
    compiler.excluded = tuple(exclude_wrappers)
    tests = compiler.all_of(conditions, "n")
    finding, keys, sorting = ordering(compiler, order or [])

    kind = "HeadNode" if issubclass(model, Document) else "Entity"
    where = " AND ".join(
        [fragments.listed("n"), tests, *compiler.root_allowed(model, "n")]
    )
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
        RETURN collect(n{{.*, meta: {{
            created_by: {fragments.creators("creation")},
            uploaded_by: creation.uploaded_by,
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


def build_search_ids_query(
    model: type[Document | Entity],
    conditions: list[Expr],
    limit: int,
    see_unpublished: bool,
    exclude_wrappers: tuple[str, ...] = (),
    without: list[str] | None = None,
    among: list[str] | None = None,
) -> tuple[LiteralString, dict]:
    """A search that gives what it finds as ids: how many fit, and the first `limit` by label, each with its id,
    type and label (no `meta`: for what works with the result, not for a page a person reads). `see_unpublished`:
    the reader it is made for, whoever asks. `without`: ids that are not counted or given. `among`: only these
    ids are looked at (found by their index, not by a scan of the class).

    A row for each item, with the count on each (one row with no id, if there is none). (Made as a list of maps by a
    comprehension over the collected nodes, Memgraph gave the first node for each of them.)"""
    params: dict = {"limit": limit, "see_unpublished": see_unpublished}
    compiler: Compiler = dialect().search_compiler(params)
    compiler.excluded = tuple(exclude_wrappers)
    tests = compiler.all_of(conditions, "n")
    kind = "HeadNode" if issubclass(model, Document) else "Entity"
    where = [fragments.listed("n"), tests, *compiler.root_allowed(model, "n")]
    if without:
        params["without"] = list(without)
        where.append("NOT n.id IN $without")
    label = fragments.label(model.__name__)
    if among is None:
        match = f"MATCH (n:{label}:{kind})"
    else:
        params["among"] = list(among)
        match = "UNWIND $among AS among_id MATCH (n:PGIndexableNode {id: among_id})"
        where.append(f"n:{label} AND n:{kind}")
    prelude = "\n    ".join(text for text, _ in compiler.preludes)
    query = f"""
    {prelude}
    {match}
    WHERE {" AND ".join(where)}
    WITH DISTINCT n
    ORDER BY toLower(n.label), {dialect().tie_break("n")}
    WITH collect(n) AS found
    WITH size(found) AS count, found[0..$limit] AS first
    UNWIND (CASE WHEN size(first) = 0 THEN [null] ELSE first END) AS item
    RETURN count, item.id AS id, item.type AS type, item.label AS label
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
        seen = fragments.listed("n")
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
