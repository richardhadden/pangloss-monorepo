"""Why a candidate is offered: the entities the payload names that are also named in a stored document together with
the candidate (step 10.3 of implementation_docs/similarity-build-plan.md, "reasons"). Since step 11.2 their number is
in the score too (`score.shared_score`), so they are asked once for every candidate found of a request, before the
cut to `limit`, and uncut: what is shown of them is cut afterwards (`RECONCILE_REASONS`, `api.answer`).

The entities of the payload are those its plan refers to (each `ReferenceToExisting`, a URL as the node it names)
and those written in it that exist, as the write would resolve them (`pangloss_cypher.validate_write.resolved_plan`:
an entity merged into another is its survivor). A stored document shares one with a candidate when, below or in its
head, one node has a forward relation to the candidate and one has a forward relation to that entity.

One query for every candidate of a request, as the reader may see it: the document a head document the reader may
look through (`fragments.listed`: not deleted, published unless the reader may see what is not), not a class whose
references do not count (`fragments.counted`: a derived document), and not the plan's own head (the stored route's
document); the shared entity looked through too; forward edges of fields only (`fragments.forward`), not those of a
relation the server computes (`fragments.reference`), as `pangloss_vectors.search._used` counts a use.

**A guess no person has confirmed is no evidence** (step 10.5c; `hooks.unconfirmed`: with `pangloss-library`, every
class of suggestion). An edge does not count when the node it starts from is a node of such a class, or is below one
in its document through wrappers (a `WeightedAlternative` in the suggestion, the suggestion in an `InRole`): in the
stored documents (`unconfirmed`, a `NOT EXISTS` that walks up from the node through the wrappers that hold it, from a
node below a head only), and in the plan asked about (`named_entities`: what its own suggestions name is not among its
entities). With no such class the query is what it was."""

from collections.abc import Mapping, Sequence
from typing import Any


def unconfirmed(node: str, names: Sequence[str]) -> str:
    """A condition (with its `AND`, or nothing with no `names`): the node `node` (one with an edge to what is counted)
    is not of a class of `names` (`hooks.unconfirmed_classes()`), nor below one through the wrappers that hold it. A
    head (`head_node_id` null: a head document, an entity) is below nothing, and is not walked from: the edges into
    an entity are from every document that names it. Each class by its own label (a class below one is named itself)"""
    from pangloss_cypher import fragments
    from pangloss_cypher.transactions import dialect

    if not names:
        return ""
    held = f"{node}_held"
    for name in names:
        fragments.label(name)  # (refused if it cannot be the name of a class)
    labels = ", ".join(f"'{name}'" for name in names)
    return (
        f" AND ({node}.head_node_id IS NULL OR NOT EXISTS {{ MATCH ({node})"
        f"{dialect().through_wrappers(f'{node}_up', backwards=True)}({held}) "
        f"WHERE any(label IN labels({held}) WHERE label IN [{labels}]) }})"
    )


def _query(fragments: Any, names: Sequence[str] = ()) -> str:
    """What the candidates `$candidates` share with the entities `$entities`: each pair, and in how many documents.
    `names`: the classes whose nodes hold a guess no person has confirmed (`unconfirmed`)"""
    return f"""
        UNWIND $entities AS xid
        MATCH (x:PGIndexableNode {{id: xid}})
        WHERE {fragments.listed("x")}
        MATCH (x)<-[e2]-(n2:PGIndexableNode)
        WHERE {fragments.forward("e2")}{fragments.reference("e2")}{unconfirmed("n2", names)}
        WITH xid, collect(DISTINCT coalesce(n2.head_node_id, n2.id)) AS heads
        WITH collect(xid) AS xs, collect(heads) AS hs
        UNWIND $candidates AS cid
        MATCH (c:PGIndexableNode {{id: cid}})<-[e1]-(n1:PGIndexableNode)
        WHERE {fragments.forward("e1")}{fragments.reference("e1")}{unconfirmed("n1", names)}
        WITH DISTINCT xs, hs, cid, coalesce(n1.head_node_id, n1.id) AS hid
        WHERE hid <> $own
        MATCH (h:HeadNode {{id: hid}})
        WHERE h:Document AND {fragments.listed("h")}{fragments.counted("h")}
        UNWIND range(0, size(xs) - 1) AS i
        WITH cid, hid, xs[i] AS xid, hs[i] AS heads
        WHERE xid <> cid AND hid IN heads
        RETURN cid, xid, count(hid) AS documents
    """


def guessed(plan: Any, names: Sequence[str]) -> set[str]:
    """The ids of the nodes of a plan that are of a class of `names` (`hooks.unconfirmed_classes()`) or below one
    through wrappers, in its document, as `unconfirmed` finds them in a stored one (not an entity written in it, which
    is a head of its own; not what is below a document in a suggestion)"""
    from pangloss_cypher.write_plan import PlannedNode
    from pangloss_models.search import WRAPPER_LABELS

    wanted = set(names)
    found: set[str] = set()

    def walk(node: Any, below: bool) -> None:
        guess = node.type in wanted
        if below or guess:
            found.add(node.id)
        # (what it holds is below a guess if it is one, or a wrapper that is below one)
        holds = guess or (below and any(l in WRAPPER_LABELS for l in node.labels))
        for relation in node.relations:
            if isinstance(relation.target, PlannedNode):
                walk(relation.target, holds)

    if wanted:
        walk(plan.head, False)
    return found


def named_entities(
    plan: Any,
    existing: Mapping[Any, Any],
    urls: Mapping[str, str],
    guesses: Sequence[str] = (),
) -> list[str]:
    """The ids of the entities a resolved plan refers to, and of those written in it that exist; not by a relation
    from a node of a class of `guesses` (`hooks.unconfirmed_classes()`), or below one (`guessed`)"""
    from pangloss_cypher.write_plan import InlineEntity, ReferenceToExisting

    found: set[str] = set()
    left_out = guessed(plan, guesses)
    for node, relation, _ in plan.walk(existing):
        if node.id in left_out:
            continue
        target = relation.target
        if isinstance(target, ReferenceToExisting):
            found.add(
                urls.get(target.value, target.value) if target.is_url else target.value
            )
        elif isinstance(target, InlineEntity) and target.key in existing:
            found.add(str(existing[target.key].id))
    return sorted(found)


async def shared(
    plan: Any,
    candidates: Sequence[str],
    see_unpublished: bool,
    most: int | None = None,
) -> dict[str, list[tuple[str, int]]]:
    """For each candidate, every entity of the plan it is named with in stored documents (at most `most`, if given:
    the service gives none, and cuts what it shows itself), each with in how many, those of the most documents first,
    then by id. Nothing is asked with no candidate. (In one read transaction: the plan resolved, and the query)"""
    from pangloss_core import backend
    from pangloss_cypher.validate_write import resolved_plan
    from pangloss_models import hooks

    if not candidates:
        return {}
    current = backend.current()
    database = current.database()
    names = hooks.unconfirmed_classes()
    query = _query(current.fragments, names)

    @database.read_transaction
    async def read(tx: Any) -> list[tuple[str, str, int]]:
        resolved, existing, urls = await resolved_plan(tx, plan)
        entities = named_entities(resolved, existing, urls, names)
        if not entities:
            return []
        result = await tx.run(
            query,
            candidates=sorted(set(candidates)),
            entities=entities,
            own=str(plan.head.id),
            see_unpublished=see_unpublished,
        )
        return [
            (str(r["cid"]), str(r["xid"]), int(r["documents"])) async for r in result
        ]

    found: dict[str, list[tuple[str, int]]] = {}
    for candidate, entity, documents in await read():
        found.setdefault(candidate, []).append((entity, documents))
    return {
        candidate: sorted(pairs, key=lambda pair: (-pair[1], pair[0]))[:most]
        for candidate, pairs in found.items()
    }
