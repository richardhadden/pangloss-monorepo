"""Things that are wrong with how Zotero is set up, found without Zotero or the database"""

from typing import get_origin

from pangloss_models.exceptions import PanglossMetaError

from pangloss_zotero import config
from pangloss_zotero.mapping import build_table, concrete_classes


def problems(settings) -> list[str]:
    found: list[str] = []
    if not config.api_key(settings):
        found.append("ZOTERO_API_KEY is not set")
    if not config.libraries(settings):
        found.append("ZOTERO_LIBRARIES is empty")
    try:
        build_table()
    except PanglossMetaError as error:
        found.append(str(error))
    for model in concrete_classes():
        create = getattr(model, "Create", None)
        if create is None:
            found.append(f"{model.__name__} has not been initialised")
            continue
        required = [
            name
            for name, field in create.model_fields.items()
            if field.is_required()
            and get_origin(field.annotation) is not list
            and name not in ("type", "id", "label", "create_new")
        ]
        if required:
            found.append(
                f"{model.__name__} has fields the sync cannot give: {', '.join(required)} "
                "(make them optional: `X | None = None`)"
            )
    return found
