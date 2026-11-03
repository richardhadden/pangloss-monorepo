import type { Colour } from "../types";

// (whole class names, so that Tailwind finds them)
const TINTS: Record<Colour, string> = {
  slate: "bg-slate-400/25 text-slate-950",
  gray: "bg-gray-400/25 text-gray-950",
  zinc: "bg-zinc-400/25 text-zinc-950",
  neutral: "bg-neutral-400/25 text-neutral-950",
  stone: "bg-stone-400/25 text-stone-950",
  mauve: "bg-mauve-400/25 text-mauve-950",
  olive: "bg-olive-400/25 text-olive-950",
  mist: "bg-mist-400/25 text-mist-950",
  taupe: "bg-taupe-400/25 text-taupe-950",
  red: "bg-red-400/25 text-red-950",
  orange: "bg-orange-400/25 text-orange-950",
  amber: "bg-amber-400/25 text-amber-950",
  yellow: "bg-yellow-400/25 text-yellow-950",
  lime: "bg-lime-400/25 text-lime-950",
  green: "bg-green-400/25 text-green-950",
  emerald: "bg-emerald-400/25 text-emerald-950",
  teal: "bg-teal-400/25 text-teal-950",
  cyan: "bg-cyan-400/25 text-cyan-950",
  sky: "bg-sky-400/25 text-sky-950",
  blue: "bg-blue-400/25 text-blue-950",
  indigo: "bg-indigo-400/25 text-indigo-950",
  violet: "bg-violet-400/25 text-violet-950",
  purple: "bg-purple-400/25 text-purple-950",
  fuchsia: "bg-fuchsia-400/25 text-fuchsia-950",
  pink: "bg-pink-400/25 text-pink-950",
  rose: "bg-rose-400/25 text-rose-950",
};

/** The tint of a colour a model chose (`InterfaceMeta(colour=...)`), or "" if it chose none */
export function colourTint(colour: Colour | null | undefined): string {
  return colour ? TINTS[colour] : "";
}

// (a reified relation that is a document is coloured as a document)
const isDocument = (kind: string | undefined) => kind === "Document" || kind === "ReifiedRelationDocument";

/**
 * The tint behind the name of a type: the colour its model chose, or else by what kind of
 * model it is: Entities are blue and Documents (and reified relations that are documents) green.
 * The theme of the interface; anything that shows a type uses it. (Whole class names, so that
 * Tailwind finds them.)
 */
export function kindTint(kind: string | undefined, colour?: Colour | null): string {
  if (colour) return TINTS[colour];
  if (kind === "Entity") return "bg-sky-400/25 text-sky-950";
  if (isDocument(kind)) return "bg-green-400/25 text-green-950";
  return "";
}

// (for a semantic space that has no colour of its own, by how deep it is)
const DEPTH_TINTS = [
  "bg-amber-400/25 text-amber-950",
  "bg-violet-400/25 text-violet-950",
  "bg-rose-400/25 text-rose-950",
  "bg-teal-400/25 text-teal-950",
];

/**
 * The tint of a semantic space round an item: the colour its model chose, else one by how
 * deep it is (`depth` 0 is the outermost). Wherever the spaces of an item are shown, they
 * use this, so they look alike.
 */
export function spaceTint(colour: Colour | null | undefined, depth: number): string {
  return colourTint(colour) || DEPTH_TINTS[depth % DEPTH_TINTS.length];
}

// (the same colours as a rule: the line down the side of what is nested in a form)
const RULES: Record<Colour, string> = {
  slate: "border-slate-400/60",
  gray: "border-gray-400/60",
  zinc: "border-zinc-400/60",
  neutral: "border-neutral-400/60",
  stone: "border-stone-400/60",
  mauve: "border-mauve-400/60",
  olive: "border-olive-400/60",
  mist: "border-mist-400/60",
  taupe: "border-taupe-400/60",
  red: "border-red-400/60",
  orange: "border-orange-400/60",
  amber: "border-amber-400/60",
  yellow: "border-yellow-400/60",
  lime: "border-lime-400/60",
  green: "border-green-400/60",
  emerald: "border-emerald-400/60",
  teal: "border-teal-400/60",
  cyan: "border-cyan-400/60",
  sky: "border-sky-400/60",
  blue: "border-blue-400/60",
  indigo: "border-indigo-400/60",
  violet: "border-violet-400/60",
  purple: "border-purple-400/60",
  fuchsia: "border-fuchsia-400/60",
  pink: "border-pink-400/60",
  rose: "border-rose-400/60",
};

/**
 * The rule down the left of a nested item in a form, in the colour of its type's tint: the
 * colour its model chose, else Entities sky and Documents (and reified relations that are
 * documents) green; anything else slate.
 */
export function kindRule(kind: string | undefined, colour?: Colour | null): string {
  if (colour) return RULES[colour];
  if (kind === "Entity") return RULES.sky;
  if (isDocument(kind)) return RULES.green;
  return "border-slate-400/60";
}
