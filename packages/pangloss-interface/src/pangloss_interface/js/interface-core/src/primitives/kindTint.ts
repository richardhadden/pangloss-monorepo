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

/**
 * The tint behind the name of a type: the colour its model chose, or else by what kind of
 * model it is: Entities are blue and Documents green. The theme of the interface; anything
 * that shows a type uses it. (Whole class names, so that Tailwind finds them.)
 */
export function kindTint(kind: string | undefined, colour?: Colour | null): string {
  if (colour) return TINTS[colour];
  if (kind === "Entity") return "bg-sky-400/25 text-sky-950";
  if (kind === "Document") return "bg-green-400/25 text-green-950";
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
