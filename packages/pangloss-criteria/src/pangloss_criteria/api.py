"""What the app adds to the server: the worker, as a background task (`CRITERIA_WORKER_IN_SERVER = False` to run it
in a process of its own, `pangloss criteria worker`)."""

from typing import Any

from fastapi import FastAPI
from pangloss_api import BackgroundTask

from pangloss_criteria.worker import worker


def configure_app(app: FastAPI, settings: Any) -> None:
    if getattr(settings, "CRITERIA_WORKER_IN_SERVER", True):
        app.state.background_tasks.append(BackgroundTask("criteria", worker.run))
