"""`pangloss users <command>`"""

import asyncio
from collections.abc import Awaitable, Callable

import typer
from pangloss_users import service
from pangloss_users.exceptions import PanglossUserError
from pangloss_users.models import User

from pangloss_cli.project import Project, fail

users_cli = typer.Typer(name="users", help="Manage users", no_args_is_help=True)


def run_with_database[T](project: Project, function: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine function with the database connected. Errors about users are
    shown, rather than raised."""
    backend = project.require_database()

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    try:
        return asyncio.run(main())
    except PanglossUserError as error:
        fail(str(error))
        raise  # (fail raises)


def project_of(ctx: typer.Context) -> Project:
    return ctx.obj


def describe(user: User) -> str:
    flags = [
        flag for flag, on in (("admin", user.admin), ("disabled", user.disabled)) if on
    ]
    parts = [user.username, user.email or "(no email)"]
    if user.full_name:
        parts.append(user.full_name)
    if flags:
        parts.append(f"[{', '.join(flags)}]")
    return "  ".join(parts)


@users_cli.command()
def create(
    ctx: typer.Context,
    username: str = typer.Option(..., prompt=True),
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(
        ..., prompt=True, confirmation_prompt=True, hide_input=True
    ),
    full_name: str | None = typer.Option(None, help="The user's full name"),
    admin: bool = typer.Option(False, "--admin/--no-admin", prompt="Make admin?"),
) -> None:
    """Add a new user (asking for what is not given as an option)"""
    project = project_of(ctx)
    user = run_with_database(
        project,
        lambda: service.create_user(
            username=username,
            email=email,
            password=password,
            full_name=full_name or None,
            admin=admin,
        ),
    )
    typer.secho(f"Created user '{user.username}'", fg="green")


@users_cli.command("list")
def list_users(ctx: typer.Context) -> None:
    """List the users"""
    for user in run_with_database(project_of(ctx), service.list_users):
        typer.echo(describe(user))


@users_cli.command("set-password")
def set_password(
    ctx: typer.Context,
    username: str,
    password: str = typer.Option(
        ..., prompt=True, confirmation_prompt=True, hide_input=True
    ),
) -> None:
    """Set a user's password"""
    run_with_database(project_of(ctx), lambda: service.set_password(username, password))
    typer.secho(f"Changed the password of '{username}'", fg="green")


def set_flag(
    ctx: typer.Context, username: str, change: Callable[[], Awaitable], done: str
):
    run_with_database(project_of(ctx), change)
    typer.secho(f"'{username}' {done}", fg="green")


@users_cli.command("make-admin")
def make_admin(ctx: typer.Context, username: str) -> None:
    """Make a user an admin"""
    set_flag(
        ctx, username, lambda: service.set_admin(username, True), "is now an admin"
    )


@users_cli.command("remove-admin")
def remove_admin(ctx: typer.Context, username: str) -> None:
    """Make an admin an ordinary user"""
    set_flag(
        ctx,
        username,
        lambda: service.set_admin(username, False),
        "is no longer an admin",
    )


@users_cli.command()
def disable(ctx: typer.Context, username: str) -> None:
    """Stop a user logging in or writing (what they wrote stays)"""
    set_flag(ctx, username, lambda: service.set_disabled(username, True), "is disabled")


@users_cli.command()
def enable(ctx: typer.Context, username: str) -> None:
    """Let a disabled user log in and write again"""
    set_flag(ctx, username, lambda: service.set_disabled(username, False), "is enabled")


# ---------------------------------------------------------------------------
# Personal access tokens (for scripts, `git` and the SDK)
# ---------------------------------------------------------------------------

tokens_cli = typer.Typer(
    name="tokens", help="Personal access tokens of users", no_args_is_help=True
)
users_cli.add_typer(tokens_cli, name="tokens")


@tokens_cli.command("create")
def create_token(
    ctx: typer.Context,
    username: str,
    name: str = typer.Option(..., prompt="What is the token for?"),
    scope: str = typer.Option("write", help="'read' (can only read) or 'write'"),
    expires_days: int | None = typer.Option(None, help="Days until it stops working"),
) -> None:
    """Make a token for a user. It is shown once: it is not kept, and cannot be found again"""
    info, token = run_with_database(
        project_of(ctx),
        lambda: service.create_access_token(username, name, scope, expires_days),
    )
    typer.secho(
        f"Token '{info.name}' ({info.scope}) for '{username}', id {info.id}:",
        fg="green",
    )
    typer.echo(token)
    typer.echo("Keep it now: it cannot be shown again.", err=True)


@tokens_cli.command("list")
def list_tokens(ctx: typer.Context, username: str) -> None:
    """A user's tokens (not the tokens themselves)"""
    found = run_with_database(
        project_of(ctx), lambda: service.list_access_tokens(username)
    )
    if not found:
        typer.echo(f"'{username}' has no tokens")
    for info in found:
        expires = (
            f"expires {info.expires_when:%Y-%m-%d}"
            if info.expires_when
            else "no expiry"
        )
        used = (
            f"last used {info.last_used_when:%Y-%m-%d %H:%M}"
            if info.last_used_when
            else "never used"
        )
        typer.echo(f"{info.id}  {info.name}  [{info.scope}]  {expires}  {used}")


@tokens_cli.command("revoke")
def revoke_token(ctx: typer.Context, username: str, token_id: str) -> None:
    """Delete one of a user's tokens, by its id (see `list`)"""
    revoked = run_with_database(
        project_of(ctx), lambda: service.revoke_access_token(username, token_id)
    )
    if not revoked:
        fail(f"'{username}' has no token with the id {token_id}")
    typer.secho(f"Revoked the token {token_id} of '{username}'", fg="green")
