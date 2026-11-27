"""`GET /api/compare/{type}/{ref}?near=true` where `pangloss-vectors` is not installed (the settings of this folder):
no pairs, `near.state` `none`, the same 404s; and without `near` the answer is the pairs by rule with `near` null
(implementation_docs/spaces-and-comparison-plan.md, step 6.4). Nothing written."""

from typing import no_type_check
from uuid import uuid4

import pytest
from pangloss_compare.compare import compare

from test_compare_pairs_live import counts, settled, stored
from test_compare_route_live import client, world

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
async def test_without_vectors_there_are_no_pairs_through_near_entities(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await world(m)
    before = await settled(db_driver)
    id = stored(db_driver, "Ada is born")

    async with client() as api:
        near = await api.get(f"/api/compare/Birth/{id}?near=true")
        plain = await api.get(f"/api/compare/Birth/{id}")
        explicit = await api.get(f"/api/compare/Birth/{id}?near=false")
        missing = await api.get(f"/api/compare/Birth/{uuid4()}?near=true")
        other_class = await api.get(f"/api/compare/Activity/{id}?near=true")

    assert near.status_code == 200, near.text
    answer = near.json()
    assert answer["pairs"] == [] and answer["more"] is False
    assert answer["near"] == {"profile": None, "k": 5, "floor": 0.6, "state": "none"}
    assert answer["statement"]["label"] == "Ada is born"
    # (without it: the pairs by rule, as before, and `near` null)
    assert plain.json() == explicit.json() == (await compare(id, False)).as_json()
    assert list(plain.json()) == ["statement", "pairs", "more", "model", "near"]
    assert plain.json()["near"] is None
    assert [e["found"] for e in plain.json()["pairs"]] == ["rule"]
    assert missing.status_code == 404 and other_class.status_code == 404
    assert counts(db_driver) == before
