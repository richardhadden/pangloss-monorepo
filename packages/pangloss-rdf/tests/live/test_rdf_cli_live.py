"""`pangloss rdf check`, `ontology`, `dump` and `generate-ontology`, run as the command line runs them (on the backend
under test, for the dump)"""

import gzip
import json
from typing import no_type_check

from pangloss_models import Entity, ModelRegistry, initialise
from pangloss_rdf import RDFMeta
from pangloss_testing.live import run_command, run_connected
from rdflib import Dataset, Graph

from pangloss_rdf.cli import cli
from test_rdf_live import declare, fill


def rdf(backend, *arguments):
    return run_command(cli, backend, *arguments)


@no_type_check
def test_check_says_the_names_are_good_or_what_is_wrong_with_them(clear_database):
    declare()
    good = rdf(None, "check")
    assert good.exit_code == 0, good.output
    assert good.output.strip().endswith("The RDF names are good.")
    # (and what to settle before publishing: the tests' base URL has no path of its own)
    assert "warning: ENTITY_BASE_URL has no path of its own" in good.output

    ModelRegistry._reset()

    class Person(Entity):
        _rdf_meta = RDFMeta(class_name="Agent")

    class Group(Entity):
        _rdf_meta = RDFMeta(class_name="Agent")

    initialise()
    bad = rdf(None, "check")
    assert bad.exit_code == 1
    assert "Person and Group are both the class" in bad.output
    assert "The RDF names are good." not in bad.output


@no_type_check
def test_the_ontology_its_shapes_and_its_context_are_written(clear_database, tmp_path):
    declare()
    turtle = rdf(None, "ontology")
    assert turtle.exit_code == 0, turtle.output
    ontology = Graph().parse(data=turtle.output, format="turtle")
    assert len(ontology) > 0

    out = tmp_path / "shapes.ttl"
    shapes = rdf(None, "ontology", "--shapes", "-o", str(out))
    assert shapes.exit_code == 0 and shapes.output == ""
    shape_graph = Graph().parse(out, format="turtle")
    assert set(shape_graph) != set(ontology)
    assert any("shacl" in str(p) for _, p, _ in shape_graph)

    context = rdf(None, "ontology", "--context")
    assert "@context" in json.loads(context.output)

    as_jsonld = rdf(None, "ontology", "--format", "jsonld")
    assert set(Graph().parse(data=as_jsonld.output, format="json-ld")) == set(ontology)


@no_type_check
def test_the_dump_writes_every_item_to_a_file(
    clear_database, command_backend, tmp_path
):
    m = declare()
    run_connected(command_backend, lambda: fill(m))

    out = tmp_path / "all.nq.gz"
    dumped = rdf(command_backend, "dump", "-o", str(out))
    assert dumped.exit_code == 0, dumped.output
    items, quads = (
        dumped.output.split(" items, ")[0],
        dumped.output.split(" items, ")[1].split(" quads")[0],
    )
    assert dumped.output.strip().endswith(f"in {out}")
    dataset = Dataset()
    dataset.parse(data=gzip.decompress(out.read_bytes()).decode(), format="nquads")
    # (the count is of the quads in the file, each once)
    lines = gzip.decompress(out.read_bytes()).decode().splitlines()
    assert int(items) == 2 and int(quads) == len(lines) == len(set(lines)) > 0
    assert len(list(dataset.quads((None, None, None, None)))) == len(lines)

    # (only one class, as Turtle)
    only = tmp_path / "people.ttl"
    some = rdf(
        command_backend, "dump", "-o", str(only), "--format", "ttl", "--types", "Person"
    )
    assert some.exit_code == 0, some.output
    assert some.output.startswith("1 items, ")
    assert len(Graph().parse(only, format="turtle")) > 0


def test_a_module_of_mixins_is_generated_from_an_ontology(tmp_path):
    source = tmp_path / "o.ttl"
    source.write_text(
        """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix o: <http://o/> .
        o:A a rdfs:Class .
        o:B a rdfs:Class ; rdfs:subClassOf o:A .
        """
    )
    out = tmp_path / "o.py"
    made = run_command(
        cli,
        None,
        "generate-ontology",
        str(source),
        "--prefix",
        "o",
        "--out",
        str(out),
        "--title",
        "O",
    )
    assert made.exit_code == 0, made.output
    assert made.output.strip() == f"Written {out}"
    namespace: dict = {}
    exec(out.read_text(), namespace)
    assert namespace["B"].__bases__ == (namespace["A"],)
