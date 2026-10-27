"""JSONC: reading with comments, and writing in one form."""

import json

import pytest
from pangloss_interface.i18n import jsonc


def test_comments_are_taken_out_and_the_rest_is_read():
    text = """
    // the top
    {
      "a": 1, // after a value
      /* a block
         over lines */
      "b": [1, /* in a list */ 2]
    }
    """
    assert jsonc.loads(text) == {"a": 1, "b": [1, 2]}


def test_comment_marks_inside_a_string_are_text():
    text = r'{"url": "https://example.org/a//b", "c": "/* not */ a comment", "q": "a \" // b"}'
    assert jsonc.loads(text) == {
        "url": "https://example.org/a//b",
        "c": "/* not */ a comment",
        "q": 'a " // b',
    }


def test_the_text_keeps_its_lines_so_that_an_error_is_where_it_is():
    text = '{\n  // one\n  "a": 1,\n  /* two\n  three */\n  "b": nope\n}'
    assert strip_lines(text) == text.count("\n")
    with pytest.raises(jsonc.JsoncError, match="line 6"):
        jsonc.loads(text)


def strip_lines(text: str) -> int:
    return jsonc.strip_comments(text).count("\n")


def test_a_comment_that_is_not_closed_is_an_error():
    with pytest.raises(jsonc.JsoncError, match="not closed"):
        jsonc.loads('{"a": 1} /* never ends')


def test_a_trailing_comma_is_not_accepted():
    with pytest.raises(jsonc.JsoncError):
        jsonc.loads('{"a": 1,}')


def test_render_writes_the_form_with_comments_above_keys_and_reads_back():
    data = {
        "models": {"Person": {"de": {"name": "Größe ö", "plural": ""}}},
        "empty": {},
    }
    comments = {("models", "Person", "de", "name"): ["en: Size", "NEEDS REVIEW"]}

    text = jsonc.render(data, comments, header=["A header"])

    assert text.startswith("// A header\n{")
    assert (
        '        // en: Size\n        // NEEDS REVIEW\n        "name": "Größe ö",'
        in text
    )
    assert "Gr\\u" not in text  # (not escaped)
    assert '"empty": {}' in text
    assert jsonc.loads(text) == data
    assert json.loads(jsonc.strip_comments(text)) == data


def test_a_comment_with_slashes_in_it_is_still_a_comment_when_read():
    text = jsonc.render({"a": "x"}, {("a",): ["see https://example.org // here"]})
    assert jsonc.loads(text) == {"a": "x"}
