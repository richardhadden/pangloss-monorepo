/**
 * The tint behind the name of a type, by what kind of model it is: Entities are blue and
 * Documents green. The theme of the interface; anything that shows a type uses it.
 * (Whole class names, so that Tailwind finds them.)
 */
export function kindTint(kind: string | undefined): string {
  if (kind === "Entity") return "bg-sky-400/25 text-sky-950";
  if (kind === "Document") return "bg-green-400/25 text-green-950";
  return "";
}
