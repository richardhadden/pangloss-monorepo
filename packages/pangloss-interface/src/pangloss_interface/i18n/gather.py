"""`gather`: the texts of every layer, as the one JSON object the interface loads.

    {"default": "en", "languages": ["en", "de"],
     "ui":     {"en": {"title": ...}, "de": {...}},
     "models": {"en": {"Person": {"name", "plural", "description", "help",
                                  "fields": {"birth_place": {"name", "plural", "help"}},
                                  "incoming": {...}}}, "de": {...}},
     "enums":  {"en": {"Colour": {"name", "plural", "description", "help",
                                  "members": {"RED": {"name"}}}}, "de": {...}}}

Every language is complete: where a text is missing it is the default language's (see `resolve.py`).
A model has all of its fields, the inherited ones too, with the text of the model that declares them
(or of the model that narrows one, if it gives its own). A model's `kind` is its kind in the code
("Entity", ...); the words for it are the `ui` slots `kind_entity` and `kind_entity_plural`."""

from typing import Any

from pangloss_interface.i18n.resolve import Layers


def item_texts(layers: Layers, language: str, item: tuple[str, ...]) -> dict[str, str]:
    return {
        "name": layers.final(language, (*item, "name")),
        "plural": layers.plural(language, item),
        "help": layers.final(language, (*item, "help")),
    }


def chain_texts(
    layers: Layers, language: str, chain: list[str], field_name: str
) -> dict[str, str]:
    """The texts of a field: those of the first model of the chain that has one in the language (a model
    that narrows a field can give its own), then the same in the default language"""

    def first(language: str, key: str) -> str:
        for model in chain:
            text = layers.pick(language, ("models", model, "fields", field_name, key))
            if text:
                return text
        return ""

    def text(key: str) -> str:
        return first(language, key) or (
            first(layers.default, key) if language != layers.default else ""
        )

    def plural() -> str:
        for lang in dict.fromkeys([language, layers.default]):
            own = first(lang, "plural") or first(lang, "name")
            if own:
                return own
        return ""

    return {"name": text("name"), "plural": plural(), "help": text("help")}


def gather(layers: Layers) -> dict[str, Any]:
    extracted = layers.extracted
    result: dict[str, Any] = {
        "default": layers.default,
        "languages": list(layers.languages),
        "ui": {},
        "models": {},
        "enums": {},
    }
    for language in layers.languages:
        result["ui"][language] = {
            key: layers.ui_final(language, key) for key in layers.ui_keys()
        }

        models: dict[str, Any] = {}
        for section, name in extracted.entities():
            if section != "models":
                continue
            entity = (section, name)
            entry: dict[str, Any] = dict(item_texts(layers, language, entity))
            entry["description"] = layers.final(language, (*entity, "description"))
            fields = {}
            for field_name, chain in extracted.field_chain.get(name, {}).items():
                fields[field_name] = chain_texts(layers, language, chain, field_name)
            entry["kind"] = extracted.kinds.get(name, "")
            entry["fields"] = fields
            incoming = sorted(
                {p[3] for p in extracted.texts if p[:3] == (*entity, "incoming")}
            )
            entry["incoming"] = {
                n: item_texts(layers, language, (*entity, "incoming", n))
                for n in incoming
            }
            models[name] = entry
        result["models"][language] = models

        enums: dict[str, Any] = {}
        for section, name in extracted.entities():
            if section != "enums":
                continue
            entity = (section, name)
            entry: dict[str, Any] = dict(item_texts(layers, language, entity))
            entry["description"] = layers.final(language, (*entity, "description"))
            members = sorted(
                {p[3] for p in extracted.texts if p[:3] == (*entity, "members")}
            )
            entry["members"] = {
                m: {"name": layers.final(language, (*entity, "members", m, "name"))}
                for m in members
            }
            enums[name] = entry
        result["enums"][language] = enums
    return result
