"""The words of a search, as patterns for the full-text index (no database needed)"""

import pytest
from pangloss_neo4j.databases.neo4j.schema import fold, search_patterns


@pytest.mark.parametrize(
    "typed, patterns",
    [
        ("Maximilian", ["*maximilian*"]),
        ("Marie of Burgundy", ["*marie*", "*of*", "*burgundy*"]),
        ("  spaced   out ", ["*spaced*", "*out*"]),
        ("Zürich Café", ["*zurich*", "*cafe*"]),
        ("Straße Æther", ["*strasse*", "*aether*"]),
        ("max-planck", ["*max*", "*planck*"]),
        ("a(b", ["*a*", "*b*"]),
        ("snake_case", ["*snake_case*"]),
        (
            'what? *wild* [x] "quote" \\ / ~ ^ : && ||',
            ["*what*", "*wild*", "*x*", "*quote*"],
        ),
        ("", []),
        ("   ", []),
        ("()-*", []),
        (None, []),
    ],
)
def test_the_words_of_a_search_become_patterns_that_cannot_be_syntax(typed, patterns):
    assert search_patterns(typed) == patterns


def test_folding_is_what_the_index_does_to_a_label():
    assert fold("Zürich Café") == "zurich cafe"
    assert fold("Straße") == "strasse"
    assert fold("ÆØ Łódź") == "aeo lodz"
