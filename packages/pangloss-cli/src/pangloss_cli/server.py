"""`pangloss run` and `pangloss dev`: starting the API server (with uvicorn)"""

import importlib.util
import os
import sys
from pathlib import Path

import typer

from pangloss_cli.project import Project, fail, import_if_present

APP = "pangloss_api.app:create_app"

# Where the settings module is given to the server, which may be a new process
SETTINGS_ENVIRONMENT_VARIABLE = "PANGLOSS_SETTINGS"

# Directories that hold environments, not the project's code
ENVIRONMENT_DIRECTORIES = (".venv", "venv")


def installed_app_directories(project: Project, root: Path) -> list[Path]:
    """The directories of installed apps that are not in the project (for example
    a Pangloss package being worked on), but not those of installed packages"""
    assert project.settings is not None
    directories = []
    for app in project.settings.INSTALLED_APPS:
        try:
            spec = importlib.util.find_spec(app)
        except ImportError, ValueError:
            continue
        for location in (spec.submodule_search_locations or []) if spec else []:
            path = Path(location).resolve()
            if "site-packages" in path.parts or path.is_relative_to(root):
                continue
            directories.append(path)
    return directories


def reload_options(project: Project, root: Path) -> dict:
    """What `uvicorn.run` needs to restart when the code or settings change"""
    return {
        "reload": True,
        "reload_dirs": [
            str(root),
            *[str(path) for path in installed_app_directories(project, root)],
        ],
        # (`.env` holds settings; it would be left out for being hidden)
        "reload_includes": ["*.py", ".env"],
        "reload_excludes": [
            str(root / name)
            for name in ENVIRONMENT_DIRECTORIES
            if (root / name).is_dir()
        ],
    }


def serve(project: Project, host: str, port: int, reload: bool) -> None:
    project.require_settings()
    assert project.location is not None  # (there are settings, so it was found)
    root = project.location.root.resolve()

    try:
        import uvicorn

        if import_if_present("pangloss_api") is None:
            raise ImportError("pangloss_api")
    except ImportError:
        fail(
            "The server needs the pangloss-api package (and uvicorn): add "
            "pangloss-api to the dependencies of the project."
        )
        return

    # The server runs from the project, as `.env` and imports are found from there.
    # (With reload it is a new process, which gets these from the environment.)
    os.chdir(root)
    os.environ[SETTINGS_ENVIRONMENT_VARIABLE] = project.location.module
    os.environ["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(root), os.environ.get("PYTHONPATH")])
    )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    options = reload_options(project, root) if reload else {}
    if reload:
        typer.echo(f"Reloading when files change in {root}")

    uvicorn.run(APP, factory=True, host=host, port=port, app_dir=str(root), **options)
