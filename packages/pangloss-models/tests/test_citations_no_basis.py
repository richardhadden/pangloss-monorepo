"""A `Cites` subclass with `bases = False` takes no cited basis (`PGCitedBasis`), even where an app has asked for
them: its field is the same with them or without (so is a package's migration of it)"""

from typing import no_type_check

from pangloss_models import Cites, Document, initialise
from pangloss_models import citations
from pangloss_models.field_definitions import RelationToCitation


class CitesItself[Target](Cites[Target]):
    bases = False


@no_type_check
def test_a_citation_that_takes_no_basis_has_one_option_where_another_takes_two(
    monkeypatch,
):
    monkeypatch.setattr(citations, "_basis_enabled", True)

    class Note(Document):
        text: str

    class Inference(Document):
        evidence: list[Cites[Note]]
        shared: CitesItself[Note] | None = None

    initialise()
    fields = Inference._meta.fields.relation_fields
    assert {type(o).__name__ for o in fields["evidence"].type_options} == {
        "RelationToCitation",
        "RelationToDocument",
    }
    (only,) = fields["shared"].type_options
    assert isinstance(only, RelationToCitation) and only.protect
    # (it is a citation as any other: it protects what it cites)
    assert citations.takes_bases(CitesItself[Note]) is False
    assert citations.takes_bases(Cites[Note]) is True
