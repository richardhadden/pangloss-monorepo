"""The terms that every export uses, whatever the project's models are: `pgo:` and the standard vocabularies"""

import re

from pangloss_core.settings import get_settings
from pangloss_models.exceptions import PanglossMetaError

from pangloss_rdf.fields import ontology_prefixes
from pangloss_rdf.terms import IRI, RDF_NS
from pangloss_rdf.uris import ontology_url

_PREFIX = re.compile(r"[^\W\d_][\w-]*")
# (what the standard vocabularies are called in the output, which a project's prefix cannot be)
STANDARD_PREFIXES = frozenset(
    {"rdf", "rdfs", "owl", "xsd", "dcterms", "skos", "schema", "sh", "void"}
)
DEFAULT_CORE_PREFIX = "core"

RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
OWL_NS = "http://www.w3.org/2002/07/owl#"
DCTERMS_NS = "http://purl.org/dc/terms/"
SKOS_NS = "http://www.w3.org/2004/02/skos/core#"
SCHEMA_NS = "https://schema.org/"
SH_NS = "http://www.w3.org/ns/shacl#"
VOID_NS = "http://rdfs.org/ns/void#"

RDF_TYPE = IRI(f"{RDF_NS}type")
RDF_SUBJECT = IRI(f"{RDF_NS}subject")
RDF_PREDICATE = IRI(f"{RDF_NS}predicate")
RDF_OBJECT = IRI(f"{RDF_NS}object")
RDF_VALUE = IRI(f"{RDF_NS}value")
RDF_FIRST = IRI(f"{RDF_NS}first")
RDF_REST = IRI(f"{RDF_NS}rest")
RDF_NIL = IRI(f"{RDF_NS}nil")
RDF_STATEMENT = IRI(f"{RDF_NS}Statement")

RDFS_LABEL = IRI(f"{RDFS_NS}label")
RDFS_COMMENT = IRI(f"{RDFS_NS}comment")
RDFS_SUBCLASS = IRI(f"{RDFS_NS}subClassOf")
RDFS_SUBPROPERTY = IRI(f"{RDFS_NS}subPropertyOf")

OWL_SAME_AS = IRI(f"{OWL_NS}sameAs")


def pgo_namespace() -> str:
    """The structural terms (`Edge`, `inSpace`...): the project's own, next to its ontology, unless `RDF_CORE_URL` says
    otherwise (projects that want to be queried alike can give the same address)"""
    url = getattr(get_settings(), "RDF_CORE_URL", None)
    if url is None:
        return f"{ontology_url().rstrip('/#')}/core#"
    url = str(url)
    return url if url.endswith(("/", "#")) else f"{url}#"


def ontology_prefix() -> str:
    """`RDF_PREFIX`, or made from the project's name"""
    chosen = getattr(get_settings(), "RDF_PREFIX", None)
    if chosen is not None:
        return str(chosen)
    name = str(getattr(get_settings(), "PROJECT_NAME", "") or "")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"p_{slug}".rstrip("_")
    return f"{slug}_" if slug in STANDARD_PREFIXES or slug == core_prefix() else slug


def core_prefix() -> str:
    return str(getattr(get_settings(), "RDF_CORE_PREFIX", None) or DEFAULT_CORE_PREFIX)


def check_prefixes() -> None:
    """Raise if a prefix could not be written, or is one the output uses for something else"""
    chosen, core = ontology_prefix(), core_prefix()
    problems = [
        f"{prefix!r} cannot be a prefix: use letters, digits, '_' and '-', starting with a letter"
        for prefix in (chosen, core)
        if not _PREFIX.fullmatch(prefix)
    ]
    problems += [
        f"{prefix!r} is the prefix of a standard vocabulary: choose another"
        for prefix in (chosen, core)
        if prefix in STANDARD_PREFIXES
    ]
    problems += [
        f"{prefix!r} is the prefix of an ontology that is mixed in: choose another"
        for prefix in (chosen, core)
        if prefix in ontology_prefixes()
    ]
    if chosen == core:
        problems.append(f"RDF_PREFIX and RDF_CORE_PREFIX are both {chosen!r}")
    if problems:
        raise PanglossMetaError("RDF prefixes: " + "; ".join(problems))


def pgo(name: str) -> IRI:
    return IRI(f"{pgo_namespace()}{name}")


def dcterms(name: str) -> IRI:
    return IRI(f"{DCTERMS_NS}{name}")


def owl(name: str) -> IRI:
    return IRI(f"{OWL_NS}{name}")


def rdfs(name: str) -> IRI:
    return IRI(f"{RDFS_NS}{name}")


def skos(name: str) -> IRI:
    return IRI(f"{SKOS_NS}{name}")


def schema(name: str) -> IRI:
    return IRI(f"{SCHEMA_NS}{name}")


def sh(name: str) -> IRI:
    return IRI(f"{SH_NS}{name}")


def void(name: str) -> IRI:
    return IRI(f"{VOID_NS}{name}")
