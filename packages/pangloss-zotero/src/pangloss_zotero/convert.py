"""A Zotero item, as the API gives it, as the fields of a `ZoteroBacked` model. No database."""

import datetime
import html
import json
from html.parser import HTMLParser
from typing import Any

WEB = "https://www.zotero.org"


def item_url(library: str, key: str) -> str:
    return f"{WEB}/{library}/items/{key}"


def library_url(library: str) -> str:
    return f"{WEB}/{library}"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("br", "div", "p"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("div", "p"):
            self.parts.append("\n")


def plain(markup: str | None) -> str | None:
    """The text of some HTML, as Zotero's citations and bibliographies are"""
    if not markup:
        return None
    parser = _Text()
    parser.feed(markup)
    parser.close()
    lines = [
        " ".join(line.split())
        for line in html.unescape("".join(parser.parts)).splitlines()
    ]
    return "\n".join(line for line in lines if line) or None


def creator_name(creator: dict[str, Any]) -> str | None:
    if creator.get("name"):
        return str(creator["name"]).strip()
    last, first = (
        creator.get("lastName", "").strip(),
        creator.get("firstName", "").strip(),
    )
    if last and first:
        return f"{last}, {first}"
    return last or first or None


def creators_text(creators: list[dict[str, Any]]) -> str | None:
    names = [n for c in creators if (n := creator_name(c))]
    return "; ".join(names) or None


def text_or_none(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def trashed(item: dict[str, Any]) -> bool:
    return bool(item.get("data", {}).get("deleted"))


def convert(item: dict[str, Any], library: str) -> dict[str, Any]:
    """The fields of an item. `label` is the citation, or the title, or the key"""
    data = item.get("data", {})
    key = item["key"]
    citation = plain(item.get("citation"))
    title = text_or_none(data.get("title"))
    csl = item.get("csljson")
    fields: dict[str, Any] = {
        "label": citation or title or key,
        "zotero_url": item_url(library, key),
        "zotero_library": library,
        "zotero_key": key,
        "zotero_version": int(item.get("version", data.get("version", 0))),
        "item_type": data.get("itemType"),
        "title": title,
        "short_title": text_or_none(data.get("shortTitle")),
        "creators": creators_text(data.get("creators", [])),
        "date": text_or_none(data.get("date")),
        "language": text_or_none(data.get("language")),
        "abstract": text_or_none(data.get("abstractNote")),
        "zotero_data": json.dumps(data, sort_keys=True, ensure_ascii=False),
        "citation": citation,
        "bibliography": plain(item.get("bib")),
        "csl_json": json.dumps(csl, sort_keys=True, ensure_ascii=False)
        if csl is not None
        else None,
        "removed_from_zotero": True if trashed(item) else None,
    }
    return fields


def stamp(fields: dict[str, Any], when: datetime.datetime) -> dict[str, Any]:
    return {**fields, "synced_when": when}
