"""Text as it is searched: lower case, with accents folded, so that `zurich` finds "Zürich" and `strasse` finds "Straße".

Each backend searches labels in this form: Neo4j's full-text index folds them itself (its `standard-folding` analyzer),
and Memgraph's text index is on `label_folded`, which is written as `fold(label)`. The words of a search are folded here,
in the same way, before they are looked for."""

import unicodedata

# What does not decompose into a letter and an accent (Lucene's ASCII folding folds these too)
FOLDED = str.maketrans(
    {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ð": "d", "đ": "d", "ł": "l", "þ": "th"}
)


def fold(text: str) -> str:
    """The text as the index holds it: lower case, accents folded"""
    lowered = text.lower().translate(FOLDED)
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(c for c in decomposed if not unicodedata.combining(c))
