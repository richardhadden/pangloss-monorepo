import datetime
from uuid import UUID, uuid7

from pangloss_models.model_bases.base_models import (
    _APIHeadMeta,
    _ListItems,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentHeadViewBase,
    _DocumentReferenceViewBase,
    _DocumentUpdateBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateDBBase,
    _EntityHeadViewBase,
    _EntityReferenceViewBase,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pydantic import AnyHttpUrl


def save(
    tx,
    self: _EntityCreateDBBase
    | _DocumentCreateDBBase
    | _EntityUpdateDBBase
    | _DocumentUpdateDBBase,
):
    print("wahoo!", self)


def get_document(cls: type[Document], id: UUID | AnyHttpUrl) -> _DocumentHeadViewBase:
    return cls.HeadView(
        id=uuid7(),
        label="A document",
        meta=_APIHeadMeta(
            created_by="asf",
            created_when=datetime.datetime.now(),
            updated_by="asdf",
            updated_when=datetime.datetime.now(),
        ),
    )


def get_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> _EntityHeadViewBase | None:
    pass


def create_head_node(self: _DocumentCreateBase, return_created: bool = False):
    pass


def update_head_node(
    self: _DocumentUpdateBase | _EntityUpdateBase, return_type="Reference"
):
    pass


def list_items(
    cls: type[Document | Entity], search_terms: str
) -> _ListItems[_DocumentReferenceViewBase | _EntityReferenceViewBase]:
    pass
