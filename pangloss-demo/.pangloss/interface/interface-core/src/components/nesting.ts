import { createContext, useContext } from "solid-js";

/**
 * How many blocks (a document inside a document, a reified relation, a conjunction) a thing is inside: each
 * block gives what is in it one more. A block `FOLD_FROM` deep starts folded, in the view and in the form, and
 * what it holds is not made until it is unfolded; unfolded, it shows the next `FOLD_EVERY` levels, and the one
 * after them starts folded again.
 *
 * (Documents nest without limit, and each level costs the browser hundreds of synchronous frames to make: a chain
 * of sixty reached the limit of the call stack, in the browser and on the server, where one request took minutes
 * (PROBLEMS.md #38, #39 of the smoke test). Unfolding starts a new stack from the click, so what is shown at once is
 * what is bounded, not the depth. Five levels is also about as deep as the indentation leaves room for.)
 */
const NestingContext = createContext(0);

export const FOLD_FROM = 5;
export const FOLD_EVERY = 5;

export const useNesting = () => useContext(NestingContext);
// (in Solid 2 the context is its own provider: `<NestingProvider value={n}>`)
export const NestingProvider = NestingContext;

export const startsFolded = (depth: number) => depth >= FOLD_FROM && (depth - FOLD_FROM) % FOLD_EVERY === 0;

/**
 * The id of a part of the item that the page is to show (`?show=<id>` of the edit page): a block that starts
 * folded but has it inside starts open instead, so that it can be scrolled to.
 */
// (an accessor: the page can stay as one item follows another, and a block asks when it is made)
const RevealContext = createContext<() => string | null>(() => null);

export const useRevealed = () => useContext(RevealContext);
export const RevealProvider = RevealContext;

/** Whether something with the id `id` is in `value`, at any depth */
export function holdsId(value: unknown, id: string): boolean {
  if (Array.isArray(value)) return value.some((item) => holdsId(item, id));
  if (typeof value !== "object" || value === null) return false;
  const object = value as Record<string, unknown>;
  if (object.id === id) return true;
  return Object.values(object).some((inner) => typeof inner === "object" && inner !== null && holdsId(inner, id));
}
