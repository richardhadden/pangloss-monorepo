"""What a 422 says of a request that is not valid: where in what was sent each problem is, and no more.

Pydantic puts in the location (`loc`) of a problem the member of a union that the input was read as
(`["body", "statements", 0, "DeathCreate", "text"]`), and the name of a generic class is every type it takes: one
problem in a `Causes` of a project with 68 kinds of statement was 3 KB, most of it that name, and a form could not
find the field (`DeathCreate` is not a key of what was sent). It also repeats the input, which for a field that is
missing is the whole object it is missing from: a large document with five fields missing came back five times.

So here `loc` is the path in what was sent and nothing else; what the input was read as is `model` (without the
types of a generic); and `input` is given only when it is short.
"""

import json
import re
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pangloss_models import ModelRegistry
from pangloss_models.initialise_models.tagged_union import is_tag

# (longer than this, an input is left out, and a part of a location is cut)
MAX_INPUT = 200
MAX_PART = 80
# (the types of a generic class: `Causes[Accusation, Appointment, ...]Create`)
PARAMETERS = re.compile(r"\[.{20,}\]")
NOTHING = object()

MESSAGES = {
    # (Pydantic's: "Unable to extract tag using discriminator choose()")
    "union_tag_not_found": "Input should be an object, of one of the types that are allowed here",
}


def short(part: str) -> str:
    part = PARAMETERS.sub("[…]", part)
    return part if len(part) <= MAX_PART else part[: MAX_PART - 1] + "…"


def is_model(part: str) -> bool:
    return is_tag(part) or part in ModelRegistry.all_models()


def located(loc: tuple | list, body: Any) -> tuple[list, str | None]:
    """The location without the members of unions it passes through, and the last of them. A part is a member
    only if it is not a key of what was sent there"""
    if not loc or loc[0] != "body":
        return [short(p) if isinstance(p, str) else p for p in loc], None
    path: list = [loc[0]]
    value = body
    model = None
    for part in loc[1:]:
        if isinstance(part, int):
            inside = isinstance(value, list) and -len(value) <= part < len(value)
            value = value[part] if inside else NOTHING
            path.append(part)
        elif isinstance(value, dict) and part in value:
            value = value[part]
            path.append(part)
        elif isinstance(part, str) and is_model(part):
            model = short(part)
        else:
            value = NOTHING
            path.append(short(part) if isinstance(part, str) else part)
    return path, model


def is_brief(value: Any) -> bool:
    if isinstance(value, str):
        return len(value) <= MAX_INPUT
    if isinstance(value, dict | list | tuple):
        try:
            return len(json.dumps(value, default=str)) <= MAX_INPUT
        except TypeError, ValueError:
            return False
    return True


def problem(error: dict, body: Any) -> dict:
    loc, model = located(error.get("loc", ()), body)
    made = {**error, "loc": loc}
    if model is not None:
        made["model"] = model
    if error.get("type") in MESSAGES:
        made["msg"] = MESSAGES[error["type"]]
        made.pop("ctx", None)
    if "input" in made and not is_brief(made["input"]):
        del made["input"]
    return made


async def validation_error_handler(request: Request, error: Exception) -> JSONResponse:
    # (registered for `RequestValidationError` alone)
    assert isinstance(error, RequestValidationError)
    problems = [problem(found, error.body) for found in error.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(problems)})
