"""Citations in the database (`Cites[T]`, `pangloss_models.citations`; implementation_docs/entity-identity.md,
part 3).

A citation is a node of the citing document, `(:PGCitation {target_id, ...})`, written with it as any nested document
is. What is here is the rest:

- **when a citation is written** (`record`): what it names is checked (a document node of an allowed class, not
  deleted), and the head it is in, that head's version and a hash of what is cited are put on the citation. The cited
  head is written to as well (`pg_cited`), so that this write and a write of that head cannot both go through without
  one seeing the other: the database refuses the second, or makes it wait;
- **when a head that is cited is written** (`before_change`, then `after_change`): what its cited parts are before
  and after is compared. A change is refused unless the writer acknowledged the citations, and then each is marked
  `changed_since_cited`; a removal is refused unless an admin overrides it;
- **when it is deleted** (`check_removal`): refused as a removal is;
- **when a citing document is read** (`hydrate`): what each citation names, as it is now.

A **citation that does not protect** (`PGUnprotectedCitation`: a `Cites` with `protect = False`) has only the
first and the last of these, and less of the first: what it names is checked, and its head and label recorded, but
the cited head is not written to and not read. It is of another class so that the second and third, which find who
cites a head by the index of `PGCitation`, never meet it: a head that thousands of them cite is saved as one that
nothing cites.

A **cited basis** (`PGCitedBasis`) holds citations as any other, with a record of what was chosen (`via_*`). An
installed app makes one of a citation of something that cannot itself be cited (`resolve`, before the write); what a
write sends as one has to be what that app says it is, or one the document has already (`check_bases`); and it is
marked when what was chosen changes or goes (`mark_via`).

The comparison is of two readings made in one transaction, never with a hash stored earlier: a merge of entities, a
migration or a change of how values are stored cannot make a citation look changed.
"""

import dataclasses
import datetime
import hashlib
import json
import typing
import uuid

from pangloss_models import ModelRegistry, hooks
from pangloss_models.citations import (
    BASIS,
    CITATION,
    CITATION_TYPES,
    UNPROTECTED,
    acknowledged,
    allows,
    is_basis,
    is_citation,
    is_protecting,
)
from pangloss_models.exceptions import (
    PanglossCitedError,
    PanglossClassChangeError,
    PanglossReferenceError,
)
from pangloss_models.field_definitions import (
    RelationFieldDefinition,
    RelationToCitation,
    RelationToTypeVar,
)
from pydantic import BaseModel

from pangloss_cypher import fragments
from pangloss_cypher.build_tree import INTERNAL_EDGE_PROPERTIES, _list_order
from pangloss_cypher.read_query import build_fetch_document_query
from pangloss_cypher.transaction import Transaction
from pangloss_cypher.transactions import dialect
from pangloss_cypher.visibility import unpublished_visible

# (of the normal form: a change of it gives every hash anew)
HASH_VERSION = 1

# How many citing documents an error names
MAX_REPORTED = 10


def any_citations() -> bool:
    """Whether the models have a `Cites[...]` at all: without one, nothing here costs anything"""
    return CITATION in ModelRegistry._model_dict


def any_unprotected() -> bool:
    return UNPROTECTED in ModelRegistry._model_dict


def any_at_all() -> bool:
    """Whether the models have a citation of either kind"""
    return any_citations() or any_unprotected()


def any_bases() -> bool:
    return BASIS in ModelRegistry._model_dict


# --- what a payload cites ---------------------------------------------------------------------------------------------


def _cited_by_options(options: typing.Iterable[typing.Any]) -> frozenset[type] | None:
    """The classes the citations among `options` allow (through the parameters of generic wrappers too); None if
    there is no citation among them"""
    found: set[type] = set()
    any_found = False
    for option in options:
        if isinstance(option, RelationToCitation):
            found |= option.cited
            any_found = True
        for parameter in getattr(option, "parameter_type_options", {}).values():
            inner = _cited_by_options(parameter.type_options)
            if inner is not None:
                found |= inner
                any_found = True
    return frozenset(found) if any_found else None


# (the classes allowed for a citation inside a cited basis: any. What a basis may hold is checked as a whole)
type Allowed = frozenset[type] | None


def citations_in(instance: typing.Any) -> list[tuple[typing.Any, Allowed]]:
    """The citations in what is to be written (a `CreateDB` or `UpdateDB` model), of both kinds, each with the
    classes its field allows (None: any, for one inside a cited basis)"""
    found: list[tuple[typing.Any, Allowed]] = []

    def visit(value: typing.Any, allowed: Allowed) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item, allowed)
            return
        if not isinstance(value, BaseModel):
            return
        if is_citation(value):
            found.append((value, allowed))
            return
        if is_basis(value):
            visit(getattr(value, "basis", None), None)
            return
        owner = getattr(type(value), "_owner", None)
        definitions = owner._meta.fields if owner is not None else {}
        for name in type(value).model_fields:
            definition = definitions.get(name)
            inner = allowed
            if isinstance(definition, RelationFieldDefinition):
                cited = _cited_by_options(definition.type_options)
                if cited is not None:
                    inner = cited
                elif not any(
                    isinstance(option, RelationToTypeVar)
                    for option in definition.type_options
                ):
                    inner = frozenset()
            visit(getattr(value, name, None), inner)

    visit(instance, frozenset())
    return found


def bases_in(instance: typing.Any) -> list[typing.Any]:
    """The cited bases in what is to be written"""
    found: list[typing.Any] = []

    def visit(value: typing.Any) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif isinstance(value, BaseModel):
            if is_basis(value):
                found.append(value)
                return
            if is_citation(value):
                return
            for name in type(value).model_fields:
                visit(getattr(value, name, None))

    visit(instance)
    return found


# --- what is cited in the place of something that cannot be ----------------------------------------------------------


async def resolve(instance: typing.Any) -> None:
    """Before a `Create` or an `Update` is made what is written: each citation in it that an installed app resolves
    (`hooks.resolve_citation`: it names something that cannot itself be cited) is replaced, in place, by a cited
    basis: citations of what that rests on, and a record of what was chosen. Nothing, without such an app"""
    if not hooks.resolve_citation or not any_bases():
        return
    basis_class = ModelRegistry._model_dict[BASIS]

    async def replaced(value: typing.Any) -> typing.Any:
        """The value to put in its place, or None if it stays"""
        if not is_protecting(value):
            return None
        resolved = await hooks.resolved_citation(
            str(value.target_type), value.target_id, None
        )
        if resolved is None:
            return None
        return typing.cast(typing.Any, basis_class).Create(
            type=BASIS,
            via_id=resolved.via[1] if resolved.via else value.target_id,
            via_type=resolved.via[0] if resolved.via else value.target_type,
            via_rule=resolved.rule,
            via_key=resolved.key,
            via_label=resolved.label,
            basis=[{"type": kind, "id": id} for kind, id in resolved.targets],
        )

    async def visit(value: typing.Any) -> None:
        if not isinstance(value, BaseModel) or is_basis(value) or is_citation(value):
            return
        for name in type(value).model_fields:
            held = getattr(value, name, None)
            if isinstance(held, list):
                for index, item in enumerate(held):
                    new = await replaced(item)
                    if new is not None:
                        held[index] = new
                    else:
                        await visit(item)
            elif isinstance(held, BaseModel):
                new = await replaced(held)
                if new is not None:
                    # (not `setattr`: the model would validate the assignment against its own form of the class)
                    value.__dict__[name] = new
                else:
                    await visit(held)

    await visit(instance)


def _basis_query() -> str:
    return f"""
    MATCH {dialect().tree_below("(head:HeadNode {id: $id})", "(basis:PGCitedBasis)")}
    OPTIONAL MATCH (basis)-[:{fragments.field_edge("basis")}]->(citation:PGCitation)
    RETURN basis.via_id AS via, basis.via_type AS type, basis.via_rule AS rule, basis.via_key AS key,
           basis.via_label AS label, basis.id AS id, coalesce(basis.derivation_state, '') AS state,
           collect(citation.target_id) AS targets
    """


async def previous_bases(
    tx: Transaction, head_id: typing.Any
) -> dict[tuple[str, frozenset[str]], dict[str, typing.Any]]:
    """The cited bases a head has now, before it is written again: by what was chosen and what is cited for it"""
    if not any_bases():
        return {}
    result = await tx.run(_basis_query(), id=str(head_id))  # ty: ignore[invalid-argument-type]
    return {
        (str(row["via"]), frozenset(str(t) for t in row["targets"])): row
        for row in await result.data()
    }


RECORD_BASIS_QUERY = """
    UNWIND $rows AS row
    MATCH (basis:PGIndexableNode {id: row.id})
    SET basis.via_rule = row.rule, basis.via_key = row.key, basis.via_label = row.label
    RETURN count(basis) AS written
"""


async def check_bases(
    tx: Transaction,
    instance: typing.Any,
    stored: dict[tuple[str, frozenset[str]], dict[str, typing.Any]] | None = None,
) -> None:
    """After a head is written, in its transaction: each cited basis in it has to be what an installed app makes of
    what it names (asked again here), or one the document had already (the same thing chosen, the same things
    cited). So a payload cannot name any documents as the "basis" of something and put them in a field that does not
    take their class. `PanglossReferenceError` otherwise. What is recorded of what was chosen (the rule, the key,
    the label) is what the app or the stored basis says, whatever was sent"""
    found = bases_in(instance)
    stored = stored or {}
    await _clear_notices(tx, instance, stored, found)
    if not found:
        return
    rows = []
    for basis in found:
        targets = frozenset(str(c.target_id) for c in basis.basis)
        key = (str(basis.via_id), targets)
        named = f"{basis.via_type} {basis.via_id}"
        if key in stored:
            kept = stored[key]
            rows.append(
                {
                    "id": str(basis.id),
                    "rule": kept["rule"],
                    "key": kept["key"],
                    "label": kept["label"],
                }
            )
            continue
        resolved = await hooks.resolved_citation(str(basis.via_type), basis.via_id, tx)
        if resolved is None:
            raise PanglossReferenceError(
                f"A citation names what cannot be cited: {named} is not something that is cited through what it "
                "rests on (or is not there any more)"
            )
        if frozenset(str(id) for _, id in resolved.targets) != targets:
            raise PanglossReferenceError(
                f"A citation names what cannot be cited: what is given as the basis of {named} is not what it "
                "rests on. Cite it again, by its id alone"
            )
        rows.append(
            {
                "id": str(basis.id),
                "rule": resolved.rule,
                "key": resolved.key,
                "label": resolved.label,
            }
        )
    result = await tx.run(RECORD_BASIS_QUERY, rows=rows)
    await result.consume()


async def _clear_notices(
    tx: Transaction,
    instance: typing.Any,
    stored: dict[tuple[str, frozenset[str]], dict[str, typing.Any]],
    found: list[typing.Any],
) -> None:
    """A basis that was marked, and is written without its mark or not at all: what was said of it to whoever
    looks after the document (`hooks.give_notice`) no longer holds"""
    marked = {key: row for key, row in stored.items() if row.get("state")}
    if not marked:
        return
    still = {
        (str(basis.via_id), frozenset(str(c.target_id) for c in basis.basis))
        for basis in found
        if basis.derivation_state
    }
    for key, row in marked.items():
        if key in still:
            continue
        await hooks.give_notice(
            tx,
            hooks.Notice(
                head_id=uuid.UUID(str(instance.id)),
                head_type=str(getattr(instance, "type", "")),
                kind="",
                target_id=uuid.UUID(str(row["id"])),
                clears=tuple(f"derivation_{state}" for state in MARK_NOTICES),
            ),
        )


# --- marking what was cited through something that has changed or gone ------------------------------------------------

MARK_VIA_QUERY = """
    MATCH (basis:PGCitedBasis {via_id: $id})
    WHERE coalesce(basis.derivation_state, '') <> $state
    SET basis.derivation_state = $state
    RETURN basis.id AS basis, coalesce(basis.head_node_id, basis.id) AS head, basis.head_node_type AS head_type,
           basis.via_label AS label
"""

# What is said of a document that cites through something, when that is marked (`hooks.give_notice`)
MARK_NOTICES = {
    "lost": "A derivation this document cites no longer holds",
    "changed": "A derivation this document cites has changed",
}

_marks: list[hooks.CitationMark] = []


async def mark_via(tx: Transaction, via_id: typing.Any, state: str) -> int:
    """In the transaction of a write of something that citations were made through: every cited basis of it is
    given the state (`changed`, `lost`, or `""` when it is back), found by the index on what it was made of. Gives
    how many were. The listeners (`hooks.citation_marked`) are told when the write has committed (`flush_marks`)"""
    if not any_bases():
        return 0
    result = await tx.run(MARK_VIA_QUERY, id=str(via_id), state=state)
    rows = await result.data()
    for row in rows:
        await hooks.give_notice(
            tx,
            hooks.Notice(
                head_id=uuid.UUID(str(row["head"])),
                head_type=row["head_type"] or "",
                kind=f"derivation_{state}" if state else "",
                text=f"{MARK_NOTICES[state]}: {row['label'] or ''}" if state else "",
                target_id=uuid.UUID(str(row["basis"])),
                target_label=row["label"],
                clears=tuple(
                    f"derivation_{other}" for other in MARK_NOTICES if other != state
                ),
            ),
        )
        _marks.append(
            hooks.CitationMark(
                via_id=uuid.UUID(str(via_id)),
                state=state,
                head_id=uuid.UUID(str(row["head"])),
                head_type=row["head_type"] or "",
                basis_id=uuid.UUID(str(row["basis"])),
            )
        )
    return len(rows)


def flush_marks() -> None:
    """(After a write has committed) tell the listeners of the bases it marked: each once, though the transaction
    may have been run again"""
    if not _marks:
        return
    marks = list(dict.fromkeys(_marks))
    _marks.clear()
    hooks.emit_citation_marks(marks)


# --- the normal form of what is cited, and its hash -------------------------------------------------------------------

# Properties every node has that are not what it says
NOT_CONTENT = {
    "id",
    "head_node_id",
    "head_node_type",
    "meta",
    "deleted",
    "published",
    "pg_cited",
    "merged_into",
    "marked_for_deletion",
}


def _own_properties(node: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """The properties of a node that are its content: its literal fields as the models declare them (not those
    worked out when it is written), and its label unless that is worked out from what it holds"""
    if node.get("type") in CITATION_TYPES:
        return {"target_id": node.get("target_id")}
    cls = ModelRegistry._model_dict.get(str(node.get("type")))
    if cls is None:
        return {
            key: value
            for key, value in node.items()
            if key not in NOT_CONTENT and not key.startswith(("meta_", "review"))
        }
    fields = cls._meta.fields
    kept = {
        name: node[name]
        for name, definition in fields.items()
        if name in node and not definition.db_field
    }
    if "label" in node and getattr(cls._meta, "label_template", None) is None:
        kept["label"] = node["label"]
    return kept


@dataclasses.dataclass
class Tree:
    """A head and everything in it, as the read query gives it"""

    root: dict[str, typing.Any]
    edges_from: dict[str, list[dict[str, typing.Any]]]
    nodes: dict[str, dict[str, typing.Any]]
    version: int

    def normal(
        self, node_id: str, only: typing.Iterable[str] | None = None
    ) -> typing.Any:
        """The normal form of a node and what is in it: its content, each entity it refers to by its id (once in a
        list, so that two entities merged into one change nothing), and the nodes in it in the same form. `only`:
        those fields alone"""
        node = self.nodes[node_id]
        properties = _own_properties(node)
        held: dict[str, list[typing.Any]] = {}
        for edge in self.edges_from.get(node_id, []):
            target = edge["target"]
            if "Entity" in edge["target_labels"]:
                value: typing.Any = {"entity": target["id"]}
            else:
                value = self.normal(target["id"])
            edge_properties = {
                key: value
                for key, value in edge["properties"].items()
                if key not in INTERNAL_EDGE_PROPERTIES
            }
            if edge_properties:
                value = {"to": value, "edge": edge_properties}
            values = held.setdefault(edge["type"], [])
            if value not in values:
                values.append(value)
        if only is not None:
            wanted = set(only)
            properties = {k: v for k, v in properties.items() if k in wanted}
            held = {k: v for k, v in held.items() if k in wanted}
            return {"properties": properties, "holds": held}
        return {"type": node.get("type"), "properties": properties, "holds": held}

    def hash_of(self, node_id: str) -> str | None:
        """The hash of what is cited when the node is: the node, and those fields of its head that the head's class
        names (`Document.Meta(cited_with=[...])`). None if the head has no such node"""
        if node_id not in self.nodes:
            return None
        form: list[typing.Any] = [HASH_VERSION, self.normal(node_id)]
        if node_id != self.root["id"]:
            head_class = ModelRegistry._model_dict.get(str(self.root.get("type")))
            with_head = getattr(getattr(head_class, "_meta", None), "cited_with", [])
            if with_head:
                form.append(self.normal(self.root["id"], only=with_head))
        text = json.dumps(form, sort_keys=True, default=str, separators=(",", ":"))
        return f"{HASH_VERSION}:{hashlib.sha256(text.encode()).hexdigest()}"


async def read_tree(tx: Transaction, head_id: str, head_type: str) -> Tree | None:
    """A head as it is now in the transaction (whether or not it is published). None if there is none, or it is
    deleted"""
    head_class = ModelRegistry._model_dict.get(head_type)
    if head_class is None:
        return None
    query, params = build_fetch_document_query(head_class, uuid.UUID(head_id))  # ty: ignore[invalid-argument-type]
    params = {**params, "see_unpublished": True}
    result = await tx.run(query, **params)  # ty: ignore[invalid-argument-type]
    records = await result.data()
    if not records:
        return None
    record = records[0]
    edges_from: dict[str, list[dict[str, typing.Any]]] = {}
    nodes = {record["root"]["id"]: record["root"]}
    for edge in record["edges"]:
        edges_from.setdefault(edge["source"], []).append(edge)
        if "Entity" not in edge["target_labels"]:
            nodes[edge["target"]["id"]] = edge["target"]
    for outgoing in edges_from.values():
        outgoing.sort(key=lambda edge: (edge["type"], _list_order(edge)))
    return Tree(
        root=record["root"],
        edges_from=edges_from,
        nodes=nodes,
        version=record["meta"]["version"],
    )


# --- writing a citation -----------------------------------------------------------------------------------------------

TARGETS_QUERY = f"""
    UNWIND $ids AS id
    MATCH (node:PGIndexableNode {{id: id}})
    OPTIONAL MATCH (head:HeadNode {{id: coalesce(node.head_node_id, node.id)}})
    RETURN node.id AS id, node.type AS type, node.label AS label, node:Entity AS entity,
           head.id AS head, head.type AS head_type, {fragments.deleted("head")} AS deleted
"""

TOUCH_QUERY = """
    UNWIND $heads AS id
    MATCH (head:HeadNode {id: id})
    SET head.pg_cited = $now
    RETURN count(head) AS touched
"""

RECORD_UNPROTECTED_QUERY = """
    UNWIND $rows AS row
    MATCH (citation:PGIndexableNode {id: row.id})
    SET citation.target_type = row.type,
        citation.target_head_id = row.head,
        citation.cited_label = row.label
    RETURN count(citation) AS written
"""

RECORD_QUERY = """
    UNWIND $rows AS row
    MATCH (citation:PGIndexableNode {id: row.id})
    SET citation.target_type = row.type,
        citation.target_head_id = row.head,
        citation.cited_version = row.version,
        citation.cited_hash = row.hash,
        citation.cited_label = row.label
    RETURN count(citation) AS written
"""


def _previous_query() -> str:
    return f"""
    MATCH {dialect().tree_below("(head:HeadNode {id: $id})", "(citation:PGCitation)")}
    RETURN citation.target_id AS target, citation.target_type AS type, citation.target_head_id AS head,
           citation.cited_version AS version, citation.cited_hash AS hash, citation.cited_label AS label
    """


async def previous(
    tx: Transaction, head_id: typing.Any
) -> dict[str, dict[str, typing.Any]]:
    """What the citations of a head record now, before it is written again, by what each cites (in other documents)"""
    if not any_citations():
        return {}
    result = await tx.run(_previous_query(), id=str(head_id))  # ty: ignore[invalid-argument-type]
    # (not those of its own parts: one of them that this write removes is a citation of nothing)
    return {
        row["target"]: row for row in await result.data() if row["head"] != str(head_id)
    }


def _gone(target: dict[str, typing.Any] | None) -> bool:
    return target is None or target["head"] is None or target["deleted"]


def _refuse_what_cannot_be_cited(
    found: list[tuple[typing.Any, Allowed]],
    targets: dict[str, dict[str, typing.Any]],
    kept: typing.Container[str] = (),
) -> None:
    """`PanglossReferenceError` naming each citation of what is not there, of an entity, or of a class its field does
    not allow (`targets`: what `TARGETS_QUERY` found, by id; `kept`: ids that may be gone)"""
    problems: list[str] = []
    for citation, allowed in found:
        target = targets.get(str(citation.target_id))
        named = f"{citation.target_type} {citation.target_id}"
        if target is None or _gone(target):
            if str(citation.target_id) in kept:
                continue
            problems.append(f"{named} does not exist (or is deleted)")
        elif target["entity"]:
            problems.append(
                f"{named} is an entity: only a document can be cited (an entity is referred to as it is)"
            )
        elif allowed is not None and not allows(allowed, target["type"]):
            names = ", ".join(sorted(c.__name__ for c in allowed)) or "nothing"
            problems.append(
                f"{named} is a {target['type']}, which cannot be cited here (allowed: {names})"
            )
    if problems:
        raise PanglossReferenceError(
            "A citation names what cannot be cited: " + "; ".join(sorted(set(problems)))
        )


async def check_before(
    tx: Transaction, instance: typing.Any, own: typing.Collection[str]
) -> None:
    """Before a new head is written: the citations of what is already in the database (not of the head's own parts,
    `own`, which are there only once it is written) are checked, so that a write that would be refused writes
    nothing. That matters where nothing is rolled back: Memgraph's analytical mode, which `bulk-load` uses, kept a
    refused record whole when the check came only after it. `record` checks again, with the parts, after the write"""
    if not any_at_all():
        return
    found = [
        (citation, allowed)
        for citation, allowed in citations_in(instance)
        if str(citation.target_id) not in own
    ]
    if not found:
        return
    ids = sorted({str(citation.target_id) for citation, _ in found})
    result = await tx.run(TARGETS_QUERY, ids=ids)  # ty: ignore[invalid-argument-type]
    _refuse_what_cannot_be_cited(found, {row["id"]: row for row in await result.data()})


async def record(
    tx: Transaction,
    instance: typing.Any,
    kept: dict[str, dict[str, typing.Any]] | None = None,
) -> None:
    """After a head is written, in its transaction: check what its citations name, and put on each what is recorded
    of it. `PanglossReferenceError` if one names what is not there, or what its field does not allow.

    `kept` (`previous`, read before an update): a citation the document already had of something that has since been
    removed (by an admin's override) stays as it was, so that the document can still be saved; a new one cannot be
    made.

    A citation that does not protect has only its class, head and label recorded: the head it cites is not written
    to, nor read."""
    if not any_at_all():
        return
    every = citations_in(instance)
    if not every:
        return
    kept = kept or {}

    ids = sorted({str(citation.target_id) for citation, _ in every})
    result = await tx.run(TARGETS_QUERY, ids=ids)  # ty: ignore[invalid-argument-type]
    targets = {row["id"]: row for row in await result.data()}

    unprotected = [pair for pair in every if not is_protecting(pair[0])]
    found = [pair for pair in every if is_protecting(pair[0])]
    # (of one that does not protect, nothing is kept that is gone: what wrote it writes it again)
    _refuse_what_cannot_be_cited(unprotected, targets)
    _refuse_what_cannot_be_cited(found, targets, kept)
    if unprotected:
        result = await tx.run(
            RECORD_UNPROTECTED_QUERY,
            rows=[
                {
                    "id": str(citation.id),
                    "type": targets[str(citation.target_id)]["type"],
                    "head": targets[str(citation.target_id)]["head"],
                    "label": targets[str(citation.target_id)]["label"],
                }
                for citation, _ in unprotected
            ],
        )
        await result.consume()
    if not found:
        return

    # The cited heads are written to before they are read: a write of one of them that is under way then conflicts
    # with this one (or this one waits for it), and what is read after is what that write left
    targets = {id: target for id, target in targets.items() if not _gone(target)}
    heads = sorted({target["head"] for target in targets.values()})
    result = await tx.run(
        TOUCH_QUERY,
        heads=heads,
        now=datetime.datetime.now(datetime.UTC).isoformat(),
    )
    await result.consume()

    trees: dict[str, Tree | None] = {}
    for target in targets.values():
        if target["head"] not in trees:
            trees[target["head"]] = await read_tree(
                tx, target["head"], target["head_type"]
            )

    rows = []
    for citation, _ in found:
        target = targets.get(str(citation.target_id))
        if target is None:
            rows.append({"id": str(citation.id), **kept[str(citation.target_id)]})
            continue
        tree = trees[target["head"]]
        hash_of = tree.hash_of(target["id"]) if tree is not None else None
        if tree is None or hash_of is None:
            raise PanglossReferenceError(
                f"A citation names what cannot be cited: {citation.target_type} {citation.target_id} does not "
                "exist (or is deleted)"
            )
        rows.append(
            {
                "id": str(citation.id),
                "type": target["type"],
                "head": target["head"],
                "version": tree.version,
                "hash": hash_of,
                "label": target["label"],
            }
        )
    result = await tx.run(RECORD_QUERY, rows=rows)
    await result.consume()


# --- protecting what is cited -----------------------------------------------------------------------------------------

# Who cites the nodes of a head: found by the index on `target_head_id`. A citation in a deleted document does not
# count, nor one in the head itself (it is written again with what it cites)
CITING_QUERY = f"""
    MATCH (citation:PGCitation {{target_head_id: $id}})
    MATCH (holder:HeadNode {{id: coalesce(citation.head_node_id, citation.id)}})
    WHERE {fragments.not_deleted("holder")} AND holder.id <> $id
    RETURN citation.id AS citation, citation.target_id AS target, citation.cited_label AS target_label,
           coalesce(citation.changed_since_cited, false) AS changed,
           holder.id AS id, holder.type AS type, holder.label AS label,
           {fragments.published("holder")} AS published
    ORDER BY label, id, target, citation
"""

# (of one part, for the page of a part of a document)
CITING_PART_QUERY = CITING_QUERY.replace(
    "{target_head_id: $id}", "{target_id: $id}"
).replace("AND holder.id <> $id", "")

# (the same of the citations that do not protect, by their own index: "derived from this")
UNPROTECTED_CITING_QUERY = CITING_QUERY.replace(
    "(citation:PGCitation {", "(citation:PGUnprotectedCitation {"
).replace(
    "coalesce(citation.changed_since_cited, false) AS changed", "false AS changed"
)
UNPROTECTED_CITING_PART_QUERY = UNPROTECTED_CITING_QUERY.replace(
    "{target_head_id: $id}", "{target_id: $id}"
).replace("AND holder.id <> $id", "")

MARK_QUERY = """
    UNWIND $ids AS id
    MATCH (citation:PGIndexableNode {id: id})
    SET citation.changed_since_cited = true
    RETURN count(citation) AS marked
"""


async def citing(tx: Transaction, head_id: typing.Any) -> list[dict[str, typing.Any]]:
    """The citations of the nodes of a head (and of the head), from documents that are not deleted: each with what
    it cites (`target`) and the head document it is in (`id`, `type`, `label`, `published`)"""
    if not any_citations():
        return []
    result = await tx.run(CITING_QUERY, id=str(head_id))  # ty: ignore[invalid-argument-type]
    return await result.data()


@dataclasses.dataclass
class Guard:
    """What cites a head, and what each cited part was, before a write of the head"""

    head_id: str
    head_type: str
    citations: list[dict[str, typing.Any]]
    before: dict[str, str | None]


async def before_change(
    tx: Transaction, head_id: typing.Any, head_type: str
) -> Guard | None:
    """Before a head is written again: what cites it, and what those parts are now. None if nothing does"""
    found = await citing(tx, head_id)
    if not found:
        return None
    tree = await read_tree(tx, str(head_id), head_type)
    targets = {row["target"] for row in found}
    return Guard(
        head_id=str(head_id),
        head_type=head_type,
        citations=found,
        before={
            target: tree.hash_of(target) if tree is not None else None
            for target in targets
        },
    )


def _reported(rows: list[dict[str, typing.Any]]) -> list[dict[str, typing.Any]]:
    return [
        {
            "target": row["target"],
            "target_label": row["target_label"],
            "id": row["id"],
            "type": row["type"],
            "label": row["label"],
        }
        for row in rows[:MAX_REPORTED]
    ]


def _documents(rows: list[dict[str, typing.Any]]) -> str:
    names = sorted({f"{row['type']} “{row['label']}”" for row in rows})
    shown = ", ".join(names[:MAX_REPORTED])
    return shown + (
        f" and {len(names) - MAX_REPORTED} more" if len(names) > MAX_REPORTED else ""
    )


def refusal(
    changed: list[dict[str, typing.Any]], removed: list[dict[str, typing.Any]]
) -> PanglossCitedError:
    parts = []
    if removed:
        parts.append(
            f"it would remove what is cited as evidence by {_documents(removed)}"
        )
    if changed:
        parts.append(
            f"it would change what is cited as evidence by {_documents(changed)}"
        )
    return PanglossCitedError(
        "This is not written: " + ", and ".join(parts),
        changed=_reported(changed),
        removed=_reported(removed),
        fix=(
            "Change the citations first, so that nothing cites what is removed (an admin may override this with "
            "`acknowledge_citations=removals`)"
            if removed
            else "Write it again with `acknowledge_citations`, which marks each citation as changed since it was "
            "cited, or change the citations first"
        ),
    )


async def after_change(tx: Transaction, guard: Guard | None) -> None:
    """After the head is written, in the same transaction: what each cited part is now, against what it was. Raises
    `PanglossCitedError` (and so nothing is written) for a change that is not acknowledged, or a removal that is not
    overridden; otherwise marks each changed citation.

    A citation in a document that is not published does not refuse anything (who is refused may not be able to see
    it): it is marked, as the others are."""
    if guard is None:
        return
    tree = await read_tree(tx, guard.head_id, guard.head_type)
    changed, removed = [], []
    for row in guard.citations:
        now = tree.hash_of(row["target"]) if tree is not None else None
        was = guard.before.get(row["target"])
        if now is None and was is not None:
            removed.append(row)
        elif now != was:
            changed.append(row)

    said = acknowledged.get()
    blocking_removed = [row for row in removed if row["published"]]
    blocking_changed = [row for row in changed if row["published"]]
    if (blocking_removed and said != "removals") or (blocking_changed and said is None):
        raise refusal(
            blocking_changed if said is None else [],
            blocking_removed if said != "removals" else [],
        )
    if changed:
        result = await tx.run(MARK_QUERY, ids=[row["citation"] for row in changed])
        await result.consume()


def _citing_fields_query() -> str:
    return f"""
    MATCH (citation:PGCitation {{target_id: $id}})
    MATCH (holder:HeadNode {{id: coalesce(citation.head_node_id, citation.id)}})
    WHERE {fragments.not_deleted("holder")}
    MATCH (parent)-[edge]->(citation)
    WHERE NOT coalesce(edge.reverse, false)
    RETURN parent.type AS parent, type(edge) AS field,
           holder.id AS id, holder.type AS type, holder.label AS label,
           {fragments.published("holder")} AS published
    ORDER BY label, id
    """


async def check_class_held(tx: Transaction, head_id: typing.Any, new: type) -> None:
    """After the class of a document is changed in place, in the transaction: every citation of the document itself
    (not of its parts, which are what they were, or are gone and refused as such) must be in a field that takes the
    class it is now. `PanglossClassChangeError` (and so nothing is written) if one is not. A citation inside a cited
    basis, or in a field of a generic wrapper, takes any class"""
    if not any_citations():
        return
    result = await tx.run(_citing_fields_query(), id=str(head_id))  # ty: ignore[invalid-argument-type]
    refusing = []
    for row in await result.data():
        holder = ModelRegistry._model_dict.get(str(row["parent"]))
        definition = (
            holder._meta.fields.get(row["field"]) if holder is not None else None
        )
        if not isinstance(definition, RelationFieldDefinition):
            continue
        allowed = _cited_by_options(definition.type_options)
        if allowed is not None and not allows(allowed, new.__name__):
            refusing.append(row)
    if refusing:
        # (a document the writer may not see is counted, not named)
        see = unpublished_visible()
        named = [row for row in refusing if row["published"] or see]
        hidden = len({row["id"] for row in refusing}) - len(
            {row["id"] for row in named}
        )
        by = " and ".join(
            part
            for part in (
                _documents(named) if named else "",
                f"{hidden} document{'s' if hidden != 1 else ''} that cannot be shown"
                if hidden
                else "",
            )
            if part
        )
        raise PanglossClassChangeError(
            f"{head_id} cannot become a {new.__name__}: it is cited in a field that cannot hold a {new.__name__}, "
            f"by {by}"
        )


async def check_removal(tx: Transaction, head_id: typing.Any) -> None:
    """Before a head is deleted: refused while a published document cites it or a part of it, unless an admin
    overrides"""
    if acknowledged.get() == "removals":
        return
    blocking = [row for row in await citing(tx, head_id) if row["published"]]
    if blocking:
        raise refusal([], blocking)


# --- reading ----------------------------------------------------------------------------------------------------------


def _citations_of(
    tree: typing.Any,
    found: list[dict[str, typing.Any]],
    bases: list[dict[str, typing.Any]] | None = None,
) -> None:
    if isinstance(tree, list):
        for item in tree:
            _citations_of(item, found, bases)
    elif isinstance(tree, dict):
        if tree.get("type") in CITATION_TYPES and "target_id" in tree:
            found.append(tree)
            return
        if tree.get("type") == BASIS and "via_id" in tree and bases is not None:
            bases.append(tree)
        for value in tree.values():
            if isinstance(value, (list, dict)):
                _citations_of(value, found, bases)


def _hydrate_query() -> str:
    return f"""
    UNWIND $ids AS id
    OPTIONAL MATCH (node:PGIndexableNode {{id: id}})
    OPTIONAL MATCH (head:HeadNode {{id: coalesce(node.head_node_id, node.id)}})
    RETURN id, node.label AS label, node.type AS type,
           head.id AS head, head.type AS head_type, head.label AS head_label,
           (head IS NULL OR {fragments.deleted("head")}) AS gone,
           {fragments.published("head")} AS published,
           {dialect().meta_property("node", "semantic_spaces")} AS spaces
    """


async def hydrate(tx: Transaction, tree: typing.Any) -> None:
    """Put on each citation in what was read (the tree of a document, or several) what it names as it is now: its
    label, the head it is in, the semantic spaces round it; or that it is gone, or not to be seen by this reader"""
    if not any_at_all():
        return
    found: list[dict[str, typing.Any]] = []
    bases: list[dict[str, typing.Any]] = []
    _citations_of(tree, found, bases)
    if not found and not bases:
        return
    ids = sorted(
        {str(citation["target_id"]) for citation in found}
        | {str(basis["via_id"]) for basis in bases}
    )
    result = await tx.run(_hydrate_query(), ids=ids)  # ty: ignore[invalid-argument-type]
    targets = {row["id"]: row for row in await result.data()}
    see_unpublished = unpublished_visible()
    # (what a basis was made of, as it is now: there, gone, or not for this reader)
    for basis in bases:
        target = targets.get(str(basis["via_id"]))
        basis["via_label_now"] = None
        if target is None or target["gone"]:
            basis["via_state"] = "removed"
        elif not target["published"] and not see_unpublished:
            basis["via_state"] = "hidden"
        else:
            basis["via_state"] = "there"
            basis["via_label_now"] = target["label"]
    for citation in found:
        target = targets.get(str(citation["target_id"]))
        citation["target_label"] = None
        citation["target_head_type"] = None
        citation["target_head_label"] = None
        citation["target_spaces"] = []
        if target is None or target["gone"]:
            citation["target_state"] = "removed"
        elif not target["published"] and not see_unpublished:
            citation["target_state"] = "hidden"
        else:
            citation["target_state"] = "there"
            citation["target_type"] = target["type"]
            citation["target_label"] = target["label"]
            citation["target_head_id"] = target["head"]
            citation["target_head_type"] = target["head_type"]
            citation["target_head_label"] = target["head_label"]
            citation["target_spaces"] = list(target["spaces"] or [])


async def cited_by(
    tx: Transaction, head_id: typing.Any, unprotected: bool = False
) -> list[dict[str, typing.Any]]:
    """What a reader is shown of who cites a head and its parts: the citations of `citing`, those in documents the
    reader may not see without their document (`hidden`). `unprotected`: instead, the citations that do not protect
    it ("derived from this"), which are never `changed`"""
    see_unpublished = unpublished_visible()
    shown = []
    if unprotected:
        rows = []
        if any_unprotected():
            result = await tx.run(UNPROTECTED_CITING_QUERY, id=str(head_id))  # ty: ignore[invalid-argument-type]
            rows = await result.data()
            if not rows:
                result = await tx.run(UNPROTECTED_CITING_PART_QUERY, id=str(head_id))  # ty: ignore[invalid-argument-type]
                rows = await result.data()
    else:
        rows = await citing(tx, head_id)
    if not unprotected and not rows and any_citations():
        # (not a head that is cited: a part of one, perhaps)
        result = await tx.run(CITING_PART_QUERY, id=str(head_id))  # ty: ignore[invalid-argument-type]
        rows = await result.data()
    for row in rows:
        if row["published"] or see_unpublished:
            shown.append({**row, "hidden": False})
        else:
            shown.append(
                {
                    "citation": None,
                    "target": row["target"],
                    "target_label": row["target_label"],
                    "changed": row["changed"],
                    "id": None,
                    "type": None,
                    "label": None,
                    "published": False,
                    "hidden": True,
                }
            )
    return shown


# --- checking the data ------------------------------------------------------------------------------------------------

ALL_QUERY = """
    MATCH (citation:PGCitation)
    RETURN citation.id AS citation, citation.target_id AS target, citation.target_type AS target_type,
           coalesce(citation.head_node_id, citation.id) AS holder
"""

THERE_QUERY = f"""
    UNWIND $ids AS id
    MATCH (node:PGIndexableNode {{id: id}})
    OPTIONAL MATCH (head:HeadNode {{id: coalesce(node.head_node_id, node.id)}})
    WITH node, head WHERE head IS NOT NULL AND {fragments.not_deleted("head")}
    RETURN node.id AS id
"""

HOLDERS_QUERY = f"""
    UNWIND $ids AS id
    MATCH (head:HeadNode {{id: id}})
    WHERE {fragments.not_deleted("head")}
    RETURN head.id AS id, head.type AS type, head.label AS label
"""


OF_CLASSES_QUERY = """
    UNWIND $ids AS id
    MATCH (node:PGIndexableNode {id: id})
    WHERE any(label IN labels(node) WHERE label IN $classes)
    RETURN node.id AS id
"""


async def of_classes(
    tx: Transaction, classes: list[str]
) -> list[dict[str, typing.Any]]:
    """The citations, in documents that are not deleted, of nodes of these classes (by label, so of their
    subclasses too): what a migration that deletes the classes would leave citing nothing. Rows as
    `pointing_at_nothing` gives them. (Asked of the database as it is, whatever the models say now: a migration may
    be removing the last `Cites`)"""
    if not classes:
        return []
    rows = await (await tx.run(ALL_QUERY)).data()
    if not rows:
        return []
    result = await tx.run(
        OF_CLASSES_QUERY,
        ids=sorted({row["target"] for row in rows}),
        classes=sorted(classes),
    )
    hit = set(await result.value())
    found = [row for row in rows if row["target"] in hit]
    if not found:
        return []
    result = await tx.run(HOLDERS_QUERY, ids=sorted({row["holder"] for row in found}))  # ty: ignore[invalid-argument-type]
    holders = {row["id"]: row for row in await result.data()}
    return [
        {
            "citation": row["citation"],
            "target": row["target"],
            "target_type": row["target_type"],
            **holders[row["holder"]],
        }
        for row in found
        if row["holder"] in holders
    ]


async def pointing_at_nothing(tx: Transaction) -> list[dict[str, typing.Any]]:
    """The citations, in documents that are not deleted, of what is not there any more (removed by an admin's
    override, or by a write that went round the checks): each with its `citation`, `target`, `target_type` and the
    head document it is in (`id`, `type`, `label`). For `pangloss check-data`"""
    if not any_citations():
        return []
    result = await tx.run(ALL_QUERY)
    rows = await result.data()
    if not rows:
        return []
    # (from the ids in hand: a join written from the citations' side reads every node)
    result = await tx.run(THERE_QUERY, ids=sorted({row["target"] for row in rows}))  # ty: ignore[invalid-argument-type]
    there = set(await result.value())
    lost = [row for row in rows if row["target"] not in there]
    if not lost:
        return []
    result = await tx.run(HOLDERS_QUERY, ids=sorted({row["holder"] for row in lost}))  # ty: ignore[invalid-argument-type]
    holders = {row["id"]: row for row in await result.data()}
    return [
        {
            "citation": row["citation"],
            "target": row["target"],
            "target_type": row["target_type"],
            **holders[row["holder"]],
        }
        for row in lost
        if row["holder"] in holders
    ]
