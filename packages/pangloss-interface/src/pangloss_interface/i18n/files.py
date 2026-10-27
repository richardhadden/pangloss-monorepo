"""Reading and writing the translation files.

    <app>/translations/models.jsonc   the texts of the app's models and enums, all languages (people edit it)
    <app>/translations/.state.json    what the generator wrote the last time (`merge.Leaf`; commit it)
    <app>/translations/ui.jsonc       fixed text for the page: {"log_in": {"en": "Log in", "de": ...}}
    <project>/translations/...        the project's overrides, in the same forms

`models.jsonc` is `{"models": {...}, "enums": {...}, "_obsolete": {...}}` (see `docs/translations.md`).
"""

import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path as FilePath
from typing import Any

from pangloss_interface.i18n import jsonc
from pangloss_interface.i18n.merge import Leaf
from pangloss_interface.i18n.paths import (
    SECTIONS,
    Path,
    as_text,
    from_text,
    language_of,
)

FOLDER = "translations"
MODELS_FILE = "models.jsonc"
UI_FILE = "ui.jsonc"
STATE_FILE = ".state.json"
OBSOLETE = "_obsolete"

HEADER = [
    "Translations of the models. Edit the texts (not the keys); `pangloss interface translations generate`",
    "keeps what you write and adds what the models add. An empty text is not translated yet; an empty",
    '"plural" is the same as the singular. What is under "_obsolete" is for names that have gone.',
]


class TranslationFileError(ValueError):
    pass


@dataclass
class ModelsFile:
    texts: dict[Path, str] = field(default_factory=dict)
    obsolete: dict[Path, str] = field(default_factory=dict)
    state: dict[Path, Leaf] = field(default_factory=dict)
    # the comments a person wrote above keys (by path in the file; `()` is the top): kept when it is
    # written again
    comments: dict[Path, list[str]] = field(default_factory=dict)


def app_directory(app: str) -> FilePath | None:
    """The folder of an installed app (found without importing it)"""
    try:
        spec = importlib.util.find_spec(app)
    except ImportError, ValueError:
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return FilePath(next(iter(spec.submodule_search_locations)))
    return FilePath(spec.origin).parent if spec.origin else None


def in_project(directory: FilePath, root: FilePath) -> bool:
    """Whether a folder is the project's own (not an installed package, which is not to be written)"""
    resolved = directory.resolve()
    return resolved.is_relative_to(root.resolve()) and not {
        "site-packages",
        ".venv",
    } & set(resolved.parts)


# --- nested <-> flat --------------------------------------------------------------------------------


def flatten(data: Any, source: str, prefix: Path = ()) -> dict[Path, str]:
    """The texts of a nested dict: every string, by its path. Anything else is an error"""
    if isinstance(data, str):
        return {prefix: data}
    if not isinstance(data, dict):
        raise TranslationFileError(
            f"{source}: expected a text or an object at {'/'.join(prefix) or 'the top'}, not {data!r}"
        )
    found: dict[Path, str] = {}
    for key, value in data.items():
        found.update(flatten(value, source, (*prefix, key)))
    return found


def nest(texts: dict[Path, str]) -> dict[str, Any]:
    """The nested dict of texts, in the order of the paths"""
    tree: dict[str, Any] = {}
    for path, text in texts.items():
        node = tree
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = text
    return tree


def split_file(data: Any, source: str) -> tuple[dict[Path, str], dict[Path, str]]:
    """(texts, obsolete) of the content of `models.jsonc`"""
    if not isinstance(data, dict):
        raise TranslationFileError(f"{source}: the top must be an object")
    unknown = set(data) - {*SECTIONS, OBSOLETE}
    if unknown:
        raise TranslationFileError(
            f"{source}: unexpected {', '.join(sorted(unknown))} (only {', '.join(SECTIONS)} and {OBSOLETE})"
        )
    texts = flatten({k: v for k, v in data.items() if k != OBSOLETE}, source)
    obsolete = flatten(data.get(OBSOLETE, {}), source)
    for path in [*texts, *obsolete]:
        if len(path) < 4:
            raise TranslationFileError(
                f"{source}: {'/'.join(path)} is not a text (models/Name/language/name ...)"
            )
    return texts, obsolete


# --- the files --------------------------------------------------------------------------------------


def read_jsonc(path: FilePath) -> Any:
    try:
        return jsonc.loads(path.read_text(encoding="utf-8"))
    except jsonc.JsoncError as error:
        raise TranslationFileError(f"{path}: {error}") from error


KEY_LINE = re.compile(r'^(?P<indent> *)"(?P<key>(?:[^"\\]|\\.)*)":')


def user_comments(text: str, languages: list[str]) -> dict[Path, list[str]]:
    """The comments a person wrote, by the key they are above. The file is in the one form that
    `jsonc.render` writes, so a key's depth is its indentation. A comment that the generator makes
    (`en: ...`, `NEEDS REVIEW: ...`, and the lines under them) is not a person's.

    Only whole-line `//` comments directly above a key (or at the top) are kept: a comment at the end
    of a line, or a `/* */` block, is not."""
    generated = tuple(f"{lang}: " for lang in languages) + ("NEEDS REVIEW: ",)
    header = {line.strip() for line in HEADER}
    found: dict[Path, list[str]] = {}
    pending: list[str] = []
    stack: list[str] = []
    started = False
    continuing = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            body = stripped[2:]
            body = body.removeprefix(" ")
            if stripped in {f"// {h}" for h in header}:
                continue
            if body.startswith(generated):
                continuing = True
                continue
            if continuing and (body.startswith("    ") or not body.strip()):
                continue  # (the lines under a generated comment, a blank one too)
            continuing = False
            pending.append(body)
            continue
        continuing = False
        if stripped == "{" and not started:
            started = True
            if pending:
                found[()] = pending
                pending = []
            continue
        match = KEY_LINE.match(line)
        if match is None:
            pending = []
            continue
        depth = len(match["indent"]) // 2 - 1
        stack = [*stack[:depth], json.loads(f'"{match["key"]}"')]
        if pending:
            found[tuple(stack)] = pending
        pending = []
    return found


def read_models_file(
    directory: FilePath, languages: list[str] | None = None
) -> ModelsFile:
    """The files of an app or the project (`directory` is its `translations` folder); empty if not there.
    `languages` are needed to tell a person's comments from the generator's"""
    result = ModelsFile()
    path = directory / MODELS_FILE
    if path.is_file():
        source = path.read_text(encoding="utf-8")
        result.texts, result.obsolete = split_file(read_jsonc(path), str(path))
        result.comments = user_comments(source, languages or [])
    state_path = directory / STATE_FILE
    if state_path.is_file():
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            result.state = {
                from_text(key): Leaf(**value) for key, value in raw["texts"].items()
            }
        except (ValueError, KeyError, TypeError) as error:
            raise TranslationFileError(f"{state_path}: {error}") from error
    return result


def state_text(state: dict[Path, Leaf]) -> str:
    texts = {
        as_text(path): {
            "base": leaf.base,
            "source": leaf.source,
            "seen": leaf.seen,
            **({"review": True} if leaf.review else {}),
        }
        for path, leaf in sorted(state.items())
    }
    return (
        json.dumps({"version": 1, "texts": texts}, indent=2, ensure_ascii=False) + "\n"
    )


def comments_for(
    texts: dict[Path, str],
    state: dict[Path, Leaf],
    default: str,
    people: dict[Path, list[str]] | None = None,
) -> dict[Path, list[str]]:
    """The generator's comments: the default language's text above a translation, and a mark where a
    text needs review"""
    comments: dict[Path, list[str]] = {}
    for path in texts:
        leaf = state.get(path)
        if leaf is None:
            continue
        lines: list[str] = []
        other = language_of(path) != default
        if other and leaf.source:
            first, *rest = leaf.source.splitlines() or [""]
            lines.append(f"{default}: {first}")
            lines.extend(f"    {line}" for line in rest)
        if leaf.review:
            lines.append(
                "NEEDS REVIEW: the "
                + (
                    f"{default} text has changed since this was translated"
                    if other
                    else "model has changed since this was edited"
                )
            )
        if lines:
            comments[path] = lines
    # (a person's comments come after the generator's)
    for path, lines in (people or {}).items():
        comments[path] = [*comments.get(path, []), *lines]
    return comments


def render_models_file(
    texts: dict[Path, str],
    obsolete: dict[Path, str],
    state: dict[Path, Leaf],
    default: str,
    people: dict[Path, list[str]] | None = None,
) -> str:
    people = dict(people or {})
    tree = nest(texts)
    if obsolete:
        tree[OBSOLETE] = nest(dict(sorted(obsolete.items())))
    comments = comments_for(texts, state, default, people)
    top = comments.pop((), [])
    return jsonc.render(tree, comments, header=[*HEADER, *top])


def write_if_changed(path: FilePath, text: str) -> bool:
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def write_models_file(
    directory: FilePath,
    texts: dict[Path, str],
    obsolete: dict[Path, str],
    state: dict[Path, Leaf],
    default: str,
    people: dict[Path, list[str]] | None = None,
) -> bool:
    """Write `models.jsonc` and `.state.json` (only what has changed); whether anything did"""
    changed = write_if_changed(
        directory / MODELS_FILE,
        render_models_file(texts, obsolete, state, default, people),
    )
    # (the state of the texts that are in the file, and of the obsolete)
    kept = {p: s for p, s in state.items() if p in texts or p in obsolete}
    return write_if_changed(directory / STATE_FILE, state_text(kept)) or changed


def read_ui_file(path: FilePath) -> dict[str, dict[str, str]]:
    """{key: {language: text}} of a `ui.jsonc` (none if there is no file)"""
    if not path.is_file():
        return {}
    data = read_jsonc(path)
    if not isinstance(data, dict):
        raise TranslationFileError(f"{path}: the top must be an object")
    result: dict[str, dict[str, str]] = {}
    for key, languages in data.items():
        if not isinstance(languages, dict) or not all(
            isinstance(text, str) for text in languages.values()
        ):
            raise TranslationFileError(
                f"{path}: {key!r} must be an object of language: text"
            )
        result[key] = dict(languages)
    return result
