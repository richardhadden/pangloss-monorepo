"""The check for references left on merged entities (and for citations of what has been removed), as a job on the admin page (found by `pangloss_admin`; nothing
else imports this module). It reports, as `pangloss check-data` does, and moves nothing: a job does not know who
started it, and a move is a write made by someone (`pangloss check-data --move-merged --user U`)."""

from pangloss_admin import JobContext, JobKind
from pangloss_core import storage_of


async def run_check_merged(context: JobContext) -> None:
    operations = storage_of().operations
    if not hasattr(operations, "stray_references"):
        raise RuntimeError("The storage of this project cannot merge entities")
    context.progress(1, 3, "references on merged entities")
    strays = await operations.stray_references()
    context.progress(2, 3, "merges that stopped part of the way")
    unfinished = await operations.unfinished_merges()
    # (citations, `Cites[...]`, of what an admin has removed since: not wrong, but someone should look)
    context.progress(3, 3, "citations of what has been removed")
    lost = (
        await operations.citations_pointing_at_nothing()
        if hasattr(operations, "citations_pointing_at_nothing")
        else []
    )
    report = context.directory / "merged-references.txt"
    lines = (
        [
            f"{stray.head_type} {stray.head}: {stray.source_type}.{stray.field} -> "
            f"{stray.absorbed_type} {stray.absorbed} ({stray.absorbed_label}), merged into {stray.survivor}"
            + ("" if stray.merge else "; no merge of it stands")
            for stray in strays
        ]
        + [
            f"Merge {merge.id} ({merge.absorbed_label} into {merge.survivor_label}) stopped part of the way"
            for merge in unfinished
        ]
        + [
            f"{row['type']} {row['id']} ({row['label']}) cites {row['target_type']} {row['target']}, which has been "
            "removed"
            for row in lost
        ]
    )
    if lines:
        report.write_text("\n".join(lines) + "\n")
    context.progress(
        3,
        3,
        counts={
            "strays": len(strays),
            "unfinished": len(unfinished),
            "citations": len(lost),
        },
    )


jobs = [JobKind("check_merged", run_check_merged)]
