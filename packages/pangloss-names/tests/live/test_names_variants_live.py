"""The table of name variants on the backend under test (implementation_docs/similarity-build-plan.md, step 8.5): a
variant and its canonical form have the same name vector, and a changed table makes a rebuild due for the name part
alone"""

from typing import no_type_check

import numpy as np
import pangloss_core.settings as core_settings
import pytest
from pangloss_names import settings, vector_of
from pangloss_names.part import NAME
from pangloss_testing.parts import drop_vector_indexes, one_turn, stored

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@pytest.fixture
def table(tmp_path, monkeypatch):
    """A table of variants in the settings: the path of its file, to be written again by a test"""
    path = tmp_path / "variants.csv"
    path.write_text("# given names\nJohannes,Johann,Hans,Jan\n", encoding="utf-8")
    monkeypatch.setattr(core_settings.SETTINGS, "NAMES_VARIANTS", str(path))
    settings.forget()
    yield path
    settings.forget()


def cosine(a, b) -> float:
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


@no_type_check
async def built(database):
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare()
    hans = await m.Person.Create(label="Hans Mayer").save()
    other = await m.Person.Create(label="Peter Mayer").save()
    await rebuild()
    await one_turn(database)
    return m, str(hans.id), str(other.id)


@no_type_check
async def test_with_a_table_a_variant_and_its_canonical_form_are_at_cosine_1(
    database, table
):
    _, hans, other = await built(database)
    have = await stored(database, NAME)
    assert cosine(have[hans], await vector_of("Johannes Mayer")) == pytest.approx(1)
    assert cosine(have[hans], await vector_of("Jan Mayer")) == pytest.approx(1)
    assert cosine(have[other], await vector_of("Johannes Mayer")) < 0.9


@no_type_check
async def test_without_the_table_they_are_not(database):
    _, hans, _ = await built(database)
    have = await stored(database, NAME)
    assert cosine(have[hans], await vector_of("Johannes Mayer")) < 0.9


@no_type_check
async def test_a_changed_table_makes_a_rebuild_due_for_the_name_part_alone(
    database, table
):
    from pangloss_vectors.status import status

    await built(database)
    before = await status()
    assert not before.rebuild_due, before

    table.write_text("Johannes,Johann,Hans\n", encoding="utf-8")
    settings.forget()
    after = await status()
    due = {p.part: p.reasons for p in after.parts}
    assert [reason.split(",")[0] for reason in due[NAME]] == [
        f"its signature is now {next(p.signature for p in after.parts if p.part == NAME)}"
    ]
    assert {part: reasons for part, reasons in due.items() if part != NAME} == {
        part: () for part in due if part != NAME
    }
    # (and of the profiles, only those that weigh it)
    profiles = {p.profile: p.rebuild_due for p in after.profiles}
    assert profiles == {"default": False, "who": True}

    # (a comment added to the table as it was makes nothing due)
    table.write_text(
        "# given names\nJohannes,Johann,Hans,Jan\n# more to come\n", encoding="utf-8"
    )
    settings.forget()
    assert not (await status()).rebuild_due
