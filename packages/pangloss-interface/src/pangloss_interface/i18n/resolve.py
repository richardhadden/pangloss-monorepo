"""What text there is for a language, from the layers, highest first:

    1. the project's override file     (`<project>/translations/models.jsonc`)
    2. the file of the app             (`<app>/translations/models.jsonc`)
    3. what the models give            (the default language only)

An empty text is not there, and the next layer is looked at. A language other than the default
falls back to the default language's text. A plural that is not there is the singular."""

from dataclasses import dataclass, field
from pathlib import Path as FilePath

from pangloss_interface.i18n import files
from pangloss_interface.i18n.extract import Extracted
from pangloss_interface.i18n.paths import Path, with_language


@dataclass
class Layers:
    extracted: Extracted
    default: str
    languages: list[str]
    app: dict[Path, str] = field(default_factory=dict)
    override: dict[Path, str] = field(default_factory=dict)
    # {key: {language: text}} of the apps, in order, then the project's
    ui: list[dict[str, dict[str, str]]] = field(default_factory=list)
    app_files: dict[str, files.ModelsFile] = field(default_factory=dict)

    def pick(self, language: str, plain: Path) -> str:
        """The text in exactly this language (empty if there is none)"""
        path = with_language(plain, language)
        for layer in (self.override, self.app):
            if layer.get(path):
                return layer[path]
        return self.extracted.texts.get(plain, "") if language == self.default else ""

    def final(self, language: str, plain: Path) -> str:
        return self.pick(language, plain) or (
            self.pick(self.default, plain) if language != self.default else ""
        )

    def plural(self, language: str, item: Path) -> str:
        own = self.pick(language, (*item, "plural"))
        if own:
            return own
        name = self.pick(language, (*item, "name"))
        if name:
            return name
        return self.pick(self.default, (*item, "plural")) or self.pick(
            self.default, (*item, "name")
        )

    def ui_text(self, language: str, key: str) -> str:
        for layer in reversed(self.ui):
            if layer.get(key, {}).get(language):
                return layer[key][language]
        return ""

    def ui_final(self, language: str, key: str) -> str:
        return self.ui_text(language, key) or self.ui_text(self.default, key)

    def ui_keys(self) -> list[str]:
        return sorted({key for layer in self.ui for key in layer})


def load_layers(
    root: FilePath,
    extracted: Extracted,
    apps: list[str],
    default: str,
    languages: list[str],
) -> Layers:
    layers = Layers(extracted, default, languages)
    # (the labels of the apps' navigation links are the default-language texts of their slots: the lowest layer)
    from pangloss_interface.config import load_configs, nav_defaults

    layers.ui.append(
        {slot: {default: text} for slot, text in nav_defaults(load_configs(apps)).items()}
    )
    # (the interface's own slots are there whether or not it is one of the INSTALLED_APPS)
    for app in dict.fromkeys(["pangloss_interface", *apps]):
        directory = files.app_directory(app)
        if directory is None:
            continue
        folder = directory / files.FOLDER
        if extracted.entities(app):
            loaded = files.read_models_file(folder)
            layers.app_files[app] = loaded
            layers.app.update(loaded.texts)
        layers.ui.append(files.read_ui_file(folder / files.UI_FILE))
    project = root / files.FOLDER
    layers.override = files.read_models_file(project).texts
    layers.ui.append(files.read_ui_file(project / files.UI_FILE))
    return layers
