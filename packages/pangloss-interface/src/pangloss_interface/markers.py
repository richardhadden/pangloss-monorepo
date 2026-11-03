"""How the interface edits a literal field, said on the field (`Annotated[int, Ge(1), Le(100), Slider()]`)"""

from typing import Any

from pangloss_models.exceptions import PanglossModelError
from pangloss_models.markers import FieldMarker


class Slider(FieldMarker):
    """An `int` or `float` field edited with a slider, from its lower bound to its upper (`Ge`/`Gt` and `Le`/`Lt`,
    which it must have), with the number beside it. `step`: how far one move of it goes (1, if not given)."""

    def __init__(self, step: int | float | None = None):
        self.step = step

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
        return {} if self.step is None else {"step": self.step}
