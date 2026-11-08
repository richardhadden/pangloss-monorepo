from pangloss_lsp.describe import model_markdown

PERSON = {
    "kind": "Entity",
    "abstract": False,
    "doc": "Someone in the sources.",
    "indexes": ["name"],
    "above": ["Agent", "Dateable"],
    "fields": {"name": "literal", "born_in": "relation", "friends": "relation"},
}


def reference(label: str, via: str | None = None) -> dict:
    return {"label": label, "via": via}


def test_a_model_is_described_by_its_kind_docstring_and_neighbours():
    text = model_markdown("Person", PERSON, [reference("Statement.about", "Agent")])

    assert text.startswith("**Person**: entity\n\nSomeone in the sources.")
    assert "Above it: `Agent`, `Dateable`" in text
    assert "Indexed: `name`" in text
    assert "3 fields, 2 of them relations" in text
    assert "Can be held by 1 field: `Statement.about` (as a `Agent`)" in text


def test_a_model_that_nothing_points_at_says_so():
    assert model_markdown("Person", PERSON, []).endswith(
        "No relation field can hold it."
    )


def test_a_long_list_of_references_is_cut_short():
    references = [reference(f"A.f{n}") for n in range(9)]
    text = model_markdown("Person", PERSON, references)

    assert "Can be held by 9 fields: `A.f0`" in text
    assert "`A.f5`, and 3 more (find references lists them)" in text
    assert "A.f6" not in text


def test_a_model_with_nothing_to_say_is_still_named():
    text = model_markdown("Place", {"kind": "Entity", "abstract": True}, [])

    assert text.startswith("**Place**: abstract entity")
    assert "fields" not in text and "Indexed" not in text and "Above" not in text
