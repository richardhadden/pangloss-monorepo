"""Logging for every Pangloss package.

All of Pangloss logs to loggers under `pangloss` (`pangloss.api.auth`, `pangloss.memgraph.queries`,
and so on), so that one area can be turned up or down alone (`logging.getLogger("pangloss.memgraph")`).
`configure_logging` (called when the app is made, and by the command line) puts one handler on
`pangloss`, from the settings `LOG_LEVEL` and `LOG_FORMAT` ("text", or "json": a line each).

What is logged follows these rules:

- Never a password, a token, an `Authorization` header, or the content of a document or entity: ids,
  model names, counts and parameter names. A secret that gets into a message anyway is replaced by
  `[redacted]` on the way out (`redact`), as a last defence.
- What comes from a client (a username) is logged with `%r`, so that it cannot make a line of its own.
- A failure is logged once, where it is dealt with.
- Each record has the `request_id` of the request it was made in (`request_id`), if there is one.
"""

import contextvars
import datetime
import json
import logging
import re
import sys
from typing import Any, Literal

ROOT_LOGGER = "pangloss"
HANDLER_MARKER = "_pangloss_handler"

# The id of the request being dealt with, set by the API's middleware
request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pangloss_request_id", default=None
)

REDACTED = "[redacted]"

# A secret that should never be in a log line: a JWT (the tokens of a session), a personal access
# token (`pgl_...`), the value of an Authorization header, a password given as `password=...`
SECRET_PATTERNS = [
    re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*"),
    re.compile(r"\bpgl_[\w-]{8,}"),
    re.compile(r"(?i)\b(bearer|basic)\s+[\w.~+/=-]{8,}"),
    re.compile(
        r"(?i)\b(password|passwd|secret|token|authorization)(['\"]?\s*[:=]\s*)['\"]?[^\s,'\"}&]+"
    ),
]


def redact(text: str) -> str:
    """`text` with anything that looks like a secret replaced"""
    for pattern in SECRET_PATTERNS:
        if pattern.groups == 1:
            text = pattern.sub(lambda match: f"{match.group(1)} {REDACTED}", text)
        elif pattern.groups == 2:
            text = pattern.sub(
                lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text
            )
        else:
            text = pattern.sub(REDACTED, text)
    return text


class RequestIdFilter(logging.Filter):
    """Gives each record the `request_id` of the request it was made in"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class TextFormatter(logging.Formatter):
    """`2026-10-24 10:00:00 INFO pangloss.api.auth [3f2a...] message`, with secrets redacted"""

    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s%(request_tag)s %(message)s"
        )

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None)
        record.request_tag = f" [{rid}]" if rid else ""
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    """One JSON object a line: `time`, `level`, `logger`, `message`, `request_id` (if any), and
    `exception` (if any); with secrets redacted"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.datetime.fromtimestamp(
                record.created, datetime.UTC
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if rid := getattr(record, "request_id", None):
            entry["request_id"] = rid
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(entry, default=str))


class StderrHandler(logging.StreamHandler):
    """Writes to whatever `sys.stderr` is at the time (so a redirected one is followed, and a
    closed one is not written to)"""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self) -> Any:  # ty: ignore[invalid-property-type-override]
        return sys.stderr


def configure_logging(
    level: str = "INFO", format: Literal["text", "json"] = "text", stream: Any = None
) -> None:
    """Put the handler on `pangloss` (once: calling it again changes the level, the format and
    where it goes)"""
    logger = logging.getLogger(ROOT_LOGGER)
    for handler in list(logger.handlers):
        if getattr(handler, HANDLER_MARKER, False):
            logger.removeHandler(handler)

    handler = logging.StreamHandler(stream) if stream else StderrHandler()
    setattr(handler, HANDLER_MARKER, True)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if format == "json" else TextFormatter())
    logger.addHandler(handler)
    logger.setLevel(level.upper())


def configure_from_settings(settings: Any) -> None:
    configure_logging(
        getattr(settings, "LOG_LEVEL", "INFO"), getattr(settings, "LOG_FORMAT", "text")
    )
