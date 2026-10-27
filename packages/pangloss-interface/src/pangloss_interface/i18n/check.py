"""`check`: what is missing, what needs a person to look at it, and what points at nothing."""

from dataclasses import dataclass

from pangloss_interface.i18n.paths import as_text, language_of, without_language
from pangloss_interface.i18n.resolve import Layers

# A plural is optional (empty is the singular); the other texts are wanted when the default language has one
WANTED = ("name", "description", "help")


@dataclass(frozen=True)
class Problem:
    kind: str  # "missing", "review", "unknown"
    language: str
    where: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.kind:8} {self.language:6} {self.where}" + (
            f"  {self.detail}" if self.detail else ""
        )


def check(layers: Layers, only_language: str | None = None) -> list[Problem]:
    problems: list[Problem] = []
    others = [
        lang
        for lang in layers.languages
        if lang != layers.default and only_language in (None, lang)
    ]

    for plain in layers.extracted.texts:
        if plain[-1] not in WANTED or not layers.pick(layers.default, plain):
            continue
        for language in others:
            if not layers.pick(language, plain):
                problems.append(Problem("missing", language, as_text(plain)))

    for key in layers.ui_keys():
        if not layers.ui_text(layers.default, key):
            problems.append(Problem("missing", layers.default, f"ui/{key}"))
        for language in others:
            if not layers.ui_text(language, key):
                problems.append(Problem("missing", language, f"ui/{key}"))

    live = set(layers.extracted.texts)
    for app, loaded in layers.app_files.items():
        for path, leaf in loaded.state.items():
            if (
                leaf.review
                and path in loaded.texts
                and without_language(path) in live
                and only_language in (None, language_of(path))
            ):
                problems.append(
                    Problem(
                        "review",
                        language_of(path),
                        as_text(without_language(path)),
                        app,
                    )
                )
        for path in loaded.obsolete:
            problems.append(
                Problem(
                    "unknown",
                    language_of(path),
                    as_text(without_language(path)),
                    f"{app}: _obsolete",
                )
            )
    for source, texts in (("the project's overrides", layers.override),):
        for path in texts:
            if (
                without_language(path) not in live
                or language_of(path) not in layers.languages
            ):
                problems.append(
                    Problem(
                        "unknown",
                        language_of(path),
                        as_text(without_language(path)),
                        source,
                    )
                )
    return problems


def failing(problems: list[Problem], strict: bool) -> bool:
    return any(
        p.kind == "missing" or (strict and p.kind in ("review", "unknown"))
        for p in problems
    )
