"""The language server: `pangloss check` at the line.

Nothing is worked out here. A project's models are imported in a `pangloss check --json` of their own, on each save,
so a broken model cannot take the server down and each run starts with nothing registered; this publishes what it says.
"""

import asyncio
import json
import re
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from lsprotocol import types
from pangloss_cli.project import settings_from_pyproject
from pygls.lsp.server import LanguageServer

from pangloss_lsp.completion import complete, hover_on_parameter, offset_of
from pangloss_lsp.hints import hints_in

CHECK_TIMEOUT_SECONDS = 120


@dataclass
class ProjectState:
    root: Path
    checked: bool = False
    # (saves that come during a run are one more run, after it)
    running: asyncio.Task | None = None
    again: bool = False
    published: set[str] = field(default_factory=set)
    fields: dict[str, str] = field(default_factory=dict)
    # What `pangloss check` knew of the options and models (`pangloss_models.editor_schema`)
    schema: dict = field(default_factory=dict)
    # The relation fields that can hold each model (`Model` to their places)
    references: dict = field(default_factory=dict)
    # The inlay hint of each relation field, `Model.field` to its text and tooltip
    hints: dict = field(default_factory=dict)
    # The last report's diagnostics by file, with their fixes, for the code actions
    problems: dict[str, list[dict]] = field(default_factory=dict)


class PanglossLanguageServer(LanguageServer):
    def __init__(self) -> None:
        super().__init__("pangloss-lsp", "0.1.0")
        self.projects: dict[Path, ProjectState] = {}


server = PanglossLanguageServer()


def path_of(uri: str) -> Path | None:
    parsed = urlparse(uri)
    return Path(url2pathname(parsed.path)) if parsed.scheme == "file" else None


def project_of(ls: PanglossLanguageServer, uri: str) -> ProjectState | None:
    """The project a Python file belongs to, by the `pyproject.toml` that names its settings"""
    path = path_of(uri)
    if path is None or path.suffix != ".py" or ".venv" in path.parts:
        return None
    location = settings_from_pyproject(path.parent)
    if location is None:
        return None
    return ls.projects.setdefault(location.root, ProjectState(location.root))


def to_lsp(diagnostic: dict) -> types.Diagnostic:
    # (`line` from 1, as Python counts. Columns are characters, and LSP's are UTF-16 units; what comes before a name
    # on its line is indentation or an identifier, which do not differ)
    return types.Diagnostic(
        range=types.Range(
            start=types.Position(
                line=diagnostic["line"] - 1, character=diagnostic["column"]
            ),
            end=types.Position(
                line=diagnostic["end_line"] - 1, character=diagnostic["end_column"]
            ),
        ),
        message=diagnostic["message"],
        severity=types.DiagnosticSeverity.Error
        if diagnostic["severity"] == "error"
        else types.DiagnosticSeverity.Warning,
        source="pangloss",
    )


async def run_check(root: Path) -> dict:
    """What `pangloss check` says of a project, in a process of its own. It has the server's Python, the project's"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pangloss_cli.main",
        "check",
        "--json",
        "--write-stubs",
        cwd=root,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), CHECK_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        return _failure(f"`pangloss check` took over {CHECK_TIMEOUT_SECONDS} s")
    last = out.decode().strip().rsplit("\n", 1)[-1]
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return _failure(f"`pangloss check` failed:\n{err.decode()[-2000:]}")


def _failure(message: str) -> dict:
    return {
        "diagnostics": [{"severity": "error", "message": message, "file": None}],
        "fields": None,
    }


def publish(
    ls: PanglossLanguageServer, project: ProjectState, report: dict, saved: str
) -> None:
    by_uri: dict[str, list[types.Diagnostic]] = defaultdict(list)
    for diagnostic in report["diagnostics"]:
        if diagnostic.get("file"):
            by_uri[Path(diagnostic["file"]).as_uri()].append(to_lsp(diagnostic))
        else:
            # (it has no line of its own, and would otherwise not be seen: at the top of the file just saved)
            by_uri[saved].append(
                to_lsp(
                    diagnostic
                    | {"line": 1, "column": 0, "end_line": 1, "end_column": 1}
                )
            )
    # (a file that had problems and has none now is told so: an editor keeps what it was last sent)
    for uri in project.published | set(by_uri):
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=by_uri.get(uri, []))
        )
    project.published = set(by_uri)
    project.problems = defaultdict(list)
    for diagnostic in report["diagnostics"]:
        if diagnostic.get("file"):
            project.problems[Path(diagnostic["file"]).as_uri()].append(diagnostic)
    # (with an error there is no description: the hover of the last good run is better than none)
    if report["fields"]:
        project.fields = report["fields"]
    if report["fields"]:
        project.hints = report.get("hints") or {}
        project.references = report.get("references") or {}
    if report.get("schema"):
        # (a model that did not come through has no fields to offer: the last run's are kept)
        previous = project.schema.get("models")
        project.schema = report["schema"]
        if previous and any(d["severity"] == "error" for d in report["diagnostics"]):
            project.schema["models"] = previous


async def analyse(
    ls: PanglossLanguageServer, project: ProjectState, saved: str
) -> None:
    while True:
        project.again = False
        publish(ls, project, await run_check(project.root), saved)
        if not project.again:
            project.running = None
            return


def request_analysis(
    ls: PanglossLanguageServer, project: ProjectState, saved: str
) -> None:
    project.checked = True
    if project.running is not None:
        project.again = True
        return
    project.running = asyncio.create_task(analyse(ls, project, saved))


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(
    ls: PanglossLanguageServer, params: types.DidOpenTextDocumentParams
) -> None:
    project = project_of(ls, params.text_document.uri)
    # (once a project: an editor keeps what it was sent, for files opened later too)
    if project is not None and not project.checked:
        request_analysis(ls, project, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(
    ls: PanglossLanguageServer, params: types.DidSaveTextDocumentParams
) -> None:
    project = project_of(ls, params.text_document.uri)
    if project is not None:
        request_analysis(ls, project, params.text_document.uri)


def field_at(lines: Sequence[str], position: types.Position) -> str | None:
    """`Class.field`, if the cursor is on the name a field is declared with. By indentation, not `ast`: the buffer
    being edited need not parse"""
    if position.line >= len(lines):
        return None
    line = lines[position.line]
    declared = re.match(r"(\s+)([A-Za-z_]\w*)\s*:", line)
    if declared is None or not declared.start(2) <= position.character <= declared.end(
        2
    ):
        return None
    indent = len(declared[1])
    for above in reversed(lines[: position.line]):
        stripped = above.lstrip()
        if not stripped or len(above) - len(stripped) >= indent:
            continue
        if owner := re.match(r"class\s+([A-Za-z_]\w*)", stripped):
            return f"{owner[1]}.{declared[2]}"
        return None
    return None


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: PanglossLanguageServer, params: types.HoverParams) -> types.Hover | None:
    project = project_of(ls, params.text_document.uri)
    if project is None:
        return None
    document = ls.workspace.get_text_document(params.text_document.uri)
    if project.schema:
        option = hover_on_parameter(
            project.schema, document.source, offset_of(document.source, params.position)
        )
        if option is not None:
            return types.Hover(
                contents=types.MarkupContent(
                    kind=types.MarkupKind.Markdown, value=option
                )
            )
    name = field_at(document.lines, params.position)
    description = project.fields.get(name) if name else None
    if description is None:
        return None
    return types.Hover(
        contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=description)
    )


COMPLETION_TRIGGERS = ["(", ",", "=", '"', "'", "[", "_"]


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=COMPLETION_TRIGGERS),
)
def completion(
    ls: PanglossLanguageServer, params: types.CompletionParams
) -> types.CompletionList | None:
    project = project_of(ls, params.text_document.uri)
    if project is None or not project.schema:
        return None
    text = ls.workspace.get_text_document(params.text_document.uri).source
    items = complete(project.schema, text, offset_of(text, params.position))
    return types.CompletionList(is_incomplete=False, items=items) if items else None


def buffer_text(source: str, edit: dict) -> str:
    start = offset_of(source, types.Position(edit["line"] - 1, edit["column"]))
    end = offset_of(source, types.Position(edit["end_line"] - 1, edit["end_column"]))
    # (an edit that removes the last line reaches past the end of the text)
    if edit["end_line"] > source.count("\n") + 1:
        end = len(source)
    return source[start:end]


def code_action_for(
    ls: PanglossLanguageServer,
    diagnostic: dict,
    fix: dict,
    lsp_diagnostic: types.Diagnostic,
) -> types.CodeAction | None:
    changes: dict[str, list[types.TextEdit]] = {}
    for edit in fix["edits"]:
        uri = Path(edit["file"]).as_uri()
        source = ls.workspace.get_text_document(uri).source
        # (the fix was made from the file as it was saved: if the buffer has been changed there, it may not fit)
        if buffer_text(source, edit).rstrip("\n") != edit["old_text"].rstrip("\n"):
            return None
        changes.setdefault(uri, []).append(
            types.TextEdit(
                types.Range(
                    types.Position(edit["line"] - 1, edit["column"]),
                    types.Position(edit["end_line"] - 1, edit["end_column"]),
                ),
                edit["new_text"],
            )
        )
    return types.CodeAction(
        title=fix["title"],
        kind=types.CodeActionKind.QuickFix,
        diagnostics=[lsp_diagnostic],
        edit=types.WorkspaceEdit(changes=changes),
    )


@server.feature(
    types.TEXT_DOCUMENT_CODE_ACTION,
    types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]),
)
def code_action(
    ls: PanglossLanguageServer, params: types.CodeActionParams
) -> list[types.CodeAction] | None:
    project = project_of(ls, params.text_document.uri)
    if project is None:
        return None
    actions = []
    for diagnostic in project.problems.get(params.text_document.uri, []):
        first, last = diagnostic["line"] - 1, diagnostic["end_line"] - 1
        if not first <= params.range.end.line or not params.range.start.line <= last:
            continue
        for fix in diagnostic.get("fixes", []):
            action = code_action_for(ls, diagnostic, fix, to_lsp(diagnostic))
            if action is not None:
                actions.append(action)
    return actions or None


def word_at(text: str, position: types.Position) -> str | None:
    lines = text.splitlines()
    if position.line >= len(lines):
        return None
    line = lines[position.line]
    for found in re.finditer(r"[A-Za-z_]\w*", line):
        if found.start() <= position.character <= found.end():
            return found[0]
    return None


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def references(
    ls: PanglossLanguageServer, params: types.ReferenceParams
) -> list[types.Location] | None:
    """The relation fields that can hold the model whose name is under the cursor"""
    project = project_of(ls, params.text_document.uri)
    if project is None or not project.references:
        return None
    text = ls.workspace.get_text_document(params.text_document.uri).source
    name = word_at(text, params.position)
    found = project.references.get(name or "")
    if not found:
        return None
    return [
        types.Location(
            Path(place["file"]).as_uri(),
            types.Range(
                types.Position(place["line"] - 1, place["column"]),
                types.Position(place["line"] - 1, place["end_column"]),
            ),
        )
        for place in found
    ]


@server.feature(types.TEXT_DOCUMENT_INLAY_HINT)
def inlay_hint(
    ls: PanglossLanguageServer, params: types.InlayHintParams
) -> list[types.InlayHint] | None:
    project = project_of(ls, params.text_document.uri)
    if project is None or not project.hints:
        return None
    text = ls.workspace.get_text_document(params.text_document.uri).source
    found = hints_in(
        project.hints, text, params.range.start.line, params.range.end.line
    )
    return [
        types.InlayHint(
            position=types.Position(hint.line, hint.character),
            label=hint.label,
            padding_left=True,
            tooltip=types.MarkupContent(types.MarkupKind.Markdown, hint.tooltip)
            if hint.tooltip
            else None,
        )
        for hint in found
    ] or None


def main() -> None:
    server.start_io()


if __name__ == "__main__":
    main()
