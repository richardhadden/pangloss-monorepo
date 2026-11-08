"""A write the server refuses (`@before_create`, `@before_update`) is raised in the client as the same error, with
the field it is about"""

from types import SimpleNamespace

from pangloss_models import PanglossWriteRefused
from pangloss_sdk import protocol


def answer(body: dict) -> SimpleNamespace:
    return SimpleNamespace(
        status_code=422, is_success=False, json=lambda: body, text=""
    )


def test_a_refusal_at_a_field_has_the_field_in_snake_case():
    error = protocol.error_for(
        answer(
            {
                "error": "PanglossWriteRefused",
                "detail": [
                    {"loc": ["body", "bornIn"], "msg": "Not there", "type": "refused"}
                ],
            }
        )
    )
    assert isinstance(error, PanglossWriteRefused)
    assert str(error) == "Not there" and error.field == "born_in"
    assert error.path == ("born_in",)


def test_a_refusal_in_a_nested_document_has_its_path():
    error = protocol.error_for(
        answer(
            {
                "error": "PanglossWriteRefused",
                "detail": [
                    {
                        "loc": ["body", "clauses", 1, "signedBy"],
                        "msg": "No",
                        "type": "refused",
                    }
                ],
            }
        )
    )
    assert error.field == "signed_by" and error.path == ("clauses", 1, "signed_by")


def test_a_refusal_of_the_whole_write_has_no_field():
    error = protocol.error_for(
        answer({"error": "PanglossWriteRefused", "detail": "No"})
    )
    assert isinstance(error, PanglossWriteRefused)
    assert str(error) == "No" and error.field is None
