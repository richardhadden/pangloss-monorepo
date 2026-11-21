"""The whole of the computing of the name part, with no database in it: a name to a vector.

    name ──fold──▶ words ──canonical──▶ words ──weighted (rarity, trigrams)──▶ weights ──hashed──▶ vector

- **Folded**: lower case, accents folded (`pangloss_models.fold`, as labels are searched), and cut into words at
  whatever is neither a letter nor a digit. The words are a bag: "Smith, John" and "John Smith" are the same name.
- **Canonical**: a word that a table of variants knows (`Hans`) is replaced by its canonical form (`johannes`).
- **Trigrams**: each word between a start and an end mark, cut into threes (`^jo`, `joh`, `ohn`, `hn$`), so that
  two spellings of a name share most of theirs.
- **Weighted** by rarity: the trigrams of a word that few names have (a surname) count for more than those of a
  word that many have (a given name). Rarity is a count over every name, so it is made at a rebuild (`Rarity.of`)
  and kept with the vectors: a refresh and an overlay weigh by the table of the last rebuild, and a word it never
  saw is as rare as can be. (By the word and not by the trigram: measured, rarity by the trigram costs quality,
  since the trigrams that two spellings of a name do not share are the rare ones.)
- **Hashed** to a fixed dimension, each trigram to one place with a sign (the hashing trick), by a hash that is the
  same in every process (never `hash()`).

The cosine of two such vectors is high for a name and its other spellings and variants, and near nothing for two
different names. It finds candidates; it is not a comparison of two names (review's `likeness` is).
implementation_docs/similarity-build-plan.md, step 8.2.
"""

import dataclasses
import functools
import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping

import numpy as np
from pangloss_models import fold as fold_text

START, END = "^", "$"

# (letters and digits of any script; the underscore is no part of a name)
_WORD = re.compile(r"[^\W_]+")


def fold(name: str) -> list[str]:
    """The words of a name: lower case, accents folded, cut at whatever is neither a letter nor a digit"""
    return _WORD.findall(fold_text(name))


def canonical(words: Iterable[str], table: Mapping[str, str]) -> list[str]:
    """The words, each replaced by its canonical form where the table of variants (`variants_table`) knows it"""
    return [table.get(word, word) for word in words]


def variants_table(variants: Mapping[str, Iterable[str]]) -> dict[str, str]:
    """A table for `canonical` from canonical forms and their variants, all folded. A form of several words is not
    taken (a table is of single words). Raises `ValueError` for a variant of two canonical forms, or one that is
    itself a canonical form of another"""
    table: dict[str, str] = {}
    forms: dict[str, str] = {}
    for form in variants:
        words = fold(form)
        if len(words) != 1:
            raise ValueError(f"A canonical form is one word, not {form!r}")
        forms[form] = words[0]
    said = set(forms.values())
    for form, others in variants.items():
        for variant in others:
            words = fold(variant)
            if len(words) != 1:
                raise ValueError(
                    f"A variant is one word, not {variant!r} (of {form!r})"
                )
            word = words[0]
            if word == forms[form]:
                continue
            if word in said:
                raise ValueError(
                    f"{variant!r} is given as a variant of {form!r} and is itself a canonical form"
                )
            if table.get(word, forms[form]) != forms[form]:
                raise ValueError(
                    f"{variant!r} is a variant of two canonical forms: {table[word]!r} and {forms[form]!r}"
                )
            table[word] = forms[form]
    return table


def trigrams(word: str) -> list[str]:
    """The threes of a word between its start and end marks (`ann`: `^an`, `ann`, `nn$`); of the empty word, none"""
    if not word:
        return []
    marked = f"{START}{word}{END}"
    return [marked[at : at + 3] for at in range(len(marked) - 2)]


def words(names: Iterable[str], table: Mapping[str, str] | None = None) -> Counter[str]:
    """How often each word, in its canonical form, is in the names of one item (its label, and whatever other
    fields are names)"""
    found: Counter[str] = Counter()
    for name in names:
        found.update(canonical(fold(name), table or {}))
    return found


@dataclasses.dataclass(frozen=True)
class Rarity:
    """How many items had names when the table was made, and how many of them had each word (in its canonical
    form). A word only one item had is not kept: it weighs as one the table never saw, so the table is no longer
    than the words that are shared"""

    names: int = 0
    having: Mapping[str, int] = dataclasses.field(default_factory=dict)

    @classmethod
    def of(cls, items: Iterable[Iterable[str]]) -> Rarity:
        """From the words of each item (any iterable of them: a word counts once for an item)"""
        having: Counter[str] = Counter()
        names = 0
        for found in items:
            distinct = set(found)
            if not distinct:
                continue
            names += 1
            having.update(distinct)
        return cls(names, {word: n for word, n in sorted(having.items()) if n > 1})

    def weight(self, word: str) -> float:
        """`1 + ln((names + 1) / (having + 1))`: 1 for a word every name has, more the fewer have it, and the most
        for a word that one item has or none (a word the table never saw is as rare as can be)"""
        return 1.0 + math.log((self.names + 1) / (max(1, self.having.get(word, 0)) + 1))


def weighted(found: Mapping[str, int], rarity: Rarity) -> dict[str, float]:
    """The weight of each trigram of an item, from its words and how often it has each: every trigram of a word
    weighs as the word is rare (a surname few have counts for more than a given name many have)"""
    weights: dict[str, float] = {}
    for word, count in found.items():
        weight = count * rarity.weight(word)
        for gram in trigrams(word):
            weights[gram] = weights.get(gram, 0.0) + weight
    return weights


@functools.lru_cache(maxsize=1 << 18)
def place(gram: str, dimension: int) -> tuple[int, float]:
    """Where a trigram goes in a vector of the dimension, and with which sign: from a hash that is the same in any
    process and on any machine"""
    number = int.from_bytes(
        hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big"
    )
    return (number >> 1) % dimension, 1.0 if number & 1 else -1.0


def hashed(weights: Mapping[str, float], dimension: int) -> np.ndarray:
    """The vector of weighted trigrams: each added, with its sign, at its place"""
    vector = np.zeros(dimension, dtype=np.float64)
    for gram, weight in weights.items():
        at, sign = place(gram, dimension)
        vector[at] += sign * weight
    return vector


def vector(
    names: Iterable[str],
    rarity: Rarity,
    dimension: int,
    table: Mapping[str, str] | None = None,
) -> np.ndarray | None:
    """The vector of an item with these names, at length one; None if they hold no letter or digit (no vector), or
    if every trigram fell on another of the opposite sign (which a real name does not do)"""
    # (a plain string is one name, not its letters)
    names = [names] if isinstance(names, str) else names
    found = words(names, table)
    if not found:
        return None
    made = hashed(weighted(found, rarity), dimension)
    length = float(np.linalg.norm(made))
    if length == 0:
        return None
    return made / length
