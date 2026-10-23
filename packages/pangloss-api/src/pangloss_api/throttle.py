"""Limiting guesses at a password: after `LOGIN_MAX_FAILURES` wrong passwords for a username
within `LOGIN_FAILURE_WINDOW_SECONDS`, that username is refused (`429`, with `Retry-After`)
until the oldest of them is out of the window. A right password clears the count.

It is kept in memory, **in each server process**: with several workers each has its own count
(so the limit is that many times as high), and a restart forgets it. It is a brake on guessing,
not a replacement for a proxy's rate limit. A `LOGIN_MAX_FAILURES` of 0 turns it off.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status
from pangloss_core import settings as core_settings

# username (lower case) -> when (monotonic seconds) each recent failure was
FAILURES: dict[str, deque[float]] = defaultdict(deque)
# (so that guessing at made-up usernames cannot make this grow without end)
MAX_USERNAMES = 10_000


def limits() -> tuple[int, float]:
    settings = core_settings.__dict__.get("SETTINGS")
    return (
        getattr(settings, "LOGIN_MAX_FAILURES", 10),
        getattr(settings, "LOGIN_FAILURE_WINDOW_SECONDS", 300),
    )


def recent(username: str, window: float) -> deque[float]:
    failures = FAILURES[username.lower()]
    cutoff = time.monotonic() - window
    while failures and failures[0] <= cutoff:
        failures.popleft()
    return failures


def check(username: str) -> None:
    """Raise 429 if the username has had too many wrong passwords lately"""
    maximum, window = limits()
    if maximum <= 0:
        return
    failures = recent(username, window)
    if len(failures) >= maximum:
        wait = max(1, int(failures[0] + window - time.monotonic()) + 1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed logins for this username: try again later",
            headers={"Retry-After": str(wait)},
        )


def failed(username: str) -> None:
    maximum, window = limits()
    if maximum <= 0:
        return
    if len(FAILURES) >= MAX_USERNAMES:
        for name in [name for name in FAILURES if not recent(name, window)]:
            del FAILURES[name]
    FAILURES[username.lower()].append(time.monotonic())


def succeeded(username: str) -> None:
    FAILURES.pop(username.lower(), None)


def reset() -> None:
    FAILURES.clear()
