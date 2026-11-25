"""A rule as Cypher: the query that finds the justifications in which a node of `$seeds` is at one place of the rule (the
"delta" of incremental Datalog). The worker runs it for the nodes of the documents written; a rebuild runs it, seeded at
one place, for every node of its class.

    UNWIND $seeds AS seed
    MATCH (n_0:PGIndexableNode {id: seed}) WHERE n_0:`MemberOf` AND ...
    MATCH (n_0) <up the reverse edges> (hd_n_0:HeadNode) WHERE NOT <deleted>
    MATCH rp_0 = (n_0)-[re_0:`member`]->(rx_0) <out of wrappers> (v_a) WHERE v_a:`Person` AND ...
    ...
    RETURN seed, [<the fields of the fact>] AS fields, [<the node of each pattern>] AS nodes, [<their heads>] AS heads,
           [<their semantic spaces>] AS spaces, [<the wrappers of each relation>] AS through, [<its edge's properties>] AS props,
           ..., [<the id and stored path of each node that is not an entity>] AS walks, [<each relation's wrappers>] AS ways

The order of the joins is chosen here, not by the planner: from the seed, each relation that starts at a node already
found (one edge out of it) before one that ends at one (all the edges into an entity). Every name of the models in the
text is checked (a class, a field); every value is a parameter.
"""

from typing import Any

from pangloss_cypher import fragments
from pangloss_cypher.search_query import wrapper
from pangloss_cypher.transactions import dialect
from pangloss_models.computed import EVERYONE, has_computed_relations

from pangloss_derived.check import CheckedRule, Edge, Node, PathValue
from pangloss_derived.declare import Constraint
from pangloss_derived.status import walked_nodes


class RuleQuery:
    def __init__(self, rule: CheckedRule, start: str):
        self.rule = rule
        self.start = start
        self.params: dict[str, Any] = {}
        self.compiler = dialect().search_compiler(self.params)
        if rule.blocked:
            self.params["blocked"] = sorted(rule.blocked)
        self.bound: set[str] = set()
        self.values: dict[str, str] = {}
        """The expression of each literal variable, once bound"""
        self.waiting: list[tuple[set[str], str | Constraint]] = []
        """Conditions to give when all of their nodes and variables are found"""
        self.clauses: list[str] = []
        self.heads: dict[str, str] = {}
        """The expression of the head node of each node of a pattern"""
        self.unwinds: dict[str, list] = {}
        """The list fields of each node that a variable is an item of, to be unwound after its `MATCH`"""

    # -- names --

    def name_of_var(self, name: str) -> str:
        node = f"v_{name}"
        if node in self.rule.nodes:
            return node
        return self.values[name]

    def param(self, value: Any) -> str:
        return self.compiler.param(value)

    # -- conditions --

    def node_conditions(self, node: Node) -> list[str]:
        n = node.name
        conditions = [f"{n}:{fragments.label(node.model.__name__)}"]
        if node.kind == "entity":
            conditions.append(fragments.not_deleted(n))
        if node.filters:
            conditions.append(self.compiler.all_of(node.filters, n))
        if self.rule.blocked and node.kind != "entity":
            spaces = dialect().meta_property(n, "semantic_spaces")
            conditions.append(f"none(s IN coalesce({spaces}, []) WHERE s IN $blocked)")
        for binding in self.rule.values:
            if binding.node != n:
                continue
            expression = f"{n}.{fragments.field_edge(binding.field)}"
            if binding.many:
                # (one of the items of a list: bound by an `UNWIND` after the node is found, or, if it is bound already,
                # the item has to be in the list)
                if binding.var in self.values:
                    conditions.append(f"{self.values[binding.var]} IN {expression}")
                else:
                    self.unwinds.setdefault(n, []).append(binding)
            elif binding.var in self.values:
                conditions.append(f"{expression} = {self.values[binding.var]}")
            else:
                self.values[binding.var] = expression
        return conditions

    def after_match(self, *nodes: Node) -> None:
        """The clauses that follow the `MATCH` of nodes: each item of a list field a variable stands for"""
        for node in nodes:
            for binding in self.unwinds.pop(node.name, []):
                value = f"val_{binding.var}"
                self.values[binding.var] = value
                self.clauses.append(
                    f"UNWIND {node.name}.{fragments.field_edge(binding.field)} AS {value}"
                )
                ready = self.ready()
                if ready:
                    self.clauses.append("WITH *\nWHERE " + "\n  AND ".join(ready))

    def ready(self) -> list[str]:
        """The conditions waiting whose nodes and variables are all found now"""
        known = self.bound | {f"value:{v}" for v in self.values}
        given = [c for needs, c in self.waiting if needs <= known]
        self.waiting = [(needs, c) for needs, c in self.waiting if not needs <= known]
        return [self.text_of(c) for c in given]

    def wait_for_constraints(self) -> None:
        for constraint in self.rule.constraints:
            needs = set()
            for variable in constraint.variables():
                node = f"v_{variable.name}"
                needs.add(node if node in self.rule.nodes else f"value:{variable.name}")
            self.waiting.append((needs, constraint))
        if self.rule.symmetric:
            a, b = (f"v_{name}" for name in self.rule.symmetric)
            if self.rule.symmetric_body:
                # (each pair once, in order of id: and never a thing with itself)
                self.waiting.append(({a, b}, f"{a}.id < {b}.id"))
            else:
                # (the body is not the same with the two swapped: both orders are tried, and the fact is written with
                # its ends in order. Never a thing with itself)
                self.waiting.append(({a, b}, f"{a} <> {b}"))

    def text_of(self, condition: "str | Constraint") -> str:
        if isinstance(condition, str):
            return condition
        return condition.cypher(lambda v: self.name_of_var(v.name), self.param)

    def where(self, conditions: list[str]) -> str:
        texts = conditions + self.ready()
        return ("\nWHERE " + "\n  AND ".join(texts)) if texts else ""

    # -- clauses --

    def find_head(self, node: Node) -> None:
        """The head node of a node of a pattern (its evidence), which must not be deleted"""
        n = node.name
        if node.kind == "entity":
            self.heads[n] = n
            return
        head = f"hd_{n}"
        # (a rule that blocks a document class reads nothing inside a document of it)
        blocked = "".join(
            f"\n  AND NOT {head}:{fragments.label(name)}"
            for name in sorted(self.rule.blocked_heads)
        )
        self.clauses.append(
            f"MATCH ({n}){dialect().up_reverse(f'u_{n}', minimum=0)}({head}:HeadNode)"
            f"\nWHERE {fragments.not_deleted(head)}{blocked}"
        )
        self.heads[n] = head

    def bind(self, node: Node) -> list[str]:
        self.bound.add(node.name)
        return self.node_conditions(node)

    def edge_clause(self, edge: Edge) -> None:
        source, target = self.rule.nodes[edge.source], self.rule.nodes[edge.target]
        k = edge.index
        path, first = f"rp_{k}", f"re_{k}"
        field = fragments.field_edge(edge.field)
        if edge.wrapped:
            pattern = (
                f"{path} = ({source.name})-[{first}:{field}]->(rx_{k})"
                f"{dialect().from_wrappers(f'rw_{k}')}({target.name})"
            )
        else:
            pattern = f"{path} = ({source.name})-[{first}:{field}]->({target.name})"
        conditions: list[str] = []
        for node in (source, target):
            if node.name not in self.bound:
                conditions += self.bind(node)
        if edge.wrapped:
            conditions.append(f"NOT {wrapper(target.name)}")
            if has_computed_relations():
                # (what the server computed to be related, for those logged in only, rests on what is not
                # published: a fact is shown by the documents it rests on, and that one is not among them. So a
                # rule follows a computed edge only if everyone may see it)
                conditions.append(
                    f"all(x IN relationships({path}) "
                    f"WHERE coalesce(x.seen_by, '{EVERYONE}') = '{EVERYONE}')"
                )
            if self.rule.blocked:
                conditions.append(f"none(x IN nodes({path}) WHERE x.type IN $blocked)")
        if edge.through:
            conditions.append(
                f"all(t IN {self.param(list(edge.through))} WHERE any(x IN nodes({path}) WHERE t IN labels(x)))"
            )
        # (what a `Through` asks of a wrapper on the way: one that binds no variable is a condition of the path)
        binding = {v.step for v in edge.values if v.step is not None}
        for index, step in enumerate(edge.steps):
            if index not in binding:
                i = self.compiler.name("i")
                conditions.append(
                    f"any({i} IN range(1, size(nodes({path})) - 2) "
                    f"WHERE {self.compiler.step_at(step, path, i)})"
                )
        if edge.last is not None:
            # (of its edge model, and with its values as asked: an edge says which edge model it is of)
            ed = self.compiler.name("ed")
            conditions.append(
                f"any({ed} IN [last(relationships({path}))] "
                f"WHERE {self.compiler.edge_is(edge.last.model, edge.last.items, ed)})"
            )
        self.clauses.append(f"MATCH {pattern}{self.where(conditions)}")
        self.path_values(edge, path)
        self.after_match(source, target)
        for node in (source, target):
            if node.top and node.name not in self.heads:
                self.find_head(node)

    def path_values(self, edge: Edge, path: str) -> None:
        """The clauses that bind the variables met on the way of a relation: for a wrapper asked for with a variable, a
        row for each wrapper of the path that fits (most often one), and its value, or its edge's; and the value of the
        edge that reaches what the relation is to. A value that is not there binds nothing"""
        k = edge.index
        for index in sorted({v.step for v in edge.values if v.step is not None}):
            at, i = f"ti_{k}_{index}", self.compiler.name("i")
            self.clauses.append(
                f"UNWIND [{i} IN range(1, size(nodes({path})) - 2) "
                f"WHERE {self.compiler.step_at(edge.steps[index], path, i)}] AS {at}"
            )
            node, leaving = f"tn_{k}_{index}", f"te_{k}_{index}"
            self.value_clause(
                f"nodes({path})[{at}] AS {node}, relationships({path})[{at}] AS {leaving}",
                [v for v in edge.values if v.step == index],
                node,
                leaving,
            )
        last = [v for v in edge.values if v.step is None]
        if last:
            reaching = f"le_{k}"
            self.value_clause(
                f"last(relationships({path})) AS {reaching}", last, "", reaching
            )

    def value_clause(
        self, named: str, values: list[PathValue], node: str, edge: str
    ) -> None:
        conditions = []
        for value in values:
            holder = node if value.on == "node" else edge
            expression = f"{holder}.{fragments.property_name(value.field)}"
            conditions.append(f"{expression} IS NOT NULL")
            if value.var in self.values:
                conditions.append(f"{expression} = {self.values[value.var]}")
            else:
                self.values[value.var] = expression
        self.clauses.append(f"WITH *, {named}{self.where(conditions)}")

    def build(self) -> str:
        rule = self.rule
        self.wait_for_constraints()
        start = rule.nodes[self.start]
        conditions = self.bind(start)
        self.clauses.append(
            f"UNWIND $seeds AS seed\nMATCH ({start.name}:PGIndexableNode {{id: seed}})"
            + self.where(conditions)
        )
        self.after_match(start)
        if start.top:
            self.find_head(start)
        remaining = list(rule.edges)
        while remaining or len(self.bound) < len(rule.nodes):
            edge = self.next_edge(remaining)
            if edge is not None:
                remaining.remove(edge)
                self.edge_clause(edge)
                continue
            # (a part of the body joined to the rest by nothing: every node of its class)
            node = next(
                n
                for n in rule.nodes.values()
                if n.name not in self.bound and (n.pattern or not remaining)
            )
            conditions = self.bind(node)
            self.clauses.append(f"MATCH ({node.name})" + self.where(conditions))
            self.after_match(node)
            if node.top:
                self.find_head(node)
        # (a condition whose last variable was bound by the last clause)
        left = self.ready()
        if left:
            self.clauses.append("WITH *\nWHERE " + "\n  AND ".join(left))
        if self.waiting:
            raise AssertionError(f"conditions not given: {self.waiting}")
        # (`WITH *` between the clauses: the planner takes them in this order, each from what is found. Without it,
        # Memgraph planned the clauses as one pattern and began with every `MemberOf`, for each seed)
        return "\nWITH *\n".join(self.clauses) + "\n" + self.returned()

    def next_edge(self, remaining: list[Edge]) -> Edge | None:
        forward = [e for e in remaining if e.source in self.bound]
        if forward:
            return forward[0]
        backward = [e for e in remaining if e.target in self.bound]
        return backward[0] if backward else None

    def returned(self) -> str:
        rule = self.rule
        fields = []
        for kind, value in rule.head.values():
            if kind == "var":
                node = f"v_{value}"
                fields.append(
                    f"{node}.id" if node in rule.nodes else self.values[value]
                )
            else:
                fields.append(self.param(value))
        nodes = [f"{name}.id" for name in rule.patterns]
        heads = [f"{self.heads[name]}.id" for name in rule.patterns]
        spaces = [
            f"coalesce({dialect().meta_property(name, 'semantic_spaces')}, [])"
            if rule.nodes[name].kind != "entity"
            else "[]"
            for name in rule.patterns
        ]
        through = [
            f"[x IN nodes(rp_{e.index})[1..-1] | x.type]" if e.wrapped else "[]"
            for e in rule.edges
        ]
        props = [f"properties(last(relationships(rp_{e.index})))" for e in rule.edges]
        # (what each node of a path is, for `store.one_of_each`: its id; of a wrapper that is exclusive together
        # with others of its document by a field, the document and the value, which those others have too)
        one = "x.id"
        for kind, field in rule.exclusive_with:
            name = fragments.property_name(field)
            one = (
                f"CASE WHEN x.type = {self.param(kind)} AND x.{name} IS NOT NULL"
                f" THEN x.head_node_id + ':' + toString(x.{name}) ELSE {one} END"
            )
        paths = [
            f"[x IN nodes(rp_{e.index})[1..] | {one}]" if e.wrapped else "[]"
            for e in rule.edges
        ]
        # (for the walk, `pangloss_derived.status`: the id and the stored path of each node that is not an entity,
        # and the type and id of each wrapper of each relation)
        walks = [
            f"[{name}.id, {dialect().meta_property(name, 'path')}]"
            for name in walked_nodes(rule)
        ]
        ways = [
            f"[x IN nodes(rp_{e.index})[1..-1] | [x.type, x.id]]" if e.wrapped else "[]"
            for e in rule.edges
        ]
        return (
            "RETURN seed,\n"
            f"       [{', '.join(fields)}] AS fields,\n"
            f"       [{', '.join(nodes)}] AS nodes,\n"
            f"       [{', '.join(heads)}] AS heads,\n"
            f"       [{', '.join(spaces)}] AS spaces,\n"
            f"       [{', '.join(through)}] AS through,\n"
            f"       [{', '.join(props)}] AS props,\n"
            f"       [{', '.join(paths)}] AS paths,\n"
            f"       [{', '.join(walks)}] AS walks,\n"
            f"       [{', '.join(ways)}] AS ways"
        )


def compile_rule(rule: CheckedRule, start: str) -> tuple[str, dict[str, Any]]:
    """The query of the rule seeded at the node `start` (one of `rule.seeds`); `$seeds` is to be given"""
    query = RuleQuery(rule, start)
    text = query.build()
    preludes = "\n".join(t for t, _ in query.compiler.preludes)
    return (preludes + "\n" + text if preludes else text), query.params


def join_order(rule: CheckedRule, start: str) -> list[str]:
    """The order the relations are joined in, from `start` (for `explain`)"""
    query = RuleQuery(rule, start)
    query.build()
    return [c.split("\n")[0] for c in query.clauses]
