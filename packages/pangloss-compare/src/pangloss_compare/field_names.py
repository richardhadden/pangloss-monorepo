"""`FieldName`: the name of a field of a statement as a value (a judgement's `fields`, `models.py`). Its own module,
not `models.py`, which the tests load again for a fresh registry: the codec registered here is for this one class."""

from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic.alias_generators import to_camel
from pydantic_core import core_schema

FIELD_NAME = "field-name"


class FieldName(str):
    """The name of a field of a statement, as a judgement's `fields` holds it: Python's name in Python and in the
    store, camelCase in JSON (`to_camel`, as a payload's keys are), wherever a model holding it is given as JSON (the
    API's answers, a version in pangloss-history). What JSON gives back is taken as it comes (camelCase, or Python's):
    a judgement's names are resolved against the two statements' classes when it is made (`models.resolved`), for which
    `to_camel` of each field's name is the exact way back. A literal of the models, stored as text (a codec of the
    format `field-name`, registered when this module is imported)"""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda value: to_camel(str(value)), when_used="json"
            ),
        )


def _register_codec() -> None:
    """`FieldName` a literal type of the models, stored as text (once)"""
    from pangloss_models import literals

    if not any(codec.format == FIELD_NAME for codec in literals.codecs()):
        literals.register_codec(
            literals.LiteralCodec((FieldName,), "str", FIELD_NAME, "text", str)
        )


_register_codec()
