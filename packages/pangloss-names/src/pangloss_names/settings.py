"""The settings of `pangloss-names`, read from the project's settings object with their defaults
(implementation_docs/similarity-build-plan.md, phase 8):

- `NAMES_DIMENSION` (256): the length of the name part's vectors. A whole number from 8 to 2048.
- `NAMES_VARIANTS` (None): a table of name variants, the path of a CSV file (absolute, or relative to the directory
  of the settings module). One line for each canonical form, the form first and then its variants:

      # given names
      Johannes,Johann,Hans,Jan
      Margaret,Margareta,Greta

  UTF-8; blank lines and lines that start with `#` are skipped; each cell is one word once folded (`maths.fold`). A
  word of a name that is a variant is replaced by its canonical form before its trigrams are made, so `Hans Mayer`
  and `Johannes Mayer` have the same name vector. Read once for a settings object (`variants()`), forgotten when the
  models are reset; checked at `initialise()` when the app is installed (`check_variants`), each fault refused by the
  file and the line. What the part's signature holds of it is `variants_hash()`, so a changed table makes a rebuild
  due for the name part alone.
"""

import csv
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pangloss_models import ModelRegistry
from pangloss_models.exceptions import PanglossInitialisationError

DEFAULT_DIMENSION = 256
DIMENSIONS = (8, 2048)

APP = "pangloss_names"
VARIANTS = "NAMES_VARIANTS"

__all__ = ["check_variants", "dimension", "read_variants", "variants", "variants_hash"]

# (the table read: for the settings object, the value of `NAMES_VARIANTS` it was read for, and what was read)
_remembered: tuple[Any, Any, dict[str, list[str]]] | None = None


def _settings(settings: Any) -> Any:
    if settings is not None:
        return settings
    from pangloss_core import settings as core_settings

    return core_settings.__dict__.get("SETTINGS")


def dimension(settings: Any = None) -> int:
    """`NAMES_DIMENSION`: the length of the name part's vectors (256)"""
    value = getattr(_settings(settings), "NAMES_DIMENSION", DEFAULT_DIMENSION)
    low, high = DIMENSIONS
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise PanglossInitialisationError(
            f"NAMES_DIMENSION is a whole number from {low} to {high} (the length of the name part's vectors), "
            f"not {value!r}"
        )
    return value


def variants_path(settings: Any = None) -> Path | None:
    """The file `NAMES_VARIANTS` names, or None if it names none: a relative path is taken from the directory of the
    module the settings class is declared in (the project's settings module), or the working directory if that
    module has no file"""
    settings = _settings(settings)
    value = getattr(settings, VARIANTS, None)
    if value is None:
        return None
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise PanglossInitialisationError(
            f"{VARIANTS} is the path of a CSV file of name variants (a canonical form and its variants on each line), "
            f"or None, not {value!r}"
        )
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    module = sys.modules.get(type(settings).__module__)
    found = getattr(module, "__file__", None)
    base = Path(found).parent if found else Path.cwd()
    return base / path


def read_variants(path: Path) -> dict[str, list[str]]:
    """The canonical forms of the file and their variants, as written (each cell stripped; a variant that folds to
    its own form left out). Refuses, by the file and the line (`PanglossInitialisationError`): a file that is not
    there or not UTF-8; a line with no variant; a cell that is not one word once folded (two words, or none); a
    canonical form on two lines; a variant of two canonical forms; a variant that is itself a canonical form"""
    from pangloss_names.maths import fold

    def refused(line: int | None, why: str) -> PanglossInitialisationError:
        where = f"{path}" if line is None else f"{path}, line {line}"
        return PanglossInitialisationError(f"{VARIANTS}: {where}: {why}")

    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise refused(
            None, "there is no such file (the table of name variants)"
        ) from None
    except IsADirectoryError:
        raise refused(None, "is a directory, not a CSV file") from None
    except UnicodeDecodeError as error:
        raise refused(None, f"is not UTF-8 ({error.reason})") from None

    def word(line: int, cell: str) -> str:
        words = fold(cell)
        if len(words) != 1:
            raise refused(
                line,
                f"a cell is one word, and {cell.strip()!r} is "
                + (f"{len(words)} ({' '.join(words)})" if words else "none"),
            )
        return words[0]

    # (each line kept: its number, its form as written and folded, its variants as written and folded)
    lines: list[tuple[int, str, str, list[tuple[str, str]]]] = []
    forms: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cells = next(csv.reader([line]))
        form = cells[0].strip()
        folded = word(number, cells[0])
        if folded in forms:
            raise refused(
                number,
                f"the canonical form {form!r} is on line {forms[folded]} too: give its variants on one line",
            )
        forms[folded] = number
        if len(cells) < 2:
            raise refused(number, f"the canonical form {form!r} has no variant")
        lines.append(
            (
                number,
                form,
                folded,
                [(cell.strip(), word(number, cell)) for cell in cells[1:]],
            )
        )
    found: dict[str, list[str]] = {}
    # (each variant's canonical form, folded and as written, and its line)
    of: dict[str, tuple[str, str, int]] = {}
    for number, form, folded, cells in lines:
        given: list[str] = []
        for cell, variant in cells:
            if variant == folded:
                continue
            if variant in forms:
                raise refused(
                    number,
                    f"{cell!r} is given as a variant of {form!r} and is itself a canonical form (line "
                    f"{forms[variant]})",
                )
            if variant in of and of[variant][0] != folded:
                raise refused(
                    number,
                    f"{cell!r} is a variant of two canonical forms: of {form!r} here and of "
                    f"{of[variant][1]!r} on line {of[variant][2]}",
                )
            if variant not in of:
                of[variant] = (folded, form, number)
                given.append(cell)
        found[form] = given
    return found


def variants(settings: Any = None) -> Mapping[str, Sequence[str]]:
    """The table of variants: canonical forms of a word of a name, each with its variants (`{"Johannes": ["Hans",
    "Jan"]}`), as the file of `NAMES_VARIANTS` gives them and `maths.variants_table` takes them; `{}` if the setting
    names none. Read once for the settings object, and again after the models are reset"""
    global _remembered
    settings = _settings(settings)
    value = getattr(settings, VARIANTS, None)
    remembered = _remembered
    if remembered is not None and remembered[0] is settings and remembered[1] == value:
        return remembered[2]
    path = variants_path(settings)
    found = {} if path is None else read_variants(path)
    _remembered = (settings, value, found)
    return found


def variants_hash(settings: Any = None) -> str:
    """What the name part's signature holds of the table of variants: a hash of the table it makes
    (`maths.variants_table`), so that a comment, a blank line, the order of the lines or the case of a word changes
    nothing; with no table, the hash of the empty one"""
    from pangloss_vectors.parts import signature_of

    from pangloss_names.maths import variants_table

    return signature_of(variants_table(variants(settings)))


def forget() -> None:
    """(`ModelRegistry.on_reset`) forget the table read"""
    global _remembered
    _remembered = None


def check_variants() -> None:
    """(`ModelRegistry.after_finalise`) a project with this app installed has its table of variants read and checked
    at `initialise()`: what is wrong with it is refused there, by the file and the line"""
    settings = _settings(None)
    if APP not in list(getattr(settings, "INSTALLED_APPS", None) or []):
        return
    variants(settings)


def install() -> None:
    """(`pangloss_names._install`)"""
    if check_variants not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_variants)
    if forget not in ModelRegistry.on_reset:
        ModelRegistry.on_reset.append(forget)
