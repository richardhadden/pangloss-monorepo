"""Retraining as a job on the admin page (found by `pangloss_admin`, which this package does not depend on; nothing
else imports this module): `pangloss reconcile learn` (`fits.learn`), with `dry_run` `no` or `yes`. Its counts are
the job's counts; the lines the command prints are its report, `learnt.txt`, in the job's directory"""

from pangloss_admin import Choice, JobContext, JobKind

NO, YES = "no", "yes"
REPORT = "learnt.txt"


async def run_learn(context: JobContext) -> None:
    from pangloss_reconcile.fits import learn

    learnt = await learn(dry_run=context.options["dry_run"] == YES)
    context.progress(counts=learnt.counts())
    (context.directory / REPORT).write_text(
        "".join(f"{line}\n" for line in learnt.lines())
    )


jobs = [
    JobKind(
        "reconcile_learn",
        run_learn,
        options=(Choice("dry_run", (NO, YES), NO),),
    )
]
