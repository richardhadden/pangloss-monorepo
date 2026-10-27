"""Bringing a translation file up to date with the models without losing what people wrote.

For each text there are three values:

    base      what the generator wrote the last time (kept in `.state.json`)
    current   what is in the file now (a person may have changed it)
    new       what the models give now

and the rule is: a text that is **not edited** (`current == base`) follows the models; one that **is**
edited is kept, and is marked *needs review* if the models have changed under it. A text in another
language than the default is made from the default language's, so what it is compared with is that
text (`source`): if it has changed since the translation was made, the translation is kept and marked.
Nothing is overwritten that a person has written.

Things that have gone (a model or field with another name, or deleted) are moved to `_obsolete`, not
deleted, with the key they had; and if the migrations say that something was renamed, what was written
for the old name is moved to the new. All of this is on flat maps of paths to text (see `paths.py`),
so that it needs no files and no models.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from pangloss_interface.i18n.paths import (
    Path,
    language_of,
    with_language,
    without_language,
)


@dataclass(frozen=True)
class Leaf:
    """What is remembered of a text"""

    base: str  # what the generator wrote
    source: str  # the default language's text this was made from (the same as `base` in that language)
    seen: str  # the text as it was at the end of the last run
    review: bool = False


@dataclass(frozen=True)
class ItemRename:
    """Something with another name now (paths without a language: a model, a field, an enum, a member,
    or an incoming relation; a `"*"` stands for any name, the same one in `old` and `new`)"""

    old: Path
    new: Path


def renamed(path: Path, renames: list[ItemRename]) -> Path:
    """The path after the renames, in the order they happened. A `"*"` in a rename matches any name at
    that place and keeps it (the reverse name of a relation is on whichever model it points to)"""
    plain = without_language(path)
    for rename in renames:
        old = rename.old
        if len(plain) < len(old) or any(
            o not in ("*", p) for o, p in zip(old, plain, strict=False)
        ):
            continue
        carried = iter(p for o, p in zip(old, plain, strict=False) if o == "*")
        new = tuple(next(carried) if n == "*" else n for n in rename.new)
        plain = (*new, *plain[len(old) :])
    return with_language(plain, path[2])


def merge_default(
    new: str, current: str | None, state: Leaf | None
) -> tuple[str, Leaf, str]:
    """A text in the default language: (the text, what to remember, what happened to it)"""
    if current is None:
        return new, Leaf(new, new, new), "added"
    edited = current != (state.base if state else new)
    if not edited:
        how = "same" if current == new else "followed"
        return new, Leaf(new, new, new), how
    changed_under = state is not None and new != state.base
    review = changed_under or bool(state and state.review and current == state.seen)
    return current, Leaf(new, new, current, review), "kept"


def merge_other(
    source: str, current: str | None, state: Leaf | None
) -> tuple[str, Leaf, str]:
    """A text in another language: always what is in the file (the generator has nothing to say in it),
    marked for review if the text it was made from has changed"""
    if current is None:
        return "", Leaf("", source, ""), "added"
    if current == "":
        return "", Leaf("", source, ""), "same"
    source_changed = state is not None and state.source != source
    review = source_changed or bool(state and state.review and current == state.seen)
    return current, Leaf("", source, current, review), "kept"


@dataclass
class Report:
    added: list[Path] = field(default_factory=list)
    followed: list[Path] = field(
        default_factory=list
    )  # not edited: the models' new text
    kept: list[Path] = field(default_factory=list)  # edited, and kept
    review: list[Path] = field(default_factory=list)
    moved: list[Path] = field(default_factory=list)  # carried to a new name by a rename
    obsolete: list[Path] = field(default_factory=list)  # put in `_obsolete` in this run
    pruned: list[Path] = field(default_factory=list)


@dataclass
class Outcome:
    texts: dict[Path, str]
    state: dict[Path, Leaf]
    obsolete: dict[Path, str]
    report: Report


def is_edited(
    path: Path,
    text: str,
    state: Leaf | None,
    generated: Mapping[Path, str],
    default: str,
) -> bool:
    if language_of(path) != default:
        return text != ""
    return text != (state.base if state else generated.get(without_language(path)))


def reconcile(
    generated: Mapping[Path, str],
    languages: list[str],
    default: str,
    current: Mapping[Path, str],
    obsolete: Mapping[Path, str] | None = None,
    state: Mapping[Path, Leaf] | None = None,
    renames: list[ItemRename] | None = None,
    prune: bool = False,
) -> Outcome:
    """The texts of a file after `generate`.

    `generated` is what the models give (paths without a language, default language text);
    `current`, `obsolete` and `state` are what the file, its `_obsolete` section and its state file
    have. The texts that result have every language (an empty text in those that are not the default)."""
    obsolete, state, renames = obsolete or {}, state or {}, renames or []
    languages = [default, *(lang for lang in languages if lang != default)]
    live = {with_language(p, lang) for p in generated for lang in languages}
    report = Report()

    pool: dict[Path, str] = {**obsolete, **current}
    remembered = dict(state)

    # what was written for a name that something else replaced, by a rename
    for path in [p for p in pool if p not in live]:
        target = renamed(path, renames)
        if target == path or target not in live:
            continue
        there = pool.get(target)
        if there not in (None, "") and is_edited(
            target, there or "", remembered.get(target), generated, default
        ):
            continue  # (the new name has text of its own: the old stays where it is)
        pool[target] = pool.pop(path)
        if path in remembered:
            remembered[target] = remembered.pop(path)
        else:
            remembered.pop(target, None)
        report.moved.append(target)

    texts: dict[Path, str] = {}
    new_state: dict[Path, Leaf] = {}
    for plain, new in generated.items():
        default_path = with_language(plain, default)
        shown, leaf, how = merge_default(
            new, pool.get(default_path), remembered.get(default_path)
        )
        for language in languages:
            path = with_language(plain, language)
            if language != default:
                shown_here, leaf_here, how = merge_other(
                    shown, pool.get(path), remembered.get(path)
                )
            else:
                shown_here, leaf_here = shown, leaf
            texts[path] = shown_here
            new_state[path] = leaf_here
            if how == "added" and path not in report.moved:
                report.added.append(path)
            elif how == "followed":
                report.followed.append(path)
            elif how == "kept":
                report.kept.append(path)
            if leaf_here.review:
                report.review.append(path)

    kept_obsolete: dict[Path, str] = {}
    for path, text in pool.items():
        if path in live:
            continue
        previous = path in obsolete and path not in current
        worth = text != "" and (
            previous
            or language_of(path) != default
            or (path in remembered and text != remembered[path].base)
        )
        if not worth:
            remembered.pop(path, None)
            continue
        if prune:
            report.pruned.append(path)
            remembered.pop(path, None)
            continue
        kept_obsolete[path] = text
        if path in remembered:
            new_state[path] = remembered[path]
        if not previous:
            report.obsolete.append(path)

    return Outcome(texts, new_state, kept_obsolete, report)
