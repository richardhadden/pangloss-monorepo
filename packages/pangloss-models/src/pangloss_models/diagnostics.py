"""What is wrong with the declared models, and where in the source it is (`pangloss check`, the language server).

The rules are those of `initialise()`, which is run: nothing here decides what is an error. It adds two things:
`initialise()` goes on past a field it refuses, to find the others, and each refusal is given a place in the file.
"""

import ast
import difflib
import functools
import inspect
import re
import sys
import traceback
import warnings
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_origin

from pydantic_core import PydanticUndefined

from pangloss_models.exceptions import MODEL_ERRORS, AtString, PanglossModelWarning


@dataclass(frozen=True)
class Edit:
    """Replace `old_text`, which is at this range of `file`, with `new_text`. (`old_text` is there so that an editor
    whose buffer has changed since can see that the range is no longer this)"""

    file: str
    line: int
    column: int
    end_line: int
    end_column: int
    old_text: str
    new_text: str


@dataclass(frozen=True)
class Fix:
    title: str
    edits: tuple[Edit, ...]


@dataclass(frozen=True)
class Diagnostic:
    """`line` counts from 1 and `column` from 0, as `ast` does (here `column` is a character, not a byte). With no
    `file`, the problem has no one place. `fixes` are what the source could be changed to"""

    severity: Literal["error", "warning"]
    message: str
    file: str | None = None
    line: int = 1
    column: int = 0
    end_line: int = 1
    end_column: int = 0
    fixes: tuple[Fix, ...] = ()


@dataclass(frozen=True)
class _Place:
    file: str
    line: int
    column: int
    end_column: int


class _StopCollecting(Exception):
    """The models cannot be taken further with what has been found so far"""


# (the problems of the `check_models` under way: `reported` lets everything through when there is none)
_collecting: list[tuple[Exception, type | None, str | None]] | None = None


@contextmanager
def reported(model: type, field_name: str | None = None) -> Generator[None]:
    """Around what can refuse a model or a field, in `initialise()`: under `check_models` the refusal is noted, and
    initialising goes on to the next"""
    try:
        yield
    except Exception as error:
        if _collecting is None:
            raise
        # (once something is wrong, what is not a refusal is more likely to follow from it than to be news)
        if isinstance(error, MODEL_ERRORS) or not _collecting:
            _collecting.append((error, model, field_name))


def stop_if_refused() -> None:
    """Called where the steps after need all that came before to have worked"""
    if _collecting:
        raise _StopCollecting


@functools.lru_cache(maxsize=64)
def _parsed(file: str, modified: int) -> tuple[ast.Module, str]:
    source = Path(file).read_text()
    return ast.parse(source), source


def _class_node(model: type) -> tuple[Path, ast.ClassDef, list[str]] | None:
    module = sys.modules.get(model.__module__)
    file = getattr(module, "__file__", None)
    if file is None or not file.endswith(".py"):
        return None
    tree, source = _parsed(file, Path(file).stat().st_mtime_ns)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == model.__name__:
            return Path(file), node, source.splitlines()
    return None


def _column(lines: list[str], line: int, byte_column: int) -> int:
    """`ast` counts the columns of a line in UTF-8 bytes; the editor wants characters"""
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    return len(text.encode()[:byte_column].decode(errors="ignore"))


def _name_at(path: Path, lines: list[str], node: Any, name: str) -> _Place:
    """The name that a `class` or `def` statement gives: the statement's own position is that of its keyword"""
    line = lines[node.lineno - 1]
    column = line.find(name, _column(lines, node.lineno, node.col_offset))
    return _Place(str(path), node.lineno, column, column + len(name))


def _member_statement(node: ast.ClassDef, name: str) -> tuple[ast.stmt, ast.AST] | None:
    """The statement in the class body that gives `name` (a field, a method, an attribute), and the node of the name"""
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name == name:
                return statement, statement
        targets = (
            [statement.target]
            if isinstance(statement, ast.AnnAssign)
            else statement.targets
            if isinstance(statement, ast.Assign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return statement, target
    return None


def _locate(
    model: type, name: str
) -> tuple[Path, list[str], str, ast.stmt, ast.AST] | None:
    """Where in the source a class (or its parents: a field is declared where it first is) says `name`"""
    for candidate in model.__mro__:
        found = _class_node(candidate)
        if found is None:
            continue
        path, node, lines = found
        member = _member_statement(node, name)
        if member is not None:
            _, source = _parsed(str(path), path.stat().st_mtime_ns)
            return path, lines, source, member[0], member[1]
    return None


def source_place(model: type, name: str | None = None) -> _Place | None:
    """Where the class says `name` (a field, or a method), or itself. A field a class inherits is at its parent"""
    located = _locate(model, name) if name else None
    if located is not None:
        path, lines, _, _, target = located
        if isinstance(target, ast.Name):
            column = _column(lines, target.lineno, target.col_offset)
            return _Place(str(path), target.lineno, column, column + len(target.id))
        return _name_at(path, lines, target, name or "")
    found = _class_node(model)
    if found is None:
        return None
    path, node, lines = found
    return _name_at(path, lines, node, node.name)


def _places_named_in(message: str, models: Mapping[str, type]) -> list[_Place]:
    """For a problem that was not raised beside its model: messages begin with, or list, `Model.field` or `Model`"""
    places: list[_Place] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)(?:\.([a-z_]\w*))?", message):
        model = models.get(match[1])
        if model is None:
            continue
        place = source_place(model, match[2])
        if place is not None and place not in places:
            places.append(place)
        # (only what comes first says whose fault it is, unless the message lists one problem a line)
        if "\n" not in message and places:
            break
    return places


def _diagnostics_at(
    severity: Literal["error", "warning"],
    message: str,
    places: list[_Place],
    fixes: tuple[Fix, ...] = (),
) -> list[Diagnostic]:
    if not places:
        return [Diagnostic(severity, message)]
    return [
        Diagnostic(
            severity,
            message,
            place.file,
            place.line,
            place.column,
            place.line,
            place.end_column,
            fixes,
        )
        for place in places
    ]


# ---------------------------------------------------------------------------
# Fixes: what the source could be changed to. A refusal names one (`PanglossModelError(fix="drop_optional")`), here
# is what it does to the text
# ---------------------------------------------------------------------------


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _none_union(tree: ast.AST) -> tuple[ast.BinOp, ast.expr] | None:
    """The first `X | None` in the annotation, and the `X`"""
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            if _is_none(node.right):
                return node, node.left
            if _is_none(node.left):
                return node, node.right
    return None


def _edit(
    path: Path, lines: list[str], source: str, node: ast.expr, new_text: str
) -> Edit:
    end_line = node.end_lineno or node.lineno
    return Edit(
        str(path),
        node.lineno,
        _column(lines, node.lineno, node.col_offset),
        end_line,
        _column(lines, end_line, node.end_col_offset or 0),
        ast.get_source_segment(source, node) or "",
        new_text,
    )


def _annotation_of(
    model: type, field_name: str
) -> tuple[Path, list[str], str, ast.expr] | None:
    located = _locate(model, field_name)
    if located is None:
        return None
    path, lines, source, statement, _ = located
    if not isinstance(statement, ast.AnnAssign):
        return None
    return path, lines, source, statement.annotation


def _drop_optional(model: type, field_name: str | None) -> Fix | None:
    """`list[Person] | None` is `list[Person]`: a list may already be empty"""
    found = _annotation_of(model, field_name or "")
    union = _none_union(found[3]) if found else None
    if found is None or union is None:
        return None
    path, lines, source, annotation = found
    node, kept = union
    new_text = ast.get_source_segment(source, kept) or ""
    return Fix(f"Change to `{new_text}`", (_edit(path, lines, source, node, new_text),))


def _list_with_none_items(annotation: ast.expr) -> ast.Subscript | None:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Subscript) and _none_union(node.slice):
            return node
    return None


def _drop_none_in_items(model: type, field_name: str | None) -> Fix | None:
    found = _annotation_of(model, field_name or "")
    subscript = _list_with_none_items(found[3]) if found else None
    if found is None or subscript is None:
        return None
    path, lines, source, _ = found
    union = _none_union(subscript.slice)
    assert union is not None
    new_text = ast.get_source_segment(source, union[1]) or ""
    return Fix(
        f"Remove `None` from the items: `{ast.get_source_segment(source, subscript.value)}[{new_text}]`",
        (_edit(path, lines, source, subscript.slice, new_text),),
    )


def _optional_list(model: type, field_name: str | None) -> Fix | None:
    found = _annotation_of(model, field_name or "")
    subscript = _list_with_none_items(found[3]) if found else None
    if found is None or subscript is None:
        return None
    path, lines, source, _ = found
    union = _none_union(subscript.slice)
    assert union is not None
    new_text = (
        f"{ast.get_source_segment(source, subscript.value)}"
        f"[{ast.get_source_segment(source, union[1])}] | None"
    )
    return Fix(
        f"Make the whole list optional: `{new_text}`",
        (_edit(path, lines, source, subscript, new_text),),
    )


def _remove_member(model: type, member: str | None) -> Fix | None:
    located = _locate(model, member or "")
    if located is None:
        return None
    path, lines, _, statement, _ = located
    first = min(
        [
            statement.lineno,
            *(d.lineno for d in getattr(statement, "decorator_list", [])),
        ]
    )
    last = statement.end_lineno or statement.lineno
    return Fix(
        f"Remove `{member}`",
        (
            Edit(
                str(path),
                first,
                0,
                last + 1,
                0,
                "\n".join(lines[first - 1 : last]) + "\n",
                "",
            ),
        ),
    )


def _find_string(
    model: type, member: str | None, at: AtString
) -> tuple[Path, list[str], str, ast.Constant] | None:
    """The string literal `at.value` given to the option `at.option`: in the field's statement if the refusal is about
    a field, else in the class (or, for a name a class inherits, the class above that wrote it)"""
    for candidate in model.__mro__:
        found = _class_node(candidate)
        if found is None:
            continue
        path, node, lines = found
        _, source = _parsed(str(path), path.stat().st_mtime_ns)
        located = _member_statement(node, member) if member else None
        statement = located[0] if located else None
        for root in (statement, node) if statement is not None else (node,):
            for call in ast.walk(root):
                if not isinstance(call, ast.Call):
                    continue
                for keyword in call.keywords:
                    if keyword.arg != at.option:
                        continue
                    for string in ast.walk(keyword.value):
                        if (
                            isinstance(string, ast.Constant)
                            and string.value == at.value
                        ):
                            return path, lines, source, string
    return None


def _string_place(model: type, member: str | None, at: AtString) -> _Place | None:
    found = _find_string(model, member, at)
    if found is None:
        return None
    path, lines, _, string = found
    column = _column(lines, string.lineno, string.col_offset)
    if (string.end_lineno or string.lineno) != string.lineno:
        return _Place(str(path), string.lineno, column, len(lines[string.lineno - 1]))
    return _Place(
        str(path),
        string.lineno,
        column,
        _column(lines, string.lineno, string.end_col_offset or 0),
    )


def _did_you_mean_fixes(
    model: type, member: str | None, at: AtString
) -> tuple[Fix, ...]:
    """A fix for each of the (up to three) names that the misspelt one is close to"""
    found = _find_string(model, member, at)
    if found is None:
        return ()
    path, lines, source, string = found
    written = ast.get_source_segment(source, string) or ""
    quote = written[-1] if written and written[-1] in "'\"" else '"'
    return tuple(
        Fix(
            f"Change to {quote}{name}{quote}",
            (_edit(path, lines, source, string, f"{quote}{name}{quote}"),),
        )
        for name in difflib.get_close_matches(at.value, at.candidates, n=3, cutoff=0.6)
    )


FIXES: dict[str, Callable[[type, str | None], Fix | None]] = {
    "drop_optional": _drop_optional,
    "drop_none_in_items": _drop_none_in_items,
    "optional_list": _optional_list,
    "remove_member": _remove_member,
}


def _fixes_of(
    names: str | tuple[str, ...] | None, model: type | None, member: str | None
) -> tuple[Fix, ...]:
    if names is None or model is None:
        return ()
    found = (
        FIXES[name](model, member)
        for name in ((names,) if isinstance(names, str) else names)
    )
    return tuple(fix for fix in found if fix is not None)


def diagnose_model(
    severity: Literal["error", "warning"],
    message: str,
    model_name: str | None,
    member: str | None = None,
) -> Diagnostic:
    """A problem about a model (and perhaps one of its fields) by the model's name, at the source if the class is
    one that is registered: the migrations name models, not classes"""
    from pangloss_models.model_registry import ModelRegistry

    model = ModelRegistry.all_models().get(model_name or "")
    place = source_place(model, member) if model is not None else None
    if place is None:
        return Diagnostic(severity, message)
    return _diagnostics_at(severity, message, [place])[0]


def diagnostic_of_exception(error: BaseException, root: Path) -> Diagnostic:
    """Importing a module failed: where it failed, in the project's own code (the framework's frames say nothing)"""
    message = f"{type(error).__name__}: {error}" if not _is_ours(error) else str(error)
    if isinstance(error, SyntaxError) and error.filename:
        line = error.lineno or 1
        column = max((error.offset or 1) - 1, 0)
        return Diagnostic(
            "error", message, error.filename, line, column, line, column + 1
        )
    root = root.resolve()
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(root) and ".venv" not in path.parts:
            lines = path.read_text().splitlines()
            line = frame.lineno or 1
            text = lines[line - 1] if line <= len(lines) else ""
            column = len(text) - len(text.lstrip())
            return Diagnostic(
                "error", message, str(path), line, column, line, len(text)
            )
    return Diagnostic("error", message)


def _is_ours(error: BaseException) -> bool:
    return isinstance(error, MODEL_ERRORS)


def check_models() -> list[Diagnostic]:
    """Initialise the models that have been imported, without a database, and say what is wrong with them. The models
    are made if the answer has no error (warnings do not stop them)"""
    global _collecting
    from pangloss_models.model_registry import ModelRegistry

    found: list[Diagnostic] = []
    _collecting = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PanglossModelWarning)
        unattached: Exception | None = None
        try:
            ModelRegistry.finalise(bind_database=False)
        except _StopCollecting:
            pass
        except Exception as error:
            unattached = error
    collected, _collecting = _collecting, None

    models = ModelRegistry.all_models()
    for error, model, field_name in collected:
        message = str(error) if _is_ours(error) else f"{type(error).__name__}: {error}"
        at_string = getattr(error, "at_string", None)
        string_place = (
            _string_place(model, field_name, at_string) if at_string and model else None
        )
        places = [source_place(model, field_name)] if field_name and model else []
        places = [place for place in places if place is not None]
        found += _diagnostics_at(
            "error",
            message,
            [string_place]
            if string_place
            else places or _places_named_in(message, models) or _own_place(model),
            _fixes_of(getattr(error, "fix", None), model, field_name)
            + (
                _did_you_mean_fixes(model, field_name, at_string)
                if at_string and model and string_place
                else ()
            ),
        )
    if unattached is not None and (_is_ours(unattached) or not found):
        message = (
            str(unattached)
            if _is_ours(unattached)
            else f"{type(unattached).__name__}: {unattached}"
        )
        found += _diagnostics_at("error", message, _places_named_in(message, models))
    for warning in caught:
        if issubclass(warning.category, PanglossModelWarning):
            message = str(warning.message)
            owner = getattr(warning.message, "model", None)
            member = getattr(warning.message, "member", None)
            place = source_place(owner, member) if owner and member else None
            found += _diagnostics_at(
                "warning",
                message,
                [place] if place else _places_named_in(message, models),
                _fixes_of(getattr(warning.message, "fix", None), owner, member),
            )
    # (a field refused on a parent is refused again, in the child's name, on each of its children, at the one place)
    first_at: dict[tuple, Diagnostic] = {}
    for diagnostic in found:
        place = (diagnostic.file, diagnostic.line, diagnostic.column)
        first_at.setdefault(
            place if diagnostic.file else (diagnostic.message,), diagnostic
        )
    return list(first_at.values())


def _own_place(model: type | None) -> list[_Place]:
    place = source_place(model) if model is not None else None
    return [place] if place is not None else []


def _type_name(annotation: Any) -> str:
    """As it would be written: without the modules, or `<class ...>`"""
    text = (
        annotation.__name__
        if inspect.isclass(annotation) and get_origin(annotation) is None
        else str(annotation)
    )
    return re.sub(r"(?:\w+\.)+(?=[A-Za-z_])", "", text).replace("NoneType", "None")


def _names(options: Any) -> str:
    names = sorted(
        getattr(option.annotated_type, "__name__", str(option.annotated_type))
        for option in options
    )
    return " or ".join(f"`{name}`" for name in names)


def _what_the_field_is(definition: Any) -> str:
    # (by name, rather than importing them: `field_definitions` is for the kinds of field what this file is for words)
    match type(definition).__name__:
        case "LiteralFieldDefinition":
            return f"A value stored on the node: `{_type_name(definition.annotated_type)}`."
        case "ListFieldDefinition":
            return f"A list of values stored on the node: `{_type_name(definition.inner_type)}`."
        case "AnnotatedValueFieldDefinition":
            return "A value with facts about it, stored as a map on the node."
        case "EmbeddedFieldDefinition":
            optional = "Optional embedded" if definition.optional else "Embedded"
            return f"{optional} object, a node of its own: {_names(definition.type_options)}."
        case "RelationFieldDefinition":
            count = (
                "zero or one"
                if definition.optional
                else "a list"
                if definition.wrapper
                else "exactly one"
            )
            return (
                f"Relation to {_names(definition.type_options)} ({count}). Each is two edges: "
                f"`{definition.field_name}` and the reverse, `{definition.reverse_name}`."
            )
        case _:
            return f"`{type(definition).__name__}`"


def _in_create(model: type, field_name: str) -> str | None:
    create = getattr(model, "Create", None)
    field = getattr(create, "model_fields", {}).get(field_name)
    if field is None:
        return None
    if field.is_required():
        given = "required"
    elif field.default_factory is not None:
        given = "may be left out"
    elif field.default is PydanticUndefined:
        given = "may be left out"
    else:
        given = f"may be left out: `{field.default!r}`"
    return f"In `{model.__name__}.Create`: `{_type_name(field.annotation)}`, {given}."


def field_descriptions() -> dict[str, str]:
    """For each field a class declares, `Model.field`: what it is to Pangloss, in Markdown (the language server's
    hover). The models have to have been made"""
    from pangloss_models.model_registry import ModelRegistry

    descriptions: dict[str, str] = {}
    for name, model in ModelRegistry.all_models().items():
        meta = getattr(model, "_meta", None)
        definitions = getattr(getattr(meta, "field_definitions", None), "fields", None)
        for field_name, definition in (definitions or {}).items():
            parts = [_what_the_field_is(definition)]
            if in_create := _in_create(model, field_name):
                parts.append(in_create)
            if definition.description:
                parts.append(definition.description)
            descriptions[f"{name}.{field_name}"] = "\n\n".join(parts)
    return descriptions
