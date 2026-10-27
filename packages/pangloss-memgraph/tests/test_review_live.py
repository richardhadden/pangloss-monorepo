"""Review (`pangloss-review`) with the data in Memgraph"""

from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid4

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_review import service
from pangloss_review.exceptions import (
    PanglossCommentTargetError,
    PanglossNoSuchCommentError,
    PanglossNotReviewableError,
    PanglossSelfReviewError,
)
from pangloss_review.meta import ReviewMeta
from pangloss_review.status import ReviewStatus
from pangloss_users import current_request_username, see_unpublished

from .conftest import MEMGRAPH_DATABASE

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Note(Document):
        text: str

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)
        title: str
        notes: list[Note]

    class Memo(Document):
        title: str

    class Postcard(Letter):  # (inherits that it is reviewed)
        pass

    initialise()
    return Note, Letter, Memo, Postcard


def make_user(db_driver, username):
    db_driver.execute_query(
        "MERGE (:PGUser {username: $username})",
        parameters_={"username": username},
        database=MEMGRAPH_DATABASE,
    )


@no_type_check
async def test_a_reviewed_document_starts_unpublished_and_is_published_by_checking(
    clear_database, db_driver
):
    Note, Letter, Memo, Postcard = models()
    make_user(db_driver, "reviewer")
    letter = await Letter.Create(
        label="L", title="t", notes=[Note.Create(label="n", text="a")]
    ).save()
    memo = await Memo.Create(label="M", title="t").save()
    postcard = await Postcard.Create(label="P", title="t", notes=[]).save()

    state = await service.get_state(letter.id)
    assert (state.status, state.published) == (ReviewStatus.UNCHECKED, False)
    assert state.created_by == "pangloss_default_user"
    meta = (await Letter.get(id=letter.id)).meta
    assert (meta.published, meta.review_status) == (False, "unchecked")

    # (only logged-in users see it; a class that is not reviewed is published at once)
    token = see_unpublished.set(False)
    try:
        assert (await Letter.list()).results == []
        assert [m.label for m in (await Memo.list()).results] == ["M"]
    finally:
        see_unpublished.reset(token)
    with pytest.raises(PanglossNotReviewableError):
        await service.get_state(memo.id)
    assert (await service.get_state(postcard.id)).published is False

    queue = await service.queue()
    assert sorted(i.label for i in queue.results) == ["L", "P"]
    assert queue.count == 2

    errors = await service.set_status(
        letter.id, ReviewStatus.ERRORS_FOUND, "reviewer", comment="Wrong date"
    )
    assert (errors.status, errors.published, errors.reviewed_by) == (
        ReviewStatus.ERRORS_FOUND,
        False,
        "reviewer",
    )
    assert errors.open_comments == 1
    assert [i.label for i in (await service.queue()).results] == ["P"]
    found = await service.queue([ReviewStatus.ERRORS_FOUND])
    assert [i.label for i in found.results] == ["L"]

    done = await service.set_status(letter.id, ReviewStatus.CHECKED, "reviewer")
    assert done.published is True
    token = see_unpublished.set(False)
    try:
        assert [i.label for i in (await Letter.list()).results] == ["L"]
    finally:
        see_unpublished.reset(token)

    # an edit leaves it published and checked
    await Letter.Update(id=letter.id, label="L", title="changed", notes=[]).save()
    after = await service.get_state(letter.id)
    assert (after.status, after.published) == (ReviewStatus.CHECKED, True)
    assert after.last_edited_by == "pangloss_default_user"

    # whoever edits can send it back for checking, which unpublishes it
    sent_back = await service.set_status(letter.id, ReviewStatus.UNCHECKED, "john")
    assert sent_back.published is False


@no_type_check
async def test_comments_on_a_document_and_on_a_part(clear_database, db_driver):
    Note, Letter, *_ = models()
    letter = await Letter.Create(
        label="L", title="t", notes=[Note.Create(label="the note", text="a")]
    ).save()
    note_id = (await Letter.get(id=letter.id)).notes[0].id

    whole = await service.add_comment(letter.id, "ann", "  Needs a source  ")
    part = await service.add_comment(letter.id, "bob", "Check this", target_id=note_id)
    assert whole.text == "Needs a source" and whole.target_id is None
    assert (part.target_id, part.target_label) == (note_id, "the note")

    assert [c.text for c in await service.list_comments(letter.id)] == [
        "Needs a source",
        "Check this",
    ]
    with pytest.raises(PanglossCommentTargetError):
        await service.add_comment(letter.id, "ann", "x", target_id=uuid4())
    with pytest.raises(PanglossNotReviewableError):
        await service.add_comment(uuid4(), "ann", "x")

    # the part is renamed, then gone: the comment still says what it was about
    await Letter.Update(
        id=letter.id,
        label="L",
        title="t",
        notes=[Note.Update(id=note_id, label="renamed", text="a")],
    ).save()
    assert (await service.list_comments(letter.id))[1].target_label == "the note"

    resolved = await service.resolve_comment(letter.id, whole.id, "bob")
    assert resolved.resolved and resolved.resolved_by == "bob"
    assert [c.text for c in await service.list_comments(letter.id)] == ["Check this"]
    assert len(await service.list_comments(letter.id, include_resolved=True)) == 2
    assert (await service.get_state(letter.id)).open_comments == 1
    with pytest.raises(PanglossNoSuchCommentError):
        await service.resolve_comment(letter.id, uuid4(), "bob")


@no_type_check
async def test_a_user_can_be_stopped_from_checking_their_own_work(
    clear_database, db_driver, monkeypatch
):
    from pangloss_core import settings as core_settings

    _, Letter, *_ = models()
    make_user(db_driver, "ann")
    make_user(db_driver, "bob")
    token = current_request_username.set("ann")
    try:
        letter = await Letter.Create(label="L", title="t", notes=[]).save()
    finally:
        current_request_username.reset(token)

    # (allowed unless the setting says no)
    await service.set_status(letter.id, ReviewStatus.UNCHECKED, "ann")

    monkeypatch.setattr(
        core_settings,
        "SETTINGS",
        SimpleNamespace(
            DATABASE_MODULE=core_settings.SETTINGS.DATABASE_MODULE,
            REVIEW_ALLOW_SELF_REVIEW=False,
        ),
    )
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.CHECKED, "ann")
    assert (
        await service.set_status(letter.id, ReviewStatus.CHECKED, "bob")
    ).published is True

    # the last editor counts as well
    token = current_request_username.set("bob")
    try:
        await Letter.Update(id=letter.id, label="L", title="u", notes=[]).save()
    finally:
        current_request_username.reset(token)
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.CHECKED, "bob")
    # (the creator still counts, though somebody else edited it since)
    with pytest.raises(PanglossSelfReviewError):
        await service.set_status(letter.id, ReviewStatus.CHECKED, "ann")
    await service.set_status(letter.id, ReviewStatus.CHECKED, "cat")


@no_type_check
async def test_the_api(clear_database, db_driver):
    from pangloss_api.app import create_app
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    models()
    app = create_app()
    app.include_router(api.router)
    api.configure_app(app, None)

    async with client_for(app) as client:
        ann = await logged_in(client, "ann")
        bob = await logged_in(client, "bob")

        # nothing about review is sent with a create
        made = await client.post(
            "/api/Letter",
            headers=ann,
            json={
                "type": "Letter",
                "label": "L",
                "title": "t",
                "notes": [{"type": "Note", "label": "n", "text": "a"}],
            },
        )
        assert made.status_code == 201, made.text
        id = made.json()["id"]
        memo = await client.post(
            "/api/Memo", headers=ann, json={"type": "Memo", "label": "M", "title": "t"}
        )
        assert memo.status_code == 201

        # it is in the meta of the read, and not for anyone who is not logged in
        meta = (await client.get(f"/api/Letter/{id}", headers=bob)).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (False, "unchecked")
        assert (await client.get(f"/api/Letter/{id}")).status_code == 404
        meta = (await client.get(f"/api/Memo/{memo.json()['id']}")).json()["meta"]
        assert (meta["published"], meta["reviewStatus"]) == (True, None)

        # review needs a login
        assert (await client.get("/api/review/queue")).status_code == 401
        queue = (await client.get("/api/review/queue", headers=bob)).json()
        assert [i["label"] for i in queue["results"]] == ["L"]
        assert queue["results"][0]["createdBy"] == "ann"

        detail = (await client.get(f"/api/review/{id}", headers=bob)).json()
        assert detail["status"] == "unchecked" and detail["comments"] == []
        assert (
            await client.get(f"/api/review/{memo.json()['id']}", headers=bob)
        ).status_code == 404

        part = (await client.get(f"/api/Letter/{id}", headers=bob)).json()["notes"][0][
            "id"
        ]
        comment = await client.post(
            f"/api/review/{id}/comments",
            headers=bob,
            json={"text": "Check this", "targetId": part},
        )
        assert comment.status_code == 201
        assert comment.json()["targetLabel"] == "n"
        bad = await client.post(
            f"/api/review/{id}/comments",
            headers=bob,
            json={"text": "x", "targetId": str(uuid4())},
        )
        assert bad.status_code == 422

        errors = await client.post(
            f"/api/review/{id}/status",
            headers=bob,
            json={"status": "errors_found", "comment": "Wrong"},
        )
        assert errors.status_code == 200
        assert errors.json()["status"] == "errors_found"
        assert len(errors.json()["comments"]) == 2

        resolved = await client.post(
            f"/api/review/{id}/comments/{comment.json()['id']}/resolve", headers=bob
        )
        assert resolved.json()["resolved"] is True
        shown = (await client.get(f"/api/review/{id}", headers=bob)).json()
        assert len(shown["comments"]) == 1
        everything = (
            await client.get(f"/api/review/{id}?resolved=true", headers=bob)
        ).json()
        assert len(everything["comments"]) == 2

        done = await client.post(
            f"/api/review/{id}/status", headers=bob, json={"status": "checked"}
        )
        assert done.json()["published"] is True
        # (published: anyone can read it, with its state in the meta)
        read = (await client.get(f"/api/Letter/{id}")).json()
        assert read["meta"]["reviewStatus"] == "checked"
        assert (await client.get("/api/review/queue", headers=bob)).json()["count"] == 0


@no_type_check
async def test_lists_and_searches_carry_the_state_and_can_be_filtered(
    clear_database, db_driver
):
    from pangloss_api.app import create_app
    from pangloss_models.search import Match
    from pangloss_review import api

    from .test_api_models import client_for, logged_in

    _, Letter, *_ = models()
    await Letter.Create(label="Waiting", title="t", notes=[]).save()
    wrong = await Letter.Create(label="Wrong", title="t", notes=[]).save()
    right = await Letter.Create(label="Right", title="t", notes=[]).save()
    await service.set_status(wrong.id, ReviewStatus.ERRORS_FOUND, "bob")
    await service.set_status(right.id, ReviewStatus.CHECKED, "bob")

    def states(found):
        return {
            i.label: (i.meta.published, i.meta.review_status) for i in found.results
        }

    everything = await Letter.list()
    assert states(everything) == {
        "Waiting": (False, "unchecked"),
        "Wrong": (False, "errors_found"),
        "Right": (True, "checked"),
    }
    assert states(await Letter.search(Match(where={})))["Right"] == (True, "checked")

    def labels(found):
        return sorted(i.label for i in found.results)

    assert labels(await Letter.list(published=True)) == ["Right"]
    assert labels(await Letter.list(published=False)) == ["Waiting", "Wrong"]
    assert labels(await Letter.list(review_status="errors_found")) == ["Wrong"]
    assert labels(await Letter.list(published=False, review_status="unchecked")) == [
        "Waiting"
    ]
    # (and in the other kinds of list, which count and page the same way)
    assert labels(await Letter.list(search_terms="Wr", published=False)) == ["Wrong"]
    assert (
        labels(
            await Letter.list(
                search_terms="Wr", deep_search=True, review_status="checked"
            )
        )
        == []
    )

    app = create_app()
    app.include_router(api.router)
    async with client_for(app) as client:
        bob = await logged_in(client, "bob")
        found = await client.get(
            "/api/Letter?published=false&review_status=unchecked", headers=bob
        )
        assert [r["label"] for r in found.json()["results"]] == ["Waiting"]
        assert found.json()["results"][0]["meta"]["reviewStatus"] == "unchecked"
        assert found.json()["count"] == 1
        # not logged in: what is not published is not there, whatever is asked
        assert (await client.get("/api/Letter?published=false")).json()["count"] == 0
        anyone = (await client.get("/api/Letter")).json()
        assert [r["label"] for r in anyone["results"]] == ["Right"]
