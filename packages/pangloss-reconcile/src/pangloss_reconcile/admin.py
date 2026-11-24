"""Reconciliation's jobs on the admin page (found by `pangloss_admin`, which this package does not depend on; nothing
else imports this module):

- `reconcile_learn`, retraining: `pangloss reconcile learn` (`fits.learn`), with `dry_run` `no` or `yes`. Its counts
  are the job's counts; the lines the command prints are its report, `learnt.txt`, in the job's directory;
- `reconcile_suggest`, the documents stored left for the worker that suggests: `pangloss reconcile suggest`
  (`suggesting.mark_stored`) over every class that can hold a stand-in, with `again` (a flag: what was tried is
  forgotten first). Its counts are what it did (`marked`, `already`, `stand_ins`, `forgotten`). (A job's options are
  declared when the module is imported, before the models may be: the classes are not an option, as the command's
  `--class` is)"""

from pangloss_admin import Choice, Flag, JobContext, JobKind

NO, YES = "no", "yes"
REPORT = "learnt.txt"


async def run_learn(context: JobContext) -> None:
    from pangloss_reconcile.fits import learn

    learnt = await learn(dry_run=context.options["dry_run"] == YES)
    context.progress(counts=learnt.counts())
    (context.directory / REPORT).write_text(
        "".join(f"{line}\n" for line in learnt.lines())
    )


async def run_suggest(context: JobContext) -> None:
    from pangloss_reconcile.suggesting import mark_stored

    done = await mark_stored(again=context.options["again"])
    context.progress(
        counts={
            "marked": done.marked,
            "already": done.already,
            "stand_ins": done.stand_ins,
            "forgotten": done.forgotten,
        }
    )


jobs = [
    JobKind(
        "reconcile_learn",
        run_learn,
        options=(Choice("dry_run", (NO, YES), NO),),
    ),
    JobKind("reconcile_suggest", run_suggest, options=(Flag("again"),)),
]
