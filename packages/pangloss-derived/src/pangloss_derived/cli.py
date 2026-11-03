"""`pangloss derive <command>`: look at the rules, build them, run the worker, and take the facts out as a graph.

pangloss derive explain [rule]        each rule as Datalog, what triggers it, its query and join order
pangloss derive dry-run [rule]        how many facts it would make, and the seeds that give most, without writing
pangloss derive rebuild [rule]        derive everything again (after a bulk load, which writes no pending marks)
pangloss derive status                what is pending, the state of each rule
pangloss derive graph TYPE            the facts of the rules of a type, as edges (JSON, or --csv)
pangloss derive worker                the worker, on its own (with `DERIVED_WORKER_IN_SERVER = False`)
"""

import asyncio
import csv
import json
import sys
from collections.abc import Awaitable, Callable

import typer

cli = typer.Typer(
    name="derive",
    help="Derived relations: rules, their facts, and the worker",
    no_args_is_help=True,
)


def initialised(ctx: typer.Context) -> None:
    from pangloss_models import initialise

    project = ctx.obj
    project.require_database()
    project.import_models()
    initialise()


def run_connected[T](ctx: typer.Context, function: Callable[[], Awaitable[T]]) -> T:
    """Import and initialise the models, then run a coroutine function with the database connected"""
    project = ctx.obj
    backend = project.require_database()
    initialised(ctx)

    async def main() -> T:
        await backend.connect()
        try:
            return await function()
        finally:
            await backend.disconnect()

    return asyncio.run(main())


def rules_named(name: str | None) -> list:
    from pangloss_derived.registry import DerivedRegistry

    if name is None:
        return list(DerivedRegistry.checked.values())
    rule = DerivedRegistry.checked.get(name)
    if rule is None:
        known = ", ".join(sorted(DerivedRegistry.checked)) or "(none)"
        typer.secho(f"No rule {name}. Known: {known}", fg="red", err=True)
        raise typer.Exit(2)
    return [rule]


@cli.command()
def explain(
    ctx: typer.Context,
    rule: str | None = typer.Argument(None, help="One rule (all, if not given)"),
    queries: bool = typer.Option(
        False, "--queries", help="Print the query of each place too"
    ),
) -> None:
    """Each rule as Datalog, its types, what can trigger it, the wrappers it does not derive through, and the order of
    the joins from each place it can be seeded at"""
    from pangloss_derived.compile import compile_rule, join_order
    from pangloss_derived.registry import DerivedRegistry

    initialised(ctx)
    for checked in rules_named(rule):
        typer.secho(
            f"{checked.name}  ({checked.model.__name__}, hash {checked.hash})",
            bold=True,
        )
        if checked.rule.description:
            typer.echo(f"  {checked.rule.description}")
        if checked.types:
            typer.echo(f"  types: {', '.join(checked.type_names)}")
        typer.echo("  " + checked.describe().replace("\n", "\n  "))
        triggers = sorted(
            head
            for head, seeds in DerivedRegistry.triggers.items()
            if any(s.rule == checked.name for s in seeds)
        )
        typer.echo(f"  triggered by writes of: {', '.join(triggers) or '(nothing)'}")
        if checked.symmetric:
            typer.echo(
                "  symmetric: each pair matched once (the body is the same with the two swapped)"
                if checked.symmetric_body
                else "  symmetric: both orders matched (the body is not the same with the two swapped); the fact's ends "
                "are put in order of id"
            )
        if checked.blocked:
            typer.echo(f"  not through: {', '.join(sorted(checked.blocked))}")
        if checked.transparent:
            typer.echo(
                f"  through, as if not there: {', '.join(sorted(checked.transparent))}"
            )
        for seed in checked.seeds:
            typer.echo(f"  seeded at {seed.node} ({seed.model.__name__}):")
            for step in join_order(checked, seed.node):
                typer.echo(f"      {step}")
            if queries:
                query, _ = compile_rule(checked, seed.node)
                typer.echo("      " + query.replace("\n", "\n      "))
        typer.echo()


@cli.command("dry-run")
def dry_run(
    ctx: typer.Context,
    rule: str | None = typer.Argument(None, help="One rule (all, if not given)"),
    top: int = typer.Option(
        5, "--top", help="How many of the seeds that give most to show"
    ),
) -> None:
    """What a rule would derive from the data as it is, without writing anything: how many facts and justifications,
    and the seeds that give most (a seed past the class's `max_per_seed` gives none)"""
    from pangloss_derived import store
    from pangloss_derived.worker import database

    async def run() -> None:
        db = database()
        for checked in rules_named(rule):

            @db.read_transaction
            async def count(tx, checked=checked) -> None:
                seed = next(s for s in checked.seeds if s.node == checked.patterns[0])
                ids = await store.ids_of_class(tx, seed.model.__name__)
                found = store.Found()
                for start in range(0, len(ids), 500):
                    await store.run_seeded(
                        tx, checked, seed.node, ids[start : start + 500], found
                    )
                place = checked.patterns.index(seed.node)
                by_seed: dict[str, int] = {}
                for j in found.justifications.values():
                    by_seed[j.nodes[place]] = by_seed.get(j.nodes[place], 0) + 1
                typer.secho(checked.name, bold=True)
                typer.echo(
                    f"  {len(found.facts)} facts, {len(found.justifications)} justifications, from {len(ids)} "
                    f"{seed.model.__name__} nodes ({found.rows} rows)"
                )
                if found.overflowed:
                    typer.secho(
                        f"  {len(found.overflowed)} seeds over max_per_seed ({checked.model._meta.max_per_seed}): "
                        "they would give nothing",
                        fg="yellow",
                    )
                for node, n in sorted(by_seed.items(), key=lambda kv: -kv[1])[:top]:
                    typer.echo(f"    {node}: {n}")

            await count()

    run_connected(ctx, run)


@cli.command()
def rebuild(
    ctx: typer.Context,
    rule: str | None = typer.Argument(None, help="One rule (all, if not given)"),
) -> None:
    """Derive everything again (what is there and is found again is kept; what is not, deleted). After a bulk load,
    which leaves nothing pending, this is the way to derive what the data gives"""
    from pangloss_derived.worker import worker

    async def run() -> None:
        if not await worker.take_lease():
            typer.secho(
                "Another worker is working (a server, or `pangloss derive worker`): stop it, or wait for its lease",
                fg="red",
                err=True,
            )
            raise typer.Exit(1)
        try:
            for checked in rules_named(rule):
                counts = await worker.rebuild(checked)
                typer.echo(f"{checked.name}: {json.dumps(counts)}")
        finally:
            await worker.give_up_lease()

    run_connected(ctx, run)


@cli.command()
def status(ctx: typer.Context) -> None:
    """What is pending, and the state of each rule"""
    from pangloss_derived.registry import DerivedRegistry
    from pangloss_derived.worker import pending_status

    found = run_connected(ctx, pending_status)
    pending = found["pending"]
    typer.echo(f"pending: {pending['pending']} heads ({pending['claimed']} claimed)")
    for name, checked in DerivedRegistry.checked.items():
        state = found["rules"].get(name)
        if state is None:
            typer.echo(f"  {name}: not built")
            continue
        current = (
            "" if state["hash"] == checked.hash else " (changed since: to build again)"
        )
        overflows = (
            f", {state['overflows']} seeds over the limit"
            if state.get("overflows")
            else ""
        )
        typer.echo(f"  {name}: {state['state']}{current}{overflows}")
    for name in found["rules"]:
        if name not in DerivedRegistry.checked:
            typer.echo(
                f"  {name}: removed (what it derived is deleted when the worker starts)"
            )


@cli.command()
def graph(
    ctx: typer.Context,
    type_name: str = typer.Argument(help="A type of rule (RuleType)"),
    plain: bool = typer.Option(
        False, "--plain-only", help="Only facts with a plain justification"
    ),
    as_csv: bool = typer.Option(
        False,
        "--csv",
        help="An edge list (source, target, class, justifications, plain, context)",
    ),
) -> None:
    """The facts derived by the rules of a type, as a graph of edges between their two ends"""
    from pangloss_derived import read

    edges = run_connected(ctx, lambda: read.graph(type_name, plain_only=plain))
    if as_csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "source",
                "source_label",
                "target",
                "target_label",
                "class",
                "justifications",
                "plain",
                "context",
            ]
        )
        for e in edges:
            writer.writerow(
                [
                    e["source"]["id"],
                    e["source"]["label"],
                    e["target"]["id"],
                    e["target"]["label"],
                    e["class"],
                    e["justifications"],
                    e["plain"],
                    "|".join(e["context_labels"]),
                ]
            )
        return
    json.dump({"type": type_name, "edges": edges}, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


@cli.command("worker")
def run_worker(
    ctx: typer.Context,
    batch: int = typer.Option(200, "--batch", help="Heads claimed at once"),
) -> None:
    """Run the worker until stopped (Ctrl-C). Only one works at a time: a second waits for the first's lease"""
    from pangloss_derived.worker import worker

    worker.settings.batch = batch

    async def run() -> None:
        try:
            await worker.run()
        except asyncio.CancelledError:
            pass

    try:
        run_connected(ctx, run)
    except KeyboardInterrupt:
        typer.echo("stopped")
