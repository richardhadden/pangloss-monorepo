"""`pangloss admin run-job`: how the server starts a job's process. Not for typing"""

import asyncio

import typer

cli = typer.Typer(name="admin", help="Administration", no_args_is_help=True)


@cli.command("run-job", hidden=True)
def run_job_command(ctx: typer.Context, job_id: str) -> None:
    from pangloss_core import settings as core_settings
    from pangloss_models import initialise

    from pangloss_admin.kinds import job_kinds
    from pangloss_admin.runner import run_job, start_heartbeat
    from pangloss_admin.store import JobStore, jobs_directory

    project = ctx.obj
    settings = project.require_settings()
    store = JobStore(jobs_directory(core_settings.SETTINGS))
    start_heartbeat(store, job_id)
    backend = project.require_database()
    project.import_models()
    initialise()

    async def main() -> bool:
        await backend.connect()
        try:
            return await run_job(store, job_id, job_kinds(settings.INSTALLED_APPS))
        finally:
            await backend.disconnect()

    if not asyncio.run(main()):
        raise typer.Exit(1)
