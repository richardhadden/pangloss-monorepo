import io
import json
import logging

import pytest
from pangloss_core import logs

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huIn0.c2lnbmF0dXJlLXZhbHVl"


@pytest.fixture
def stream():
    stream = io.StringIO()
    yield stream
    logger = logging.getLogger("pangloss")
    for handler in list(logger.handlers):
        if getattr(handler, logs.HANDLER_MARKER, False):
            logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)


@pytest.mark.parametrize(
    "text",
    [
        f"token {JWT} was refused",
        "Authorization: Bearer abcdefgh12345678",
        "header Basic dXNlcjpwYXNzd29yZA== sent",
        "personal token pgl_abcdefgh12345678 made",
        "form password=hunter2 given",
        "{'password': 'hunter2'}",
    ],
)
def test_secrets_are_redacted(text):
    redacted = logs.redact(text)
    for secret in (JWT, "abcdefgh12345678", "dXNlcjpwYXNzd29yZA==", "hunter2"):
        assert secret not in redacted
    assert logs.REDACTED in redacted


def test_ordinary_text_is_not_changed():
    text = "Login: 'john' from 127.0.0.1 (token); write create Person 1234 v1"
    assert logs.redact(text) == text


def test_text_format_has_level_logger_and_request_id(stream):
    logs.configure_logging("INFO", "text", stream)
    token = logs.request_id.set("abc123")
    try:
        logging.getLogger("pangloss.test").info("hello %s", "there")
    finally:
        logs.request_id.reset(token)
    line = stream.getvalue().strip()
    assert "INFO pangloss.test [abc123] hello there" in line


def test_text_format_without_a_request(stream):
    logs.configure_logging("INFO", "text", stream)
    logging.getLogger("pangloss.test").info("quiet")
    assert "INFO pangloss.test quiet" in stream.getvalue()


def test_json_lines_are_parseable(stream):
    logs.configure_logging("INFO", "json", stream)
    token = logs.request_id.set("abc123")
    try:
        logging.getLogger("pangloss.test").warning("a %s", "warning")
        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("pangloss.test").exception("failed")
    finally:
        logs.request_id.reset(token)
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["level"] == "WARNING"
    assert first["logger"] == "pangloss.test"
    assert first["message"] == "a warning"
    assert first["request_id"] == "abc123"
    assert "time" in first
    assert "ValueError: boom" in second["exception"]


def test_a_secret_in_an_exception_is_redacted_in_json_and_text(stream):
    for format in ("json", "text"):
        stream.truncate(0)
        stream.seek(0)
        logs.configure_logging("INFO", format, stream)
        try:
            raise ValueError(f"bad token {JWT}")
        except ValueError:
            logging.getLogger("pangloss.test").exception("failed")
        assert JWT not in stream.getvalue()


def test_the_level_is_applied_and_calling_again_replaces_the_handler(stream):
    logs.configure_logging("WARNING", "text", stream)
    logs.configure_logging("WARNING", "text", stream)
    logger = logging.getLogger("pangloss.test")
    logger.info("not shown")
    logger.warning("shown")
    assert stream.getvalue().count("shown") == 1
    assert "not shown" not in stream.getvalue()


def test_configure_from_settings(stream):
    class Settings:
        LOG_LEVEL = "DEBUG"
        LOG_FORMAT = "json"

    logs.configure_from_settings(Settings())
    assert logging.getLogger("pangloss").level == logging.DEBUG
