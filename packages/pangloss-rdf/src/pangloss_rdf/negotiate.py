"""What a client asks for in `Accept`"""

from pangloss_rdf.serialise import FORMATS, Format

_HTML = ("text/html", "application/xhtml+xml")


def accepted(header: str) -> list[tuple[str, float]]:
    """Each media type with its weight, the most wanted first (in the order written, where they are equal)"""
    found: list[tuple[str, float]] = []
    for part in header.split(","):
        media_type, *parameters = [piece.strip() for piece in part.split(";")]
        if not media_type:
            continue
        weight = 1.0
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip() == "q":
                try:
                    weight = float(value)
                except ValueError:
                    weight = 0.0
        found.append((media_type.lower(), weight))
    return sorted(found, key=lambda item: -item[1])


def format_from_accept(header: str) -> Format | None:
    for media_type, weight in accepted(header):
        for candidate in FORMATS.values():
            if weight > 0 and candidate.media_type == media_type:
                return candidate
    return None


def prefers_html(header: str) -> bool:
    """A browser, and not a client of data: one that names HTML, above any RDF. (`*/*` is not asking for a page)"""
    weights = accepted(header)
    html = max((w for t, w in weights if t in _HTML), default=0.0)
    rdf = max(
        (w for t, w in weights if t in {f.media_type for f in FORMATS.values()}),
        default=0.0,
    )
    return html > rdf
