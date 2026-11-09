"""A description of the dataset (VoID): what it is, under what licence, and where the rest is"""

from collections.abc import Iterator

from pangloss_core.settings import get_settings

from pangloss_rdf.literals import to_literal
from pangloss_rdf.ontology import ontology_address
from pangloss_rdf.terms import IRI, Quad
from pangloss_rdf.uris import base_url
from pangloss_rdf.vocabulary import RDF_TYPE, dcterms, void


def dataset_uri() -> IRI:
    return IRI(f"{base_url()}/dataset")


def dataset_quads() -> Iterator[Quad]:
    settings = get_settings()
    uri = dataset_uri()
    yield Quad(uri, RDF_TYPE, void("Dataset"))
    yield Quad(uri, dcterms("title"), to_literal(settings.PROJECT_NAME))
    yield Quad(uri, void("uriSpace"), to_literal(f"{base_url()}/"))
    yield Quad(uri, void("vocabulary"), ontology_address())
    if licence := getattr(settings, "RDF_LICENSE", None):
        yield Quad(uri, dcterms("license"), IRI(str(licence)))
    if dump := getattr(settings, "RDF_DUMP_URL", None):
        yield Quad(uri, void("dataDump"), IRI(str(dump)))
