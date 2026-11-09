"""The dump as a job on the admin page (found by `pangloss_admin`; nothing else imports this module)"""

import datetime

from pangloss_admin import Choice, Flag, JobContext, JobKind
from pangloss_core import settings as core_settings


def _file_name(options: dict) -> str:
    project = "".join(
        character if character.isalnum() else "-"
        for character in core_settings.SETTINGS.PROJECT_NAME
    )
    day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    return f"{project}-{day}.{options['format']}{'.gz' if options['compress'] else ''}"


async def run_dump(context: JobContext) -> None:
    from pangloss_rdf.dump import dump

    options = context.options

    def progress(step: int, steps: int, current: str, items: int, quads: int) -> None:
        context.progress(step, steps, current, {"items": items, "quads": quads})

    result = await dump(
        context.directory / _file_name(options),
        options["format"],
        None,
        options["include_unpublished"],
        options["include_unused"],
        progress,
    )
    context.progress(counts={"items": result.items, "quads": result.quads})


jobs = [
    JobKind(
        "rdf_dump",
        run_dump,
        options=(
            Choice("format", ("nq", "trig", "ttl"), "nq"),
            Flag("compress", True),
            Flag("include_unpublished"),
            Flag("include_unused"),
        ),
    )
]
