"""What jobs there are. An installed app declares its own in an `admin.py`:

    async def rebuild(context: JobContext) -> None: ...

    jobs = [JobKind("myapp_rebuild", rebuild, options=(Flag("everything"),))]

The options are data, so that the admin page can draw their form: an app needs no interface code for a job, only the
words (`{kind}_title`, `{kind}_option_{name}`, `{kind}_{name}_{value}`, `{kind}_count_{key}` in its `ui.jsonc`).
"""

import importlib
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Flag:
    name: str
    default: bool = False

    def check(self, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{self.name} must be true or false")
        return value

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "type": "flag", "default": self.default}


@dataclass(frozen=True)
class Choice:
    name: str
    values: tuple[str, ...]
    default: str

    def __post_init__(self) -> None:
        if self.default not in self.values:
            raise ValueError(f"{self.default!r} is not a value of {self.name}")

    def check(self, value: Any) -> str:
        if value not in self.values:
            raise ValueError(f"{self.name} must be one of {', '.join(self.values)}")
        return value

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "choice",
            "default": self.default,
            "values": list(self.values),
        }


@dataclass(frozen=True)
class JobKind:
    name: str
    run: Callable[[Any], Awaitable[None]]
    """`async def run(context: JobContext)`, in a process of its own, connected to the database"""
    options: tuple[Flag | Choice, ...] = ()

    def __post_init__(self) -> None:
        if not NAME.match(self.name):
            raise ValueError(f"{self.name!r} cannot be the name of a job")

    def checked_options(self, given: dict[str, Any]) -> dict[str, Any]:
        """Each option's value, or its default. A value that is wrong, or an option there is not, is a `ValueError`"""
        known = {option.name: option for option in self.options}
        unknown = sorted(set(given) - set(known))
        if unknown:
            raise ValueError(f"{self.name} has no option {', '.join(unknown)}")
        return {
            name: option.check(given[name]) if name in given else option.default
            for name, option in known.items()
        }

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "options": [option.describe() for option in self.options],
        }


def _admin_module(app: str) -> Any:
    name = f"{app}.admin"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name and (name == error.name or name.startswith(f"{error.name}.")):
            return None
        raise


def job_kinds(apps: list[str]) -> dict[str, JobKind]:
    """The jobs that the `admin.py` of the installed apps declare (the same name twice is an error)"""
    found: dict[str, JobKind] = {}
    for app in apps:
        module = _admin_module(app)
        for kind in getattr(module, "jobs", ()):
            if kind.name in found:
                raise ValueError(f"There are two admin jobs called {kind.name!r}")
            found[kind.name] = kind
    return found
