"""The dump as a job of the admin page, on a real database"""

import gzip

import pytest

from pangloss_admin.kinds import job_kinds
from pangloss_admin.runner import run_job
from pangloss_admin.store import JobStore
from pangloss_models import Entity, initialise


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_the_dump_job_writes_a_file_and_says_how_far_it_got(
    clear_database, tmp_path
):
    class Person(Entity):
        pass

    initialise()
    await Person.Create(label="Someone").save()

    kinds = job_kinds(["pangloss_rdf"])
    assert list(kinds) == ["rdf_dump"]
    options = kinds["rdf_dump"].checked_options({})
    assert options == {
        "format": "nq",
        "compress": True,
        "include_unpublished": False,
        "include_unused": False,
    }

    store = JobStore(tmp_path / "jobs")
    job = store.create("rdf_dump", options, "me")
    await run_job(store, job["id"], kinds)

    done = store.read(job["id"])
    assert done is not None
    assert done["state"] == "finished", done["error"]
    assert done["counts"]["items"] == 1
    assert done["counts"]["quads"] > 1
    [file] = done["files"]
    assert file["name"].endswith(".nq.gz")
    with gzip.open(store.files(job["id"]) / file["name"], "rt") as text:
        assert "Someone" in text.read()
