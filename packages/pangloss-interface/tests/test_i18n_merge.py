"""Bringing a translation file up to date without losing what people wrote (`i18n.merge`).

No files and no models: flat maps of paths to text."""

import pytest
from pangloss_interface.i18n.merge import (
    ItemRename,
    Leaf,
    merge_default,
    merge_other,
    reconcile,
    renamed,
)

NAME = ("models", "Person", "name")
EN_NAME = ("models", "Person", "en", "name")
DE_NAME = ("models", "Person", "de", "name")
BIRTH = ("models", "Person", "fields", "birth", "name")
EN_BIRTH = ("models", "Person", "en", "fields", "birth", "name")
DE_BIRTH = ("models", "Person", "de", "fields", "birth", "name")


def run(generated, current=None, obsolete=None, state=None, renames=None, **kw):
    return reconcile(
        generated,
        ["en", "de"],
        "en",
        current or {},
        obsolete or {},
        state or {},
        renames or [],
        **kw,
    )


def again(first, generated, edits=None, **kw):
    """Run again on the result of a run, as a person who has changed some texts"""
    current = {**first.texts, **(edits or {})}
    return run(generated, current, first.obsolete, first.state, **kw)


# --- one text, in the default language (the table of docs/translations.md) ------------------


@pytest.mark.parametrize(
    ("new", "current", "base", "result", "how", "review"),
    [
        ("A", None, None, "A", "added", False),
        ("A", "A", "A", "A", "same", False),
        # not edited: follows the model
        ("B", "A", "A", "B", "followed", False),
        # edited, the model has not changed: the edit is kept
        ("A", "mine", "A", "mine", "kept", False),
        # edited, and the model has changed: kept, and to be looked at
        ("B", "mine", "A", "mine", "kept", True),
    ],
)
def test_a_text_in_the_default_language(new, current, base, result, how, review):
    state = None if base is None else Leaf(base, base, base)

    text, leaf, what = merge_default(new, current, state)

    assert (text, what, leaf.review) == (result, how, review)
    assert leaf.base == new  # (what the generator wrote this time)


def test_with_no_memory_a_text_that_differs_is_taken_to_be_an_edit():
    text, leaf, how = merge_default("A", "mine", None)
    assert (text, how, leaf.review) == ("mine", "kept", False)


def test_the_review_mark_stays_until_the_text_is_touched():
    first = Leaf("A", "A", "A")
    _, marked, _ = merge_default("B", "mine", first)
    assert marked.review

    _, still, _ = merge_default("B", "mine", marked)  # (nobody has looked)
    assert still.review
    _, cleared, _ = merge_default("B", "mine, looked at", marked)  # (a person has)
    assert not cleared.review


# --- one text, in another language ----------------------------------------------------------


def test_a_text_in_another_language_is_never_written_by_the_generator():
    assert merge_other("Person", None, None)[0] == ""
    assert merge_other("Person", "", None)[0] == ""
    assert merge_other("Person", "Mensch", None)[0] == "Mensch"
    assert merge_other("Person", "Mensch", Leaf("", "Person", "Mensch"))[2] == "kept"


def test_a_translation_is_marked_when_the_text_it_was_made_from_changes():
    made_from = Leaf("", "Person", "Mensch")

    _, same, _ = merge_other("Person", "Mensch", made_from)
    assert not same.review

    text, changed, _ = merge_other("Person (a human)", "Mensch", made_from)
    assert text == "Mensch" and changed.review and changed.source == "Person (a human)"

    # an empty translation has nothing to review
    assert not merge_other("Other", "", made_from)[1].review


# --- a file -------------------------------------------------------------------------------


def test_a_first_run_has_every_language_with_the_others_empty():
    done = run({NAME: "Person", BIRTH: "Birth"})

    assert done.texts == {
        EN_NAME: "Person",
        DE_NAME: "",
        EN_BIRTH: "Birth",
        DE_BIRTH: "",
    }
    assert set(done.report.added) == set(done.texts)
    assert done.obsolete == {}


def test_a_second_run_with_nothing_changed_changes_nothing():
    generated = {NAME: "Person", BIRTH: "Birth"}
    first = run(generated)

    second = again(first, generated, {DE_NAME: "Mensch", EN_BIRTH: "Date of birth"})
    third = again(second, generated)

    assert third.texts == second.texts and third.state == second.state
    assert third.report.added == third.report.followed == third.report.review == []


def test_edits_are_kept_and_unedited_texts_follow_the_models():
    first = run({NAME: "Person", BIRTH: "Birth"})
    edited = {EN_NAME: "Person or group", DE_NAME: "Mensch"}

    second = again(first, {NAME: "Human", BIRTH: "Date of birth"}, edited)

    assert second.texts[EN_NAME] == "Person or group"  # (edited: kept)
    assert second.texts[EN_BIRTH] == "Date of birth"  # (not edited: follows)
    assert second.texts[DE_NAME] == "Mensch"
    assert set(second.report.review) == {
        EN_NAME,
        DE_NAME,
    }  # (both made from what changed)
    assert second.report.followed == [EN_BIRTH]


def test_a_new_language_is_added_without_touching_the_others():
    generated = {NAME: "Person"}
    first = run(generated)
    first.texts[DE_NAME] = "Mensch"

    done = reconcile(
        generated, ["en", "de", "fr"], "en", first.texts, {}, first.state, []
    )

    assert done.texts[DE_NAME] == "Mensch"
    assert done.texts[("models", "Person", "fr", "name")] == ""


def test_the_default_language_comes_first_wherever_the_settings_put_it():
    done = reconcile({NAME: "Person"}, ["de", "en"], "en", {}, {}, {}, [])
    assert [p[2] for p in done.texts] == ["en", "de"]


# --- names that have gone ---------------------------------------------------------------------


def test_what_was_written_for_a_name_that_is_gone_goes_to_obsolete_and_comes_back():
    first = run({NAME: "Person", BIRTH: "Birth"})
    translated = {**first.texts, DE_BIRTH: "Geburt"}

    # the field is no longer there
    second = run({NAME: "Person"}, translated, {}, first.state)
    assert second.obsolete == {DE_BIRTH: "Geburt"}
    assert (
        EN_BIRTH not in second.texts and EN_BIRTH not in second.obsolete
    )  # (never edited)

    # and is there again: what was written is back
    third = again(second, {NAME: "Person", BIRTH: "Birth"})
    assert third.texts[DE_BIRTH] == "Geburt" and third.obsolete == {}


def test_an_edit_in_the_default_language_is_obsolete_too_but_an_unedited_text_is_dropped():
    first = run({NAME: "Person", BIRTH: "Birth"})
    translated = {**first.texts, EN_BIRTH: "Date of birth"}

    done = run({NAME: "Person"}, translated, {}, first.state)

    assert done.obsolete == {EN_BIRTH: "Date of birth"}


def test_prune_removes_obsolete():
    first = run({NAME: "Person", BIRTH: "Birth"})
    translated = {**first.texts, DE_BIRTH: "Geburt"}

    done = run({NAME: "Person"}, translated, {}, first.state, prune=True)

    assert done.obsolete == {} and done.report.pruned == [DE_BIRTH]
    assert DE_BIRTH not in done.state


def test_a_language_taken_out_of_the_settings_is_obsolete_not_deleted():
    first = run({NAME: "Person"})
    first.texts[DE_NAME] = "Mensch"

    done = reconcile({NAME: "Person"}, ["en"], "en", first.texts, {}, first.state, [])

    assert done.obsolete == {DE_NAME: "Mensch"}


# --- renames -----------------------------------------------------------------------------------


def test_the_path_after_the_renames_in_the_order_they_happened():
    renames = [
        ItemRename(("models", "Person"), ("models", "Human")),
        ItemRename(
            ("models", "Human", "fields", "birth"),
            ("models", "Human", "fields", "born"),
        ),
    ]
    assert renamed(DE_BIRTH, renames) == (
        "models",
        "Human",
        "de",
        "fields",
        "born",
        "name",
    )
    assert renamed(DE_NAME, renames) == ("models", "Human", "de", "name")
    assert renamed(("models", "Other", "de", "name"), renames) == (
        "models",
        "Other",
        "de",
        "name",
    )


def test_a_rename_that_a_migration_records_carries_the_text_and_its_review_to_the_new_name():
    first = run({NAME: "Person", BIRTH: "Birth"})
    translated = {**first.texts, DE_BIRTH: "Geburt", EN_NAME: "Person or group"}
    new_birth = ("models", "Person", "fields", "born")
    rename = ItemRename(("models", "Person", "fields", "birth"), new_birth)

    done = run(
        {NAME: "Person", (*new_birth, "name"): "Birth"},
        translated,
        {},
        first.state,
        [rename],
    )

    assert done.texts[("models", "Person", "de", "fields", "born", "name")] == "Geburt"
    assert done.texts[EN_NAME] == "Person or group"
    assert done.obsolete == {}


def test_a_rename_recorded_later_finds_what_was_put_in_obsolete():
    first = run({NAME: "Person", BIRTH: "Birth"})
    translated = {**first.texts, DE_BIRTH: "Geburt"}
    born = ("models", "Person", "fields", "born")
    after_the_change = {NAME: "Person", (*born, "name"): "Birth"}

    # no migration yet: the old name is put aside
    second = run(after_the_change, translated, {}, first.state)
    assert second.obsolete == {DE_BIRTH: "Geburt"}
    assert second.texts[("models", "Person", "de", "fields", "born", "name")] == ""

    # `makemigrations` records the rename: the next run moves it
    third = again(
        second,
        after_the_change,
        renames=[ItemRename(("models", "Person", "fields", "birth"), born)],
    )
    assert third.texts[("models", "Person", "de", "fields", "born", "name")] == "Geburt"
    assert third.obsolete == {}


def test_a_rename_does_not_overwrite_text_the_new_name_already_has():
    first = run({NAME: "Person", BIRTH: "Birth"})
    born = ("models", "Person", "fields", "born")
    has_both = {
        **first.texts,
        DE_BIRTH: "Geburt",
        ("models", "Person", "de", "fields", "born", "name"): "Geboren",
    }

    done = run(
        {NAME: "Person", (*born, "name"): "Born"},
        has_both,
        {},
        first.state,
        [ItemRename(("models", "Person", "fields", "birth"), born)],
    )

    assert done.texts[("models", "Person", "de", "fields", "born", "name")] == "Geboren"
    assert done.obsolete == {DE_BIRTH: "Geburt"}


def test_a_translation_with_no_memory_of_it_is_still_put_aside_when_its_name_has_gone():
    current = {EN_NAME: "Person", DE_NAME: "Mensch", DE_BIRTH: "Geburt"}

    done = run({NAME: "Person"}, current, {}, {})

    assert done.obsolete == {DE_BIRTH: "Geburt"}


def test_a_wildcard_in_a_rename_matches_any_model_and_keeps_it():
    rename = ItemRename(
        ("models", "*", "incoming", "carried_out"),
        ("models", "*", "incoming", "did"),
    )
    assert renamed(
        ("models", "Person", "de", "incoming", "carried_out", "name"), [rename]
    ) == (
        "models",
        "Person",
        "de",
        "incoming",
        "did",
        "name",
    )
    assert renamed(
        ("models", "Group", "en", "incoming", "carried_out", "help"), [rename]
    ) == (
        "models",
        "Group",
        "en",
        "incoming",
        "did",
        "help",
    )
    # not another name, nor another kind of item
    other = ("models", "Person", "de", "incoming", "gave", "name")
    assert renamed(other, [rename]) == other
    fields = ("models", "Person", "de", "fields", "carried_out", "name")
    assert renamed(fields, [rename]) == fields


def test_a_changed_reverse_name_carries_the_text_of_the_incoming_relation():
    old = ("models", "Person", "incoming", "carried_out")
    new = ("models", "Person", "incoming", "did")
    first = run({(*old, "name"): "Carried out"})
    translated = {
        **first.texts,
        ("models", "Person", "de", "incoming", "carried_out", "name"): "Ausgeführt",
    }

    done = run(
        {(*new, "name"): "Did"},
        translated,
        {},
        first.state,
        [
            ItemRename(
                ("models", "*", "incoming", "carried_out"),
                ("models", "*", "incoming", "did"),
            )
        ],
    )

    assert (
        done.texts[("models", "Person", "de", "incoming", "did", "name")]
        == "Ausgeführt"
    )
    assert done.obsolete == {}
