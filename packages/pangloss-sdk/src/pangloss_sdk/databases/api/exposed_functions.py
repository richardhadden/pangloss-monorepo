import datetime
from typing import TYPE_CHECKING, overload
from uuid import UUID, uuid7

from pangloss_models.model_bases.base_models import (
    _APIHeadMeta,
    _CreateDBBase,
    _UpdateDBBase,
)
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentHeadViewBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityCreateBase,
    _EntityCreateDBBase,
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


def create_head_node(self: _DocumentCreateBase, return_created: bool = False):
    pass
