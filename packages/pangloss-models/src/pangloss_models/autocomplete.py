"""Finding existing entities by their label, over any set of entity types (see implementation_docs/autocomplete.md).

The types asked for are named (`resolve_entity_types`), and reduced to as few as will find the same
entities (`smallest_types`): a node has the name of each of its parents and traits as a label, so a
class that is a subclass of another one asked for finds nothing more.
"""

import re
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl

from pangloss_models.exceptions import PanglossUnknownTypeError
from pangloss_models.model_bases.base_models import _BaseObject
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.labels import labels_for_model
from pangloss_models.text import fold


class AutocompleteItem(_BaseObject):
    id: UUID | AnyHttpUrl
    type: str
    label: str
    # If it was found by the label of an entity that was merged into it (`Entity.merge`), and not by its own: that label
    merged_label: str | None = None


class AutocompleteResults(_BaseObject):
    """One page of what was found, with the paging fields of a list"""

    results: list[AutocompleteItem]
    count: int
    page: int
    page_size: int
    next_page: int | None
    previous_page: int | None


def resolve_entity_types(names: list[str]) -> list[type]:
    """The classes named, each once, in the order given. A name that is not an entity (or a trait
    that only entities have) raises `PanglossUnknownTypeError`."""
    from pangloss_models.model_registry import ModelRegistry
    from pangloss_models.utils import get_concrete_types, model_is_trait

    models = ModelRegistry.all_models()
    found: list[type] = []
    for name in names:
        if name == "Entity":  # (any entity)
            found.append(Entity)
            continue
        model = models.get(name)
        if model is None:
            raise PanglossUnknownTypeError(f"There is no model called '{name}'")
        if model_is_trait(model):  # type: ignore[arg-type]
            implementing = get_concrete_types(model, include_abstract=True)  # type: ignore[type-var]
            ok = bool(implementing) and all(issubclass(t, Entity) for t in implementing)
        else:
            ok = isinstance(model, type) and issubclass(model, Entity)
        if not ok:
            raise PanglossUnknownTypeError(
                f"'{name}' is not an entity type: only entities can be found by their label"
            )
        if model not in found:
            found.append(model)
    return found


def smallest_types(types: Sequence[type]) -> list[type]:
    """The types that find everything the given ones do: those that are not a subclass (or an
    application of the trait) of another one in the list"""
    result = []
    for model in types:
        # (a trait has no kind, and its labels are its own and those of the traits it extends)
        labels = labels_for_model(model, getattr(model, "__metatype__", ""))  # type: ignore
        if any(other is not model and other.__name__ in labels for other in types):
            continue
        result.append(model)
    return result


def search_words(text: str) -> list[str]:
    """What was typed as the words of the text index: lower case, accents folded (`pangloss_models.text.fold`), cut at
    anything that is not a letter or digit. (That is how the index cuts a label, so no punctuation, and no
    regular-expression character, is left to be matched.)"""
    return re.findall(r"\w+", fold(text))


def labels_to_match(types: Sequence[type]) -> list[str]:
    """The node labels, any of which finds the entities of these types"""
    return [model.__name__ for model in smallest_types(types)]


def excluded_from_global_search() -> list[str]:
    """The names of the classes that "search everything" does not find (`global_search=False`)"""
    from pangloss_models.model_registry import ModelRegistry

    return sorted(
        name
        for name, model in ModelRegistry.all_models().items()
        if isinstance(model, type)
        and issubclass(model, (Document, Entity))
        and not model._meta.global_search  # type: ignore[attr-defined]
    )


def search_everything(
    search_terms: str,
    types: Sequence[type] | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    documents_only: bool = False,
) -> Any:
    """The head documents and entities whose label has every word (of `types` and their subclasses, if given), the most
    connected first (with no words, all of `types`; without those too, nothing); what is awaited on a backend that is async. See implementation_docs/homepage-and-pages.md.
    `documents_only`: no entities (what a citation is chosen from)"""
    from pangloss_core import storage_of

    return storage_of().operations.search_everything(
        search_terms,
        labels_to_match(types) if types else None,
        excluded_from_global_search(),
        page_number,
        page_size,
        documents_only=documents_only,
    )
