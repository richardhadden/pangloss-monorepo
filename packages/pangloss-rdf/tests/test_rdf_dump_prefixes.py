"""Documents that follow each other in one file say each prefix once"""

from pangloss_rdf.serialise import without_repeated_prefixes
from rdflib import Graph

FIRST = """@prefix a: <http://a/> .
@prefix ns1: <http://one/> .

a:x ns1:p "1" .

"""

SECOND = """@prefix a: <http://a/> .
@prefix ns1: <http://two/> .

a:y ns1:p \"\"\"
@prefix a: <http://a/> .
\"\"\" .

"""


def test_a_prefix_is_kept_only_if_it_is_new_or_means_something_else():
    declared = {}
    first = without_repeated_prefixes(FIRST, declared)
    second = without_repeated_prefixes(SECOND, declared)
    assert first.count("@prefix") == 2
    assert "@prefix a:" not in second.split("a:y")[0]
    assert "@prefix ns1: <http://two/> ." in second
    assert declared == {"a": "http://a/", "ns1": "http://two/"}
    # (the literal that looks like a prefix is left as it was)
    assert second.count("@prefix a:") == 1

    parsed = Graph().parse(data=first + second, format="turtle")
    predicates = {str(p) for p in parsed.predicates()}
    assert predicates == {"http://one/p", "http://two/p"}
