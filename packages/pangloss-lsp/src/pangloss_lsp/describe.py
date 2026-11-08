"""What to say of a model where its name is hovered."""

from typing import Any

SHOWN = 6


def model_markdown(
    name: str, model: dict[str, Any], references: list[dict[str, Any]]
) -> str:
    """The kind, the docstring, the classes above it, its indexes, and the fields that can hold it"""
    kind = model.get("kind") or "model"
    abstract = "abstract " if model.get("abstract") else ""
    parts = [f"**{name}**: {abstract}{kind.lower()}"]
    if model.get("doc"):
        parts.append(model["doc"])

    facts = []
    if model.get("above"):
        facts.append("Above it: " + ", ".join(f"`{n}`" for n in model["above"]))
    if model.get("indexes"):
        facts.append("Indexed: " + ", ".join(f"`{n}`" for n in model["indexes"]))
    fields = model.get("fields") or {}
    if fields:
        relations = sum(1 for kind in fields.values() if kind == "relation")
        facts.append(
            f"{len(fields)} field{'s' if len(fields) != 1 else ''}"
            + (f", {relations} of them relations" if relations else "")
        )
    if facts:
        parts.append("  \n".join(facts))

    if references:
        held = [
            f"`{r['label']}`" + (f" (as a `{r['via']}`)" if r.get("via") else "")
            for r in references[:SHOWN]
        ]
        more = len(references) - SHOWN
        parts.append(
            f"Can be held by {len(references)} field{'s' if len(references) != 1 else ''}: "
            + ", ".join(held)
            + (f", and {more} more (find references lists them)" if more > 0 else "")
        )
    else:
        parts.append("No relation field can hold it.")
    return "\n\n".join(parts)
