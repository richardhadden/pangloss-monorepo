"""The rebuild as a job on the admin page (found by `pangloss_admin`; nothing else imports this module). `part` is one
of the parts registered when the job is declared, or `all`"""

from pangloss_admin import Choice, JobContext, JobKind

from pangloss_vectors import import_installed_apps
from pangloss_vectors.parts import parts

ALL = "all"


async def run_rebuild(context: JobContext) -> None:
    from pangloss_vectors.rebuild import rebuild

    chosen = context.options["part"]

    def progress(step: int, steps: int, current: str) -> None:
        context.progress(step, steps, current)

    done = await rebuild(None if chosen == ALL else chosen, progress=progress)
    context.progress(
        counts={
            **{f"part {made.part}": made.count for made in done.parts},
            **{f"profile {made.profile}": made.count for made in done.profiles},
        }
    )
    if done.skipped:
        report = context.directory / "skipped.txt"
        report.write_text(
            "".join(f"{what}: {why}\n" for what, why in done.skipped.items())
        )


# (the installed apps first, so that each part's package has registered its part)
import_installed_apps()

jobs = [
    JobKind(
        "vectors_rebuild",
        run_rebuild,
        options=(Choice("part", (ALL, *parts()), ALL),),
    )
]
