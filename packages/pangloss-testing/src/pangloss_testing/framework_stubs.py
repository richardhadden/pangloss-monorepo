"""The type stubs of the models that Pangloss's own packages declare (`pangloss_dates/models.pyi`, ...).

    uv run python -m pangloss_testing.framework_stubs            # write them
    uv run python -m pangloss_testing.framework_stubs --check    # fail if one is not what would be written

A project's stubs (`pangloss make-stubs`, and those of its SDK) name the classes made for these models
(`pangloss_dates.models.ExactDate.Create`), which a type checker cannot see without a stub of the package's module:
it then refuses every field that holds a date. So the packages ship stubs of their model modules, made here as a
project's are, from the models of the packages alone (no project: a class has no more than the package gives it).
`run_tests.sh` runs the check; write them again after changing a model of a package.
"""

import importlib
import sys
from pathlib import Path

# The modules of the packages that declare models (a new one goes here)
MODULES = (
    "pangloss_dates.models",
    "pangloss_dates.julian",
    "pangloss_dates.gregorian",
    "pangloss_dates.dateable",
    "pangloss_calendar.models",
    "pangloss_library.models",
    "pangloss_review.models",
    "pangloss_zotero.models",
)
# (imported as well, so that what they add to the models is there as on a server: they declare none themselves)
ALSO = ("pangloss_typology", "pangloss_review", "pangloss_derived")


def stubs() -> dict[Path, str]:
    """The stub of each module, by its path"""
    from pangloss_core import ClientSettings
    from pangloss_models import initialise
    from pangloss_models.typestubs import (
        modules_with_models,
        registered_class_names,
        stub_for_module,
        stub_path,
    )

    # (a storage that needs no database)
    ClientSettings(INSTALLED_APPS=[], STORAGE="pangloss_sdk.storage:api")
    modules = [importlib.import_module(name) for name in (*MODULES, *ALSO)]
    initialise()

    names = registered_class_names()
    found: dict[Path, str] = {}
    for module in modules[: len(MODULES)]:
        root = Path(module.__file__ or "").resolve().parent
        models = modules_with_models(root).get(module.__name__)
        if not models:
            raise SystemExit(
                f"{module.__name__} declares no models: take it out of MODULES"
            )
        found[stub_path(module)] = stub_for_module(module, models, names)
    return found


def main(arguments: list[str]) -> int:
    check = "--check" in arguments
    stale = []
    for path, text in sorted(stubs().items()):
        current = path.read_text() if path.exists() else None
        if current == text:
            continue
        if check:
            stale.append(path)
        else:
            path.write_text(text)
            print(f"  wrote {path}")
    for path in stale:
        print(f"  not current: {path}")
    if stale:
        print("Write them again: uv run python -m pangloss_testing.framework_stubs")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
