"""The plan of a document already stored, for its stand-ins (step 10.2c of
implementation_docs/similarity-build-plan.md, row f): the head of the node asked about read as the reader, made an
`Update` as review's `rewrite_part` makes one (`editable(view.model_dump())`), and the plan of that update made as an
update makes it, **without writing and without running an update's write**.

Of what `update_head_node` does before its transaction this takes what makes the database model (`citations.resolve`,
`to_db_model`, `fill_labels`), and of what it does inside it only the plan (`plan_update`). It leaves out the
`@before_update`s of the classes (which may refuse a change; the document is stored, and nothing is changed), and the
transaction's checks and reads (the user, the version, a change of class, what cites it, `checked_plan`): what they
refuse is a write, and none is made. The plan's nodes keep their stored ids (an update's plan gives every node that
has one its id), so the stand-in asked about is the node of the plan of that id.

A head that is an entity is read as it is edited (`get_for_edit`, as review's `give_uris` reads one), a document as
it is read (`get`). A stored document cannot be refused: what would refuse it as an update (the `Update` not
taking the view, a `@update_validator`, a label template) is `Unplannable`, which the route answers as a 404."""

from typing import Any
from uuid import UUID

from pangloss_core import backend
from pangloss_models import Entity, ModelRegistry, PanglossWriteRefused
from pydantic import ValidationError


class Unplannable(Exception):
    """The document of a stored stand-in cannot be planned as an update of it (said with the reason)"""


# (a node below a head: a document nested in it, whose head is there and not deleted)
NODE_QUERY = """
MATCH (n:PGIndexableNode {id: $id})
WHERE n.head_node_id IS NOT NULL
MATCH (head:HeadNode {id: n.head_node_id})
RETURN head.id AS head, head.type AS type
"""


async def _head_of(id: str) -> tuple[str, str] | None:
    database = backend.current().database()

    @database.read_transaction
    async def read(tx: Any) -> tuple[str, str] | None:
        found = await (await tx.run(NODE_QUERY, id=id)).single()
        return None if found is None else (str(found["head"]), str(found["type"]))

    return await read()


async def stored_plan(id: str) -> Any | None:
    """The plan of the document that holds the node `id` (`pangloss_cypher.write_plan.WritePlan`), as the reader
    may see it (the head read as `GET /api/NAME/{head}` reads it); None if the node is not below a head, or the
    reader may not see the head. Nothing is written"""
    found = await _head_of(id)
    if found is None:
        return None
    head, type_name = found
    model: Any = ModelRegistry._model_dict.get(type_name)
    if model is None or not hasattr(model, "Update"):
        return None
    is_entity = isinstance(model, type) and issubclass(model, Entity)
    view = await (model.get_for_edit if is_entity else model.get)(UUID(head))
    if view is None:
        return None
    return await plan_of_view(model, view)


async def plan_of_view(model: Any, view: Any) -> Any:
    """The plan of a head already read (`view`, as `rewriting.read_head` reads it), as an update of it with nothing
    changed would make it: what the worker that suggests plans a marked head by (step 10.5d), and `stored_plan`
    after its read. `Unplannable` if it cannot be. Nothing is read but what the plan's labels and citations need,
    and nothing is written"""
    from pangloss_cypher.write_functions import read_labels, to_db_model
    from pangloss_cypher.write_plan import plan_update
    from pangloss_cypher import citations
    from pangloss_models.label_templates import fill_labels
    from pangloss_models.utils import editable

    try:
        update = model.Update(**editable(view.model_dump()))
        await citations.resolve(update)
        db_instance = to_db_model(update)
        await fill_labels(db_instance, read_labels)
    except (ValidationError, PanglossWriteRefused) as error:
        raise Unplannable(f"{model.__name__} {view.id}: {error}") from error
    return plan_update(db_instance)
