"""How the interface edits a literal field, said on the field (`Annotated[int, Ge(1), Le(100), Slider()]`)"""

from typing import Any

from pangloss_models import FieldMarker, PanglossModelError


class Slider(FieldMarker):
    """An `int` or `float` field edited with a slider, from its lower bound to its upper (`Ge`/`Gt` and `Le`/`Lt`,
    which it must have), with the number beside it as text. `step`: how far one move of it goes (1, if not given).
    `unit`: what is written after the number (`Slider(unit="%")`: "40%")."""

    def __init__(self, step: int | float | None = None, unit: str | None = None):
        self.step = step
        self.unit = unit

    def check(self, owner: str, field: dict[str, Any]) -> None:
        where = f"{owner}.{field['name']}: Slider()"
        if field["type"].get("type") not in ("int", "float"):
            raise PanglossModelError(f"{where} is only for an int or a float field")
        names = {validator["name"] for validator in field["validators"]}
        if not names & {"Ge", "Gt"} or not names & {"Le", "Lt"}:
            raise PanglossModelError(
                f"{where} needs a lower and an upper bound (`Ge(...)` and `Le(...)`)"
            )

    def export(self) -> dict[str, Any]:
        given = {"step": self.step, "unit": self.unit}
        return {key: value for key, value in given.items() if value is not None}
