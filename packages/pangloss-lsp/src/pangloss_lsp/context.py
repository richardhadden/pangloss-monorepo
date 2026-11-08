"""Where the cursor is in a Python file that may not parse: in which call, at which argument, in a string or not.

An editor asks for a completion in the middle of typing, when the buffer is almost never valid, so this reads the text
the way a person does (brackets, commas, quotes), and not with `ast`.
"""

import keyword
import re
from dataclasses import dataclass, field


@dataclass
class Frame:
    """A bracket that is open at the cursor"""

    char: str
    position: int
    # (the commas that are directly in it; kept up to its close, which is after the cursor)
    commas: list[int] = field(default_factory=list)
    close: int | None = None


@dataclass
class Scan:
    frames: list[Frame]
    # The quote the cursor is inside, and where that string begins
    quote: str | None = None
    string_start: int | None = None
    in_comment: bool = False


def scan(text: str, offset: int) -> Scan:
    """The brackets open at `offset`, and the string or comment it is in. The text after `offset` is read as well,
    to find where those brackets close and where their commas are"""
    stack: list[Frame] = []
    snapshot: Scan | None = None
    quote: str | None = None
    string_start = 0
    comment = False
    index = 0
    length = len(text)
    while index <= length:
        if index == offset:
            snapshot = Scan(
                list(stack),
                quote,
                string_start if quote else None,
                comment,
            )
        if index == length:
            break
        char = text[index]
        if comment:
            if char == "\n":
                comment = False
        elif quote:
            if char == "\\":
                index += 1
            elif text.startswith(quote, index):
                index += len(quote) - 1
                quote = None
            elif len(quote) == 1 and char == "\n":
                quote = None
        elif char == "#":
            comment = True
        elif char in "\"'":
            quote = char * 3 if text.startswith(char * 3, index) else char
            string_start = index
            index += len(quote) - 1
        elif char in "([{":
            stack.append(Frame(char, index))
        elif char in ")]}":
            if stack:
                stack.pop().close = index
        elif char == "," and stack:
            stack[-1].commas.append(index)
        index += 1
    return snapshot or Scan([])


_ARGUMENT = re.compile(r"\s*([A-Za-z_]\w*)\s*=(?!=)")
_CALLEE = re.compile(r"([A-Za-z_][\w.]*)\s*$")


@dataclass
class CallContext:
    callee: str
    # The keyword of the argument the cursor is in (`indexes` in `Meta(indexes=["na|`), if it has one
    keyword: str | None
    # The cursor is where an argument's name goes
    at_name: bool
    # Inside a bracket within the argument (a list of names), not the argument's own value
    nested: bool
    in_string: bool
    # Where the word being typed begins (inside the quotes, if in a string)
    prefix_start: int
    # The keywords already given in the call
    used: frozenset[str]
    # Where the statement that holds the call begins: the line of its outermost bracket
    statement_line: int


def callee_before(text: str, position: int) -> str | None:
    found = _CALLEE.search(text[:position])
    if found is None or keyword.iskeyword(found[1].rsplit(".", 1)[-1]):
        return None
    return found[1]


def call_at(text: str, offset: int) -> CallContext | None:
    """The call the cursor is in (the innermost, though a list or a tuple within it may be open), or None"""
    state = scan(text, offset)
    if state.in_comment:
        return None
    calls = [
        (index, frame)
        for index, frame in enumerate(state.frames)
        if frame.char == "(" and callee_before(text, frame.position)
    ]
    if not calls:
        return None
    index, frame = calls[-1]
    callee = callee_before(text, frame.position)
    assert callee is not None
    nested = index != len(state.frames) - 1

    before = [frame.position, *(c for c in frame.commas if c < offset)]
    argument = text[before[-1] + 1 : offset]
    given = _ARGUMENT.match(argument)
    in_string = state.quote is not None
    if state.quote is not None:
        prefix_start = (state.string_start or 0) + len(state.quote)
    else:
        word = re.search(r"\w*$", text[:offset])
        prefix_start = offset - len(word[0] if word else "")

    # (every argument but the one being typed)
    bounds = [frame.position, *frame.commas, frame.close or len(text)]
    used = set()
    for start, end in zip(bounds, bounds[1:], strict=False):
        if start < offset <= end:
            continue
        if found := _ARGUMENT.match(text[start + 1 : end]):
            used.add(found[1])

    return CallContext(
        callee=callee,
        keyword=given[1] if given else None,
        at_name=not nested
        and given is None
        and not in_string
        and re.fullmatch(r"\s*\w*", argument) is not None,
        nested=nested,
        in_string=in_string,
        prefix_start=prefix_start,
        used=frozenset(used),
        statement_line=text.count("\n", 0, state.frames[0].position),
    )


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def enclosing_class(lines: list[str], line: int) -> tuple[str, int] | None:
    """The class whose body holds the statement that starts at `line`: its name and the line it begins on"""
    indent = indentation(lines[line]) if line < len(lines) else 0
    for above in range(line - 1, -1, -1):
        text = lines[above]
        if not text.strip() or text.lstrip().startswith(("#", "@")):
            continue
        if indentation(text) < indent:
            found = re.match(r"\s*class\s+([A-Za-z_]\w*)", text)
            return (found[1], above) if found else None
    return None


def fields_declared_in(lines: list[str], class_line: int) -> list[str]:
    """The names a class body gives to annotated fields, from the text (the fields of the last good run are the
    saved file's; these are what has been typed since)"""
    names: list[str] = []
    class_indent = indentation(lines[class_line])
    body_indent: int | None = None
    for text in lines[class_line + 1 :]:
        if not text.strip():
            continue
        if indentation(text) <= class_indent:
            break
        if body_indent is None:
            body_indent = indentation(text)
        found = re.match(r"([A-Za-z_]\w*)\s*:", text.strip())
        if (
            found
            and indentation(text) == body_indent
            and not text.lstrip().startswith("_")
        ):
            names.append(found[1])
    return names


def field_of_statement(lines: list[str], line: int) -> str | None:
    """`born_in` for a statement that begins `born_in: Annotated[...`"""
    found = (
        re.match(r"\s*([A-Za-z_]\w*)\s*:", lines[line]) if line < len(lines) else None
    )
    return found[1] if found else None


def bases_of(lines: list[str], class_line: int) -> list[str]:
    found = re.match(
        r"\s*class\s+\w+\s*(?:\[[^\]]*\])?\s*\(([^)]*)\)", lines[class_line]
    )
    if not found:
        return []
    return [
        base.strip().rsplit(".", 1)[-1].split("[")[0]
        for base in found[1].split(",")
        if base.strip()
    ]


def class_body_word(text: str, offset: int) -> tuple[int, str] | None:
    """If the cursor ends a word that begins a line of a class body (`    _inter|`): where the word starts, and the
    word. Nothing else may be open"""
    state = scan(text, offset)
    if state.frames or state.quote or state.in_comment:
        return None
    line_start = text.rfind("\n", 0, offset) + 1
    found = re.fullmatch(r"(\s+)(\w*)", text[line_start:offset])
    if found is None:
        return None
    return line_start + len(found[1]), found[2]


def line_end_depths(text: str) -> list[int]:
    """How many brackets are open at the end of each line (so where a statement that goes over several lines ends).
    Strings and comments are read as `scan` reads them"""
    depths: list[int] = []
    depth = 0
    quote: str | None = None
    comment = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\n":
            depths.append(depth)
            comment = False
            if quote is not None and len(quote) == 1:
                quote = None
        elif comment:
            pass
        elif quote:
            if char == "\\":
                index += 1
            elif text.startswith(quote, index):
                index += len(quote) - 1
                quote = None
        elif char == "#":
            comment = True
        elif char in "\"'":
            quote = char * 3 if text.startswith(char * 3, index) else char
            index += len(quote) - 1
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(depth - 1, 0)
        index += 1
    depths.append(depth)
    return depths


def word_at(text: str, line: int, character: int) -> str | None:
    """The identifier the cursor is in or just after"""
    lines = text.splitlines()
    if line >= len(lines):
        return None
    for found in re.finditer(r"[A-Za-z_]\w*", lines[line]):
        if found.start() <= character <= found.end():
            return found[0]
    return None
