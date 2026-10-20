from typer.testing import CliRunner

from pangloss_cli.main import build_app

runner = CliRunner()


class Result:
    def __init__(self, result):
        self.exit_code = result.exit_code
        self.output = result.output + result.stderr


def invoke(*args: str, input: str | None = None):
    app = build_app(argv=[], environment={})
    return Result(runner.invoke(app, list(args), input=input))


def create(username="john", email="john@example.com", *extra):
    admin = [] if "--admin" in extra else ["--no-admin"]
    return invoke(
        "users",
        "create",
        "--username",
        username,
        "--email",
        email,
        "--password",
        "correct horse",
        *admin,
        *extra,
    )


def test_create_and_list(project):
    result = create("john", "john@example.com", "--admin", "--full-name", "John Smith")
    assert result.exit_code == 0, result.output
    assert "Created user 'john'" in result.output

    result = invoke("users", "list")
    assert result.exit_code == 0
    assert "john  john@example.com  John Smith  [admin]" in result.output


def test_create_asks_for_what_is_missing(project):
    result = invoke(
        "users",
        "create",
        input="jane\njane@example.com\ncorrect horse\ncorrect horse\ny\n",
    )
    assert result.exit_code == 0, result.output
    assert "Created user 'jane'" in result.output
    assert "[admin]" in invoke("users", "list").output


def test_create_reports_errors_without_a_traceback(project):
    assert create().exit_code == 0

    taken = create("john", "other@example.com")
    assert taken.exit_code == 1
    assert "already in use" in taken.output

    bad_email = create("jane", "not an email")
    assert bad_email.exit_code == 1

    short = invoke(
        "users", "create", "--username", "jane", "--email", "jane@example.com",
        "--password", "short", "--no-admin",
    )
    assert short.exit_code == 1
    assert "at least 8 characters" in short.output


def test_set_password_and_flags(project):
    create()

    result = invoke("users", "set-password", "john", "--password", "a new password")
    assert result.exit_code == 0, result.output

    assert invoke("users", "make-admin", "john").exit_code == 0
    assert "[admin]" in invoke("users", "list").output
    assert invoke("users", "remove-admin", "john").exit_code == 0
    assert "[admin]" not in invoke("users", "list").output

    assert invoke("users", "disable", "john").exit_code == 0
    assert "[disabled]" in invoke("users", "list").output
    assert invoke("users", "enable", "john").exit_code == 0
    assert "[disabled]" not in invoke("users", "list").output


def test_unknown_user(project):
    result = invoke("users", "disable", "nobody")
    assert result.exit_code == 1
    assert "There is no user 'nobody'" in result.output
