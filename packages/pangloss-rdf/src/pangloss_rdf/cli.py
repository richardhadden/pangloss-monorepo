"""`pangloss rdf <command>`: check the names, write the ontology, dump the data, and make a module of an ontology's mixins"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

cli = typer.Typer(name="rdf", help="Export as RDF", no_args_is_help=True)


def _initialised(ctx: typer.Context) -> None:
    from pangloss_models import initialise

    ctx.obj.import_models()
    initialise()


def _emit(text: str, output: Path | None) -> None:
    if output is None:
        typer.echo(text)
    else:
        output.write_text(text, encoding="utf-8")


@cli.command()
def check(ctx: typer.Context) -> None:
    """Find what is wrong with the names of the models in RDF, and what to settle before publishing"""
    from pangloss_models.exceptions import PanglossMetaError

    from pangloss_rdf.checks import check_markers, warnings
    from pangloss_rdf.uris import check_models
    from pangloss_rdf.vocabulary import check_prefixes

    _initialised(ctx)
    try:
        check_models()
        check_markers()
        check_prefixes()
    except PanglossMetaError as error:
        typer.secho(str(error), fg="red", err=True)
        raise typer.Exit(1) from None
    for warning in warnings():
        typer.secho(f"warning: {warning}", fg="yellow")
    typer.echo("The RDF names are good.")


@cli.command()
def ontology(
    ctx: typer.Context,
    format: Annotated[str, typer.Option(help="ttl, trig, jsonld, nt or nq")] = "ttl",
    shapes: Annotated[bool, typer.Option(help="The SHACL shapes instead")] = False,
    context: Annotated[bool, typer.Option(help="The JSON-LD context instead")] = False,
    output: Annotated[Path | None, typer.Option("-o", "--output")] = None,
) -> None:
    """Write the ontology, made from the models"""
    import json

    from pangloss_rdf.ontology import jsonld_context, ontology_quads
    from pangloss_rdf.serialise import serialise
    from pangloss_rdf.shacl import shape_quads

    _initialised(ctx)
    if context:
        _emit(json.dumps({"@context": jsonld_context()}, indent=2), output)
        return
    _emit(serialise(shape_quads() if shapes else ontology_quads(), format), output)


@cli.command()
def dump(
    ctx: typer.Context,
    output: Annotated[
        Path, typer.Option("-o", "--output", help="A name ending .gz is compressed")
    ],
    format: Annotated[str, typer.Option(help="nq or trig")] = "nq",
    types: Annotated[
        str | None, typer.Option(help="Only these classes, with commas")
    ] = None,
    include_unpublished: Annotated[
        bool, typer.Option(help="Also what a reader who is not logged in cannot see")
    ] = False,
) -> None:
    """Write every document and entity to a file"""
    from pangloss_rdf.dump import dump as run_dump

    project = ctx.obj
    backend = project.require_database()
    _initialised(ctx)

    async def main():
        await backend.connect()
        try:
            return await run_dump(
                output,
                format,
                types.split(",") if types else None,
                include_unpublished,
            )
        finally:
            await backend.disconnect()

    result = asyncio.run(main())
    typer.echo(f"{result.items} items, {result.quads} quads, in {output}")


@cli.command("generate-ontology")
def generate_ontology(
    source: Path,
    prefix: Annotated[
        str, typer.Option(help="What the ontology is called in the output, such as crm")
    ],
    output: Annotated[Path, typer.Option("--out")],
    title: Annotated[
        str | None, typer.Option(help="Its name, in the module's docstring")
    ] = None,
) -> None:
    """Make a Python module of mixins from an ontology's RDFS or OWL file"""
    from pangloss_rdf.generate import generate_module

    output.write_text(generate_module(source, prefix, title), encoding="utf-8")
    typer.echo(f"Written {output}")
