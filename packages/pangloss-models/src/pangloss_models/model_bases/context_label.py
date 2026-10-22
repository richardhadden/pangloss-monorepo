from typing import NotRequired, TypedDict


class ContextLabel(TypedDict):
    type: str | None
    id: NotRequired[str]
    contents: NotRequired[list[ContextLabel]]
