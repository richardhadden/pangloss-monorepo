"""What `pangloss_rdf` writes for a Zotero item, beyond its fields: the usual terms for a bibliographic record. Found by name; only imported by that package."""

from collections.abc import Iterator
from typing import Any

from pangloss_rdf import IRI, Quad, register_rdf_converter, to_literal
from pangloss_rdf.context import Context
from pangloss_rdf.vocabulary import OWL_SAME_AS, dcterms, schema

from pangloss_zotero.models import ZoteroBacked


def convert_item(value: Any, uri: IRI, context: Context) -> Iterator[Quad]:
    for field, term in (
        ("title", dcterms("title")),
        ("date", dcterms("date")),
        ("language", dcterms("language")),
        ("abstract", dcterms("abstract")),
        ("citation", dcterms("bibliographicCitation")),
        # (not dcterms:creator, which the export uses of who made the record)
        ("creators", schema("author")),
    ):
        found = getattr(value, field, None)
        if found is not None:
            yield context.quad(uri, term, to_literal(found))
    url = getattr(value, "zotero_url", None)
    if url and url.startswith(("http://", "https://")):
        yield context.quad(uri, OWL_SAME_AS, IRI(url))


register_rdf_converter(ZoteroBacked, convert_item)
