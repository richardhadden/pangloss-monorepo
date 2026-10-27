"""The paths of texts.

Without a language, a text is `(section, entity, *rest)`: `("models", "Person", "fields", "birth_place",
"name")`, `("enums", "Colour", "members", "RED", "name")`, `("models", "Person", "plural")`.
In a file the language comes after the entity: `("models", "Person", "de", "fields", "birth_place",
"name")`.

An **item** is what the texts are about: the entity itself, or one of its fields, incoming relations or
members (`("models", "Person", "fields", "birth_place")`). It has no language either.
"""

Path = tuple[str, ...]

SECTIONS = ("models", "enums")


def with_language(path: Path, language: str) -> Path:
    return (*path[:2], language, *path[2:])


def language_of(path: Path) -> str:
    return path[2]


def without_language(path: Path) -> Path:
    return (*path[:2], *path[3:])


def item_of(path: Path) -> Path:
    """The item a text is about (no language, no name of text): `("models", "Person", "fields", "a")`"""
    return without_language(path)[:-1]


def key_of(path: Path) -> str:
    return path[-1]


def as_text(path: Path) -> str:
    return "/".join(path)


def from_text(text: str) -> Path:
    return tuple(text.split("/"))
