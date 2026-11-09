"""`pangloss rdf generate-ontology`: an ontology's RDFS or OWL file as a Python module of mixins.

    class E21_Person(E20_Biological_Object, E39_Actor):
        _rdf_uri = "http://www.cidoc-crm.org/cidoc-crm/E21_Person"

    P14_carried_out_by = OntologyProperty("http://.../P14_carried_out_by", domain=(...), range=(...))

The classes keep the ontology's hierarchy as Python bases, so a mistake in the order of bases is Python's error."""

import itertools
import keyword
import re
from pathlib import Path
from typing import Any

from pangloss_models.exceptions import PanglossMetaError

_FORMATS = {
    ".rdfs": "xml",
    ".rdf": "xml",
    ".owl": "xml",
    ".xml": "xml",
    ".ttl": "turtle",
    ".nt": "nt",
}
COMMENT_LENGTH = 400
_PREFIX = re.compile(r"[^\W\d_][\w-]*")


def _python_name(uri: str) -> str:
    local = re.split(r"[#/]", uri.rstrip("/#"))[-1]
    name = re.sub(r"\W", "_", local)
    if name[:1].isdigit() or keyword.iskeyword(name):
        name = f"_{name}"
    return name


def _comment(graph: Any, subject: Any) -> str:
    from rdflib import RDFS

    comments = list(graph.objects(subject, RDFS.comment))
    chosen = next((c for c in comments if getattr(c, "language", None) == "en"), None)
    if chosen is None and comments:
        chosen = comments[0]
    if chosen is None:
        return ""
    text = " ".join(str(chosen).split())
    if len(text) > COMMENT_LENGTH:
        text = f"{text[:COMMENT_LENGTH].rsplit(' ', 1)[0]}…"
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"').rstrip('"')


def _deprecated(graph: Any, subject: Any) -> bool:
    from rdflib import OWL

    return any(str(v).lower() == "true" for v in graph.objects(subject, OWL.deprecated))


def _ancestors(uri: str, parents: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(parents.get(uri, ()))
    while stack:
        current = stack.pop()
        if current not in seen:
            seen.add(current)
            stack.extend(parents.get(current, ()))
    return seen


def _bases_in_order(
    uri: str, direct: list[str], made: dict[str, type], names: dict[str, str]
) -> tuple[list[str], list[str]]:
    """The bases in an order Python accepts, and any left out because none exists (an ontology may ask what Python cannot)"""
    for count in range(len(direct), 0, -1):
        for chosen in itertools.permutations(direct, count):
            try:
                made[uri] = type(names[uri], tuple(made[b] for b in chosen), {})
            except TypeError:
                continue
            return list(chosen), [b for b in direct if b not in chosen]
    made[uri] = type(names[uri], (), {})
    return [], list(direct)


def _namespace(uris: list[str]) -> str:
    """Where most of the terms are"""
    counts = _count(uri[: max(uri.rfind("#"), uri.rfind("/")) + 1] for uri in uris)
    return max(counts, key=lambda namespace: counts[namespace])


def generate_module(source: Path, prefix: str, title: str | None = None) -> str:
    """`prefix`: what the ontology is called in the output (`crm`). `title`: in the module's docstring"""
    if not _PREFIX.fullmatch(prefix):
        raise PanglossMetaError(
            f"{prefix!r} cannot be a prefix: use letters, digits, '_' and '-', starting with a letter"
        )
    from rdflib import OWL, RDF, RDFS, Graph, URIRef

    graph = Graph()
    graph.parse(source, format=_FORMATS.get(source.suffix.lower(), "xml"))

    classes = sorted(
        {
            str(s)
            for kind in (RDFS.Class, OWL.Class)
            for s in graph.subjects(RDF.type, kind)
            if isinstance(s, URIRef) and not _deprecated(graph, s)
        }
    )
    properties = sorted(
        {
            str(s)
            for kind in (
                RDF.Property,
                OWL.ObjectProperty,
                OWL.DatatypeProperty,
                OWL.AnnotationProperty,
            )
            for s in graph.subjects(RDF.type, kind)
            if isinstance(s, URIRef) and not _deprecated(graph, s)
        }
    )
    names = {uri: _python_name(uri) for uri in [*classes, *properties]}
    clashes = [name for name, n in _count(names.values()).items() if n > 1]
    if clashes:
        raise PanglossMetaError(
            f"These names of {source.name} are the same in Python: {', '.join(sorted(clashes))}"
        )

    known = set(classes)
    parents = {
        uri: sorted(
            str(o)
            for o in graph.objects(URIRef(uri), RDFS.subClassOf)
            if str(o) in known and str(o) != uri
        )
        for uri in classes
    }
    # (a parent that another parent already has adds nothing, and is what makes an order of bases impossible)
    direct = {
        uri: [
            p
            for p in found
            if not any(p in _ancestors(o, parents) for o in found if o != p)
        ]
        for uri, found in parents.items()
    }

    lines = [
        f'"""{title or prefix}: generated from {source.name} by `pangloss rdf generate-ontology`. Do not edit."""',
        "",
        "from pangloss_rdf.fields import OntologyProperty, register_ontology_prefix",
        "",
        f'register_ontology_prefix("{prefix}", "{_namespace([*classes, *properties])}")',
        "",
    ]
    made: dict[str, type] = {}
    pending = list(classes)
    while pending:
        ready = [u for u in pending if all(p in made for p in direct[u])]
        if not ready:
            raise PanglossMetaError(
                f"{source.name}: its classes are their own ancestors: {', '.join(names[u] for u in pending)}"
            )
        for uri in ready:
            bases, dropped = _bases_in_order(uri, direct[uri], made, names)
            pending.remove(uri)
            header = f"({', '.join(names[b] for b in bases)})" if bases else ""
            lines += ["", "", f"class {names[uri]}{header}:"]
            if text := _comment(graph, URIRef(uri)):
                lines.append(f'    """{text}"""')
                lines.append("")
            lines.append(f'    _rdf_uri = "{uri}"')
            for parent in dropped:
                lines.append(
                    f"    # (not a base, as Python has no order for it: {names[parent]})"
                )
    lines += ["", ""]
    for uri in properties:
        domain = sorted(str(o) for o in graph.objects(URIRef(uri), RDFS.domain))
        range_ = sorted(str(o) for o in graph.objects(URIRef(uri), RDFS.range))
        lines.append(
            f'{names[uri]} = OntologyProperty("{uri}", domain={_tuple(domain)}, range={_tuple(range_)})'
        )
    return "\n".join(lines) + "\n"


def _tuple(values: list[str]) -> str:
    return "(" + "".join(f'"{v}", ' for v in values).rstrip(" ") + ")"


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
