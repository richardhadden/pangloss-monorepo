"""Each rule of the name part on its own (`pangloss_names.maths`; implementation_docs/similarity-build-plan.md, step
8.2): folding, the table of variants, trigrams, rarity, the weights and the hashing, from the module's docstrings.
No database."""

import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest
from pangloss_names import maths
from pangloss_names.maths import Rarity

DIMENSION = 1024


def cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    assert a is not None and b is not None
    return float(a @ b)


# -- fold -------------------------------------------------------------------------------------------------------------


def test_fold_lowers_the_case():
    assert maths.fold("JOHN Smith") == ["john", "smith"]


def test_fold_folds_accents():
    assert maths.fold("Zürich") == ["zurich"]
    assert maths.fold("Straße") == ["strasse"]
    assert maths.fold("Łukasz") == ["lukasz"]


def test_fold_cuts_at_punctuation_and_at_more_than_one_space():
    assert maths.fold("Smith,  John.   (Jr.)") == ["smith", "john", "jr"]


def test_a_hyphenated_name_is_two_words():
    assert maths.fold("Anne-Marie") == ["anne", "marie"]


def test_fold_keeps_digits():
    assert maths.fold("Louis XIV 14") == ["louis", "xiv", "14"]
    assert maths.fold("b2b") == ["b2b"]


def test_an_underscore_is_no_letter():
    assert maths.fold("john_smith") == ["john", "smith"]


def test_the_empty_string_and_punctuation_alone_give_no_words():
    assert maths.fold("") == []
    assert maths.fold(" .,;-_!? ") == []


# -- word order -------------------------------------------------------------------------------------------------------


def test_the_order_of_the_words_makes_no_difference_to_the_vector():
    rarity = Rarity.of([["john", "smith"], ["john", "brown"], ["ann", "smith"]])
    a = maths.vector(["Smith, John"], rarity, DIMENSION)
    b = maths.vector(["John Smith"], rarity, DIMENSION)
    assert a is not None and b is not None
    assert np.array_equal(a, b)


# -- canonical and variants_table -------------------------------------------------------------------------------------


def test_a_variant_is_replaced_by_its_canonical_form_and_another_word_is_not():
    table = maths.variants_table({"johannes": ["hans", "jan"]})
    assert maths.canonical(["hans", "mayer", "jan"], table) == [
        "johannes",
        "mayer",
        "johannes",
    ]


def test_the_table_of_variants_is_folded():
    table = maths.variants_table({"Georg": ["Jörg"]})
    assert table == {"jorg": "georg"}
    assert maths.canonical(maths.fold("JORG"), table) == ["georg"]


def test_a_variant_equal_to_its_own_canonical_form_is_no_entry():
    table = maths.variants_table({"Johannes": ["johannes", "JOHANNES", "Hans"]})
    assert table == {"hans": "johannes"}


def test_a_variant_of_two_canonical_forms_is_refused():
    with pytest.raises(ValueError):
        maths.variants_table({"johannes": ["hans"], "hannes": ["Hans"]})


def test_a_variant_that_is_itself_the_canonical_form_of_another_is_refused():
    with pytest.raises(ValueError):
        maths.variants_table({"johannes": ["hans"], "hans": ["hansi"]})
    # (whichever comes first)
    with pytest.raises(ValueError):
        maths.variants_table({"hans": ["hansi"], "johannes": ["hans"]})


def test_a_canonical_form_of_two_words_is_refused():
    with pytest.raises(ValueError):
        maths.variants_table({"Anne Marie": ["annemarie"]})


def test_a_variant_of_two_words_is_refused():
    with pytest.raises(ValueError):
        maths.variants_table({"annemarie": ["Anne-Marie"]})


# -- trigrams ---------------------------------------------------------------------------------------------------------


def test_the_trigrams_of_a_word_are_between_its_start_and_end_marks():
    assert maths.trigrams("ann") == ["^an", "ann", "nn$"]


def test_a_word_of_one_letter_gives_one_trigram():
    assert maths.trigrams("a") == ["^a$"]


def test_the_empty_word_gives_no_trigrams():
    assert maths.trigrams("") == []


# -- words ------------------------------------------------------------------------------------------------------------


def test_words_counts_across_the_names_of_one_item():
    assert maths.words(["John Smith", "Smith, J.", "Johnny"]) == {
        "john": 1,
        "smith": 2,
        "j": 1,
        "johnny": 1,
    }


def test_with_the_table_the_canonical_form_is_what_is_counted():
    table = maths.variants_table({"johannes": ["hans", "jan"]})
    assert maths.words(["Hans Mayer", "Johannes Mayer", "Jan"], table) == {
        "johannes": 3,
        "mayer": 2,
    }


# -- Rarity -----------------------------------------------------------------------------------------------------------


def test_rarity_counts_an_item_once_for_a_word_however_often_it_has_it():
    rarity = Rarity.of([["smith", "smith", "smith"], ["smith"]])
    assert rarity.names == 2
    assert rarity.having == {"smith": 2}


def test_rarity_takes_a_counter_of_words_as_the_words_of_an_item():
    rarity = Rarity.of([maths.words(["Smith Smith", "Smith"]), maths.words(["Smith"])])
    assert rarity.having == {"smith": 2}


def test_an_item_with_no_words_is_not_counted_among_the_names():
    rarity = Rarity.of([[], ["ann", "smith"], maths.words(["!!"]), ["ann"]])
    assert rarity.names == 2


def test_a_word_only_one_item_has_is_not_kept():
    rarity = Rarity.of([["ann", "smith"], ["ann", "brown"]])
    assert rarity.having == {"ann": 2}


def test_a_word_every_item_has_weighs_one():
    rarity = Rarity.of([["ann", "smith"], ["ann", "brown"], ["ann", "jones"]])
    assert rarity.weight("ann") == pytest.approx(1.0)


def test_a_word_weighs_the_more_the_fewer_items_have_it():
    rarity = Rarity.of(
        [
            ["ann", "smith", "x"],
            ["ann", "smith", "x"],
            ["ann", "brown"],
            ["ann", "brown"],
        ]
        + [["ann", "smith"]] * 2
    )
    # ann: 6 of 6, smith: 4, brown: 2
    assert rarity.weight("ann") < rarity.weight("smith") < rarity.weight("brown")
    assert rarity.weight("x") == rarity.weight("brown")


def test_a_word_one_item_has_weighs_as_one_none_has_and_one_never_seen():
    rarity = Rarity.of([["ann", "smith"], ["ann", "brown"], ["bob", "brown"]])
    once = rarity.weight("smith")
    assert once == rarity.weight("bob")
    assert once == rarity.weight("zebedee")
    assert once > rarity.weight("brown") > 1.0
    # (the most a word can weigh)
    assert once == pytest.approx(1 + math.log((3 + 1) / 2))


def test_an_empty_rarity_weighs_every_word_the_same():
    assert Rarity().weight("johannes") == Rarity().weight("mayer")


# -- weighted ---------------------------------------------------------------------------------------------------------


def test_every_trigram_of_a_word_carries_the_weight_of_the_word():
    rarity = Rarity.of([["ann", "mayer"], ["ann", "mayer"], ["ann", "smith"]])
    weights = maths.weighted({"mayer": 1}, rarity)
    assert set(weights) == set(maths.trigrams("mayer"))
    assert all(
        weight == pytest.approx(rarity.weight("mayer")) for weight in weights.values()
    )


def test_a_trigram_two_words_of_an_item_share_carries_both_weights():
    rarity = Rarity.of([["anna", "x"], ["anna", "x"], ["anna", "y"], ["y"]])
    weights = maths.weighted({"anna": 1, "hanna": 1}, rarity)
    both = rarity.weight("anna") + rarity.weight("hanna")
    for gram in ("ann", "nna", "na$"):
        assert weights[gram] == pytest.approx(both)
    assert weights["^an"] == pytest.approx(rarity.weight("anna"))
    assert weights["^ha"] == pytest.approx(rarity.weight("hanna"))


# -- nearness ---------------------------------------------------------------------------------------------------------


def test_a_name_and_its_variant_spelling_are_nearer_than_two_different_names():
    rarity = Rarity()
    name = maths.vector("Johannes Mayer", rarity, DIMENSION)
    spelling = maths.vector("Johannes Maier", rarity, DIMENSION)
    other = maths.vector("Wilhelm Schuster", rarity, DIMENSION)
    assert cosine(name, spelling) > 0.5
    assert cosine(name, other) < 0.2
    assert cosine(name, spelling) > cosine(name, other)


def test_with_the_table_a_name_and_its_variant_are_the_same_vector():
    table = maths.variants_table({"johannes": ["hans"]})
    rarity = Rarity.of(
        maths.words([name], table)
        for name in ["Hans Mayer", "Johannes Mayer", "Johannes Huber"]
    )
    a = maths.vector("Hans Mayer", rarity, DIMENSION, table)
    b = maths.vector("Johannes Mayer", rarity, DIMENSION, table)
    assert a is not None and b is not None
    assert np.array_equal(a, b)
    # (and without the table they are not)
    assert not np.array_equal(
        maths.vector("Hans Mayer", rarity, DIMENSION),
        maths.vector("Johannes Mayer", rarity, DIMENSION),
    )


SURNAMES = ["mayer", "schuster", "huber", "wagner", "bauer", "fischer", "weber", "koch"]
# `johannes` in most names, each surname in a few
POPULATION = [f"Johannes {s.title()}" for s in SURNAMES for _ in range(2)] + [
    "Wilhelm Mayer",
    "Wilhelm Schuster",
]


def test_a_rare_name_outweighs_a_common_one():
    rarity = Rarity.of(maths.words([name]) for name in POPULATION)
    assert rarity.weight("mayer") > rarity.weight("johannes")
    name = maths.vector("Johannes Mayer", rarity, DIMENSION)
    assert cosine(name, maths.vector("Wilhelm Mayer", rarity, DIMENSION)) > cosine(
        name, maths.vector("Johannes Schuster", rarity, DIMENSION)
    )


def test_with_a_rarity_that_knows_nothing_the_rare_name_does_not_outweigh_the_common():
    rarity = Rarity()
    name = maths.vector("Johannes Mayer", rarity, DIMENSION)
    assert cosine(name, maths.vector("Wilhelm Mayer", rarity, DIMENSION)) <= cosine(
        name, maths.vector("Johannes Schuster", rarity, DIMENSION)
    )


# -- hashing ----------------------------------------------------------------------------------------------------------


def test_the_place_of_a_trigram_is_fixed():
    # (computed once on 2026-11-21 and written in: a change of hash moves every vector ever stored)
    assert maths.place("^jo", 256) == (168, 1.0)
    assert maths.place("joh", 256) == (164, -1.0)
    assert maths.place("ohn", 256) == (37, 1.0)
    assert maths.place("hn$", 256) == (201, 1.0)
    assert maths.place("^jo", 1024) == (680, 1.0)
    assert maths.place("hn$", 1024) == (969, 1.0)


def test_another_process_with_another_hash_seed_gives_the_same_vector():
    script = (
        "import json; from pangloss_names import maths; "
        "print(json.dumps(maths.vector('Johannes Mayer', maths.Rarity(), 256).tolist()))"
    )
    vectors = [
        json.loads(
            subprocess.run(
                [sys.executable, "-c", script],
                env={**os.environ, "PYTHONHASHSEED": seed},
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        for seed in ("1", "12345")
    ]
    here = maths.vector("Johannes Mayer", Rarity(), 256)
    assert here is not None
    assert vectors[0] == vectors[1] == here.tolist()


def test_both_signs_are_used():
    signs = {maths.place(gram, 256)[1] for gram in maths.trigrams("johannesmayer")}
    assert signs == {1.0, -1.0}


def test_the_hashed_vector_has_the_dimension_asked():
    weights = maths.weighted(maths.words(["Johannes Mayer"]), Rarity())
    for dimension in (1, 7, 64, 256):
        assert maths.hashed(weights, dimension).shape == (dimension,)


def colliding(dimension: int, same_sign: bool) -> tuple[str, str]:
    """Two trigrams at one place of the dimension, with the same or opposite signs"""
    seen: dict[tuple[int, float], str] = {}
    for a in "abcdefghij":
        for b in "abcdefghij":
            gram = f"^{a}{b}"
            at, sign = maths.place(gram, dimension)
            other = seen.get((at, sign if same_sign else -sign))
            if other is not None:
                return other, gram
            seen.setdefault((at, sign), gram)
    raise AssertionError("no two trigrams collide")


def test_two_trigrams_at_one_place_with_one_sign_add():
    one, two = colliding(8, same_sign=True)
    at, sign = maths.place(one, 8)
    vector = maths.hashed({one: 1.5, two: 2.0}, 8)
    assert vector[at] == pytest.approx(sign * 3.5)
    assert np.count_nonzero(vector) == 1


def test_two_trigrams_at_one_place_with_opposite_signs_cancel():
    one, two = colliding(8, same_sign=False)
    at, sign = maths.place(one, 8)
    assert maths.hashed({one: 1.5, two: 2.0}, 8)[at] == pytest.approx(sign * -0.5)
    assert not maths.hashed({one: 2.0, two: 2.0}, 8).any()


# -- vector -----------------------------------------------------------------------------------------------------------


def test_a_vector_is_at_length_one():
    rarity = Rarity.of(maths.words([name]) for name in POPULATION)
    for names in (["Johannes Mayer"], ["J. Mayer", "Hans Mayer, called Jack"], "Ann"):
        made = maths.vector(names, rarity, DIMENSION)
        assert made is not None
        assert float(np.linalg.norm(made)) == pytest.approx(1.0)


def test_there_is_no_vector_for_an_empty_name_punctuation_alone_or_no_names():
    assert maths.vector([""], Rarity(), DIMENSION) is None
    assert maths.vector("", Rarity(), DIMENSION) is None
    assert maths.vector(["-- !! ,"], Rarity(), DIMENSION) is None
    assert maths.vector([], Rarity(), DIMENSION) is None


def test_a_plain_string_is_one_name_and_not_its_letters():
    as_string = maths.vector("Anna", Rarity(), DIMENSION)
    as_name = maths.vector(["Anna"], Rarity(), DIMENSION)
    as_letters = maths.vector(["A", "n", "n", "a"], Rarity(), DIMENSION)
    assert as_string is not None and as_name is not None and as_letters is not None
    assert np.array_equal(as_string, as_name)
    assert not np.allclose(as_string, as_letters)
