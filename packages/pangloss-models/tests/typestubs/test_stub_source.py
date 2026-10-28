"""The parts of `typestubs` that write a stub: how types are written, and what is kept of the source"""

import ast
import collections.abc
import enum
import types
import typing

import pytest
from pangloss_models.typestubs import (
    Stubifier,
    TypeRenderer,
    insert_source,
    is_in_environment,
    module_source_path,
    stub_path,
)

T = typing.TypeVar("T")


class Colour(enum.Enum):
    RED = "red"


def renderer(names=None) -> TypeRenderer:
    return TypeRenderer("here", names or {})


# --- types ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("annotation", "written"),
    [
        (None, "None"),
        (type(None), "None"),
        (int, "int"),
        (typing.Any, "typing.Any"),
        (T, "typing.Any"),
        (Ellipsis, "..."),
        (int | None, "int | None"),
        (typing.Optional[str], "str | None"),
        (list[int], "list[int]"),
        (dict[str, list[int]], "dict[str, list[int]]"),
        (tuple[int, ...], "tuple[int, ...]"),
        (typing.Annotated[int, "metadata"], "int"),
        (typing.Literal["a", 1], "typing.Literal['a', 1]"),
        # a list of arguments cannot be written
        (collections.abc.Callable[[int], str], "typing.Any"),
        # what is not found where it says it is cannot be named
        (list[type("Made", (), {})], "typing.Any"),
        (42, "typing.Any"),
    ],
)
def test_types_are_written_as_annotations(annotation, written):
    assert renderer().render(annotation) == written


def test_an_enum_member_in_a_literal_is_written_by_name_and_noted_as_an_import():
    rendered = TypeRenderer("here", {Colour: ("elsewhere", "Colour")})
    assert (
        rendered.render(typing.Literal[Colour.RED])
        == "typing.Literal[elsewhere.Colour.RED]"
    )
    assert "elsewhere" in rendered.imports

    # (one that cannot be named is not written)
    class Local(enum.Enum):
        A = 1

    assert renderer().render(typing.Literal[Local.A]) == "typing.Any"


def test_a_class_of_the_module_itself_is_not_imported():
    rendered = TypeRenderer("here", {Colour: ("here", "Colour")})
    assert rendered.render(Colour) == "Colour"
    assert rendered.imports == {"typing"}


def test_a_generic_alias_of_a_class_made_at_run_time_is_any():
    assert (
        renderer().render(types.GenericAlias(type("Made", (), {}), (int,)))
        == "typing.Any"
    )


def test_the_bases_of_a_class_that_cannot_be_named_are_replaced_by_its_ancestors():
    class Parent:
        pass

    class Made(Parent):
        pass

    rendered = TypeRenderer("here", {Parent: ("here", "Parent")})
    assert rendered.base_names(Made) == ["Parent"]


def test_a_class_with_no_nameable_base_is_a_base_model():
    class Made:
        pass

    rendered = renderer()
    assert rendered.base_names(Made) == ["pydantic.BaseModel"]
    assert "import pydantic" in rendered.import_lines()


# --- the source of a module ----------------------------------------------------------------------


def stubbed(source: str) -> str:
    stubifier = Stubifier(renderer(), {})
    tree = ast.parse(source)
    return ast.unparse(ast.fix_missing_locations(stubifier.module(tree)))


def test_function_bodies_are_dropped_and_annotated_values_kept_only_if_they_say_something():
    stub = stubbed(
        """
import os
from typing import TypeVar

T = TypeVar("T")
ALIAS = int | None
TIMEOUT = 30

def work(a: int) -> int:
    return a + 1

async def later():
    await something()

class Config:
    name: str = "x"
    size: int = compute()
    field: int = Field(default=3)
    COLOUR = "red"
    other = compute()
    a, b = 1, 2

    def method(self):
        return 1
"""
    )
    assert "import os" in stub
    assert "T = TypeVar('T')" in stub
    assert "ALIAS = int | None" in stub
    assert "TIMEOUT = 30" in stub
    assert "return" not in stub and "await" not in stub
    assert "def work(a: int) -> int:\n    ..." in stub
    assert "async def later():\n    ..." in stub
    assert "name: str = 'x'" in stub
    assert "size: int = ..." in stub
    assert "field: int = Field(default=3)" in stub
    assert "COLOUR = 'red'" in stub
    assert "other = ..." in stub
    assert "a, b" not in stub


def test_conditions_and_alternative_imports_are_kept_as_they_are():
    stub = stubbed(
        """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a import B
else:
    B = None

try:
    import fast
except ImportError:
    import slow
else:
    import extra

print("not a declaration")
x.y = 1
"""
    )
    assert "if TYPE_CHECKING:\n    from a import B" in stub
    assert "import fast" in stub and "import slow" in stub and "import extra" in stub
    assert "print" not in stub
    assert "x.y" not in stub


def test_an_if_with_nothing_to_keep_is_given_an_ellipsis():
    assert "if flag:\n    ..." in stubbed("if flag:\n    print(1)\n")


def test_a_class_with_nothing_in_it_has_an_ellipsis():
    assert "class Empty:\n    ..." in stubbed("class Empty:\n    pass\n")


def test_source_is_put_in_place_of_a_line_that_is_only_its_placeholder():
    code = "class A:\n    x: int\n    __here__\n    y: int"
    assert insert_source(code, "__here__", "def f(): ...\n\nz: str") == (
        "class A:\n    x: int\n    def f(): ...\n\n    z: str\n    y: int"
    )
    with pytest.raises(ValueError, match="No place"):
        insert_source(code, "__nowhere__", "x")


def test_a_module_with_no_python_source_has_no_stub(tmp_path):
    module = types.ModuleType("nowhere")
    with pytest.raises(ValueError, match="no Python source"):
        module_source_path(module)
    module.__file__ = str(tmp_path / "compiled.so")
    with pytest.raises(ValueError, match="no Python source"):
        stub_path(module)
    module.__file__ = str(tmp_path / "real.py")
    assert stub_path(module) == tmp_path / "real.pyi"


def test_no_stub_is_written_in_an_environment(tmp_path):
    (tmp_path / "project" / "pkg").mkdir(parents=True)
    (tmp_path / "project" / ".venv" / "lib" / "site-packages" / "lib").mkdir(
        parents=True
    )
    (tmp_path / "project" / "venv2").mkdir()
    (tmp_path / "project" / "venv2" / "pyvenv.cfg").write_text("")
    root = tmp_path / "project"
    assert not is_in_environment(root, root / "pkg" / "models.py")
    assert is_in_environment(
        root, root / ".venv" / "lib" / "site-packages" / "lib" / "m.py"
    )
    assert is_in_environment(root, root / "venv2" / "m.py")


def test_save_of_a_document_can_say_what_review_status_to_write_and_save_of_an_entity_cannot():
    from pangloss_models.typestubs import save_methods

    document = "\n".join(save_methods("Letter", "Update", "async", is_document=True))
    assert "published: bool | None = None, review_status: str | None = None" in document
    assert "expected_version: int | None = None" in document
    entity = "\n".join(save_methods("Person", "Create", "async"))
    assert "published" not in entity and "review_status" not in entity
