from pangloss_lsp.context import (
    bases_of,
    call_at,
    class_body_word,
    enclosing_class,
    field_of_statement,
    fields_declared_in,
)

# (`|` is the cursor)


def at(source: str):
    offset = source.index("|")
    return call_at(source.replace("|", "", 1), offset), source.replace("|", "", 1)


def test_at_the_start_of_the_arguments_a_name_is_wanted():
    ctx, _ = at("_meta = Document.Meta(|")
    assert ctx is not None
    assert ctx.callee == "Document.Meta"
    assert ctx.at_name and ctx.keyword is None


def test_a_partly_typed_name_is_the_prefix():
    ctx, text = at("_meta = Document.Meta(abs|")
    assert ctx is not None and ctx.at_name
    assert text[ctx.prefix_start :] == "abs"


def test_after_a_comma_a_name_is_wanted_again_and_the_given_ones_are_known():
    ctx, _ = at("_meta = Document.Meta(abstract=True, indexes=['a'], |)")
    assert ctx is not None and ctx.at_name
    assert ctx.used == {"abstract", "indexes"}


def test_a_given_name_is_not_among_those_used_while_it_is_being_retyped():
    ctx, _ = at("Meta(abstract=True, ind|exes=['a'])")
    assert ctx is not None
    assert ctx.used == {"abstract"}


def test_after_an_equals_sign_the_value_of_that_keyword_is_wanted():
    ctx, _ = at("Document.Meta(indexes=|")
    assert ctx is not None
    assert ctx.keyword == "indexes" and not ctx.at_name and not ctx.nested


def test_inside_a_list_the_keyword_is_still_that_of_the_argument():
    ctx, _ = at("Document.Meta(indexes=['year', |")
    assert ctx is not None
    assert ctx.keyword == "indexes" and ctx.nested and not ctx.at_name


def test_inside_a_string_the_prefix_is_what_is_inside_the_quotes():
    ctx, text = at("Document.Meta(indexes=['ye|")
    assert ctx is not None and ctx.in_string
    assert text[ctx.prefix_start :] == "ye"


def test_a_call_inside_an_annotation_is_the_innermost_call():
    ctx, _ = at("born_in: Annotated[list[Place], RelationConfig(reverse_name=|")
    assert ctx is not None
    assert ctx.callee == "RelationConfig" and ctx.keyword == "reverse_name"
    assert ctx.statement_line == 0


def test_a_comparison_is_not_a_keyword():
    ctx, _ = at("f(a == |")
    assert ctx is not None and ctx.keyword is None


def test_a_comma_in_a_string_does_not_start_an_argument():
    ctx, _ = at("Meta(nav_section='a, b', abstract=|")
    assert ctx is not None and ctx.keyword == "abstract"


def test_a_comment_is_no_place_for_anything():
    ctx, _ = at("Meta(abstract=True,  # indexes=|")
    assert ctx is None


def test_a_parenthesis_that_is_not_a_call_is_not_one():
    ctx, _ = at("x = (|")
    assert ctx is None
    ctx, _ = at("if (|")
    assert ctx is None


def test_nothing_open_is_no_call():
    ctx, _ = at("class Person(Entity):\n    name: str|")
    assert ctx is None


def test_the_text_after_the_cursor_that_does_not_close_the_call_is_read_safely():
    ctx, _ = at("Meta(|\n\nclass Other:\n    pass\n")
    assert ctx is not None and ctx.at_name


CLASS = """\
import x


class Person(Entity):
    name: str
    born: Date
    _meta = Document.Meta(
        indexes=[
    )

    def method(self): ...


class Other(Document):
    title: str
"""


def test_the_class_of_a_statement_is_the_one_whose_body_holds_it():
    lines = CLASS.splitlines()
    assert enclosing_class(lines, 6) == ("Person", 3)
    assert enclosing_class(lines, 14) == ("Other", 13)
    assert enclosing_class(lines, 0) is None


def test_the_fields_typed_in_a_class_are_found_even_when_the_file_does_not_parse():
    lines = CLASS.splitlines()
    assert fields_declared_in(lines, 3) == ["name", "born"]
    assert fields_declared_in(lines, 13) == ["title"]


def test_the_field_a_statement_declares():
    assert field_of_statement(["    born_in: Annotated["], 0) == "born_in"
    assert field_of_statement(["    _meta = Document.Meta("], 0) is None


def test_the_bases_of_a_class():
    assert bases_of(["class Person(Entity, Dateable):"], 0) == ["Entity", "Dateable"]
    assert bases_of(["class Negative[T](SemanticSpace[T]):"], 0) == ["SemanticSpace"]
    assert bases_of(["class Plain:"], 0) == []


def test_a_word_that_begins_a_line_of_a_body():
    source = "class A(Entity):\n    _int"
    assert class_body_word(source, len(source)) == (21, "_int")
    assert class_body_word("x = _in", 7) is None
    assert class_body_word("class A:\n    f(_in", len("class A:\n    f(_in")) is None
