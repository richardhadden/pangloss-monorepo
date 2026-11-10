import type { Colour } from "../types";

// (whole class names, so that Tailwind finds them)
const TINTS: Record<Colour, string> = {
  slate: "bg-slate-200 text-slate-950",
  gray: "bg-gray-200 text-gray-950",
  zinc: "bg-zinc-200 text-zinc-950",
  neutral: "bg-neutral-200 text-neutral-950",
  stone: "bg-stone-200 text-stone-950",
  mauve: "bg-mauve-200 text-mauve-950",
  olive: "bg-olive-200 text-olive-950",
  mist: "bg-mist-200 text-mist-950",
  taupe: "bg-taupe-200 text-taupe-950",
  red: "bg-red-200 text-red-950",
  orange: "bg-orange-200 text-orange-950",
  amber: "bg-amber-200 text-amber-950",
  yellow: "bg-yellow-200 text-yellow-950",
  lime: "bg-lime-200 text-lime-950",
  green: "bg-green-200 text-green-950",
  emerald: "bg-emerald-200 text-emerald-950",
  teal: "bg-teal-200 text-teal-950",
  cyan: "bg-cyan-200 text-cyan-950",
  sky: "bg-sky-200 text-sky-950",
  blue: "bg-blue-200 text-blue-950",
  indigo: "bg-indigo-200 text-indigo-950",
  violet: "bg-violet-200 text-violet-950",
  purple: "bg-purple-200 text-purple-950",
  fuchsia: "bg-fuchsia-200 text-fuchsia-950",
  pink: "bg-pink-200 text-pink-950",
  rose: "bg-rose-200 text-rose-950",
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
  if (kind === "Entity") return "bg-sky-200 text-sky-950";
  if (isDocument(kind)) return "bg-green-200 text-green-950";
  return "";
}

// (the same colours, solid: a type that is chosen, among others to choose from, in white on its colour; a light hue
// (yellow, amber, lime), which would be brown so dark, is its bright colour with dark text instead)
const SOLIDS: Record<Colour, string> = {
  slate: "border-slate-800 bg-slate-700 text-white",
  gray: "border-gray-800 bg-gray-700 text-white",
  zinc: "border-zinc-800 bg-zinc-700 text-white",
  neutral: "border-neutral-800 bg-neutral-700 text-white",
  stone: "border-stone-800 bg-stone-700 text-white",
  mauve: "border-mauve-800 bg-mauve-700 text-white",
  olive: "border-olive-800 bg-olive-700 text-white",
  mist: "border-mist-800 bg-mist-700 text-white",
  taupe: "border-taupe-800 bg-taupe-700 text-white",
  red: "border-red-800 bg-red-700 text-white",
  orange: "border-orange-800 bg-orange-700 text-white",
  amber: "border-amber-700 bg-amber-400 text-amber-950",
  yellow: "border-yellow-700 bg-yellow-400 text-yellow-950",
  lime: "border-lime-700 bg-lime-400 text-lime-950",
  green: "border-green-800 bg-green-700 text-white",
  emerald: "border-emerald-800 bg-emerald-700 text-white",
  teal: "border-teal-800 bg-teal-700 text-white",
  cyan: "border-cyan-800 bg-cyan-700 text-white",
  sky: "border-sky-800 bg-sky-700 text-white",
  blue: "border-blue-800 bg-blue-700 text-white",
  indigo: "border-indigo-800 bg-indigo-700 text-white",
  violet: "border-violet-800 bg-violet-700 text-white",
  purple: "border-purple-800 bg-purple-700 text-white",
  fuchsia: "border-fuchsia-800 bg-fuchsia-700 text-white",
  pink: "border-pink-800 bg-pink-700 text-white",
  rose: "border-rose-800 bg-rose-700 text-white",
};

/**
 * A type chosen among others (a chip pressed): its colour, solid, the text white, and a darker frame. The colour its
 * model chose, or else by its kind, as `kindTint`; a type with neither is slate. (Whole class names, so that Tailwind
 * finds them.)
 */
export function kindSolid(kind: string | undefined, colour?: Colour | null): string {
  if (colour) return SOLIDS[colour];
  if (kind === "Entity") return SOLIDS.sky;
  if (isDocument(kind)) return SOLIDS.green;
  return SOLIDS.slate;
}

// (the same colours, lighter, for a semantic space: a box with no line round it)
const SPACE_TINTS: Record<Colour, string> = {
  slate: "bg-slate-400/15 text-slate-950",
  gray: "bg-gray-400/15 text-gray-950",
  zinc: "bg-zinc-400/15 text-zinc-950",
  neutral: "bg-neutral-400/15 text-neutral-950",
  stone: "bg-stone-400/15 text-stone-950",
  mauve: "bg-mauve-400/15 text-mauve-950",
  olive: "bg-olive-400/15 text-olive-950",
  mist: "bg-mist-400/15 text-mist-950",
  taupe: "bg-taupe-400/15 text-taupe-950",
  red: "bg-red-400/15 text-red-950",
  orange: "bg-orange-400/15 text-orange-950",
  amber: "bg-amber-400/15 text-amber-950",
  yellow: "bg-yellow-400/15 text-yellow-950",
  lime: "bg-lime-400/15 text-lime-950",
  green: "bg-green-400/15 text-green-950",
  emerald: "bg-emerald-400/15 text-emerald-950",
  teal: "bg-teal-400/15 text-teal-950",
  cyan: "bg-cyan-400/15 text-cyan-950",
  sky: "bg-sky-400/15 text-sky-950",
  blue: "bg-blue-400/15 text-blue-950",
  indigo: "bg-indigo-400/15 text-indigo-950",
  violet: "bg-violet-400/15 text-violet-950",
  purple: "bg-purple-400/15 text-purple-950",
  fuchsia: "bg-fuchsia-400/15 text-fuchsia-950",
  pink: "bg-pink-400/15 text-pink-950",
  rose: "bg-rose-400/15 text-rose-950",
};

// (for a semantic space that has no colour of its own, by how deep it is)
const DEPTH_TINTS = [SPACE_TINTS.amber, SPACE_TINTS.violet, SPACE_TINTS.rose, SPACE_TINTS.teal];

/**
 * The tint of a semantic space round an item: the colour its model chose, else one by how
 * deep it is (`depth` 0 is the outermost), lighter than the tint of a type. Wherever the spaces
 * of an item are shown, they use this, so they look alike.
 */
export function spaceTint(colour: Colour | null | undefined, depth: number): string {
  return colour ? SPACE_TINTS[colour] : DEPTH_TINTS[depth % DEPTH_TINTS.length]!;
}

// (the same colours as a rule: the line down the side of what is nested in a form)
const RULES: Record<Colour, string> = {
  slate: "border-slate-400/60",
  gray: "border-gray-600/40",
  zinc: "border-zinc-600/40",
  neutral: "border-neutral-600/40",
  stone: "border-stone-600/40",
  mauve: "border-mauve-600/40",
  olive: "border-olive-600/40",
  mist: "border-mist-600/40",
  taupe: "border-taupe-600/40",
  red: "border-red-600/40",
  orange: "border-orange-600/40",
  amber: "border-amber-600/40",
  yellow: "border-yellow-600/40",
  lime: "border-lime-600/40",
  green: "border-green-600/40",
  emerald: "border-emerald-600/40",
  teal: "border-teal-600/40",
  cyan: "border-cyan-600/40",
  sky: "border-sky-600/40",
  blue: "border-blue-600/40",
  indigo: "border-indigo-600/40",
  violet: "border-violet-600/40",
  purple: "border-purple-600/40",
  fuchsia: "border-fuchsia-600/40",
  pink: "border-pink-600/40",
  rose: "border-rose-600/40",
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
